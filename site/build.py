"""Build the recap site from data/ facts + recaps/ writeups.

Writes two self-contained single-file sites (pages are hash routes inside one HTML file):
  site/dist/index.html    league site: only weeks whose recap has "status": "published"
  site/dist/preview.html  Maya's review copy: published + draft weeks (drafts are marked)

Season stats (standings, all-play, streaks, team pages) are computed only from the
weeks included in each output, so the league site never leaks a draft week's results.

Usage: python3 site/build.py [--season 2026]
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
LEAGUE = json.loads((ROOT / "league.json").read_text())

AWARD_KEYS = ("game_balls", "flags", "tough_breaks")
PLAYER_KEYS = ("name", "pos", "slot", "points", "projected")


def side(t):
    return {
        "team_id": t["team_id"], "manager": t["manager"], "team_name": t["team_name"],
        "points": t["points"], "projected": t["projected"], "optimal": t["optimal_points"],
        "points_left": t["points_left_on_bench"], "result": t["result"],
        "swaps": [{k: s[k] for k in ("started", "started_points", "benched", "benched_points", "slot", "gain")}
                  for s in t["lineup_swaps"]],
        "starters": [{k: p[k] for k in PLAYER_KEYS} for p in t["starters"]],
        "bench": [{k: p[k] for k in PLAYER_KEYS} for p in t["bench"]],
    }


def week_payload(facts, recap):
    teams = {t["team_id"]: t for t in facts["teams"]}
    games, seen = [], set()
    for t in facts["teams"]:
        key = tuple(sorted((t["team_id"], t["opponent_id"])))
        if key in seen:
            continue
        seen.add(key)
        a, b = teams[key[0]], teams[key[1]]
        winner, loser = (a, b) if a["points"] >= b["points"] else (b, a)
        games.append({"key": f"{key[0]}-{key[1]}", "winner": side(winner), "loser": side(loser),
                      "blurb": recap.get("matchups", {}).get(f"{key[0]}-{key[1]}", "")})
    games.sort(key=lambda g: g["winner"]["points"] + g["loser"]["points"], reverse=True)

    lg = facts["league"]
    return {
        "week": facts["week"],
        "status": recap.get("status", "draft"),
        "complete": facts["complete"],
        "headline": recap.get("headline", ""),
        "dek": recap.get("dek", ""),
        "games": games,
        **{k: recap.get(k, []) for k in AWARD_KEYS},
        "glossary": recap.get("glossary", []),
        "standings": facts["standings"],
        "top_performers": lg["top_performers"],
        "high_score": lg["high_score"],
        "low_score": lg["low_score"],
        "median": lg["median_score"],
    }


def season_payload(facts_list, weeks):
    """Season-to-date stats per team, from the included weeks only."""
    teams = {t["team_id"]: {"team_id": t["team_id"], "manager": t["manager"].split(" (")[0],
                            "team_name": t["team_name"]} for t in LEAGUE["teams"]}
    for s in teams.values():
        s.update(wins=0, losses=0, ties=0, points_for=0.0, points_against=0.0, all_play_w=0, all_play_l=0,
                 bench_left=0.0, weekly=[], rank_history=[], awards=[])
    n_teams = len(teams)

    for facts in facts_list:
        wk = facts["week"]
        for t in facts["teams"]:
            s = teams[t["team_id"]]
            s["points_for"] = round(s["points_for"] + t["points"], 2)
            s["points_against"] = round(s["points_against"] + t["opponent_points"], 2)
            s["wins"] += t["result"] == "W"
            s["losses"] += t["result"] == "L"
            s["ties"] += t["result"] == "T"
            s["all_play_w"] += n_teams - t["score_rank"]
            s["all_play_l"] += t["score_rank"] - 1
            s["bench_left"] = round(s["bench_left"] + t["points_left_on_bench"], 2)
            s["weekly"].append({"week": wk, "points": t["points"], "opponent_id": t["opponent_id"],
                                "opponent": teams[t["opponent_id"]]["manager"], "opponent_points": t["opponent_points"],
                                "result": t["result"], "score_rank": t["score_rank"],
                                "points_left": t["points_left_on_bench"],
                                "game_key": "-".join(map(str, sorted((t["team_id"], t["opponent_id"]))))})
        for rank, row in enumerate(facts["standings"], 1):
            teams[row["team_id"]]["rank_history"].append({"week": wk, "rank": rank})

    by_manager = {s["manager"]: s for s in teams.values()}
    for w in weeks:
        for kind in AWARD_KEYS:
            for a in w[kind]:
                if a["manager"] in by_manager:
                    by_manager[a["manager"]]["awards"].append({"week": w["week"], "kind": kind, "title": a["title"]})

    for s in teams.values():
        streak = ""
        for g in reversed(s["weekly"]):
            if not streak:
                streak = g["result"]
                count = 1
            elif g["result"] == streak:
                count += 1
            else:
                break
        s["streak"] = f"{streak}{count}" if streak in ("W", "L") else ""
        games = len(s["weekly"])
        s["avg"] = round(s["points_for"] / games, 2) if games else 0
        s["best"] = max(s["weekly"], key=lambda g: g["points"]) if games else None

    table = sorted(teams.values(), key=lambda s: (s["wins"] + 0.5 * s["ties"], s["points_for"]), reverse=True)
    return {"standings": table, "weeks_played": [f["week"] for f in facts_list]}


def render(recap_weeks, preview):
    included = [(f, w) for f, w in recap_weeks if preview or w["status"] == "published"]
    weeks = [w for _, w in included]
    data = {
        "league": {"name": LEAGUE["name"].strip(), "season": LEAGUE["season"], "scoring": LEAGUE["scoring"]},
        "preview": preview,
        "weeks": weeks,
        "season": season_payload([f for f, _ in included], weeks),
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = "Flag on the Play Preview" if preview else "Flag on the Play"
    template = (SITE / "template.html").read_text()
    return template.replace("__PAGE_TITLE__", title).replace("__RECAP_DATA__", blob), weeks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=LEAGUE["season"])
    args = ap.parse_args()

    recap_weeks = []
    for recap_path in sorted((ROOT / "recaps" / str(args.season)).glob("week-*.json")):
        recap = json.loads(recap_path.read_text())
        facts_path = ROOT / "data" / str(args.season) / f"week-{recap['week']:02d}" / "facts.json"
        if not facts_path.exists():
            raise SystemExit(f"{recap_path.name}: missing {facts_path.relative_to(ROOT)}; run scripts/analyze.py")
        facts = json.loads(facts_path.read_text())
        recap_weeks.append((facts, week_payload(facts, recap)))
    recap_weeks.sort(key=lambda fw: fw[1]["week"])

    dist = SITE / "dist"
    dist.mkdir(exist_ok=True)
    html, weeks = render(recap_weeks, preview=False)
    (dist / "index.html").write_text(html)
    print(f"index.html: weeks {[w['week'] for w in weeks] or 'none yet'}")
    html, weeks = render(recap_weeks, preview=True)
    (dist / "preview.html").write_text(html)
    print(f"preview.html: weeks {[(w['week'], w['status']) for w in weeks]}")


if __name__ == "__main__":
    main()
