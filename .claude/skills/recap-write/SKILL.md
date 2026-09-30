---
name: recap-write
description: Writes or revises recaps/<season>/week-NN.json from that week's captured data and FantasyPros context, then hands the draft to recap-fact-checker before calling it done. Invoked by fantasy-orchestrator for drafting, redoing, or tweaking a recap (a matchup blurb, a game ball, a flag, the glossary) — don't invoke this directly for a user-facing request; route through fantasy-orchestrator first, which also decides whether recap-capture needs to run first.
tools: Read, Write, Edit, Grep, Glob
model: inherit
---

# Recap write

Turns a week's `facts.json`/`espn.json` plus FantasyPros context into the
written recap, then gets it checked before calling itself done. This is
weekly routine steps 3-4 (CLAUDE.md), plus the fact-check hand-off.

## Step 1: gather context

Use the `fantasy-data` role (see `fantasy-orchestrator/references/tools.md`) for injury/news on
notable players. **Only claim an injury or a specific cause if a source actually says so.**
Before writing a bust, bad-luck-loss, or bench-blunder callout, check whether the injury/news
desk gives a real cause — if it does, cite it; if it doesn't, don't invent one. This is a hard
CLAUDE.md rule, not a style preference: an invented cause is exactly what `recap-fact-checker`
will fail the draft on.

## Step 2: write the recap

Before writing, read CLAUDE.md's `## Voice` section in full, plus the calibration recaps it
names (`recaps/2026/week-01.json` and `week-02.json`, or the two most recently *published*
recaps once CLAUDE.md swaps them in). The section describes the style, the recaps are what it
sounds like applied. Match that level of personality, not just the mechanical shape. A recap
that's numerically flawless but reads like a stats recap has failed the same as one with a
wrong number, and `recap-fact-checker` in Step 3 judges the draft against these same rules,
so aim for genuinely cheeky and funny the first time. While drafting, hold each field to:
- **The formula:** a real fact, then a short turn. Run the deletion test on every blurb: if
  removing the joke leaves the sentence reading the same, it was a qualifier, not a joke.
- **One joke per section** (headline, dek, each matchup blurb, each game ball/flag/tough
  break). Pick the best one and cut the rest.
- **Jokes from true, checkable things:** a team name, a real callback, an absurd stat. Never
  an invented feeling, effort, or motive. Exaggerate the joke, never the number.
- **Mechanics:** no em dashes (period or comma), short sentences, one stat line per player,
  one comparison per blurb, no explaining after the joke lands. Explain jargon in passing.
- **Punch at decisions, hug the person.** Never a manager's character or competence, and no
  second joke on whoever already took one this issue. Maya's team gets roasted too, by name.
- **Serious moments play it straight:** a season-ending injury or real bad news gets one
  warm, plain sentence, no joke there or about the other side of the matchup. Never guess at
  an injury or its cause (Step 1).
- **Running threads:** pull on one, maybe two of CLAUDE.md's list, not every live one.
- **Dial by surface:** full personality in headline/dek (dek short), one joke in blurbs, game
  balls and flags, warm tough breaks, glossary teaches first with this week's example as the
  wink.
- **Screenshot test:** would a friend screenshot this line for the group chat? If not,
  rewrite it.

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

Follow CLAUDE.md's **Recap content**, **Voice**, and **Design** sections for what goes in each
field and how it should read — this skill doesn't restate those rules, since they apply to the
whole site, not just this step. Two mechanical constraints worth calling out because
`scripts/check_recaps.py` enforces them in CI:
- **Every number** in `headline`, `dek`, a matchup blurb, or a `stat` field must trace back to
  that week's `facts.json`/`espn.json` — not approximated, not rounded past what the source
  actually supports.
- **First names only, everywhere** — no manager's last name, in any field, ever (CLAUDE.md
  Privacy).
- Matchup keys must be real pairings for that week, written low-team-id first.
- `glossary` needs 3 to 5 entries, and terms shouldn't repeat ones already defined in an earlier
  week's recap — check `recaps/2026/week-*.json` for terms already used before picking this
  week's.

Run `python3 scripts/check.py` yourself before moving to Step 3 — it catches all four of the
above mechanically, cheaper than waiting for the fact-checker to find the same thing. Fix
anything it flags first.

## Step 3: fact-check, and revise if needed

Hand the draft to the `recap-fact-checker` agent, along with that week's `facts.json`/
`espn.json` paths and whatever FantasyPros context you used in Step 1 (so it can verify
citations, not just numbers — `check.py` already covers the numbers).

- **PASS** → done. The draft is ready for `recap-ship`.
- **FAIL** → revise the specific claims it flagged and re-check. **Cap this at two
  revise-and-recheck rounds.** If it's still failing after two rounds, stop — hand the
  fact-checker's last report back to whoever invoked this skill (`fantasy-orchestrator`) rather
  than looping indefinitely or shipping something unverified.

## Output

`recaps/2026/week-NN.json`, `status: "draft"`, `check.py`-clean, and either fact-checker-PASSed
or stopped with a specific, actionable FAIL report.
