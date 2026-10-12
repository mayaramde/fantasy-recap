#!/usr/bin/env python3
"""Tests for the worst-performances list in site/build.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
import build  # noqa: E402


def team(tid, opp, pts, proj, starters=(), result="W"):
    return {"team_id": tid, "opponent_id": opp, "points": pts, "projected": proj, "result": result,
            "manager": f"M{tid}", "starters": list(starters)}


def starter(name, pts, proj, state=None):
    return {"player_id": 7, "logo": "L", "team": "DET", "name": name, "pos": "WR", "slot": "WR", "points": pts, "projected": proj, "game_state": state}


class Worst(unittest.TestCase):
    def test_live_week_skips_games_not_final(self):
        t = team(1, 2, 0, 0, [starter("Done", 2, 15, "post"), starter("Playing", 0, 20, "in"),
                               starter("Fine", 20, 10, "post")])
        got = build.worst_performances({"complete": False, "teams": [t]})
        self.assertEqual([p["name"] for p in got], ["Done"])
        self.assertEqual(got[0]["short"], 13.0)

    def test_starter_who_did_not_play_is_not_a_bust(self):
        ghost = dict(starter("Ghost", 0, 12), played=False)
        t = team(1, 2, 0, 0, [ghost, starter("Real", 3, 10)])
        got = build.worst_performances({"complete": True, "teams": [t]})
        self.assertEqual([p["name"] for p in got], ["Real"])

    def test_final_week_counts_everyone_sorted(self):
        t = team(1, 2, 0, 0, [starter("A", 5, 10), starter("B", 1, 14), starter("C", 9, 8)])
        got = build.worst_performances({"complete": True, "teams": [t]})
        self.assertEqual([p["name"] for p in got], ["B", "A"])


if __name__ == "__main__":
    unittest.main()
