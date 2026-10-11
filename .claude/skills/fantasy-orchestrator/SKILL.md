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

## Execution model

The four skills (`recap-capture`, `recap-write`, `recap-ship`, `coach-daily`)
run in this session, one after another, because each step needs the
previous one's output. The two read-only judges, `recap-fact-checker` and
`code-reviewer`, are spawned as real subagents (via the `Agent` tool) from
inside `recap-write` and `recap-ship`, because their value is being
independent of whatever produced the thing they review. `voice-check` is a
third read-only judge, spawned the same way but by this orchestrator itself,
between `recap-write`'s fact-check and its draft PR (Phase 2).

## Team

| Member | Type | Role | Skill it uses | Output |
|--------|------|------|----------------|--------|
| (this session) | — | capture | `recap-capture` | `data/<season>/week-NN/{espn.json,facts.json}` |
| (this session) | — | write | `recap-write` | `recaps/<season>/week-NN.json` (`status: draft`), draft PR, preview URL |
| recap-fact-checker | custom agent | fact-check | (invoked by recap-write) | PASS/FAIL + claim table |
| voice-check | custom agent | voice review | (invoked by this orchestrator, Phase 2, and by coach-daily) | per-field verdict + rewrites |
| (this session) | — | ship | `recap-ship` | published site + publish PR |
| code-reviewer | custom agent | code review | (invoked by recap-ship, conditionally) | findings list |
| (this session) | — | daily snapshot | `coach-daily` | `data/<season>/fantasypros/latest.json` |

## Workflow

### Phase 0: intake & triage (always entered first — this skill is the repo's entry point)

Before anything else, sort the request:

- **Trivial / conversational / no fantasy-football domain knowledge needed to answer** ("what does PPR mean", "who's Ja'Marr Chase") → answer directly. Stop.
- **A change to `scripts/`, `site/`, `.github/`, or any other engineering work not about recap *content*** → this is the normal PR flow, not this skill. Use `code-reviewer` the way any non-trivial change would, per CLAUDE.md. Stop.
- **"Why is the live page stale / ESPN 401 / deploy failing"** → answer from `docs/vercel.md`, `docs/architecture.md`, and the relevant GitHub Actions run logs. No skill writes anything for this; it's a diagnosis, not a production step. Stop.
- **Anything else about a weekly recap, the Coach page, or coach-daily's cards** → continue to the context check below.

**Context check** — figure out which stage of the pipeline the request is actually asking for:

1. Identify the target season/week. Default to the most recent week that's final but has no recap yet (check the Live page / most recent `data/<season>/week-NN/` capture against `recaps/<season>/`); use an explicit week if the user names one.
2. Look for `recaps/<season>/week-NN.json` on an up-to-date `main` (`git fetch origin`, then
   check `origin/main`) and on any open `recap-week-NN` PR (drafts auto-merge, so a stale local
   checkout can miss one). Read its `status` if it exists:
   - **Absent** → this is a new recap. Go to Phase 1 (recap-capture), then Phase 2 (recap-write).
   - **Present, `status: "draft"`** → a revision. If the request implies the underlying data might have changed (re-capture explicitly asked for, or the data looks stale), go to Phase 1 first; otherwise skip straight to Phase 2 (recap-write) with the existing draft as input.
   - **Present, `status: "published"`** → nothing left to draft or revise. A request to "redo" a published week is unusual — confirm with the user what they actually want (a correction PR is different from a normal draft cycle) rather than assuming.
3. A request to **publish, approve, or ship** → Phase 3 (recap-ship) directly, using whatever draft already exists. If no draft exists yet, say so — there's nothing to ship.
4. A request about **coach cards, waiver ideas, trade ideas, or "run coach-daily"** → Phase 4 (`coach-daily`), independent of the recap pipeline above.

### Phase 1: capture — runs `recap-capture`

Input: target season/week. Output: `data/<season>/week-NN/{espn.json,facts.json}` on disk,
`complete: true` confirmed. See `recap-capture`'s own SKILL.md for the exact steps (Chrome
capture, the headless fallback, `analyze.py`) — this orchestrator just confirms the output exists
and is complete before moving on. If capture fails and the documented fallback also fails,
**stop and tell the user** — don't proceed to writing a recap from data that isn't there.

### Phase 2: write — runs `recap-write`

Input: `data/<season>/week-NN/{espn.json,facts.json}`, FantasyPros context, (if a revision)
the existing draft. Output: a fact-checked, voice-checked `recaps/<season>/week-NN.json` with
`status: "draft"`, the `Week NN recap draft` PR, and a review preview URL for the user.

Order: `recap-write` Steps 1-3 (write, `check.py`, fact-check), then the voice gate below, then
`recap-write` Step 4 (draft PR and preview). If the fact-checker still FAILs after two revise
rounds, stop and show the user its last report.

**Voice gate.** Once the draft passes the fact-check, spawn the `voice-check` agent on it (the
`Agent` tool, `subagent_type: voice-check`), passing the draft's path and, for a partial
revision like one blurb or the glossary, which fields changed so it judges those rather than
re-litigating the whole recap. It reads CLAUDE.md's Voice section and the calibration recaps
itself. The fact-checker doesn't judge tone, so this is the only voice check.

- **reads as intended** → on to `recap-write` Step 4.
- **reads flat** or **breaks a rule** → hand its report back to `recap-write` to revise exactly
  those fields, then re-run the fact-check (a rewrite can break a number or a citation) and the
  voice gate. **This shares the fact-check's two-round cap**, counted across both judges. If
  it still isn't clean, stop and show the user both reports.

### Phase 3: ship — runs `recap-ship`

Input: `recaps/<season>/week-NN.json` (status `draft`, already fact- and voice-checked). **Nothing
publishes without the user's explicit approval of the preview.** Then `recap-ship` flips
`status` to `"published"` and opens the `Publish week NN recap` PR — CI deploys the live
site automatically once that PR merges (`live-update.yml`'s `push` trigger), not this skill.

### Phase 4: coach-daily (independent of the recap pipeline)

Input: none beyond the target date. Output: `data/<season>/fantasypros/latest.json`, its own
PR with auto-merge. `coach-daily` runs its own `voice-check` gate on the cards before writing the
file (its Step 5b), since that PR merges without a human reading it. Doesn't touch any recap or any `data/<season>/week-NN/` file — see
`coach-daily`'s own SKILL.md.

## Error handling

| Situation | Strategy |
|-----------|----------|
| ESPN capture 401s and the documented fallback (`capture_node.mjs`) also fails | Stop. The league has likely gone private again: tell the user (the commissioner switches it back to public) — don't guess at data. |
| FantasyPros MCP is unavailable or gated (premium tool) | `recap-write` proceeds on ESPN data alone, notes the gap; never invents an injury/bad-luck cause it can't source. |
| The user approves a preview, then asks for a change before shipping | Loop back to `recap-write` for that change, then re-run the fact-check and the voice gate and re-deploy the preview — don't skip re-verification because "it was already approved." |

## Test scenarios

- **Normal:** "draft the week 4 recap" → no `recaps/2026/week-04.json` yet → capture → write →
  fact-check PASS → voice-check "reads as intended" → draft PR open, preview URL shared,
  waiting on approval.
- **Flat voice:** correct numbers and sourced injuries, but every blurb is a fact with a
  qualifier stapled on → fact-check PASS → `voice-check` "reads flat" with per-field rewrites →
  one round back through `recap-write` and both judges → clean → draft PR and preview.
- **Revision:** "tweak the Cambri blurb in this week's recap" → draft already exists → straight
  to `recap-write` with the existing draft, skipping capture → fact-check → updated draft.
- **Triage:** "what does PPR mean" → answered directly, no skill invoked. "make the standings
  table sortable" (`site/`) → the normal engineering flow, not this skill.
- **Ship:** "publish the recap" with an existing fact-checked draft → straight to `recap-ship`,
  which confirms approval before touching `status` or the live site.

## Tools

Skills name tools by role (see `references/tools.md`); when a role's preferred tool is
unavailable, use its listed fallback rather than failing.
