"""Structure checks for the Behind the scenes page (site/bts/).

The page's markup, CSS, JS and icon sprite are stitched into template.html at build time, so a
typo in an id, a class that escaped its prefix, or a sprite symbol that was dropped would only
show up as a quietly broken page in a browser. These read the same files the build does.
"""
import re
import unittest
from pathlib import Path

BTS = Path(__file__).resolve().parent.parent / "site" / "bts"
PAGE = (BTS / "page.html").read_text()
SPRITE = (BTS / "sprite.svg").read_text()
JS = (BTS / "bts.js").read_text()
TEMPLATE = (BTS.parent / "template.html").read_text()
SECTIONS = ["big", "data", "api", "harness", "deploy", "safe", "cheat"]


class BehindTheScenesPage(unittest.TestCase):
    def test_ids_are_unique_and_namespaced(self):
        ids = re.findall(r'\bid="([^"]+)"', PAGE)
        self.assertEqual(len(ids), len(set(ids)), "duplicate id on the page")
        # #coach, #live, #standings and friends are real routes: no bare id may shadow a route name
        self.assertEqual([i for i in ids if not i.startswith("bts-")], [])

    def test_every_idref_points_at_an_id(self):
        ids = set(re.findall(r'\bid="([^"]+)"', PAGE))
        for attr in ("aria-controls", "aria-labelledby", "data-jump"):
            for ref in re.findall(rf'{attr}="([^"]+)"', PAGE):
                self.assertIn(ref, ids, f"{attr}={ref} has no matching id")

    def test_classes_stay_inside_the_prefix(self):
        # the page root, plus the two site classes it borrows on purpose: the page head and its kicker
        allowed = {"bts", "page-head", "kicker"}
        for group in re.findall(r'\bclass="([^"]+)"', PAGE):
            for token in group.split():
                self.assertTrue(token.startswith("bts-") or token in allowed, f"unprefixed class {token!r}")

    def test_no_inline_styles_or_em_dashes(self):
        self.assertNotIn("style=", PAGE)
        self.assertNotIn("—", PAGE + JS)  # CLAUDE.md: no em dashes in site copy

    def test_sprite_covers_every_icon_used(self):
        symbols = set(re.findall(r'<symbol id="([^"]+)"', SPRITE))
        used = set(re.findall(r'<use href="#([^"]+)"', PAGE + JS))
        self.assertEqual(used - symbols, set())
        self.assertEqual(symbols - used, set(), "sprite carries icons nothing uses")

    def test_links_are_real_routes_or_in_page_jumps(self):
        for href in re.findall(r'\bhref="([^"]+)"', PAGE):
            if href.startswith("#bts-"):
                continue
            ok = href in ("#standings", "#coach") or re.fullmatch(r"#behind-the-scenes\.(%s)" % "|".join(SECTIONS), href)
            self.assertTrue(ok, f"unexpected link {href}")

    def test_route_knows_every_section(self):
        m = re.search(r"behind-the-scenes\(\?:\\\.\(([^)]*)\)\)\?", TEMPLATE)
        self.assertIsNotNone(m, "route branch missing from template.html")
        self.assertEqual(m.group(1).split("|"), SECTIONS)
        for s in SECTIONS:
            self.assertIn(f'id="bts-{s}"', PAGE)

    def test_nav_tab_follows_glossary(self):
        self.assertRegex(TEMPLATE, r'data-nav="glossary">Glossary</a>\s*<a href="#behind-the-scenes" data-nav="behind-the-scenes">Behind the scenes</a>')

    def test_accordion_buttons_are_buttons_with_state(self):
        for head in re.findall(r'<button class="bts-(?:shead|mhead)"[^>]*>', PAGE):
            self.assertIn("aria-expanded=", head)
            self.assertIn("aria-controls=", head)


if __name__ == "__main__":
    unittest.main()
