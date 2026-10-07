# Architecture

When the site's automated pieces run, and what the Live and Coach pages compute versus what a
daily skill authors for them. Reference for a human reading the codebase; the skills in
`.claude/skills/` own *how* each job is done.

## League rules

ESPN's league settings, mirrored in `league.json` (the source of truth; edit it, not the code, if a rule changes):

- **Regular season**: Weeks 1-14, one week per matchup, no matchup tiebreaker (a tie stands and counts as half
  a win in the standings), no home-field advantage, no bonus wins.
- **Playoffs** (`playoffs`): top 4, **no byes**. Seeds 1v4 and 2v3 play Week 15; the championship is the two
  teams' combined points over Weeks 16 and 17 (`championship_weeks: 2`). Seeding ties go to total points for;
  no reseeding; no playoff home-field advantage; everyone else plays a consolation ladder. `site/playoffs.py`
  simulates and draws exactly this bracket. It derives byes from the field size (a power-of-two field has
  none), so the Standings page's Bye column and stickers can't disagree with the bracket.
- **Transactions** (`transactions`): lineups lock per player at his game's kickoff (the Coach page's "locked"),
  waivers with no season limit, a 1-day waiver period, waiver order reset each week to inverse standings, and
  eliminated teams are not locked out of moves during the playoffs. Nothing computes waiver priority yet;
  these are recorded so copy and Coach cards don't contradict them.

## Schedule

- **Cloud live update** (`.github/workflows/live-update.yml`, GitHub Actions) runs on two kinds of trigger:
  - **Scheduled**: hourly during NFL game windows plus a daily 7:30 AM EDT run (see the workflow's own cron
    comments for the exact holiday-window coverage). Captures the current week headlessly
    (`scripts/capture_node.mjs`, same `capture.js` trimming), then the week after it (`capture_node.mjs next`) for
    the Coach page, a step allowed to fail without taking the live scores down with it. Skips the rest of the run
    once that week's recap is already published — nothing left to show live.
  - **Push to `main`**, scoped to the paths that affect the site (`recaps/`, `data/`, `site/`, `scripts/`, `api/`,
    `league.json`, `vercel.json`): deploys within minutes of a merge, and — unlike the scheduled trigger — never
    skips, since it fires because something (often a just-published recap or a coach-daily snapshot) needs to go
    live now.
  - Either way: analyze + check, then `scripts/site_guard.py` refuses to deploy if the live site has a published
    recap that `main` doesn't (a recap shipped from the Mac whose PR hasn't merged), then `scripts/deploy.sh`.
    Nothing is committed. On failure, a step opens (or comments on) a GitHub issue — a message mentioning "ESPN
    401" means the ESPN cookie secrets expired, in both GitHub Actions secrets and the matching Vercel env vars.
- **`fantasy-weekly-recap`** runs Tuesdays around 8:15 AM: invokes `fantasy-orchestrator` to capture last week
  (final), draft and fact-check the recap, open the `Week NN recap draft` PR, and deploy a review preview. It stops
  there. Maya approves the preview before `recap-ship` publishes and opens the `Publish week NN recap` PR — merging
  that PR is what triggers the push-deploy above.
- **`fantasy-coach-daily`** runs once a day: invokes `coach-daily`, which writes FantasyPros-sourced Coach cards
  (start/sit, waiver and trade leads, injury/news changes since yesterday) to `data/2026/fantasypros/latest.json`
  and opens its own auto-merging PR. It works in its own git worktree so it never switches branches under another
  session, and it never deploys itself — merging its PR triggers the push-deploy above, same as a recap.
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

- A league-wide grid at `#coach` (the week being played) and `#coach-next` (the week after it, from the
  `next-week` capture; no tab when that capture is missing or stale), one card per team. Each team's own week lives
  on her **team profile** (`#team-<id>`, and `#team-<id>.next` for next week); the old `#coach-<id>` and
  `#coach-next-<id>` links redirect there. Once the live week is final the page leads with next week. The browser
  remembers the last team opened. The grid and the profile's week sections disappear once the live week's recap is
  published; the rest of the profile stays all season.
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
- **Written copy for the computed cards.** Each computed card (and the one-line team summary) carries a `key`
  naming its exact situation, e.g. `swap:<starter id>:<bench id>:<his injury status>`. `coach-daily` reads them
  with `scripts/coach_brief.py` and writes voice-checked advice for each key into its snapshot (`coach_cards`,
  `summary`). The page shows the written title and text only while that key is still computed, so advice for a
  situation that has since changed falls back to the computed wording on its own. Written copy never carries a
  decimal or a percentage (the build rejects it); the live number stays in the computed stat pill.
- **Authored cards** (`consensus`, `waiver`, `trade`, `fp_news`, `fp_back`, and the "Worth a look" section) come
  from `coach-daily`'s snapshot. `site/build.py` only decides whether that day's snapshot is fresh enough to merge in.
- **Player cards** (`player_cards` in `site/build.py`): every lineup row opens into one cheeky line about his week,
  ESPN's scoring broken down stat by stat, and a few notes (his share of your total, what the injury report says
  and whether that's new, where his game is up to, what else you have at that spot). The numbers are ESPN's, the
  jokes are ours, and no card reports news no source gave us. A week nobody has played has no stat line, so its
  cards are the blurb and the notes; with no projections published yet, nothing quotes one.

## Standings page

`#standings`: the table (wins, then points for, recapped weeks only), then the **playoff picture**, Points by week and
the luck report.

- **Playoff odds** (`site/playoffs.py`, baked at build time into `season.playoffs`; `/api/live` never touches them):
  the rest of the regular season and the bracket, simulated 8,000 times from each team's recapped scores. The format
  comes from `league.json`'s `playoffs` block. Opponents follow `data/<season>/schedule.json` when it pairs every team
  for a week, and are random otherwise; the page's "How this works" note says which.
- Only regular-season weeks count toward seeding, so a recapped playoff game never moves a seed, a Bye sticker or the
  playoff line.
- The RNG is seeded from a sha256 of the inputs, so the same weeks always give the same numbers, and the result is
  memoized because `render()` runs twice per build.
- Labels come from the odds alone (Near lock, Bye race, Comfortable, Bubble, Long shot, Near out), and In/Out only once
  no regular-season games are left. A simulation proves nothing mathematically, so no label ever claims a clinch.
- The section is skipped without odds; the projected bracket only renders for 6 teams with 2 byes.

## Team profile

`#team-<id>`: header and season tiles, this week's to-dos and lineup (the Coach page section above), the
**coach's audit**, roster ideas ("Worth a look"), her **recent moves**, week by week, and awards.

- **Audit** (`site/team_profile.py`, from recapped weeks only): Lineup IQ (`lineup:<band>:<benched id>:w<week>`, or `:none` / `:scattered`),
  Position strength (`pos:<best><rank>:<worst><rank>`, e.g. `pos:RB1:WR8`; the worst group is her `weak_spot`) and Projection vs reality
  (`proj:<over|under>:<top id>:<bottom id>`). The A–D band exists only in the key, never on the page.
  `coach-daily` writes copy per key into `latest.json`'s top-level `audit`; it applies on key match alone, with no
  36-hour gate, since the key already describes finished weeks.
- **Roster ideas** whose optional `pos` equals her `weak_spot` get a "fills your weak spot" sticker.
- **Moves**: adds, drops and trades from every captured week (the live week included), newest first. ESPN's
  "Player 12345" placeholders are filled from `data/player_names.json` when `analyze.py` has looked them up.
