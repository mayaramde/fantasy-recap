/* The rank heatmap's data. `teams` is [{id, manager, ranks: {QB: 2, ...}}] in standings order;
   `cols` is the spot order. A team's best and weakest spot are the first occurrence in column
   order when ranks tie, and are only marked when they differ (a flat row has neither). Each
   spot's league best and worst are the first team in standings order holding rank 1 and the
   last rank. */
const STRENGTH_COLS = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'DST', 'K'];
function strengthMap(teams, cols = STRENGTH_COLS) {
  const n = teams.length;
  const rows = teams.map((t) => {
    const vals = cols.map((c) => t.ranks[c]);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const best = lo === hi ? null : cols[vals.indexOf(lo)];
    const weak = lo === hi ? null : cols[vals.indexOf(hi)];
    return { id: t.id, manager: t.manager, ranks: t.ranks, best, weak,
      avg: Math.round((vals.reduce((a, b) => a + b, 0) / cols.length) * 10) / 10 };
  });
  const pick = (rank) => Object.fromEntries(cols.map((c) => [c, (teams.find((t) => t.ranks[c] === rank) || {}).manager || null]));
  return { cols, rows, bestBy: pick(1), worstBy: pick(n) };
}
if (typeof module !== 'undefined') module.exports = { strengthMap, STRENGTH_COLS };
