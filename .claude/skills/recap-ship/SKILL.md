---
name: recap-ship
description: Builds the site, deploys a review preview, waits for Maya's approval, then publishes and ships a fact-checked recap draft. Invoked by fantasy-orchestrator for "publish/ship/approve the recap" requests, once recap-write has produced a draft that passed recap-fact-checker. Don't invoke this directly for a user-facing request; route through fantasy-orchestrator first.
tools: Read, Edit, Bash, Grep, Glob
model: inherit
---

# Recap ship

Takes a fact-checked draft from `draft` to live. This is weekly routine
steps 5-8 (CLAUDE.md) — build, preview, wait for approval, publish, commit.
**Nothing in this skill publishes anything without Maya's explicit
approval**, and no step here reads or prints ESPN cookies or Vercel tokens.

## Step 1: build

`python3 site/build.py` → `site/dist/web-preview/` (drafts included — what Step 2 deploys) and
`site/dist/web/` (published only — what `scripts/deploy.sh` ships).

## Step 2: deploy the review preview

`scripts/deploy.sh --preview` builds the draft copy and deploys it to a fresh, throwaway Vercel
URL (a new `fantasy-recap-*.vercel.app` link every time — nothing to bookmark).

**Fatal if skipped — confirm the draft is actually on disk before running this.** Run `ls
recaps/2026/` (should show `week-NN.json`) and `git branch --show-current` (should be that
week's own branch, not `main`, unless its PR already merged). The draft file exists only on its
own branch until the PR merges; checking out `main` removes it from the working tree with no
error, and a preview built right after will deploy *successfully* while silently missing the
week — a preview that looks complete but isn't. **If `ls`/`git branch` don't show the draft
where expected, stop. Do not run `scripts/deploy.sh --preview` anyway.** Tell Maya what's
missing instead of handing her a preview that quietly isn't showing what she thinks it is.

Once confirmed, share the printed preview URL with Maya. **Wait here for her review and
explicit approval** — nothing in the next step runs until she says go.

## Step 3: publish (only after approval)

1. Set `"status": "published"` in `recaps/2026/week-NN.json`.
2. Run `scripts/deploy.sh` to ship `site/dist/web/` to the live site.

## Step 4: commit and PR

Run `python3 scripts/check.py` first and fix anything it flags. On the recap's own branch
(`recap-week-NN`, never `main` directly):

1. Commit **only** these paths: `recaps/2026/week-NN.json`, `data/2026/week-NN/`,
   `data/player_names.json`, and any `facts.json` under `data/2026` that changed for
   already-committed weeks. Never `git add -A`, and never sweep in another week's uncommitted
   data — a concurrent live-update run can leave the *next* week's files sitting uncommitted in
   the same working tree.
2. Push, and open a PR titled `"Week NN recap draft"`. Enable auto-merge (squash) — it merges
   once the `checks` workflow passes. Don't merge it yourself.

**If the diff includes anything beyond `recaps/`/`data/`** — a change to `scripts/`, `site/`, or
`.github/` bundled into the same PR — call the `code-reviewer` agent on that part of the diff
before opening the PR, the same as any other engineering change would get. Surface its findings
to Maya; don't silently proceed if it flags something.

## Output

The live site updated, `status: "published"` committed, a PR open with auto-merge on. If
`code-reviewer` was invoked, its findings are part of what gets reported back.
