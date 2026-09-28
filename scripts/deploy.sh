#!/usr/bin/env bash
# Deploy the league site to Vercel.
#
# Builds locally (so it includes this Mac's uncommitted live-week data), packages
# site/dist/web as a Vercel Build Output API bundle, and uploads it with --prebuilt.
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

python3 site/build.py

out=.vercel/output
rm -rf "$out"
mkdir -p "$out/static"
if $preview; then
  cp site/dist/web-preview/index.html site/dist/web-preview/robots.txt "$out/static/"
else
  cp site/dist/web/index.html site/dist/web/robots.txt "$out/static/"
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
    { "src": "/((?!api/).*)", "headers": { "X-Robots-Tag": "noindex, nofollow", "Cache-Control": "public, max-age=0, must-revalidate" }, "continue": true },
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
