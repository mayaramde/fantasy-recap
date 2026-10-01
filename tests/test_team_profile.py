#!/usr/bin/env python3
"""Tests for site/team_profile.py: the team profile's audit cards and roster moves.

Hand-built fixtures only, so every expected number is checkable by eye.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
import team_profile as tp  # noqa: E402


def item(kind, pid, name, frm, to):
    return {"type": kind, "player_id": pid, "name": name, "from_team_id": frm, "to_team_id": to,
            "from_slot": None, "to_slot": None}


def txn(kind, team_id, date, items):
    return {"type": kind, "team_id": team_id, "date": date, "bid": 0, "items": items}


def cap(week, transactions):
    return ({"week": week}, {"week": week, "transactions": transactions})


class MovesTest(unittest.TestCase):
    def test_keeps_adds_drops_and_trades_drops_lineup_and_draft(self):
        captured = [cap(1, [
            txn("DRAFT", 2, "2026-09-01T00:00:00Z", [item("ADD", 1, "Draft Pick", 0, 2)]),
            txn("ROSTER", 2, "2026-09-02T00:00:00Z", [item("LINEUP", 1, "Draft Pick", 0, 0)]),
            txn("WAIVER", 2, "2026-09-03T00:00:00Z", [item("ADD", 3139477, "Patrick Mahomes", 0, 2),
                                                     item("DROP", 4432708, "Marvin Harrison Jr.", 2, 0)]),
            txn("FUTURE_ROSTER", 2, "2026-09-04T00:00:00Z", [item("LINEUP", 1, "Draft Pick", 0, 0)]),
        ])]
        self.assertEqual(tp.moves(2, captured), [
            {"week": 1, "date": "2026-09-03T00:00:00Z", "type": "add",
             "added": ["Patrick Mahomes"], "dropped": ["Marvin Harrison Jr."]}])

    def test_trade_shows_on_both_sides_with_direction(self):
        # Recorded under team 5's transaction; team 7 is the other party.
        captured = [cap(2, [txn("TRADE_ACCEPT", 5, "2026-09-10T00:00:00Z", [
            item("TRADE", 10, "Player Ten", 5, 7), item("TRADE", 20, "Player Twenty", 7, 5)])])]
        five, seven = tp.moves(5, captured), tp.moves(7, captured)
        self.assertEqual(five[0]["type"], "trade")
        self.assertEqual((five[0]["added"], five[0]["dropped"]), (["Player Twenty"], ["Player Ten"]))
        self.assertEqual((seven[0]["added"], seven[0]["dropped"]), (["Player Ten"], ["Player Twenty"]))

    def test_other_teams_moves_are_ignored(self):
        captured = [cap(1, [txn("FREEAGENT", 3, "2026-09-03T00:00:00Z", [item("ADD", 9, "Someone", 0, 3)])])]
        self.assertEqual(tp.moves(2, captured), [])

    def test_dedupes_across_captures_keeping_first_week_and_sorts_newest_first(self):
        a = txn("FREEAGENT", 2, "2026-09-03T00:00:00Z", [item("ADD", 9, "Early Add", 0, 2)])
        b = txn("FREEAGENT", 2, "2026-09-12T00:00:00Z", [item("DROP", -16034, "Texans D/ST", 2, 0)])
        rows = tp.moves(2, [cap(1, [a]), cap(2, [a, b])])
        self.assertEqual([(r["week"], r["date"]) for r in rows],
                         [(2, "2026-09-12T00:00:00Z"), (1, "2026-09-03T00:00:00Z")])
        self.assertEqual(rows[0]["dropped"], ["Texans D/ST"])

    def test_placeholder_names_resolve_from_the_name_cache(self):
        captured = [cap(1, [txn("FREEAGENT", 1, "2026-09-03T00:00:00Z", [
            item("ADD", 3, "Mark Andrews", 0, 1), item("DROP", 4242355, "Player 4242355", 1, 0),
            item("DROP", 99, "Player 99", 1, 0)])])]
        row = tp.moves(1, captured, names={"4242355": "Jake Ferguson"})[0]
        self.assertEqual(row["dropped"], ["Jake Ferguson", "Player 99"])   # uncached stays as ESPN sent it
        self.assertEqual(row["added"], ["Mark Andrews"])


def player(pid, name, slot, points, projected):
    return {"player_id": pid, "name": name, "pos": slot, "slot": slot, "points": points, "projected": projected}


def row(team_id, points, optimal, left=0.0, worst=None, starters=(), bench=()):
    return {"team_id": team_id, "points": points, "optimal_points": optimal, "points_left_on_bench": left,
            "worst_bench_call": worst, "starters": list(starters), "bench": list(bench)}


def call(benched, started, bp, sp, slot="TE"):
    return {"benched": benched, "benched_points": bp, "benched_projected": 10, "started": started,
            "started_points": sp, "started_projected": 10, "slot": slot, "gap": round(bp - sp, 2)}


class LineupIQTest(unittest.TestCase):
    def test_band_edges(self):
        self.assertEqual([tp.band(x) for x in (1.0, 0.95, 0.9499, 0.88, 0.80, 0.7999)],
                         ["A", "A", "B", "B", "C", "D"])

    def test_percent_of_optimal_worst_call_and_key(self):
        rows = [
            (1, row(6, 90, 100, left=10, worst=call("Kincaid", "Odunze", 12, 5, "FLEX"),   # gap 7 < week 2 gap 9.4
                    bench=[player(111, "Kincaid", "BENCH", 15, 10)])),
            (2, row(6, 90, 100, left=24.1, worst=call("Fannin", "Warren", 24.1, 14.7),
                    bench=[player(222, "Fannin", "BENCH", 24.1, 9.8)])),
        ]
        card = tp.lineup_iq(rows)
        self.assertEqual(card["key"], "lineup:B:222:w2")          # 180/200 = 0.90 → B; biggest gap is week 2
        self.assertEqual(card["stat"], "90% of optimal · 34.1 benched")
        self.assertEqual((card["kind"], card["level"]), ("lineup_iq", "info"))
        self.assertIn("Week 2", card["text"])
        self.assertNotIn(" B ", f" {card['title']} {card['text']} ")   # band never shown

    def test_perfect_lineups(self):
        card = tp.lineup_iq([(1, row(6, 120, 120)), (2, row(6, 100, 100))])
        self.assertEqual(card["key"], "lineup:A:none")
        self.assertEqual(card["stat"], "100% of optimal · 0.0 benched")

    def test_points_left_without_a_single_bad_call_is_not_perfect(self):
        # analyze.py leaves worst_bench_call null when the points came from, say, an empty slot.
        card = tp.lineup_iq([(2, row(6, 120, 128.5, left=8.5))])   # 93% → B
        self.assertEqual(card["key"], "lineup:B:scattered")
        # 96%: same band as a perfect team, but must not share its key (or its written copy).
        self.assertEqual(tp.lineup_iq([(2, row(6, 120, 125, left=5))])["key"], "lineup:A:scattered")
        self.assertNotIn("Perfect", card["title"])
        self.assertNotIn("best possible lineup every", card["text"])

    def test_week_in_key_changes_when_same_player_misses_a_later_week(self):
        w1 = (1, row(6, 90, 100, worst=call("Watson", "Judkins", 32.7, 7, "FLEX"), bench=[player(9, "Watson", "BENCH", 32.7, 10)]))
        w5 = (5, row(6, 90, 100, worst=call("Watson", "Cook", 40, 2, "FLEX"), bench=[player(9, "Watson", "BENCH", 40, 10)]))
        self.assertNotEqual(tp.lineup_iq([w1])["key"], tp.lineup_iq([w1, w5])["key"])

    def test_benched_name_missing_from_bench_falls_back_to_slug(self):
        rows = [(1, row(6, 70, 100, left=30, worst=call("Texans D/ST", "49ers D/ST", 30, 0, "DST")))]
        self.assertEqual(tp.lineup_iq(rows)["key"], "lineup:D:texans-d-st:w1")

    def test_negative_dst_id(self):
        rows = [(1, row(6, 70, 100, left=30, worst=call("Texans D/ST", "49ers D/ST", 30, 0, "DST"),
                        bench=[player(-16034, "Texans D/ST", "BENCH", 30, 5)]))]
        self.assertEqual(tp.lineup_iq(rows)["key"], "lineup:D:-16034:w1")

    def test_ties_keep_the_oldest_week(self):
        rows = [(1, row(6, 90, 100, worst=call("A", "B", 20, 10), bench=[player(1, "A", "BENCH", 20, 9)])),
                (2, row(6, 90, 100, worst=call("C", "D", 20, 10), bench=[player(2, "C", "BENCH", 20, 9)]))]
        self.assertEqual(tp.lineup_iq(rows)["key"], "lineup:B:1:w1")


def week(wk, teams):
    return {"week": wk, "teams": teams}


def lineup(team_id, **slot_points):
    starters = [player(i, f"{team_id}-{slot}", slot, pts, 10) for i, (slot, pts) in enumerate(slot_points.items())]
    return row(team_id, sum(slot_points.values()), 0, starters=starters)


class PositionTest(unittest.TestCase):
    def test_totals_and_ranks(self):
        facts = [week(1, [lineup(1, QB=20, TE=2), lineup(2, QB=10, TE=12)]),
                 week(2, [lineup(1, QB=20, TE=2), lineup(2, QB=10, TE=12)])]
        totals = tp.position_totals(facts)
        self.assertEqual((totals[1]["QB"], totals[2]["TE"]), (40, 24))
        ranks = tp.position_ranks(totals)
        self.assertEqual((ranks[1]["QB"], ranks[1]["TE"], ranks[2]["QB"]), (1, 2, 2))

    def test_card_key_and_weak_spot(self):
        ranks = {"QB": 1, "RB": 4, "WR": 3, "TE": 8, "FLEX": 2, "DST": 5, "K": 6}
        card, weak = tp.position_card(ranks)
        self.assertEqual((card["key"], weak), ("pos:QB1:TE8", "TE"))
        self.assertEqual(card["stat"], "Best: QB (#1) · Worst: TE (#8)")
        self.assertIn("tight end", card["text"])

    def test_ties_break_by_slot_order_and_are_stable(self):
        ranks = {"QB": 3, "RB": 1, "WR": 1, "TE": 7, "FLEX": 7, "DST": 4, "K": 5}
        for _ in range(3):
            self.assertEqual(tp.position_card(dict(ranks))[0]["key"], "pos:RB1:TE7")

    def test_same_rank_everywhere(self):
        card, weak = tp.position_card(dict.fromkeys(tp.GROUPS, 1))
        self.assertEqual((card["key"], weak), ("pos:RB1:RB1", "RB"))

    def test_tied_weak_spot_prefers_rb_and_wr_over_qb(self):
        # Waiver pickups that move the needle are mostly RBs and WRs; a tied QB is the last
        # place a manager can actually upgrade, so it loses the tie for weak spot.
        ranks = {"QB": 8, "RB": 3, "WR": 8, "TE": 2, "FLEX": 4, "DST": 5, "K": 6}
        self.assertEqual(tp.position_card(ranks)[1], "WR")


class VoiceCopyTest(unittest.TestCase):
    """Copy that has to stay true for every team, not just the example ones (voice-check)."""

    def test_tie_joke_only_when_first_everywhere(self):
        top, _ = tp.position_card(dict.fromkeys(tp.GROUPS, 1))
        bottom, _ = tp.position_card(dict.fromkeys(tp.GROUPS, 8))
        self.assertIn("its own kind of flex", top["text"])
        self.assertNotIn("flex", bottom["text"])
        self.assertIn("8th", bottom["text"])

    def test_last_place_group_says_so(self):
        card, _ = tp.position_card({"QB": 1, "RB": 4, "WR": 3, "TE": 8, "FLEX": 2, "DST": 5, "K": 6})
        self.assertIn("8th, also known as last", card["text"])
        card, _ = tp.position_card({"QB": 1, "RB": 4, "WR": 3, "TE": 7, "FLEX": 2, "DST": 5, "K": 6})
        self.assertNotIn("also known as last", card["text"])
        self.assertIn("rank 7th, so", card["text"])

    def test_flex_reads_mid_sentence_in_lineup_iq(self):
        rows = [(1, row(6, 70, 100, left=30, worst=call("Swift", "Egbuka", 32.4, 11.3, "FLEX"),
                        bench=[player(5, "Swift", "BENCH", 32.4, 9)]))]
        self.assertIn("at flex, the wild-card spot, while Swift", tp.lineup_iq(rows)["text"])

    def test_dst_gets_its_not_his(self):
        rows = [(w, row(1, 0, 0, starters=[player(-16034, "Texans D/ST", "DST", 2, 8)])) for w in (1, 2)]
        self.assertIn("Texans D/ST is coming up 6.0 a game short of its projection", tp.projection_card(rows)["text"])

    def test_band_d_title_makes_no_literal_claim(self):
        self.assertNotIn("outscoring", tp.LINEUP_TITLE["D"])


class ProjectionTest(unittest.TestCase):
    def rows(self):
        return [(1, row(1, 0, 0, starters=[player(10, "Hot", "WR", 20, 10), player(20, "Cold", "RB", 2, 12),
                                           player(30, "Once", "TE", 30, 5)])),
                (2, row(1, 0, 0, starters=[player(10, "Hot", "WR", 16, 10), player(20, "Cold", "RB", 4, 12)]))]

    def test_delta_over_and_players(self):
        card = tp.projection_card(self.rows())
        # (10+6) + (-10-8) + 25 = +23
        self.assertEqual(card["key"], "proj:over:10:20")
        self.assertEqual(card["stat"], "+23.0 vs projections")
        self.assertNotIn("Once", card["text"])         # one start: not eligible

    def test_under(self):
        rows = [(1, row(1, 0, 0, starters=[player(20, "Cold", "RB", 2, 12)]))]
        card = tp.projection_card(rows)
        self.assertEqual((card["key"], card["stat"]), ("proj:under:none:none", "-10.0 vs projections"))

    def test_null_projection_is_skipped(self):
        rows = self.rows() + [(3, row(1, 0, 0, starters=[player(20, "Cold", "RB", 40, None)]))]
        self.assertEqual(tp.projection_card(rows)["stat"], "+23.0 vs projections")

    def test_single_eligible_player_has_no_bottom(self):
        rows = [(w, row(1, 0, 0, starters=[player(10, "Hot", "WR", 20, 10)])) for w in (1, 2)]
        self.assertEqual(tp.projection_card(rows)["key"], "proj:over:10:none")


class AuditsTest(unittest.TestCase):
    def test_no_weeks(self):
        self.assertEqual(tp.audits([], [1, 2]), {1: {"cards": [], "weak_spot": None},
                                                 2: {"cards": [], "weak_spot": None}})

    def test_three_cards_in_order_and_stable_keys(self):
        def facts():
            t1 = lineup(1, QB=20, TE=2)
            t1.update(points=22, optimal_points=22)
            t2 = lineup(2, QB=10, TE=12)
            t2.update(points=22, optimal_points=30, points_left_on_bench=8)
            return [week(1, [t1, t2])]
        a, b = tp.audits(facts(), [1, 2]), tp.audits(facts(), [1, 2])
        self.assertEqual([c["kind"] for c in a[1]["cards"]], ["lineup_iq", "position", "projection"])
        self.assertEqual([c["key"] for c in a[1]["cards"]], [c["key"] for c in b[1]["cards"]])
        # Team 1 is 1st at QB and, on the team-id tie-break, at every empty group; 2nd only at TE.
        self.assertEqual(a[1]["weak_spot"], "TE")


if __name__ == "__main__":
    unittest.main()
