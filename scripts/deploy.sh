#!/usr/bin/env bash
# Deploy the league site to Vercel.
#
# Builds locally (so it includes this Mac's uncommitted live-week data) with `vercel
# build`, then uploads the result with --prebuilt.
# Git-triggered deploys are off for main in vercel.json (other branches get automatic,
# committed-data-only previews), so this script is the only way the production site
# changes. Needs a one-time `vercel login` and `vercel link`
# (or, in GitHub Actions, the VERCEL_* settings described in live-update.yml).
#
# The bundle also carries the /api/live function (api/live.py), which recomputes the
# current week from ESPN per request so the Live page can refresh itself instead of
# waiting for a redeploy. It needs no secrets: the league is public on ESPN. If ESPN refuses
# (the league went private), it answers 503 and the page keeps showing its baked data.
#
# Usage: scripts/deploy.sh [--preview]
#   (no flag)  build the league site and deploy it to production
#   --preview  build the draft review copy and deploy it to a throwaway preview URL,
#              so a recap can be read on a phone before it's published
set -euo pipefail
cd "$(dirname "$0")/.."

preview=false
[ "${1:-}" = "--preview" ] && { preview=true; shift; }
if [ $# -gt 0 ]; then
  echo "usage: scripts/deploy.sh [--preview]" >&2
  exit 2
fi

# Vercel's own build produces the bundle (see vercel.json and scripts/vercel_build.sh).
# It has to be Vercel's build and not a hand-assembled one, because a Python function
# only works with the launcher Vercel generates for it: hand-writing .vc-config.json
# leaves Lambda calling the BaseHTTPRequestHandler subclass with (event, context), which
# raises TypeError. The launcher and its vendored runtime are ~180 files, so replicating
# them is not an option. `vercel build` runs here, on this Mac, so the uncommitted
# live-week capture still reaches the site.
# On this Mac the CLI uses `vercel login`; the cloud live update passes VERCEL_TOKEN
# (plus VERCEL_ORG_ID / VERCEL_PROJECT_ID in place of `vercel link`).
#
# Expanded below as ${token[@]+"${token[@]}"}, not "${token[@]}". macOS ships bash 3.2,
# and before bash 4.4 an empty array expanded under `set -u` is an unbound variable, not
# an empty list. Without a token — which is every run on this Mac — the plain form aborts
# the script before it builds anything. Don't "tidy" it back.
token=(${VERCEL_TOKEN:+--token "$VERCEL_TOKEN"})

# `vercel build` needs the project linked, i.e. a .vercel/project.json on disk. This Mac
# has one from the one-time `vercel link`; a GitHub Actions runner never does, and
# VERCEL_ORG_ID / VERCEL_PROJECT_ID on their own don't make one, so the build stops with
# "Could not retrieve Project Settings". `vercel pull` writes it from those two variables
# along with the project's settings, so run it wherever a token stands in for the link.
if [ -n "${VERCEL_TOKEN:-}" ]; then
  if $preview; then
    vercel pull --yes --environment=preview "${token[@]}"
  else
    vercel pull --yes --environment=production "${token[@]}"
  fi
fi

# A git worktree (what an agentic session builds in) has no project link of its own —
# .vercel/project.json only exists wherever `vercel link` was run once (this Mac's main
# checkout). Without a local link, `vercel build`/`vercel deploy` fall back to the
# repo-wide link Vercel's CLI finds by walking up to the nearest directory holding a
# *real* .git directory. From inside a worktree — where .git is just a pointer file —
# that walk skips right past it and lands on the main checkout, making the *whole* main
# checkout the function's bundling root: every other worktree nested under its
# .claude/worktrees/, each with its own .git pointer file, comes along for the ride, and
# Vercel then refuses to upload those as "version-control files". Bootstrapping a link
# scoped to *this* directory — the same trick GitHub Actions already uses above with a
# token — keeps the build scoped to just this checkout. No secrets involved: the org and
# project IDs aren't secret, and they're read straight from the main checkout's own
# .vercel/repo.json (written there by `vercel link`'s repo-aware mode), not typed in here.
#
# Gated on `[ -f .git ]`: a worktree's .git is a plain file, a normal checkout's is a
# directory. That keeps a brand-new Mac's very first `deploy.sh` — before `vercel link`
# has ever run, where .git is a directory and this block has nothing to do — from paying
# for `git rev-parse --path-format=absolute` (needs git 2.31+) at all.
if [ -z "${VERCEL_TOKEN:-}" ] && [ ! -f .vercel/project.json ] && [ -f .git ]; then
  main_root="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
  repo_link="$main_root/.vercel/repo.json"
  if [ "$main_root" != "$(pwd)" ] && [ -f "$repo_link" ]; then
    # repo.json (as `vercel link`'s repo-aware mode writes it today) nests orgId inside
    # each projects[] entry; fall back to a top-level orgId too, in case a future CLI
    # version moves it, rather than dying on a bare KeyError traceback.
    ids="$(python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
p = d['projects'][0]
print(p.get('orgId', d.get('orgId', '')), p['id'])
" "$repo_link")"
    read -r VERCEL_ORG_ID VERCEL_PROJECT_ID <<<"$ids"
    export VERCEL_ORG_ID VERCEL_PROJECT_ID
    if $preview; then
      vercel pull --yes --environment=preview
    else
      vercel pull --yes --environment=production
    fi
  elif [ "$main_root" != "$(pwd)" ]; then
    echo "deploy.sh: running from a worktree with no $repo_link to link from — the build may sweep in sibling worktrees' .git files (see vercel.json's excludeFiles)" >&2
  fi
fi

# scripts/vercel_build.sh reads this to choose which tree to publish. Passed explicitly
# because `vercel build --prod` leaves VERCEL_ENV unset in the build command.
if $preview; then
  FANTASY_TARGET=preview vercel build --yes ${token[@]+"${token[@]}"}
  vercel deploy --prebuilt --yes ${token[@]+"${token[@]}"}
else
  FANTASY_TARGET=production vercel build --prod --yes ${token[@]+"${token[@]}"}
  vercel deploy --prebuilt --prod --yes ${token[@]+"${token[@]}"}
fi
