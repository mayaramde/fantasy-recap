---
name: recap-capture
description: Captures a week's ESPN fantasy data (rosters, scores, projections) and runs analyze.py to produce facts.json. Invoked by fantasy-orchestrator as the first step of drafting or redoing a recap — don't invoke this directly for a user-facing request; route through fantasy-orchestrator first. Also fires on an explicit standalone request like "capture week N" or "re-run the ESPN capture for this week".
tools: Bash, Read
model: inherit
---

# Recap capture

Gets one week's ESPN data onto disk and turns it into `facts.json`. This is
weekly routine steps 1-2 (CLAUDE.md), extracted here since it's the same
procedure whether it's run as part of drafting a recap or on its own.

## Why Chrome, and why never touch the cookies

The league is private, so ESPN's API needs an authenticated session.
**Claude in Chrome**, using Maya's own logged-in session, is the default and
the only way *you* (the agent) ever touch ESPN's private data — never ask
for, copy, print, or store `espn_s2`/`SWID` or any other credential.

There are exactly two cookie-based fallbacks, and neither involves you
reading a cookie value — a *script* consumes them, never you:
1. The cloud live update (`live-update.yml`) reads `ESPN_S2`/`ESPN_SWID`
   from GitHub Actions secrets Maya set herself.
2. On Maya's Mac, if the Chrome capture 401s (her ESPN session logged out)
   and `.env.espn.local` exists (she copies `.env.espn.local.example` and
   fills in real values from Chrome DevTools herself — you never do this
   for her), fall back to `node scripts/capture_node.mjs N`.

Chrome is always the first attempt. The fallback is for when Chrome *can't*
authenticate, not a routine alternative.

## Step 0: get on the right branch

Only do this for a *new* recap (fantasy-orchestrator's context check found no
`recaps/2026/week-NN.json` yet) — a re-capture for an existing draft stays on that draft's
existing branch.

1. `git checkout main && git pull`. If checkout fails because of uncommitted changes, **stop
   and tell the user** — don't stash, reset, or discard anything that might be someone else's
   in-progress work.
2. Work out the target week: one more than the highest week number in `recaps/2026/`. If that
   week is past 17, the regular season is over — stop and tell the user rather than capturing
   a week that can't exist.
3. Create branch `recap-week-NN` (zero-padded, e.g. `recap-week-04`) and switch to it. Every
   later step in this pipeline (write, fact-check, ship) happens on this same branch.

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
5. **If ESPN returns 401** (Maya's Chrome session logged out): check whether `.env.espn.local`
   exists. If it does, stop the Chrome attempt (kill `receive.py`, close the tab) and fall back
   to `node scripts/capture_node.mjs N` — same output file, same `complete` field to check. If
   it doesn't exist, or the fallback also fails, **stop and tell the user** what's missing (see
   CLAUDE.md's Data sources section for the exact setup) — don't guess at data or proceed with
   a partial capture.
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
