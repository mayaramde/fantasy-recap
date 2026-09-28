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
# This runs on Maya's Mac, not on Vercel (git-triggered deploys are off), which is what
# lets the uncommitted live-week capture in data/ reach the site at all.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 site/build.py

src=site/dist/web-preview
[ "${FANTASY_TARGET:-preview}" = "production" ] && src=site/dist/web

out=site/dist/out
rm -rf "$out"
mkdir -p "$out"
cp -R "$src/." "$out/"
echo "vercel_build: staged $src -> $out ($(ls "$out" | tr '\n' ' '))"
