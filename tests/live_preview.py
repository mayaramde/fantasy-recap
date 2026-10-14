#!/usr/bin/env python3
"""Render the Live scoreboard in each of its states from committed data, for looking at in a browser.

The repo only holds finished weeks, so a normal build has no live week (and a branch preview can't show
this page). This turns the newest captured week into one in progress, with every starter's NFL game
before, during or after, and serves it with a scripted /api/live so the refresh behaviour (the +X.XX
tags, "Lead changed") can be watched too. Nothing here is a real week: scores are last week's, spread
over a made-up Sunday. It's for layout and behaviour, not for facts.

  python3 tests/live_preview.py <output dir>           write one static page per state
  python3 tests/live_preview.py <output dir> --serve   serve them on :8765, /api/live steps via /__step?n=K
"""
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
sys.path.insert(0, str(ROOT / "scripts"))
import analyze  # noqa: E402
import build  # noqa: E402

STARTING = analyze.STARTING
ISO = "%Y-%m-%dT%H:%M:%S.000Z"


def iso(dt):
    return dt.strftime(ISO)


def inprogress(last, *, playing=2, bump=None, win=None, captured_at=None, now=None):
    """`last` (a finished capture) as the next week with games under way.

    playing: starters per side with an NFL game on right now; 0 means between windows.
    bump: {team_id: extra points}, applied to that team's side (a touchdown landing).
    win: {matchup index: left-side win probability or None}; default 0.5 everywhere.
    """
    now = now or datetime.now(timezone.utc)
    week = copy.deepcopy(last)
    week.update(week=last["week"] + 1, complete=False, transactions=[], captured_at=captured_at or iso(now))
    bump = bump or {}
    win = win or {}
    for i, m in enumerate(week["matchups"]):
        m["winner"] = "UNDECIDED"
        for s in ("home", "away"):
            side = m[s]
            starters = [p for p in side["lineup"] if p["slot"] in STARTING]
            for n, p in enumerate(starters):
                if n < 3:     # done
                    p.update(game_state="post", game_clock=None, played=True, kickoff=iso(now - timedelta(hours=5)))
                elif n < 3 + playing:   # on the field, half his points banked
                    p.update(game_state="in", game_clock="Q3 7:22", played=True, points=round(p["points"] / 2, 2),
                             kickoff=iso(now - timedelta(hours=2)))
                else:         # kickoff ahead
                    p.update(game_state="pre", game_clock=None, played=False, points=0, scoring=[],
                             kickoff=iso(now + timedelta(hours=3 + n % 3)))
            side["points"] = round(sum(p["points"] for p in starters) + bump.get(side["team_id"], 0), 2)
            side["projected"] = round(side["points"] + sum(p["projected"] or 0 for p in starters if p["game_state"] == "pre"), 2)
        left, right = m["home"], m["away"]
        p = win.get(i, 0.5)
        left["win_probability"] = p
        right["win_probability"] = None if p is None else round(1 - p, 4)
    return week


def scenario(name, step=0):
    """(recap weeks, captured weeks, live week's facts, live week's capture, history) for a named state."""
    recap_weeks, captured, _, fp, _ = build.load_inputs(build.LEAGUE["season"])
    history = [e for _, e in captured]
    last = history[-1]
    kw = dict(win={0: 0.54, 1: 0.93, 2: 0.52, 3: 0.30})
    if name == "idle":
        kw["playing"] = 0
    if name == "noprob":
        kw["win"] = {i: None for i in range(4)}
    if name == "stale":
        kw["captured_at"] = iso(datetime.now(timezone.utc) - timedelta(minutes=12))
    t1, t2 = last["matchups"][0]["home"]["team_id"], last["matchups"][0]["away"]["team_id"]
    if name == "delta" and step >= 1:
        kw["bump"] = {t1: 6.4}
    if name == "flip":
        kw["bump"] = {t1: 0 if step == 0 else 60, t2: 0}
    nxt = inprogress(last, **kw)
    return recap_weeks, captured, nxt, history, fp


def page(name, step=0):
    recap_weeks, captured, nxt, history, fp = scenario(name, step)
    cap = captured + [(analyze.analyze(nxt, history + [nxt]), nxt)]
    html, _ = build.render(recap_weeks[:-1], cap, preview=False, fp=fp)
    return build.standalone(html)


def payload(name, step):
    recap_weeks, captured, nxt, history, fp = scenario(name, step)
    facts = analyze.analyze(nxt, history + [nxt])
    return build.live_payload(facts, nxt, history[-1], fp=fp, history=history)


STATES = ["live", "idle", "noprob", "stale", "delta", "flip"]


def main(out, serve):
    out.mkdir(parents=True, exist_ok=True)
    for n in STATES:
        (out / f"{n}.html").write_text(page(n))
    print(f"wrote {', '.join(n + '.html' for n in STATES)} in {out}")
    if not serve:
        return
    cur = {"name": "live", "step": 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            path, _, q = self.path.partition("?")
            args = dict(kv.split("=") for kv in q.split("&") if kv)
            if path == "/__step":
                cur.update(name=args["name"], step=int(args["n"]))
                body, ctype = b"ok", "text/plain"
            elif path == "/api/live":
                body, ctype = json.dumps(payload(cur["name"], cur["step"])).encode(), "application/json"
            else:
                body, ctype = (out / (path.strip("/") or "live.html")).read_bytes(), "text/html"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

    print("serving on http://127.0.0.1:8765")
    HTTPServer(("127.0.0.1", 8765), H).serve_forever()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    main(Path(args[0]), "--serve" in sys.argv)
