#!/usr/bin/env python3
"""Tests for scripts/check_recaps.py.

The number and structure checks are tested directly against fixtures under
tests/fixtures/, independent of the last-name check. The last-name tests are
separate and will report as skipped (not failed) until find_possible_last_names
is implemented (see the TODO(human) in scripts/check_recaps.py) — the rest of
this suite doesn't depend on it and should pass right now.
"""
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
import check_recaps  # noqa: E402


def load_fixture(name):
    """Returns (recap, facts, league) for a fixture directory under tests/fixtures/."""
    base = FIXTURES / name
    recap_path = next((base / "recaps" / "2099").glob("week-*.json"))
    recap = json.loads(recap_path.read_text())
    facts = json.loads((base / "data" / "2099" / "week-01" / "facts.json").read_text())
    league = json.loads((base / "league.json").read_text())
    return recap, facts, league


class NumbersTest(unittest.TestCase):
    def test_valid_recap_has_no_number_problems(self):
        recap, facts, _ = load_fixture("valid")
        numbers = set()
        check_recaps.collect_numbers(facts, numbers)
        problems = []
        check_recaps.check_numbers(recap, numbers, problems)
        self.assertEqual(problems, [])

    def test_invented_number_is_flagged(self):
        recap, facts, _ = load_fixture("bad_number")
        numbers = set()
        check_recaps.collect_numbers(facts, numbers)
        problems = []
        check_recaps.check_numbers(recap, numbers, problems)
        self.assertEqual(len(problems), 1)
        self.assertIn("999.99", problems[0])

    def test_small_integers_are_ignored(self):
        numbers = {1.0}  # deliberately sparse — "20" should not need to be sourced
        problems = []
        check_recaps.check_numbers(
            {"headline": "Week 20 was a good one", "dek": "", "matchups": {}}, numbers, problems)
        self.assertEqual(problems, [])

    def test_small_decimal_is_not_ignored(self):
        # 20 is exempt as a plain integer, but 20.0 was deliberately written with
        # a decimal point and must still be sourced.
        problems = []
        check_recaps.check_numbers(
            {"headline": "She scored exactly 20.0", "dek": "", "matchups": {}}, set(), problems)
        self.assertEqual(len(problems), 1)


class MatchupStructureTest(unittest.TestCase):
    def test_valid_recap_has_no_structure_problems(self):
        recap, facts, _ = load_fixture("valid")
        real_pairs = check_recaps.real_matchup_pairs(facts)
        problems = []
        check_recaps.check_matchup_structure(recap, real_pairs, problems)
        self.assertEqual(problems, [])

    def test_fake_pairing_is_flagged(self):
        recap, facts, _ = load_fixture("bad_structure")
        real_pairs = check_recaps.real_matchup_pairs(facts)
        problems = []
        check_recaps.check_matchup_structure(recap, real_pairs, problems)
        self.assertEqual(len(problems), 1)
        self.assertIn("1-3", problems[0])

    def test_malformed_key_is_flagged(self):
        problems = []
        check_recaps.check_matchup_structure({"matchups": {"not-a-pair": "x"}}, set(), problems)
        self.assertEqual(len(problems), 1)

    def test_high_low_swapped_is_flagged(self):
        problems = []
        check_recaps.check_matchup_structure({"matchups": {"5-2": "x"}}, {(2, 5)}, problems)
        self.assertEqual(len(problems), 1)


class AwardsTest(unittest.TestCase):
    ROSTER = {"Josh Allen", "Mike Evans"}

    def run_check(self, award, week=5, roster=ROSTER, section="game_balls"):
        recap = {"week": week, section: [dict({"manager": "Maya", "title": "A title", "stat": "49.6-pt win",
                                                "text": "Plain text."}, **award)]}
        problems = []
        check_recaps.check_awards(recap, roster, problems)
        return problems

    def test_good_award_passes(self):
        self.assertEqual(self.run_check({"emoji": "🍽️", "player": "Josh Allen"}), [])

    def test_zwj_sequence_and_flag_count_as_one_character(self):
        self.assertEqual(self.run_check({"emoji": "🤦‍♀️"}), [])
        self.assertEqual(self.run_check({"emoji": "🇺🇸"}), [])
        self.assertEqual(self.run_check({"emoji": "🥈🥶"}), [])

    def test_three_emoji_fail(self):
        problems = self.run_check({"emoji": "🥈🥶🐘"})
        self.assertEqual(len(problems), 1)
        self.assertIn("1 or 2 visible characters", problems[0])

    def test_emoji_with_hidden_text_fails(self):
        for bad in ("🏆\u200dA", "🏆\u0301", "AB", "A🏆"):
            self.assertEqual(len(self.run_check({"emoji": bad})), 1, repr(bad))
        for good in ("‼️", "❤️", "👍🏽", "🥶"):
            self.assertEqual(self.run_check({"emoji": good}), [], repr(good))

    def test_hand_typed_photo_keys_fail(self):
        self.assertEqual(len(self.run_check({"headshot": "https://x/y.png", "player_id": 1})), 2)

    def test_non_text_fields_report_instead_of_crashing(self):
        self.assertTrue(self.run_check({"stat": 5}))
        recap = {"week": 5, "flags": ["oops"]}
        problems = []
        check_recaps.check_awards(recap, set(), problems)
        self.assertEqual(len(problems), 1)

    def test_short_stat_is_not_a_substring_false_positive(self):
        self.assertEqual(self.run_check({"title": "Chat about it", "stat": "at"}), [])

    def test_stat_and_title_limits_are_inclusive(self):
        self.assertEqual(self.run_check({"stat": "x" * 22, "title": "t" * 48}), [])

    def test_empty_and_text_emoji_fail(self):
        self.assertEqual(len(self.run_check({"emoji": ""})), 1)
        self.assertEqual(len(self.run_check({"emoji": "ok"})), 1)

    def test_unknown_player_fails(self):
        problems = self.run_check({"player": "Josh Alien"})
        self.assertEqual(len(problems), 1)
        self.assertIn("isn't on any roster", problems[0])

    def test_player_without_facts_fails(self):
        self.assertEqual(len(self.run_check({"player": "Josh Allen"}, roster=None)), 1)

    def test_long_stat_fails_from_week_5_only(self):
        award = {"stat": "x" * 23}
        self.assertEqual(len(self.run_check(award, week=5)), 1)
        self.assertEqual(self.run_check(award, week=4), [])

    def test_stat_repeating_title_fails(self):
        problems = self.run_check({"title": "Right call, wrong week", "stat": "Right call"})
        self.assertEqual(len(problems), 1)
        self.assertIn("repeats the title", problems[0])

    def test_long_title_fails(self):
        self.assertEqual(len(self.run_check({"title": "t" * 49})), 1)

    def test_em_dash_fails_in_each_field(self):
        for field in ("title", "stat", "text"):
            problems = self.run_check({field: "one \u2014 two"})
            self.assertTrue(any("em dash" in p for p in problems), field)

    def test_old_awards_without_new_fields_pass(self):
        self.assertEqual(self.run_check({}, week=1, roster=None), [])


class BakedAwardsTest(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / "site"))
        import build
        self.build = build
        self.facts = {"teams": [{"starters": [{"name": "Josh Allen", "player_id": 3918298, "pos": "QB"},
                                              {"name": "Texans D/ST", "player_id": -1, "pos": "DST",
                                               "logo": "https://logo/hou.png"}],
                                 "bench": [{"name": "Mike Evans", "player_id": 16737, "pos": "WR"}]}]}

    def bake(self, award):
        return self.build.baked_awards({"flags": [award]}, self.facts)["flags"][0]

    def test_player_resolves_to_id_and_headshot(self):
        a = self.bake({"player": "Mike Evans"})
        self.assertEqual(a["player_id"], 16737)
        self.assertTrue(a["headshot"].endswith("/16737.png"))

    def test_dst_gets_its_logo(self):
        self.assertEqual(self.bake({"player": "Texans D/ST"})["headshot"], "https://logo/hou.png")

    def test_unknown_or_absent_player_bakes_nothing_and_typed_keys_are_dropped(self):
        for award in ({"player": "Nobody Here"}, {}, {"headshot": "https://evil/x.png", "player_id": 9}):
            a = self.bake(award)
            self.assertNotIn("headshot", a)
            self.assertNotIn("player_id", a)

    def test_recap_without_awards(self):
        self.assertEqual(self.build.baked_awards({}, self.facts),
                         {"game_balls": [], "flags": [], "tough_breaks": []})


class RolloutTest(unittest.TestCase):
    def test_within_grace_period(self):
        self.assertTrue(check_recaps.draft_violations_are_warnings(today=date(2026, 10, 5)))

    def test_after_grace_period(self):
        self.assertFalse(check_recaps.draft_violations_are_warnings(today=date(2026, 11, 1)))


class FirstNamesTest(unittest.TestCase):
    def test_nickname_in_parens_yields_both_names(self):
        names = check_recaps.first_names({"teams": [{"manager": "Cara (CC)"}]})
        self.assertEqual(names, {"Cara", "CC"})

    def test_plain_name(self):
        names = check_recaps.first_names({"teams": [{"manager": "Alice"}]})
        self.assertEqual(names, {"Alice"})


def _skip_if_not_implemented(test_method):
    def wrapper(self):
        try:
            test_method(self)
        except NotImplementedError:
            self.skipTest("find_possible_last_names not implemented yet — see the "
                           "TODO(human) in scripts/check_recaps.py")
    return wrapper


class LastNameTest(unittest.TestCase):
    @_skip_if_not_implemented
    def test_obvious_last_name_is_flagged(self):
        recap, _, league = load_fixture("last_name")
        names = check_recaps.first_names(league)
        problems = []
        check_recaps.check_no_last_names(recap, names, problems)
        self.assertTrue(any("Johnson" in p for p in problems), problems)

    @_skip_if_not_implemented
    def test_possessive_team_names_are_not_flagged(self):
        recap, _, league = load_fixture("last_name_clean")
        names = check_recaps.first_names(league)
        problems = []
        check_recaps.check_no_last_names(recap, names, problems)
        self.assertEqual(problems, [])

    @_skip_if_not_implemented
    def test_clean_recap_end_to_end(self):
        errors, warnings = check_recaps.check_all_recaps(FIXTURES / "valid")
        self.assertEqual((errors, warnings), ([], []))


class RealRecapsNumbersAndStructureTest(unittest.TestCase):
    """Runs the number and structure checks (not the last-name check, which
    isn't implemented yet) against the actual committed recaps and data —
    the real regression test the harness plan asked for: weeks 1-3 must be
    clean before this check can start blocking."""

    def test_every_committed_recap_is_clean(self):
        for recap_path in sorted(ROOT.glob("recaps/*/week-*.json")):
            with self.subTest(recap=recap_path.relative_to(ROOT)):
                recap = json.loads(recap_path.read_text())
                week_dir = ROOT / "data" / str(recap["season"]) / f"week-{recap['week']:02d}"
                numbers = set()
                for filename in ("facts.json", "espn.json"):
                    path = week_dir / filename
                    if path.exists():
                        check_recaps.collect_numbers(json.loads(path.read_text()), numbers)
                facts_path = week_dir / "facts.json"
                real_pairs = (check_recaps.real_matchup_pairs(json.loads(facts_path.read_text()))
                              if facts_path.exists() else set())

                problems = []
                check_recaps.check_numbers(recap, numbers, problems)
                check_recaps.check_matchup_structure(recap, real_pairs, problems)
                self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
