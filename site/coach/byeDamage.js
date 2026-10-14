/* Bye-week damage, three ways: one tile per NFL team that's off, an exposure bar per
   manager, and the injured starters. `abbr` turns "Rome Odunze" into "R. Odunze". */
function abbr(name) {
  const parts = String(name).trim().split(/\s+/);
  if (parts.length < 2 || /D\/ST$/.test(name)) return String(name);
  return `${parts[0][0]}. ${parts.slice(1).join(' ')}`;
}
function byeDamage(teams) {
  const nfl = new Map();
  for (const t of teams) for (const p of [...t.byeStarters, ...t.byeBench]) {
    if (!p.nfl) continue;
    if (!nfl.has(p.nfl)) nfl.set(p.nfl, []);
    nfl.get(p.nfl).push(abbr(p.name));
  }
  const tiles = [...nfl.entries()].map(([team, names]) => ({ team, count: names.length, names }))
    .sort((a, b) => (b.count - a.count) || a.team.localeCompare(b.team));
  const exposure = teams.map((t, i) => ({
    team_id: t.id, manager: t.manager, starters: t.byeStarters.length, bench: t.byeBench.length, i,
  })).sort((a, b) => (b.starters - a.starters) || (b.bench - a.bench) || (a.i - b.i)).map(({ i, ...e }) => ({
    ...e,
    label: !e.starters && !e.bench ? 'Clean'
      : [e.starters ? `${e.starters} starter${e.starters === 1 ? '' : 's'}` : '', e.bench ? `${e.bench} bench` : ''].filter(Boolean).join(' · '),
  }));
  const injured = teams.flatMap((t) => t.injured.map((p) => ({ team_id: t.id, manager: t.manager, name: p.name, status: p.status, spot: p.spot })));
  return { tiles, exposure, injured };
}
if (typeof module !== 'undefined') module.exports = { byeDamage, abbr };
