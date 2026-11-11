"""The team profile's Game day tab (site/template.html): two tabs, the old tab routes land on Game day,
the page picks its own week, and the heads-up line only says what ESPN's week-ahead capture says.

The week rule and the heads-up line run in node against stubbed page globals; the rest checks markup."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "site" / "template.html").read_text()


def fn(start):
    """One top-level function or const from the template, through its own closing line."""
    i = SRC.index(start)
    end = SRC.index("\n  }\n", i) + 4 if start.lstrip().startswith("function") else SRC.index(";\n", i) + 2
    return SRC[i:end]


def run(js):
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


class Structure(unittest.TestCase):
    def test_two_tabs_only(self):
        self.assertIn("const TP_TABS = [['gameday', 'Game day', ''], ['season', 'Season', '.season']];", SRC)

    def test_old_header_pieces_are_gone(self):
        for gone in ("function tpStrip", "class=\"crumbs\"><a href=\"${onCoach", "tp-back", "tp-key"):
            self.assertNotIn(gone, SRC)

    def test_old_routes_land_on_game_day(self):
        self.assertIn(r"/^team-(\d+)\.(lineup|next|league)$/", SRC)
        self.assertIn("location.replace(`#team-${m[1]}`)", SRC)

    def test_league_view_has_its_own_route(self):
        self.assertIn(r"/^league-(\d+)$/", SRC)
        self.assertIn('href="#league-${id}"', SRC)

    def test_redraw_skips_an_open_sheet(self):
        self.assertIn("(document.getElementById('tp-sheet') || {}).open", SRC)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class WeekRule(unittest.TestCase):
    def pick(self, live, nxt, this_row=True, next_row=True):
        js = f"""
          const LIVE = {json.dumps(live)};
          const ahead = () => ({json.dumps(nxt)});
          const coachFor = (id, next) => (next ? {json.dumps(next_row)} : {json.dumps(this_row)}) ? {{ team_id: id }} : null;
          {fn("  const gdNext = (id) =>")}
          process.stdout.write(JSON.stringify(gdNext(5)));"""
        return run(js)

    def test_this_week_until_it_is_final(self):
        self.assertFalse(self.pick({"complete": False}, {"week": 11}))

    def test_next_week_once_final_and_posted(self):
        self.assertTrue(self.pick({"complete": True}, {"week": 11}))

    def test_this_week_when_nothing_is_posted(self):
        self.assertFalse(self.pick({"complete": True}, None))

    def test_next_week_when_this_week_has_nothing_for_her(self):
        self.assertTrue(self.pick({"complete": False}, {"week": 11}, this_row=False))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HeadsUp(unittest.TestCase):
    def line(self, starters, complete=False, next_=False):
        js = f"""
          const LIVE = {{ complete: {json.dumps(complete)} }};
          const ahead = () => ({{ week: 11 }});
          const coachFor = () => ({{ lineup: {{ starters: {json.dumps(starters)}, bench: [] }} }});
          const face = (p) => '[' + p.name + ']';
          const esc = (s) => String(s);
          {fn("  const OUTISH =")}
          {fn("  function gdHeadsUp(")}
          process.stdout.write(JSON.stringify(gdHeadsUp(5, {json.dumps(next_)})));"""
        return re.sub(r"<[^>]+>", "", run(js))

    def test_one_out(self):
        self.assertEqual(self.line([{"name": "DeVonta Smith", "injury": "Out"}]),
                         "[DeVonta Smith]Heads up for Week 11: DeVonta Smith is listed out.")

    def test_two_out(self):
        self.assertIn("X and Y are listed out.", self.line([{"name": "X", "injury": "Out"}, {"name": "Y", "injury": "Out"}]))

    def test_mixed_designations_say_each(self):
        self.assertIn("X is listed out and Y is on IR.",
                      self.line([{"name": "X", "injury": "Out"}, {"name": "Y", "injury": "On IR"}]))

    def test_questionable_never_triggers_it(self):
        self.assertEqual(self.line([{"name": "Q", "injury": "Questionable"}, {"name": "H", "injury": None}]), "")

    def test_only_while_this_week_is_in_play(self):
        hurt = [{"name": "X", "injury": "Out"}]
        self.assertEqual(self.line(hurt, complete=True), "")
        self.assertEqual(self.line(hurt, next_=True), "")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class FineLine(unittest.TestCase):
    """"Make the moves in the ESPN app" only shows when there's a move to make, as the homework card's last line."""
    def card(self, items, you=False):
        js = f"""
          const LIVE = {{ kicked_off: false }};
          const esc = (s) => String(s);
          const voice = (s) => s;
          const TP_CHECK = '';
          const gdSwap = () => '<article class="gd-swap"></article>';
          const gdLine = () => '<div class="gd-line"></div>';
          {fn("  function gdHomework(")}
          process.stdout.write(JSON.stringify(gdHomework({{ items: {json.dumps(items)}, summary: 'All set.' }}, false, {json.dumps(you)})));"""
        return run(js)

    def test_clean_lineup_has_no_espn_line(self):
        html = self.card([{"level": "soon"}])
        self.assertIn("Lineup's clean", html)
        self.assertNotIn("gd-fine", html)
        self.assertNotIn("ESPN app", html)

    def test_fixes_put_the_espn_line_last_inside_the_card(self):
        html = self.card([{"level": "now", "swap": {}}, {"level": "now"}])
        self.assertIn("2 to fix before Sunday", html)
        self.assertEqual(html.count("gd-fine"), 1)
        inside = re.sub(r"\s+", " ", html).strip()
        self.assertTrue(inside.endswith("lineup.</p> </section>"), inside[-80:])
        self.assertIn("Nothing here changes her lineup.", html)
        self.assertIn("Nothing here changes your lineup.", self.card([{"level": "now"}], you=True))


if __name__ == "__main__":
    unittest.main()
