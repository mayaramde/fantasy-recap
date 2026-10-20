#!/usr/bin/env python3
"""Teams with the same record share a rank in season_payload()'s rank history (1, 1, 3...), the way
ESPN's table shows them, while the standings rows stay in tiebreaker order (wins, then points scored)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
import build  # noqa: E402

SEASON_DIR = ROOT / "data" / str(build.LEAGUE["season"])


def facts(week):
    return json.loads((SEASON_DIR / f"week-{week:02d}" / "facts.json").read_text())


def rank_of(season, manager, week):
    team = next(s for s in season["standings"] if s["manager"] == manager)
    return next(r["rank"] for r in team["rank_history"] if r["week"] == week)


@unittest.skipUnless((SEASON_DIR / "week-06" / "facts.json").exists(), "needs the Week 6 capture")
class SharedRanks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.season = build.season_payload([facts(w) for w in range(1, 7)],
                                       [{"week": w, **{k: [] for k in build.AWARD_KEYS}} for w in range(1, 7)])

    def test_week_six_leaders_are_level_on_record_and_share_first(self):
        # Kyra and Maya are both 5-1 after Week 6
        self.assertEqual(rank_of(self.season, "Kyra", 6), 1)
        self.assertEqual(rank_of(self.season, "Maya", 6), 1)

    def test_the_next_team_skips_the_shared_spot(self):
        # Amie is 4-2, third behind the two 5-1 teams, not second
        self.assertEqual(rank_of(self.season, "Amie", 6), 3)

    def test_rows_stay_in_tiebreaker_order(self):
        order = [s["manager"] for s in self.season["standings"]]
        self.assertEqual(order[:2], ["Kyra", "Maya"])   # Kyra has scored more points

    def test_a_three_way_tie_shares_one_rank_and_the_next_team_skips_two_spots(self):
        # Tara, Samantha and Maddie are all 2-4 after Week 6, then Cambri at 1-5
        for manager in ("Tara", "Samantha", "Maddie"):
            self.assertEqual(rank_of(self.season, manager, 6), 5)
        self.assertEqual(rank_of(self.season, "Cambri", 6), 8)

    def test_week_one_ranks_come_in_two_shared_groups(self):
        ranks = sorted(rank_of(self.season, s["manager"], 1) for s in self.season["standings"])
        # Week 1 had four winners and four losers, so ranks come in two shared groups
        self.assertEqual(ranks, [1, 1, 1, 1, 5, 5, 5, 5])


if __name__ == "__main__":
    unittest.main()
