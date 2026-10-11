"""Local dev server: build the site, serve it, rebuild on change, reload the browser.

Serves the same tree Vercel would (site/dist/web-preview by default, drafts included;
--prod for the league copy in site/dist/web), plus /api/live backed by api/live.py, so
the Live page's refresh works locally exactly as it does on Vercel.

Watches site/, data/, recaps/ and league.json. Any change reruns site/build.py and the
open page reloads itself. Nothing here deploys; use scripts/deploy.sh for that.

HOST defaults to 127.0.0.1 on macOS, so drafts never reach the rest of the Wi-Fi, and to
0.0.0.0 elsewhere, so a v0/container sandbox's preview proxy can reach it. The server is
single-threaded on purpose: /api/live rewrites data/player_names.json when it resolves a
new name, and two overlapping requests could read it half-written.

Usage: python3 scripts/dev.py [--prod] [--port 3000] [--season 2026]
       npm run dev
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCH = [ROOT / "site", ROOT / "data", ROOT / "recaps", ROOT / "league.json"]
IGNORE = {"dist", "__pycache__", "raw"}
POLL_SECONDS = 0.75

RELOAD_SNIPPET = b"""<script>(()=>{let v;setInterval(async()=>{try{const r=await fetch('/__dev/version',{cache:'no-store'});const n=await r.text();if(v&&n!==v)location.reload();v=n}catch{}},1000)})()</script>"""


def load_live_module():
    spec = importlib.util.spec_from_file_location("live", ROOT / "api" / "live.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot():
    mtimes = {}
    for base in WATCH:
        if base.is_file():
            mtimes[base] = base.stat().st_mtime
            continue
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not IGNORE.intersection(path.relative_to(ROOT).parts):
                mtimes[path] = path.stat().st_mtime
    return mtimes


class Builder:
    def __init__(self, season):
        self.season = season
        self.version = 0
        self.lock = threading.Lock()

    def build(self):
        cmd = [sys.executable, str(ROOT / "site" / "build.py")]
        if self.season:
            cmd += ["--season", str(self.season)]
        started = time.monotonic()
        result = subprocess.run(cmd, cwd=ROOT)
        took = time.monotonic() - started
        if result.returncode == 0:
            with self.lock:
                self.version += 1
            print(f"dev: built in {took:.1f}s", flush=True)
        else:
            print(f"dev: build failed (exit {result.returncode}); serving the last good build", flush=True)
        return result.returncode == 0

    def watch(self):
        seen = snapshot()
        while True:
            time.sleep(POLL_SECONDS)
            current = snapshot()
            if current != seen:
                changed = {p for p in current.keys() | seen.keys() if current.get(p) != seen.get(p)}
                names = ", ".join(sorted(str(p.relative_to(ROOT)) for p in changed)[:3])
                more = f" (+{len(changed) - 3} more)" if len(changed) > 3 else ""
                print(f"dev: changed {names}{more}; rebuilding", flush=True)
                seen = current
                self.build()


def make_handler(builder, live):
    class DevHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/__dev/version":
                return self.send_text(str(builder.version))
            if path == "/api/live":
                return live.handler.do_GET(self)
            if path in ("/", "/index.html"):
                return self.send_index()
            return super().do_GET()

        def send_text(self, text):
            body = text.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_index(self):
            index = Path(self.directory) / "index.html"
            if not index.exists():
                self.send_error(503, "No build yet; check the terminal for build errors")
                return
            html = index.read_bytes()
            marker = b"</body>"
            html = html.replace(marker, RELOAD_SNIPPET + marker, 1) if marker in html else html + RELOAD_SNIPPET
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def end_headers(self):
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            super().end_headers()

        def log_message(self, fmt, *args):
            if not self.path.startswith("/__dev/"):
                super().log_message(fmt, *args)

    return DevHandler


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--prod", action="store_true", help="serve the league copy (site/dist/web) instead of the draft preview")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 3000)))
    ap.add_argument("--host", default=os.environ.get("HOST") or ("127.0.0.1" if sys.platform == "darwin" else "0.0.0.0"))
    ap.add_argument("--season", type=int, default=None)
    args = ap.parse_args()

    builder = Builder(args.season)
    builder.build()

    out = ROOT / "site" / "dist" / ("web" if args.prod else "web-preview")
    out.mkdir(parents=True, exist_ok=True)

    threading.Thread(target=builder.watch, daemon=True).start()

    handler = partial(make_handler(builder, load_live_module()), directory=str(out))
    server = HTTPServer((args.host, args.port), handler)
    label = "league site" if args.prod else "draft preview"
    print(f"dev: serving {label} from {out.relative_to(ROOT)} at http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ndev: stopped")


if __name__ == "__main__":
    main()
