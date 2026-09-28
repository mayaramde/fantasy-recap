#!/usr/bin/env bash
# Prepare a Claude Code cloud session to run scripts/deploy.sh.
#
# Point the cloud environment's "Setup script" at this file:
#   bash scripts/cloud_setup.sh
#
# Cloud containers don't ship the Vercel CLI, so deploy.sh has nothing to call. This
# installs it, pinned to the same major the cloud live update uses (see live-update.yml)
# so both deploy paths behave alike.
#
# Two things this script can't supply, because they're environment settings:
#   - VERCEL_TOKEN, VERCEL_ORG_ID, VERCEL_PROJECT_ID (the values live-update.yml uses).
#     It warns when they're missing rather than failing, so the rest of the session works.
#   - Network access that allows api.vercel.com and *.vercel.app. Without it the CLI
#     can't reach Vercel at all, whatever the token says.
#
# Note a cloud deploy publishes only committed data, so its Live page misses the
# uncommitted live-week capture that a deploy from the Mac includes.
set -euo pipefail
cd "$(dirname "$0")/.."

vercel_major=60

installed=$(vercel --version 2>/dev/null || true)
case "$installed" in
  "$vercel_major".*)
    echo "cloud_setup: vercel $installed already installed"
    ;;
  *)
    if npm install --global "vercel@$vercel_major" >/dev/null 2>&1; then
      echo "cloud_setup: installed vercel $(vercel --version 2>/dev/null)"
    else
      # Not fatal: everything except deploying still works without the CLI.
      echo "cloud_setup: WARNING could not install vercel@$vercel_major; scripts/deploy.sh won't run" >&2
    fi
    ;;
esac

missing=
for var in VERCEL_TOKEN VERCEL_ORG_ID VERCEL_PROJECT_ID; do
  [ -n "${!var:-}" ] || missing="$missing $var"
done
[ -z "$missing" ] || echo "cloud_setup: WARNING not set:$missing — scripts/deploy.sh can't authenticate here" >&2
