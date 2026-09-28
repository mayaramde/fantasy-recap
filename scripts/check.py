#!/usr/bin/env python3
"""Pre-merge checks: valid JSON, no raw ESPN data or credentials, no dashboard
links, advice files well-formed, every capture matching one declared shape, site builds.

Run locally with `python scripts/check.py`; CI runs the same thing.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dashboards  # noqa: E402
import espn_fetch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Strings that only show up in credentials or an untrimmed ESPN payload.
FORBIDDEN = [
    re.compile(r"espn_s2", re.I),
    re.compile(r"\bSWID\b"),
    re.compile(r'"lastName"'),
    re.compile(r'"notificationSettings"'),
]
# Files that mention those strings on purpose (the names of the cookie environment
# variables, never a value).
SKIP = {"CLAUDE.md", "docs/vercel.md", "scripts/check.py", "scripts/capture_node.mjs",
        "scripts/espn_fetch.py", "scripts/deploy.sh", "api/live.py"}


def check_capture_shape(errors):
    """espn.json now has two possible authors — scripts/capture.js in Chrome and
    scripts/espn_fetch.py inside /api/live — and scripts/analyze.py can't tell which one
    wrote the file it's reading. Hold every capture on disk to the single shape declared in
    espn_fetch.SHAPE, so a field added, renamed or retyped on one side is caught here
    instead of quietly changing a number on the site.

    This walks the filesystem rather than tracked files on purpose: the in-progress week is
    uncommitted, and it's the freshest capture.js output there is."""
    for path in sorted((ROOT / "data").glob("*/week-*/espn.json")):
        rel = path.relative_to(ROOT)
        try:
            capture = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue  # already reported as invalid JSON
        for problem in espn_fetch.shape_problems(capture):
            errors.append(f"{rel}: {problem}")

# Every advice file needs these, because the dashboard leads with them.
ADVICE_REQUIRED = ("season", "week", "manager", "team_id", "generated_at", "summary")
ADVICE_LISTS = ("waivers", "start_sit", "watch", "trade_ideas", "your_habits", "glossary")


def check_advice(files, errors):
    """Advice files are per-manager and hand-written, so catch the easy mistakes:
    a filename that isn't a manager, a week that disagrees with its folder, a team_id
    that belongs to someone else. A page built from a mislabelled file would show one
    manager another manager's plans."""
    league = json.loads((ROOT / "league.json").read_text())
    by_slug = {dashboards.slug(t["manager"]): t for t in league["teams"]}
    for rel in files:
        if not re.fullmatch(r"advice/\d{4}/week-\d{2}/[a-z-]+\.json", rel):
            continue
        _, season, folder, fname = rel.split("/")
        try:
            a = json.loads((ROOT / rel).read_text())
        except json.JSONDecodeError:
            continue  # already reported as invalid JSON
        team = by_slug.get(fname[:-5])
        if not team:
            errors.append(f"{rel}: {fname[:-5]!r} is not a manager in league.json")
            continue
        for field in ADVICE_REQUIRED:
            if not a.get(field):
                errors.append(f"{rel}: missing {field!r}")
        if a.get("week") != int(folder.split("-")[1]):
            errors.append(f"{rel}: week {a.get('week')} doesn't match the {folder} folder")
        if a.get("season") != int(season):
            errors.append(f"{rel}: season {a.get('season')} doesn't match the {season} folder")
        if a.get("team_id") != team["team_id"]:
            errors.append(f"{rel}: team_id {a.get('team_id')} is not {team['manager']}'s "
                          f"(expected {team['team_id']})")
        if a.get("manager") != dashboards.short(team["manager"]):
            errors.append(f"{rel}: manager {a.get('manager')!r} doesn't match the filename")
        for key in ADVICE_LISTS:
            if key in a and not isinstance(a[key], list):
                errors.append(f"{rel}: {key!r} must be a list")


def check_no_links(files, errors):
    """The private dashboard links must never be committed: the repo is private today,
    but the links are the only thing making those pages private, and git history is
    forever. Derive each token and make sure no tracked file contains it."""
    if dashboards.SECRET_FILE.name in files or ".dashboard-secret" in files:
        errors.append(".dashboard-secret: the dashboard link secret must not be committed")
    key = dashboards.secret()
    if not key:
        return
    league = json.loads((ROOT / "league.json").read_text())
    tokens = {dashboards.token(league["season"], t["team_id"], key): dashboards.short(t["manager"])
              for t in league["teams"]}
    for rel in files:
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for token, manager in tokens.items():
            if token in text:
                errors.append(f"{rel}: contains {manager}'s private dashboard link")


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    return [p for p in out.split("\0") if p]


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

    check_advice(files, errors)
    check_no_links(files, errors)
    check_capture_shape(errors)

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
