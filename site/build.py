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
        row.update(logo=p.get("logo"), team=p.get("team"))
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


def team_advice(team, before, before_week, states_known, projected=True, week_open=True):
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
    filled = Counter(s["slot"] for s in starters) if can_change else Counter(LINEUP)
    for slot, need in LINEUP.items():
        for _ in range(need - filled.get(slot, 0)):
            r = backup(slot)
            if r:
                claimed.add(r["player_id"])
            items.append({"kind": "empty", "level": "now", "title": f"Your {slot} spot is empty",
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
                      "title": f"{s['name']} is {label.lower()}",
                      "stat": worth(s) or label,
                      "text": (f"{label} means his team hasn't decided whether he plays; the call usually "
                               f"lands about 90 minutes before kickoff.{news(s)} {plan}")})

    # 6. A starter ESPN expects nothing from, with no better option behind him.
    for s in (starters if projected and can_change else []):
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
                "stat": worth(p) or "Back",
                "text": (f"He was listed {INJURY_PHRASE[was]} in Week {before_week} and isn't any more. "
                         f"He's {where}.")}))
    items += [it for _, it in sorted(fresh, key=lambda x: x[0])[:3]]

    if not items:
        done = not can_change
        items.append({"kind": "clear", "level": "info", "title": "Nothing to fix", "stat": "",
                      "text": ("Every game you had this week is done, so this lineup is what it is. "
                               "Anything worth changing is on next week's list."
                               if done else
                               ("Every starter is healthy, playing this week, and the best projection you "
                                "have at his spot. Nothing on your bench beats what you've got. Go enjoy "
                                "the games." if projected else
                                "Every starter is healthy and has a game that week. ESPN hasn't published "
                                "its projections yet, so the start-or-sit calls come later."))})

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
        "counts": {lvl: sum(1 for it in items if it["level"] == lvl) for lvl in LEVELS},
    }


def advice_payload(teams, espn, previous):
    """The Coach page's data: one entry per team, in league order.

    `teams` are facts.json-shaped (starters, bench, opponent_id), either from a played
    week's facts or from next_week_teams(). `previous` is the capture before this one (or
    None), which is what lets an injury designation be called new rather than just current.
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
    return [team_advice(by_id[t["team_id"]], before, previous["week"] if previous else None,
                        states_known, projected, week_open)
            for t in LEAGUE["teams"] if t["team_id"] in by_id]


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


def next_payload(capture, previous):
    """The Coach page's "next week" tab: the same advice, a week early.

    Baked at build time and never refreshed by /api/live, because next week's numbers
    move about once a day, not once a minute — and because asking ESPN for a second week
    on every request would double what the live page costs it.
    """
    teams = next_week_teams(capture)
    rows = advice_payload(teams, capture, previous)
    lineups = {t["team_id"]: {"starters": [player(p, True) for p in t["starters"]],
                              "bench": [player(p, True) for p in t["bench"]]} for t in teams}
    by_id = {t["team_id"]: t for t in teams}
    for r in rows:
        r["lineup"] = lineups[r["team_id"]]
        r["projected"] = by_id[r["team_id"]]["projected"]
    return {"week": capture["week"], "captured_at": capture["captured_at"],
            # ESPN can be days from publishing next week's projections; the page says so
            # instead of showing a column of zeros.
            "projected": any(p.get("projected") for t in teams for p in t["starters"]),
            "teams": rows}


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
             advice=advice_payload(facts["teams"], espn, previous))
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


def render(recap_weeks, captured, preview, ahead=None):
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
        # The week-ahead capture is only good for the week after the live one. A stale
        # one (captured before this week started) is dropped rather than shown as next.
        if ahead and ahead["week"] == facts["week"] + 1:
            live["next"] = next_payload(ahead, previous)
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

    # The week-ahead preview, if one has been captured (scripts/capture.js 'next').
    # Optional by design: no file, no "next week" tab, everything else unchanged.
    ahead_path = ROOT / "data" / str(args.season) / "next-week" / "espn.json"
    ahead = json.loads(ahead_path.read_text()) if ahead_path.exists() else None

    dist = SITE / "dist"
    dist.mkdir(exist_ok=True)
    html, weeks = render(recap_weeks, captured, preview=False, ahead=ahead)
    (dist / "index.html").write_text(html)
    # Standalone site for Vercel: league content only (never the preview), not indexed by search engines
    web = dist / "web"
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text(standalone(html))
    (web / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    nxt = next((w.get("next") for w in weeks if w.get("next")), None)
    print(f"index.html: weeks {[(w['week'], 'live' if w.get('live') else 'recap') for w in weeks] or 'none yet'}"
          + (f", next week {nxt['week']}" + ("" if nxt["projected"] else " (no projections yet)") if nxt else ""))
    html, weeks = render(recap_weeks, captured, preview=True, ahead=ahead)
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
