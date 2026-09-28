#!/usr/bin/env bash
# Deploy the league site to Vercel production.
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
# Usage: scripts/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

python3 site/build.py --require-dashboards

out=.vercel/output
rm -rf "$out"
mkdir -p "$out/static"
# The whole tree, so the private dashboards under me/ ship with the league page.
cp -R site/dist/web/. "$out/static/"
cat > "$out/config.json" <<'EOF'
{
  "version": 3,
  "routes": [
    { "src": "/((?!me/).*)", "headers": { "X-Robots-Tag": "noindex, nofollow", "Cache-Control": "public, max-age=0, must-revalidate" }, "continue": true },
    { "src": "/me/.*", "headers": { "X-Robots-Tag": "noindex, nofollow", "Cache-Control": "private, no-store, max-age=0", "Referrer-Policy": "no-referrer" }, "continue": true },
    { "src": "/me/([^/]+)/?$", "dest": "/me/$1/index.html" },
    { "handle": "filesystem" }
  ]
}
EOF

# On this Mac the CLI uses `vercel login`; the cloud live update passes VERCEL_TOKEN
# (plus VERCEL_ORG_ID / VERCEL_PROJECT_ID in place of `vercel link`).
vercel deploy --prebuilt --prod --yes ${VERCEL_TOKEN:+--token "$VERCEL_TOKEN"}
