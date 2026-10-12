#!/usr/bin/env python3
"""Tests for borrowing production's live week in a branch-preview build (site/build.py).

Fetches from a local file:// page, so nothing here touches the network.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
import build  # noqa: E402

LIVE = {"week": 99, "live": True, "advice": [{"team_id": 1, "roster_ideas": [{"pos": "WR"}]}]}


def page(data):
    blob = json.dumps(data).replace("</", "<\\/")
    return f'<html><script id="recap-data" type="application/json">{blob}</script></html>'


def served(text):
    d = tempfile.TemporaryDirectory()
    p = Path(d.name) / "index.html"
    p.write_text(text)
    return d, p.as_uri()


class FetchProductionLive(unittest.TestCase):
    def test_reads_live_out_of_the_page(self):
        d, url = served(page({"live": LIVE}))
        with d:
            self.assertEqual(build.fetch_production_live(url), LIVE)

    def test_no_live_week_is_none(self):
        d, url = served(page({"live": None}))
        with d:
            self.assertIsNone(build.fetch_production_live(url))

    def test_shape_is_checked(self):
        d, url = served(page({"live": {"week": "4", "advice": []}}))
        with d:
            self.assertIsNone(build.fetch_production_live(url))

    def test_malformed_rows_are_none_not_a_crash(self):
        bad = [dict(LIVE, advice=["x"]), dict(LIVE, advice=[{"roster_ideas": []}]),
               dict(LIVE, advice=[{"team_id": 1, "roster_ideas": ["x"]}]), dict(LIVE, next="x"),
               dict(LIVE, next={"teams": [{}]})]
        for live in bad:
            d, url = served(page({"live": live}))
            with d:
                self.assertIsNone(build.fetch_production_live(url), live)
        d, url = served(page(["not", "an", "object"]))
        with d:
            self.assertIsNone(build.fetch_production_live(url))

    def test_unreadable_page_is_none_not_a_crash(self):
        d, url = served("<html>no data here</html>")
        with d:
            self.assertIsNone(build.fetch_production_live(url))
        self.assertIsNone(build.fetch_production_live("file:///does/not/exist.html"))
        d, url = served('<script id="recap-data" type="application/json">{oops</script>')
        with d:
            self.assertIsNone(build.fetch_production_live(url))


class SiteDataBorrowsLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = build.load_inputs(build.LEAGUE["season"])

    def data(self, preview, live_from):
        recap_weeks, captured, ahead, fp, news = self.inputs
        return build.site_data(recap_weeks, captured, preview, ahead=ahead, fp=fp, news=news,
                               live_from=json.loads(json.dumps(live_from)))[0]

    def test_draft_build_without_a_live_week_borrows_it(self):
        if any(c[0]["week"] > max((w["week"] for _, w in self.inputs[0]), default=0) for c in self.inputs[1]):
            self.skipTest("this checkout has its own uncommitted live week")
        live = self.data(True, LIVE)["live"]
        self.assertEqual(live["week"], 99)

    def test_borrowed_ideas_get_the_weak_spot_flag(self):
        if any(c[0]["week"] > max((w["week"] for _, w in self.inputs[0]), default=0) for c in self.inputs[1]):
            self.skipTest("this checkout has its own uncommitted live week")
        data = self.data(True, LIVE)
        weak = next(s for s in data["season"]["standings"] if s["team_id"] == 1)["profile"]["weak_spot"]
        self.assertEqual(data["live"]["advice"][0]["roster_ideas"][0]["fills_weak_spot"], weak == "WR")

    def test_league_build_never_borrows(self):
        self.assertNotEqual((self.data(False, LIVE)["live"] or {}).get("week"), 99)

    def test_a_week_that_already_has_a_recap_is_not_borrowed(self):
        self.assertNotEqual((self.data(True, dict(LIVE, week=1))["live"] or {}).get("week"), 1)


if __name__ == "__main__":
    unittest.main()
