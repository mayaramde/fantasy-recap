# Fantasy Recap

Weekly recap page for the ESPN league "Fantasy Football for the Girls" (8 teams, PPR).
League facts (IDs, teams, managers, roster slots) live in `league.json`, and that file is the source of truth.

## Data sources
- **ESPN** (primary): the league is private. Read it through **Claude in Chrome**, which uses Maya's logged-in session:
  `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/698468554?view=...&scoringPeriodId=N`
  Never ask for, copy, or store ESPN cookies (`espn_s2`, `SWID`) or any credentials.
- **FantasyPros MCP**: rankings, projections, injury news, player context. Pass `league_key` explicitly on every league-scoped call.
  Maya is on the free tier. Waiver Finder is premium, and the upsell has already been shown.

## Privacy
- The raw ESPN payload includes members' last names, ESPN IDs and notification settings. **Do not commit it.**
  Save only trimmed data (team ID, players, slots, points, projections, transactions) under `data/`.
- Recaps use first names only.

## Layout
- `data/<season>/week-NN/`: trimmed per-week data (JSON)
- `recaps/<season>/week-NN.json`: the written recap (awards, callouts, blurbs). Content only, no HTML.
- `site/`: template + build script → `site/dist/index.html` (the published page, with all weeks)
- `scripts/`: `capture.js` (runs in Chrome), `receive.py` (localhost receiver that also serves capture.js), `analyze.py`
- `data/player_names.json`: cache of names resolved via ESPN's public athlete API

## Weekly routine (Tuesday, after MNF is final)
1. **Capture.** Start `python3 scripts/receive.py --count 1` (background). In Chrome, open a tab at
   `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/698468554?view=mStatus`
   and run in it (javascript_tool):
   `eval(await fetch('http://127.0.0.1:8765/capture.js').then(r => r.text())); await fantasyCapture([N])`
   → writes `data/2026/week-NN/espn.json`. Never retype the captured JSON by hand. Check `complete: true`.
2. **Analyze.** `python3 scripts/analyze.py` → `facts.json` per week.
3. **Context.** FantasyPros MCP for injury/news on notable players (only claim an injury if a source says so).
4. **Write.** `recaps/2026/week-NN.json` with `"status": "draft"`. Schema: `headline`, `dek`,
   `matchups` (keys `"<lowTeamId>-<highTeamId>"`), `game_balls` / `flags` / `tough_breaks`
   (each `{manager, title, text, stat}`). Every number must match `facts.json` or `espn.json`.
5. **Build.** `python3 site/build.py` → `site/dist/preview.html` (drafts included) and `site/dist/index.html` (published only).
6. **Review.** Republish the preview artifact: https://claude.ai/artifact/6yiwuixW1kTVztAp2s5d87. Maya reviews.
7. **Ship.** Only after Maya approves: set `"status": "published"`, rebuild, republish the league artifact.
8. **Commit.** On a branch: commit, push, open a PR, and enable auto-merge (squash). It merges once the `checks`
   workflow passes (`python scripts/check.py` runs the same checks locally). Don't push to `main` directly.

## Schedule
- Local scheduled task `fantasy-weekly-recap` runs Tuesdays around 8:15 AM (while the Claude app is open) and does steps 1-6,
  then opens a draft PR. Maya approves before anything reaches the league site.

## Published pages
- Preview (private, Maya only): https://claude.ai/artifact/6yiwuixW1kTVztAp2s5d87 (from `site/dist/preview.html`)
- League page (shared with the league): https://claude.ai/artifact/XU5jqS5WzR47mK3kCDhNKZ (from `site/dist/index.html`). Launched with Weeks 1-2 on 2026-09-28.

## Recap content
- Matchup results, high/low scores, standings
- Good decisions: waiver pickups that paid off, smart benchings/starts
- Bench blunders: points left on the bench (optimal lineup vs actual)
- Unexpectedly screwed: injuries mid-game, big misses vs projection, bad-luck losses (e.g., 2nd-highest score but lost)
- Rookie glossary: 3-5 football/fantasy terms used in that week's recap, defined in one friendly sentence each.

## Voice
- The league is "Fantasy Football for the Girls," and for most members this is their first season following football.
- Cheeky and funny, like a friend explaining the game at a watch party. Roast lineup decisions, never people. Maya's own team gets roasted too.
- Explain jargon in passing ("flex, the wild-card spot"), never assume football knowledge, and never talk down.
- Pop-culture asides are welcome when accurate. The jokes can exaggerate, but every number stays exact.

## Design
- Palette "Tailgate pop": cobalt (navigation, links, scoreboard), tangerine (game balls), bubblegum pink (flags),
  lime (highlight badges), navy ink. Pop colors are fills with ink text on top, never text on white.
  Green/red only as small W/L labels. All tokens live in `site/template.html` `:root` (plus dark-mode blocks).
- UI style "Sticker book": 2px ink outlines, hard offset shadows, a few slightly tilted badges.
- Fonts: Big Shoulders Display (headings, scores), Figtree (body), DM Mono (numbers), Fredoka (small badge labels).
  Maya found the cursive script (Yellowtail) hard to read, so no script fonts.
