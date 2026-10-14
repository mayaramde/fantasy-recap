/* The Live scoreboard's logic, kept apart from its markup so it can be tested with
   `node --test tests/live/*.test.js`. A game is {key, winner, loser}: the payload names the sides by who
   leads, which swaps them whenever the lead flips, so everything here puts them back in a fixed order
   (the picked team on the left, else the lower team id) before anything is drawn. */

// Left, right: yours on the left when `me` is in the game, otherwise the lower team id.
function liveSides(g, me) {
  const two = [g.winner, g.loser].sort((a, b) => a.team_id - b.team_id);
  return me != null && two[1].team_id === me ? [two[1], two[0]] : two;
}

// The chance the left side wins, from ESPN's win_probability: its own number, else the right side's flipped.
function liveChance(left, right) {
  if (typeof left.win_probability === 'number') return left.win_probability;
  if (typeof right.win_probability === 'number') return 1 - right.win_probability;
  return null;
}

const liveGap = (g) => Math.abs(g.winner.points - g.loser.points);

// Closest game first: win chance nearest 50%, or the points gap when any game has no win chance
// (one rule for the whole list, so the two measures are never compared with each other).
function liveClosest(games) {
  const chance = games.map((g) => { const [l, r] = liveSides(g); return liveChance(l, r); });
  const useChance = chance.every((c) => c != null);
  const keyed = games.map((g, i) => ({ g, k: useChance ? Math.abs(chance[i] - 0.5) : liveGap(g) }));
  return keyed.sort((a, b) => a.k - b.k || liveGap(a.g) - liveGap(b.g) || (a.g.key < b.g.key ? -1 : 1)).map((x) => x.g);
}

// The hero: the picked team's game, else the closest one.
function liveHero(games, me) {
  const mine = me != null ? games.find((g) => g.winner.team_id === me || g.loser.team_id === me) : null;
  if (mine) return { game: mine, picked: true };
  return { game: games.length ? liveClosest(games)[0] : null, picked: false };
}

// The sticker on a game. `chance` is the left side's; the favorite is whoever it favors.
function liveVerdict(chance) {
  if (typeof chance !== 'number') return null;
  const top = Math.max(chance, 1 - chance);
  const [label, tone] = top >= 0.85 ? ['Nearly locked', 'lime'] : top >= 0.65 ? ['Leaning', 'cobalt'] : ['Coin flip', 'pink'];
  return { label, tone, percent: Math.round(top * 100), favorite: chance >= 0.5 ? 'left' : 'right' };
}

// What is still to come for a side: ESPN's projection for the starters yet to play (analyze.py's
// remaining_projection), never below zero. Null when the payload doesn't carry it.
const liveRemaining = (s) => (typeof s.remaining_projection === 'number' ? Math.max(s.remaining_projection, 0) : null);

// Who leads a game right now, as a team id; null for a tie.
const liveLeader = (g) => (g.winner.points === g.loser.points ? null : g.winner.points > g.loser.points ? g.winner.team_id : g.loser.team_id);

// Movement between two refreshes. `prev` is what this returned last time (null before the first
// refresh, which therefore reports nothing). delta: team id -> points gained, when it is 0.01 or more.
// flip: keys of games whose leader changed. The last real leader is carried through a tie so
// A, tie, B still counts as a flip.
function liveMovement(prev, games) {
  const pts = new Map(), lead = new Map(), delta = new Map(), flip = new Set();
  for (const g of games) {
    for (const s of [g.winner, g.loser]) {
      pts.set(s.team_id, s.points);
      const was = prev && prev.pts.get(s.team_id);
      if (typeof was === 'number' && s.points - was >= 0.01 - 1e-9) delta.set(s.team_id, Math.round((s.points - was) * 100) / 100);
    }
    const now = liveLeader(g), before = prev ? prev.lead.get(g.key) : null;
    if (before != null && now != null && now !== before) flip.add(g.key);
    lead.set(g.key, now ?? before ?? null);
  }
  return { pts, lead, delta, flip };
}

// The earliest kickoff still ahead among starters not on the field, as an ISO string (null if none).
function liveNextKickoff(starters, now) {
  const ahead = starters.filter((p) => !p.playing && p.kickoff && Date.parse(p.kickoff) > now).map((p) => p.kickoff);
  return ahead.length ? ahead.reduce((a, b) => (Date.parse(a) <= Date.parse(b) ? a : b)) : null;
}

// A capture is stale when the live API is on and it is more than five minutes old.
const LIVE_STALE_MS = 5 * 60 * 1000;
const liveStale = (capturedAt, now, apiOn) => !!apiOn && !!capturedAt && now - Date.parse(capturedAt) > LIVE_STALE_MS;

if (typeof module !== 'undefined') module.exports = { liveSides, liveChance, liveGap, liveClosest, liveHero, liveVerdict, liveRemaining, liveLeader, liveMovement, liveNextKickoff, liveStale };
