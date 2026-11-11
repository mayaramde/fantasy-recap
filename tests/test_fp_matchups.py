"""FantasyPros matchup ratings on the Coach lineup cards: scripts/fp_matchups.py builds the snapshot's
`matchups` block, scripts/check.py validates it, site/build.py turns it into a chip and a note."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import check  # noqa: E402
import fp_matchups  # noqa: E402


def resp(pos, rows, start=10, end=10, key="team schedule"):
    """A get_schedule_and_strength response, shaped like the real one."""
    p = pos.lower()
    sched = []
    for team, rank, stars in rows:
        sos = {"weeks": f"Weeks {start}-{end}", "ratings": None} if rank is None else \
            {"weeks": f"Weeks {start}-{end}", f"{p}_stars_out_of_5": stars, f"{p}_rank_out_of_{32}": rank}
        sched.append({"team": team, "bye_week": 6, "Strength of Schedule": sos})
    return {"current_week": 10, "sos_window": {"week_start": start, "week_end": end, "label": f"Weeks {start}-{end}"},
            key: {"position": pos, "schedules": sched}}


class Build(unittest.TestCase):
    def test_ratings_by_team_and_position(self):
        block, notes = fp_matchups.build([resp("WR", [("DET", 1, 5.0), ("LV", 28, 0.9)]),
                                          resp("DST", [("DET", 11, 3.6)])], 10)
        self.assertEqual(block, {"week": 10, "teams": {"DET": {"WR": {"rank": 1, "stars": 5.0}, "DST": {"rank": 11, "stars": 3.6}},
                                                       "LV": {"WR": {"rank": 28, "stars": 0.9}}}})
        self.assertEqual(notes, [])

    def test_fantasypros_codes_become_espn_codes(self):
        block, _ = fp_matchups.build([resp("QB", [("JAC", 2, 5.0), ("WAS", 10, 3.9)])], 10)
        self.assertEqual(sorted(block["teams"]), ["JAX", "WSH"])

    def test_bye_teams_get_no_rating(self):
        block, _ = fp_matchups.build([resp("WR", [("CHI", None, None), ("DET", 1, 5.0)])], 10)
        self.assertEqual(list(block["teams"]), ["DET"])

    def test_a_window_that_is_not_the_live_week_is_skipped_and_reported(self):
        block, notes = fp_matchups.build([resp("WR", [("DET", 1, 5.0)], start=10, end=12)], 10)
        self.assertEqual(block["teams"], {})
        self.assertEqual(len(notes), 1)
        self.assertIn("Weeks 10-12", notes[0])

    def test_the_five_team_view_is_read_too(self):
        block, _ = fp_matchups.build([resp("WR", [("DET", 1, 5.0)], key="easiest schedules")], 10)
        self.assertEqual(block["teams"]["DET"]["WR"]["rank"], 1)

    def test_untrustworthy_numbers_are_dropped(self):
        block, _ = fp_matchups.build([resp("WR", [("DET", 0, 5.0), ("LV", 33, 1.0), ("NE", 5, 6.0), ("KC", 2.5, 4.0)])], 10)
        self.assertEqual(block["teams"], {})


def snap(block):
    return {"generated_at": "2026-11-10T14:00:00Z", "fantasypros": {"reached": True, "checked_at": "2026-11-10T14:00:00Z"},
            "weeks": {}, "matchups": block}


def check_errors(s):
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "data" / "2026" / "fantasypros"
        d.mkdir(parents=True)
        (d / "latest.json").write_text(json.dumps(s))
        errors = []
        check.check_fantasypros_snapshot(errors, root=Path(tmp))
        return errors


class Check(unittest.TestCase):
    good = {"week": 10, "teams": {"DET": {"WR": {"rank": 1, "stars": 5.0}}}}

    def test_valid(self):
        self.assertEqual(check_errors(snap(self.good)), [])

    def test_rejects_bad_shapes(self):
        for bad in ({"week": 10}, {"teams": {}}, {"week": 10, "teams": {"det": {"WR": {"rank": 1, "stars": 5}}}},
                    {"week": 10, "teams": {"DET": {"WR": {"rank": 33, "stars": 5}}}},
                    {"week": 10, "teams": {"DET": {"WR": {"rank": 1, "stars": 6}}}},
                    {"week": 10, "teams": {"DET": {"FLEX": {"rank": 1, "stars": 5}}}},
                    {"week": 10, "teams": {"DET": {"WR": {"rank": 1}}}}):
            self.assertTrue(check_errors(snap(bad)), bad)

    def test_unreached_snapshot_cannot_hold_matchups(self):
        s = snap(self.good)
        s["fantasypros"] = {"reached": False, "checked_at": "2026-11-10T14:00:00Z", "error": "down"}
        self.assertTrue(any("matchups" in e for e in check_errors(s)))


def fresh(block):
    return {"generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "matchups": block}


class Cards(unittest.TestCase):
    ratings = {"week": 10, "teams": {"DET": {"WR": {"rank": 1, "stars": 5.0}, "QB": {"rank": 20, "stars": 2.0}},
                                     "NE": {"DST": {"rank": 16, "stars": 3.0}}}}

    def ctx(self, **kw):
        base = {"locked": lambda p: False, "on_bye": lambda p: False,
                "matchups": build.fp_matchups(fresh(self.ratings), 10), "projected": True, "can_change": True,
                "starters": [], "bench_best": lambda slot: None, "form": {}, "stats": {}}
        base.update(kw)
        return base

    def wr(self, **kw):
        return dict({"player_id": 1, "name": "A", "pos": "WR", "slot": "WR", "team": "DET", "projected": 10.0,
                     "points": 0.0, "injury_status": None}, **kw)

    def test_easy_matchup_chip_and_note(self):
        chips = {c["label"]: c["value"] for c in build.player_chips(self.wr(), self.ctx())}
        self.assertEqual(chips["WR matchup"], "1st easiest")
        notes = build.player_notes(self.wr(), True, dict(self.ctx(), team_points=0, top_starter=None, top_bench=None,
                                                         before={}, before_week=None, pickups={}, news=lambda p: "",
                                                         starter_for=lambda p: None))
        self.assertIn("FantasyPros ranks this week's WR matchup 1st easiest of 32 teams (5.0 of 5 stars, where 5 is the easiest).", notes)

    def test_back_half_reads_as_hardest_from_the_other_end(self):
        qb = self.wr(pos="QB", slot="QB")
        self.assertEqual(build.player_matchup(qb, self.ctx())["phrase"], "13th hardest")   # rank 20 of 32
        self.assertEqual(build.player_matchup(self.wr(pos="DST", team="NE"), self.ctx())["phrase"], "16th easiest")
        self.assertEqual(build.player_matchup(self.wr(pos="DST", team="NE"), self.ctx())["label"], "D/ST")

    def test_ordinals(self):
        self.assertEqual([build._ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 32)],
                         ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "32nd"])

    def test_nothing_once_his_game_starts_or_on_a_bye_or_with_no_rating(self):
        self.assertIsNone(build.player_matchup(self.wr(), self.ctx(locked=lambda p: True)))
        self.assertIsNone(build.player_matchup(self.wr(), self.ctx(on_bye=lambda p: True)))
        self.assertIsNone(build.player_matchup(self.wr(team="MIA"), self.ctx()))
        self.assertIsNone(build.player_matchup(self.wr(slot="BENCH", pos="LB"), self.ctx()))

    def test_stale_or_other_week_ratings_are_never_read(self):
        self.assertIsNone(build.fp_matchups(fresh(self.ratings), 11))                  # the Next tab's week
        old = fresh(self.ratings)
        old["generated_at"] = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat().replace("+00:00", "Z")
        self.assertIsNone(build.fp_matchups(old, 10))
        self.assertIsNone(build.fp_matchups(None, 10))
        self.assertIsNone(build.fp_matchups({**fresh(self.ratings), "matchups": "junk"}, 10))


if __name__ == "__main__":
    unittest.main()
