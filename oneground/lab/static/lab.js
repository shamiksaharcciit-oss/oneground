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
  let layout = null;       // the layout on screen: cells, or the projection
  let cellLayout = null;   // by home region -- always available
  let projLayout = null;   // the declared projection -- only when the state has one
  let layoutMode = 'projection';   // which the reader asked for
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

  /* The declared projection, as pixels (task 027).
   *
   * The state carries a 2-D position per vector, declared and illustrative.
   * This maps those coordinates onto the canvas and nothing else: no distance
   * is taken, nothing is clustered, no neighbour is found by position. The
   * server refuses those operations in a view; the page does not need them.
   *
   * Points land on whole pixels, so several vectors can share one at this
   * scale — the picture is a density, which is what the teaser's is too. The
   * bounds are the projection's own extent, padded so nothing sits on the
   * edge, and they are computed once: they do not move when epsilon does,
   * because epsilon changes a vector's colour and not its place.
   */
  const PROJECTED_SIDE = 900;

  // What each layout is, said under the picture. Two different claims about
  // what is on screen, and showing the wrong one states something false: the
  // cell caption ends "the state holds no positions", which stops being true
  // the moment the state carries a projection.
  const FIGCAPTION = {
    projection: 'Every vector at its declared position, coloured by how many '
      + 'regions hold a copy of it at this ε. The positions are a projection '
      + 'the fixture declares illustrative; regions, distances and copy counts '
      + 'were computed in the full space, not from this picture. Rings mark '
      + 'each region at the mean position of its own vectors.',
    regions: 'One cell per region; inside it, the vectors whose home is that '
      + 'region, in id order, coloured by how many regions hold a copy of each '
      + 'at this ε. It is a layout, not a map: it places a vector by which '
      + 'region it belongs to, and nothing else.',
  };
  const HOVER = {
    projection: 'Positions are the declared projection; switch to "By region" '
      + 'to point at a region.',
    regions: 'Point at a cell to see which region it is.',
  };

  // What the trace's marks are, per layout. A key that names marks the
  // canvas is not drawing is worse than no key at all.
  const KEY = {
    projection: [
      ['ring routed', 'the region the query was routed to'],
      ['ring probed', 'the other region(s) it probed'],
      ['ring neighbours', 'its true neighbours; louder where one lives '
        + 'outside the routed region'],
      ['cross', 'the query itself, placed among its true neighbours'],
    ],
    regions: [
      ['key-box routed', 'the region the query was routed to'],
      ['key-box probed', 'the other region(s) it probed'],
      ['key-box neighbours', 'regions its true neighbours live in'],
    ],
  };

  function describeLayout() {
    const which = (layout && layout.projected) ? 'projection' : 'regions';
    text($('ground-figcaption'), FIGCAPTION[which]);
    text($('ground-hover'), HOVER[which]);
    text($('trace-hover'), HOVER[which]);
    const key = $('trace-key');
    if (key) {
      key.replaceChildren();
      KEY[which].forEach(([cls, label]) => {
        const li = make('li');
        li.append(make('span', cls), document.createTextNode(label));
        key.append(li);
      });
      const ramp = make('li');
      const swatches = make('span', 'key-ramp');
      swatches.setAttribute('aria-hidden', 'true');
      ['c1', 'c2', 'c3', 'c4'].forEach((c) => swatches.append(make('span', c)));
      ramp.append(swatches,
                  document.createTextNode('vector colour: held by 1, 2, 3, 4 regions'));
      key.append(ramp);
    }
  }

  function buildProjected(points) {
    const xs = points.data.x;
    const ys = points.data.y;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (let i = 0; i < xs.length; i++) {
      if (xs[i] < minX) minX = xs[i];
      if (xs[i] > maxX) maxX = xs[i];
      if (ys[i] < minY) minY = ys[i];
      if (ys[i] > maxY) maxY = ys[i];
    }
    const spanX = (maxX - minX) || 1;
    const spanY = (maxY - minY) || 1;
    const span = Math.max(spanX, spanY);
    const pad = PROJECTED_SIDE * 0.02;
    const usable = PROJECTED_SIDE - 2 * pad;
    // one scale for both axes, so the picture is not stretched
    const place = (x, y) => [
      pad + ((x - minX) - (spanX - span) / 2) / span * usable,
      // y grows downward on a canvas and upward in a projection
      pad + usable - ((y - minY) - (spanY - span) / 2) / span * usable,
    ];
    const at = new Int32Array(xs.length);
    for (let i = 0; i < xs.length; i++) {
      const [px, py] = place(xs[i], ys[i]);
      const cx = Math.min(PROJECTED_SIDE - 1, Math.max(0, Math.round(px)));
      const cy = Math.min(PROJECTED_SIDE - 1, Math.max(0, Math.round(py)));
      at[i] = cy * PROJECTED_SIDE + cx;
    }
    return { at, width: PROJECTED_SIDE, height: PROJECTED_SIDE,
             projected: true, place };
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
    if (layout.projected) paintRegionMarks(ctx);
    if (withOutlines) paintTraceOutlines(ctx);
    fitCanvas(canvas);
  }

  /* Each region at the position the state declares for it -- the mean of its
   * own vectors' positions, computed at emit time, never here. Small and
   * muted: they locate the regions without competing with the vectors. */
  function paintRegionMarks(ctx) {
    const at = regionPlacement();
    if (!at) return;
    ctx.strokeStyle = 'rgba(231, 234, 239, 0.45)';
    ctx.lineWidth = 1;
    for (const [, pos] of at) {
      const [px, py] = layout.place(pos[0], pos[1]);
      ctx.beginPath();
      ctx.arc(px, py, 3.5, 0, Math.PI * 2);
      ctx.stroke();
    }
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
    if (layout && layout.projected) { paintTraceOnProjection(ctx); return; }
    const point = lastTrace.marks[2];
    const link = lastTrace.marks[1];
    for (const region of new Set(point.data.home_region)) outline(ctx, region, '#E7EAEF', 1);
    link.data.region.forEach((region, i) => { if (i > 0) outline(ctx, region, '#8B96A5', 2); });
    outline(ctx, lastTrace.figures.routed_region, '#C99A3B', 3);
  }

  /* The same three things the cell layout outlines, on the projection: the
   * routed region, the other probed regions, and the query's true
   * neighbours -- plus the query's own declared placement, which the cells
   * have nowhere to put. Regions are rings at the position the state
   * declares for them (`partition.projection`), not shapes computed here. */
  function ring(ctx, x, y, radius, colour, weight) {
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.strokeStyle = colour;
    ctx.lineWidth = weight;
    ctx.stroke();
  }

  function regionPlacement() {
    // the ground's region mark, when the state declared one
    const mark = (lastGround && lastGround.marks || []).find(
      (m) => m.kind === 'region' && m.data && m.data.x);
    if (!mark) return null;
    const at = new Map();
    mark.data.region.forEach((r, i) => {
      const x = mark.data.x[i];
      const y = mark.data.y[i];
      if (Number.isFinite(x) && Number.isFinite(y)) at.set(r, [x, y]);
    });
    return at;
  }

  function paintTraceOnProjection(ctx) {
    const place = layout.place;
    const [, link, point, queryMark] = lastTrace.marks;
    const regions = regionPlacement();

    if (regions) {
      link.data.region.forEach((r, i) => {
        const pos = regions.get(r);
        if (!pos) return;
        const [px, py] = place(pos[0], pos[1]);
        if (i === 0) ring(ctx, px, py, 26, '#C99A3B', 3);
        else ring(ctx, px, py, 20, '#8B96A5', 2);
      });
    }

    // the true neighbours, ringed; the ones outside the routed region louder
    point.data.x.forEach((x, i) => {
      const [px, py] = place(x, point.data.y[i]);
      const outside = point.data.outside_routed_region[i];
      ring(ctx, px, py, 5, outside ? '#E0A83A' : '#E7EAEF', outside ? 2 : 1.5);
    });

    // the query itself: a cross, so it is not mistaken for a vector
    if (queryMark && queryMark.data && queryMark.data.x) {
      const [px, py] = place(queryMark.data.x[0], queryMark.data.y[0]);
      ctx.strokeStyle = '#E7EAEF';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(px - 7, py); ctx.lineTo(px + 7, py);
      ctx.moveTo(px, py - 7); ctx.lineTo(px, py + 7);
      ctx.stroke();
      ring(ctx, px, py, 10, '#E7EAEF', 1);
    }
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
      if (layout && layout.projected) {
        hover.textContent = HOVER.projection;
        return;
      }
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
  /* The words come from the server: `contract.RenderMode` writes them once,
   * and the startup line, the ground's caption and this page all show the
   * same string. Composing a second version here from the parts is how the
   * page and the log come to disagree about one measurement. */
  function modeSentence(r) {
    if (!r.evidence) return r.mode;
    return `${r.mode} — ${r.evidence}`
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
    const points = drawing.marks[0];
    if (!cellLayout) {
      cellLayout = buildLayout(points, drawing.marks[1].data.region.length);
    }
    if (!projLayout && points.data.x) projLayout = buildProjected(points);
    // Epsilon recolours; it never moves a point. Both layouts are built once.
    const seg = $('ground-layout');
    if (seg) seg.hidden = !projLayout;
    if (!projLayout) layoutMode = 'regions';
    layout = (layoutMode === 'projection' && projLayout) ? projLayout : cellLayout;

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
    describeLayout();
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

    /* The count line carries the way to the rest. It used to say "showing the
     * first 250" with the only control at the bottom of a list 250 rows deep,
     * inside its own scroll box — true, and unreachable without knowing it was
     * there. */
    const count = need('q-count');
    count.replaceChildren(make('span', null,
      `${fmtInt(total)} of ${fmtInt(run.n_queries)} queries`
      + (total > cap ? `, showing the first ${fmtInt(cap)}` : '')));
    if (total > cap) {
      const all = make('button', 'linky', `show all ${fmtInt(total)}`);
      all.type = 'button';
      all.addEventListener('click', () => buildQueryList(total));
      count.append(all);
    } else if (total > QLIST_MAX) {
      const fewer = make('button', 'linky', 'show fewer');
      fewer.type = 'button';
      fewer.addEventListener('click', () => buildQueryList(QLIST_MAX));
      count.append(fewer);
    }

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
    const seg = $('ground-layout');
    if (seg) {
      seg.querySelectorAll('button').forEach((b) => {
        b.addEventListener('click', () => {
          layoutMode = b.dataset.layout;
          seg.querySelectorAll('button').forEach((o) => o.setAttribute(
            'aria-pressed', String(o === b)));
          // Both layouts are already built; this only chooses which to paint.
          layout = (layoutMode === 'projection' && projLayout)
            ? projLayout : cellLayout;
          describeLayout();
          paint($('ground-canvas'), false);
          paint($('trace-canvas'), true);
        });
      });
    }
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
