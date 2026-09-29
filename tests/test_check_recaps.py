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
