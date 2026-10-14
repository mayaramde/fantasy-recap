# Behind the scenes: mockup audit

The mockup was designed without the codebase, so every claim it makes about how the site works was
checked against the code, workflows and docs. Each item is labelled **Fixed**, **Needs my decision** or
**Factually unverified**. The page's own copy (`site/bts/page.html`, `site/bts/bts.js`) reflects the
"Fixed" rows; if the site changes, change the copy and this file together.

## Needs my decision

1. **Coach's voice: "I" or "she".** The site talks *about* Coach in the third person ("Coach has her back",
   "she needs one finished week"). The mockup lets Coach speak as "I" in labelled COACH speech bubbles. I kept "I"
   inside the bubbles (it's a character speaking, and it's what makes the page fun) and "Coach / she" everywhere
   else. Say the word if you'd rather the whole page be third person.
2. **"Go ahead, try to trip me up" implies live Q&A, and there is none.** The site has no chat. Coach writes
   cards once a day and the Coach page computes the rest. I kept the five buttons you asked for, but they now say
   "The site doesn't take live questions, so these are example replies that show how my rules work." Keep as is,
   rename ("How Coach's rules would answer"), or drop?
3. **Layer 5, "a human is in charge".** True for recaps (Maya approves a preview, then a publish PR). It is **not**
   true for Coach's daily cards: `coach-daily` opens a PR and turns on auto-merge with no human review
   (`.claude/skills/coach-daily/SKILL.md`, step 7). The copy now says exactly that. Is that the message you want on a page
   the league reads?
4. **Existing copy that disagrees with the code.** The Live page says "Scores refresh about every minute"
   (`site/template.html`, the `liveLabel` dek). `livePace()` actually polls every 20 s while somebody's game is on and every
   60 s otherwise. The new page uses the real numbers. I did not touch the Live page.
5. **Icon sprite: inline or a separate file?** It is defined once and inlined once per document (14 KB, 29 icons),
   not per page. A separate cached `bts-sprite.svg` would shave 14 KB off every first load, but the legacy
   single-file artifact build (`site/dist/index.html`) and `scripts/dev.py` would lose their icons. Inline stays unless
   you decide the artifact build is dead.
6. **Glossary overlap.** The mockup teaches *API*, *cache* and *agentic harness*. None of them is in the Glossary,
   and nothing contradicts it (the Glossary page is built only from each recap's `glossary` array, so a term can
   only be added by a recap). Want those three added to a future recap's glossary so the two pages can link?
7. **No per-page `<title>` and hash-route page views.** Every route shares one static `<title>`
   (`__PAGE_TITLE__`), and Vercel Web Analytics only counts the initial load, so visits to this page won't show up
   as page views. Existing behaviour for every page; not changed here.
8. **Nav on a phone.** Six tabs don't fit at 390 px, so the nav scrolls inside itself (the site's existing
   `overflow-x: auto`, with a visible scrollbar line under it). I scroll the active tab into view when the page opens.
   Shortening the label ("Behind scenes", "How it works") would avoid the scroll; you asked for the full name, so I left it.
9. **Screenshots are committed** under `docs/behind-the-scenes/` so the PR can show them. Delete the folder
   before merging if you don't want them in the repo.

## Fixed: facts

| Mockup claim | What the code says | Result |
|---|---|---|
| Data is "ESPN plus a few other data sources" | ESPN for league data, headshots/logos (ESPN CDN), the public NFL scoreboard and public headlines; FantasyPros (free tier) for Coach's rankings, start/sit, waivers, news (`CLAUDE.md` Data sources) | Named them: "ESPN + FantasyPros" |
| Scouts refresh "on a schedule", site keeps "the last answer handy" | `live-update.yml`: hourly during NFL game windows plus 7:30 AM EDT daily, and on every push to `main`; the build bakes the data into the page; `/api/live` re-asks ESPN every 20 s (game on) or 60 s | Copy now states hourly + every morning, and the 20 s / 60 s pace |
| Sticky note = cache | Matches the Coach page's "captured <time>" stamp (`coachSource`) | Kept, and points at the stamp. Coach's FantasyPros snapshot is ignored once 36 h old; next week's tab is baked at build and never refreshed by `/api/live` |
| "Some doors need a key or login" | Our league is public on ESPN; every read is anonymous, there are no ESPN secrets (`docs/vercel.md` §5b) | Says so |
| Vercel "notices a new version, sets up the field, opens the gates" | Production does **not** deploy from Vercel's git integration (`vercel.json`: `deploymentEnabled.main = false`). A GitHub Actions run does checks, then `scripts/deploy.sh` builds with Vercel's CLI and uploads. Vercel's own git build is only for branch/PR previews | Pipeline reads "Check, then build"; GitHub robot runs the checks |
| "Goes live in about a minute" | The last six `live-update` runs took 45-52 s each. That is run time; queueing isn't included | Kept "about a minute" |
| "A failed build never replaces the live site" | Steps run in order (analyze, `check.py`, `site_guard.py`, `deploy.sh`) and the upload is last, so a failure stops before anything is published; a failed run opens or comments on a GitHub issue | True; copy also mentions the alert, not "nobody notices" |
| "Rewind button" | Vercel Instant Rollback, to a Production row only (`docs/vercel.md` §7). Maya-only | Says Maya can roll back in Vercel |
| "Preview link before it touches the real site" | True; Deployment Protection means only Maya's Vercel login opens a preview | Added "Only Maya can open it" |
| Coach "looks things up live" | The Coach page's computed cards refresh with each capture; the written cards are authored once a day | "Pulls fresh numbers every day" |
| "Reads every roster in it" | `coach-daily` writes for all 8 rosters | Kept, with "all eight" |
| "Checks its work, loops back if unsure" | The recap path has `recap-fact-checker` and `voice-check`; `coach-daily` has a mandatory `voice-check` gate (step 5c) and runs `check.py` (step 7). A literal "loops back" isn't documented | "Gets its work checked before it ships" |
| Coach tools are read-only | Coach *reads* ESPN and FantasyPros, but also writes its own snapshot file and opens an auto-merging PR (never pushes to `main`; a Bash guard hook blocks that and any secret read) | Layer 1 reworded: reads only, never changes ESPN, her one write is a PR |
| "Passwords and API keys live in a locked vault, never in the public code" | The one real secret is `VERCEL_TOKEN` (GitHub Actions secret); org/project ids are repo variables. `CLAUDE.md` forbids reading or printing tokens | Reworded; "public code" dropped (see unverified) |
| "Ask Coach", "Answers your questions", "start or sit question" | No chat on the site | Reworded to "Coach's notes", "Writes the daily notes"; the stepper's prompt is now "Is anybody on the bench better than who's starting?" |
| "Win odds" | The site calls them playoff odds | Renamed |
| Raw ESPN sample used `points.for` / `against` | Real capture reads `record.overall.pointsFor` / `pointsAgainst` | Sample matches ESPN's shape; still labelled example data |

## Fixed: anchors, links, structure

- **Anchor collisions.** The mockup's `#big #data #api #coach #deploy #safe #cheat` collide with the router (`#coach` is a real
  page). Every id on the page is `bts-…`. Chips and "see how…" links keep a real `#behind-the-scenes.<section>` href (so a pasted link works,
  and the same dot pattern as `#week-4.awards`), and a click scrolls and rewrites the URL with `history.replaceState`, so no
  `hashchange`, no redraw, no lost accordion or demo state. Verified in the browser: zero hashchange events per jump.
- **Dead links.** Footer `#coach-page` → the live Coach route (`coachHref()`, so it follows next-week mode); hidden when the Coach tab
  is hidden, because `#coach` is a 404 without advice. "Back to Standings" → `#standings`.
- **Unknown sub-route.** `#behind-the-scenes.nope` falls through to the site's "Fumble" page; the route only accepts the seven section names.
- **Scroll offset under the sticky header.** The header is 66 px on desktop and 102 px at 390 px (it wraps to two rows), so jumps
  measure `.site-head` instead of using a fixed number.
- **Accessibility fixes the mockup lacked.** Accordion panels are `role="region"` and `inert` while closed (their links were
  tabbable); the raw/clean switch used `role="tablist"` with no tabs, now a `aria-pressed` group; demo outputs are `aria-live`; the
  stepper marks `aria-current="step"`; decorative SVGs are `aria-hidden`; transitions and the icon hop only run under
  `prefers-reduced-motion: no-preference`; focus rings use the site's accent outline.
- **Sprite.** Defined once; the 24 unused line icons from the mockup are dropped (53 → 29 symbols) and every id is `bts-`-prefixed.
- **Phone layout.** No horizontal scroll at 390 px (checked). Six chips stay on one line on desktop and wrap to two columns on a
  phone. The cheat-sheet table stacks into labelled cards under 560 px.
- **Mockup-only pieces deleted.** Its duplicate header (with a "This week" tab; the site's tab is "Live", and hidden without live data), its
  `:root`, its five stacked override `<style>` blocks, inline styles and emoji.

## Fixed: design drift (what I followed)

I followed the **live site** everywhere they differed.

- Cards, bubbles and panels: the site's sticker (2 px `--edge` outline, 4 px hard `--drop` shadow, 14 px radius), not the mockup's
  3 px / 6 px / 22 px.
- Buttons: the site's accent pill with a hard shadow and press-down state, not the mockup's ink-and-lime button.
- Page header: the site's `.page-head` + `.kicker` + `h1`, not the mockup's eyebrow and football glyph.
- Colour: only the site's tokens (`--accent`, `--lime`, `--rule`, `--board`, `--logo-chip`…). Text on lime/pink/orange uses `--on-pop`
  so it stays dark in dark mode.
- **Dark mode.** The mockup was light-only; the site follows the OS (and `data-theme`). The page works in both (checked). The
  illustrated icons keep their own colours on the site's white `--logo-chip` so they stay readable on dark cards.
- Jokes and voice: no em dashes (a test enforces this), one wink per bubble, an emoji removed from a reply.

## Factually unverified

- **Repo visibility.** I couldn't tell whether the repo is public, so "never in the public code" is gone.
- **Who reviews ordinary code PRs.** `checks.yml` runs on every PR, but I can't read GitHub branch-protection or required-reviewer
  settings from here, so I can't say that code changes need a second pair of eyes beyond Maya.
- **"About a minute" end to end** includes GitHub's queue time, which the run durations don't show.
- **"Six plays, about six minutes"** is a reading-time guess.
- **Coach "loops back".** Not found in any skill; reworded rather than claimed.
- **The Vercel branch-preview URL** exists only after the PR is pushed; see the PR.
