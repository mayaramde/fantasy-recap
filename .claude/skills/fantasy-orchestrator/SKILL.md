---
name: fantasy-orchestrator
description: Entry point for ALL Fantasy Recap work — invoke this before responding to any request about drafting, redoing, tweaking, or publishing a weekly recap; running or updating the Coach page's start/sit, waiver, or trade cards; or why the Live page, a capture, or a deploy looks stale/broken. Triggers on "draft the recap", "write week N", "redo the recap", "update the Cambri matchup blurb", "publish/ship the recap", "run the coach cards", "refresh waiver ideas", "is the live page stale", "re-run coach-daily", and everyday phrasing like it — including follow-ups ("tweak that", "redo this one", "supplement with X", "improve that blurb"). Does NOT trigger on generic football/fantasy questions with no repo action attached ("what does PPR mean"), or on a change to scripts/, site/, or CI unrelated to recap content — those go through the normal engineering flow with code-reviewer, not this skill.
model: inherit
---

# Fantasy orchestrator

Coordinates recap production and shipping, and the daily Coach snapshot.
Doesn't write recap content, capture data, or review code itself — it
triages the request and runs the right skill(s) in order, in this same
session, passing along whatever the next step needs.

## Execution mode: subagent

The four skills below (`recap-capture`, `recap-write`, `recap-ship`,
`coach-daily`) are sequential procedures this same session follows one after
another — they don't run as separate parallel agents, because each step
needs the previous one's output before it can start (you can't write a
recap before you've captured the week's data). The two read-only judges —
`recap-fact-checker` and `code-reviewer` — **are** spawned as actual
subagents (via the `Agent` tool), from inside `recap-write` and `recap-ship`
respectively, because their whole value is being independent of whatever
produced the thing they're reviewing.

## Team

| Member | Type | Role | Skill it uses | Output |
|--------|------|------|----------------|--------|
| (this session) | — | capture | `recap-capture` | `data/<season>/week-NN/{espn.json,facts.json}` |
| (this session) | — | write | `recap-write` | `recaps/<season>/week-NN.json` (`status: draft`) |
| recap-fact-checker | custom agent | fact-check | (invoked by recap-write) | PASS/FAIL + claim table |
| (this session) | — | ship | `recap-ship` | published site + merged PR |
| code-reviewer | custom agent | code review | (invoked by recap-ship, conditionally) | findings list |
| (this session) | — | daily snapshot | `coach-daily` | `data/<season>/fantasypros/latest.json` |

No SDD or issue-tracker coordination applies here: OpenSpec and GitHub
Issues (registered elsewhere in this repo for changes to the codebase
itself) are for proposing and tracking *code* changes. Recap production is
a recurring content pipeline over data that's captured fresh every week —
there's no spec to propose or a ticket to pull for "write week 4's recap."

## Workflow

### Phase 0: intake & triage (always entered first — this skill is the repo's entry point)

Before anything else, sort the request:

- **Trivial / conversational / no fantasy-football domain knowledge needed to answer** ("what does PPR mean", "who's Ja'Marr Chase") → answer directly. Stop.
- **A change to `scripts/`, `site/`, `.github/`, or any other engineering work not about recap *content*** → this is the normal PR flow, not this skill. Use `code-reviewer` the way any non-trivial change would, per CLAUDE.md. Stop.
- **"Why is the live page stale / ESPN 401 / deploy failing"** → answer from `docs/vercel.md`, `docs/architecture.md`, and the relevant GitHub Actions run logs. No skill writes anything for this; it's a diagnosis, not a production step. Stop.
- **Anything else about a weekly recap, the Coach page, or coach-daily's cards** → continue to the context check below.

**Context check** — figure out which stage of the pipeline the request is actually asking for:

1. Identify the target season/week. Default to the most recent week that's final but has no recap yet (check the Live page / most recent `data/<season>/week-NN/` capture against `recaps/<season>/`); use an explicit week if the user names one.
2. Look for `recaps/<season>/week-NN.json` and read its `status` if it exists:
   - **Absent** → this is a new recap. Go to Phase 1 (recap-capture), then Phase 2 (recap-write).
   - **Present, `status: "draft"`** → a revision. If the request implies the underlying data might have changed (re-capture explicitly asked for, or the data looks stale), go to Phase 1 first; otherwise skip straight to Phase 2 (recap-write) with the existing draft as input.
   - **Present, `status: "published"`** → nothing left to draft or revise. A request to "redo" a published week is unusual — confirm with the user what they actually want (a correction PR is different from a normal draft cycle) rather than assuming.
3. A request to **publish, approve, or ship** → Phase 3 (recap-ship) directly, using whatever draft already exists. If no draft exists yet, say so — there's nothing to ship.
4. A request about **coach cards, waiver ideas, trade ideas, or "run coach-daily"** → Phase 4 (`coach-daily`), independent of the recap pipeline above.

### Phase 1: capture — runs `recap-capture`

Input: target season/week. Output: `data/<season>/week-NN/{espn.json,facts.json}` on disk,
`complete: true` confirmed. See `recap-capture`'s own SKILL.md for the exact steps (Chrome
capture, the 401 fallback, `analyze.py`) — this orchestrator just confirms the output exists
and is complete before moving on. If capture fails and the documented fallback also fails,
**stop and tell the user** — don't proceed to writing a recap from data that isn't there.

### Phase 2: write — runs `recap-write`

Input: `data/<season>/week-NN/{espn.json,facts.json}`, FantasyPros context, (if a revision)
the existing draft. Output: `recaps/<season>/week-NN.json` with `status: "draft"`.

`recap-write` hands its own draft to the `recap-fact-checker` agent before considering itself
done, and revises on a FAIL — **capped at two revise-and-recheck rounds**. If it's still
failing after two rounds, stop and show the user the fact-checker's last report rather than
publishing something unverified or looping forever.

### Phase 3: ship — runs `recap-ship`

Input: `recaps/<season>/week-NN.json` (status `draft`, already fact-checked). Runs the build,
deploys the review preview, **waits for the user's explicit approval** — nothing publishes
without it, and no skill reads or prints ESPN cookies or Vercel tokens at any point — then
flips `status` to `"published"`, ships via `scripts/deploy.sh`, and opens the PR. If the diff
touches `scripts/`, `site/`, or `.github/` (not just `recaps/`/`data/`), `recap-ship` calls
`code-reviewer` on that part of the diff before opening the PR.

### Phase 4: coach-daily (independent of the recap pipeline)

Input: none beyond the target date. Output: `data/<season>/fantasypros/latest.json`, its own
PR with auto-merge. Doesn't touch any recap or any `data/<season>/week-NN/` file — see
`coach-daily`'s own SKILL.md.

## Error handling

| Situation | Strategy |
|-----------|----------|
| ESPN capture 401s and the documented fallback (`.env.espn.local` + `capture_node.mjs`) also fails | Stop. Tell the user what's missing — don't guess at data. |
| FantasyPros MCP is unavailable or gated (premium tool) | `recap-write` proceeds on ESPN data alone, notes the gap; never invents an injury/bad-luck cause it can't source. |
| `recap-fact-checker` FAILs twice in a row | Stop. Show the user the last FAIL report — don't force a third round or publish anyway. |
| `code-reviewer` flags something in `recap-ship`'s engineering diff | Surface it to the user before opening the PR; don't silently proceed. |
| The user approves a preview, then asks for a change before shipping | Loop back to `recap-write` for that change, then re-run the fact-check and re-deploy the preview — don't skip re-verification because "it was already approved." |

## Test scenarios

- **Normal:** "draft the week 4 recap" → no `recaps/2026/week-04.json` yet → capture → write →
  fact-check PASS → draft exists with `status: "draft"`, ready for `recap-ship` once approved.
- **Revision:** "tweak the Cambri blurb in this week's recap" → draft already exists → straight
  to `recap-write` with the existing draft, skipping capture → fact-check → updated draft.
- **Error:** a copy of a draft with an invented injury cause and a wrong score → `recap-write`
  → `recap-fact-checker` FAILs both → one revise-and-recheck round → still failing → stop and
  report exactly what's wrong, don't publish.
- **Triage:** "what does PPR mean" → answered directly, no skill invoked. "fix a typo in
  README.md" → routed to the normal engineering flow, not this skill.
- **Ship:** "publish the recap" with an existing fact-checked draft → straight to `recap-ship`,
  waits for approval before touching `status` or the live site.

## Tools

Roles this pipeline depends on are registered by role (not by hard tool name) in
`references/tools.md`, reviewed 2026-09-29. Skills reference a role from that file; when the
preferred tool for a role is unavailable, they fall back to the registered alternative rather
than failing outright.
