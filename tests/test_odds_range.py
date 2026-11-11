"""The team profile's playoff odds chip: oddsRange() in site/template.html, run in node with the real pct().

Each end of the range carries its own %, so ">99%" and "<1%" never get glued to a dash ("98–>99%")."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "site" / "template.html").read_text()
PCT = SRC[SRC.index("  const pct = (p, exact = false) => {"):SRC.index("  const PO_TIP")]
ODDS = SRC[SRC.index("  function oddsRange(o) {"):SRC.index("  function tpStrip(")]


def odds_range(o):
    js = f"{PCT}\n{ODDS}\nprocess.stdout.write(JSON.stringify(oddsRange({json.dumps(o)})));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class OddsRange(unittest.TestCase):
    def test_capped_high_end_keeps_its_own_percent(self):
        self.assertEqual(odds_range({"lose": 0.98, "win": 0.996, "opp": "Kyra"}),
                         {"text": "98% → >99%", "sub": "lose → win vs Kyra"})

    def test_capped_low_end_keeps_its_own_percent(self):
        self.assertEqual(odds_range({"lose": 0.004, "win": 0.02, "opp": None})["text"], "<1% → 2%")

    def test_plain_range(self):
        self.assertEqual(odds_range({"lose": 0.81, "win": 0.94, "opp": "Amie"}),
                         {"text": "81% → 94%", "sub": "lose → win vs Amie"})

    def test_same_rounded_number_is_one_number_either_way(self):
        self.assertEqual(odds_range({"lose": 0.996, "win": 0.999, "opp": "Tara"}),
                         {"text": ">99%", "sub": "either way vs Tara"})

    def test_after_kickoff_is_todays_single_number(self):
        self.assertEqual(odds_range({"now": 0.42}), {"text": "42%", "sub": "chance to make the top 4"})

    def test_no_dash_glued_to_a_capped_end(self):
        for lo, hi in ((0.98, 0.996), (0.004, 0.02), (0.001, 0.999)):
            text = odds_range({"lose": lo, "win": hi})["text"]
            for bad in ("–>", "–<", "->", "-<"):
                self.assertNotIn(bad, text)

    def test_chip_escapes_the_text(self):
        self.assertIn("<dd>${esc(odds.text)}</dd>", SRC)


if __name__ == "__main__":
    unittest.main()
