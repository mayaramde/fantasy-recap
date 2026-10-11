---
name: coach-daily
description: Writes the day's Coach cards for all 8 rosters, voice-checked: this week's advice for every computed card on the Coach page (swaps, injuries, byes, empty slots) plus FantasyPros-sourced start/sit and waiver ideas, trades evaluated for both teams by scripts/trade_eval.py, and injury/news deltas, and writes data/<season>/fantasypros/latest.json, then opens its own auto-merging PR. Invoked by fantasy-orchestrator for "run/update/refresh coach cards", "waiver ideas", "trade ideas", "what changed in the injury report". Independent of recap production — never touches a recap or any data/<season>/week-NN/ file.
model: inherit
---

# Coach daily

This is content authoring, not just data capture: you write the finished,
voiced card text yourself, the same way recap-write writes game_balls/
flags/tough_breaks. `site/build.py` never invents copy — it only decides
which of your cards to show and when. Data only otherwise: this skill
never deploys, never touches a recap, and never touches any
`data/<season>/week-NN/` file; the next live-update run picks up whatever
this merges.

## Step 1: work in your own worktree, never the project checkout

In GitHub Actions (fantasy-orchestrator's "GitHub Actions mode"), nothing else shares the
checkout and the workflow has already captured and analyzed both weeks. Skip this step and
work in the checkout on a new `coach-daily-<date>` branch. Step 2's open-PR snapshot is the
file the prompt names (no `gh`). Step 7 stops after item 2: the workflow pushes, opens the PR
with auto-merge, and closes superseded ones. With no FantasyPros MCP configured, Step 4 has no
data: write Step 5b's copy and the season audit, leave `advice_cards` and `roster_ideas` empty,
and skip Step 5a (`trade_eval.py` needs FantasyPros' rest-of-season projections).

Other sessions (the weekly recap, an interactive one) switch branches in the project's own
checkout while this runs — working there would pull the rug out from under them.

```
git fetch origin
git worktree add -B coach-daily-<YYYY-MM-DD> /tmp/fantasy-coach-daily-<YYYY-MM-DD> origin/main
```

(If that path or branch already exists from an earlier run today, remove it first:
`git worktree remove --force` / `git branch -D`.) Every edit, build, check, and commit below
happens in the worktree — don't `git checkout` anything in the project folder itself.

The live week's `data/2026/week-NN/` and `data/2026/next-week/` may be uncommitted, so they can
exist only in the project folder's working tree. Copy them into the same paths inside the
worktree right away: Step 5b's brief and Step 7's build both read them from there.

## Step 2: read yesterday's snapshot

Read `data/2026/fantasypros/latest.json` from the worktree (`origin/main`) before touching
anything else — it's your only source for "what changed since yesterday." If yesterday's
coach-daily PR is still open (`gh pr list --state open --head coach-daily-`), its branch has a
newer snapshot than `main`; read that one instead. A missing snapshot is fine — say so in your
notes rather than inventing a comparison.

## Step 3: work out which week(s) to write cards for

The current live week (the highest week in `data/2026/week-NN/facts.json` whose
`recaps/2026/week-NN.json` has no *published* status yet), and, if `data/2026/next-week/espn.json`
exists and its `week` is exactly one more than the live week, that week too — a full week of
lead time is exactly when start/sit and waiver/trade ideas matter most, so don't skip it just
because the live week already got cards. If there's no live week, there are no week cards to write,
but the season audit (Step 5b) still gets written every run. If every week through 17 already has a
published recap, the season's over: stop and say so.

## Step 4: pull FantasyPros data (free tier only)

Use the `fantasy-data` role's free-tier calls, with `league.json`'s `fantasypros_league_key` on
every call (never hardcode it): `get_projections` (weekly, target week, PPR), `injury_status`
for rostered players and any candidate you're considering, `get_ecr` (ROS, PPR) for the
relevant positions, `get_player_ownership` (confirm a pickup is actually unowned in *this*
league), `get_leaders` (recent weeks, for real recent form over preseason rank), and
`get_roster(all_teams=true)` to see all 8 rosters at once. For trades (Step 5a), also
`get_projections(projection_type="ros")` for each of QB, RB, WR, TE, K and DST with a `limit` big
enough to cover every rostered player (200 does it): save the six responses, as returned, to one
JSON list in the worktree's scratch space (not the repo), e.g. `/tmp/fantasy-coach-daily-<date>-ros.json`.

If `waiver_finder`/`trade_finder`/`trade_analyzer` return `status: "premium_required"`, don't
retry them — building the idea yourself from the free tools above (and `scripts/trade_eval.py`
for trades) is the point of this skill.
- Waiver Finder's upsell has already been shown to Maya — don't repeat it.
- Trade Finder's disclosure **hasn't** been shown yet. If a call surfaces a
  `required_user_disclosure` for it, relay it once, in this run's final summary, and persist
  `trade_finder_disclosure_shown: true` in Step 6's file — check that flag before ever
  showing it again.

## Step 5: do the actual roster analysis

For each of the 8 teams (in `league.json` order): compare its position counts and bench depth
against the rest of the league (from `get_roster(all_teams=true)`); cross-reference ECR,
ownership, and recent performance for unowned adds tied to a *real* roster gap (a thin
position, an injured starter with no backup, an RB1 with no handcuff rostered); trades are
Step 5a's. This is judgment, not a formula: decide what's actually worth a manager's attention,
the way you would if she asked directly. An empty list for a team with no real gap is the right
answer, not a stretch to fill one in.

The brief (Step 5b) names each team's `weak_spot`: her lowest-ranked lineup group this season. When a
real waiver or trade option exists at that group, prefer it, and set `pos` (`QB`, `RB`, `WR`, `TE`,
`FLEX`, `DST` or `K`) on every waiver and trade card; the team profile puts a "fills your weak spot"
sticker on the ones that match. Never invent an option to fill a weak spot.

Write the cards in the site's voice (CLAUDE.md's Voice section: roast decisions, never people;
explain jargon in passing). Every card is `{kind, level, title, stat, text}`:

- `kind: "consensus"` — a start/sit suggestion from FantasyPros' own rankings/projections. You
  won't necessarily know what ESPN's own "swap" card (if any) says for that team, so don't claim
  agreement or disagreement with it — just state what FantasyPros' numbers say.
- `kind: "waiver"` — an unowned player (confirmed via `get_player_ownership`) worth a claim,
  tied to a real gap on that specific roster.
- `kind: "trade"` — an evaluated trade proposal from Step 5a, and only one that
  `scripts/trade_eval.py` passed. Never a trade idea without its `trade` block: the site drops
  those.
- `kind: "fp_news"` / `"fp_back"` — a real day-over-day change in a rostered player's
  FantasyPros injury/news status since yesterday's snapshot (mirror the "that's new since Week
  N" pattern `site/build.py`'s `team_advice` already uses for ESPN's own injury field, but
  sourced from FantasyPros, across the league — not just each team's own roster where ESPN's
  field already covers it).

Put `consensus`/`fp_news`/`fp_back` cards in `advice_cards`; put `waiver`/`trade` cards in
`roster_ideas`. **Every card whose text uses a FantasyPros number or claim must say so
explicitly** ("FantasyPros' expert consensus has...", "nobody in the league owns him, per
FantasyPros' ownership numbers") — never state a FantasyPros claim as if it were ESPN's, and
never invent an injury/news/ranking claim no tool actually returned. `level` is `"now"` only for
something worth acting on before this week's games lock; otherwise `"watch"` or `"info"`. A team
with nothing real to say gets an empty list for that section, not a filler card.

## Step 5a: find, evaluate and propose trades

The method is the trade-analyzer plugin's (`trade-finder`, `trade-evaluation`), adapted to a
page the whole league reads. `scripts/trade_eval.py` does the evaluating; you do the finding
and the writing. A trade card means "we scored this for both of you and it's good for both of
you", so nothing ships that the script didn't pass.

**Ground rules.** Every proposal follows all twelve. The script enforces the ones marked (s);
the rest are yours.

1. (s) **Both teams benefit.** Each side's best starting lineup gains at least about a point a
   week (blended, rule 3). A trade that only helps the proposer is not a proposal.
2. (s) **Not this week's opponents.** Partners she isn't playing this week rank first. A trade
   with this week's opponent counts as a rival trade (rule 4) and is flagged "you play her this week".
3. (s) **The next three to four weeks, not just this one.** Gains are scored week by week over
   the next four (byes at zero) and over the rest of the season, the near term counted double,
   the way a bubble team has to think. A deal that wins the season but loses the next four
   weeks fails.
4. (s) **Don't arm a rival.** A rival is this week's or next week's opponent, or a team as
   unsure of the playoffs as she is (both somewhere between 10% and 90%). A rival may not gain
   more from the deal, playoff plus title odds, than the proposer does.
5. (s) **The odds go up.** The proposer's playoff or title odds rise; the partner's fall in
   neither. Both rising ranks first.
6. (s) **Fair-looking, never a fleece.** The two sides' rest-of-season value lands within 15%
   of each other. The plugin's lowball "anchor" opener doesn't apply here: the partner reads the
   same card, and most of this league is in its first season.
7. (s, plus you) **No injury gambles.** Nobody OUT, on IR or suspended changes hands (the
   script). And no trade whose case rests on an injury or a return date unless FantasyPros'
   `injury_status` and ESPN's own designation agree (you).
8. (s) **Count the roster cost.** A startable bench player keeps about a quarter of his value
   as injury and bye cover, and a 2-for-1 that pushes a team over the roster limit costs her the
   player she'd have to cut.
9. (s, plus you) **Keep it simple.** 1-for-1 or 2-for-1 only (the script); at most one trade
   card per team per day, and at most one per pair of teams (you).
10. (s) **Respect the clock.** Nothing once ESPN's trade deadline has passed (`league.json`'s
    `trade_deadline`, Dec 2 at 9am Eastern this season) or the regular season is over. The site
    also hides every trade card from that moment, even one written that morning.
11. **Stale cards disappear.** `site/build.py` drops a trade card as soon as a player in it
    changes rosters or is ruled out, and this skill re-runs the whole evaluation every morning.
12. (you) **Honest about both sides.** Each card says what the partner gets out of it too. If
    she gains more per week than the proposer, say so; that's what a fair trade looks like.

**Finding.** Two sources, both scored the same way:

- `python3 scripts/trade_eval.py --ros <ros file> --scan` scores every 1-for-1 and 2-for-1 in
  the league and prints up to three passing trades per team, best first. Use `--sims 4000` (the
  default); `--byes '{"<abbr>": week}'` only if ESPN's scoreboard can't be reached.
- Your own ideas, from the plugin's finder logic: each team's surplus against its starting slots
  (weight running backs above receivers, since waivers refill receivers and not backs), and
  mispriced players from `get_leaders` and ECR (buy: a top-15 share of targets or carries with a
  points rank outside the top 30; sell: touchdowns running well ahead of the volume). Write them
  as `[{"team_id", "partner_id", "give": [ESPN ids], "get": [ESPN ids]}]` and run
  `trade_eval.py --ros <ros file> --proposals <file>`. `team_id` is the proposer.

Check the output's header before trusting a result that leans on it: `no_fantasypros_projection`
(players scored on ESPN's weekly number instead), `byes_known_for_weeks`, and
`opponents_known_for_weeks` (rules 2 and 4 can only see opponents for the weeks listed; with this
week or next missing, check ESPN's schedule yourself before shipping a trade between those two
teams). `scored_from_week` is one past `week` once this week's games have started.

**Choosing.** Of the passing trades (`"pass": true`), pick at most one per team (rule 9),
preferring ones that fill her `weak_spot`, never a pair twice, and never one you couldn't
explain to her in two sentences. If a trade passes for both teams as proposer, it may go on
both pages, each from her own side. None passing is a normal day: no trade card.

**Writing the card.** `kind: "trade"`, `pos` (the position she receives), `level: "watch"`
(`"info"` when it's a rival trade), and a `trade` block copied from the script's result
without changing a number: `partner_id`, `give` and `get` (each `{id, name, pos}`), `you` and
`them` (each `{near, playoff, title}`), `week` and `flags`. The page prints those numbers itself, so the
`title` and `text` carry none (no decimals, no `%`, same rule as Step 5b). The `title` is the
offer ("Offer DeVonta Smith to Amie for D'Andre Swift"). The `text` leads with why it works for
both rosters in plain words, gives the one-line pitch she could send ("you're deep at running
back and thin at receiver"), and names a fallback version if there's a sensible one. Then one
line of personality, at most, aimed at the rosters, the projections or the fantasy gods, never
at either manager: the partner reads this card too. No fleece words ("steal", "fleece", "buy low
from her", "sell her on"); they break rule 6's spirit in front of the person they describe. The
`stat` pill is short, number-free, and says something true of *this* trade that isn't true of
every one: "both odds go up" when both sides' playoff odds rise, "a straight 1-for-1" for a
1-for-1. Never "both lineups improve": every card clears that bar. Credit FantasyPros for its
projections.

## Step 5b: write this week's advice for the computed cards

The Coach page's own cards (bench swaps, a hurt or bye-week starter, an empty slot, a starter
projected zero, a game-time decision, injury-report changes, the opponent preview, "nothing to
fix") are worked out from ESPN's capture on every page load. Each one names its exact situation
with a `key`. Your job is the words: real advice for this week, in the site's voice, written
against those keys, so managers never read a fill-in-the-blank template.

1. In the worktree, run `python3 scripts/coach_brief.py`. For the live week (and next week,
   when its capture is current) it prints every team's `summary_key` plus each card's `key`,
   `kind`, `level`, `stat` and computed `title`/`text`. The computed text states the facts
   behind the card; it's your source, not your copy. It always prints a top-level `audit`
   block too (see **Season audit** below); that key is not a week. With no live week, `audit`
   is the only key, so skip items 2-3 and write the audit.
2. For **every** card under a week key in the brief, write a `title` and `text` under its exact `key`, and one
   `summary` line per team under its exact `summary_key`. That key lists the very cards the
   summary sums up, so it's safe to name those players; it stops showing once the list
   changes. Lead with the advice (what to do, and why, in plain words a first-season manager
   follows), then one line of personality. Use
   what the brief and Step 4's FantasyPros context actually say about that player this week,
   and credit FantasyPros for anything it sourced.
3. **No projections, point totals or percentages in the text.** No decimals and no `%`: those
   numbers move all day, so the site keeps them in the card's stat pill, which it recomputes
   live, and `site/build.py` rejects written copy that carries a decimal, a `%`, "percent" or a
   point count ("17 points", "a 12-point edge"). Say "a couple of points better", "the bigger
   projection", "a big fat zero" instead. Week numbers are fine.
4. Injury cards follow CLAUDE.md's serious-moments rule: plain and warm, no joke, and never a
   cause or timeline no source gave you.
5. Don't invent a card or a key. The site shows written copy only while its key is still
   computed, so copy for a situation that has since changed (a kickoff, a new injury) simply
   stops showing and the computed wording comes back. That's the intended backup, not an error.

**Season audit.** The brief's top-level `audit` block lists every team's three season-audit cards
(Lineup IQ, Position strength, Projection vs reality) with their `key`, `stat` and computed wording.
Write one `{title, text}` per key, dial "Coach cards": advice first, one line of personality. Roast the
lineup call, never the manager (the A–D band inside a Lineup IQ key is for invalidation only; never
mention a grade). Same number rule as above: no decimals or percentages, the stat pill carries the
numbers. The brief prints the audit even with no live week, so write it every run. Each key
already names everything the computed text does (the Lineup IQ key carries the worst call's week,
`:w3`; the Position key carries both ranks, `pos:RB1:WR8`), so your copy may name that week, those
players and those ranks, and it disappears on its own when any of them changes.

## Step 5c: voice gate

No card ships without `voice-check`'s sign-off, and that includes Step 5b's copy and the season-audit copy. Once Steps 5
and 5b are written, spawn the
`voice-check` agent (the `Agent` tool, `subagent_type: voice-check`) on them: write the cards to
a scratch file (or pass them in the prompt), keyed `<week>/<team_id>/<section>/<index>` so its
per-field table maps straight back to a card, and tell it the surface is **Coach cards**
(advice first, one line of personality). It judges `title` and `text` only; the numbers and
FantasyPros attributions are yours to keep exact, as in Step 5.

- **reads as intended** → on to Step 6.
- **reads flat** or **breaks a rule** → revise exactly the cards it flagged, using its rewrites
  as the starting point but keeping every number and every "per FantasyPros" attribution intact,
  then run it again on the revised cards only. **Two rounds at most.**
- Still flagged after the second round → drop those cards rather than ship them (an empty list
  is already the right answer for a team with nothing that reads well; a dropped Step 5b entry
  just leaves that card on its computed wording), and list what was
  dropped and why in the Output summary. Nobody reviews this PR, so this gate is the only one.

## Step 6: write the snapshot file

Overwrite the whole file (it's a rolling daily snapshot, not a per-week archive — git history
is the archive):

```json
{
  "generated_at": "<ISO-8601 UTC timestamp for right now>",
  "league_key": "<league.json's fantasypros_league_key>",
  "trade_finder_disclosure_shown": <yesterday's value, or true if you relayed it this run>,
  "weeks": {
    "<week number>": {
      "teams": {
        "<team_id>": {
          "advice_cards": [...], "roster_ideas": [...],
          "coach_cards": { "<key from the brief>": {"title": "...", "text": "..."} },
          "summary": {"key": "<summary_key from the brief>", "text": "..."}
        }
      }
    }
  },
  "audit": {
    "<team_id>": { "<audit key from the brief>": {"title": "...", "text": "..."} }
  }
}
```

One top-level entry under `weeks` for each week you wrote cards for (Step 3), each with one
team entry for every `team_id` in `league.json` (all 8), even when both lists are empty.
`coach_cards` and `summary` come from Step 5b; leave them out for a week the brief didn't cover.
`audit` (top level, one entry per team) also comes from Step 5b; waiver and trade cards in
`roster_ideas` carry `pos` (Step 5), and trade cards their `trade` block (Step 5a). A trade isn't
tied to one week, so put it in `roster_ideas` under every week you write.

## Step 7: build, check, commit, ship the PR

1. `python3 site/build.py` then `python3 scripts/check.py`. Fix anything either flags. Don't
   touch any recap file or any `data/2026/week-NN/` file.
2. Commit **only** `data/2026/fantasypros/latest.json` on the worktree's `coach-daily-<date>`
   branch. Never `git add -A`.
3. Push, open a PR against `main` (`gh pr create --title "Coach: daily FantasyPros cards
   (<date>)"`), and turn on auto-merge: `gh pr merge <number> --auto --squash --delete-branch`.
   No human review is needed — small, derived data whose copy already passed Step 5c. Never
   push to `main` directly and never merge with `--admin`.
4. Any older coach-daily PR still open is superseded (the file is a rolling snapshot; both PRs
   would overwrite it) — close it (`gh pr close <n> --delete-branch`) so it can't conflict with
   today's.
5. Confirm auto-merge is actually on (`gh pr view <n> --json autoMergeRequest`), then remove the
   worktree: `git worktree remove /tmp/fantasy-coach-daily-<date>`.
6. Don't deploy the website yourself — the next `live-update.yml` run picks up the merged
   snapshot the next time it builds.

## Output

A short summary: the PR link and whether auto-merge is on, which teams got a new waiver idea or
an evaluated trade today (and how many trades the scan passed league-wide), any FantasyPros injury/news changes worth knowing about, any card Step 5c dropped
for failing the voice gate twice, and — only the first time
it comes up — Trade Finder's premium disclosure.
