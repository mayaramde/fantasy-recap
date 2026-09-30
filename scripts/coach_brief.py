"""Print the Coach page's computed cards, the brief coach-daily writes this week's advice from.

For the live week (and next week, when its capture is current), one entry per team: the
summary key, and every computed card with its situation `key`, kind, level, stat pill and
the computed wording the written copy replaces. coach-daily writes a title and text for
each key into data/<season>/fantasypros/latest.json (`coach_cards`, `summary`); site/build.py
shows the written copy only while the same key is still computed. Reads the same files the
build does, with no FantasyPros snapshot, so the wording shown is always the computed one.

Usage: python3 scripts/coach_brief.py [--season 2026]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
import build  # noqa: E402

CARD_KEYS = ("key", "kind", "level", "stat", "title", "text")


def team_brief(row):
    return {"team_id": row["team_id"], "manager": row["manager"], "team_name": row["team_name"],
           "summary_key": row["summary_key"], "summary": row["summary"],
           "cards": [{k: it.get(k) for k in CARD_KEYS} for it in row["items"] if it.get("key")]}


def brief(season):
    recap_weeks, captured, ahead, _ = build.load_inputs(season)
    # The league site's view (published recaps only), since that's the page managers read.
    _, weeks = build.render(recap_weeks, captured, preview=False, ahead=ahead, fp=None)
    live = next((w for w in weeks if w.get("live")), None)
    if not live:
        return {}
    out = {str(live["week"]): {"tab": "this week", "teams": [team_brief(r) for r in live["advice"]]}}
    nxt = live.get("next")
    if nxt:
        out[str(nxt["week"])] = {"tab": "next week", "projected": nxt["projected"],
                                 "teams": [team_brief(r) for r in nxt["teams"]]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=build.LEAGUE["season"])
    args = ap.parse_args()
    out = brief(args.season)
    if not out:
        raise SystemExit("No live week: every captured week already has a published recap.")
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
