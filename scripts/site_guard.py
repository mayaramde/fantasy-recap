#!/usr/bin/env python3
"""Refuse a cloud deploy that would take published work off the website.

The cloud live update builds from `main`, and a deploy replaces the whole site. If Maya
shipped something from her Mac with scripts/deploy.sh but its PR hasn't merged yet, the
live site has content this build doesn't, and deploying would silently remove it. Two
things get checked:

  recaps      the weeks embedded in the live page vs. site/dist/web/index.html
  dashboards  each manager's private /me/<token>/ page, live vs. built

Usage: python3 scripts/site_guard.py   (after site/build.py)
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dashboards  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://fantasy-recap-eight.vercel.app"
DATA = re.compile(r'<script id="recap-data" type="application/json">(.*?)</script>', re.S)


def recap_weeks(html):
    m = DATA.search(html)
    if not m:
        raise SystemExit("recap data not found in page")
    return {w["week"] for w in json.loads(m.group(1))["weeks"]}


def live_page(url):
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError:
        return False


def dashboards_ok():
    """True unless the live site has private dashboards this build would delete."""
    league = json.loads((ROOT / "league.json").read_text())
    key = dashboards.secret()
    if not key:
        # Without the secret the tokens can't be derived, so there is nothing to compare.
        # site/build.py already refuses to build when advice exists and the secret doesn't,
        # so the only way here is a checkout with neither.
        print("dashboards: no link secret in this checkout, skipping that check")
        return True
    lost = []
    for team in league["teams"]:
        token = dashboards.token(league["season"], team["team_id"], key)
        built = (ROOT / "site/dist/web/me" / token / "index.html").exists()
        if not built and live_page(f"{SITE}/me/{token}/"):
            lost.append(dashboards.short(team["manager"]))
    if lost:
        print(f"live site has private dashboards for {', '.join(lost)} that this build doesn't; "
              "not deploying. Merge the PR with that week's advice/ files first.", file=sys.stderr)
        return False
    print("dashboards: nothing live would be removed")
    return True


def main():
    built = recap_weeks((ROOT / "site/dist/web/index.html").read_text())
    with urllib.request.urlopen(SITE, timeout=30) as r:
        live = recap_weeks(r.read().decode())
    missing = sorted(live - built)
    if missing:
        print(f"live site has recap week(s) {missing} that main doesn't; not deploying. "
              "Merge that recap's PR first.", file=sys.stderr)
        return 1
    if not dashboards_ok():
        return 1
    print(f"ok: build has recap weeks {sorted(built)}; live site has {sorted(live)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
