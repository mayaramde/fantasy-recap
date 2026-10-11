#!/usr/bin/env python3
"""Refuse a cloud deploy that would take a published recap off the website.

The cloud live update builds from `main`. If Maya shipped a recap from her Mac with
scripts/deploy.sh but its PR hasn't merged yet, the live site has a recap week that
this build doesn't, and deploying would silently remove it. Compare the recap weeks
embedded in the live page with the ones in site/dist/web/index.html.

Usage: python3 scripts/site_guard.py   (after site/build.py)
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://fantasyforthegirls.vercel.app"
DATA = re.compile(r'<script id="recap-data" type="application/json">(.*?)</script>', re.S)


def recap_weeks(html):
    m = DATA.search(html)
    if not m:
        raise SystemExit("recap data not found in page")
    return {w["week"] for w in json.loads(m.group(1))["weeks"]}


def main():
    built = recap_weeks((ROOT / "site/dist/web/index.html").read_text())
    with urllib.request.urlopen(SITE, timeout=30) as r:
        live = recap_weeks(r.read().decode())
    missing = sorted(live - built)
    if missing:
        print(f"live site has recap week(s) {missing} that main doesn't; not deploying. "
              "Merge that recap's PR first.", file=sys.stderr)
        return 1
    print(f"ok: build has recap weeks {sorted(built)}; live site has {sorted(live)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
