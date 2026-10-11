---
name: recap-capture
description: Captures a week's ESPN fantasy data (rosters, scores, projections) and runs analyze.py to produce facts.json. Invoked by fantasy-orchestrator as the first step of drafting or redoing a recap — don't invoke this directly for a user-facing request; route through fantasy-orchestrator first. Also fires on an explicit standalone request like "capture week N" or "re-run the ESPN capture for this week".
model: inherit
---

# Recap capture

Gets one week's ESPN data onto disk and turns it into `facts.json`, whether as the first
step of a recap or on its own.

**Claude in Chrome** is always the first attempt. The league is public on ESPN, so neither it
nor the fallback in Step 5 needs a login. Still never ask for, copy, print, or store
`espn_s2`/`SWID` (CLAUDE.md, Data sources).

## Step 0: get on the right branch

In GitHub Actions (fantasy-orchestrator's "GitHub Actions mode"), the checkout is already a
fresh `main`: skip item 1's `git pull`, and skip Steps 1-4 (there's no Chrome) for Step 5's
`node scripts/capture_node.mjs N`.

Only do this for a *new* recap (fantasy-orchestrator's context check found no
`recaps/2026/week-NN.json` yet). A re-capture for an existing draft happens wherever
`recap-write` will revise it: the open draft PR's branch, or `recap-week-NN-rev` from `main`
if that PR already merged.

1. `git checkout main && git pull`. If checkout fails because of uncommitted changes, **stop
   and tell the user** — don't stash, reset, or discard anything that might be someone else's
   in-progress work.
2. Use the week `fantasy-orchestrator` picked (the user's explicit week, else the most recent
   final week with no recap). If that week is past 17, the regular season is over: stop and
   tell the user rather than capturing a week that can't exist.
3. Create branch `recap-week-NN` (zero-padded, e.g. `recap-week-04`) and switch to it. Write,
   fact-check, and the draft PR happen on this branch; `recap-ship` publishes from its own.

## Steps

1. Start the local receiver in the background: `python3 scripts/receive.py --count 1`.
2. In Chrome, open a tab at:
   `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/698468554?view=mStatus`
3. Run in that tab (via the `javascript_tool`):
   ```
   eval(await fetch('http://127.0.0.1:8765/capture.js').then(r => r.text()));
   await fantasyCapture([N])
   ```
   This writes `data/2026/week-NN/espn.json`. **Never retype or hand-construct this JSON** —
   it must come from the capture script, since a raw ESPN payload contains members' last names,
   ESPN IDs, and notification settings that must never be committed (CLAUDE.md Privacy). Check
   the response for `complete: true` before moving on.
4. If the site also needs next week's tab before the next scheduled run, run
   `await fantasyCapture('next')` in the same tab (raise `--count` to accept both responses).
   This writes `data/2026/next-week/espn.json` — deliberately never committed
   (`.gitignore`); it's recaptured on every live update and goes stale the moment the week
   starts, so there's no reason to keep an old copy around.
5. **If the Chrome capture fails** (Claude in Chrome unavailable, or the tab errors): stop the
   Chrome attempt (kill `receive.py`, close the tab) and fall back to
   `node scripts/capture_node.mjs N`, same output file, same `complete` field to check. If that
   fails too with **ESPN 401**, the league has gone private again: **stop and tell the user**
   (the commissioner switches it back to public in ESPN's league settings). Don't guess at data
   or proceed with a partial capture.
6. **If the capture reports `complete: false`** (a game is still in progress or stats haven't
   settled): stop without drafting anything, switch back to `main`, delete the empty
   `recap-week-NN` branch you created in Step 0, and tell the user to try again later. Keep the
   captured data file on disk either way — the Live page uses it even when it's incomplete.
7. Run `python3 scripts/analyze.py` → writes `facts.json` for the week, next to `espn.json`.
8. Close any Chrome tabs you opened for this and confirm `receive.py` has exited.

## Output

`data/2026/week-NN/{espn.json,facts.json}`, both with `complete: true`/valid structure, on
branch `recap-week-NN`. This is what `recap-write` reads next. Neither file is ever
hand-edited — if something in them looks wrong, the fix is a better capture or a fix to
`analyze.py`, not editing the JSON directly.
