# Report: 028b-determinism-measurements

Two measurements asked for after 028's decomposition: do the centroids
diverge on this machine at all, and does the index layer diverge directly.
Both were made; the third (re-measuring at `1fe8e26`) was skipped as
instructed. No product code was changed.

**The short version: neither layer diverges on this machine today, and the
028 sighting is explained by a commit rather than by nondeterminism.** The
detail, and what it does to 029's premise, is below.

## Repo state expected vs found

Expected to work on `task-028`: found at `2ace28f`, local and `origin` in
agreement. `main` was not touched.

Two things about the repo that were not there when 028 was written:

* **The 029 brief moved off this branch, twice.** While 028b was starting the
  developer cherry-picked `7c13582` onto `main` as `e2c9a01`; by the time
  028c looked again, `main` was back at `570f07d` — frozen, as it should be —
  and the brief was on a new `task-029` at `e610275`, branched from
  `570f07d`, with `e2c9a01` left dangling. **This paragraph said the brief
  was on `main`; corrected in 028c.** The file is byte-identical in `7c13582`
  and `e610275`, so `task-028` and `task-029` each add the same content and a
  later merge of both has two commits doing it. Not a conflict while they stay
  identical; worth knowing before the merge.
* Nothing else moved. `tasks/020-simulator-state.md` is still the only
  untracked file.

## What was done

One scratch script, `tasks/scratch/028b-determinism.py`, importing project
code unmodified — `crispness.kmeans`, `crispness.centroid_dists`,
`base.single_threaded_faiss`, and the family's own `MAX_ASSIGN` and
`EF_CONSTRUCTION` constants. It runs on the same arxiv-150k sample the 028
cards were measured on.

It was run twice. **The first run restated `MAX_ASSIGN` as 8 instead of
importing it; the family's value is 4.** That measured a closure the family
never builds — 6.458 copies per vector against the real 3.715 — and picked
its "largest region" under the wrong cap. The script now imports both
constants and the run below is the corrected one. The comparisons in the
first run were a-against-b under one cap on both sides, so their verdicts did
not change; the absolute numbers did, and they are the ones a reader would
have quoted.

## Measurements

This machine, `.venv\Scripts\python.exe`, numpy 2.5.3, faiss-cpu 1.15.0
(pinned). 150,000 vectors of 768 dimensions, the workdir's own sample; 2,000
queries; seed 20260908; `centroids=256`, `epsilon=0.2`, `M=32`,
`efConstruction=200`, `efSearch=96`. faiss's default thread count here is
**4**.

### 1. The centroids, computed twice, compared array to array

| | default threads (4) | one thread |
|---|---|---|
| two runs bitwise identical | **yes** | **yes** |
| home region differs | 0 of 150,000 | 0 of 150,000 |
| copy counts differ | 0 vectors | 0 vectors |
| stored vectors | 557,274 = 557,274 | 557,274 = 557,274 |
| `storage_amplification` | 3.715160 = 3.715160 | 3.715160 = 3.715160 |
| wall clock per run | 18.4 s, 16.9 s | 17.9 s, 17.4 s |

**The k-means does not diverge on this machine**, and it does not diverge
when the thread count is what the family's build is *not* pinning it to
either. Two independent runs of `kmeans(base, 256, 20260908)` produce
bit-identical arrays.

A second reading, free with the first: **3.715160 is the sweep's own value**
for this configuration, from 2026-09-09. The whole routing closure —
centroids, nearest region for 150,000 vectors, copy counts, amplification —
reproduces nine days later to the last digit recorded. That is the same
conclusion 028's row comparison reached from the other end, now from the
centroids themselves rather than from what was derived from them.

What this does **not** establish: the pod's divergence is across
environments, and nothing here crosses one. Only the thread count was varied;
the BLAS backend, the sample size and the k-means `nredo`/`niter`/`spherical`
settings were not, and those are 029's step 1.

### 2. One shard's HNSW, built twice and searched twice

Region 218, the largest under the ε=0.2 closure, holding **5,219** vectors.
Built exactly as `semantic_sharded.build` builds a shard, searched with the
run's own 2,000 queries at k=10.

| | default threads (4) | one thread |
|---|---|---|
| one index searched twice, identical | **yes** | **yes** |
| two builds, returned ids identical | **no** | **yes** |
| ids differing | 691 of 20,000 (**3.455%**) | 0 |
| queries with any difference | 115 of 2,000 | 0 |
| max abs score difference | 0.068346 | 0 |
| mean top-10 overlap | 0.991850 | 1.0 |
| build wall clock | 3.9 s, 4.7 s | 10.9 s, 10.7 s |

**Search is deterministic; the multi-threaded build is not.** Two builds of
one shard from identical vectors, under four threads, disagree on 3.455% of
returned ids. Under one thread — which is what `deterministic=True` pins, and
what `semantic_sharded.build` runs — they are identical.

That is task 012's finding reproduced for a sharded family: 012 measured 37%
of ids differing at `efSearch=10` for `single_node_hnsw`; at `efSearch=96`
over one 5,219-vector shard it is 3.455%, and the single-threaded build
removes it. The build cost of one thread, on this shard, is 2.6×.

### 3. When the sharded families were converted

`git log -S "single_threaded_faiss" -- oneground/models/semantic_sharded/model.py`
returns exactly one commit, and the same for `hash_sharded`:

    dc85609  2026-09-10 18:47:40 +0200  task 015: sharded determinism, the
             pgvector adapter, and two required methods

It added `deterministic`, `resolve_deterministic` and
`with single_threaded_faiss(det):` to both families' `build`.

The arxiv workdir's `simulate_info.json` records `run_at:
2026-09-09T16:47:12Z`. **The sweep ran 24 hours before the commit that made
these families' builds deterministic.**

## Verification

* **Does the k-means diverge here?** No. Bitwise identity over two runs under
  each of two thread settings, plus identity of everything derived from it,
  plus agreement with the sweep's own amplification to six decimals.
* **Does the index layer diverge here?** Yes, and only when built
  multi-threaded: 3.455% of ids over one shard. Single-threaded, it does not,
  and searching a fixed index twice never did.
* **What this says about 028's sighting.** Its baseline rows were measured by
  a build that predates `dc85609`; the rows compared against them were
  measured by today's single-threaded build. A multi-threaded build differs
  from a single-threaded one in exactly the layer 028 saw move — the ids
  returned from inside a shard — and in exactly the layer it saw *not* move,
  it does not, because routing does not depend on the graph. The magnitudes
  line up as well: 3.455% of ids differing inside one shard produced a
  recall@10 change of 0.00005 in the full configuration, because most
  differing ids are swaps between near-equal neighbours (mean top-10 overlap
  0.9919) and recall counts only whether the true neighbour came back.
* **Couldn't check, and it is the one thing that would close it:** that the
  code installed on 2026-09-09 was in fact the pre-`dc85609` build. The
  author date is strong evidence and not proof — this repo's history has been
  rebased at least once (`pre-rebase-015-backup` exists), and
  `simulate_info.json` records no oneground version, which is 028's
  *Observed, not done* item 3. Re-measuring one configuration at `1fe8e26` —
  the measurement skipped by instruction — is what would turn "consistent
  with" into "established". It is now worth more than it looked, because
  everything else has been eliminated: it is the only remaining explanation
  for 028's sighting that has not been tested.

## Observed, not done

1. **`oneground/models/base.py:52-53` is stale, and 029's brief quotes it.**
   It says `hash_sharded` and `semantic_sharded` "build `IndexHNSWFlat` per
   shard and have not been converted; they take the same helper when someone
   does." `dc85609` converted both, a week ago. 029's *Why* cites those lines
   as the recorded gap. The prose is two lines and I did not touch it: it
   sits in the module 029 will work in, and this is the developer's brief to
   revise.
2. **The arxiv workdir's sharded rows were measured by a non-deterministic
   build.** Every `semantic_sharded` and `hash_sharded` row in
   `runs/arxiv-150k-via-characterize/simulate.json` predates `dc85609`; the
   `single_node_hnsw` row does not have this problem, since that family was
   converted earlier. Those rows are the baselines the 028 cards cite by
   digest. Nothing measured here says they are wrong — they are inside every
   published tolerance — but a card comparing a new single-threaded row
   against an old multi-threaded one carries this difference inside its
   delta, at the 1e-5 to 1e-3 scale seen in 028. Re-sweeping that workdir
   would remove it. That is a decision about a run, not about code, and it is
   the developer's.
3. **Only the thread count was varied.** The other knobs 029's step 1 names —
   BLAS backend, `nredo`/`niter`/`spherical`, sample size — were not, and
   neither was a second environment. This report says the k-means is stable
   here under threads, not that it is stable.
4. **The first run of the script measured the wrong closure**, described
   under *What was done*. It is corrected, and the only reason it is in the
   report is that a reader comparing a 6.458 in a console log against a 3.715
   in a card deserves to know which was wrong.

## Repo now contains

    tasks/028b-determinism-measurements.report.md   this report
    tasks/scratch/028b-determinism.py               the two measurements (untracked, .gitignore:62)

No product code was changed by this task.

## Blocked on developer

Nothing. 029's brief is the developer's to revise; the findings above are
what it asked this branch for.
