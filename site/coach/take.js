/* Coach's take: the headline, the paragraph and the three callout pills.
   `teams` are normalized teams (standings order), `v` is vitals(), `headlines` is
   COACH_HEADLINES. Everything is read off the league state; nothing is guessed. Managers are
   named, never pronouned. */
function coachTake(teams, v, headlines) {
  const ord = (n) => n + (['th', 'st', 'nd', 'rd'][(n % 100 - 20) % 10] || ['th', 'st', 'nd', 'rd'][n % 100] || 'th');
  const f1 = (n) => (Math.round(n * 10) / 10).toFixed(1);
  const join = (xs) => (xs.length < 3 ? xs.join(' and ') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);
  const state = { total: v.total, fixTeams: v.fixTeams, byeTeams: v.byeTeams };
  const hit = headlines.find((h) => h.when(state));
  const headline = hit ? hit.text.replace('{n}', String(v.fixTeams)) : 'Coach has notes.';
  const problems = (t) => t.swaps.length + t.empties.length + t.byeStarters.length + t.injured.length;
  const clean = teams.filter((t) => problems(t) === 0);
  const byProj = [...teams].sort((a, b) => b.projected - a.projected);

  const parts = [];
  parts.push(v.fixTeams === 0 ? `All ${v.total} lineups are clean.`
    : `${v.fixTeams} of ${v.total} lineups have something to fix.`);
  if (v.byeStarters > 0) {
    parts.push(`${v.byeStarters} ${v.byeStarters === 1 ? 'starter' : 'starters'} across ${v.byeTeams} ${v.byeTeams === 1 ? 'team' : 'teams'} ${v.byeStarters === 1 ? 'is' : 'are'} on bye and score zero until ${v.byeStarters === 1 ? "he's" : "they're"} swapped out.`);
  }
  if (v.fixTeams > 0 && clean.length === 0) parts.push('Nobody has a clean lineup.');
  else if (v.fixTeams > 0 && clean.length === 1) {
    const c = clean[0];
    const rank = byProj.indexOf(c) + 1;
    parts.push(`${c.manager} is the only clean lineup, and projected ${rank === 1 ? `to lead the league at ${f1(c.projected)}` : `${ord(rank)} of ${v.total} at ${f1(c.projected)}`}.`);
  } else if (v.fixTeams > 0) {
    parts.push(`${join(clean.map((c) => c.manager))} have clean lineups.`);
  }

  // Pills: a pill nobody qualifies for is left out.
  const pills = [];
  if (clean.length) {
    const c = [...clean].sort((a, b) => b.projected - a.projected)[0];
    pills.push({ label: 'Cleanest lineup', text: c.manager });
  }
  const swaps = teams.flatMap((t) => t.swaps.map((s) => ({ t, s }))).sort((a, b) => b.s.gain - a.s.gain);
  if (swaps.length) pills.push({ label: 'Biggest swap', text: `${swaps[0].t.manager} +${f1(swaps[0].s.gain)}` });
  const top = Math.max(0, ...teams.map((t) => t.byeStarters.length));
  if (top > 0) {
    const names = teams.filter((t) => t.byeStarters.length === top).map((t) => t.manager);
    pills.push({ label: 'Most on bye', text: `${names.length > 2 ? `${names.length} teams` : join(names)}, ${top}${names.length > 1 ? ' each' : ''}` });
  }
  return { headline, paragraph: parts.join(' '), pills };
}
if (typeof module !== 'undefined') module.exports = { coachTake };
