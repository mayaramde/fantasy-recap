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

def moves(team_id, captured):
    """Her adds, drops and trades across every captured week, newest first.

    A trade is recorded under one party's transaction, so "is she in it" is read off the
    items, not the transaction's team. A transaction can show up in two consecutive
    captures; the first (oldest) week it appeared in wins.
    """
    seen, out = set(), []
    for facts, espn in captured:
        for t in espn.get("transactions", []):
            kind = MOVE_TYPES.get(t["type"])
            if not kind:
                continue
            items = t.get("items", [])
            added = [i["name"] for i in items if i["type"] in ("ADD", "TRADE") and i["to_team_id"] == team_id]
            dropped = [i["name"] for i in items if i["type"] in ("DROP", "TRADE") and i["from_team_id"] == team_id]
            if not added and not dropped:
                continue
            key = (t["date"], t["type"], tuple(sorted(str(i["player_id"]) for i in items)))
            if key in seen:
                continue
            seen.add(key)
            out.append({"week": facts["week"], "date": t["date"], "type": kind, "added": added, "dropped": dropped})
    out.sort(key=lambda m: m["date"], reverse=True)
    return out
