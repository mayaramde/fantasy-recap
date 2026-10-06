# Team Profile Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `#team-<id>` into each manager's one-stop team page (this week's to-dos and lineup, a season audit, suggestions, roster moves), absorbing the per-team Coach page.

**Architecture:** A new pure module `site/team_profile.py` computes the audit cards (each with a situation `key`) and roster moves from already-loaded captures. `site/build.py` attaches them to each team in the season payload, applies coach-daily's written audit copy by key, and tags roster ideas that fit the team's weak spot. `site/template.html` renders the profile by composing the existing coach components; `#coach-<id>` redirects to it.

**Tech Stack:** Python 3 stdlib (`unittest`), vanilla JS/HTML in `site/template.html`, GitHub Actions `checks` workflow.

**Spec:** `docs/superpowers/specs/2026-09-30-team-profile-design.md`

## Global Constraints

- Site copy: no em dashes (use a period or comma); first names only; explain jargon in passing ("flex (the wild-card spot)").
- Roast decisions, never a manager's competence: the Lineup IQ band (A–D) appears **only inside the key**, never on the page.
- Pop colors (lime, pink, tangerine, cobalt) are fills with ink text on top (`var(--on-pop)`), never text on white.
- Audit computed from **included weeks only** (published recaps on the league site; drafts too in preview). Moves read **every captured week**.
- Key formats, verbatim: `lineup:<A|B|C|D>:<benched player id | none>`, `pos:<best group>:<worst group>`, `proj:<over|under>:<top id | none>:<bottom id | none>`.
- Slot groups, in this order (tie-break order): `QB, RB, WR, TE, FLEX, DST, K`.
- Lineup IQ bands: A ≥ 0.95, B ≥ 0.88, C ≥ 0.80, else D. Projection over/under-performers need ≥ 2 starts.
- Written copy (coach cards and audit) is rejected by `_MOVING_NUMBER` if it contains a decimal, `%`, "percent", or "N points".
- Written audit copy: key match only, **no** 36-hour freshness gate. Coach cards keep the gate.
- `pos` on a roster idea is optional; missing `pos` must never break anything.
- Never read or print `.env*` files, ESPN cookies or Vercel tokens. Work only in this worktree (`.claude/worktrees/team-profile`, branch `team-profile-design`).

## Review Focus

1. **`#team-3.next` with no current next-week capture**: should render the This week tab, not a blank section or "Fumble". Pinned in Task 7 Step 6.
2. **A `worst_bench_call` whose benched name isn't in that week's `bench`** (renamed player, D/ST label drift): the key should fall back to a name slug and stay stable across builds. Pinned in Task 2.
3. **A starter with `projected: null`** (a week captured before ESPN published projections): skipped by Projection vs reality, no crash, no fake zero. Pinned in Task 4.
4. **A trade recorded under the *other* team's transaction**: must still appear on both managers' profiles with the right direction. Pinned in Task 1.
5. **An old `#coach-3` bookmark before any recap exists** (preseason, `WEEKS` empty): must land on the profile, not the "First recap coming soon" screen. Pinned in Task 7 Step 6.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `site/team_profile.py` | Create | Pure functions: `moves`, `lineup_iq`, `position_totals`, `position_ranks`, `position_card`, `projection_card`, `audits`. No I/O. |
| `tests/test_team_profile.py` | Create | Unit tests on hand-built fixtures. |
| `site/build.py` | Modify | `site_data()` split out of `render()`; `written_audit()`; attach `profile`; tag `fills_weak_spot`. |
| `tests/test_coach_written.py` | Modify | Written audit copy, freshness split, weak-spot tag, brief audit block. |
| `scripts/coach_brief.py` | Modify | Top-level `audit` block; no exit when there's no live week. |
| `site/template.html` | Modify | Router + redirects, `teamPage(id, next)` composing coach sections, audit, suggestions, moves. |
| `scripts/check.py` | Modify | `check_team_profiles()`. |
| `.github/workflows/checks.yml` | Modify | Run `tests.test_team_profile`. |
| `docs/architecture.md`, `CLAUDE.md`, `.claude/skills/coach-daily/SKILL.md` | Modify | Document the page, the module and the snapshot contract. |

---

### Task 1: `team_profile.moves()`

**Files:**
- Create: `site/team_profile.py`
- Test: `tests/test_team_profile.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `team_profile.moves(team_id: int, captured: list[tuple[dict, dict]]) -> list[dict]`, rows `{"week": int, "date": str, "type": "add" | "trade", "added": list[str], "dropped": list[str]}`, newest first. `captured` is `build.load_inputs()`'s list of `(facts, espn)`, oldest week first.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_team_profile.py`:

```python
#!/usr/bin/env python3
"""Tests for site/team_profile.py: the team profile's audit cards and roster moves.

Hand-built fixtures only, so every expected number is checkable by eye.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
import team_profile as tp  # noqa: E402


def item(kind, pid, name, frm, to):
    return {"type": kind, "player_id": pid, "name": name, "from_team_id": frm, "to_team_id": to,
            "from_slot": None, "to_slot": None}


def txn(kind, team_id, date, items):
    return {"type": kind, "team_id": team_id, "date": date, "bid": 0, "items": items}


def cap(week, transactions):
    return ({"week": week}, {"week": week, "transactions": transactions})


class MovesTest(unittest.TestCase):
    def test_keeps_adds_drops_and_trades_drops_lineup_and_draft(self):
        captured = [cap(1, [
            txn("DRAFT", 2, "2026-09-01T00:00:00Z", [item("ADD", 1, "Draft Pick", 0, 2)]),
            txn("ROSTER", 2, "2026-09-02T00:00:00Z", [item("LINEUP", 1, "Draft Pick", 0, 0)]),
            txn("WAIVER", 2, "2026-09-03T00:00:00Z", [item("ADD", 3139477, "Patrick Mahomes", 0, 2),
                                                     item("DROP", 4432708, "Marvin Harrison Jr.", 2, 0)]),
            txn("FUTURE_ROSTER", 2, "2026-09-04T00:00:00Z", [item("LINEUP", 1, "Draft Pick", 0, 0)]),
        ])]
        self.assertEqual(tp.moves(2, captured), [
            {"week": 1, "date": "2026-09-03T00:00:00Z", "type": "add",
             "added": ["Patrick Mahomes"], "dropped": ["Marvin Harrison Jr."]}])

    def test_trade_shows_on_both_sides_with_direction(self):
        # Recorded under team 5's transaction; team 7 is the other party.
        captured = [cap(2, [txn("TRADE_ACCEPT", 5, "2026-09-10T00:00:00Z", [
            item("TRADE", 10, "Player Ten", 5, 7), item("TRADE", 20, "Player Twenty", 7, 5)])])]
        five, seven = tp.moves(5, captured), tp.moves(7, captured)
        self.assertEqual(five[0]["type"], "trade")
        self.assertEqual((five[0]["added"], five[0]["dropped"]), (["Player Twenty"], ["Player Ten"]))
        self.assertEqual((seven[0]["added"], seven[0]["dropped"]), (["Player Ten"], ["Player Twenty"]))

    def test_other_teams_moves_are_ignored(self):
        captured = [cap(1, [txn("FREEAGENT", 3, "2026-09-03T00:00:00Z", [item("ADD", 9, "Someone", 0, 3)])])]
        self.assertEqual(tp.moves(2, captured), [])

    def test_dedupes_across_captures_keeping_first_week_and_sorts_newest_first(self):
        a = txn("FREEAGENT", 2, "2026-09-03T00:00:00Z", [item("ADD", 9, "Early Add", 0, 2)])
        b = txn("FREEAGENT", 2, "2026-09-12T00:00:00Z", [item("DROP", -16034, "Texans D/ST", 2, 0)])
        rows = tp.moves(2, [cap(1, [a]), cap(2, [a, b])])
        self.assertEqual([(r["week"], r["date"]) for r in rows],
                         [(2, "2026-09-12T00:00:00Z"), (1, "2026-09-03T00:00:00Z")])
        self.assertEqual(rows[0]["dropped"], ["Texans D/ST"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_team_profile -v`
Expected: `ModuleNotFoundError: No module named 'team_profile'`

- [ ] **Step 3: Implement**

Create `site/team_profile.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_team_profile -v`
Expected: 4 tests, OK

- [ ] **Step 5: Commit**

```bash
git add site/team_profile.py tests/test_team_profile.py
git commit -m "Team profile: roster moves across every captured week

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Lineup IQ card

**Files:**
- Modify: `site/team_profile.py` (append)
- Test: `tests/test_team_profile.py` (append a class)

**Interfaces:**
- Consumes: `_f1`, `_slug`, `GROUP_LABEL`, `BANDS` from Task 1.
- Produces: `team_profile.band(pct: float) -> str`; `team_profile.lineup_iq(rows: list[tuple[int, dict]]) -> dict`. `rows` = `(week, facts team row)` for one team, oldest first, non-empty. Card shape (shared by every audit card): `{"key", "kind", "level": "info", "stat", "title", "text"}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_team_profile.py` (above the `if __name__` line):

```python
def player(pid, name, slot, points, projected):
    return {"player_id": pid, "name": name, "pos": slot, "slot": slot, "points": points, "projected": projected}


def row(team_id, points, optimal, left=0.0, worst=None, starters=(), bench=()):
    return {"team_id": team_id, "points": points, "optimal_points": optimal, "points_left_on_bench": left,
            "worst_bench_call": worst, "starters": list(starters), "bench": list(bench)}


def call(benched, started, bp, sp, slot="TE"):
    return {"benched": benched, "benched_points": bp, "benched_projected": 10, "started": started,
            "started_points": sp, "started_projected": 10, "slot": slot, "gap": round(bp - sp, 2)}


class LineupIQTest(unittest.TestCase):
    def test_band_edges(self):
        self.assertEqual([tp.band(x) for x in (1.0, 0.95, 0.9499, 0.88, 0.80, 0.7999)],
                         ["A", "A", "B", "B", "C", "D"])

    def test_percent_of_optimal_worst_call_and_key(self):
        rows = [
            (1, row(6, 90, 100, left=10, worst=call("Kincaid", "Odunze", 15, 5, "FLEX"),
                    bench=[player(111, "Kincaid", "BENCH", 15, 10)])),
            (2, row(6, 90, 100, left=24.1, worst=call("Fannin", "Warren", 24.1, 14.7),
                    bench=[player(222, "Fannin", "BENCH", 24.1, 9.8)])),
        ]
        card = tp.lineup_iq(rows)
        self.assertEqual(card["key"], "lineup:B:222")          # 180/200 = 0.90 → B; biggest gap is week 2
        self.assertEqual(card["stat"], "90% of optimal · 34.1 benched")
        self.assertEqual((card["kind"], card["level"]), ("lineup_iq", "info"))
        self.assertIn("Week 2", card["text"])
        self.assertNotIn(" B ", f" {card['title']} {card['text']} ")   # band never shown

    def test_perfect_lineups(self):
        card = tp.lineup_iq([(1, row(6, 120, 120)), (2, row(6, 100, 100))])
        self.assertEqual(card["key"], "lineup:A:none")
        self.assertEqual(card["stat"], "100% of optimal · 0.0 benched")

    def test_benched_name_missing_from_bench_falls_back_to_slug(self):
        rows = [(1, row(6, 70, 100, left=30, worst=call("Texans D/ST", "49ers D/ST", 30, 0, "DST")))]
        self.assertEqual(tp.lineup_iq(rows)["key"], "lineup:D:texans-d-st")

    def test_negative_dst_id(self):
        rows = [(1, row(6, 70, 100, left=30, worst=call("Texans D/ST", "49ers D/ST", 30, 0, "DST"),
                        bench=[player(-16034, "Texans D/ST", "BENCH", 30, 5)]))]
        self.assertEqual(tp.lineup_iq(rows)["key"], "lineup:D:-16034")

    def test_ties_keep_the_oldest_week(self):
        rows = [(1, row(6, 90, 100, worst=call("A", "B", 20, 10), bench=[player(1, "A", "BENCH", 20, 9)])),
                (2, row(6, 90, 100, worst=call("C", "D", 20, 10), bench=[player(2, "C", "BENCH", 20, 9)]))]
        self.assertEqual(tp.lineup_iq(rows)["key"], "lineup:B:1")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_team_profile.LineupIQTest -v`
Expected: `AttributeError: module 'team_profile' has no attribute 'band'`

- [ ] **Step 3: Implement**

Append to `site/team_profile.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_team_profile -v`
Expected: all tests OK

- [ ] **Step 5: Commit**

```bash
git add site/team_profile.py tests/test_team_profile.py
git commit -m "Team profile: Lineup IQ audit card

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Position strength card and `weak_spot`

**Files:**
- Modify: `site/team_profile.py` (append)
- Test: `tests/test_team_profile.py` (append a class)

**Interfaces:**
- Consumes: `GROUPS`, `GROUP_LABEL`, `_card`, `_ordinal`.
- Produces:
  - `position_totals(facts_list: list[dict]) -> dict[int, dict[str, float]]`: team_id → group → starter points.
  - `position_ranks(totals) -> dict[int, dict[str, int]]`: 1 = best in the league for that group.
  - `position_card(ranks_for_team: dict[str, int]) -> tuple[dict, str]`: (card, weak_spot group).

> **Human contribution (Learn by Doing, at execution time):** the choice of best and worst group inside `position_card` (the two `min(...)` lines), including the tie-break, is left for Maya to write. The code below is the reference the tests are written against.

- [ ] **Step 1: Write the failing tests**

```python
def week(wk, teams):
    return {"week": wk, "teams": teams}


def lineup(team_id, **slot_points):
    starters = [player(i, f"{team_id}-{slot}", slot, pts, 10) for i, (slot, pts) in enumerate(slot_points.items())]
    return row(team_id, sum(slot_points.values()), 0, starters=starters)


class PositionTest(unittest.TestCase):
    def test_totals_and_ranks(self):
        facts = [week(1, [lineup(1, QB=20, TE=2), lineup(2, QB=10, TE=12)]),
                 week(2, [lineup(1, QB=20, TE=2), lineup(2, QB=10, TE=12)])]
        totals = tp.position_totals(facts)
        self.assertEqual((totals[1]["QB"], totals[2]["TE"]), (40, 24))
        ranks = tp.position_ranks(totals)
        self.assertEqual((ranks[1]["QB"], ranks[1]["TE"], ranks[2]["QB"]), (1, 2, 2))

    def test_card_key_and_weak_spot(self):
        ranks = {"QB": 1, "RB": 4, "WR": 3, "TE": 8, "FLEX": 2, "DST": 5, "K": 6}
        card, weak = tp.position_card(ranks)
        self.assertEqual((card["key"], weak), ("pos:QB:TE", "TE"))
        self.assertEqual(card["stat"], "Best: QB (#1) · Worst: TE (#8)")
        self.assertIn("tight end", card["text"])

    def test_ties_break_by_slot_order_and_are_stable(self):
        ranks = {"QB": 3, "RB": 1, "WR": 1, "TE": 7, "FLEX": 7, "DST": 4, "K": 5}
        for _ in range(3):
            self.assertEqual(tp.position_card(dict(ranks))[0]["key"], "pos:RB:TE")

    def test_same_rank_everywhere(self):
        card, weak = tp.position_card(dict.fromkeys(tp.GROUPS, 1))
        self.assertEqual((card["key"], weak), ("pos:QB:QB", "QB"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_team_profile.PositionTest -v`
Expected: `AttributeError: ... 'position_totals'`

- [ ] **Step 3: Implement**

```python
# ---------- audit: Position strength ----------

def position_totals(facts_list):
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
    best = min(GROUPS, key=lambda g: (ranks[g], GROUPS.index(g)))
    worst = min(GROUPS, key=lambda g: (-ranks[g], GROUPS.index(g)))
    stat = f"Best: {best} (#{ranks[best]}) · Worst: {worst} (#{ranks[worst]})"
    if ranks[best] == ranks[worst]:
        title = "Even across the board"
        text = f"Every spot in your lineup ranks {_ordinal(ranks[best])} in the league. No weak link to fix, which is its own kind of flex."
    else:
        title = f"Your {GROUP_LABEL[best].split(' (')[0]} is carrying you"
        text = (f"Your {GROUP_LABEL[best]} points rank {_ordinal(ranks[best])} in the league. Your "
                f"{GROUP_LABEL[worst]} points rank {_ordinal(ranks[worst])}, so that's where a pickup helps most.")
    return _card(f"pos:{best}:{worst}", "position", stat, title, text), worst
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_team_profile -v`
Expected: all OK

- [ ] **Step 5: Commit**

```bash
git add site/team_profile.py tests/test_team_profile.py
git commit -m "Team profile: Position strength card and weak spot

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Projection vs reality card and `audits()`

**Files:**
- Modify: `site/team_profile.py` (append)
- Test: `tests/test_team_profile.py` (append two classes)

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `projection_card(rows: list[tuple[int, dict]]) -> dict`
  - `audits(facts_list: list[dict], team_ids: list[int]) -> dict[int, {"cards": list[dict], "weak_spot": str | None}]`. Cards are in order `[lineup_iq, position, projection]`; empty list and `None` when `facts_list` is empty.

- [ ] **Step 1: Write the failing tests**

```python
class ProjectionTest(unittest.TestCase):
    def rows(self):
        return [(1, row(1, 0, 0, starters=[player(10, "Hot", "WR", 20, 10), player(20, "Cold", "RB", 2, 12),
                                           player(30, "Once", "TE", 30, 5)])),
                (2, row(1, 0, 0, starters=[player(10, "Hot", "WR", 16, 10), player(20, "Cold", "RB", 4, 12)]))]

    def test_delta_over_and_players(self):
        card = tp.projection_card(self.rows())
        # (10+6) + (-10-8) + 25 = +23
        self.assertEqual(card["key"], "proj:over:10:20")
        self.assertEqual(card["stat"], "+23.0 vs projections")
        self.assertNotIn("Once", card["text"])         # one start: not eligible

    def test_under(self):
        rows = [(1, row(1, 0, 0, starters=[player(20, "Cold", "RB", 2, 12)]))]
        card = tp.projection_card(rows)
        self.assertEqual((card["key"], card["stat"]), ("proj:under:none:none", "-10.0 vs projections"))

    def test_null_projection_is_skipped(self):
        rows = self.rows() + [(3, row(1, 0, 0, starters=[player(20, "Cold", "RB", 40, None)]))]
        self.assertEqual(tp.projection_card(rows)["stat"], "+23.0 vs projections")

    def test_single_eligible_player_has_no_bottom(self):
        rows = [(w, row(1, 0, 0, starters=[player(10, "Hot", "WR", 20, 10)])) for w in (1, 2)]
        self.assertEqual(tp.projection_card(rows)["key"], "proj:over:10:none")


class AuditsTest(unittest.TestCase):
    def test_no_weeks(self):
        self.assertEqual(tp.audits([], [1, 2]), {1: {"cards": [], "weak_spot": None},
                                                 2: {"cards": [], "weak_spot": None}})

    def test_three_cards_in_order_and_stable_keys(self):
        def facts():
            t1 = lineup(1, QB=20, TE=2)
            t1.update(points=22, optimal_points=22)
            t2 = lineup(2, QB=10, TE=12)
            t2.update(points=22, optimal_points=30, points_left_on_bench=8)
            return [week(1, [t1, t2])]
        a, b = tp.audits(facts(), [1, 2]), tp.audits(facts(), [1, 2])
        self.assertEqual([c["kind"] for c in a[1]["cards"]], ["lineup_iq", "position", "projection"])
        self.assertEqual([c["key"] for c in a[1]["cards"]], [c["key"] for c in b[1]["cards"]])
        # Team 1 is 1st at QB and, on the team-id tie-break, at every empty group; 2nd only at TE.
        self.assertEqual(a[1]["weak_spot"], "TE")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_team_profile.ProjectionTest tests.test_team_profile.AuditsTest -v`
Expected: `AttributeError: ... 'projection_card'`

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_team_profile -v`
Expected: all OK

- [ ] **Step 5: Commit**

```bash
git add site/team_profile.py tests/test_team_profile.py
git commit -m "Team profile: Projection vs reality card and audits()

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Wire the profile into `site/build.py`

**Files:**
- Modify: `site/build.py` (imports near line 25; after `apply_written` ~line 260; `render()` ~line 1123)
- Test: `tests/test_coach_written.py` (append tests)

**Interfaces:**
- Consumes: `team_profile.audits`, `team_profile.moves`; existing `apply_written`, `_valid_written`, `season_payload`, `live_payload`, `next_payload`.
- Produces:
  - `build.site_data(recap_weeks, captured, preview, ahead=None, fp=None) -> tuple[dict, list]`: the `data` dict `render()` embeds, plus `weeks` (same second value `render()` returned before). `render()` keeps its signature and return value.
  - `build.written_audit(team_id: int, fp: dict | None) -> dict[str, dict]`
  - Each `data["season"]["standings"][i]["profile"] = {"audit": [card], "weak_spot": str | None, "moves": [move]}`.
  - Each roster idea in `live["advice"][i]["roster_ideas"]` and `live["next"]["teams"][i]["roster_ideas"]` gets `fills_weak_spot: bool`.

- [ ] **Step 1: Write the failing tests**

Append inside `class CoachWrittenTest` in `tests/test_coach_written.py`:

```python
    def data(self, fp=None):
        data, _ = build.site_data(copy.deepcopy(self.recap_weeks), copy.deepcopy(self.captured),
                                  preview=False, fp=fp)
        return data

    def team(self, data, team_id):
        return next(s for s in data["season"]["standings"] if s["team_id"] == team_id)

    def test_every_team_has_a_profile(self):
        for s in self.data()["season"]["standings"]:
            self.assertEqual([c["kind"] for c in s["profile"]["audit"]], ["lineup_iq", "position", "projection"])
            self.assertIn(s["profile"]["weak_spot"], ("QB", "RB", "WR", "TE", "FLEX", "DST", "K"))
            self.assertIsInstance(s["profile"]["moves"], list)

    def test_audit_uses_recapped_weeks_only(self):
        # Week 3 is the live week here, so no audit text may mention it.
        for s in self.data()["season"]["standings"]:
            for c in s["profile"]["audit"]:
                self.assertNotIn("Week 3", c["text"])

    def audit_fp(self, team_id, key, text="Kincaid sat while the lineup starved.", hours_ago=0, **extra):
        fp = self.snapshot(extra.pop("teams", {}), hours_ago=hours_ago)
        fp["audit"] = {str(team_id): {key: {"title": "Written title", "text": text}}}
        return fp

    def test_written_audit_applies_on_key_match(self):
        tid = 6
        key = self.team(self.data(), tid)["profile"]["audit"][0]["key"]
        card = self.team(self.data(self.audit_fp(tid, key)), tid)["profile"]["audit"][0]
        self.assertEqual((card["title"], card.get("written")), ("Written title", True))

    def test_written_audit_ignored_on_key_mismatch(self):
        card = self.team(self.data(self.audit_fp(6, "lineup:Z:none")), 6)["profile"]["audit"][0]
        self.assertNotEqual(card["title"], "Written title")

    def test_written_audit_survives_a_stale_snapshot_but_coach_cards_do_not(self):
        tid = 6
        key = self.team(self.data(), tid)["profile"]["audit"][0]["key"]
        live_row = next(r for r in self.live() if r["team_id"] == tid)
        coach_key = next(it["key"] for it in live_row["items"] if it.get("key"))
        teams = {str(tid): {"coach_cards": {coach_key: {"title": "Written coach", "text": "Swap him."}}}}
        data = self.data(self.audit_fp(tid, key, hours_ago=48, teams=teams))
        self.assertEqual(self.team(data, tid)["profile"]["audit"][0]["title"], "Written title")
        row = next(r for r in data["live"]["advice"] if r["team_id"] == tid)
        self.assertNotIn("Written coach", [it["title"] for it in row["items"]])

    def test_written_audit_rejects_moving_numbers(self):
        tid = 6
        key = self.team(self.data(), tid)["profile"]["audit"][0]["key"]
        card = self.team(self.data(self.audit_fp(tid, key, text="You hit 91% of optimal.")), tid)["profile"]["audit"][0]
        self.assertNotEqual(card["title"], "Written title")

    def test_roster_ideas_tagged_only_on_weak_spot_match(self):
        tid = 6
        weak = self.team(self.data(), tid)["profile"]["weak_spot"]
        other = "K" if weak != "K" else "QB"
        idea = lambda title, **kw: {"kind": "waiver", "level": "info", "title": title, "text": "Worth a claim.", **kw}
        fp = self.snapshot({str(tid): {"roster_ideas": [idea("fits", pos=weak), idea("other", pos=other), idea("nopos")]}})
        row = next(r for r in self.data(fp)["live"]["advice"] if r["team_id"] == tid)
        tags = {i["title"]: i["fills_weak_spot"] for i in row["roster_ideas"]}
        self.assertEqual(tags, {"fits": True, "other": False, "nopos": False})
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_coach_written -v`
Expected: new tests fail with `AttributeError: module 'build' has no attribute 'site_data'`; existing tests still pass.

- [ ] **Step 3: Implement**

In `site/build.py`, add after the existing imports (next to `from pathlib import Path`):

```python
import team_profile
```

Add right after `apply_written()`:

```python
def written_audit(team_id, fp):
    """{key: {title, text}} for one team's season-audit cards, from the snapshot's top-level
    `audit`. No freshness gate, unlike the coach cards: an audit key fully describes weeks
    that are already over, so copy written for a key that still matches is still true
    however old the file is. A missing or malformed snapshot just means computed wording."""
    if not fp:
        return {}
    row = (fp.get("audit") or {}).get(str(team_id))
    return {k: v for k, v in row.items() if _valid_written(v)} if isinstance(row, dict) else {}
```

Replace `render()` with `site_data()` + a thin `render()`:

```python
def site_data(recap_weeks, captured, preview, ahead=None, fp=None):
    """(data, weeks): everything the page's RECAP_DATA blob carries, and the week payloads
    (live included) render() hands back to its callers."""
    included = [(f, w) for f, w in recap_weeks if preview or w["status"] == "published"]
    weeks = [w for _, w in included]
    # Live page: the newest captured week that isn't in this output's recaps yet
    last = max((w["week"] for w in weeks), default=0)
    pending = [c for c in captured if c[0]["week"] > last]
    live = None
    if pending:
        facts, espn = pending[-1]
        previous = next((e for f, e in reversed(captured) if f["week"] < facts["week"]), None)
        live = live_payload(facts, espn, previous, fp=fp)
        # The week-ahead capture is only good for the week after the live one. A stale
        # one (captured before this week started) is dropped rather than shown as next.
        if ahead and ahead["week"] == facts["week"] + 1:
            live["next"] = next_payload(ahead, previous, fp=fp)

    season = season_payload([f for f, _ in included], weeks)
    # Team profiles: the audit reads only this output's included weeks (a draft week never
    # reaches the league site); moves read every captured week, same as the Live page does.
    profiles = team_profile.audits([f for f, _ in included], [t["team_id"] for t in LEAGUE["teams"]])
    for s in season["standings"]:
        p = profiles[s["team_id"]]
        s["profile"] = {"audit": apply_written(p["cards"], written_audit(s["team_id"], fp)),
                        "weak_spot": p["weak_spot"], "moves": team_profile.moves(s["team_id"], captured)}
    if live:
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


def render(recap_weeks, captured, preview, ahead=None, fp=None):
    data, weeks = site_data(recap_weeks, captured, preview, ahead=ahead, fp=fp)
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = "Fantasy Football for the Girls (Preview)" if preview else "Fantasy Football for the Girls"
    template = (SITE / "template.html").read_text()
    return template.replace("__PAGE_TITLE__", title).replace("__RECAP_DATA__", blob), weeks
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_coach_written tests.test_team_profile -v && python3 site/build.py`
Expected: all OK; build writes `site/dist/` without error.

- [ ] **Step 5: Commit**

```bash
git add site/build.py tests/test_coach_written.py
git commit -m "Build: attach team profiles, written audit copy and weak-spot tags

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `scripts/coach_brief.py` audit block

**Files:**
- Modify: `scripts/coach_brief.py`
- Modify: `docs/superpowers/specs/2026-09-30-team-profile-design.md` (one line, see Step 3)
- Test: `tests/test_coach_written.py` (append a test)

**Interfaces:**
- Consumes: `build.site_data`, `build.load_inputs`.
- Produces: `coach_brief.brief(season) -> dict` always containing `"audit": {"<team_id>": {"manager", "weak_spot", "cards": [{key, kind, stat, title, text}]}}`, plus the existing per-week blocks when there's a live week.

- [ ] **Step 1: Write the failing test**

Append inside `CoachWrittenTest`:

```python
    def test_brief_has_audit_for_every_team(self):
        import coach_brief
        out = coach_brief.brief(SEASON)
        self.assertEqual(len(out["audit"]), 8)
        for row in out["audit"].values():
            self.assertEqual(set(row), {"manager", "weak_spot", "cards"})
            for c in row["cards"]:
                self.assertEqual(set(c), {"key", "kind", "stat", "title", "text"})
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_coach_written.CoachWrittenTest.test_brief_has_audit_for_every_team -v`
Expected: `KeyError: 'audit'`

- [ ] **Step 3: Implement**

In `scripts/coach_brief.py`, add `AUDIT_KEYS` and rewrite `brief()` / `main()`:

```python
AUDIT_KEYS = ("key", "kind", "stat", "title", "text")


def brief(season):
    recap_weeks, captured, ahead, _ = build.load_inputs(season)
    # The league site's view (published recaps only), since that's the page managers read.
    data, weeks = build.site_data(recap_weeks, captured, preview=False, ahead=ahead, fp=None)
    # The season audit exists all season, live week or not.
    out = {"audit": {str(s["team_id"]): {"manager": s["manager"], "weak_spot": s["profile"]["weak_spot"],
                                         "cards": [{k: c[k] for k in AUDIT_KEYS} for c in s["profile"]["audit"]]}
                     for s in data["season"]["standings"]}}
    live = next((w for w in weeks if w.get("live")), None)
    if not live:
        return out
    out[str(live["week"])] = {"tab": "this week", "teams": [team_brief(r) for r in live["advice"]]}
    nxt = live.get("next")
    if nxt:
        out[str(nxt["week"])] = {"tab": "next week", "projected": nxt["projected"],
                                 "teams": [team_brief(r) for r in nxt["teams"]]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=build.LEAGUE["season"])
    args = ap.parse_args()
    json.dump(brief(args.season), sys.stdout, indent=2, ensure_ascii=False)
    print()
```

Update the module docstring's first paragraph to mention the `audit` block and that it prints even with no live week.

In the spec, change the brief bullet "computed from the league site's view (published recaps only) via `team_profile` directly." to "computed from the league site's view (published recaps only) via `build.site_data`, so the brief's keys are byte-for-byte the page's." (`site_data` is cheaper than the old `render()` and guarantees identical keys; importing `team_profile` alone would duplicate the included-weeks logic.)

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_coach_written -v && python3 scripts/coach_brief.py | head -30`
Expected: OK; brief prints an `audit` block even though every captured week is recapped.

- [ ] **Step 5: Commit**

```bash
git add scripts/coach_brief.py tests/test_coach_written.py docs/superpowers/specs/2026-09-30-team-profile-design.md
git commit -m "coach_brief: season audit block, printed with or without a live week

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The profile page in `site/template.html`

**Files:**
- Modify: `site/template.html`: CSS (next to `.decided .tag.*`, ~line 296), `coachUrl` (~line 567), `teamPage` (~line 1217), `coachTeamPage` (~line 1358, replaced), `route()` (~line 1443), `refreshLive()` (~line 1511).

**Interfaces:**
- Consumes: `TEAMS[id].profile` (Task 5), `roster_ideas[].fills_weak_spot` (Task 5), existing `coachFor`, `ahead`, `advice`, `weekToggle`, `teamSwitch`, `adviceCard`, `lineupCard`, `nextLineupCard`, `coachSource`, `nextSource`, `ADVICE_LEVEL`, `secHead`, `myTeam`.
- Produces: routes `#team-<id>` and `#team-<id>.next`; `#coach-<id>` / `#coach-next-<id>` redirect.

- [ ] **Step 1: Point coach URLs at profiles**

Replace the `coachUrl` line:

```js
  // A team's coach page is now a section of her profile; the league-wide grid keeps #coach.
  const coachUrl = (next, id) => (id ? `#team-${id}${next ? '.next' : ''}` : `#coach${next ? '-next' : ''}`);
```

- [ ] **Step 2: Weak-spot tag on cards + CSS**

In `adviceCard`, change the `card-top` line to:

```js
      <div class="card-top"><span class="who">${esc(ADVICE_KIND[it.kind] || 'Note')}</span>${it.fills_weak_spot ? '<span class="fit">fills your weak spot</span>' : ''}${it.stat ? `<span class="stat">${esc(it.stat)}</span>` : ''}</div>
```

After `.decided .tag.info { ... }` add:

```css
  .card .fit { font: 600 11px/1 var(--mono); background: var(--lime); color: var(--on-pop); border: 1.5px solid var(--edge); border-radius: 999px; padding: 4px 8px; transform: rotate(-2deg); white-space: nowrap; }
```

Add `lineup_iq: 'Lineup calls', position: 'Position strength', projection: 'Vs projections'` to the `ADVICE_KIND` map.

- [ ] **Step 3: Replace `coachTeamPage` with `thisWeekSection`**

Delete `function coachTeamPage(id, next) { ... }` and add in its place:

```js
  /* The week-in-progress part of a team's profile: what used to be her own Coach page.
     Same cards and lineup, still refreshed by /api/live through LIVE. */
  function thisWeekSection(id, next) {
    const a = coachFor(id, next);
    if (!a) {
      const wk = (WEEKS.length ? WEEKS[WEEKS.length - 1].week : 0) + 1;
      return `<section>${secHead('board', 'This week')}<p class="sec-sub">Nothing to fix until Week ${wk}'s rosters land.</p></section>`;
    }
    myTeam.set(id);
    const week = next ? ahead().week : LIVE.week;
    const g = next ? null : LIVE.games.find((x) => x.winner.team_id === id || x.loser.team_id === id);
    const mine = g && (g.winner.team_id === id ? g.winner : g.loser);
    const opp = g ? (g.winner.team_id === id ? g.loser : g.winner) : TEAMS[a.opponent_id];
    const byes = a.items.filter((it) => it.kind === 'bye').length;
    const groups = Object.keys(ADVICE_LEVEL)
      .map((lvl) => [lvl, a.items.filter((it) => it.level === lvl)])
      .filter(([, items]) => items.length);
    return `
      <section>
        <div class="kicker-row">
          ${secHead('board', next ? `Week ${week}, coming up` : `Week ${week}, this week`)}
          ${weekToggle(next, id)}
        </div>
        <p class="dek">${!next && a.can_change === false
          ? `Your Week ${week} lineup is locked, every game you had is over.${ahead() ? ` <a href="${coachUrl(true, id)}">Week ${ahead().week}</a> is where the work is now.` : ''}`
          : (a.counts.now ? `${a.counts.now} thing${a.counts.now === 1 ? '' : 's'} to ${next ? 'sort out before Sunday' : 'fix before kickoff'}.` : 'Nothing urgent.')}${opp ? ` You're playing <a href="#team-${opp.team_id}">${esc(opp.manager)}</a>${next ? ` in Week ${week}.` : `. <a href="#live.game-${g.key}">Live box score →</a>`}` : ''}</p>
        <p class="team-summary">${esc(a.summary)}</p>
        <div class="stat-tiles">
          <div class="tile"><div class="label">To ${next ? 'sort out' : 'fix now'}</div><div class="value">${a.counts.now}</div><div class="sub">${a.counts.watch} to keep an eye on</div></div>
          <div class="tile"><div class="label">Projected total</div><div class="value">${next && !ahead().projected ? '–' : f1(a.projected)}</div><div class="sub">${next ? (ahead().projected ? "ESPN's estimate for Week " + week : 'not published yet') : (mine ? `${f2(mine.points)} on the board` : "ESPN's estimate")}</div></div>
          ${next
            ? `<div class="tile"><div class="label">Starters on a bye</div><div class="value">${byes}</div><div class="sub">${byes ? 'a bye week means his NFL team doesn\'t play' : 'everyone has a game'}</div></div>`
            : `<div class="tile"><div class="label">Starters left to play</div><div class="value">${a.yet_to_play}</div><div class="sub">${a.playing_now ? `${a.playing_now} on the field right now` : `${a.movable} still swappable`}</div></div>`}
          ${a.win_probability == null ? '' : `<div class="tile"><div class="label">Chance to win</div><div class="value">${Math.round(a.win_probability * 100)}%</div><div class="sub">ESPN's number${opp ? `, vs ${esc(opp.manager)}` : ''}</div></div>`}
        </div>
      </section>

      ${groups.map(([lvl, items]) => `
        <section>
          ${secHead(ADVICE_LEVEL[lvl].marker, (next && ADVICE_LEVEL[lvl].nextTitle) || ADVICE_LEVEL[lvl].title)}
          <p class="sec-sub">${(next && ADVICE_LEVEL[lvl].nextSub) || ADVICE_LEVEL[lvl].sub}</p>
          <div class="cards">${items.map(adviceCard).join('')}</div>
        </section>`).join('')}

      ${next ? `
      <section>
        ${secHead('board', `Your lineup for Week ${week}`)}
        <p class="sec-sub">What you have set right now, and what ESPN projects for it. Tap any player for what ESPN is saying about him. The badge next to a name is his NFL team and a colored pill is ESPN's injury designation. Nobody has played, so there are no points yet.</p>
        <div class="box-grid">${nextLineupCard(a)}</div>
      </section>` : (mine ? `
      <section>
        ${secHead('board', 'Your lineup right now')}
        <p class="sec-sub">Tap any player for how his points happened, plus whatever ESPN is saying about him. The badge next to a name is his NFL team, a colored pill is ESPN's injury designation, and a pulsing lime sticker means his game is on right now. A ⚑ on the bench marks a player already outscoring a starter he could have replaced.</p>
        <div class="box-grid">${lineupCard(mine, true, true, `<span class="res">proj ${f1(a.projected)}</span>`, a.players)}</div>
      </section>` : '')}
      <p class="sec-sub">${next ? nextSource() : coachSource(LIVE)}</p>`;
  }

  function auditSection(p) {
    return `
      <section>
        ${secHead('board', "Coach's audit")}
        ${p.audit.length
          ? `<p class="sec-sub">How her season is going, from the weeks with a recap so far.</p><div class="cards">${p.audit.map(adviceCard).join('')}</div>`
          : '<p class="sec-sub">The coach needs one finished week before she has opinions.</p>'}
      </section>`;
  }

  function suggestionsSection(id, next) {
    const a = coachFor(id, next);
    const ideas = (a && a.roster_ideas) || [];
    return `
      <section>
        ${secHead('board', 'Worth a look')}
        ${ideas.length
          ? `<p class="sec-sub">Roster ideas from FantasyPros' rankings, ownership and your league's own rosters. Not urgent, not automatic, just worth a look.</p><div class="cards">${ideas.map(adviceCard).join('')}</div>`
          : '<p class="sec-sub">No new ideas today.</p>'}
      </section>`;
  }

  function movesSection(p) {
    const names = (xs) => xs.map(esc).join(', ');
    return `
      <section>
        ${secHead('board', 'Recent moves')}
        ${p.moves.length
          ? `<ul class="decided">${p.moves.map((m) => `<li><span class="tag ${m.type === 'trade' ? 'good' : 'info'}">Week ${m.week}</span><span>${m.type === 'trade' ? '<b>Trade.</b> ' : ''}${m.added.length ? `Added ${names(m.added)}` : ''}${m.added.length && m.dropped.length ? ' · ' : ''}${m.dropped.length ? `${m.type === 'trade' ? 'Sent' : 'Dropped'} ${names(m.dropped)}` : ''}</span></li>`).join('')}</ul>`
          : '<p class="sec-sub">No adds, drops or trades yet. Loyal to a fault.</p>'}
      </section>`;
  }
```

- [ ] **Step 4: Rewrite `teamPage`**

Replace `function teamPage(id) { ... }` with:

```js
  function teamPage(id, next) {
    const t = TEAMS[id];
    if (!t) return notFound();
    next = !!(next && ahead());                     // no current next-week capture → This week
    const rank = SEASON.standings.indexOf(t) + 1;
    const p = t.profile || { audit: [], moves: [], weak_spot: null };
    const onCoach = !!coachFor(id, next);
    return `
      <div class="crumbs"><a href="${onCoach ? coachUrl(next, null) : '#standings'}">${onCoach ? 'Coach' : 'Standings'}</a><span>›</span><span>${esc(t.manager)}</span></div>
      ${onCoach ? teamSwitch(id, next) : ''}
      <div class="page-head">
        <div class="kicker">${esc(t.team_name)}</div>
        <h1>${esc(t.manager)}</h1>
      </div>
      <div class="stat-tiles">
        <div class="tile"><div class="label">Record</div><div class="value">${record(t)}</div><div class="sub">${ordinal(rank)} place</div></div>
        <div class="tile"><div class="label">Average score</div><div class="value">${f1(t.avg)}</div><div class="sub">${f2(t.points_for)} total</div></div>
        <div class="tile"><div class="label">Best week</div><div class="value">${t.best ? f1(t.best.points) : '–'}</div><div class="sub">${t.best ? `Week ${t.best.week}` : ''}</div></div>
        <div class="tile"><div class="label">Vs. everyone</div><div class="value">${t.all_play_w}–${t.all_play_l}</div><div class="sub">if she played all 7 teams weekly</div></div>
        <div class="tile"><div class="label">Points benched</div><div class="value">${f1(t.bench_left)}</div><div class="sub">season total</div></div>
      </div>

      ${thisWeekSection(id, next)}
      ${auditSection(p)}
      ${suggestionsSection(id, next)}
      ${movesSection(p)}

      ${t.weekly.length ? `
      <section>
        ${secHead('board', 'Week by week')}
        <div class="std-card table-scroll">
          <table class="std">
            <thead><tr><th>Week</th><th>Opponent</th><th class="r">Score</th><th class="r">Result</th><th class="r" title="Where her score ranked among all 8 teams that week">Week rank</th><th class="r">Benched</th></tr></thead>
            <tbody>${t.weekly.map((g) => `
              <tr>
                <td><a href="#week-${g.week}.game-${g.game_key}" style="font-weight:700;text-decoration:none;color:var(--accent)">Week ${g.week}</a></td>
                <td class="mgr"><a href="#team-${g.opponent_id}">${esc(g.opponent)}</a></td>
                <td class="r">${f2(g.points)} – ${f2(g.opponent_points)}</td>
                <td class="r"><span class="res ${g.result}">${g.result}</span></td>
                <td class="r">${g.score_rank} of 8</td>
                <td class="r">${f2(g.points_left)}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </section>` : ''}

      <section>
        ${secHead('ball', 'Her awards')}
        ${t.awards.length ? `<ul class="decided">${t.awards.map((a) => `<li><span class="tag ${KIND[a.kind].tag}">${KIND[a.kind].label}</span><span><a href="#week-${a.week}.awards" style="font-weight:700;text-decoration:none">Week ${a.week}</a> · ${esc(a.title)}</span></li>`).join('')}</ul>`
          : '<p class="sec-sub">No awards yet. Give it time.</p>'}
      </section>`;
  }
```

- [ ] **Step 5: Router + live refresh**

In `route()`, delete the two `coach-next-(\d+)` / `coach-(\d+)` lines and the old `team-(\d+)` line, and insert these two lines directly after the `coach-next` grid line (so they run **before** the `!WEEKS.length` gates):

```js
    else if ((m = /^coach(-next)?-(\d+)$/.exec(h))) { location.replace(`#team-${m[2]}${m[1] ? '.next' : ''}`); return; }
    else if ((m = /^team-(\d+)(\.next)?$/.exec(h))) { html = teamPage(Number(m[1]), !!m[2]); nav = coachFor(Number(m[1]), false) ? 'coach' : 'standings'; }
```

In `refreshLive()`, change the re-render condition to:

```js
      if (h.startsWith('live') || h.startsWith('coach') || h.startsWith('team-') || h === '') route();
```

- [ ] **Step 6: Build and check in the browser pane**

Run: `python3 site/build.py && python3 -m http.server 8765 --directory site/dist/web`
(run in the background). Then, in the built-in browser at phone width (`resize_window` preset `mobile`), check:
1. `http://localhost:8765/#team-6` renders header, tiles, "This week" (one-line fallback, since every captured week is recapped), audit with 3 cards, "No new ideas today", moves list, week by week, awards.
2. `#team-6.next` renders the same as `#team-6` (no next-week capture), not "Fumble" (Review Focus 1).
3. `#coach-6` → URL becomes `#team-6`; `#coach-next-6` → `#team-6.next`.
4. `read_console_messages` with `onlyErrors: true` returns nothing.
5. Preseason check (Review Focus 5): render with no recaps into the session scratchpad (`$SCRATCH` = the scratchpad directory from the system prompt): `python3 -c "import sys; sys.path.insert(0,'site'); import build; rw,c,a,fp=build.load_inputs(2026); html,_=build.render([],c,False,a,fp); open(sys.argv[1],'w').write(build.standalone(html))" "$SCRATCH/preseason/index.html"` (create the folder first), serve it with a second `http.server` on port 8766, and confirm `#coach-6` lands on `#team-6` showing "The coach needs one finished week…" and a This week section for Week 3.
Stop the server(s) afterwards and reset the viewport with preset `desktop`.

- [ ] **Step 7: Commit**

```bash
git add site/template.html
git commit -m "Team profile page absorbs the per-team Coach page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Checks, CI, docs, and coach-daily's contract

**Files:**
- Modify: `scripts/check.py`, `.github/workflows/checks.yml`, `docs/architecture.md`, `CLAUDE.md`, `.claude/skills/coach-daily/SKILL.md`

**Interfaces:**
- Consumes: `build.site_data`, `build.load_inputs`.
- Produces: `check_team_profiles(errors: list) -> None` in `scripts/check.py`.

- [ ] **Step 1: Write the failing check**

In `scripts/check.py`, add above `main()`:

```python
def check_team_profiles(errors):
    """Every team on both builds has a profile, and every audit card is fully formed."""
    sys.path.insert(0, str(ROOT / "site"))
    import build  # noqa: E402  (site/build.py; imported late so a broken build fails here, not at import)
    recap_weeks, captured, ahead, fp = build.load_inputs(build.LEAGUE["season"])
    for preview in (False, True):
        data, _ = build.site_data(recap_weeks, captured, preview=preview, ahead=ahead, fp=fp)
        for s in data["season"]["standings"]:
            prof = s.get("profile")
            if not isinstance(prof, dict):
                errors.append(f"team {s['team_id']}: no profile (preview={preview})")
                continue
            for c in prof.get("audit", []):
                for k in ("key", "stat", "title", "text"):
                    if not (isinstance(c.get(k), str) and c[k].strip()):
                        errors.append(f"team {s['team_id']}: audit card {c.get('kind')} missing {k}")
```

and call it in `main()` right after `check_scoring_rows(errors)`:

```python
    check_team_profiles(errors)
```

- [ ] **Step 2: Run the check**

Run: `python3 scripts/check.py`
Expected: `ok: N tracked files checked`. (Per project memory, `check.py` scans only tracked files, and every new file here is already committed by Tasks 1–7.)

- [ ] **Step 3: CI**

In `.github/workflows/checks.yml`, after the `tests.test_coach_written` line add:

```yaml
      - run: python -m unittest tests.test_team_profile -v
```

- [ ] **Step 4: Docs**

`docs/architecture.md`, `## Coach page` section: replace its first bullet with:

```markdown
- A league-wide grid at `#coach` / `#coach-next`, one card per team. Each team's own week lives on her
  **team profile** (`#team-<id>`, `#team-<id>.next` for next week); the old `#coach-<id>` and
  `#coach-next-<id>` links redirect there. The week sections disappear once the live week's recap is
  published; the rest of the profile stays all season. The browser remembers the last team opened.
```

and append a new section after the Coach page section:

```markdown
## Team profile

`#team-<id>`: header and season tiles, this week's to-dos and lineup (above), the **coach's audit**,
roster ideas ("Worth a look"), her **recent moves**, week by week, and awards.

- **Audit** (`site/team_profile.py`, from recapped weeks only): Lineup IQ (`lineup:<band>:<benched id>`),
  Position strength (`pos:<best>:<worst>`; the worst group is her `weak_spot`) and Projection vs reality
  (`proj:<over|under>:<top id>:<bottom id>`). The A–D band exists only in the key. `coach-daily` writes copy
  per key into `latest.json`'s top-level `audit`; it applies on key match alone, with no 36-hour gate,
  since the key already describes finished weeks.
- **Roster ideas** whose optional `pos` equals her `weak_spot` get a "fills your weak spot" sticker.
- **Moves**: adds, drops and trades from every captured week (the live week included), newest first.
```

`CLAUDE.md`, `## Layout`: in the `scripts/` line leave as is; add a line after the `site/` bullet:

```markdown
- `site/team_profile.py`: the team profile's audit cards (and their keys) and roster moves; pure functions shared by `site/build.py` and `scripts/coach_brief.py`
```

and in the `FantasyPros daily snapshot` bullet, after "keyed by situation, see `docs/architecture.md`)", add: "and, top level, each team's written season-audit copy (`audit`, keyed by audit key)".

`.claude/skills/coach-daily/SKILL.md`:
- Step 5: add a paragraph: "The brief (Step 5b) names each team's `weak_spot`, her lowest-ranked lineup group. When a real waiver or trade option exists at that group, prefer it, and set `pos` (`QB`, `RB`, `WR`, `TE`, `FLEX`, `DST` or `K`) on every waiver and trade card. Never invent an option to fill a weak spot."
- Step 5b: add: "The brief's top-level `audit` block lists every team's three season-audit cards with their `key`, `stat` and computed wording. Write one `{title, text}` per key, dial "Coach cards": advice first, one line of personality. Roast the lineup call, never the manager. No decimals or percentages; the stat pill carries the numbers. The brief prints the audit even with no live week."
- Step 5c: add "including the audit copy" to the voice-gate sentence.
- Step 6 JSON example: add a sibling of `"weeks"`: `"audit": { "<team_id>": { "<audit key from the brief>": {"title": "...", "text": "..."} } }`, and `"pos": "TE"` to the waiver-card example if one is shown.

- [ ] **Step 5: Run everything**

Run: `python3 -m unittest tests.test_guard_bash tests.test_check_recaps tests.test_coach_written tests.test_team_profile -v && python3 scripts/check.py`
Expected: all OK

- [ ] **Step 6: Commit**

```bash
git add scripts/check.py .github/workflows/checks.yml docs/architecture.md CLAUDE.md .claude/skills/coach-daily/SKILL.md
git commit -m "Checks, CI and docs for the team profile; coach-daily writes audit copy

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Review, preview, PR

**Files:** none new (fixes land in whichever file a reviewer flags).

- [ ] **Step 1: Voice check.** Spawn `voice-check` (Agent tool, `subagent_type: voice-check`) on every new user-facing string: `LINEUP_TITLE`, the Lineup IQ/Position/Projection computed texts in `site/team_profile.py`, and the empty states in `site/template.html` ("Nothing to fix until…", "The coach needs one finished week…", "No new ideas today.", "No adds, drops or trades yet. Loyal to a fault.", "Worth a look" sub). Apply its rewrites, re-run `python3 -m unittest tests.test_team_profile -v` (a rewrite can break an `assertIn`), commit.
- [ ] **Step 2: Code review.** Spawn `code-reviewer` on `git diff origin/main...HEAD`. Fix confirmed findings, re-run Task 8 Step 5, commit.
- [ ] **Step 3: Push and open the PR.** `git push -u origin team-profile-design`, then `gh pr create --base main --title "Team profile page: this week, season audit, suggestions and moves" --body "<summary, test plan>\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"`. Bind it with the ccd_pr tools. Branch pushes get an automatic Vercel preview (PR #78); share that URL with Maya. Nothing merges without her approval of the preview.
