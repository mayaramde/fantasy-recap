#!/usr/bin/env python3
"""Tests for the Key stats tiles on the live week's rows (key_stats / fp_player_stats / player() in
site/build.py) and for scripts/fp_player_stats.py, which builds the snapshot block they read."""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import fp_player_stats as fps  # noqa: E402

LABELS = {
    "RB": ["Carries / game", "Rush yds / game", "Targets / game", "Catches / game"],
    "WR": ["Targets / game", "Catches / game", "Rec yds / game", "TDs this season"],
    "TE": ["Targets / game", "Catches / game", "Rec yds / game", "TDs this season"],
    "QB": ["Pass att / game", "Pass yds / game", "Rush att / game", "Pass TDs this season"],
    "K": ["FGs / game", "FG accuracy", "Extra points", "Games played"],
}
WASHINGTON = {"games": 5, "rec_tar": 35, "rec_rec": 22, "rec_yds": 352, "rec_tds": 4, "rush_att": 1, "rush_yds": 3, "rush_tds": 0}


def values(pos, st):
    tiles, games = build.key_stats(pos, st)
    return [t["value"] for t in tiles]


class Tiles(unittest.TestCase):
    def test_labels_and_order_per_position(self):
        for pos, labels in LABELS.items():
            tiles, _ = build.key_stats(pos, {"games": 5, "fga": 1})
            self.assertEqual([t["label"] for t in tiles], labels, pos)
            self.assertTrue(all(set(t) == {"label", "value"} and isinstance(t["value"], str) for t in tiles))

    def test_parker_washington_through_week_five(self):
        tiles, games = build.key_stats("WR", WASHINGTON)
        self.assertEqual(games, 5)
        self.assertEqual([t["value"] for t in tiles], ["7.0", "4.4", "70.4", "4"])

    def test_per_game_divides_by_the_players_own_games(self):
        st = {"games": 4, "rush_att": 61, "rush_yds": 306, "rec_tar": 11, "rec_rec": 10}
        self.assertEqual(values("RB", st), ["15.3", "76.5", "2.8", "2.5"])     # not by 5, the league's weeks
        self.assertEqual(build.key_stats("RB", st)[1], 4)

    def test_halves_round_up_and_one_decimal_always(self):
        self.assertEqual(values("RB", {"games": 4, "rush_att": 9, "rush_yds": 10, "rec_tar": 8, "rec_rec": 0})[0], "2.3")
        self.assertEqual(values("RB", {"games": 5, "rush_att": 10})[0], "2.0")

    def test_td_tile_counts_every_touchdown_and_a_missing_stat_is_zero(self):
        self.assertEqual(values("WR", {"games": 5, "rec_tds": 3, "rush_tds": 1})[3], "4")
        self.assertEqual(values("TE", {"games": 3})[:3], ["0.0", "0.0", "0.0"])

    def test_qb_and_kicker(self):
        qb = {"games": 5, "pass_att": 151, "pass_yds": 1228, "pass_tds": 8, "rush_att": 30}
        self.assertEqual(values("QB", qb), ["30.2", "245.6", "6.0", "8"])
        k = {"games": 5, "fg": 9, "fga": 12, "xpt": 13, "xpa": 14}
        self.assertEqual(values("K", k), ["1.8", "75%", "13 of 14", "5"])
        self.assertEqual(values("K", {"games": 5, "fg": 2, "fga": 3, "xpt": 0, "xpa": 0})[1], "67%")
        self.assertEqual(values("K", {"games": 2, "fg": 0, "fga": 0, "xpt": 1, "xpa": 1})[1], "-")

    def test_no_tiles_without_a_position_to_show_or_a_game_to_divide_by(self):
        self.assertIsNone(build.key_stats("DST", {"games": 5}))
        self.assertIsNone(build.key_stats("RB", None))
        for games in (0, None, "5", 2.5):
            self.assertIsNone(build.key_stats("RB", {"games": games, "rush_att": 5}))


def fresh(block, age=timedelta(hours=2)):
    return {"generated_at": (datetime.now(timezone.utc) - age).strftime("%Y-%m-%dT%H:%M:%SZ"), "weeks": {},
            "player_stats": block}


BLOCK = {"through_week": 5, "players": {"4432620": WASHINGTON}}   # ESPN id, not FantasyPros'


class Snapshot(unittest.TestCase):
    def test_fresh_snapshot_gives_the_players(self):
        self.assertEqual(build.fp_player_stats(fresh(BLOCK), 6), BLOCK["players"])

    def test_missing_stale_or_malformed_gives_none(self):
        for fp in (None, {}, fresh(None), fresh([]), fresh({"through_week": 5}), fresh({"through_week": "5", "players": {}}),
                   fresh({"through_week": 5, "players": []}), fresh(BLOCK, age=timedelta(hours=37)),
                   {"weeks": {}, "player_stats": BLOCK}, {"generated_at": "garbage", "player_stats": BLOCK}):
            self.assertIsNone(build.fp_player_stats(fp, 6), fp)

    def test_a_snapshot_a_week_behind_is_dropped(self):
        self.assertIsNotNone(build.fp_player_stats(fresh(BLOCK), 6))       # through 5 is the week before 6
        self.assertIsNone(build.fp_player_stats(fresh(BLOCK), 7))          # through 5 would lag a week
        self.assertIsNotNone(build.fp_player_stats(fresh({"through_week": 6, "players": {}}), 6))


def facts():
    return json.loads((ROOT / "data" / "2026" / "week-05" / "facts.json").read_text())


def rows(payload):
    return [r for g in payload["games"] for s in (g["winner"], g["loser"]) for r in s["starters"] + s["bench"]]


class LiveRows(unittest.TestCase):
    def setUp(self):
        self.stats = {"4432620": WASHINGTON}         # Parker Washington's ESPN id

    def test_live_rows_with_a_match_carry_key_and_key_games(self):
        got = {r["name"]: r for r in rows(build.week_payload(facts(), {}, live=True, stats=self.stats))}
        self.assertEqual(got["Parker Washington"]["key_games"], 5)
        self.assertEqual([t["label"] for t in got["Parker Washington"]["key"]], LABELS["WR"])
        self.assertEqual([r["name"] for r in got.values() if "key" in r], ["Parker Washington"])

    def test_no_stats_means_no_key_anywhere(self):
        for r in rows(build.week_payload(facts(), {}, live=True, stats=None)):
            self.assertNotIn("key", r)
            self.assertNotIn("key_games", r)

    def test_finished_weeks_never_carry_key(self):
        for r in rows(build.week_payload(facts(), {}, stats=self.stats)):
            self.assertNotIn("key", r)

    def test_a_defense_never_does(self):
        stats = {str(r["player_id"]): {"games": 5} for r in rows(build.week_payload(facts(), {}, live=True))}
        for r in rows(build.week_payload(facts(), {}, live=True, stats=stats)):
            self.assertEqual("key" in r, r["pos"] != "DST", r["name"])

    def test_live_payload_reads_the_fresh_snapshot_and_ignores_a_stale_one(self):
        f = facts()
        espn = json.loads((ROOT / "data" / "2026" / "week-05" / "espn.json").read_text())
        for fp, expect in ((fresh(BLOCK), 1), (fresh(BLOCK, age=timedelta(hours=40)), 0), (None, 0)):
            w = build.live_payload(f, espn, None, fp=fp)
            self.assertEqual(sum("key" in r for r in rows(w)), expect)


def resp(*rows_):
    return {"data": [{"player_id": "1", "player_name": n, "position_id": pos, "team_id": team, "stats": st}
                     for n, pos, team, st in rows_], "unresolved_names": ["everything, unreliably"]}


def pl(pid, name, pos, team):
    return {"player_id": pid, "name": name, "pos": pos, "team": team}


class Matching(unittest.TestCase):
    def test_pairs_by_name_team_and_position_across_spelling_differences(self):
        responses = [resp(("Patrick Mahomes II", "QB", "KC", {"games": 4}),
                          ("Parker Washington", "WR", "JAC", {"games": 5}),
                          ("Stefon Diggs", "WR", "WAS", {"games": 4}),
                          ("Amon-Ra St. Brown", "WR", "DET", {"games": 5}),
                          ("Deebo Samuel Sr.", "WR", "SF", {"games": 5}))]
        roster = [pl(1, "Patrick Mahomes", "QB", "KC"), pl(2, "Parker Washington", "WR", "JAX"),
                  pl(3, "Stefon Diggs", "WR", "WSH"), pl(4, "Amon-Ra St. Brown", "WR", "DET"),
                  pl(5, "Deebo Samuel", "WR", "SF")]
        block = fps.build(roster, responses, 5)
        self.assertEqual(sorted(block["players"]), ["1", "2", "3", "4", "5"])
        self.assertEqual(block["unmatched"], [])

    def test_unmatched_players_are_listed_not_dropped_or_guessed(self):
        responses = [resp(("Zach Charbonnet", "RB", "SEA", {"games": 5}), ("DJ Moore", "WR", "BUF", {"games": 4}))]
        roster = [pl(1, "Zach Charbonnet", "RB", "LAR"),            # traded: same name, other team
                  pl(2, "DJ Moore", "WR", "CHI"),                   # a different DJ Moore
                  pl(3, "Somebody New", "WR", "DEN"),
                  pl(4, "Pos Mismatch", "TE", "DEN")]
        block = fps.build(roster, responses, 5)
        self.assertEqual(block["players"], {})
        self.assertEqual([u["name"] for u in block["unmatched"]], ["Zach Charbonnet", "DJ Moore", "Somebody New", "Pos Mismatch"])

    def test_two_different_rows_for_one_key_is_ambiguous(self):
        responses = [resp(("Mike Williams", "WR", "NYJ", {"games": 3}), ("Mike Williams", "WR", "NYJ", {"games": 5}))]
        block = fps.build([pl(1, "Mike Williams", "WR", "NYJ")], responses, 5)
        self.assertEqual(block["unmatched"][0]["why"], "ambiguous")

    def test_the_same_row_twice_is_fine_and_unresolved_names_is_ignored(self):
        row = ("Josh Allen", "QB", "BUF", {"games": 5})
        block = fps.build([pl(1, "Josh Allen", "QB", "BUF")], [resp(row), resp(row)], 5)
        self.assertEqual(list(block["players"]), ["1"])

    def test_a_stray_defense_row_never_matches_and_a_rostered_defense_is_skipped(self):
        responses = [resp(("Washington Commanders", "DST", "WAS", {"games": 5}))]
        block = fps.build([pl(-16016, "Vikings D/ST", "DST", "MIN"), pl(2, "Parker Washington", "WR", "JAX")], responses, 5)
        self.assertEqual(block["players"], {})
        self.assertEqual([u["name"] for u in block["unmatched"]], ["Parker Washington"])

    def test_a_player_with_no_games_has_no_tiles(self):
        block = fps.build([pl(1, "Rookie Guy", "WR", "DEN")], [resp(("Rookie Guy", "WR", "DEN", {"games": 0}))], 5)
        self.assertEqual(block["players"], {})
        self.assertEqual(block["unmatched"][0]["why"], "no games played")

    def test_only_whole_number_totals_the_tiles_read_are_kept(self):
        st = {"games": 5, "rec_tar": 35, "points": 59.5, "rec_att": 35, "fumbles": 0, "rec_yds": 352.0}
        block = fps.build([pl(1, "Parker Washington", "WR", "JAX")], [resp(("Parker Washington", "WR", "JAC", st))], 5)
        self.assertEqual(block["players"]["1"], {"games": 5, "rec_tar": 35})
        self.assertEqual(block["through_week"], 5)


if __name__ == "__main__":
    unittest.main()
