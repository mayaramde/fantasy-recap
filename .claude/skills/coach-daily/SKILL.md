---
name: coach-daily
description: Builds the day's FantasyPros-sourced Coach cards (start/sit, waiver, trade ideas, injury/news deltas) for all 8 rosters and writes data/<season>/fantasypros/latest.json, then opens its own auto-merging PR. Invoked by fantasy-orchestrator for "run/update/refresh coach cards", "waiver ideas", "trade ideas", "what changed in the injury report". Independent of recap production — never touches a recap or any data/<season>/week-NN/ file.
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

The live week's `data/2026/week-NN/` and `data/2026/next-week/` are deliberately uncommitted, so
they only exist in the project folder's working tree. Read them from there, and copy them into
the same paths inside the worktree before Step 6's build.

## Step 2: read yesterday's snapshot

Read `data/2026/fantasypros/latest.json` from the worktree (`origin/main`) before touching
anything else — it's your only source for "what changed since yesterday." If yesterday's
coach-daily PR is still open (`gh pr list --state open --head coach-daily-`), its branch has a
newer snapshot than `main`; read that one instead. A missing snapshot is fine — say so in your
notes rather than inventing a comparison.

## Step 3: work out which week(s) to write cards for

The current live week (the highest week in `data/2026/week-NN/facts.json` whose
`recaps/2026/week-NN.json` has no *published* status yet), and, if `data/2026/next-week/espn.json`
exists and its `week` is exactly one more than the live week, that week too — a full week of
lead time is exactly when start/sit and waiver/trade ideas matter most, so don't skip it just
because the live week already got cards. If every week through 17 already has a published
recap, the season's over: stop and say so.

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

## Step 6: write the snapshot file

Overwrite the whole file (it's a rolling daily snapshot, not a per-week archive — git history
is the archive):

```json
{
  "generated_at": "<ISO-8601 UTC timestamp for right now>",
  "league_key": "<league.json's fantasypros_league_key>",
  "trade_finder_disclosure_shown": true,
  "weeks": {
    "<week number>": {
      "teams": {
        "<team_id>": { "advice_cards": [...], "roster_ideas": [...] }
      }
    }
  }
}
```

One top-level entry under `weeks` for each week you wrote cards for (Step 3), each with one
team entry for every `team_id` in `league.json` (all 8), even when both lists are empty.

## Step 7: build, check, commit, ship the PR

1. `python3 site/build.py` then `python3 scripts/check.py`. Fix anything either flags. Don't
   touch any recap file or any `data/2026/week-NN/` file.
2. Commit **only** `data/2026/fantasypros/latest.json` on the worktree's `coach-daily-<date>`
   branch. Never `git add -A`.
3. Push, open a PR against `main` (`gh pr create --title "Coach: daily FantasyPros cards
   (<date>)"`), and turn on auto-merge: `gh pr merge <number> --auto --squash --delete-branch`.
   No review is needed — small, factual, derived data, not the creative recap content. Never
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
idea today, any FantasyPros injury/news changes worth knowing about, and — only the first time
it comes up — Trade Finder's premium disclosure.
