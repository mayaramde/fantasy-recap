"""Fetch one week from ESPN and trim it exactly the way scripts/capture.js does.

capture.js runs in Chrome on Maya's logged-in session and stays the primary capture
path. This module is its Python twin, for the /api/live function (api/live.py), which
has to build the same espn.json shape server-side so scripts/analyze.py can consume it
unchanged — that is what keeps the Live page's numbers identical to the recap's.

Two implementations of one trim is a divergence risk, so the shape they must agree on is
declared once here in SHAPE, and scripts/check.py asserts every committed espn.json
matches it. That catches a field added, renamed or retyped on one side. It cannot catch
the two sides computing the same field differently, so when you change capture.js's
trimming, change this too.

Cookies come from ESPN_S2 / ESPN_SWID. They are never logged, returned or written.
"""

import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

SEASON = 2026
LEAGUE_ID = 698468554
BASE = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"
PLAYERS = (f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}"
           "/players?scoringPeriodId=0&view=players_wl")

SLOT = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DST", 17: "K", 20: "BENCH", 21: "IR", 23: "FLEX"}
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}


def cookie():
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
    if not s2 or not swid:
        raise RuntimeError("ESPN_S2 and ESPN_SWID are not set")
    return f"espn_s2={s2}; SWID={swid}"


def round2(x):
    """JS `Math.round(x * 100) / 100`. Halves go toward +Infinity, unlike Python's round(),
    and an integral result stays an int so the JSON matches capture.js's (0, not 0.0)."""
    if x is None:
        return None
    v = math.floor(x * 100 + 0.5) / 100
    return int(v) if v == int(v) else v


def _nn(*vals):
    """JS `a ?? b`: the first value that is not None (0 does not fall through)."""
    for v in vals:
        if v is not None:
            return v
    return None


def _iso(ms):
    ms = int(ms)
    dt = datetime.fromtimestamp(ms // 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def _now_iso():
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _get(url, ck, headers=None):
    req = urllib.request.Request(url, headers={"Cookie": ck, "Accept": "application/json",
                                               **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ESPN {e.code}: cookies may have expired") from None


def _pick_stat(stats, source, week):
    for s in stats or []:
        if (s.get("statSourceId") == source and s.get("scoringPeriodId") == week
                and s.get("statSplitTypeId") == 1):
            return s
    return None


def _side(s, week, names):
    if not s:
        return None
    lineup = []
    for e in (s.get("rosterForCurrentScoringPeriod") or {}).get("entries") or []:
        p = e["playerPoolEntry"]["player"]
        names[p["id"]] = p["fullName"]
        actual = _pick_stat(p.get("stats"), 0, week)
        proj = _pick_stat(p.get("stats"), 1, week)
        lineup.append({
            "player_id": p["id"],
            "name": p["fullName"],
            "pos": POS.get(p.get("defaultPositionId")) or str(p.get("defaultPositionId")),
            "pro_team_id": p.get("proTeamId"),
            "slot": SLOT.get(e.get("lineupSlotId")) or str(e.get("lineupSlotId")),
            "points": round2(_nn(actual.get("appliedTotal") if actual else None, 0)),
            "projected": round2(proj.get("appliedTotal") if proj else None),
            "played": bool(actual),
        })
    return {
        "team_id": s.get("teamId"),
        "points": round2(_nn(s.get("totalPointsLive"), s.get("totalPoints"))),
        "projected": round2(_nn(s.get("totalProjectedPointsLive"), s.get("totalProjectedPoints"))),
        "win_probability": s.get("winProbability"),
        "lineup": lineup,
    }


def current_week(ck=None):
    ck = ck or cookie()
    return _get(f"{BASE}?view=mStatus", ck)["status"]["currentMatchupPeriod"]


def fetch_week(week, ck=None):
    """The trimmed capture for one week: the same dict scripts/capture.js POSTs."""
    ck = ck or cookie()
    box = _get(f"{BASE}?view=mBoxscore&view=mMatchupScore&scoringPeriodId={week}", ck)
    teams_res = _get(f"{BASE}?view=mTeam", ck)
    status_res = _get(f"{BASE}?view=mStatus", ck)
    tx_res = _get(f"{BASE}?view=mTransactions2&scoringPeriodId={week}", ck)

    names = {}
    matchups = [{"id": m.get("id"), "winner": m.get("winner"),
                 "home": _side(m.get("home"), week, names), "away": _side(m.get("away"), week, names)}
                for m in box.get("schedule") or [] if m.get("matchupPeriodId") == week]

    # Names for transacted players who aren't on anyone's current lineup (e.g. dropped)
    txs = [t for t in tx_res.get("transactions") or [] if t.get("status") == "EXECUTED"]
    missing = sorted({i.get("playerId") for t in txs for i in t.get("items") or []} - set(names))
    if missing:
        filt = json.dumps({"filterIds": {"value": missing}})
        for pl in _get(PLAYERS, ck, {"x-fantasy-filter": filt}) or []:
            names[pl["id"]] = pl["fullName"]

    def name_of(pid):
        return names.get(pid) or (f"DST {-pid}" if pid is not None and pid < 0 else f"Player {pid}")

    transactions = sorted(({
        "type": t.get("type"),
        "team_id": t.get("teamId"),
        "date": _iso(t.get("processDate") or t.get("proposedDate")),
        "bid": t.get("bidAmount") or 0,
        "items": [{
            "type": i.get("type"),
            "player_id": i.get("playerId"),
            "name": name_of(i.get("playerId")),
            "from_team_id": i.get("fromTeamId"),
            "to_team_id": i.get("toTeamId"),
            "from_slot": SLOT.get(i.get("fromLineupSlotId")),
            "to_slot": SLOT.get(i.get("toLineupSlotId")),
        } for i in t.get("items") or []],
    } for t in txs), key=lambda t: t["date"])

    teams = [{"team_id": t.get("id"),
              "wins": (t.get("record") or {}).get("overall", {}).get("wins") or 0,
              "losses": (t.get("record") or {}).get("overall", {}).get("losses") or 0,
              "ties": (t.get("record") or {}).get("overall", {}).get("ties") or 0,
              "points_for": round2((t.get("record") or {}).get("overall", {}).get("pointsFor") or 0),
              "points_against": round2((t.get("record") or {}).get("overall", {}).get("pointsAgainst") or 0)}
             for t in teams_res.get("teams") or []]

    status = status_res.get("status") or {}
    return {
        "season": SEASON,
        "week": week,
        "captured_at": _now_iso(),
        "espn_status": {"current_matchup_period": status.get("currentMatchupPeriod"),
                        "latest_scoring_period": status.get("latestScoringPeriod")},
        "complete": bool(matchups) and all(m["winner"] and m["winner"] != "UNDECIDED" for m in matchups),
        "matchups": matchups,
        "teams": teams,
        "transactions": transactions,
    }


# ---------- the shape capture.js and fetch_week must agree on ----------

_PLAYER = {"player_id": "int", "name": "str", "pos": "str", "pro_team_id": "int?",
           "slot": "str", "points": "num", "projected": "num?", "played": "bool"}
# A "?" on a key means the key may be absent (week-01 and week-02 were captured before
# capture.js started recording win_probability); a "?" on a type means the value may be null.
_SIDE = {"team_id": "int", "points": "num", "projected": "num?", "win_probability?": "num?",
         "lineup": [_PLAYER]}
_ITEM = {"type": "str", "player_id": "int", "name": "str", "from_team_id": "int?",
         "to_team_id": "int?", "from_slot": "str?", "to_slot": "str?"}
SHAPE = {
    "season": "int", "week": "int", "captured_at": "str",
    "espn_status": {"current_matchup_period": "int?", "latest_scoring_period": "int?"},
    "complete": "bool",
    "matchups": [{"id": "int", "winner": "str", "home": _SIDE, "away": _SIDE}],
    "teams": [{"team_id": "int", "wins": "int", "losses": "int", "ties": "int",
               "points_for": "num", "points_against": "num"}],
    "transactions": [{"type": "str", "team_id": "int", "date": "str", "bid": "num",
                      "items": [_ITEM]}],
}

_TYPES = {"int": int, "str": str, "bool": bool, "num": (int, float)}


def shape_problems(obj, shape=SHAPE, path=""):
    """Every way `obj` disagrees with `shape`, as readable strings. Empty means it matches."""
    bad = []
    if isinstance(shape, dict):
        if not isinstance(obj, dict):
            return [f"{path or '<root>'}: expected an object, got {type(obj).__name__}"]
        spec = {k.rstrip("?"): (v, k.endswith("?")) for k, v in shape.items()}
        for k in sorted(set(spec) | set(obj)):
            if k not in obj:
                if not spec[k][1]:
                    bad.append(f"{path}.{k}: missing")
            elif k not in spec:
                bad.append(f"{path}.{k}: not in SHAPE (capture.js and espn_fetch.py disagree)")
            else:
                bad += shape_problems(obj[k], spec[k][0], f"{path}.{k}")
    elif isinstance(shape, list):
        if not isinstance(obj, list):
            return [f"{path}: expected a list, got {type(obj).__name__}"]
        for i, item in enumerate(obj):
            bad += shape_problems(item, shape[0], f"{path}[{i}]")
    else:
        optional = shape.endswith("?")
        want = _TYPES[shape.rstrip("?")]
        if obj is None:
            if not optional:
                bad.append(f"{path}: null, but SHAPE says {shape}")
        elif not isinstance(obj, want) or isinstance(obj, bool) is not (shape.rstrip("?") == "bool"):
            bad.append(f"{path}: {type(obj).__name__}, but SHAPE says {shape}")
    return bad
