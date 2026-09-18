/* oneground lab — the interface.
 *
 * It asks the server for drawings and paints them. It computes no figure of
 * its own: every number on the page is a figure the view stated, and every
 * caption is the view's own. Where a drawing reports a gap, the gap is shown
 * rather than filled.
 *
 * Structure
 *   boot()        load the run, the receipts, and the first drawings
 *   route()       #/overview, #/ground, #/trace — one epsilon across all three
 *   epsilon       one control, shared; ticks mark the simulated values
 *   ground()      canvas, readouts, copies legend, caption, gaps
 *   trace()       picker over /api/query-index, four hops, recall panel
 *
 * Two rules this file must not break:
 *   - Nothing between simulated epsilon values is interpolated. The recall
 *     panel renders whatever `panels.recall` says and never fills a blank.
 *   - In `render on release` the epsilon on screen is named whenever it is not
 *     the epsilon the control is at, so a screenshot cannot mislead.
 */
'use strict';

(function () {
  const TOKEN = document.querySelector('meta[name="oneground-lab-token"]').content;
  const RAMP = ['#3D7EB8', '#7FA3B0', '#B79C63', '#E0A83A'];
  const SLATE = [0x1B, 0x24, 0x32];
  const DIM = [0x2A, 0x33, 0x40];         // a vector filtered out of view
  const MOVE = 'redraw on move';
  const STATIC = 'no epsilon control';
  const NOT_SIM = 'not simulated at this epsilon';
  const GUTTER = 3;                       // the widest outline's weight
  const QLIST_MAX = 250;                  // rows built at once; the rest on ask

  // ------------------------------------------------------------- elements
  // `need` names the element it could not find. The previous version of this
  // file called `el.textContent = …` on whatever getElementById returned, so a
  // renamed id threw "Cannot set properties of null" from inside boot, and the
  // catch that was meant to report it threw the same way before it could. The
  // page then sat on "Loading the run…" with nothing said. Every lookup that
  // must succeed goes through `need`, and `fail` below cannot itself throw.
  const $ = (id) => document.getElementById(id);
  function need(id) {
    const el = document.getElementById(id);
    if (!el) throw new Error(`the interface is missing #${id}: index.html and lab.js disagree`);
    return el;
  }
  function text(el, value) { if (el) el.textContent = value; return el; }
  function make(tag, cls, value) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (value !== undefined) el.textContent = value;
    return el;
  }
  const fmtInt = (n) => Number(n).toLocaleString('en-US');
  const fmtEps = (e) => (e === null || e === undefined ? '—' : Number(e).toFixed(3));
  const epsList = (values) => (values || []).map((e) => Number(e)).join(', ');

  function hex(h) {
    const v = parseInt(h.slice(1), 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  const RAMP_RGB = RAMP.map(hex);

  // --------------------------------------------------------- saying so
  // What the page is doing, while it does it. A blank page that never changes
  // cannot be told from a hung one.
  function progress(what) {
    const title = $('ov-title');
    if (title) title.textContent = what;
    const name = $('run-name');
    if (name && !loaded) name.textContent = what.toLowerCase();
  }

  function fail(error) {
    const message = (error && error.message) || String(error);
    const box = $('fatal');
    if (box) {
      box.hidden = false;
      box.replaceChildren(
        make('strong', null, 'The lab could not load this run. '),
        make('span', null, message),
        make('span', 'source', ' — the server is still running and has written '
          + 'nothing; its own output says whether it started cleanly.'));
    }
    const title = $('ov-title');
    if (title) title.textContent = 'This run did not load';
    const name = $('run-name');
    if (name) name.textContent = 'not loaded';
    const overlay = $('ground-overlay');
    if (overlay) { overlay.hidden = false; overlay.className = 'overlay error'; overlay.textContent = message; }
  }

  async function api(path, params) {
    const query = new URLSearchParams(params || {}).toString();
    let response;
    try {
      response = await fetch(path + (query ? '?' + query : ''), {
        headers: { 'X-Oneground-Token': TOKEN },
        credentials: 'omit',
        cache: 'no-store',
        referrerPolicy: 'no-referrer',
      });
    } catch (e) {
      throw new Error(`${path} could not be reached: ${e.message}. The lab `
        + 'server may have been stopped.');
    }
    let body;
    try {
      body = await response.json();
    } catch (e) {
      throw new Error(`${path} answered ${response.status} with something that is not JSON`);
    }
    if (!response.ok) throw new Error(`${path}: ${body.error || response.status}`);
    return body;
  }

  // ------------------------------------------------------------ state held
  let run = null;          // /api/run: declared facts about the run
  let check = null;        // /api/check: workdir, receipts, mode
  let layout = null;       // per-vector pixel positions, fixed by home region
  let lastGround = null;   // the ground drawing on screen
  let lastTrace = null;    // the trace drawing on screen
  let index = null;        // the query index drawing, for the picker
  let shownEpsilon = null; // the epsilon the ground on screen belongs to
  let indexEpsilon = null; // the epsilon the query index belongs to
  let copiesFilter = null; // show only vectors with this copy count
  let queryRow = 0;        // the query on screen
  let loaded = false;
  let booting = true;      // during boot the trace is drawn after the landing
  let inFlight = null;     // at most one ground request at a time
  let queued = null;       // the latest epsilon asked for while one was away

  const modeOf = () => (run && run.render ? run.render.mode : STATIC);

  // --------------------------------------------------------------- layout
  // Cells by home region. Home region does not depend on epsilon, so this is
  // computed once and every later drawing recolours the same pixels.
  function buildLayout(points, regionCount) {
    const homes = points.data.home_region;
    const ids = points.data.vector_id;
    const members = Array.from({ length: regionCount }, () => []);
    for (let i = 0; i < ids.length; i++) members[homes[i]].push(i);
    let largest = 1;
    for (const m of members) largest = Math.max(largest, m.length);
    const side = Math.ceil(Math.sqrt(largest));
    const columns = Math.ceil(Math.sqrt(regionCount));
    const cell = side + 2 * GUTTER;
    const width = columns * cell;
    const rows = Math.ceil(regionCount / columns);
    const at = new Int32Array(ids.length);
    const cellOrigin = [];
    members.forEach((list, region) => {
      const cx = (region % columns) * cell + GUTTER;
      const cy = Math.floor(region / columns) * cell + GUTTER;
      cellOrigin[region] = [cx, cy];
      list.forEach((point, k) => {
        at[point] = (cy + Math.floor(k / side)) * width + cx + (k % side);
      });
    });
    return { at, width, height: rows * cell, cell, side, columns, cellOrigin };
  }

  /* The canvas holds one pixel per vector, and CSS scales it to the box. The
   * drawing is therefore independent of the window; resizing only rescales
   * what is already painted, which is why a resize needs no redraw of the
   * data — but the element's own width must be set, so it is set on resize. */
  function fitCanvas(canvas) {
    if (!layout || !canvas) return;
    const box = canvas.parentElement;
    const available = Math.max(120, box.clientWidth - 2);
    const scale = Math.max(1, Math.floor(available / layout.width)) || 1;
    const width = layout.width * scale <= available
      ? layout.width * scale : available;
    canvas.style.width = Math.round(width) + 'px';
    canvas.style.height = Math.round(width * (layout.height / layout.width)) + 'px';
    canvas.style.imageRendering = 'pixelated';
  }

  function paint(canvas, withOutlines) {
    if (!lastGround || !layout || !canvas) return;
    canvas.width = layout.width;
    canvas.height = layout.height;
    const ctx = canvas.getContext('2d');
    const image = ctx.createImageData(layout.width, layout.height);
    const px = image.data;
    for (let i = 0; i < px.length; i += 4) {
      px[i] = SLATE[0]; px[i + 1] = SLATE[1]; px[i + 2] = SLATE[2]; px[i + 3] = 255;
    }
    const copies = lastGround.marks[0].data.copy_count;
    for (let i = 0; i < copies.length; i++) {
      const n = copies[i];
      const colour = (copiesFilter !== null && n !== copiesFilter)
        ? DIM : RAMP_RGB[Math.min(n, RAMP_RGB.length) - 1];
      const o = layout.at[i] * 4;
      px[o] = colour[0]; px[o + 1] = colour[1]; px[o + 2] = colour[2];
    }
    ctx.putImageData(image, 0, 0);
    if (withOutlines) paintTraceOutlines(ctx);
    fitCanvas(canvas);
  }

  function outline(ctx, region, colour, weight) {
    const origin = layout.cellOrigin[region];
    if (!origin) return;
    ctx.strokeStyle = colour;
    ctx.lineWidth = weight;
    ctx.strokeRect(origin[0] - GUTTER + weight / 2, origin[1] - GUTTER + weight / 2,
                   layout.cell - weight, layout.cell - weight);
  }

  function paintTraceOutlines(ctx) {
    if (!lastTrace) return;
    const point = lastTrace.marks[2];
    const link = lastTrace.marks[1];
    for (const region of new Set(point.data.home_region)) outline(ctx, region, '#E7EAEF', 1);
    link.data.region.forEach((region, i) => { if (i > 0) outline(ctx, region, '#8B96A5', 2); });
    outline(ctx, lastTrace.figures.routed_region, '#C99A3B', 3);
  }

  // Which region a pointer is over, so a cell can be named.
  function regionAt(canvas, event) {
    if (!layout) return null;
    const rect = canvas.getBoundingClientRect();
    const x = Math.floor((event.clientX - rect.left) / rect.width * layout.width);
    const y = Math.floor((event.clientY - rect.top) / rect.height * layout.height);
    const col = Math.floor(x / layout.cell);
    const row = Math.floor(y / layout.cell);
    const region = row * layout.columns + col;
    return layout.cellOrigin[region] ? region : null;
  }

  function wireHover(canvasId, hoverId) {
    const canvas = $(canvasId);
    const hover = $(hoverId);
    if (!canvas || !hover) return;
    const rest = hover.textContent;
    canvas.addEventListener('mousemove', (e) => {
      const region = regionAt(canvas, e);
      if (region === null) { hover.textContent = rest; return; }
      const held = lastGround && lastGround.marks[1].data.vectors_held[region];
      hover.textContent = held === undefined
        ? `region ${region}`
        : `region ${region} · holds ${fmtInt(held)} vectors at ε ${fmtEps(shownEpsilon)}`;
    });
    canvas.addEventListener('mouseleave', () => { hover.textContent = rest; });
  }

  // ------------------------------------------------------------- epsilon
  function sliderEpsilon() { return Number(need('eps').value); }

  function isSimulated(value) {
    return (run.simulated_epsilons || []).some(
      (e) => Math.abs(Number(e) - Number(value)) < 5e-7);
  }

  function buildTicks() {
    const ticks = need('eps-ticks');
    ticks.replaceChildren();
    const slider = need('eps');
    const min = Number(slider.min);
    const span = Number(slider.max) - min;
    (run.simulated_epsilons || []).forEach((value) => {
      const tick = make('button', 'tick', String(Number(value)));
      tick.type = 'button';
      tick.style.left = ((Number(value) - min) / span * 100) + '%';
      tick.title = `simulated at ε ${Number(value)} — recall exists here`;
      tick.addEventListener('click', () => {
        slider.value = String(value);
        onMove();
        onRelease();
      });
      ticks.append(tick);
    });
    markTicks();
  }

  function markTicks() {
    const at = sliderEpsilon();
    need('eps-ticks').querySelectorAll('.tick').forEach((tick) => {
      tick.setAttribute('aria-current',
        Math.abs(Number(tick.textContent) - at) < 5e-7 ? 'true' : 'false');
    });
  }

  function showEpsStatus() {
    const pill = need('eps-status');
    const at = sliderEpsilon();
    const simulated = isSimulated(at);
    pill.className = 'pill ' + (simulated ? 'simulated' : 'not-simulated');
    pill.textContent = simulated ? 'simulated' : NOT_SIM;
    pill.title = simulated
      ? 'this ε was simulated: recall, candidates and missed neighbours exist here'
      : 'the geometry is recounted from state here; no recall figure exists at this ε';
  }

  function onMove() {
    const at = sliderEpsilon();
    text(need('eps-out'), fmtEps(at));
    markTicks();
    showEpsStatus();
    if (modeOf() === MOVE) { drawAt(at); return; }
    const stale = need('eps-stale');
    if (shownEpsilon !== null && Math.abs(shownEpsilon - at) > 1e-9) {
      stale.hidden = false;
      text(stale, `showing ε ${fmtEps(shownEpsilon)}; release to redraw at ${fmtEps(at)}`);
    } else {
      stale.hidden = true;
    }
  }

  function onRelease() {
    if (modeOf() !== MOVE) drawAt(sliderEpsilon());
  }

  // ------------------------------------------------------ render verdicts
  const VERDICT_WORDS = {
    within: 'every reading within the threshold',
    straddled: 'the readings straddled the threshold',
    above: 'above the threshold',
  };

  function readingsPhrase(r) {
    const n = r.readings_ms.length;
    return `${n} reading${n === 1 ? '' : 's'} of ${r.draws} draws`;
  }

  function modeSentence(r) {
    if (r.p95_ms === null || r.p95_ms === undefined) return r.mode;
    return `${r.mode} — ${VERDICT_WORDS[r.verdict] || r.verdict}: ground draw p95 `
      + `${r.readings_ms.join(' / ')} ms over ${readingsPhrase(r)} on this host against `
      + `${r.threshold_ms} ms (${Math.round(r.margin * 100)}% inside the ${r.frame_ms} ms frame)`
      + (r.chosen_by === '--mode' ? ` — chosen by --mode; measurement alone chose ${r.measured_mode}` : '');
  }

  function modeExplained(r) {
    if (r.mode === MOVE) {
      return 'Every reading of this host\'s drawing time fitted inside the threshold, '
        + 'so the ground is redrawn on every move of the control.';
    }
    if (r.mode === STATIC) return 'This family has no ε, so there is nothing to move.';
    return 'At least one reading of this host\'s drawing time was over the threshold, so the '
      + 'ground is redrawn when you let go of the control rather than during the drag. '
      + 'While you drag, the reading follows your hand and the ground says which ε it still '
      + 'belongs to — a drawing that trailed the control could be screenshotted under an ε it '
      + 'does not belong to.';
  }

  // -------------------------------------------------------------- routing
  const VIEWS = ['overview', 'ground', 'trace'];

  function route() {
    const wanted = (location.hash || '#/overview').replace('#/', '');
    const name = VIEWS.includes(wanted) ? wanted : 'overview';
    VIEWS.forEach((v) => {
      const section = $(`view-${v}`);
      if (section) section.hidden = v !== name;
      const tab = $(`tab-${v}`);
      if (tab) tab.setAttribute('aria-current', v === name ? 'page' : 'false');
    });
    // The control belongs to both drawing views, and keeps its value across
    // them: moving between views must not move epsilon.
    const control = $('control');
    if (control) control.hidden = !(loaded && name !== 'overview' && run.epsilon !== null);
    if (name === 'ground') { fitCanvas($('ground-canvas')); }
    if (name === 'trace') { fitCanvas($('trace-canvas')); ensureIndex(); }
  }

  // ------------------------------------------------------------- overview
  function fact(dl, term, value, cls) {
    dl.append(make('dt', null, term), make('dd', cls, value));
  }

  function showOverview() {
    // The workdir's own last segment, on either separator. Written without a
    // regex because the escape survives fewer layers than it looks like it
    // does: an earlier attempt lost its backslash and showed the whole path.
    const SEPARATORS = ['/', String.fromCharCode(92)];
    let parts = [String(check.workdir)];
    SEPARATORS.forEach((sep) => {
      parts = parts.reduce((all, piece) => all.concat(piece.split(sep)), []);
    });
    parts = parts.filter((piece) => piece !== '');
    const leaf = parts.length ? parts[parts.length - 1] : '';
    text(need('ov-title'), leaf || run.family);
    text(need('run-name'), run.config_label);
    text(need('ov-lede'),
      `${fmtInt(run.n_base)} vectors in ${fmtInt(run.partition_regions || 0)} regions, `
      + `${fmtInt(run.n_queries)} queries, k = ${run.k}. Everything below was measured on this `
      + 'corpus by the run in the workdir; the lab draws it and measures nothing.');

    const facts = need('ov-facts');
    facts.replaceChildren();
    fact(facts, 'workdir', check.workdir, 'mono');
    (check.also || []).forEach((dir) => fact(facts, 'also reading', dir, 'mono'));
    fact(facts, 'configuration', run.config_label, 'mono');
    fact(facts, 'family', run.family);
    fact(facts, 'vectors', fmtInt(run.n_base));
    fact(facts, 'queries', fmtInt(run.n_queries));
    fact(facts, 'regions', fmtInt(run.partition_regions || 0));
    fact(facts, 'ε in the run', fmtEps(run.epsilon));
    fact(facts, 'ε simulated', run.simulated_epsilons && run.simulated_epsilons.length
      ? epsList(run.simulated_epsilons) : 'none');
    const files = Object.entries(run.files || {});
    fact(facts, 'files present',
      files.filter(([, there]) => there).map(([n]) => n).join(', ') || 'none');
    const missing = files.filter(([, there]) => !there).map(([n]) => n);
    if (missing.length) fact(facts, 'not in this run', missing.join(', '), 'unchecked');

    const receipts = need('ov-receipts');
    receipts.replaceChildren();
    (check.digests || []).forEach((entry) => {
      const li = make('li');
      if (!entry.manifest) {
        li.append(make('span', 'verdict unchecked', 'not checked'),
                  make('span', null, entry.note || 'no manifest'),
                  make('span', 'path', entry.directory));
      } else {
        const good = entry.files.filter((f) => f.verified).length;
        li.append(
          make('span', 'verdict ' + (entry.all_verified ? 'ok' : 'bad'),
               entry.all_verified ? 'verified' : 'NOT verified'),
          make('span', null, `${good} of ${entry.files.length} files match the digests recorded when they were written`),
          make('span', 'path', entry.directory));
      }
      receipts.append(li);
    });

    const simulated = run.simulated_epsilons || [];
    text(need('ov-epsilon'), run.epsilon === null
      ? 'This family has no closure band, so there is no ε control.'
      : `ε is the closure band: how far past its nearest region a vector is still copied. `
        + `Moving it recounts the geometry from the stored distances — copies, the histogram, `
        + `storage, p99 and the routing ceiling — live, at any value. Recall, candidates and `
        + `missed neighbours are different: they need a new simulate run, so they exist only at `
        + `ε ${epsList(simulated)}, and nowhere between. The lab never runs one; between those `
        + `values it shows what a run would cost and the exact command.`);
    text(need('ov-mode'), modeSentence(run.render) + '. ' + modeExplained(run.render));
    text(need('ov-writes'), `${check.writes}. Token: ${check.token}`);
  }

  // --------------------------------------------------------------- ground
  function showGround(drawing) {
    lastGround = drawing;
    const f = drawing.figures;
    shownEpsilon = f.epsilon === undefined ? null : f.epsilon;
    if (!layout) layout = buildLayout(drawing.marks[0], drawing.marks[1].data.region.length);

    text(need('r-copied'), f.vectors_copied === undefined ? '—' : fmtInt(f.vectors_copied));
    text(need('r-storage'), f.storage_amplification === undefined
      ? '—' : f.storage_amplification.toFixed(3) + '×');
    text(need('r-p99'), f.p99_copies === undefined ? '—' : String(f.p99_copies));
    text(need('r-ceiling'), f.routing_ceiling_at_k === undefined
      ? '—' : f.routing_ceiling_at_k.toFixed(4));

    buildCopyBars(f);
    showGroundNotice(f);
    text(need('ground-caption'), drawing.caption || '');
    listGaps(need('ground-gaps'), drawing.gaps);
    need('eps-stale').hidden = true;
    paint($('ground-canvas'), false);
    paint($('trace-canvas'), true);
  }

  /* Copies 3 and 4 sit close together in the ramp at one pixel per vector.
   * The palette is the teaser's and is not forked, so the legend carries the
   * counts and each row isolates its own vectors on the ground: selecting
   * "3" dims everything else, which separates them exactly. */
  function buildCopyBars(f) {
    const box = need('copy-bars');
    box.replaceChildren();
    const histogram = f.copies_histogram || [];
    const pct = f.copies_histogram_pct || [];
    const most = Math.max(1, ...histogram);
    histogram.forEach((count, i) => {
      const copies = i + 1;
      const row = make('button', 'copy-bar');
      row.type = 'button';
      row.setAttribute('aria-pressed', copiesFilter === copies ? 'true' : 'false');
      if (copiesFilter !== null && copiesFilter !== copies) row.classList.add('dimmed');
      const bar = make('span', 'bar');
      const fill = make('span', `fill c${Math.min(copies, 4)}`);
      fill.style.width = (count / most * 100) + '%';
      bar.append(fill);
      row.append(
        make('span', `swatch c${Math.min(copies, 4)}`),
        make('span', 'name', `${copies} ${copies === 1 ? 'region' : 'regions'}`),
        bar,
        make('span', 'count', `${fmtInt(count)}${pct[i] === undefined ? '' : ` · ${pct[i]}%`}`));
      row.title = copiesFilter === copies
        ? 'showing only these; select again to show all'
        : `show only the vectors held by ${copies} region${copies === 1 ? '' : 's'}`;
      row.addEventListener('click', () => {
        copiesFilter = copiesFilter === copies ? null : copies;
        buildCopyBars(f);
        paint($('ground-canvas'), false);
        paint($('trace-canvas'), true);
        const overlay = need('ground-overlay');
        overlay.hidden = copiesFilter === null;
        overlay.className = 'overlay';
        overlay.textContent = copiesFilter === null ? ''
          : `showing only vectors held by ${copiesFilter} region${copiesFilter === 1 ? '' : 's'}`;
      });
      box.append(row);
    });
  }

  // The honest caption, in the view rather than as fine print.
  function showGroundNotice(f) {
    const notice = need('ground-notice');
    notice.replaceChildren();
    const at = shownEpsilon;
    const simulated = isSimulated(at);
    notice.className = 'notice' + (simulated ? '' : ' not-simulated');
    if (simulated) {
      notice.append(make('p', null,
        `ε ${fmtEps(at)} was simulated. The geometry here is what the run emitted, and the `
        + 'query trace carries recall, candidates and missed neighbours for it.'));
      return;
    }
    notice.append(
      make('p', null, ''),
      make('p', null,
        `The geometry is recounted from the stored distances at ε ${fmtEps(at)}; nothing here is `
        + 'interpolated. No recall, candidate or missed-neighbour figure exists at this ε, '
        + 'because those need a simulate run that has not been done.'));
    notice.firstChild.append(
      make('strong', null, NOT_SIM + '. '),
      document.createTextNode(`Simulated: ε ${epsList(run.simulated_epsilons)}.`));
    const jumps = make('div', 'jumps');
    (run.simulated_epsilons || []).forEach((value) => {
      const b = make('button', null, `go to ε ${Number(value)}`);
      b.type = 'button';
      b.addEventListener('click', () => {
        need('eps').value = String(value);
        onMove(); onRelease();
      });
      jumps.append(b);
    });
    if (jumps.childElementCount) notice.append(jumps);
  }

  function listGaps(el, gaps) {
    el.replaceChildren();
    Object.entries(gaps || {}).forEach(([name, why]) => {
      el.append(make('li', null, `${name}: ${why}`));
    });
  }

  async function drawAt(epsilon) {
    if (inFlight) { queued = epsilon; return; }
    const params = epsilon === null || epsilon === undefined ? {} : { epsilon };
    inFlight = true;
    try {
      const drawing = await api('/api/ground', params);
      showGround(drawing);
      if (loaded && !booting) {
        await redrawTrace();
        // The picker's rows are epsilon-dependent too: what a route missed
        // exists only at a simulated epsilon, and the geometry it orders by is
        // recounted. Leaving the old rows up would caption this epsilon's list
        // with the last one's -- which is how the note came to say "at ε 0.150"
        // while the control stood at a simulated 0.1.
        const trace = $('view-trace');
        if (trace && !trace.hidden) await ensureIndex();
      }
    } catch (error) {
      const overlay = $('ground-overlay');
      if (overlay) {
        overlay.hidden = false;
        overlay.className = 'overlay error';
        overlay.textContent = error.message;
      }
      throw error;
    } finally {
      inFlight = null;
      if (queued !== null && queued !== undefined) {
        const next = queued; queued = null; drawAt(next);
      }
    }
  }

  // ---------------------------------------------------------------- trace
  async function ensureIndex() {
    const at = sliderEpsilon();
    if (index && indexEpsilon !== null && Math.abs(indexEpsilon - at) < 1e-9) return;
    text(need('q-count'), 'reading every query…');
    try {
      index = await api('/api/query-index', run.epsilon === null ? {} : { epsilon: at });
      indexEpsilon = at;
      buildQueryList();
    } catch (error) {
      text(need('q-count'), `the query list could not be read: ${error.message}`);
    }
  }

  function indexRows() {
    if (!index) return [];
    const d = index.marks[0].data;
    const panel = index.panels && index.panels.recall;
    const simulated = panel && panel.status === 'simulated';
    const hits = simulated ? panel.figures.hits : null;
    const missed = simulated ? panel.figures.missed_by_route : null;
    return d.query.map((q, i) => ({
      query: q,
      name: (run.query_ids && run.query_ids[q] !== undefined) ? run.query_ids[q] : String(q),
      routed: d.routed_region[i],
      outside: d.outside_routed_region[i],
      located: d.true_neighbours_located[i],
      ambiguous: d.ambiguous ? d.ambiguous[i] : null,
      ratio: d.distance_ratio ? d.distance_ratio[i] : null,
      hits: hits ? hits[i] : null,
      missed: missed ? missed[i] : null,
      simulated,
    }));
  }

  function buildQueryList(limit) {
    const list = need('q-list');
    const note = need('q-note');
    let rows = indexRows();
    const simulated = rows.length > 0 && rows[0].simulated;

    const term = need('q-search').value.trim().toLowerCase();
    if (term) rows = rows.filter((r) => String(r.name).toLowerCase().includes(term)
      || String(r.query).includes(term));

    const filter = need('q-filter').querySelector('[aria-pressed="true"]');
    const which = filter ? filter.dataset.filter : 'all';
    if (which === 'ambiguous') rows = rows.filter((r) => r.ambiguous === true);
    if (which === 'clear') rows = rows.filter((r) => r.ambiguous === false);

    const order = need('q-order').value;
    const by = {
      'missed-most': (a, b) => (b.missed - a.missed) || (b.outside - a.outside),
      'missed-least': (a, b) => (a.missed - b.missed) || (a.outside - b.outside),
      'outside-most': (a, b) => (b.outside - a.outside) || (a.query - b.query),
      'outside-least': (a, b) => (a.outside - b.outside) || (a.query - b.query),
      query: (a, b) => a.query - b.query,
    }[order] || ((a, b) => a.query - b.query);

    // Ordering by what the route missed needs a simulated epsilon: between
    // them no run measured it. The list says so and orders by geometry.
    const needsRecall = order.startsWith('missed');
    if (needsRecall && !simulated) {
      note.hidden = false;
      text(note, `Ordering by neighbours missed needs a simulated ε — at ε `
        + `${fmtEps(indexEpsilon)} no run measured it. Ordered by neighbours outside the routed `
        + `region instead, which is recounted from state.`);
      rows.sort((a, b) => (b.outside - a.outside) || (a.query - b.query));
    } else {
      note.hidden = true;
      rows.sort(by);
    }

    const total = rows.length;
    const cap = limit || QLIST_MAX;
    text(need('q-count'), `${fmtInt(total)} of ${fmtInt(run.n_queries)} queries`
      + (total > cap ? `, showing the first ${fmtInt(cap)}` : ''));

    list.replaceChildren();
    if (!total) {
      // An empty list with only a count is a state that renders blank. Say
      // what emptied it and how to get back.
      const why = make('li', 'more');
      why.append(make('span', null, term
        ? `No query matches “${term}”`
        : 'No query matches this filter'));
      const clear = make('button', null, 'show all queries');
      clear.type = 'button';
      clear.addEventListener('click', () => {
        need('q-search').value = '';
        need('q-filter').querySelectorAll('button').forEach(
          (o) => o.setAttribute('aria-pressed', String(o.dataset.filter === 'all')));
        buildQueryList();
      });
      why.append(clear);
      list.append(why);
      return;
    }
    rows.slice(0, cap).forEach((r) => {
      const li = make('li');
      const b = make('button');
      b.type = 'button';
      b.setAttribute('aria-current', r.query === queryRow ? 'true' : 'false');
      const found = r.simulated ? `${r.hits}/${index.figures.k}` : `${r.located} true`;
      b.append(
        make('span', 'qname', r.name),
        make('span', 'qfound', found),
        make('span', 'qmeta',
          `region ${r.routed} · ${r.outside} outside`
          + (r.ambiguous === null ? '' : (r.ambiguous ? ' · ambiguous' : ''))));
      b.addEventListener('click', () => { queryRow = r.query; redrawTrace(); buildQueryList(cap); });
      li.append(b);
      list.append(li);
    });
    if (total > cap) {
      const more = make('li', 'more');
      const b = make('button', null, `show ${fmtInt(Math.min(total - cap, QLIST_MAX))} more`);
      b.type = 'button';
      b.addEventListener('click', () => buildQueryList(cap + QLIST_MAX));
      more.append(b);
      list.append(more);
    }
  }

  function hopDetail(id, nodes) {
    const box = need(id);
    box.replaceChildren();
    nodes.forEach((n) => box.append(n));
  }

  function showTrace(drawing) {
    lastTrace = drawing;
    const f = drawing.figures;
    const [scored, link, point] = drawing.marks;
    const name = (run.query_ids && run.query_ids[f.query] !== undefined)
      ? run.query_ids[f.query] : String(f.query);

    text(need('t-title'), `Query ${name}`);
    text(need('t-sub'), `row ${f.query} of ${fmtInt(run.n_queries)} · ε ${fmtEps(f.epsilon)}`
      + (isSimulated(f.epsilon) ? ' · simulated' : ' · ' + NOT_SIM));

    // 1: scored
    const scoredRows = scored.data.region.map((region, i) => make('p', null,
      `region ${region} at distance ${scored.data.distance[i].toFixed(4)}`));
    hopDetail('hop-1', [
      make('p', 'big', `${scored.data.region.length} region${scored.data.region.length === 1 ? '' : 's'} scored`),
      ...scoredRows,
      make('p', 'dim', f.ambiguous === undefined ? ''
        : `nearest two differ by ${((f.distance_ratio - 1) * 100).toFixed(2)}% — `
          + `${f.ambiguous ? 'ambiguous' : 'not ambiguous'} at the declared ratio ${f.ambiguity_ratio}`),
    ]);

    // 2: routed and probed
    text(need('hop-2-title'), `Routed to region ${f.routed_region}`);
    hopDetail('hop-2', [
      make('p', 'big', `probed ${link.data.region.length} region${link.data.region.length === 1 ? '' : 's'}`),
      ...link.data.region.map((region, i) => make('p', null,
        `${i === 0 ? 'routed' : 'also probed'}: region ${region} — ${link.data.reason[i]}`)),
    ]);

    // 3: true neighbours
    text(need('hop-3-title'), `Its ${point.data.vector_id.length} true neighbours`);
    const nbrs = make('ol', 'nbrs');
    point.data.vector_id.forEach((id, i) => {
      const outside = point.data.outside_routed_region[i];
      const li = make('li', outside ? 'missed' : 'found');
      li.textContent = `#${point.data.rank[i] + 1} vector ${id} · region ${point.data.home_region[i]}`
        + (outside ? ' · outside the routed region' : '');
      nbrs.append(li);
    });
    hopDetail('hop-3', [
      make('p', 'big', `${f.outside_routed_region} of ${point.data.vector_id.length} live outside the routed region`),
      nbrs,
    ]);

    // 4: the recall panel, under the epsilon rule
    showRecall(drawing.panels && drawing.panels.recall);
    listGaps(need('trace-gaps'), drawing.gaps);
    paint($('trace-canvas'), true);
  }

  function showRecall(panel) {
    const title = need('hop-4-title');
    const item = need('hop-4-item');
    item.hidden = false;
    if (!panel) {
      text(title, 'What the probed regions returned');
      hopDetail('hop-4', [make('p', 'dim', 'this drawing carries no recall panel')]);
      return;
    }
    if (panel.status === 'simulated') {
      const g = panel.figures;
      text(title, 'What the probed regions returned');
      hopDetail('hop-4', [
        make('p', 'big', `recall@${g.k} ${g.recall_at_k.toFixed(3)} — ${g.hits} of ${g.k} found`),
        make('p', null, `${fmtInt(g.candidates_returned)} candidates returned by the probed shards`),
        make('p', null, `${g.missed_by_route} of ${g.k} true neighbours were never reached by the route`),
        make('p', 'dim', `measured by the run simulated at ε ${fmtEps(panel.epsilon)}`),
      ]);
      return;
    }
    // Not simulated: the values, the cost, the command. Never a blank, never
    // an interpolation.
    text(title, 'What the probed regions returned — not measured at this ε');
    const box = make('div', 'recall-unsim');
    box.append(make('p', 'status', `${NOT_SIM} (${fmtEps(panel.epsilon)})`));
    box.append(make('p', null,
      `Recall, candidates and missed neighbours need a simulate run at this ε. `
      + `Simulated so far: ε ${epsList(panel.simulated_epsilons)}.`));
    const jumps = make('div', 'jumps');
    (panel.simulated_epsilons || []).forEach((value) => {
      const b = make('button', null, `go to ε ${Number(value)}`);
      b.type = 'button';
      b.addEventListener('click', () => {
        need('eps').value = String(value); onMove(); onRelease();
      });
      jumps.append(b);
    });
    if (jumps.childElementCount) box.append(jumps);
    const cost = panel.cost_minutes;
    if (cost && typeof cost === 'object') {
      box.append(make('p', null, cost.low === cost.high
        ? `Simulating this ε would cost about ${cost.low} minutes.`
        : `Simulating this ε would cost about ${cost.low}–${cost.high} minutes.`));
      box.append(make('p', 'dim', cost.basis));
    } else if (cost) {
      box.append(make('p', 'dim', String(cost)));
    }
    const action = panel.action;
    if (action && action.command) {
      const wrap = make('div', 'command');
      wrap.append(make('pre', null, action.command));
      if (action.grid) {
        wrap.append(make('p', 'dim', 'with this grid in the requirements file:'));
        wrap.append(make('pre', null, JSON.stringify(action.grid, null, 2)));
      }
      const copy = make('button', 'copy', 'copy the command');
      copy.type = 'button';
      copy.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(action.command);
          copy.textContent = 'copied';
        } catch (e) {
          copy.textContent = 'select the text above to copy it';
        }
      });
      wrap.append(copy);
      box.append(wrap);
    }
    box.append(make('p', 'dim', 'The lab never runs it.'));
    hopDetail('hop-4', [box]);
  }

  async function redrawTrace() {
    const params = { query: queryRow };
    if (run.epsilon !== null) params.epsilon = sliderEpsilon();
    try {
      showTrace(await api('/api/trace', params));
    } catch (error) {
      hopDetail('hop-4', [make('p', 'dim', `the trace could not be drawn: ${error.message}`)]);
    }
  }

  // ----------------------------------------------------------------- boot
  async function boot() {
    progress('Reading the run…');
    run = await api('/api/run');
    loaded = true;

    progress('Checking the receipts…');
    check = await api('/api/check');

    progress('Laying out the overview…');
    showOverview();

    const r = run.render;
    text(need('mode-summary'), `rendering: ${modeSentence(r)}`);
    text(need('mode-detail'), modeExplained(r));

    // The page's own URL may name where to start: `epsilon` and `query`,
    // beside the token. They set the controls; they are not sent anywhere.
    const start = new URLSearchParams(location.search);
    if (start.has('query')) {
      queryRow = Math.min(run.n_queries - 1, Math.max(0, Number(start.get('query')) || 0));
    }

    const slider = need('eps');
    let initial = run.epsilon;
    if (run.epsilon === null || r.mode === STATIC) {
      slider.disabled = true;
      text(need('eps-status'), 'this family has no ε');
      need('control').hidden = true;
    } else {
      slider.max = String(run.epsilon_max);
      if (start.has('epsilon') && Number.isFinite(Number(start.get('epsilon')))) {
        initial = Math.min(run.epsilon_max, Math.max(0, Number(start.get('epsilon'))));
      }
      slider.value = String(initial);
      text(need('eps-out'), fmtEps(initial));
      buildTicks();
      showEpsStatus();
      slider.addEventListener('input', onMove);
      slider.addEventListener('change', onRelease);
    }

    need('t-prev').addEventListener('click', () => {
      queryRow = Math.max(0, queryRow - 1); redrawTrace(); buildQueryList();
    });
    need('t-next').addEventListener('click', () => {
      queryRow = Math.min(run.n_queries - 1, queryRow + 1); redrawTrace(); buildQueryList();
    });
    need('q-search').addEventListener('input', () => buildQueryList());
    need('q-order').addEventListener('change', () => buildQueryList());
    need('q-filter').querySelectorAll('button').forEach((b) => {
      b.addEventListener('click', () => {
        need('q-filter').querySelectorAll('button').forEach(
          (o) => o.setAttribute('aria-pressed', String(o === b)));
        buildQueryList();
      });
    });
    window.addEventListener('hashchange', route);
    window.addEventListener('resize', () => {
      fitCanvas($('ground-canvas'));
      fitCanvas($('trace-canvas'));
    });
    wireHover('ground-canvas', 'ground-hover');
    wireHover('trace-canvas', 'trace-hover');

    progress('Drawing the ground…');
    await drawAt(initial === null ? null : initial);

    // The landing page is complete here. The trace and its query index are
    // fetched after, so a slow index never holds up what is already drawable.
    showOverview();
    booting = false;
    route();
    await redrawTrace();
  }

  // A failure anywhere above must reach the page. `fail` touches elements
  // defensively and cannot throw, so this handler always finishes.
  boot().catch((error) => {
    try { fail(error); } catch (e) { /* nothing left to say it with */ }
    if (window.console) console.error('oneground lab:', error);
  });

  // For the browser-driven test: what the page believes it has loaded.
  window.__labState = () => ({
    loaded, shownEpsilon, queryRow,
    hasRun: !!run, hasCheck: !!check, hasGround: !!lastGround,
    hasTrace: !!lastTrace, hasIndex: !!index,
  });
})();
