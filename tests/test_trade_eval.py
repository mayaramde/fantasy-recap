#!/usr/bin/env python3
"""Tests for scripts/trade_eval.py (the Coach's trade scoring), playoffs.trade_odds(), and the
site's handling of trade cards (site/build.py's _valid_trade and live_trades).

Hand-built rosters only. Every player has a flat rest-of-season rate and nobody has a bye unless a
test says so, so each lineup is checkable by eye against league.json's slots: QB, RB, RB, WR, WR,
TE, FLEX (RB/WR/TE), DST, K, plus seven bench spots.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "site"))
import build  # noqa: E402
import playoffs as po  # noqa: E402
import trade_eval as te  # noqa: E402

WEEK = 5
SPAN = te.NFL_LAST_WEEK - WEEK + 1   # games left for a player with no bye


def player(pid, pos, rate, slot="BENCH", injury=None, pro=1):
    # Letters only: FantasyPros names are matched with digits and punctuation stripped
    return {"player_id": pid, "name": "Player " + "".join(chr(97 + int(d)) for d in str(pid)), "pos": pos, "pro_team_id": pro, "slot": slot,
            "injury_status": injury, "projected": rate}


def ros_rows(players):
    """FantasyPros-shaped rest-of-season rows giving each player exactly his `projected` rate."""
    return [{"name": p["name"], "position": p["pos"], "team": "ATL",
             "stats": {"points_ppr": p["projected"] * SPAN}} for p in players]


def lineup(base, extra=()):
    """A full starting lineup (ids base..base+8) worth 10 a week at every slot, plus `extra`."""
    starters = [player(base + i, pos, 10, slot) for i, (pos, slot) in enumerate(
        [("QB", "QB"), ("RB", "RB"), ("RB", "RB"), ("WR", "WR"), ("WR", "WR"), ("TE", "TE"),
         ("WR", "FLEX"), ("DST", "DST"), ("K", "K")])]
    return starters + list(extra)


def league(rosters, standings=None, opp_now=None, deadline=None):
    """A trade_eval.League built in memory, skipping the disk reads in __init__."""
    lg = object.__new__(te.League)
    lg.week = WEEK
    lg.rosters = rosters
    lg.opp_now, lg.opp_next = opp_now or {}, {}
    lg.schedule = {}
    players = [p for r in rosters.values() for p in r]
    lg.vals = te.Values(players, te.ros_table(ros_rows(players)), {}, WEEK)
    lg.standings, lg.weeks_played = standings or [], [1, 2, 3, 4] if standings else []
    lg.sims, lg._base, lg._now = 400, None, {}
    lg.reg_weeks = [w for w in lg.vals.weeks if w <= 14]
    lg.deadline = deadline
    return lg


def odds_pair(one, two):
    """A trade_odds()-shaped result for teams 1 and 2: (playoff before, after, title before, after)."""
    return {"before": {1: {"playoff": one[0], "title": one[2]}, 2: {"playoff": two[0], "title": two[2]}},
            "after": {1: {"playoff": one[1], "title": one[3]}, 2: {"playoff": two[1], "title": two[3]}}}


# Team 1 is two good RBs deep on the bench and starts a weak TE; team 2 is the mirror image.
TEAM_1 = lineup(100, [player(150, "RB", 14), player(151, "RB", 4)])
TEAM_1[5]["projected"] = 3                           # her TE scores 3 a week
TEAM_2 = lineup(200, [player(250, "TE", 13), player(251, "TE", 4)])
TEAM_2[1]["projected"] = 4                           # her RB1 scores 4 a week
FAIR_SWAP = dict(team_id=1, partner_id=2, give=[150], get=[250])


class LineupMath(unittest.TestCase):
    def test_best_lineup_plus_a_share_of_the_bench(self):
        lg = league({1: TEAM_1, 2: TEAM_2})
        # nine starters, the TE at 3, the bench RBs at 14 and 4: the 14 moves into the FLEX ahead of a 10 WR
        best = 8 * 10 + 3 + 14 - 10
        bench = 10 + 4                                 # the displaced WR and the spare RB
        self.assertAlmostEqual(te.team_week(TEAM_1, lg.vals, WEEK), best + te.BENCH_SHARE * bench)

    def test_bye_week_and_out_this_week_count_zero(self):
        p = player(1, "WR", 10, injury="OUT", pro=7)
        vals = te.Values([p], te.ros_table(ros_rows([p])), {WEEK + 1: {1, 2}}, WEEK)
        self.assertEqual(vals.get(p, WEEK), 0.0)       # ruled out this week
        self.assertEqual(vals.get(p, WEEK + 1), 0.0)   # team 7 isn't on that week's slate
        self.assertGreater(vals.get(p, WEEK + 2), 10)  # the bye spreads his total over one game fewer

    def test_only_a_growing_roster_cuts_and_never_the_new_player(self):
        full = TEAM_1 + [player(160 + i, "WR", 1 + i) for i in range(te.ROSTER_MAX - len(TEAM_1))]
        incoming = [player(900, "K", 0.5)]
        lg = league({1: full, 2: incoming})
        _, cut = te.after_trade(full, {150}, incoming, lg.vals, {900})
        self.assertIsNone(cut)                         # one out, one in
        new, cut = te.after_trade(full, set(), incoming, lg.vals, {900})
        self.assertEqual(cut["player_id"], 160)        # the 1-a-week WR, not the 0.5 K she just got
        self.assertEqual(len(new), te.ROSTER_MAX)


class Rules(unittest.TestCase):
    def setUp(self):
        self.lg = league({1: TEAM_1, 2: TEAM_2})

    def rules(self, **kw):
        _, fails = self.lg.quick(**kw)
        return {f["rule"] for f in fails}

    def test_fair_swap_helps_both_lineups(self):
        res, fails = self.lg.quick(**FAIR_SWAP)
        self.assertEqual(fails, [])
        self.assertGreaterEqual(res["you"]["blend"], te.MIN_GAIN)
        self.assertGreaterEqual(res["them"]["blend"], te.MIN_GAIN)

    def test_rule_1_and_3_one_sided_trade(self):
        # her spare 4-a-week RB for their 13-a-week TE helps her and costs them
        self.assertTrue({1, 3} <= self.rules(team_id=1, partner_id=2, give=[151], get=[250]))

    def test_rule_6_lopsided_value(self):
        self.assertIn(6, self.rules(team_id=1, partner_id=2, give=[150], get=[251]))

    def test_rule_7_nobody_hurt_changes_hands(self):
        hurt = [dict(p, injury_status="INJURY_RESERVE") if p["player_id"] == 250 else p for p in TEAM_2]
        lg = league({1: TEAM_1, 2: hurt})
        self.assertIn(7, {f["rule"] for f in lg.quick(**FAIR_SWAP)[1]})

    def test_rule_9_sizes(self):
        self.assertIn(9, self.rules(team_id=1, partner_id=2, give=[150, 151], get=[250, 251]))

    def test_rule_10_deadline(self):
        lg = league({1: TEAM_1, 2: TEAM_2}, deadline=WEEK - 1)
        self.assertIn(10, {f["rule"] for f in lg.quick(**FAIR_SWAP)[1]})

    def test_unknown_player_is_not_scored(self):
        res, fails = self.lg.quick(team_id=1, partner_id=2, give=[999], get=[250])
        self.assertIsNone(res)
        self.assertEqual(fails[0]["rule"], 0)


class OddsRules(unittest.TestCase):
    """Rules 4 and 5 read the playoff simulation; here it's replaced by fixed numbers."""

    def finish(self, sim, opp_now=None):
        lg = league({1: TEAM_1, 2: TEAM_2}, opp_now=opp_now)
        lg.odds = lambda shift: sim
        lg._base = sim["before"]
        res, fails = lg.quick(**FAIR_SWAP)
        return lg.finish(res, fails)

    def test_passes_when_both_go_up(self):
        r = self.finish(odds_pair((0.95, 0.97, 0.3, 0.32), (0.05, 0.06, 0.0, 0.0)))
        self.assertTrue(r["pass"], r["failures"])
        self.assertFalse(r["flags"]["rival"])

    def test_rule_5_proposer_must_gain(self):
        r = self.finish(odds_pair((0.95, 0.95, 0.3, 0.3), (0.05, 0.08, 0.0, 0.0)))
        self.assertIn(5, {f["rule"] for f in r["failures"]})

    def test_rule_5_partner_may_not_lose(self):
        r = self.finish(odds_pair((0.95, 0.97, 0.3, 0.32), (0.05, 0.03, 0.0, 0.0)))
        self.assertIn(5, {f["rule"] for f in r["failures"]})

    def test_rule_4_bubble_rival_may_not_gain_more(self):
        r = self.finish(odds_pair((0.5, 0.52, 0.1, 0.11), (0.45, 0.55, 0.1, 0.12)))
        self.assertTrue(r["flags"]["rival"])
        self.assertIn(4, {f["rule"] for f in r["failures"]})

    def test_rule_2_this_weeks_opponent_is_flagged_and_ranked_last(self):
        sim = odds_pair((0.95, 0.97, 0.3, 0.32), (0.05, 0.06, 0.0, 0.0))
        playing = self.finish(sim, opp_now={1: 2, 2: 1})
        not_playing = self.finish(sim)
        self.assertTrue(playing["flags"]["plays_this_week"] and playing["flags"]["rival"])
        self.assertLess(te.rank(not_playing), te.rank(playing))


class TradeOdds(unittest.TestCase):
    def standings(self):
        rows = []
        for t in range(1, 9):
            weekly = [{"week": w, "points": 100.0 + 2 * t + w, "opponent_id": t % 8 + 1, "result": "W" if t <= 4 else "L"}
                      for w in range(1, 5)]
            rows.append({"team_id": t, "wins": 4 if t <= 4 else 0, "losses": 0 if t <= 4 else 4, "ties": 0,
                         "points_for": sum(g["points"] for g in weekly), "weekly": weekly})
        return rows

    def test_no_shift_changes_nothing_and_a_boost_helps(self):
        league_cfg = {"playoffs": {"teams": 4, "regular_season_weeks": 14, "first_round_week": 15, "championship_weeks": 2}}
        same = po.trade_odds(self.standings(), [1, 2, 3, 4], league_cfg, {}, n_sims=500)
        self.assertEqual(same["before"], same["after"])
        boosted = po.trade_odds(self.standings(), [1, 2, 3, 4], league_cfg, {5: 30.0}, n_sims=500)
        self.assertGreater(boosted["after"][5]["playoff"], boosted["before"][5]["playoff"])

    def test_nothing_to_say_after_the_regular_season(self):
        league_cfg = {"playoffs": {"teams": 4, "regular_season_weeks": 4, "first_round_week": 5}}
        self.assertIsNone(po.trade_odds(self.standings(), [1, 2, 3, 4], league_cfg, {}, n_sims=100))


def card(give=150, get=250, partner=2):
    side = {"near": 1.5, "playoff": [0.5, 0.55], "title": [0.1, 0.12]}
    return {"kind": "trade", "level": "watch", "title": "t", "text": "x", "pos": "TE",
            "trade": {"partner_id": partner, "give": [{"id": give, "name": "A"}], "get": [{"id": get, "name": "B"}],
                      "you": side, "them": side}}


class SiteCards(unittest.TestCase):
    def teams(self, injury=None):
        def facts(tid, roster):
            return {"team_id": tid, "starters": [p for p in roster if p["slot"] != "BENCH"],
                    "bench": [dict(p, injury_status=injury) if p["player_id"] == 250 else p
                              for p in roster if p["slot"] == "BENCH"]}
        return [facts(1, TEAM_1), facts(2, TEAM_2)]

    def test_a_trade_card_needs_its_numbers(self):
        self.assertTrue(build._valid_fp_card(card()))
        lead = card()
        del lead["trade"]
        self.assertFalse(build._valid_fp_card(lead))   # an unevaluated lead
        waiver = {"kind": "waiver", "level": "info", "title": "t", "text": "x"}
        self.assertTrue(build._valid_fp_card(waiver))  # other kinds are unchanged

    def test_stale_trades_disappear(self):
        rows = [{"team_id": 1, "roster_ideas": [card(), card(give=999), card(get=999)]}]
        kept = build.live_trades(rows, self.teams())[0]["roster_ideas"]
        self.assertEqual(len(kept), 1)                  # the two naming a player who isn't there go
        rows = [{"team_id": 1, "roster_ideas": [card()]}]
        self.assertEqual(build.live_trades(rows, self.teams(injury="OUT"))[0]["roster_ideas"], [])


if __name__ == "__main__":
    unittest.main()
