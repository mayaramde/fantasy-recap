#!/usr/bin/env python3
"""Pre-merge checks: valid JSON, no raw ESPN data or credentials, site builds.

Run locally with `python scripts/check.py`; CI runs the same thing.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Strings that only show up in credentials or an untrimmed ESPN payload.
FORBIDDEN = [
    re.compile(r"espn_s2", re.I),
    re.compile(r"\bSWID\b"),
    re.compile(r'"lastName"'),
    re.compile(r'"notificationSettings"'),
]
# Files that mention those strings on purpose.
SKIP = {"CLAUDE.md", "docs/vercel.md", "scripts/check.py", "scripts/capture_node.mjs"}


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
