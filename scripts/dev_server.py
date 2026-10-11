"""Local dev server that mirrors what Vercel serves: `npm run dev:vercel`.

Why this exists: v0 (and any other "import a repo, run its dev script" tool) needs one
command that builds the site and serves it on $PORT. The real deploy path stays
scripts/deploy.sh; this is for looking at the site, never for publishing it.

It builds with site/build.py and serves site/dist/web-preview, the draft copy Vercel's
branch previews serve. It deliberately does not go through scripts/vercel_build.sh: that
restages site/dist/out, which a concurrent `scripts/deploy.sh` on the same checkout is
about to ship to the league. It routes /api/live to api/live.py's handler, the same function Vercel runs. ESPN is
read anonymously as always; if it refuses, /api/live answers 503 and the page falls back
to its baked data, same as production. Stdlib only.

Env: PORT (default 3000), HOST (default 127.0.0.1 on macOS, so drafts never reach the rest
of the Wi-Fi; 0.0.0.0 elsewhere, so a v0/container sandbox's preview proxy can reach it).
Single-threaded on purpose: /api/live rewrites data/player_names.json when it resolves a
new name, and two overlapping requests could read it half-written.
"""
import os
import subprocess
import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "dist" / "web-preview"

sys.path.insert(0, str(ROOT))
from api.live import handler as LiveHandler  # noqa: E402


class DevHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0].rstrip("/") == "/api/live":
            # BaseHTTPRequestHandler subclasses share one interface, so the Vercel
            # handler's do_GET runs fine against this request's socket.
            LiveHandler.do_GET(self)
            return
        super().do_GET()

    def end_headers(self):
        # Keep every page out of search results, like vercel.json. /api/live sets its own.
        if not self.path.startswith("/api/"):
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    subprocess.run([sys.executable, str(ROOT / "site" / "build.py")], cwd=ROOT, check=True)

    host = os.environ.get("HOST") or ("127.0.0.1" if sys.platform == "darwin" else "0.0.0.0")
    port = int(os.environ.get("PORT", "3000"))
    server = HTTPServer((host, port), partial(DevHandler, directory=str(OUT)))
    print(f"dev_server: serving {OUT.relative_to(ROOT)} at http://localhost:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
