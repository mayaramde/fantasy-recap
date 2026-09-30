# Architecture

When the site's automated pieces run, and what the Live and Coach pages compute versus what a
daily skill authors for them. Reference for a human reading the codebase; the skills in
`.claude/skills/` own *how* each job is done.

## Schedule

- **Cloud live update** (`.github/workflows/live-update.yml`, GitHub Actions): hourly during NFL game windows plus a
  daily 7:30 AM EDT run. Captures the current week headlessly (`scripts/capture_node.mjs`, same `capture.js`
  trimming), then the week after it (`capture_node.mjs next`) for the Coach page, a step allowed to fail without
  taking the live scores down with it. Then analyze + check, then `scripts/site_guard.py` refuses to deploy if the
  live site has a published recap that `main` doesn't (a recap shipped from the Mac whose PR hasn't merged). Then
  `scripts/deploy.sh`. Nothing is committed. A failure email saying "ESPN 401" means the ESPN cookie secrets expired.
- **`fantasy-weekly-recap`** runs Tuesdays around 8:15 AM: invokes `fantasy-orchestrator` to capture last week
  (final), draft and fact-check the recap, open the `Week NN recap draft` PR, and deploy a review preview. It stops
  there. Maya approves the preview before `recap-ship` publishes and opens the `Publish week NN recap` PR.
- **`fantasy-coach-daily`** runs once a day: invokes `coach-daily`, which writes FantasyPros-sourced Coach cards
  (start/sit, waiver and trade leads, injury/news changes since yesterday) to `data/2026/fantasypros/latest.json`
  and opens its own auto-merging PR. It works in its own git worktree so it never switches branches under another
  session, and it never deploys; the next live-update run picks up the merged snapshot.
- Every scheduled job works from `main`, so anything it depends on must be merged first.

## Live page

- Shows the newest captured week without a recap in that build: "live" while games are on, "final, recap drops
  Tuesday" after Monday night. Standings only count weeks with a recap.
- Refreshes itself through `/api/live` (`api/live.py`), which recomputes the week from ESPN per request.
- Box scores put each player's NFL team logo next to his name (the slot column already names the position) and give
  a player whose game is on right now a pulsing lime sticker with the game clock ("Q3 7:22", "Halftime").
- Each matchup card counts, per side, "2 playing now" (a starter whose game is on) and "1 starter yet to play"
  (kickoff still ahead), or "all starters done" when neither is left.

## Coach page

- Hangs off the live week, with two tabs: `#coach` / `#coach-<teamId>` is the week being played, and
  `#coach-next` / `#coach-next-<teamId>` is the week after it, from the `next-week` capture (no tab when that
  capture is missing or stale). Once the live week is final the page leads with next week. The browser remembers
  the last team opened. The page disappears once the live week's recap is published.
- Next week's tab is baked at build time and never refreshed by `/api/live`: those numbers move about once a day,
  and asking ESPN for a second week on every request would double what the Live page costs it.
- **Computed cards** (`team_advice` in `site/build.py`), from the capture alone (ESPN projections, injury
  designations, which NFL games have kicked off), so this week's refresh with the rest of the live data:
  - swap a bench player in (only for a projection gap of 2+ points)
  - a starter is out, doubtful, on IR, or suspended
  - a starter's team is on a bye, or a starting slot is empty
  - a starter is projected zero with nothing better behind him
  - who has newly landed on (or come off) the injury report since last week's capture

  A player whose game has kicked off is locked, so nothing suggests moving him. With no projections published for a
  week, that tab drops the start-or-sit cards rather than comparing zeros, and says so. Neither week ever states an
  injury ESPN didn't report.
- **Authored cards** (`consensus`, `waiver`, `trade`, `fp_news`, `fp_back`, and the "Worth a look" section) come
  from `coach-daily`'s snapshot. `site/build.py` only decides whether that day's snapshot is fresh enough to merge in.
- **Player cards** (`player_cards` in `site/build.py`): every lineup row opens into one cheeky line about his week,
  ESPN's scoring broken down stat by stat, and a few notes (his share of your total, what the injury report says
  and whether that's new, where his game is up to, what else you have at that spot). The numbers are ESPN's, the
  jokes are ours, and no card reports news no source gave us. A week nobody has played has no stat line, so its
  cards are the blurb and the notes; with no projections published yet, nothing quotes one.
