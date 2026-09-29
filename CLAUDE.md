# Fantasy Recap

Weekly recap page for the ESPN league "Fantasy Football for the Girls" (8 teams, PPR).
League facts (IDs, teams, managers, roster slots) live in `league.json`, and that file is the source of truth.

## Data sources
- **ESPN** (primary): the league is private. Read it through **Claude in Chrome**, which uses Maya's logged-in session:
  `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/698468554?view=...&scoringPeriodId=N`
  Never ask for, copy, or store ESPN cookies (`espn_s2`, `SWID`) or any credentials.
  Two exceptions, both cookie-based captures run by `scripts/capture_node.mjs` (never Claude reading the values,
  only a script consuming them): the cloud live update reads them from GitHub Actions secrets (`ESPN_S2`,
  `ESPN_SWID`) that Maya set herself; and, on this Mac, if the Chrome capture 401s (Maya's ESPN session logged
  out) and `.env.espn.local` exists (copy `.env.espn.local.example`, gitignored, Maya fills in the values
  herself from Chrome DevTools), fall back to `node scripts/capture_node.mjs N`. Claude never sees, prints, sets
  or rotates any of these values; when they expire, Maya updates them. Chrome stays the default for every
  capture — this is a fallback for when it can't authenticate, not a replacement.
- **ESPN CDN headshots** (public, no auth): `https://a.espncdn.com/i/headshots/nfl/players/full/<espnId>.png`,
  and `https://a.espncdn.com/i/teamlogos/nfl/500/<abbr>.png` for a D/ST. `scripts/analyze.py` writes the URL into
  each week's top scorers; the site falls back to a silhouette when ESPN has no photo (rookies, call-ups).
- **ESPN public NFL scoreboard** (public, no auth): `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=<season>&seasontype=2&week=N`
  says which NFL games are in progress, so a live box score can mark the players who are on the field right now.
  Both captures call it without cookies, and both treat it as best effort: if it fails, the capture still succeeds
  and the site just shows no "playing" stickers.
- **ESPN scoring lines** (part of the same private capture): ESPN's own points for each stat a player
  earned them with (`appliedStats`), paired with the stat behind it, ride along in `espn.json` as
  `scoring`: `[{stat, value, points}]`. The stat ids are ESPN's; `scripts/analyze.py` names the ones this
  league can score and folds anything else into one "Other scoring" row, so a player card's rows always
  add up to his total (`scripts/check.py` asserts that). Weeks captured before this don't carry the field,
  and the site simply shows no breakdown for them.
- **ESPN injury designations** (part of the same private capture): each rostered player's `injuryStatus`
  (`QUESTIONABLE`, `DOUBTFUL`, `OUT`, `INJURY_RESERVE`, `SUSPENSION`, ...) rides along in `espn.json` as
  `injury_status`. It's what the Coach page and the box-score injury pills are built on. Weeks captured before
  this existed simply don't carry the field, and the site treats that as "we don't know", never as "healthy".
- **ESPN next week** (same private capture, `fantasyCapture('next')`): rosters and projections for the week
  ahead, from `view=mRoster&scoringPeriodId=N+1` plus the season schedule for the pairings. Lands in
  `data/<season>/next-week/espn.json` — deliberately not under `week-NN/`, where the site would read it as the
  week in progress and it would take over the Live page. Never committed (`.gitignore`); it's recaptured on every
  live update and stale the moment the week starts. ESPN can be days from publishing next week's projections, so
  the page checks before quoting one.
- **FantasyPros MCP**: rankings, projections, injury news, player context. Pass `league_key` explicitly on every league-scoped call.
  Maya is on the free tier. Waiver Finder is premium, and the upsell has already been shown; Trade Finder and Trade
  Analyzer are premium too, and their disclosure hasn't been shown yet — relay it once, the first time either one
  gates a call. `fantasy-coach-daily` (see Schedule) uses `get_projections`, `injury_status`, `get_ecr`,
  `get_player_ownership`, `get_leaders` and `get_roster(all_teams=true)` — all free-tier — to build start/sit,
  waiver and trade ideas itself rather than relying on the gated finder tools.
- **FantasyPros daily snapshot** (`data/<season>/fantasypros/latest.json`): the finished, voiced Coach cards
  `fantasy-coach-daily` writes once a day — start/sit suggestions (`consensus`), waiver and trade leads
  (`roster_ideas`), and day-over-day injury/news changes (`fp_news`/`fp_back`) for every team, keyed by
  week under `weeks`. Unlike `next-week/espn.json`, this **is** committed, through a PR that
  auto-merges (squash) once `checks` passes, with no review (small, factual, derived data, the same category as `data/player_names.json`, not the human-reviewed recap content). `site/build.py`
  treats it exactly like `next-week/espn.json` otherwise: best effort, and a missing, malformed, or stale
  (>36h old) file just means ESPN-only Coach cards, same as before this existed.

## Privacy
- The raw ESPN payload includes members' last names, ESPN IDs and notification settings. **Do not commit it.**
  Save only trimmed data (team ID, players, slots, points, projections, transactions) under `data/`.
- Recaps use first names only.

## Layout
- `data/<season>/week-NN/`: trimmed per-week data (JSON)
- `data/<season>/next-week/`: the week-ahead capture behind the Coach page's "next week" tab (uncommitted)
- `data/<season>/fantasypros/latest.json`: `fantasy-coach-daily`'s rolling snapshot of FantasyPros-sourced Coach
  cards and roster ideas (committed)
- `recaps/<season>/week-NN.json`: the written recap (awards, callouts, blurbs). Content only, no HTML.
- `site/`: template + build script → `site/dist/index.html`/`preview.html` (Claude-artifact-shaped, legacy),
  and the standalone Vercel builds `web/` (published site) and `web-preview/` (draft review copy)
- `scripts/`: `capture.js` (runs in Chrome), `receive.py` (localhost receiver that also serves capture.js), `analyze.py`
- `data/player_names.json`: cache of names resolved via ESPN's public athlete API

## Weekly routine (Tuesday, after MNF is final)
1. **Capture.** Start `python3 scripts/receive.py --count 1` (background). In Chrome, open a tab at
   `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/698468554?view=mStatus`
   and run in it (javascript_tool):
   `eval(await fetch('http://127.0.0.1:8765/capture.js').then(r => r.text())); await fantasyCapture([N])`
   → writes `data/2026/week-NN/espn.json`. Never retype the captured JSON by hand. Check `complete: true`.
   `await fantasyCapture('next')` in the same tab writes `data/2026/next-week/espn.json` for the Coach page's
   next-week tab (raise `--count` to accept both). The cloud live update does this on its own; it's only worth
   doing by hand when the site needs the tab before the next scheduled run.
   If ESPN returns 401 (Maya's Chrome session logged out) and `.env.espn.local` exists, fall back to
   `node scripts/capture_node.mjs N` instead of stopping — same output file, same `complete` field to check.
   Only stop and tell Maya if that also fails or `.env.espn.local` isn't set up (see Data sources).
2. **Analyze.** `python3 scripts/analyze.py` → `facts.json` per week.
3. **Context.** FantasyPros MCP for injury/news on notable players (only claim an injury if a source says so).
   Before writing a bust, bad-luck-loss, or bench-blunder callout, check whether FantasyPros' injury/news desk
   gives a real cause and cite it if so — never invent one when there isn't one.
4. **Write.** `recaps/2026/week-NN.json` with `"status": "draft"`. Schema: `headline`, `dek`,
   `matchups` (keys `"<lowTeamId>-<highTeamId>"`), `game_balls` / `flags` / `tough_breaks`
   (each `{manager, title, text, stat}`). Every number must match `facts.json` or `espn.json`.
5. **Build.** `python3 site/build.py` → `site/dist/web-preview/` (drafts included, what step 6 deploys) and
   `site/dist/web/` (published only, what `scripts/deploy.sh` ships).
6. **Review.** `scripts/deploy.sh --preview` — builds the draft copy and deploys it to a fresh, throwaway Vercel
   URL. Run it while the recap's branch is still checked out: the draft recap file only exists on that branch,
   not on `main`, so switching back first would build a preview missing the week you just wrote. Share the
   printed URL with Maya; she reviews there.
7. **Ship.** Only after Maya approves: set `"status": "published"`, then run `scripts/deploy.sh` to update the website.
8. **Commit.** On a branch: commit, push, open a PR, and enable auto-merge (squash). It merges once the `checks`
   workflow passes (`python scripts/check.py` runs the same checks locally). Don't push to `main` directly.

## Schedule
- **Cloud live update** (`.github/workflows/live-update.yml`, GitHub Actions): hourly during NFL game windows plus a
  daily 7:30 AM EDT run. Captures the current week headlessly (`scripts/capture_node.mjs`, same `capture.js` trimming),
  then captures the week after it (`capture_node.mjs next`) for the Coach page, a step allowed to fail without
  taking the live scores down with it. Then analyze + check, then `scripts/site_guard.py` refuses to deploy if the live site has a published recap that
  `main` doesn't (a recap shipped from the Mac whose PR hasn't merged). Then `scripts/deploy.sh`. Nothing is committed.
  A failure email saying "ESPN 401" means the ESPN cookie secrets expired.
- `fantasy-live-update` (local, this Mac) runs daily at 7:30 AM: captures ESPN's current week (`fantasyCapture('current')`), then runs
  `scripts/deploy.sh` so the website's **Live** page is current. Data only, no commentary, no commits. The in-progress
  week's `data/2026/week-NN/` files stay uncommitted until that week's recap PR.
  **Paused 2026-09-28** now that the cloud live update works. Re-enable it only if the cloud run can't be fixed
  (e.g. while waiting on fresh ESPN cookies).
- `fantasy-weekly-recap` runs Tuesdays around 8:15 AM: captures last week (final), drafts the recap, updates the preview,
  and opens a draft PR. Maya approves before the recap reaches the league site.
- `fantasy-coach-daily` runs once a day: pulls FantasyPros projections, rankings, ownership and injury/news for
  all 8 rosters, and writes finished, voiced Coach cards — start/sit suggestions, waiver and trade leads, and what's
  changed in FantasyPros' injury report since yesterday — to `data/2026/fantasypros/latest.json`. Unlike the recap,
  this opens its own PR with auto-merge (squash) on and merges once `checks` passes, with no review (small, factual,
  derived data). It works in its own git worktree, so it never switches branches under another session. Data only
  otherwise: it doesn't deploy, touch any recap, or touch any `data/2026/week-NN/` file; the next live-update run
  picks up the merged snapshot.
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
  authored daily by `fantasy-coach-daily` from FantasyPros MCP data (see Data sources), not computed here —
  `site/build.py` only decides whether that day's snapshot is fresh enough to merge in, and refreshes with the
  same request that serves the rest of the live week.
- Every row of either Coach lineup opens into that player's own card (`player_cards` in `site/build.py`): one
  cheeky line about his week, ESPN's scoring broken down stat by stat, and a few notes — his share of your
  total, what the injury report says and whether that's new, where his game is up to, what else you have at
  that spot. Same rule as the to-do cards: the numbers are ESPN's, the jokes are ours, and no card reports news
  no source gave us. A week nobody has played has no stat line to break down, so its cards are the blurb and
  the notes; with no projections published yet, nothing quotes one.

## Published pages
- `docs/vercel.md` explains the deploy model and the Vercel dashboard for Maya; keep it true if this section changes.
- **League website (Vercel, what the league uses):** https://fantasyforthegirls.vercel.app (also answers at fantasy-recap-eight.vercel.app), built from `site/dist/web/`.
  Deploy only with `scripts/deploy.sh`: it builds locally (including the uncommitted live week) and uploads a prebuilt
  bundle. Git-triggered Vercel deploys are off in `vercel.json` so a merge can't wipe the Live page. The site sends
  `noindex` (header, meta tag, robots.txt): public to anyone with the link, but kept out of search results.
  Needs `vercel login` on this Mac. Never read or print `.env.local` or Vercel tokens.
- Preview (Vercel, private, Maya only): `scripts/deploy.sh --preview` deploys `site/dist/web-preview/` to a new
  throwaway `fantasy-recap-*.vercel.app` URL every time it runs — there's no fixed link to bookmark. Deployment
  URLs aren't guessable or indexed (`docs/vercel.md` §7), so that's the only access control it has. Drafts are
  reviewed here before they go to the website. Retired 2026-09-29: the Claude artifact preview this replaced.
- Old league artifact (retired 2026-09-28, no longer updated): https://claude.ai/artifact/XU5jqS5WzR47mK3kCDhNKZ

## Recap content
- Matchup results, high/low scores, standings
- Good decisions: waiver pickups that paid off, smart benchings/starts
- Bench blunders: points left on the bench (optimal lineup vs actual)
- Unexpectedly screwed: injuries mid-game, big misses vs projection, bad-luck losses (e.g., 2nd-highest score but lost).
  Cite a real cause from FantasyPros' injury/news desk when one exists (weekly routine step 3); never invent one.
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
