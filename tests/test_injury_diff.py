#!/usr/bin/env python3
"""The Coach page's injury diff (injury_map / advice_payload in site/build.py): a designation is only
"new" or "gone" against a capture that has an injury report of its own. Built on the committed Week 9
capture, with designations written in by hand."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
import build  # noqa: E402

WEEK9 = json.loads((ROOT / "data" / str(build.LEAGUE["season"]) / "week-09" / "espn.json").read_text())


def rows(capture):
    return [p for m in capture["matchups"] for s in (m["home"], m["away"]) if s for p in s["lineup"]]


def capture_with(status, week, listed=None):
    """Week 9's rosters as week `week`, every row's injury_status set to `status`, and `listed`
    ({player_id: status}) on top."""
    c = copy.deepcopy(WEEK9)
    c["week"] = week
    for p in rows(c):
        p["injury_status"] = (listed or {}).get(p["player_id"], status)
    return c


def titles(capture, previous):
    return [it["title"] for r in build.next_payload(capture, previous)["teams"] for it in r["items"]]


class InjuryMap(unittest.TestCase):
    def test_all_null_week_is_no_report(self):
        self.assertEqual(build.injury_map(capture_with(None, 9)), {})

    def test_a_real_report_maps_every_player(self):
        m = build.injury_map(capture_with("ACTIVE", 9))
        self.assertEqual(len(m), len(rows(WEEK9)))


class InjuryDiff(unittest.TestCase):
    def setUp(self):
        starter = next(p for p in rows(WEEK9) if p["slot"] not in ("BENCH", "IR") and p["pos"] != "DST")
        self.name = starter["name"]
        self.previous = capture_with("ACTIVE", 9, {starter["player_id"]: "QUESTIONABLE"})

    def test_failed_read_this_week_calls_nobody_back(self):
        # This capture's injury read failed: every designation is null. Nobody is "off the report".
        self.assertFalse([t for t in titles(capture_with(None, 10), self.previous) if "off the injury report" in t])

    def test_a_real_report_still_says_who_is_back(self):
        self.assertIn(f"{self.name} is off the injury report", titles(capture_with("ACTIVE", 10), self.previous))


if __name__ == "__main__":
    unittest.main()
