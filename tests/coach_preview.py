#!/usr/bin/env python3
"""Render the Coach landing from committed data, for looking at in a browser.

Like hub_preview.py, this makes the week after the newest capture (same rosters, nothing kicked off) because a
normal build holds only recapped weeks. On top of that it puts a few starters and bench players on a bye, in the
same pattern as the Week 6 snapshot's counts, so every module has something to draw. The player names, rosters
and projections are last week's real capture, NOT Week 6's: this is for layout, not for facts. Unit tests use
tests/fixtures/week-06/golden.json instead.

Usage: python3 tests/coach_preview.py <output dir>   (writes coach.html)
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub_preview  # noqa: E402  (also puts site/ and scripts/ on sys.path)
import analyze  # noqa: E402
import build  # noqa: E402

# manager -> (starters on bye, bench on bye), after the Week 6 snapshot's counts
BYES = {"Samantha": (3, 0), "Kyra": (2, 0), "Maddie": (1, 0), "Tara": (1, 1), "Maya": (1, 0), "Cambri": (1, 2), "Marlee": (0, 4)}


def with_byes(week):
    week = copy.deepcopy(week)
    first = {t["team_id"]: t["manager"].split(" (")[0] for t in build.LEAGUE["teams"]}
    for m in week["matchups"]:
        for side in ("home", "away"):
            s = m[side]
            starters, bench = (n for n in BYES.get(first.get(s["team_id"]), (0, 0)))
            live = [p for p in s["lineup"] if p["slot"] not in ("BENCH", "IR")]
            rest = [p for p in s["lineup"] if p["slot"] == "BENCH"]
            for p in live[:starters] + rest[:bench]:
                p["game_state"] = None
    return week


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    recap_weeks, captured, _, fp, _ = build.load_inputs(build.LEAGUE["season"])
    history = [e for _, e in captured]
    nxt = with_byes(hub_preview.upcoming(history[-1]))
    before = captured + [(analyze.analyze(nxt, history + [nxt]), nxt)]
    html, _ = build.render(recap_weeks, before, preview=False, fp=fp, news=[])
    (out / "coach.html").write_text(build.standalone(html).replace('window.FANTASY_LIVE_API="/api/live"', ""))
    print(f"wrote {out / 'coach.html'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
