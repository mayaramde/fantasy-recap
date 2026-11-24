/* ---------- Coach's league-wide modules ----------
   The markup for "Around the league" on the This week / Live tab (weekLeague) and the Coach tab's
   name picker (clPickCard).
   Browser-side only (it reads the page's own data and helpers), inlined into template.html by
   site/build.py after the pure insight functions in this folder. Read-only: nothing here
   changes a lineup or claims a trade. A module whose inputs aren't there is left out. */
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
   This week has nobody open, so it only ever lights "you"; `view` is kept for a caller that has one. */
const clTone = (id, me, view) => (id === me ? ' me' : view != null && id === view ? ' view' : '');
const clTag = (id, me, view) => (id === me ? clYou(true) : view != null && id === view ? '<span class="cl-viewing">Viewing</span>' : '');
/* A name that opens that team's profile. role=button, not a link: the router handles the tap
   (and Enter / Space) in template.html, so a name inside a table row or list item stays valid markup. */
const clOpen = (id, name) => `role="button" tabindex="0" data-open-team="${id}" title="Open ${esc(name)}'s team"`;

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

/* AVG's fill runs lime (the best lineup) through white to pink (the weakest), the same lime and
   pink as the League best / League worst rows under it. Fixed colors with ink text, like the blue
   spot cells, so it reads the same in dark mode. */
function clAvgTone(overall, n) {
  const t = n > 1 ? (overall - 1) / (n - 1) : 0;
  const [pop, pct] = t <= 0.5 ? ['#c7f04a', Math.round((1 - 2 * t) * 100)] : ['#ff6fb5', Math.round((2 * t - 1) * 100)];
  return `background: color-mix(in srgb, ${pop} ${pct}%, #ffffff)`;
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
      <td class="avg" title="${esc(`${r.manager}: average rank ${r.avg.toFixed(1)}, ${ord(r.overall)} best lineup of ${n}`)}" aria-label="${esc(`${r.manager}: average rank ${r.avg.toFixed(1)}, ${ord(r.overall)} best lineup of ${n}`)}"><div class="cl-hc cl-avg" style="${clAvgTone(r.overall, n)}" aria-hidden="true">${r.overall === 1 ? '<i class="cl-trophy">🏆</i>' : ''}<span>${r.avg.toFixed(1)}</span><span class="cl-meter"><i style="width:${r.meter}%"></i></span></div></td></tr>`).join('');
  const foot = (cls, label, by) => `<tr class="${cls}"><th scope="row">${label}</th>${sm.cols.map((c) => `<td title="${esc(`${label} at ${CL_NAME[c]}: ${by[c] || 'nobody'}`)}"><span>${esc(by[c] || '')}</span></td>`).join('')}<td class="avg"></td></tr>`;
  return `
    <div class="cl-heat table-scroll" role="region" aria-label="Lineup spot rankings, scrolls sideways" tabindex="0">
      <table><thead><tr><th scope="col">Manager</th>${sm.cols.map((c) => `<th scope="col" title="${CL_NAME[c]}">${c}</th>`).join('')}<th scope="col" class="avg" title="Average rank across the seven spots. Lower is stronger: the darker the cell and the fuller its bar, the better the lineup.">AVG<small class="cl-lower">lower = better</small></th></tr></thead>
        <tbody>${body}</tbody>
        <tfoot>${foot('best', 'League best', sm.bestBy)}${foot('worst', 'League worst', sm.worstBy)}</tfoot></table>
    </div>
    <p class="cl-key"><span class="cl-corner best" aria-hidden="true">${CL_ICON.up}</span>best spot <span class="cl-corner weak" aria-hidden="true">${CL_ICON.down}</span>weakest spot · 1 is the league's best, ${n} the worst <span class="cl-key-avg">AVG: <span class="cl-swatch lime" aria-hidden="true"></span>strongest lineup <span class="cl-swatch pink" aria-hidden="true"></span>weakest · a fuller bar is stronger</span></p>`;
}

function clCallouts(list) {
  if (!list.length) return '';
  return `<ul class="cl-callouts">${list.map((c) => `
    <li class="${c.kind}"><h3>${esc(c.title)}</h3><ul>${c.items.map((i) => `<li><b>${esc(i.manager)}</b> ${esc(i.text)}</li>`).join('')}</ul></li>`).join('')}</ul>`;
}

function clTrades(cards) {
  // One spot per line: a run-on "RB 7th · DST 7th · K 7th" wraps mid-list in a narrow side.
  const col = (label, xs) => `<div><span class="cl-col-l">${label}</span>${xs.map((x) => `<b>${x.spot} ${ordinal(x.rank)}</b>`).join('')}</div>`;
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

/* "Make this page yours": the whole Coach tab for someone who hasn't picked a name, since Coach is
   always one team's report. The pink ! is the same homework signal as the profile's Switch team
   sheet (fixes waiting). */
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


/* The strength grid at panel size, for This week: the same blue rank cells and lime-to-pink AVG as
   clStrength, best lineup on top (ties keep standings order), without the corner stickers or the
   League best / worst rows. */
function clMiniStrength(sm, me, n) {
  const rows = [...sm.rows].sort((a, b) => a.overall - b.overall);
  const body = rows.map((r) => `
      <tr${r.id === me ? ' class="me"' : ''}><th scope="row"><span class="cl-go" ${clOpen(r.id, r.manager)}>${esc(r.manager)}</span>${r.id === me ? '<span class="vh"> (you)</span>' : ''}</th>
        ${sm.cols.map((c) => `<td><span class="cl-hc h${r.ranks[c]}" title="${esc(`${r.manager} at ${CL_NAME[c]}: ${ordinal(r.ranks[c])} of ${n}`)}">${r.ranks[c]}</span></td>`).join('')}
        <td class="avg"><span class="ls-avg" style="${clAvgTone(r.overall, n)}" title="${esc(`${r.manager}: average rank ${r.avg.toFixed(1)}, ${ordinal(r.overall)} best lineup of ${n}`)}">${r.avg.toFixed(1)}</span></td></tr>`).join('');
  return `
    <div class="cl-card ls-mini table-scroll" role="region" aria-label="Lineup spot rankings" tabindex="0">
      <table>
        <thead><tr><th scope="col"><span class="vh">Manager</span></th>${sm.cols.map((c) => `<th scope="col" title="${CL_NAME[c]}">${c}</th>`).join('')}<th scope="col" class="avg" title="Average rank across the seven spots. Lower is stronger.">AVG</th></tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

/* "Around the league" on the This week / Live tab: the league-wide modules that used to open the
   Coach tab for anyone who hadn't picked a team. Where the week gets decided (only before kickoff:
   it reads pre-game projections, which a game in progress has already moved past; the Live page passes
   `decided: false`), the waiver order (the League wire above it already counts pickups, so this one
   doesn't), where everyone's strong and the trade matchmaker. Always this week: `rows` are this
   week's Coach rows, which only the trade matchmaker needs (to skip a spot that's empty or on a bye).
   Nothing to show, nothing drawn. */
function weekLeague(w, rows, me, { decided = !w.complete } = {}) {
  const stand = SEASON.standings || [];
  const n = stand.length;
  const teams = rows.length ? clTeams(rows) : [];
  const sm = n && stand.every((t) => t.profile && t.profile.pos_ranks)
    ? strengthMap(stand.map((t) => ({ id: t.team_id, manager: t.manager, ranks: t.profile.pos_ranks }))) : null;
  const b = decided ? battles(clGames(false, rows)) : null;
  const order = SEASON.waiver_order ? SEASON.waiver_order.map((id) => TEAMS[id]).filter(Boolean) : [...stand].reverse();
  const trades = sm ? tradeMatches(sm.rows, unavailableSpots(teams)) : [];
  const calls = sm ? callouts(sm.rows, n) : [];
  const duo = [
    b && b.edges.length ? clSection('orange', 'Where the week gets decided', clBattles(b, me), 'The biggest projected gaps at a single lineup spot, across every game.') : '',
    order.length ? clSection('cobalt', 'Waiver order this week', clWaiver(order, me, null), 'Worst record picks first. The order resets every week.') : '',
  ].filter(Boolean);
  const body = [
    duo.length ? `<div class="cl-duo wx">${duo.join('')}</div>` : '',
    sm ? clSection('cobalt', "Where everyone's strong", `<div class="ls-strong">${clMiniStrength(sm, me, n)}${clCallouts(calls)}</div>`,
      `Today's starters, ranked 1 to ${n} at every lineup spot on their last three weeks. 1 is the league's best. AVG is the average of the seven, so lower is stronger.`) : '',
    trades.length ? clSection('lime', 'Trade matchmaker', clTrades(trades), 'Pairs whose weak spots line up with each other\'s strengths.') : '',
  ].join('');
  return body ? `<div class="cl-page wk-league">${body}</div>` : '';
}
