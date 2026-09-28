#!/usr/bin/env python3
"""Print each manager's private dashboard link, to hand out one at a time.

The links are the only thing keeping these pages private, so treat them like that:
send each manager her own link directly (text, DM), never to the group chat, and never
paste this output into a file, a commit or the league site.

On first run this creates .dashboard-secret (gitignored, 0600). Keep it: the same secret
always produces the same links, so rebuilds don't break the links already handed out.
Deleting or changing it rotates all 8 at once, and everyone needs a new link.

Usage:
  python3 scripts/links.py              # every manager
  python3 scripts/links.py Kyra Maya    # just these
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dashboards  # noqa: E402

SITE = "https://fantasy-recap-eight.vercel.app"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("managers", nargs="*", help="first names; default is everyone")
    ap.add_argument("--season", type=int)
    args = ap.parse_args()

    league = json.loads((dashboards.ROOT / "league.json").read_text())
    season = args.season or league["season"]
    key = dashboards.secret(create=True)
    week = dashboards.latest_advice_week(season, league["teams"])

    wanted = {m.lower() for m in args.managers}
    rows = [t for t in league["teams"]
            if not wanted or dashboards.short(t["manager"]).lower() in wanted]
    unknown = wanted - {dashboards.short(t["manager"]).lower() for t in league["teams"]}
    if unknown:
        raise SystemExit(f"not in this league: {', '.join(sorted(unknown))}")

    width = max(len(dashboards.short(t["manager"])) for t in rows)
    for t in rows:
        token = dashboards.token(season, t["team_id"], key)
        print(f"{dashboards.short(t['manager']):<{width}}  {SITE}/me/{token}/")
    print(f"\nShowing week {week} advice." if week else
          "\nNo advice generated yet, so these pages are not deployed. These are the links they will have.")


if __name__ == "__main__":
    main()
