#!/usr/bin/env python3
"""Find and score trades for the Coach page: the numbers behind every trade card coach-daily ships.

Two modes, same scoring:

  --scan               every 1-for-1 and 2-for-1 between every pair of teams, scored, best few per team
  --proposals FILE     only the trades in FILE, [{"team_id", "partner_id", "give": [ids], "get": [ids]}]

`team_id` is the team proposing the trade (she sends `give`, receives `get`); `partner_id` is the
other side. Each result says which ground rules it passes and fails, so coach-daily ships only a
trade whose `pass` is true. The rules (numbered as in the coach-daily skill):

  1  both teams' lineups get better: each side's blended weekly gain is at least MIN_GAIN
  2  this week's opponents rank last: flagged `plays_this_week` and sorted after everyone else
  3  the next NEAR_WEEKS weeks count double, and neither side may lose ground over them
  4  no arming a rival (this or next week's opponent, or both teams on the playoff bubble): a rival
     may not gain more from the deal, playoff plus title odds, than the proposer
  5  the proposer's playoff or title odds go up; the partner's go down in neither
  6  fair-looking: the two sides' rest-of-season value within FAIR_GAP of each other
  7  nobody OUT, on IR, or suspended changes hands
  9  1-for-1 or 2-for-1 only
  10 not once ESPN's trade deadline has passed (league.json "trade_deadline", an ISO time with
     its offset) or the regular season is over

Rules 8 (a startable bench player keeps BENCH_SHARE of his value; a team pushed over the roster
limit cuts her least valuable player) and 12 (each side's own gain, reported honestly) are in the
scoring itself, not pass/fail. Rule 11 (stale cards disappear) is site/build.py's job.

Once this week's games have started, the evaluation starts with next week: whatever already
happened this week is banked and can't be traded.

Value is FantasyPros' rest-of-season PPR projection (coach-daily saves get_projections(ros) for
every position to the --ros file), spread evenly over a player's remaining games, with bye weeks
at zero. A rostered player FantasyPros doesn't project falls back to ESPN's projection for the
week, every week. Lineups are this league's slots (league.json), filled optimally.

Usage: python3 scripts/trade_eval.py --ros ros.json --scan [--top 3] [--byes byes.json] [--sims 8000]
       python3 scripts/trade_eval.py --ros ros.json --proposals trades.json
Prints JSON on stdout. Never writes anything.
"""

import argparse
import itertools
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import playoffs  # noqa: E402
from analyze import PRO_TEAM_ABBR  # noqa: E402

LEAGUE = build.LEAGUE

MIN_GAIN = 1.0          # points per week, blended; less than this is projection noise, not a benefit
NEAR_WEEKS = 4          # "the next three to four weeks"
NEAR_WEIGHT = 2         # ...counted double against the rest of the season (a bubble team's view)
BENCH_SHARE = 0.25      # a startable bench player is worth this much of his projection: injury and bye cover
BENCH_DEPTH = 3         # how many bench RB/WR/TE count toward that
FAIR_GAP = 0.15         # most the two sides' rest-of-season value may differ, as a share of the bigger one
ODDS_NOISE = 0.005      # half a percentage point: smaller odds moves than this are the simulation, not the trade
RIVAL_BAND = (0.10, 0.90)  # two teams both this unsure of the playoffs are chasing the same spots
NFL_LAST_WEEK = 18      # FantasyPros' rest-of-season projection runs to the end of the NFL season
UNAVAILABLE = {"OUT", "INJURY_RESERVE", "SUSPENSION"}
SIZES = {(1, 1), (1, 2), (2, 1)}
SCAN_ODDS_PER_TEAM = 12  # scan: most of a team's best lineup trades that get the (slow) playoff simulation
FLEX_POS = {"RB", "WR", "TE"}

# FantasyPros and ESPN spell a few team abbreviations differently
_ABBR_ALIASES = {"jac": "jax", "was": "wsh", "la": "lar"}
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


# ---------- league shape ----------

def slots():
    """[(slot, {positions})] from league.json's roster_slots, fixed slots first, then any flex."""
    fixed, flex = [], []
    for name, count in LEAGUE["roster_slots"].items():
        if name == "BENCH":
            continue
        m = re.match(r"FLEX \((.+)\)", name)
        for _ in range(count):
            if m:
                flex.append(("FLEX", set(m.group(1).split("/"))))
            else:
                fixed.append((name, {name}))
    return fixed + flex


SLOTS = slots()
ROSTER_MAX = sum(LEAGUE["roster_slots"].values())


def last_week():
    """The league's final week: the championship's last week."""
    p = playoffs._config(LEAGUE)
    rounds, size = 0, 1
    while size < p["teams"]:
        size *= 2
        rounds += 1
    return p["first_round_week"] + rounds - 1 + p["championship_weeks"] - 1


# ---------- value ----------

def norm(name):
    name = _SUFFIX.sub("", re.sub(r"[^a-z ]", "", name.lower().replace("-", " ")))
    return " ".join(name.split())


def ros_table(raw):
    """{(normalized name, pos): {"ros", "team"}} from FantasyPros get_projections(ros) output: either a
    list of its responses, one response, or a bare list of its projection rows. D/STs are keyed by team."""
    if isinstance(raw, dict):
        raw = [raw]
    rows = []
    for r in raw:
        rows.extend(r.get("projections", []) if isinstance(r, dict) and "projections" in r else [r])
    out = {}
    for r in rows:
        try:
            pos, team = r["position"], (r.get("team") or "").lower()
            team = _ABBR_ALIASES.get(team, team)
            pts = float(r["stats"]["points_ppr"])
            key = ("dst:" + team, "DST") if pos == "DST" else (norm(r["name"]), pos)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        out[key] = {"ros": pts, "team": team}
    return out


def ros_key(p):
    if p["pos"] == "DST":
        return ("dst:" + (PRO_TEAM_ABBR.get(p.get("pro_team_id")) or ""), "DST")
    return (norm(p["name"]), p["pos"])


def fetch_byes(weeks):
    """{week: {pro team ids playing}} from ESPN's public scoreboard, for the weeks it answers.
    Best effort, like every other scoreboard call here: a week it can't read is just missing."""
    out = {}
    season = LEAGUE["season"]
    for w in weeks:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={season}&seasontype=2&week={w}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                events = json.load(r).get("events") or []
            playing = {int(c["team"]["id"]) for ev in events for c in ev["competitions"][0]["competitors"]}
        except Exception:  # noqa: BLE001 - best effort
            continue
        if playing:
            out[w] = playing
    return out


class Values:
    """Each rostered player's projected points in each remaining week."""

    def __init__(self, players, ros, playing, week):
        self.week = week
        self.playing = playing          # {week: {pro team ids with a game}}; a missing week means unknown
        self.weeks = list(range(week, last_week() + 1))
        self.unmatched = []
        self.rate = {}
        for p in players:
            hit = ros.get(ros_key(p))
            if hit is None:
                self.unmatched.append(p["name"])
                self.rate[p["player_id"]] = float(p.get("projected") or 0.0)
                continue
            games = sum(1 for w in range(week, NFL_LAST_WEEK + 1) if self.plays(p, w)) or 1
            self.rate[p["player_id"]] = hit["ros"] / games
        self.out_now = {p["player_id"] for p in players if p.get("injury_status") in UNAVAILABLE}

    def plays(self, p, w):
        known = self.playing.get(w)
        return known is None or p.get("pro_team_id") in known

    def get(self, p, w):
        if not self.plays(p, w) or (w == self.week and p["player_id"] in self.out_now):
            return 0.0
        return self.rate[p["player_id"]]

    def ros(self, p):
        """Rest-of-season value, for the fairness check: his rate over this league's remaining weeks."""
        return sum(self.get(p, w) for w in self.weeks)


def team_week(roster, vals, w):
    """A roster's worth in week `w`: its best lineup, plus BENCH_SHARE of its best BENCH_DEPTH
    bench RB/WR/TE. Fixed slots fill first, then flex from what's left, which is optimal with a
    single flex slot (league.json has one)."""
    lineup, bench = lineup_and_bench(roster, vals, w)
    return lineup + BENCH_SHARE * bench


def lineup_and_bench(roster, vals, w):
    """(best lineup's points, the bench RB/WR/TE depth team_week() credits a share of)."""
    pool = sorted(((vals.get(p, w), p["player_id"], p["pos"]) for p in roster if p["slot"] != "IR"), reverse=True)
    used, total = set(), 0.0
    for _, ok in SLOTS:
        for v, pid, pos in pool:
            if pid not in used and pos in ok:
                used.add(pid)
                total += v
                break
    bench = [v for v, pid, pos in pool if pid not in used and pos in FLEX_POS][:BENCH_DEPTH]
    return total, sum(bench)


def after_trade(roster, out_ids, incoming, vals, protect):
    """The roster after the trade, with a forced cut when it runs over the limit: the player she'd
    miss least (a backup QB who'd never start before a bench receiver who might), never one she just
    traded for. Returns (roster, cut player or None)."""
    new = [p for p in roster if p["player_id"] not in out_ids] + [dict(p, slot="BENCH") for p in incoming]
    cut = None
    # Only a trade that grows the roster forces a cut; IR spots sit outside league.json's count.
    if len(incoming) > len(out_ids) and sum(p["slot"] != "IR" for p in new) > ROSTER_MAX:
        cands = [p for p in new if p["player_id"] not in protect and p["slot"] != "IR"]
        if cands:
            def without(c):
                rest = [p for p in new if p["player_id"] != c["player_id"]]
                return sum(team_week(rest, vals, w) for w in vals.weeks), -vals.ros(c)
            cut = max(cands, key=without)
            new = [p for p in new if p["player_id"] != cut["player_id"]]
    return new, cut


# ---------- the evaluation ----------

class League:
    """Everything a trade is scored against, loaded once: rosters, values, standings, schedule."""

    def __init__(self, season, ros_raw, byes=None, sims=8000):
        _, captured, ahead, _, _ = build.load_inputs(season)
        done = [f for f, _ in captured if f.get("complete")]
        played = max((f["week"] for f in done), default=0)
        self.week = played + 1
        # Rosters from the freshest capture: next week's, when it's for the week we're scoring
        if ahead and ahead["week"] == self.week:
            src, self.source = ahead, f"next-week capture, {ahead.get('captured_at')}"
        else:
            src = captured[-1][1] if captured else None
            self.source = f"week {src['week']} capture, {src.get('captured_at')}" if src else "none"
        if not src:
            raise SystemExit("no ESPN capture to read rosters from")
        self.rosters = {}
        for m in src["matchups"]:
            for s in (m["home"], m["away"]):
                if s:
                    self.rosters[s["team_id"]] = s["lineup"]
        # Who plays whom, from every capture we have and the optional schedule file
        self.schedule = build.load_schedule(season)
        pairs = {w: list(ps) for w, ps in self.schedule.items()}
        for e in [c for _, c in captured] + ([ahead] if ahead else []):
            pairs[e["week"]] = [(m["home"]["team_id"], m["away"]["team_id"]) for m in e["matchups"]
                                if m.get("home") and m.get("away")]
        opp = {w: {t: o for a, b in ps for t, o in ((a, b), (b, a))} for w, ps in pairs.items()}
        self.opp_now, self.opp_next = opp.get(self.week, {}), opp.get(self.week + 1, {})
        self.opponents_known = [w for w in (self.week, self.week + 1) if opp.get(w)]
        # Once this week's games have started, what's happened is banked: score from next week on
        started = src["week"] == self.week and any(
            p.get("game_state") in ("in", "post") for m in src["matchups"] for s in (m["home"], m["away"]) if s
            for p in s["lineup"])
        first = self.week + 1 if started else self.week

        players = [p for r in self.rosters.values() for p in r]
        if byes is None:
            playing = fetch_byes(range(first, NFL_LAST_WEEK + 1))
        else:
            playing = byes_to_playing(byes, first)
        self.byes_known = sorted(playing)
        self.vals = Values(players, ros_table(ros_raw), playing, first)

        season_rows = build.season_payload(done, [])
        self.standings, self.weeks_played = season_rows["standings"], season_rows["weeks_played"]
        self.sims = sims
        self._base = None
        self._now = {}
        cfg = playoffs._config(LEAGUE)
        self.reg_weeks = [w for w in self.vals.weeks if w <= cfg["regular_season_weeks"]]
        self.deadline = build.trade_deadline()
        self.now = datetime.now(timezone.utc)

    def player(self, team_id, pid):
        return next((p for p in self.rosters.get(team_id, []) if p["player_id"] == pid), None)

    def odds(self, shift):
        res = playoffs.trade_odds(self.standings, self.weeks_played, LEAGUE, shift, self.schedule, self.sims)
        if res and self._base is None:
            self._base = res["before"]
        return res

    def base_odds(self):
        if self._base is None:
            self.odds({})
        return self._base

    def side(self, team_id, out_ids, incoming):
        """One team's numbers: weekly gains (near, rest of season, blended, regular season) and any cut."""
        roster = self.rosters[team_id]
        if team_id not in self._now:
            self._now[team_id] = {w: lineup_and_bench(roster, self.vals, w) for w in self.vals.weeks}
        now = self._now[team_id]
        new, cut = after_trade(roster, set(out_ids), incoming, self.vals, {p["player_id"] for p in incoming})
        after = {w: lineup_and_bench(new, self.vals, w) for w in self.vals.weeks}
        deltas = {w: (after[w][0] + BENCH_SHARE * after[w][1]) - (now[w][0] + BENCH_SHARE * now[w][1])
                  for w in self.vals.weeks}
        near_w = self.vals.weeks[:NEAR_WEEKS]
        near = sum(deltas[w] for w in near_w) / len(near_w)
        ros = sum(deltas.values()) / len(deltas)
        # The odds simulation moves her weekly score, so it gets the lineup's change alone: bench
        # depth is insurance, not points. Regular-season weeks, since those decide the playoffs.
        lineup_w = self.reg_weeks or self.vals.weeks
        reg = sum(after[w][0] - now[w][0] for w in lineup_w) / len(lineup_w)
        return {"near": round(near, 2), "ros": round(ros, 2),
                "blend": round((NEAR_WEIGHT * near + ros) / (NEAR_WEIGHT + 1), 2),
                "_reg": reg, "cut": ({"id": cut["player_id"], "name": cut["name"], "pos": cut["pos"]} if cut else None)}

    def quick(self, team_id, partner_id, give, get):
        """Everything but the playoff simulation: rules 1, 3, 6, 7, 9 and 10. (result, failures)."""
        fails = []
        if team_id == partner_id or team_id not in self.rosters or partner_id not in self.rosters:
            return None, [{"rule": 0, "why": "needs two different teams in this league"}]
        if (len(give), len(get)) not in SIZES:
            fails.append({"rule": 9, "why": "only 1-for-1 and 2-for-1 trades"})
        if self.week > playoffs._config(LEAGUE)["regular_season_weeks"]:
            fails.append({"rule": 10, "why": "the regular season is over"})
        elif build.past_trade_deadline(self.now):
            fails.append({"rule": 10, "why": f"past the trade deadline ({self.deadline:%b %-d, %-I:%M %p})"})
        if any(f["rule"] == 10 for f in fails) or not self.vals.weeks:
            return None, fails or [{"rule": 10, "why": "no weeks left to play"}]
        gp = [self.player(team_id, i) for i in give]
        tp = [self.player(partner_id, i) for i in get]
        if None in gp or None in tp:
            return None, [{"rule": 0, "why": "a player isn't on the roster named"}]
        hurt = [p["name"] for p in gp + tp if p.get("injury_status") in UNAVAILABLE]
        if hurt:
            fails.append({"rule": 7, "why": f"{', '.join(hurt)} can't play right now"})
        v_give, v_get = sum(self.vals.ros(p) for p in gp), sum(self.vals.ros(p) for p in tp)
        gap = abs(v_give - v_get) / max(v_give, v_get, 1e-9)
        if gap > FAIR_GAP:
            fails.append({"rule": 6, "why": "the two sides' rest-of-season value is too far apart"})
        you = self.side(team_id, give, tp)
        them = self.side(partner_id, get, gp)
        for who, s in (("you", you), ("them", them)):
            if s["blend"] < MIN_GAIN:
                fails.append({"rule": 1, "why": f"{who}: the lineup barely improves, or gets worse"})
            if s["near"] <= 0:
                fails.append({"rule": 3, "why": f"{who}: worse over the next {NEAR_WEEKS} weeks"})
        brief = lambda p: {"id": p["player_id"], "name": p["name"], "pos": p["pos"], "ros": round(self.vals.ros(p), 1)}  # noqa: E731
        return {"team_id": team_id, "partner_id": partner_id, "give": [brief(p) for p in gp],
                "get": [brief(p) for p in tp], "value_gap": round(gap, 3), "you": you, "them": them,
                "week": self.week, "flags": {"plays_this_week": self.opp_now.get(team_id) == partner_id}}, fails

    def finish(self, res, fails):
        """The playoff half: rules 2, 4 and 5, on a trade that's already been through quick()."""
        t, o = res["team_id"], res["partner_id"]
        sim = self.odds({t: res["you"].pop("_reg"), o: res["them"].pop("_reg")})
        base = self.base_odds()
        if sim:
            for who, tid in (("you", t), ("them", o)):
                res[who]["playoff"] = [sim["before"][tid]["playoff"], sim["after"][tid]["playoff"]]
                res[who]["title"] = [sim["before"][tid]["title"], sim["after"][tid]["title"]]
            d = {who: (res[who]["playoff"][1] - res[who]["playoff"][0], res[who]["title"][1] - res[who]["title"][0])
                 for who in ("you", "them")}
            if max(d["you"]) < ODDS_NOISE:
                fails.append({"rule": 5, "why": "your playoff and title odds don't go up"})
            if min(d["them"]) < -ODDS_NOISE:
                fails.append({"rule": 5, "why": "their playoff or title odds go down"})
            res["flags"]["rival"] = rival_reason(
                self.opp_now.get(t) == o, self.opp_next.get(t) == o,
                all(RIVAL_BAND[0] < base[i]["playoff"] < RIVAL_BAND[1] for i in (t, o)))
            if res["flags"]["rival"] and sum(d["them"]) > sum(d["you"]) + ODDS_NOISE:
                fails.append({"rule": 4, "why": "arms a rival: her playoff and title odds gain more than yours"})
        else:
            res["flags"]["rival"] = "this_week" if res["flags"]["plays_this_week"] else None
            fails.append({"rule": 5, "why": "no playoff odds to check against (no finished week, or the season's over)"})
        res["you"].pop("_reg", None)
        res["them"].pop("_reg", None)
        res["failures"] = fails
        res["pass"] = not fails
        return res

    def evaluate(self, team_id, partner_id, give, get):
        res, fails = self.quick(team_id, partner_id, give, get)
        if res is None:
            return {"team_id": team_id, "partner_id": partner_id, "give": give, "get": get,
                    "pass": False, "failures": fails}
        return self.finish(res, fails)

    def scan(self, top=3):
        """Every 1-for-1 and 2-for-1 from every team's side, cheap rules first; at most
        SCAN_ODDS_PER_TEAM survivors per team get the playoff simulation. Up to `top` passing
        trades per team, best first."""
        out = {}
        ids = sorted(self.rosters)
        for t in ids:
            cands = []
            mine = [p for p in self.rosters[t] if p["slot"] != "IR"]
            for o in ids:
                if o == t:
                    continue
                theirs = [p for p in self.rosters[o] if p["slot"] != "IR"]
                for ng, nt in SIZES:
                    for give in itertools.combinations(mine, ng):
                        v_give = sum(self.vals.ros(p) for p in give)
                        for get in itertools.combinations(theirs, nt):
                            v_get = sum(self.vals.ros(p) for p in get)
                            if abs(v_give - v_get) > FAIR_GAP * max(v_give, v_get, 1e-9):
                                continue
                            res, fails = self.quick(t, o, [p["player_id"] for p in give], [p["player_id"] for p in get])
                            if res and not fails:
                                cands.append(res)
            # This week's opponent last (rule 2), then the smaller side's gain; simulate down the list
            # until `top` pass or the budget runs out, so a few failures up top can't hide the rest.
            cands.sort(key=lambda r: (r["flags"]["plays_this_week"], -min(r["you"]["blend"], r["them"]["blend"])))
            passed = []
            for r in cands[:SCAN_ODDS_PER_TEAM]:
                if self.finish(r, [])["pass"]:
                    passed.append(r)
                    if len(passed) >= top:
                        break
            out[t] = sorted(passed, key=rank)
        return out


def rival_reason(this_week, next_week, bubble):
    """Why the partner counts as a rival (rule 4), for the card's sticker, or None."""
    return "this_week" if this_week else "next_week" if next_week else "bubble" if bubble else None


def byes_to_playing(byes, first):
    """{"<abbr>": bye week} (ESPN or FantasyPros spelling) as fetch_byes()'s {week: {pro team ids playing}}."""
    ids = {v: k for k, v in PRO_TEAM_ABBR.items()}
    off = {}
    for abbr, week in byes.items():
        a = _ABBR_ALIASES.get(abbr.lower(), abbr.lower())
        if a in ids:
            off.setdefault(int(week), set()).add(ids[a])
    return {w: set(PRO_TEAM_ABBR) - off.get(w, set()) for w in range(first, NFL_LAST_WEEK + 1)}


def rank(r):
    """Best first: not this week's opponent (rule 2), then both teams' odds up, then the smaller
    side's lineup gain."""
    up = lambda s: (s["playoff"][1] - s["playoff"][0]) + (s["title"][1] - s["title"][0])  # noqa: E731
    both_up = up(r["you"]) > ODDS_NOISE and up(r["them"]) > ODDS_NOISE
    return (r["flags"]["plays_this_week"], not both_up, -(up(r["you"]) + up(r["them"])),
            -min(r["you"]["blend"], r["them"]["blend"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--season", type=int, default=LEAGUE["season"])
    ap.add_argument("--ros", required=True, help="FantasyPros get_projections(ros) output, saved as JSON")
    ap.add_argument("--byes", help='a JSON file, or inline JSON, {"<team abbr>": bye week}, instead of asking '
                                   "ESPN's scoreboard")
    ap.add_argument("--sims", type=int, default=8000, help="8000 matches the Standings page's odds")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--scan", action="store_true")
    mode.add_argument("--proposals", help="[{team_id, partner_id, give: [ids], get: [ids]}]")
    ap.add_argument("--top", type=int, default=3)
    args = ap.parse_args()

    byes = None
    if args.byes:
        byes = json.loads(args.byes if args.byes.lstrip().startswith("{") else Path(args.byes).read_text())
    lg = League(args.season, json.loads(Path(args.ros).read_text()), byes=byes, sims=args.sims)
    head = {"week": lg.week, "scored_from_week": lg.vals.week, "rosters": lg.source,
            "opponents_known_for_weeks": lg.opponents_known, "byes_known_for_weeks": lg.byes_known,
            "no_fantasypros_projection": sorted(lg.vals.unmatched)}
    if args.scan:
        body = {"by_team": {str(t): rs for t, rs in lg.scan(args.top).items()}}
    else:
        props = json.loads(Path(args.proposals).read_text())
        body = {"results": sorted((lg.evaluate(p.get("team_id"), p.get("partner_id"), p.get("give") or [],
                                               p.get("get") or []) for p in props),
                                  key=lambda r: (not r["pass"],) + (rank(r) if r["pass"] else ()))}
    json.dump({**head, **body}, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
