/* The four tiles under Coach's take. `teams` are normalized (see landing.js): each has
   swaps [{gain}], empties, byeStarters, injured. `byeKnown` is false when the injury report
   hasn't been captured, which hides the bye tile rather than reading "0". */
function vitals(teams, opts = {}) {
  const r1 = (n) => Math.round(n * 10) / 10;
  const fixCount = (t) => t.swaps.length + t.empties.length + t.byeStarters.length + t.injured.length;
  const byeTeams = teams.filter((t) => t.byeStarters.length);
  const injuredStarters = teams.reduce((n, t) => n + t.injured.length, 0);
  const projected = teams.map((t) => t.projected).filter((p) => typeof p === 'number');
  return {
    total: teams.length,
    fixTeams: teams.filter((t) => fixCount(t) > 0).length,
    byeStarters: teams.reduce((n, t) => n + t.byeStarters.length, 0),
    byeTeams: byeTeams.length,
    injuredStarters,
    noStarterHurt: injuredStarters === 0,
    swapGain: r1(teams.reduce((n, t) => n + t.swaps.reduce((m, s) => m + s.gain, 0), 0)),
    avgProjection: projected.length ? r1(projected.reduce((a, b) => a + b, 0) / projected.length) : null,
    seasonAvg: opts.seasonAvg ?? null,
  };
}
if (typeof module !== 'undefined') module.exports = { vitals };
