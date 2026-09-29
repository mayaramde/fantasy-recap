"""One-shot local receiver for ESPN captures.

Chrome (running scripts/capture.js on the ESPN tab) POSTs the trimmed JSON to
http://127.0.0.1:8765/save?week=N and this writes data/<season>/week-NN/espn.json,
so the data lands on disk byte-for-byte without being retyped. With &next=1 (the Coach
page's preview of the week ahead) it writes data/<season>/next-week/espn.json instead:
a week nobody has played doesn't belong in the numbered weeks, where the site would
read it as the week in progress.

Usage: python3 scripts/receive.py [--count N] [--timeout 120]
Also serves scripts/capture.js at GET /capture.js.
Listens on localhost only, accepts --count valid captures (default 1), then exits.
"""

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ORIGIN = "https://lm-api-reads.fantasy.espn.com"
PORT = 8765


class Handler(BaseHTTPRequestHandler):
    saved = []

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin == ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        # Serve the capture script so Chrome runs exactly what's on disk
        if urlparse(self.path).path != "/capture.js":
            return self._reply(404, {"error": "not found"})
        payload = (ROOT / "scripts" / "capture.js").read_bytes()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/javascript")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/save" or self.headers.get("Origin") != ALLOWED_ORIGIN:
            return self._reply(403, {"error": "forbidden"})
        try:
            query = parse_qs(url.query)
            week = int(query["week"][0])
            nxt = query.get("next", ["0"])[0] == "1"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            data = json.loads(body)
            assert data["week"] == week and 1 <= week <= 18
            assert len(data["matchups"]) > 0
        except Exception as e:  # noqa: BLE001
            return self._reply(400, {"error": f"invalid capture: {e}"})

        folder = "next-week" if nxt else f"week-{week:02d}"
        out = ROOT / "data" / str(data["season"]) / folder / "espn.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        Handler.saved.append(out)
        self._reply(200, {"saved": str(out.relative_to(ROOT)), "bytes": out.stat().st_size})

    def _reply(self, code, obj):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=120, help="seconds to wait for all captures")
    ap.add_argument("--count", type=int, default=1, help="number of weekly captures to accept")
    args = ap.parse_args()
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    deadline = time.monotonic() + args.timeout
    print(f"Waiting for capture on http://127.0.0.1:{PORT}/save ...", flush=True)
    while len(Handler.saved) < args.count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print("Timed out waiting for capture", file=sys.stderr)
            return 1
        server.timeout = remaining
        server.handle_request()  # returns after one request (e.g. CORS preflight) or timeout
    for out in Handler.saved:
        print(f"Saved {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
