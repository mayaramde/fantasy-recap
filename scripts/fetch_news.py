#!/usr/bin/env python3
"""Fetch ESPN's public NFL headlines for the Week hub's "ESPN on your rosters" module.

Writes data/<season>/news/latest.json: for each article kept, only its id, headline, link,
publish time, byline and the ESPN athlete ids it tags. No article text, ever: the page shows the
headline as a link out to ESPN and nothing more.

An article is kept only if
  - it tags at most MAX_ATHLETES players (a rankings listicle that tags forty is not news about any
    one of them), and at least one of them is on a league roster in the newest capture; and
  - nothing in its headline or description reads as off-field (see OFF_FIELD). When in doubt it's
    dropped: this module is for football, and a courtroom story has no business under a team's name.

Best effort, like the scoreboard fetch: the feed is public and needs no cookies, and any failure
(network, a changed shape, no capture to match against) writes nothing and exits 0, so the build
just goes without the module. The file is never committed (.gitignore), and site/build.py ignores
one more than 36 hours old.

Usage: python3 scripts/fetch_news.py [--season 2026]
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=50"
TIMEOUT = 10
MAX_ATHLETES = 4
LINK = re.compile(r"https://www\.espn\.com/[^\s\"'<>]+")
OFF_FIELD = re.compile(
    r"\b(lawsuits?|sue[sd]?|suing|trial|arrest\w*|charged|charges|assault\w*|abus\w+|defamation|divorce\w*"
    r"|investigat\w+|suspen\w+|dui|dwi|domestic|police|jail\w*|prison|court|indict\w*|felony|misdemeanor"
    r"|shooting|die[sd]|dead|death|killed|funeral|gambling|harass\w*|alleg\w+|accus\w+|restraining"
    r"|custody|probation|sentenc\w+|plea|plead(?:s|ed|ing)?|guilty|victim|crash|hospitali[sz]ed|murder\w*|homicide"
    r"|manslaughter|rape\w*|sexual\w*|misconduct|guns?|firearms?|weapons?|stabb\w+|fatal\w*|die|dying"
    r"|pass(?:es|ed) away|mourn\w*|overdos\w+|drugs?|burglar\w*|theft|robb\w+|warrant|detained"
    r"|arraign\w*)\b", re.IGNORECASE)


def roster_ids(season):
    """ESPN player ids on any league roster in the newest captured week. Empty if there's no capture."""
    captures = sorted((ROOT / "data" / str(season)).glob("week-*/espn.json"))
    if not captures:
        return set()
    capture = json.loads(captures[-1].read_text())
    return {p["player_id"] for m in capture["matchups"] for s in ("home", "away") for p in m[s]["lineup"]}


def keep(feed, rostered):
    """The trimmed articles worth keeping from one feed response. Anything malformed is skipped."""
    out = []
    for a in feed.get("articles") or []:
        try:
            ids = [int(c["athleteId"]) for c in a.get("categories") or []
                   if c.get("type") == "athlete" and c.get("athleteId") is not None]
            link = a["links"]["web"]["href"]
            headline, published = a["headline"], a["published"]
            datetime.fromisoformat(published.replace("Z", "+00:00"))
            if (not ids or len(ids) > MAX_ATHLETES or not rostered.intersection(ids)
                    or not isinstance(headline, str) or not LINK.fullmatch(link)
                    or OFF_FIELD.search(f"{headline} {a.get('description') or ''}")):
                continue
            row = {"id": a.get("id"), "headline": headline, "link": link, "published": published,
                   "athlete_ids": sorted(set(ids))}
            if isinstance(a.get("byline"), str):
                row["byline"] = a["byline"]
            out.append(row)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    args = ap.parse_args()
    try:
        season = args.season or json.loads((ROOT / "league.json").read_text())["season"]
        rostered = roster_ids(season)
        if not rostered:
            print("fetch_news: no capture to match against, nothing written", file=sys.stderr)
            return
        req = urllib.request.Request(FEED, headers={"User-Agent": "fantasy-recap"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            feed = json.load(res)
        articles = keep(feed, rostered)
        out = ROOT / "data" / str(season) / "news" / "latest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                   "articles": articles}, ensure_ascii=False, indent=1) + "\n")
        print(f"fetch_news: kept {len(articles)} of {len(feed.get('articles') or [])} articles")
    except Exception as e:  # noqa: BLE001 - best effort: no news is fine, a failed deploy is not
        print(f"fetch_news: skipped ({type(e).__name__})", file=sys.stderr)


if __name__ == "__main__":
    main()
