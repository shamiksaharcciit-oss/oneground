# Report: 027-projection-declared

## Repo state expected vs found

| Expected | Found |
|---|---|
| `task-020` at `fc83608` or later, rebased on `main` | yes — started from `ef60011`, nineteen commits on `main` at `1fe8e26` |
| the brief at `tasks/027-projection-declared.md` | present, committed at `cde4de3` |
| step 6: "the arXiv run **with the fixture's own `projection.npy`**" | **`arxiv-150k` ships no `projection.npy`.** It is not in the fixture directory, not in either release tarball, and not in the asset folder. `stackexchange-150k` has one; arXiv does not. |

**What was used instead, and why it is equivalent.**
`fixtures/arxiv-150k/ground_view_base.parquet` is tracked, listed in the
fixture's `MANIFEST.sha256`, and carries `x` and `y` for all 150,000 rows. It
was written by `corpora/export_ground_view.py` from the fixture build's
`projection.npy` — the same file the teaser's `base.bin` was written from, by a
different script into a different format. I verified its coordinates are
**bit-identical** to `base.bin`'s before building anything on it. So the
declared projection the brief asks for exists in the repo under another name,
and step 6's comparison is still between two independently written artifacts.

Also found, and reported below rather than worked around: the intended
producer for step 6 — a fresh `simulate --emit-state` — does not complete on
this machine.

## What was done

### 1. The columns (step 1)

Three, all declared, all additive (`state_version` unchanged; a state written
before them simply lacks them):

| column | shape | source |
|---|---|---|
| `assignment.projection` | (N, 2) float32 | read from the declared file |
| `route.projection` | (Q, 2) float32 | derived at emit time |
| `partition.projection` | (R, 2) float32 | derived at emit time |

The two derived ones are derived **in the pipeline, never in a view**, because
both are arithmetic over projected coordinates:

- **A query has no position.** The projection was fitted on base vectors;
  projecting a query into it would be a new computation in a space the run does
  not use. It is placed at the mean of its own true neighbours' positions —
  what the teaser draws. Verified to reproduce `ground_view_queries.parquet`
  exactly, float32 for float32.
- **A centroid is not a base vector either.** A region is placed at the mean
  position of the vectors whose home it is. A region with no home vectors gets
  NaN, not the origin, because the origin is a real place. The state contract
  allows NaN there and only there, and refuses a region that holds vectors and
  has no position.

Declared as `corpus.sample.projection.path`, digested with the other inputs,
read once **before anything is measured** so a mismatch stops the run in a
second rather than after an hour. A row count that does not match the corpus is
refused — not padded, truncated or reordered, because a placement that does not
line up draws every point in somebody else's place and looks fine.

`state_info.json` records path, sha256, size, row count, method, seed, library
and `fitted_on` where declared, the query-placement rule and its `k`, and the
fixture spec's sentence verbatim. Where the requirements declare no method or
seed it writes `couldnt_check` and why, rather than omitting the field.

Two formats: `.npy` (N, 2) and `.parquet` with `x`/`y`. `pyarrow` is imported
only for the second and only on demand, since it lives in the `[view]` extra.
**Never a precondition**: with none declared, `state_info.json` records
`kind: absent` with the reason and the lab falls back to the cell layout.

### 2. The refusal (step 2)

A vector column can be withheld; a projection cannot, because drawing the
picture *is* passing these numbers to a mark. So the rule became "you may not
compute with it", enforced twice:

- **`contract.Positions`**, the array a view is handed. Every ufunc and array
  function raises `MeasuredFromProjection`. Indexing, slicing, iteration and
  `.tolist()` work; a slice stays a `Positions`, so taking the x column does
  not launder it; the array is read-only.
- **`guard._projection_violations`**, static. It binds the names a module takes
  from a projection column and flags them in arithmetic, a comparison or a
  numpy statistic. Naming the columns alone would be useless — a view that
  draws them mentions them legitimately.

The stated limit is the vector rule's: `np.asarray(p)` returns a plain array.
This makes the mistake impossible by accident and obvious in review.

### 3–5. The drawing

The ground places every vector at its declared position and rings each region
at its declared placement; the cell layout stays as fallback and as a toggle.
The trace overlays the same picture: rings at the routed and probed regions,
each true neighbour ringed and louder where it lives outside the routed region,
and the query as a cross. The `positions` row goes `couldnt_check` → `declared`.

`contract.draw` **refuses** a drawing that read a projection and does not
caption it, checked as words rather than a flag because the words are what a
screenshot carries.

### 7. Docs

`docs/STATE.md` gains "The declared projection"; `docs/LAB.md` describes the
two layouts, what each is for, and the per-layout trace marks. Both files are
named by the brief.

## Measurements

**Step 6, the acceptance.** ε 0.20, all 150,000 arXiv vectors, compared by id
against `site/teaser/data/base.bin`:

| | |
|---|---|
| vectors compared | 150,000 |
| maximum coordinate difference | **0** (bit-identical, x and y) |
| copy-count disagreements | **0** |
| home-region disagreements | **0** |
| `positions` row | `declared` |
| caption carries the placement sentence | yes |

`base.bin` came from `export_teaser_data.py`; the state's positions from
`ground_view_base.parquet` via `export_ground_view.py`; copy counts from
neither — the ground recounts them from the state's own stored distances.

**Emitting, through the real product path.** A 4,000-vector synthetic corpus
with a declared projection, through `oneground characterize` then
`oneground simulate --emit-state`, emits all three columns at (4000, 2),
(1, 2) and (200, 2) with the provenance above.

**Cost.** The semantic state grew 18.0 → 19.2 MB at 150,000 vectors; the
single-node state 8.0 → 9.2 MB. Ground drawing p95 on this host at 150k:
92–253 ms, so arXiv chooses *render on release*, as it did before.

**Looked at, in a browser.** arXiv 150k at ε 0.200 in Edge, both layouts and
both views, zero uncaught errors. Toggle present, `positions` gaps rows 0,
canvas 900×900 projected and 688×688 by region.

## Verification

- **Full suite: 944 passed, 5 skipped, 0 failed** (`pytest oneground corpora`
  from the worktree root).
- **Guard: clean** over `views/` and the transport.
- **Identifier scan: it actually scanned.** `test_no_tracked_file_carries_a_machine_identifier`,
  `test_the_scan_actually_reads_the_tree`, `test_a_stamp_never_carries_a_machine_identifier`
  and `test_the_tracked_scan_opens_tracked_archives_synthetic` all **PASSED**,
  none skipped. This is stated explicitly because earlier in this task they did
  not — see "A defect the environment hid" below.
- **Task 020's acceptance script**, unchanged (sha256 `9fc0a0d9…`): **20 of 20**.
- **Tests added:** every arithmetic path over a `Positions` is refused while
  indexing and `tolist` work; the guard passes a module that draws the column
  and flags one that measures from it, at both lines; `draw` refuses an
  uncaptioned projected drawing; the ground's and the trace's mark orders are
  pinned; a browser test toggles the layouts and asserts each caption and the
  trace key describe what is on screen.

**Couldn't check.**
- **A fresh `simulate --emit-state` at 150,000 vectors.** Not attempted again,
  per your ruling. `semantic_sharded` builds 256 HNSW shards and faiss raises
  `MemoryError: std::bad_alloc` with under a gigabyte free on this 7.6 GB
  machine. **The drawing path is proved — projection → state → view → drawing
  places and colours every vector correctly. The emit path waits for a pod.**
  The state used for step 6 is task 020's own emitted state with the declared
  columns attached by `state.with_projection`, the same function `simulate`
  calls, which is the only step the OOM prevented.
- **`lab.js` is still not parsed where node is absent**, as in task 025. The
  static id test and the browser tests cover the failure modes that have
  actually bitten.

## Observed, not done

- **A fixture finding, for the main stream.** `ground_view_base.parquet`'s own
  `region` and `copies` columns disagree with `base.bin`'s on near-tie rows:
  **35 region disagreements** and **40 copy-count disagreements** at ε 0.20,
  out of 150,000. I first read this as two exports of the same
  `projection.npy` breaking ties differently. **The pod session showed that is
  wrong**: the cause is that `semantic_sharded`'s k-means does not reproduce
  across environments, so the two exports were not breaking ties — they were
  working from different centroids. See "A main-stream defect this session
  found" above; this bullet is that defect seen from one side.
  **This is a fixture matter, not a lab one**, and I used only the parquet's
  `x`/`y`, which are bit-identical to `base.bin`'s. The state's own copy counts
  and home regions agree with `base.bin` exactly — 0 and 0 — so nothing the lab
  draws is affected.
- **`stackexchange-150k`'s projection cannot be declared for its current run.**
  It has 150,000 rows and the run subsamples to 20,000, so the loader refuses
  it on the row count — correctly. A projection must be matched to the sampled
  corpus, not the source.
- **`requirements.arxiv-150k.yaml` does not declare a projection.** Adding one
  changes a published run's declared inputs and their digests, and the brief
  does not name that file. The scratch requirements used here is
  `tasks/scratch/027-arxiv-projection.yaml`.
- **Two scan tests confuse "not a checkout" with "git is not runnable."**
  Below; `main`'s file, outside this brief.

## A main-stream defect this session found: `semantic_sharded` does not reproduce across environments

**Not task 027's**, and not fixed here. Recorded with the evidence so the main
stream can act on it. It is also the cause of the fixture finding reported
earlier in this report, which I had put down to two exports breaking ties
differently.

### What was run

Session `20260918-184234`, pod `wlfnzjp71vpjw6`, RTX PRO 4000 in EU-RO-1:
`oneground simulate --emit-state` on arXiv 150k with the projection declared —
the one path this laptop cannot take. It succeeded. The state carries all
three declared columns, and the acceptance **read the emitted columns** rather
than attaching its own:

```
projection: READ FROM THE STATE as emitted
emitted column == the declared file: True
maximum coordinate difference               0     (bit-identical)
```

**So the emit path is proved.** What failed is beside it.

### The two camps

Four independent computations of the same assignment over the same 150,000
vectors, the same seed and the same configuration. They fall into two groups
that agree perfectly inside each and disagree across:

| | home-region disagreements |
|---|---|
| pod state vs laptop state (task 020) | **35** |
| pod state vs `ground_view_base.parquet` | **0** |
| laptop state vs `site/teaser/data/base.bin` | **0** |
| `ground_view_base.parquet` vs `base.bin` | **35** |

Camp A: the laptop's task-020 state and `base.bin`. Camp B: the pod's fresh
state and the parquet `export_ground_view.py` wrote. Each pair agrees to the
row; the pairs disagree on the same 35 vectors.

### It is not a tie-break

That was my first reading, and it is wrong. The stored distances themselves
differ:

```
centroid_dist identical, pod vs laptop : False
maximum |difference|                   : 0.004463374614715576
nearest_region identical               : False
```

A tie-break would leave `centroid_dist` bit-identical and move only which of
two equal distances won. **The centroids are different**, so k-means itself
converged elsewhere. The 35 rows that flip are simply the ones close enough to
a boundary for a centroid shift of that size to move them: their `d2/d1`
ranges 1.000012 to 1.005830.

### What it moves

At epsilon 0.20, `simulate.json` for the same configuration:

| field | pod | laptop (020) |
|---|---|---|
| `storage_amplification` | 3.715147 | 3.71516 |
| `stored_vectors` | 557,272 | 557,274 |
| `recall_at_10` | 0.9319 | 0.9318 |
| `ceiling_at_10` | 0.9324 | 0.9323 |
| `recall_at_1` | 0.9505 | 0.95 |
| `routing_loss` | 0.0676 | 0.0677 |
| `recall_at_100` | 0.886 | 0.886115 |
| `inv_ratio_at_10` | 0.997593 | 0.997592 |

`fanout`, `shards`, `index_loss` and the copy percentiles are unchanged.

### It was already written down as an open gap

`oneground/models/base.py:52-53`, from task 012b:

> `hash_sharded` and `semantic_sharded` build `IndexHNSWFlat` per shard and
> have not been converted; they take the same helper when someone does.

That paragraph is about the HNSW build, which task 012 made deterministic for
`single_node_hnsw` by pinning faiss to one OpenMP thread after measuring 37% of
returned ids differing between two builds. The k-means that decides the regions
is the same class of problem and is not covered by that fix either. The
determinism promise in the same docstring — *"two builds from the same
(vectors, config, seed) must produce the same measurements"* — does not hold
for this family across machines.

### What it means for what is published

- `requirements.arxiv-150k.yaml` is frozen and its published values came from
  one environment. Nothing here changes them.
- It does mean **a user reproducing the fixture on their own machine may not
  get the published `storage_amplification` to six decimals**, and the fixture
  verification's tolerances are what decides whether that reads as verified or
  contradicted. That is worth checking against the declared tolerances; I have
  not.
- The lab is unaffected. Positions are declared and read from a file, so they
  are bit-identical everywhere; the ground's colours are recounted from
  whatever the state holds, and are correct for that state.

### What I did not do

Not fixed here, per the ruling. No seed, threshold, tolerance or published
value was touched. `corpora/export_ground_view.py` and
`corpora/export_teaser_data.py` were read and not changed.

## A check that would have proved the wrong thing

Recorded prominently because it was caught before anything was spent, and
because the failure would have been invisible: a green result, on a real pod,
for a claim the run never tested.

**What the script did.** `027_acceptance.py` compares the lab's ground against
the teaser's `base.bin`. On this laptop no state carried a projection, so the
script read the declared parquet and *attached* the columns itself before
drawing — which is right here, and is why the laptop run proves the **drawing**
path.

**What that would have done on a pod.** The pod session exists to prove the
**emit** path: that `simulate --emit-state` writes those columns correctly at
150,000 vectors. But the script attached the projection unconditionally. Run
against a pod-emitted state it would have **overwritten the columns `simulate`
had just written**, drawn from the parquet instead, and printed `0 and 0` —
the same answer, from the same source, having never read what the run emitted.
The session would have cost real money to re-prove a thing already proved, and
the report would have said the emit path was verified.

Nothing would have failed. That is the whole point of recording it: a check
that silently substitutes its own input for the one under test does not go red,
it goes green for the wrong reason.

**The fix.** The script now uses the state's own columns where they exist, says
which it used, and refuses if an emitted column differs from the declared file
it was supposed to be written from:

```
        projection: READ FROM THE STATE as emitted
        emitted column == the declared file: True
```

against a state carrying them, and

```
        projection: ATTACHED here (this state emitted none)
```

against task 020's. Both still `0 and 0`. `027-acceptance.json` gains
`projection_emitted_by_simulate`, so the artifact records which of the two ran
rather than leaving it to the log.

**The general shape**, which is the part worth keeping: *a verification that
can supply its own input will eventually be pointed at a case where the input
is the thing being tested.* The same class as task 025's "a 200 says nothing
about whether the script that consumes it ran", and as the identifier scan
reporting a green skip while scanning nothing. In all three the check was
honest about what it measured and silent about what it had quietly replaced.

## A defect the environment hid

Recorded because it is the kind that makes a green suite mean less than it
says, and because I nearly reported around it.

Partway through this task my shells lost their `PATH` — a bare Windows system
path with no Git and no `/usr/bin`. A fresh terminal of yours was fine; my
calls inherit the Claude Code process environment, so they kept the stale copy
until you restarted it. What that did to the checks:

- `test_the_tracked_scan_opens_tracked_archives_synthetic` **failed** with
  `FileNotFoundError`, having no guard at all.
- `test_no_tracked_file_carries_a_machine_identifier` and
  `test_the_scan_actually_reads_the_tree` **skipped**, with the reason **"not a
  git checkout; nothing to scan"** — while `.git` existed. The scan that stops
  machine identifiers reaching a published tree reported a green-looking skip,
  with a false reason, having inspected nothing.

I committed nothing while that held, and after the restart confirmed all four
run and pass. The lasting lesson is the misleading skip: **a check that cannot
run should say it could not run, not describe a repo state that is not true.**
Those two tests are on `main` and outside this brief, so I have not changed
them; my suggestion is that they distinguish the two cases and fail on the
second.

## Repo now contains

On `task-020`, pushed after each commit:

| commit | |
|---|---|
| `c22249c` | the early-stop wording, and the picker's way to the rest of the list |
| `59ca25f` | the three declared columns; `Positions`; the guard rule |
| `84fe7dc` | the ground draws it; `draw` requires the caption |
| `ef60011` | step 6, and the mark-order defect |
| `fddfa5b` | the trace draws on the same placement |
| `16fdb68` | the interface half: the toggle, and what the page says about itself |
| `ebf2d79` | docs |

New: `oneground/models/projection.py`. Changed: `oneground/models/state.py`,
`oneground/lab/contract.py`, `oneground/lab/guard.py`,
`oneground/lab/views/ground.py`, `oneground/lab/views/query_trace.py`,
`oneground/lab/server.py`, `oneground/lab/static/{index.html,lab.js,lab.css}`,
`oneground/intake/__init__.py`, `oneground/simulate/__init__.py`,
`oneground/lab/test_lab.py`, `oneground/lab/test_server.py`,
`docs/STATE.md`, `docs/LAB.md`.

No measured value, tolerance, seed, gate, fixture file or published figure was
changed. No new dependency. `main` and `site/teaser/` untouched; no rebase, no
merge.

## Blocked on developer

- ~~A pod run of `simulate --emit-state` on arXiv 150k~~ **— done.** Session
  `20260918-184234`, pod `wlfnzjp71vpjw6`. The emit path is proved: all three
  declared columns emitted at 150,000 vectors, the acceptance read them rather
  than attaching its own, and the coordinates are bit-identical to `base.bin`.
  The same run found the k-means defect above. Emit time 2 min 41 s for the
  configuration, 3.3 s to write 19.2 MB of state; ~$0.05 against the $0.57
  cap; pod terminated, `pod ls` reports 0 oneground pods. The session as
  planned and priced was:
  `sessions/027-emit-state-arxiv.yaml`, with
  `requirements.arxiv-150k.projection.pod.yaml` and
  `corpora/run_027_emit_state.sh`. `oneground pod plan` resolves it live to
  RTX PRO 4000 (Blackwell) in EU-RO-1, derived from the `vecbench` volume, at
  **$0.50-$0.57/hr**, confirmed at the top of the range: **up to $0.57** for
  the one-hour cap, inside `max_usd $2.00`. Uploads 8.32 MB against the 50 MB
  cap; the 460 MB corpus is read from the volume, not sent.
- **The fixture finding above** — 35 region and 40 copy-count disagreements in
  `ground_view_base.parquet` — for the main stream, as you said you would route.
- **Whether `requirements.arxiv-150k.yaml` should declare the projection.** It
  would make the published run emit positions by default, and it changes that
  run's declared inputs and digests.
