#!/usr/bin/env python3
"""Build-output tests for the matchup box score's rows (player() / week_payload() in site/build.py),
run against the committed captures in data/<season>/week-NN/facts.json."""
import functools
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
import build  # noqa: E402

SEASON_DIR = ROOT / "data" / str(build.LEAGUE["season"])
FIRST_WITH_STATES = 3          # weeks 1 and 2 were captured before game_state existed


@functools.lru_cache(maxsize=None)
def load(week):
    """Cached: nothing here mutates a facts dict, and the lines tests read every week."""
    return json.loads((SEASON_DIR / f"week-{week:02d}" / "facts.json").read_text())


def rows(payload):
    return [r for g in payload["games"] for s in (g["winner"], g["loser"]) for r in s["starters"] + s["bench"]]


def written(folder):
    """What a build left in box-lines/. write_box_lines clears the folder and only recreates it when
    it writes a file, so a build with no lines to write leaves no folder at all, not an empty one."""
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


WEEKS = sorted(int(d.name.split("-")[1]) for d in SEASON_DIR.glob("week-*") if (d / "facts.json").exists())
# The newest week on disk can be the live, uncommitted capture, and a week captured before kickoff has
# no points yet, so ESPN gave it no scoring lines at all. Anything about lines reads the newest week
# that has them, not whatever was captured last.
WEEKS_WITH_LINES = [w for w in WEEKS if build.week_lines(load(w))]
WEEKS_WITHOUT_LINES = [w for w in WEEKS if w not in WEEKS_WITH_LINES]


class CompletedWeekRows(unittest.TestCase):
    def test_every_row_has_player_id_and_a_named_team_has_a_logo(self):
        """ESPN can fail to name a team (a free agent), so a row with no team is allowed and just has no badge."""
        for w in WEEKS:
            p = build.week_payload(load(w), {})
            for r in rows(p):
                with self.subTest(week=w, player=r["name"]):
                    self.assertIn("team", r)
                    self.assertIsNotNone(r["player_id"])
                    if r["team"]:
                        self.assertTrue(p["team_logos"].get(r["team"]), "no logo for his team")

    def test_state_is_the_captures_own_and_never_invented(self):
        for w in WEEKS:
            facts = load(w)
            by_id = {x["player_id"]: x for t in facts["teams"] for x in t["starters"] + t["bench"]}
            for r in rows(build.week_payload(facts, {})):
                src = by_id[r["player_id"]].get("game_state")
                with self.subTest(week=w, player=r["name"]):
                    if src:
                        self.assertEqual(r["state"], src)
                        self.assertIn(r["state"], ("pre", "in", "post"))
                    else:
                        self.assertNotIn("state", r)

    def test_bye_is_the_coach_rule_and_weeks_without_states_have_none(self):
        for w in WEEKS:
            facts = load(w)
            known = build.game_states_known(build.box_players(facts))
            for r in rows(build.week_payload(facts, {})):
                with self.subTest(week=w, player=r["name"]):
                    self.assertEqual(bool(r.get("bye")), known and "state" not in r)
            if w < FIRST_WITH_STATES:
                self.assertFalse(known)

    def test_week_five_byes_are_the_chiefs_and_panthers(self):
        names = {r["name"] for r in rows(build.week_payload(load(5), {})) if r.get("bye")}
        self.assertEqual(names, {"Rashee Rice", "Jonathon Brooks", "Tetairoa McMillan", "Jalen Coker", "Chuba Hubbard",
                                 "Bryce Young", "Kenneth Walker III", "Patrick Mahomes", "Travis Kelce"})

    def test_kickoff_logo_and_lines_stay_out_of_a_completed_weeks_rows(self):
        for w in WEEKS:
            for r in rows(build.week_payload(load(w), {})):
                for key in ("kickoff", "logo", "lines"):
                    with self.subTest(week=w, player=r["name"], key=key):
                        self.assertNotIn(key, r)


class LinesFile(unittest.TestCase):
    def test_lines_sum_to_points(self):
        """Reported, not repaired: any row whose ESPN lines miss its points is listed by name."""
        gaps = []
        for w in WEEKS:
            facts = load(w)
            lines = build.week_lines(facts)
            for t in facts["teams"]:
                for p in t["starters"] + t["bench"]:
                    got = lines.get(str(p["player_id"]))
                    if got and abs(sum(l["points"] for l in got) - p["points"]) > 0.01:
                        gaps.append(f"week {w} {p['name']}: lines {sum(l['points'] for l in got):.2f} vs points {p['points']:.2f}")
        self.assertEqual(gaps, [])

    def test_lines_only_for_players_with_a_stat_line_and_in_the_coach_card_shape(self):
        for w in WEEKS:
            facts = load(w)
            lines = build.week_lines(facts)
            for p in build.box_players(facts):
                with self.subTest(week=w, player=p["name"]):
                    self.assertEqual(str(p["player_id"]) in lines, bool(p.get("scoring_lines")))
            for rowlines in lines.values():
                self.assertTrue(all(set(l) == {"label", "value", "points"} for l in rowlines))

    def test_weeks_captured_before_scoring_lines_have_no_file_and_no_pointer(self):
        for w in WEEKS:
            if w < FIRST_WITH_STATES:
                self.assertEqual(build.week_lines(load(w)), {})
                self.assertNotIn("lines_src", build.week_payload(load(w), {}))

    def test_files_are_written_for_published_weeks_only_and_stale_ones_are_cleared(self):
        # The newest captured week is the draft under review; every earlier week is published.
        draft = max(WEEKS)
        recap_weeks = [(load(w), {"week": w, "status": "published" if w != draft else "draft"}) for w in WEEKS]
        published_files = sorted(Path(build.box_lines_path(w)).name for w in WEEKS_WITH_LINES if w != draft)
        preview_files = sorted(Path(build.box_lines_path(w)).name for w in WEEKS_WITH_LINES)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            stale = out / "box-lines" / "week-99.json"
            stale.parent.mkdir()
            stale.write_text("{}")
            build.write_box_lines(out, recap_weeks, preview=False)
            self.assertEqual(written(out / "box-lines"), published_files)
            build.write_box_lines(out, recap_weeks, preview=True)
            self.assertEqual(written(out / "box-lines"), preview_files)
            if draft in WEEKS_WITH_LINES:
                got = json.loads((out / build.box_lines_path(draft)).read_text())
                self.assertEqual(got, {"week": draft, "lines": build.week_lines(load(draft))})
            else:
                # A draft captured before kickoff has no lines, so the preview build writes it no file.
                self.assertFalse((out / build.box_lines_path(draft)).exists())


class LiveWeekRows(unittest.TestCase):
    def test_live_rows_keep_logo_and_kickoff(self):
        """True of the newest capture whether or not it has kicked off: the Live page serves it either way."""
        p = build.week_payload(load(max(WEEKS)), {"status": "live"}, live=True)
        self.assertNotIn("team_logos", p)
        for r in rows(p):
            with self.subTest(player=r["name"]):
                self.assertIn("logo", r)
                self.assertIn("kickoff", r)

    @unittest.skipUnless(WEEKS_WITH_LINES, "no captured week carries scoring lines")
    def test_live_rows_carry_lines_inline(self):
        p = build.week_payload(load(WEEKS_WITH_LINES[-1]), {"status": "live"}, live=True)
        self.assertTrue(any("lines" in r for r in rows(p)))

    @unittest.skipUnless(WEEKS_WITHOUT_LINES, "every captured week carries scoring lines")
    def test_a_lineless_weeks_live_rows_carry_no_lines(self):
        """The state this file used to trip on: nobody has scored, so there is nothing to inline."""
        p = build.week_payload(load(WEEKS_WITHOUT_LINES[-1]), {"status": "live"}, live=True)
        self.assertFalse(any("lines" in r for r in rows(p)))


class InjuryDetails(unittest.TestCase):
    """ESPN's injury type and expected return ride along on a row only beside a designation."""

    BASE = {"player_id": 1, "name": "A", "pos": "WR", "slot": "BENCH", "points": 0, "projected": 9.5}

    def row(self, **extra):
        return build.player({**self.BASE, **extra}, live=True, states_known=False)

    def test_listed_player_carries_type_and_return(self):
        r = self.row(injury_status="QUESTIONABLE", injury_type="Achilles", injury_return="2026-11-15")
        self.assertEqual((r["injury"], r["injury_type"], r["injury_return"]), ("Questionable", "Achilles", "2026-11-15"))

    def test_unlisted_player_carries_neither(self):
        r = self.row(injury_status="ACTIVE", injury_type="Ankle", injury_return="2026-11-15")
        self.assertNotIn("injury", r)
        self.assertNotIn("injury_type", r)
        self.assertNotIn("injury_return", r)

    def test_missing_details_are_absent_not_null(self):
        r = self.row(injury_status="OUT", injury_type=None, injury_return=None)
        self.assertEqual(r["injury"], "Out")
        self.assertNotIn("injury_type", r)
        self.assertNotIn("injury_return", r)


if __name__ == "__main__":
    unittest.main()
