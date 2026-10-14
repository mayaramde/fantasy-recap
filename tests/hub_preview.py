#!/usr/bin/env python3
"""Render the Week hub in both of its states from committed data, for looking at in a browser.

The repo only ever holds finished, recapped weeks, so neither state of the "This week" page exists
in a normal build (and never on a Vercel branch preview). This makes both on demand:

  before.html  the week after the newest capture, before kickoff: the same rosters with every score
               wiped and every game still to play, so projections, stakes, Coach and the wire all draw
  final.html   the newest captured week as if its recap hadn't been written yet

Nothing here is a real upcoming week: projections are last week's. It's for layout, not for facts.

Usage: python3 tests/hub_preview.py <output dir>
"""
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
sys.path.insert(0, str(ROOT / "scripts"))
import analyze  # noqa: E402
import build  # noqa: E402

PHOTO = "https://a.espncdn.com/photo/2026/1014/r1730452_600x400_3-2.jpg"
# (headline, tag, has a photo, how many players it tags). Players are dealt out from the rosters in order,
# so the stories land on different teams; the last teams get nothing, which is what the empty state is for.
SAMPLE_NEWS = [
    ("Sample injury headline: starter is questionable and might not play Sunday", "Injury", True, 1),
    ("A second sample headline, this one long enough to wrap onto another line on a phone", "Team news", True, 2),
    ("Sample feature: why one offense keeps stalling on third down", "Feature", False, 1),
    ("Third sample headline", "Team news", False, 1),
    ("Fourth sample headline about a quarterback", "Team news", True, 1),
    ("Sample injury headline: a running back is out for the season", "Injury", False, 1),
    ("Sixth sample feature about the rookies", "Feature", True, 2),
]


def upcoming(last):
    """`last` (a finished capture) turned into the week after it, before anything has kicked off."""
    week = copy.deepcopy(last)
    week.update(week=last["week"] + 1, complete=False, transactions=[],
                captured_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    for m in week["matchups"]:
        m["winner"] = "UNDECIDED"
        for s in ("home", "away"):
            m[s]["points"] = 0
            for p in m[s]["lineup"]:
                p.update(points=0, played=False, scoring=[], game_state="pre", game_clock=None)
    return week


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    recap_weeks, captured, _, fp, _ = build.load_inputs(build.LEAGUE["season"])
    history = [e for _, e in captured]
    players = [p for m in history[-1]["matchups"] for s in ("home", "away") for p in m[s]["lineup"][:1]]
    news = {"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "articles": [
        {"id": i, "headline": h, "link": f"https://www.espn.com/nfl/story/_/id/{i}/sample", "tag": tag,
         "published": f"2026-10-{14 - i % 5:02d}T15:00:00Z",
         "athlete_ids": [players[(i * 2 + k) % len(players)]["player_id"] for k in range(n)],
         **({"image": PHOTO} if photo else {})}
        for i, (h, tag, photo, n) in enumerate(SAMPLE_NEWS, 1)]}

    nxt = upcoming(history[-1])
    before = captured + [(analyze.analyze(nxt, history + [nxt]), nxt)]
    html, _ = build.render(recap_weeks, before, preview=False, fp=fp, news=news)
    (out / "before.html").write_text(build.standalone(html).replace('window.FANTASY_LIVE_API="/api/live"', ""))

    html, _ = build.render(recap_weeks[:-1], captured, preview=False, fp=fp, news=news)
    (out / "final.html").write_text(build.standalone(html).replace('window.FANTASY_LIVE_API="/api/live"', ""))
    print(f"wrote {out / 'before.html'} and {out / 'final.html'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
