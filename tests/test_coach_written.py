#!/usr/bin/env python3
"""Tests for the Coach page's written copy (site/build.py written_cards / apply_written).

Uses the committed 2026 captures with Week 3 treated as the live week (its recap left out)
and rewound to before kickoff (every game "pre", nothing played), so the computed cards are
real ones: bench swaps, the opponent preview, "nothing to fix". Each test writes a snapshot
in memory, the way coach-daily would, and checks what the page ends up showing.
"""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402

SEASON = 2026
WEEK = 3


def _now(hours_ago=0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class CoachWrittenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recap_weeks, captured, _, _, _ = build.load_inputs(SEASON)
        cls.recap_weeks = [rw for rw in recap_weeks if rw[1]["week"] < WEEK]
        facts, espn = copy.deepcopy(next(c for c in captured if c[0]["week"] == WEEK))
        facts["complete"] = False
        for t in facts["teams"]:
            t["yet_to_play"] = len(t["starters"])
            for p in t["starters"] + t["bench"]:
                if p.get("game_state"):
                    p["game_state"] = "pre"
                p["played"] = False
        for m in espn["matchups"]:
            for side in (m["home"], m["away"]):
                for p in (side or {}).get("lineup", []):
                    if p.get("game_state"):
                        p["game_state"] = "pre"
        cls.captured = [c for c in captured if c[0]["week"] < WEEK] + [(facts, espn)]

    def live(self, fp=None):
        _, weeks = build.render(copy.deepcopy(self.recap_weeks), copy.deepcopy(self.captured),
                                preview=False, fp=fp)
        live = next(w for w in weeks if w.get("live"))
        self.assertEqual(live["week"], WEEK)
        return live["advice"]

    def snapshot(self, teams, hours_ago=0):
        return {"generated_at": _now(hours_ago), "weeks": {str(WEEK): {"teams": teams}}}

    def test_every_computed_card_has_a_key(self):
        for row in self.live():
            self.assertTrue(row["summary_key"])
            for it in row["items"]:
                self.assertTrue(it.get("key"), it)
            keys = [it["key"] for it in row["items"]]
            self.assertEqual(len(keys), len(set(keys)), f"duplicate keys for team {row['team_id']}")

    def swap_team(self):
        row = next(r for r in self.live() if any(it["kind"] == "swap" for it in r["items"]))
        return row, next(it for it in row["items"] if it["kind"] == "swap")

    def test_pre_kickoff_week_has_real_advice(self):
        kinds = {it["kind"] for r in self.live() for it in r["items"]}
        self.assertTrue({"swap", "matchup", "clear"} <= kinds, kinds)

    def test_written_copy_replaces_matching_card_only(self):
        row, target = self.swap_team()
        fp = self.snapshot({str(row["team_id"]): {
            "coach_cards": {
                target["key"]: {"title": "Written title", "text": "Written advice, with one line of personality."},
                "swap:1:2:none": {"title": "Stale", "text": "A situation that no longer holds."},
            },
            "summary": {"key": row["summary_key"], "text": "Written summary."},
        }})
        after = next(r for r in self.live(fp) if r["team_id"] == row["team_id"])
        got = next(it for it in after["items"] if it["key"] == target["key"])
        self.assertEqual((got["title"], got["text"]), ("Written title", "Written advice, with one line of personality."))
        # Kind, level and the stat pill stay computed.
        self.assertEqual((got["kind"], got["level"], got["stat"]), (target["kind"], target["level"], target["stat"]))
        self.assertEqual(after["summary"], "Written summary.")
        self.assertNotIn("Stale", [it["title"] for it in after["items"]])
        # Every other card, and every other team, keeps its computed wording.
        others = [it for it in after["items"] if it["key"] != target["key"]]
        self.assertFalse(any(it.get("written") for it in others))
        self.assertEqual([r for r in self.live(fp) if r["team_id"] != row["team_id"]],
                         [r for r in self.live() if r["team_id"] != row["team_id"]])

    def test_opponent_preview_takes_written_copy(self):
        row = self.live()[0]
        target = next(it for it in row["items"] if it["kind"] == "matchup")
        fp = self.snapshot({str(row["team_id"]): {"coach_cards": {
            target["key"]: {"title": "Next up", "text": "Written preview."}}}})
        got = next(it for it in self.live(fp)[0]["items"] if it["key"] == target["key"])
        self.assertEqual(got["text"], "Written preview.")

    def test_changed_situation_falls_back_to_computed(self):
        """Written for a swap whose bench player has since landed on the injury report."""
        row, target = self.swap_team()
        stale_key = target["key"].rsplit(":", 1)[0] + ":QUESTIONABLE"
        fp = self.snapshot({str(row["team_id"]): {"coach_cards": {
            stale_key: {"title": "T", "text": "Advice for a healthy bench player."}}}})
        after = next(r for r in self.live(fp) if r["team_id"] == row["team_id"])
        got = next(it for it in after["items"] if it["key"] == target["key"])
        self.assertEqual(got["text"], target["text"])

    def test_summary_for_a_different_situation_is_ignored(self):
        row = self.live()[0]
        fp = self.snapshot({str(row["team_id"]): {"summary": {"key": "now:nothing-like-this", "text": "Nope."}}})
        self.assertEqual(self.live(fp)[0]["summary"], row["summary"])

    def test_summary_key_names_the_cards_it_sums_up(self):
        row, target = self.swap_team()
        self.assertTrue(row["summary_key"].startswith("now|"))
        self.assertIn(target["key"], row["summary_key"].split("|"))

    def test_fantasypros_cards_dont_move_the_summary_key(self):
        """coach_brief runs without a snapshot, so the key it prints has to be the one the
        site computes even when the same snapshot adds FantasyPros cards to the list."""
        row = next(r for r in self.live() if r["summary_key"] == "clear")
        fp = self.snapshot({str(row["team_id"]): {
            "advice_cards": [{"kind": "consensus", "level": "now", "title": "FP", "stat": "", "text": "FP says."}],
            "summary": {"key": "clear", "text": "Written summary."},
        }})
        after = next(r for r in self.live(fp) if r["team_id"] == row["team_id"])
        self.assertEqual(after["summary_key"], "clear")
        self.assertEqual(after["summary"], "Written summary.")

    def test_moving_numbers_are_rejected(self):
        row, target = self.swap_team()
        for text in ("ESPN projects him for 12.4 points.", "ESPN gives you a 61% chance.",
                     "He's at 17 points.", "A 12-point edge.", "61 percent of the time."):
            fp = self.snapshot({str(row["team_id"]): {"coach_cards": {target["key"]: {"title": "T", "text": text}}}})
            after = next(r for r in self.live(fp) if r["team_id"] == row["team_id"])
            got = next(it for it in after["items"] if it["key"] == target["key"])
            self.assertEqual(got["text"], target["text"], text)

    def test_summary_over_the_card_cap_falls_back_to_computed(self):
        row = self.live()[0]
        ok = "A tidy line that fits on a card."
        too_long = "Words " * 19 + "end."            # 114 characters
        self.assertGreater(len(too_long), build.SUMMARY_MAX)
        for text, expect_written in ((ok, True), (too_long, False)):
            fp = self.snapshot({str(row["team_id"]): {"summary": {"key": row["summary_key"], "text": text}}})
            got = self.live(fp)[0]["summary"]
            self.assertEqual(got == text, expect_written, text)

    def league_fp(self, key, text, hours_ago=0):
        fp = self.snapshot({}, hours_ago)
        fp["weeks"][str(WEEK)]["league"] = {"key": key, "text": text}
        return fp

    def test_brief_carries_the_league_key_and_facts_for_the_paragraph(self):
        import coach_brief
        rows = self.live()
        brief = coach_brief.league_brief(rows)
        self.assertEqual(brief["key"], rows[0]["league_key"])
        self.assertEqual(brief["teams"], len(rows))
        self.assertEqual(set(brief), {"key", "teams", "teams_with_something_to_fix", "starters_on_bye",
                                      "teams_with_a_starter_on_bye", "clean_lineups"})

    def test_league_key_is_stable_and_names_the_situation(self):
        rows = self.live()
        self.assertEqual(len({r["league_key"] for r in rows}), 1)
        self.assertEqual(rows[0]["league_key"], self.live()[0]["league_key"])
        changed = [dict(r, summary_key=r["summary_key"] + "x") if i == 0 else r for i, r in enumerate(rows)]
        self.assertNotEqual(build.league_key(changed), build.league_key(rows))

    def test_written_league_take_applies_on_key_match_only(self):
        key = self.live()[0]["league_key"]
        text = "Two lineups need a swap and everyone else is fine."
        self.assertEqual({r["league_take"] for r in self.live(self.league_fp(key, text))}, {text})
        self.assertEqual({r["league_take"] for r in self.live(self.league_fp("stale-key", text))}, {None})
        self.assertEqual({r["league_take"] for r in self.live()}, {None})

    def test_league_take_rejects_moving_numbers_length_and_stale_snapshots(self):
        key = self.live()[0]["league_key"]
        for text, hours in (("Amie projects at 140.3 this week.", 0), ("About 61% of lineups are fine.", 0),
                            ("Word. " * 80, 0), ("A fine paragraph.", 40), ("   ", 0)):
            got = {r["league_take"] for r in self.live(self.league_fp(key, text, hours))}
            self.assertEqual(got, {None}, text)

    def test_stale_snapshot_is_ignored(self):
        row, target = self.swap_team()
        fp = self.snapshot({str(row["team_id"]): {"coach_cards": {target["key"]: {"title": "T", "text": "Old news."}}}},
                           hours_ago=40)
        after = next(r for r in self.live(fp) if r["team_id"] == row["team_id"])
        got = next(it for it in after["items"] if it["key"] == target["key"])
        self.assertEqual(got["text"], target["text"])

    # ---------- team profile: season audit and roster ideas ----------

    def data(self, fp=None):
        data, _ = build.site_data(copy.deepcopy(self.recap_weeks), copy.deepcopy(self.captured),
                                  preview=False, fp=fp)
        return data

    def team(self, data, team_id):
        return next(s for s in data["season"]["standings"] if s["team_id"] == team_id)

    def test_every_team_has_a_profile(self):
        for s in self.data()["season"]["standings"]:
            self.assertEqual([c["kind"] for c in s["profile"]["audit"]], ["lineup_iq", "position", "projection"])
            self.assertIn(s["profile"]["weak_spot"], ("QB", "RB", "WR", "TE", "FLEX", "DST", "K"))
            self.assertIsInstance(s["profile"]["moves"], list)

    def test_audit_uses_recapped_weeks_only(self):
        # Week 3 is the live week here, so no audit text may mention it.
        for s in self.data()["season"]["standings"]:
            for c in s["profile"]["audit"]:
                self.assertNotIn("Week 3", c["text"])

    def audit_fp(self, team_id, key, text="Kincaid sat while the lineup starved.", hours_ago=0, **extra):
        fp = self.snapshot(extra.pop("teams", {}), hours_ago=hours_ago)
        fp["audit"] = {str(team_id): {key: {"title": "Written title", "text": text}}}
        return fp

    def test_written_audit_applies_on_key_match(self):
        tid = 6
        key = self.team(self.data(), tid)["profile"]["audit"][0]["key"]
        card = self.team(self.data(self.audit_fp(tid, key)), tid)["profile"]["audit"][0]
        self.assertEqual((card["title"], card.get("written")), ("Written title", True))

    def test_written_audit_ignored_on_key_mismatch(self):
        card = self.team(self.data(self.audit_fp(6, "lineup:Z:none")), 6)["profile"]["audit"][0]
        self.assertNotEqual(card["title"], "Written title")

    def test_written_audit_survives_a_stale_snapshot_but_coach_cards_do_not(self):
        tid = 6
        key = self.team(self.data(), tid)["profile"]["audit"][0]["key"]
        live_row = next(r for r in self.live() if r["team_id"] == tid)
        coach_key = next(it["key"] for it in live_row["items"] if it.get("key"))
        teams = {str(tid): {"coach_cards": {coach_key: {"title": "Written coach", "text": "Swap him."}}}}
        data = self.data(self.audit_fp(tid, key, hours_ago=48, teams=teams))
        self.assertEqual(self.team(data, tid)["profile"]["audit"][0]["title"], "Written title")
        row = next(r for r in data["live"]["advice"] if r["team_id"] == tid)
        self.assertNotIn("Written coach", [it["title"] for it in row["items"]])

    def test_malformed_audit_block_falls_back_instead_of_crashing(self):
        for bad in (["not", "a", "dict"], "oops", {"6": ["list"]}):
            fp = self.snapshot({})
            fp["audit"] = bad
            card = self.team(self.data(fp), 6)["profile"]["audit"][0]
            self.assertNotIn("written", card)

    def test_written_audit_rejects_moving_numbers(self):
        tid = 6
        key = self.team(self.data(), tid)["profile"]["audit"][0]["key"]
        card = self.team(self.data(self.audit_fp(tid, key, text="You hit 91% of optimal.")), tid)["profile"]["audit"][0]
        self.assertNotEqual(card["title"], "Written title")

    def test_roster_ideas_tagged_only_on_weak_spot_match(self):
        tid = 6
        weak = self.team(self.data(), tid)["profile"]["weak_spot"]
        other = "K" if weak != "K" else "QB"
        idea = lambda title, **kw: {"kind": "waiver", "level": "info", "title": title, "text": "Worth a claim.", **kw}  # noqa: E731
        fp = self.snapshot({str(tid): {"roster_ideas": [idea("fits", pos=weak), idea("other", pos=other), idea("nopos")]}})
        row = next(r for r in self.data(fp)["live"]["advice"] if r["team_id"] == tid)
        tags = {i["title"]: i["fills_weak_spot"] for i in row["roster_ideas"]}
        self.assertEqual(tags, {"fits": True, "other": False, "nopos": False})

    def test_brief_has_audit_for_every_team(self):
        import coach_brief
        out = coach_brief.brief(SEASON)
        self.assertEqual(len(out["audit"]), 8)
        for row in out["audit"].values():
            self.assertEqual(set(row), {"manager", "weak_spot", "cards"})
            for c in row["cards"]:
                self.assertEqual(set(c), {"key", "kind", "stat", "title", "text"})


if __name__ == "__main__":
    unittest.main()
