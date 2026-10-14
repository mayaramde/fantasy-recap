/* Trade matchmaker: pairs of managers whose weak spots line up with each other's strengths.
   `rows` is strengthMap().rows, in standings order. `unavailable` is a Set of "id:spot" for
   spots where that manager has nothing to offer (the starter is on a bye or the slot is empty).

   For a pair (A, B), A "needs" the spots where A is ranked 7th or worse and B 3rd or better.
   - Perfect fit: A needs something B has AND B needs something A has.
   - Partial fit: each side has a spot where the other is ranked 5th or better and ahead of
     them, and at least one of the needy ranks involved is 7th or worse.
   Each manager appears in one card. Perfect fits come first, then partials; within each, the
   biggest total rank improvement wins. Ideas only: nothing here moves a player. */
function tradeMatches(rows, unavailable = new Set(), cols = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'DST', 'K'], limit = 3) {
  const ok = (p, spot) => !unavailable.has(`${p.id}:${spot}`);
  const strict = (a, b) => cols.filter((c) => a.ranks[c] >= 7 && b.ranks[c] <= 3 && ok(b, c));
  const loose = (a, b) => cols.filter((c) => b.ranks[c] <= 5 && b.ranks[c] < a.ranks[c] && ok(b, c));
  const cands = [];
  rows.forEach((a, i) => rows.slice(i + 1).forEach((b, j) => {
    const sa = strict(a, b), sb = strict(b, a);
    let kind = null, na = sa, nb = sb;
    if (sa.length && sb.length) kind = 'perfect';
    else {
      const la = loose(a, b), lb = loose(b, a);
      if (la.length && lb.length && [...la.map((c) => a.ranks[c]), ...lb.map((c) => b.ranks[c])].some((r) => r >= 7)) {
        kind = 'partial'; na = la; nb = lb;
      }
    }
    if (!kind) return;
    const gain = na.reduce((n, c) => n + a.ranks[c] - b.ranks[c], 0) + nb.reduce((n, c) => n + b.ranks[c] - a.ranks[c], 0);
    cands.push({ kind, gain, order: -(i + (i + 1 + j)),   // ties go to the pair lower in the standings, the ones with more to gain
      a: { id: a.id, manager: a.manager, needs: na.map((c) => ({ spot: c, rank: a.ranks[c] })), has: nb.map((c) => ({ spot: c, rank: a.ranks[c] })) },
      b: { id: b.id, manager: b.manager, needs: nb.map((c) => ({ spot: c, rank: b.ranks[c] })), has: na.map((c) => ({ spot: c, rank: b.ranks[c] })) } });
  }));
  cands.sort((x, y) => ((y.kind === 'perfect') - (x.kind === 'perfect')) || (y.gain - x.gain) || (x.order - y.order));
  const used = new Set();
  const out = [];
  for (const c of cands) {
    if (used.has(c.a.id) || used.has(c.b.id)) continue;
    used.add(c.a.id); used.add(c.b.id);
    out.push(c);
    if (out.length === limit) break;
  }
  return out;
}

/* The spots a manager can't offer right now, as a Set of "id:spot": a starter there is on a bye,
   or the slot is empty. Feed it to tradeMatches. */
function unavailableSpots(teams) {
  const out = new Set();
  for (const t of teams) {
    for (const p of t.byeStarters) if (p.spot) out.add(`${t.id}:${p.spot}`);
    for (const e of t.empties) if (e.spot) out.add(`${t.id}:${e.spot}`);
  }
  return out;
}
if (typeof module !== 'undefined') module.exports = { tradeMatches, unavailableSpots };
