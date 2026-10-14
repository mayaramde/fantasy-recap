"""Build the recap site from data/ facts + recaps/ writeups.

Writes two self-contained single-file sites (pages are hash routes inside one HTML file):
  site/dist/index.html    league site: only weeks whose recap has "status": "published"
  site/dist/preview.html  Maya's review copy: published + draft weeks (drafts are marked)
  site/dist/web/          the league site as a standalone web page for Vercel (index.html + robots.txt)

A "live" page shows the newest captured week that has no recap in that output yet
(in progress, or final and waiting for Tuesday's recap). It's data only, no commentary.
A "coach" page hangs off the same week: per team, what to do about it before kickoff
(who to swap in, who's hurt, which slot is empty), all computed from that same capture.

Season stats (standings, all-play, streaks, team pages) are computed only from the
weeks included in each output, so the league site never leaks a draft week's results.

Usage: python3 site/build.py [--season 2026]
"""

import argparse
import json
import os
import re
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import playoffs
import team_profile

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
LEAGUE = json.loads((ROOT / "league.json").read_text())

AWARD_KEYS = ("game_balls", "flags", "tough_breaks")
PLAYER_KEYS = ("name", "pos", "slot", "points", "projected")

# ---------- coach page: the shape of a legal lineup ----------
# Which positions can fill each starting slot, and how many of each the league starts.
SLOT_OK = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"},
           "FLEX": {"RB", "WR", "TE"}, "DST": {"DST"}, "K": {"K"}}
LINEUP = {k.split(" (")[0]: n for k, n in LEAGUE["roster_slots"].items()
          if k.split(" (")[0] not in ("BENCH", "IR")}
SLOT_ORDER = list(LINEUP)
STARTING = set(LINEUP)

# ESPN's injury designations, in the words the site shows. Anything else (ACTIVE,
# NORMAL, or nothing at all) means ESPN isn't listing him.
INJURY_LABEL = {"OUT": "Out", "DOUBTFUL": "Doubtful", "QUESTIONABLE": "Questionable",
                "INJURY_RESERVE": "On IR", "SUSPENSION": "Suspended", "DAY_TO_DAY": "Day to day"}
# The same designations in the middle of a sentence ("ESPN lists him as ...")
INJURY_PHRASE = {"OUT": "out", "DOUBTFUL": "doubtful", "QUESTIONABLE": "questionable",
                 "INJURY_RESERVE": "on injured reserve (IR)", "SUSPENSION": "suspended",
                 "DAY_TO_DAY": "day to day"}
# Said once, the first time a card leans on the jargon
IR_NOTE = " A player on IR is hurt long enough that he can't be put in a lineup at all."
SIDELINED = {"OUT", "DOUBTFUL", "INJURY_RESERVE", "SUSPENSION"}   # won't play, or probably won't
IFFY = {"QUESTIONABLE", "DAY_TO_DAY"}                              # a game-time decision
# A projection is an estimate, so only a gap this big is worth calling a swap.
SWAP_MIN = 2.0
LEVELS = ("now", "watch", "info")


def player(p, live):
    """One row of a box score. `playing` is the game clock ("Q3 7:22") while that player's
    NFL game is on, and absent otherwise, so a finished week carries no live leftovers.
    The NFL team logo rides along on the live week, which is the only page that shows it,
    and `injury` is ESPN's designation in plain words, absent when he isn't listed."""
    row = {k: p.get(k) for k in PLAYER_KEYS}
    if live:
        # player_id is what pairs a row with its Coach card (see player_cards); it is an
        # ESPN *player* id, the same one the headshot URLs already carry, never a member's.
        row.update(logo=p.get("logo"), team=p.get("team"), player_id=p.get("player_id"), kickoff=p.get("kickoff"))
    if p.get("game_state") == "in":
        row["playing"] = p.get("game_clock") or "on now"
    if INJURY_LABEL.get(p.get("injury_status")):
        row["injury"] = INJURY_LABEL[p["injury_status"]]
    return row


def side(t, live=False):
    return {
        "team_id": t["team_id"], "manager": t["manager"], "team_name": t["team_name"],
        "points": t["points"], "projected": t["projected"], "optimal": t["optimal_points"],
        "points_left": t["points_left_on_bench"], "result": t["result"],
        "live_projection": t.get("live_projection"), "win_probability": t.get("win_probability"),
        "yet_to_play": t.get("yet_to_play", 0), "playing_now": t.get("playing_now", 0),
        "swaps": [{k: s[k] for k in ("started", "started_points", "started_pos", "benched", "benched_points",
                                     "benched_pos", "slot", "gain")}
                  for s in t["lineup_swaps"]],
        "starters": [player(p, live) for p in t["starters"]],
        "bench": [player(p, live) for p in t["bench"]],
    }


LOWLIGHT_COUNT = 3
HEADSHOT_URL = "https://a.espncdn.com/i/headshots/nfl/players/full/{}.png"


def worst_performances(facts):
    """The starters who fell furthest short of ESPN's projection. Only players whose NFL game
    is over count, so a live week never calls a Sunday-night starter a bust at kickoff."""
    rows = []
    for t in facts["teams"]:
        for p in t["starters"]:
            final = facts["complete"] or p.get("game_state") == "post"
            # A starter who never played (scratch, inactive) is a missing player, not a bad game
            if final and p.get("played", True) and (p.get("projected") or 0) > 0 and p["points"] < p["projected"]:
                dst = p.get("pos") == "DST"
                rows.append({"name": p["name"], "pos": p.get("pos"), "manager": t["manager"], "slot": p["slot"],
                             "points": p["points"], "projected": p["projected"],
                             "short": round(p["projected"] - p["points"], 2),
                             # Same photo/logo shape as top_performers, so the site draws both alike
                             "headshot": p.get("logo") if dst else HEADSHOT_URL.format(p["player_id"]),
                             "logo": None if dst else p.get("logo"), "team": None if dst else p.get("team")})
    return sorted(rows, key=lambda r: r["short"], reverse=True)[:LOWLIGHT_COUNT]


def week_payload(facts, recap, live=False):
    teams = {t["team_id"]: t for t in facts["teams"]}
    games, seen = [], set()
    for t in facts["teams"]:
        key = tuple(sorted((t["team_id"], t["opponent_id"])))
        if key in seen:
            continue
        seen.add(key)
        a, b = teams[key[0]], teams[key[1]]
        winner, loser = (a, b) if a["points"] >= b["points"] else (b, a)
        games.append({"key": f"{key[0]}-{key[1]}", "winner": side(winner, live), "loser": side(loser, live),
                      "blurb": recap.get("matchups", {}).get(f"{key[0]}-{key[1]}", "")})
    games.sort(key=lambda g: g["winner"]["points"] + g["loser"]["points"], reverse=True)

    lg = facts["league"]
    return {
        "week": facts["week"],
        "status": recap.get("status", "draft"),
        "complete": facts["complete"],
        "headline": recap.get("headline", ""),
        "dek": recap.get("dek", ""),
        "games": games,
        **{k: recap.get(k, []) for k in AWARD_KEYS},
        "glossary": recap.get("glossary", []),
        "standings": facts["standings"],
        "top_performers": lg["top_performers"],
        "worst_performances": worst_performances(facts),
        "high_score": lg["high_score"],
        "low_score": lg["low_score"],
        "median": lg["median_score"],
        "mid_pack": lg["mid_pack"],
    }


# ---------- coach: what each team should do about the live week ----------
# Every line below is read off the capture: ESPN's own projections, its injury
# designations, and which NFL games have kicked off. Nothing here is a hunch, and
# nothing invents news ESPN didn't report.


def _proj(p):
    return p.get("projected") or 0.0


def _f1(x):
    return f"{x:.1f}"


def _f2(x):
    return f"{x:.2f}"


def _an(x):
    """A projection with the article you'd say in front of it: "an 8.2", "a 20.4"."""
    s = _f1(x)
    return f"{'an' if s[:1] == '8' or s[:2] in ('11', '18') else 'a'} {s}"


def _pts(x):
    """A score the way you'd say it out loud: 8, 12.3, 20.55. Exact to the cent, but a
    trailing zero in the middle of a sentence reads like a spreadsheet."""
    return f"{round(x, 2):g}"


def injury_map(espn):
    """Every rostered player's injury designation in one captured week.

    Empty for a week captured before the site recorded injuries at all: without the
    field there is no telling a healthy player from an unrecorded one, and guessing
    would call every designation "new".
    """
    rows = [p for m in espn["matchups"] for s in (m["home"], m["away"]) if s for p in s["lineup"]]
    if not any("injury_status" in p for p in rows):
        return {}
    return {p["player_id"]: p.get("injury_status") for p in rows}


# ---------- coach: FantasyPros-sourced cards, authored daily by a separate task ----------
# fantasy-coach-daily (a scheduled Claude session, not this script) writes finished, voiced
# cards straight into data/<season>/fantasypros/latest.json — the same way the weekly recap
# writes game_balls/flags/tough_breaks. This file only reads, validates and merges: it never
# invents a word of FantasyPros-sourced copy itself.
FP_MAX_AGE = timedelta(hours=36)


def load_fantasypros(season):
    """Best-effort read of the daily FantasyPros snapshot. None if missing or malformed,
    so every caller can fall back to ESPN-only advice without a special case."""
    path = ROOT / "data" / str(season) / "fantasypros" / "latest.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(data.get("weeks"), dict) or "generated_at" not in data:
        return None
    return data


def _fp_fresh(fp):
    """A snapshot left over from a missed run is worse than none: it would tell a
    manager about "news since yesterday" that's actually a week stale."""
    if not fp:
        return False
    try:
        generated = datetime.fromisoformat(fp["generated_at"].replace("Z", "+00:00"))
    except (ValueError, KeyError):
        return False
    return datetime.now(timezone.utc) - generated <= FP_MAX_AGE


def _valid_fp_card(it):
    return (isinstance(it, dict) and it.get("kind") and it.get("level") in LEVELS
            and it.get("title") and it.get("text") and (it["kind"] != "trade" or _valid_trade(it.get("trade"))))


def _valid_trade(t):
    """A trade card's `trade` block, as coach-daily copies it from scripts/trade_eval.py: who it's
    with, the players each way, and both sides' numbers. A trade card without one is a lead nobody
    evaluated, and the Coach page no longer shows those."""
    def players(xs):
        return (isinstance(xs, list) and xs
                and all(isinstance(x, dict) and type(x.get("id")) is int and x.get("name") for x in xs))

    def side(s):
        return (isinstance(s, dict) and isinstance(s.get("near"), (int, float))
                and all(isinstance(s.get(k), list) and len(s[k]) == 2 for k in ("playoff", "title")))

    return (isinstance(t, dict) and type(t.get("partner_id")) is int and players(t.get("give"))
            and players(t.get("get")) and side(t.get("you")) and side(t.get("them")))


# An injury designation that takes a player out of a trade (scripts/trade_eval.py's rule 7).
_CANT_PLAY = {"OUT", "INJURY_RESERVE", "SUSPENSION"}


def trade_deadline():
    """league.json's "trade_deadline" (ESPN's, an ISO 8601 time with its offset) as an aware
    datetime, or None when it isn't set or doesn't parse."""
    try:
        return datetime.fromisoformat(LEAGUE["trade_deadline"])
    except (KeyError, TypeError, ValueError):
        return None


def past_trade_deadline(now=None):
    """True once ESPN stops taking trades. A card written the morning before still has a
    day and a half to live in the snapshot, so the page checks the clock itself."""
    deadline = trade_deadline()
    return bool(deadline and deadline.tzinfo) and (now or datetime.now(timezone.utc)) >= deadline


def live_trades(rows, teams, now=None):
    """Drop every trade card that no longer describes the league: a player in it has changed
    rosters, or has since been ruled out, or the trade deadline has passed. coach-daily re-runs the evaluation every morning; this
    keeps a card from outliving its trade between runs. `rows` are advice_payload()'s, `teams`
    the facts-shaped teams they were built from."""
    roster = {t["team_id"]: {p["player_id"]: p for p in t["starters"] + t["bench"]} for t in teams}

    def holds(team_id, players):
        mine = roster.get(team_id, {})
        return all(x["id"] in mine and mine[x["id"]].get("injury_status") not in _CANT_PLAY for x in players)

    closed = past_trade_deadline(now)
    for row in rows:
        row["roster_ideas"] = [it for it in row["roster_ideas"] if it.get("kind") != "trade"
                               or (not closed and holds(row["team_id"], it["trade"]["give"])
                                   and holds(it["trade"]["partner_id"], it["trade"]["get"]))]
    return rows


def fantasypros_cards(team_id, fp, week):
    """(advice_items, roster_ideas) for one team in one week, from today's FantasyPros
    snapshot — or ([], []) if the file is missing, stale, or has nothing for that team and
    week. Every card here is already fully authored; this only selects and validates shape."""
    if not _fp_fresh(fp):
        return [], []
    wk = (fp.get("weeks") or {}).get(str(week)) or {}
    row = (wk.get("teams") or {}).get(str(team_id)) or {}
    return ([it for it in row.get("advice_cards", []) if _valid_fp_card(it)],
            [it for it in row.get("roster_ideas", []) if _valid_fp_card(it)])


# ---------- coach: this week's advice, written daily for the cards computed below ----------
# Every computed card carries a `key` naming the exact situation behind it ("swap:<starter>:
# <bench player>:<his status>"). coach-daily writes voiced, voice-checked copy for each key
# into the same snapshot; the site shows it only while that key is still on the list, so a
# card whose situation has moved on since the morning (a kickoff, a new injury) quietly
# falls back to its computed wording instead of giving yesterday's advice. The written copy
# never carries a projection or a percentage: those move all day, so they stay in the
# computed stat pill, which /api/live refreshes on every request.
_MOVING_NUMBER = re.compile(r"\d?\.\d|%|\bpercent\b|\d+[- ]?(?:points?|pts)\b", re.IGNORECASE)


def _valid_written(it):
    return (isinstance(it, dict) and isinstance(it.get("title"), str) and isinstance(it.get("text"), str)
            and it["title"].strip() and it["text"].strip()
            and not _MOVING_NUMBER.search(it["title"] + it["text"]))


def written_cards(team_id, fp, week):
    """({key: {title, text}}, summary or None) for one team in one week, from today's
    snapshot — or ({}, None) if it's missing, stale, or has nothing written for them."""
    if not _fp_fresh(fp):
        return {}, None
    wk = (fp.get("weeks") or {}).get(str(week)) or {}
    row = (wk.get("teams") or {}).get(str(team_id)) or {}
    cards = row.get("coach_cards")
    cards = {k: v for k, v in cards.items() if _valid_written(v)} if isinstance(cards, dict) else {}
    summary = row.get("summary")
    ok = (isinstance(summary, dict) and isinstance(summary.get("key"), str)
          and _valid_written({"title": "-", "text": summary.get("text")}))
    return cards, (summary if ok else None)


def apply_written(items, cards):
    """Swap in the written title and text for every computed card whose situation still
    holds. Kind, level and stat stay computed: they're what the page sorts and counts by,
    and the stat pill is where the live number lives."""
    for it in items:
        w = cards.get(it.get("key"))
        if w:
            it.update(title=w["title"].strip(), text=w["text"].strip(), written=True)
    return items


def written_audit(team_id, fp):
    """{key: {title, text}} for one team's season-audit cards, from the snapshot's top-level
    `audit`. No freshness gate, unlike the coach cards: an audit key fully describes weeks
    that are already over, so copy written for a key that still matches is still true
    however old the file is. A missing or malformed snapshot just means computed wording."""
    audit = fp.get("audit") if fp else None
    if not isinstance(audit, dict):
        return {}
    row = audit.get(str(team_id))
    return {k: v for k, v in row.items() if _valid_written(v)} if isinstance(row, dict) else {}


def _key(*parts):
    return ":".join("none" if p is None else str(p) for p in parts)


# ---------- coach: one line about the team, for under the page header ----------
# Flavor on top of the to-do list below it, never a fact of its own: everything here is
# read off the same items and counts the list is built from, so it can't say anything the
# list doesn't already back up.
TEAM_SUMMARY_BY_KIND = {
    "out": ["Somebody in your starting lineup is on ESPN's injury report. The fix is right below.",
            "Somebody in your starting lineup won't be playing this week, and the sideline scores zero."],
    "bye": ["Half your lineup, or so it feels, is on a beach this week.",
            "Bye weeks: the NFL's way of telling you to go check your bench."],
    "swap": ["Somewhere on your bench, ESPN thinks a better lineup is just sitting there.",
             "Your bench is quietly outprojecting your actual lineup. Rude, but probably right."],
    "empty": ["There's an empty seat in your starting lineup, and empty seats score zero.",
              "A blank spot in your lineup is doing exactly what you'd expect: nothing."],
    "hole": ["ESPN expects a big fat zero from someone in your lineup, and isn't shy about it.",
             "Somebody in your starting lineup is projected for nothing at all."],
}
TEAM_SUMMARY_WATCH = [
    "Nothing urgent, but ESPN's still holding its breath on somebody in your lineup.",
    "Nothing to fix yet, though there's a name or two worth a second look before kickoff.",
]
TEAM_SUMMARY_CLEAR = [
    "Everything's set. Go watch the games.",
    "Nothing to fix here. Your lineup is exactly what ESPN would draw up. Look at you.",
]
TEAM_SUMMARY_DEFAULT = ["There's work to do before kickoff. Good news: it's all listed below."]


def team_summary(team_id, items, counts, can_change, win_probability):
    """One cheeky sentence for the top of a team's Coach page, when coach-daily hasn't
    written one for this exact situation (see summary_key).

    Picks the loudest thing on the to-do list (the most common kind among its "now"
    items) and says something about that, so it never drifts from what the cards below
    actually list. `team_id` only chooses which of a few phrasings to use, the same way
    player cards pick a voice — so a manager doesn't get a different joke every time the
    Live page refreshes with no real change underneath it.
    """
    if not can_change:
        return ("Every game on your schedule this week is in the books. "
                "This lineup is now a matter of historical record.")
    now_items = [it for it in items if it["level"] == "now"]
    if not now_items:
        if counts["watch"]:
            return TEAM_SUMMARY_WATCH[team_id % len(TEAM_SUMMARY_WATCH)]
        if win_probability is not None:
            pct = round(win_probability * 100)
            return (f"Nothing to fix here, and ESPN gives you a {pct}% chance to win this week. Act natural."
                    if pct >= 50 else
                    f"Nothing to fix here. ESPN only gives you a {pct}% chance to win, "
                    "and ESPN has been wrong before.")
        return TEAM_SUMMARY_CLEAR[team_id % len(TEAM_SUMMARY_CLEAR)]
    dominant = Counter(it["kind"] for it in now_items).most_common(1)[0][0]
    options = TEAM_SUMMARY_BY_KIND.get(dominant, TEAM_SUMMARY_DEFAULT)
    return options[team_id % len(options)]


# ---------- coach: one expandable card per player on the lineup ----------
# Same rule as the to-do cards: every sentence is read off the capture. The numbers are
# ESPN's own (its points, its projection, its injury report, its game clock) and the jokes
# are ours. Nothing here reports news no source gave us, and nothing calls a player
# healthy just because ESPN isn't listing him.

COUNT_WORD = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}


def _voice(p, options):
    """Pick one phrasing for this player, always the same one.

    A hundred and twenty cards on one page shouldn't read like a form letter, and a player
    shouldn't change his mind every time the Live data refreshes, so his ESPN id chooses.
    """
    return options[p["player_id"] % len(options)]


def _pct(part, whole):
    return round(100 * part / whole) if whole else 0


def _td_line(p):
    """" Two touchdowns." — only ever what the stat line carries."""
    td = p.get("touchdowns") or 0
    if td < 1:
        return ""
    if td == 1:
        return " There's a touchdown in there."
    return f" {COUNT_WORD.get(td, td)} touchdowns. Screenshot it."


def player_blurb(p, starting, ctx):
    """One cheeky line about a player's week, built only from his own numbers.

    `ctx["projected"]` is False on the next-week tab while ESPN still hasn't published
    projections for it, and then nothing here quotes one: a 0.0 read as a forecast is
    worse than saying we don't know yet.
    """
    his = "its" if p["pos"] == "DST" else "his"
    guess = ctx["projected"]
    pts, proj = p["points"], _proj(p)
    gap = round(pts - proj, 2)
    st = p.get("injury_status")
    spot = p["slot"] if starting else "bench"

    if ctx["on_bye"](p):
        return ("This defense is on a bye this week, so it plays nobody and scores exactly 0.0."
                if p["pos"] == "DST" else
                "He doesn't have a game this week. His NFL team is on a bye, so that's a "
                "guaranteed 0.0 from wherever you put him.")
    if p["slot"] == "IR" and pts <= 0.005:
        return ("He's in your injured-reserve spot, which is where ESPN parks a player hurt long "
                "enough that he can't be put in a lineup at all.")
    if p.get("game_state") == "in":
        return ((f"On the field right now: {_pts(pts)} on the board against {_an(proj)} projection."
                 if guess else f"On the field right now, with {_pts(pts)} on the board.")
                + _td_line(p))
    # Before kickoff the injury report is the whole story; after it, the score is (ESPN can
    # still be carrying a designation for a player who has already played).
    if not ctx["locked"](p):
        if st in SIDELINED:
            if starting and st == "INJURY_RESERVE":
                # Often season-ending, so no joke here: just the fix.
                return ("ESPN has him on injured reserve (IR), which is rough news. Move someone into "
                        "his spot before kickoff.")
            if starting:
                return _voice(p, [
                    f"ESPN lists him {INJURY_PHRASE[st]}, which makes that {_f1(proj)}-point "
                    f"projection a lovely piece of fiction." if guess else
                    f"ESPN lists him {INJURY_PHRASE[st]}, and he's in your starting lineup. That's the "
                    f"one to fix while there's still time.",
                    f"He's {INJURY_PHRASE[st]} on ESPN's report. Starting him is a hope, not a plan.",
                ])
            return (f"ESPN lists him {INJURY_PHRASE[st]}, so he's staying put. The bench is the right "
                    f"place for that.")
        if not guess:
            return _voice(p, [
                "ESPN hasn't put a projection on him for that week yet. They usually land a few days "
                "out, so this is one to look at again later.",
                "No projection from ESPN for that week yet. It's early, so check back closer to "
                "kickoff.",
            ])
        return _voice(p, [
            f"Hasn't kicked off yet. ESPN pencils him in for {_f1(proj)}, which is a guess in a nice suit.",
            f"The {_f1(proj)} next to {his} name is a projection, not a promise.",
            f"ESPN says {_f1(proj)} for him. The football gets the final word.",
        ])
    # His game has started, so the number on the row is the story.
    if pts < -0.005:
        return (f"{_pts(pts)} points. Negative. He lost you points from the {spot} spot, which takes "
                f"a particular kind of week." if starting else
                f"{_pts(pts)} points. Negative! Luckily it's from the bench, where it costs you nothing.")
    if pts <= 0.005:
        if st == "INJURY_RESERVE":
            return "0.0 points. He's on injured reserve (IR), so there was no game for him this week."
        if st in SIDELINED:
            return (f"0.0 points, which is what ESPN's \u201c{INJURY_LABEL[st]}\u201d "
                    f"tag was trying to tell you.")
        return (f"A donut: 0.0 points out of the {spot} spot. An empty chair scores the same."
                if starting else
                "0.0 points, and from the bench, which is exactly where you want your zeroes.")
    if not starting:
        if gap >= 5:
            return _voice(p, [
                f"{_pts(pts)} points on {_an(proj)} projection, from your bench, where they count "
                f"for precisely nothing. Sorry.",
                f"He went and scored {_pts(pts)} against {_an(proj)} projection while sitting on "
                f"your bench. File it under \u201cwe don't talk about that\u201d.",
            ]) + _td_line(p)
        return _voice(p, [
            f"{_pts(pts)} points off the bench, against {_an(proj)} projection.",
            f"{_pts(pts)} from the bench, where ESPN expected {_f1(proj)}. No harm either way.",
            f"ESPN said {_f1(proj)}, the afternoon said {_pts(pts)}, and it all happened on your bench.",
        ]) + _td_line(p)
    if gap >= 8:
        return _voice(p, [
            f"Cooked: {_pts(pts)} points on {_an(proj)} projection, {_f1(gap)} more than anyone "
            f"asked for.",
            f"{_pts(pts)} against {_an(proj)} projection. That's the ceiling, and he found it.",
        ]) + _td_line(p)
    if gap >= 3:
        return (f"A good day at the office: {_pts(pts)} on {_an(proj)} projection, "
                f"{_f1(gap)} to the good." + _td_line(p))
    if gap <= -8:
        return _voice(p, [
            f"{_pts(pts)} points where {_f1(proj)} were forecast. {_f1(-gap)} of them went missing and "
            f"nobody has seen them since.",
            f"Rough: {_pts(pts)} against {_an(proj)} projection, {_f1(-gap)} short of the ask.",
        ]) + _td_line(p)
    if gap <= -3:
        return f"A quiet one: {_pts(pts)} on {_an(proj)} projection, {_f1(-gap)} short." + _td_line(p)
    return f"Exactly what it said on the tin: {_pts(pts)} on {_an(proj)} projection." + _td_line(p)


def player_notes(p, starting, ctx):
    """The short factual list under the blurb: how much of the team he is, what ESPN's
    injury report says, where his game is up to, and what else you had at that spot. The
    blurb already covers his points against his projection, and the row prints both, so
    none of that is repeated here. At most five lines."""
    notes = []
    pts = p["points"]
    st = p.get("injury_status")
    state = p.get("game_state")
    started = ctx["locked"](p)

    if starting and pts > 0.005 and ctx["team_points"] > 0.005:
        notes.append(f"That's {_pct(pts, ctx['team_points'])}% of your {_pts(ctx['team_points'])} so far.")
    if pts > 0.005 and p["player_id"] == (ctx["top_starter"] if starting else ctx["top_bench"]):
        notes.append("Your highest-scoring starter this week." if starting
                     else "The best score on your bench this week.")

    if st in SIDELINED or st in IFFY:
        notes.append(f"ESPN's injury report lists him {INJURY_PHRASE[st]}.{ctx['news'](p)}")
    else:
        was = ctx["before"].get(p["player_id"])
        if was in SIDELINED or was in IFFY:
            notes.append(f"He was listed {INJURY_PHRASE[was]} in Week {ctx['before_week']} and "
                         f"isn't on the report any more.")

    if ctx["on_bye"](p):
        notes.append("That NFL team is on a bye this week, so there's no game to score in.")
    elif state == "in":
        notes.append(f"That game is on right now ({p.get('game_clock') or 'in progress'}).")
    elif state == "post":
        notes.append("That game is final, so the number is the number.")
    elif state == "pre":
        notes.append("Kickoff is still ahead, so you can still make a change here.")

    if starting and not started and ctx["can_change"]:
        alt = ctx["bench_best"](p["slot"])
        if alt:
            notes.append(f"Best option behind him on your bench: {alt['name']}"
                         + (f" ({_f1(_proj(alt))} projected)." if ctx["projected"] else "."))
    elif not starting and p["slot"] != "IR" and st not in SIDELINED and not ctx["on_bye"](p):
        rival = ctx["starter_for"](p)
        # Only worth saying once there are points to compare: on a week nobody has played,
        # both sides of it are 0.0.
        if rival and max(pts, rival["points"]) > 0.005:
            if pts > rival["points"] + 0.005:
                notes.append(f"Outscoring your starting {rival['slot']}, {rival['name']} "
                             f"({_pts(rival['points'])}), from the bench.")
            else:
                notes.append(f"Would have gone in for {rival['name']} at {rival['slot']}, who is on "
                             f"{_pts(rival['points'])}.")

    add = ctx["pickups"].get(p["name"])
    if add:
        how = "off waivers" if add["type"] == "WAIVER" else "off the free-agent pile"
        bid = f" for ${add['bid']}" if add.get("bid") else ""
        notes.append(f"You picked him up {how} in Week {add['week_added']}{bid}.")

    return notes[:5]


def player_cards(starters, bench, ctx):
    """Every player on this roster, keyed by ESPN player id: the line the site shows when
    someone taps his row. `lines` is ESPN's own scoring for the week (see
    scripts/analyze.py), empty for a player it has no stat line for yet."""
    cards = {}
    for p, starting in [(x, True) for x in starters] + [(x, False) for x in bench]:
        cards[str(p["player_id"])] = {
            "blurb": player_blurb(p, starting, ctx),
            "lines": p.get("scoring_lines") or [],
            "notes": player_notes(p, starting, ctx),
            # His NFL game: 'pre', 'in', 'post', or None; bye is "no game this week", which the
            # lineup rows draw as BYE rather than as a projection of nothing.
            "state": p.get("game_state"),
            "bye": bool(ctx["on_bye"](p)),
        }
    return cards


def injury_report(starters, bench, on_bye):
    """Who on one roster is hurt or on a bye, for the Coach page's "Injuries and byes" card:
    [{name, pos, team, logo, status, role}], starters first. `status` is ESPN's designation in
    plain words (see INJURY_LABEL), or "Bye" for a healthy player whose NFL team has no game;
    `role` is "starting" or "bench" (a player on IR counts as bench). A designation wins over
    a bye, since being hurt is the more useful thing to say."""
    out = []
    for role, pool in (("starting", starters), ("bench", bench)):
        for p in pool:
            status = INJURY_LABEL.get(p.get("injury_status")) or ("Bye" if on_bye(p) else None)
            if status:
                out.append({"name": p["name"], "pos": p.get("pos"), "team": p.get("team"),
                            "logo": p.get("logo"), "status": status, "role": role})
    return out


def team_advice(team, before, before_week, states_known, projected=True, week_open=True,
                fp_items=(), fp_ideas=(), written=None, written_summary=None):
    """One team's to-do list for a week.

    `before` maps player id to that player's injury designation in the previous captured
    week (week `before_week`), so a designation that is new can be called new. It's empty
    when there's no earlier capture to compare with. `states_known` is False when the NFL
    scoreboard call failed, in which case nobody is called locked or on a bye on a guess.
    `projected` is False when ESPN hasn't published projections for the week yet (it can
    be days out on next week's), and then nothing here compares two numbers that are both
    zero: no swaps, and nobody is called projected zero. `week_open` is False once every
    NFL game of the week has kicked off, when no lineup change and no waiver pickup can
    score another point, so nothing is asked of anybody.

    `fp_items` and `fp_ideas` are already-authored FantasyPros-sourced cards for this team
    and week (see fantasypros_cards) — never generated here, only merged in. `written` and
    `written_summary` are coach-daily's copy for the computed cards themselves, keyed by
    situation (see written_cards); a card with no written copy keeps its computed wording.
    """
    order = {slot: i for i, slot in enumerate(SLOT_ORDER)}
    starters = sorted(team["starters"], key=lambda p: order.get(p["slot"], len(order)))
    bench = [p for p in team["bench"] if p["slot"] != "IR"]
    starter_ids = {p["player_id"] for p in starters}

    def locked(p):
        """His NFL game has kicked off, so the lineup can't move him any more."""
        if states_known:
            return p.get("game_state") in ("in", "post")
        return bool(p.get("played"))

    def on_bye(p):
        """His NFL team has no game this week, so he cannot score."""
        return states_known and p.get("game_state") is None

    def playable(p):
        """He has a game this week that hasn't kicked off — the only kind of player a
        lineup change can still involve. A player on a bye is never "locked", because no
        game of his ever starts, but there is equally nothing he can still do."""
        return not locked(p) and not on_bye(p)

    def free(p):
        """Healthy, playing this week, and still swappable."""
        return playable(p) and p.get("injury_status") not in SIDELINED

    def news(p):
        """" That's new since Week 2." — when the previous capture can tell us."""
        pid = p["player_id"]
        if pid not in before or before[pid] == p.get("injury_status"):
            return ""
        was = before[pid]
        if was in SIDELINED or was in IFFY:
            return f" He was listed {INJURY_PHRASE[was]} in Week {before_week} too."
        return f" That's new since Week {before_week}, when ESPN wasn't listing him at all."

    # Whether anything this team does can still change its score: at least one player
    # with a game ahead of him, in a week that still has games in it. Without this, a
    # starter on a bye or on IR — neither of whom is ever "locked" — keeps a waiver-wire
    # card at "do this now" long after the last whistle of the week.
    can_change = week_open and any(playable(p) for p in starters + bench)

    claimed = set()   # bench players already promised to a slot, so nobody is spent twice
    said_ir = []      # the IR explainer earns its space once per team, not once per card

    def backup(slot):
        pool = [b for b in bench if b["pos"] in SLOT_OK.get(slot, ()) and free(b)
                and b["player_id"] not in claimed]
        return max(pool, key=_proj, default=None)

    def shape(p):
        """How a bench player is doing, since "healthy" is a claim, not a default. He can
        still be the best option while carrying a designation of his own."""
        st = p.get("injury_status")
        return f"listed {INJURY_PHRASE[st]} himself" if st in IFFY else "off the injury report"

    def how(p):
        """"(17.1 projected, off the injury report)", or just the status when ESPN has
        published no projections for the week — quoting 0.0 would read as a forecast."""
        return f"({_f1(_proj(p))} projected, {shape(p)})" if projected else f"({shape(p)})"

    def worth(p):
        """" 12.4 projected" as a card's stat pill, where there is a projection to quote."""
        return f"{_f1(_proj(p))} projected" if projected else ""

    def no_backup(slot):
        """Why there's no swap: an empty bench at that position reads differently from a
        bench whose players are themselves hurt, on a bye or already playing."""
        eligible = [b for b in bench if b["pos"] in SLOT_OK.get(slot, ())]
        if not eligible:
            return f"Nobody on your bench plays {slot}"
        if len(eligible) == 1:
            return f"The one {slot} on your bench is hurt, on a bye or already playing"
        return f"Every {slot} on your bench is hurt, on a bye or already playing"

    def ir_note(p):
        if p.get("injury_status") != "INJURY_RESERVE" or said_ir:
            return ""
        said_ir.append(True)
        return IR_NOTE

    items, covered = [], set()

    # 1. Starters who can't help you: hurt, suspended, or on a bye.
    for s in starters:
        hurt = s.get("injury_status") in SIDELINED
        bye = on_bye(s)
        if locked(s) or not (hurt or bye):
            continue
        r = backup(s["slot"])
        if not r and not can_change:
            # Nothing on the bench and no time left: the only advice would be a waiver
            # pickup that can't score this week. Next week's tab carries it instead.
            continue
        covered.add(s["player_id"])
        phrase = INJURY_PHRASE.get(s.get("injury_status"), "out")
        # "ESPN lists him as on injured reserve (IR). A player on IR is hurt long enough..."
        why = (f"ESPN lists {s['name']} as {phrase}.{ir_note(s)}" if hurt else
               f"{s['name']}'s NFL team is on a bye this week, so he doesn't play at all.")
        if r:
            claimed.add(r["player_id"])
            title = f"Start {r['name']} over {s['name']}"
            text = (f"{why}{news(s)} {r['name']} is on your bench, {shape(r)}"
                    + (f", and projected {_f1(_proj(r))} points" if projected else "")
                    + f". Move him into the {s['slot']} spot.")
        else:
            title = f"{s['name']} is {phrase}" if hurt else f"{s['name']} is on a bye"
            text = (f"{why}{news(s)} {no_backup(s['slot'])}, so the only fix is the waiver wire, "
                    f"the pool of players nobody in the league owns.")
        kind = "bye" if bye and not hurt else "out"
        items.append({"kind": kind, "level": "now", "title": title,
                      "key": _key(kind, s["player_id"], s["slot"], s.get("injury_status") if hurt else "bye",
                                  r["player_id"] if r else None, r.get("injury_status") if r else None),
                      "stat": "Bye" if bye and not hurt else INJURY_LABEL.get(s.get("injury_status"), "Out"),
                      "text": text})

    # 2. Game-time decisions get their own card further down. Claim them now so no swap
    #    card is written about a starter whose own status is still in the air.
    iffy_starters = [s for s in starters
                     if not locked(s) and s["player_id"] not in covered
                     and s.get("injury_status") in IFFY]
    covered.update(s["player_id"] for s in iffy_starters)

    # 3. Straight upgrades: a bench player ESPN projects well above a starter he can replace.
    pairs = []
    for s in (starters if projected else []):
        if locked(s) or s["player_id"] in covered:
            continue
        for b in bench:
            if b["pos"] not in SLOT_OK.get(s["slot"], ()) or not free(b) or b["player_id"] in claimed:
                continue
            gain = round(_proj(b) - _proj(s), 2)
            if gain >= SWAP_MIN:
                pairs.append((gain, s, b))
    pairs.sort(key=lambda x: (-x[0], x[1]["name"], x[2]["name"]))
    swapped = set()
    for gain, s, b in pairs:
        if s["player_id"] in swapped or b["player_id"] in claimed:
            continue
        swapped.add(s["player_id"])
        claimed.add(b["player_id"])
        items.append({"kind": "swap", "level": "now",
                      "key": _key("swap", s["player_id"], s["slot"], b["player_id"], b.get("injury_status")),
                      "title": f"Start {b['name']} over {s['name']}",
                      "stat": f"+{_f1(gain)} projected", "gain": gain,
                      "text": (f"ESPN projects {b['name']} for {_f1(_proj(b))} points and {s['name']} for "
                               f"{_f1(_proj(s))}. Both can play {s['slot']}, so that's {_f1(gain)} points of "
                               f"difference for one tap"
                               + (f", though {b['name']} is {INJURY_PHRASE[b['injury_status']]}, so check he's "
                                  f"playing first" if b.get("injury_status") in IFFY else "")
                               + ". A projection is an estimate, not a promise, but a gap this size is "
                               "usually worth taking.")})

    # 4. A starting slot with nobody in it scores exactly zero.
    filled = Counter(s["slot"] for s in starters) if can_change else Counter(LINEUP)
    for slot, need in LINEUP.items():
        for n in range(need - filled.get(slot, 0)):
            r = backup(slot)
            if r:
                claimed.add(r["player_id"])
            items.append({"kind": "empty", "level": "now", "title": f"Your {slot} spot is empty",
                          "key": _key("empty", slot, n, r["player_id"] if r else None, r.get("injury_status") if r else None),
                          "stat": "nobody starting",
                          "text": (f"There's nobody in your {slot} spot, and an empty spot scores zero. "
                                   + (f"{r['name']} {how(r)} can fill it."
                                      if r else f"{no_backup(slot)}, so try the waiver wire."))})

    # 5. The game-time decisions themselves. Last of the lineup passes, so the backup it
    #    names is one nothing above has already spent.
    for s in iffy_starters:
        label = INJURY_LABEL[s["injury_status"]]
        r = backup(s["slot"])
        plan = (f"If he's ruled out, {r['name']} {how(r)} is your best swap."
                if r else f"{no_backup(s['slot'])}, so check early.")
        items.append({"kind": "watch", "level": "watch",
                      "key": _key("watch", s["player_id"], s["injury_status"], r["player_id"] if r else None,
                                  r.get("injury_status") if r else None),
                      "title": f"{s['name']} is {label.lower()}",
                      "stat": worth(s) or label,
                      "text": (f"{label} means his team hasn't decided whether he plays; the call usually "
                               f"lands about 90 minutes before kickoff.{news(s)} {plan}")})

    # 6. A starter ESPN expects nothing from, with no better option behind him.
    for s in (starters if projected and can_change else []):
        if locked(s) or s["player_id"] in covered or s["player_id"] in swapped or _proj(s) > 0.05:
            continue
        items.append({"kind": "hole", "level": "now", "title": f"{s['name']} is projected zero",
                      "key": _key("hole", s["player_id"]),
                      "stat": "0.0 projected",
                      "text": (f"ESPN expects nothing from {s['name']} at {s['slot']} this week, and your "
                               f"bench has nothing better. Worth a look at the waiver wire.")})

    # 7. Injury news since the last capture, for players no card above mentions. Starters
    #    first, and only the three loudest: this is the news feed, not the to-do list.
    fresh = []
    for p in starters + bench:
        pid = p["player_id"]
        if pid in covered or pid in claimed or pid in swapped or pid not in before:
            continue
        was, now = before[pid], p.get("injury_status")
        if was == now:
            continue
        starting = pid in starter_ids
        where = "starting" if starting else "on your bench"
        too_late = " His game has already kicked off, so there's nothing to do about it now." if locked(p) else ""
        if now in SIDELINED or now in IFFY:
            fresh.append((0 if starting else 1, {
                "kind": "news", "level": "watch" if starting and not locked(p) else "info",
                "key": _key("news", pid, now, "starting" if starting else "bench",
                            "locked" if locked(p) else "open"),
                "title": f"{p['name']} is now listed {INJURY_LABEL[now].lower()}",
                "stat": INJURY_LABEL[now],
                "text": (f"New since Week {before_week}: ESPN has {p['name']} ({p['pos']}, {where}) as "
                         f"{INJURY_PHRASE[now]}.{too_late}")}))
        elif was in SIDELINED or was in IFFY:
            fresh.append((2, {
                "kind": "back", "level": "info",
                "key": _key("back", pid, "starting" if starting else "bench"),
                "title": f"{p['name']} is off the injury report",
                "stat": worth(p) or "Back",
                "text": (f"He was listed {INJURY_PHRASE[was]} in Week {before_week} and isn't any more. "
                         f"He's {where}.")}))
    items += [it for _, it in sorted(fresh, key=lambda x: x[0])[:3]]

    if not items:
        done = not can_change
        items.append({"kind": "clear", "level": "info", "title": "Nothing to fix", "stat": "",
                      "key": _key("clear", "done" if done else "open" if projected else "unprojected"),
                      "text": ("Every game you had this week is done, so this lineup is what it is. "
                               "Anything worth changing is on next week's list."
                               if done else
                               ("Every starter still to play is off the injury report and has a game this "
                                "week, and nobody on your bench is projected to beat him by 2 or more. Go "
                                "enjoy the games." if projected else
                                "Every starter is off the injury report and has a game that week. ESPN hasn't "
                                "published its projections yet, so the start-or-sit calls come later."))})

    # Everything the per-player cards need. `bench_best` and `starter_for` deliberately
    # ignore `claimed`: a card describes one player's own week, and two cards naming the
    # same bench player is fine, where two to-do items spending him twice would not be.
    def bench_best(slot):
        return max((b for b in bench if b["pos"] in SLOT_OK.get(slot, ()) and free(b)),
                   key=_proj, default=None)

    def starter_for(b):
        """The starter this bench player would have gone in for: the lowest-scoring one
        whose slot his position can fill."""
        return min((s for s in starters if b["pos"] in SLOT_OK.get(s["slot"], ())),
                   key=lambda s: s["points"], default=None)

    def best_id(pool):
        top = max(pool, key=lambda p: p["points"], default=None)
        return top["player_id"] if top else None

    ctx = {
        "locked": locked, "on_bye": on_bye, "news": news,
        "before": before, "before_week": before_week,
        "projected": projected, "can_change": can_change,
        # next_week_teams() builds the roster half of a team only: no result, no points.
        "team_points": team.get("points") or 0,
        "top_starter": best_id(starters), "top_bench": best_id(team["bench"]),
        "bench_best": bench_best, "starter_for": starter_for,
        "pickups": {a["name"]: a for a in team.get("pickups_started", [])},
    }

    # FantasyPros-sourced cards join the to-do list as if they'd always been part of it —
    # they carry their own {kind, level, title, stat, text} shape already, so counts and
    # the team summary read across them the same way they read ESPN's own cards.
    apply_written(items, written or {})
    # Keyed off the computed cards alone, before FantasyPros' join the list, so it matches
    # what coach_brief printed for coach-daily (which runs without a snapshot).
    skey = summary_key(items, can_change)
    items = items + [it for it in fp_items if it not in items]

    rank = {lvl: i for i, lvl in enumerate(LEVELS)}
    items.sort(key=lambda it: rank[it["level"]])
    return {
        "team_id": team["team_id"], "manager": team["manager"], "team_name": team["team_name"],
        "opponent_id": team["opponent_id"],
        "projected": team.get("live_projection") if team.get("live_projection") is not None else team["projected"],
        "win_probability": team.get("win_probability"),
        "yet_to_play": team.get("yet_to_play", 0),
        "playing_now": team.get("playing_now", 0),
        # Starters whose game hasn't kicked off: the ones a lineup change can still reach.
        # Wider than yet_to_play, which counts only players with a game ahead of them —
        # a starter on a bye is movable but has nothing to play in.
        "movable": sum(1 for s in starters if playable(s)),
        # False once the week is out of reach: the page stops asking for changes nobody
        # can make any more and points at next week instead.
        "can_change": can_change,
        "items": items,
        "counts": (counts := {lvl: sum(1 for it in items if it["level"] == lvl) for lvl in LEVELS}),
        # One cheeky line for the top of her Coach page, under the header.
        "summary": (written_summary["text"].strip() if written_summary and written_summary["key"] == skey else
                    team_summary(team["team_id"], items, counts, can_change, team.get("win_probability"))),
        # What a written summary has to be keyed to, for coach-daily's brief
        "summary_key": skey,
        # Everyone on the roster who is hurt or on a bye, for the "Injuries and byes" card
        "report": injury_report(starters, team["bench"], on_bye),
        # One card per player on the roster, for the lineup rows on her Coach page
        "players": player_cards(starters, team["bench"], ctx),
        # Waiver/trade leads from FantasyPros — not a per-week to-do, so kept separate from
        # the now/watch/info list. Empty when today's snapshot has nothing for this team.
        "roster_ideas": list(fp_ideas),
    }


def summary_key(items, can_change):
    """What a written summary line has to match to replace the computed one: the exact
    cards it would be summing up (every "now" card, else every "watch" card), so a summary
    naming this morning's swap stops showing the moment the swap list changes."""
    if not can_change:
        return "done"
    for level in ("now", "watch"):
        keys = sorted(it["key"] for it in items if it["level"] == level and it.get("key"))
        if keys:
            return "|".join([level] + keys)
    return "clear"


def advice_payload(teams, espn, previous, fp=None, week=None):
    """The Coach page's data: one entry per team, in league order.

    `teams` are facts.json-shaped (starters, bench, opponent_id), either from a played
    week's facts or from next_week_teams(). `previous` is the capture before this one (or
    None), which is what lets an injury designation be called new rather than just current.
    `fp` is today's FantasyPros snapshot (see load_fantasypros), best effort like everything
    else here: with no snapshot, or nothing for this `week`, every team just gets its
    ESPN-only cards, same as before this existed.
    """
    rows = [p for m in espn["matchups"] for s in (m["home"], m["away"]) if s for p in s["lineup"]]
    # Both calls behind these are best effort. With no NFL game states, no player is
    # called locked or on a bye on a guess; with no projections published for the week,
    # no card pretends to compare them.
    states_known = any(p.get("game_state") for p in rows)
    projected = any(p.get("projected") for p in rows)
    # Is there any football left this week? Read across the whole league, not one roster,
    # so a manager with nobody in the late game still gets told the truth. With no game
    # states at all (the scoreboard is best effort) assume the week is still live rather
    # than silencing every card.
    week_open = not states_known or any(p.get("game_state") == "pre" for p in rows)
    before = injury_map(previous) if previous else {}
    by_id = {t["team_id"]: t for t in teams}
    rows_out = []
    for t in LEAGUE["teams"]:
        if t["team_id"] not in by_id:
            continue
        fp_items, fp_ideas = fantasypros_cards(t["team_id"], fp, week)
        written, written_summary = written_cards(t["team_id"], fp, week)
        rows_out.append(team_advice(by_id[t["team_id"]], before, previous["week"] if previous else None,
                                    states_known, projected, week_open, fp_items, fp_ideas,
                                    written, written_summary))
    return live_trades(rows_out, teams)


# ---------- midweek landing page: two computed cards for a week nobody's watching live ----------
# Both read only numbers already on the capture — no invented reasons, same rule as everything
# else in Coach. They ride into a team's regular card list (team_advice's `items`) so the client
# renders them with the exact same components as every other Coach card.


def lookback_card(team, teams, week):
    """One cheeky, computed line about how a team just did, for a week that's finished but
    hasn't been recapped yet. The moment a real recap ships for this week, `live_payload`
    stops covering it and this card stops appearing on its own — the authored recap is the
    story from then on, not a guess at one."""
    ranked = sorted(teams, key=lambda t: t["points"], reverse=True)
    rank = next(i for i, t in enumerate(ranked, 1) if t["team_id"] == team["team_id"])
    pts, opp_pts = team["points"], team["opponent_points"]
    margin = abs(round(pts - opp_pts, 2))
    won = team["result"] == "W"
    verb = "Won" if won else "Lost"
    if rank == 1:
        text = f"Top score in the league this week: {_pts(pts)} points."
    elif rank == len(teams):
        text = f"Bottom of the league this week with {_pts(pts)} points. Nowhere to go but up."
    elif team["points_left_on_bench"] >= 15:
        text = (f"{verb} {_pts(pts)}-{_pts(opp_pts)}, but left {_f1(team['points_left_on_bench'])} points "
                f"sitting on the bench doing it.")
    elif margin <= 3:
        text = f"{verb} by just {_f1(margin)}. About as close as it gets."
    elif margin >= 30:
        text = f"{'A blowout win' if won else 'A blowout loss'}, {_f1(margin)} points apart."
    else:
        text = f"{verb} {_pts(pts)}-{_pts(opp_pts)}."
    return {"kind": "recap", "level": "info", "key": _key("recap", week, team["result"], rank, _f1(margin)), "title": f"Week {week} recap",
            "stat": f"{_pts(pts)} pts", "text": text}


def opponent_preview_card(row, by_id, record_by_id):
    """A heads-up about whoever's on the other side of a week that hasn't kicked off yet:
    her record this season and the one player on her roster most likely to hurt you. Read
    straight off the same capture as every other Coach card, never a guess."""
    opp = by_id.get(row["opponent_id"])
    if not opp:
        return None
    rec = record_by_id.get(opp["team_id"])
    record_txt = (f"{rec['wins']}-{rec['losses']}" + (f"-{rec['ties']}" if rec.get("ties") else "")) if rec else ""
    who = opp["manager"] + (f" ({record_txt})" if record_txt else "")
    starters = [p for p in opp.get("starters", []) if p.get("projected")]
    threat = max(starters, key=_proj, default=None)
    if not threat:
        text = f"You're playing {who} next. No projections on her roster yet to say who to watch."
        stat = record_txt
    else:
        st = threat.get("injury_status")
        if st in SIDELINED or st in IFFY:
            text = (f"You're playing {who} next. Her highest-projected starter is {threat['name']} "
                    f"({threat['pos']}), and ESPN lists him {INJURY_PHRASE[st]}. Check back before kickoff "
                    f"to see who she plays instead.")
        else:
            text = (f"You're playing {who} next. Keep an eye on {threat['name']} ({threat['pos']}), "
                    f"projected for {_f1(_proj(threat))}.")
        stat = record_txt or f"{_f1(_proj(threat))} projected"
    return {"kind": "matchup", "level": "info", "title": f"Next up: {opp['manager']}", "stat": stat, "text": text,
            "key": _key("matchup", opp["team_id"], threat["player_id"] if threat else None,
                        threat.get("injury_status") if threat else None)}


def next_week_teams(capture):
    """Teams shaped like facts.json's, from a capture of a week nobody has played.

    scripts/analyze.py is all about results — who won, what was left on the bench — and a
    week with no results has none of that. The Coach page only ever reads the roster half
    of a team, so build that half here rather than running the whole analysis over zeros.
    """
    manager = {t["team_id"]: t["manager"].split(" (")[0] for t in LEAGUE["teams"]}
    name = {t["team_id"]: t["team_name"] for t in LEAGUE["teams"]}
    teams = []
    for m in capture["matchups"]:
        for a, b in ((m["home"], m["away"]), (m["away"], m["home"])):
            if not a or not b:
                continue
            starters = [p for p in a["lineup"] if p["slot"] in STARTING]
            teams.append({
                "team_id": a["team_id"], "manager": manager.get(a["team_id"], "?"),
                "team_name": name.get(a["team_id"], ""), "opponent_id": b["team_id"],
                "starters": starters,
                "bench": [p for p in a["lineup"] if p["slot"] in ("BENCH", "IR")],
                "projected": round(sum(p["projected"] or 0 for p in starters), 2),
                # Nothing has kicked off, so every starter is still to play and none is
                # on the field. No score, so ESPN publishes no win probability either.
                "yet_to_play": len(starters), "playing_now": 0, "win_probability": None,
            })
    return teams


def next_payload(capture, previous, fp=None):
    """The Coach page's "next week" tab: the same advice, a week early.

    Baked at build time and never refreshed by /api/live, because next week's numbers
    move about once a day, not once a minute — and because asking ESPN for a second week
    on every request would double what the live page costs it. `fp` (today's FantasyPros
    snapshot) is looked up under this week's own number, so it's only used if
    fantasy-coach-daily actually wrote cards for the week ahead, not just the live one.
    """
    teams = next_week_teams(capture)
    rows = advice_payload(teams, capture, previous, fp=fp, week=capture["week"])
    lineups = {t["team_id"]: {"starters": [player(p, True) for p in t["starters"]],
                              "bench": [player(p, True) for p in t["bench"]]} for t in teams}
    by_id = {t["team_id"]: t for t in teams}
    record_by_id = {t["team_id"]: t for t in capture["teams"]}
    for r in rows:
        r["lineup"] = lineups[r["team_id"]]
        r["projected"] = by_id[r["team_id"]]["projected"]
        # A week that hasn't started yet is exactly when "who's next" is worth saying.
        opp = opponent_preview_card(r, by_id, record_by_id)
        if opp:
            apply_written([opp], written_cards(r["team_id"], fp, capture["week"])[0])
            r["items"] = [opp] + r["items"]
            r["counts"]["info"] += 1
    return {"week": capture["week"], "captured_at": capture["captured_at"],
            # ESPN can be days from publishing next week's projections; the page says so
            # instead of showing a column of zeros.
            "projected": any(p.get("projected") for t in teams for p in t["starters"]),
            "teams": rows}


# ---------- week hub: the league wire ----------
WIRE_DAYS = 7
TRADE_DONE = ("TRADE_ACCEPT", "TRADE_UPHOLD")


def _when(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _rosters(capture):
    """{player_id: (team_id, name)} for everyone on a league roster in one capture."""
    return {p["player_id"]: (m[s]["team_id"], p["name"])
            for m in capture.get("matchups") or [] for s in ("home", "away") for p in m[s]["lineup"]}


def _trades(capture, before):
    """Trades executed during `capture`'s week, as [(date, {team_id: [names she received]})].

    ESPN's log says a trade went through (TRADE_UPHOLD) but leaves the players empty, and the team
    on that record isn't reliably one of the two who traded. So who moved is read off the rosters
    instead: a player on a different league team than in the capture before, with no pickup on record
    to explain it, was traded. No trade record in the log, no trade here, however the rosters look.
    """
    txs = capture["transactions"]
    done = sorted(t["date"] for t in txs if t["type"] in TRADE_DONE)
    if not done:
        return []
    # The league's go-ahead (UPHOLD) is when the players actually moved; the accept can be days earlier.
    upheld = [t["date"] for t in txs if t["type"] == "TRADE_UPHOLD"]
    when = max(upheld) if upheld else done[-1]
    out = []
    for t in txs:      # the well-formed case, if ESPN ever sends it: the players are on the record
        got = {}
        for i in t["items"] if t["type"] == "TRADE_ACCEPT" else ():
            if i["type"] == "TRADE" and i.get("to_team_id"):
                got.setdefault(i["to_team_id"], []).append(i["name"])
        if len(got) == 2:
            out.append((t["date"], got))
    if out or not before:
        return out
    picked_up = {(i["player_id"], i["to_team_id"]) for t in txs for i in t["items"] if i["type"] == "ADD"}
    was, pairs = _rosters(before), {}
    for pid, (team, name) in _rosters(capture).items():
        if pid in was and was[pid][0] != team and (pid, team) not in picked_up:
            pairs.setdefault(frozenset((team, was[pid][0])), {}).setdefault(team, []).append(name)
    # A trade moves players both ways; anything one-directional is something else, so it's left out.
    return [(when, got) for _, got in sorted(pairs.items(), key=lambda kv: sorted(kv[0])) if len(got) == 2]


def wire(espn, history=()):
    """The league's last week of roster activity, newest first, for the Week hub.

    Three kinds of event, each one read off ESPN's transaction log: "move" (a pickup and/or a drop),
    "trade", and "lineup" (somebody rearranged her starters; `promoted` is the player ids she moved off
    the bench, which can be none). Declined trade offers are deliberately not here: they're private between two managers.
    The page groups these by day in the reader's own time zone, so that's left to the browser.
    """
    manager = {t["team_id"]: t["manager"].split(" (")[0] for t in LEAGUE["teams"]}
    cutoff = _when(espn["captured_at"]) - timedelta(days=WIRE_DAYS)
    captures = sorted([h for h in history if h["week"] < espn["week"]], key=lambda c: c["week"]) + [espn]
    events = []
    for before, cap in zip([None] + captures, captures):
        for t in cap["transactions"]:
            if _when(t["date"]) < cutoff or t["team_id"] not in manager:
                continue
            base = {"date": t["date"], "team_id": t["team_id"], "manager": manager[t["team_id"]]}
            added = [i["name"] for i in t["items"] if i["type"] == "ADD" and i["to_team_id"] == t["team_id"]]
            dropped = [i["name"] for i in t["items"] if i["type"] == "DROP"]
            lineup = [i for i in t["items"] if i["type"] == "LINEUP"]
            if (added or dropped) and not t["type"].startswith("TRADE"):
                events.append({**base, "kind": "move", "added": added, "dropped": dropped,
                               "waiver": t["type"] == "WAIVER"})
            elif lineup:
                events.append({**base, "kind": "lineup", "promoted": sorted(
                    i["player_id"] for i in lineup if i.get("from_slot") in ("BENCH", "IR")
                    and i.get("to_slot") not in ("BENCH", "IR"))})
        for date, got in _trades(cap, before):
            a, b = sorted(got)
            if _when(date) >= cutoff and a in manager and b in manager:
                events.append({"date": date, "kind": "trade", "team_id": a, "manager": manager[a],
                               "with_id": b, "with": manager[b], "added": got[a], "dropped": got[b]})
    events.sort(key=lambda e: e["date"], reverse=True)
    return events


# ---------- week hub: ESPN headlines about players on a league roster ----------
NEWS_MAX_AGE = timedelta(hours=36)
NEWS_SHOWN = 6
_ESPN_LINK = re.compile(r"https://www\.espn\.com/[^\s\"'<>]+")


def load_news(season):
    """scripts/fetch_news.py's file, as a list of articles. Best effort like the FantasyPros snapshot:
    missing, malformed or more than 36 hours old is just [], and the page goes without the module."""
    try:
        data = json.loads((ROOT / "data" / str(season) / "news" / "latest.json").read_text())
        fetched = datetime.fromisoformat(data["fetched_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - fetched > NEWS_MAX_AGE:
            return []
        return [a for a in data["articles"] if isinstance(a, dict)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


def news_items(articles, espn):
    """The newest few headlines, each tagged with whose roster it touches right now. Only the headline
    and a link out to ESPN ever reach the page; an article about nobody on a roster is dropped."""
    manager = {t["team_id"]: t["manager"].split(" (")[0] for t in LEAGUE["teams"]}
    rosters = _rosters(espn)
    out = []
    for a in articles:
        try:
            ids = [i for i in a["athlete_ids"] if i in rosters]
            owners = sorted({rosters[i][0] for i in ids if rosters[i][0] in manager})
            if not owners or not isinstance(a["headline"], str) or not _ESPN_LINK.fullmatch(a["link"]):
                continue
            _when(a["published"])
            out.append({"headline": a["headline"][:200], "link": a["link"], "published": a["published"],
                        "owners": [{"team_id": t, "manager": manager[t]} for t in owners],
                        "players": sorted({rosters[i][1] for i in ids})})
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    out.sort(key=lambda n: n["published"], reverse=True)
    return out[:NEWS_SHOWN]


def hub_payload(live, season, espn, news, schedule=None):
    """What the Week hub needs that /api/live can't recompute: the stakes (they need the season's
    standings) and the headlines (a file only the build has). Baked here and left alone by a live
    refresh, like the week-ahead tab. Everything else on the hub is drawn from the live games and
    Coach rows in the browser, so it can never disagree with a refreshed projection."""
    hub = {}
    if not live["complete"] and not live["kicked_off"]:
        pairs = [tuple(int(x) for x in g["key"].split("-")) for g in live["games"]]
        stakes = playoffs.stakes(season["standings"], season["weeks_played"], LEAGUE, live["week"], pairs,
                                 schedule=schedule)
        if stakes:
            hub["stakes"] = stakes
    items = news_items(news or [], espn)
    if items:
        hub["news"] = items
    return hub


def live_payload(facts, espn, previous=None, fp=None, history=None):
    """The in-progress (or final but not yet recapped) week: data only, no commentary.

    `previous` is the capture before this one, used only to tell a new injury
    designation from one that was already there last week. `fp` is today's FantasyPros
    snapshot (see load_fantasypros); passed straight through to advice_payload.
    `history` is every earlier capture, for the league wire (see wire()); without it the
    wire reads this week and `previous`.
    """
    w = week_payload(facts, {"status": "live"}, live=True)
    manager = {t["team_id"]: t["manager"].split(" (")[0] for t in LEAGUE["teams"]}
    moves = []
    for t in espn["transactions"]:
        if t["type"] not in ("FREEAGENT", "WAIVER", "TRADE_ACCEPT"):
            continue
        added = [i["name"] for i in t["items"] if i["type"] in ("ADD", "TRADE") and i["to_team_id"] == t["team_id"]]
        dropped = [i["name"] for i in t["items"] if i["type"] == "DROP"]
        if added or dropped:
            moves.append({"date": t["date"], "manager": manager.get(t["team_id"], "?"), "added": added, "dropped": dropped})
    moves.sort(key=lambda m: m["date"], reverse=True)
    # Has anybody's game actually started this week? Not a day-of-week guess — read
    # straight off the same per-starter game states everything else on this page uses.
    # This is what tells a genuinely live week apart from the dead stretch between Monday
    # night and Thursday's kickoff, on either side of that week's own recap shipping.
    kicked_off = any(t["yet_to_play"] < len(t["starters"]) for t in facts["teams"])
    advice = advice_payload(facts["teams"], espn, previous, fp=fp, week=facts["week"])
    by_id = {t["team_id"]: t for t in facts["teams"]}
    record_by_id = {t["team_id"]: t for t in espn["teams"]}
    for row in advice:
        extra = None
        if facts["complete"]:
            # The week is over but not yet recapped: a computed stand-in for "how'd you
            # do", which stops appearing on its own the moment the real recap ships.
            extra = lookback_card(by_id[row["team_id"]], facts["teams"], facts["week"])
        elif not kicked_off:
            # Nothing has kicked off yet: worth a heads-up about who's coming.
            extra = opponent_preview_card(row, by_id, record_by_id)
        if extra:
            apply_written([extra], written_cards(row["team_id"], fp, facts["week"])[0])
            row["items"] = [extra] + row["items"]
            row["counts"]["info"] += 1
    # The wire is decoration next to the scores: a transaction in a shape nobody expected must
    # cost the page its wire, never the build or a /api/live response.
    try:
        feed = wire(espn, history if history is not None else [previous] if previous else [])
    except (KeyError, TypeError, ValueError, AttributeError):
        feed = []
    w.update(live=True, captured_at=espn["captured_at"], moves=moves, kicked_off=kicked_off, advice=advice, wire=feed)
    return w


def waiver_order(captures):
    """Team ids in ESPN's own waiver order (first pick first), from the newest capture that has it.

    ESPN resets the order after each week from its own standings and tiebreaks, which
    aren't ours, so the site shows ESPN's rank rather than reversing its standings. Weeks
    captured before `waiver_rank` existed don't carry it; None then means "the page falls back".
    """
    for cap in sorted(captures, key=lambda c: c.get("captured_at", ""), reverse=True):
        ranks = {t["team_id"]: t.get("waiver_rank") for t in cap.get("teams", [])}
        if ranks and all(isinstance(r, int) for r in ranks.values()):
            return sorted(ranks, key=ranks.get)
    return None


def award_players(award, facts, limit=3):
    """The players an award's story names, as {id, name, pos}, in the order the story mentions
    them, so the page can put a face next to each. Matched by full name against that week's
    rosters; a name the story shortens ("Bowers") or a player since dropped is simply not drawn."""
    if not facts:
        return []
    text = f"{award.get('title', '')} {award.get('text', '')}"
    found = {}
    for t in facts["teams"]:
        for p in t["starters"] + t["bench"]:
            at = text.find(p["name"])
            if at >= 0 and p["player_id"] not in found:
                found[p["player_id"]] = (at, {"id": p["player_id"], "name": p["name"], "pos": p.get("pos")})
    return [v[1] for v in sorted(found.values(), key=lambda v: v[0])][:limit]


def season_payload(facts_list, weeks):
    """Season-to-date stats per team, from the included weeks only."""
    teams = {t["team_id"]: {"team_id": t["team_id"], "manager": t["manager"].split(" (")[0],
                            "team_name": t["team_name"]} for t in LEAGUE["teams"]}
    for s in teams.values():
        s.update(wins=0, losses=0, ties=0, points_for=0.0, points_against=0.0, all_play_w=0, all_play_l=0,
                 bench_left=0.0, weekly=[], rank_history=[], awards=[])
    n_teams = len(teams)

    for facts in facts_list:
        wk = facts["week"]
        for t in facts["teams"]:
            s = teams[t["team_id"]]
            s["points_for"] = round(s["points_for"] + t["points"], 2)
            s["points_against"] = round(s["points_against"] + t["opponent_points"], 2)
            s["wins"] += t["result"] == "W"
            s["losses"] += t["result"] == "L"
            s["ties"] += t["result"] == "T"
            s["all_play_w"] += n_teams - t["score_rank"]
            s["all_play_l"] += t["score_rank"] - 1
            s["bench_left"] = round(s["bench_left"] + t["points_left_on_bench"], 2)
            s["weekly"].append({"week": wk, "points": t["points"], "opponent_id": t["opponent_id"],
                                "opponent": teams[t["opponent_id"]]["manager"], "opponent_points": t["opponent_points"],
                                "result": t["result"], "score_rank": t["score_rank"],
                                "points_left": t["points_left_on_bench"],
                                "game_key": "-".join(map(str, sorted((t["team_id"], t["opponent_id"]))))})
        for rank, row in enumerate(facts["standings"], 1):
            teams[row["team_id"]]["rank_history"].append({"week": wk, "rank": rank})

    by_manager = {s["manager"]: s for s in teams.values()}
    facts_by_week = {f["week"]: f for f in facts_list}
    for w in weeks:
        for kind in AWARD_KEYS:
            for a in w[kind]:
                if a["manager"] in by_manager:
                    by_manager[a["manager"]]["awards"].append(
                        {"week": w["week"], "kind": kind, "title": a["title"], "text": a.get("text", ""),
                         "stat": a.get("stat", ""), "players": award_players(a, facts_by_week.get(w["week"]))})

    for s in teams.values():
        streak = ""
        for g in reversed(s["weekly"]):
            if not streak:
                streak = g["result"]
                count = 1
            elif g["result"] == streak:
                count += 1
            else:
                break
        s["streak"] = f"{streak}{count}" if streak in ("W", "L") else ""
        # Places gained (+) or lost (-) because of the latest finished week; 0 holds, None when
        # there's no earlier week to compare to (Week 1, or a team with no prior rank).
        hist = s["rank_history"]
        s["rank_move"] = hist[-2]["rank"] - hist[-1]["rank"] if len(hist) >= 2 else None
        games = len(s["weekly"])
        s["avg"] = round(s["points_for"] / games, 2) if games else 0
        s["best"] = max(s["weekly"], key=lambda g: g["points"]) if games else None

    table = sorted(teams.values(), key=lambda s: (s["wins"] + 0.5 * s["ties"], s["points_for"]), reverse=True)
    return {"standings": table, "weeks_played": [f["week"] for f in facts_list]}


def load_player_names():
    """analyze.py's cache of names for ESPN's "Player 12345" placeholders. Read-only here
    (no network): a missing or malformed file just leaves the placeholders as they are."""
    try:
        names = json.loads((ROOT / "data" / "player_names.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return names if isinstance(names, dict) else {}


def load_schedule(season):
    """data/<season>/schedule.json, {"<week>": [[team_id, team_id], ...]}, as {week: [(a, b), ...]} for the
    playoff odds. Optional: a missing or malformed file returns {}, and the odds draw random opponents."""
    try:
        raw = json.loads((ROOT / "data" / str(season) / "schedule.json").read_text())
        out = {}
        for week, pairs in raw.items():
            if not all(isinstance(p, list) and len(p) == 2 and all(type(t) is int for t in p) for p in pairs):
                return {}
            out[int(week)] = [tuple(p) for p in pairs]
        return out
    except (OSError, ValueError, TypeError, AttributeError, RecursionError):
        return {}


def _live_shape_ok(live):
    """Is a borrowed payload shaped the way site_data and the template read it? Production can
    lag a schema change on a branch, and a draft build must never fail on that."""
    def rows_ok(rows):
        return isinstance(rows, list) and all(
            isinstance(r, dict) and isinstance(r.get("team_id"), int)
            and isinstance(r.get("roster_ideas") or [], list)
            and all(isinstance(it, dict) for it in r.get("roster_ideas") or [])
            for r in rows)
    nxt = live.get("next")
    return (isinstance(live, dict) and isinstance(live.get("week"), int) and rows_ok(live.get("advice"))
            and (nxt is None or (isinstance(nxt, dict) and rows_ok(nxt.get("teams") or []))))


def fetch_production_live(url, timeout=20, limit=16_000_000):
    """The live-week payload the site at `url` is serving right now, read out of its own page,
    or None. Best effort by design: any failure just means a preview with no live week.

    Why: a Vercel branch preview builds from committed data, and the live capture never is, so
    it has no Coach tab. Borrowing what production already computed shows the same week. It is
    production's snapshot (its standings and odds, published recaps only), good for reviewing
    design, not a computation over this branch's data."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fantasy-recap-preview-build"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            page = r.read(limit).decode("utf-8")
        m = re.search(r'<script id="recap-data" type="application/json">(.*?)</script>', page, re.S)
        live = json.loads(m.group(1)).get("live") if m else None
        return live if live and _live_shape_ok(live) else None
    except Exception:  # noqa: BLE001 - best effort: anything wrong with the page means no live week
        return None


def site_data(recap_weeks, captured, preview, ahead=None, fp=None, news=None, live_from=None):
    """(data, weeks): everything the page's RECAP_DATA blob carries, and the week payloads
    (live included) render() hands back to its callers.

    `live_from` is a ready-made live payload (see fetch_production_live) for a draft build that
    has no live week of its own. It never touches the league site's build."""
    included = [(f, w) for f, w in recap_weeks if preview or w["status"] == "published"]
    weeks = [w for _, w in included]
    # Live page: the newest captured week that isn't in this output's recaps yet
    last = max((w["week"] for w in weeks), default=0)
    pending = [c for c in captured if c[0]["week"] > last]
    live = None
    if pending:
        facts, espn = pending[-1]
        previous = next((e for f, e in reversed(captured) if f["week"] < facts["week"]), None)
        live = live_payload(facts, espn, previous, fp=fp, history=[e for f, e in captured if f["week"] < facts["week"]])
        # The week-ahead capture is only good for the week after the live one. A stale
        # one (captured before this week started) is dropped rather than shown as next.
        if ahead and ahead["week"] == facts["week"] + 1:
            live["next"] = next_payload(ahead, previous, fp=fp)
    elif live_from and preview and live_from["week"] > last:
        live = live_from                    # already carries its hub and next week

    season = season_payload([f for f, _ in included], weeks)
    # The schedule file belongs to the season being built (`--season`), which the facts carry;
    # league.json's season is only the default.
    year = next((f["season"] for f, _ in included if f.get("season")), LEAGUE["season"])
    schedule = load_schedule(year)
    season["playoffs"] = playoffs.build(season["standings"], season["weeks_played"], LEAGUE, schedule)
    season["waiver_order"] = waiver_order([e for _, e in captured] + ([ahead] if ahead else []))
    # Team profiles: the audit reads only this output's included weeks (a draft week never
    # reaches the league site); moves read every captured week, same as the Live page does.
    profiles = team_profile.audits([f for f, _ in included], [t["team_id"] for t in LEAGUE["teams"]])
    names = load_player_names()
    for s in season["standings"]:
        p = profiles[s["team_id"]]
        s["profile"] = {"audit": apply_written(p["cards"], written_audit(s["team_id"], fp)),
                        "weak_spot": p["weak_spot"], "best_spot": p["best_spot"], "pos_ranks": p["ranks"],
                        "moves": team_profile.moves(s["team_id"], captured, names)}
    if live:
        if pending:
            live["hub"] = hub_payload(live, season, pending[-1][1], news, schedule)
        weak = {s["team_id"]: s["profile"]["weak_spot"] for s in season["standings"]}
        for rows in (live["advice"], (live.get("next") or {}).get("teams") or []):
            for row in rows:
                for it in row.get("roster_ideas") or []:
                    it["fills_weak_spot"] = bool(it.get("pos")) and it.get("pos") == weak.get(row["team_id"])

    data = {
        "league": {"name": LEAGUE["name"].strip(), "season": LEAGUE["season"], "scoring": LEAGUE["scoring"]},
        "preview": preview,
        "weeks": weeks,
        "season": season,
        "live": live,
    }
    return data, weeks + ([live] if live else [])


def render(recap_weeks, captured, preview, ahead=None, fp=None, news=None, live_from=None):
    data, weeks = site_data(recap_weeks, captured, preview, ahead=ahead, fp=fp, news=news, live_from=live_from)
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = "Fantasy Football for the Girls (Preview)" if preview else "Fantasy Football for the Girls"
    template = (SITE / "template.html").read_text()
    # The Behind the scenes page lives in site/bts/ (markup, CSS, JS, one shared icon sprite) and is
    # stitched in here once, so template.html stays about the pages that carry league data.
    bts = SITE / "bts"
    template = (template.replace("__BTS_CSS__", (bts / "bts.css").read_text())
                .replace("__BTS_JS__", (bts / "bts.js").read_text())
                .replace("__BTS_SPRITE__", (bts / "sprite.svg").read_text())
                .replace("__BTS_PAGE__", (bts / "page.html").read_text()))
    return template.replace("__PAGE_TITLE__", title).replace("__RECAP_DATA__", blob), weeks


# The Claude artifact host wraps pages in its own document shell. The standalone web build
# (Vercel) needs its own: charset, viewport, no-index, favicon, and the small reset the
# artifact shell used to provide.
FAVICON = ("data:image/svg+xml," "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Cpolygon points='6,4 28,4 22,15 28,26 6,26' fill='%23ff6fb5' stroke='%23151a33' stroke-width='2'/%3E"
           "%3Crect x='4' y='2' width='3' height='28' fill='%23151a33'/%3E%3C/svg%3E")


def standalone(html, description="Weekly recaps, live scores and standings for our fantasy league."):
    head = (
        '<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        f'<meta name="description" content="{description}">\n'
        f'<link rel="icon" href="{FAVICON}">\n'
        '<style>body{margin:0}[hidden]{display:none!important}img{max-width:100%}'
        ':root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}</style>\n'
        # Only the Vercel builds have api/live.py behind them. The artifact build leaves
        # this unset and so never calls it, and keeps rendering from its baked data.
        '<script>window.FANTASY_LIVE_API="/api/live"</script>\n'
        # Vercel Web Analytics - CDN approach for static sites
        '<script defer src="https://cdn.vercel-insights.com/v1/script.js"></script>\n'
    )
    return head + html + "\n</html>\n"


def load_inputs(season):
    """(recap_weeks, captured, ahead, fp, news): everything render() reads from disk."""
    recap_weeks = []
    for recap_path in sorted((ROOT / "recaps" / str(season)).glob("week-*.json")):
        recap = json.loads(recap_path.read_text())
        facts_path = ROOT / "data" / str(season) / f"week-{recap['week']:02d}" / "facts.json"
        if not facts_path.exists():
            raise SystemExit(f"{recap_path.name}: missing {facts_path.relative_to(ROOT)}; run scripts/analyze.py")
        facts = json.loads(facts_path.read_text())
        recap_weeks.append((facts, week_payload(facts, recap)))
    recap_weeks.sort(key=lambda fw: fw[1]["week"])

    # Every captured week (facts + raw capture), for the live page
    captured = []
    for d in sorted((ROOT / "data" / str(season)).glob("week-*")):
        if (d / "facts.json").exists() and (d / "espn.json").exists():
            captured.append((json.loads((d / "facts.json").read_text()), json.loads((d / "espn.json").read_text())))
    captured.sort(key=lambda c: c[0]["week"])

    # The week-ahead preview, if one has been captured (scripts/capture.js 'next').
    # Optional by design: no file, no "next week" tab, everything else unchanged.
    ahead_path = ROOT / "data" / str(season) / "next-week" / "espn.json"
    ahead = json.loads(ahead_path.read_text()) if ahead_path.exists() else None

    # Today's FantasyPros snapshot, if fantasy-coach-daily has written one. Optional by
    # design, same as `ahead`: missing, malformed or stale just means ESPN-only advice.
    return recap_weeks, captured, ahead, load_fantasypros(season), load_news(season)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=LEAGUE["season"])
    args = ap.parse_args()
    recap_weeks, captured, ahead, fp, news = load_inputs(args.season)

    dist = SITE / "dist"
    dist.mkdir(exist_ok=True)
    html, weeks = render(recap_weeks, captured, preview=False, ahead=ahead, fp=fp, news=news)
    (dist / "index.html").write_text(html)
    # Standalone site for Vercel: league content only (never the preview), not indexed by search engines
    web = dist / "web"
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text(standalone(html))
    (web / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    nxt = next((w.get("next") for w in weeks if w.get("next")), None)
    print(f"index.html: weeks {[(w['week'], 'live' if w.get('live') else 'recap') for w in weeks] or 'none yet'}"
          + (f", next week {nxt['week']}" + ("" if nxt["projected"] else " (no projections yet)") if nxt else ""))
    # Vercel's own branch-preview build (scripts/vercel_build.sh) has no live capture; borrow
    # production's. Set only there, and only the draft copy ever reads it.
    borrow = os.environ.get("FANTASY_LIVE_FROM")
    live_from = fetch_production_live(borrow) if borrow else None
    if borrow:
        print("live week for the preview: " + (f"borrowed from {borrow} (week {live_from['week']})" if live_from else f"none, {borrow} didn't give one"))
    html, weeks = render(recap_weeks, captured, preview=True, ahead=ahead, fp=fp, news=news, live_from=live_from)
    (dist / "preview.html").write_text(html)
    # The same preview as a standalone page, for `scripts/deploy.sh --preview` (a real
    # URL to review a draft on a phone). preview.html itself is the artifact build, which
    # relies on the artifact host's document shell.
    web_preview = dist / "web-preview"
    web_preview.mkdir(exist_ok=True)
    (web_preview / "index.html").write_text(standalone(html, "Draft recap, not published yet."))
    (web_preview / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    print(f"preview.html: weeks {[(w['week'], w['status']) for w in weeks]}")


if __name__ == "__main__":
    main()
