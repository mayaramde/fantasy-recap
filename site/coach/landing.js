/* ---------- Coach landing: the league first, a team second ----------
   Browser-side only (it reads the page's own data and helpers), inlined into template.html by
   site/build.py after the pure insight functions in this folder. Read-only: nothing here
   changes a lineup or claims a trade. A module whose inputs aren't there is left out. */
let clShowAll = false;
const CL_ROWS = 10;
const CL_KIND = { swap: 'Lineup swap', empty: 'Empty slot', bye: 'Bye week', out: 'Injured starter' };
const CL_NAME = { QB: 'quarterback', RB: 'running back', WR: 'wide receiver', TE: 'tight end', FLEX: 'flex', DST: 'defense', K: 'kicker' };
const CL_ICON = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  swap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 8h15M15 4l4 4-4 4M20 16H5M9 12l-4 4 4 4"/></svg>',
  up: '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 1l4 7H1z" fill="currentColor"/></svg>',
  down: '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M5 9L1 2h8z" fill="currentColor"/></svg>',
};

const clSection = (marker, title, body, sub = '') => `
  <section class="cl-sec">
    <div class="cl-head"><span class="cl-mark ${marker}" aria-hidden="true"></span><h2>${title}</h2><span class="cl-rule" aria-hidden="true"></span></div>
    ${sub ? `<p class="cl-sub">${sub}</p>` : ''}
    ${body}
  </section>`;

/* One normalized team per advice row, in standings order, for the pure functions in this folder. */
function clTeams(rows) {
  const known = rows.some((r) => Array.isArray(r.report));
  const stand = SEASON.standings || [];
  const ordered = stand.length ? stand.map((s) => rows.find((r) => r.team_id === s.team_id)).filter(Boolean) : rows;
  const spotOf = (p) => p.slot || p.pos || '';
  return ordered.map((r) => {
    const t = TEAMS[r.team_id];
    const report = known ? (r.report || []) : [];
    const isBye = (p) => (p.bye != null ? p.bye : p.status === 'Bye');
    const item = (kinds, name) => r.items.find((it) => kinds.includes(it.kind)
      && (it.title === `${name} is on a bye` || it.title.endsWith(` over ${name}`) || it.title.startsWith(`${name} is `)));
    const hurt = (p) => p.status !== 'Bye';
    return {
      id: r.team_id, manager: r.manager, projected: r.projected, record: t ? record(t) : '', streak: t ? t.streak : '',
      swaps: r.items.filter((it) => it.kind === 'swap' && it.gain).map((it) => ({ text: deskTitle(it.title), gain: it.gain })),
      empties: r.items.filter((it) => it.kind === 'empty').map((it) => ({ text: deskTitle(it.title), spot: (it.title.match(/^Your (\S+) spot/) || [])[1] })),
      byeStarters: report.filter((p) => p.role === 'starting' && isBye(p)).map((p) => {
        const it = item(['bye'], p.name);
        return { name: p.name, nfl: p.team, spot: spotOf(p), text: hurt(p) ? null : (it ? deskTitle(it.title) : `${p.name} is on a bye`) };
      }),
      byeBench: report.filter((p) => p.role === 'bench' && isBye(p)).map((p) => ({ name: p.name, nfl: p.team })),
      injured: report.filter((p) => p.role === 'starting' && hurt(p)).map((p) => {
        const it = item(['out'], p.name);
        return { name: p.name, status: p.status, spot: spotOf(p), text: it ? deskTitle(it.title) : null };
      }),
      ranks: t && t.profile && t.profile.pos_ranks ? t.profile.pos_ranks : null,
      teamName: r.team_name,
      summary: r.summary,
    };
  });
}

/* Every game's two lineups, for "where the week gets decided". This week reads the live games
   (so it refreshes with them); next week reads the captured lineups. */
function clGames(next, rows) {
  if (!next) {
    return ((LIVE && LIVE.games) || []).map((g) => [g.winner, g.loser]).map(([a, b]) => ({
      a: { id: a.team_id, manager: a.manager, projected: projOf(a), starters: a.starters || [] },
      b: { id: b.team_id, manager: b.manager, projected: projOf(b), starters: b.starters || [] } }));
  }
  const side = (r) => ({ id: r.team_id, manager: r.manager, projected: r.projected, starters: (r.lineup && r.lineup.starters) || [] });
  const seen = new Set();
  const out = [];
  for (const r of rows) {
    const o = rows.find((x) => x.team_id === r.opponent_id);
    if (!o || seen.has(r.team_id)) continue;
    seen.add(r.team_id); seen.add(o.team_id);
    out.push({ a: side(r), b: side(o) });
  }
  return out;
}

const clYou = (on) => (on ? '<span class="cl-you">You</span>' : '');
/* "You" is the Viewing-as pick (orange); "viewing" is whichever team's profile is open (cobalt-soft).
   Only the League tab passes a `view`; the landing has nobody open, so it only ever lights "you". */
const clTone = (id, me, view) => (id === me ? ' me' : view != null && id === view ? ' view' : '');
const clTag = (id, me, view) => (id === me ? clYou(true) : view != null && id === view ? '<span class="cl-viewing">Viewing</span>' : '');
/* A name that opens that team's profile. role=button, not a link: the router handles the tap
   (and Enter / Space) in template.html, so a name inside a table row or list item stays valid markup. */
const clOpen = (id, name) => `role="button" tabindex="0" data-open-team="${id}" title="Open ${esc(name)}'s team"`;

function clTake(take, v, show, unwritten = false) {
  const tile = (tone, label, big, sub) => `<div class="cl-vital"><span class="cl-chip ${tone}">${label}</span><span class="cl-vn">${big}</span>${sub ? `<span class="cl-vs">${sub}</span>` : ''}</div>`;
  const tiles = [
    tile('lime', 'Lineups to fix', `${v.fixTeams}<small> / ${v.total}</small>`, 'teams with something to fix'),
    show.bye ? tile('pink', 'Starters on bye', String(v.byeStarters), `across ${v.byeTeams} ${v.byeTeams === 1 ? 'team' : 'teams'}${v.noStarterHurt ? ' · no starter is hurt' : ''}`) : '',
    show.proj ? tile('orange', 'Swap gains', `+${f1(v.swapGain)}`, 'projected points on benches') : '',
    show.proj && v.avgProjection ? tile('blue', 'Avg projection', f1(v.avgProjection), v.seasonAvg ? `season average is ${f1(v.seasonAvg)}` : '') : '',
  ].filter(Boolean).join('');
  const PILL = { 'Cleanest lineup': 'lime', 'Biggest swap': 'orange', 'Most on bye': 'pink' };
  return `
    <div class="cl-top">
      <section class="cl-take${unwritten ? ' light' : ''}" aria-labelledby="cl-take-h">
        <span class="cl-take-label">Coach's take</span>
        <h2 id="cl-take-h">${esc(take.headline)}</h2>
        <p>${esc(take.paragraph)}</p>
        ${unwritten ? '<p class="cl-unwritten">Coach hasn\'t written today\'s take yet.</p>' : ''}
        ${take.pills.length ? `<ul class="cl-pills">${take.pills.map((p) => `<li class="${PILL[p.label] || ''}"><span>${esc(p.label)}</span>${esc(p.text)}</li>`).join('')}</ul>` : ''}
      </section>
      <div class="cl-vitals" role="group" aria-label="League vitals">${tiles}</div>
    </div>`;
}

function clQuip(t) {
  const ok = (s) => s && s.length <= 110;
  if (ok(t.summary)) return t.summary;
  const swap = [...t.swaps].sort((a, b) => b.gain - a.gain)[0];
  const q = t.byeStarters.length ? `${t.byeStarters.length} ${t.byeStarters.length === 1 ? 'starter is' : 'starters are'} on bye and scoring zero until swapped.`
    : t.empties.length ? `${t.empties[0].spot || 'A'} spot is empty, and an empty spot scores zero.`
    : swap ? `${swap.text} is ${f1(swap.gain)} points waiting on the bench.`
    : t.injured.length ? `${t.injured[0].name} is on the injury report as ${t.injured[0].status.toLowerCase()}.`
    : 'Nothing to fix. Suspiciously tidy.';
  return q.length <= 110 ? q : 'A few things to fix. The report has the details.';
}

function clTeamCards(teams, next, me, waiverIdx) {
  const po = (SEASON.playoffs && SEASON.playoffs.teams) || [];
  const line = (SEASON.playoffs && SEASON.playoffs.config && SEASON.playoffs.config.teams) || 4;
  const card = (t, i) => {
    const o = po.find((x) => x.team_id === t.id);
    const mine = t.id === me;
    const inLine = i + 1 <= line;
    const bestSwap = [...t.swaps].sort((a, b) => b.gain - a.gain)[0];
    const clear = !t.swaps.length && !t.empties.length && !t.byeStarters.length && !t.injured.length;
    const chips = [
      clear ? ['lime', 'All clear'] : null,
      t.byeStarters.length ? ['pink', `${t.byeStarters.length} ${t.byeStarters.length === 1 ? 'starter' : 'starters'} on bye`] : null,
      bestSwap ? ['lime', `+${f1(bestSwap.gain)} swap`] : null,
      t.empties.length ? ['orange', `${t.empties[0].spot || ''} slot empty`.trim()] : null,
      t.injured.length ? ['pink', `${t.injured.length} ${t.injured.length === 1 ? 'starter' : 'starters'} hurt`] : null,
      t.byeBench.length ? ['soft', `${t.byeBench.length} bench on bye`] : null,
      waiverIdx.has(t.id) ? ['blue', `Waiver #${waiverIdx.get(t.id)}`] : null,
    ].filter(Boolean).slice(0, 3);
    return `
      <li class="cl-team${mine ? ' me' : ''}">
        <div class="cl-band ${inLine ? 'in' : 'out'}"><span>Seed ${i + 1}</span><span>${inLine ? `In the top ${line}` : 'Outside the line'}</span></div>
        <div class="cl-team-body">
          <h3>${esc(t.manager)}${clYou(mine)}</h3>
          <p class="cl-tn">${esc(t.teamName || '')}</p>
          <div class="cl-stats3"><div><b>${esc(t.record)}${t.streak ? ` · <span class="cl-streak ${t.streak[0] === 'W' ? 'w' : 'l'}">${esc(t.streak)}</span>` : ''}</b><small>record · streak</small></div>
            ${o ? `<div><b>${pct(o.playoff)}</b><small>playoff odds</small></div>` : ''}</div>
          ${o ? `<span class="cl-bar" role="img" aria-label="Playoff odds ${pct(o.playoff)}"><span style="width:${(o.playoff * 100).toFixed(1)}%"></span></span>` : ''}
          <p class="cl-quip">${esc(clQuip(t))}</p>
          <ul class="cl-chips">${chips.map(([c, x]) => `<li class="${c}">${esc(x)}</li>`).join('')}</ul>
          <a class="cl-open" href="${coachUrl(next, t.id)}">Open ${esc(t.manager)}'s report →</a>
        </div>
      </li>`;
  };
  return `<ul class="cl-teams">${teams.map(card).join('')}</ul>`;
}

function clFixBoard(fixes, me) {
  const row = (r) => {
    const [cls, val] = r.kind === 'swap' ? ['lime', `+${f1(r.gain)}`] : r.kind === 'empty' ? ['orange', 'EMPTY'] : r.kind === 'bye' ? ['pink', 'BYE'] : ['pink', 'OUT'];
    return `<li class="cl-fix"><a class="cl-who${r.team_id === me ? ' me' : ''}" href="${lineupUrl(false, r.team_id)}">${esc(r.manager)}</a>
      <div class="cl-fix-t">${esc(r.text)}<small>${CL_KIND[r.kind]}</small></div><span class="cl-val ${cls}">${val}</span></li>`;
  };
  const head = fixes.rows.slice(0, CL_ROWS);
  const rest = fixes.rows.slice(CL_ROWS);
  return `
    <div class="cl-card cl-fixes">
      ${fixes.rows.length ? `<ul>${head.map(row).join('')}${clShowAll ? rest.map(row).join('') : ''}</ul>` : '<p class="cl-empty">Nothing to fix on any roster.</p>'}
      ${rest.length ? `<button type="button" class="cl-more" data-cl-more aria-expanded="${clShowAll}">${clShowAll ? 'Show fewer' : `Show all ${fixes.rows.length}`}</button>` : ''}
      ${fixes.clear.length ? `<div class="cl-allclear">${CL_ICON.check}<span><b>All clear:</b> ${fixes.clear.map(esc).join(' · ')}</span></div>` : ''}
    </div>`;
}

function clByes(d, me, injuryKnown, view) {
  const strip = !injuryKnown ? ''
    : d.injured.length
    ? `<div class="cl-injury"><h4>Hurt starters</h4><ul>${d.injured.map((p) => `<li><b>${esc(p.manager)}</b> ${esc(p.name)} <span class="cl-pill pink">${esc(p.status)}</span> <small>${esc(p.spot)}</small></li>`).join('')}</ul></div>`
    : `<div class="cl-injury clean">${CL_ICON.check}<span><b>Injury report is clean.</b> No starter is hurt.</span></div>`;
  return `
    <div class="cl-card cl-byes">
      ${d.tiles.length ? `<ul class="cl-tiles">${d.tiles.map((t) => `<li><div class="cl-tn2"><b>${t.count}</b><span>${esc(t.team)} on bye</span></div><small>${esc(t.names.join(' · '))}</small></li>`).join('')}</ul>` : '<p class="cl-empty">No NFL team is off this week.</p>'}
      <div class="cl-label">Exposure by manager</div>
      <ul class="cl-expo">${d.exposure.map((e) => `
        <li><span class="cl-nm${clTone(e.team_id, me, view)}">${esc(e.manager)}</span>
          <span class="cl-segs" aria-hidden="true">${e.starters ? `<i class="s" style="width:${e.starters * 34}px"></i>` : ''}${e.bench ? `<i class="b" style="width:${e.bench * 34}px"></i>` : ''}</span>
          <span class="cl-el">${esc(e.label)}</span></li>`).join('')}</ul>
      <p class="cl-legend"><span><i class="s" aria-hidden="true"></i>Starter on bye</span><span><i class="b" aria-hidden="true"></i>Bench on bye</span></p>
      ${strip}
    </div>`;
}

function clBattles(b, me) {
  const maxEdge = b.edges.length ? b.edges[0].margin : 1;
  const stat = (label, g) => g ? `<div class="cl-stat"><small>${label}</small><b>${esc(g.a)} vs ${esc(g.b)} · ${f1(g.gap)} pts</b></div>` : '';
  return `
    <div class="cl-card cl-battles">
      <div class="cl-stats">${stat('Closest game', b.closest)}${stat('Biggest gap', b.biggest)}</div>
      ${b.edges.length ? `<ol class="cl-edges">${b.edges.map((e) => `
        <li><span class="cl-slot">${esc(e.slot)}</span><div class="cl-mid"><b>${esc(e.winner)} over ${esc(e.loser)}</b>
          <span class="cl-bar2" aria-hidden="true"><span style="width:${(100 * e.margin / maxEdge).toFixed(1)}%"></span></span></div><span class="cl-en">+${f1(e.margin)}</span></li>`).join('')}</ol>` : ''}
    </div>`;
}

function clWaiver(order, me, p, view) {
  return `
    <div class="cl-card cl-waiver">
      <ol class="cl-order">${order.map((t, i) => `<li class="${i === 0 ? 'first' : ''}${clTone(t.team_id, me, view)}" data-open-team="${t.team_id}"><b class="n">${i + 1}</b><span class="cl-go" ${clOpen(t.team_id, t.manager)}>${esc(t.manager)}</span>${clTag(t.team_id, me, view) || `<small>${esc(record(t))}</small>`}</li>`).join('')}</ol>
      ${p && p.rows.length ? `<div class="cl-pick"><div class="cl-label">Pickups, last seven days · ${p.total} total</div>
        <ul class="cl-picks">${p.rows.map((r) => `<li><span class="cl-nm">${esc(r.manager)}</span><span class="cl-bar" aria-hidden="true"><span style="width:${(100 * r.count / p.max).toFixed(1)}%"></span></span><b>${r.count}</b></li>`).join('')}</ul>
        <p class="cl-prow-note">${esc(p.quip)}</p></div>` : ''}
    </div>`;
}

function clStrength(sm, me, n, view) {
  const ord = (r) => ordinal(r);
  const body = sm.rows.map((r) => `
    <tr${clTone(r.id, me, view) ? ` class="${clTone(r.id, me, view).trim()}"` : ''}><th scope="row"><span class="cl-go" ${clOpen(r.id, r.manager)}>${esc(r.manager)}</span>${clTag(r.id, me, view)}${r.id === me ? '<span class="vh"> (you)</span>' : view != null && r.id === view ? '<span class="vh"> (viewing)</span>' : ''}</th>
      ${sm.cols.map((c) => {
        const rk = r.ranks[c];
        const tag = c === r.best ? ['best', 'best spot', CL_ICON.up] : c === r.weak ? ['weak', 'weakest spot', CL_ICON.down] : null;
        const label = `${r.manager} at ${CL_NAME[c]}: ${ord(rk)} of ${n}${tag ? `, ${tag[1]}` : ''}`;
        return `<td title="${esc(label)}" aria-label="${esc(label)}"><div class="cl-hc h${rk}"><span aria-hidden="true">${rk}</span>${tag ? `<i class="cl-corner ${tag[0]}">${tag[2]}</i>` : ''}</div></td>`;
      }).join('')}
      <td class="avg" aria-label="${esc(r.manager)}, average rank ${r.avg.toFixed(1)}"><span aria-hidden="true">${r.avg.toFixed(1)}</span></td></tr>`).join('');
  const foot = (cls, label, by) => `<tr class="${cls}"><th scope="row">${label}</th>${sm.cols.map((c) => `<td title="${esc(`${label} at ${CL_NAME[c]}: ${by[c] || 'nobody'}`)}"><span>${esc(by[c] || '')}</span></td>`).join('')}<td></td></tr>`;
  return `
    <div class="cl-heat table-scroll" role="region" aria-label="Lineup spot rankings, scrolls sideways" tabindex="0">
      <table><thead><tr><th scope="col">Manager</th>${sm.cols.map((c) => `<th scope="col" title="${CL_NAME[c]}">${c}</th>`).join('')}<th scope="col" title="average rank">AVG</th></tr></thead>
        <tbody>${body}</tbody>
        <tfoot>${foot('best', 'League best', sm.bestBy)}${foot('worst', 'League worst', sm.worstBy)}</tfoot></table>
    </div>
    <p class="cl-key"><span class="cl-corner best" aria-hidden="true">${CL_ICON.up}</span>best spot <span class="cl-corner weak" aria-hidden="true">${CL_ICON.down}</span>weakest spot · 1 is the league's best, ${n} the worst</p>`;
}

function clCallouts(list) {
  if (!list.length) return '';
  return `<ul class="cl-callouts">${list.map((c) => `
    <li class="${c.kind}"><h3>${esc(c.title)}</h3><ul>${c.items.map((i) => `<li><b>${esc(i.manager)}</b> ${esc(i.text)}</li>`).join('')}</ul></li>`).join('')}</ul>`;
}

function clTrades(cards) {
  const col = (label, xs) => `<div><span class="cl-col-l">${label}</span><b>${xs.map((x) => `${x.spot} ${ordinal(x.rank)}`).join(' · ')}</b></div>`;
  const text = (c) => {
    const a = c.a.needs.map((x) => x.spot).join(' and '), b = c.b.needs.map((x) => x.spot).join(' and ');
    return c.kind === 'perfect'
      ? `${c.a.manager} could use ${a} help and ${c.b.manager} could use ${b} help, and each has what the other lacks.`
      : `A looser fit: ${c.a.manager} is thin at ${a}, ${c.b.manager} is thin at ${b}, and each is stronger where the other is weaker.`;
  };
  return `
    <ul class="cl-trades">${cards.map((c) => `
      <li class="cl-trade ${c.kind}">
        <span class="cl-chip ${c.kind === 'perfect' ? 'lime' : 'softpink'}">${c.kind === 'perfect' ? 'Perfect fit' : 'Partial fit'}</span>
        <div class="cl-pair">
          <div class="cl-side a"><h3>${esc(c.a.manager)}</h3>${col('Needs', c.a.needs)}${col('Has', c.a.has)}</div>
          <span class="cl-swap">${CL_ICON.swap}</span>
          <div class="cl-side b"><h3>${esc(c.b.manager)}</h3>${col('Needs', c.b.needs)}${col('Has', c.b.has)}</div>
        </div>
        <p>${esc(text(c))}</p>
      </li>`).join('')}</ul>
    <p class="cl-note">Ideas, not offers: trades happen in the ESPN app.</p>`;
}

/* Everything both views are built from, computed once per render: the normalized teams, the
   league's vitals and take, the strength grid and the waiver order. The landing and the League
   tab both start here, so a number can't differ between them. */
function clModel(next, rows) {
  const teams = clTeams(rows);
  const known = rows.some((r) => Array.isArray(r.report));
  const projected = next ? !!ahead().projected : true;
  const n = teams.length;
  const injuryKnown = rows.some((r) => r.injuries_known);
  const v = vitals(teams, { seasonAvg: seasonAverage(SEASON.standings || []), injuriesKnown: injuryKnown });
  const take = coachTake(teams, v, COACH_HEADLINES, { projected });
  // coach-daily's paragraph, while it still describes the league as it is; the template wording otherwise.
  const written = (rows.find((r) => r.league_take) || {}).league_take;
  if (written) take.paragraph = written;
  const withRanks = teams.length && teams.every((t) => t.ranks);
  const sm = withRanks ? strengthMap(teams.map((t) => ({ id: t.id, manager: t.manager, ranks: t.ranks }))) : null;
  // Waiver order resets after each week's games, so next week's isn't known yet: no module, no chips.
  const order = next ? [] : SEASON.waiver_order ? SEASON.waiver_order.map((id) => TEAMS[id]).filter(Boolean) : [...(SEASON.standings || [])].reverse();
  return { teams, known, projected, n, injuryKnown, v, take, written: !!written, sm, order };
}

/* "Make this page yours": the way into a team's profile for someone who hasn't picked a name.
   The pink ! is the same homework signal the profile's team strip shows (this week's fixes waiting). */
function clPickCard(teams, rows) {
  const homework = (id) => ((rows.find((r) => r.team_id === id) || {}).counts || {}).now || 0;
  return `
    <section class="cl-sec cl-pickme" aria-labelledby="cl-pick-h">
      <div class="cl-card">
        <h2 id="cl-pick-h">Make this page yours</h2>
        <p class="cl-sub">Tap your name and Coach opens your team.</p>
        <div class="cl-pickgrid">${teams.map((t) => {
          const n = homework(t.id);
          return `<button type="button" class="cl-pickchip" data-cl-pick="${t.id}"${n ? ` aria-label="${esc(t.manager)}, ${n} to fix"` : ''}>${esc(t.manager)}${n ? '<span class="cl-dot" aria-hidden="true">!</span>' : ''}</button>`;
        }).join('')}</div>
        <p class="cl-pickhint"><span class="cl-dot" aria-hidden="true">!</span> A pink ! means that team has homework.</p>
      </div>
    </section>`;
}

function coachLanding(next, rows, me) {
  const m = clModel(next, rows);
  const { teams, known, projected, n, injuryKnown, v, take, sm, order } = m;
  const fixes = buildFixes(teams);
  const waiverIdx = new Map(order.map((t, i) => [t.team_id, i + 1]));
  const b = projected ? battles(clGames(next, rows)) : null;
  const pk = next ? null : pickups((LIVE && LIVE.wire) || []);
  const dmg = known ? byeDamage(teams) : null;
  const trades = sm ? tradeMatches(sm.rows, unavailableSpots(teams)) : [];
  const calls = sm ? callouts(sm.rows, n) : [];
  const body = [
    me ? '' : clPickCard(teams, rows),
    clTake(take, v, { bye: known, proj: projected }),
    clSection('pink', 'Pick a team', clTeamCards(teams, next, me, waiverIdx), 'Eight lineups, one tap to the full report. Seeds are today\'s standings; odds come from the same simulation as Standings.'),
    `<div class="cl-duo fx">
      ${clSection('lime', 'Fix board', clFixBoard(fixes, me), 'Every lineup problem on every roster, biggest projected gain first.')}
      ${dmg ? clSection('pink', 'Bye-week damage', clByes(dmg, me, injuryKnown), 'A bye means his NFL team doesn\'t play, so he scores zero.') : ''}
    </div>`,
    `<div class="cl-duo wx">
      ${b && b.edges.length ? clSection('orange', 'Where the week gets decided', clBattles(b, me), 'The biggest projected gaps at a single lineup spot, across every game.') : ''}
      ${order.length ? clSection('cobalt', 'Waiver wire', clWaiver(order, me, pk), 'Worst record picks first. The order resets every week.') : ''}
    </div>`,
    sm ? clSection('cobalt', "Where everyone's strong", clStrength(sm, me, n) + clCallouts(calls), 'Each team\'s lineup spots, ranked against the league. Darker means stronger.') : '',
    trades.length ? clSection('lime', 'Trade matchmaker', clTrades(trades), 'Pairs whose weak spots line up with each other\'s strengths.') : '',
  ].join('');
  return body;
}

/* The League tab on a team's profile: the league-wide half of the landing (Coach's take, the strength
   grid, the waiver order, injuries and byes) built from the same pieces, minus the pick card and the
   team strip, which the profile already has. `me` is the Viewing-as pick (orange), `view` the team
   whose profile is open (cobalt-soft). Each module that has nothing to show says so instead of
   drawing an empty table. */
function coachLeague(rows, me, view) {
  if (!rows.length) {
    return clSection('cobalt', 'The league', '<div class="cl-card"><p class="cl-empty">No rosters to read yet. The league view fills in once Coach has captured this week.</p></div>');
  }
  const { teams, known, n, injuryKnown, v, take, written, sm, order } = clModel(false, rows);
  const pk = pickups((LIVE && LIVE.wire) || []);
  const dmg = known ? byeDamage(teams) : null;
  const calls = sm ? callouts(sm.rows, n) : [];
  const body = [
    clTake(take, v, { bye: known, proj: true }, !written),
    clSection('cobalt', "Where everyone's strong",
      sm ? clStrength(sm, me, n, view) + clCallouts(calls) : '<div class="cl-card"><p class="cl-empty"><b>No grid yet.</b> It fills in once a week has been recapped.</p></div>',
      'Each team\'s lineup spots, ranked against the league. Darker means stronger.'),
    order.length ? clSection('cobalt', 'Waiver order this week', clWaiver(order, me, pk, view), 'Worst record picks first. The order resets every week.') : '',
    clSection('pink', 'Injuries and byes',
      dmg ? clByes(dmg, me, injuryKnown, view) : '<div class="cl-card"><p class="cl-empty">The injury and bye report isn\'t in yet.</p></div>',
      'A bye means his NFL team doesn\'t play, so he scores zero.'),
  ].join('');
  return body;
}

/* The one-line note under the week toggle: what this tab is built from, and what it leaves out. */
function clWeekNote(next, rows) {
  const injuryKnown = rows.some((r) => r.injuries_known);
  if (!next) return '';   // this week needs no explaining; only Next week says what it leaves out
  const a = ahead();
  return a.projected
    ? `Week ${a.week} is projected: ESPN's projected points, byes${injuryKnown ? ' and injury report' : ''} as of ${updated(a.captured_at)}. No pickups or waiver order until the week starts.`
    : `Week ${a.week} is byes${injuryKnown ? ' and injuries' : ''} only: ESPN hasn't published projected points yet. No pickups or waiver order until the week starts.`;
}
