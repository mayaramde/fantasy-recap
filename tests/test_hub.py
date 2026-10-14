#!/usr/bin/env python3
"""Tests for the Week hub's build-side data in site/build.py: the league wire, the trades it reads off
rosters, the headlines, and what gets baked into live["hub"].

Hand-built captures only: two teams' worth of roster is enough to say everything the wire has to get
right. Team ids are the league's real ones because wire() names managers from league.json."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
import build  # noqa: E402

NAME = {t["team_id"]: t["manager"].split(" (")[0] for t in build.LEAGUE["teams"]}


def player(pid, name, slot="BENCH", pos="WR", pro_team_id=2):
    return {"player_id": pid, "name": name, "slot": slot, "pos": pos, "pro_team_id": pro_team_id}


def capture(week, rosters, transactions=(), captured_at="2026-10-07T12:00:00.000Z"):
    """rosters: {team_id: [player, ...]}, paired off into matchups in the order given."""
    ids = list(rosters)
    return {"week": week, "captured_at": captured_at, "transactions": list(transactions),
            "matchups": [{"home": {"team_id": a, "lineup": rosters[a]}, "away": {"team_id": b, "lineup": rosters[b]}}
                         for a, b in zip(ids[::2], ids[1::2])]}


def tx(kind, team, date, *items):
    return {"type": kind, "team_id": team, "date": date, "bid": 0, "items": list(items)}


def item(kind, pid, name, frm=0, to=0, from_slot=None, to_slot=None):
    return {"type": kind, "player_id": pid, "name": name, "from_team_id": frm, "to_team_id": to,
            "from_slot": from_slot, "to_slot": to_slot}


BEFORE = capture(3, {3: [player(1, "Ann Alpha"), player(2, "Bea Bravo")],
                     4: [player(3, "Cy Charlie"), player(4, "Di Delta")]})


class WireTest(unittest.TestCase):
    def test_pickups_and_drops_become_moves(self):
        cap = capture(4, BEFORE_ROSTERS(), [
            tx("WAIVER", 3, "2026-10-06T07:43:00.000Z", item("ADD", 9, "New Guy", to=3), item("DROP", 2, "Bea Bravo", frm=3)),
            tx("ROSTER", 4, "2026-10-05T10:00:00.000Z", item("DROP", 4, "Di Delta", frm=4)),
            tx("FREEAGENT", 4, "2026-10-05T11:00:00.000Z", item("ADD", 8, "Free Guy", to=4))])
        got = build.wire(cap, [BEFORE])
        self.assertEqual([e["kind"] for e in got], ["move", "move", "move"])
        self.assertEqual(got[0], {"date": "2026-10-06T07:43:00.000Z", "team_id": 3, "manager": NAME[3], "kind": "move",
                                  "added": ["New Guy"], "dropped": ["Bea Bravo"], "waiver": True})
        self.assertEqual((got[2]["added"], got[2]["dropped"], got[2]["waiver"]), ([], ["Di Delta"], False))

    def test_newest_first_and_a_week_back_only(self):
        cap = capture(4, BEFORE_ROSTERS(), [
            tx("FREEAGENT", 3, "2026-09-30T11:59:00.000Z", item("ADD", 7, "Too Old", to=3)),
            tx("FREEAGENT", 3, "2026-09-30T12:01:00.000Z", item("ADD", 8, "Just In", to=3)),
            tx("FREEAGENT", 4, "2026-10-07T09:00:00.000Z", item("ADD", 9, "Latest", to=4))])
        self.assertEqual([e["added"] for e in build.wire(cap)], [["Latest"], ["Just In"]])

    def test_the_week_before_is_read_too(self):
        old = capture(3, BEFORE_ROSTERS(), [tx("FREEAGENT", 3, "2026-10-02T09:00:00.000Z", item("ADD", 7, "Last Week", to=3))])
        cap = capture(4, BEFORE_ROSTERS())
        self.assertEqual([e["added"] for e in build.wire(cap, [old])], [["Last Week"]])
        self.assertEqual(build.wire(cap), [])

    def test_lineup_changes_name_the_players_promoted(self):
        cap = capture(4, BEFORE_ROSTERS(), [tx("ROSTER", 3, "2026-10-06T10:00:00.000Z",
            item("LINEUP", 1, "Ann Alpha", from_slot="BENCH", to_slot="WR"),
            item("LINEUP", 2, "Bea Bravo", from_slot="WR", to_slot="BENCH")),
            tx("FUTURE_ROSTER", 4, "2026-10-06T11:00:00.000Z", item("LINEUP", 3, "Cy Charlie", from_slot="RB", to_slot="FLEX"))])
        got = build.wire(cap)
        # Team 4 only slid a starter from RB to FLEX: a lineup change, but nobody came off the bench.
        self.assertEqual([(e["kind"], e["manager"], e["promoted"]) for e in got],
                         [("lineup", NAME[4], []), ("lineup", NAME[3], [1])])

    def test_draft_and_declined_offers_stay_out(self):
        cap = capture(4, BEFORE_ROSTERS(), [
            tx("DRAFT", 3, "2026-10-06T10:00:00.000Z", item("DRAFT", 1, "Ann Alpha", to=3)),
            tx("TRADE_DECLINE", 4, "2026-10-06T11:00:00.000Z"),
            tx("TRADE_PROPOSAL", 4, "2026-10-06T11:30:00.000Z")])
        self.assertEqual(build.wire(cap, [BEFORE]), [])

    def test_unknown_team_is_skipped(self):
        cap = capture(4, BEFORE_ROSTERS(), [tx("FREEAGENT", 99, "2026-10-06T10:00:00.000Z", item("ADD", 7, "Ghost", to=99))])
        self.assertEqual(build.wire(cap), [])


def BEFORE_ROSTERS():
    return {t: list(m[s]["lineup"]) for m in BEFORE["matchups"] for s in ("home", "away") for t in [m[s]["team_id"]]}


SWAPPED = {3: [player(1, "Ann Alpha"), player(3, "Cy Charlie")], 4: [player(2, "Bea Bravo"), player(4, "Di Delta")]}
UPHOLD = [tx("TRADE_UPHOLD", 1, "2026-10-01T01:28:17.000Z"), tx("TRADE_UPHOLD", 1, "2026-10-01T01:28:27.000Z")]


class TradeTest(unittest.TestCase):
    def test_trade_is_read_off_the_rosters_not_the_record(self):
        """ESPN's record names team 1 and no players; the two who traded are 3 and 4."""
        got = build.wire(capture(4, SWAPPED, UPHOLD), [BEFORE])
        self.assertEqual(got, [{"date": "2026-10-01T01:28:27.000Z", "kind": "trade", "team_id": 3, "manager": NAME[3],
                                "with_id": 4, "with": NAME[4], "added": ["Cy Charlie"], "dropped": ["Bea Bravo"]}])

    def test_two_records_are_one_trade(self):
        self.assertEqual(len(build._trades(capture(4, SWAPPED, UPHOLD), BEFORE)), 1)

    def test_dated_by_the_go_ahead_not_the_accept(self):
        """Accepted eight days ago, upheld six days ago: it happened inside the week, so it shows."""
        txs = [tx("TRADE_ACCEPT", 3, "2026-09-29T10:00:00.000Z"), tx("TRADE_UPHOLD", 1, "2026-10-01T10:00:00.000Z")]
        self.assertEqual([e["date"] for e in build.wire(capture(4, SWAPPED, txs), [BEFORE])], ["2026-10-01T10:00:00.000Z"])

    def test_a_trade_then_a_drop_is_missed_not_misreported(self):
        """Known limit: once one side's player has moved on, the rosters can't prove a trade, so none is shown."""
        moved = {3: [player(1, "Ann Alpha"), player(3, "Cy Charlie")], 4: [player(4, "Di Delta")]}
        cap = capture(4, moved, UPHOLD + [tx("ROSTER", 4, "2026-10-02T10:00:00.000Z", item("DROP", 2, "Bea Bravo", frm=4))])
        self.assertEqual([e["kind"] for e in build.wire(cap, [BEFORE])], ["move"])

    def test_a_malformed_log_costs_the_wire_not_the_page(self):
        src = (ROOT / "site" / "build.py").read_text()
        with self.assertRaises((KeyError, TypeError)):
            build.wire(capture(4, SWAPPED, [{"type": "FREEAGENT", "team_id": 3, "date": "2026-10-06T10:00:00.000Z"}]))
        self.assertIn("except (KeyError, TypeError, ValueError, AttributeError):\n        feed = []", src)

    def test_no_trade_record_means_no_trade(self):
        self.assertEqual(build.wire(capture(4, SWAPPED), [BEFORE]), [])

    def test_a_pickup_is_not_a_trade(self):
        """Dropped by one team, picked up by the other: the log explains it, so it isn't a trade."""
        moved = {3: [player(1, "Ann Alpha")], 4: [player(2, "Bea Bravo"), player(3, "Cy Charlie"), player(4, "Di Delta")]}
        cap = capture(4, moved, UPHOLD + [tx("FREEAGENT", 4, "2026-10-02T10:00:00.000Z", item("ADD", 2, "Bea Bravo", to=4))])
        self.assertEqual([e["kind"] for e in build.wire(cap, [BEFORE])], ["move"])

    def test_one_way_movement_is_left_out(self):
        moved = {3: [player(1, "Ann Alpha")], 4: [player(2, "Bea Bravo"), player(3, "Cy Charlie"), player(4, "Di Delta")]}
        self.assertEqual(build._trades(capture(4, moved, UPHOLD), BEFORE), [])

    def test_no_earlier_capture_means_no_guess(self):
        self.assertEqual(build._trades(capture(1, SWAPPED, UPHOLD), None), [])

    def test_a_record_with_players_is_used_as_is(self):
        accept = tx("TRADE_ACCEPT", 3, "2026-10-01T02:00:00.000Z",
                    item("TRADE", 3, "Cy Charlie", frm=4, to=3), item("TRADE", 2, "Bea Bravo", frm=3, to=4))
        got = build.wire(capture(4, SWAPPED, [accept]), [BEFORE])
        self.assertEqual([(e["kind"], e["added"], e["dropped"]) for e in got], [("trade", ["Cy Charlie"], ["Bea Bravo"])])

    def test_the_real_week_four_trade(self):
        """The capture that prompted all this: Zay Flowers and Aaron Jones Sr. changed hands."""
        caps = [json.loads((ROOT / "data" / "2026" / f"week-{w:02d}" / "espn.json").read_text()) for w in (3, 4)]
        trades = [e for e in build.wire(caps[1], caps[:1]) if e["kind"] == "trade"]
        self.assertEqual([(e["manager"], e["with"], e["added"], e["dropped"]) for e in trades],
                         [("Maddie", "Tara", ["Zay Flowers"], ["Aaron Jones Sr."])])


def article(**over):
    return {"id": 1, "headline": "Ann Alpha is a must-start", "link": "https://www.espn.com/nfl/story/_/id/1/x",
            "published": "2026-10-06T12:00:00Z", "athlete_ids": [1], **over}


class NewsTest(unittest.TestCase):
    def test_tags_the_owner_and_the_player(self):
        got = build.news_items([article(tag="Injury", image="https://a.espncdn.com/photo/x.jpg")], BEFORE)
        self.assertEqual(got, [{"headline": "Ann Alpha is a must-start", "url": "https://www.espn.com/nfl/story/_/id/1/x",
                                "date": "2026-10-06T12:00:00Z", "tag": "Injury",
                                "image": "https://a.espncdn.com/photo/x.jpg",
                                "owners": [{"team_id": 3, "manager": NAME[3]}],
                                "players": [{"name": "Ann Alpha", "pos": "WR", "team": "BUF",
                                             "headshot": "https://a.espncdn.com/i/headshots/nfl/players/full/1.png"}]}])

    def test_a_dst_gets_its_team_logo_and_no_image_means_no_key(self):
        cap = capture(3, {3: [player(7, "Bills D/ST", pos="DST")], 4: []})
        got = build.news_items([article(athlete_ids=[7])], cap)
        self.assertEqual(got[0]["players"][0]["headshot"], "https://a.espncdn.com/i/teamlogos/nfl/500/buf.png")
        self.assertNotIn("image", got[0])
        self.assertEqual(got[0]["tag"], "Team news")      # an untagged or unknown tag falls back to the plain one

    def test_two_owners_and_only_rostered_players(self):
        got = build.news_items([article(athlete_ids=[1, 3, 999])], BEFORE)
        self.assertEqual([o["team_id"] for o in got[0]["owners"]], [3, 4])
        self.assertEqual([p["name"] for p in got[0]["players"]], ["Ann Alpha", "Cy Charlie"])

    def test_nobody_on_a_roster_is_dropped(self):
        self.assertEqual(build.news_items([article(athlete_ids=[999])], BEFORE), [])

    def test_only_espn_links_reach_the_page(self):
        for link in ("http://www.espn.com/x", "https://evil.example/x", "javascript:alert(1)", "https://www.espn.com/a b", None):
            self.assertEqual(build.news_items([article(link=link)], BEFORE), [], link)

    def test_only_espn_cdn_images_reach_the_page(self):
        for image in ("https://evil.example/x.jpg", "javascript:alert(1)", "http://a.espncdn.com/x.jpg", 5):
            self.assertNotIn("image", build.news_items([article(image=image)], BEFORE)[0], image)

    def test_malformed_rows_are_skipped_not_fatal(self):
        rows = [article(published="yesterday"), article(headline=None), {"id": 2}, article(athlete_ids=None), article()]
        self.assertEqual(len(build.news_items(rows, BEFORE)), 1)

    def test_espn_order_is_kept_and_capped(self):
        rows = [article(id=i, headline=f"Story {i}") for i in range(1, 20)]
        got = build.news_items(rows, BEFORE)
        self.assertEqual([n["headline"] for n in got], [f"Story {i}" for i in range(1, 13)])


class LoadNewsTest(unittest.TestCase):
    def load(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            if payload is not None:
                d = Path(tmp) / "data" / "2026" / "news"
                d.mkdir(parents=True)
                (d / "latest.json").write_text(payload if isinstance(payload, str) else json.dumps(payload))
            with mock.patch.object(build, "ROOT", Path(tmp)):
                return build.load_news(2026)

    @staticmethod
    def stamp(hours_ago):
        return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_fresh_file(self):
        at = self.stamp(1)
        self.assertEqual(self.load({"fetched_at": at, "articles": [article(), "junk"]}),
                         {"fetched_at": at, "articles": [article()]})

    def test_missing_stale_and_malformed_are_empty(self):
        self.assertEqual(self.load(None), {})
        self.assertEqual(self.load({"fetched_at": self.stamp(37), "articles": [article()]}), {})
        self.assertEqual(self.load("{not json"), {})
        self.assertEqual(self.load({"articles": [article()]}), {})
        self.assertEqual(self.load({"fetched_at": self.stamp(1), "articles": None}), {})
        self.assertEqual(self.load([1, 2]), {})


class HubPayloadTest(unittest.TestCase):
    """hub_payload() over a live week. Three recapped weeks, so week 4 is the one coming up."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tests"))
        import test_playoffs as tp
        cls.season = {"standings": tp.standings([1, 2, 3]), "weeks_played": [1, 2, 3]}
        cls.games = [{"key": f"{a}-{b}"} for a, b in ((1, 8), (4, 5), (2, 7), (3, 6))]

    def live(self, **over):
        return {"week": 4, "complete": False, "kicked_off": False, "games": self.games, **over}

    def test_stakes_before_kickoff(self):
        hub = build.hub_payload(self.live(), self.season, BEFORE, {})
        self.assertEqual(hub["stakes"]["week"], 4)
        self.assertEqual(sorted(g["key"] for g in hub["stakes"]["games"]), ["1-8", "2-7", "3-6", "4-5"])
        self.assertNotIn("news", hub)

    def test_no_stakes_once_it_starts_or_ends(self):
        self.assertEqual(build.hub_payload(self.live(kicked_off=True), self.season, BEFORE, {}), {})
        self.assertEqual(build.hub_payload(self.live(complete=True), self.season, BEFORE, {}), {})

    def test_no_stakes_when_an_earlier_week_has_no_recap(self):
        self.assertEqual(build.hub_payload(self.live(week=5), self.season, BEFORE, {}), {})

    def test_news_rides_along_in_either_state(self):
        hub = build.hub_payload(self.live(complete=True), self.season, BEFORE,
                                {"fetched_at": "2026-10-06T13:00:00Z", "articles": [article()]})
        self.assertEqual(list(hub), ["news", "news_at"])
        self.assertEqual(hub["news_at"], "2026-10-06T13:00:00Z")

    def test_swap_cards_carry_a_number_to_sort_on(self):
        """Coach's desk sorts on `gain`; it has to be the number behind the card's own stat pill."""
        sys.path.insert(0, str(ROOT / "scripts"))
        import analyze
        sys.path.insert(0, str(ROOT / "tests"))
        import hub_preview
        _, captured, _, _, _ = build.load_inputs(build.LEAGUE["season"])
        history = [e for _, e in captured]
        nxt = hub_preview.upcoming(history[-1])
        live = build.live_payload(analyze.analyze(nxt, history + [nxt]), nxt, history[-1], history=history)
        swaps = [it for row in live["advice"] for it in row["items"] if it["kind"] == "swap"]
        self.assertTrue(swaps)
        for it in swaps:
            self.assertEqual(it["stat"], f"+{it['gain']:.1f} projected")


if __name__ == "__main__":
    unittest.main()
