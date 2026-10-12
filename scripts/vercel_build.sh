#!/usr/bin/env bash
# Vercel's buildCommand (see vercel.json).
#
# Why this exists: vercel.json's outputDirectory is a single fixed path, but this project
# publishes two different trees — the league site, and the draft review copy. So this
# stages whichever one the current target wants into one directory that Vercel then
# serves. The target comes from FANTASY_TARGET, exported by scripts/deploy.sh, and NOT
# from VERCEL_ENV: `vercel build --prod` does not set VERCEL_ENV in the build command's
# environment at all, so keying off it silently staged the draft copy for production.
# Defaulting to preview means a mistake shows a draft to nobody rather than the league.
#
# For the league site this runs on Maya's Mac or in CI, via scripts/deploy.sh, which is
# what lets the uncommitted live-week capture in data/ reach the site at all. It also runs
# on Vercel's own servers for the automatic preview of every branch except main (see
# vercel.json); there FANTASY_TARGET is unset, so it stages the draft copy from committed
# data only, behind Deployment Protection.
set -euo pipefail
cd "$(dirname "$0")/.."

# Fail closed: a production build on Vercel's own servers (someone promoting a branch
# preview from the dashboard, or a push to whatever the dashboard calls the Production
# Branch) would otherwise take the preview default below and publish the draft copy, with
# no live week, to the league. Vercel sets VERCEL_ENV in its server builds; deploy.sh
# always exports FANTASY_TARGET, so its local and CI builds never reach this.
if [ -z "${FANTASY_TARGET:-}" ] && [ "${VERCEL_ENV:-}" = "production" ]; then
  echo "vercel_build: refusing a production build without FANTASY_TARGET; deploy the league site with scripts/deploy.sh" >&2
  exit 1
fi

# Vercel's own preview build has only committed data, so no live week and no Coach tab. Borrow
# the live week production is serving (best effort; the draft copy only). deploy.sh sets
# FANTASY_TARGET and builds with the real live capture, so it never takes this branch.
if [ -z "${FANTASY_TARGET:-}" ]; then
  export FANTASY_LIVE_FROM="${FANTASY_LIVE_FROM:-https://fantasyforthegirls.vercel.app/}"
fi

python3 site/build.py

src=site/dist/web-preview
[ "${FANTASY_TARGET:-preview}" = "production" ] && src=site/dist/web

out=site/dist/out
rm -rf "$out"
mkdir -p "$out"
cp -R "$src/." "$out/"
echo "vercel_build: staged $src -> $out ($(ls "$out" | tr '\n' ' '))"
