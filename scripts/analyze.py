"""Turn captured ESPN weeks into the facts every recap callout is built on.

Reads  data/<season>/week-NN/espn.json (from scripts/capture.js)
Writes data/<season>/week-NN/facts.json

Every number in a recap should trace back to a field here.

Usage: python3 scripts/analyze.py [--season 2026] [--week N]   (default: all captured weeks)
"""

import argparse
import json
import urllib.request
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEAGUE = json.loads((ROOT / "league.json").read_text())
MANAGER = {t["team_id"]: t["manager"].split(" (")[0] for t in LEAGUE["teams"]}
TEAM_NAME = {t["team_id"]: t["team_name"] for t in LEAGUE["teams"]}

# Starting slots and which positions can fill them
SLOTS = [("QB", {"QB"}), ("RB", {"RB"}), ("RB", {"RB"}), ("WR", {"WR"}), ("WR", {"WR"}),
         ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}), ("DST", {"DST"}), ("K", {"K"})]
STARTING = {"QB", "RB", "WR", "TE", "FLEX", "DST", "K"}
SLOT_OK = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
           "FLEX": {"RB", "WR", "TE"}, "DST": {"DST"}, "K": {"K"}}

NAME_CACHE = ROOT / "data" / "player_names.json"

# ESPN serves every athlete's photo from one public CDN path, keyed by the same player id
# the fantasy API uses. A D/ST has no photo, so it gets its team's logo instead: its
# fantasy player id is -16000 minus the pro team id, so go by pro_team_id.
HEADSHOT_URL = "https://a.espncdn.com/i/headshots/nfl/players/full/{}.png"
TEAM_LOGO_URL = "https://a.espncdn.com/i/teamlogos/nfl/500/{}.png"
PRO_TEAM_ABBR = {
    1: "atl", 2: "buf", 3: "chi", 4: "cin", 5: "cle", 6: "dal", 7: "den", 8: "det",
    9: "gb", 10: "ten", 11: "ind", 12: "kc", 13: "lv", 14: "lar", 15: "mia", 16: "min",
    17: "ne", 18: "no", 19: "nyg", 20: "nyj", 21: "phi", 22: "ari", 23: "pit", 24: "lac",
    25: "sf", 26: "sea", 27: "tb", 28: "wsh", 29: "car", 30: "jax", 33: "bal", 34: "hou",
}


def headshot(player):
    """Photo URL for a player, team logo for a D/ST, None when we can't name the team.

    ESPN 404s players it has no photo for yet (rookies, practice-squad call-ups), so the
    site falls back to a silhouette on image error rather than checking each URL here.
    """
    if player["pos"] == "DST":
        abbr = PRO_TEAM_ABBR.get(player.get("pro_team_id"))
        return TEAM_LOGO_URL.format(abbr) if abbr else None
    return HEADSHOT_URL.format(player["player_id"])


# ---------- player names (ESPN public athlete API, cached) ----------

def resolve_names(weeks):
    cache = json.loads(NAME_CACHE.read_text()) if NAME_CACHE.exists() else {}
    changed = False
    for w in weeks:
        for t in w["transactions"]:
            for i in t["items"]:
                if not i["name"].startswith(("Player ", "DST ")):
                    continue
                pid = str(i["player_id"])
                if pid not in cache:
                    try:
                        url = f"https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{pid}"
                        with urllib.request.urlopen(url, timeout=10) as r:
                            cache[pid] = json.load(r)["athlete"]["displayName"]
                        changed = True
                    except Exception:  # noqa: BLE001 - leave the placeholder name
                        continue
                i["name"] = cache[pid]
    if changed:
        try:
            NAME_CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
        except OSError:
            # /api/live runs this on Vercel, where the bundle is read-only. Losing the
            # cache write there only costs a repeat lookup on the next cold start.
            pass


# ---------- lineup math ----------

def optimal_lineup(roster):
    """Best possible starting lineup from the non-IR roster, by actual points."""
    pool = [p for p in roster if p["slot"] != "IR"]
    # Fill fixed slots greedily by position, then FLEX from leftovers. With one
    # FLEX this is exact: FLEX takes the best remaining RB/WR/TE.
    used, picks = set(), []
    for slot, ok in SLOTS:
        if slot == "FLEX":
            continue
        cands = sorted((p for p in pool if p["pos"] in ok and p["player_id"] not in used),
                       key=lambda p: p["points"], reverse=True)
        if cands:
            used.add(cands[0]["player_id"])
            picks.append((slot, cands[0]))
    flex = sorted((p for p in pool if p["pos"] in SLOT_OK["FLEX"] and p["player_id"] not in used),
                  key=lambda p: p["points"], reverse=True)
    if flex:
        picks.append(("FLEX", flex[0]))
    best_total = round(sum(p["points"] for _, p in picks), 2)
    best = [{"slot": s, "name": p["name"], "points": p["points"]} for s, p in picks]
    return best_total, best


def worst_bench_call(roster):
    """Single benched player who most outscored a starter they could have replaced."""
    starters = [p for p in roster if p["slot"] in STARTING]
    bench = [p for p in roster if p["slot"] == "BENCH"]
    worst = None
    for b in bench:
        for s in starters:
            if b["pos"] in SLOT_OK[s["slot"]]:
                gap = round(b["points"] - s["points"], 2)
                if gap > 0 and (worst is None or gap > worst["gap"]):
                    worst = {"benched": b["name"], "benched_points": b["points"], "benched_projected": b["projected"],
                             "started": s["name"], "started_points": s["points"], "started_projected": s["projected"],
                             "slot": s["slot"], "gap": gap}
    return worst


# ---------- transactions ----------

def lineup_swaps(week, team_id, roster):
    """Pair same-transaction lineup moves (X in, Y out) and score the decision.

    Only swaps that stuck count: X must be starting and Y benched in the final lineup.
    """
    points_by_id = {p["player_id"]: p["points"] for p in roster}
    final_slot = {p["player_id"]: p["slot"] for p in roster}
    swaps = []
    for t in week["transactions"]:
        if t["type"] not in ("ROSTER", "FUTURE_ROSTER") or t["team_id"] != team_id:
            continue
        ins = [i for i in t["items"] if i["type"] == "LINEUP" and i["to_slot"] in STARTING and i["from_slot"] == "BENCH"]
        outs = [i for i in t["items"] if i["type"] == "LINEUP" and i["from_slot"] in STARTING and i["to_slot"] == "BENCH"]
        for i in ins:
            o = next((o for o in outs if o["from_slot"] == i["to_slot"]), None)
            if not o or i["player_id"] not in points_by_id or o["player_id"] not in points_by_id:
                continue
            if final_slot[i["player_id"]] not in STARTING or final_slot[o["player_id"]] != "BENCH":
                continue
            gain = round(points_by_id[i["player_id"]] - points_by_id[o["player_id"]], 2)
            swaps.append({"date": t["date"], "started": i["name"], "started_points": points_by_id[i["player_id"]],
                          "benched": o["name"], "benched_points": points_by_id[o["player_id"]],
                          "slot": i["to_slot"], "gain": gain})
    # Keep only the final state per player pair if they flip-flopped
    seen, final = set(), []
    for s in reversed(swaps):
        key = frozenset((s["started"], s["benched"]))
        if key not in seen:
            seen.add(key)
            final.append(s)
    return list(reversed(final))


def season_adds(weeks_upto):
    """Players each team added via waivers/free agency, and when."""
    adds = {}
    for w in weeks_upto:
        for t in w["transactions"]:
            if t["type"] not in ("FREEAGENT", "WAIVER"):
                continue
            for i in t["items"]:
                if i["type"] == "ADD":
                    adds[(t["team_id"], i["player_id"])] = {"week_added": w["week"], "type": t["type"],
                                                            "date": t["date"], "bid": t["bid"]}
    return adds


def season_drops(weeks_upto):
    drops = {}
    for w in weeks_upto:
        for t in w["transactions"]:
            for i in t["items"]:
                if i["type"] == "DROP":
                    drops[i["player_id"]] = {"team_id": t["team_id"], "week_dropped": w["week"], "name": i["name"]}
    return drops


# ---------- main per-week analysis ----------

def analyze(week, history):
    """history: all captured weeks up to and including this one, in order."""
    rosters, teams = {}, []
    for m in week["matchups"]:
        for side, other in (("home", "away"), ("away", "home")):
            s, o = m[side], m[other]
            rosters[s["team_id"]] = s["lineup"]
            won = (m["winner"] == side.upper())
            teams.append({"team_id": s["team_id"], "points": s["points"], "projected": s["projected"],
                          "opponent_id": o["team_id"], "opponent_points": o["points"],
                          "result": "W" if won else ("T" if m["winner"] == "TIE" else ("L" if m["winner"] in ("HOME", "AWAY") else "-")),
                          "margin": round(s["points"] - o["points"], 2),
                          # ESPN's in-week estimate of the final score (points so far + remaining projections)
                          "live_projection": s["projected"], "win_probability": s.get("win_probability")})

    ranked = sorted(teams, key=lambda t: t["points"], reverse=True)
    for rank, t in enumerate(ranked, 1):
        t["score_rank"] = rank

    adds = season_adds(history)
    drops = season_drops(history)
    owner_of = {p["player_id"]: tid for tid, r in rosters.items() for p in r}
    all_players = {p["player_id"]: p for r in rosters.values() for p in r}

    for t in teams:
        r = rosters[t["team_id"]]
        opt_total, opt = optimal_lineup(r)
        t["manager"] = MANAGER[t["team_id"]]
        t["team_name"] = TEAM_NAME[t["team_id"]]
        t["optimal_points"] = opt_total
        t["points_left_on_bench"] = round(opt_total - t["points"], 2)
        t["would_have_won_with_optimal"] = t["result"] == "L" and opt_total > t["opponent_points"]
        t["worst_bench_call"] = worst_bench_call(r)
        t["lineup_swaps"] = lineup_swaps(week, t["team_id"], r)
        t["starters"] = [dict(p, beat_projection=round(p["points"] - (p["projected"] or 0), 2))
                         for p in r if p["slot"] in STARTING]
        # ESPN drops the team projection once games are final; rebuild it from starters
        t["projected"] = round(sum(p["projected"] or 0 for p in t["starters"]), 2)
        t["bench"] = [p for p in r if p["slot"] in ("BENCH", "IR")]
        # Starters with no stats yet this week (game not played yet, or player inactive)
        t["yet_to_play"] = sum(1 for p in t["starters"] if not p["played"])
        t["zero_point_starters"] = [p["name"] for p in r if p["slot"] in STARTING and (not p["played"] or p["points"] == 0)]
        t["pickups_started"] = [dict(name=p["name"], points=p["points"], slot=p["slot"], **adds[(t["team_id"], p["player_id"])])
                                for p in r if p["slot"] in STARTING and (t["team_id"], p["player_id"]) in adds]

    # Players this team dropped earlier who scored for someone else this week
    dropped_regrets = []
    for pid, d in drops.items():
        if pid in owner_of and owner_of[pid] != d["team_id"]:
            p = all_players[pid]
            if p["slot"] in STARTING:
                dropped_regrets.append({"name": p["name"], "points": p["points"], "dropped_by": MANAGER[d["team_id"]],
                                        "week_dropped": d["week_dropped"], "now_with": MANAGER[owner_of[pid]]})
    dropped_regrets.sort(key=lambda x: x["points"], reverse=True)

    starters = [dict(s, manager=t["manager"]) for t in teams for s in t["starters"]]
    median = sorted(t["points"] for t in teams)[len(teams) // 2 - 1: len(teams) // 2 + 1]
    median = round(sum(median) / 2, 2)
    games = [(a, b) for a, b in combinations(teams, 2) if a["opponent_id"] == b["team_id"]]

    league = {
        "high_score": {k: ranked[0][k] for k in ("manager", "points")},
        "low_score": {k: ranked[-1][k] for k in ("manager", "points")},
        "median_score": median,
        "closest_game": min(({"winner": w["manager"], "loser": l["manager"], "margin": abs(w["margin"])}
                             for a, b in games for w, l in [(a, b) if a["margin"] > 0 else (b, a)]),
                            key=lambda g: g["margin"]),
        "biggest_blowout": max(({"winner": w["manager"], "loser": l["manager"], "margin": abs(w["margin"])}
                                for a, b in games for w, l in [(a, b) if a["margin"] > 0 else (b, a)]),
                               key=lambda g: g["margin"]),
        "bad_luck_losses": [{"manager": t["manager"], "points": t["points"], "score_rank": t["score_rank"]}
                            for t in teams if t["result"] == "L" and t["points"] > median],
        "lucky_wins": [{"manager": t["manager"], "points": t["points"], "score_rank": t["score_rank"]}
                       for t in teams if t["result"] == "W" and t["points"] < median],
        "top_performers": [{**{k: s[k] for k in ("name", "manager", "slot", "points", "projected")},
                            "headshot": headshot(s)}
                           for s in sorted(starters, key=lambda s: s["points"], reverse=True)[:5]],
        "biggest_busts": [{k: s[k] for k in ("name", "manager", "slot", "points", "projected", "beat_projection")}
                          for s in sorted(starters, key=lambda s: s["beat_projection"])[:5]],
        "biggest_surprises": [{k: s[k] for k in ("name", "manager", "slot", "points", "projected", "beat_projection")}
                              for s in sorted(starters, key=lambda s: s["beat_projection"], reverse=True)[:5]],
        "most_points_left_on_bench": sorted(({"manager": t["manager"], "points_left": t["points_left_on_bench"],
                                              "would_have_won": t["would_have_won_with_optimal"]} for t in teams),
                                            key=lambda x: x["points_left"], reverse=True),
        "best_pickups": sorted(({**p, "manager": t["manager"]} for t in teams for p in t["pickups_started"]),
                               key=lambda p: p["points"], reverse=True),
        "best_lineup_calls": sorted(({**s, "manager": t["manager"]} for t in teams for s in t["lineup_swaps"] if s["gain"] > 0),
                                    key=lambda s: s["gain"], reverse=True),
        "worst_lineup_calls": sorted(({**s, "manager": t["manager"]} for t in teams for s in t["lineup_swaps"] if s["gain"] < 0),
                                     key=lambda s: s["gain"]),
        "dropped_and_regretted": dropped_regrets,
    }

    # Standings through this week, rebuilt from results
    standings = {tid: {"manager": MANAGER[tid], "team_name": TEAM_NAME[tid], "wins": 0, "losses": 0, "ties": 0,
                       "points_for": 0.0, "points_against": 0.0} for tid in MANAGER}
    for w in history:
        for m in w["matchups"]:
            for side, other in (("home", "away"), ("away", "home")):
                st = standings[m[side]["team_id"]]
                st["points_for"] = round(st["points_for"] + m[side]["points"], 2)
                st["points_against"] = round(st["points_against"] + m[other]["points"], 2)
                if m["winner"] == side.upper():
                    st["wins"] += 1
                elif m["winner"] == "TIE":
                    st["ties"] += 1
                elif m["winner"] in ("HOME", "AWAY"):
                    st["losses"] += 1
    table = sorted(({"team_id": k, **v} for k, v in standings.items()),
                   key=lambda s: (s["wins"] + 0.5 * s["ties"], s["points_for"]), reverse=True)

    return {"season": week["season"], "week": week["week"], "complete": week["complete"],
            "captured_at": week["captured_at"], "league": league, "teams": teams, "standings": table}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=LEAGUE["season"])
    ap.add_argument("--week", type=int)
    args = ap.parse_args()

    season_dir = ROOT / "data" / str(args.season)
    weeks = [json.loads(p.read_text()) for p in sorted(season_dir.glob("week-*/espn.json"))]
    weeks.sort(key=lambda w: w["week"])
    resolve_names(weeks)

    for i, w in enumerate(weeks):
        if args.week and w["week"] != args.week:
            continue
        facts = analyze(w, weeks[: i + 1])
        out = season_dir / f"week-{w['week']:02d}" / "facts.json"
        out.write_text(json.dumps(facts, indent=1, ensure_ascii=False) + "\n")
        flag = "" if w["complete"] else "  (week not final)"
        print(f"week {w['week']}: {out.relative_to(ROOT)}{flag}")


if __name__ == "__main__":
    main()
