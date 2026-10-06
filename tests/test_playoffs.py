#!/usr/bin/env python3
"""Tests for site/playoffs.py: the Standings page's playoff odds and projected bracket.

Hand-built fixtures only. Team t scores 160 - 10*t + week every week, so a lower id always wins,
and three weeks of this rotation give a table checkable by eye:

    3-0: team 1 (456 pts), team 5 (336)   2-1: team 2 (426), team 6 (306)
    1-2: team 3 (396), team 7 (276)       0-3: team 4 (366), team 8 (246)

so seeds 1-6 are teams 1, 5, 2, 6, 3, 7, and teams 4 and 8 are out.
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
import playoffs as po  # noqa: E402

IDS = list(range(1, 9))
PAIRINGS = {
    1: [(1, 2), (3, 4), (5, 6), (7, 8)],
    2: [(1, 3), (2, 4), (5, 7), (6, 8)],
    3: [(1, 4), (2, 3), (5, 8), (6, 7)],
}
TABLE = [1, 5, 2, 6, 3, 7, 4, 8]
LEAGUE = {"playoffs": {"teams": 6, "byes": 2, "regular_season_weeks": 14, "first_round_week": 15,
                       "tiebreaker": "points_for", "reseed": False}}
SIMS = 2000


def points(team, week):
    return 160 - 10 * team + week


def standings(weeks):
    """season_payload()-shaped rows for the given weeks of PAIRINGS."""
    rows = {t: {"team_id": t, "wins": 0, "losses": 0, "ties": 0, "points_for": 0.0, "weekly": []} for t in IDS}
    for wk in weeks:
        for a, b in PAIRINGS[wk]:
            for me, opp in ((a, b), (b, a)):
                mine, theirs = points(me, wk), points(opp, wk)
                result = "W" if mine > theirs else "L" if mine < theirs else "T"
                r = rows[me]
                r["wins"] += result == "W"
                r["losses"] += result == "L"
                r["ties"] += result == "T"
                r["points_for"] += mine
                r["weekly"].append({"week": wk, "points": mine, "opponent_id": opp, "opponent_points": theirs,
                                    "result": result})
    return list(rows.values())


def league(**overrides):
    lg = copy.deepcopy(LEAGUE)
    lg["playoffs"].update(overrides)
    return lg


def by_team(result):
    return {t["team_id"]: t for t in result["teams"]}


class OddsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=SIMS)

    def test_playoff_odds_sum_to_slots(self):
        self.assertAlmostEqual(sum(t["playoff"] for t in self.r["teams"]), 6, places=3)

    def test_bye_odds_sum_to_two(self):
        self.assertAlmostEqual(sum(t["bye"] for t in self.r["teams"]), 2, places=3)

    def test_title_odds_sum_to_one(self):
        self.assertAlmostEqual(sum(t["title"] for t in self.r["teams"]), 1, places=3)

    def test_each_seed_distribution_sums_to_one(self):
        for t in self.r["teams"]:
            self.assertEqual(len(t["seed_dist"]), 8)
            self.assertAlmostEqual(sum(t["seed_dist"]), 1, places=3)

    def test_best_team_favored_over_worst(self):
        teams = by_team(self.r)
        self.assertGreater(teams[1]["playoff"], teams[8]["playoff"])
        self.assertGreater(teams[1]["title"], teams[8]["title"])
        self.assertLess(teams[1]["avg_seed"], teams[8]["avg_seed"])
        self.assertEqual(self.r["teams"][0]["team_id"], 1)
        self.assertEqual([t["proj_seed"] for t in self.r["teams"]], list(range(1, 9)))

    def test_now_cut_is_current_top_six(self):
        self.assertEqual(self.r["now_cut"], TABLE[:6])
        self.assertEqual(self.r["games_left"], 11)
        self.assertFalse(self.r["real_schedule"])

    def test_trend_after_week_one(self):
        self.assertTrue(all(t["trend"] is not None for t in self.r["teams"]))

    def test_deterministic_after_clearing_cache(self):
        po._CACHE.clear()
        again = po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=SIMS)
        self.assertEqual(again, self.r)

    def test_returned_result_is_a_copy(self):
        first = po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=SIMS)
        first["teams"][0]["playoff"] = -1
        self.assertEqual(po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=SIMS), self.r)


class BracketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=SIMS)
        cls.b = cls.r["bracket"]

    def seeds(self, game):
        return [t["seed"] for t in game["teams"]]

    def winner_seed(self, game):
        return next(t["seed"] for t in game["teams"] if t["team_id"] == game["favorite"])

    def test_round_one_is_three_v_six_and_four_v_five(self):
        self.assertEqual([self.seeds(g) for g in self.b["round1"]], [[3, 6], [4, 5]])

    def test_top_two_seeds_skip_round_one_and_meet_the_right_winners(self):
        r1_36, r1_45 = self.b["round1"]
        self.assertEqual(self.seeds(self.b["semis"][0]), [1, self.winner_seed(r1_45)])
        self.assertEqual(self.seeds(self.b["semis"][1]), [2, self.winner_seed(r1_36)])

    def test_favorites_advance_to_the_final_and_title(self):
        self.assertEqual([t["team_id"] for t in self.b["final"]["teams"]],
                         [g["favorite"] for g in self.b["semis"]])
        self.assertEqual(self.b["champion"], self.b["final"]["favorite"])

    def test_teams_follow_projected_seeds(self):
        seed_of = {t["team_id"]: t["proj_seed"] for t in self.r["teams"]}
        for g in self.b["round1"] + self.b["semis"] + [self.b["final"]]:
            for t in g["teams"]:
                self.assertEqual(seed_of[t["team_id"]], t["seed"])
            self.assertGreaterEqual(g["win_prob"], 0.5)
            self.assertLessEqual(g["win_prob"], 1)


class WinProbTest(unittest.TestCase):
    def test_symmetric(self):
        for a, b, s in ((120, 100, 25), (95.5, 131.2, 18), (110, 110, 35)):
            self.assertAlmostEqual(po.win_prob(a, b, s) + po.win_prob(b, a, s), 1, places=12)

    def test_even_and_ordered(self):
        self.assertEqual(po.win_prob(110, 110, 25), 0.5)
        self.assertGreater(po.win_prob(130, 100, 25), po.win_prob(115, 100, 25))
        self.assertGreater(po.win_prob(115, 100, 18), po.win_prob(115, 100, 35))


class EdgeCaseTest(unittest.TestCase):
    def test_finished_season_matches_the_table_exactly(self):
        r = po.build(standings([1, 2, 3]), [1, 2, 3], league(regular_season_weeks=3), n_sims=500)
        teams = by_team(r)
        self.assertEqual(r["games_left"], 0)
        for rank, tid in enumerate(TABLE):
            t = teams[tid]
            self.assertEqual(t["playoff"], 1.0 if rank < 6 else 0.0)
            self.assertEqual(t["bye"], 1.0 if rank < 2 else 0.0)
            self.assertEqual(t["seed_dist"], [1.0 if k == rank else 0.0 for k in range(8)])
            self.assertEqual(t["proj_seed"], rank + 1)
            self.assertEqual(t["label"], "In" if rank < 6 else "Out")
        self.assertEqual(sum(t["title"] for t in r["teams"] if t["team_id"] in (4, 8)), 0)

    def test_playoff_weeks_do_not_count_toward_seeding(self):
        # Week 3 played as if it were a playoff week: the table must be the 2-week one.
        r = po.build(standings([1, 2, 3]), [1, 2, 3], league(regular_season_weeks=2), n_sims=500)
        self.assertEqual(r["weeks_played"], [1, 2])
        two_weeks = po.build(standings([1, 2]), [1, 2], league(regular_season_weeks=2), n_sims=500)
        self.assertEqual(r["now_cut"], two_weeks["now_cut"])

    def test_supplied_schedule_sets_real_schedule(self):
        sched = {w: PAIRINGS[(w - 1) % 3 + 1] for w in range(4, 15)}
        r = po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, schedule=sched, n_sims=500)
        self.assertTrue(r["real_schedule"])
        partial = po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, schedule={4: PAIRINGS[1]}, n_sims=500)
        self.assertFalse(partial["real_schedule"])

    def test_bad_schedule_weeks_fall_back_to_random(self):
        good = {w: PAIRINGS[(w - 1) % 3 + 1] for w in range(4, 15)}
        for bad in ([(1, 99), (3, 4), (5, 6), (7, 8)], [(1, 2), (3, 4)], [(1, 1), (3, 4), (5, 6), (7, 8)]):
            r = po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, schedule={**good, 9: bad}, n_sims=200)
            self.assertFalse(r["real_schedule"])
            self.assertAlmostEqual(sum(t["playoff"] for t in r["teams"]), 6, places=3)

    def test_string_week_keys_are_accepted(self):
        sched = {str(w): PAIRINGS[(w - 1) % 3 + 1] for w in range(4, 15)}
        self.assertTrue(po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, schedule=sched, n_sims=200)["real_schedule"])

    def test_no_weeks_played_returns_none(self):
        self.assertIsNone(po.build(standings([]), [], LEAGUE))

    def test_four_team_config(self):
        r = po.build(standings([1, 2, 3]), [1, 2, 3], league(teams=4, byes=0), n_sims=SIMS)
        self.assertIsNone(r["bracket"])
        self.assertAlmostEqual(sum(t["playoff"] for t in r["teams"]), 4, places=3)
        self.assertAlmostEqual(sum(t["title"] for t in r["teams"]), 1, places=3)
        self.assertEqual(sum(t["bye"] for t in r["teams"]), 0)

    def test_week_one_has_no_trend(self):
        r = po.build(standings([1]), [1], LEAGUE, n_sims=500)
        self.assertTrue(all(t["trend"] is None for t in r["teams"]))

    def test_labels_come_from_odds(self):
        label = po._label
        self.assertEqual(label({"playoff": 0.996, "bye": 0.9}, 5, True), "Near lock")
        self.assertEqual(label({"playoff": 0.97, "bye": 0.6}, 5, True), "Bye race")
        self.assertEqual(label({"playoff": 0.85, "bye": 0.1}, 5, True), "Comfortable")
        self.assertEqual(label({"playoff": 0.5, "bye": 0.0}, 5, False), "Bubble")
        self.assertEqual(label({"playoff": 0.2, "bye": 0.0}, 5, False), "Long shot")
        self.assertEqual(label({"playoff": 0.005, "bye": 0.0}, 5, False), "Near out")
        self.assertEqual(label({"playoff": 1.0, "bye": 1.0}, 0, True), "In")
        for t in by_team(po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=500)).values():
            self.assertNotIn(t["label"], ("Locked in", "Clinched"))


if __name__ == "__main__":
    unittest.main()
