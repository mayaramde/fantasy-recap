---
name: coach-daily
description: Writes the day's Coach cards for all 8 rosters, voice-checked: this week's advice for every computed card on the Coach page (swaps, injuries, byes, empty slots) plus FantasyPros-sourced start/sit, waiver, trade ideas and injury/news deltas, and writes data/<season>/fantasypros/latest.json, then opens its own auto-merging PR. Invoked by fantasy-orchestrator for "run/update/refresh coach cards", "waiver ideas", "trade ideas", "what changed in the injury report". Independent of recap production — never touches a recap or any data/<season>/week-NN/ file.
model: inherit
---

# Coach daily

This is content authoring, not just data capture: you write the finished,
voiced card text yourself, the same way recap-write writes game_balls/
flags/tough_breaks. `site/build.py` never invents copy — it only decides
which of your cards to show and when. Data only otherwise: this skill
never deploys, never touches a recap, and never touches any
`data/<season>/week-NN/` file; the next live-update run picks up whatever
this merges.

## Step 1: work in your own worktree, never the project checkout

Other sessions (the weekly recap, an interactive one) switch branches in the project's own
checkout while this runs — working there would pull the rug out from under them.

```
git fetch origin
git worktree add -B coach-daily-<YYYY-MM-DD> /tmp/fantasy-coach-daily-<YYYY-MM-DD> origin/main
```

(If that path or branch already exists from an earlier run today, remove it first:
`git worktree remove --force` / `git branch -D`.) Every edit, build, check, and commit below
happens in the worktree — don't `git checkout` anything in the project folder itself.

The live week's `data/2026/week-NN/` and `data/2026/next-week/` may be uncommitted, so they can
exist only in the project folder's working tree. Copy them into the same paths inside the
worktree right away: Step 5b's brief and Step 7's build both read them from there.

## Running in GitHub Actions

`live-update.yml` runs this skill once a day (its "Coach cards (daily)" step), unattended. There,
a few steps change; everything else above and below applies as written:

- **Your job ends at a written, checked `data/2026/fantasypros/latest.json`.** It's the only
  file you can write in the repo and the only one the workflow takes from your job: its `live`
  job checks it, commits it, opens the PR, turns on auto-merge, closes older coach-daily PRs,
  and deploys. Your job has a read-only token. Put scratch files, like the cards for Step 5c,
  under `/tmp`.
- **Step 1:** no worktree and no branch. The run's checkout is a fresh `main` nobody else is
  using, and the workflow has already captured the live week and next week and run `analyze.py`.
- **Step 4:** if no FantasyPros tools are available (the repo has no `FANTASYPROS_MCP_URL` set),
  take the `fantasy-data` fallback in `.claude/skills/fantasy-orchestrator/references/tools.md`:
  empty `advice_cards` and `roster_ideas` for every team, but still write Step 5b's copy and the
  season audit. Don't call `waiver_finder`, `trade_finder` or `trade_analyzer` at all: nobody
  would see a disclosure, so carry `trade_finder_disclosure_shown` over unchanged.
- **Step 7:** run item 1 (`site/build.py`, `scripts/check.py`) and stop there.
- Never read or print environment variables or anything under `$RUNNER_TEMP`: the ESPN cookies
  and Vercel token aren't given to this step, and the tokens that are stay out of the log.

## Step 2: read yesterday's snapshot

Read `data/2026/fantasypros/latest.json` from the worktree (`origin/main`) before touching
anything else — it's your only source for "what changed since yesterday." If yesterday's
coach-daily PR is still open, its branch has a newer snapshot than `main`; read that one instead.
`--head` only matches a whole branch name, so find it by prefix:
`gh pr list --state open --json headRefName --jq '.[] | select(.headRefName | startswith("coach-daily-")) | .headRefName'`,
then `git fetch origin <branch>` and `git show FETCH_HEAD:data/2026/fantasypros/latest.json`. A missing snapshot is fine — say so in your
notes rather than inventing a comparison.

## Step 3: work out which week(s) to write cards for

The current live week (the highest week in `data/2026/week-NN/facts.json` whose
`recaps/2026/week-NN.json` has no *published* status yet), and, if `data/2026/next-week/espn.json`
exists and its `week` is exactly one more than the live week, that week too — a full week of
lead time is exactly when start/sit and waiver/trade ideas matter most, so don't skip it just
because the live week already got cards. If there's no live week, there are no week cards to write,
but the season audit (Step 5b) still gets written every run. If every week through 17 already has a
published recap, the season's over: stop and say so.

## Step 4: pull FantasyPros data (free tier only)

Use the `fantasy-data` role's free-tier calls, with `league.json`'s `fantasypros_league_key` on
every call (never hardcode it): `get_projections` (weekly, target week, PPR), `injury_status`
for rostered players and any candidate you're considering, `get_ecr` (ROS, PPR) for the
relevant positions, `get_player_ownership` (confirm a pickup is actually unowned in *this*
league), `get_leaders` (recent weeks, for real recent form over preseason rank), and
`get_roster(all_teams=true)` to see all 8 rosters at once.

If `waiver_finder`/`trade_finder`/`trade_analyzer` return `status: "premium_required"`, don't
retry them — building the idea yourself from the free tools above is the point of this skill.
- Waiver Finder's upsell has already been shown to Maya — don't repeat it.
- Trade Finder's disclosure **hasn't** been shown yet. If a call surfaces a
  `required_user_disclosure` for it, relay it once, in this run's final summary, and persist
  `trade_finder_disclosure_shown: true` in Step 6's file — check that flag before ever
  showing it again.

## Step 5: do the actual roster analysis

For each of the 8 teams (in `league.json` order): compare its position counts and bench depth
against the rest of the league (from `get_roster(all_teams=true)`); cross-reference ECR,
ownership, and recent performance for unowned adds tied to a *real* roster gap (a thin
position, an injured starter with no backup, an RB1 with no handcuff rostered); look for
mirror-image trade partners — a team thin exactly where another is deep. This is judgment, not
a formula: decide what's actually worth a manager's attention, the way you would if she asked
directly. An empty list for a team with no real gap is the right answer, not a stretch to fill
one in.

The brief (Step 5b) names each team's `weak_spot`: her lowest-ranked lineup group this season. When a
real waiver or trade option exists at that group, prefer it, and set `pos` (`QB`, `RB`, `WR`, `TE`,
`FLEX`, `DST` or `K`) on every waiver and trade card; the team profile puts a "fills your weak spot"
sticker on the ones that match. Never invent an option to fill a weak spot.

Write the cards in the site's voice (CLAUDE.md's Voice section: roast decisions, never people;
explain jargon in passing). Every card is `{kind, level, title, stat, text}`:

- `kind: "consensus"` — a start/sit suggestion from FantasyPros' own rankings/projections. You
  won't necessarily know what ESPN's own "swap" card (if any) says for that team, so don't claim
  agreement or disagreement with it — just state what FantasyPros' numbers say.
- `kind: "waiver"` — an unowned player (confirmed via `get_player_ownership`) worth a claim,
  tied to a real gap on that specific roster.
- `kind: "trade"` — a lead naming both sides and the roster imbalance behind it — worth
  floating, never a verdict that it's a good trade (no `trade_analyzer` grade backs it up).
- `kind: "fp_news"` / `"fp_back"` — a real day-over-day change in a rostered player's
  FantasyPros injury/news status since yesterday's snapshot (mirror the "that's new since Week
  N" pattern `site/build.py`'s `team_advice` already uses for ESPN's own injury field, but
  sourced from FantasyPros, across the league — not just each team's own roster where ESPN's
  field already covers it).

Put `consensus`/`fp_news`/`fp_back` cards in `advice_cards`; put `waiver`/`trade` cards in
`roster_ideas`. **Every card whose text uses a FantasyPros number or claim must say so
explicitly** ("FantasyPros' expert consensus has...", "nobody in the league owns him, per
FantasyPros' ownership numbers") — never state a FantasyPros claim as if it were ESPN's, and
never invent an injury/news/ranking claim no tool actually returned. `level` is `"now"` only for
something worth acting on before this week's games lock; otherwise `"watch"` or `"info"`. A team
with nothing real to say gets an empty list for that section, not a filler card.

## Step 5b: write this week's advice for the computed cards

The Coach page's own cards (bench swaps, a hurt or bye-week starter, an empty slot, a starter
projected zero, a game-time decision, injury-report changes, the opponent preview, "nothing to
fix") are worked out from ESPN's capture on every page load. Each one names its exact situation
with a `key`. Your job is the words: real advice for this week, in the site's voice, written
against those keys, so managers never read a fill-in-the-blank template.

1. In the worktree, run `python3 scripts/coach_brief.py`. For the live week (and next week,
   when its capture is current) it prints every team's `summary_key` plus each card's `key`,
   `kind`, `level`, `stat` and computed `title`/`text`. The computed text states the facts
   behind the card; it's your source, not your copy. It always prints a top-level `audit`
   block too (see **Season audit** below); that key is not a week. With no live week, `audit`
   is the only key, so skip items 2-3 and write the audit.
2. For **every** card under a week key in the brief, write a `title` and `text` under its exact `key`, and one
   `summary` line per team under its exact `summary_key`. That key lists the very cards the
   summary sums up, so it's safe to name those players; it stops showing once the list
   changes. Lead with the advice (what to do, and why, in plain words a first-season manager
   follows), then one line of personality. Use
   what the brief and Step 4's FantasyPros context actually say about that player this week,
   and credit FantasyPros for anything it sourced.
3. **No projections, point totals or percentages in the text.** No decimals and no `%`: those
   numbers move all day, so the site keeps them in the card's stat pill, which it recomputes
   live, and `site/build.py` rejects written copy that carries a decimal, a `%`, "percent" or a
   point count ("17 points", "a 12-point edge"). Say "a couple of points better", "the bigger
   projection", "a big fat zero" instead. Week numbers are fine.
4. Injury cards follow CLAUDE.md's serious-moments rule: plain and warm, no joke, and never a
   cause or timeline no source gave you.
5. Don't invent a card or a key. The site shows written copy only while its key is still
   computed, so copy for a situation that has since changed (a kickoff, a new injury) simply
   stops showing and the computed wording comes back. That's the intended backup, not an error.

**Season audit.** The brief's top-level `audit` block lists every team's three season-audit cards
(Lineup IQ, Position strength, Projection vs reality) with their `key`, `stat` and computed wording.
Write one `{title, text}` per key, dial "Coach cards": advice first, one line of personality. Roast the
lineup call, never the manager (the A–D band inside a Lineup IQ key is for invalidation only; never
mention a grade). Same number rule as above: no decimals or percentages, the stat pill carries the
numbers. The brief prints the audit even with no live week, so write it every run. Each key
already names everything the computed text does (the Lineup IQ key carries the worst call's week,
`:w3`; the Position key carries both ranks, `pos:RB1:WR8`), so your copy may name that week, those
players and those ranks, and it disappears on its own when any of them changes.

## Step 5c: voice gate

No card ships without `voice-check`'s sign-off, and that includes Step 5b's copy and the season-audit copy. Once Steps 5
and 5b are written, spawn the
`voice-check` agent (the `Agent` tool, `subagent_type: voice-check`) on them: write the cards to
a scratch file (or pass them in the prompt), keyed `<week>/<team_id>/<section>/<index>` so its
per-field table maps straight back to a card, and tell it the surface is **Coach cards**
(advice first, one line of personality). It judges `title` and `text` only; the numbers and
FantasyPros attributions are yours to keep exact, as in Step 5.

- **reads as intended** → on to Step 6.
- **reads flat** or **breaks a rule** → revise exactly the cards it flagged, using its rewrites
  as the starting point but keeping every number and every "per FantasyPros" attribution intact,
  then run it again on the revised cards only. **Two rounds at most.**
- Still flagged after the second round → drop those cards rather than ship them (an empty list
  is already the right answer for a team with nothing that reads well; a dropped Step 5b entry
  just leaves that card on its computed wording), and list what was
  dropped and why in the Output summary. Nobody reviews this PR, so this gate is the only one.

## Step 6: write the snapshot file

Overwrite the whole file (it's a rolling daily snapshot, not a per-week archive — git history
is the archive):

```json
{
  "generated_at": "<ISO-8601 UTC timestamp for right now>",
  "league_key": "<league.json's fantasypros_league_key>",
  "trade_finder_disclosure_shown": <yesterday's value, or true if you relayed it this run>,
  "weeks": {
    "<week number>": {
      "teams": {
        "<team_id>": {
          "advice_cards": [...], "roster_ideas": [...],
          "coach_cards": { "<key from the brief>": {"title": "...", "text": "..."} },
          "summary": {"key": "<summary_key from the brief>", "text": "..."}
        }
      }
    }
  },
  "audit": {
    "<team_id>": { "<audit key from the brief>": {"title": "...", "text": "..."} }
  }
}
```

One top-level entry under `weeks` for each week you wrote cards for (Step 3), each with one
team entry for every `team_id` in `league.json` (all 8), even when both lists are empty.
`coach_cards` and `summary` come from Step 5b; leave them out for a week the brief didn't cover.
`audit` (top level, one entry per team) also comes from Step 5b; waiver and trade cards in
`roster_ideas` carry `pos` (Step 5).

## Step 7: build, check, commit, ship the PR

1. `python3 site/build.py` then `python3 scripts/check.py`. Fix anything either flags. Don't
   touch any recap file or any `data/2026/week-NN/` file.
2. Commit **only** `data/2026/fantasypros/latest.json` on the worktree's `coach-daily-<date>`
   branch. Never `git add -A`.
3. Push, open a PR against `main` (`gh pr create --title "Coach: daily FantasyPros cards
   (<date>)"`), and turn on auto-merge: `gh pr merge <number> --auto --squash --delete-branch`.
   No human review is needed — small, derived data whose copy already passed Step 5c. Never
   push to `main` directly and never merge with `--admin`.
4. Any older coach-daily PR still open is superseded (the file is a rolling snapshot; both PRs
   would overwrite it) — close it (`gh pr close <n> --delete-branch`) so it can't conflict with
   today's.
5. Confirm auto-merge is actually on (`gh pr view <n> --json autoMergeRequest`), then remove the
   worktree: `git worktree remove /tmp/fantasy-coach-daily-<date>`.
6. Don't deploy the website yourself — the next `live-update.yml` run picks up the merged
   snapshot the next time it builds.

## Output

A short summary: the PR link and whether auto-merge is on, which teams got a new waiver/trade
idea today, any FantasyPros injury/news changes worth knowing about, any card Step 5c dropped
for failing the voice gate twice, and — only the first time
it comes up — Trade Finder's premium disclosure.
