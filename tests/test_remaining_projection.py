#!/usr/bin/env python3
"""remaining_projection: what ESPN projects a lineup still to score, behind the Live page's 'still to come' meter."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import analyze  # noqa: E402


def p(state, proj, pts=0.0, played=False):
    return {"game_state": state, "projected": proj, "points": pts, "played": played}


class RemainingProjection(unittest.TestCase):
    def test_games_ahead_count_in_full_games_over_count_nothing(self):
        self.assertEqual(analyze.remaining_projection([p("pre", 12.5), p("pre", 8.0), p("post", 20.0, 25.0, True)]), 20.5)

    def test_mid_game_counts_what_is_left_of_his_projection_never_below_zero(self):
        self.assertEqual(analyze.remaining_projection([p("in", 18.0, 6.5, True), p("in", 10.0, 14.0, True)]), 11.5)

    def test_missing_projection_is_zero(self):
        self.assertEqual(analyze.remaining_projection([p("pre", None), p("in", None, 3.0, True)]), 0)

    def test_without_game_states_an_unplayed_starter_is_still_to_come(self):
        self.assertEqual(analyze.remaining_projection([p(None, 9.0, 0, False), p(None, 7.0, 7.4, True)]), 9.0)

    def test_nobody_left(self):
        self.assertEqual(analyze.remaining_projection([]), 0)


if __name__ == "__main__":
    unittest.main()
