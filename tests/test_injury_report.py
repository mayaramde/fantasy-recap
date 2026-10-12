#!/usr/bin/env python3
"""Tests for build.injury_report: the rows behind the Coach page's "Injuries and byes" card."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
import build  # noqa: E402


def p(name, status=None, slot="WR", team="LAR"):
    return {"name": name, "pos": "WR", "slot": slot, "team": team, "logo": f"{team}.png", "injury_status": status}


class InjuryReportTest(unittest.TestCase):
    def test_hurt_and_bye_rows_starters_first(self):
        on_bye = lambda x: x["name"] in ("Bye Guy", "Hurt Bye")   # noqa: E731
        rows = build.injury_report(
            [p("Fine"), p("Q Guy", "QUESTIONABLE"), p("Bye Guy")],
            [p("Out Guy", "OUT", "BENCH"), p("IR Guy", "INJURY_RESERVE", "IR"), p("Hurt Bye", "OUT", "BENCH")],
            on_bye)
        self.assertEqual([(r["name"], r["status"], r["role"]) for r in rows], [
            ("Q Guy", "Questionable", "starting"), ("Bye Guy", "Bye", "starting"),
            ("Out Guy", "Out", "bench"), ("IR Guy", "On IR", "bench"),
            ("Hurt Bye", "Out", "bench")])   # a designation beats a bye

    def test_healthy_roster_is_empty(self):
        self.assertEqual(build.injury_report([p("A")], [p("B", slot="BENCH")], lambda x: False), [])


if __name__ == "__main__":
    unittest.main()
