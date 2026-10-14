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
  eliminated teams are not locked out of moves during the playoffs. The Coach page's waiver order is ESPN's own `waiverRank`
  (captured as `waiver_rank`, read by `build.waiver_order` from the newest capture), since ESPN's tiebreaks aren't ours;
  captures from before the field fall back to the standings upside down.

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
- **`fantasy-weekly-recap`** runs Tuesdays around 8:15 AM: invokes `fantasy-orchestrator` to capture last week
  (final), draft and fact-check the recap, open the `Week NN recap draft` PR, and deploy a review preview. It stops
  there. Maya approves the preview before `recap-ship` publishes and opens the `Publish week NN recap` PR — merging
  that PR is what triggers the push-deploy above.
- **`fantasy-coach-daily`** runs once a day: invokes `coach-daily`, which writes FantasyPros-sourced Coach cards
  (start/sit, waiver ideas, evaluated trades, injury/news changes since yesterday) to `data/2026/fantasypros/latest.json`
  and archives a dated copy as `history/<date>.json` (plus a compact `history/index.json`), then opens its own auto-merging PR. It works in its own git worktree so it never switches branches under another
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
- While games are on, the scoreboard (`liveBoard` in `site/template.html`, logic in `site/live/live.js`) leads with
  "Your game" for the Viewing-as team (else the closest game, with a "Pick your team" button), then "Rest of the
  league" as tug-of-war cards, closest first. Sides never swap: yours on the left, otherwise the lower team id. The
  verdict sticker is ESPN's win chance for the favorite (0.85 or more "Nearly locked", 0.65 or more "Leaning", else
  "Coin flip"). A "+X.XX" tag and a "Lead changed" sticker last for one `/api/live` refresh, diffed in the browser
  against the previous refresh (nothing on first load). The page says it is a few minutes behind when the capture
  is over five minutes old.
- The "Still to come" meter uses `remaining_projection` (`scripts/analyze.py`): full projection for starters whose
  game is ahead, what is left of it for one mid-game, nothing once his game is over. ESPN's own team figure
  (`live_projection`) is not points plus remaining, so it is shown only as "Projected".

## Week hub ("This week")

What the Live tab shows when nothing is on the field (`landingPage` in `site/template.html`): before the week's
first kickoff, and again once every game is final and the recap isn't out yet.

- **Before kickoff**: a season strip, up to four scoreboard cards (Closest, Favorite, Top projection, Biggest fix: a label, a
  big number with its unit, a first name and one small line, 2×2 on a phone), then one card per matchup beside Coach's desk and
  the projections ranked. The reader's own game sorts first when the browser remembers her team (picked with the
  "Viewing as" chip in the header); otherwise the game with the most at stake leads.
- **Where each piece comes from.** Everything a lineup change can move is drawn in the browser from the live
  games and Coach rows, so it refreshes with `/api/live` and can't disagree with the projected scores beside it:
  the split bar, the **edge strip** (per lineup spot, who leads and by how many projected points, RB and WR
  summing both starters), the ranked projections, the stickers and **Coach's desk** (every team's "do this now"
  swaps, byes, outs and empty slots, biggest projected gain first; a swap card carries its `gain` as a number
  for this).
- **Lineup rows** (`player()` in `site/build.py`, built on the live week by `/api/live` and the build alike): each
  starter and bench row in "Full lineups" carries `player_id` (ESPN's player id, the headshot's key), `team` (NFL
  abbreviation), `logo`, `kickoff` and, when it applies, `injury` and `bye: true`. A D/ST has no headshot, so its
  `team` and `logo` come from its pro team id like everyone else's. Each is whatever ESPN gave: the scoreboard is
  best effort, so a capture without game states has a null `kickoff` and no `bye`, and one without `injury_status`
  has no `injury`. Absent means unknown, never "healthy" or "has a game". `bye` is the Coach cards' own rule
  (`is_on_bye`: game states are known and he has no game), so a bye player has `bye: true` and a null `kickoff`.
  `playing` is still present only while his game is on. Recapped (finished) weeks keep the plain rows without any of
  these. The Week hub's "Full lineups" draws them (`hubRow` in `site/template.html`): the player's face with his NFL
  badge (a D/ST gets its logo), team and kickoff in the viewer's own time zone, a status sticker (Q, DTD, D, OUT, IR,
  SUSP or BYE; a designation wins over a bye), a soft row tint for a row with a status, and an "N to check" flag on
  the side. With no injury report in the capture the legend is replaced by a note saying a blank isn't "healthy".
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
- **Ticker and Latest news** (`live.hub.news` and `news_at`, baked): `scripts/fetch_news.py` runs in the live-update
  workflow before the build and writes `data/<season>/news/latest.json`, never committed. It keeps an article only if
  it tags four or fewer players, at least one on a league roster, and nothing in the headline or description reads
  as off-field, plus its tag and ESPN-CDN photo. The build (`news_items`) re-matches each article against the live
  rosters and keeps up to twelve in ESPN's order, each with its owners and the rostered players (name, position,
  NFL team, headshot). The link must be `https://www.espn.com/...` and the photo `https://a.espncdn.com/...`. The
  browser ranks them: the viewer's team first, then injuries, then ESPN's order. The viewer is the team Coach
  already remembers in `localStorage` (`ffg-coach-team`); with none there are no highlights. The ticker (a bar under
  the nav on This week only, drawn outside `#main` so a live refresh doesn't restart its scroll) shows the first
  twelve; Latest news sits at the bottom with team chips, a lead card and a grid. A file over 36 hours old is
  ignored, and a fetch that fails or finds nothing hides both quietly. Since it only refreshes on a deploy,
  midweek headlines are up to a day old. Off switch: the repo variable `NEWS_ENABLED=false` skips the fetch.
- **Phone tabs** (620px and under): the bottom of This week becomes a tab switch (Latest news, League wire,
  Projected) over the same sections the desktop draws. Local state, not persisted, and it never refetches.
- **After the last game**: the final scores and stickers as before, plus the wire and the headlines. No
  stakes, edge strip or Coach's desk for a week nobody can change.
- A module with nothing to show is left out, never drawn empty.
- `tests/hub_preview.py <dir>` renders both states from committed data for a look in a browser. A normal build
  of committed data has no live week, so a Vercel branch preview never shows this page; review it with
  `scripts/deploy.sh --preview` from a checkout that has a live capture.

## Coach page

- (With a pick, `#coach` and `#coach-next` redirect to her **League** tab, `#team-<id>.league`; the landing below is what
  the league view, with no pick, sees, opening with a "Make this page yours" name picker.)
- A league-wide grid at `#coach` (the week being played) and `#coach-next` (the week after it, from the
  `next-week` capture; no tab when that capture is missing or stale): the viewer's team and a league radar on
  top, then **Where everyone's strong**, an 8 × 7 heat grid of each team's league rank (1–8) at QB, RB, WR, TE, FLEX,
  DST and K. The ranks are season points at each lineup spot, the same ones behind the profile's Position strength
  card (`team_profile.position_ranks`, shipped as `profile.pos_ranks`), so both weeks' tabs show the same grid and it
  stays empty until a week has a recap. Each team's best spot gets a lime sticker and her weakest a pink one; there
  are no letter grades. A last **AVG** column is the mean of her seven ranks, unshaded. Under it sit two cards: **Waiver order this week** (ESPN's `waiver_rank`, which resets to
  worst-record-first each week) and **Injuries and byes** (`report` on each advice row, from
  `build.injury_report`: every hurt or bye-week player, starters first; its This week / Next week toggle is local to
  the card). Each team's own week lives
  on her **team profile** (`#team-<id>`, `.lineup`, `.next` for next week, `.season`); the old `#coach-<id>` and
  `#coach-next-<id>` links redirect there. Once the live week is final the page leads with next week. The browser
  remembers the team picked with the "Viewing as" chip, never the last one opened. The grid and the profile's week sections disappear once the live week's recap is
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
- **The Coach landing's quips and take.** The one-line quip on each team's card is that team's `summary`, capped at
  110 characters (the build drops a longer one). The dark "Coach's take" paragraph is the week's `league` entry,
  filed under `league_key` (a hash of every team's `summary_key`, printed by `coach_brief.py` next to the facts it
  sums up). Both are cached by key: `coach-daily` carries yesterday's entry forward while its key is unchanged and
  writes fresh copy only when the situation moved. Missing, stale, over-length or mismatched copy falls back to
  the page's own wording, so a failed generation never leaves a blank or a wrong card.
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
- **What-if mode** (four-team, no-reseed format only): `bracket.what_if` carries every semifinal winner probability,
  all four possible finals, and the eight scenarios (`P = P(semi 1) × P(semi 2) × P(final)`, treated as independent;
  they sum to 1). Final odds come from the same Gaussian `win_prob()` as the chalk bracket, so none are estimated
  (`est: false`; the page prints a "~" and a footnote line only if a future source sets it). A scenario's odds run
  lower than the champion's title odds because title odds also count other seeds. Other formats keep the plain bracket.

## Team profile

**Viewing as** (every page): a glowing chip in the site header (`viewingAs` in `site/template.html`) says whose eyes the
site is wearing. First visit with nothing saved asks "Who are you?" (8 teams or "Just looking"). The menu lists all 8
teams, "Open <name>'s team page" and "League view"; every change raises an Undo toast. The pick lives in
`localStorage` (`ffg-coach-team`, and `ffg-viewing-asked` so it never nags), with in-memory fallbacks when storage is
blocked. The pick is "who I am", and it decides where Coach goes: the single **Coach** nav item opens `#team-<me>` (the league
landing `#coach` with no pick), and `#coach` / `#coach-next` redirect to `#team-<me>.league` once someone is picked. It also
lights the pick's team orange (the "You" badge). Which team is on screen is the URL's, not the pick's, so `#team-<other>`
still shows that team with the same layout, written about as "her" (`herCopy` in `site/coach/pronouns.js` swaps the
second person in the computed and written copy), with a "Back to my team (<name>)" chip, or "Back to the league" with no
pick. Letting go of the pick (League view) while on that team's pages returns to `#coach`. Every change, including the
landing's "Make this page yours" chips, raises the Undo toast, since a wrong pick now changes what opens.
Browsing a team never makes it "you". On phones the header collapses to a 48px bar past 70px of scroll (and reopens
below 20px); `siteHead` adds the height it gave up back as a margin, and `tpSticky` keeps the team tab bar's sticky `top`
equal to the header's measured height (scroll, resize, header resize, fonts).

Every tab opens with the same header: breadcrumb, the team strip (standings order, pink badge = fixes waiting, orange dot =
you), the dark identity card (playoff odds as a range from the Week hub's `stakes`, "lose–win vs <opponent>"; once the week
has kicked off the range is gone and it shows today's single number, labelled), and a sticky Overview / Lineup / Season / League bar.

- **Overview** `#team-<id>`: the matchup (ESPN's win chance, both projections, starters left, what to fix), the playoff
  card (seed, top-4 line, the odds if she loses / beats her opponent and what the game is worth), **Coach's take**
  (one audit card, then this week's waiver and trade ideas: three up front, the rest behind "N more ideas") and **Who's next**
  (the week-ahead opponent, the one player of theirs to watch, and a one-line reason: Injury watch, Her engine or Top threat;
  it only appears once the next-week capture exists).
- **Lineup** `#team-<id>.lineup`, and `#team-<id>.next` for next week (the week toggle lives here): a To fix card, then one
  expandable row per player (Top scorers' headshot and logo sources, kickoff time from the public scoreboard's `kickoff`,
  Coach's blurb and scoring lines in the panel); the next-week view then ends with **Coach's advice** (waiver and trade
  ideas), since Overview only shows this week's.
- **League** `#team-<id>.league`: the league-wide half of the Coach landing, built by `coachLeague` in `site/coach/landing.js`
  from the same pieces as `#coach` (one source of truth): Coach's take, **Where everyone's strong**, **Waiver order this week**
  and **Injuries and byes**, for the week being played. The pick's row is orange ("you"), the open team's cobalt-soft
  ("viewing"), and names in the grid and waiver order open that team's profile. Empty states: no recapped week shows "No
  grid yet"; a take coach-daily hasn't written (no `league_take`, or an unwritten audit card on Overview) shows the computed
  wording on a light card with a one-line note. The This week / Next week toggle stays on Lineup only.
- **Season** `#team-<id>.season`: score-by-week chart with the season average, stat tiles, the full audit, week by week, and
  every award and the roster moves as accordion rows. Awards carry their story text and the players they name
  (`build.award_players`); audit cards carry `players`; moves carry `added_ids` / `dropped_ids`.

- **Audit** (`site/team_profile.py`, from recapped weeks only): Lineup IQ (`lineup:<band>:<benched id>:w<week>`, or `:none` / `:scattered`),
  Position strength (`pos:<best><rank>:<worst><rank>`, e.g. `pos:RB1:WR8`; the worst group is her `weak_spot`) and Projection vs reality
  (`proj:<over|under>:<top id>:<bottom id>`). The A–D band exists only in the key, never on the page.
  `coach-daily` writes copy per key into `latest.json`'s top-level `audit`; it applies on key match alone, with no
  36-hour gate, since the key already describes finished weeks.
- **Roster ideas** whose optional `pos` equals her `weak_spot` get a "fills your weak spot" sticker.
- **Moves**: adds, drops and trades from every captured week (the live week included), newest first. ESPN's
  "Player 12345" placeholders are filled from `data/player_names.json` when `analyze.py` has looked them up.
