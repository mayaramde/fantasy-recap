"""The Live hero opens its box score from one stretched link; chips and the Coach link are their own anchors
(anchors can't nest, so none of them may sit inside another). Checks the markup in site/template.html."""
import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "site" / "template.html").read_text()
CSS = (Path(__file__).resolve().parent.parent / "site" / "live" / "live.css").read_text()
HERO = SRC[SRC.index("function liveHeroCard"):SRC.index("// A game that isn't yours")]


class HeroLinks(unittest.TestCase):
    def test_hero_has_box_score_bar_and_coach_link(self):
        self.assertIn('class="lv-go" href="${boxHref}"', HERO)
        self.assertIn("coachHref()", HERO)

    def test_chips_are_links_to_the_same_box_score(self):
        self.assertIn('<a class="lv-chip" href="${boxHref}"', HERO)

    def test_no_nested_anchors(self):
        for a in re.findall(r"<a\b[^>]*>(.*?)</a>", HERO, re.S):
            self.assertNotIn("<a ", a)

    def test_stretched_link_and_layering_css(self):
        self.assertRegex(CSS, r"\.lv-go::after \{[^}]*inset: 0")
        for sel in (".lv-coach", "a.lv-chip", ".lv-pickbox .lv-btn"):
            self.assertRegex(CSS, re.escape(sel) + r" \{[^}]*z-index: 2")


if __name__ == "__main__":
    unittest.main()
