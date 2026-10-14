/* Up to three callouts read off the rank matrix. `rows` is strengthMap().rows; `n` the league
   size (the worst rank). Any callout nobody qualifies for is skipped. */
function callouts(rows, n = rows.length, cols = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'DST', 'K']) {
  const spots = (r, rank) => cols.filter((c) => r.ranks[c] === rank);
  const list = (xs) => (xs.length < 3 ? xs.join(' and ') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);
  const info = rows.map((r) => ({ r, firsts: spots(r, 1), lasts: spots(r, n) }));
  const out = [];
  const split = info.filter((x) => x.firsts.length >= 2 && x.lasts.length >= 2);
  if (split.length) out.push({ kind: 'split', title: 'Split personalities', items: split.map((x) => ({
    manager: x.r.manager, text: `#1 at ${list(x.firsts)}, dead last at ${list(x.lasts)}` })) });
  const base = info.filter((x) => x.lasts.length >= 2);
  if (base.length) out.push({ kind: 'basement', title: 'Basement dwellers', items: base.map((x) => ({
    manager: x.r.manager, text: `last at ${list(x.lasts)}` })) });
  const splitNames = new Set(split.map((x) => x.r.manager));
  const lop = info.filter((x) => x.firsts.length && x.lasts.length && !splitNames.has(x.r.manager));
  if (lop.length) out.push({ kind: 'lopsided', title: 'Lopsided', items: lop.map((x) => ({
    manager: x.r.manager, text: `best at ${list(x.firsts)}, worst at ${list(x.lasts)}` })) });
  return out;
}
if (typeof module !== 'undefined') module.exports = { callouts };
