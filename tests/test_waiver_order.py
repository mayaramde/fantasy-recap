#!/usr/bin/env python3
"""build.waiver_order: the site shows ESPN's own waiver rank, not our standings upside down."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
import build  # noqa: E402


def cap(at, ranks):
    return {"captured_at": at, "teams": [{"team_id": t, "waiver_rank": r} for t, r in ranks.items()]}


class WaiverOrder(unittest.TestCase):
    def test_orders_by_espn_rank(self):
        self.assertEqual(build.waiver_order([cap("2026-10-13", {1: 5, 2: 6, 3: 2, 4: 4, 5: 7, 6: 8, 7: 3, 8: 1})]),
                         [8, 3, 7, 4, 1, 2, 5, 6])

    def test_newest_capture_wins(self):
        old, new = cap("2026-10-06", {1: 1, 2: 2}), cap("2026-10-13", {1: 2, 2: 1})
        self.assertEqual(build.waiver_order([new, old]), [2, 1])
        self.assertEqual(build.waiver_order([old, new]), [2, 1])

    def test_captures_before_the_field_fall_back(self):
        self.assertIsNone(build.waiver_order([cap("2026-10-06", {1: None, 2: None})]))
        self.assertIsNone(build.waiver_order([]))

    def test_skips_a_partial_newest_capture(self):
        old = cap("2026-10-06", {1: 2, 2: 1})
        self.assertEqual(build.waiver_order([cap("2026-10-13", {1: 1, 2: None}), old]), [2, 1])


if __name__ == "__main__":
    unittest.main()
