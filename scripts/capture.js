// ESPN weekly capture. Runs inside Chrome (Claude in Chrome javascript_tool) on a tab
// already at https://lm-api-reads.fantasy.espn.com/..., so the request uses Maya's
// ESPN session. No cookies or credentials are read, copied or returned.
//
// Usage (scripts/receive.py must be running; it serves this file and saves results):
//   eval(await fetch('http://127.0.0.1:8765/capture.js').then(r => r.text()));
//   await fantasyCapture([3]);          // one or more weeks, or 'current'
//   await fantasyCapture('next');       // the week after this one, for the Coach page
// Each week is trimmed (no member names, ESPN IDs or settings) and POSTed to the
// receiver, which writes data/<season>/week-NN/espn.json verbatim. 'next' writes
// data/<season>/next-week/espn.json instead: same shape, but a week nobody has played
// yet, so every point is 0 and the numbers that matter are ESPN's projections.
// One request goes to ESPN's public NFL scoreboard (no session, no cookies) for the
// state of each NFL game, so the live box score can say who is on the field right now.
// Note: `teams` records are season-to-date as of capture time; per-week
// standings are rebuilt from matchup results in site/build.py.

// weeks: an array of week numbers, 'current' for ESPN's current matchup week, or
// 'next' for the week after it (a preview: rosters and projections, no scores).
window.fantasyCapture = async (weeks) => {
if (weeks === 'current' || weeks === 'next') {
  const { get } = espnHelpers();
  const week = (await get('view=mStatus')).status.currentMatchupPeriod;
  if (weeks === 'next') {
    if (week >= 18) throw new Error(`no week after ${week}`);
    return [await captureNextWeek(week + 1)];
  }
  weeks = [week];
}
const out = [];
for (const WEEK of weeks) out.push(await captureWeek(WEEK));
return out;
};

// Everything both captures share. A function declaration, not top-level consts, so the
// script can be eval'd twice in the same tab without "already declared".
function espnHelpers() {
const SEASON = 2026;
const LEAGUE_ID = 698468554;
const BASE = `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${SEASON}/segments/0/leagues/${LEAGUE_ID}`;

const SLOT = { 0: 'QB', 2: 'RB', 4: 'WR', 6: 'TE', 16: 'DST', 17: 'K', 20: 'BENCH', 21: 'IR', 23: 'FLEX' };
const POS = { 1: 'QB', 2: 'RB', 3: 'WR', 4: 'TE', 5: 'K', 16: 'DST' };
const round2 = (x) => (x == null ? null : Math.round(x * 100) / 100);

const get = (qs) =>
  fetch(`${BASE}?${qs}`, { credentials: 'include' }).then((r) => {
    if (!r.ok) throw new Error(`ESPN ${r.status} for ${qs}`);
    return r.json();
  });

// ESPN files a player's weekly numbers as stat rows: source 0 is what he actually
// scored, source 1 is the projection, and for a week nobody has played only source 1
// exists. Split type 1 is the weekly total.
const pickStat = (stats, source, week) =>
  (stats || []).find((s) => s.statSourceId === source && s.scoringPeriodId === week && s.statSplitTypeId === 1);

// Stats that earn no points in this league but explain the ones that did (attempts,
// targets, a kicker's chances, what a defense gave up). Kept even at zero points so a
// line like "8 catches on 11 targets" can be shown; everything else rides along only
// when it moved the score.
const CONTEXT_STATS = new Set([0, 1, 23, 58, 64, 84, 87, 120, 127]);

// How one player's week broke down: ESPN's own appliedStats (its points for each stat,
// under this league's scoring) paired with the raw stat behind them. Stat ids are ESPN's;
// the site names the ones it knows and reports the rest as "other scoring", so the rows
// always add up to his total. Empty when ESPN has no stat line for him yet.
const scoringLines = (stat) => {
  if (!stat) return [];
  const applied = stat.appliedStats || {};
  const raw = stat.stats || {};
  const ids = new Set([...Object.keys(applied), ...Object.keys(raw).filter((k) => CONTEXT_STATS.has(Number(k)))]);
  const lines = [];
  for (const k of ids) {
    const points = round2(applied[k] ?? 0);
    const value = round2(raw[k] ?? null);
    if (!points && !value) continue;
    lines.push({ stat: Number(k), value, points });
  }
  // Biggest mover first, ties by stat id, so both captures order a week the same way.
  lines.sort((a, b) => Math.abs(b.points) - Math.abs(a.points) || a.stat - b.stat);
  return lines;
};

// One roster row, trimmed the same way for a finished week and a preview.
const trimPlayer = (e, week, games) => {
  const p = e.playerPoolEntry.player;
  const g = games[p.proTeamId] || null;
  const actual = pickStat(p.stats, 0, week);
  return {
    player_id: p.id,
    name: p.fullName,
    pos: POS[p.defaultPositionId] || String(p.defaultPositionId),
    pro_team_id: p.proTeamId,
    slot: SLOT[e.lineupSlotId] || String(e.lineupSlotId),
    // ESPN's designation for the week: QUESTIONABLE, DOUBTFUL, OUT, INJURY_RESERVE,
    // SUSPENSION, ACTIVE... Absent for a D/ST and for anyone ESPN isn't listing.
    injury_status: p.injuryStatus ?? null,
    points: round2(actual?.appliedTotal ?? 0),
    projected: round2(pickStat(p.stats, 1, week)?.appliedTotal ?? null),
    played: !!actual,
    // What those points were made of: yards, catches, touchdowns, a missed kick. Empty
    // for a week nobody has played, which has no stat line to break down.
    scoring: scoringLines(actual),
    // His NFL game: 'pre', 'in' or 'post', and the game clock while it's 'in'
    game_state: g ? g.state : null,
    game_clock: g ? g.clock : null,
    // When his NFL game kicks off (ISO, UTC), for the lineup's "Sun 1:00 PM" line
    kickoff: g ? g.kickoff : null,
  };
};

// Which of this week's NFL games are on right now, by ESPN pro team id (the same ids the
// fantasy API uses for proTeamId), so a live box score can mark the players still on the
// field. Public scoreboard: no cookies, no credentials. Best effort — on any failure the
// players simply carry no game state and the site shows no marker.
const proGames = async (week) => {
  try {
    const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard` +
      `?dates=${SEASON}&seasontype=2&week=${week}`);
    if (!r.ok) throw new Error(`scoreboard ${r.status}`);
    const games = {};
    for (const ev of (await r.json()).events || []) {
      const st = ev.status || {};
      const state = st.type?.state || null; // 'pre' before kickoff, 'in' while playing, 'post' once final
      if (!state) continue;
      let clock = null;
      if (state === 'in') {
        clock = st.type?.name === 'STATUS_HALFTIME'
          ? 'Halftime'
          : [st.period ? (st.period > 4 ? 'OT' : `Q${st.period}`) : null, st.displayClock]
            .filter(Boolean).join(' ') || st.type?.shortDetail || null;
      }
      for (const c of ev.competitions?.[0]?.competitors || []) {
        games[Number(c.id)] = { state, clock, kickoff: ev.date || null };
      }
    }
    return games;
  } catch (e) {
    console.warn('no NFL game states this capture:', e.message);
    return {};
  }
};

return { SEASON, SLOT, POS, round2, get, pickStat, trimPlayer, proGames };
}

// One played (or in-progress) week: scores, rosters and the week's transactions.
async function captureWeek(WEEK) {
const { SEASON, SLOT, round2, get, pickStat, trimPlayer, proGames } = espnHelpers();

const [box, teamsRes, statusRes, txRes, games] = await Promise.all([
  get(`view=mBoxscore&view=mMatchupScore&scoringPeriodId=${WEEK}`),
  get('view=mTeam'),
  get('view=mStatus'),
  get(`view=mTransactions2&scoringPeriodId=${WEEK}`),
  proGames(WEEK),
]);

const names = {};

const side = (s) => {
  if (!s) return null;
  const lineup = (s.rosterForCurrentScoringPeriod?.entries || []).map((e) => {
    names[e.playerPoolEntry.player.id] = e.playerPoolEntry.player.fullName;
    return trimPlayer(e, WEEK, games);
  });
  return {
    team_id: s.teamId,
    points: round2(s.totalPointsLive ?? s.totalPoints),
    projected: round2(s.totalProjectedPointsLive ?? s.totalProjectedPoints ?? null),
    win_probability: s.winProbability ?? null,
    lineup,
  };
};

const matchups = box.schedule
  .filter((m) => m.matchupPeriodId === WEEK)
  .map((m) => ({ id: m.id, winner: m.winner, home: side(m.home), away: side(m.away) }));

// Player names for transacted players not on a current lineup (e.g., dropped players)
const txs = (txRes.transactions || []).filter((t) => t.status === 'EXECUTED');
const missing = [...new Set(txs.flatMap((t) => (t.items || []).map((i) => i.playerId)))].filter(
  (id) => !names[id]
);
if (missing.length) {
  // Global player list, filtered to the IDs we need (negative IDs are D/ST)
  const r = await fetch(
    `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${SEASON}/players?scoringPeriodId=0&view=players_wl`,
    { credentials: 'include', headers: { 'x-fantasy-filter': JSON.stringify({ filterIds: { value: missing } }) } }
  ).then((r) => r.json());
  for (const pl of r || []) names[pl.id] = pl.fullName;
}
const nameOf = (id) => names[id] || (id < 0 ? `DST ${-id}` : `Player ${id}`);

const transactions = txs
  .map((t) => ({
    type: t.type, // FREEAGENT, WAIVER, ROSTER (lineup moves), TRADE_ACCEPT, ...
    team_id: t.teamId,
    date: new Date(t.processDate || t.proposedDate).toISOString(),
    bid: t.bidAmount || 0,
    items: (t.items || []).map((i) => ({
      type: i.type, // ADD, DROP, LINEUP, TRADE
      player_id: i.playerId,
      name: nameOf(i.playerId),
      from_team_id: i.fromTeamId,
      to_team_id: i.toTeamId,
      from_slot: SLOT[i.fromLineupSlotId] ?? null,
      to_slot: SLOT[i.toLineupSlotId] ?? null,
    })),
  }))
  .sort((a, b) => a.date.localeCompare(b.date));

const teams = (teamsRes.teams || []).map((t) => ({
  team_id: t.id,
  wins: t.record?.overall?.wins ?? 0,
  losses: t.record?.overall?.losses ?? 0,
  ties: t.record?.overall?.ties ?? 0,
  points_for: round2(t.record?.overall?.pointsFor ?? 0),
  points_against: round2(t.record?.overall?.pointsAgainst ?? 0),
  waiver_rank: t.waiverRank ?? null,
}));

const capture = {
  season: SEASON,
  week: WEEK,
  captured_at: new Date().toISOString(),
  espn_status: {
    current_matchup_period: statusRes.status?.currentMatchupPeriod,
    latest_scoring_period: statusRes.status?.latestScoringPeriod,
  },
  complete: matchups.every((m) => m.winner && m.winner !== 'UNDECIDED'),
  matchups,
  teams,
  transactions,
};

// Hand off to scripts/receive.py (must be running) so the file is written verbatim.
const res = await fetch(`http://127.0.0.1:8765/save?week=${WEEK}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(capture),
});
return {
  week: WEEK,
  receiver: await res.json(),
  complete: capture.complete,
  scores: matchups.map((m) => `${m.away.team_id} ${m.away.points} @ ${m.home.team_id} ${m.home.points} (${m.winner})`),
  transactions: transactions.length,
  playing: Object.values(games).filter((g) => g.state === 'in').length,
  unnamed: transactions.flatMap((t) => t.items).filter((i) => /^(Player|DST) -?\d+$/.test(i.name)).length,
};
}

// The week after this one: the same trimmed shape, for the Coach page's "next week" tab.
//
// Nobody has played it, so there are no scores and no transactions to read — what matters
// is who each team would start, what ESPN projects them for, who is hurt, and whose NFL
// team is on a bye. Rosters come from view=mRoster at that scoring period rather than
// mBoxscore, which only carries a lineup for a week that has started; the pairings come
// from the season schedule, which is already there for every week.
//
// Saved to data/<season>/next-week/espn.json, deliberately not as a week of its own:
// a file under week-NN/ would look to the site like a week in progress and take the Live
// page over from the real one.
async function captureNextWeek(WEEK) {
const { SEASON, SLOT, round2, get, trimPlayer, proGames } = espnHelpers();

const [sched, rosterRes, teamsRes, statusRes, games] = await Promise.all([
  get(`view=mMatchupScore&scoringPeriodId=${WEEK}`),
  get(`view=mRoster&scoringPeriodId=${WEEK}`),
  get('view=mTeam'),
  get('view=mStatus'),
  proGames(WEEK),
]);

const rosters = {};
for (const t of rosterRes.teams || []) {
  rosters[t.id] = (t.roster?.entries || []).map((e) => trimPlayer(e, WEEK, games));
}

// A side of a matchup nobody has played: no score, no win probability, and a projected
// total built from the starters ESPN has in the lineup right now.
const side = (teamId) => {
  const lineup = rosters[teamId] || [];
  const starting = lineup.filter((p) => p.slot !== 'BENCH' && p.slot !== 'IR');
  return {
    team_id: teamId,
    points: 0,
    projected: round2(starting.reduce((n, p) => n + (p.projected || 0), 0)),
    win_probability: null,
    lineup,
  };
};

const matchups = (sched.schedule || [])
  .filter((m) => m.matchupPeriodId === WEEK)
  .map((m) => ({ id: m.id, winner: 'UNDECIDED', home: side(m.home?.teamId), away: side(m.away?.teamId) }));

const teams = (teamsRes.teams || []).map((t) => ({
  team_id: t.id,
  wins: t.record?.overall?.wins ?? 0,
  losses: t.record?.overall?.losses ?? 0,
  ties: t.record?.overall?.ties ?? 0,
  points_for: round2(t.record?.overall?.pointsFor ?? 0),
  points_against: round2(t.record?.overall?.pointsAgainst ?? 0),
  waiver_rank: t.waiverRank ?? null,
}));

const capture = {
  season: SEASON,
  week: WEEK,
  captured_at: new Date().toISOString(),
  espn_status: {
    current_matchup_period: statusRes.status?.currentMatchupPeriod,
    latest_scoring_period: statusRes.status?.latestScoringPeriod,
  },
  complete: false,
  matchups,
  teams,
  transactions: [],
};

const res = await fetch(`http://127.0.0.1:8765/save?week=${WEEK}&next=1`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(capture),
});
const rostered = matchups.flatMap((m) => [m.home, m.away]).flatMap((s) => s.lineup);
return {
  week: WEEK,
  next_week: true,
  receiver: await res.json(),
  matchups: matchups.length,
  players: rostered.length,
  // If ESPN has no projections this far out the Coach page says so rather than
  // pretending everyone is projected zero, so it's worth seeing in the capture result.
  projected: rostered.filter((p) => p.projected != null).length,
  on_bye: rostered.filter((p) => !games[p.pro_team_id]).length,
};
}
