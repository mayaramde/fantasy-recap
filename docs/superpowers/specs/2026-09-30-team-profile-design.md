# Team profile page: design

Date: 2026-09-30 · Status: approved in conversation, awaiting spec review

## Goal

Turn `#team-<id>` into each manager's one-stop page for her team: who she's starting and what to
fix this week, what she's changed on her roster, an honest (cheeky) read on how her season is
going, and what to do about it. Readers are league members, most in their first season, so the
page explains as it goes (CLAUDE.md Voice, "Coach cards" dial).

## Decisions

| Decision | Choice |
|---|---|
| Relationship to the per-team Coach page | The profile **absorbs** it. `#coach-<id>` and `#coach-next-<id>` redirect to the profile. The league-wide `#coach` grid stays and links to profiles. |
| Source of the season audit | **Computed + written**: `build.py` computes each audit card with a situation `key`; `coach-daily` writes voiced copy per key; computed wording is the fallback. |
| Audit signals | Lineup IQ, Position strength, Projection vs reality. (Luck check considered and cut.) |
| Code location | New pure module `site/team_profile.py`, shared by `site/build.py` and `scripts/coach_brief.py`. |

## Page layout (`#team-<id>`, top to bottom)

1. **Header + stat tiles**: unchanged (record, average, best week, all-play, points benched).
2. **This week**: shown only while a live week exists. Week toggle (This week / Next week, only when
   the next-week capture is current), the one-line team summary, her computed and written to-do
   cards, then her lineup with the existing expandable player cards. This is today's `#coach-<id>`
   content moved as-is, refreshed by `/api/live` exactly as the Coach page is today. With no live
   week, it collapses to one line: "Nothing to fix until Week N's rosters land."
   `#team-<id>.next` selects the Next week tab.
3. **Coach's audit**: three cards (below), each with a computed stat pill plus a title and one line.
4. **Suggestions**: coach-daily's `roster_ideas` (waiver and trade leads) and "Worth a look" for
   this team. An idea whose `pos` matches the team's `weak_spot` gets a "fills your weak spot" tag.
   This week's computed swap cards stay in section 2.
5. **Recent moves**: her adds, drops and trades across every captured week, newest first, each
   tagged with its week. Lineup-only shuffles are excluded.
6. **Week by week + awards**: unchanged.

Routing: `#coach-<id>` → `#team-<id>`; `#coach-next-<id>` → `#team-<id>.next`. The browser's
"last team opened" memory for the Coach grid keeps working.

## Data flow

```
data/<season>/week-NN/{facts,espn}.json ──┐
data/<season>/fantasypros/latest.json ────┤
                                          ▼
                    site/team_profile.py  (pure functions, no I/O)
                      audit(team_id, facts_list)   → 3 cards, each with a key
                      moves(team_id, espn_list)    → her adds/drops/trades, all weeks
                      weak_spot(facts_list, team_id) → slot group, e.g. "TE"
                                          ▼
   site/build.py  season_payload() attaches team["profile"] = {audit, moves, weak_spot, ideas}
                  applies written audit copy where keys still match
                                          ▼
                  RECAP_DATA blob → template.html teamPage(id)
                                          ▲
               /api/live (unchanged) ─────┘  refreshes LIVE → "This week" section only
```

| Section | Source | Refreshes |
|---|---|---|
| This week | `LIVE.advice` / `LIVE.next` (existing) | Live, via `/api/live` |
| Coach's audit | `team_profile.audit()` over **included weeks only** (published recaps on the league site; drafts too in preview) | Each deploy |
| Suggestions | `latest.json` `roster_ideas` for the live week, tagged against `weak_spot` | Daily (coach-daily PR merge → deploy) |
| Recent moves | `team_profile.moves()` over **every captured** `espn.json`, including the live week | Each deploy |
| Stats + week by week | `season_payload()` (existing) | Each deploy |

Moves include the live week, so a pickup can show before that week's recap is published. The Live
page already shows the same moves publicly, so this is accepted. The audit uses recapped weeks
only, so a draft week's scores never reach the league site.

## Audit computations

All read existing `facts.json` fields; no capture changes.

- **Lineup IQ** (`kind: "lineup_iq"`). `pct = Σ points / Σ optimal_points` over her included
  weeks. Worst call = the `worst_bench_call` with the largest `benched_points − started_points`
  across those weeks. Band: A ≥ 95%, B ≥ 88%, C ≥ 80%, else D (starting thresholds; tune once
  the season has more weeks, since changing them changes keys and resets written copy once).
  Key `lineup:<band>:<benched player id>:w<week>`; `lineup:<band>:none` for a perfect season (nothing benched), `lineup:<band>:scattered` when points were left but no single call stands out (amended in review). Stat pill: `"<pct>% of optimal · <Σ points_left_on_bench> benched"`.
- **Position strength** (`kind: "position"`). Sum her starters' `points` by starting slot group
  (the `LINEUP` slots from `league.json`: QB, RB, WR, TE, FLEX, DST, K), rank each against the other 7 teams over the
  same weeks. Best = highest rank; worst = lowest rank; ties broken by `SLOT_ORDER` so the result is
  stable. `weak_spot` = worst group. Key `pos:<best><rank>:<worst><rank>`, e.g. `pos:RB1:WR8` (ranks added in review, so copy naming a rank expires when it changes). Stat pill: `"Best: <best> (#r) · Worst: <worst> (#r)"`.
- **Projection vs reality** (`kind: "projection"`). `delta = Σ (points − projected)` over her
  starters. Over- and under-performer: the starter with the largest and smallest average
  `points − projected`, among players with at least 2 starts. Key
  `proj:<over|under>:<top id | none>:<bottom id | none>` (`over` when `delta ≥ 0`). Stat pill: `"<±delta> vs projections"`.

Player ids go into keys as strings, so negative D/ST ids work. The A–D band lives only in the
key (for invalidation) and is never displayed: per CLAUDE.md, roast decisions, never a manager's
competence. Written copy roasts the specific call, not her.

Each card: `{key, kind, level: "info", stat, title, text}` plus `written: true` when coach-daily's
copy applied.

## Moves

From each captured `espn.json`'s `transactions`, keep types `FREEAGENT`, `WAIVER` and
`TRADE_ACCEPT` where the team is a party. Row: `{week, date, type, added: [names], dropped: [names]}`
(for a trade, `added` = players coming to her, `dropped` = players leaving). Drop `ROSTER`,
`DRAFT`, `FUTURE_ROSTER`. Sort newest first. Deduplicate by (date, type, player ids), since a
transaction can appear in two consecutive captures.

## coach-daily contract

### `scripts/coach_brief.py`
- Adds a top-level `audit` block: `{"<team_id>": {manager, weak_spot, cards: [{key, kind, stat, title, text}]}}`,
  computed from the league site's view (published recaps only) via `build.site_data`, so the brief's keys are byte-for-byte the page's.
- No longer exits with an error when there's no live week; the audit block exists all season.
  Per-week blocks are unchanged.

### `data/<season>/fantasypros/latest.json`
- New top-level `audit`: `{"<team_id>": {"<audit key>": {"title": "...", "text": "..."}}}`.
- `waiver` and `trade` cards in `roster_ideas` gain an optional `pos` (slot group string).

### Build validation
| Rule | Coach cards | Audit copy |
|---|---|---|
| Shown only while its key is still computed | yes | yes |
| `_MOVING_NUMBER` rejects decimals / % / "N points" in written text | yes | yes |
| 36-hour freshness gate (`_fp_fresh`) | yes | **no**, key match only |

An audit key fully encodes its situation and only changes when a new week is recapped, so
day-old copy for a still-matching key is still true. `load_fantasypros` must still parse the
file; a malformed file means computed wording everywhere.

### `.claude/skills/coach-daily/SKILL.md`
- **Step 5**: prefer waiver/trade leads at the brief's `weak_spot` when a real option exists there
  (never invent one to fill it), and set `pos` on those cards.
- **Step 5b**: also write `{title, text}` for every audit key. Dial: Coach cards.
- **Step 5c**: the voice gate covers audit copy. A dropped entry falls back to computed wording.
- **Step 6**: document the new `audit` block and `pos` field.

## Edge cases

| Situation | Behavior |
|---|---|
| No recapped weeks yet | Audit shows "The coach needs one finished week before she has opinions." Moves and This week still render. |
| One recapped week | Audit renders. Projection vs reality has no over/under-performer (key uses `none`). |
| No live week | This week collapses to one line; `#coach-<id>` links still land on the profile. |
| Next-week capture stale/missing | No week toggle; `#team-<id>.next` falls back to This week. |
| `latest.json` missing/malformed | Computed audit wording; Suggestions shows "No new ideas today." |
| `latest.json` older than 36h | Audit written copy still applies on key match; Suggestions shows "No new ideas today." |
| Written audit copy fails `_MOVING_NUMBER` | That card falls back to computed wording. |
| Position tie | Broken by `SLOT_ORDER`; the key is stable across builds. |
| Optimal lineup every week | Key `lineup:A:none`; the fallback line credits the perfect lineups. |
| Moved player since dropped | Moves render from ESPN's transaction names regardless of current roster. |

## Testing

1. `tests/test_team_profile.py` (new, added to `.github/workflows/checks.yml`), with small fixtures:
   Lineup IQ percentage, worst call and band edges, perfect-lineup case; Position strength ranking,
   tie-break stability and `weak_spot`; Projection vs reality 2-start minimum and sign; Moves
   filtering, trade direction, dedupe, sort and week tags; key stability (same input → same key,
   changed relevant input → changed key); negative D/ST ids.
2. `tests/test_coach_written.py` (extend): audit copy applies on key match, ignored on mismatch;
   audit copy survives a >36h snapshot while coach cards don't; `_MOVING_NUMBER` rejects audit
   copy; `pos` tag only on a `weak_spot` match; missing `pos` is harmless.
3. `scripts/check.py` (extend): every team in the built payload has `profile`, and every audit card
   has non-empty `key`, `stat`, `title`, `text`.
4. Manual: `scripts/deploy.sh --preview`; check `#team-<id>` for two teams at phone width, and that
   `#coach-3` / `#coach-next-3` land correctly. Then `code-reviewer` on the diff and `voice-check`
   on every new computed fallback string and empty state.

## Docs to update

- `docs/architecture.md`: the Coach page section describes the profile as its home; add the audit
  and moves.
- `CLAUDE.md` Layout: mention `site/team_profile.py`, and the new `latest.json` fields.

## Out of scope

Luck check; charts or sparklines of weekly scores; head-to-head history; any change to
`api/live.py` or the captures.
