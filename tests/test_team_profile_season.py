"""The team profile's Season tab (site/template.html): the report card, the season story's detail panel and the
bench math, run in node against stubbed page globals, plus checks that the old blocks are gone."""
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
    end = SRC.index("\n  }\n", i) + 4 if start.lstrip().startswith("function") else SRC.index("\n", i) + 1
    return SRC[i:end]


STUBS = """
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const f1 = (n) => (Math.round(n * 10) / 10).toFixed(1);
  const f2 = (n) => n.toFixed(2);
  const ordinal = (n) => n + (['th', 'st', 'nd', 'rd'][(n % 100 - 20) % 10] || ['th', 'st', 'nd', 'rd'][n % 100] || 'th');
  const CL_NAME = {};
  const SEASON = { standings: [1, 2, 3, 4, 5, 6, 7, 8] };
  const myTeam = { get: () => null };
  const KIND = { game_balls: { cls: 'balls', label: 'Game ball' }, flags: { cls: 'flags', label: 'Flag' } };
"""

TEAM = {
    "team_id": 5, "avg": 131.22, "points_for": 1180.96, "bench_left": 209.4,
    "profile": {"pos_ranks": {"QB": 4, "RB": 3, "WR": 5, "TE": 2, "FLEX": 4, "DST": 3, "K": 7}},
    "weekly": [
        {"week": 7, "points": 92.22, "opponent": "Kyra", "opponent_points": 110.9, "result": "L", "score_rank": 8,
         "points_left": 38.26, "game_key": "5-6"},
        {"week": 9, "points": 175.08, "opponent": "Amie", "opponent_points": 159.38, "result": "W", "score_rank": 1,
         "points_left": 25.08, "game_key": "2-5"},
    ],
    "awards": [{"week": 7, "kind": "flags", "title": "One (1) catch"},
               {"week": 9, "kind": "game_balls", "title": "Add to cart, 32 times"},
               {"week": 9, "kind": "flags", "title": "Another flag"}],
}


def run(expr, picked=None):
    js = f"""{STUBS}
      {fn("  const SN_WEEK = new Map();")}
      {fn("  const SN_COLS = ")}
      {fn("  const SN_ICON = ")}
      {fn("  function snReport(")}
      {fn("  function snStory(")}
      {fn("  function snBench(")}
      const t = {json.dumps(TEAM)};
      {f"SN_WEEK.set(5, {picked});" if picked else ""}
      process.stdout.write(JSON.stringify({expr}));"""
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Season(unittest.TestCase):
    def test_report_card_tones(self):
        html = run("snReport(t)")
        self.assertIn('class="sn-cell top tl"', html)                  # TE #2, the 4th cell
        self.assertIn('aria-label="K: 7th of 8"', html)
        self.assertEqual(re.findall(r"#(\d)", text(html)), ["4", "3", "5", "2", "4", "3", "7"])
        self.assertEqual(html.count(" low"), 1)

    def test_no_ranks_no_report_card(self):
        self.assertEqual(run("snReport({ ...t, profile: {} })"), "")

    def test_latest_week_is_picked_by_default(self):
        html = run("snStory(5, t)")
        self.assertIn('aria-label="Week 9, won, 175.08"', html)
        self.assertIn('data-snw="9" data-sn-team="5" aria-pressed="true"', html)
        self.assertIn("Week 9 vs Amie", text(html))

    def test_picked_week_panel(self):
        panel = text(run("snStory(5, t)", picked=7))
        for bit in ("Week 7 vs Kyra", "Lost", "92.22 – 110.90", "8 of 8 that week", "38.26 benched", "One (1) catch",
                    "Week 7 recap"):
            self.assertIn(bit, panel)
        self.assertIn("🏈 1 game ball · 🚩 2 flags", panel)

    def test_week_without_awards(self):
        bare = {**TEAM, "awards": []}
        self.assertIn("No game balls or flags this week.", text(run(f"snStory(5, {json.dumps(bare)})")))

    def test_bench_math(self):
        tiles = text(run("snBench(5, t)"))
        self.assertIn("85% of her best possible lineup", tiles)
        self.assertIn("209.4 points left on the bench", tiles)


class Removed(unittest.TestCase):
    def test_old_season_blocks_are_gone(self):
        body = fn("  function tpSeason(")
        for gone in ("Week by week", "Expand all", "data-act=\"all\"", "tp-unwritten", "sc-wl", "awardRow"):
            self.assertNotIn(gone, body)

    def test_bars_are_buttons_and_the_panel_is_live(self):
        story = fn("  function snStory(")
        self.assertIn('<button type="button" class="sn-bar', story)
        self.assertIn('aria-live="polite"', story)
        self.assertIn("'ArrowLeft', 'ArrowRight', 'Home', 'End'", SRC)


if __name__ == "__main__":
    unittest.main()
