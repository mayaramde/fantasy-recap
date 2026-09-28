#!/usr/bin/env bash
# Deploy the league site to Vercel.
#
# Builds locally (so it includes this Mac's uncommitted live-week data) with `vercel
# build`, then uploads the result with --prebuilt.
# Git-triggered deploys are off in vercel.json, so this script is the only way the
# production site changes. Needs a one-time `vercel login` and `vercel link`
# (or, in GitHub Actions, the VERCEL_* settings described in live-update.yml).
#
# The bundle also carries the /api/live function (api/live.py), which recomputes the
# current week from ESPN per request so the Live page can refresh itself instead of
# waiting for a redeploy. It needs ESPN_S2 and ESPN_SWID as Vercel environment
# variables; without them it answers 503 and the page keeps showing its baked data.
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
token=(${VERCEL_TOKEN:+--token "$VERCEL_TOKEN"})
# scripts/vercel_build.sh reads this to choose which tree to publish. Passed explicitly
# because `vercel build --prod` leaves VERCEL_ENV unset in the build command.
if $preview; then
  FANTASY_TARGET=preview vercel build --yes "${token[@]}"
  vercel deploy --prebuilt --yes "${token[@]}"
else
  FANTASY_TARGET=production vercel build --prod --yes "${token[@]}"
  vercel deploy --prebuilt --prod --yes "${token[@]}"
fi
