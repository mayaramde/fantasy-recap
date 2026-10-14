#!/usr/bin/env python3
"""Build-output tests for the matchup box score's rows (player() / week_payload() in site/build.py),
run against the committed captures in data/<season>/week-NN/facts.json."""
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


def load(week):
    return json.loads((SEASON_DIR / f"week-{week:02d}" / "facts.json").read_text())


def rows(payload):
    return [r for g in payload["games"] for s in (g["winner"], g["loser"]) for r in s["starters"] + s["bench"]]


WEEKS = sorted(int(d.name.split("-")[1]) for d in SEASON_DIR.glob("week-*") if (d / "facts.json").exists())


class CompletedWeekRows(unittest.TestCase):
    def test_every_row_has_player_id_team_and_a_logo_for_its_team(self):
        for w in WEEKS:
            p = build.week_payload(load(w), {})
            for r in rows(p):
                with self.subTest(week=w, player=r["name"]):
                    self.assertIsNotNone(r["player_id"])
                    self.assertTrue(r["team"])
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
        recap_weeks = [(load(w), {"week": w, "status": "published" if w != 5 else "draft"}) for w in WEEKS]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            stale = out / "box-lines" / "week-99.json"
            stale.parent.mkdir()
            stale.write_text("{}")
            build.write_box_lines(out, recap_weeks, preview=False)
            self.assertEqual(sorted(p.name for p in (out / "box-lines").iterdir()), ["week-03.json", "week-04.json"])
            build.write_box_lines(out, recap_weeks, preview=True)
            self.assertEqual(sorted(p.name for p in (out / "box-lines").iterdir()), ["week-03.json", "week-04.json", "week-05.json"])
            got = json.loads((out / build.box_lines_path(5)).read_text())
            self.assertEqual(got, {"week": 5, "lines": build.week_lines(load(5))})


class LiveWeekRows(unittest.TestCase):
    def test_live_rows_keep_logo_kickoff_and_carry_lines_inline(self):
        facts = load(max(WEEKS))
        p = build.week_payload(facts, {"status": "live"}, live=True)
        self.assertNotIn("team_logos", p)
        for r in rows(p):
            with self.subTest(player=r["name"]):
                self.assertIn("logo", r)
                self.assertIn("kickoff", r)
        self.assertTrue(any("lines" in r for r in rows(p)))


if __name__ == "__main__":
    unittest.main()
