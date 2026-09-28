#!/usr/bin/env bash
# Deploy the league site to Vercel.
#
# Builds locally (so it includes this Mac's uncommitted live-week data), packages
# site/dist/web as a Vercel Build Output API bundle, and uploads it with --prebuilt.
# That bundle includes the private per-manager dashboards at /me/<token>/, so a deploy
# from a checkout without the link secret would take them offline; site/build.py refuses
# to build in that state rather than let that happen quietly.
# Git-triggered deploys are off in vercel.json, so this script is the only way the
# production site changes. Needs a one-time `vercel login` and `vercel link`
# (or, in GitHub Actions, the VERCEL_* settings described in live-update.yml).
#
# The /me/ routes serve each manager's dashboard with no-store and no referrer, so the
# secret URL isn't cached by a shared proxy or leaked in a Referer header when she taps
# a link out of the page.
#
# The bundle also carries the /api/live function (api/live.py), which recomputes the
# current week from ESPN per request so the Live page can refresh itself instead of
# waiting for a redeploy. It needs ESPN_S2 and ESPN_SWID as Vercel environment
# variables; without them it answers 503 and the page keeps showing its baked data.
#
# Usage: scripts/deploy.sh [--preview]
#   (no flag)  build the league site and deploy it to production
#   --preview  build the draft review copy and deploy it to a throwaway preview URL:
#              drafts included, no private dashboards, never aliased to production
set -euo pipefail
cd "$(dirname "$0")/.."

preview=false
[ "${1:-}" = "--preview" ] && { preview=true; shift; }
if [ $# -gt 0 ]; then
  echo "usage: scripts/deploy.sh [--preview]" >&2
  exit 2
fi

out=.vercel/output
rm -rf "$out"
mkdir -p "$out/static"
if $preview; then
  python3 site/build.py
  # The draft copy only. No me/: a draft review doesn't need the dashboards, and those
  # tokens should exist at one URL rather than two.
  cp -R site/dist/web-preview/. "$out/static/"
else
  python3 site/build.py --require-dashboards
  # The whole tree, so the private dashboards under me/ ship with the league page.
  cp -R site/dist/web/. "$out/static/"
fi

# /api/live: a Python function whose bundle mirrors the repo layout, so the analyze.py
# and build.py inside it resolve league.json and data/ exactly as they do here — that is
# what keeps the Live page's numbers identical to the ones the recap will quote. Only the
# current week is fetched from ESPN; earlier weeks come from the captures shipped here.
fn="$out/functions/api/live.func"
mkdir -p "$fn/scripts" "$fn/site" "$fn/data"
cp api/live.py "$fn/live.py"
cp league.json "$fn/"
cp scripts/analyze.py scripts/espn_fetch.py "$fn/scripts/"
cp site/build.py "$fn/site/"
cp data/player_names.json "$fn/data/"
for capture in data/*/week-*/espn.json; do
  mkdir -p "$fn/$(dirname "$capture")"
  cp "$capture" "$fn/$capture"
done
cat > "$fn/.vc-config.json" <<'EOF'
{ "runtime": "python3.12", "handler": "live.py", "maxDuration": 30 }
EOF

# /api/ is excluded from the header rule so the function's own Cache-Control (which lets
# the CDN answer eight refreshes from one ESPN request) isn't overwritten by the page's.
cat > "$out/config.json" <<'EOF'
{
  "version": 3,
  "routes": [
    { "src": "/((?!me/|api/).*)", "headers": { "X-Robots-Tag": "noindex, nofollow", "Cache-Control": "public, max-age=0, must-revalidate" }, "continue": true },
    { "src": "/me/.*", "headers": { "X-Robots-Tag": "noindex, nofollow", "Cache-Control": "private, no-store, max-age=0", "Referrer-Policy": "no-referrer" }, "continue": true },
    { "src": "/me/([^/]+)/?$", "dest": "/me/$1/index.html" },
    { "handle": "filesystem" }
  ]
}
EOF

# On this Mac the CLI uses `vercel login`; the cloud live update passes VERCEL_TOKEN
# (plus VERCEL_ORG_ID / VERCEL_PROJECT_ID in place of `vercel link`).
if $preview; then
  vercel deploy --prebuilt --yes ${VERCEL_TOKEN:+--token "$VERCEL_TOKEN"}
else
  vercel deploy --prebuilt --prod --yes ${VERCEL_TOKEN:+--token "$VERCEL_TOKEN"}
fi
