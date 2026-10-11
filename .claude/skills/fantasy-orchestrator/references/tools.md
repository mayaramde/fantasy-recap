# Tools registry

Skills reference a tool by its **role**. When the preferred tool for a role is unavailable, use
the fallback: a missing tool degrades the pipeline, it doesn't stop it.

| Role | Preferred tool | Fallback |
|------|----------------|----------|
| fantasy-data | FantasyPros MCP (free-tier tools; pass `league_key` on every call) | ESPN capture only: no FantasyPros start/sit, waiver, or trade cards, and no injury causes in the recap |
| browser-capture | Claude in Chrome | `scripts/capture_node.mjs` (the league is public, so it needs no login) |
| source-control | GitHub MCP tools or `gh` CLI | plain `git` (PR steps then need the user) |
| deploy-inspection | Vercel MCP (read-only lookups) | `vercel ls`, `vercel logs` |

Considered but not installed (2026-09-29): Chrome DevTools MCP, a Gitleaks secret-scan wrapper,
Playwright MCP for visual checks, and a Vale prose linter. Nothing depends on them.
