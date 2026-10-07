"""/api/live — the current week's Live payload, computed from ESPN on request.

Why this exists: the Live page used to be baked into the HTML, so showing a fresher score
meant recapturing, rebuilding and redeploying the whole site (hourly, from GitHub
Actions). This function does the same work per request instead, so the page can refresh
itself in seconds.

It deliberately reuses scripts/analyze.py and site/build.py unchanged, because the Live
page's numbers have to be the same numbers the Tuesday recap will quote. The only piece
written twice is the ESPN trim (scripts/capture.js in Chrome, scripts/espn_fetch.py here),
and scripts/check.py holds those two to one declared shape.

The bundle mirrors the repo layout (see scripts/deploy.sh), so analyze.py and build.py
resolve league.json and data/ exactly as they do on Maya's Mac. History comes from the
committed weeks in the bundle; only the current week is fetched live.

Responses are cached at Vercel's CDN for 20 seconds, so eight people watching the same
game still cost ESPN about three requests a minute between them. There is deliberately no Access-Control-Allow-Origin: the Claude artifact
build must keep rendering from its baked data rather than quietly depending on this.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).resolve().parent
# In the deployed bundle this file sits at the root, beside league.json and scripts/.
# In the repo it sits in api/, one level down. Supporting both is what lets this be
# exercised locally (see scripts/check.py).
ROOT = HERE if (HERE / "league.json").exists() else HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "site"))

# The page asks every 20 seconds while games are on, so the CDN holds each answer for
# just under that: everyone watching a game still shares one request to ESPN, but nobody
# is served a score that's most of a minute old.
CACHE = "public, s-maxage=20, stale-while-revalidate=120"


def live_payload():
    import analyze
    import build
    import espn_fetch

    ck = espn_fetch.cookie()
    week = espn_fetch.current_week(ck)
    current = espn_fetch.fetch_week(week, ck)

    season_dir = ROOT / "data" / str(current["season"])
    history = [json.loads(p.read_text()) for p in sorted(season_dir.glob("week-*/espn.json"))]
    history = sorted([w for w in history if w["week"] < week] + [current], key=lambda w: w["week"])

    analyze.resolve_names(history)
    # The capture before this one, so the Coach page can tell a new injury designation
    # from one that was already there last week.
    previous = max((w for w in history if w["week"] < week), key=lambda w: w["week"], default=None)
    # Today's FantasyPros snapshot, if fantasy-coach-daily has written one — committed to
    # git (unlike next-week/espn.json), so it ships in this bundle like league.json does.
    fp = build.load_fantasypros(current["season"])
    return build.live_payload(analyze.analyze(current, history), current, previous, fp=fp,
                              history=[w for w in history if w["week"] < week])


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = json.dumps(live_payload(), ensure_ascii=False, separators=(",", ":"))
        except Exception as e:  # noqa: BLE001 - any failure here is just "no live upgrade"
            # RuntimeError is ours and safe to show ("ESPN 401: cookies may have expired").
            # Anything else could carry internals, so it stays generic. Neither can contain
            # the cookies: espn_fetch never puts them in a message.
            reason = str(e) if isinstance(e, RuntimeError) else "live data unavailable"
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps({"error": reason}).encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", CACHE)
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.end_headers()
        self.wfile.write(body.encode())
