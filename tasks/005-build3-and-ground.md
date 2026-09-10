# Task 005 — Build 3 canonical, and the ground

## Expected repo state
Build 3's small artifacts committed in `fixtures/arxiv-150k/` (nine files:
MANIFEST, characterization, build_info, query_ids, ground_truth,
projection, three ground_view parquets). `logs/build-arxiv-150k.log` from
build 3 present locally (git-ignored). `~/oneground-assets/arxiv-150k-large.tgz`
exists outside the repo (do not read it into the repo).

## Part A — publish build 3 (source of truth: the files, not a pasted block)

1. Read `characterization.json`, `build_info.json`, `MANIFEST.sha256`, and
   the `TO_BE_FILLED` block in the log. Cross-check: every value in the log
   block must match the file; report any mismatch and stop.
2. Edit `fixtures/arxiv-150k.fixture.yaml`:
   - `embedding.vectors_sha256`, `queries.queries_sha256`,
     `ground_truth.ground_truth_sha256` ← build 3's array digests (log block).
   - drift pair and any other value that moved ← from `characterization.json`
     at printed precision. Report each value written beside build 2's.
   - `embedding.torch_version` and `cuda_device` ← from `build_info.json`;
     replace the "developer-reported" comments with `# recorded by the
     builder (build 3)`. Add `embedding.torch_cuda` from build_info.
   - `findings`: update the reproducibility finding to three builds —
     three environments (numpy 2.1.2 / pinned 4090 / pinned RTX Pro 4500),
     identical sampling receipts (`404cb92e…`, `a0f3236c…`), three distinct
     vector digests, all published values agreeing at printed precision
     (state the drift pair's spread across the three builds). Add: the
     ground-view export recomputed crispness, ambiguity, skew, and
     one-region recall on build 3 within ≤ 0.0005 of the published values
     — the first live value-reproduction. Add: copies histogram
     1:3.6% 2:5.6% 3:6.5% 4:84.3% — closure at ε=0.20 replicates 84% of the
     corpus to the cap; this is the mechanism behind 3.715×.
   - remove the finding that torch was developer-reported (now recorded).
   - `changelog`: `build: 3`, date 2026-09-09, note: pinned env, RTX Pro
     4500, torch recorded, ground-view export; canonical.
   - `artifacts.files`: add the three `ground_view_*.parquet` lines with
     `# declared`.
3. `docs/CHARTER.md`: status rows 004 done, 005 in progress; findings
   sentence updated to three builds; Phase 1 line "build 3" → done.
4. Verifier default on the local directory: report counts (expect 9
   verified, 3 couldn't-check).

## Part B — the ground (hero image)

The image must be honest about what build 3 found: this embedding space
has almost no crisp region boundaries (crispness 0.036), and closure
replication at ε=0.20 copies 84% of the corpus. The picture has to make
*that* legible — overlapping regions, not tidy Voronoi cells — while still
being the arresting image the product leads with.

Inputs: `ground_view_base.parquet` (x, y, region, copies, ratio,
top_level_category, …), `ground_view_centroids.parquet`,
`ground_view_queries.parquet`. Matplotlib only (add pinned to
requirements.txt); no seaborn, no external styling.

5. Write `corpora/render_ground.py --dir fixtures/arxiv-150k --out docs/img/`
   producing four variants, each 2400×1500 px PNG and an SVG, deep-slate
   background (#1B2432), no chart chrome (no axes, ticks, grid, title):
   - **A. by category** — points coloured by `top_level_category` (a
     muted, distinguishable palette; legend as a small key bottom-left);
     centroids as small white rings.
   - **B. by copies** — points coloured by `copies` (1 = quiet blue
     #5F7D9E, 4 = ochre #C99A3B, 2–3 intermediate); this is the
     crispness story: the image should be mostly ochre. Caption text
     bottom-left in the image: "84% of vectors sit within ε of four
     regions. There is no boundary to shard on." plus the three numbers
     (crispness 0.036 · ambiguity 0.891 · storage 3.7×).
   - **C. by region** — 256-colour cyclic palette by `region`, points at
     low alpha so the overlap reads as overlap; centroids labelled with
     their member count for the 8 largest.
   - **D. one query** — variant B as background at 30% alpha, plus the
     worst-recall ambiguous query from `ground_view_queries.parquet`: its
     position, its top-2 regions' centroids highlighted, its 10 true
     neighbours (from `ground_truth.npy` → base rows) drawn as small
     coral marks, and a one-line caption naming how many of the ten fall
     outside the routed region.
   Sensible point sizing for 150k points (size ~1–2 px, alpha tuned so
   density reads). Deterministic (no random jitter).
6. Also emit `docs/img/ground_thumbnail.png` (800×500) of whichever variant
   the script flags as default (B).
7. Report: per variant, the render time and one sentence on what it shows.
   No aesthetic judgement — the developer chooses.

## Acceptance
- Spec: no developer-reported comments remain; findings and changelog
  updated; diff touches only the named fields.
- Charter updated.
- Verifier counts as expected.
- `docs/img/` contains 8 files + thumbnail; `render_ground.py` runs in
  under 5 minutes on the laptop; requirements.txt gains one pinned line.

## Do not
- Rebuild anything. Read the large tarball. Change any measured value.
- Use the fixture's abstracts for any text in the image.
