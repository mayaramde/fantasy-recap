# Tools registry

Agents and skills in this harness reference a tool by its **role**, never by a hard tool name.
When the preferred tool for a role is unavailable, fall back to the alternative — a missing or
unreachable tool degrades the pipeline, it doesn't stop it outright. Reviewed on the dates below.

| Role | Preferred tool | Alternative (if unavailable) | Status | Last reviewed |
|------|-----------------|-------------------------------|--------|---------------|
| fantasy-data | FantasyPros MCP (free-tier tools; pass `league_key` on every call) | ESPN capture only — no start/sit, waiver, or trade cards from FantasyPros | active | 2026-09-29 |
| browser-capture | Claude in Chrome | `scripts/capture_node.mjs` with `.env.espn.local`, run by the script, never read by Claude | active | 2026-09-29 |
| source-control | GitHub (`gh` CLI) | plain `git` | active | 2026-09-29 |
| deploy-inspection | Vercel MCP (read-only lookups) | `vercel ls`, `vercel logs` | active | 2026-09-29 |
| ci-log-inspection | GitHub MCP server (structured workflow-run/job-log tools) | `gh run list` / `gh run view --log` | **not configured** — this session's own GitHub MCP connector failed to authenticate ("incompatible auth server, no dynamic client registration"); `gh` CLI is the working path today | 2026-09-29 |
| browser-network-debug | Chrome DevTools MCP (structured network/console/perf access) | Claude in Chrome's existing console/network tools | **not configured** — public preview, not yet installed | 2026-09-29 |
| secret-scan | Gitleaks MCP wrapper (blocks ESPN cookies from landing in a diff) | manual `git diff` review before commit, plus `guard_bash.py`'s existing secret-path denials | **not configured** — not yet installed | 2026-09-29 |
| site-visual-check | Playwright MCP (deterministic browser control for visual-checking the built site) | the user's own review of the deployed preview URL | **not configured** — not yet installed | 2026-09-29 |
| voice-lint | Vale MCP wrapper (prose-pattern linting for jargon/glossary-count issues) | `recap-fact-checker`'s manual voice-and-jargon pass | **not configured** — not yet installed | 2026-09-29 |

The five roles marked "not configured" were accepted during tool discovery on 2026-09-29 but
registering a role here is not the same as installing the tool — nothing runs against them
until someone sets up the actual MCP server/plugin. Until then, every one of those roles has a
working fallback, so no skill is blocked by their absence.
