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

Share the printed preview URL with Maya, and if the draft PR body carries a `voice-check`
"reads flat" report, show her that report with it. **Wait for her explicit approval**; nothing below
runs until she says go. If she asks for a change instead, that's `recap-write` again,
fact-check and voice gate included, then a fresh preview.

## Step 2: publish (only after approval)

1. The `Week NN recap draft` PR must have merged. If it hasn't, wait for it (or fix whatever
   is blocking `checks`); don't publish from the draft branch.
2. `git checkout main && git pull`, then create `publish-week-NN`. Branching from an
   up-to-date `main` also guarantees every earlier published week is in the tree, so the
   deploy can't pull one off the live site. If checkout fails on uncommitted changes, stop and
   tell Maya; don't stash or discard them.
3. Set `"status": "published"` in `recaps/2026/week-NN.json`.
4. **Update CLAUDE.md's Running threads** from the recap being published, in this same PR: add
   threads this recap started or kept alive, retire ones that died or paid off, and cite the
   weeks (verify every cite against the recap JSONs). Edit only the threads list in the Voice
   section. This runs from the next publish onward; it never rewrites old weeks.
5. Run `python3 scripts/check.py` and fix anything it flags. A published recap's problems
   always block, where a draft's may only have warned, so this must pass **before** the PR
   can merge.

## Step 3: publish PR

1. Commit **only** `recaps/2026/week-NN.json`, the Running threads edit in `CLAUDE.md`, plus `data/2026/week-NN/`,
   `data/player_names.json`, or already-committed weeks' `facts.json` if they changed. Never
   `git add -A`, and never sweep in another week's uncommitted data.
2. Push and open a PR titled `Publish week NN recap`. Enable auto-merge (squash); it merges
   once `checks` passes. Don't merge it yourself. Until it merges, `site_guard.py` keeps the cloud live update from deploying over
   the published recap.

**If the diff includes anything beyond `recaps/`/`data/` and the threads list** (a change to `scripts/`, `site/`, or
`.github/`), call the `code-reviewer` agent on that part of the diff before opening the PR and
surface its findings to Maya. Don't proceed silently if it flags something.

## Step 4: nothing to do — CI deploys

Once the publish PR merges, `live-update.yml`'s `push` trigger deploys the live site within
minutes on its own; the Mac is no longer in this path. Don't run `scripts/deploy.sh` yourself
as part of this skill — that's now a manual backstop (see `docs/vercel.md` §3), not a routine
step, and running it here would just race the same deploy CI is about to do. If the site
hasn't updated a few minutes after the PR merges, check the `live-update` workflow's run log
before reaching for `scripts/deploy.sh` by hand.

## Output

`status: "published"` committed, the publish PR open with auto-merge on (CI deploys once it
merges), plus `code-reviewer`'s findings if it ran.
