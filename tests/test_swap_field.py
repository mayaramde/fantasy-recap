"""The structured `swap` field on the Coach's lineup fix cards (site/build.py team_advice).

Every "now" card of kind out, bye or swap carries {out, in, gain}, so the Game day swap card can
show who sits, who starts and the gain without parsing the card's text. Hand-built rosters only, so
every expected number is checkable by eye."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "site"))
import build  # noqa: E402

FIX_KINDS = {"out", "bye", "swap"}


def pl(pid, name, pos, slot, proj, st=None, state="pre"):
    return {"player_id": pid, "name": name, "pos": pos, "slot": slot, "projected": proj, "points": 0.0,
            "injury_status": st, "game_state": state, "played": False}


def team(starters, bench):
    return {"team_id": 5, "manager": "Maya", "team_name": "Test", "opponent_id": 1,
            "starters": starters, "bench": bench, "projected": sum(p["projected"] or 0 for p in starters)}


def advise(starters, bench, projected=True):
    return build.team_advice(team(starters, bench), {}, None, True, projected=projected)["items"]


def only(items, kind):
    found = [it for it in items if it["kind"] == kind]
    assert len(found) == 1, found
    return found[0]


class SwapField(unittest.TestCase):
    def test_injured_starter_with_a_backup(self):
        s = pl(10, "C.J. Stroud", "QB", "QB", 21.45, st="OUT")
        r = pl(11, "Bench QB", "QB", "BE", 17.3, st="QUESTIONABLE")
        it = only(advise([s], [r]), "out")
        self.assertEqual(it["swap"], {
            "out": {"player_id": 10, "name": "C.J. Stroud", "projected": 21.45, "slot": "QB", "status": "OUT"},
            "in": {"player_id": 11, "name": "Bench QB", "projected": 17.3, "status": "QUESTIONABLE"},
            "gain": -4.2})

    def test_bye_starter_with_no_backup(self):
        s = pl(20, "Bye WR", "WR", "WR", 12.0, state=None)   # no game state on a known slate = bye
        qb = pl(21, "Playing QB", "QB", "QB", 18.0)        # someone still to play, so the week can change
        it = only(advise([qb, s], []), "bye")
        self.assertEqual(it["swap"]["out"],
                         {"player_id": 20, "name": "Bye WR", "projected": 12.0, "slot": "WR", "status": "bye"})
        self.assertIsNone(it["swap"]["in"])
        self.assertIsNone(it["swap"]["gain"])

    def test_straight_upgrade_swap_matches_the_card(self):
        s = pl(30, "Starter RB", "RB", "RB", 8.26)
        b = pl(31, "Bench RB", "RB", "BE", 14.71)
        it = only(advise([s], [b]), "swap")
        self.assertEqual(it["swap"]["out"],
                         {"player_id": 30, "name": "Starter RB", "projected": 8.26, "slot": "RB", "status": None})
        self.assertEqual(it["swap"]["in"], {"player_id": 31, "name": "Bench RB", "projected": 14.71, "status": None})
        self.assertEqual(it["swap"]["gain"], round(it["gain"], 1))
        self.assertEqual(it["swap"]["gain"], 6.5)
        self.assertEqual(it["stat"], f"+{it['swap']['gain']:.1f} projected")

    def test_gain_half_cases_agree_with_the_stat_pill(self):
        # Gains that sit on a .x5 boundary in decimal are where two roundings could split.
        for lo, hi in ((10.0, 12.05), (10.0, 12.15), (7.1, 9.35), (3.33, 5.38)):
            it = only(advise([pl(1, "S", "WR", "WR", lo)], [pl(2, "B", "WR", "BE", hi)]), "swap")
            self.assertEqual(it["swap"]["gain"], round(it["gain"], 1))
            self.assertEqual(it["stat"], f"+{it['swap']['gain']:.1f} projected")

    def test_tiny_negative_gap_is_zero_not_minus_zero(self):
        s = pl(70, "Hurt WR", "WR", "WR", 9.04, st="OUT")
        r = pl(71, "Bench WR", "WR", "BE", 9.0)
        gain = only(advise([s], [r]), "out")["swap"]["gain"]
        self.assertEqual(gain, 0.0)
        self.assertEqual(str(gain), "0.0")

    def test_unprojected_week_has_no_numbers(self):
        s = pl(40, "Hurt TE", "TE", "TE", None, st="INJURY_RESERVE")
        r = pl(41, "Bench TE", "TE", "BE", None)
        it = only(advise([s], [r], projected=False), "out")
        self.assertIsNone(it["swap"]["out"]["projected"])
        self.assertIsNone(it["swap"]["in"]["projected"])
        self.assertIsNone(it["swap"]["gain"])
        self.assertEqual(it["swap"]["out"]["status"], "INJURY_RESERVE")

    def test_only_fix_kinds_carry_it(self):
        starters = [pl(50, "Iffy QB", "QB", "QB", 20.0, st="QUESTIONABLE"),
                    pl(51, "Zero TE", "TE", "TE", 0.0),
                    pl(52, "Out WR", "WR", "WR", 9.0, st="OUT")]
        bench = [pl(53, "Bench QB", "QB", "BE", 15.0)]
        items = advise(starters, bench)
        kinds = {it["kind"] for it in items}
        self.assertTrue({"watch", "hole", "out", "empty"} <= kinds, kinds)
        for it in items:
            self.assertEqual("swap" in it, it["kind"] in FIX_KINDS and it["level"] == "now", it["kind"])

    def test_written_copy_keeps_the_field(self):
        s, r = pl(60, "Hurt RB", "RB", "RB", 10.0, st="OUT"), pl(61, "Bench RB", "RB", "BE", 9.0)
        items = advise([s], [r])
        key = only(items, "out")["key"]
        written = {key: {"title": "Written title", "text": "Written text."}}
        it = only(build.team_advice(team([s], [r]), {}, None, True, written=written)["items"], "out")
        self.assertTrue(it.get("written"))
        self.assertEqual(it["swap"]["in"]["player_id"], 61)


class LiveRefresh(unittest.TestCase):
    """/api/live (api/live.py) rebuilds LIVE.advice with build.live_payload on every refresh. Run that
    same call on a committed capture turned into a not-yet-played week, the way tests/hub_preview.py
    does, so only the ESPN fetch is swapped out."""

    def test_field_survives_live_payload(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import analyze
        import hub_preview
        _, captured, _, _, _ = build.load_inputs(build.LEAGUE["season"])
        history = [e for _, e in captured]
        nxt = hub_preview.sample_flags(hub_preview.upcoming(history[-1]))
        payload = build.live_payload(analyze.analyze(nxt, history + [nxt]), nxt, history[-1], history=history)
        items = [it for t in payload["advice"] for it in t["items"]]
        fixes = [it for it in items if it["kind"] in FIX_KINDS and it["level"] == "now"]
        # hub_preview's sample flags put an RB on OUT and a D/ST on a bye; if that ever changes, say so
        # here rather than quietly testing less.
        self.assertTrue({"out", "bye"} <= {it["kind"] for it in fixes}, [it["kind"] for it in fixes])
        for it in items:
            self.assertEqual("swap" in it, it in fixes, it["kind"])
        for it in fixes:
            self.assertEqual(set(it["swap"]), {"out", "in", "gain"})
            if it["kind"] == "swap":
                self.assertEqual(it["swap"]["gain"], round(it["gain"], 1))


if __name__ == "__main__":
    unittest.main()
