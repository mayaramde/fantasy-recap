---
name: coach-daily
description: Builds the day's FantasyPros-sourced Coach cards (start/sit, waiver, trade ideas, injury/news deltas) for all 8 rosters and writes data/<season>/fantasypros/latest.json, then opens its own auto-merging PR. Invoked by fantasy-orchestrator for "run/update/refresh coach cards", "waiver ideas", "trade ideas", "what changed in the injury report". Independent of recap production — never touches a recap or any data/<season>/week-NN/ file.
tools: Read, Write, Bash, Grep, Glob
model: inherit
---

# Coach daily

Writes the finished, voiced Coach cards that `site/build.py` merges into the
Coach page's `consensus`/`waiver`/`trade`/`fp_news`/`fp_back` sections and
the "Worth a look" section. Data only — this skill never deploys, never
touches a recap, and never touches any `data/<season>/week-NN/` file; the
next live-update run picks up whatever this merges.

## Tools: free tier only

Use the `fantasy-data` role's free-tier calls only: `get_projections`, `injury_status`,
`get_ecr`, `get_player_ownership`, `get_leaders`, and `get_roster(all_teams=true)`. Build
start/sit, waiver, and trade ideas from these yourself — don't reach for Waiver Finder, Trade
Finder, or Trade Analyzer; those are premium and Maya is on the free tier.

- Waiver Finder's upsell has already been shown once — don't repeat it.
- Trade Finder's and Trade Analyzer's disclosures **haven't** been shown yet — if either would
  otherwise gate a call, relay the disclosure once, the first time it happens, then don't repeat
  it either.

## Steps

1. Work in this task's own git worktree (it's set up to never switch branches under another
   session — don't `git checkout` anything here).
2. For each of the 8 rosters: pull projections, ECR, ownership, and injury/news via the
   free-tier calls above.
3. Write the voiced cards:
   - `consensus` — start/sit suggestions.
   - `roster_ideas` — waiver and trade leads, built from your own read of the free-tier data,
     not a finder tool's output.
   - `fp_news`/`fp_back` — what's changed in FantasyPros' injury/news report since yesterday's
     snapshot (diff against the previous `latest.json`, not just today's raw state).
4. Write all of it to `data/2026/fantasypros/latest.json`, keyed by week under `weeks`. This
   file is small, factual, derived data — the same category as `data/player_names.json`, not
   human-reviewed recap content.
5. Commit, push, open a PR, and enable auto-merge (squash) — it merges once `checks` passes, with
   **no review needed**, unlike a recap PR.

## Output

`data/2026/fantasypros/latest.json` updated, PR open with auto-merge on. `site/build.py`
decides on its own whether that day's snapshot is fresh enough to merge into the live Coach
page (a missing, malformed, or >36h-old file just means ESPN-only Coach cards) — this skill's
job ends at a clean, committed snapshot.
