const test = require('node:test');
const assert = require('node:assert/strict');
const g = require('./fixture.js');
const { vitals } = require('../../site/coach/vitals.js');
const { buildFixes } = require('../../site/coach/fixes.js');
const { byeDamage, abbr } = require('../../site/coach/byeDamage.js');
const { battles } = require('../../site/coach/battles.js');
const { pickups } = require('../../site/coach/pickups.js');
const { strengthMap } = require('../../site/coach/strengthMap.js');
const { callouts } = require('../../site/coach/callouts.js');
const { tradeMatches, unavailableSpots } = require('../../site/coach/tradeMatches.js');
const { coachTake } = require('../../site/coach/take.js');
const { COACH_HEADLINES } = require('../../site/coach/headlines.js');
const { seasonAverage } = require('../../site/coach/seasonAverage.js');

const names = (xs) => xs.map((x) => x.manager);

test('vitals match the Week 6 snapshot', () => {
  const v = vitals(g.teams, { seasonAvg: g.seasonAvg });
  assert.equal(v.fixTeams, 7);
  assert.equal(v.total, 8);
  assert.equal(v.byeStarters, 9);
  assert.equal(v.byeTeams, 6);
  assert.equal(v.noStarterHurt, true);
  assert.equal(v.swapGain, 8.4);
  assert.equal(v.avgProjection, 113.1);
  assert.equal(v.seasonAvg, 129.1);
});

test('seasonAverage is the mean of every completed weekly score', () => {
  assert.equal(seasonAverage([{ weekly: [{ points: 100 }, { points: 120 }] }, { weekly: [{ points: 140 }] }]), 120);
  assert.equal(seasonAverage([{ weekly: [] }]), null);
});

test('fix board: swaps by gain, then empty slots, then byes, with every bye starter', () => {
  const { rows, clear } = buildFixes(g.teams);
  assert.deepEqual(rows.slice(0, 3).map((r) => [r.manager, r.kind, r.gain]), [['Samantha', 'swap', 3.7], ['Tara', 'swap', 2.5], ['Kyra', 'swap', 2.2]]);
  assert.deepEqual([rows[3].manager, rows[3].kind], ['Marlee', 'empty']);
  const byes = rows.slice(4);
  assert.equal(byes.length, 9);
  assert.ok(byes.every((r) => r.kind === 'bye'));
  assert.deepEqual(byes.map((r) => r.manager), ['Kyra', 'Kyra', 'Maya', 'Tara', 'Samantha', 'Samantha', 'Samantha', 'Maddie', 'Cambri']);
  assert.equal(byes.filter((r) => r.manager === 'Samantha').length, 3);
  assert.ok(byes.some((r) => r.text === 'Start Hubbard over Brown'));
  assert.deepEqual(clear, ['Amie']);
});

test('bye tiles and exposure bars', () => {
  const d = byeDamage(g.teams);
  assert.deepEqual(d.tiles.map((t) => [t.team, t.count]), [['CIN', 5], ['DET', 5], ['MIN', 4], ['MIA', 2]]);
  const ex = Object.fromEntries(d.exposure.map((e) => [e.manager, e]));
  assert.equal(ex.Samantha.label, '3 starters');
  assert.equal(ex.Cambri.label, '1 starter · 2 bench');
  assert.equal(ex.Marlee.label, '4 bench');
  assert.equal(ex.Amie.label, 'Clean');
  assert.deepEqual(names(d.exposure), ['Samantha', 'Kyra', 'Cambri', 'Tara', 'Maya', 'Maddie', 'Marlee', 'Amie']);
  assert.deepEqual(d.injured, []);
  assert.equal(abbr('Rome Odunze'), 'R. Odunze');
  assert.equal(abbr('CIN D/ST'), 'CIN D/ST');
});

test('where the week gets decided', () => {
  const b = battles(g.games);
  assert.deepEqual(b.edges.map((e) => [e.slot, e.winner, e.loser, Math.round(e.margin * 10) / 10]), [
    ['WR', 'Maddie', 'Samantha', 22.2], ['QB', 'Cambri', 'Kyra', 20.2], ['FLEX', 'Kyra', 'Cambri', 14.9],
    ['RB', 'Cambri', 'Kyra', 11.0], ['WR', 'Amie', 'Marlee', 9.9]]);
  assert.deepEqual([b.closest.a, b.closest.b, b.closest.gap], ['Tara', 'Maya', 4.6]);
  assert.deepEqual([b.biggest.a, b.biggest.b, b.biggest.gap], ['Maddie', 'Samantha', 35.1]);
});

test('pickups over the last seven days', () => {
  const p = pickups(g.wire);
  assert.deepEqual(p.rows.map((r) => [r.manager, r.count]).sort(), [['Amie', 1], ['Cambri', 3], ['Marlee', 2], ['Maya', 2], ['Samantha', 2]]);
  assert.equal(p.rows[0].manager, 'Cambri');
  assert.equal(p.total, 10);
  assert.equal(p.max, 3);
  assert.match(p.quip, /Cambri made 3 of the league's 10 pickups/);
});

test('pickups net out same-day add and drop, and ignore other event kinds', () => {
  const e = (kind, added, dropped) => ({ kind, manager: 'Maya', team_id: 2, date: '2026-10-10T12:00:00Z', added, dropped });
  const p = pickups([e('move', ['A', 'B'], ['A']), e('lineup', ['Z'], [])]);
  assert.deepEqual(p.rows, [{ manager: 'Maya', count: 1 }]);
  assert.equal(pickups([]).quip, '');
});

const sm = strengthMap(g.teams.map((t) => ({ id: t.id, manager: t.manager, ranks: t.ranks })));

test('strength map: per-team averages and best/weakest spot', () => {
  assert.deepEqual(sm.rows.map((r) => r.avg), [4.4, 4.3, 4.1, 4.6, 4.1, 4.3, 5.4, 4.7]);
  const kyra = sm.rows[0];
  assert.equal(kyra.best, 'RB');   // RB and FLEX tie at 1st: first occurrence wins
  assert.equal(kyra.weak, 'WR');   // WR and DST tie at 8th: first occurrence wins
});

test('strength map: league best and worst per spot', () => {
  const cols = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'DST', 'K'];
  assert.deepEqual(cols.map((c) => sm.bestBy[c]), ['Samantha', 'Kyra', 'Amie', 'Tara', 'Kyra', 'Samantha', 'Marlee']);
  assert.deepEqual(cols.map((c) => sm.worstBy[c]), ['Maddie', 'Samantha', 'Kyra', 'Maddie', 'Samantha', 'Kyra', 'Amie']);
});

test('callouts from the matrix', () => {
  const c = Object.fromEntries(callouts(sm.rows).map((x) => [x.kind, names(x.items)]));
  assert.deepEqual(c.split, ['Kyra', 'Samantha']);
  assert.deepEqual(c.basement, ['Kyra', 'Samantha', 'Maddie']);
  assert.deepEqual(c.lopsided, ['Amie']);
  // nobody qualifies: every callout is skipped
  assert.deepEqual(callouts([{ manager: 'A', ranks: { QB: 2, RB: 2 } }, { manager: 'B', ranks: { QB: 2, RB: 2 } }], 3, ['QB', 'RB']), []);
});

test('trade matchmaker: Samantha-Amie and Kyra-Tara lead, both perfect fits', () => {
  const m = tradeMatches(sm.rows, unavailableSpots(g.teams));
  assert.ok(m.length <= 3);
  assert.deepEqual(m.slice(0, 2).map((x) => [x.kind, [x.a.manager, x.b.manager].sort()]), [
    ['perfect', ['Amie', 'Samantha']], ['perfect', ['Kyra', 'Tara']]]);
  const used = m.flatMap((x) => [x.a.id, x.b.id]);
  assert.equal(new Set(used).size, used.length, 'each manager appears once');
  const sa = m[0];
  for (const side of [sa.a, sa.b]) {
    const other = side === sa.a ? sa.b : sa.a;
    assert.deepEqual(side.has.map((h) => h.spot), other.needs.map((n) => n.spot));
  }
});

test('trade matchmaker: a spot on bye or empty is never offered', () => {
  const m = tradeMatches(sm.rows).find((x) => [x.a.manager, x.b.manager].includes('Kyra'));
  const spot = m.a.manager === 'Kyra' ? m.a.has[0].spot : m.b.has[0].spot;
  const kyra = g.teams[0].id;
  const again = tradeMatches(sm.rows, new Set([`${kyra}:${spot}`]));
  const card = again.find((x) => [x.a.manager, x.b.manager].includes('Kyra'));
  const kyraSide = card && (card.a.manager === 'Kyra' ? card.a : card.b);
  assert.ok(!kyraSide || !kyraSide.has.some((h) => h.spot === spot));
});

test('Coach\'s take: bye-week headline and paragraph', () => {
  const v = vitals(g.teams, { seasonAvg: g.seasonAvg });
  const t = coachTake(g.teams, v, COACH_HEADLINES);
  assert.equal(t.headline, 'Bye week came for everyone.');
  assert.equal(t.paragraph, "7 of 8 lineups have something to fix. 9 starters across 6 teams are on bye and score zero until they're swapped out. Amie is the only clean lineup, and projected to lead the league at 140.3.");
  assert.deepEqual(t.pills, [
    { label: 'Cleanest lineup', text: 'Amie' }, { label: 'Biggest swap', text: 'Samantha +3.7' }, { label: 'Most on bye', text: 'Samantha, 3' }]);
});

test('headline pool follows league state, first match wins', () => {
  const h = (s) => COACH_HEADLINES.find((x) => x.when(s)).text;
  assert.equal(h({ total: 8, fixTeams: 7, byeTeams: 4 }), 'Bye week came for everyone.');
  assert.equal(h({ total: 8, fixTeams: 0, byeTeams: 0 }), 'Mostly fine, and Coach is suspicious.');
  assert.equal(h({ total: 8, fixTeams: 1, byeTeams: 1 }), 'Mostly fine, and Coach is suspicious.');
  assert.equal(h({ total: 8, fixTeams: 3, byeTeams: 2 }), 'A few lineups need a hug and a swap.');
  assert.equal(h({ total: 8, fixTeams: 5, byeTeams: 3 }), 'Coach has notes.');
});

test('take adapts for no clean lineups, several, and none to fix', () => {
  const bad = g.teams.map((t) => (t.swaps.length || t.empties.length || t.byeStarters.length ? t : { ...t, swaps: [{ text: 'x', gain: 1 }] }));
  const t0 = coachTake(bad, vitals(bad), COACH_HEADLINES);
  assert.match(t0.paragraph, /Nobody has a clean lineup\./);
  assert.ok(!t0.pills.some((p) => p.label === 'Cleanest lineup'));
  const ok = g.teams.map((t) => ({ ...t, swaps: [], empties: [], byeStarters: [], injured: [] }));
  const t1 = coachTake(ok, vitals(ok), COACH_HEADLINES);
  assert.equal(t1.paragraph, 'All 8 lineups are clean.');
  const two = g.teams.map((t) => (['Amie', 'Maya'].includes(t.manager) ? { ...t, byeStarters: [] } : t));
  assert.match(coachTake(two, vitals(two), COACH_HEADLINES).paragraph, /Maya and Amie have clean lineups\./);
});

test('trade matchmaker: Marlee\'s empty kicker slot means Maya\'s K need is not filled by her', () => {
  const unavailable = unavailableSpots(g.teams);
  assert.ok(unavailable.has(`${g.teams[3].id}:K`));
  const card = tradeMatches(sm.rows, unavailable).find((x) => [x.a.manager, x.b.manager].sort().join() === 'Marlee,Maya');
  assert.ok(!card || card.kind !== 'perfect');
  assert.ok(tradeMatches(sm.rows, unavailable).every((x) => [x.a, x.b].every((s) => !(s.manager === 'Marlee' && s.has.some((h) => h.spot === 'K')))));
});

test('next week without projections: no ranks or scores, no arbitrary "cleanest" pick', () => {
  const v = vitals(g.teams, { seasonAvg: g.seasonAvg });
  const t = coachTake(g.teams, v, COACH_HEADLINES, { projected: false });
  assert.match(t.paragraph, /Amie is the only clean lineup\.$/);
  assert.ok(!/projected|lead the league|\d\.\d/.test(t.paragraph.split('on bye')[1]));
  const two = g.teams.map((x) => (['Amie', 'Maya'].includes(x.manager) ? { ...x, byeStarters: [] } : x));
  const t2 = coachTake(two, vitals(two), COACH_HEADLINES, { projected: false });
  assert.ok(!t2.pills.some((p) => p.label === 'Cleanest lineup'), 'two clean teams and no projections: nobody is "cleanest"');
});

test('"no starter is hurt" is only said when injuries were captured', () => {
  assert.equal(vitals(g.teams, { injuriesKnown: true }).noStarterHurt, true);
  assert.equal(vitals(g.teams, { injuriesKnown: false }).noStarterHurt, false);
});
