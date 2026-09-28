#!/usr/bin/env bash
# Deploy the league site to Vercel production.
#
# Builds locally (so it includes this Mac's uncommitted live-week data), packages
# site/dist/web as a Vercel Build Output API bundle, and uploads it with --prebuilt.
# Git-triggered deploys are off in vercel.json, so this script is the only way the
# production site changes. Needs a one-time `vercel login` and `vercel link`
# (or, in GitHub Actions, the VERCEL_* settings described in live-update.yml).
#
# Usage: scripts/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

python3 site/build.py

out=.vercel/output
rm -rf "$out"
mkdir -p "$out/static"
cp site/dist/web/index.html site/dist/web/robots.txt "$out/static/"
cat > "$out/config.json" <<'EOF'
{
  "version": 3,
  "routes": [
    { "src": "/(.*)", "headers": { "X-Robots-Tag": "noindex, nofollow", "Cache-Control": "public, max-age=0, must-revalidate" }, "continue": true },
    { "handle": "filesystem" }
  ]
}
EOF

# On this Mac the CLI uses `vercel login`; the cloud live update passes VERCEL_TOKEN
# (plus VERCEL_ORG_ID / VERCEL_PROJECT_ID in place of `vercel link`).
vercel deploy --prebuilt --prod --yes ${VERCEL_TOKEN:+--token "$VERCEL_TOKEN"}
