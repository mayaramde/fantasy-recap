#!/usr/bin/env python3
"""Recap content checks: every number in a written recap must trace back to
that week's captured data, every matchup key must be a real pairing, and no
manager's last name may appear anywhere (recaps use first names only).

Imported by scripts/check.py; not meant to be run standalone, though
`check_all_recaps(ROOT)` is a normal function you can call from a REPL or a
test for a specific root directory.
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path
import string

# The Fri Oct 2 2026 target from the harness hardening plan. For two weeks
# after that, a violation in a *draft* recap only warns — a false positive in
# the new check must not block a Tuesday recap PR while the heuristics are
# still fresh. A *published* recap has always been reviewed by Maya already,
# so its violations are errors from day one.
ROLLOUT_START = date(2026, 10, 2)
DRAFT_GRACE = timedelta(weeks=2)

# A written number ≤ this, with no decimal point, is a rank/count/week-number
# rather than a stat, and isn't required to trace back to source data.
SMALL_INTEGER_CEILING = 20

NUMBER_RE = re.compile(r"[-−]?\d+(?:\.\d+)?")
MATCHUP_KEY_RE = re.compile(r"(\d+)-(\d+)")


def draft_violations_are_warnings(today=None):
    today = today or date.today()
    return today < ROLLOUT_START + DRAFT_GRACE


def collect_numbers(obj, out):
    """Recursively collect every numeric leaf in a JSON-decoded structure,
    rounded to 4 decimals so a recap number and its source can be compared by
    simple set membership. `bool` is deliberately excluded — it's a subclass
    of `int` in Python, but a JSON `true`/`false` is never a stat."""
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(round(float(obj), 4))
    elif isinstance(obj, dict):
        for value in obj.values():
            collect_numbers(value, out)
    elif isinstance(obj, list):
        for value in obj:
            collect_numbers(value, out)


def extract_written_numbers(text):
    """Yield (raw_text, value, is_plain_integer) for every number written in
    `text`. `is_plain_integer` is true only when there's no decimal point in
    what was actually written — "24" is plain, "24.0" is not — since a
    deliberately-written ".0" is a stat, not a rank."""
    for match in NUMBER_RE.finditer(text):
        raw = match.group(0)
        is_plain_integer = "." not in raw
        value = float(raw.replace("−", "-"))
        yield raw, value, is_plain_integer


def recap_number_fields(recap):
    """The fields a recap's numbers must be sourced from, per the harness
    plan: headline, dek, matchup blurbs, and each stat field. Deliberately
    NOT game_balls/flags/tough_breaks `text` — narrative prose is out of
    scope for this check for now (see the PR description)."""
    fields = [("headline", recap.get("headline", "")), ("dek", recap.get("dek", ""))]
    for key, blurb in recap.get("matchups", {}).items():
        fields.append((f"matchups.{key}", blurb))
    for section in ("game_balls", "flags", "tough_breaks"):
        for i, entry in enumerate(recap.get(section, [])):
            stat = entry.get("stat")
            if stat:
                fields.append((f"{section}[{i}].stat", stat))
    return fields


def decimal_places_written(raw):
    return len(raw.split(".", 1)[1]) if "." in raw else 0


def check_numbers(recap, source_numbers, problems):
    """A written number must be within source data, but two things about how
    it's written have to be tolerated rather than compared by exact equality:

    - Sign. The recap deliberately negates a "this cost you points" stat
      (e.g. a bench-blunder `gap`, always stored as a positive magnitude) to
      -23.7 for voice, while a stat that's already signed in the source (e.g.
      `beat_projection`, negative when a player underperforms) keeps its own
      sign. Comparing by magnitude handles both without caring which
      convention a given field happens to use.
    - Rounding. The source stores two decimals; recap prose sometimes writes
      one ("19.9" for a source 19.95). The tolerance is half a unit of the
      *written* precision, which accepts any rounding convention (up, down,
      to-even) for that many decimal places — not just whichever one Python's
      round() happens to produce for a given float.
    """
    abs_sources = {abs(v) for v in source_numbers}
    for field_name, text in recap_number_fields(recap):
        for raw, value, is_plain_integer in extract_written_numbers(text):
            if is_plain_integer and abs(value) <= SMALL_INTEGER_CEILING:
                continue
            tolerance = 0.5 * 10 ** -decimal_places_written(raw) + 1e-9
            if not any(abs(abs(value) - src) <= tolerance for src in abs_sources):
                problems.append(
                    f"{field_name}: {raw!r} doesn't match any number in that week's "
                    f"facts.json/espn.json")


def real_matchup_pairs(facts):
    pairs = set()
    for team in facts.get("teams", []):
        team_id, opponent_id = team.get("team_id"), team.get("opponent_id")
        if team_id is not None and opponent_id is not None:
            pairs.add(tuple(sorted((team_id, opponent_id))))
    return pairs


def check_matchup_structure(recap, real_pairs, problems):
    for key in recap.get("matchups", {}):
        match = MATCHUP_KEY_RE.fullmatch(key)
        if not match:
            problems.append(f"matchups key {key!r} isn't in <lowTeamId>-<highTeamId> form")
            continue
        low, high = int(match.group(1)), int(match.group(2))
        if low >= high:
            problems.append(f"matchups key {key!r}: team ids must be written low-high")
            continue
        if (low, high) not in real_pairs:
            problems.append(f"matchups key {key!r} isn't a real matchup this week")


def first_names(league):
    """The set of valid manager first names from league.json. A manager
    written as "Samantha (Sam)" contributes both "Samantha" and "Sam" — the
    recap is free to use either, so both must be recognized as legitimate,
    not flagged as a stray extra word."""
    names = set()
    for team in league.get("teams", []):
        manager = team.get("manager", "")
        base = re.sub(r"\s*\([^)]*\)", "", manager).strip()
        if base:
            names.add(base.split()[0])
        nickname = re.search(r"\(([^)]+)\)", manager)
        if nickname:
            names.add(nickname.group(1).strip())
    return names

def find_possible_last_names(text, names):
    words = text.split()
    flagged = []

    for k in range(len(words) - 1):
        i, j = words[k], words[k + 1]
        nxt = words[k + 2] if k + 2 < len(words) else ""

        if i not in names:
            continue

        j_clean = j.rstrip(string.punctuation)

        if not j_clean[:1].isupper():   # sentence start / lowercase word
            continue
        if j_clean.isupper():           # QB, RB, etc.
            continue
        if j_clean in names:            # "Maya Kyra" matchup
            continue
        if nxt[:1].isdigit():           # "Maya Week 3"
            continue

        flagged.append(f"{i} {j_clean}")

    return flagged



def check_no_last_names(recap, names, problems):
    fields = [("headline", recap.get("headline", "")), ("dek", recap.get("dek", ""))]
    for key, blurb in recap.get("matchups", {}).items():
        fields.append((f"matchups.{key}", blurb))
    for section in ("game_balls", "flags", "tough_breaks"):
        for i, entry in enumerate(recap.get(section, [])):
            fields.append((f"{section}[{i}].text", entry.get("text", "")))

    for field_name, text in fields:
        for phrase in find_possible_last_names(text, names):
            problems.append(f"{field_name}: {phrase!r} looks like it could include a last name")


def check_one_recap(recap_path, root, league, errors, warnings):
    recap = json.loads(recap_path.read_text())
    season, week = recap["season"], recap["week"]
    week_dir = root / "data" / str(season) / f"week-{week:02d}"

    source_numbers = set()
    for filename in ("facts.json", "espn.json"):
        path = week_dir / filename
        if path.exists():
            collect_numbers(json.loads(path.read_text()), source_numbers)

    facts_path = week_dir / "facts.json"
    real_pairs = real_matchup_pairs(json.loads(facts_path.read_text())) if facts_path.exists() else set()

    problems = []
    check_numbers(recap, source_numbers, problems)
    check_matchup_structure(recap, real_pairs, problems)
    check_no_last_names(recap, first_names(league), problems)

    if not problems:
        return

    rel = recap_path.relative_to(root)
    is_draft = recap.get("status") == "draft"
    blocking = not (is_draft and draft_violations_are_warnings())
    target = errors if blocking else warnings
    for problem in problems:
        target.append(f"{rel}: {problem}")


def check_all_recaps(root):
    """Returns (errors, warnings) across every recaps/<season>/week-NN.json
    under `root`. Errors should fail the caller's check; warnings should be
    printed but not fail it."""
    errors, warnings = [], []
    league_path = root / "league.json"
    league = json.loads(league_path.read_text()) if league_path.exists() else {}
    for recap_path in sorted(root.glob("recaps/*/week-*.json")):
        check_one_recap(recap_path, root, league, errors, warnings)
    return errors, warnings
