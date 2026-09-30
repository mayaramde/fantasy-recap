---
name: recap-ship
description: Builds the site, deploys a review preview, waits for Maya's approval, then publishes and ships a fact-checked recap draft. Invoked by fantasy-orchestrator for "publish/ship/approve the recap" requests, once recap-write has produced a draft that passed recap-fact-checker. Don't invoke this directly for a user-facing request; route through fantasy-orchestrator first.
model: inherit
---

# Recap ship

Takes a fact-checked draft from `draft` to live: preview, wait for approval, publish, PR.
**Nothing in this skill publishes anything without Maya's explicit approval**, and no step
here reads or prints ESPN cookies or Vercel tokens.

## Step 1: preview (skip if recap-write just shared one and nothing changed since)

`scripts/deploy.sh --preview` builds the draft copy (`site/build.py` → `site/dist/web-preview/`)
and deploys it to a fresh, throwaway Vercel URL.

**Fatal if skipped: confirm the draft is on disk first.** `recaps/2026/week-NN.json` must exist
in the working tree with `"status": "draft"`. It lives on the `recap-week-NN` branch until the
draft PR merges, and on `main` after. Checking out a branch without it removes it with no error,
and a preview built then deploys *successfully* while silently missing the week. **If the file
isn't there, stop. Do not run `scripts/deploy.sh --preview` anyway.** Tell Maya what's missing.

Share the printed preview URL with Maya. **Wait for her explicit approval**; nothing below
runs until she says go. If she asks for a change instead, that's `recap-write` again,
fact-check included, then a fresh preview.

## Step 2: publish (only after approval)

1. Get onto a branch that has the draft: `recap-week-NN` if its PR is still open, otherwise a
   new `publish-week-NN` branch from an up-to-date `main`.
2. Set `"status": "published"` in `recaps/2026/week-NN.json`.
3. Run `scripts/deploy.sh` to ship the league site.

## Step 3: publish PR

Run `python3 scripts/check.py` first and fix anything it flags. Then:

1. Commit **only** `recaps/2026/week-NN.json`, plus `data/2026/week-NN/`,
   `data/player_names.json`, or already-committed weeks' `facts.json` if they changed. Never
   `git add -A`, and never sweep in another week's uncommitted data.
2. Push and open a PR titled `Publish week NN recap` (or push to the open draft PR if you stayed
   on `recap-week-NN`). Enable auto-merge (squash); it merges once `checks` passes. Don't merge
   it yourself. Until it merges, `site_guard.py` keeps the cloud live update from deploying over
   the published recap.

**If the diff includes anything beyond `recaps/`/`data/`** (a change to `scripts/`, `site/`, or
`.github/`), call the `code-reviewer` agent on that part of the diff before opening the PR and
surface its findings to Maya. Don't proceed silently if it flags something.

## Output

The live site updated, `status: "published"` committed, a PR open with auto-merge on, plus
`code-reviewer`'s findings if it ran.
