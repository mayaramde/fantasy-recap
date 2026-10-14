#!/usr/bin/env python3
"""Archive coach-daily's rolling snapshot as a dated history file.

`data/<season>/fantasypros/latest.json` is overwritten every day. This copies it to
`data/<season>/fantasypros/history/<YYYY-MM-DD>.json` (the Pacific calendar date of its `generated_at`) and
rebuilds `history/index.json`, a compact one-row-per-day summary, so a reader can scan a whole season
cheaply and open a full day only when it needs to.

A second run on the same day replaces that day's file (the last run of the day wins); earlier days are
never touched. Stdlib only.

    python3 scripts/snapshot_history.py [--season 2026]
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1
# A "day" is a Pacific-time day (Maya's), not a UTC one, so an evening rerun overwrites that
# day's file instead of spilling into tomorrow's. PST/PDT is handled by the zone.
DAY_TZ = ZoneInfo("America/Los_Angeles")
INDEX = "index.json"


def local_day(generated_at):
    """The Pacific calendar date ('YYYY-MM-DD') of an ISO 8601 UTC time, else a ValueError."""
    if not isinstance(generated_at, str):
        raise ValueError("generated_at must be an ISO 8601 UTC time")
    raw = generated_at[:-1] + "+00:00" if generated_at[-1:] in "Zz" else generated_at
    when = datetime.fromisoformat(raw)
    if when.tzinfo is None or when.utcoffset().total_seconds() != 0:
        raise ValueError("generated_at must be an ISO 8601 UTC time")
    return when.astimezone(DAY_TZ).date().isoformat()


def _summarize(snap, day):
    """One index row: enough to see how the day went without opening the file."""
    weeks = {}
    for week, wk in (snap.get("weeks") or {}).items():
        teams = (wk.get("teams") or {}) if isinstance(wk, dict) else {}
        count = {"advice_cards": 0, "roster_ideas": 0, "trades": 0, "coach_cards": 0}
        for t in teams.values():
            if not isinstance(t, dict):
                continue
            count["advice_cards"] += len(t.get("advice_cards") or [])
            ideas = t.get("roster_ideas") or []
            count["roster_ideas"] += len(ideas)
            count["trades"] += sum(1 for c in ideas if isinstance(c, dict) and c.get("kind") == "trade")
            count["coach_cards"] += len(t.get("coach_cards") or {})
        weeks[week] = count
    fp = snap.get("fantasypros") if isinstance(snap.get("fantasypros"), dict) else {}
    return {
        "date": day,
        "file": f"{day}.json",
        "generated_at": snap.get("generated_at"),
        "fantasypros_reached": fp.get("reached"),
        "weeks": weeks,
    }


def archive(season_dir):
    """Copy `<season_dir>/fantasypros/latest.json` into history/ and rebuild the index.
    Returns the dated file's path."""
    fp_dir = Path(season_dir) / "fantasypros"
    snap = json.loads((fp_dir / "latest.json").read_text())
    if not isinstance(snap, dict):
        raise ValueError("latest.json must be a JSON object")
    day = local_day(snap.get("generated_at"))

    hist = fp_dir / "history"
    hist.mkdir(exist_ok=True)
    dated = hist / f"{day}.json"
    dated.write_text(json.dumps({"schema_version": SCHEMA_VERSION, **snap}, indent=2, sort_keys=False) + "\n")

    rows = []
    for path in sorted(hist.glob("????-??-??.json")):
        try:
            day_snap = json.loads(path.read_text())
            rows.append(_summarize(day_snap, path.stem))
        except (json.JSONDecodeError, AttributeError):
            continue  # scripts/check.py reports a broken day; don't let it block the rest
    (hist / INDEX).write_text(json.dumps({"schema_version": SCHEMA_VERSION, "days": rows}, indent=2) + "\n")
    return dated


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", default=None, help="season folder under data/ (default: the newest one with a snapshot)")
    args = ap.parse_args(argv)
    data = ROOT / "data"
    seasons = [args.season] if args.season else sorted(p.parent.parent.name for p in data.glob("*/fantasypros/latest.json"))
    if not seasons:
        print("no data/<season>/fantasypros/latest.json to archive", file=sys.stderr)
        return 1
    dated = archive(data / seasons[-1])
    print(f"archived {dated.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
