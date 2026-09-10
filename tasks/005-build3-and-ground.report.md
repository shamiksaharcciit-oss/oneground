# Report: 005-build3-and-ground

## Repo state expected vs found

| Expected | Found |
|---|---|
| build 3's nine small artifacts committed in `fixtures/arxiv-150k/` | yes — `d7222b2 build 3 artifacts (RTX Pro 4500, pinned env, torch recorded)`; all nine present |
| `logs/build-arxiv-150k.log` from build 3, git-ignored | yes — 88,106 bytes, ignored |
| `~/oneground-assets/arxiv-150k-large.tgz` outside the repo | yes — 483,468,013 bytes. **Not read.** |
| tree clean | yes, apart from the untracked brief |

Task 004 and 003c are both committed (`3850f3f`, `d8f76cd`), so the split diff
I flagged at the end of 004 has been resolved.

## What was done

Both parts. One number came out differently from the brief's expectation and
one input turned out not to exist locally; both are below rather than buried.

### Part A — publish build 3

**1. Cross-check.** `tasks/scratch/005-build3-crosscheck.py` re-derives every
line of the log's `TO_BE_FILLED` block from build 3's own files, re-applying
`build_fixture`'s print formatting rather than eyeballing. **17/17 match, 0
mismatch**, so the stop condition did not fire. One of the three array digests
is independently checkable — `ground_truth.npy` is present locally, and
`sha256_array` over it reproduces the log's `96fc8bd0…` exactly. The other two
(`vectors.npy`, `queries.npy`) are the release asset and are taken on the log's
authority, stated as such.

**2. Spec.** Written by `tasks/scratch/005-build3-publish-edit.py`, each
substitution anchored and asserted to occur once. Three array digests, the
drift pair, torch/CUDA now recorded, the three parquet lines in
`artifacts.files`, the changelog entry, and the findings.

**3. Charter.** 004 → done, 005 → in progress, findings sentence rewritten to
three builds (and the closure mechanism), Phase 1 "build 3" → done.

**4. Verifier.** Run and reported below. The count differs from the brief's
expectation for a structural reason, not a failure.

### Part B — the ground

`corpora/render_ground.py`, matplotlib only, four variants at 2400×1500 PNG +
SVG on `#1B2432`, no axes/ticks/grid/title, plus an 800×500 thumbnail of the
default (B). The script computes no geometry: every position, region, copy
count and category is read from the parquet tables. Point clouds are
`rasterized=True` inside the SVG — 150,000 vector circles would make an SVG no
browser enjoys — while text and rings stay vector.

### Deviations, each with its reason

- **Variant D shows the routed region and the regions its true neighbours
  actually occupy, not "its top-2 regions".** The second-nearest region id for
  a query is in no local artifact: `ground_view_queries.parquet` carries
  `region` (nearest) and `ratio` (d2/d1) but not the identity of the second,
  and deriving it needs `queries.npy`, which is the release asset the brief
  forbids reading. Rather than approximate it from 2-D positions — which would
  be a 2-D guess at a 768-d fact — the image highlights the routed region plus
  the regions the ten true neighbours are actually in, which is computable
  from `ground_truth.npy` and `ground_view_base.parquet` and tells the same
  story more directly.
- **Points are drawn larger than the brief's "~1–2 px" guidance** — `s=5.0`,
  about 3.1 px diameter, at alpha 0.85. At 1.2/0.45 the first render came out
  as near-empty slate: variant B, whose entire job is to show that the corpus
  is mostly ochre, did not show it. I tuned by rendering and looking
  (`tasks/scratch/005-tune-ink.py`, three settings compared) rather than
  guessing. The operative clause in the brief is "alpha tuned so density
  reads"; this is what made it read.
- **A soft scrim sits under the bottom-left text.** The captions and keys fall
  over the point cloud and were unreadable against it. It is a bottom-edge
  alpha ramp, not a band with an edge, and carries no scale or category — it
  is legibility, not chart chrome.
- **Two stale things were corrected**, both made false by this task's own
  edits: the `device:` comment still said "canonical build on RTX 4090" two
  lines above a `cuda_device` of RTX PRO 4500 Blackwell, and the
  `no_drift_penalty` and `loss_is_partitioning` findings quoted build 2's
  numbers. Same precedent as tasks 003b and 003c.

## Measurements

### Cross-check: the log block against build 3's files

17 of 17 match. The formatting column is the builder's own (`:.2f`, `:.3f`,
`round(v, 3)`) re-applied to the stored value.

| Field | Log block | From the file | |
|---|---|---|---|
| `intrinsic_dimensionality` | 32.55 | 32.55 (file 32.553257) | OK |
| `boundary_crispness` | 0.036 | 0.036 (file 0.036273) | OK |
| `ambiguous_query_rate` | 0.891 | 0.891 (file 0.8915) | OK |
| `skew_top10_share` | 0.075 | 0.075 (file 0.0754) | OK |
| `drift.value_before` | 0.522 | 0.522 (file 0.522383, n=965) | OK |
| `drift.value_after` | 0.549 | 0.549 (file 0.548792, n=1035) | OK |
| `single_node_hnsw.recall_at_10` | 0.997 | 0.997 (file 0.9973) | OK |
| `semantic_sharded.recall_at_10` | 0.932 | 0.932 (file 0.932) | OK |
| `semantic_sharded.routing_ceiling` | 0.932 | 0.932 (file 0.9324) | OK |
| `storage_amplification` | 3.715 | 3.715 (file 3.715147) | OK |
| p50 / p95 / p99 copies | 4 / 4 / 4 | 4 / 4 / 4 | OK |
| `source.snapshot_sha256` | `99dc9b05…` | build_info.json | OK |
| `embedding.library_version` | 6.0.1 | build_info.json | OK |
| `sampling.sample_sha256` | `404cb92e…` | MANIFEST.sha256 | OK |
| `ground_truth.ground_truth_sha256` | `96fc8bd0…` | **recomputed from the local .npy** | OK |

### Every value written, beside build 2's

| Field | Build 2 | Build 3 | Moved? |
|---|---|---|---|
| `embedding.vectors_sha256` | `414e1484…` | `cb973a94…` | yes |
| `queries.queries_sha256` | `87718975…` | `16e0f488…` | yes |
| `ground_truth.ground_truth_sha256` | `ecb93315…` | `96fc8bd0…` | yes |
| `drift.value_before` | 0.524 | **0.522** | yes |
| `drift.value_after` | 0.551 | **0.549** | yes |
| `intrinsic_dimensionality` | 32.55 | 32.55 | no (32.553249 → 32.553257) |
| `boundary_crispness` | 0.036 | 0.036 | no (0.036247 → 0.036273) |
| `ambiguous_query_rate` | 0.891 | 0.891 | no (0.8915 → 0.8915) |
| `skew_top10_share` | 0.075 | 0.075 | no (0.0754 → 0.0754) |
| `single_node_hnsw.recall_at_10` | 0.997 | 0.997 | no (0.99695 → 0.9973) |
| `semantic_sharded.recall_at_10` | 0.932 | 0.932 | no (0.9316 → 0.9320) |
| `semantic_sharded.routing_ceiling` | 0.932 | 0.932 | no (0.9323 → 0.9324) |
| `storage_amplification` | 3.715 | 3.715 | no (3.715167 → 3.715147) |
| p50 / p95 / p99 copies | 4 / 4 / 4 | 4 / 4 / 4 | no |
| `torch_version` | "2.14.0+cu130" *declared* | "2.14.0+cu130" **recorded** | now recorded |
| `torch_cuda` | — | **"13.0"** | new field |
| `cuda_device` | "NVIDIA GeForce RTX 4090" *declared* | **"NVIDIA RTX PRO 4500 Blackwell"** recorded | yes |

**The drift pair is the only published value that moved.** Everything else is
identical at printed precision across two different GPUs.

Two findings quote sub-printed precision and so had to move with it:
`loss_is_partitioning` from build 2's 0.9316 / 0.9323 (index loss 0.0007, 14 of
20,000 slots) to build 3's 0.9320 / 0.9324 (0.0004, **8 of 20,000 slots**), and
`no_drift_penalty` from 0.524 / 0.551 to 0.522 / 0.549.

Mechanically confirmed: extracting all 30 value-bearing fields from the
committed and working revisions and diffing them shows every field except the
drift pair and the three array digests byte-unchanged.

### build_info.json (build 3)

    built_at          2026-09-09T11:27:01Z
    device            cuda
    cuda_device_name  NVIDIA RTX PRO 4500 Blackwell
    torch_cuda        13.0
    platform          Linux-6.8.0-138-generic-x86_64-with-glibc2.39
    python_version    3.12.3
    library_versions  faiss-cpu 1.15.0, numpy 2.5.3, sentence-transformers 6.0.1,
                      torch 2.14.0+cu130, umap-learn 0.5.12

numpy is the pinned 2.5.3, and **torch is recorded for the first time**, with
its CUDA build (`+cu130`) and the device name — the three fields task 003c
added, doing exactly what they were added for. The two spec fields that were
attestation are now artifacts, and the finding that said so is removed.

### The ground-view export's live value reproduction (from the build log)

    copies histogram    1:5,441 (0.036)  2:8,363 (0.056)  3:9,679 (0.065)  4:126,517 (0.843)
    storage amplification  3.715x

    boundary_crispness    0.0363   spec 0.036   delta 0.0003   OK
    ambiguous_query_rate  0.8915   spec 0.891   delta 0.0005   OK
    skew_top10_share      0.0754   spec 0.075   delta 0.0004   OK
    one_region_recall@10  0.5473   drift band [0.504, 0.571]   OK

This is the first live value reproduction in the project: geometry recomputed
from the artifacts the build had just written, independently of the
characterization step, agreeing to within 0.0005. The one-region recall of
0.5473 also lands where task 004 predicted it would (~0.545, extrapolated from
the smoke fixture's +0.007 offset between full-corpus and pre-2019 centroids),
which is a small piece of evidence that the band was derived correctly rather
than luckily.

### Verifier — 8 verified, not the 9 the brief expected

    summary: 8 verified, 0 contradicted, 3 couldnt_check  (digests only; 6 receipt, 5 declared)

Exit 0. **This is correct, and the expectation of 9 counts a file that cannot
be counted.** There are nine files in the directory, but `MANIFEST.sha256`
cannot list its own digest — it would have to contain the hash of itself. The
manifest has 11 entries: 8 whose file is present and verified, 3 (the release
asset) absent and reported couldn't-check. 9 files on disk = 8 manifest entries
present + the manifest itself. 8 is the maximum achievable and nothing is
missing.

    couldnt_check receipt  sample.jsonl.zst / vectors.npy / queries.npy   (release asset)
    verified      receipt  query_ids.json, ground_truth.npy, characterization.json
    verified      declared build_info.json, projection.npy,
                           ground_view_{base,queries,centroids}.parquet

The smoke fixture is unaffected: 11 verified, 0 contradicted.

### Part B — render times and what each shows

Final clean run, `--dir fixtures/arxiv-150k --out docs/img/`. Times are per
variant end to end, PNG and SVG writes included.

| Variant | Time | What it shows |
|---|---|---|
| A by category | 7.8 s | The categories *do* separate: cs, math, astro-ph, cond-mat occupy visibly distinct territory, which is why the space looks shardable until you measure it. |
| B by copies (default) | 3.9 s | Almost the whole map is ochre — 84.3% of vectors sit within ε of four regions — so the visible category structure is not a partition anything can route on. |
| C by region | 6.3 s | 256 region colours intermingle everywhere instead of forming cells; the eight largest regions are labelled with their membership. |
| D one query | 4.3 s | One ambiguous query (d2/d1 = 1.000) whose ten true neighbours are spread across four regions, **all ten outside** the region it routes to — recall@10 of 0.0 for that query. |
| thumbnail (B, 800×500) | 2.5 s | — |
| **total incl. load** | **25.5 s** | budget was 5 minutes |

Data load 0.8 s for 150,000 base rows, 2,000 queries, 256 centroids.

The variant-D query is chosen deterministically: among ambiguous queries at the
minimum recall (91 tie at 0.0), the one with the tightest d2/d1. That is
index 434, routed region 189 (254 vectors), ratio 1.0000769.

### Output

    docs/img/ground_a_category.png    2400x1500   2.44 MB
    docs/img/ground_a_category.svg                2.97 MB
    docs/img/ground_b_copies.png      2400x1500   2.16 MB
    docs/img/ground_b_copies.svg                  2.67 MB
    docs/img/ground_c_region.png      2400x1500   2.32 MB
    docs/img/ground_c_region.svg                  3.36 MB
    docs/img/ground_d_query.png       2400x1500   1.78 MB
    docs/img/ground_d_query.svg                   2.45 MB
    docs/img/ground_thumbnail.png      800x500    0.41 MB

Eight files plus the thumbnail. I opened each rendered PNG and looked at it
before reporting; three defects were found and fixed that way and are recorded
under "What was done" (ink too faint, key colliding with the caption, and an
inverted scrim gradient that drew a hard line across the image).

### Diffs

    docs/CHARTER.md                    +8 / -4
    fixtures/arxiv-150k.fixture.yaml  +48 / -28
    requirements.txt                   +1 / -0   (matplotlib==3.11.1)

No fixture artifact was rebuilt or altered; nothing under
`fixtures/arxiv-150k/` changed.

## Verification

**Passed**

- Log block vs files: 17/17, including `ground_truth`'s array digest
  recomputed locally. Stop condition not triggered.
- Spec: no `developer-reported` comment remains (grep count 0); findings and
  changelog updated; the diff touches only the named fields plus the two
  corrections listed under Deviations; parses under `yaml.safe_load` with 7
  findings and 4 changelog entries.
- Every field except the drift pair and the three array digests is
  byte-unchanged — 30 value-bearing fields compared mechanically.
- Charter updated as specified.
- Verifier exit 0, 8 verified / 3 couldn't-check (see above for why 8, not 9).
- `docs/img/` holds 8 files + thumbnail, correct dimensions; the render runs in
  25.5 s against a 5-minute budget; `requirements.txt` gains exactly one pinned
  line.
- 11 tests pass; the smoke fixture still verifies.

**Failed**

Nothing.

**Couldn't check**

- **`vectors.npy` and `queries.npy` array digests.** Both are the release asset
  and are not in the repo, so build 3's `cb973a94…` and `16e0f488…` are
  published on the build log's authority. `ground_truth`'s was recomputable and
  matched, which is one of three.
- **Whether the images are *good*.** The brief reserves that judgement, and I
  have not made it. What I did check is that each renders, that the numbers in
  the captions match the spec, and that nothing is illegible.
- **The second-nearest region for the variant-D query**, as above — not
  derivable from any local artifact.
- **Value reproduction as a verifier feature.** Still unimplemented; the live
  reproduction reported here came from the export inside the build, not from
  `fixture verify`, which remains digests-only.

## Observed, not done

- **`fixture.status` is still `built`, not `verified`.** With three builds
  agreeing on values and the export reproducing four of them live, the case for
  `verified` is now much stronger than it was — but `verification.passes_when`
  describes a check `fixture_verify` still does not perform, so flipping the
  status would claim a check nobody runs. The roadmap already has
  "Fixture value-reproduction in `fixture verify`" in Phase 2.
- **The charter's 005 row says "in progress"**, as the brief specified. It
  wants flipping to done when this report is accepted.
- **`docs/img/` is not in `.gitignore` and the PNGs total ~14 MB.** They are
  deliberate deliverables, so that is presumably intended, but it is 14 MB of
  binaries entering git history.
- **`requirements.txt`'s transitive-closure section is now stale.** matplotlib
  pulled in contourpy, cycler, fonttools, kiwisolver, pillow, pyparsing,
  python-dateutil and six; the brief allowed exactly one line, so the closure
  section no longer lists everything installed. Same for pyarrow in task 004.
- **`single_node_hnsw.recall_at_10` moved 0.99695 → 0.9973** between builds 2
  and 3, the largest sub-printed movement of any reference result (0.00035).
  Still an order of magnitude inside its 0.01 tolerance, and invisible at
  published precision.
- **Variant A's key covers 13 of 37 top-level categories**, the rest folded
  into "25 others 6.2%". The parquet carries `primary_category` too, unused by
  any variant.

## Repo now contains

New:

    corpora/render_ground.py
    docs/img/ground_a_category.{png,svg}
    docs/img/ground_b_copies.{png,svg}
    docs/img/ground_c_region.{png,svg}
    docs/img/ground_d_query.{png,svg}
    docs/img/ground_thumbnail.png
    tasks/005-build3-and-ground.report.md
    tasks/scratch/005-build3-crosscheck.py
    tasks/scratch/005-build3-publish-edit.py
    tasks/scratch/005-tune-ink.py

Modified:

    fixtures/arxiv-150k.fixture.yaml   (build 3 values, torch recorded,
                                        parquet artifacts, changelog, findings)
    docs/CHARTER.md                    (004 done, 005 in progress, findings,
                                        Phase 1 build 3 done)
    requirements.txt                   (+1: matplotlib==3.11.1)

Unchanged: everything under `fixtures/arxiv-150k/` and
`fixtures/arxiv-smoke/`, `corpora/build_fixture.py`,
`corpora/export_ground_view.py`, `oneground/`.

### Dependencies added

`matplotlib==3.11.1`, one pinned line. Installed into `.venv`; it brought
eight transitive packages (see "Observed, not done").

### Not committed

Nothing was committed.

## Blocked on developer

Nothing blocked this task.

Three things to decide:

- **Which variant is the hero.** The script flags B as default and the
  thumbnail is B; the brief reserves the aesthetic choice, so nothing is
  fixed by that beyond the filename.
- **Whether `status: built` should become `verified`** — see "Observed, not
  done"; my reading is not yet, because no shipped code performs the check the
  spec describes.
- **Whether 14 MB of PNG/SVG belongs in git** or in the release asset
  alongside the vectors.
