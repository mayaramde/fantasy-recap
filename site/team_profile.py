"""Season-level facts for a team's profile page: the coach's audit and her roster moves.

Pure functions over already-loaded facts.json / espn.json dicts: no file I/O and no clock,
so site/build.py and scripts/coach_brief.py share one source of truth for the audit keys
coach-daily writes copy against. A key names the exact situation behind a card, and it
changes only when a newly included week changes that situation.
"""
import re

GROUPS = ("QB", "RB", "WR", "TE", "FLEX", "DST", "K")   # also the tie-break order
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
            added = [name(i) for i in items if i["type"] in ("ADD", "TRADE") and i["to_team_id"] == team_id]
            dropped = [name(i) for i in items if i["type"] in ("DROP", "TRADE") and i["from_team_id"] == team_id]
            if not added and not dropped:
                continue
            key = (t["date"], t["type"], tuple(sorted(str(i["player_id"]) for i in items)))
            if key in seen:
                continue
            seen.add(key)
            out.append({"week": facts["week"], "date": t["date"], "type": kind, "added": added, "dropped": dropped})
    out.sort(key=lambda m: m["date"], reverse=True)
    return out


# ---------- audit: shared ----------

def _card(key, kind, stat, title, text):
    return {"key": key, "kind": kind, "level": "info", "stat": stat, "title": title, "text": text}


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


LINEUP_TITLE = {"A": "Your lineup calls have been sharp", "B": "Mostly the right calls",
                "C": "The bench keeps getting the good weeks", "D": "Your bench is outscoring your lineup"}


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
        return _card(f"lineup:{b}:none", "lineup_iq", stat, "Perfect lineups, every week",
                     "You've started your best possible lineup every single week. The bench has scored nothing you needed.")
    wk, r, c = worst
    text = (f"Biggest miss: Week {wk}, starting {c['started']} ({_f1(c['started_points'])}) at "
            f"{GROUP_LABEL.get(c['slot'], c['slot'])} while {c['benched']} put up {_f1(c['benched_points'])} on your bench.")
    return _card(f"lineup:{b}:{_benched_id(r, c['benched'])}", "lineup_iq", stat, LINEUP_TITLE[b], text)


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


def position_card(ranks):
    """(card, weak_spot) for one team, from its {group: league rank} (1 = best)."""
    best = [g for g in GROUPS if ranks[g] == min(ranks.values())][0]
    worst = [g for g in GROUPS if ranks[g] == max(ranks.values())][0]
    stat = f"Best: {best} (#{ranks[best]}) · Worst: {worst} (#{ranks[worst]})"
    if ranks[best] == ranks[worst]:
        title = "Even across the board"
        text = f"Every spot in your lineup ranks {_ordinal(ranks[best])} in the league. No weak link to fix, which is its own kind of flex."
    else:
        title = f"Your {GROUP_LABEL[best].split(' (')[0]} is carrying you"
        text = (f"Your {GROUP_LABEL[best]} points rank {_ordinal(ranks[best])} in the league. Your "
                f"{GROUP_LABEL[worst]} points rank {_ordinal(ranks[worst])}, so that's where a pickup helps most.")
    return _card(f"pos:{best}:{worst}", "position", stat, title, text), worst


# ---------- audit: Projection vs reality ----------

def _vs(name, avg):
    return f"{name} is running {_f1(abs(avg))} a game {'ahead of' if avg >= 0 else 'behind'} his projection"


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
            e = per.setdefault(str(p["player_id"]), {"name": p["name"], "n": 0, "sum": 0.0})
            e["n"] += 1
            e["sum"] += d
    eligible = sorted(((e["sum"] / e["n"], pid, e["name"]) for pid, e in per.items() if e["n"] >= MIN_STARTS),
                      key=lambda x: (-x[0], x[1]))
    top = eligible[0] if eligible else None
    bottom = eligible[-1] if len(eligible) >= 2 else None
    direction = "over" if delta >= 0 else "under"
    stat = f"{'+' if delta >= 0 else '-'}{_f1(abs(delta))} vs projections"
    title = "Your starters are beating ESPN's guesses" if direction == "over" else "Your starters keep landing under projection"
    if not top:
        text = "Nobody has two starts yet, so it's too early to name names."
    elif not bottom:
        text = f"{_vs(top[2], top[0])}."
    else:
        text = f"{_vs(top[2], top[0])}. {_vs(bottom[2], bottom[0])}."
    key = f"proj:{direction}:{top[1] if top else 'none'}:{bottom[1] if bottom else 'none'}"
    return _card(key, "projection", stat, title, text)


# ---------- audit: all three, every team ----------

def audits(facts_list, team_ids):
    """{team_id: {"cards": [lineup_iq, position, projection], "weak_spot": group}}, from the
    weeks given (the build passes only recapped ones). No weeks → no cards, no weak spot."""
    ranks = position_ranks(position_totals(facts_list)) if facts_list else {}
    out = {}
    for tid in team_ids:
        rows = [(f["week"], t) for f in facts_list for t in f["teams"] if t["team_id"] == tid]
        if not rows:
            out[tid] = {"cards": [], "weak_spot": None}
            continue
        pos, weak = position_card(ranks[tid])
        out[tid] = {"cards": [lineup_iq(rows), pos, projection_card(rows)], "weak_spot": weak}
    return out
