"""Season-level facts for a team's profile page: the coach's audit and her roster moves.

Pure functions over already-loaded facts.json / espn.json dicts: no file I/O and no clock,
so site/build.py and scripts/coach_brief.py share one source of truth for the audit keys
coach-daily writes copy against. A key names the exact situation behind a card, and it
changes only when that situation does: a newly included week, or (for Position strength,
a snapshot of today's lineups) a lineup change that moves a best or worst rank.
"""
import re

# Also the tie-break order for best/worst group. RB and WR come first: a tied weak spot there
# is one a waiver pickup can actually fix, while a QB upgrade rarely sits on waivers.
GROUPS = ("RB", "WR", "QB", "TE", "FLEX", "DST", "K")
GROUP_LABEL = {"QB": "quarterback", "RB": "running back", "WR": "wide receiver", "TE": "tight end",
               "FLEX": "flex (the wild-card spot)", "DST": "defense", "K": "kicker"}
BANDS = ((0.95, "A"), (0.88, "B"), (0.80, "C"))
MOVE_TYPES = {"FREEAGENT": "add", "WAIVER": "add", "TRADE_ACCEPT": "trade"}
MIN_STARTS = 2


def _f1(x):
    return f"{x:.1f}"


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# ---------- roster moves ----------

def moves(team_id, captured, names=None):
    """Her adds, drops and trades across every captured week, newest first.

    A trade is recorded under one party's transaction, so "is she in it" is read off the
    items, not the transaction's team. A transaction can show up in two consecutive
    captures; the first (oldest) week it appeared in wins. ESPN sometimes sends a
    placeholder ("Player 4242355"); `names` (data/player_names.json, {id: name}) fills in
    the ones analyze.py has already looked up.
    """
    names = names or {}

    def name(i):
        return names.get(str(i["player_id"]), i["name"]) if i["name"].startswith("Player ") else i["name"]

    seen, out = set(), []
    for facts, espn in captured:
        for t in espn.get("transactions", []):
            kind = MOVE_TYPES.get(t["type"])
            if not kind:
                continue
            items = t.get("items", [])
            added_i = [i for i in items if i["type"] in ("ADD", "TRADE") and i["to_team_id"] == team_id]
            dropped_i = [i for i in items if i["type"] in ("DROP", "TRADE") and i["from_team_id"] == team_id]
            added, dropped = [name(i) for i in added_i], [name(i) for i in dropped_i]
            if not added and not dropped:
                continue
            key = (t["date"], t["type"], tuple(sorted(str(i["player_id"]) for i in items)))
            if key in seen:
                continue
            seen.add(key)
            # The ids ride along (same order as the names) so the page can draw a headshot chip.
            out.append({"week": facts["week"], "date": t["date"], "type": kind, "added": added, "dropped": dropped,
                        "added_ids": [i["player_id"] for i in added_i], "dropped_ids": [i["player_id"] for i in dropped_i]})
    out.sort(key=lambda m: m["date"], reverse=True)
    return out


# ---------- audit: shared ----------

def _card(key, kind, stat, title, text, players=()):
    """`players` ([{id, name, pos}]) are the people the card is about, so the page can show
    their faces next to the words. Display only: never part of the key."""
    return {"key": key, "kind": kind, "level": "info", "stat": stat, "title": title, "text": text,
            "players": list(players)}


def _ref(p):
    return {"id": p["player_id"], "name": p["name"], "pos": p.get("pos")}


def _find(row, name, side):
    return next((p for p in row.get(side, []) if p.get("name") == name), None)


# ---------- audit: Lineup IQ ----------

def band(pct):
    """A–D, for the key only. Never shown: grading her lineups on the page would read as
    grading her, and CLAUDE.md says roast the decision, hug the person."""
    for floor, letter in BANDS:
        if pct >= floor:
            return letter
    return "D"


def _benched_id(team_row, name):
    """facts.json's worst_bench_call names the player but doesn't carry his id, so find him
    on that week's bench. A name that isn't there still needs a stable key: slug it."""
    for p in team_row.get("bench", []):
        if p.get("name") == name:
            return str(p["player_id"])
    return _slug(name)


LINEUP_TITLE = {"A": "Your lineup calls have been sharp", "B": "Mostly the right calls, a few bench regrets",
                "C": "The bench keeps getting the good weeks", "D": "Your bench deserves a promotion"}


def lineup_iq(rows):
    """rows: (week, facts.json team row) for one team, oldest first, non-empty."""
    points = sum(r["points"] for _, r in rows)
    optimal = sum(r["optimal_points"] for _, r in rows)
    pct = points / optimal if optimal > 0 else 1.0
    left = sum(r["points_left_on_bench"] for _, r in rows)
    worst = None                                    # (week, row, call); ties keep the oldest week
    for wk, r in rows:
        c = r.get("worst_bench_call")
        if c and (worst is None or c["gap"] > worst[2]["gap"]):
            worst = (wk, r, c)
    b = band(pct)
    stat = f"{round(pct * 100)}% of optimal · {_f1(left)} benched"
    if not worst:
        # Null worst_bench_call doesn't mean nothing was left behind (analyze.py also nulls it
        # when the points came from, say, an empty slot), so "perfect" needs a zero to say so.
        if left < 0.005:
            return _card(f"lineup:{b}:none", "lineup_iq", stat, "Perfect lineups, every week",
                         "You've started your best possible lineup every single week. Your bench has yet to be right about anything.")
        return _card(f"lineup:{b}:scattered", "lineup_iq", stat, LINEUP_TITLE[b],
                     "No single benching stands out. What's left on the bench came in small pieces, not one big miss.")
    wk, r, c = worst
    at = _at(c["slot"]) if c["slot"] in GROUP_LABEL else f"at {c['slot']}"
    text = (f"Biggest miss: Week {wk}, starting {c['started']} ({_f1(c['started_points'])}) "
            f"{at} while {c['benched']} put up {_f1(c['benched_points'])} on your bench, where points don't count.")
    faces = [_ref(p) for p in (_find(r, c["benched"], "bench"), _find(r, c["started"], "starters")) if p]
    return _card(f"lineup:{b}:{_benched_id(r, c['benched'])}:w{wk}", "lineup_iq", stat, LINEUP_TITLE[b], text, faces)


# ---------- audit: Position strength ----------
# A snapshot, not a season tally: the lineup each team has set right now, every starter rated by
# his points per game this season (on any roster), summed per lineup spot and ranked.

def _finished(p, week_final=True):
    """Did he play a game that's over? A bye, an inactive day, or a game still ahead or under
    way isn't a game played, so it neither scores nor counts toward his average. Without a game
    state (weeks captured before them, or a failed scoreboard read) only a final week's games
    count: mid-week, a player with a stat on the board may still be playing."""
    if not p.get("played", True):
        return False
    state = p.get("game_state")
    return state not in ("pre", "in") if state else week_final


def per_game(facts_list):
    """player_id → his points per game over every finished game in the weeks given, whichever
    roster (starting or bench) he was on. Weeks he spent as a free agent aren't captured."""
    seen = {}
    for f in facts_list:
        final = f.get("complete", True)
        for t in f["teams"]:
            for p in list(t["starters"]) + list(t.get("bench", [])):
                if _finished(p, final):
                    seen[(f["week"], p["player_id"])] = p["points"]     # one roster per week
    sums = {}
    for (_, pid), pts in seen.items():
        e = sums.setdefault(pid, [0.0, 0])
        e[0] += pts
        e[1] += 1
    return {pid: total / games for pid, (total, games) in sums.items()}


def lineup_totals(lineup_facts, ppg, team_ids):
    """team_id → slot group → the summed points per game of the starters she has there now.
    An empty slot, or a starter with no finished game yet, adds nothing."""
    totals = {tid: dict.fromkeys(GROUPS, 0.0) for tid in team_ids}
    for t in lineup_facts["teams"]:
        g = totals.get(t["team_id"])
        if g is None:
            continue
        for p in t["starters"]:
            if p["slot"] in g:
                g[p["slot"]] += ppg.get(p["player_id"], 0.0)
    return totals


def position_ranks(totals):
    """1 = the league's best at that group. Equal totals rank by team id, so a rank never
    wobbles between two builds of the same data."""
    ranks = {tid: {} for tid in totals}
    for grp in GROUPS:
        for i, tid in enumerate(sorted(totals, key=lambda tid: (-round(totals[tid][grp], 2), tid)), 1):
            ranks[tid][grp] = i
    return ranks


def _at(group):
    """"at running back", "at flex, the wild-card spot," — reads mid-sentence for every group."""
    return "at flex, the wild-card spot," if group == "FLEX" else f"at {GROUP_LABEL[group]}"


def _rank(n, n_teams):
    return f"{_ordinal(n)}, also known as last" if n == n_teams else _ordinal(n)


def extremes(ranks):
    """(best, worst) group from a team's {group: league rank}; ties go to the first in GROUPS order."""
    best = [g for g in GROUPS if ranks[g] == min(ranks.values())][0]
    worst = [g for g in GROUPS if ranks[g] == max(ranks.values())][0]
    return best, worst


def position_card(ranks, n_teams=8):
    """(card, weak_spot) for one team, from its {group: league rank} (1 = best)."""
    best, worst = extremes(ranks)
    stat = f"Best: {best} (#{ranks[best]}) · Worst: {worst} (#{ranks[worst]})"
    if ranks[best] == ranks[worst]:
        title = "Even across the board"
        text = (f"Every spot in your current lineup ranks {_ordinal(ranks[best])} in the league on points per game. "
                + ("No weak link to fix, which is its own kind of flex." if ranks[best] == 1
                   else "Nothing stands out yet, so any strong pickup helps."))
    else:
        title = f"{GROUP_LABEL[best].split(' (')[0].capitalize()} is carrying this team"
        text = (f"Your starters {_at(best)} rank {_ordinal(ranks[best])} in the league on points per game. "
                f"Your starters {_at(worst)} rank {_rank(ranks[worst], n_teams)}, so that's where a pickup, "
                f"a free agent you add, helps most.")
    # "now" marks the snapshot: copy written for the old season-total key must not match it.
    return _card(f"pos:now:{best}{ranks[best]}:{worst}{ranks[worst]}", "position", stat, title, text), worst


def position_faces(starters, group, ppg, n=2):
    """Her two best current starters at `group` by points per game (ties by id)."""
    at = [p for p in starters if p["slot"] == group]
    top = sorted(at, key=lambda p: (-round(ppg.get(p["player_id"], 0.0), 2), p["player_id"]))[:n]
    return [_ref(p) for p in top]


# ---------- audit: Projection vs reality ----------

def _vs(name, avg, its):
    pron = "its" if its else "his"
    if avg >= 0:
        return f"{name} is beating {pron} projection by {_f1(avg)} a game"
    return f"{name} is coming up {_f1(-avg)} a game short of {pron} projection"


def projection_card(rows):
    """A starter with no projection (a week captured before ESPN published them) is left
    out rather than counted as projected zero, which would hand him a fake beat."""
    delta, per = 0.0, {}
    for _, r in rows:
        for p in r["starters"]:
            if p.get("projected") is None:
                continue
            d = p["points"] - p["projected"]
            delta += d
            e = per.setdefault(str(p["player_id"]), {"name": p["name"], "pos": p.get("pos"), "id": p["player_id"], "n": 0, "sum": 0.0,
                                                     "its": p.get("slot") == "DST" or p["name"].endswith("D/ST")})
            e["n"] += 1
            e["sum"] += d
    eligible = sorted(((e["sum"] / e["n"], pid, e["name"], e["its"]) for pid, e in per.items() if e["n"] >= MIN_STARTS),
                      key=lambda x: (-x[0], x[1]))
    top = eligible[0] if eligible else None
    bottom = eligible[-1] if len(eligible) >= 2 else None
    direction = "over" if delta >= 0 else "under"
    faces = [{"id": per[x[1]]["id"], "name": x[2], "pos": per[x[1]]["pos"]} for x in (top, bottom) if x]
    stat = f"{'+' if delta >= 0 else '-'}{_f1(abs(delta))} vs projections"
    title = "Your starters are beating ESPN's guesses" if direction == "over" else "ESPN keeps overrating your starters"
    if not top:
        text = "Nobody has two starts yet, so it's too early to name names."
    else:
        text = f"{_vs(top[2], top[0], top[3])}." + (" ESPN hasn't caught on yet." if top[0] >= 0 else "")
        if bottom:
            text += f" {_vs(bottom[2], bottom[0], bottom[3])}."
    key = f"proj:{direction}:{top[1] if top else 'none'}:{bottom[1] if bottom else 'none'}"
    return _card(key, "projection", stat, title, text, faces)


# ---------- audit: all three, every team ----------

def audits(facts_list, team_ids, captured=None):
    """{team_id: {"cards": [lineup_iq, position, projection], "weak_spot": group, "best_spot": group,
    "ranks": {group: league rank}}}.

    Lineup IQ and Projection vs reality read the weeks given (the build passes only recapped
    ones). Position strength, and with it the ranks and spots, is a snapshot: the starters in the
    newest of `captured` (every captured week, oldest first; defaults to `facts_list`), each rated
    by his points per game across all of them. No weeks → no cards, no spots, no ranks."""
    captured = captured or facts_list
    ppg = per_game(captured) if captured else {}
    now = captured[-1] if captured else None
    ranks = position_ranks(lineup_totals(now, ppg, team_ids)) if ppg else {}
    starters = {t["team_id"]: t["starters"] for t in now["teams"]} if now else {}
    out = {}
    for tid in team_ids:
        rows = [(f["week"], t) for f in facts_list for t in f["teams"] if t["team_id"] == tid]
        if not rows:
            out[tid] = {"cards": [], "weak_spot": None, "best_spot": None, "ranks": None}
            continue
        cards, weak, best = [lineup_iq(rows)], None, None
        if tid in ranks:
            pos, weak = position_card(ranks[tid], len(team_ids))
            best = extremes(ranks[tid])[0]
            pos["players"] = position_faces(starters.get(tid, []), best, ppg)
            cards.append(pos)
        cards.append(projection_card(rows))
        out[tid] = {"cards": cards, "weak_spot": weak, "best_spot": best, "ranks": ranks.get(tid)}
    return out
