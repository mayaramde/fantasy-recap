# Fantasy Recap

Weekly recap page for the ESPN league "Fantasy Football for the Girls" (8 teams, PPR).
League facts (IDs, teams, managers, roster slots) live in `league.json`, and that file is the source of truth.

## Harness: Fantasy Recap

**Goal:** produce the weekly recap (capture, write, fact-check, ship) and the daily Coach
cards, without ever publishing anything unreviewed or touching an ESPN cookie/Vercel token.

**Entry point — applies to every prompt in this repo:** You MUST invoke the
`fantasy-orchestrator` skill *before* responding to any request about drafting, redoing,
tweaking, or publishing a recap; running or updating Coach cards; or diagnosing a stale
Live page/capture/deploy. It is the single entry point for this domain; do not craft a
response outside it. The orchestrator answers trivial or out-of-domain requests directly and
routes everything else to the right skill — see `.claude/skills/fantasy-orchestrator/SKILL.md`
for the full routing table. A change to `scripts/`, `site/`, or CI that isn't about recap
*content* is normal engineering work, not this harness — it still gets `code-reviewer`, per
the project's usual review practice.

Architecture detail that used to live in this file (the schedule of automated tasks, what the
Live and Coach pages compute) is now in `docs/architecture.md` — the skills above are the
current source of truth for *how* the work gets done; that doc is reference material for *when*
things run and what the pages show.

**Change history:**
| Date | Change | Target | Reason |
|------|--------|--------|--------|
| 2026-09-29 | Added `recap-fact-checker`; dropped `Bash` from `code-reviewer` (orchestrator passes the diff in-prompt); removed `researcher` (built-in Explore covers it) | `agents/recap-fact-checker.md`, `agents/code-reviewer.md`, `agents/researcher.md` | Harness plan PR 5 |
| 2026-09-29 | Built `fantasy-orchestrator` + `recap-capture`/`recap-write`/`recap-ship`/`coach-daily` skills, tools registry, `docs/architecture.md` | `skills/fantasy-orchestrator/`, `skills/recap-capture/`, `skills/recap-write/`, `skills/recap-ship/`, `skills/coach-daily/`, `docs/architecture.md` | Harness plan PR 6 |

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
  gates a call. The `coach-daily` skill (see `docs/architecture.md`) uses `get_projections`, `injury_status`, `get_ecr`,
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
  Cite a real cause from FantasyPros' injury/news desk when one exists (`recap-write`'s context-gathering step); never invent one.
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
