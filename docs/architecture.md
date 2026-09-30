# Architecture

How the site's automated pieces run on a timer, and what the Live and Coach
pages actually compute versus what a daily skill authors for them. Moved
out of `CLAUDE.md` when the `.claude/` harness was built (2026-09-29) — the
skills own *how* to do the work now; this is reference material about *when*
things run and what the pages show, for a human reading the codebase.

## Schedule

- **Cloud live update** (`.github/workflows/live-update.yml`, GitHub Actions): hourly during NFL game windows plus a
  daily 7:30 AM EDT run. Captures the current week headlessly (`scripts/capture_node.mjs`, same `capture.js` trimming),
  then captures the week after it (`capture_node.mjs next`) for the Coach page, a step allowed to fail without
  taking the live scores down with it. Then analyze + check, then `scripts/site_guard.py` refuses to deploy if the live site has a published recap that
  `main` doesn't (a recap shipped from the Mac whose PR hasn't merged). Then `scripts/deploy.sh`. Nothing is committed.
  A failure email saying "ESPN 401" means the ESPN cookie secrets expired.
- `fantasy-weekly-recap` runs Tuesdays around 8:15 AM: invokes `fantasy-orchestrator` to capture last week (final),
  draft the recap, and update the preview, stopping at a draft PR. Maya approves before the recap reaches the
  league site (`recap-ship`'s approval gate).
- `fantasy-coach-daily` runs once a day: invokes the `coach-daily` skill, which pulls FantasyPros projections,
  rankings, ownership and injury/news for all 8 rosters, and writes finished, voiced Coach cards — start/sit
  suggestions, waiver and trade leads, and what's changed in FantasyPros' injury report since yesterday — to
  `data/2026/fantasypros/latest.json`. Unlike the recap, this opens its own PR with auto-merge (squash) on and
  merges once `checks` passes, with no review (small, factual, derived data). It works in its own git worktree, so
  it never switches branches under another session. Data only otherwise: it doesn't deploy, touch any recap, or
  touch any `data/2026/week-NN/` file; the next live-update run picks up the merged snapshot.
- All three tasks start with `git checkout main && git pull`, so anything they need must be merged to `main`.
- The Live page shows the newest captured week without a recap in that build: "live" while games are on,
  "final, recap drops Tuesday" after Monday night. Standings only count weeks with a recap. Its box scores put each
  player's NFL team logo next to his name (the slot column already names the position) and give a player whose game
  is on right now a pulsing lime sticker with the game clock ("Q3 7:22", "Halftime"). Each matchup card counts the
  same two things per side: "2 playing now" (a starter whose game is on) and "1 starter yet to play" (kickoff still
  ahead), or "all starters done" when neither is left.
- The **Coach** page hangs off that same live week, with a tab for each of two weeks: `#coach` / `#coach-<teamId>`
  is the week being played, `#coach-next` / `#coach-next-<teamId>` is the week after it, from the `next-week`
  capture (no tab at all when that capture is missing or stale). Next week's tab is baked at build time and
  never refreshed by `/api/live` — those numbers move about once a day, and asking ESPN for a second week on
  every request would double what the Live page costs it. Once the live week is final the Coach tab leads with
  next week, since nothing in a finished week can be fixed. The browser remembers the last team opened.
  Most cards are computed in `site/build.py` (`team_advice`) from the capture alone — ESPN's projections, its
  injury designations, and which NFL games have kicked off — so this week's refreshes through `/api/live` with
  the rest of the live data, and neither week ever states an injury ESPN didn't report. What it can say: swap a bench
  player in (only for a projection gap of 2+ points), a starter is out/doubtful/on IR/suspended, a starter's team
  is on a bye, a starting slot is empty, a starter is projected zero with nothing better behind him, and who has
  newly landed on (or come off) the injury report since last week's capture. A player whose NFL game has already
  kicked off is locked, so nothing suggests moving him. There is no recap page for the live week, and the Coach
  page disappears once that week's recap is published. With no projections published for a week, that week's
  tab drops the start-or-sit cards rather than comparing zeros, and says so.
  On top of that, `consensus`/`waiver`/`trade`/`fp_news`/`fp_back` cards (and the "Worth a look" section) are
  authored daily by the `coach-daily` skill from FantasyPros MCP data (see CLAUDE.md's Data sources), not computed
  here — `site/build.py` only decides whether that day's snapshot is fresh enough to merge in, and refreshes with
  the same request that serves the rest of the live week.
- Every row of either Coach lineup opens into that player's own card (`player_cards` in `site/build.py`): one
  cheeky line about his week, ESPN's scoring broken down stat by stat, and a few notes — his share of your
  total, what the injury report says and whether that's new, where his game is up to, what else you have at
  that spot. Same rule as the to-do cards: the numbers are ESPN's, the jokes are ours, and no card reports news
  no source gave us. A week nobody has played has no stat line to break down, so its cards are the blurb and
  the notes; with no projections published yet, nothing quotes one.
