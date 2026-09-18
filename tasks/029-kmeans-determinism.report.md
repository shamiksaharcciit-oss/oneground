# Report: 029-kmeans-determinism

**Status: steps 1 and 2 done; the task reshaped twice on the developer's
rulings; step 4 needs a pod session and the developer's `y`. Steps 3, 5, 6 and
7 follow that, because what the fix should be depends on what the pod says.**

## Repo state expected vs found

| Expected | Found |
|---|---|
| new branch from `main` | `task-029` from `origin/main` at `570f07d`, clean |
| `tasks/029-kmeans-determinism.md` | **not on `origin/main`.** It is untracked in the main checkout and committed on `task-028` (`7c13582`). Read from the main checkout without modifying it, as task 020 did with its own brief. |
| `models/base.py:52-53` records the gap | present — **and stale.** See below. |
| step 4's "byte-identical state columns" | **not checkable on this branch.** `oneground/models/state.py`, `oneground/lab/` and `corpora/render_from_state.py` are all task-020's and merge on the 23rd. There is no `--emit-state` here. |
| timings out of `simulate.json` (020b) | **also task-020's.** `build_seconds` and `query_seconds` are still inside `simulate.json` on `main`, so the file differs run to run for a reason that is not the defect. |

On the developer's ruling, **step 4 splits**: `simulate.json` with the two
timing fields masked, and the centroids array-to-array, are checkable today;
state columns wait for Monday's merge and are **task 029b**, not part of this
report's step 4. Saying step 4 was done on the strength of half of it would be
the wrong call.

### `models/base.py:52-53` is stale, and it misdirected two streams

It says:

> `hash_sharded` and `semantic_sharded` build `IndexHNSWFlat` per shard and
> have not been converted; they take the same helper when someone does.

Both were converted by **task 015, `dc85609`, 10 September** — a commit titled
"sharded determinism" that changed both families' `model.py` and never touched
this docstring:

```
oneground/models/semantic_sharded/model.py:152    with single_threaded_faiss(det):
oneground/models/hash_sharded/model.py:147        with single_threaded_faiss(det):
```

`git show --stat dc85609` touches `models/base.py` zero times.

This is not a footnote. That line is quoted **in the 029 brief itself** as
evidence, it is what pointed the brief at an HNSW defect, and it is what sent
me looking for a local HNSW divergence. A stale claim in the place people go
to check a claim costs exactly this.

## What was done

### Step 1 — reproduce it locally, before changing anything

Three independent attempts, all null, on a 4-core laptop. **A null here does
not show the defect is absent**: the pod evidence in task 027 stands on its
own, and the developer's ruling is that a local null was the expected result.

**1a. `faiss.Kmeans` across every axis this machine can reach**
(`tasks/scratch/029_reproduce.py`, `029_reproduce_wide.py`), synthetic
clustered vectors, seed 20260908:

| varied | values | result |
|---|---|---|
| threads, run to run | 1, 2, 4, 8, 16, 32 (oversubscribed past 4 cores) | identical, max abs difference **0** |
| threads, across counts | 1 vs 2, 4, 8, 16, 32 | **identical**, 0 vectors reassigned |
| `niter` | 1, 5, 20 | identical |
| dimension | 64, 768 | identical |
| n | 2,000 / 20,000 / 50,000 / 80,000 | identical |

**1b. The pod's exact configuration, on this laptop**
(`tasks/scratch/029_kmeans_real.py`): 256 centroids over the real arXiv
150,000 × 768 at seed 20260908 — the configuration whose centroids differed
between this machine and the pod.

| | result |
|---|---|
| 4 threads, run to run | **identical**, max abs difference 0 (22.9 s, 23.7 s) |
| 1 thread, run to run | **identical**, max abs difference 0 (16.6 s, 14.4 s) |
| 4 threads vs 1 | **identical** |

Worth recording: at k=256 faiss trains on at most
`max_points_per_centroid * k` = 65,536 points, so 150,000 **is** subsampled —
and the subsample is reproducible here too.

**1c. Independently confirmed.** The proposals stream measured the same 256
centroids over the same 150,000 twice on this machine, under four threads and
one, and got bitwise reproduction. Three nulls, two streams.

### Step 2 — naming the cause

**Established.** Within one machine, `semantic_sharded`'s k-means is bitwise
deterministic: same centroids, same subsample, at any thread count, on
synthetic and on the real corpus. So the mechanism is **not** multithreaded
accumulation order, **not** thread-count-dependent initialisation, and **not**
scheduling — those would all show up in 1a or 1b and none did. Those three
candidates from the brief are ruled **out** on this machine.

**Superseded: SIMD dispatch, disproved on this machine.** It was the leading
explanation and it is wrong. faiss picks kernels by instruction set and exposes
the choice through `FAISS_OPT_LEVEL`; this laptop supports AVX512, so it can be
made to run AVX2 or the generic path as well. All four
(`tasks/scratch/029_simd.py`, each level in its own process because the level
is read at import):

| `FAISS_OPT_LEVEL` | vs the pod's centroids | vs this laptop's emitted state |
|---|---|---|
| (default) | differs, 0.00103923 | **identical** |
| AVX512 | differs, 0.00103923 | **identical** |
| AVX2 | differs, 0.00103923 | **identical** |
| generic | differs, 0.00103923 | **identical** |

Every level agrees with every other, bitwise. The kernel dispatch does not
change this result, so it cannot be what separates the two machines.

**What does change it: the reduction order of the assignment step** — and that
is a local reproduction of the divergence, which step 1 asked for. faiss
computes k-means assignment through BLAS above
`distance_compute_blas_threshold` and through its own kernels below it. Both
are reachable on one machine (`tasks/scratch/029_blas.py`):

| path | vs the pod | vs the default path |
|---|---|---|
| default (threshold 128,000) | differs, 0.00103923 | — |
| **BLAS disabled** (threshold 1e9) | differs, 0.00366427 | **differs, 0.00366427** |
| BLAS always (threshold 1) | differs, 0.00103923 | identical |
| BLAS, `query_bs` 1024 | differs, 0.00103923 | identical |
| BLAS, `database_bs` 4096 | differs, 0.00103923 | identical |

Turning BLAS off moves the centroids by **0.00366** on one machine, with one
wheel, one CPU and one seed — **larger than the 0.00104 that separates this
laptop from the pod.** Block sizes change nothing. So the mechanism is
established: *the k-means result depends on the order in which the assignment
step sums floats, and which implementation performs that step decides the
order.*

**The leading explanation is now the BLAS each wheel links.** Both environments
pin `faiss-cpu 1.15.0` and `numpy 2.5.3` — read from each run's own
`state_info.json` — so the *version* is not the variable. A Windows wheel and a
Linux wheel of the same faiss link different BLAS builds, and a different BLAS
sums a dot product in a different order. That is deterministic *within* a
machine and different *across*, which is the shape task 027 measured: four
computations falling into two camps that agree perfectly inside each, {laptop,
`base.bin`} and {pod, `ground_view_base.parquet`}.

The cross-machine shape is the same under either explanation — which is why it
could not, on its own, tell SIMD dispatch from BLAS. The local test could, and
did.

**Established:** the assignment step's reduction order changes the centroids,
by more than the observed cross-machine difference, on one machine.
**Not established:** that the two wheels' BLAS is *the* difference that
produced 027's 0.00104. Magnitudes differ (0.00366 for BLAS-off here against
0.00104 pod-to-laptop), which is expected if the pod also used BLAS but a
different one — but I have not shown it.

**What would confirm it:** the same k-means on a pod under the same knobs,
with the centroids brought back. If the pod's default reproduces 027's
centroids and some setting there reproduces this laptop's, the reduction order
is the whole story. That is step 4's session.

**If it is confirmed, the honest fix may not be "make it reproduce across
machines."** Pinning every float reduction order across instruction sets means
giving up the vectorised path, and the effect here is ~1.3e-5 against declared
tolerances of 0.02. The alternative is to *state* that centroid assignment is
per-platform and bound the effect. **That is a finding, not a failure — and it
is the developer's decision, not mine.** I will measure and present it, per
the ruling.

### The task reshaped, twice

Recorded because the shape of 029 changed under measurement, and the report
should say so rather than present the final shape as the original.

1. **The brief framed one defect** — k-means — citing both sightings.
2. **The developer corrected it to two** (18 September), after the proposals
   stream compared all ten fields rather than two: `index_loss` absorbed the
   whole of that sighting's recall delta while `ceiling_at_10`, `routing_loss`,
   `storage_amplification`, `fanout` and `est_memory_bytes` reproduced exactly
   — the signature of the index, not the partition. My pod finding separates
   from the other side: there `ceiling_at_10` **did** move.
3. **The developer corrected it back to one**, after the proposals stream
   traced the HNSW sighting to a sweep run 24 hours before task 015's fix
   landed. That sighting is a live measurement against a pre-fix baseline, not
   a live defect. It independently confirmed the fix: one shard, two builds,
   691 of 20,000 ids differing at four threads and **zero at one**, at 2.6×
   build time.

**One defect stands: k-means across environments.** The HNSW half is dropped.

My own HNSW sweep agrees with that and is reported here only so the next
person does not repeat it. It builds `IndexHNSWFlat` **directly**, not through
a family, so it measures faiss and not oneground:

| shard population, 4 threads, built twice | result |
|---|---|
| 125 | reproduces |
| 600 | diverges, 15 of 5,000 slots (0.30%) |
| 2,000 | diverges, 173 (3.46%) |
| 8,000 | diverges, 1,673 (33.46%) |
| 20,000 | diverges, 3,075 (61.50%) |
| the same, pinned to one thread | **reproduces at every size** |

That is the behaviour task 012 measured and task 015 fixed for these families;
it is reachable now only by bypassing the families, which is what the stale
docstring invited.

## Measurements

Every figure above carries its script. The two that matter most:

- **Within a machine, the real configuration is bitwise reproducible.** 256
  centroids, 150,000 × 768, seed 20260908: identical at 4 threads and at 1,
  and identical between them.
- **Across machines it is not.** Task 027, pod `wlfnzjp71vpjw6`:
  `centroid_dist` max difference **0.004463374614715576**, 35 of 150,000 home
  regions moved, 40 copy counts, eight published values in the sixth decimal.

## Verification

- Step 1 attempted and null, three ways, reported as a null.
- Step 2's three candidate mechanisms ruled out by measurement; the fourth
  named as leading and explicitly not established.
- Suite, guard and identifier scan: **not yet run for this task** — no project
  code has changed yet beyond the docstring correction below.

**Couldn't check.** Which BLAS each wheel links, and whether that is the
difference that produced 027's 0.00104. Step 4's session.

## Observed, not done

- **`models/base.py:52-53`.** Corrected, because 029 is the determinism task
  and the line is the project's own statement of what determinism guarantees
  per family. It is a docstring: no gate, value, seed or tolerance moved.
- **`docs/MODELS.md`** (step 7) is not touched yet; it waits on step 4, since
  what it should claim about cross-environment behaviour is what step 4
  decides.

## Repo now contains

To follow — nothing committed at the time this section was first written.

## Blocked on developer

- **A pod session for step 4.** Prepared and priced; needs a typed `y`.
  `sessions/029-kmeans-second-environment.yaml` with
  `corpora/run_029_kmeans.sh` and `tasks/scratch/029_pod_kmeans.py`. It runs
  the same 256-centroid k-means on the pod under all four `FAISS_OPT_LEVEL`
  settings and all three BLAS-threshold settings — twelve runs — and brings
  the raw centroid arrays back with the host's CPU description, so the two
  machines can be compared setting by setting. It measures and decides
  nothing.

  `oneground pod plan` resolves it live: **RTX PRO 4000 (Blackwell), EU-RO-1**
  (derived from the `vecbench` volume), **$0.50–$0.57/hr**, confirmed at the
  top of the range — **up to $0.57** for the one-hour cap, inside
  `max_usd $2.00`. Uploads 0.004 MB; the corpus is read from the volume.
  Stock on that card is **Low**, so `up` may not get one first try.

  Three outcomes, all informative: the pod's default reproducing task 027's
  centroids confirms 027 from a second run; any pod setting reproducing this
  laptop's makes the difference a knob rather than a platform; none matching
  means the BLAS implementations differ and the honest answer is to state that
  centroid assignment is per-platform and bound the effect — **a finding, not
  a failure, and yours to rule on.**
- **Task 029b**, the state-column half of step 4, after task-020 merges on the
  23rd.
