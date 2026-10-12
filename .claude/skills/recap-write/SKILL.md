---
name: recap-write
description: Writes or revises recaps/<season>/week-NN.json from that week's captured data and FantasyPros context, hands the draft to recap-fact-checker, then (after fantasy-orchestrator's voice-check gate) opens the draft PR and a review preview. Invoked by fantasy-orchestrator for drafting, redoing, or tweaking a recap (a matchup blurb, a game ball, a flag, the glossary) — don't invoke this directly for a user-facing request; route through fantasy-orchestrator first, which also decides whether recap-capture needs to run first.
model: inherit
---

# Recap write

Turns a week's `facts.json`/`espn.json` plus FantasyPros context into the
written recap, gets it fact-checked, then opens the draft PR and a review preview.

## Step 1: gather context

Use the `fantasy-data` role (see `fantasy-orchestrator/references/tools.md`) for injury/news on
notable players. **Only claim an injury or a specific cause if a source actually says so.**
Before writing a bust, bad-luck-loss, or bench-blunder callout, check whether the injury/news
desk gives a real cause — if it does, cite it; if it doesn't, don't invent one. This is a hard
CLAUDE.md rule, not a style preference: an invented cause is exactly what `recap-fact-checker`
will fail the draft on.

## Step 2: write the recap

Voice isn't restated or self-checked here. Write to CLAUDE.md's **Voice** section as usual;
`voice-check` judges the draft after the fact-check, run by `fantasy-orchestrator`, and any
rewrites it asks for come back to this skill as a revision.

Write (or edit, for a revision) `recaps/2026/week-NN.json` with `"status": "draft"`. Schema:

```json
{
  "season": 2026, "week": N, "status": "draft",
  "headline": "...", "dek": "...",
  "matchups": { "<lowTeamId>-<highTeamId>": "blurb", "...": "..." },
  "game_balls": [{ "manager": "...", "title": "...", "text": "...", "stat": "..." }],
  "flags": [ /* same shape as game_balls */ ],
  "tough_breaks": [ /* same shape as game_balls */ ],
  "glossary": [{ "term": "...", "definition": "one friendly sentence" }]
}
```

Follow CLAUDE.md's **Recap content** and **Voice** sections for what goes in each field and how
it should read. `scripts/check_recaps.py` enforces the first three of these in CI:
- **Every number** in `headline`, `dek`, a matchup blurb, or a `stat` field must trace back to
  that week's `facts.json`/`espn.json` — not approximated, not rounded past what the source
  actually supports.
- **First names only, everywhere** — no manager's last name, in any field, ever (CLAUDE.md
  Privacy).
- Matchup keys must be real pairings for that week, written low-team-id first.
- `glossary` needs 3 to 5 entries, and terms shouldn't repeat ones already defined in an earlier
  week's recap (check `recaps/2026/week-*.json`). CI doesn't check this; the fact-checker does.

Run `python3 scripts/check.py` before Step 3 and fix anything it flags. It's cheaper than
waiting for the fact-checker to find the same thing.

## Step 3: fact-check, and revise if needed

Hand the draft to the `recap-fact-checker` agent, along with that week's `facts.json`/
`espn.json` paths and whatever FantasyPros context you used in Step 1 (so it can verify
citations, not just numbers — `check.py` already covers the numbers).

- **PASS** → return to `fantasy-orchestrator` for its voice gate. Step 4 runs only once
  `voice-check` says the draft reads as intended.
- **FAIL** → revise the specific claims it flagged and re-check. **Cap this at two
  revise-and-recheck rounds.** If it's still failing after two rounds, stop — hand the
  fact-checker's last report back to whoever invoked this skill (`fantasy-orchestrator`) rather
  than looping indefinitely or shipping something unverified.

## Step 4: draft PR and review preview (after the voice gate passes)

For a new draft, on the `recap-week-NN` branch (a revision stays on whichever branch holds the
draft; if the draft PR already merged, branch `recap-week-NN-rev` from `main`):

1. Commit **only** `recaps/2026/week-NN.json`, `data/2026/week-NN/`, and
   `data/player_names.json` if it changed. Never `git add -A`: a concurrent live-update run can
   leave the next week's files uncommitted in the same tree.
2. Push, open a PR titled `Week NN recap draft`, and enable auto-merge (squash). A draft recap
   is safe on `main`, since the league site only shows published weeks.
3. Run `scripts/deploy.sh --preview` from the tree that holds the draft (see `recap-ship` Step 1
   for the on-disk check) and share the preview URL with Maya.

## Output

`recaps/2026/week-NN.json` with `status: "draft"`, `check.py`-clean, fact-checker-PASSed and
voice-checked, a draft PR, and a preview URL. Or a stop with the judges' specific reports.
