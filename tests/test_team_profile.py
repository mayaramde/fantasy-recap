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
