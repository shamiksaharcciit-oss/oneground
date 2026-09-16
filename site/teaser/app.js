/* oneground teaser — app.js
   ---------------------------------------------------------------------------
   No framework, no build step, no CDN, no telemetry. Two rules govern this
   file:

     1. Nothing on the page is a constant typed in here. Every number comes
        from data/values.json (published, or measured by the export) or is
        recomputed in this file from data/base.bin. The one exception is the
        page's own prose, which states no figures.

     2. The interaction is real. Moving epsilon does not look up a precomputed
        frame: it recounts copies for all 150,000 vectors from the four
        centroid distances each one carries, using the same rule the fixture
        uses. The page checks itself against the export's own sweep at load,
        and says so loudly if the two disagree.

   Loading. Chrome and Edge refuse fetch() and XMLHttpRequest against file://
   URLs, so a page opened by double-clicking cannot read its own data
   directory. Over http(s) the four data files are fetched directly; on file://
   a <script src="data/inline.js"> carries the same four files gzipped and
   base64'd, and is injected only in that case. The protocol is checked up
   front rather than after a failed fetch, so neither path logs an error.
*/

'use strict';

(function () {

// --------------------------------------------------------------- constants
// Every colour here is either a design token (docs/design/tokens.css) or the
// derived closure ramp declared beside it in style.css. The three outcome
// colours are used only where an outcome is being stated.
const TOKENS = {
  slate: '#1B2432', panel: '#243040', ink: '#E7EAEF', muted: '#8B96A5',
  ochre: '#C99A3B', teal: '#4FC1AD', coral: '#E36C5E', amber: '#D9A441',
};
const COPIES_RAMP = ['#3D7EB8', '#7FA3B0', '#B79C63', '#E0A83A'];  // 1..4
const CANVAS_BG = '#161D28';
const GROUND_DIM = '#2E3B4C';       // the ground, out of focus
const REGION_LIT = '#5E82AE';       // the region a query routes to

// The release these numbers were produced under. The only two outward links
// on the page are this one and PyPI, and neither is fetched until clicked.
const RELEASE_URL = 'https://github.com/shamiksaharcciit-oss/oneground/releases/tag/v0.1.0-preview';

const OUTCOMES = ['meets', 'fails', 'couldnt_check'];
const OUTCOME_LABEL = { meets: 'meets', fails: 'fails', couldnt_check: "couldn't check" };

// A muted categorical scale for the 37 top-level arXiv categories. Held well
// below the saturation of the outcome colours on purpose: these are labels,
// not verdicts, and must not read as one.
function categoryColour(i, n) {
  const h = (i * 360 / n + 18) % 360;
  const l = 56 + ((i % 3) - 1) * 7;
  return hslHex(h, 42, l);
}

const $ = (id) => document.getElementById(id);
const boot = $('boot');

// --------------------------------------------------------------- utilities

function hslHex(h, s, l) {
  s /= 100; l /= 100;
  const k = (n) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  const c = (n) => Math.round(255 * f(n)).toString(16).padStart(2, '0');
  return '#' + c(0) + c(8) + c(4);
}

// Pixels are written through a Uint32Array view over the ImageData, which is
// the whole reason a 150,000-point repaint fits in a frame. That makes the
// packing byte-order dependent, so it is measured rather than assumed.
const LITTLE_ENDIAN = (function () {
  const b = new ArrayBuffer(4);
  new Uint32Array(b)[0] = 0x11223344;
  return new Uint8Array(b)[0] === 0x44;
})();

function pack(hex) {
  const v = parseInt(hex.slice(1), 16);
  const r = (v >> 16) & 0xFF, g = (v >> 8) & 0xFF, b = v & 0xFF;
  return LITTLE_ENDIAN
    ? ((0xFF << 24) | (b << 16) | (g << 8) | r) >>> 0
    : ((r << 24) | (g << 16) | (b << 8) | 0xFF) >>> 0;
}

const fmtInt = (n) => n.toLocaleString('en-US');
const fmtPct = (x, dp) => (x * 100).toFixed(dp === undefined ? 0 : dp) + '%';
const short = (d) => d.slice(0, 8) + '…';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function fail(message, detail) {
  boot.hidden = false;
  boot.textContent = '';
  boot.appendChild(el('p', 'err', message));
  if (detail) boot.appendChild(el('p', 'source', detail));
}

/* Cache-busting for the data directory.
   ---------------------------------------------------------------------------
   Pages sets its own cache headers and a CDN sits in front of them, so a
   returning reader can be served a stale base.bin beside a fresh values.json.
   The page would catch that -- it checks base.bin's length against
   values.json and recounts the closure at the reference epsilon before it
   renders -- but catching it and refusing to render is a worse outcome than
   not getting a stale file in the first place.

   So each data URL carries ?v=<first 8 hex of that file's sha256>, taken from
   data/MANIFEST.sha256 at export time. A new export changes the digest,
   changes the URL, and the cache has nothing to serve. The four files are
   still fetched in parallel: the token is here, not in the data, so there is
   no round trip to discover it.

   The block below is written by corpora/export_teaser_data.py. Editing it by
   hand achieves nothing -- the next export overwrites it -- and
   verify_teaser_data.py fails if it disagrees with the manifest. */

// --- generated by corpora/export_teaser_data.py --- do not edit by hand ---
const DATA_VERSION = {"base.bin": "08268d20", "centroids.json": "26cd059b", "inline.js": "793c00ae", "queries.json": "97289c3a", "values.json": "deada30f"};
// --- end generated ---

// ----------------------------------------------------------------- loading

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error('could not load ' + src));
    document.head.appendChild(s);
  });
}

function b64ToBytes(s) {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function gunzip(bytes) {
  const stream = new Blob([bytes]).stream()
    .pipeThrough(new DecompressionStream('gzip'));
  return new Response(stream).arrayBuffer();
}

async function loadOverHttp() {
  const get = (name, as) => {
    const v = DATA_VERSION[name];
    return fetch('data/' + name + (v ? '?v=' + v : '')).then((r) => {
      if (!r.ok) throw new Error('data/' + name + ' — HTTP ' + r.status);
      return as === 'json' ? r.json() : r.arrayBuffer();
    });
  };
  const [values, centroids, queries, base] = await Promise.all([
    get('values.json', 'json'), get('centroids.json', 'json'),
    get('queries.json', 'json'), get('base.bin', 'buf'),
  ]);
  return { values, centroids, queries, base, via: 'fetch' };
}

async function loadFromFile() {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('This browser has no DecompressionStream, which the ' +
      'file:// path needs. Serve this directory over http instead — any ' +
      'static server will do.');
  }
  await loadScript('data/inline.js');
  const bundle = window.__ONEGROUND_TEASER__;
  if (!bundle || !bundle.files) throw new Error('data/inline.js loaded but was empty');
  const one = async (name) => gunzip(b64ToBytes(bundle.files[name].gzip_b64));
  const text = async (name) => JSON.parse(new TextDecoder().decode(await one(name)));
  return {
    values: await text('values.json'),
    centroids: await text('centroids.json'),
    queries: await text('queries.json'),
    base: await one('base.bin'),
    via: 'inline.js (file://)',
  };
}

// base.bin is a struct-of-arrays; values.json carries the layout so the
// offsets live in the data rather than in this file.
function columns(buffer, values) {
  const spec = values.base_bin;
  if (buffer.byteLength !== spec.bytes) {
    throw new Error('base.bin is ' + buffer.byteLength + ' bytes, values.json ' +
      'says ' + spec.bytes);
  }
  const out = { n: spec.rows };
  for (const c of spec.columns) {
    out[c.name] = c.dtype === 'float32'
      ? new Float32Array(buffer, c.offset, c.count)
      : new Uint8Array(buffer, c.offset, c.count);
  }
  return out;
}

// ------------------------------------------------------------- the closure
// The rule the fixture uses, in `oneground/measures` and re-applied by
// corpora/export_ground_view.py:
//
//     a vector is stored in region j when d_j <= d_1 * (1 + eps)
//
// counted over the four nearest regions, because the spec's semantic_sharded
// reference configuration stores at most four copies. Each of the four is
// tested against the limit independently, exactly as the numpy does.

function recount(D, eps, copies) {
  const n = D.n, d1 = D.d1, d2 = D.d2, d3 = D.d3, d4 = D.d4;
  const f = 1 + eps;
  let total = 0, copied = 0;
  const hist = [0, 0, 0, 0];
  for (let i = 0; i < n; i++) {
    const lim = d1[i] * f;
    let c = 1;
    if (d2[i] <= lim) c++;
    if (d3[i] <= lim) c++;
    if (d4[i] <= lim) c++;
    copies[i] = c;
    hist[c - 1]++;
    total += c;
    if (c > 1) copied++;
  }
  // p99 the way numpy's percentile(..., method='lower') takes it: the value at
  // the floor of the virtual index, read off the histogram instead of sorting.
  const k = Math.floor(0.99 * (n - 1));
  let acc = 0, p99 = 1;
  for (let c = 1; c <= 4; c++) {
    acc += hist[c - 1];
    if (acc > k) { p99 = c; break; }
  }
  return { hist, copied, p99, amplification: total / n };
}

// -------------------------------------------------------------- the ground

function Ground(canvas, D) {
  this.canvas = canvas;
  this.ctx = canvas.getContext('2d', { alpha: false });
  this.D = D;
  this.w = 0; this.h = 0;

  let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity;
  for (let i = 0; i < D.n; i++) {
    const x = D.x[i], y = D.y[i];
    if (x < minx) minx = x; if (x > maxx) maxx = x;
    if (y < miny) miny = y; if (y > maxy) maxy = y;
  }
  this.bounds = { minx, maxx, miny, maxy };
}

Ground.prototype.layout = function () {
  const r = this.canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.max(1, Math.round(r.width * dpr));
  const h = Math.max(1, Math.round(r.height * dpr));
  if (w === this.w && h === this.h) return false;

  this.canvas.width = w; this.canvas.height = h;
  this.w = w; this.h = h; this.dpr = dpr;
  this.img = this.ctx.createImageData(w, h);
  this.buf = new Uint32Array(this.img.data.buffer);
  this.stamp = dpr >= 2 || w > 900;      // two device pixels wide, so a dot is a dot

  const pad = Math.round(12 * dpr);
  const b = this.bounds;
  const s = Math.min((w - 2 * pad) / (b.maxx - b.minx),
                     (h - 2 * pad) / (b.maxy - b.miny));
  const ox = (w - (b.maxx - b.minx) * s) / 2 - b.minx * s;
  const oy = (h - (b.maxy - b.miny) * s) / 2 - b.miny * s;
  this.scale = s; this.ox = ox; this.oy = oy;

  const n = this.D.n, X = this.D.x, Y = this.D.y;
  const px = new Int32Array(n), py = new Int32Array(n);
  const xmax = w - 2, ymax = h - 2;
  for (let i = 0; i < n; i++) {
    let a = (X[i] * s + ox) | 0;
    let c = (h - (Y[i] * s + oy)) | 0;      // flip y so the picture reads up
    px[i] = a < 0 ? 0 : (a > xmax ? xmax : a);
    py[i] = c < 0 ? 0 : (c > ymax ? ymax : c);
  }
  this.px = px; this.py = py;
  return true;
};

Ground.prototype.place = function (i) {
  return [this.px[i] / this.dpr, this.py[i] / this.dpr];
};

Ground.prototype.placeXY = function (x, y) {
  return [(x * this.scale + this.ox) / this.dpr,
          (this.h - (y * this.scale + this.oy)) / this.dpr];
};

Ground.prototype.clear = function () { this.buf.fill(pack(CANVAS_BG)); };

Ground.prototype.blit = function () { this.ctx.putImageData(this.img, 0, 0); };

/* Paint every point whose `key[i] === cls`, in the given colour.
   150,000 points overplot heavily, so the classes are painted in a fixed
   order by the caller and the rarest class goes on last: at eps 0.20 the
   four-copy class is 84% of the corpus and would otherwise bury the 3.6% that
   is stored once. The order is a drawing choice; the counts beside the
   picture are the measurement. */
Ground.prototype.paintClass = function (key, cls, colour) {
  const buf = this.buf, w = this.w, px = this.px, py = this.py, n = this.D.n;
  const c = pack(colour), s = this.stamp;
  for (let i = 0; i < n; i++) {
    if (key[i] !== cls) continue;
    const idx = py[i] * w + px[i];
    buf[idx] = c;
    if (s) { buf[idx + 1] = c; buf[idx + w] = c; buf[idx + w + 1] = c; }
  }
};

Ground.prototype.paintAll = function (colour) {
  const buf = this.buf, w = this.w, px = this.px, py = this.py, n = this.D.n;
  const c = pack(colour), s = this.stamp;
  for (let i = 0; i < n; i++) {
    const idx = py[i] * w + px[i];
    buf[idx] = c;
    if (s) { buf[idx + 1] = c; buf[idx + w] = c; buf[idx + w + 1] = c; }
  }
};

// ================================================================= the page

function start(data) {
  const values = data.values;
  const D = columns(data.base, values);
  const Q = data.queries.queries;
  const curated = data.queries.curated;
  const centroids = data.centroids;
  const cats = values.categories || [];

  const copies = new Uint8Array(D.n);
  const catColours = [];
  for (let i = 0; i < 256; i++) {
    catColours.push(categoryColour(i, Math.max(cats.length, 8)));
  }

  // ---- the self-check ----------------------------------------------------
  // The export measured the same sweep in Python. If this file's arithmetic
  // has drifted from it, the page is showing numbers that are not the
  // fixture's, and it says so instead of rendering.
  const refEps = values.geometry.reference_epsilon.toFixed(2);
  const here = recount(D, values.geometry.reference_epsilon, copies);
  const there = values.measured.eps_sweep[refEps];
  const agrees = there &&
    here.hist.every((v, i) => v === there.hist[i]) &&
    here.copied === there.copied && here.p99 === there.p99;
  if (!agrees) {
    fail('This page recounted the closure at ε = ' + refEps + ' and got a ' +
      'different answer from the export that produced its data.',
      'browser ' + JSON.stringify(here.hist) + ' · export ' +
      JSON.stringify(there && there.hist));
    return;
  }

  buildGround(values, D, Q, centroids, copies, catColours, cats);
  buildQuery(values, D, Q, curated, centroids);
  buildVerdict(values);
  buildRecommendation(values);
  buildSettle(values);
  buildReceipt(values, data.via);

  const V = values.verify;
  if (V) {
    const cal = V.calibration;
    $('calibration-line').textContent =
      'Simulator vs ' + V.engine.charAt(0).toUpperCase() + V.engine.slice(1) +
      ' ' + V.engine_version + ' on this corpus: ' +
      cal.error_recall.toFixed(4).replace('-', '−') +
      ' recall@10 (simulated ' +
      cal.simulated_recall_at_10 + ', measured ' + cal.measured_recall_at_10 +
      '), measured ' + V.date + ', environment ' + V.environment_id + '.';
  }
  $('footer-gen').textContent = 'exported ' + values.generated_at +
    ' · loaded via ' + data.via;
  boot.hidden = true;
  window.__oneground_first_paint = performance.now();

  if (new URLSearchParams(location.search).has('selftest')) {
    selfTest(D, values.geometry.reference_epsilon.toFixed(2));
  }
}

// ------------------------------------------------------ 1. hero: the ground

function buildGround(values, D, Q, centroids, copies, catColours, cats) {
  const canvas = $('ground-canvas');
  const g = new Ground(canvas, D);
  const slider = $('eps');
  const cap = values.geometry.max_assign;
  let mode = 'copies';
  let stats = null;
  let lastMs = 0;

  slider.value = values.geometry.reference_epsilon.toFixed(2);

  const legend = $('legend');
  const rows = [];
  for (let c = 1; c <= cap; c++) {
    const row = el('div', 'legend-row');
    const sw = el('span', 'swatch');
    sw.style.background = COPIES_RAMP[c - 1];
    row.appendChild(sw);
    const bar = el('div', 'bar');
    const fillEl = document.createElement('i');
    fillEl.style.background = COPIES_RAMP[c - 1];
    bar.appendChild(fillEl);
    row.appendChild(bar);
    const pct = el('span', 'pct', '—');
    row.appendChild(pct);
    row.title = c + (c === 1 ? ' copy' : ' copies');
    legend.appendChild(row);
    rows.push({ fill: fillEl, pct });
  }

  function caption(s) {
    const n = D.n;
    const p4 = s.hist[cap - 1] / n;
    const multi = s.copied / n;
    const crisp = values.measured.boundary_crispness;
    if (s.copied === 0) {
      return 'At ε = 0.00 every vector sits within ε of exactly one region — ' +
        'one copy each, 1.000× storage, and routing to that one region finds <b>' +
        fmtPct(values.measured.one_region_recall_at_10, 1) + '</b> of true ' +
        'neighbours. The boundaries are still there: <b>' + fmtPct(1 - crisp) +
        '</b> of vectors have a second centroid inside 1.20× of the first.';
    }
    if (p4 >= 0.5) {
      return '<b>' + fmtPct(p4) + '</b> of vectors sit within ε of four regions. ' +
        'There is no boundary to shard on.';
    }
    return '<b>' + fmtPct(p4) + '</b> of vectors sit within ε of four regions, <b>' +
      fmtPct(multi) + '</b> within ε of more than one. There is no boundary to ' +
      'shard on.';
  }

  function repaint() {
    if (mode === 'copies') {
      g.clear();
      // rarest class last, so 3.6% is not buried under 84%
      const order = [4, 3, 2, 1].sort((a, b) =>
        (stats.hist[b - 1] - stats.hist[a - 1]));
      for (const c of order) g.paintClass(copies, c, COPIES_RAMP[c - 1]);
    } else {
      g.clear();
      g.paintAll(GROUND_DIM);
      const counts = new Int32Array(256);
      for (let i = 0; i < D.n; i++) counts[D.category[i]]++;
      const order = Array.from(counts.keys())
        .filter((c) => counts[c] > 0)
        .sort((a, b) => counts[b] - counts[a]);
      for (const c of order) g.paintClass(D.category, c, catColours[c]);
    }
    g.blit();
  }

  function update(recompute) {
    const t0 = performance.now();
    const eps = parseFloat(slider.value);
    if (recompute) stats = recount(D, eps, copies);
    const t1 = performance.now();
    repaint();
    const t2 = performance.now();

    $('eps-out').textContent = eps.toFixed(2);
    $('c-copied').textContent = fmtInt(stats.copied);
    $('c-amp').textContent = stats.amplification.toFixed(3) + '×';
    $('c-p99').textContent = String(stats.p99);
    for (let c = 1; c <= cap; c++) {
      const frac = stats.hist[c - 1] / D.n;
      rows[c - 1].fill.style.width = (frac * 100).toFixed(2) + '%';
      rows[c - 1].pct.textContent = fmtPct(frac, 1);
    }
    $('ground-caption').innerHTML = caption(stats);

    const t3 = performance.now();
    lastMs = t3 - t0;
    window.__oneground_timing = {
      recount: +(t1 - t0).toFixed(2),
      paint: +(t2 - t1).toFixed(2),
      dom: +(t3 - t2).toFixed(2),
      total: +lastMs.toFixed(2),
    };
    $('ground-source').textContent = sourceLine + lastMs.toFixed(0) + ' ms';
  }

  // One short line under the caption. Everything it used to carry -- the
  // closure rule, the copy cap, the published value it reproduces -- now sits
  // in the epsilon control's expand, next to the control it describes,
  // instead of competing with the sentence above it.
  const sourceLine = 'base.bin:d1..d4 · recounted for ' + fmtInt(D.n) +
    ' vectors · ';

  const ref = values.published.reference_results.semantic_sharded;
  const ruleText =
    'A vector is stored in region j when d_j ≤ d_1 × (1 + ε), counted over ' +
    'its four nearest regions. Four is the copy cap of the semantic_sharded ' +
    'reference configuration in the spec — a property of that ' +
    'configuration, not of the corpus — which is why base.bin carries four ' +
    'distances per vector. At ε = ' +
    values.geometry.reference_epsilon.toFixed(2) + ' this page recounts ' +
    ref.storage_amplification + '×, the published value in ' +
    'fixtures/arxiv-150k.fixture.yaml:reference_results.semantic_sharded.';
  $('eps-rule').textContent = ruleText;
  $('eps-hint-summary').title = ruleText;

  slider.addEventListener('input', () => update(true));

  const bCopies = $('mode-copies'), bCat = $('mode-category');
  function setMode(m) {
    mode = m;
    bCopies.setAttribute('aria-pressed', String(m === 'copies'));
    bCat.setAttribute('aria-pressed', String(m === 'category'));
    $('ground-figcaption').textContent = m === 'copies'
      ? '2-D placement is UMAP and is illustrative. Regions, distances and copy counts are computed in the full 768 dimensions.'
      : cats.length + ' top-level arXiv categories. They separate here, in two ' +
        'dimensions; in 768 their boundaries do not.';
    update(false);
  }
  bCopies.addEventListener('click', () => setMode('copies'));
  bCat.addEventListener('click', () => setMode('category'));

  const onResize = () => { if (g.layout()) update(false); };
  observe(canvas, onResize);
  g.layout();
  update(true);

  window.__oneground_ground = { g, update, recountAt: (e) => {
    slider.value = String(e); update(true); return lastMs;
  } };
}

// ------------------------------------------------ 2. one query, every hop

function buildQuery(values, D, Q, curated, centroids) {
  const canvas = $('query-canvas');
  const g = new Ground(canvas, D);
  const ctx = g.ctx;
  const list = $('query-list');
  const cache = document.createElement('canvas');
  const cctx = cache.getContext('2d', { alpha: false });

  const still = window.matchMedia &&
                window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let current = null, step = 0, t0 = 0, raf = 0, buttons = [], visible = true;
  let timers = [];

  function label(i) {
    const q = Q[i];
    const b = el('button');
    b.type = 'button';
    b.dataset.miss = String(q.outside);
    b.appendChild(document.createTextNode(q.title));
    const m = el('span', 'miss', q.outside + ' of 10 neighbours outside the routed region');
    b.appendChild(m);
    b.addEventListener('click', () => select(i));
    return b;
  }

  for (const i of curated) {
    const b = label(i);
    list.appendChild(b);
    buttons.push({ i, b });
  }

  $('surprise').addEventListener('click', () => {
    const i = Math.floor(Math.random() * Q.length);
    select(i, true);
  });

  function paintBase(q) {
    g.clear();
    g.paintAll(GROUND_DIM);
    if (step >= 2) g.paintClass(D.region, q.region, REGION_LIT);
    g.blit();
    cache.width = g.w; cache.height = g.h;
    cctx.drawImage(canvas, 0, 0);
  }

  function frame() {
    raf = 0;
    if (!current || !g.w) return;
    const q = current;
    const t = still ? 0.35 : (performance.now() - t0) / 1000;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(cache, 0, 0, g.w, g.h, 0, 0, g.w, g.h);
    ctx.setTransform(g.dpr, 0, 0, g.dpr, 0, 0);

    const [qx, qy] = g.placeXY(q.x, q.y);

    // step 2 — the centroid of the region it routed to
    if (step >= 2) {
      const c = centroids[q.region];
      if (c && c.x !== null) {
        const [cx, cy] = g.placeXY(c.x, c.y);
        ctx.strokeStyle = REGION_LIT;
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(cx, cy, 7, 0, 6.2832); ctx.stroke();
      }
    }

    // step 3 — the ten true neighbours: ink, with a thin ring.
    // Not coral. A true neighbour is not an outcome, and the three outcome
    // colours mean meets / fails / couldnt_check everywhere on the site.
    // The routed region is the only colour on this canvas; the neighbours
    // that fall outside it are told apart by the pulse, not by a hue.
    if (step >= 3) {
      for (let k = 0; k < q.nn.length; k++) {
        const idx = q.nn[k];
        const [nx, ny] = g.place(idx);
        const outside = D.region[idx] !== q.region;
        if (outside && step >= 4) {
          const pulse = 0.5 + 0.5 * Math.sin(t * 3.2 - k * 0.35);
          ctx.strokeStyle = TOKENS.ink;
          ctx.globalAlpha = 0.18 + 0.28 * pulse;
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(qx, qy); ctx.lineTo(nx, ny); ctx.stroke();
          ctx.beginPath(); ctx.arc(nx, ny, 4 + 5 * pulse, 0, 6.2832); ctx.stroke();
          ctx.globalAlpha = 1;
        }
        ctx.strokeStyle = TOKENS.ink;
        ctx.globalAlpha = 0.75;
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(nx, ny, 5, 0, 6.2832); ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.fillStyle = TOKENS.ink;
        ctx.beginPath(); ctx.arc(nx, ny, 2.4, 0, 6.2832); ctx.fill();
      }
    }

    // step 1 — the query itself. Same ink as its neighbours, heavier: the
    // difference between the query and its neighbours is weight, not colour.
    const ring = step === 1 ? 8 + 10 * (1 - Math.min(1, t * 1.6)) : 8;
    ctx.strokeStyle = TOKENS.ink;
    ctx.lineWidth = 1.8;
    ctx.beginPath(); ctx.arc(qx, qy, ring, 0, 6.2832); ctx.stroke();
    ctx.fillStyle = TOKENS.ink;
    ctx.beginPath(); ctx.arc(qx, qy, 3.6, 0, 6.2832); ctx.fill();
    ctx.setTransform(1, 0, 0, 1, 0, 0);

    // The only thing that keeps moving is the pulse on the neighbours the
    // routed region misses. Once they are all inside it, or the section is
    // scrolled away, or the reader asked for reduced motion, the loop stops.
    const moving = (step >= 4 && missCount(q) > 0) || (step === 1 && t < 0.8);
    if (!still && visible && moving) raf = requestAnimationFrame(frame);
  }

  function draw() {
    if (!raf) raf = requestAnimationFrame(frame);
  }

  function missCount(q) {
    if (!q) return 0;
    let n = 0;
    for (const idx of q.nn) if (D.region[idx] !== q.region) n++;
    return n;
  }

  function setStep(n, q) {
    step = n;
    for (const li of $('trace').children) {
      li.dataset.on = Number(li.dataset.step) <= n ? '1' : '0';
    }
    // Only the region layer depends on the step, and only at step 2.
    if (n <= 2) paintBase(q);
    draw();
  }

  function select(i, surprised) {
    const q = Q[i];
    current = q;
    for (const b of buttons) b.b.setAttribute('aria-pressed', String(b.i === i));
    if (surprised) {
      const exists = buttons.some((b) => b.i === i);
      if (!exists) {
        const b = label(i);
        b.setAttribute('aria-pressed', 'true');
        list.insertBefore(b, list.firstChild);
        buttons.unshift({ i, b });
        b.scrollIntoView({ block: 'nearest' });
      }
    }

    // Recomputed here, in the browser, from base.bin's region column against
    // the query's routed region -- not read from queries.json. The exported
    // value is then used to check this arithmetic.
    const outside = missCount(q);
    const mismatch = outside !== q.outside;

    const line = $('query-verdict');
    line.innerHTML = mismatch
      ? '<b>the browser and the export disagree about this query</b>'
      : '<b>' + outside + '</b> of 10 true neighbours are outside the region ' +
        'this query routes to.';

    $('query-source').textContent =
      'queries.json:nn (ground_truth.npy, exact brute force over all ' +
      fmtInt(D.n) + ') · base.bin:region · recall@10 at one-region routing ' +
      q.recall10_one_region.toFixed(1) + ' (queries.json:recall10_one_region)';

    $('query-figcaption').textContent = q.title;

    const size = centroids[q.region] ? centroids[q.region].size : 0;
    $('t1').textContent = 'd2 / d1 = ' + (q.ratio === null ? 'n/a' : q.ratio.toFixed(4)) +
      ' · ' + (q.ambiguous ? 'ambiguous (≤ ' + values.geometry.ambiguous_ratio + ')'
                          : 'not ambiguous (> ' + values.geometry.ambiguous_ratio + ')');
    $('t2').textContent = 'region ' + q.region + ' of ' + values.geometry.n_centroids +
      ' · ' + fmtInt(size) + ' vectors · second choice was region ' + q.region2;
    $('t3').textContent = 'the exact top ' + values.geometry.k +
      ' over all ' + fmtInt(D.n) + ' vectors';
    $('t4').textContent = (10 - outside) + ' of 10 found · ' + outside +
      ' in other regions · recall@10 ' + q.recall10_one_region.toFixed(1);

    // the trace, in order: score, route, neighbours, what was missed
    t0 = performance.now();
    for (const id of timers) clearTimeout(id);
    timers = [];
    setStep(1, q);
    const at = [520, 1100, 1750];
    [2, 3, 4].forEach((n, k) => timers.push(setTimeout(() => {
      if (current === q) { t0 = performance.now(); setStep(n, q); }
    }, still ? 0 : at[k])));
  }

  const onResize = () => { if (g.layout() && current) { paintBase(current); draw(); } };
  observe(canvas, onResize);

  // The pulse runs only while the section is on screen.
  if (typeof IntersectionObserver !== 'undefined') {
    new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting;
      if (visible) draw();
    }, { threshold: 0 }).observe(canvas);
  }

  g.layout();
  select(curated[0]);
}

// ------------------------------------------------------------ 3. the verdict

// The five constraints, each rendered from its own threshold. Named in the
// order the report judges them, and all five are named: a verdict that shows
// four of five constraints is a verdict with a hidden term.
function constraintPhrases(c) {
  const money = (m) => (m.currency === 'EUR' ? '€' : m.currency + ' ') +
    m.amount.toLocaleString('en-US');
  const out = [];
  if (c.recall_at_k) out.push('recall@' + c.recall_at_k.k + ' ≥ ' + c.recall_at_k.min);
  if (c.storage_amplification_max !== undefined) {
    out.push('storage ≤ ' + c.storage_amplification_max.toFixed(1) + '×');
  }
  if (c.latency) {
    out.push('p95 ≤ ' + c.latency.p95_ms + ' ms' +
      (c.latency.at_qps ? ' at ' + c.latency.at_qps + ' qps' : '') +
      (c.latency.concurrency ? ' / concurrency ' + c.latency.concurrency : ''));
    if (c.latency.at_qps) out.push('sustains ' + c.latency.at_qps + ' qps');
  }
  if (c.monthly_budget) out.push(money(c.monthly_budget) + '/month');
  return out;
}

const WORDS = ['no', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven'];

function buildVerdict(values) {
  const v = values.verdict;
  const c = v.constraints;
  const phrases = constraintPhrases(c);

  // Both halves come from report.json. "Nothing recommended" was true until a
  // verify run made it false, and a heading that has to be edited by hand when
  // the decision changes is a heading that will one day be wrong.
  const families = v.families.length;
  $('verdict-h').innerHTML =
    (WORDS[families] || families) + ' options. <em>' +
    (v.recommendation ? 'One recommended.' : 'Nothing recommended.') + '</em>';

  $('verdict-lede').textContent =
    'oneground judged ' + v.summary.options + ' configurations across ' +
    (WORDS[families] || families).toLowerCase() + ' architecture families ' +
    'against ' + phrases.length + ' constraints: ' + phrases.join(', ') + '. ' +
    (v.recommendation
      ? 'One meets every constraint that could be checked.'
      : 'Nothing was recommended, and the reason is written down.');

  const chips = $('verdict-summary');
  for (const o of OUTCOMES) {
    chips.appendChild(el('span', 'chip ' + o,
      v.summary[o] + ' ' + OUTCOME_LABEL[o]));
  }

  const blurbs = {
    single_node_hnsw: 'one index, one machine, one copy of every vector',
    hash_sharded: 'shards by hash — no semantics, no closure, no copies',
    semantic_sharded: 'shards by meaning, and copies each vector into every region within ε',
  };

  const host = $('verdict-families');
  for (const fam of v.families) {
    const card = el('div', 'family panel');
    const h = el('h3');
    h.appendChild(el('span', 'fam', fam.family));
    h.appendChild(el('span', 'source', fam.options.length +
      (fam.options.length === 1 ? ' configuration' : ' configurations')));
    card.appendChild(h);
    card.appendChild(el('p', 'blurb', blurbs[fam.family] || ''));
    const head = el('div', 'opt-head');
    head.appendChild(el('span', null, ''));
    head.appendChild(el('span', null, 'configuration'));
    head.appendChild(el('span', 'm', 'recall@10'));
    head.appendChild(el('span', 'm', 'storage'));
    head.appendChild(el('span', 'm', ''));
    card.appendChild(head);

    // One summary row per configuration -- params, recall@10, storage, the
    // outcome -- and the three constraint verdicts with their source fields
    // inside the <details>. Eight configurations at full height buried the
    // receipt and the promise below a very long scroll. Every number is still
    // in the DOM; they are just not all on screen at once.
    for (const o of fam.options) {
      const box = el('details', 'opt');
      const sum = el('summary');
      sum.appendChild(el('span', 'caret', '▸'));
      sum.appendChild(el('span', 'cfg',
        Object.entries(o.params).map(([k, v]) => k + '=' + v).join(' · ')));
      const m = o.measurement;
      const metric = (label, text) => {
        const e = el('span', 'm', text);
        e.dataset.l = label;   // shown only where the column header is not
        return e;
      };
      sum.appendChild(metric('recall@10',
        m.recall_at_10 === undefined ? '—' : m.recall_at_10.toFixed(4)));
      sum.appendChild(metric('storage',
        m.storage_amplification === undefined
          ? '—' : m.storage_amplification.toFixed(2) + '×'));
      sum.appendChild(el('span', 'chip ' + o.outcome, OUTCOME_LABEL[o.outcome]));
      sum.title = o.config;
      box.appendChild(sum);

      const cells = el('div', 'cells');
      for (const k of o.constraints) {
        const cell = el('div', 'cell ' + k.outcome);
        cell.appendChild(el('span', 'k', k.constraint + ' — ' + OUTCOME_LABEL[k.outcome]));
        cell.appendChild(el('span', 'v', k.reason));
        cell.appendChild(el('span', 'src', k.source));
        cells.appendChild(cell);
      }
      if (o.indistinguishable_from && o.indistinguishable_from.length) {
        cells.appendChild(el('span', 'src', 'indistinguishable on recall from ' +
          o.indistinguishable_from.join(', ')));
      }
      box.appendChild(cells);
      card.appendChild(box);
    }
    host.appendChild(card);
  }

  const log = $('verdict-log');
  for (const e of v.decision_log_quoted) {
    const q = el('blockquote');
    q.appendChild(document.createTextNode(e.text));
    q.appendChild(el('span', 'src', e.source));
    log.appendChild(q);
  }

  const perOption = v.families[0].options[0].constraints.length;
  $('verdict-note').textContent =
    'Each row opens: its ' + perOption + ' constraint verdicts, each with the ' +
    'field it was read from. Nothing is summarised away — every number the ' +
    'report holds is on this page.';
  $('verdict-source').textContent = v.source + ' · run ' + v.run + ' · generated ' +
    v.generated_at + ' · ' + v.decision_log_quoted.length + ' of ' +
    v.decision_log_total + ' decision-log entries quoted verbatim · ' +
    'calibration tolerance ' + v.calibration.tolerance;
}

// ------------------------------------------------------------ 4. the receipt

function buildReceipt(values, via) {
  const r = values.receipt;
  const m = values.measured;
  const p = values.published;

  $('receipt-lede').textContent =
    'The same 150,000 records were embedded three times, in three ' +
    'environments. The sampling receipt came out byte-identical every time. ' +
    'The vectors did not, and neither did anything derived from them. Every ' +
    'published value still agreed — including here, on the laptop that ' +
    'exported this page, which is the fourth environment.';

  const t1 = $('receipt-same');
  t1.appendChild(headRow(['file', 'sha256', 'builds 1–3']));
  for (const row of r.identical_across_builds) {
    t1.appendChild(dataRow([
      [row.file, 'mono'],
      [short(row.sha256), 'mono same', row.sha256],
      ['identical', 'same'],
    ]));
  }

  const t2 = $('receipt-builds');
  t2.appendChild(headRow(['build', 'environment', 'vectors.npy sha256']));
  for (const b of r.builds) {
    t2.appendChild(dataRow([
      [String(b.build)],
      [b.environment + ' · ' + b.device],
      [short(b.vectors_sha256), 'mono differs', b.vectors_sha256],
    ]));
  }

  const t3 = $('receipt-values');
  t3.appendChild(headRow(['value', 'published', 'recomputed here']));
  const ch = p.characterization, ref = p.reference_results.semantic_sharded;
  const rows = [
    ['boundary_crispness', ch.boundary_crispness.value, m.boundary_crispness, ch.boundary_crispness.tolerance],
    ['ambiguous_query_rate', ch.ambiguous_query_rate.value, m.ambiguous_query_rate, ch.ambiguous_query_rate.tolerance],
    ['skew_top10_share', ch.skew_top10_share.value, m.skew_top10_share, ch.skew_top10_share.tolerance],
    ['storage_amplification', ref.storage_amplification, m.storage_amplification_at_eps_0_20, ref.tolerance],
  ];
  for (const [k, pub, got, tol] of rows) {
    const d = Math.abs(got - pub);
    t3.appendChild(dataRow([
      [k, 'mono'], [String(pub), 'mono'], [got.toFixed(4), 'mono'],
    ]));
    t3.appendChild(deltaRow(3, 'δ ' + d.toFixed(4) + ' ≤ tolerance ' + tol,
                            d <= tol));
  }
  const dr = ch.drift;
  t3.appendChild(dataRow([
    ['drift pair', 'mono'],
    [dr.value_before + ' / ' + dr.value_after, 'mono'],
    ['—', 'mono'],
  ]));
  t3.appendChild(deltaRow(3, 'not recomputed here · builds 1/2/3 published ' +
    r.builds.map((b) => b.drift_before + '/' + b.drift_after).join(' · ') +
    ' · spread 0.002 ≤ tolerance ' + dr.tolerance, null));

  $('receipt-values-source').textContent =
    'published: fixtures/arxiv-150k.fixture.yaml:characterization and ' +
    ':reference_results · recomputed: corpora/export_teaser_data.py on ' +
    m.environment.platform + ', python ' + m.environment.python + ', numpy ' +
    m.environment.numpy + ', faiss ' + m.environment.faiss;

  const release = $('release-link');
  if (release) release.href = RELEASE_URL;

  // Task 022a. Only what works today from a clone with no install. The
  // installed-package route, `oneground fixture verify`, fails on 0.1.0rc1:
  // that wheel ships no fixture data. Task 022 changes that, and this panel
  // changes with it.
  const pre = $('verify-cmd');
  pre.textContent = '';
  pre.appendChild(document.createTextNode(
    'python site/teaser/verify_teaser_data.py\n'));
  pre.appendChild(el('span', 'c',
    '# needs a clone of the repository and nothing else: standard library only.'));

  const cx = m.cross_check_vs_build3_tables;
  $('receipt-source').textContent =
    'This page\'s geometry was recomputed on the export machine and compared ' +
    'against build 3\'s own tables: ' + fmtPct(cx.copies_identical_frac, 3) +
    ' of vectors landed on the same copy count, storage amplification ' +
    cx.storage_amplification_here + '× here against ' +
    cx.storage_amplification_pod + '× there, one-region recall@10 ' +
    cx.query_recall_mean_here + ' against ' + cx.query_recall_mean_pod +
    '. The region numbering is not identical and neither is every vector: ' +
    'k-means on different hardware lands on a different local optimum. ' +
    'The values agree; the bytes do not. Page data loaded via ' + via + '.';
}

/* The recommendation: what was chosen, on what engine, on which machine, and
   the two numbers that were measured there rather than simulated. Every value
   carries its source field on hover, as every number on this page does. */
function buildRecommendation(values) {
  const v = values.verdict;
  const host = $('recommendation');
  const rec = v.recommended;
  if (!rec) {
    host.appendChild(el('h3', null, 'nothing recommended'));
    host.appendChild(el('p', 'src',
      'No option met every constraint that could be checked. ' + v.source));
    return;
  }
  const V = values.verify;

  host.appendChild(el('h3', null, 'recommended'));
  const name = el('p', 'rec-config');
  name.appendChild(el('span', 'mono', rec.config));
  host.appendChild(name);

  const on = el('p', 'src', 'built and measured on ' + V.engine + ' ' +
    V.engine_version + ' · ' + V.target + ' pod ' + V.environment_id + ' · ' +
    V.platform + ' · ' + V.date);
  on.title = V.source + ' · ' + V.info_source;
  host.appendChild(on);

  // The two numbers that needed a real engine. Everything else on this page
  // was measured against the corpus; these were measured against a machine.
  const measured = el('div', 'rec-measured');
  const cell = (label, value, note, source) => {
    const b = el('div', 'rec-num');
    b.appendChild(el('span', 'value', value));
    b.appendChild(el('span', 'label', label));
    const s = el('span', 'src', note);
    s.title = source;
    b.appendChild(s);
    return b;
  };
  measured.appendChild(cell('p95 under load',
    V.latency.under_load.p95_ms.toFixed(2) + ' ms',
    'at concurrency ' + V.latency.under_load.concurrency + ', ' +
    fmtInt(V.latency.under_load.n_queries) + ' queries',
    'verify.json:searches[k=10_under_load].latency_shape_single_client.p95_ms'));
  measured.appendChild(cell('sustained qps',
    V.qps.achieved.toFixed(2),
    fmtInt(V.qps.completed) + ' of ' + fmtInt(V.qps.offered) + ' offered in ' +
    V.qps.duration_seconds + ' s, ' + V.qps.errors + ' errors',
    'verify.json:load.completed · offered = ' + V.qps.offered_basis));
  host.appendChild(measured);

  // All five constraints, named. Including the budget, with its band and the
  // fact that the verdict was taken on the upper bound.
  const cells = el('div', 'cells');
  for (const k of rec.constraints) {
    const cellEl = el('div', 'cell ' + k.outcome);
    cellEl.appendChild(el('span', 'k', k.constraint + ' — ' + OUTCOME_LABEL[k.outcome]));
    cellEl.appendChild(el('span', 'v', k.reason));
    cellEl.appendChild(el('span', 'src', k.source));
    cells.appendChild(cellEl);
  }
  host.appendChild(cells);

  const cost = rec.cost;
  if (cost && cost.monthly !== undefined) {
    const band = (cost.monthly_high - cost.monthly) ;
    const money = (x) => (cost.currency === 'EUR' ? '€' : cost.currency + ' ') +
      Math.round(x).toLocaleString('en-US');
    const p = el('p', 'src',
      'monthly_budget: ' + money(cost.monthly) + ' ± ' + money(band) +
      ' — the verdict uses the upper bound, ' + money(cost.monthly_high) +
      ', against a budget of ' + money(cost.budget.amount) + '. ' +
      cost.kind + '. ' + cost.basis + '. ' + cost.note);
    p.title = cost.source;
    host.appendChild(p);
  }

  if (v.runner_up) {
    const r = v.runner_up;
    const missing = r.couldnt_check.map((x) => x.constraint);
    const line = el('p', 'runner-up');
    line.appendChild(document.createTextNode(
      'indistinguishable on recall from '));
    line.appendChild(el('span', 'mono', r.family));
    line.appendChild(document.createTextNode(
      ' — ' + OUTCOME_LABEL[r.outcome] + ' on ' + missing.join(' and ') + ': ' +
      (r.couldnt_check[0] ? r.couldnt_check[0].reason : '')));
    const s = el('span', 'src', r.config + ' · ' +
      (r.couldnt_check[0] ? r.couldnt_check[0].source : ''));
    line.appendChild(s);
    host.appendChild(line);
  }
}

/* The number this run existed to settle. Three latencies, one of which is the
   only one that means anything, and the reason stated once. */
function buildSettle(values) {
  const V = values.verify;
  const host = $('settle');
  const L = V.latency;

  host.appendChild(el('h3', null, 'the number this run existed to settle'));

  const rows = [
    ['RTT baseline, p95', L.rtt_baseline.p95_ms, null,
     'the client-to-engine round trip with no query behind it, ' +
     fmtInt(L.rtt_baseline.n_queries) + ' samples at concurrency ' +
     L.rtt_baseline.concurrency,
     'verify.json:rtt_baseline_ms.p95_ms'],
    ['query p95, sequential', L.sequential.p95_ms, L.sequential.rtt_share_of_p95,
     'single client, ' + fmtInt(L.sequential.n_queries) + ' queries — the ' +
     'baseline is most of it, so this is the path, not the engine',
     'verify.json:searches[k=10].rtt_share_of_p95'],
    ['query p95, under load', L.under_load.p95_ms, L.under_load.rtt_share_of_p95,
     'concurrency ' + L.under_load.concurrency + ', ' +
     fmtInt(L.under_load.n_queries) + ' queries — the baseline is a small ' +
     'share, so this one is the engine',
     'verify.json:searches[k=10_under_load].rtt_share_of_p95'],
  ];

  // Three columns and the note on its own line underneath, the same shape the
  // receipt's value table uses. A fourth column for the note squeezed the p95
  // to about two characters on a phone and broke "38.22 ms" across three
  // lines, which is the receipt's old delta-column bug in a new table.
  const table = document.createElement('table');
  table.className = 'settle-table';
  table.appendChild(headRow(['', 'p95', 'baseline share']));
  for (const [label, ms, share, note, source] of rows) {
    const tr = document.createElement('tr');
    tr.appendChild(el('td', null, label));
    tr.appendChild(el('td', 'mono nowrap', ms.toFixed(2) + ' ms'));
    tr.appendChild(el('td', 'mono nowrap ' + (share === null ? '' :
      (share > 0.2 ? 'couldnt_check' : 'same')),
      share === null ? '—' : fmtPct(share, 1)));
    table.appendChild(tr);

    const nr = document.createElement('tr');
    nr.className = 'dnote';
    const nd = el('td', 'src', note);
    nd.colSpan = 3;
    nd.title = source;
    nr.appendChild(nd);
    table.appendChild(nr);
  }
  host.appendChild(table);

  const rule = el('p', 'settle-rule',
    'Single-client latency is unattributable on loopback; loaded latency is not.');
  rule.title = L.sequential.outcome;
  host.appendChild(rule);

  const src = el('p', 'src',
    'A single-client p95 whose baseline share is over the 20% limit measures ' +
    'the path to the engine more than the engine, and is reported as ' +
    "couldn't-check rather than rounded into a verdict. The p95 the " +
    'recommendation rests on is the loaded one.');
  src.title = L.sequential.outcome;
  host.appendChild(src);
}

function headRow(cells) {
  const tr = document.createElement('tr');
  for (const c of cells) tr.appendChild(el('th', null, c));
  return tr;
}

/* The delta line under a value row: one cell across the table, carrying
   whether the row reproduced within its tolerance. */
function deltaRow(span, text, ok) {
  const tr = document.createElement('tr');
  tr.className = 'dnote';
  // ok === null: this page did not check the row, so it gets no outcome
  // colour. couldn't-check is never rounded up to a verdict.
  const td = el('td', 'src' + (ok === null ? '' : (ok ? ' same' : ' differs')),
                text);
  td.colSpan = span;
  tr.appendChild(td);
  return tr;
}

function dataRow(cells) {
  const tr = document.createElement('tr');
  for (const [text, cls, title] of cells) {
    const td = el('td', cls, text);
    if (title) td.title = title;
    tr.appendChild(td);
  }
  return tr;
}

// ------------------------------------------------------------------ plumbing

function observe(node, fn) {
  let pending = 0;
  const run = () => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(fn);
  };
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(run).observe(node);
  window.addEventListener('resize', run);
  window.addEventListener('orientationchange', run);
}

/* ?selftest=1 — the instrument the task brief's performance numbers are read
   from. Sweeps the slider across its whole range and reports the frame time
   distribution into the DOM, so a headless browser can be asked for it. */
function selfTest(D, restoreEps) {
  const g = window.__oneground_ground;
  const times = [];
  for (let pass = 0; pass < 2; pass++) {
    for (let e = 0; e <= 40; e += 1) {
      const t = g.recountAt((e / 100).toFixed(2));
      if (pass) times.push(t);
    }
  }
  g.recountAt(restoreEps);
  times.sort((a, b) => a - b);
  const nav = performance.getEntriesByType('navigation')[0];
  const out = {
    frames: times.length,
    slider_ms_median: +times[times.length >> 1].toFixed(1),
    slider_ms_p95: +times[Math.floor(times.length * 0.95)].toFixed(1),
    slider_ms_max: +times[times.length - 1].toFixed(1),
    time_to_first_ground_ms: +(window.__oneground_first_paint -
      (nav ? nav.startTime : 0)).toFixed(0),
    dpr: window.devicePixelRatio,
    canvas: $('ground-canvas').width + 'x' + $('ground-canvas').height,
    rows: D.n,
  };
  const pre = el('pre');
  pre.id = 'selftest';
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}

// --------------------------------------------------------------------- boot

(async function () {
  try {
    const data = location.protocol === 'file:'
      ? await loadFromFile()
      : await loadOverHttp();
    start(data);
    window.__oneground_first_paint = performance.now();
  } catch (err) {
    fail('The page could not read its data.', String(err && err.message || err));
  }
})();

})();
