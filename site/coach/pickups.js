/* Pickups per manager from the league wire (last seven days). Counted the way the wire's own
   feed counts them: adds and drops by one manager on one day are netted first, so a player
   picked up and dropped the same day doesn't count. `events` is LIVE.wire. */
function pickups(events) {
  const day = (e) => new Date(e.date).toDateString();
  const rolled = new Map();
  for (const e of events || []) {
    if (e.kind !== 'move') continue;
    const k = `${day(e)}|${e.team_id}`;
    const had = rolled.get(k) || { manager: e.manager, added: [], dropped: [] };
    had.added.push(...(e.added || []));
    had.dropped.push(...(e.dropped || []));
    rolled.set(k, had);
  }
  const counts = new Map();
  for (const m of rolled.values()) {
    const n = m.added.filter((x) => !m.dropped.includes(x)).length;
    if (n) counts.set(m.manager, (counts.get(m.manager) || 0) + n);
  }
  const rows = [...counts.entries()].map(([manager, count]) => ({ manager, count }))
    .sort((a, b) => (b.count - a.count) || a.manager.localeCompare(b.manager));
  const total = rows.reduce((n, r) => n + r.count, 0);
  let quip = '';
  if (rows.length) {
    const lead = rows.filter((r) => r.count === rows[0].count);
    quip = lead.length === 1
      ? `${rows[0].manager} made ${rows[0].count} of the league's ${total} ${total === 1 ? 'pickup' : 'pickups'}. Busiest thumbs in the group chat.`
      : `${lead.map((r) => r.manager).join(' and ')} tied for the most, ${rows[0].count} each. A very polite arms race.`;
  }
  return { rows, total, max: rows.length ? rows[0].count : 0, quip };
}
if (typeof module !== 'undefined') module.exports = { pickups };
