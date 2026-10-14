import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check  # noqa: E402
import snapshot_history  # noqa: E402

FP = {"reached": True, "checked_at": "2026-10-14T20:00:00Z"}


def snap(generated="2026-10-14T20:00:00Z", ideas=None):
    return {"generated_at": generated, "fantasypros": FP,
            "weeks": {"6": {"teams": {"1": {"advice_cards": [], "roster_ideas": ideas or [],
                                            "coach_cards": {"k": {"title": "t", "text": "x"}}}}}}}


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.season = Path(self.tmp.name) / "data" / "2026"
        (self.season / "fantasypros").mkdir(parents=True)

    def write_latest(self, s):
        (self.season / "fantasypros" / "latest.json").write_text(json.dumps(s))

    def hist(self):
        return self.season / "fantasypros" / "history"

    def test_writes_dated_file_and_index(self):
        self.write_latest(snap(ideas=[{"kind": "waiver"}, {"kind": "trade"}]))
        out = snapshot_history.archive(self.season)
        self.assertEqual(out.name, "2026-10-14.json")
        day = json.loads(out.read_text())
        self.assertEqual(day["schema_version"], 1)
        self.assertEqual(day["generated_at"], "2026-10-14T20:00:00Z")
        row = json.loads((self.hist() / "index.json").read_text())["days"][0]
        self.assertEqual(row["date"], "2026-10-14")
        self.assertTrue(row["fantasypros_reached"])
        self.assertEqual(row["weeks"]["6"], {"advice_cards": 0, "roster_ideas": 2, "trades": 1, "coach_cards": 1})

    def test_new_day_adds_and_old_day_is_kept(self):
        self.write_latest(snap("2026-10-13T20:00:00Z"))
        snapshot_history.archive(self.season)
        first = (self.hist() / "2026-10-13.json").read_text()
        self.write_latest(snap("2026-10-14T20:00:00Z"))
        snapshot_history.archive(self.season)
        self.assertEqual((self.hist() / "2026-10-13.json").read_text(), first)
        days = json.loads((self.hist() / "index.json").read_text())["days"]
        self.assertEqual([d["date"] for d in days], ["2026-10-13", "2026-10-14"])

    def test_same_day_rerun_replaces_that_day(self):
        self.write_latest(snap("2026-10-14T20:00:00Z"))
        snapshot_history.archive(self.season)
        self.write_latest(snap("2026-10-14T23:00:00Z"))
        snapshot_history.archive(self.season)
        self.assertEqual(len(list(self.hist().glob("????-??-??.json"))), 1)
        self.assertEqual(json.loads((self.hist() / "2026-10-14.json").read_text())["generated_at"],
                         "2026-10-14T23:00:00Z")

    def test_bad_generated_at_is_rejected(self):
        for bad in (None, "yesterday", "2026-10-14T06:00:00"):
            s = snap()
            s["generated_at"] = bad
            self.write_latest(s)
            with self.assertRaises(ValueError):
                snapshot_history.archive(self.season)

    def test_index_survives_a_broken_day(self):
        self.write_latest(snap())
        snapshot_history.archive(self.season)
        (self.hist() / "2026-10-01.json").write_text("{not json")
        snapshot_history.archive(self.season)
        days = json.loads((self.hist() / "index.json").read_text())["days"]
        self.assertEqual([d["date"] for d in days], ["2026-10-14"])


class LocalDayTest(unittest.TestCase):
    def test_utc_evening_belongs_to_the_pacific_day_before(self):
        # 01:41Z on the 14th is 6:41pm PDT on the 13th
        self.assertEqual(snapshot_history.local_day("2026-10-14T01:41:07Z"), "2026-10-13")

    def test_pacific_midnight_boundary_in_daylight_time(self):
        self.assertEqual(snapshot_history.local_day("2026-10-14T06:59:59Z"), "2026-10-13")
        self.assertEqual(snapshot_history.local_day("2026-10-14T07:00:00Z"), "2026-10-14")

    def test_pacific_midnight_boundary_in_standard_time(self):
        # clocks go back on 2026-11-01, so midnight moves from 07:00Z to 08:00Z
        self.assertEqual(snapshot_history.local_day("2026-11-15T07:59:59Z"), "2026-11-14")
        self.assertEqual(snapshot_history.local_day("2026-11-15T08:00:00Z"), "2026-11-15")

    def test_evening_rerun_overwrites_the_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            season = Path(tmp) / "data" / "2026"
            (season / "fantasypros").mkdir(parents=True)
            latest = season / "fantasypros" / "latest.json"
            for generated in ("2026-10-14T01:41:07Z", "2026-10-14T05:30:00Z"):  # 6:41pm and 10:30pm PDT, the 13th
                latest.write_text(json.dumps(snap(generated)))
                snapshot_history.archive(season)
            files = sorted(p.name for p in (season / "fantasypros" / "history").glob("????-??-??.json"))
            self.assertEqual(files, ["2026-10-13.json"])


class CheckHistoryTest(unittest.TestCase):
    def run_check(self, name, s):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "data" / "2026" / "fantasypros" / "history"
            d.mkdir(parents=True)
            (d / name).write_text(json.dumps(s))
            (d / "index.json").write_text("{}")  # must not be treated as a snapshot
            errors = []
            check.check_fantasypros_snapshot(errors, root=root)
            return errors

    def test_matching_filename_passes(self):
        self.assertEqual(self.run_check("2026-10-14.json", snap()), [])

    def test_filename_follows_the_pacific_date_not_the_utc_one(self):
        self.assertEqual(self.run_check("2026-10-13.json", snap("2026-10-14T01:41:07Z")), [])
        self.assertEqual(len(self.run_check("2026-10-14.json", snap("2026-10-14T01:41:07Z"))), 1)

    def test_filename_must_match_generated_at(self):
        errors = self.run_check("2026-10-13.json", snap())
        self.assertEqual(len(errors), 1)
        self.assertIn("filename date", errors[0])

    def test_history_gets_the_same_checks_as_latest(self):
        s = snap()
        del s["fantasypros"]
        self.assertEqual(len(self.run_check("2026-10-14.json", s)), 1)


if __name__ == "__main__":
    unittest.main()
