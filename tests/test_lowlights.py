#!/usr/bin/env python3
"""Tests for the upsets and worst-performances lists in site/build.py."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
import build  # noqa: E402


def team(tid, opp, pts, proj, starters=(), result="W"):
    return {"team_id": tid, "opponent_id": opp, "points": pts, "projected": proj, "result": result,
            "manager": f"M{tid}", "starters": list(starters)}


def starter(name, pts, proj, state=None):
    return {"name": name, "pos": "WR", "slot": "WR", "points": pts, "projected": proj, "game_state": state}


class Upsets(unittest.TestCase):
    def facts(self, complete=True):
        return {"complete": complete, "teams": [
            team(1, 2, 100, 90), team(2, 1, 80, 110, result="L"),      # underdog 1 won by 20 on paper
            team(3, 4, 120, 130), team(4, 3, 90, 100, result="L"),     # favorite held
        ]}

    def test_underdog_win_only(self):
        got = build.upsets(self.facts())
        self.assertEqual([(u["winner"], u["loser"], u["gap"]) for u in got], [("M1", "M2", 20.0)])

    def test_unfinished_week_has_none(self):
        self.assertEqual(build.upsets(self.facts(complete=False)), [])


class Worst(unittest.TestCase):
    def test_live_week_skips_games_not_final(self):
        t = team(1, 2, 0, 0, [starter("Done", 2, 15, "post"), starter("Playing", 0, 20, "in"),
                               starter("Fine", 20, 10, "post")])
        got = build.worst_performances({"complete": False, "teams": [t]})
        self.assertEqual([p["name"] for p in got], ["Done"])
        self.assertEqual(got[0]["short"], 13.0)

    def test_final_week_counts_everyone_sorted(self):
        t = team(1, 2, 0, 0, [starter("A", 5, 10), starter("B", 1, 14), starter("C", 9, 8)])
        got = build.worst_performances({"complete": True, "teams": [t]})
        self.assertEqual([p["name"] for p in got], ["B", "A"])


if __name__ == "__main__":
    unittest.main()
