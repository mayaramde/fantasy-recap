"""The Coach lineup's per-player outlook: form from earlier weeks, a start/swap verdict, and chips.

Everything is built from numbers on the capture, so these tests pin the arithmetic and the bar a
swap has to clear (SWAP_MIN, the same one team_advice's swap cards use)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
import build  # noqa: E402


def pl(pid, name, pos="WR", slot="WR", proj=10.0, pts=0.0, st=None, **kw):
    return {"player_id": pid, "name": name, "pos": pos, "slot": slot, "projected": proj, "points": pts,
            "injury_status": st, **kw}


def ctx_for(starters, bench, form=None, stats=None, locked=(), bye=(), projected=True, can_change=True):
    def bench_best(slot):
        return max((b for b in bench if b["pos"] in build.SLOT_OK[slot] and b.get("injury_status") not in build.SIDELINED),
                   key=build._proj, default=None)
    return {"locked": lambda p: p["player_id"] in locked, "on_bye": lambda p: p["player_id"] in bye,
            "projected": projected, "can_change": can_change, "starters": starters, "bench_best": bench_best,
            "form": form or {}, "stats": stats or {}}


def cap(week, rows_home):
    return {"week": week, "matchups": [{"home": {"lineup": rows_home}, "away": None}]}


class PlayerForm(unittest.TestCase):
    def test_collects_played_games_oldest_first(self):
        hist = [cap(2, [dict(pl(1, "A"), played=True, points=9.0)]), cap(1, [dict(pl(1, "A"), played=True, points=20.5)])]
        self.assertEqual(build.player_form(hist), {1: [20.5, 9.0]})

    def test_skips_ir_unplayed_and_unexplained_zeros(self):
        rows = [dict(pl(1, "IR guy", slot="IR"), played=True, points=0),
                dict(pl(2, "Bye", slot="BENCH"), played=False, points=0),
                dict(pl(3, "Bench zero", slot="BENCH"), played=True, points=0),
                dict(pl(4, "Out", st="OUT"), played=True, points=0),
                dict(pl(5, "Starter donut"), played=True, points=0)]
        self.assertEqual(build.player_form([cap(1, rows)]), {5: [0]})


class Verdicts(unittest.TestCase):
    def test_start_with_a_close_bench_option(self):
        a, b = pl(1, "Lawrence", "QB", "QB", 21.5), pl(2, "Stroud", "QB", "BN", 18.3)
        v = build.player_verdict(a, True, ctx_for([a], [b]))
        self.assertEqual((v["label"], v["level"]), ("Start", "go"))
        self.assertIn("Stroud", v["reason"])
        self.assertIn("3.2 behind", v["reason"])

    def test_swap_needs_the_full_gap(self):
        a, b = pl(1, "Starter", proj=10.0), pl(2, "Bench", proj=12.0)
        self.assertEqual(build.player_verdict(a, True, ctx_for([a], [b]))["label"], "Consider swap")
        b["projected"] = 11.9
        self.assertEqual(build.player_verdict(a, True, ctx_for([a], [b]))["label"], "Start")

    def test_bench_player_mirrors_the_swap(self):
        a, b = pl(1, "Starter", proj=10.0), pl(2, "Bench", slot="BN", proj=13.0)
        v = build.player_verdict(b, False, ctx_for([a], [b]))
        self.assertEqual(v["label"], "Consider swap")
        self.assertIn("3.0 higher than Starter", v["reason"])

    def test_bench_player_holds_when_not_worth_a_move(self):
        a, b = pl(1, "Starter", proj=10.0), pl(2, "Bench", slot="BN", proj=9.0)
        v = build.player_verdict(b, False, ctx_for([a], [b]))
        self.assertEqual((v["label"], v["level"]), ("Hold", "info"))
        self.assertIn("1.0 ahead", v["reason"])

    def test_injured_or_bye_starter_is_fix_now(self):
        a = pl(1, "Hurt", st="OUT")
        self.assertEqual(build.player_verdict(a, True, ctx_for([a], []))["level"], "now")
        c = pl(3, "Bye")
        self.assertEqual(build.player_verdict(c, True, ctx_for([c], [], bye={3}))["label"], "Fix now")

    def test_questionable_starter_is_a_watch(self):
        a = pl(1, "Maybe", st="QUESTIONABLE")
        self.assertEqual(build.player_verdict(a, True, ctx_for([a], []))["label"], "Watch")

    def test_no_verdict_once_the_game_has_started_or_on_ir(self):
        a = pl(1, "Playing")
        self.assertIsNone(build.player_verdict(a, True, ctx_for([a], [], locked={1})))
        ir = pl(2, "IR", slot="IR")
        self.assertIsNone(build.player_verdict(ir, False, ctx_for([], [ir])))

    def test_no_projections_means_no_comparison(self):
        a, b = pl(1, "Starter", proj=0), pl(2, "Bench", slot="BN", proj=0)
        ctx = ctx_for([a], [b], projected=False)
        self.assertIsNone(build.player_verdict(a, True, ctx))
        self.assertIsNone(build.player_verdict(b, False, ctx))


class ReviewRegressions(unittest.TestCase):
    def test_bench_player_is_checked_against_every_open_spot(self):
        rb1 = pl(1, "RB One", "RB", "RB", 8.0)
        rb2 = pl(2, "RB Two", "RB", "RB", 7.0)
        flex = pl(3, "Flex WR", "WR", "FLEX", 5.0)
        b = pl(4, "RB B", "RB", "BN", 13.0)
        c = pl(5, "WR C", "WR", "BN", 14.0)
        ctx = ctx_for([rb1, rb2, flex], [b, c])
        # RB1's own card says swap in B, so B's card has to say the same, not "isn't worth a move".
        self.assertEqual(build.player_verdict(rb1, True, ctx)["label"], "Consider swap")
        v = build.player_verdict(b, False, ctx)
        self.assertEqual(v["label"], "Consider swap")
        self.assertIn("6.0 higher than RB Two", v["reason"])
        self.assertNotIn("worth a move", v["reason"])

    def test_questionable_starter_is_not_a_swap_target(self):
        a, b = pl(1, "Maybe", st="QUESTIONABLE", proj=8.0), pl(2, "Bench", slot="BN", proj=14.0)
        v = build.player_verdict(b, False, ctx_for([a], [b]))
        self.assertEqual(v["label"], "Hold")

    def test_swap_bar_uses_the_printed_numbers(self):
        # 10.04 and 11.99 print as 10.0 and 12.0: a printed gap of 2.0 clears the bar.
        a, b = pl(1, "Starter", proj=10.04), pl(2, "Bench", slot="BN", proj=11.99)
        v = build.player_verdict(a, True, ctx_for([a], [b]))
        self.assertEqual(v["label"], "Consider swap")
        self.assertIn("2.0 higher (12.0 to 10.0)", v["reason"])
        # and a tiny lead never prints as "only 0.0 higher"
        c, d = pl(3, "Starter", proj=10.04), pl(4, "Bench", slot="BN", proj=10.01)
        self.assertNotIn("0.0 higher", build.player_verdict(c, True, ctx_for([c], [d]))["reason"])

    def test_defense_verdicts_say_it(self):
        d = pl(1, "Jaguars D/ST", "DST", "DST")
        v = build.player_verdict(d, True, ctx_for([d], [], bye={1}))
        self.assertTrue(v["reason"].startswith("Its NFL team"))

    def test_form_skips_unfinished_captures_and_rows_without_ids(self):
        done = cap(1, [dict(pl(1, "A"), played=True, points=10.0), {"slot": "WR", "played": True, "points": 3}])
        mid = dict(cap(2, [dict(pl(1, "A"), played=True, points=4.0)]), complete=False)
        self.assertEqual(build.player_form([done, mid]), {1: [10.0]})

    def test_average_rounds_half_up(self):
        p = pl(1, "A")
        form = build._form_summary(p, {"form": {1: [10.0, 10.05, 10.05]}})
        self.assertEqual(form["avg"], 10.0)
        form = build._form_summary(p, {"form": {1: [0.25, 0.0, 0.0]}})   # 0.0833 -> 0.1
        self.assertEqual(form["avg"], 0.1)


class Chips(unittest.TestCase):
    def test_form_projection_and_role_chips(self):
        p = pl(7, "Wide Out", proj=21.5)
        ctx = ctx_for([p], [], form={7: [10.0, 21.0, 9.2, 24.1]},
                      stats={"7": {"games": 4, "rec_tar": 33, "rec_rec": 22, "rec_yds": 300, "rec_tds": 2}})
        chips = {c["label"]: c["value"] for c in build.player_chips(p, ctx)}
        self.assertEqual(chips["Avg, 4 games"], "16.1")
        self.assertEqual(chips["Last 3"], "21.0, 9.2, 24.1")
        self.assertEqual(chips["Proj vs avg"], "+5.4")
        self.assertEqual(chips["Targets / game"], "8.3")
        self.assertEqual(chips["Rec yds / game"], "75.0")

    def test_short_history_shows_no_form(self):
        p = pl(7, "Rookie")
        self.assertEqual(build.player_chips(p, ctx_for([p], [], form={7: [5.0, 6.0]})), [])

    def test_no_projection_chip_after_kickoff(self):
        p = pl(7, "Wide Out", proj=21.5)
        labels = [c["label"] for c in build.player_chips(p, ctx_for([p], [], form={7: [1.0, 2.0, 3.0]}, locked={7}))]
        self.assertNotIn("Proj vs avg", labels)


class FormBlurb(unittest.TestCase):
    form = {"n": 8, "avg": 17.4}

    def test_bands(self):
        p = pl(2, "X", proj=21.5)
        self.assertIn("4.1 above his 17.4 average", build.form_blurb(p, self.form, 4.1, 0))
        self.assertIn("4.1 under", build.form_blurb(p, self.form, -4.1, 0))
        self.assertIn("right in line", build.form_blurb(p, self.form, 0.5, 0))

    def test_defense_reads_as_it(self):
        d = pl(3, "Jaguars D/ST", "DST", "DST", proj=8.5)
        self.assertIn("ESPN has it at 8.5", build.form_blurb(d, self.form, 0.5, 0, dst=True))


class ZeroProjection(unittest.TestCase):
    def test_a_zero_projection_gets_no_comparison(self):
        a, b = pl(1, "Starter", proj=10.0), pl(2, "Nothing", slot="BN", proj=0.0)
        ctx = ctx_for([a], [b], form={2: [10.0, 11.0, 12.0]})
        self.assertIsNone(build.player_verdict(b, False, ctx))
        self.assertNotIn("Proj vs avg", [c["label"] for c in build.player_chips(b, ctx)])


if __name__ == "__main__":
    unittest.main()
