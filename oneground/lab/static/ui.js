// The read half, over many runs (task 041).
//
// Four pages, all renderings of drawings the server made: the run list, one
// run's finding, its report with the evidence drawer, and two runs side by
// side under the comparability verdict. Nothing here computes a measurement,
// and nothing here runs anything: there is no POST in this file.
//
// THE ONE RULE THIS FILE IS HELD TO
// ---------------------------------
// Layout drifts; structure does not. Where a guarantee could live either in
// the drawing or in this file, it lives in the drawing, and this file renders
// what it is given:
//
//   * the three outcome counts arrive as three entries, always, in one order,
//     so this file loops over them and cannot drop the zero;
//   * a comparison arrives as one joined mark only when the verdict permits
//     it, so this file cannot line up two runs it was not handed together;
//   * a drawer entry arrives with `navigable`, so a non-field citation cannot
//     be rendered as a link that does nothing.
(() => {
  'use strict';
  const TOKEN = document.querySelector(
    'meta[name="oneground-lab-token"]').content;
  const $ = (id) => document.getElementById(id);

  let check = null;
  let runList = null;
  let lastError = null;
  // Which navigation is current. Two routes can be in flight at once -- a
  // hashchange during a fetch -- and both used to clear the page and then
  // append to it, so the slower one's output landed under the faster one's:
  // the finding page rendered its three counts twice. A sequence number,
  // checked after every await, keeps only the newest.
  let routeSeq = 0;

  async function api(path, params) {
    // Built by appending, not from an object: URLSearchParams({run: [a, b]})
    // yields `run=a,b` -- one parameter holding a comma -- and /api/compare
    // correctly refuses that as "name two runs". A real browser found this;
    // every endpoint had answered correctly over HTTP.
    const q = new URLSearchParams();
    Object.keys(params || {}).forEach((k) => {
      const v = params[k];
      if (Array.isArray(v)) v.forEach((one) => q.append(k, one));
      else q.append(k, v);
    });
    q.set('token', TOKEN);
    const r = await fetch(path + '?' + q.toString(),
                          { headers: { 'Accept': 'application/json' } });
    const body = await r.json().catch(() => ({ error: 'unreadable answer' }));
    if (!r.ok) throw new Error(body.error || (path + ' answered ' + r.status));
    return body;
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }

  function rowsOf(mark) {
    if (!mark) return [];
    const keys = Object.keys(mark.data);
    const n = keys.length ? mark.data[keys[0]].length : 0;
    const out = [];
    for (let i = 0; i < n; i += 1) {
      const row = {};
      keys.forEach((k) => { row[k] = mark.data[k][i]; });
      out.push(row);
    }
    return out;
  }

  function fatal(message) {
    lastError = message;
    const f = $('fatal');
    f.textContent = message;
    f.hidden = false;
  }

  function clearFatal() { $('fatal').hidden = true; lastError = null; }

  // --- the three outcomes, always all three ------------------------------
  // `counts` is a list of {outcome, n} the server always sends in full. This
  // renders every entry it is given and has no branch that skips one, so a
  // zero cannot be dropped here even by mistake.
  function outcomeCounts(counts) {
    const ul = el('ul', 'counts');
    if (!counts) {
      ul.appendChild(el('li', 'counts-gap', 'no outcome counts recorded'));
      return ul;
    }
    counts.forEach((c) => {
      const li = el('li', 'count outcome-' + c.outcome);
      li.appendChild(el('span', 'count-n', c.n));
      li.appendChild(el('span', 'count-label', label(c.outcome)));
      ul.appendChild(li);
    });
    return ul;
  }

  function label(outcome) {
    if (outcome === 'couldnt_check') return "couldn't check";
    return outcome;
  }

  function gapsList(gaps) {
    const ul = el('ul', 'gaps');
    Object.keys(gaps || {}).forEach((name) => {
      const li = el('li');
      li.appendChild(el('span', 'gap-name', name));
      li.appendChild(el('span', 'gap-why', gaps[name]));
      ul.appendChild(li);
    });
    return ul;
  }

  // --- page: the run list -------------------------------------------------
  async function showRuns() {
    const mine = routeSeq;
    const d = runList || (runList = await api('/api/runs'));
    if (mine !== routeSeq) return;
    const main = $('ui-main');
    main.textContent = '';
    const h = el('header', 'page-head');
    h.appendChild(el('h1', null, 'Runs'));
    h.appendChild(el('p', 'sub', d.figures.directory + ' · '
      + d.figures.n_runs + ' run(s) · each verified against its own MANIFEST'));
    main.appendChild(h);

    if (d.figures.unverified && d.figures.unverified.length) {
      const w = el('p', 'unverified-banner',
        'digests do not verify for: ' + d.figures.unverified.join(', ')
        + ' — listed below, and not to be read as sound');
      main.appendChild(w);
    }
    if (d.gaps && d.gaps.runs) {
      main.appendChild(gapsList(d.gaps));
      return;
    }

    const table = el('table', 'runs');
    const head = el('tr');
    ['run', 'corpus', 'stages', 'outcome', 'version', 'digests']
      .forEach((c) => head.appendChild(el('th', null, c)));
    table.appendChild(head);

    rowsOf(d.marks[0]).forEach((r) => {
      const tr = el('tr', r.verified === true ? null : 'row-unverified');
      const name = el('td');
      const a = el('a', 'run-link', r.name);
      a.href = '#/run/' + encodeURIComponent(r.name);
      name.appendChild(a);
      tr.appendChild(name);

      tr.appendChild(el('td', 'corpus',
        r.n_base === null || r.n_base === undefined ? '—' : r.n_base));
      tr.appendChild(el('td', 'stages', (r.stages || []).join(' · ') || '—'));

      const out = el('td', 'outcome-cell');
      if (r.counted) {
        out.appendChild(outcomeCounts([
          { outcome: 'meets', n: r.meets },
          { outcome: 'fails', n: r.fails },
          { outcome: 'couldnt_check', n: r.couldnt_check }]));
      } else {
        // Not three zeros: three zeros would say every constraint was
        // checked and none held.
        out.appendChild(el('span', 'not-reported', 'has not reported'));
      }
      tr.appendChild(out);

      const ver = el('td', 'version');
      if (r.version) { ver.textContent = r.version; } else {
        const s = el('span', 'unknown', 'not recorded');
        s.title = r.version_reason || '';
        ver.appendChild(s);
      }
      tr.appendChild(ver);

      const dig = el('td', 'digests');
      if (r.verified === true) dig.appendChild(el('span', 'ok', 'verified'));
      else if (r.verified === false) {
        dig.appendChild(el('span', 'bad',
          'FAILS: ' + (r.failing || []).join(', ')));
      } else {
        const s = el('span', 'unknown', "couldn't check");
        s.title = r.manifest_note || '';
        dig.appendChild(s);
      }
      tr.appendChild(dig);
      table.appendChild(tr);
    });
    main.appendChild(table);
    main.appendChild(comparePicker(rowsOf(d.marks[0]).map((r) => r.name)));
  }

  function comparePicker(names) {
    const box = el('section', 'compare-picker');
    box.appendChild(el('h2', null, 'Two runs, side by side'));
    box.appendChild(el('p', 'sub',
      'shown only under the comparability verdict (docs/LIBRARY.md §2.2)'));
    const a = el('select'); const b = el('select');
    names.forEach((n) => {
      [a, b].forEach((s) => {
        const o = document.createElement('option');
        o.value = n; o.textContent = n; s.appendChild(o);
      });
    });
    if (names.length > 1) b.selectedIndex = 1;
    const go = el('button', null, 'Compare');
    go.type = 'button';
    go.addEventListener('click', () => {
      window.location.hash = '#/compare/' + encodeURIComponent(a.value)
        + '/' + encodeURIComponent(b.value);
    });
    box.appendChild(a); box.appendChild(b); box.appendChild(go);
    return box;
  }

  // --- page: one run's finding -------------------------------------------
  async function showRun(name) {
    const mine = routeSeq;
    const d = await api('/api/headline', { run: name });
    if (mine !== routeSeq) return;
    const main = $('ui-main');
    main.textContent = '';

    const h = el('header', 'page-head');
    const back = el('a', 'back', '← all runs');
    back.href = '#/runs';
    h.appendChild(back);
    h.appendChild(el('h1', null, name));
    main.appendChild(h);

    const finding = el('section', 'finding');
    if (d.view === 'run_progress') {
      finding.appendChild(el('p', 'headline',
        'This run has not reported.'));
      finding.appendChild(el('p', 'sub',
        'furthest stage: ' + (d.figures.furthest_stage || 'none')));
      if (d.figures.next_command) {
        finding.appendChild(el('p', 'next',
          'next: ' + d.figures.next_command));
      }
    } else {
      finding.appendChild(el('p', 'headline', d.figures.headline || '—'));
      const src = el('p', 'source');
      src.appendChild(el('span', 'source-label', 'from '));
      src.appendChild(el('code', null, d.figures.headline_source || '—'));
      if (d.figures.from_rule) {
        src.appendChild(el('span', 'from-rule',
          ' — a rule, not a row'));
      }
      finding.appendChild(src);
      finding.appendChild(outcomeCounts(d.figures.counts));
    }
    finding.appendChild(gapsList(d.gaps));
    main.appendChild(finding);

    const nav = el('nav', 'run-tabs');
    const rep = el('a', null, 'The report, with its evidence');
    rep.href = '#/run/' + encodeURIComponent(name) + '/report';
    nav.appendChild(rep);
    main.appendChild(nav);
  }

  // --- page: the report, with the evidence drawer -------------------------
  async function showReport(name) {
    const mine = routeSeq;
    const main = $('ui-main');
    main.textContent = '';
    const h = el('header', 'page-head');
    const back = el('a', 'back', '← ' + name);
    back.href = '#/run/' + encodeURIComponent(name);
    h.appendChild(back);
    h.appendChild(el('h1', null, 'The report'));
    main.appendChild(h);

    let d;
    try {
      d = await api('/api/evidence', { run: name });
    } catch (e) {
      if (mine === routeSeq) {
        main.appendChild(el('p', 'not-reported', e.message));
      }
      return;
    }
    if (mine !== routeSeq) return;

    const kinds = d.figures.entry_kinds || {};
    const sum = el('p', 'sub',
      d.figures.n_claims + ' claim(s), ' + d.figures.n_entries
      + ' citation(s) · '
      + Object.keys(kinds).filter((k) => kinds[k])
          .map((k) => kinds[k] + ' ' + k).join(' · '));
    main.appendChild(sum);

    if (d.figures.disagreeing && d.figures.disagreeing.length) {
      main.appendChild(el('p', 'unverified-banner',
        'a cited figure and the field it names disagree: '
        + Array.from(new Set(d.figures.disagreeing)).join(', ')));
    }

    const claims = rowsOf(d.marks[0]);
    const entries = rowsOf(d.marks[1]);
    const list = el('ol', 'claims');
    claims.forEach((c) => {
      const li = el('li', 'claim kind-' + c.kind);
      const text = el('p', 'claim-text', c.text);
      li.appendChild(text);

      const mine = entries.filter((e) => e.claim === c.index);
      const drawer = el('ul', 'drawer');
      mine.forEach((e) => {
        const d1 = el('li', 'entry entry-' + e.kind
          + (e.navigable ? ' navigable' : ' not-navigable')
          + (e.agrees === false ? ' disagrees' : ''));
        const src = el('span', 'entry-source', e.source || '(none)');
        d1.appendChild(src);
        if (e.navigable) {
          const v = el('span', 'entry-value');
          v.textContent = 'cited ' + JSON.stringify(e.cited_value)
            + ' · field holds ' + shortJSON(e.field_value);
          d1.appendChild(v);
          if (e.within) {
            d1.appendChild(el('span', 'entry-note',
              'the source names the block; the figure is its ' + e.within));
          }
          if (e.agrees === false) {
            d1.appendChild(el('span', 'entry-bad',
              'these do not agree'));
          }
        } else {
          // Never a link that does nothing: the kind is named and the
          // sentence says what kind of thing it is.
          d1.appendChild(el('span', 'entry-kind', e.kind));
          d1.appendChild(el('span', 'entry-note', e.note || ''));
        }
        drawer.appendChild(d1);
      });
      if (c.remedy && c.remedy.remedy) {
        const r = el('li', 'entry entry-remedy');
        r.appendChild(el('span', 'entry-kind', 'what would settle it'));
        r.appendChild(el('span', 'entry-note', c.remedy.remedy));
        drawer.appendChild(r);
      }
      li.appendChild(drawer);
      list.appendChild(li);
    });
    main.appendChild(list);
    main.appendChild(gapsList(d.gaps));
  }

  function shortJSON(v) {
    const s = JSON.stringify(v);
    if (s === undefined) return 'null';
    return s.length > 120 ? s.slice(0, 117) + '…' : s;
  }

  // --- page: two runs -----------------------------------------------------
  async function showCompare(a, b) {
    const mine = routeSeq;
    const main = $('ui-main');
    main.textContent = '';
    const h = el('header', 'page-head');
    const back = el('a', 'back', '← all runs');
    back.href = '#/runs';
    h.appendChild(back);
    h.appendChild(el('h1', null, 'Two runs'));
    main.appendChild(h);

    const d = await api('/api/compare', { run: [a, b] });
    if (mine !== routeSeq) return;
    const v = d.figures.verdict;
    const verdict = el('section', 'verdict verdict-' + v);
    verdict.appendChild(el('p', 'verdict-name', v.replace('_', ' ')));
    verdict.appendChild(el('p', 'verdict-means', d.figures.means || ''));
    verdict.appendChild(el('p', 'verdict-why', d.figures.reason || ''));
    main.appendChild(verdict);

    const table = el('table', 'ingredients');
    const head = el('tr');
    ['ingredient', 'state', 'required', a, b]
      .forEach((c) => head.appendChild(el('th', null, c)));
    table.appendChild(head);
    rowsOf(d.marks[0]).forEach((r) => {
      const tr = el('tr', 'state-' + r.state);
      tr.appendChild(el('td', null, r.ingredient));
      tr.appendChild(el('td', null, r.state));
      tr.appendChild(el('td', null, r.required ? 'required' : 'optional'));
      tr.appendChild(el('td', 'side', shortJSON(r.left)));
      tr.appendChild(el('td', 'side', shortJSON(r.right)));
      if (r.note) {
        const why = el('tr', 'ingredient-note');
        const td = el('td', null, r.note);
        td.colSpan = 5;
        why.appendChild(td);
        table.appendChild(tr);
        table.appendChild(why);
        return;
      }
      table.appendChild(tr);
    });
    main.appendChild(table);

    if (d.figures.paired) {
      // Only reachable when the verdict permits it: the server sent one mark
      // holding both runs, and that is the only way this branch has data.
      const joined = d.marks.find(
        (m) => m.data.left && m.data.right && !m.data.ingredient);
      const t = el('table', 'joined');
      rowsOf(joined).forEach((r) => {
        const tr = el('tr');
        tr.appendChild(el('td', null, r.field));
        tr.appendChild(el('td', null, shortJSON(r.left)));
        tr.appendChild(el('td', null, shortJSON(r.right)));
        t.appendChild(tr);
      });
      main.appendChild(t);
    } else {
      main.appendChild(el('p', 'two-observations',
        'Two observations, kept apart'));
      const wrap = el('div', 'observations');
      d.marks.slice(1).forEach((m) => {
        rowsOf(m).forEach((r) => {
          const card = el('article', 'observation');
          card.appendChild(el('h3', null, r.run));
          card.appendChild(el('p', 'sub',
            'corpus ' + shortJSON(r.n_base) + ' · tier ' + r.tier));
          if (r.headline) card.appendChild(el('p', 'headline', r.headline));
          wrap.appendChild(card);
        });
      });
      main.appendChild(wrap);
      main.appendChild(gapsList(d.gaps));
    }
  }

  // --- routing ------------------------------------------------------------
  async function route() {
    const mine = ++routeSeq;
    clearFatal();
    const h = window.location.hash || '#/runs';
    const parts = h.replace(/^#\//, '').split('/').map(decodeURIComponent);
    try {
      if (parts[0] === 'run' && parts[2] === 'report') {
        await showReport(parts[1]);
      } else if (parts[0] === 'run' && parts[1]) {
        await showRun(parts[1]);
      } else if (parts[0] === 'compare' && parts[2]) {
        await showCompare(parts[1], parts[2]);
      } else {
        await showRuns();
      }
    } catch (e) {
      if (mine === routeSeq) fatal(e.message);
    }
  }

  async function boot() {
    check = await api('/api/check');
    document.querySelector('.run-name').textContent =
      check.runs_dir + ' · ' + check.n_runs + ' run(s)';
    document.querySelector('.eyebrow').textContent =
      'oneground ui · served from this machine · read-only · '
      + 'nothing runs from this page';
    const tabs = document.querySelector('.tabs');
    if (tabs) tabs.remove();
    const lab = document.getElementById('lab-panels');
    if (lab) lab.remove();
    window.addEventListener('hashchange', route);
    await route();
  }

  boot().catch((e) => fatal(e.message));

  // For the browser-driven test: what the page believes it has rendered.
  window.__uiState = () => ({
    mode: window.__ONEGROUND_MODE__ || null,
    hasCheck: !!check,
    hash: window.location.hash,
    error: lastError,
    runRows: document.querySelectorAll('table.runs tr').length,
    counts: Array.from(document.querySelectorAll('.counts .count'))
      .map((n) => n.className),
    notNavigable: document.querySelectorAll('.entry.not-navigable').length,
    navigable: document.querySelectorAll('.entry.navigable').length,
    joinedTables: document.querySelectorAll('table.joined').length,
    observations: document.querySelectorAll('.observation').length,
    verdict: (document.querySelector('.verdict-name') || {}).textContent
      || null,
  });
})();
