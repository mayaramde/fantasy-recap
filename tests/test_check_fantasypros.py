import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check  # noqa: E402

CARD = {"kind": "waiver", "level": "watch", "title": "t", "text": "x"}


def run(snap):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        d = root / "data" / "2026" / "fantasypros"
        d.mkdir(parents=True)
        (d / "latest.json").write_text(json.dumps(snap))
        errors = []
        check.check_fantasypros_snapshot(errors, root=root)
        return errors


def snap(fp=None, generated="2026-10-14T06:00:00Z", cards=False):
    s = {"generated_at": generated,
         "weeks": {"6": {"teams": {"1": {"advice_cards": [CARD] if cards else [], "roster_ideas": []}}}}}
    if fp is not None:
        s["fantasypros"] = fp
    return s


class FantasyProsFieldTest(unittest.TestCase):
    def test_reached(self):
        self.assertEqual(run(snap({"reached": True, "checked_at": "2026-10-14T06:00:00Z"}, cards=True)), [])

    def test_old_snapshot_without_field_is_left_alone(self):
        self.assertEqual(run(snap(generated="2026-10-12T06:08:37Z")), [])

    def test_new_snapshot_must_have_field(self):
        self.assertEqual(len(run(snap())), 1)

    def test_not_reached_needs_error(self):
        errors = run(snap({"reached": False, "checked_at": "2026-10-14T06:00:00Z"}))
        self.assertTrue(any("error" in e for e in errors))

    def test_not_reached_with_error_and_no_cards_is_fine(self):
        fp = {"reached": False, "checked_at": "2026-10-14T06:00:00Z", "error": "tool not available"}
        self.assertEqual(run(snap(fp)), [])

    def test_not_reached_cannot_hold_fantasypros_cards(self):
        fp = {"reached": False, "checked_at": "2026-10-14T06:00:00Z", "error": "tool not available"}
        self.assertEqual(len(run(snap(fp, cards=True))), 1)

    def test_bad_shape(self):
        self.assertEqual(len(run(snap({"reached": "yes", "checked_at": "2026-10-14T06:00:00Z"}))), 1)
        self.assertTrue(run(snap({"reached": True, "checked_at": "yesterday"})))

    def test_malformed_shapes_report_instead_of_crashing(self):
        fp = {"reached": False, "checked_at": "2026-10-14T06:00:00Z", "error": "down"}
        for weeks in ([], {"6": {"teams": []}}, {"6": {"teams": {"1": None}}}, {"6": []}):
            s = snap(fp)
            s["weeks"] = weeks
            self.assertTrue(run(s), weeks)
        self.assertTrue(run([]))
        self.assertTrue(run("x"))

    def test_generated_at_must_be_utc_time(self):
        for bad in ("2026-10-14T06:00:00", "2026-10-14", None, 5, "2026-10-14T06:00:00+05:00"):
            s = snap(generated=bad)
            if bad is None:
                del s["generated_at"]
            self.assertTrue(run(s), bad)

    def test_boundary_and_zero_offset(self):
        self.assertEqual(len(run(snap(generated="2026-10-13T00:00:00Z"))), 1)
        self.assertEqual(run(snap(generated="2026-10-12T23:59:59Z")), [])
        fp = {"reached": True, "checked_at": "2026-10-14T06:00:00+00:00"}
        self.assertEqual(run(snap(fp, generated="2026-10-14T06:00:00+00:00")), [])

    def test_checked_at_must_be_utc(self):
        for bad in ("2026-10-14T06:00:00", "2026-10-14T06:00:00-04:00", None):
            self.assertTrue(run(snap({"reached": True, "checked_at": bad})), bad)

    def test_fp_wrong_type_and_bad_error(self):
        for fp in ("yes", [], {"reached": 1, "checked_at": "2026-10-14T06:00:00Z"}):
            self.assertTrue(run(snap(fp)), fp)
        for err in ("  ", 123):
            fp = {"reached": False, "checked_at": "2026-10-14T06:00:00Z", "error": err}
            self.assertTrue(any("error" in e for e in run(snap(fp))), err)

    def test_roster_ideas_only_and_second_team_violation(self):
        fp = {"reached": False, "checked_at": "2026-10-14T06:00:00Z", "error": "down"}
        s = snap(fp)
        s["weeks"]["6"]["teams"]["2"] = {"advice_cards": [], "roster_ideas": [CARD]}
        s["weeks"]["7"] = {"teams": {"1": {"advice_cards": [], "roster_ideas": []}}}
        errors = run(s)
        self.assertEqual(len(errors), 1)
        self.assertIn("team 2", errors[0])


class PlayerStatsTest(unittest.TestCase):
    FP = {"reached": True, "checked_at": "2026-10-14T06:00:00Z"}

    def with_stats(self, block, fp=None):
        s = snap(fp or self.FP)
        s["player_stats"] = block
        return run(s)

    def test_a_good_block_passes(self):
        block = {"through_week": 5, "players": {"4432620": {"games": 5, "rec_tar": 35, "rec_rec": 22}, "-16016": {"games": 5}},
                 "unmatched": [{"name": "Zach Charbonnet", "team": "SEA", "why": "no match"}]}
        self.assertEqual(self.with_stats(block), [])

    def test_absent_is_fine(self):
        self.assertEqual(run(snap(self.FP)), [])

    def test_bad_shapes_report(self):
        good = {"games": 5, "rec_tar": 35}
        for bad in ("x", [], {"players": {}}, {"through_week": "5", "players": {}}, {"through_week": 0, "players": {}},
                    {"through_week": 5, "players": []},
                    {"through_week": 5, "players": {"abc": good}},
                    {"through_week": 5, "players": {"1": {"rec_tar": 35}}},
                    {"through_week": 5, "players": {"1": {"games": 0}}},
                    {"through_week": 5, "players": {"1": {"games": 5, "rec_tar": 3.5}}},
                    {"through_week": 5, "players": {"1": {"games": 5, "points": 9}}},
                    {"through_week": 5, "players": {"1": None}},
                    {"through_week": 5, "players": {}, "unmatched": "x"}):
            self.assertTrue(self.with_stats(bad), bad)

    def test_cannot_ride_a_run_that_never_reached_fantasypros(self):
        fp = {"reached": False, "checked_at": "2026-10-14T06:00:00Z", "error": "tool not available"}
        self.assertTrue(self.with_stats({"through_week": 5, "players": {"1": {"games": 5}}}, fp))


if __name__ == "__main__":
    unittest.main()
