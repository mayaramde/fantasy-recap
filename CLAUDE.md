# Fantasy Recap

Weekly recap page for the ESPN league "Fantasy Football for the Girls" (8 teams, PPR).
League facts (IDs, teams, managers, roster slots, playoff format) live in `league.json`, and that file is the source of truth.

## Harness: Fantasy Recap

**Goal:** produce the weekly recap (capture, write, fact-check, voice-check, ship) and the daily Coach
cards, without ever publishing anything unreviewed or touching a Vercel token.

**Entry point — applies to every prompt in this repo:** You MUST invoke the
`fantasy-orchestrator` skill *before* responding to any request about drafting, redoing,
tweaking, or publishing a recap; running or updating Coach cards; or diagnosing a stale
Live page/capture/deploy. It is the single entry point for this domain; do not craft a
response outside it. The orchestrator answers trivial or out-of-domain requests directly and
routes everything else to the right skill — see `.claude/skills/fantasy-orchestrator/SKILL.md`
for the full routing table. A change to `scripts/`, `site/`, or CI that isn't about recap
*content* is normal engineering work, not this harness — it still gets `code-reviewer`, per
the project's usual review practice.

The skills say *how* the work gets done. `docs/architecture.md` says *when* the automated tasks
run and what the Live and Coach pages compute. `docs/vercel.md` covers deploys and the Vercel dashboard.

## Data sources
- **ESPN** (primary): the league is **public** (the commissioner's setting since 2026-10-09), so it's read
  anonymously, with no cookies or secrets anywhere: `scripts/capture_node.mjs` in the cloud live update and as the
  local fallback, `api/live.py` on Vercel, and Claude in Chrome for the Tuesday capture:
  `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/698468554?view=...&scoringPeriodId=N`
  If ESPN answers 401 the league has gone private again; that's the commissioner's setting to fix, not a secret
  to add (`docs/vercel.md` §6). Still never ask for, copy, print, or store ESPN cookies (`espn_s2`, `SWID`) or
  any credentials.
- **ESPN CDN headshots** (public, no auth): `https://a.espncdn.com/i/headshots/nfl/players/full/<espnId>.png`,
  and `https://a.espncdn.com/i/teamlogos/nfl/500/<abbr>.png` for a D/ST. `scripts/analyze.py` writes the URL into
  each week's top scorers; the site falls back to a silhouette when ESPN has no photo (rookies, call-ups).
- **ESPN public NFL scoreboard** (public, no auth): `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=<season>&seasontype=2&week=N`
  says which NFL games are in progress, so a live box score can mark the players who are on the field right now.
  Both captures call it without cookies, and both treat it as best effort: if it fails, the capture still succeeds
  and the site just shows no "playing" stickers.
- **ESPN public NFL news** (public, no auth): `https://site.api.espn.com/apis/site/v2/sports/football/nfl/news?limit=50`,
  fetched by `scripts/fetch_news.py` in the cloud live update for the Week hub's ticker and "Latest news" section. Only an
  article's headline, link, publish time, byline, tagged ESPN athlete ids, lead photo URL (ESPN's own CDN only) and a
  derived tag (Injury, Team news or Feature; read off the headline and blurb, since ESPN's categories carry no injury
  marker) are kept, never its text, and only when it
  tags four or fewer players, one of them on a league roster, and nothing in it reads as off-field (lawsuits, arrests,
  suspensions, deaths). Lands in `data/<season>/news/latest.json`, never committed. Best effort like the scoreboard: a
  failed fetch, or a file over 36 hours old, just means the page has no headlines.
- **ESPN scoring lines** (part of the same ESPN capture): ESPN's own points for each stat a player
  earned them with (`appliedStats`), paired with the stat behind it, ride along in `espn.json` as
  `scoring`: `[{stat, value, points}]`. The stat ids are ESPN's; `scripts/analyze.py` names the ones this
  league can score and folds anything else into one "Other scoring" row, so a player card's rows always
  add up to his total (`scripts/check.py` asserts that). Weeks captured before this don't carry the field,
  and the site simply shows no breakdown for them.
- **ESPN injury designations** (part of the same ESPN capture): each rostered player's `injuryStatus`
  (`QUESTIONABLE`, `DOUBTFUL`, `OUT`, `INJURY_RESERVE`, `SUSPENSION`, ...) rides along in `espn.json` as
  `injury_status`. It's what the Coach page and the box-score injury pills are built on. Weeks captured before
  this existed simply don't carry the field, and the site treats that as "we don't know", never as "healthy".
- **ESPN next week** (same ESPN capture, `fantasyCapture('next')`): rosters and projections for the week
  ahead, from `view=mRoster&scoringPeriodId=N+1` plus the season schedule for the pairings. Lands in
  `data/<season>/next-week/espn.json` — deliberately not under `week-NN/`, where the site would read it as the
  week in progress and it would take over the Live page. Never committed (`.gitignore`); it's recaptured on every
  live update and stale the moment the week starts. ESPN can be days from publishing next week's projections, so
  the page checks before quoting one.
- **FantasyPros MCP**: rankings, projections, injury news, player context. Pass `league_key` explicitly on every league-scoped call.
  Maya is on the free tier. Waiver Finder is premium and its upsell has already been shown. Trade Finder and Trade
  Analyzer are premium too; relay their disclosure once, the first time either gates a call
  (`trade_finder_disclosure_shown` in `latest.json` records whether it has been). `latest.json`'s `fantasypros` field (`reached`, `checked_at`, `error?`) records whether that day's run actually reached the MCP; `scripts/check.py` requires it on snapshots from 2026-10-13 on. `coach-daily` builds its
  start/sit and waiver ideas from free-tier tools instead of the gated finders, and evaluates trades itself with
  `scripts/trade_eval.py` on FantasyPros' free rest-of-season projections.
- **FantasyPros daily snapshot** (`data/<season>/fantasypros/latest.json`): the finished, voice-checked Coach cards
  `coach-daily` writes once a day for every team, keyed by week, including this week's written advice for each
  computed card (keyed by situation, see `docs/architecture.md`) and, top level, each team's written season-audit
  copy (`audit`, keyed by audit key). Committed through its own auto-merging PR (small,
  factual, derived data, like `data/player_names.json`, so no review). `site/build.py` treats it as best effort: a
  missing, malformed, or stale (>36h old) file just means ESPN-only Coach cards (written season-audit copy still
  applies while its key matches, since it describes finished weeks).

## Privacy
- The raw ESPN payload includes members' last names, ESPN IDs and notification settings. **Do not commit it.**
  Save only trimmed data (team ID, players, slots, points, projections, transactions) under `data/`.
- Recaps use first names only.

## Layout
- `data/<season>/week-NN/`: trimmed per-week data (JSON)
- `data/<season>/next-week/`: the week-ahead capture behind the Coach page's "next week" tab (uncommitted)
- `data/<season>/news/latest.json`: ESPN headlines about rostered players, for the Week hub (uncommitted)
- `data/<season>/schedule.json` (optional): `{"<week>": [[team_id, team_id], ...]}`, the real remaining matchups for the
  playoff odds; without it they draw random opponents
- `data/<season>/fantasypros/latest.json`: `fantasy-coach-daily`'s rolling snapshot of FantasyPros-sourced Coach
  cards and roster ideas (committed)
- `recaps/<season>/week-NN.json`: the written recap (awards, callouts, blurbs). Content only, no HTML.
- `site/`: template + build script → `site/dist/index.html`/`preview.html` (Claude-artifact-shaped, legacy),
  and the standalone Vercel builds `web/` (published site) and `web-preview/` (draft review copy)
- `site/bts/`: the Behind the scenes page (`#behind-the-scenes`, sections `.big/.data/.api/.harness/.deploy/.safe/.cheat`): `page.html` (markup, copy),
  `bts.css` and `bts.js` (all `bts-` prefixed), and `sprite.svg` (its illustrated icons, shipped once per document). `site/build.py`
  stitches them into `template.html`. Its claims about how the site works are audited in `docs/behind-the-scenes-audit.md`;
  change the copy and that file together.
- `site/coach/`: the Coach tab's landing (the league overview shown before anyone opens a team's report). One pure
  insight function per file (`vitals`, `fixes`, `byeDamage`, `battles`, `pickups`, `strengthMap`, `callouts`,
  `tradeMatches`, `take`), the editable headline list `headlines.js`, `landing.js` (markup) and `coach.css`.
  `site/build.py` inlines them into `template.html`. They run in the browser so they refresh with `/api/live`;
  `tests/coach/*.test.js` (run with `node --test tests/coach/*.test.js`, also in CI) check them against the Week 6
  golden values in `tests/fixtures/week-06/`. `tests/coach_preview.py` renders the page for a look in a browser.
- `site/team_profile.py`: the team profile's audit cards (and their keys) and roster moves; pure functions shared by
  `site/build.py` and `scripts/coach_brief.py`
- `site/playoffs.py`: the Standings page's playoff odds and projected bracket (stdlib-only Monte Carlo, read by
  `site/build.py` into `season.playoffs`), and the Week hub's `stakes()`: each team's odds with a win and with a loss
- `api/live.py`: the Vercel function behind `/api/live`, which recomputes the live week from ESPN per request
- `scripts/`: `capture.js` (runs in Chrome), `receive.py` (localhost receiver that also serves capture.js),
  `capture_node.mjs` (headless capture, no login), `espn_fetch.py` (capture.js's Python twin for `/api/live`), `analyze.py` (→ `facts.json`),
  `check.py` + `check_recaps.py` (data and recap checks, run by the CI `checks` workflow),
  `coach_brief.py` (the computed Coach cards and season-audit cards and their keys, which `coach-daily` writes advice for),
  `trade_eval.py` (finds and scores trades for both teams against `coach-daily`'s ground rules; only a passing trade becomes a card), `deploy.sh` + `vercel_build.sh` (deploy),
  `dev.py` (`npm run dev`, alias `dev:vercel` for v0: local server for `web-preview/`, or `web/` with `--prod`, plus `/api/live`; rebuilds and reloads on change; never a deploy path),
  `site_guard.py` (stops CI from deploying over a recap `main` doesn't have yet),
  `fetch_news.py` (ESPN headlines for the Week hub, best effort)
- `.github/workflows/`: `checks.yml` and `live-update.yml` (capture + deploy); the scheduled Claude routines run locally, see `docs/architecture.md`
- `tests/`: unittest suites for `check_recaps.py`, the Bash guard hook, the Coach page's written copy, the team
  profile, the playoff odds, the trade evaluation, the Week hub's wire, stakes and headlines, and the news filter (also run by `checks`);
  `hub_preview.py` renders the Week hub's two states for a look in a browser
- `data/player_names.json`: cache of names resolved via ESPN's public athlete API

## Published pages
- `docs/vercel.md` explains the deploy model and the Vercel dashboard for Maya; keep it true if this section changes.
- **League website (Vercel, what the league uses):** https://fantasyforthegirls.vercel.app (the only domain the repo uses), built from `site/dist/web/`.
  Deploy only with `scripts/deploy.sh`: it builds locally (including the uncommitted live week) and uploads a prebuilt
  bundle. Vercel's own git integration is off for `main` in `vercel.json` — a merge alone can't build-and-wipe the Live page —
  but a push to `main` touching `recaps/`, `data/`, `site/`, `scripts/`, `api/`, `league.json`, or `vercel.json` does
  trigger `live-update.yml` to run that same `scripts/deploy.sh` within minutes (`docs/vercel.md` §3). `scripts/deploy.sh`
  run by hand stays as a manual backstop. The site sends
  `noindex` (header, meta tag, robots.txt): public to anyone with the link, but kept out of search results.
  `/api/live` keeps the Live page fresh between deploys, reading ESPN anonymously; if ESPN refuses (the league
  went private) it answers 503 and the page shows its baked data. Needs `vercel login` on this Mac. Never read or print `.env.local`
  or Vercel tokens.
- Branch previews (Vercel, automatic): every push to a branch other than `main` gets its own preview URL, built on
  Vercel's servers from that branch's committed data only (the draft copy), plus the live week borrowed from the
  league site (`FANTASY_LIVE_FROM`, best effort, `docs/vercel.md` §3). For design and
  code review; the link shows on the PR. Same Deployment Protection as below.
- Preview (Vercel, for Maya): `scripts/deploy.sh --preview` deploys `site/dist/web-preview/` (drafts included) to a
  new throwaway `fantasy-recap-*.vercel.app` URL every time it runs. Drafts are reviewed here before they go to the
  website. Deployment Protection (Standard) puts every deployment URL, previews included, behind a Vercel
  login, so only Maya can open it; only the production aliases are public (`docs/vercel.md` §7).

## Recap content
- Matchup results, high/low scores, standings
- Good decisions: waiver pickups that paid off, smart benchings/starts
- Bench blunders: points left on the bench (optimal lineup vs actual)
- Unexpectedly screwed: injuries mid-game, big misses vs projection, bad-luck losses (e.g., 2nd-highest score but lost).
  Events must be verified from FantasyPros' injury/news desk when one exists (`recap-write`'s context-gathering step); never invent one.
- Rookie glossary: 3-5 football/fantasy terms used in that week's recap, defined in one friendly sentence each.

## Voice
This is the voice for everything Claude writes on the site, not just the weekly recap: recap copy, Coach cards, Live page copy, labels, empty states. Cheeky, a little smug, on everyone's side, like the friend at the watch party who's actually paying attention, dialed by surface (below). The league is "Fantasy Football for the Girls" and for most members this is their first season, so explain jargon in passing ("flex, the wild-card spot") and never talk down. Never a stats recap with a joke sprinkled on top.

**Calibration.** Read `recaps/2026/week-01.json` and `week-02.json` before writing anything — they're what this voice sounds like when it works. Swap in the two most recently *published* recaps once a newer one reads at that same level.

**The formula.** State a real fact, then turn it with a short line: "Amie started the best possible lineup and still lost, which feels illegal but isn't." One joke per section — headline, dek, each matchup blurb, each game ball/flag/tough break. Pick the best one and cut the rest; three jokes stacked on one blurb is worse than one good one. Deletion test: if removing the joke leaves the sentence reading the same, it wasn't a joke, it was a fact with a qualifier stapled on ("no excuse required" doesn't count). Exception: serious moments, below.

Get the joke from something true and checkable — a team name, a real callback, a stat that's absurd on its own — never from an invented feeling, effort, or motive ("without breaking a sweat," "ever the professional" aren't in the data). Techniques that work here: deadpan hyperbole, a short punchy coda (2-6 words, never re-explains the joke), an accurate pop-culture tie-in, a running callback, personifying luck or instinct ("her gut won this one"), team-name wordplay when a name sets one up, a fourth-wall aside to Maya or the reader.

**Mechanics.** No em dashes in site copy — use a period or comma. Keep it tight: short sentences, one stat line per player, one comparison per blurb (no rule-of-three filler), don't explain or moralize after the joke lands.

**Punch at decisions, hug the person.** Roast lineup decisions, projections, stat lines, the fantasy gods — never a manager's character or competence. Don't stack a second joke on whoever's already taken one this issue; her next mention is a hug. Maya's own team gets roasted too, by name, same as anyone else's.

**Serious moments: play it straight.** A season-ending injury or real bad news gets one warm, plain sentence and nothing else — no joke here or about the other side of the same matchup. Never guess at an injury or its cause; cite a real source (see Recap content) or leave it out.

**Running threads.** Pull on one, maybe two threads from the calibration recaps, not every live thread every week. Update this list as one dies or a new one starts:
- Mark Andrews: dropped by Maya Week 1, still not producing for Marlee.
- Maddie's Waddle bet: a Week 2 game ball, a Week 3 flag.
- Christian Watson on Tara's bench: Weeks 1 and 3.

**Dial by surface:**
| Surface | Dial |
|---|---|
| Headline / dek | Full personality; the dek stays short |
| Matchup blurbs, game balls, flags | One joke, coda optional |
| Tough breaks | Warm, no joke at all for real injuries |
| Glossary | Teach first, this week's example as the wink |
| Coach cards | Advice first, one line of personality |
| Labels, empty states | Short and warm, a wink at most |

**Before you call it done:** would a friend screenshot this line for the group chat? If not, rewrite it. Run the deletion test on every blurb. The jokes can exaggerate; every number stays exact.

## Design
- Palette "Tailgate pop": cobalt (navigation, links, scoreboard), tangerine (game balls), bubblegum pink (flags),
  lime (highlight badges), navy ink. Pop colors are fills with ink text on top, never text on white.
  Green/red only as small W/L labels. All tokens live in `site/template.html` `:root` (plus dark-mode blocks).
- UI style "Sticker book": 2px ink outlines, hard offset shadows, a few slightly tilted badges.
- Fonts: Big Shoulders Display (headings, scores), Figtree (body), DM Mono (numbers), Fredoka (small badge labels).
  Maya found the cursive script (Yellowtail) hard to read, so no script fonts.
