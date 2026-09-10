# Report: 004-ground-view-export

## Repo state expected vs found

The brief expected task 003c committed and the tree clean.

| Expected | Found |
|---|---|
| 003c committed | **no** — HEAD is `0ab7567` (task 003b). 003c's work is present but uncommitted |
| tree clean | **no** — five files modified, three untracked, all of them 003c's output plus this task's brief |

**Task 003c is not committed.** Its changes sit in the working tree exactly as
this session left them: `corpora/build_fixture.py` (+38, `torch_receipt`),
`docs/CHARTER.md`, `fixtures/arxiv-150k.fixture.yaml`, the smoke fixture's
`build_info.json` and `MANIFEST.sha256`, plus the untracked 003c brief and
report.

I proceeded rather than stopping, for three reasons, and flag it here so the
commit sequence is a deliberate choice rather than an accident:

1. Nothing 004 builds on comes from 003c. The export imports `kmeans`,
   `centroid_dists`, `one_region_exact_recall`, `project`, `primary_category`,
   `year_of` and `append_manifest` from `build_fixture.py` — none of which
   003c touched. 003c added `torch_receipt`, which runs at `build_info` time.
2. The substance of 003c is present and was verified last session, so this is
   an uncommitted-but-complete state, not a half-finished one.
3. 004's brief carries no explicit "stop and report" clause, unlike 001b's,
   003's and 003b's, which all named one.

**The consequence is real**: my diff now spans two tasks. `build_fixture.py`'s
+38 lines are 003c's, not 004's — task 004 did not change that file at all.
Committing 003c and 004 separately would keep the receipt trail readable.

## What was done

All four steps, plus two verifications the brief did not ask for that seemed
necessary given what went wrong. Three things did not go to plan; they are in
Measurements, not buried.

### 1. `corpora/export_ground_view.py`

New. Imports `build_fixture.py` unmodified and defines no geometry of its own:
`kmeans(base, 256, seed)`, `centroid_dists`, `primary_category`, `year_of`,
`project`, `append_manifest` all come from there, so a change to a definition
in the builder changes the export with it.

Per base vector: region, d1, d2, ratio, closure copies at ε=0.20 / MAX_ASSIGN 4,
`primary_category`, `top_level_category`, `update_year`. Per query: region,
d1/d2 ratio, ambiguous at τ=1.10, and recall@10 at one-region exact routing.
Per centroid: region, position, size.

**Per-query recall is checked against the builder's own aggregate.**
`one_region_exact_recall` returns only the mean, so the per-query figure is
computed here and then compared with the builder's aggregate on the same
inputs; a mismatch beyond 1e-9 aborts. On the smoke run they agreed exactly
(0.290000). Without that check, this file could quietly drift from the
estimator it claims to mirror.

2-D placement is documented at the top of the file as illustrative and is the
only part not computed in 768-d: base points use `projection.npy` as built;
queries are placed at the mean position of their 10 true nearest neighbours;
centroids at the mean position of their members. The header spells out the
failure mode — a query whose true neighbours are scattered lands between them,
which is an artifact of the rule, not a property of the query.

Three parquet files, written with zstd compression, digests added to
`MANIFEST.sha256`, classified declared.

### 2. `fixture_verify.py`

`kind_of` gained a glob list so `ground_view_*.parquet` classify as declared,
alongside the exact-name set. Test added:
`test_ground_view_parquets_are_declared_synthetic` asserts all three are
declared, that the glob does *not* swallow `ground_view.txt`,
`ground_view_base.npy` or `vectors.parquet`, and that a tampered parquet is
still reported contradicted. 11 tests pass.

### 3. `corpora/run_arxiv_150k.sh`

Export step added between verify and the tarball; the three parquets added to
the small tarball; a second tarball `TARBALL_LARGE`
(`/workspace/arxiv-150k-large.tgz`) carrying `vectors.npy`, `queries.npy` and
`sample.jsonl.zst`. The large tarball is built *after* the small one so a
failure packing 460 MB still leaves the reviewable bundle on disk. `DONE` is
now followed by both paths.

The header note about `SKIP_PROJECTION` was inverted: the export needs
`projection.npy`, so a skipped projection now fails the run at the export step.
The smoke-test recipe in the header no longer sets it.

### 4. `corpora/POD_SETUP.md`

New "Build 3 — the reproducibility build" section: isolated venv **without**
`--system-site-packages` (naming that as the specific mistake that made build 1
differ), `pip install -r requirements.txt`, a one-line version check to run
before spending an hour, then the same single command. Documents both tarballs,
what each is for, and that a failed export assertion after a passing verifier
is a real disagreement to report rather than work around.

### Two checks the brief did not ask for

- **The assertion path is proven to fire.** On arxiv-smoke every published
  value is `TO_BE_FILLED`, so the export runs with nothing asserted — meaning
  the comparison code would first execute for real on the pod, after a
  three-hour build. `tasks/scratch/004-ground-view-assertions.py` runs the
  export unmodified against a copy of the fixture and two doctored spec copies.
  Result below.
- **The export is now idempotent w.r.t. the manifest.** See Measurements: the
  first version duplicated its own manifest lines on a second run.

## Measurements

### Three consecutive segfaults in the build step

The plan was one script run covering steps 2 and 3. Instead:

| Attempt | Died at | Exit |
|---|---|---|
| 1 | embedding batch 7/16 | 139 (SIGSEGV) |
| 2 | embedding batch 11/16 | 139 |
| 3 | embedding batch 8/16 | 139 |

    corpora/run_arxiv_150k.sh: line 93: 1770 Segmentation fault
        python corpora/build_fixture.py "${BUILD_ARGS[@]}" 2>&1

All three inside `python corpora/build_fixture.py` during embedding, at
different batches — non-deterministic. This is the unmodified build step;
task 004 changes nothing in it. The same machine crashed twice mid-embedding in
task 002b, and completed the same build successfully in 002b (x3), 003c and
several earlier runs, so it is intermittent rather than a regression.

`set -euo pipefail` caught every one and aborted before verify, export or
tarball, which is the correct behaviour and is itself evidence the script's
error handling works.

I did not keep re-rolling. The two things the failure blocked were obtained
another way, described below and both labelled for what they are.

### Working around it: `projection.npy`

The export needs `projection.npy`; the smoke fixture's last build (003c) ran
with `--skip-projection`. `tasks/scratch/004-ground-view-projection.py` runs
*only* the projection stage — `bf.project(base, spec["projection"]["params"])`
over the existing `vectors.npy`, saved and appended to the manifest exactly as
`build_fixture.main()` would.

    vectors: (2000, 768)
    projection: (2000, 2) in 51.9 s

**The result is bit-identical to what a full build produces.** Its digest is

    adba41731040b549d0726fa76d9b9a6a03e417348c951f28e4db177f096bcf7f

which is the same digest both with-projection builds produced in task 002b, via
the builder rather than this script. UMAP has now reproduced byte-for-byte
three times on this machine through two different code paths. Nothing was
re-embedded and no receipt was touched.

### Ground-view export on the smoke fixture

    [00:20:15] base 2,000 x 768  queries 200  projection (2000, 2)
    [00:20:15] k-means 256 (seed 20260908)
    [00:20:17] per-query mean matches build_fixture aggregate (0.290000)
    [00:20:17] wrote ground_view_base.parquet  (2,000 rows, 57,394 bytes)
    [00:20:17] wrote ground_view_queries.parquet  (200 rows, 5,023 bytes)
    [00:20:17] wrote ground_view_centroids.parquet  (256 rows, 4,594 bytes)

    ================ ground view summary ================
      base rows              2,000
      query rows             200
      centroid rows          256  (0 empty)
      copies histogram       1:1,059 (0.529)  2:403 (0.202)  3:205 (0.102)  4:333 (0.167)
      storage amplification  1.906x

      recomputed vs the spec's published values
      boundary_crispness       0.5295   (spec value TO_BE_FILLED - not asserted)
      ambiguous_query_rate     0.9350   (spec value TO_BE_FILLED - not asserted)
      skew_top10_share         0.1000   (spec value TO_BE_FILLED - not asserted)
      one_region_recall@10     0.2900   (spec drift pair TO_BE_FILLED - not asserted)

Exit 0, 1.4 s.

**The recomputed values match what task 001 measured for this fixture**, which
is the real check available here even though the smoke spec publishes nothing:

| Value | Export (004) | Task 001 build |
|---|---|---|
| boundary_crispness | 0.5295 | 0.5295 |
| ambiguous_query_rate | 0.9350 | 0.935 |
| skew_top10_share | 0.1000 | 0.100 |
| storage_amplification | 1.906x | 1.906 |

So the export's geometry agrees with the builder's on every quantity they both
compute — independently derived, same numbers.

### The one-region recall band, and whether it will hold at 150k

`one_region_recall@10` has no published field, so the assertion band is derived
from the spec's drift pair widened by the drift tolerance. Those are not the
same measurement — drift uses centroids fitted to pre-2019 records only, this
uses centroids fitted to everything — so the band is an inference and worth
checking before it runs on the pod.

On smoke, measured here: full-centroid one-region recall **0.290**. Task 001's
drift pair for the same fixture was 0.291 (n=85) / 0.277 (n=115), a
size-weighted mean of **0.283**. Full centroids score **+0.007** above
pre-2019 centroids — slightly better, in the direction expected, and far inside
a ±0.02 tolerance.

Applying that to arxiv-150k: drift 0.524 (n=965) / 0.551 (n=1035), weighted
mean 0.538; a comparable small positive offset puts full-centroid recall near
0.545, against a band of [0.504, 0.571]. The assertion should hold with room.
This is an extrapolation from one fixture three orders of magnitude smaller,
not a guarantee — but it is measured evidence rather than a guess, and if it
fails on the pod the band is the thing to question, not the geometry.

### The assertion path, exercised

`tasks/scratch/004-ground-view-assertions.py`, against a copy of the fixture
and doctored copies of the spec (the real spec untouched):

**A — spec publishes the measured values:**

    boundary_crispness       0.5295   spec 0.5295  delta 0.0000  tol 0.02  OK
    ambiguous_query_rate     0.9350   spec 0.935   delta 0.0000  tol 0.02  OK
    skew_top10_share         0.1000   spec 0.1     delta 0.0000  tol 0.02  OK
    one_region_recall@10     0.2900   drift band [0.270, 0.310]  OK
    all 4 published values checked reproduced within tolerance
    exit code 0

**B — spec publishes wrong values:**

    GROUND VIEW EXPORT FAILED - recomputed geometry disagrees with the published values:
      - boundary_crispness: recomputed 0.5295, spec 0.1, delta 0.4295 exceeds tolerance 0.02
      - ambiguous_query_rate: recomputed 0.9350, spec 0.5, delta 0.4350 exceeds tolerance 0.02
      - skew_top10_share: recomputed 0.1000, spec 0.9, delta 0.8000 exceeds tolerance 0.02
      - one_region_recall@10: 0.2900 outside the band [0.880, 0.920] derived from the spec's drift pair (0.9 / 0.9) +/- 0.02
    exit code 1

Both paths behave. This is the code that will run on the pod.

### A defect found and fixed: duplicate manifest lines

The first version called `bf.append_manifest` directly, which is append-only —
correct for the builder, which writes the projection line once. Running the
export twice over the same directory listed each table twice: the manifest went
to 14 entries with 6 `ground_view_` lines. The verifier still reported
everything verified, because each duplicate names a real file with a matching
digest — so this would not have been caught by verification, only by reading
the manifest.

Fixed with `rewrite_manifest_entries`, which drops the export's own lines before
re-adding them and touches no receipt line. Proven:

    reset to 8 entries
    run 1 exit=0 ground_view lines: 3, total: 11
    run 2 exit=0 ground_view lines: 3, total: 11

### An honesty fix in my own summary line

The export originally printed "all published values reproduced within
tolerance" even when every value had been skipped as `TO_BE_FILLED` — which is
what happens on the only fixture it can currently run against. It now prints
either the count and names of what was asserted, or:

    NOTHING ASSERTED: this spec publishes no values yet (all TO_BE_FILLED), so
    the summary above was not checked against anything. Expected for
    arxiv-smoke; on arxiv-150k every line above is asserted.

### Verifier

    summary: 11 verified, 0 contradicted, 0 couldnt_check  (digests only; 6 receipt, 5 declared)

Exit 0. All three parquets present and classified declared:

    verified      declared ground_view_base.parquet       23ee242d845034ed91c01f3dd6f57817d3b5d426ce3b2b1502a61fb10c2cf948
    verified      declared ground_view_queries.parquet    32a562466ccb29932742d3c146892b7f9f420676ce91dfe8219c320ac70ef6c6
    verified      declared ground_view_centroids.parquet  b9655c45a31bd2fde2440bb05d5764d6c4611767bfa39015e64c6352beeea496

`arxiv-150k` is unchanged: 5 verified, 3 couldn't-check, exit 0. The export
cannot run there — its vectors are the release asset and are not on this
machine, which is the whole reason this task exists.

### The tables

    ground_view_base.parquet       2,000 rows   57,394 bytes
      x:float, y:float, region:int32, d1:float, d2:float, ratio:float,
      copies:int8, top_level_category:string, primary_category:string,
      update_year:int16
    ground_view_queries.parquet      200 rows    5,023 bytes
      x:float, y:float, region:int32, ratio:float, ambiguous:bool,
      recall10_one_region:float
    ground_view_centroids.parquet    256 rows    4,594 bytes
      region:int32, x:float, y:float, size:int32

Sample rows and distributions, to show the columns carry what they should:

    base row 0   : x 3.897, y 3.092, region 221, d1 0.3051, d2 0.4281,
                   ratio 1.4031, copies 1, eess / eess.SP, 2025
    query row 0  : x -0.6417, y -0.0816, region 218, ratio 1.0482,
                   ambiguous True, recall10_one_region 0.2
    centroid row0: region 0, x -1.2511, y 7.2747, size 5

    top_level_category counts: cs 1314, stat 167, eess 128, math 107, cond-mat 78
    update_year range        : 2007 - 2025
    region size min/max      : 1 / 25
    queries ambiguous        : 187 / 200   (= 0.935, the measured rate)

`top_level_category` splits correctly on the dot and leaves dotless categories
whole (`cond-mat`, `hep-th`); at 150k the counts will span the eight hot
categories in `characterization.json`.

For 150k the base table will be 75x more rows; at this row size that is roughly
4 MB compressed, which is the point of the task — rendering against megabytes
instead of the 460 MB of vectors.

### Run script: post-build logic

The end-to-end run could not complete (three segfaults). To exercise the
sections this task added, `tasks/scratch/004-run-script-postbuild.py` runs the
real script text with **exactly one line replaced** — the
`python corpora/build_fixture.py ... | tee "$LOG"` invocation becomes an echo.
Everything after it is the script's own code, against the smoke fixture already
on disk:

    tarball contents:
      fixtures/arxiv-smoke/MANIFEST.sha256
      fixtures/arxiv-smoke/characterization.json
      fixtures/arxiv-smoke/build_info.json
      fixtures/arxiv-smoke/query_ids.json
      fixtures/arxiv-smoke/ground_truth.npy
      fixtures/arxiv-smoke/ground_view_base.parquet
      fixtures/arxiv-smoke/ground_view_queries.parquet
      fixtures/arxiv-smoke/ground_view_centroids.parquet
      logs/build-arxiv-smoke.log
      fixtures/arxiv-smoke/projection.npy

      bytes: 118799

    release asset contents:
      fixtures/arxiv-smoke/vectors.npy
      fixtures/arxiv-smoke/queries.npy
      fixtures/arxiv-smoke/sample.jsonl.zst

      bytes: 6418781

    DONE
    /tmp/arxiv-smoke-small.tgz
    /tmp/arxiv-smoke-large.tgz

Exit 0. Both tarballs produced with the right members; the verify and export
steps ran as part of it. What this does **not** prove is that the build step
and the new steps work together in one process — see "Couldn't check".

### Diffs

| File | +/- | |
|---|---|---|
| `corpora/export_ground_view.py` | new, 320 lines | |
| `corpora/run_arxiv_150k.sh` | +36 / -4 | export step, parquet members, large tarball, header |
| `corpora/POD_SETUP.md` | +50 / -0 | build-3 section |
| `oneground/fixture_verify.py` | +13 / -5 | glob classification, docstring |
| `oneground/test_fixture_verify.py` | +22 / -0 | one test |
| `requirements.txt` | **+1 / -0** | `pyarrow==25.0.1` |
| `corpora/build_fixture.py` | +38 / -0 | **all of it task 003c's; 004 changed nothing here** |

`fixtures/arxiv-150k.fixture.yaml` is unchanged by this task. arxiv-150k was
not rebuilt.

## Verification

**Passed**

- Export runs on smoke; the three parquet files exist, are classified
  `declared`, and verify — 11 verified, 0 contradicted, exit 0.
- Assertions against published values are in the script, and were *proven to
  fire* in both directions rather than assumed.
- `requirements.txt` gains exactly one pinned line, `pyarrow==25.0.1`
  (`git diff --numstat` = 1 / 0).
- The run script produces both tarballs with the correct members, exit 0, DONE
  followed by both paths — via the post-build path described above.
- The export's per-query recall matches `build_fixture`'s own aggregate
  exactly; its crispness, ambiguity, skew and amplification match what task 001
  measured for this fixture.
- 11 tests pass. `build_fixture.py` unmodified by this task. arxiv-150k
  untouched and still verifying.

**Failed**

Three end-to-end runs of `run_arxiv_150k.sh` on the smoke fixture, all with
SIGSEGV inside the unmodified embedding step. Not a failure of anything this
task changed, and the script aborted correctly each time — but it is the reason
step 3 was verified by the stubbed path rather than a clean full run, and it
should not be filed as a pass.

**Couldn't check**

- **The script end to end in one process.** The build step and the new steps
  were each exercised, never together. If the interaction between them is
  broken — it is a sequence of independent commands under `set -e`, so there is
  little room — it would first show on the pod.
- **The export at 150k scale.** Every number here comes from 2,000 vectors.
  Runtime (1.4 s), memory, and parquet size will all be ~75x. `kmeans` and
  `centroid_dists` over 150k x 768 are the same calls the builder already makes
  at that size, so the export should add minutes rather than hours, but I have
  not measured it.
- **Whether the assertions pass on arxiv-150k.** They are exercised against
  doctored specs here; the real comparison needs the real vectors. The
  one-region recall band is the one I would watch, and the reasoning above says
  why I expect it to hold.
- **Whether pyarrow is implicated in the segfaults.** Installing it is the only
  environment change between 003c's clean run and three failures, which is a
  suspicious correlation — but `build_fixture.py` never imports pyarrow, so
  there is no mechanism I can point to, and I did not spend a further hour
  bisecting it. Recorded because the correlation is real and someone should
  know it exists.
- **Empty regions at 150k.** Smoke had none (min region size 1). At 150k with
  256 centroids over a much larger corpus they are unlikely, but the centroid
  table writes NaN x/y for an empty region and a renderer should expect it.

## Observed, not done

- **Task 003c is uncommitted**, so this working tree contains two tasks. The
  `build_fixture.py` diff belongs entirely to 003c.
- **The export runs after the verifier in the script**, per the brief, so the
  three parquet digests are appended *after* verification and are never checked
  in that run. The tarball therefore ships a manifest listing three files
  nothing has verified. A second verifier call after the export would close it;
  the brief fixed the order, so I did not add one.
- **`ratio` is `inf` when d1 is 0.** A base vector exactly on its centroid
  gives a divide-by-zero, handled explicitly as `inf` rather than a warning.
  Did not occur on smoke; a renderer should not assume the column is finite.
- **The centroid table has no `top_level_category`.** A region's dominant
  category would be useful for colouring but was not in the brief's column
  list; it is one group-by away from the base table.
- **`fixture_verify.py` now classifies by glob**, so any future
  `ground_view_*.parquet` is declared automatically. That is intended, but it
  means a file named to match is declared without anyone deciding so — the test
  pins the current three and the near-miss names.
- **`logs/` is still not in `.gitignore`**, carried over from task 002.
- **The charter's `004` row still reads `after 003`** and its Phase 1 line for
  the hero image is untouched; updating it was not in this brief.

## Repo now contains

New:

    corpora/export_ground_view.py
    tasks/004-ground-view-export.report.md
    tasks/scratch/004-ground-view-projection.py
    tasks/scratch/004-ground-view-assertions.py
    tasks/scratch/004-run-script-postbuild.py
    fixtures/arxiv-smoke/projection.npy            (gitignored)
    fixtures/arxiv-smoke/ground_view_base.parquet
    fixtures/arxiv-smoke/ground_view_queries.parquet
    fixtures/arxiv-smoke/ground_view_centroids.parquet

Modified by this task:

    corpora/run_arxiv_150k.sh          (export step, parquets, large tarball)
    corpora/POD_SETUP.md               (build-3 section)
    oneground/fixture_verify.py        (ground_view_* -> declared)
    oneground/test_fixture_verify.py   (+1 test)
    requirements.txt                   (+1 line: pyarrow==25.0.1)
    fixtures/arxiv-smoke/MANIFEST.sha256  (projection + three parquet digests)

Modified by task 003c, still uncommitted: `corpora/build_fixture.py`,
`docs/CHARTER.md`, `fixtures/arxiv-150k.fixture.yaml`,
`fixtures/arxiv-smoke/build_info.json`.

Unchanged: everything under `fixtures/arxiv-150k/`.

### Dependencies added

`pyarrow==25.0.1`, one pinned line in `requirements.txt`, installed into
`.venv`. Nothing else.

### Not committed

Nothing was committed.

## Blocked on developer

Nothing blocked this task.

Three things worth a decision:

- **Commit 003c and 004 separately.** The working tree holds both; the
  `build_fixture.py` change is 003c's.
- **The segfaults.** Three in a row on this machine, in the unmodified
  embedding step, after a clean run last session. It does not affect the pod
  (different OS, different hardware, and builds 1–3 there have been stable),
  but local end-to-end testing of the run script is currently unreliable, and
  the pyarrow correlation is unexplained.
- **Whether the run script should verify again after the export**, so the
  parquet digests it just added are checked before being tarred.

---

## Addendum — the segfault hypothesis, tested

Follow-up instruction after the report above: scratch-test whether the three
segfaults correlate with pyarrow. Six runs of the smoke embedding step in a
throwaway venv copy, three with pyarrow uninstalled and three with it
installed; if correlated, test import order and `KMP_DUPLICATE_LIB_OK`.

**No repo file was changed.** The harness lives outside the repo entirely, in
the session scratchpad, rather than in `tasks/scratch/` — a deliberate
departure from CLAUDE.md rule 6, because the instruction was findings only. The
real `.venv` was never touched; it still has `pyarrow 25.0.1`.

### Answer

**The crash does not correlate with pyarrow, and did not reproduce at all.**
Six runs, zero crashes:

| Run | Arm | pyarrow | Exit | Elapsed | commit_avail before |
|---|---|---|---|---|---|
| A1 | A | absent | 0 | 894 s | 1.41 GB |
| B1 | B | present | 0 | 765 s | 5.43 GB |
| A2 | A | absent | 0 | 732 s | 6.11 GB |
| B2 | B | present | 0 | 510 s | 6.04 GB |
| A3 | A | absent | 0 | 441 s | 7.55 GB |
| B3 | B | present | 0 | 428 s | 7.50 GB |

All six completed the full 16/16 batches. Arm B is the exact condition the
three crashes ran under — pyarrow installed, never imported — and it succeeded
three times out of three. **pyarrow's presence is not sufficient to cause the
crash.** Phase C (import order, `KMP_DUPLICATE_LIB_OK`) was therefore not run:
the brief made it conditional on a correlation, and there is none to explain.

### What the crashes actually correlate with

While setting the experiment up I measured the machine, and found the far more
likely cause:

    free physical : 0.42 GB of 7.56 GB
    commit used   : 29.21 GB / 30.56 GB limit
    commit free   : 1.35 GB
    pagefile      : C:\pagefile.sys  alloc 23552 MB  peak 11685 MB

The Windows commit limit was essentially exhausted. The decisive observation
was not planned: one of my own polling commands failed with

    error launching git: The paging file is too small for this operation to complete.

That is `ERROR_COMMITMENT_LIMIT` — the machine could not commit enough memory
to launch `git`, a process of a few megabytes. A torch embedding step that
peaks near 800 MB (measured in task 002b) has no chance of allocating cleanly
in that state, and native code that does not check an allocation failure
segfaults rather than raising `MemoryError`. Every one of the three crashes was
mid-embedding, at a different batch each time — the signature of an allocation
that sometimes succeeds and sometimes does not, not of a deterministic bug.

The experiment then produced a second, unplanned piece of evidence. Memory
pressure eased over the ~80 minutes it ran (other processes on the machine
released memory), and **runtime tracked commit headroom almost monotonically**:

    commit_avail 1.41 GB -> 894 s
                 5.43 GB -> 765 s
                 6.11 GB -> 732 s
                 6.04 GB -> 510 s
                 7.55 GB -> 441 s
                 7.50 GB -> 428 s

A 2.1x speedup on identical work as commit headroom went from 1.4 GB to 7.5 GB.
That is paging, and it is the same variable the crashes appeared under. The
three crashes happened at the pressured end of that range; the six clean runs
happened as it recovered.

### What this does and does not establish

**Established.** pyarrow installed but not imported does not by itself cause
the crash — three clean runs in exactly that configuration. The machine was at
its commit limit when the crashes occurred, demonstrably so, to the point where
launching `git` failed. Embedding runtime on this machine is strongly
memory-bound.

**Not established.** The experiment never reproduced a crash, so it has little
power to rule out a pyarrow effect that only appears *under* memory pressure —
both arms would pass in the absence of pressure regardless. Confirming the
memory hypothesis directly would mean deliberately exhausting commit on the
developer's machine while embedding, which I did not do: it risks taking down
the developer's other work, and it was not asked for. The correlation is
strong and the mechanism is standard, but it remains a correlation plus a
plausible mechanism, not a controlled demonstration.

The earlier report's line — "installing pyarrow is the only environment change
between 003c's clean run and three failures, which is a suspicious
correlation" — is superseded. The environment changed in a second way I had not
measured at the time: available commit collapsed. That is the variable that
moved with the crashes.

### Practical consequence

Nothing in the repo needs changing. Two things follow for whoever runs a build
on this laptop:

- Local full builds need commit headroom, not just free RAM. Before a smoke
  build, check `commit_avail` rather than the task-manager RAM figure; below
  ~2 GB, expect the embedding step to crash or to run 2x slow.
- `POD_SETUP.md`'s memory guard already covers this for the pod ("if free RAM
  drops below 2 GB during embedding, stop and report"). The pod has 40 GB and
  builds 1–3 there have been stable; this is a laptop constraint, and it is why
  the canonical builds run on the pod.

### Method, for reproduction

- Throwaway venv: `robocopy .venv <scratchpad>/probe-venv /E /MT:16`, 1.26 GB,
  37,565 files, 98 s. Confirmed independent (its own `sys.prefix`) and working
  before use.
- Probe: loads the same 2,000 base texts from `fixtures/arxiv-smoke/sample.jsonl.zst`,
  same `{title}. {abstract}` template, same batch size 128, and calls
  `build_fixture.load_model()` and `build_fixture.embed()` — imported unmodified,
  read-only. pyarrow's presence is detected with `importlib.util.find_spec`,
  never by importing it, because "installed but never imported" is the condition
  under test.
- Design: **interleaved** A B A B A B rather than blocked. The machine's memory
  state drifts over the ~80 minutes the experiment takes, and a blocked design
  would have let that drift masquerade as an arm effect — which, given how much
  it drifted, it would have done. Available physical RAM and available commit
  were recorded before and after every run.
- An earlier blocked run of the same experiment was stopped and discarded once
  the memory problem was found, before it produced any run results.
