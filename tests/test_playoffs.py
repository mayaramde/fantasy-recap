#!/usr/bin/env python3
"""Tests for site/playoffs.py: the Standings page's playoff odds and projected bracket.

Hand-built fixtures only. Team t scores 160 - 10*t + week every week, so a lower id always wins,
and three weeks of this rotation give a table checkable by eye:

    3-0: team 1 (456 pts), team 5 (336)   2-1: team 2 (426), team 6 (306)
    1-2: team 3 (396), team 7 (276)       0-3: team 4 (366), team 8 (246)

so seeds 1-8 are teams 1, 5, 2, 6, 3, 7, 4, 8. The league's format (top four, no byes, a two-week
final) puts teams 1, 5, 2 and 6 in; the six-team, two-bye variant still covers byes.
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
LEAGUE = {"playoffs": {"teams": 4, "byes": 0, "regular_season_weeks": 14, "first_round_week": 15,
                       "championship_weeks": 2, "tiebreaker": "points_for", "reseed": False}}
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
        self.assertAlmostEqual(sum(t["playoff"] for t in self.r["teams"]), 4, places=3)

    def test_no_byes(self):
        self.assertEqual(sum(t["bye"] for t in self.r["teams"]), 0)
        self.assertNotIn("Bye race", [t["label"] for t in self.r["teams"]])

    def test_config_reads_the_league_format(self):
        cfg = self.r["config"]
        self.assertEqual((cfg["teams"], cfg["byes"], cfg["championship_weeks"]), (4, 0, 2))

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

    def test_now_cut_is_current_top_four(self):
        self.assertEqual(self.r["now_cut"], TABLE[:4])
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
    """The league's bracket: 1v4 and 2v3 in Week 15, then a final totaled over Weeks 16 and 17."""
    @classmethod
    def setUpClass(cls):
        cls.r = po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=SIMS)
        cls.b = cls.r["bracket"]

    def seeds(self, game):
        return [t["seed"] for t in game["teams"]]

    def winner_seed(self, game):
        return next(t["seed"] for t in game["teams"] if t["team_id"] == game["favorite"])

    def test_semis_are_one_v_four_and_two_v_three_in_week_fifteen(self):
        semis = self.b["rounds"][0]
        self.assertEqual(len(self.b["rounds"]), 2)
        self.assertEqual((semis["week"], semis["weeks"]), (15, 1))
        self.assertEqual([self.seeds(g) for g in semis["games"]], [[1, 4], [2, 3]])

    def test_final_spans_weeks_sixteen_and_seventeen(self):
        final = self.b["rounds"][-1]
        self.assertEqual((final["week"], final["weeks"]), (16, 2))
        self.assertEqual(final["games"], [self.b["final"]])
        self.assertEqual(self.seeds(self.b["final"]), [self.winner_seed(g) for g in self.b["rounds"][0]["games"]])
        self.assertEqual(self.b["champion"], self.b["final"]["favorite"])

    def test_two_week_final_is_more_decisive_than_one(self):
        one = po.build(standings([1, 2, 3]), [1, 2, 3], league(championship_weeks=1), n_sims=SIMS)["bracket"]
        self.assertEqual(one["rounds"][-1]["weeks"], 1)
        self.assertGreater(self.b["final"]["win_prob"], one["final"]["win_prob"])

    def test_teams_follow_projected_seeds(self):
        seed_of = {t["team_id"]: t["proj_seed"] for t in self.r["teams"]}
        for rnd in self.b["rounds"]:
            for g in rnd["games"]:
                for t in g["teams"]:
                    self.assertEqual(seed_of[t["team_id"]], t["seed"])
                self.assertGreaterEqual(g["win_prob"], 0.5)
                self.assertLessEqual(g["win_prob"], 1)


class WhatIfTest(unittest.TestCase):
    """The what-if mode's data: every semifinal and final path, priced by the same model as the chalk bracket."""
    @classmethod
    def setUpClass(cls):
        cls.r = po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=SIMS)
        cls.b = cls.r["bracket"]
        cls.w = cls.b["what_if"]

    def test_eight_scenarios_cover_every_outcome(self):
        self.assertEqual(len(self.w["scenarios"]), 8)
        self.assertEqual(len({(tuple(s["semis"]), s["champion"]) for s in self.w["scenarios"]}), 8)
        self.assertAlmostEqual(sum(s["p"] for s in self.w["scenarios"]), 1, places=4)

    def test_four_possible_finals_each_sum_to_one(self):
        self.assertEqual(len(self.w["finals"]), 4)
        for f in self.w["finals"]:
            self.assertAlmostEqual(sum(f["p"].values()), 1, places=3)
            self.assertFalse(f["est"])

    def test_semis_are_one_v_four_and_two_v_three(self):
        self.assertEqual([[t["seed"] for t in g["teams"]] for g in self.w["semis"]], [[1, 4], [2, 3]])
        for g in self.w["semis"]:
            self.assertAlmostEqual(sum(t["p"] for t in g["teams"]), 1, places=3)

    def test_chalk_path_matches_the_chalk_bracket(self):
        semi_favs = [g["favorite"] for g in self.b["rounds"][0]["games"]]
        chalk = next(s for s in self.w["scenarios"] if s["semis"] == semi_favs and s["champion"] == self.b["champion"])
        win = lambda g: g["win_prob"]  # noqa: E731
        expected = win(self.b["rounds"][0]["games"][0]) * win(self.b["rounds"][0]["games"][1]) * win(self.b["final"])
        self.assertAlmostEqual(chalk["p"], expected, places=2)

    def test_scenario_is_semis_times_final(self):
        p_semi = {t["team_id"]: t["p"] for g in self.w["semis"] for t in g["teams"]}
        for s in self.w["scenarios"]:
            a, b = s["semis"]
            final = next(f for f in self.w["finals"] if sorted(f["teams"]) == sorted(s["semis"]))
            self.assertAlmostEqual(s["p"], p_semi[a] * p_semi[b] * final["p"][str(s["champion"])], places=3)
            self.assertIn(s["champion"], s["semis"])

    def test_other_formats_have_no_what_if(self):
        six = po.build(standings([1, 2, 3]), [1, 2, 3], league(teams=6), n_sims=SIMS)["bracket"]
        self.assertNotIn("what_if", six)


class LadderTest(unittest.TestCase):
    """The consolation ladder: seeds 5 to 8 play 5v8 and 6v7, then winners meet for 5th, losers for 7th."""
    @classmethod
    def setUpClass(cls):
        cls.r = po.build(standings([1, 2, 3]), [1, 2, 3], league(consolation_ladder=True), n_sims=SIMS)
        cls.l = cls.r["ladder"]
        cls.w = cls.l["what_if"]

    def test_round_one_is_five_v_eight_and_six_v_seven(self):
        r1 = self.l["rounds"][0]
        self.assertEqual((r1["week"], r1["weeks"]), (15, 1))
        self.assertEqual([[t["seed"] for t in g["teams"]] for g in r1["games"]], [[5, 8], [6, 7]])

    def test_ladder_round_spans_the_championship_weeks_and_places_the_losers_too(self):
        final = self.l["rounds"][1]
        self.assertEqual((final["week"], final["weeks"]), (16, 2))
        self.assertEqual([g["places"] for g in final["games"]], [[5, 6], [7, 8]])
        top, bottom = final["games"]
        r1_favs = [g["favorite"] for g in self.l["rounds"][0]["games"]]
        self.assertEqual({t["team_id"] for t in top["teams"]}, set(r1_favs))
        self.assertFalse({t["team_id"] for t in bottom["teams"]} & set(r1_favs))

    def test_chalk_places_run_fifth_to_eighth_with_no_repeats(self):
        self.assertEqual([p["place"] for p in self.l["places"]], [5, 6, 7, 8])
        self.assertEqual(len({p["team_id"] for p in self.l["places"]}), 4)
        out = [t["team_id"] for t in sorted(self.r["teams"], key=lambda t: t["proj_seed"])[4:]]
        self.assertEqual(sorted(p["team_id"] for p in self.l["places"]), sorted(out))

    def test_sixteen_scenarios_cover_every_outcome(self):
        self.assertEqual(len(self.w["scenarios"]), 16)
        self.assertEqual(len({(tuple(s["r1"]), s["top"], s["bottom"]) for s in self.w["scenarios"]}), 16)
        self.assertAlmostEqual(sum(s["p"] for s in self.w["scenarios"]), 1, places=3)

    def test_four_possible_ladder_games_each_sum_to_one(self):
        self.assertEqual(len(self.w["finals"]), 4)
        for f in self.w["finals"]:
            self.assertAlmostEqual(sum(f["p"].values()), 1, places=3)

    def test_chalk_scenario_is_the_product_of_the_chalk_games(self):
        r1, (top, bottom) = self.l["rounds"][0]["games"], self.l["rounds"][1]["games"]
        chalk = next(s for s in self.w["scenarios"] if s["r1"] == [g["favorite"] for g in r1]
                     and s["top"] == top["favorite"] and s["bottom"] == bottom["favorite"])
        expected = r1[0]["win_prob"] * r1[1]["win_prob"] * top["win_prob"] * bottom["win_prob"]
        self.assertAlmostEqual(chalk["p"], expected, places=2)

    def test_no_ladder_when_the_league_has_none_or_the_field_is_not_four(self):
        self.assertIsNone(po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=SIMS)["ladder"])
        six = po.build(standings([1, 2, 3]), [1, 2, 3], league(teams=6, consolation_ladder=True), n_sims=SIMS)
        self.assertIsNone(six["ladder"])


class SixTeamBracketTest(unittest.TestCase):
    """A six-team, two-bye field still works, so a format change is a league.json edit."""
    @classmethod
    def setUpClass(cls):
        cls.r = po.build(standings([1, 2, 3]), [1, 2, 3], league(teams=6, byes=2, championship_weeks=1), n_sims=SIMS)
        cls.b = cls.r["bracket"]

    def seeds(self, game):
        return [t["seed"] for t in game["teams"]]

    def winner_seed(self, game):
        return next(t["seed"] for t in game["teams"] if t["team_id"] == game["favorite"])

    def test_round_one_is_four_v_five_and_three_v_six(self):
        self.assertEqual([self.seeds(g) for g in self.b["rounds"][0]["games"]], [[4, 5], [3, 6]])
        self.assertEqual([r["week"] for r in self.b["rounds"]], [15, 16, 17])

    def test_top_two_seeds_skip_round_one_and_meet_the_right_winners(self):
        r1_45, r1_36 = self.b["rounds"][0]["games"]
        semis = self.b["rounds"][1]["games"]
        self.assertEqual(self.seeds(semis[0]), [1, self.winner_seed(r1_45)])
        self.assertEqual(self.seeds(semis[1]), [2, self.winner_seed(r1_36)])

    def test_odds_sum_to_slots(self):
        self.assertAlmostEqual(sum(t["playoff"] for t in self.r["teams"]), 6, places=3)
        self.assertAlmostEqual(sum(t["bye"] for t in self.r["teams"]), 2, places=3)
        self.assertAlmostEqual(sum(t["title"] for t in self.r["teams"]), 1, places=3)


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
            self.assertEqual(t["playoff"], 1.0 if rank < 4 else 0.0)
            self.assertEqual(t["bye"], 0.0)
            self.assertEqual(t["seed_dist"], [1.0 if k == rank else 0.0 for k in range(8)])
            self.assertEqual(t["proj_seed"], rank + 1)
            self.assertEqual(t["label"], "In" if rank < 4 else "Out")
        self.assertEqual(sum(t["title"] for t in r["teams"] if t["team_id"] in TABLE[4:]), 0)

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
            self.assertAlmostEqual(sum(t["playoff"] for t in r["teams"]), 4, places=3)

    def test_string_week_keys_are_accepted(self):
        sched = {str(w): PAIRINGS[(w - 1) % 3 + 1] for w in range(4, 15)}
        self.assertTrue(po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, schedule=sched, n_sims=200)["real_schedule"])

    def test_no_weeks_played_returns_none(self):
        self.assertIsNone(po.build(standings([]), [], LEAGUE))

    def test_missing_config_defaults_to_the_league_format(self):
        cfg = po._config({})
        self.assertEqual((cfg["teams"], cfg["byes"], cfg["championship_weeks"]), (4, 0, 1))
        self.assertEqual(po._config({"playoffs": {"championship_weeks": 0}})["championship_weeks"], 1)

    def test_byes_follow_the_field_size(self):
        self.assertEqual(po._config({"playoffs": {"teams": 4, "byes": 2}})["byes"], 0)
        self.assertEqual(po._config({"playoffs": {"teams": 6, "byes": 0}})["byes"], 2)
        self.assertEqual(po._config({"playoffs": {"teams": 0}})["teams"], 2)

    def test_week_one_has_no_trend(self):
        r = po.build(standings([1]), [1], LEAGUE, n_sims=500)
        self.assertTrue(all(t["trend"] is None for t in r["teams"]))

    def test_labels_come_from_odds(self):
        label = po._label
        self.assertEqual(label({"playoff": 0.996, "bye": 0.9}, 5, True), "Near lock")
        self.assertEqual(label({"playoff": 0.97, "bye": 0.0}, 5, True), "Comfortable")
        self.assertEqual(label({"playoff": 0.97, "bye": 0.6}, 5, True), "Bye race")
        self.assertEqual(label({"playoff": 0.85, "bye": 0.1}, 5, True), "Comfortable")
        self.assertEqual(label({"playoff": 0.5, "bye": 0.0}, 5, False), "Bubble")
        self.assertEqual(label({"playoff": 0.2, "bye": 0.0}, 5, False), "Long shot")
        self.assertEqual(label({"playoff": 0.005, "bye": 0.0}, 5, False), "Near out")
        self.assertEqual(label({"playoff": 1.0, "bye": 1.0}, 0, True), "In")
        for t in by_team(po.build(standings([1, 2, 3]), [1, 2, 3], LEAGUE, n_sims=500)).values():
            self.assertNotIn(t["label"], ("Locked in", "Clinched"))


class StakesTest(unittest.TestCase):
    """Week 4 of a four-week season, on the three-week table in this file's docstring. Teams 1 and 5
    (3-0) are in whatever happens and 4 and 8 (0-3) are out. Team 2 (2-1) has the points to survive a
    loss and team 7 can't catch up, so 3 v 6 is the only game with a playoff spot riding on it: the
    winner takes the fourth seed."""
    GAMES = [(1, 8), (4, 5), (2, 7), (3, 6)]

    @classmethod
    def setUpClass(cls):
        cls.league = league(regular_season_weeks=4, first_round_week=5)
        cls.out = po.stakes(standings([1, 2, 3]), [1, 2, 3], cls.league, 4, cls.GAMES, SIMS)
        cls.rows = {t["team_id"]: t for g in cls.out["games"] for t in g["teams"]}

    def test_every_team_has_a_row(self):
        self.assertEqual(sorted(self.rows), IDS)
        self.assertEqual(sorted(g["key"] for g in self.out["games"]), ["1-8", "2-7", "3-6", "4-5"])

    def test_a_win_never_hurts(self):
        for t in self.rows.values():
            self.assertGreaterEqual(t["win"], t["lose"], t)

    def test_decided_teams_do_not_swing(self):
        for t in (1, 5, 2, 7, 4, 8):
            self.assertEqual(self.rows[t]["swing"], 0.0, t)
        self.assertEqual((self.rows[1]["win"], self.rows[8]["lose"]), (1.0, 0.0))

    def test_a_bubble_game_swings(self):
        self.assertEqual(self.rows[3]["swing"], 1.0)
        self.assertEqual(self.rows[6]["swing"], 1.0)

    def test_the_two_sides_of_a_game_split_the_wins(self):
        for g in self.out["games"]:
            a, b = g["teams"]
            self.assertAlmostEqual(a["p_win"] + b["p_win"], 1.0, places=3)

    def test_win_and_lose_average_back_to_todays_odds(self):
        today = by_team(po.build(standings([1, 2, 3]), [1, 2, 3], self.league, {4: self.GAMES}, SIMS))
        for i, t in self.rows.items():
            blended = t["p_win"] * t["win"] + (1 - t["p_win"]) * t["lose"]
            self.assertAlmostEqual(blended, today[i]["playoff"], delta=0.05, msg=i)

    def test_the_game_with_something_riding_on_it_leads(self):
        self.assertEqual(self.out["games"][0]["key"], "3-6")

    def test_deterministic_after_clearing_cache(self):
        po._CACHE.clear()
        self.assertEqual(po.stakes(standings([1, 2, 3]), [1, 2, 3], self.league, 4, self.GAMES, SIMS), self.out)

    def test_nothing_to_say_returns_empty(self):
        s = standings([1, 2, 3])
        self.assertEqual(po.stakes(s, [1, 2, 3], self.league, 3, self.GAMES, SIMS), {})         # already played
        self.assertEqual(po.stakes(s, [1, 2, 3], self.league, 5, self.GAMES, SIMS), {})         # a playoff week
        self.assertEqual(po.stakes(s, [1, 2], self.league, 4, self.GAMES, SIMS), {})            # week 3 unplayed
        self.assertEqual(po.stakes(s, [1, 2, 3], self.league, 4, self.GAMES[:3], SIMS), {})     # a game missing
        self.assertEqual(po.stakes(s, [], self.league, 1, self.GAMES, SIMS), {})                # nothing played

    def test_malformed_input_never_raises(self):
        for bad in (None, [], [{"team_id": 1}], "nope"):
            self.assertEqual(po.stakes(bad, [1, 2, 3], self.league, 4, self.GAMES, SIMS), {})
        self.assertEqual(po.stakes(standings([1, 2, 3]), [1, 2, 3], self.league, 4, None, SIMS), {})
        self.assertEqual(po.stakes(standings([1, 2, 3]), [1, 2, 3], self.league, 4, [(1,), "x"], SIMS), {})


if __name__ == "__main__":
    unittest.main()
