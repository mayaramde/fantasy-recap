#!/usr/bin/env python3
"""Season-to-date stat totals for every rostered player, keyed by ESPN player id: what the matchup
page's "Key stats" tiles (carries per game, targets per game, ...) are made of.

Source: FantasyPros `get_player_stats` (`range_type=week_range`, weeks 1 to N), the same MCP
`coach-daily` already uses, so no new credentials. ESPN's scoring lines carry yards, catches and
TDs but never carries or targets, so they can't supply these.

The tool is looked up by name, not id, and FantasyPros' ids differ from ESPN's, so rows are paired
by name plus NFL team (suffixes and punctuation ignored, FantasyPros' JAC and WAS read as ESPN's
JAX and WSH) and position. Anything that doesn't pair, or pairs ambiguously, is listed under
`unmatched` rather than guessed. The tool's own `unresolved_names` is not trusted: it has listed
every name in a batch that came back fine. Its `data` can also carry a stray D/ST row, which is
simply never matched.

    python3 scripts/fp_player_stats.py --facts data/2026/week-06/facts.json \\
        --responses /tmp/fp-stats.json [--into data/2026/fantasypros/latest.json]

`--responses` is a JSON list of the tool's responses, as returned. Without `--into` the result is
printed; with it, the snapshot's `player_stats` is replaced and nothing else in the file changes.
Prints the unmatched players either way.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# The totals kept per player. Everything the tiles read, nothing else; absent means FantasyPros
# didn't report it for that player (a QB has no receiving line).
STAT_FIELDS = ("games", "rush_att", "rush_yds", "rush_tds", "rec_tar", "rec_rec", "rec_yds", "rec_tds",
               "pass_att", "pass_yds", "pass_tds", "fg", "fga", "xpt", "xpa")
TEAM_ALIASES = {"JAC": "JAX", "WAS": "WSH", "LA": "LAR"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_name(name):
    words = re.sub(r"[^a-z ]", "", str(name).lower().replace("-", "")).split()
    return " ".join(w for w in words if w not in SUFFIXES)


def norm_team(team):
    team = str(team or "").upper()
    return TEAM_ALIASES.get(team, team)


def _index(responses):
    """{(name, team, pos): stats}, or None for a key two different FantasyPros rows claim."""
    seen = {}
    for resp in responses:
        for row in (resp or {}).get("data") or []:
            if not isinstance(row, dict) or not isinstance(row.get("stats"), dict):
                continue
            key = (norm_name(row.get("player_name")), norm_team(row.get("team_id")), row.get("position_id"))
            stats = {k: row["stats"][k] for k in STAT_FIELDS if type(row["stats"].get(k)) is int}
            if key in seen and seen[key] != stats:
                seen[key] = None
            else:
                seen.setdefault(key, stats)
    return seen


def build(players, responses, through_week):
    """`players`: [{player_id, name, pos, team}] for every rostered player. Returns the snapshot's
    `player_stats` block: {through_week, players: {espn_id: totals}, unmatched: [{name, team, why}]}."""
    index = _index(responses)
    out, unmatched = {}, []
    for p in players:
        if p.get("pos") == "DST":
            continue                    # nothing tracked for a defense
        key = (norm_name(p["name"]), norm_team(p.get("team")), p.get("pos"))
        if key not in index:
            unmatched.append({"name": p["name"], "team": p.get("team"), "why": "no match"})
        elif index[key] is None:
            unmatched.append({"name": p["name"], "team": p.get("team"), "why": "ambiguous"})
        elif not index[key].get("games"):
            unmatched.append({"name": p["name"], "team": p.get("team"), "why": "no games played"})
        else:
            out[str(p["player_id"])] = index[key]
    return {"through_week": through_week, "players": out, "unmatched": unmatched}


def roster(facts):
    return [{k: p.get(k) for k in ("player_id", "name", "pos", "team")}
            for t in facts["teams"] for p in t["starters"] + t["bench"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", required=True, help="the live week's facts.json, for who is rostered")
    ap.add_argument("--responses", required=True, help="JSON list of get_player_stats responses")
    ap.add_argument("--through", type=int, help="last week the stats cover (default: the facts' week minus one)")
    ap.add_argument("--into", help="snapshot file whose player_stats to replace")
    args = ap.parse_args()
    facts = json.loads(Path(args.facts).read_text())
    block = build(roster(facts), json.loads(Path(args.responses).read_text()), args.through or facts["week"] - 1)
    if args.into:
        path = Path(args.into)
        snap = json.loads(path.read_text())
        snap["player_stats"] = block
        path.write_text(json.dumps(snap, indent=2) + "\n")
    else:
        print(json.dumps(block, indent=1))
    print(f"matched {len(block['players'])}, unmatched {len(block['unmatched'])}"
          + "".join(f"\n  {u['name']} ({u['team']}): {u['why']}" for u in block["unmatched"]), file=sys.stderr)


if __name__ == "__main__":
    main()
