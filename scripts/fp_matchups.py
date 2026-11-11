#!/usr/bin/env python3
"""This week's matchup ratings for every NFL team at every position, keyed by ESPN team abbreviation:
what the Coach lineup cards' "WR matchup: 2nd easiest" chip and note are made of.

Source: FantasyPros `get_schedule_and_strength` (one call per position, `week_start` = `week_end` = the
live week, all 32 team codes), the same MCP `coach-daily` already uses, so no new credentials. For each
team it gives a rank out of 32 (1 = the easiest matchup for that position, 32 = the hardest) and a star
rating out of 5 (5 = easiest). With all 32 codes it does NOT say who the opponent is or whether it's a home
game, so neither is stored. A team on a bye comes back with `"ratings": null` and simply gets no entry.

FantasyPros' codes differ from ESPN's in two places (JAC, WAS), so rows are stored under ESPN's (JAX, WSH):
that's the `team` the live rows already carry.

    python3 scripts/fp_matchups.py --week 10 \\
        --responses /tmp/fp-matchups.json [--into data/2026/fantasypros/latest.json]

`--responses` is a JSON list of the tool's responses, as returned. A response whose window isn't exactly
that one week (a range averages several weeks together) is skipped and reported rather than read as this
week's. Without `--into` the result is printed; with it, the snapshot's `matchups` is replaced and nothing
else in the file changes.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fp_player_stats import _whole, norm_team  # noqa: E402

POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
TEAMS = 32


def _schedules(resp):
    """The response's list of per-team rows, whatever the tool named the block holding it
    ("team schedule" when asked for given teams, "easiest schedules" otherwise)."""
    for value in (resp or {}).values():
        if isinstance(value, dict) and isinstance(value.get("schedules"), list):
            return value
    return None


def _stars(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 5:
        return None
    return round(float(v), 1)


def build(responses, week):
    """The snapshot's `matchups` block, {week, teams: {abbr: {pos: {rank, stars}}}}, and a list of
    notes about anything that was skipped."""
    teams, notes = {}, []
    for resp in responses:
        window = (resp or {}).get("sos_window") or {}
        block = _schedules(resp)
        pos = (block or {}).get("position")
        if window.get("week_start") != week or window.get("week_end") != week:
            notes.append(f"skipped a {pos or 'unknown-position'} response: its window is "
                         f"{window.get('label') or 'missing'}, not week {week} alone")
            continue
        if pos not in POSITIONS:
            notes.append(f"skipped a response for position {pos!r}")
            continue
        for row in block["schedules"]:
            sos = (row or {}).get("Strength of Schedule") or {}
            rank, stars = _whole(sos.get(f"{pos.lower()}_rank_out_of_{TEAMS}")), _stars(sos.get(f"{pos.lower()}_stars_out_of_5"))
            if rank is None or not 1 <= rank <= TEAMS or stars is None:
                continue                # a bye week (ratings: null), or a row we can't trust
            teams.setdefault(norm_team(row.get("team")), {})[pos] = {"rank": rank, "stars": stars}
    return {"week": week, "teams": teams}, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True, type=int, help="the live week the ratings are for")
    ap.add_argument("--responses", required=True, help="JSON list of get_schedule_and_strength responses")
    ap.add_argument("--into", help="snapshot file whose matchups to replace")
    args = ap.parse_args()
    block, notes = build(json.loads(Path(args.responses).read_text()), args.week)
    if args.into:
        path = Path(args.into)
        snap = json.loads(path.read_text())
        snap["matchups"] = block
        # Same shape coach-daily writes (indent 2, no trailing newline), so the diff is only matchups
        path.write_text(json.dumps(snap, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(block, indent=1))
    full = sum(1 for r in block["teams"].values() if len(r) == len(POSITIONS))
    print(f"{len(block['teams'])} teams rated, {full} at all {len(POSITIONS)} positions"
          + "".join(f"\n  {n}" for n in notes), file=sys.stderr)


if __name__ == "__main__":
    main()
