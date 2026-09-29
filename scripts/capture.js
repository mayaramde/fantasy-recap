// ESPN weekly capture. Runs inside Chrome (Claude in Chrome javascript_tool) on a tab
// already at https://lm-api-reads.fantasy.espn.com/..., so the request uses Maya's
// ESPN session. No cookies or credentials are read, copied or returned.
//
// Usage (scripts/receive.py must be running; it serves this file and saves results):
//   eval(await fetch('http://127.0.0.1:8765/capture.js').then(r => r.text()));
//   await fantasyCapture([3]);          // one or more weeks, or 'current'
// Each week is trimmed (no member names, ESPN IDs or settings) and POSTed to the
// receiver, which writes data/<season>/week-NN/espn.json verbatim.
// One request goes to ESPN's public NFL scoreboard (no session, no cookies) for the
// state of each NFL game, so the live box score can say who is on the field right now.
// Note: `teams` records are season-to-date as of capture time; per-week
// standings are rebuilt from matchup results in site/build.py.

// weeks: an array of week numbers, or 'current' for ESPN's current matchup week
window.fantasyCapture = async (weeks) => {
if (weeks === 'current') {
  const st = await fetch('https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/698468554?view=mStatus',
    { credentials: 'include' }).then((r) => r.json());
  weeks = [st.status.currentMatchupPeriod];
}
const out = [];
for (const WEEK of weeks) out.push(await captureWeek(WEEK));
return out;
};

async function captureWeek(WEEK) {
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
        games[Number(c.id)] = { state, clock };
      }
    }
    return games;
  } catch (e) {
    console.warn('no NFL game states this capture:', e.message);
    return {};
  }
};

const [box, teamsRes, statusRes, txRes, games] = await Promise.all([
  get(`view=mBoxscore&view=mMatchupScore&scoringPeriodId=${WEEK}`),
  get('view=mTeam'),
  get('view=mStatus'),
  get(`view=mTransactions2&scoringPeriodId=${WEEK}`),
  proGames(WEEK),
]);

const names = {};
const pickStat = (stats, source) =>
  (stats || []).find((s) => s.statSourceId === source && s.scoringPeriodId === WEEK && s.statSplitTypeId === 1);

const side = (s) => {
  if (!s) return null;
  const lineup = (s.rosterForCurrentScoringPeriod?.entries || []).map((e) => {
    const p = e.playerPoolEntry.player;
    names[p.id] = p.fullName;
    const g = games[p.proTeamId] || null;
    return {
      player_id: p.id,
      name: p.fullName,
      pos: POS[p.defaultPositionId] || String(p.defaultPositionId),
      pro_team_id: p.proTeamId,
      slot: SLOT[e.lineupSlotId] || String(e.lineupSlotId),
      // ESPN's designation for the week: QUESTIONABLE, DOUBTFUL, OUT, INJURY_RESERVE,
      // SUSPENSION, ACTIVE... Absent for a D/ST and for anyone ESPN isn't listing.
      injury_status: p.injuryStatus ?? null,
      points: round2(pickStat(p.stats, 0)?.appliedTotal ?? 0),
      projected: round2(pickStat(p.stats, 1)?.appliedTotal ?? null),
      played: !!pickStat(p.stats, 0),
      // His NFL game: 'pre', 'in' or 'post', and the game clock while it's 'in'
      game_state: g ? g.state : null,
      game_clock: g ? g.clock : null,
    };
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
