/* oneground lab — lab.js
   ---------------------------------------------------------------------------
   The interface for `oneground lab`. It draws what the server sends and
   nothing else: every number on the page is a figure or a caption from a
   drawing the lab's views produced, and every request goes back to the same
   server with this session's token. There is no other origin to reach, and the
   server's Content-Security-Policy would refuse one.

   What this file does on its own is layout: it places the vectors of a drawing
   in cells by the home region the drawing states, and colours them by the copy
   count the drawing states. It computes no measurement.

   The epsilon control follows the render mode the server measured at startup
   (task 023b):
     redraw on move     every move of the control asks for a new drawing, with
                        at most one request in flight and the latest position
                        always drawn last
     render on release  moving the control only updates its readout and says
                        which epsilon the drawing on screen belongs to; letting
                        go asks for the new drawing
*/
'use strict';

(function () {
  const TOKEN = document.querySelector('meta[name="oneground-lab-token"]').content;
  const RAMP = ['#3D7EB8', '#7FA3B0', '#B79C63', '#E0A83A'];
  const SLATE = [0x1B, 0x24, 0x32];
  const MOVE = 'redraw on move';
  const RELEASE = 'render on release';
  const STATIC = 'no epsilon control';

  const $ = (id) => document.getElementById(id);
  const fmtInt = (n) => Number(n).toLocaleString('en-US');

  function hex(h) {
    const v = parseInt(h.slice(1), 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  const RAMP_RGB = RAMP.map(hex);

  async function api(path, params) {
    const query = new URLSearchParams(params || {}).toString();
    const response = await fetch(path + (query ? '?' + query : ''), {
      headers: { 'X-Oneground-Token': TOKEN },
      credentials: 'omit',
      cache: 'no-store',
      referrerPolicy: 'no-referrer',
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || String(response.status));
    return body;
  }

  function text(el, value) { el.textContent = value; return el; }
  function make(tag, cls, value) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (value !== undefined) el.textContent = value;
    return el;
  }

  // ------------------------------------------------------------ state held
  let run = null;          // /api/run: declared facts about the run
  let layout = null;       // per-vector pixel positions, fixed by home region
  let lastGround = null;   // the ground drawing on screen
  let lastTrace = null;    // the trace drawing on screen
  let shownEpsilon = null; // the epsilon the drawing on screen belongs to

  // --------------------------------------------------------------- layout
  const GUTTER = 3;        // the widest outline's weight
  // Cells by home region. Home region does not depend on epsilon, so this is
  // computed once from the first drawing and every later drawing only
  // recolours the same pixels.
  function buildLayout(points, regionCount) {
    const homes = points.data.home_region;
    const ids = points.data.vector_id;
    const members = Array.from({ length: regionCount }, () => []);
    for (let i = 0; i < ids.length; i++) members[homes[i]].push(i);
    let largest = 1;
    for (const m of members) largest = Math.max(largest, m.length);
    const side = Math.ceil(Math.sqrt(largest));
    const columns = Math.ceil(Math.sqrt(regionCount));
    // A 3-pixel gutter on every side of a cell: the trace outlines are drawn
    // in it, so no outline ever covers a vector's pixel.
    const cell = side + 2 * GUTTER;
    const width = columns * cell;
    const rows = Math.ceil(regionCount / columns);
    const at = new Int32Array(ids.length);
    const cellOrigin = [];
    members.forEach((list, region) => {
      const cx = (region % columns) * cell + GUTTER;
      const cy = Math.floor(region / columns) * cell + GUTTER;
      cellOrigin[region] = [cx, cy];
      list.forEach((index, k) => {
        at[index] = (cy + Math.floor(k / side)) * width + cx + (k % side);
      });
    });
    return { at, width, height: rows * cell, cell, side, cellOrigin };
  }

  function paintGround() {
    if (!lastGround || !layout) return;
    const canvas = $('ground-canvas');
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
      const colour = RAMP_RGB[Math.min(copies[i], RAMP_RGB.length) - 1];
      const o = layout.at[i] * 4;
      px[o] = colour[0]; px[o + 1] = colour[1]; px[o + 2] = colour[2];
    }
    ctx.putImageData(image, 0, 0);
    paintTraceOutlines(ctx);
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
    const [, link, point] = lastTrace.marks;
    for (const region of new Set(point.data.home_region)) outline(ctx, region, '#E7EAEF', 1);
    link.data.region.forEach((region, i) => {
      if (i > 0) outline(ctx, region, '#8B96A5', 2);
    });
    outline(ctx, lastTrace.figures.routed_region, '#C99A3B', 3);
  }

  // ----------------------------------------------------------- the ground
  function showGround(drawing) {
    lastGround = drawing;
    if (!layout) layout = buildLayout(drawing.marks[0], drawing.marks[1].data.region.length);
    const f = drawing.figures;
    shownEpsilon = f.epsilon;
    text($('c-copied'), f.vectors_copied === undefined ? '—' : fmtInt(f.vectors_copied));
    text($('c-amp'), f.storage_amplification === undefined ? '—' : f.storage_amplification.toFixed(3) + '×');
    text($('c-p99'), f.p99_copies === undefined ? '—' : String(f.p99_copies));
    text($('c-ceiling'), f.routing_ceiling_at_k === undefined ? '—' : f.routing_ceiling_at_k.toFixed(4));
    const legend = $('legend');
    legend.replaceChildren();
    (f.copies_histogram || []).forEach((count, i) => {
      const item = make('span');
      item.append(make('span', 'swatch c' + Math.min(i + 1, 4)),
                  document.createTextNode(`${i + 1}: ${fmtInt(count)} (${f.copies_histogram_pct[i]}%)`));
      legend.append(item);
    });
    text($('ground-caption'), drawing.caption);
    listGaps($('ground-gaps'), drawing.gaps);
    $('eps-stale').hidden = true;
    paintGround();
  }

  function listGaps(list, gaps) {
    list.replaceChildren();
    Object.entries(gaps || {}).forEach(([name, reason]) => {
      list.append(make('li', null, `${name}: ${reason.replace(/^couldnt_check:\s*/, '')}`));
    });
  }

  // ------------------------------------------------------------ the trace
  function showTrace(drawing) {
    lastTrace = drawing;
    const f = drawing.figures;
    const [region, link, point] = drawing.marks;
    const steps = $('trace-steps');
    steps.replaceChildren();
    const step = (what, detail) => {
      const li = make('li', null, what);
      li.append(make('span', 'detail', detail));
      steps.append(li);
    };
    step(`scored against ${region.data.region.length} regions`,
         region.data.region.map((r, i) => `${r} (${region.data.distance[i].toFixed(3)})`).join(' · '));
    step(`routed to region ${f.routed_region}`,
         link.data.region.map((r, i) => `${r}: ${link.data.reason[i]}`).join(' · '));
    const outside = f.outside_routed_region === undefined ? 'couldn’t check' : `${f.outside_routed_region} of ${point.data.rank.length}`;
    step(`its true neighbours: ${f.true_neighbours_located} located, outside the routed region ${outside}`,
         point.data.vector_id.map((v, i) => `#${v} in ${point.data.home_region[i]}`).join(' · '));
    showRecall(drawing.panels.recall);
    listGaps($('trace-gaps'), drawing.gaps);
    paintGround();
  }

  function showRecall(panel) {
    const box = $('recall');
    box.replaceChildren();
    box.classList.toggle('not-simulated', panel.status !== 'simulated');
    if (panel.status === 'simulated') {
      const f = panel.figures;
      box.append(make('h3', null, `recall at ε ${panel.epsilon} — simulated`),
                 make('p', 'value', `recall@${f.k} ${f.recall_at_k.toFixed(2)}`),
                 make('p', 'source', `${fmtInt(f.candidates_returned)} candidates returned · missed by the route ${f.missed_by_route}`));
      return;
    }
    box.append(make('h3', 'status', `${panel.status} (${panel.epsilon})`),
               make('p', null, 'Recall, candidates and missed neighbours exist only where a run simulated them. Nothing here is interpolated.'),
               make('p', 'source', `simulated: ${panel.simulated_epsilons.join(', ')}`));
    const cost = panel.cost_minutes;
    box.append(make('p', 'source', typeof cost === 'string'
      ? cost.replace(/^couldnt_check:\s*/, 'couldn’t check the cost: ')
      : `simulating it costs ${cost.low}–${cost.high} min (${cost.basis})`));
    box.append(make('p', null, 'To simulate this ε, run this yourself — the lab does not:'));
    const grid = panel.action.grid ? `\n\n# with, under simulate.grid:\n${JSON.stringify(panel.action.grid)}` : '';
    box.append(make('pre', null, panel.action.command + grid));
  }

  // --------------------------------------------------------- the control
  let inFlight = false;
  let pending = null;

  async function drawAt(epsilon) {
    if (inFlight) { pending = epsilon; return; }
    inFlight = true;
    try {
      const params = epsilon === null ? {} : { epsilon: epsilon };
      const [ground, trace] = await Promise.all([
        api('/api/ground', params),
        api('/api/trace', Object.assign({ query: $('query').value || 0 }, params)),
      ]);
      lastTrace = trace;
      showGround(ground);
      showTrace(trace);
    } catch (error) {
      text($('ground-caption'), `error: ${error.message}`);
    } finally {
      inFlight = false;
      if (pending !== null) { const next = pending; pending = null; drawAt(next); }
    }
  }

  async function redrawTrace() {
    const params = { query: $('query').value || 0 };
    if (run.epsilon !== null) params.epsilon = sliderEpsilon();
    try {
      showTrace(await api('/api/trace', params));
    } catch (error) {
      text($('trace-gaps'), `error: ${error.message}`);
    }
  }

  const sliderEpsilon = () => Number($('eps').value);

  function onMove() {
    const e = sliderEpsilon();
    text($('eps-out'), e.toFixed(3));
    if (run.render.mode === MOVE) { drawAt(e); return; }
    const stale = $('eps-stale');
    stale.hidden = false;
    text(stale, `showing ε ${Number(shownEpsilon).toFixed(3)}; release to redraw at ${e.toFixed(3)}`);
  }

  function onRelease() {
    if (run.render.mode !== MOVE) drawAt(sliderEpsilon());
  }

  // ------------------------------------------------------ render verdicts
  const VERDICT_WORDS = {
    within: 'every reading within the threshold',
    straddled: 'the readings straddled the threshold',
    above: 'above the threshold',
  };
  function readings(r) {
    const n = r.readings_ms.length;
    return `${n} reading${n === 1 ? '' : 's'} of ${r.draws} draws`;
  }

  // ---------------------------------------------------------------- check
  function showCheck(check) {
    const dl = $('check');
    dl.replaceChildren();
    const row = (term, value, cls) => {
      dl.append(make('dt', null, term), make('dd', cls, value));
    };
    row('workdir', check.workdir);
    (check.also || []).forEach((dir) => row('also', dir));
    check.digests.forEach((entry) => {
      if (!entry.manifest) { row('digests', `${entry.directory}: ${entry.note}`, 'unverified'); return; }
      const good = entry.files.filter((f) => f.verified).length;
      const sep = entry.directory.includes('\\') ? '\\' : '/';
      row('digests', `${entry.directory}${sep}MANIFEST.sha256: ${good} of ${entry.files.length} verified`,
          entry.all_verified ? null : 'unverified');
    });
    const r = check.render;
    row('render mode', r.p95_ms === null ? r.mode
      : `${r.mode} (${r.chosen_by}; ${VERDICT_WORDS[r.verdict]}: ground draw p95 ${r.readings_ms.join(' / ')} ms ` +
        `over ${readings(r)}; threshold ${r.threshold_ms} ms, ` +
        `${Math.round(r.margin * 100)}% inside the ${r.frame_ms} ms frame)`);
    row('writes', check.writes);
    row('token', check.token);
  }

  // ----------------------------------------------------------------- boot
  async function boot() {
    run = await api('/api/run');
    text($('config'), run.config_label);
    text($('run-line'), `${fmtInt(run.n_base)} vectors · ${fmtInt(run.n_queries)} queries · ${run.family}`);
    const r = run.render;
    text($('mode'), r.p95_ms === null ? `rendering: ${r.mode}`
      : `rendering: ${r.mode} — ${VERDICT_WORDS[r.verdict]}: ground draw p95 ${r.readings_ms.join(' / ')} ms ` +
        `over ${readings(r)} on this host ` +
        `against ${r.threshold_ms} ms (${Math.round(r.margin * 100)}% inside the ${r.frame_ms} ms frame)` +
        (r.chosen_by === '--mode' ? ` — chosen by --mode; measured: ${r.measured_mode}` : ''));

    // The page's own URL may name where to start: `epsilon` and `query`,
    // beside the token. They set the control; they are not sent anywhere else.
    const start = new URLSearchParams(location.search);
    const query = $('query');
    query.max = String(run.n_queries - 1);
    if (start.has('query')) {
      query.value = String(Math.min(run.n_queries - 1, Math.max(0, Number(start.get('query')) || 0)));
    }

    const slider = $('eps');
    let initial = run.epsilon;
    if (run.epsilon === null || r.mode === STATIC) {
      slider.disabled = true;
      text($('eps-simulated'), 'this family has no epsilon');
    } else {
      slider.max = String(run.epsilon_max);
      if (start.has('epsilon') && Number.isFinite(Number(start.get('epsilon')))) {
        initial = Math.min(run.epsilon_max, Math.max(0, Number(start.get('epsilon'))));
      }
      slider.value = String(initial);
      text($('eps-out'), Number(initial).toFixed(3));
      text($('eps-simulated'), `simulated at ε ${run.simulated_epsilons.join(', ')}`);
      slider.addEventListener('input', onMove);
      slider.addEventListener('change', onRelease);
    }
    query.addEventListener('change', redrawTrace);
    $('prev').addEventListener('click', () => { query.value = Math.max(0, Number(query.value) - 1); redrawTrace(); });
    $('next').addEventListener('click', () => { query.value = Math.min(run.n_queries - 1, Number(query.value) + 1); redrawTrace(); });

    showCheck(await api('/api/check'));
    await drawAt(initial === null ? null : initial);
  }

  boot().catch((error) => text($('config'), `the lab could not load: ${error.message}`));
})();
