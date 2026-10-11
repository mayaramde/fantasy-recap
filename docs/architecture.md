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
    once that week's recap is already published — nothing left to show live. Before the build it also fetches
    ESPN's public headlines for the Week hub (`scripts/fetch_news.py`), another step allowed to fail.
  - **Push to `main`**, scoped to the paths that affect the site (`recaps/`, `data/`, `site/`, `scripts/`, `api/`,
    `league.json`, `vercel.json`): deploys within minutes of a merge, and — unlike the scheduled trigger — never
    skips, since it fires because something (often a just-published recap or a coach-daily snapshot) needs to go
    live now.
  - Either way: analyze + check, then `scripts/site_guard.py` refuses to deploy if the live site has a published
    recap that `main` doesn't (a recap shipped from the Mac whose PR hasn't merged), then `scripts/deploy.sh`.
    Nothing is committed. On failure, a step opens (or comments on) a GitHub issue — a message mentioning "ESPN
    401" means the league is no longer public on ESPN (every ESPN read is anonymous; there are no ESPN secrets).
- **Weekly recap** (`.github/workflows/weekly-recap.yml`, GitHub Actions, Claude Code via
  `anthropics/claude-code-action`) runs Tuesdays at 8:17 AM EDT, with retries Tuesday afternoon and Wednesday
  morning for a week that wasn't final yet. A gate job picks the week (the most recent final one) and skips, without starting Claude, when it already has a
  recap, a draft PR is open, or the season is over. Claude runs `fantasy-orchestrator` in its "GitHub Actions mode": capture
  last week (`capture_node.mjs`), draft, fact-check and voice-check, and commit the draft on `recap-week-NN`. The
  workflow then checks that the commit touches only that week's recap and data and is still a `draft`, pushes it,
  opens the auto-merging `Week NN recap draft` PR, deploys the review preview and links it on the PR. It stops there.
  Maya approves the preview before `recap-ship` publishes (from a Claude session) and opens the
  `Publish week NN recap` PR. Merging that PR is what triggers the push-deploy above. A run that stops short (a
  judge still failing, an error) opens or comments on a "weekly-recap failing" issue. A week that isn't final yet
  waits for the next retry, and alerts if it's still not final on Wednesday.
- **Coach daily** (`.github/workflows/coach-daily.yml`, same setup) runs daily at 8:41 AM EDT. The workflow
  captures both weeks first, then Claude runs `coach-daily` and commits `data/2026/fantasypros/latest.json` on
  `coach-daily-<date>`. The workflow checks that the commit touches only that file, opens its auto-merging PR, and
  closes any older coach-daily PR. Merging it triggers the push-deploy above, same as a recap.
- In both, Claude runs in a job with no publishing secret and a read-only token, and only a patch of its commits
  leaves that runner. A separate job on a fresh runner applies the patch to a clean checkout, re-checks its file list,
  and does the pushing and deploying with `RECAP_BOT_TOKEN` (a fine-grained token, so the PRs it opens run `checks` and the
  merges deploy) and `VERCEL_TOKEN`. Claude signs in only with `CLAUDE_CODE_OAUTH_TOKEN`, so runs use Maya's Claude plan and never bill per token.
  Coach daily runs on Sonnet 5.5 (30-minute cap); the recap keeps the default model (60-minute cap).
  FantasyPros is optional (`FANTASYPROS_MCP_URL` / `FANTASYPROS_MCP_AUTH`). Without it the recap is written from
  ESPN alone and the Coach page gets written copy for its computed cards and season audit, but no FantasyPros
  start/sit, waiver or trade cards. Each workflow's `workflow_dispatch` has a `dry_run` input that runs Claude and
  the checks without pushing anything.
- Every scheduled job works from `main`, so anything it depends on must be merged first.

## Live page

- Shows the newest captured week without a recap in that build: "live" while games are on, "final, recap drops
  Tuesday" after Monday night. Standings only count weeks with a recap.
- Refreshes itself through `/api/live` (`api/live.py`), which recomputes the week from ESPN per request.
- Box scores put each player's NFL team logo next to his name (the slot column already names the position) and give
  a player whose game is on right now a pulsing lime sticker with the game clock ("Q3 7:22", "Halftime").
- Each matchup card counts, per side, "2 playing now" (a starter whose game is on) and "1 starter yet to play"
  (kickoff still ahead), or "all starters done" when neither is left.

## Week hub ("This week")

What the Live tab shows when nothing is on the field (`landingPage` in `site/template.html`): before the week's
first kickoff, and again once every game is final and the recap isn't out yet.

- **Before kickoff**: a season strip, up to four stickers, then one card per matchup beside Coach's desk and
  the projections ranked. The reader's own game sorts first when the browser remembers her team (picked on
  Coach); otherwise the game with the most at stake leads.
- **Where each piece comes from.** Everything a lineup change can move is drawn in the browser from the live
  games and Coach rows, so it refreshes with `/api/live` and can't disagree with the projected scores beside it:
  the split bar, the **edge strip** (per lineup spot, who leads and by how many projected points, RB and WR
  summing both starters), the ranked projections, the stickers and **Coach's desk** (every team's "do this now"
  swaps, byes, outs and empty slots, biggest projected gain first; a swap card carries its `gain` as a number
  for this).
- **League wire** (`wire()` in `site/build.py`, part of `live_payload`, so `/api/live` refreshes it too): the
  last seven days of ESPN's transaction log from the live capture and the ones before it. Pickups and drops,
  lineup changes (with the players promoted off the bench, counted once each per day) and trades. ESPN records that a trade went
  through but not who was in it (the record's players are empty and its team id isn't reliably one of the two),
  so the players are read off the rosters: on a different league team than in the previous capture, with no
  pickup on record, in both directions between the same two teams, dated by the league's go-ahead. No trade
  record, no trade. Known limit: if a traded player is dropped again before the next capture, the rosters can no
  longer prove the trade and the wire leaves it out rather than guess. Declined offers are never shown. A log in
  a shape nobody expected costs the page its wire, never the build or `/api/live`. The browser rolls a manager's day into one line, groups by the reader's local day, and caps
  the feed at 12 lines with trades first.
- **Stakes** (`stakes()` in `site/playoffs.py`, baked by `hub_payload` into `live.hub.stakes`; `/api/live` never
  touches them): one more simulation of the rest of the season with this week's real pairings, read twice per
  team, once over the seasons where she won this week's game and once where she lost. Every other game is left
  to chance, so the two numbers sit either side of her Standings odds, give or take a point (it's a separate run
  of the same model, with the same optional `schedule.json`). Only for the next unplayed
  regular-season week (an unrecapped earlier week, or a playoff week, means no stakes), and a side with under
  100 simulated seasons behind it reports nothing. Games are ranked by the two teams' swings added together.
- **ESPN on your rosters** (`live.hub.news`, baked): `scripts/fetch_news.py` runs in the live-update workflow
  before the build and writes `data/<season>/news/latest.json`, never committed. It keeps an article only if it
  tags four or fewer players, at least one on a league roster, and nothing in the headline or description reads
  as off-field. The build re-matches each article against the live rosters, shows the newest six as a headline
  linking out to ESPN (the link must be `https://www.espn.com/...`), and ignores a file over 36 hours old. Since
  it only refreshes on a deploy, midweek headlines are up to a day old. Off switch: the repo variable
  `NEWS_ENABLED=false` skips the fetch.
- **After the last game**: the final scores and stickers as before, plus the wire and the headlines. No
  stakes, edge strip or Coach's desk for a week nobody can change.
- A module with nothing to show is left out, never drawn empty.
- `tests/hub_preview.py <dir>` renders both states from committed data for a look in a browser. A normal build
  of committed data has no live week, so a Vercel branch preview never shows this page; review it with
  `scripts/deploy.sh --preview` from a checkout that has a live capture.

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
- **Trade cards** are evaluated proposals, never leads. `coach-daily` finds candidates (its own ideas plus
  `scripts/trade_eval.py --scan`) and ships only trades the script passed against its ground rules: both
  lineups gain at least about a point a week, with the next four weeks counted double; the proposer's playoff
  or title odds rise and the partner's fall in neither (`site/playoffs.py`'s `trade_odds`, the same simulated
  seasons with and without each team's lineup gain); no rival (this or next week's opponent, or both teams on
  the playoff bubble) gains more playoff plus title odds than the proposer; the two sides'
  rest-of-season value within 15%; nobody hurt changes hands; 1-for-1 or 2-for-1; nothing past
  `league.json`'s `trade_deadline` (an ISO time with its offset; the build also hides every trade card once it
  passes) or the regular season. Values are FantasyPros' rest-of-season PPR
  projections spread over each player's remaining games, byes at zero (from ESPN's public scoreboard); once
  the week's games have started it scores from next week, since this week's points are already banked. The card
  carries the script's numbers in a `trade` block, which the page prints as the give/get boxes and both sides'
  lineup and playoff-odds changes. The build drops a trade card with no `trade` block, and (`live_trades`) one
  whose players have since changed rosters or been ruled out, so a card never outlives its trade between runs.
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
