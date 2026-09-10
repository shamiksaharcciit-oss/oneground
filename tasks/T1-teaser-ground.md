# Task T1 — The teaser: the ground, live, on real data

## Scope and separation
This is a **separate agent stream** on branch `teaser`. It touches only
`site/teaser/` and one export script; it never imports the package at
runtime and never edits anything under `oneground/`, `fixtures/`, or
`docs/` except `docs/img`. Merge to master is a directory add.

## Why
Launch is 16 September. The teaser must be flashy *and* true: every point
on screen is a real vector from the public arXiv-150k fixture, every
number is a published value, and the interaction recomputes from real
per-vector distances. It is the mockup (`oneground-mockups.html`, screens
1 and 2) made real.

## Do
1. **Export for the browser** — `corpora/export_teaser_data.py`
   (reads the release asset at `~/oneground-assets/arxiv-150k\`
   plus `fixtures/arxiv-150k/`; output to `site/teaser/data/`):
   - `base.bin`: for each of the 150,000 base vectors, float32 x, y
     (projection), float32 d1, d2, d3, d4 (non-squared L2 to the 4
     nearest of the 256 spec centroids, seed 20260908), uint8
     top-level category index, uint8 primary region. ~3.6 MB. The
     browser computes copies for any ε from d1..d4 — the slider is real.
   - `centroids.json`: 256 × (x, y, size).
   - `queries.json`: for each of 2,000 queries: x, y (as placed by
     `export_ground_view`), routed region, second region, ratio,
     ambiguous flag, the 10 true neighbour indices, one-region
     recall@10, and the query **title** from `sample.jsonl.zst` (titles
     only — never abstracts).
   - `values.json`: the published characterization and reference values
     copied from the spec, with the fixture's MANIFEST digests and the
     three build digests for the receipt panel.
   Digest every output; write `site/teaser/data/MANIFEST.sha256`.
2. **The page** — `site/teaser/index.html` + `app.js` + `style.css`,
   no framework, no CDN, no telemetry, works from `file://` and a static
   host. Design tokens exactly as `docs/design/` (task 010) — slate,
   ochre, three outcome colours, Space Grotesk / IBM Plex Mono via
   `@font-face` from local files under `site/teaser/fonts/` (check the
   licences allow bundling; if not, system fallback and say so).
   Render the 150k points on a single `<canvas>` (WebGL if you're
   confident, 2D with typed arrays otherwise — measure frame time on
   the slider and report it; target < 100 ms per ε change).
   Sections, in order, full-viewport each:
   - **Hero: the ground.** Points coloured by copies at ε = 0.20 on
     load; slider ε 0.00–0.40 recomputes copies live; three counters
     update: vectors copied, storage amplification, p99 copies. The
     caption is the measured sentence: "84% of vectors sit within ε of
     four regions. There is no boundary to shard on." at ε 0.20 — the
     sentence's number is recomputed from the data at every ε so it is
     never stale (at ε 0 it reads differently, and truthfully).
   - **One query, every hop.** A picker of 12 curated queries (the
     worst-recall ambiguous ones plus three that route well) by title;
     the trace animates: score → route (region highlighted) → the ten
     true neighbours light up coral → the ones outside the routed
     region pulse; a line states "N of 10 true neighbours are outside
     the region this query routes to." Then a "surprise me" button
     drawing from all 2,000.
   - **The verdict.** Static rendering of task 010's arXiv decision:
     the three options with meets / fails / couldn't-check, the storage
     numbers, and four sentences of the decision log verbatim from
     `report.json` (copy them into `values.json` at export time).
   - **The receipt.** Three builds, four environments, "values agree,
     bytes don't": the sampling digest identical ×3, three vector
     digests, the value table. And one command in a mono block:
     `pip install oneground` / `oneground fixture verify arxiv-150k`.
   - **The promise.** Exactly this text: "v0.1 — the advisor — public on
     23 September 2026: characterize · simulate · verify (Qdrant) ·
     report. Every number carries its receipt. The lab you just used is
     next." Below it, in muted text, the oneproof suite line: Prevent ·
     Detect · Prove · Choose.
   Footer: "All data on this page is the public arXiv-150k fixture (CC0
   metadata). Nothing here is illustrative; every figure is measured."
   And a link to the fixture spec.
3. Mobile: the canvas scales, the slider works with touch, sections
   stack. Test at 390 px.
4. Performance: report load size, time-to-first-ground, slider frame
   time, on the developer's laptop in Edge/Chrome. Under 5 MB total.
5. `site/teaser/README.md`: how the data was exported (so it is
   re-derivable), what is precomputed vs computed live, hosting notes
   (static, any host, no server).

## Acceptance
- Every number on the page traces to `values.json` or is computed live
  from `base.bin`; a test script re-derives the ε = 0.20 counters from
  `base.bin` and matches the spec (0.036 crispness, 3.715×).
- Slider < 100 ms per change on the laptop; page < 5 MB.
- Works from `file://` with no console errors; no external requests
  (assert with the network panel).
- Nothing uses abstract text. Fonts are licensed for bundling or
  fall back.

## Do not
- Touch the package. Invent any number. Use the word "simulate" for
  anything on this page — it is all measured.
