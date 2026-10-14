/* The fix board: every lineup problem on every team, not a capped desk list.
   Order: swaps by projected gain (biggest first), then empty slots, then bye starters,
   then hurt starters. Within a kind, teams keep the order they came in (standings order).
   `clear` is the managers with nothing to fix. */
function buildFixes(teams) {
  const rows = [];
  const add = (t, kind, text, gain = null) => rows.push({ team_id: t.id, manager: t.manager, kind, text, gain });
  const byGain = [];
  for (const t of teams) for (const s of t.swaps) byGain.push({ t, s });
  byGain.sort((x, y) => y.s.gain - x.s.gain);
  for (const { t, s } of byGain) add(t, 'swap', s.text, s.gain);
  for (const t of teams) for (const e of t.empties) add(t, 'empty', e.text);
  for (const t of teams) for (const b of t.byeStarters) if (b.text) add(t, 'bye', b.text);   // a hurt starter on bye is listed once, as hurt
  for (const t of teams) for (const i of t.injured) if (i.text) add(t, 'out', i.text);
  const withFix = new Set(rows.map((r) => r.team_id));
  for (const t of teams) if (!withFix.has(t.id) && (t.injured.length || t.byeStarters.length)) withFix.add(t.id);
  return { rows, clear: teams.filter((t) => !withFix.has(t.id)).map((t) => t.manager) };
}
if (typeof module !== 'undefined') module.exports = { buildFixes };
