"""The Live page's header follows state: the Coach banner only for a reader with no team picked, the score
stickers below the board (not in the head), and the kicker/dek saying whether anyone is on the field.
Checks the markup in site/template.html, like test_live_hero_links.py."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "site" / "template.html").read_text()
CSS = (ROOT / "site" / "live" / "live.css").read_text()
PAGE = SRC[SRC.index("function livePage"):SRC.index("function livePage") + 3500]
BOARD = SRC[SRC.index("function liveBoard"):SRC.index("function livePage")]


class LivePageHead(unittest.TestCase):
    def test_banner_only_without_a_picked_team(self):
        # picked comes from liveHero(), which is false for no team and for a team not in this week's games
        self.assertIn("liveHero(w.games, myTeam.get()).picked", PAGE)
        self.assertRegex(PAGE, r"showBanner = w\.advice && \(w\.complete \|\| !liveHero\(w\.games, myTeam\.get\(\)\)\.picked\)")
        self.assertIn("${showBanner ? `<a class=\"live-banner\"", PAGE)  # omitted, never an empty shell
        self.assertEqual(PAGE.count("live-banner"), 1)

    def test_score_stickers_move_below_the_live_board_only(self):
        head = PAGE[:PAGE.index("showBanner ?")]
        live_head = head[head.index("<h1>Live scoreboard</h1>"):]
        self.assertNotIn("scorePills", live_head)
        self.assertIn("Final scores", head)
        self.assertRegex(head, r"Final scores</h1>\s*\$\{scorePills\(w\)\}")  # final board keeps them in the head
        self.assertIn("Score extremes so far", BOARD)
        self.assertGreater(BOARD.index("lv-extremes"), BOARD.index("</div>"))  # after the grid

    def test_kicker_and_dek_follow_who_is_on_the_field(self):
        self.assertIn("anyPlaying ? 'live' : 'between games'", PAGE)
        self.assertIn("nothing is on the field right now", PAGE)
        self.assertIn("liveAnyPlaying(LIVE) ? LIVE_PLAYING : LIVE_IDLE", SRC)  # one definition, shared with the timer

    def test_desktop_grid_has_no_second_column_of_cards(self):
        self.assertRegex(CSS, r"\.lv-grid \{[^}]*grid-template-columns: minmax\(0, 560px\) minmax\(0, 1fr\)")
        self.assertNotRegex(CSS, r"\.lv-games \{ grid-template-columns: 1fr 1fr")


if __name__ == "__main__":
    unittest.main()
