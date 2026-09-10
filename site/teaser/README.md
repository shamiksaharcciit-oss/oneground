# site/teaser — the ground, live, on real data

A single static page. Every point on it is a real vector from the public
`arxiv-150k` fixture, every figure is either a published value or is
recomputed in the browser from per-vector distances, and moving the ε slider
recounts the closure for all 150,000 vectors rather than stepping through
precomputed frames.

    index.html      the page
    app.js          loading, the canvas, the closure recount, the four sections
    style.css       docs/design/tokens.css, copied in verbatim, plus layout
    fonts/          empty; see fonts/README.md for why
    data/           what corpora/export_teaser_data.py writes
    verify_teaser_data.py   re-derives the numbers from data/base.bin alone

No framework, no build step, no CDN, no webfont, no telemetry, no runtime
network call to anything but its own directory.

---

## How the data was exported

One command, on the developer's laptop, against the fixture's canonical
artifacts:

    python corpora/export_teaser_data.py \
        --spec    fixtures/arxiv-150k.fixture.yaml \
        --dir     fixtures/arxiv-150k/ \
        --assets  ~/oneground-assets/arxiv-150k/ \
        --report  runs/arxiv-150k-via-characterize/report.json \
        --out     site/teaser/data/

`--assets` is the release-asset directory holding the three large artifacts
(`vectors.npy`, `queries.npy`, `sample.jsonl.zst`) that are not in the clone;
`--dir` is the fixture directory in the repo. **Before it reads anything, the
export digests all eleven inputs against `fixtures/arxiv-150k/MANIFEST.sha256`
and stops if one disagrees**, so the receipt panel is describing bytes the
export actually saw.

The geometry is not re-implemented. `export_teaser_data.py` imports
`corpora/export_ground_view.py` unmodified, which imports the estimators from
the package, so k-means (256 centroids, seed 20260908, 20 iterations), the
centroid distances (non-squared Euclidean), the closure rule and the
per-query one-region recall are all the fixture's own definitions. Change one
there and it changes here.

Then it checks itself: it recomputes `boundary_crispness`,
`ambiguous_query_rate`, `skew_top10_share`, `storage_amplification` and
one-region `recall@10` and asserts each against the spec's published value and
tolerance, exiting non-zero if any misses. It also compares the whole
recomputation against build 3's own `ground_view_*.parquet` tables and records
the comparison in `values.json:measured.cross_check_vs_build3_tables` — that
comparison is reported, never asserted, because the fixture's published claim
is about values, not bytes.

### The five files it writes

| file | what |
|---|---|
| `base.bin` | 150,000 × (x, y, d1, d2, d3, d4, category, region), 3,900,000 bytes |
| `centroids.json` | 256 × (x, y, size) |
| `queries.json` | 2,000 queries: title, placement, routed and second region, ratio, ambiguous flag, the 10 true neighbour indices, one-region recall@10 — plus the 12 curated indices |
| `values.json` | published values, the fixture MANIFEST, the three build digests, the task-010 verdict, the ε sweep the export measured, and `base_bin` (the binary layout) |
| `inline.js` | the four above, gzipped and base64'd, for the `file://` path only |

`MANIFEST.sha256` carries the sha256 of all five.

### base.bin

Struct-of-arrays: the eight columns in the order above, each contiguous.

    x       150000 × float32   offset        0
    y       150000 × float32   offset   600000
    d1      150000 × float32   offset  1200000
    d2      150000 × float32   offset  1800000
    d3      150000 × float32   offset  2400000
    d4      150000 × float32   offset  3000000
    category 150000 × uint8    offset  3600000
    region  150000 × uint8     offset  3750000

Grouped by column rather than interleaved per record because a 26-byte record
puts every float32 on an odd byte boundary, and the browser could not then
take a zero-copy `Float32Array` view over it. `values.json:base_bin.columns`
carries the offsets, so `app.js` reads the layout from the data instead of
hard-coding it.

`x`, `y` are the UMAP projection **exactly as `projection.npy` holds it**.
They are the one illustrative thing in the directory: the spec declares the
projection as illustrative and not a measurement. `d1..d4` are the non-squared
Euclidean distances to the four nearest of the 256 centroids, in 768
dimensions. `region` is the nearest centroid; it fits in a uint8 because there
are 256 of them.

Query positions are the mean 2-D position of a query's ten true neighbours,
which is `export_ground_view.py`'s placement rule, not a projection of the
query vector.

---

## Precomputed versus computed live

**Precomputed** (in the export, in Python, from the 768-dimensional vectors —
none of it could be done in a browser):

- k-means and the four centroid distances per vector
- each query's routed region, second region, ratio, ambiguous flag
- each query's ten true neighbours (a brute-force scan of all 150,000)
- each query's recall@10 under one-region exact routing
- the 2-D placement
- the task-010 verdict, copied out of `report.json` without re-deriving it

**Computed live, in the browser, every time you move the slider:**

- how many regions each of the 150,000 vectors is copied into, at the current ε
- the copies histogram, the storage amplification, the count of copied
  vectors, p99 copies
- the caption sentence and its percentage
- for the selected query, how many of its ten true neighbours lie outside its
  routed region — recounted from `base.bin:region`, then checked against the
  exported value

The closure rule the browser applies is the fixture's:

    copies(ε) = #{ j ∈ 1..4 : d_j ≤ d_1 · (1 + ε) }

Four is the copy cap of the spec's `semantic_sharded` reference
configuration, which is why `base.bin` carries four distances. It is a
property of that configuration, not of the corpus, and the page says so.

At load the page recounts at ε = 0.20 and compares its own histogram, copied
count and p99 against `values.json:measured.eps_sweep["0.20"]`, which the
export measured in Python. If they disagree the page refuses to render and
prints both. It has never disagreed.

---

## Hosting

Static. Any host, any path, no server-side anything. Copy `site/teaser/`
wherever and serve it.

- **Over http(s)** the page fetches the four data files directly: **4.55 MB**
  total (`base.bin` is 3.9 MB of it). `inline.js` is never requested.
- **From `file://`** Chrome and Edge refuse `fetch()` and `XMLHttpRequest`, so
  the page checks `location.protocol` up front and instead injects
  `<script src="data/inline.js">`, which carries the same four files gzipped
  and base64'd. **4.75 MB**, and `DecompressionStream` is required (Chrome/Edge
  80+, Firefox 113+, Safari 16.4+). Nothing is fetched twice: it is one path or
  the other, never both.

Serving `base.bin` with `Content-Type: application/octet-stream` and letting
the host gzip the `.json` files is enough; there is nothing else to configure.

Two things to know before deploying only this directory:

1. The footer links to `../../fixtures/arxiv-150k.fixture.yaml`, which is a
   repo-relative path. If you host `site/teaser/` on its own, either copy the
   spec next to `index.html` and repoint that one `href`, or point it at
   wherever the spec is published.
2. `data/inline.js` is 4.7 MB and only the `file://` path uses it. A host that
   never serves `file://` can drop it; `verify_teaser_data.py` will then report
   it missing, which is the intended reminder rather than a failure of the page.

---

## Checking it

    python site/teaser/verify_teaser_data.py

Reads `base.bin` with `struct` (deliberately not numpy — the point is to read
the bytes the way something that is not the export would), reapplies the
closure rule at ε = 0.20, and checks:

- every digest in `data/MANIFEST.sha256`
- `base.bin`'s length and column layout against `values.json`, and that
  `d1 ≤ d2 ≤ d3 ≤ d4` for all 150,000 rows
- storage amplification, boundary crispness and p99 copies against the
  published values, within the spec's tolerances
- the ε sweep at 0.00, 0.20 and 0.40 against what the export recorded
- that for every one of the 2,000 queries, `recall@10 × 10` equals the number
  of true neighbours whose region is the query's routed region
- that `data/inline.js` decompresses to the four files beside it, byte for byte
- that the load size is under 5 MB on both paths

It never adjusts a tolerance. If a check fails it says which layer disagreed.

For a browser measurement, open the page with `?selftest=1` and read the JSON
in the `<pre id="selftest">` it appends: it sweeps ε across its whole range
twice, reports the frame-time distribution and puts ε back where it was.

Do this in a real browser window. Headless Chrome needs
`--virtual-time-budget` to wait for the page's async load, and under virtual
time `performance.now()` does not advance during synchronous work, so every
frame measures 0.0 ms. `tasks/scratch/T1-browser-measure.js` drives headless
Chrome over the DevTools Protocol instead, which keeps the real clock.
