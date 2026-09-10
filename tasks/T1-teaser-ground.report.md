# Report: T1-teaser-ground

## Repo state expected vs found

| the brief assumed | found |
|---|---|
| branch `teaser` | existed already, at `b7a2d3b`, identical to `master`. Checked out, not created. |
| `site/teaser/` to create | absent, as expected. Created. |
| `corpora/export_teaser_data.py` to write | absent, as expected. Written. |
| release asset at `~/oneground-assets/arxiv-150k\` | present: `vectors.npy` 460,800,128 B, `queries.npy` 6,144,128 B, `sample.jsonl.zst` 49,920,799 B, plus two meta parquets. All three digest **exactly** to the fixture MANIFEST — these are build 3's canonical bytes. |
| `fixtures/arxiv-150k/` | present, all eleven artifacts, all digests matching `MANIFEST.sha256`. |
| `docs/design/` design tokens (task 010) | present: `tokens.css` + `tokens.md`. |
| task 010's `report.json` with the arXiv decision | present at `runs/arxiv-150k-via-characterize/report.json`. |
| **`oneground-mockups.html`, screens 1 and 2** | **absent.** Not in the repo, not in `tasks/files.zip` (which holds only the two briefs), nowhere on disk. |
| `export_ground_view` for the query placement rule | present at `corpora/export_ground_view.py`; its placement rule and geometry are imported unmodified. |

Two mismatches, neither blocking, both resolved rather than guessed at:

1. **The mockup is not in the repo.** The brief calls the page "the mockup made
   real". I could not read it. The page was built from the brief's own
   section-by-section description, from `docs/design/tokens.md`, and from the
   four rendered ground views in `docs/img/` (which the tokens file says the
   palette was taken from). Anything the mockup specified beyond the brief's
   text is not in this page because I never saw it.

2. **"The three options" is eight configurations across three families.**
   `report.json` holds 8 options — 1 `single_node_hnsw`, 1 `hash_sharded`, 6
   `semantic_sharded` — summarised as 0 meets / 6 fails / 2 couldn't-check.
   I read "three options" as the three architecture families and rendered
   three cards, each listing every one of its configurations with all three
   constraint verdicts. Nothing was dropped to make the count three.

Two streams share this branch, and it keeps mattering: the task-011 stream's
`18c07b0` swept my receipt-panel and copy fixes into a task-011 commit before
I could commit them, exactly as `c89fa8f` did in the first round. Nothing was
lost or reverted and I have not rewritten anyone's history, but it means the
`T1 (fixes 2)` commit carries the report only — the code it describes is in
`18c07b0`. See also: a **parallel stream committed to `teaser`** during this task (`ae9a3df`, `c89fa8f`, `8b76b55`), and `c89fa8f`
swept my in-progress `site/teaser/` files into a task-011 commit. Nothing of
mine was lost or reverted; my own commits are `T1 teaser: the page, live on
the arXiv-150k fixture`, `T1: report` and `T1: apply the three rulings`.
Flagged because two streams are writing to one branch.

## What was done

**`corpora/export_teaser_data.py`** — one script, five outputs into
`site/teaser/data/`, run once on the laptop.

It defines no geometry. It imports `corpora/export_ground_view.py` unmodified,
which imports the estimators from the package, so k-means (256 centroids, seed
20260908), the centroid distances (non-squared Euclidean — `centroid_dists`
takes the sqrt because the spec's 1.20 and 1.10 ratios mean ratios of actual
distances), the closure rule and the per-query one-region recall are the
fixture's own definitions.

Four things it does before and after the export that are not just plumbing:

- **Digests all eleven inputs against `fixtures/arxiv-150k/MANIFEST.sha256`
  and refuses to run on a mismatch.** The page's receipt panel claims it was
  drawn from the published canonical bytes; that claim is checked here, not
  asserted on the page.
- **Checks its own receipt table against the live spec.** The three-build
  digests are a constant in the file (they come from the spec's git history);
  build 3's row is asserted against `fixtures/arxiv-150k.fixture.yaml`, so the
  table cannot silently drift from the fixture.
- **Asserts the recomputed values against the spec** and exits non-zero on a
  miss — same shape as `export_ground_view.py`, no tolerance touched.
- **Cross-checks the whole recomputation against build 3's own
  `ground_view_*.parquet`** and records the comparison in `values.json`.
  Reported, never asserted: the fixture's published claim is about values, not
  bytes.

It also asserts a property the page depends on: that for all 2,000 queries,
`recall@10 × 10` equals the count of true neighbours inside the routed region.
If those two ever disagreed, the page's sentence "N of 10 true neighbours are
outside the region this query routes to" would not be the same measurement as
the recall printed beside it. They agree for all 2,000.

**`site/teaser/index.html` + `app.js` + `style.css`** — five full-viewport
sections in the brief's order, no framework, no build step, no CDN, no
webfont, no telemetry. Tokens from `docs/design/tokens.css`, copied in verbatim
(not `@import`-ed: the directory merges as a directory add and must not reach
up into the repo at runtime).

- **Hero.** 150,000 points on one 2-D canvas, written through a `Uint32Array`
  view over an `ImageData` (the endianness is measured, not assumed). ε
  0.00–0.40 recounts copies for every vector from `d1..d4` on every change;
  three counters, a live copies histogram, and the caption recomputed each
  time. A colour-by toggle (copies / arXiv category) — see *Observed*.
- **One query, every hop.** 12 curated queries by title (nine worst-recall
  ambiguous, three that route well), the four-step trace animating
  score → route → neighbours → what the region missed, the routed region lit
  on the canvas, the ten true neighbours in ink with the missed ones
  pulsing and drawn back to the query, and "surprise me" over all 2,000.
- **The verdict.** Three family cards, eight configurations, every constraint
  with its outcome, value, threshold and **source field**, plus four
  decision-log entries verbatim. The four are selected by `kind`
  (`scope`, `indistinguishable`, `recommendation`, `to_resolve`), not by
  index, and the export fails if one is missing — so a re-run of the report
  that reorders the log still quotes the same four claims.
- **The receipt.** Three builds, three environments plus this laptop as the
  fourth; the sampling digest identical ×3; three vector digests; the
  published-value table with δ and tolerance; the drift pair across all three
  builds; and `pip install oneground` / `oneground fixture verify arxiv-150k`.
- **The promise.** The brief's text, character for character.

**`site/teaser/verify_teaser_data.py`** — the acceptance test. Reads `base.bin`
with `struct`, deliberately not numpy: the point is to read the bytes the way
something that is not the export would.

### Three fixes from the Edge review (commit `T1 (fixes)`)

**1. Sections overlapped — a real defect, and my earlier check was the wrong
check.** `@media (min-width: 901px) { #ground, #query { height: 100vh } }` is a
hard box. Its flex children shrink only as far as their content, so the moment
the header, caption and source needed more than one viewport the surplus
painted straight over the section below — which is why the query heading
landed on top of the hero's caption, and the verdict heading on top of the
trace's line. It did not reproduce at 1440×900, where the hero came to 899 px
of a 900 px box; it reproduces at every shorter viewport. Measured before the
fix: `#query` content 819 px in a 740 px box, 817 in 720, 806 in 768.

I had checked `documentElement.scrollWidth` (horizontal) and section heights,
but never whether a section's `scrollHeight` exceeded its own box. That check
is now in `tasks/scratch/T1-bounds.js` and runs at five viewports.

The fix is `min-height`, never `height`: the section is at least a viewport and
grows past one when it must, so nothing can spill. The canvas is sized from
what the viewport has left after the copy — `clamp(15rem, calc(100svh - 30rem),
30rem)` — rather than from a flat fraction of it, so the sections still fit a
short window. That fixed height sits on the grid *inside* the section, whose
two children are a canvas that clips and a panel that scrolls, so nothing can
escape it; the section itself is never given a fixed height again.

**2. The options table was too long.** Eight configuration cards at full height
made the verdict 2,857 px and pushed the receipt and the promise far below the
fold. Each configuration is now one `<details>` row — caret, params,
recall@10, storage, outcome chip — with the three constraint verdicts and
their source fields inside. No JavaScript beyond building it; `<details>` is
keyboard-accessible on its own. On a phone the row wraps to two lines and each
number carries its own label, because the column header does not fit there.

Every number is still in the DOM: with all eight rows open there are 24
constraint cells and 24 source fields, the same as before. The section is
1,428 px collapsed and 3,076 px expanded, against 2,857 px when everything was
always open.

**3. The hero footnote was fighting the caption.** It is now one short line —
`base.bin:d1..d4 · recounted for 150,000 vectors · 8 ms`. The closure rule, the
copy cap and the published value it reproduces moved into a *what ε does*
expand on the ε control itself, next to the control they describe, and are also
its `title` for hover. The duplicate cap note that sat at the bottom of the
readout panel is gone. Trimming that, the two ledes and the legend spacing is
what let the hero fit one viewport exactly at 1440×900.

**`site/teaser/README.md`**, **`site/teaser/fonts/README.md`**.

### Two design decisions worth stating

**`base.bin` is struct-of-arrays, not interleaved.** The brief lists, per
vector, `float32 x, y, d1, d2, d3, d4`, `uint8 category`, `uint8 region`. Those
eight columns are written in exactly that order, but grouped by column rather
than per record. A 26-byte record puts every `float32` on an odd byte
boundary, so the browser could not take a zero-copy `Float32Array` view and
would have to copy 150,000 records out through a `DataView` before the first
frame. `values.json:base_bin.columns` carries the offsets, so `app.js` reads
the layout from the data. Total 3,900,000 bytes, the size the brief predicts
for the float half plus the two byte columns.

**A fifth output, `data/inline.js`, for `file://`.** Chrome and Edge refuse
`fetch()` and `XMLHttpRequest` against `file://` URLs, so a page opened by
double-clicking cannot read its own data directory. The page checks
`location.protocol` **up front** — not after a failed fetch — and injects
`<script src="data/inline.js">`, which carries the same four files gzipped and
base64'd. Plain base64 would take `base.bin` from 3.9 MB to 5.2 MB and blow
the 5 MB budget on its own; gzipped first it lands at 4.4 MB. Over http the
four files are fetched directly and `inline.js` is never requested. It is one
path or the other, never both, and neither logs an error.

## Measurements

### The export (laptop, Windows 11, Python 3.12.10, numpy 2.5.3, faiss-cpu 1.15.0)

Recomputed from `vectors.npy` with the spec's seed, then checked against the
spec. Method: `corpora/export_teaser_data.py`, log in
`tasks/scratch/T1-export.log`; 56.8 s wall.

| value | recomputed here | published | δ | tolerance |
|---|---|---|---|---|
| `boundary_crispness` | 0.0362 | 0.036 | 0.0002 | 0.02 |
| `ambiguous_query_rate` | 0.8915 | 0.891 | 0.0005 | 0.02 |
| `skew_top10_share` | 0.0754 | 0.075 | 0.0004 | 0.02 |
| `storage_amplification` @ ε 0.20 | 3.7152 | 3.715 | 0.0002 | 0.01 |
| one-region `recall@10` | 0.5473 | — | inside drift band [0.502, 0.569] | 0.02 |

Copies histogram at ε 0.20, from the recomputed `d1..d4`:
1 copy 5,437 (3.6%) · 2 copies 8,363 (5.6%) · 3 copies 9,689 (6.5%) ·
4 copies 126,511 (**84.3%**). 144,563 vectors copied, p99 copies 4, 0 empty
regions, 37 top-level categories. This reproduces the spec's
`closure_replicates_most_of_the_corpus` finding (3.6 / 5.6 / 6.5 / 84.3)
exactly at the precision it is published to.

### Cross-check: this laptop against build 3's tables (the fourth environment)

Method: `export_teaser_data.py:cross_check`, comparing the recomputation
against `ground_view_*.parquet`, which `export_ground_view.py` produced on the
pod during build 3. Recorded in
`values.json:measured.cross_check_vs_build3_tables`.

| | pod (build 3) | this laptop |
|---|---|---|
| storage amplification | 3.71515× | 3.71516× |
| boundary crispness | 0.0362733 | 0.0362467 |
| one-region recall@10, mean | 0.54725 | 0.54725 |
| per-vector copy count identical | — | 99.9733% (40 vectors of 150,000 differ) |
| per-query ambiguous flag identical | — | 100.0% |
| per-query recall identical | — | 99.9% (2 queries of 2,000 differ) |
| query x/y max absolute delta | — | 0.0 |
| region-size multiset identical | — | **no** |

This is the fixture's own claim about itself, measured: k-means on different
hardware lands on a slightly different local optimum, so the partition is not
byte-identical and neither is every vector's copy count — and every published
value still reproduces well inside tolerance. Query positions match exactly
because they derive from `projection.npy`, which is a receipt shipped in the
fixture, not something recomputed.

### Load size

Method: `site/teaser/verify_teaser_data.py` (bytes on disk) and Chrome's
Resource Timing over CDP (bytes transferred).

| | bytes |
|---|---|
| `base.bin` | 3,900,000 |
| `queries.json` | 552,815 |
| `values.json` | 29,437 |
| `centroids.json` | 9,595 |
| page (`index.html` + `app.js` + `style.css`) | 65,533 |
| **total over http** | **4,557,380 (4.56 MB)** — Chrome measured 4,559,480 transferred, headers included |
| `data/inline.js` (the `file://` path, instead of the four above) | 4,697,985 |
| **total from `file://`** | **4,763,518 (4.76 MB)** |

Both under 5 MB. `inline.js` is a fifth file on disk but never a second
download.

### Two more from the Edge review (commit `T1 (fixes 2)`)

**The receipt's third panel had a 31 px column.** Four columns — value,
published, recomputed here, δ — fought for a 390 px panel and the δ lost: 31 px
wide, one character per line, rows 106–144 px tall against 29–50 px in the two
panels beside it, and the panel three times their height.

The δ is a judgement about the row, not a fourth measurement, so it moved onto
the row's own second line — the same shape the verdict cells use for their
source fields. Three columns now, and the delta reads `δ 0.0002 ≤ tolerance
0.02` underneath. Measured after: rows 23–45 px against 29–50 px in the
neighbours, all three panels 513 px, the section 1,389 → 1,132 px.

Fixing it surfaced a second, worse bug I had introduced with the first round of
fixes: `#receipt-values td:first-child { white-space: nowrap }` also matched the
new `colspan` delta cell — a colspan cell is a first child too — which dragged
the whole table wider than its panel and pushed *published* and *recomputed
here* off the right edge entirely. The rule is now scoped
`tr:not(.dnote) td:first-child`. Caught by screenshotting rather than by the
height numbers, which looked fine.

The drift row is the one value this page does not recompute; its delta line
says `not recomputed here` and carries **no** outcome colour, where the other
four are teal for reproducing within tolerance. couldn't-check is not rounded
up, including in a table cell.

**Internal task numbering is off the page.** The verdict lede read "Task 010
judged 8 configurations…"; it now reads "oneground judged 8 configurations…".
Grepping the rendered `document.body.textContent` at 1440 and 390 px finds no
`task` and no `T1` anywhere, and `values.json` carries neither — the run path
`runs/arxiv-150k-via-characterize/report.json` and the repo paths in the source
fields are the only provenance strings left, which is what they are for.

### Layout, after the fixes (Chrome over CDP, `tasks/scratch/T1-bounds.js`)

Section heights, and whether any section's content escapes its own box:

| viewport | ground | query | verdict | receipt | promise | document | overlaps |
|---|---|---|---|---|---|---|---|
| 1440×900 | 900 | 900 | 1428 | 1132 | 900 | 5485 | none |
| 1440×740 | 740 | 756 | 1428 | 1132 | 740 | 5022 | none |
| 1280×720 | 720 | 754 | 1671 | 1163 | 720 | 5253 | none |
| 1024×768 | 768 | 768 | 1643 | 1413 | 768 | 5567 | none |
| 390×844 | 1199 | 1454 | 2184 | 1920 | 347 | 7330 | none |

Before the fix, at the same three widths the checker reported
`query content 819 overflows its box 740`, `817 overflows 720`,
`806 overflows 768`. The document is 5,485 px at 1440×900, down from 7,391 px.
Boundary screenshots at 1440, 1024 and 390 px are in the scratchpad as
`final-<width>-<from>_<to>.png`.

### Browser (headless Chrome 1440×900, `tasks/scratch/T1-browser-measure.js` over CDP)

`--dump-dom` needs `--virtual-time-budget` to wait for the async load, and
under virtual time `performance.now()` does not advance during synchronous
work — every frame measures 0.0 ms. So the numbers below come from driving the
same headless Chrome over the DevTools Protocol with the real clock. Each row
is 82 frames: three sweeps of ε across 0.00–0.40 in 0.01 steps, first sweep
discarded (it reallocates the point buffers after a viewport change).

Re-measured after `T1 (fixes 2)`. Each row is 82 frames; six runs, three per
load path, **run one at a time**.

| run | slider median | p95 | max |
|---|---|---|---|
| http, desktop | 6.7 / 6.7 / 8.2 ms | 9.4 / 9.9 / 14.2 | 10.5 / 11.9 / 22.4 |
| http, 390×844 dpr 3 | 7.0 / 7.7 / 8.7 ms | 10.1 / 11.4 / 16.0 | 10.9 / 12.8 / 54.1 |
| `file://`, desktop | 8.9 / 13.5 / 7.1 ms | 12.9 / 32.4 / 12.7 | 22.4 / 44.7 / 13.9 |
| `file://`, 390×844 dpr 3 | 7.4 / 6.9 / 7.0 ms | 10.1 / 10.1 / 9.9 | 12.6 / 12.0 / 13.1 |

Canvas 955×418 desktop, 712×705 at 390 px dpr 3. **Worst frame across the six
runs: 54.1 ms, against a 100 ms target**; every median is under 14 ms.
Breakdown at 390 px (`window.__oneground_timing`): recount 1.9 ms, paint
5.5 ms, DOM 0.2 ms.

An earlier pair of runs showed a 3,682 ms frame and a 150 ms p95. Those two
were started in parallel, so two headless Chromes were sweeping 150,000
vectors on the same 16 threads at once; the numbers are the contention, not
the page. Recorded here rather than dropped, and the table above is the
sequential re-run.

Time to first ground:

| | ms |
|---|---|
| `file://` (no server, gunzip + base64 decode of 4.7 MB) | 360 / 1219 / 1402 |
| http, three runs | 805 / 1263 / 3426 |

The http figure is dominated by `python -m http.server`, which is
single-threaded and slow with a 3.9 MB body; it is not representative of a
static host. The `file://` figure is the honest measure of the page's own
decode cost, since nothing is over a network there.

### No external requests, no console errors

Method: CDP `Network.requestWillBeSent`, `Runtime.consoleAPICalled`,
`Log.entryAdded` and `Runtime.exceptionThrown`, over the whole session
including the ε sweep and the viewport change. Chrome was launched
**without** `--allow-file-access-from-files`, so the `file://` run had the
restrictions a reader double-clicking `index.html` would have.

- http: 7 requests, all same-origin — `/`, `style.css`, `app.js`,
  `values.json`, `centroids.json`, `queries.json`, `base.bin`. Console empty,
  exceptions empty, in all three runs.
- `file://`: 4 requests — `index.html`, `style.css`, `app.js`,
  `data/inline.js`. Console empty, exceptions empty, in all three runs.
- No `task` and no `T1` in the rendered `document.body.textContent`, at 1440
  and at 390 px.

The one console entry in the first measured run was Chrome's own
`/favicon.ico` 404. `<link rel="icon" href="data:,">` removed it: a request the
page did not ask for is still a request.

### Mobile at 390 px

`document.documentElement.scrollWidth` = 390 = `clientWidth`, and a walk of
every element found none extending past the viewport. It did not start that
way: `SECTION#verdict` was 422 px wide because a decision-log quote contains
`single_node_hnsw[M=32,efConstruction=200,efSearch=128]`, one unbreakable
53-character word (`overflow-wrap: break-word` on `body`); a `.src` span
outside `.cell` had no wrap rule at all; and a flex item's default
`min-width: auto` let one `<pre>` widen the page.

## Verification

**Passed.** `python site/teaser/verify_teaser_data.py` — every check, on the
committed data:

- all five digests in `data/MANIFEST.sha256`
- `base.bin` is 3,900,000 bytes with the eight declared columns, and
  `d1 ≤ d2 ≤ d3 ≤ d4` for all 150,000 rows; region ids all < 256
- **re-derived from `base.bin` alone, with `struct`, not numpy**: storage
  amplification 3.7152 vs published 3.715 (tol 0.01); boundary crispness
  0.0362 vs published 0.036 (tol 0.02); p99 copies 4 vs published 4 — which is
  the brief's acceptance criterion
- the ε sweep at 0.00, 0.20, 0.40 matches what the export recorded
- all 2,000 queries: `recall@10 × 10` == neighbours inside the routed region
- no query "title" is long enough to be an abstract (longest 204 chars)
- `data/inline.js` decompresses to the four files beside it, byte for byte
- load size under 5 MB on both paths

**Passed.** The page checks itself: at load it recounts at ε = 0.20 in the
browser and compares its histogram, copied count and p99 against
`values.json:measured.eps_sweep["0.20"]`, which the export measured in Python.
On a mismatch it refuses to render and prints both. It has not mismatched.

**Passed.** The page's own numbers, read out of the rendered DOM: caption
"84% of vectors sit within ε of four regions. There is no boundary to shard
on."; counters 144,563 / 3.715× / 4; query line "10 of 10 true neighbours are
outside the region this query routes to."; promise text character-identical to
the brief; 24 verdict constraint cells (8 options × 3 constraints).

**Passed.** No console errors, no external requests, no horizontal overflow at
390 px, on both http and `file://` — measured above.

**Couldn't check.**

- **Edge.** Everything was measured in Chrome. Edge is the same Blink engine
  and both are installed, but I did not drive Edge, so I am not reporting it
  as measured. The one API with a real version floor is
  `DecompressionStream` (Edge 80+), used only on the `file://` path.
- **A real phone, and touch.** 390 px was measured with CDP device emulation
  at dpr 3, which gives the right layout and the right canvas size but is not
  a touch device and not a phone's CPU. The slider has a 2 rem touch target
  and `touch-action: pan-y` on the canvas so vertical scrolling still works
  over it; that it *feels* right under a thumb is untested.
- **Real network load time.** Measured against `python -m http.server` only.
- **Firefox and Safari.** Not installed here. `DecompressionStream` is
  Firefox 113+ / Safari 16.4+; nothing else on the page is recent.

## Observed, not done

- **The colour-by toggle is slightly more than the brief asked for.** The
  brief mandates a `uint8` category column in `base.bin` and says the hero
  loads coloured by copies. It never says to render the category. Shipping a
  column nothing can display seemed worse than a toggle that defaults exactly
  as specified, so there is a copies/category switch in the hero panel. Say
  the word and it comes out; the column stays either way.

- **The three conflicts I raised were ruled on and the rulings are applied**
  (commit `T1: apply the three rulings`). Recorded here because the reasoning
  matters more than the diff:
  1. **Neighbours are not an outcome, so they are not coral.** The brief said
     "the ten true neighbours light up coral"; the ruling is that
     `docs/design/tokens.md` is right and the brief was wrong — the three
     outcome colours mean meets / fails / couldn't-check everywhere on the
     site. The ten true neighbours are now ink (`#E7EAEF`) with a thin ring,
     the ones outside the routed region pulse in ink, and **the routed region
     carries the only colour on that canvas**. The query marker is the same
     ink, heavier: the query and its neighbours are told apart by weight, not
     hue. The routed region's centroid ring moved from ochre to the region's
     own blue for the same reason. `.query-list .miss` went from coral/teal to
     muted (a count is not a verdict) and the "N of 10" in the verdict line is
     now ochre, matching the hero caption.
  2. **`simulate` as a command name stays.** The prohibition was on describing
     anything on the page as simulated; every figure here is measured. The
     promise names the four v0.1 commands, and the verdict source fields cite
     the file each number came from. Both are correct usage.
  3. **The footer sentence was fixed, not caveated.** It now reads: "Every
     figure on this page is measured on the public arXiv-150k fixture (CC0
     metadata). The 2-D placement is a projection, declared illustrative in
     the fixture spec; every number is not." The separate caveat paragraph
     underneath it is gone — a true sentence beats a false one with a
     footnote. The canvas figcaption still carries the same fact where the
     projection is actually on screen.

- **Where the three outcome colours still appear, and why each is `meets` /
  `fails`.** After the ruling I re-checked every use on the page. Verdict
  chips and verdict cells: the outcome itself. The receipt table's teal on
  "identical" and on "δ ≤ tolerance": both are verification passes, which is
  `meets`. Coral on the load-failure banner: a failure. No fourth meaning
  survives anywhere. Ochre stays the accent and never fills a verdict cell.

- **The footer's spec link is repo-relative** (`../../fixtures/arxiv-150k.fixture.yaml`).
  It resolves in the repo and from `file://`; it 404s if `site/teaser/` is
  hosted on its own. `README.md` says so under Hosting. Not fixed because
  fixing it means either copying the spec into `site/teaser/` (a fixture file
  in a directory the brief scoped to the page) or hard-coding a public URL
  that does not exist yet.

- **`docs/img/ground_*.svg` are 2.4–3.4 MB each.** Not touched, not used by
  this page.

- **Two agent streams are committing to `teaser`.** Task 011's stream
  committed my in-progress files. Nothing broke, but the branch is not
  single-writer.

## Repo now contains

New:

    corpora/export_teaser_data.py           the export (one script, five outputs)
    site/teaser/index.html                  the page
    site/teaser/app.js                      loading, canvas, live recount, four sections
    site/teaser/style.css                   tokens.css verbatim + layout
    site/teaser/README.md                   how the data was exported, what is live, hosting
    site/teaser/verify_teaser_data.py       the acceptance test
    site/teaser/fonts/README.md             why nothing is bundled
    site/teaser/data/base.bin               3,900,000 B
    site/teaser/data/centroids.json             9,595 B
    site/teaser/data/queries.json             552,815 B
    site/teaser/data/values.json               29,437 B
    site/teaser/data/inline.js              4,697,985 B  (the file:// path)
    site/teaser/data/MANIFEST.sha256        digests of all five
    tasks/scratch/T1-browser-measure.js     CDP harness for the browser numbers
    tasks/scratch/T1-bounds.js              section-overlap check, five viewports
    tasks/scratch/T1-export.log             the export run
    tasks/T1-teaser-ground.report.md        this file

Changed: nothing outside `site/teaser/`, `corpora/export_teaser_data.py` and
`tasks/`. No file under `oneground/`, `fixtures/`, `docs/`, `models/`,
`adapters/`, `policies/` or `runs/` was read-write; all were read only.
Commit `2579a49` on `teaser`.

No new dependency. The export uses numpy, pyyaml, zstandard, faiss-cpu and
pyarrow, all already pinned; `gzip` and `base64` are stdlib. The page has none.

## Blocked on developer

Nothing blocking. Four things only the developer can do:

1. **Confirm the colour-by toggle** stays. (The three colour and wording
   conflicts have been ruled on and applied; see *Observed*.)
2. **Point the footer's fixture-spec link** at wherever the spec will be
   published, if `site/teaser/` is deployed on its own.
3. **Open the page on a real phone and in Edge** before 16 September. The
   layout and the frame times are measured under emulation; touch feel and
   Edge are not.
