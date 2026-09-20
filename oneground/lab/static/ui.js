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
  const OUTCOMES = ['meets', 'fails', 'couldnt_check'];

  // ONE SHAPE, FOUR CASES. A column that reads "0 · 6 · 2" on three rows and
  // a sentence on the fourth is honest and unscannable: an eye cannot compare
  // two registers. So every case is three boxes in the same three positions,
  // and an absent count is an em-dash rather than a zero — a zero would say
  // the constraint was checked and did not hold. The word that distinguishes
  // the absent cases goes underneath, labelling the dashes rather than
  // replacing them.
  function outcomeCounts(counts, absentBecause) {
    const box = el('div', 'counts-cell');
    const ul = el('ul', 'counts');
    OUTCOMES.forEach((name) => {
      const found = (counts || []).find((c) => c.outcome === name);
      const li = el('li', 'count outcome-' + name
        + (found ? '' : ' count-absent'));
      li.appendChild(el('span', 'count-n', found ? found.n : '—'));
      li.appendChild(el('span', 'count-label', label(name)));
      ul.appendChild(li);
    });
    box.appendChild(ul);
    if (!counts) {
      box.appendChild(el('p', 'counts-why',
        absentBecause || 'no outcome counts recorded'));
    }
    return box;
  }

  // A value a receipt recorded as a couldn't-check sentence, rendered in the
  // register the outcome boxes use rather than as raw text. The fact was
  // right; the voice was wrong.
  function recordedValue(v) {
    if (typeof v === 'string' && v.indexOf('couldnt_check') === 0) {
      const why = v.slice(v.indexOf(':') + 1).trim();
      const s = el('span', 'cc-chip');
      s.appendChild(el('span', 'cc-mark', "couldn't check"));
      if (why) s.appendChild(el('span', 'cc-why', why));
      return s;
    }
    if (v === null || v === undefined) return el('span', 'absent', '—');
    return el('span', null, String(v));
  }

  function label(outcome) {
    if (outcome === 'couldnt_check') return "couldn't check";
    return outcome;
  }

  // The contract requires every gap reason to begin with the machine token
  // `couldnt_check:` so that `check_drawing` can verify it. That token is a
  // check, not a sentence, and a panel already headed "couldn't check" should
  // not then say it again in lower case with an underscore. Stripped here,
  // where the heading supplies it.
  function reasonText(s) {
    if (typeof s !== 'string') return s;
    return s.replace(/^\s*couldnt_check\s*:\s*/i, '');
  }

  function gapsList(gaps) {
    const ul = el('ul', 'gaps');
    Object.keys(gaps || {}).forEach((name) => {
      const li = el('li');
      li.appendChild(el('span', 'gap-name', "couldn't check · "
        + name.replace(/_/g, ' ')));
      li.appendChild(el('span', 'gap-why', reasonText(gaps[name])));
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
    // The directory is named once, in the header, and not repeated here.
    // It was printed twice, and at 500px that was four lines of a phone
    // screen spent on a path before any content.
    h.appendChild(el('p', 'sub', d.figures.n_runs
      + ' run(s) · each verified against its own MANIFEST'));
    main.appendChild(h);

    // Someone else's corpus, said in the view rather than as fine print, and
    // placed above the runs so a screenshot of the table carries it.
    if (d.figures.demo) {
      const dm = el('section', 'demo-banner');
      dm.appendChild(el('p', 'demo-label', d.figures.demo.label));
      dm.appendChild(el('p', 'demo-note', d.figures.demo.fetched_note));
      dm.appendChild(el('p', 'demo-gap',
        'not available here: ' + d.figures.demo.not_available));
      dm.appendChild(el('p', 'demo-way-out', d.figures.demo.way_out));
      main.appendChild(dm);
    }
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

    // Every cell carries the name of its column. At table width the header
    // row names them; below 40rem the rows become cards and the header is
    // gone, so a card has to name its own values — "2000" and
    // "characterize · verify" mean nothing bare.
    function cell(labelText, cls) {
      const td = el('td', cls);
      td.setAttribute('data-label', labelText);
      return td;
    }

    rowsOf(d.marks[0]).forEach((r) => {
      const tr = el('tr', r.verified === true ? null : 'row-unverified');
      const name = cell('run');
      const a = el('a', 'run-link', r.name);
      a.href = '#/run/' + encodeURIComponent(r.name);
      name.appendChild(a);
      tr.appendChild(name);

      const corpus = cell('corpus', 'corpus');
      corpus.appendChild(recordedValue(r.n_base));
      tr.appendChild(corpus);

      const stages = cell('stages', 'stages');
      stages.textContent = (r.stages || []).join(' · ') || '—';
      tr.appendChild(stages);

      const out = cell('outcome', 'outcome-cell');
      out.appendChild(r.counted
        ? outcomeCounts([{ outcome: 'meets', n: r.meets },
                         { outcome: 'fails', n: r.fails },
                         { outcome: 'couldnt_check', n: r.couldnt_check }])
        : outcomeCounts(null, 'this run has not reported'));
      tr.appendChild(out);

      const ver = cell('version', 'version');
      if (r.version) { ver.textContent = r.version; } else {
        // Not a link and not styled as one: it opens nothing.
        const s = el('span', 'unknown', 'not recorded');
        s.title = r.version_reason || '';
        ver.appendChild(s);
      }
      tr.appendChild(ver);

      const dig = cell('digests', 'digests');
      if (r.verified === true) dig.appendChild(el('span', 'ok', 'verified'));
      else if (r.verified === false) {
        dig.appendChild(el('span', 'bad', 'fails'));
        dig.appendChild(el('span', 'bad-which', (r.failing || []).join(', ')));
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
      finding.appendChild(outcomeCounts(
        d.figures.counts, 'this report records no outcome counts'));
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
  // THE REPORT PAGE LEADS WITH THE FINDING AND OPENS ITS EVIDENCE ON DEMAND.
  //
  // The first build rendered every citation of all 37 claims inline at one
  // density, and the page became a wall. That defeated the rule it was built
  // to serve: equal weight stops a refusal being *quieter* than a verdict, and
  // it does nothing when nothing on the page is quiet. A couldn't-check was
  // invisible among 37 equally loud rows.
  //
  // So: the conclusion first, the same sentence the run page leads with; then
  // one line per claim, its outcome and its sentence and nothing else; and the
  // evidence behind a claim only when a reader asks for that claim. Evidence
  // on demand is what makes the click informative, which is the whole
  // argument for having a drawer rather than a table.
  async function showReport(name) {
    const mine = routeSeq;
    const main = $('ui-main');
    main.textContent = '';
    const h = el('header', 'page-head');
    const back = el('a', 'back', '\u2190 ' + name);
    back.href = '#/run/' + encodeURIComponent(name);
    h.appendChild(back);
    h.appendChild(el('h1', null, 'The report'));
    main.appendChild(h);

    let d, head;
    try {
      [head, d] = await Promise.all([
        api('/api/headline', { run: name }),
        api('/api/evidence', { run: name }),
      ]);
    } catch (e) {
      if (mine === routeSeq) {
        main.appendChild(el('p', 'not-reported', e.message));
      }
      return;
    }
    if (mine !== routeSeq) return;

    // 1. What the run concluded, so a reader arriving here does not have to
    //    reconstruct it from the rows below.
    if (head.figures && head.figures.headline) {
      const lead = el('section', 'finding');
      lead.appendChild(el('p', 'headline', head.figures.headline));
      lead.appendChild(outcomeCounts(
        head.figures.counts, 'this report records no outcome counts'));
      main.appendChild(lead);
    }

    // 2. What is below, counted. Claims are not constraints -- one constraint
    //    can be claimed once per option -- so this says "claims" and the
    //    panel above says constraints, and neither is presented as the other.
    const by = d.figures.by_outcome || {};
    main.appendChild(el('p', 'sub',
      d.figures.n_claims + ' claims carrying ' + d.figures.n_entries
      + ' citations \u00b7 ' + (by.meets || 0) + ' meets, '
      + (by.fails || 0) + ' fails, ' + (by.couldnt_check || 0)
      + " couldn't check, " + (by.no_verdict || 0)
      + ' stating no verdict'));

    if (d.figures.disagreeing && d.figures.disagreeing.length) {
      main.appendChild(el('p', 'unverified-banner',
        'a cited figure and the field it names disagree: '
        + Array.from(new Set(d.figures.disagreeing)).join(', ')));
    }

    // 3. One line per claim. The evidence is inside a closed disclosure, so
    //    the page is scannable and a click is worth making.
    const claims = rowsOf(d.marks[0]);
    const entries = rowsOf(d.marks[1]);
    const list = el('ol', 'claims');
    claims.forEach((c) => {
      const li = el('li', 'claim');
      const box = document.createElement('details');
      box.className = 'claim-box'
        + (c.outcome_shown ? ' outcome-' + c.outcome_shown : ' no-verdict');
      const sum = document.createElement('summary');
      sum.className = 'claim-summary';
      sum.appendChild(el('span', 'claim-mark',
        c.outcome_shown ? label(c.outcome_shown) : 'note'));
      sum.appendChild(el('span', 'claim-text', c.text));
      sum.appendChild(el('span', 'claim-count',
        c.n_entries + (c.n_entries === 1 ? ' citation' : ' citations')));
      box.appendChild(sum);

      const drawer = el('ul', 'drawer');
      entries.filter((e) => e.claim === c.index).forEach((e) => {
        const row = el('li', 'entry entry-' + e.kind
          + (e.navigable ? ' navigable' : ' not-navigable')
          + (e.agrees === false ? ' disagrees' : ''));
        row.appendChild(el('span', 'entry-source', e.source || '(none)'));
        if (e.navigable) {
          row.appendChild(el('span', 'entry-value',
            'cited ' + shortJSON(e.cited_value)
            + ' \u00b7 field holds ' + shortJSON(e.field_value)));
          if (e.within) {
            row.appendChild(el('span', 'entry-note',
              'the source names the block; the figure is its ' + e.within));
          }
          if (e.agrees === false) {
            row.appendChild(el('span', 'entry-bad', 'these do not agree'));
          }
        } else {
          row.appendChild(el('span', 'entry-kind', e.kind.replace(/_/g, ' ')));
          row.appendChild(el('span', 'entry-note', reasonText(e.note) || ''));
        }
        drawer.appendChild(row);
      });
      if (c.remedy && c.remedy.remedy) {
        const r = el('li', 'entry entry-remedy');
        r.appendChild(el('span', 'entry-kind', 'what would settle it'));
        r.appendChild(el('span', 'entry-note', reasonText(c.remedy.remedy)));
        drawer.appendChild(r);
      }
      box.appendChild(drawer);
      li.appendChild(box);
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
    claimBoxes: document.querySelectorAll('details.claim-box').length,
    openBoxes: document.querySelectorAll('details.claim-box[open]').length,
    navigable: document.querySelectorAll('.entry.navigable').length,
    joinedTables: document.querySelectorAll('table.joined').length,
    demoBanner: document.querySelectorAll('.demo-banner').length,
    observations: document.querySelectorAll('.observation').length,
    verdict: (document.querySelector('.verdict-name') || {}).textContent
      || null,
  });
})();
