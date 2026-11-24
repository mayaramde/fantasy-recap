/* The rank heatmap's data. `teams` is [{id, manager, ranks: {QB: 2, ...}}] in standings order;
   `cols` is the spot order. A team's best and weakest spot are the first occurrence in column
   order when ranks tie, and are only marked when they differ (a flat row has neither). Each
   spot's league best and worst are the first team in standings order holding rank 1 and the
   last rank. `overall` ranks the rows by their average spot rank (1 = the lowest average, the
   strongest lineup; equal averages share a rank), so the page can shade and sort by it, and
   `meter` (10-100) is how full that row's strength bar is: the lowest average fills it. */
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
  // The bar spans the league's own range (best average full, worst a sliver), since averages
  // bunch together (3.4 to 5.3 out of 1 to 8) and a bar on the full 1-8 scale barely moves.
  const avgs = rows.map((r) => r.avg), top = Math.min(...avgs), bottom = Math.max(...avgs);
  for (const r of rows) {
    r.overall = 1 + rows.filter((o) => o.avg < r.avg).length;
    r.meter = bottom > top ? Math.round(10 + (90 * (bottom - r.avg)) / (bottom - top)) : 100;
  }
  const pick = (rank) => Object.fromEntries(cols.map((c) => [c, (teams.find((t) => t.ranks[c] === rank) || {}).manager || null]));
  return { cols, rows, bestBy: pick(1), worstBy: pick(n) };
}
if (typeof module !== 'undefined') module.exports = { strengthMap, STRENGTH_COLS };
