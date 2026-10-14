#!/usr/bin/env python3
"""Pre-merge checks: valid JSON, no raw ESPN data or credentials, every capture
matching one declared shape, site builds.

Run locally with `python scripts/check.py`; CI runs the same thing.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import espn_fetch  # noqa: E402
import check_recaps  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Strings that only show up in credentials or an untrimmed ESPN payload.
FORBIDDEN = [
    re.compile(r"espn_s2", re.I),
    re.compile(r"\bSWID\b"),
    re.compile(r'"lastName"'),
    re.compile(r'"notificationSettings"'),
]
# Files that mention those strings on purpose (the names of ESPN's login cookies, which the
# repo no longer uses but still guards against, never a value).
SKIP = {"CLAUDE.md", "docs/vercel.md", "scripts/check.py", ".claude/skills/recap-capture/SKILL.md"}


def check_capture_shape(errors):
    """espn.json now has two possible authors — scripts/capture.js in Chrome and
    scripts/espn_fetch.py inside /api/live — and scripts/analyze.py can't tell which one
    wrote the file it's reading. Hold every capture on disk to the single shape declared in
    espn_fetch.SHAPE, so a field added, renamed or retyped on one side is caught here
    instead of quietly changing a number on the site.

    This walks the filesystem rather than tracked files on purpose: the in-progress week is
    uncommitted, and it's the freshest capture.js output there is. The week-ahead preview
    under next-week/ is the same shape and never committed either, so it's checked too."""
    captures = sorted((ROOT / "data").glob("*/week-*/espn.json")) + \
        sorted((ROOT / "data").glob("*/next-week/espn.json"))
    for path in captures:
        rel = path.relative_to(ROOT)
        try:
            capture = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue  # already reported as invalid JSON
        for problem in espn_fetch.shape_problems(capture):
            errors.append(f"{rel}: {problem}")


def check_scoring_rows(errors):
    """Every player card on the Coach page has to add up.

    scripts/analyze.py turns ESPN's numbered stats into the rows the card shows, and folds
    anything it can't name (plus any gap) into one "Other scoring" row. So the rows must
    always sum to the points the site prints next to his name; if they don't, the breakdown
    is telling a story the box score doesn't.
    """
    for path in sorted((ROOT / "data").glob("*/week-*/facts.json")):
        rel = path.relative_to(ROOT)
        try:
            facts = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue  # already reported as invalid JSON
        for team in facts.get("teams", []):
            for player in team.get("starters", []) + team.get("bench", []):
                rows = player.get("scoring_lines")
                if rows is None:
                    continue  # captured before capture.js recorded any of this
                total = round(sum(r["points"] for r in rows), 2)
                if abs(total - player["points"]) > 0.011:
                    errors.append(f"{rel}: {player['name']}'s scoring rows add up to {total}, "
                                  f"but he scored {player['points']}")


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    return [p for p in out.split("\0") if p]


def check_team_profiles(errors):
    """Every team on both builds has a profile, and every audit card is fully formed."""
    sys.path.insert(0, str(ROOT / "site"))
    import build  # noqa: E402  (site/build.py; imported late so a broken build fails here, not at import)
    recap_weeks, captured, ahead, fp, _news = build.load_inputs(build.LEAGUE["season"])
    for preview in (False, True):
        data, _ = build.site_data(recap_weeks, captured, preview=preview, ahead=ahead, fp=fp)
        for s in data["season"]["standings"]:
            prof = s.get("profile")
            if not isinstance(prof, dict):
                errors.append(f"team {s['team_id']}: no profile (preview={preview})")
                continue
            for c in prof.get("audit", []):
                for k in ("key", "stat", "title", "text"):
                    if not (isinstance(c.get(k), str) and c[k].strip()):
                        errors.append(f"team {s['team_id']}: audit card {c.get('kind')} missing {k}")


def check_trade_deadline(errors):
    """league.json's "trade_deadline", when set, is a time with its UTC offset. Without one the
    site can't tell when it has passed, and trade cards would quietly outlive the deadline."""
    raw = json.loads((ROOT / "league.json").read_text()).get("trade_deadline")
    if raw is None:
        return
    try:
        when = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        errors.append(f"league.json: trade_deadline {raw!r} isn't an ISO 8601 time")
        return
    if when.tzinfo is None:
        errors.append(f"league.json: trade_deadline {raw!r} needs its UTC offset, e.g. -05:00 for Eastern")


# Snapshots generated before this moment predate the `fantasypros` field and are left alone;
# every one after it must carry it, so a run that never reached FantasyPros can't pass for one that did.
FANTASYPROS_FIELD_REQUIRED_FROM = datetime(2026, 10, 13, tzinfo=timezone.utc)


def _parse_utc(raw):
    """An ISO 8601 time that is explicitly UTC (a trailing Z or a zero offset), else None."""
    if not isinstance(raw, str):
        return None
    try:
        when = datetime.fromisoformat(raw[:-1] + "+00:00" if raw[-1:] in "Zz" else raw)
    except ValueError:
        return None
    if when.tzinfo is None or when.utcoffset().total_seconds() != 0:
        return None
    return when


def check_fantasypros_snapshot(errors, root=ROOT):
    """coach-daily's snapshot (and each dated copy in fantasypros/history/) says whether the run reached the FantasyPros MCP:
    `fantasypros: {reached, checked_at, error?}`. A run that didn't can't hold FantasyPros-sourced
    cards, and a failed probe has to say why."""
    paths = sorted((root / "data").glob("*/fantasypros/latest.json")) + \
        sorted((root / "data").glob("*/fantasypros/history/????-??-??.json"))
    for path in paths:
        rel = path.relative_to(root)
        try:
            snap = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue  # the generic JSON check already reports it
        if not isinstance(snap, dict):
            errors.append(f"{rel}: must be a JSON object")
            continue
        generated = _parse_utc(snap.get("generated_at"))
        if generated is None:
            errors.append(f"{rel}: generated_at must be an ISO 8601 UTC time, e.g. 2026-10-14T06:00:00Z")
        elif path.parent.name == "history" and generated.date().isoformat() != path.stem:
            errors.append(f"{rel}: filename date doesn't match generated_at ({generated.date().isoformat()})")
        fp = snap.get("fantasypros")
        if fp is None:
            if generated and generated >= FANTASYPROS_FIELD_REQUIRED_FROM:
                errors.append(f"{rel}: missing the `fantasypros` field (reached, checked_at)")
            continue
        if not isinstance(fp, dict) or not isinstance(fp.get("reached"), bool):
            errors.append(f"{rel}: fantasypros.reached must be true or false")
            continue
        if _parse_utc(fp.get("checked_at")) is None:
            errors.append(f"{rel}: fantasypros.checked_at must be an ISO 8601 UTC time")
        if fp["reached"]:
            continue
        if not (isinstance(fp.get("error"), str) and fp["error"].strip()):
            errors.append(f"{rel}: fantasypros.reached is false, so fantasypros.error must say why")
        weeks = snap.get("weeks")
        if not isinstance(weeks, dict):
            errors.append(f"{rel}: weeks must be an object")
            continue
        for week, wk in weeks.items():
            teams = wk.get("teams") if isinstance(wk, dict) else None
            if not isinstance(teams, dict):
                errors.append(f"{rel}: week {week} must have a teams object")
                continue
            for team, t in teams.items():
                if not isinstance(t, dict):
                    errors.append(f"{rel}: week {week} team {team} must be an object")
                elif t.get("advice_cards") or t.get("roster_ideas"):
                    errors.append(f"{rel}: week {week} team {team} has FantasyPros cards "
                                  "but fantasypros.reached is false")


def main():
    errors = []
    files = tracked_files()

    for rel in files:
        if rel.endswith(".raw.json") or "/raw/" in f"/{rel}":
            errors.append(f"{rel}: raw ESPN capture must not be committed")
            continue
        if rel in SKIP or rel.startswith(".github/"):
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for pat in FORBIDDEN:
            if pat.search(text):
                errors.append(f"{rel}: contains {pat.pattern!r} (credentials or raw ESPN data)")
        if rel.endswith(".json"):
            try:
                json.loads(text)
            except json.JSONDecodeError as e:
                errors.append(f"{rel}: invalid JSON ({e})")

    check_capture_shape(errors)
    check_scoring_rows(errors)
    check_team_profiles(errors)
    check_trade_deadline(errors)
    check_fantasypros_snapshot(errors)

    recap_errors, recap_warnings = check_recaps.check_all_recaps(ROOT)
    errors.extend(recap_errors)
    if recap_warnings:
        print("warning (not blocking, draft-recap grace period):", file=sys.stderr)
        print("\n".join(f"  {w}" for w in recap_warnings), file=sys.stderr)

    build = next((p for p in [ROOT / "site/build.py", ROOT / "site/build.js"] if p.exists()), None)
    if build:
        cmd = ["python3", str(build)] if build.suffix == ".py" else ["node", str(build)]
        if subprocess.run(cmd, cwd=ROOT).returncode != 0:
            errors.append(f"{build.relative_to(ROOT)}: site build failed")
    else:
        print("no site build script yet; skipping build")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"ok: {len(files)} tracked files checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
