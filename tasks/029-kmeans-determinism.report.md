# Report: 029-kmeans-determinism

## The result

**Byte-identical centroids across two microarchitectures — proved, not
predicted.**

```
pod    986c1b6b4772bcdc3b3c6835     AMD EPYC, 24c/48t, AVX2, no AVX512
laptop 986c1b6b4772bcdc3b3c6835     Intel, 4 cores, AVX512
BITWISE EQUAL: True
```

Same corpus, same seed 20260908, `deterministic=True`. Two 256 × 768 float32
arrays, identical byte for byte, on CPUs that do not share an instruction set.
Before the fix the same two machines produced centroids differing by 0.00104,
moving 35 of 150,000 vectors into different home regions and eight published
values in the sixth decimal.

**Why that needed a fix rather than a tolerance**, and this is the part the
second session settled. The pod's wheel links
`libopenblaso-r0-d77a1985.3.15.so` — OpenBLAS 0.3.15, the OpenMP build — read
off the pod with `ldd`, not inferred. This laptop's links `libopenblas.dll`.
**It is the same library family on both sides.** The divergence is therefore
not a packaging accident that aligning two wheels could remove: OpenBLAS picks
its GEMM kernel by microarchitecture at run time, by design, and sums the same
floats in a different order on a different CPU. **Keeping the arithmetic out
of that library is the only route to identity**, which is what
`deterministic_blas` does.

---

### And through `simulate`, end to end

The laptop's run completed — it did not hit task 027's OOM; that was a
machine-state fact, not a property of the code. Against the pod's:

```
masking wall-clock timings and the run name
  pod    ea80d2b87200b54c263627db
  laptop ea80d2b87200b54c263627db
  byte-identical: True
  every one of 36 measured row fields equal across the two machines
```

Two things are masked and both are labels rather than measurements: the wall
clock (`build_seconds`, `query_seconds` — task 020b moved them out of
`simulate.json` for exactly this reason, though that commit is on task-020),
and `run`, which I named differently in the two requirements files. Every
other field — recall at 1/10/100, ceiling, routing and index loss,
`inv_ratio_at_10`, `storage_amplification`, `stored_vectors`,
`est_memory_bytes`, `fanout`, the copy percentiles — is identical.

`simulate_info.deterministic` records `true` for both configurations on both
machines.

**So step 4 holds in full: byte-identity across environments, proved through
`simulate` and not only through the probe.**

---

**Status: steps 1–7 done. The cause is faiss's BLAS path — not SIMD
dispatch, not threading — and it is fixed by construction on the developer's
Option A ruling.**

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

## Step 4 — the second environment, and the answer

Session `20260918-201437`, pod `p30fscsf4at179`, RTX PRO 4000 in EU-RO-1.
Twelve k-means, DONE in 8 minutes, ~$0.07 of a $0.57 cap; fetched and
terminated by `watch`.

### The host

| | this laptop | the pod |
|---|---|---|
| CPU | Intel, 4 cores | **AMD EPYC** (AMD-V, `svm`, `sse4a`), 24 cores / 48 threads |
| instruction sets | AVX, AVX2, **AVX512** (F, BW, DQ, VL, VNNI, …) | AVX, AVX2, FMA — **no AVX512** |
| faiss / numpy | 1.15.0 / 2.5.3 | 1.15.0 / 2.5.3 |
| faiss threads | 4 | 48 |

### The twelve runs

Each cell is the sha256 prefix of the 256 × 768 float32 centroid array.

| dispatch level | BLAS setting | pod digest | this laptop | bitwise equal |
|---|---|---|---|---|
| (default) | default (thr 128,000) | `6852d797` | `9ebfeefc` | no |
| (default) | **no BLAS** (thr 1e9) | `986c1b6b` | `986c1b6b` | **YES** |
| (default) | always BLAS (thr 1) | `6852d797` | `9ebfeefc` | no |
| AVX512 | default | `6852d797` | `9ebfeefc` | no |
| AVX512 | **no BLAS** | `986c1b6b` | `986c1b6b` | **YES** |
| AVX512 | always BLAS | `6852d797` | `9ebfeefc` | no |
| AVX2 | default | `6852d797` | `9ebfeefc` | no |
| AVX2 | **no BLAS** | `986c1b6b` | `986c1b6b` | **YES** |
| AVX2 | always BLAS | `6852d797` | `9ebfeefc` | no |
| generic | default | `6852d797` | `9ebfeefc` | no |
| generic | **no BLAS** | `986c1b6b` | `986c1b6b` | **YES** |
| generic | always BLAS | `6852d797` | `9ebfeefc` | no |

"Bitwise equal" is `np.array_equal` on the two arrays, not a digest
comparison.

### Which pod setting reproduces this laptop's centroids

**All four of them with faiss's BLAS path disabled, exactly.** An Intel laptop
with AVX512 and an AMD EPYC without it produce the *same 256 centroids, bit
for bit*, when the assignment step runs through faiss's own kernels.

Two further confirmations fall out of the same table:

- **The pod's eight BLAS runs reproduce task 027's emitted state exactly.**
  027's finding is confirmed by an independent second run on a different pod.
- **The laptop's four BLAS runs reproduce task 020's emitted state exactly.**
  Each machine is self-consistent; the two camps are real and stable.
- **The dispatch level is irrelevant on both machines**, with BLAS on *and*
  with BLAS off. My step-2 test had a gap — at 150,000 × 768 faiss is above
  the BLAS threshold, so the dispatched kernels never ran and the test was a
  no-op rather than a disproof. Re-run with BLAS off
  (`tasks/scratch/029_simd_noblas.py`), all four levels still agree bitwise on
  this laptop, and the pod's twelve runs show the same. The disproof stands,
  now for the right reason.

### The cause, named

**faiss's BLAS path.** Above `distance_compute_blas_threshold` the k-means
assignment step is a GEMM handed to the bundled BLAS; below it, faiss uses its
own kernels. faiss's kernels sum in the same order on both machines and give
bit-identical centroids. The BLAS does not, because OpenBLAS selects a GEMM
kernel per microarchitecture at run time — an Intel AVX512 kernel here, a Zen
kernel on the pod — and a different blocking gives a different summation
order.

Not "faiss is non-deterministic": faiss's own arithmetic is reproducible
across these two platforms. It is the linear-algebra library underneath, and
the boundary is exactly one run-time variable.

**Which BLAS each wheel links — measured, in the second session.** The first
session recorded the CPU and not the linked libraries, so the pod's was
inferred from packaging. `ldd` on the installed `_swigfaiss*.so` settled it:

```
libopenblaso-r0-d77a1985.3.15.so => .../faiss_cpu.libs/libopenblaso-r0-d77a1985.3.15.so
== bundled libs ==
  libgfortran-83c28eba.so.5.0.0
  libgomp-e985bcbb.so.1.0.0
  libopenblaso-r0-d77a1985.3.15.so
  libquadmath-2284e583.so.0.0.0
```

The pod's wheel bundles **OpenBLAS 0.3.15**, the OpenMP-threaded build (the
`o` in `libopenblaso`). This laptop's bundles `libopenblas.dll`.

**This is a better result than the hypothesis it replaces, and it strengthens
the case for the fix.** The guess was "a Windows wheel and a Linux wheel link
*different BLAS*" — which would have made the divergence a packaging accident,
fixable in principle by aligning the two wheels. It is not that. **Both sides
bundle the same library family**, and it still diverges, because OpenBLAS
selects its GEMM kernel by microarchitecture at run time: an AVX512 kernel on
this Intel laptop, a Zen kernel on the AMD pod. So the difference is not
something a build could be aligned away — it is one library doing what it is
designed to do, faster, per CPU.

That removes the last reading under which this might have been someone's
packaging mistake to fix upstream. The only way to get byte-identity is to
keep the arithmetic out of that library, which is exactly what
`deterministic_blas` does.

### Step 5 — what the deterministic path costs

Five runs each, median with min and max.

| corpus | path | median | min | max |
|---|---|---|---|---|
| 20,000 × 768, k=256, laptop | BLAS | 1.39 s | 1.35 | 1.43 |
| 20,000 × 768, k=256, laptop | no BLAS | **8.45 s** | 5.42 | 8.69 |
| 150,000 × 768, k=256, laptop | BLAS | 6.82 s | 6.72 | 8.13 |
| 150,000 × 768, k=256, laptop | no BLAS | **33.50 s** | 29.72 | 41.17 |
| 150,000 × 768, k=256, **pod** | BLAS | 39.46 s | 29.32 | 42.84 |
| 150,000 × 768, k=256, **pod** | no BLAS | **6.85 s** | 6.78 | 6.89 |

**The cost inverts between machines.** On this 4-core laptop the deterministic
path is **4.9× slower** at 150,000 and 6.1× slower at 20,000. On the 48-thread
pod it is **5.8× faster** — 6.85 s against 39.46 s. BLAS on 48 threads over a
65,536-point subsample is losing to its own threading; faiss's kernels are
not.

Beside task 012's HNSW figures (1.8× on 1.18M, faster at 20k), this is the
same shape of answer: the deterministic path is not uniformly more expensive,
and on the machine that runs the canonical builds it is cheaper.

## Step 3 — the fix, by construction

`deterministic=True` now means both halves.

`models/base.py` gains `deterministic_blas(enabled)` beside task 012's
`single_threaded_faiss`, and `deterministic_faiss(enabled)` entering both. One
thread fixes the order of work within a process; keeping faiss's distance
computations off the BLAS path is what crosses machines. Both restore in a
`finally` — `distance_compute_blas_threshold` is a process-wide faiss global
exactly as the thread count is — and the restore was checked to hold on an
exception. The threshold is a C `int`, so `1 << 40` raises `OverflowError`; it
is `2**30`, about 1.07e9 against a largest batch here of 150,000 × 256 = 3.84e7.

**The call site that mattered was not in a family.** `simulate._centroid_cache`
computes the k-means that every semantic row in a sweep depends on — the
family's own call is only the fallback for when no context is given — and until
now it ran **outside every determinism context**. That is where task 027's
divergence came from, and the `single_threaded_faiss(det)` inside the family
never covered it. It now runs under `deterministic_faiss(det)`, and the cache
is keyed by `(centroids, deterministic)` rather than count alone, so two
configs that disagree about determinism cannot silently share one clustering
computed under whichever ran first.

**Verified that the fix engages, not merely that it exists.** The sweep's
shared cache now produces centroid digest `986c1b6b4772` on the real arXiv
256/150,000 configuration — the exact set the AMD EPYC pod and this Intel
AVX512 laptop both produced with BLAS off — against `9ebfeefc68df` (this
laptop, task 020 emitted) and `6852d7979394` (the pod, task 027 emitted).

**Scope, stated rather than implied.** `semantic_sharded` is the only family
with a k-means. `hash_sharded` has none, so for it the BLAS half affects its
index and not a partition; it takes the same context for one contract.
`single_node_hnsw` keeps the thread half alone — the brief scopes this to the
sharded families, and changing its arithmetic would move its published values
for no reason asked for.

**Which path was used is recorded** in `simulate_info.json`, per configuration,
because the state cannot: `models/state.py` is task-020's and not on this
branch.

## Step 4, the local runs — and a verdict that contradicted itself

`simulate.json` byte-identical across two full runs with `build_seconds` and
`query_seconds` masked (020b moved them out, but that commit is on task-020):
sha256 `6d836710b455f009` both times.

**The cross-environment half is proved too** — session `20260918-205534`,
reported under "The result" above: masking only the wall clock and the `run`
name, the two machines' `simulate.json` is byte-identical and all 36 measured
row fields are equal.

### The comparison said NOT PROVED with an empty residual

Recorded because of what it nearly cost.

The staged comparison printed `BYTE-IDENTITY ACROSS ENVIRONMENTS: NOT PROVED
— residual above`, and above it, under "THE RESIDUAL, field by field:", was
nothing at all.

**A failing verdict with nothing to show is a contradiction.** Either
something differs and the residual should name it, or nothing differs and the
verdict is wrong. Both cannot hold. It would have been easy to report the
verdict as it stood — it was the cautious-sounding answer, and "not proved" is
the safer thing to say when you are unsure. It would also have been false.

Chased instead, the cause was mine: `029_compare.py` diffed only `rows`, while
the actual difference sat at the top level in `run` — `029-proof` against
`029-proof-laptop`, two names I had chosen myself in the two requirements
files. A full structural diff showed exactly five differences: the four
wall-clock timings and that one label. With both masked, identical.

The lesson is not about this script. **An inconsistency between a verdict and
its evidence is a signal to investigate, not something to pass along** — and
the direction of the error does not matter. A falsely negative result is as
wrong as a falsely positive one, and it is more likely to survive review
because it looks like caution.

## Step 6 — draft fixture wording, for the developer to rule on

**The spec is unchanged.** This is a draft of one finding's `note` in
`fixtures/arxiv-150k.fixture.yaml`, for `digests_are_environment_specific`.
Nothing in `fixtures/` was edited.

### What it says now, and why it is now incomplete

> Three builds, three environments … All three produced byte-identical
> sampling receipts … and three distinct vector digests, and so three distinct
> ground-truth, characterization and projection digests. … Artifact digests
> are environment-specific; reproducing the published values within tolerance,
> not the bytes, is the cross-environment claim this fixture makes.

It is true, and it names one cause: the embedding produces different vectors
on different hardware, so every digest downstream of `vectors.npy` differs.
Task 029 found a **second, independent** cause that the passage does not
mention — one that moves the same digests **even when the vectors are
byte-identical**. A reader debugging a rebuild would check their vectors,
find them matching, and have nowhere else to look.

### Draft replacement

> **id: digests_are_environment_specific**
>
> Three builds, three environments: build 1 on the pod template's numpy 2.1.2
> (RTX 4090), build 2 in an isolated venv honouring requirements.txt exactly
> (RTX 4090), build 3 in that same pinned environment on an RTX PRO 4500
> Blackwell. All three produced byte-identical sampling receipts —
> `sample.jsonl.zst 404cb92e…` and `query_ids.json a0f3236c…` in every build —
> and three distinct vector digests, and so three distinct ground-truth,
> characterization and projection digests.
>
> **Two independent causes produce those differences, and they are separable.**
>
> **1. The embedding, across hardware.** The same model on different
> accelerators returns slightly different vectors, so `vectors.npy` differs and
> every artifact derived from it differs with it. This is what the three builds
> above show: different vector digests, different everything downstream.
>
> **2. The k-means assignment, across microarchitectures** (task 029). Above
> faiss's `distance_compute_blas_threshold` the assignment step is a GEMM
> handed to the bundled BLAS, and OpenBLAS selects its kernel by CPU at run
> time. The same floats are summed in a different order, so the centroids
> differ — **even given byte-identical vectors**. Measured on the same
> 150,000 × 768 at seed 20260908, same `faiss-cpu 1.15.0` and `numpy 2.5.3`,
> on an Intel AVX512 laptop and an AMD EPYC pod: centroids differ by 0.00104,
> **35 of 150,000 vectors change home region**, 40 copy counts change, and
> eight `simulate.json` values move in the sixth decimal —
> `storage_amplification` 3.715147 against 3.71516, `stored_vectors` 557,272
> against 557,274, `recall_at_10` 0.9319 against 0.9318, `ceiling_at_10`
> 0.9324 against 0.9323. Each machine reproduced itself exactly; the two did
> not agree with each other.
>
> **What each cause moves.** Cause 1 moves `vectors.npy` and therefore every
> digest. Cause 2 moves the characterization, the regions and the
> `semantic_sharded` rows, while leaving `vectors.npy`, the sampling receipts
> and the ground truth untouched. A rebuild whose vector digest matches and
> whose characterization does not has hit cause 2 alone.
>
> **What a rebuild should expect from task 029 onward.** Cause 2 is fixed by
> construction: `deterministic=True` — the default — now keeps the k-means off
> the BLAS path as well as pinning faiss to one thread, and two machines with
> different instruction sets produce bitwise identical centroids. A rebuild on
> the pinned environment should now reproduce the characterization and the
> `semantic_sharded` rows byte for byte on any CPU, and will still produce a
> different `vectors.npy` on different accelerator hardware, because cause 1 is
> not fixed and is not a defect. `simulate_info.json` records which path each
> configuration used.
>
> **The published values on this page were computed before that fix**, on the
> BLAS path. They are correct within their stated tolerances — the deltas cause
> 2 introduces are ~1.3e-5 against tolerances of 0.02, three orders of margin,
> and every rebuild reports `verified` — and they are **not** the bytes a
> post-029 rebuild will produce for the characterization and the semantic
> rows. Reproducing the published values within tolerance remains the
> cross-environment claim this fixture makes. Byte-identity of the derived
> artifacts is now available for the k-means half and is not claimed here,
> because these values predate it.

### What I deliberately did not put in the draft

- **Any change to a published value.** They stand; recomputing them would
  invalidate the three-build receipt that makes the fixture's claim checkable,
  which is the developer's stated reason for freezing them.
- **A claim that a post-029 rebuild reproduces *this page's* digests.** It will
  not, and saying so would be the same error the current wording makes in the
  other direction.
- **Any wording about `single_node_hnsw`.** It has no k-means and task 029 did
  not touch it.

## The decision as it was presented (the developer chose Option A)

Both options are viable on the evidence. **I am not choosing.**

### Option A — make it reproduce

One run-time variable, set before any k-means:
`faiss.cvar.distance_compute_blas_threshold` raised so the assignment never
takes the BLAS path. Measured consequence: an Intel AVX512 laptop and an AMD
Zen pod produce byte-identical centroids, so `simulate.json`,
`storage_amplification`, `stored_vectors` and the state's assignment columns
become reproducible across environments.

- **For:** it makes the fixture's byte-identical rebuild claim true across
  machines rather than within one. It is one line, with a knob
  (`deterministic=False` keeps the fast path), which is exactly the shape task
  012 used. On the pod it is *faster*.
- **Against:** 4.9× slower at 150,000 on the developer's laptop. It couples
  the project to a faiss run-time global, which is process-wide and would need
  the same `finally` discipline `single_threaded_faiss` already uses. And it
  buys byte-identity between *these two* platforms — a third microarchitecture
  is untested, and faiss's own kernels could in principle dispatch too.

### Option B — state that centroid assignment is per-platform, and bound it

Leave the arithmetic alone; declare the behaviour and put a measured bound on
it.

- **For:** the effect is already inside every tolerance that governs it. The
  deltas are ~1.3e-5 on ratios against declared tolerances of **0.02** —
  three orders of margin — so a rebuild anywhere reports `verified`, which the
  developer confirmed on 18 September. Nothing published is wrong, and no
  user-facing claim depends on byte-identity.
- **Against:** the fixture's three-build receipt is a byte-identity argument,
  and "byte-identical within a platform" is a weaker claim than the one the
  docs currently imply. It leaves a real difference undisclosed unless the
  wording changes with it.

### What I would want to know before deciding, if it were mine

Whether the fixture's rebuild claim is meant to hold across machines or only
within one. If across, Option A is now cheap and proven. If within, Option B
is honest and free. That is a product question about what the fixture
promises, which is why it is yours.

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

**Couldn't check — recorded as a known unmeasured detail, not left implied.**
Which BLAS the pod's wheel links. The result does **not** rest on it: it rests
on the twelve runs, which show the BLAS path differing across the two machines
and faiss's own kernels agreeing, whatever library was underneath. Naming
OpenBLAS on the pod is inference from packaging, not measurement. This laptop's bundles
`libopenblas.dll`, read off disk; my session script recorded the host CPU and
not the linked libraries, so the pod's is inferred from packaging rather than
measured. `ldd` on the installed `_swigfaiss*.so` would have settled it. A gap
in my spec — it does not change the result, which is established by the twelve
runs, but it is one line I should have asked for.

## Observed, not done

- **A parameter at its default produces a different label from its omission.**
  Found by making the mistake: I wrote `deterministic: true` into the proof
  requirements so a reader would not have to know the default to read the
  receipt. `deterministic` is a declared build parameter, so it went into the
  label, and the `include` and the `grid` became two distinct rows:

  ```
  semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2]
  semantic_sharded[M=32,centroids=256,deterministic=True,efSearch=96,epsilon=0.2,probe=2]
  ```

  Identical work, two rows, on both machines.

  **The rule it implies: a parameter at its default must produce the same
  label as its omission** — otherwise a sweep can measure identical work twice
  and present it as two configurations, and a proposal loop reading that table
  would see two options where there is one. That is task 026's parameter
  layer, not this task's, and it is left for it.

  Consequences here, all contained: the comparison stays like-for-like because
  both machines ran the same file; the pod time roughly doubled, inside the
  cap; and this run's row labels do not match task 020's canonical label, so
  its `simulate.json` is comparable *across machines* but not directly against
  the reference run.

- **`models/base.py:52-53`.** Corrected, because 029 is the determinism task
  and the line is the project's own statement of what determinism guarantees
  per family. It is a docstring: no gate, value, seed or tolerance moved.
- **`docs/MODELS.md`** (step 7) is not touched yet; it waits on step 4, since
  what it should claim about cross-environment behaviour is what step 4
  decides.

## Repo now contains

To follow — nothing committed at the time this section was first written.

## Blocked on developer

- **The step 4 cross-environment proof**, through `simulate` rather than a
  probe. Prepared and priced; needs a typed `y`.
  `sessions/029-determinism-proof.yaml`, with
  `requirements.arxiv-150k.determinism.pod.yaml` and
  `corpora/run_029_proof.sh`. It runs the real command on the pod with
  `deterministic: true` written out explicitly, and brings back
  `simulate.json`, `simulate_info.json` and the centroids, so the two machines
  compare through the product path. It also runs `ldd` on the installed
  `_swigfaiss*.so` and lists the bundled libs — closing the gap the first
  session left. **`pod plan`: RTX PRO 4000 (Blackwell), EU-RO-1,
  $0.50–$0.57/hr confirmed at the top of the range, up to $0.57 against the
  one-hour cap, inside `max_usd $2.00`; uploads 3.81 MB.** The claim: with the
  timing fields masked, `simulate.json` byte-identical between the two
  machines and the centroids bitwise equal. If it does not hold, the residual
  is the finding and gets reported as one.

- ~~The first pod session~~ **— done.** `20260918-201437`, pod
  `p30fscsf4at179`, ~$0.07 of a $0.57 cap, terminated, `pod ls` 0 oneground
  pods.
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
