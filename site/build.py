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
from collections import Counter
from pathlib import Path

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
        row.update(logo=p.get("logo"), team=p.get("team"), player_id=p.get("player_id"))
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
    """One cheeky line about a player's week, built only from his own numbers."""
    his = "its" if p["pos"] == "DST" else "his"
    pts, proj = p["points"], _proj(p)
    gap = round(pts - proj, 2)
    st = p.get("injury_status")
    spot = p["slot"] if starting else "bench"

    if ctx["on_bye"](p):
        return ("This defense is on a bye this week, so it plays nobody and scores exactly 0.0."
                if p["pos"] == "DST" else
                f"He doesn't have a game this week — his NFL team is on a bye — so that's a "
                f"guaranteed 0.0 from wherever you put him.")
    if p["slot"] == "IR" and pts <= 0.005:
        return ("He's in your injured-reserve spot, which is where ESPN parks a player hurt long "
                "enough that he can't be put in a lineup at all.")
    if p.get("game_state") == "in":
        return (f"On the field right now: {_pts(pts)} on the board against {_an(proj)} projection."
                + _td_line(p))
    # Before kickoff the injury report is the whole story; after it, the score is (ESPN can
    # still be carrying a designation for a player who has already played).
    if not ctx["locked"](p):
        if st in SIDELINED:
            if starting:
                return _voice(p, [
                    f"ESPN lists him {INJURY_PHRASE[st]}, which makes that {_f1(proj)}-point "
                    f"projection a lovely piece of fiction.",
                    f"He's {INJURY_PHRASE[st]} on ESPN's report. Starting him is a hope, not a plan.",
                ])
            return (f"ESPN lists him {INJURY_PHRASE[st]}, so he's staying put. The bench is the right "
                    f"place for that.")
        return _voice(p, [
            f"Hasn't kicked off yet. ESPN pencils him in for {_f1(proj)}, which is a guess in a nice suit.",
            f"Still in the tunnel. The {_f1(proj)} next to {his} name is a projection, not a promise.",
            f"No snaps yet. ESPN says {_f1(proj)}; the football gets the final word.",
        ])
    # His game has started, so the number on the row is the story.
    if pts < -0.005:
        return (f"{_pts(pts)} points. Negative. He lost you points from the {spot} spot, which takes "
                f"a particular kind of week." if starting else
                f"{_pts(pts)} points — negative, but on the bench, where it costs you nothing.")
    if pts <= 0.005:
        if st in SIDELINED:
            return (f"0.0 points — which is what ESPN's \u201c{INJURY_LABEL[st].lower()}\u201d "
                    f"designation was trying to tell you.")
        return (f"A donut: 0.0 points out of the {spot} spot. An empty chair scores the same."
                if starting else
                "0.0 points, and from the bench, which is exactly where you want your zeroes.")
    if not starting:
        if gap >= 5:
            return _voice(p, [
                f"{_pts(pts)} points on {_an(proj)} projection — from your bench, where they count "
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
    """The short factual list under the blurb: how he did against his projection, how much
    of the team he is, what ESPN's injury report says, where his game is up to, and what
    else you had at that spot. At most five lines, longest-standing facts last."""
    notes = []
    pts, proj = p["points"], _proj(p)
    st = p.get("injury_status")
    state = p.get("game_state")
    started = ctx["locked"](p)

    # The blurb already puts his points next to his projection once his game is under way,
    # so this line is only worth its space while there's nothing but a projection to report.
    if not started and pts <= 0.005 and proj and not ctx["on_bye"](p):
        notes.append(f"ESPN projects {_f1(proj)} points for him this week.")

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

    if starting and not started:
        alt = ctx["bench_best"](p["slot"])
        if alt:
            notes.append(f"Best option behind him on your bench: {alt['name']} "
                         f"({_f1(_proj(alt))} projected).")
    elif not starting and p["slot"] != "IR" and st not in SIDELINED and not ctx["on_bye"](p):
        rival = ctx["starter_for"](p)
        if rival and pts > rival["points"] + 0.005:
            notes.append(f"Outscoring your starting {rival['slot']}, {rival['name']} "
                         f"({_pts(rival['points'])}), from the bench.")
        elif rival:
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
        }
    return cards


def team_advice(team, before, before_week, states_known):
    """One team's to-do list for the live week.

    `before` maps player id to that player's injury designation in the previous captured
    week (week `before_week`), so a designation that is new can be called new. It's empty
    when there's no earlier capture to compare with. `states_known` is False when the NFL
    scoreboard call failed, in which case nobody is called locked or on a bye on a guess.
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

    def free(p):
        """Healthy, playing this week, and still swappable."""
        return not locked(p) and not on_bye(p) and p.get("injury_status") not in SIDELINED

    def news(p):
        """" That's new since Week 2." — when the previous capture can tell us."""
        pid = p["player_id"]
        if pid not in before or before[pid] == p.get("injury_status"):
            return ""
        was = before[pid]
        if was in SIDELINED or was in IFFY:
            return f" He was listed {INJURY_PHRASE[was]} in Week {before_week} too."
        return f" That's new since Week {before_week}, when ESPN wasn't listing him at all."

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
        covered.add(s["player_id"])
        phrase = INJURY_PHRASE.get(s.get("injury_status"), "out")
        # "ESPN lists him as on injured reserve (IR). A player on IR is hurt long enough..."
        why = (f"ESPN lists {s['name']} as {phrase}.{ir_note(s)}" if hurt else
               f"{s['name']}'s NFL team is on a bye this week, so he doesn't play at all.")
        r = backup(s["slot"])
        if r:
            claimed.add(r["player_id"])
            title = f"Start {r['name']} over {s['name']}"
            text = (f"{why}{news(s)} {r['name']} is on your bench, {shape(r)}, and projected "
                    f"{_f1(_proj(r))} points. Move him into the {s['slot']} spot.")
        else:
            title = f"{s['name']} is {phrase}" if hurt else f"{s['name']} is on a bye"
            text = (f"{why}{news(s)} {no_backup(s['slot'])}, so the only fix is the waiver wire — "
                    f"the pool of players nobody in the league owns.")
        items.append({"kind": "bye" if bye and not hurt else "out", "level": "now", "title": title,
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
    for s in starters:
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
                      "title": f"Start {b['name']} over {s['name']}",
                      "stat": f"+{_f1(gain)} projected",
                      "text": (f"ESPN projects {b['name']} for {_f1(_proj(b))} points and {s['name']} for "
                               f"{_f1(_proj(s))}. Both can play {s['slot']}, so that's {_f1(gain)} points of "
                               f"difference for one tap"
                               + (f" — though {b['name']} is {INJURY_PHRASE[b['injury_status']]}, so check he's "
                                  f"playing first" if b.get("injury_status") in IFFY else "")
                               + ". A projection is an estimate, not a promise, but a gap this size is "
                               "usually worth taking.")})

    # 4. A starting slot with nobody in it scores exactly zero.
    filled = Counter(s["slot"] for s in starters)
    for slot, need in LINEUP.items():
        for _ in range(need - filled.get(slot, 0)):
            r = backup(slot)
            if r:
                claimed.add(r["player_id"])
            items.append({"kind": "empty", "level": "now", "title": f"Your {slot} spot is empty",
                          "stat": "nobody starting",
                          "text": (f"There's nobody in your {slot} spot, and an empty spot scores zero. "
                                   + (f"{r['name']} ({_f1(_proj(r))} projected, {shape(r)}) can fill it."
                                      if r else f"{no_backup(slot)}, so try the waiver wire."))})

    # 5. The game-time decisions themselves. Last of the lineup passes, so the backup it
    #    names is one nothing above has already spent.
    for s in iffy_starters:
        label = INJURY_LABEL[s["injury_status"]]
        r = backup(s["slot"])
        plan = (f"If he's ruled out, {r['name']} ({_f1(_proj(r))} projected, {shape(r)}) is your best swap."
                if r else f"{no_backup(s['slot'])}, so check early.")
        items.append({"kind": "watch", "level": "watch",
                      "title": f"{s['name']} is {label.lower()}",
                      "stat": f"{_f1(_proj(s))} projected",
                      "text": (f"{label} means his team hasn't decided whether he plays; the call usually "
                               f"lands about 90 minutes before kickoff.{news(s)} {plan}")})

    # 6. A starter ESPN expects nothing from, with no better option behind him.
    for s in starters:
        if locked(s) or s["player_id"] in covered or s["player_id"] in swapped or _proj(s) > 0.05:
            continue
        items.append({"kind": "hole", "level": "now", "title": f"{s['name']} is projected zero",
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
                "title": f"{p['name']} is now listed {INJURY_LABEL[now].lower()}",
                "stat": INJURY_LABEL[now],
                "text": (f"New since Week {before_week}: ESPN has {p['name']} ({p['pos']}, {where}) as "
                         f"{INJURY_PHRASE[now]}.{too_late}")}))
        elif was in SIDELINED or was in IFFY:
            fresh.append((2, {
                "kind": "back", "level": "info",
                "title": f"{p['name']} is off the injury report",
                "stat": f"{_f1(_proj(p))} projected",
                "text": (f"He was listed {INJURY_PHRASE[was]} in Week {before_week} and isn't any more. "
                         f"He's {where}.")}))
    items += [it for _, it in sorted(fresh, key=lambda x: x[0])[:3]]

    if not items:
        done = all(locked(s) for s in starters)
        items.append({"kind": "clear", "level": "info", "title": "Nothing to fix", "stat": "",
                      "text": ("Every one of your starters has already kicked off, so this lineup is what it "
                               "is. Enjoy the games."
                               if done else
                               "Every starter is healthy, playing this week, and the best projection you have "
                               "at his spot. Nothing on your bench beats what you've got. Go enjoy the games.")})

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
        "team_points": team["points"],
        "top_starter": best_id(starters), "top_bench": best_id(team["bench"]),
        "bench_best": bench_best, "starter_for": starter_for,
        "pickups": {a["name"]: a for a in team.get("pickups_started", [])},
    }

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
        "movable": sum(1 for s in starters if not locked(s)),
        "items": items,
        "counts": {lvl: sum(1 for it in items if it["level"] == lvl) for lvl in LEVELS},
        # One card per player on the roster, for the lineup rows on her Coach page
        "players": player_cards(starters, team["bench"], ctx),
    }


def advice_payload(facts, espn, previous):
    """The coach page's data: one entry per team, in league order.

    `previous` is the capture before this one (or None), which is what lets an injury
    designation be called new rather than just current.
    """
    # The NFL scoreboard call is best effort in both captures. When it gave us nothing,
    # no player is called locked or on a bye on a guess.
    states_known = any(p.get("game_state")
                       for m in espn["matchups"] for s in (m["home"], m["away"]) if s
                       for p in s["lineup"])
    before = injury_map(previous) if previous else {}
    by_id = {t["team_id"]: t for t in facts["teams"]}
    return [team_advice(by_id[t["team_id"]], before, previous["week"] if previous else None, states_known)
            for t in LEAGUE["teams"] if t["team_id"] in by_id]


def live_payload(facts, espn, previous=None):
    """The in-progress (or final but not yet recapped) week: data only, no commentary.

    `previous` is the capture before this one, used only to tell a new injury
    designation from one that was already there last week.
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
    w.update(live=True, captured_at=espn["captured_at"], moves=moves,
             advice=advice_payload(facts, espn, previous))
    return w


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
    for w in weeks:
        for kind in AWARD_KEYS:
            for a in w[kind]:
                if a["manager"] in by_manager:
                    by_manager[a["manager"]]["awards"].append({"week": w["week"], "kind": kind, "title": a["title"]})

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
        games = len(s["weekly"])
        s["avg"] = round(s["points_for"] / games, 2) if games else 0
        s["best"] = max(s["weekly"], key=lambda g: g["points"]) if games else None

    table = sorted(teams.values(), key=lambda s: (s["wins"] + 0.5 * s["ties"], s["points_for"]), reverse=True)
    return {"standings": table, "weeks_played": [f["week"] for f in facts_list]}


def render(recap_weeks, captured, preview):
    included = [(f, w) for f, w in recap_weeks if preview or w["status"] == "published"]
    weeks = [w for _, w in included]
    # Live page: the newest captured week that isn't in this output's recaps yet
    last = max((w["week"] for w in weeks), default=0)
    pending = [c for c in captured if c[0]["week"] > last]
    live = None
    if pending:
        facts, espn = pending[-1]
        previous = next((e for f, e in reversed(captured) if f["week"] < facts["week"]), None)
        live = live_payload(facts, espn, previous)
    data = {
        "league": {"name": LEAGUE["name"].strip(), "season": LEAGUE["season"], "scoring": LEAGUE["scoring"]},
        "preview": preview,
        "weeks": weeks,
        "season": season_payload([f for f, _ in included], weeks),
        "live": live,
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = "Fantasy Football for the Girls (Preview)" if preview else "Fantasy Football for the Girls"
    template = (SITE / "template.html").read_text()
    return template.replace("__PAGE_TITLE__", title).replace("__RECAP_DATA__", blob), weeks + ([live] if live else [])


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=LEAGUE["season"])
    args = ap.parse_args()

    recap_weeks = []
    for recap_path in sorted((ROOT / "recaps" / str(args.season)).glob("week-*.json")):
        recap = json.loads(recap_path.read_text())
        facts_path = ROOT / "data" / str(args.season) / f"week-{recap['week']:02d}" / "facts.json"
        if not facts_path.exists():
            raise SystemExit(f"{recap_path.name}: missing {facts_path.relative_to(ROOT)}; run scripts/analyze.py")
        facts = json.loads(facts_path.read_text())
        recap_weeks.append((facts, week_payload(facts, recap)))
    recap_weeks.sort(key=lambda fw: fw[1]["week"])

    # Every captured week (facts + raw capture), for the live page
    captured = []
    for d in sorted((ROOT / "data" / str(args.season)).glob("week-*")):
        if (d / "facts.json").exists() and (d / "espn.json").exists():
            captured.append((json.loads((d / "facts.json").read_text()), json.loads((d / "espn.json").read_text())))
    captured.sort(key=lambda c: c[0]["week"])

    dist = SITE / "dist"
    dist.mkdir(exist_ok=True)
    html, weeks = render(recap_weeks, captured, preview=False)
    (dist / "index.html").write_text(html)
    # Standalone site for Vercel: league content only (never the preview), not indexed by search engines
    web = dist / "web"
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text(standalone(html))
    (web / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    print(f"index.html: weeks {[(w['week'], 'live' if w.get('live') else 'recap') for w in weeks] or 'none yet'}")
    html, weeks = render(recap_weeks, captured, preview=True)
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
