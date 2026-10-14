#!/usr/bin/env python3
"""Tests for scripts/fetch_news.py's filter: which ESPN headlines are allowed anywhere near the site.
A hand-built feed in ESPN's shape; nothing here touches the network."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_news  # noqa: E402

ROSTERED = {101, 102, 103}


def story(headline, athletes, description="", href="https://www.espn.com/nfl/story/_/id/1/x", **over):
    return {"id": 1, "headline": headline, "description": description, "published": "2026-10-06T12:00:00Z",
            "byline": "A. Writer", "links": {"web": {"href": href}}, "images": [{"url": "x"}], "type": "HeadlineNews",
            "categories": [{"type": "athlete", "athleteId": a} for a in athletes] + [{"type": "team", "teamId": 9}],
            **over}


class KeepTest(unittest.TestCase):
    def keep(self, *articles):
        return fetch_news.keep({"articles": list(articles)}, ROSTERED)

    def test_a_rostered_player_story_is_kept_and_trimmed(self):
        got = self.keep(story("Michael Wilson is a must-start in Week 5", [101]))
        self.assertEqual(got, [{"id": 1, "headline": "Michael Wilson is a must-start in Week 5",
                                "link": "https://www.espn.com/nfl/story/_/id/1/x", "published": "2026-10-06T12:00:00Z",
                                "athlete_ids": [101], "tag": "Team news", "byline": "A. Writer"}])

    def test_tags_and_images(self):
        photo = "https://a.espncdn.com/photo/2026/1014/r1_600x400.jpg"
        cases = [("Eagles pass rusher is unlikely vs. Panthers", "HeadlineNews", "Injury"),
                 ("Patriots lineman out with MCL sprain", "Story", "Injury"),
                 ("Why the Browns run game is struggling", "Story", "Feature"),
                 ("Broncos QB says he needs to simplify", "HeadlineNews", "Team news")]
        for headline, kind, tag in cases:
            got = self.keep(story(headline, [101], type=kind, images=[{"url": photo}]))
            self.assertEqual((got[0]["tag"], got[0]["image"]), (tag, photo), headline)
        self.assertNotIn("image", self.keep(story("No pic", [101], images=[{"url": "https://evil.example/x.jpg"}]))[0])
        self.assertNotIn("image", self.keep(story("No pic", [101], images=None))[0])

    def test_a_listicle_is_dropped(self):
        self.assertEqual(self.keep(story("Rest-of-season rankings", list(range(90, 130)))), [])
        self.assertEqual(len(self.keep(story("Four names", [101, 1, 2, 3]))), 1)
        self.assertEqual(self.keep(story("Five names", [101, 1, 2, 3, 4])), [])

    def test_nobody_rostered_is_dropped(self):
        self.assertEqual(self.keep(story("Some other guy", [555]), story("No tags at all", [])), [])

    def test_off_field_stories_are_dropped(self):
        for headline in ("Player's wife recounts assault at trial", "Friends sue player for defamation",
                         "Player arrested after traffic stop", "League suspends player six games",
                         "Player charged in nightclub incident", "Former teammate dies at 34"):
            self.assertEqual(self.keep(story(headline, [101])), [], headline)
        self.assertEqual(self.keep(story("Player speaks", [101], description="He faces a lawsuit.")), [])

    def test_football_words_that_look_like_trouble_survive(self):
        for headline in ("Chargers lean on their run game", "Courtland Sutton is a long shot to play",
                         "Receiver pleased with his targets", "Rookie drew praise for his route running"):
            self.assertEqual(len(self.keep(story(headline, [101]))), 1, headline)

    def test_when_in_doubt_it_is_dropped(self):
        """Football phrases that share a word with trouble go too. Losing a headline costs nothing."""
        for headline in ("Rookie gets a trial run at left tackle", "Team eats dead cap to move on",
                         "Player pleads no contest", "Sudden-death thriller in overtime"):
            self.assertEqual(self.keep(story(headline, [101])), [], headline)

    def test_only_espn_links(self):
        for href in ("https://example.com/x", "http://www.espn.com/x", "javascript:alert(1)"):
            self.assertEqual(self.keep(story("Fine headline", [101], href=href)), [], href)

    def test_malformed_rows_are_skipped(self):
        rows = [{"headline": "no links", "categories": [{"type": "athlete", "athleteId": 101}]}, "junk", None,
                story("Bad date", [101], published="soon"), story("Good one", [102])]
        self.assertEqual([a["headline"] for a in self.keep(*rows)], ["Good one"])

    def test_empty_and_shapeless_feeds(self):
        self.assertEqual(fetch_news.keep({}, ROSTERED), [])
        self.assertEqual(fetch_news.keep({"articles": None}, ROSTERED), [])


class MainTest(unittest.TestCase):
    def run_main(self, urlopen):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fetch_news, "ROOT", Path(tmp)), \
                mock.patch.object(fetch_news, "roster_ids", return_value=ROSTERED), \
                mock.patch.object(fetch_news.urllib.request, "urlopen", urlopen), \
                mock.patch.object(sys, "argv", ["fetch_news.py", "--season", "2026"]):
            fetch_news.main()
            return (Path(tmp) / "data" / "2026" / "news" / "latest.json").exists()

    def test_a_good_feed_writes_the_trimmed_file(self):
        import json
        feed = json.dumps({"articles": [story("Good one", [102]), story("Nobody here", [555])]}).encode()
        res = mock.MagicMock()
        res.__enter__.return_value.read.return_value = feed
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fetch_news, "ROOT", Path(tmp)), \
                mock.patch.object(fetch_news, "roster_ids", return_value=ROSTERED), \
                mock.patch.object(fetch_news.urllib.request, "urlopen", mock.Mock(return_value=res)), \
                mock.patch.object(sys, "argv", ["fetch_news.py", "--season", "2026"]):
            fetch_news.main()
            out = json.loads((Path(tmp) / "data" / "2026" / "news" / "latest.json").read_text())
        self.assertEqual(sorted(out), ["articles", "fetched_at"])
        self.assertEqual([a["headline"] for a in out["articles"]], ["Good one"])
        self.assertEqual(sorted(out["articles"][0]), ["athlete_ids", "byline", "headline", "id", "link", "published", "tag"])

    def test_no_capture_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fetch_news, "ROOT", Path(tmp)), \
                mock.patch.object(sys, "argv", ["fetch_news.py", "--season", "2026"]):
            fetch_news.main()
            self.assertFalse((Path(tmp) / "data" / "2026" / "news").exists())

    def test_a_dead_network_writes_nothing_and_does_not_raise(self):
        self.assertFalse(self.run_main(mock.Mock(side_effect=OSError("offline"))))

    def test_a_garbage_response_writes_nothing_and_does_not_raise(self):
        res = mock.MagicMock()
        res.__enter__.return_value.read.return_value = b"<html>not json"
        self.assertFalse(self.run_main(mock.Mock(return_value=res)))


if __name__ == "__main__":
    unittest.main()
