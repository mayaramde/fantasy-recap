---
name: recap-write
description: Writes or revises recaps/<season>/week-NN.json joke-first from that week's captured data and FantasyPros context, runs check.py, hands the draft to fantasy-orchestrator's voice-check gate, then to recap-fact-checker as the final truth gate, then opens the draft PR and a review preview. Invoked by fantasy-orchestrator for drafting, redoing, or tweaking a recap (a matchup blurb, a game ball, a flag, the glossary) — don't invoke this directly for a user-facing request; route through fantasy-orchestrator first, which also decides whether recap-capture needs to run first.
model: inherit
---

# Recap write

Turns a week's `facts.json`/`espn.json` plus FantasyPros context into the
written recap, joke first. Order: write → `check.py` → voice gate (run by
`fantasy-orchestrator`) → one final fact-check → draft PR and review preview.
Voice comes before the fact-check on purpose: when every joke went back through a
literal fact-check after each voice rewrite, the recaps came out as box scores.

## Step 1: gather context

Use the `fantasy-data` role (see `fantasy-orchestrator/references/tools.md`) for injury/news on
notable players. **Only claim an injury or a specific cause if a source actually says so.**
Before writing a bust, bad-luck-loss, or bench-blunder callout, check whether the injury/news
desk gives a real cause — if it does, cite it; if it doesn't, don't invent one. This is a hard
CLAUDE.md rule, not a style preference: an invented cause is exactly what `recap-fact-checker`
will fail the draft on.

### Reuse the coach's snapshots as leads, never as sources

`coach-daily` has already looked at these rosters every day, so don't rescan from scratch. After
`git fetch origin`, read `data/<season>/fantasypros/history/index.json` on `origin/main` and open the
dated files for the days whose `weeks` include this recap's week number (skip this quietly if the
folder or the week isn't there yet). Use them to build a shortlist of where to look: which players it
flagged as injured, on a bye, or worth adding, which team it saw with an empty or weak slot, and what
changed day to day. Then spend the injury/news lookups above on that shortlist, plus anything in
`facts.json` the snapshots missed.

The snapshots are Claude-written recommendations, not facts, so:
- **Never cite one.** An injury cause, a lineup decision, or a number comes from `facts.json`/`espn.json`
  (including `injury_status`) or from the FantasyPros injury/news desk, looked up or confirmed now. If a
  snapshot lead doesn't check out against those, drop it.
- **Never quote or credit a card in the recap.** No "the coach said" and no card text reused. The page's
  Coach cards are a separate surface, and Maya's league may never have opened them.
- Tell the fact-checker (Step 3) which context came from a verified source, not which came from a lead.

## Step 1b: joke pass (before any JSON)

Voice is written at write time, not judged after. A fact-first draft with jokes added later is
the failure this step prevents.

1. Read CLAUDE.md's **Voice** section, the calibration recap it names (Week 11), and the last
   three *published* recaps (only so you know which punchlines are already spent; Weeks 1-10
   are not the voice to copy).
2. Build a throwaway **material sheet** per matchup (scratch notes, never committed): the absurd
   stat, callbacks to prior weeks (check the Running threads and every player the last two
   recaps named), ironies (best score lost, bench outscored starter), and team-name or
   player-name hooks.
3. For the headline, the dek, every matchup blurb and every award, draft **three candidate
   lines**, compare them in pairs, and keep the funniest that passes the screenshot, deletion
   and scoreboard tests. Only the winner goes in the JSON.
4. **Scoreboard test:** the page already shows every final score, winner and margin. A section
   that opens with them, or has no joke left once you delete them, is a scorecard, not a blurb
   (a margin can still be a beat inside a joke, like Week 11's "spare 6.30 and a penny"). Start
   each section from the funny premise ("Maddie couldn't pick a side in Ravens vs. Panthers, so
   she started both") and bring in only the facts the joke needs.
5. **Numbers budget:** a number goes in the copy only when it is, or sets up, the joke. Aim for
   two or fewer per matchup blurb; the rest belongs in the award `stat` chips.
6. **Headline and dek:** one premise and a turn that points at something named in it. No
   generic closers ("the fantasy gods").
7. **No reuse:** never reuse a punchline shape or stock phrase from the last three published
   recaps. Callbacks are welcome; recycled jokes are not.
8. Real-injury tough breaks skip the joke pass: one warm, plain sentence, sourced (Step 1).

## Step 2: write the recap

Write to CLAUDE.md's **Voice** section, using the Step 1b material. `voice-check` (run by
`fantasy-orchestrator`) scores the draft right after you run `check.py`, but the funny is built here, not patched
in afterward. Any rewrites it asks for come back to this skill as a revision; apply them in its
joke-first shape, and don't trim a joke back to a stat line to feel safe. The fact-check comes
later and only blocks claims that are false.

Write (or edit, for a revision) `recaps/2026/week-NN.json` with `"status": "draft"`. Schema:

```json
{
  "season": 2026, "week": N, "status": "draft",
  "headline": "...", "dek": "...",
  "matchups": { "<lowTeamId>-<highTeamId>": "blurb", "...": "..." },
  "game_balls": [{ "manager": "...", "title": "...", "text": "...", "stat": "...", "emoji": "🥈", "player": "Full Name" }],
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

- **Awards carry an optional `emoji` and `player`.** Pick an emoji that jokes about the award (1 or 2
  visible characters), and a `player` (full name exactly as that week's roster spells it) only when one
  player is the story; `site/build.py` bakes the photo from it, never type an id. Keep `title` to 48
  characters or fewer, `stat` to 22 or fewer and not an echo of the title, and no em dashes in `title`,
  `stat` or `text` (`check_recaps.py` enforces all of it).

Run `python3 scripts/check.py` and fix anything it flags before handing the draft to the voice
gate. If it rejects a number inside a joke, keep the joke and change only the number (Week 11:
"spare 6.31" became "spare 6.30 and a penny"), or drop the number.

## Step 3: final fact-check (after the voice gate), and revise if needed

This runs once `fantasy-orchestrator`'s voice gate has passed the draft or spent its two
`voice-check` runs.
Hand the draft to the `recap-fact-checker` agent, along with that week's `facts.json`/
`espn.json` paths and whatever FantasyPros context you used in Step 1 (so it can verify
citations, not just numbers — `check.py` already covers the numbers). Don't hand it the coach
snapshots as support: they were only leads.

- **PASS** → Step 4.
- **FAIL** → apply its smallest-true-fix for each flagged claim, changing only the wrong word
  or number and keeping the joke's shape, re-run `python3 scripts/check.py` (a fixed number
  must still trace to the data), then re-check. Don't send these fixes back through
  the voice gate; they're too small to change the voice. **Cap this at two
  revise-and-recheck rounds.** If it's still failing after two rounds, stop — hand the
  fact-checker's last report back to whoever invoked this skill (`fantasy-orchestrator`) rather
  than looping indefinitely or shipping something unverified.

## Step 4: draft PR and review preview (after the voice gate and the final fact-check)

For a new draft, on the `recap-week-NN` branch (a revision stays on whichever branch holds the
draft; if the draft PR already merged, branch `recap-week-NN-rev` from `main`):

1. Commit **only** `recaps/2026/week-NN.json`, `data/2026/week-NN/`, and
   `data/player_names.json` if it changed. Never `git add -A`: a concurrent live-update run can
   leave the next week's files uncommitted in the same tree.
2. Push, open a PR titled `Week NN recap draft` (put `voice-check`'s last scores in the PR body,
   and its full report if the voice cap was spent), and enable auto-merge (squash). A draft recap
   is safe on `main`, since the league site only shows published weeks.
3. Run `scripts/deploy.sh --preview` from the tree that holds the draft (see `recap-ship` Step 1
   for the on-disk check) and share the preview URL with Maya.

## Output

`recaps/2026/week-NN.json` with `status: "draft"`, `check.py`-clean, voice-checked (or, if the
voice cap was spent, carrying the voice report in the PR body) and fact-checker-PASSed, a draft PR, and a preview URL. Or a stop with the judges' specific reports.
