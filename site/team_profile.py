"""Season-level facts for a team's profile page: the coach's audit and her roster moves.

Pure functions over already-loaded facts.json / espn.json dicts: no file I/O and no clock,
so site/build.py and scripts/coach_brief.py share one source of truth for the audit keys
coach-daily writes copy against. A key names the exact situation behind a card, and it
changes only when a newly included week changes that situation.
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

def position_totals(facts_list):
    """team_id → slot group → her starters' points in that group, over the given weeks."""
    totals = {}
    for facts in facts_list:
        for t in facts["teams"]:
            g = totals.setdefault(t["team_id"], dict.fromkeys(GROUPS, 0.0))
            for p in t["starters"]:
                if p["slot"] in g:
                    g[p["slot"]] += p["points"]
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
        text = (f"Every spot in your lineup ranks {_ordinal(ranks[best])} in the league. "
                + ("No weak link to fix, which is its own kind of flex." if ranks[best] == 1
                   else "Nothing stands out yet, so any strong pickup helps."))
    else:
        title = f"{GROUP_LABEL[best].split(' (')[0].capitalize()} is carrying this team"
        text = (f"Your points {_at(best)} rank {_ordinal(ranks[best])} in the league. Your points {_at(worst)} "
                f"rank {_rank(ranks[worst], n_teams)}, so that's where a pickup, a free agent you add, helps most.")
    return _card(f"pos:{best}{ranks[best]}:{worst}{ranks[worst]}", "position", stat, title, text), worst


def position_faces(rows, group, n=2):
    """His best two starters at `group` by points over the weeks given (ties by id)."""
    tot = {}
    for _, r in rows:
        for p in r["starters"]:
            if p["slot"] == group:
                e = tot.setdefault(p["player_id"], [0.0, p])
                e[0] += p["points"]
    top = sorted(tot.values(), key=lambda e: (-round(e[0], 2), e[1]["player_id"]))[:n]
    return [_ref(e[1]) for e in top]


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

def audits(facts_list, team_ids):
    """{team_id: {"cards": [lineup_iq, position, projection], "weak_spot": group, "best_spot": group,
    "ranks": {group: league rank}}}, from the weeks given (the build passes only recapped ones).
    No weeks → no cards, no spots, no ranks."""
    ranks = position_ranks(position_totals(facts_list)) if facts_list else {}
    out = {}
    for tid in team_ids:
        rows = [(f["week"], t) for f in facts_list for t in f["teams"] if t["team_id"] == tid]
        if not rows:
            out[tid] = {"cards": [], "weak_spot": None, "best_spot": None, "ranks": None}
            continue
        pos, weak = position_card(ranks[tid], len(team_ids))
        pos["players"] = position_faces(rows, extremes(ranks[tid])[0])
        out[tid] = {"cards": [lineup_iq(rows), pos, projection_card(rows)], "weak_spot": weak,
                    "best_spot": extremes(ranks[tid])[0], "ranks": ranks[tid]}
    return out
