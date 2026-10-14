const test = require('node:test');
const assert = require('node:assert/strict');
const L = require('../../site/live/live.js');

const side = (id, points, extra = {}) => ({ team_id: id, manager: `M${id}`, points, ...extra });
// The payload names sides by who leads, so winner/loser flips with the score.
const game = (a, b, key = `${Math.min(a.team_id, b.team_id)}-${Math.max(a.team_id, b.team_id)}`) =>
  (a.points >= b.points ? { key, winner: a, loser: b } : { key, winner: b, loser: a });

test('sides are fixed: lower id left, picked team left, whoever leads', () => {
  const g1 = game(side(2, 90), side(5, 80)), g2 = game(side(2, 80), side(5, 90));
  for (const g of [g1, g2]) assert.deepEqual(L.liveSides(g).map((s) => s.team_id), [2, 5]);
  for (const g of [g1, g2]) assert.deepEqual(L.liveSides(g, 5).map((s) => s.team_id), [5, 2]);
  assert.deepEqual(L.liveSides(g1, 3).map((s) => s.team_id), [2, 5]);
});

test('verdict thresholds sit at 0.65 and 0.85 on the favorite, either side', () => {
  const v = (p) => L.liveVerdict(p);
  assert.equal(v(0.5).label, 'Coin flip');
  assert.equal(v(0.649).label, 'Coin flip');
  assert.equal(v(0.65).label, 'Leaning');
  assert.equal(v(0.35).label, 'Leaning');
  assert.equal(v(0.849).label, 'Leaning');
  assert.equal(v(0.85).label, 'Nearly locked');
  assert.equal(v(0.1).label, 'Nearly locked');
  assert.equal(v(0.93).percent, 93);
  assert.equal(v(0.1).percent, 90);
  assert.equal(v(0.1).favorite, 'right');
  assert.equal(v(0.7).favorite, 'left');
  assert.equal(v(null), null);
});

test('chance falls back to the other side, then to nothing', () => {
  assert.equal(L.liveChance(side(1, 0, { win_probability: 0.4 }), side(2, 0)), 0.4);
  assert.ok(Math.abs(L.liveChance(side(1, 0), side(2, 0, { win_probability: 0.3 })) - 0.7) < 1e-9);
  assert.equal(L.liveChance(side(1, 0), side(2, 0)), null);
});

test('closest first by win chance, by points gap when any game has none', () => {
  const g = (a, b, p) => game(side(a, 50, { win_probability: p }), side(b, 40, { win_probability: p == null ? null : 1 - p }));
  const games = [g(1, 2, 0.93), g(3, 4, 0.52), g(5, 6, 0.30)];
  assert.deepEqual(L.liveClosest(games).map((x) => x.key), ['3-4', '5-6', '1-2']);
  const mixed = [game(side(1, 80, { win_probability: 0.5 }), side(2, 20)), game(side(3, 51), side(4, 50))];
  assert.deepEqual(L.liveClosest(mixed).map((x) => x.key), ['3-4', '1-2']);
});

test('hero is the picked team\'s game, else the closest one', () => {
  const games = [game(side(1, 90, { win_probability: 0.9 }), side(2, 60)), game(side(3, 70, { win_probability: 0.51 }), side(4, 69))];
  assert.deepEqual([L.liveHero(games, 2).game.key, L.liveHero(games, 2).picked], ['1-2', true]);
  assert.deepEqual([L.liveHero(games, null).game.key, L.liveHero(games, null).picked], ['3-4', false]);
  assert.equal(L.liveHero(games, 8).picked, false);
  assert.equal(L.liveHero([], 1).game, null);
});

test('remaining is never negative and null when the payload lacks it', () => {
  assert.equal(L.liveRemaining(side(1, 10, { remaining_projection: 34.2 })), 34.2);
  assert.equal(L.liveRemaining(side(1, 10, { remaining_projection: -3 })), 0);
  assert.equal(L.liveRemaining(side(1, 10)), null);
});

test('movement: nothing on the first refresh, a tag for a rise of 0.01 or more, then it clears', () => {
  const g = (a, b) => [game(side(1, a), side(2, b))];
  const first = L.liveMovement(null, g(80, 70));
  assert.equal(first.delta.size, 0);
  assert.equal(first.flip.size, 0);
  const second = L.liveMovement(first, g(86.4, 70));
  assert.deepEqual([...second.delta], [[1, 6.4]]);
  const third = L.liveMovement(second, g(86.4, 70));
  assert.equal(third.delta.size, 0);
  const tiny = L.liveMovement(third, g(86.405, 70.004));
  assert.equal(tiny.delta.size, 0);
  const cent = L.liveMovement(third, g(86.41, 70));
  assert.deepEqual([...cent.delta], [[1, 0.01]]);
  const drop = L.liveMovement(third, g(85, 70));
  assert.equal(drop.delta.size, 0);
});

test('movement: a flip is reported for one refresh, also through a tie', () => {
  const g = (a, b) => [game(side(1, a), side(2, b))];
  const s1 = L.liveMovement(null, g(80, 90));
  const s2 = L.liveMovement(s1, g(95, 90));
  assert.deepEqual([...s2.flip], ['1-2']);
  const s3 = L.liveMovement(s2, g(96, 90));
  assert.equal(s3.flip.size, 0);
  const tie = L.liveMovement(s3, g(90, 90));
  assert.equal(tie.flip.size, 0);
  const back = L.liveMovement(tie, g(90, 91));
  assert.deepEqual([...back.flip], ['1-2']);
});

test('next kickoff is the earliest one still ahead among starters not on the field', () => {
  const now = Date.parse('2026-10-18T16:00:00Z');
  const ps = [
    { kickoff: '2026-10-18T17:00:00Z' }, { kickoff: '2026-10-18T20:25:00Z' },
    { kickoff: '2026-10-18T13:00:00Z' }, { kickoff: '2026-10-18T15:59:00Z', playing: 'Q4 1:00' }, { kickoff: null },
  ];
  assert.equal(L.liveNextKickoff(ps, now), '2026-10-18T17:00:00Z');
  assert.equal(L.liveNextKickoff([{ kickoff: '2026-10-18T13:00:00Z' }], now), null);
  assert.equal(L.liveNextKickoff([], now), null);
});

test('stale means API on and more than five minutes old', () => {
  const now = Date.parse('2026-10-18T16:00:00Z');
  assert.equal(L.liveStale('2026-10-18T15:54:00Z', now, '/api/live'), true);
  assert.equal(L.liveStale('2026-10-18T15:56:00Z', now, '/api/live'), false);
  assert.equal(L.liveStale('2026-10-18T15:00:00Z', now, undefined), false);
});
