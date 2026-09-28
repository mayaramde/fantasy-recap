#!/usr/bin/env bash
# Deploy the league site to Vercel production.
#
# Builds locally (so it includes this Mac's uncommitted live-week data), packages
# site/dist/web as a Vercel Build Output API bundle, and uploads it with --prebuilt.
# Git-triggered deploys are off in vercel.json, so this script is the only way the
# production site changes. Needs a one-time `vercel login` and `vercel link`.
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

vercel deploy --prebuilt --prod --yes
