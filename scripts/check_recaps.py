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
import unicodedata

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


# Award card rules. The length and echo limits keep a card's title ticket and stat pill from
# wrapping; weeks before this one were written without them, so they only apply from here on.
AWARD_KEYS = ("game_balls", "flags", "tough_breaks")
AWARD_RULES_FROM_WEEK = 5
TITLE_MAX, STAT_MAX, EMOJI_MAX = 48, 22, 2
EM_DASH = "\u2014"


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


def emoji_clusters(text):
    """Split `text` into what a reader sees as characters: a base symbol plus any variation
    selector, skin tone, keycap or tag, ZWJ-joined sequences (🤦‍♀️) and flag pairs as one. Stdlib
    only, so it is an approximation of Unicode grapheme clusters, enough for emoji."""
    clusters, joined = [], False
    for ch in text:
        cp = ord(ch)
        ri = 0x1F1E6 <= cp <= 0x1F1FF
        extends = (cp in (0x200D, 0xFE0F, 0x20E3) or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F
                   or unicodedata.category(ch) in ("Mn", "Me"))
        flag_pair = ri and clusters and len(clusters[-1]) == 1 and 0x1F1E6 <= ord(clusters[-1]) <= 0x1F1FF
        if clusters and (extends or joined or flag_pair):
            clusters[-1] += ch
        else:
            clusters.append(ch)
        joined = cp == 0x200D
    return clusters


# Real emoji whose code points aren't category So (‼ ⁉ ℹ 〰 〽)
EMOJI_EXTRA_BASES = {0x203C, 0x2049, 0x2139, 0x3030, 0x303D}


def _emoji_base(ch):
    return unicodedata.category(ch) == "So" or ord(ch) in EMOJI_EXTRA_BASES


def _emoji_part(ch):
    cp = ord(ch)
    return cp in (0x200D, 0xFE0F, 0x20E3) or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F


def emoji_only(cluster):
    """True when every code point of one cluster is emoji: a base symbol first, then only
    selectors, skin tones, tags or a keycap, and a ZWJ only when another symbol follows it."""
    if not _emoji_base(cluster[0]):
        return False
    for i, ch in enumerate(cluster[1:], 1):
        if ch == "\u200d":
            if i + 1 >= len(cluster) or not _emoji_base(cluster[i + 1]):
                return False
        elif not (_emoji_part(ch) or _emoji_base(ch)):
            return False
        elif _emoji_base(ch) and cluster[i - 1] != "\u200d" and not (
                0x1F1E6 <= ord(ch) <= 0x1F1FF):
            return False
    return True


def _words(text):
    return re.findall(r"[a-z0-9.]+", text.lower())


def _contains_run(big, small):
    return bool(small) and any(big[i:i + len(small)] == small for i in range(len(big) - len(small) + 1))


def check_awards(recap, roster_names, problems):
    """Per-award rules: the optional `emoji` and `player` fields, and the title/stat/text limits.
    `roster_names` is None when the week has no facts.json to check a player against."""
    week = recap.get("week", 0)
    for section in AWARD_KEYS:
        for i, award in enumerate(recap.get(section, [])):
            at = f"{section}[{i}]"
            if not isinstance(award, dict):
                problems.append(f"{at} must be an object")
                continue
            for field in ("title", "stat", "text"):
                if field in award and not isinstance(award[field], str):
                    problems.append(f"{at}.{field} must be text")
            title, stat = (x if isinstance(x, str) else "" for x in (award.get("title"), award.get("stat")))

            # The photo comes from `player` through site/build.py, never from the recap itself
            for field in ("player_id", "headshot"):
                if field in award:
                    problems.append(f"{at}.{field} is baked in by the build from `player`; remove it")

            if "emoji" in award:
                emoji = award["emoji"]
                clusters = emoji_clusters(emoji) if isinstance(emoji, str) else []
                if not clusters or len(clusters) > EMOJI_MAX:
                    problems.append(f"{at}.emoji {emoji!r} must be 1 or {EMOJI_MAX} visible characters, "
                                    f"one emoji or one emoji sequence")
                elif not all(emoji_only(c) for c in clusters):
                    problems.append(f"{at}.emoji {emoji!r} must be emoji only, no letters, digits or punctuation")

            if "player" in award:
                player = award["player"]
                if not isinstance(player, str) or not player.strip():
                    problems.append(f"{at}.player must be a full player name")
                elif roster_names is None:
                    problems.append(f"{at}.player {player!r} can't be checked: no facts.json for week {week}")
                elif player not in roster_names:
                    problems.append(f"{at}.player {player!r} isn't on any roster in week {week}'s data "
                                    f"(use the full name exactly as the roster spells it)")

            if len(title) > TITLE_MAX:
                problems.append(f"{at}.title is {len(title)} characters, the limit is {TITLE_MAX}")
            if week >= AWARD_RULES_FROM_WEEK and len(stat) > STAT_MAX:
                problems.append(f"{at}.stat {stat!r} is {len(stat)} characters, the limit is {STAT_MAX}")
            sw, tw = _words(stat), _words(title)
            if sw and tw and (_contains_run(tw, sw) or _contains_run(sw, tw)):
                problems.append(f"{at}.stat {stat!r} repeats the title {title!r}; give the stat different information")
            for field in ("title", "stat", "text"):
                if EM_DASH in (award.get(field) if isinstance(award.get(field), str) else ""):
                    problems.append(f"{at}.{field} has an em dash; use a period or a comma")


def roster_names_for(facts):
    return {p["name"] for t in facts.get("teams", []) for p in t.get("starters", []) + t.get("bench", [])
            if p.get("name")}


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
    facts = json.loads(facts_path.read_text()) if facts_path.exists() else None
    real_pairs = real_matchup_pairs(facts) if facts else set()

    problems = []
    check_numbers(recap, source_numbers, problems)
    check_matchup_structure(recap, real_pairs, problems)
    check_no_last_names(recap, first_names(league), problems)
    check_awards(recap, roster_names_for(facts) if facts else None, problems)

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
