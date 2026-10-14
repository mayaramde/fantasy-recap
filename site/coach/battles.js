/* Where the week gets decided. `games` is [{a, b}], each side {id, manager, projected,
   starters: [{slot, projected}]}. A lineup-spot edge is the gap between the two sides' summed
   projection at one slot (RB and WR add both starters, same as the strips on This Week). */
const BATTLE_SLOTS = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'DST', 'K'];
function battles(games, top = 5) {
  const sum = (s, slot) => s.starters.filter((p) => p.slot === slot).reduce((n, p) => n + (p.projected || 0), 0);
  const edges = [];
  const gaps = [];
  for (const { a, b } of games) {
    for (const slot of BATTLE_SLOTS) {
      const d = Math.round((sum(a, slot) - sum(b, slot)) * 100) / 100;
      if (Math.abs(d) < 0.05) continue;
      const [winner, loser] = d > 0 ? [a, b] : [b, a];
      edges.push({ slot, winner: winner.manager, loser: loser.manager, margin: Math.abs(d) });
    }
    gaps.push({ a: a.manager, b: b.manager, gap: Math.round(Math.abs(a.projected - b.projected) * 100) / 100 });
  }
  edges.sort((x, y) => y.margin - x.margin);
  return {
    edges: edges.slice(0, top),
    closest: gaps.length ? gaps.reduce((m, g) => (g.gap < m.gap ? g : m)) : null,
    biggest: gaps.length ? gaps.reduce((m, g) => (g.gap > m.gap ? g : m)) : null,
  };
}
if (typeof module !== 'undefined') module.exports = { battles };
