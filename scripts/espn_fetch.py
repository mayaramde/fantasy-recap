"""Fetch one week from ESPN and trim it exactly the way scripts/capture.js does.

capture.js runs in Chrome on Maya's logged-in session and stays the primary capture
path. This module is its Python twin, for the /api/live function (api/live.py), which
has to build the same espn.json shape server-side so scripts/analyze.py can consume it
unchanged — that is what keeps the Live page's numbers identical to the recap's.

Only the week being played needs a twin: the Coach page's week-ahead preview
(fantasyCapture('next')) is baked into the site at build time and never served from here,
so capture.js is its only author.

Two implementations of one trim is a divergence risk, so the shape they must agree on is
declared once here in SHAPE, and scripts/check.py asserts every committed espn.json
matches it. That catches a field added, renamed or retyped on one side. It cannot catch
the two sides computing the same field differently, so when you change capture.js's
trimming, change this too.

No cookies: the league is public on ESPN (the commissioner's setting), so every read here is
anonymous, the same as the public NFL scoreboard call. If the league goes private again, ESPN
answers 401 and every caller reports that rather than serving stale data.
"""

import json
import math
import urllib.error
import urllib.request
from datetime import datetime, timezone

SEASON = 2026
LEAGUE_ID = 698468554
BASE = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}"
PLAYERS = (f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}"
           "/players?scoringPeriodId=0&view=players_wl")
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

SLOT = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DST", 17: "K", 20: "BENCH", 21: "IR", 23: "FLEX"}
POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}


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


def _get(url, headers=None):
    req = urllib.request.Request(url, headers={"Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        hint = ": is the league still public on ESPN?" if e.code in (401, 403) else ""
        raise RuntimeError(f"ESPN {e.code}{hint}") from None


def _pro_games(week):
    """Which of this week's NFL games are on right now, keyed by ESPN pro team id (the same
    ids the fantasy API uses for proTeamId). The twin of proGames() in capture.js: public
    scoreboard, no cookies, and best effort — on any failure the players carry no game
    state and the site simply shows no marker."""
    url = f"{SCOREBOARD}?dates={SEASON}&seasontype=2&week={week}"
    games = {}
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            events = json.load(r).get("events") or []
        for ev in events:
            st = ev.get("status") or {}
            # 'pre' before kickoff, 'in' while the game is being played, 'post' once final
            state = (st.get("type") or {}).get("state")
            if not state:
                continue
            clock = None
            if state == "in":
                if (st.get("type") or {}).get("name") == "STATUS_HALFTIME":
                    clock = "Halftime"
                else:
                    period = st.get("period")
                    quarter = ("OT" if period > 4 else f"Q{period}") if period else None
                    clock = " ".join(x for x in (quarter, st.get("displayClock")) if x) or None
                clock = clock or (st.get("type") or {}).get("shortDetail") or None
            for c in ((ev.get("competitions") or [{}])[0].get("competitors") or []):
                games[int(c["id"])] = {"state": state, "clock": clock}
    except Exception:  # noqa: BLE001 - no game states is a missing marker, not a failed capture
        return {}
    return games


# The twin of CONTEXT_STATS in capture.js: stats that earn nothing but explain what did.
CONTEXT_STATS = {0, 1, 23, 58, 64, 84, 87, 120, 127}


def _scoring(stat):
    """The twin of scoringLines() in capture.js: ESPN's points per stat for the week, with
    the raw stat behind each one. Stat ids are ESPN's; naming them is the site's job."""
    if not stat:
        return []
    applied = stat.get("appliedStats") or {}
    raw = stat.get("stats") or {}
    ids = set(applied) | {k for k in raw if str(k).lstrip("-").isdigit() and int(k) in CONTEXT_STATS}
    lines = []
    for k in ids:
        points = round2(applied.get(k) or 0)
        value = round2(raw.get(k)) if raw.get(k) is not None else None
        if not points and not value:
            continue
        lines.append({"stat": int(k), "value": value, "points": points})
    lines.sort(key=lambda ln: (-abs(ln["points"]), ln["stat"]))
    return lines


def _pick_stat(stats, source, week):
    for s in stats or []:
        if (s.get("statSourceId") == source and s.get("scoringPeriodId") == week
                and s.get("statSplitTypeId") == 1):
            return s
    return None


def _side(s, week, names, games):
    if not s:
        return None
    lineup = []
    for e in (s.get("rosterForCurrentScoringPeriod") or {}).get("entries") or []:
        p = e["playerPoolEntry"]["player"]
        names[p["id"]] = p["fullName"]
        actual = _pick_stat(p.get("stats"), 0, week)
        proj = _pick_stat(p.get("stats"), 1, week)
        game = games.get(p.get("proTeamId"))
        lineup.append({
            "player_id": p["id"],
            "name": p["fullName"],
            "pos": POS.get(p.get("defaultPositionId")) or str(p.get("defaultPositionId")),
            "pro_team_id": p.get("proTeamId"),
            "slot": SLOT.get(e.get("lineupSlotId")) or str(e.get("lineupSlotId")),
            # ESPN's designation for the week: QUESTIONABLE, DOUBTFUL, OUT,
            # INJURY_RESERVE, SUSPENSION, ACTIVE... Absent for a D/ST and for anyone
            # ESPN isn't listing.
            "injury_status": p.get("injuryStatus"),
            "points": round2(_nn(actual.get("appliedTotal") if actual else None, 0)),
            "projected": round2(proj.get("appliedTotal") if proj else None),
            "played": bool(actual),
            # What those points were made of: yards, catches, touchdowns, a missed kick...
            "scoring": _scoring(actual),
            # His NFL game: 'pre', 'in' or 'post', and the game clock while it is 'in'
            "game_state": game["state"] if game else None,
            "game_clock": game["clock"] if game else None,
        })
    return {
        "team_id": s.get("teamId"),
        "points": round2(_nn(s.get("totalPointsLive"), s.get("totalPoints"))),
        "projected": round2(_nn(s.get("totalProjectedPointsLive"), s.get("totalProjectedPoints"))),
        "win_probability": s.get("winProbability"),
        "lineup": lineup,
    }


def current_week():
    return _get(f"{BASE}?view=mStatus")["status"]["currentMatchupPeriod"]


def fetch_week(week):
    """The trimmed capture for one week: the same dict scripts/capture.js POSTs."""
    box = _get(f"{BASE}?view=mBoxscore&view=mMatchupScore&scoringPeriodId={week}")
    teams_res = _get(f"{BASE}?view=mTeam")
    status_res = _get(f"{BASE}?view=mStatus")
    tx_res = _get(f"{BASE}?view=mTransactions2&scoringPeriodId={week}")
    games = _pro_games(week)

    names = {}
    matchups = [{"id": m.get("id"), "winner": m.get("winner"),
                 "home": _side(m.get("home"), week, names, games),
                 "away": _side(m.get("away"), week, names, games)}
                for m in box.get("schedule") or [] if m.get("matchupPeriodId") == week]

    # Names for transacted players who aren't on anyone's current lineup (e.g. dropped)
    txs = [t for t in tx_res.get("transactions") or [] if t.get("status") == "EXECUTED"]
    missing = sorted({i.get("playerId") for t in txs for i in t.get("items") or []} - set(names))
    if missing:
        filt = json.dumps({"filterIds": {"value": missing}})
        for pl in _get(PLAYERS, {"x-fantasy-filter": filt}) or []:
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
           "slot": "str", "points": "num", "projected": "num?", "played": "bool",
           # Added for the live box score, so weeks captured before it are missing both keys
           "game_state?": "str?", "game_clock?": "str?",
           # Added for the Coach page; same story for weeks captured before it
           "injury_status?": "str?",
           # Added for the player cards on the Coach page: ESPN's scoring for the week,
           # one row per stat. Absent for weeks captured before it, empty for a player
           # ESPN has no stat line for yet.
           "scoring?": [{"stat": "int", "value": "num?", "points": "num"}]}
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
