/* Mean of every completed weekly score across all teams. `teams` is [{weekly: [{points}]}].
   Null when nothing has been played, so the vitals tile can leave its subtext out. */
function seasonAverage(teams) {
  const scores = teams.flatMap((t) => (t.weekly || []).map((g) => g.points)).filter((p) => typeof p === 'number');
  if (!scores.length) return null;
  return Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 10) / 10;
}
if (typeof module !== 'undefined') module.exports = { seasonAverage };
