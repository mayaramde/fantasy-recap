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


if __name__ == "__main__":
    unittest.main()
