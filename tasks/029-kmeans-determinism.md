# Task 029 — The k-means that does not reproduce

## Setup
New branch from `main`: `git checkout -b task-029 main` — in the worktree
is fine, but **not** on `task-020`, which is finished and merges on the
23rd. `main` is release-frozen, so nothing lands there; 029 merges after.
Commit `task 029:` and push after every commit.

## Why
Two streams found this independently this week.

The lab stream, on a pod (`tasks/027-projection-declared.report.md`): the
same `semantic_sharded` configuration, same seed, same inputs, measured on
a pod and on the laptop, produced different centroids. `centroid_dist`
differs by up to 0.004463, `nearest_region` differs for 35 of 150,000
vectors, 40 copy counts differ, and eight published values move in the
sixth decimal — `storage_amplification` 3.715147 against 3.71516,
`stored_vectors` 557,272 against 557,274, `recall_at_10` 0.9319 against
0.9318, `ceiling_at_10` 0.9324 against 0.9323. Four computations fall into
two camps that agree perfectly inside each. The 35 rows that move are the
ones nearest a boundary (d2/d1 1.000012–1.005830), which is the symptom,
not the cause.

The proposals stream, on one machine
(`tasks/028-proposals-tier1.report.md`): `epsilon=0.2,probe=2` measured
twice differed by 0.00005 of recall@10 — one neighbour in 20,000 — under a
seeded k-means and a deterministic build.

`models/base.py:52-53` already records the gap: task 012 converted
`single_node_hnsw` to a deterministic build and noted that `hash_sharded`
and `semantic_sharded` "have not been converted." That was about HNSW.
This is the k-means, and the HNSW fix does not cover it.

Nothing published is wrong: the fixture's tolerances are 0.02 on the
ratios and these deltas are ~1.3e-5, so a rebuild reports `verified`. The
defect is in the reproducibility of the bytes, not the correctness of the
values — and in what the fixture says about why its bytes differ.

## Do

1. **Reproduce it deliberately, on one machine.** Before changing
   anything, find a configuration and a thread setting under which two
   runs of the same seed diverge locally. Vary, one at a time:
   `OMP_NUM_THREADS` / `faiss.omp_set_num_threads`, the k-means
   `nredo`/`niter`/`spherical` settings, the BLAS backend, and the sample
   size. Report which one moves it and by how much. If it cannot be made
   to diverge locally, say so and use the pod state already on disk as the
   evidence — but try first, because a local reproduction makes everything
   after it cheap.

2. **Name the cause.** Not "faiss is non-deterministic" — which mechanism.
   Candidates worth ruling in or out by measurement: multithreaded
   assignment accumulating in a non-fixed order; a thread-count-dependent
   initialisation; float summation order in the centroid update; a BLAS
   kernel choice that differs by CPU. Say which you established and which
   you did not.

3. **Fix it the way 012 did** — by construction, not by tolerance. Single
   threading, a fixed reduction order, or whatever the cause demands, and
   it applies to `semantic_sharded` and `hash_sharded` alike. The knob is
   the existing `deterministic=True` default; `deterministic=False` may
   keep the fast path, and the state must record which was used.

4. **Prove it.** Two runs on this machine, byte-identical `simulate.json`
   (with the timing fields already moved to `simulate_info.json` by 020b),
   byte-identical state columns, and byte-identical centroids. Then the
   harder half: the same configuration on a second environment. A pod
   session is allowed for this and needs the developer's `y` — prepare the
   spec, run `pod plan`, and ask. Cross-environment byte-identity is the
   claim; if it does not hold after the fix, that is a finding and you
   report the residual rather than widening anything.

5. **Measure the cost.** Build and query time at 20k and 150k, before and
   after, median and spread over at least five runs, reported beside 012's
   HNSW figures (1.8× on 1.18M, faster at 20k). If the cost is severe,
   propose the split — deterministic for reference and fixture builds,
   parallel for sweeps — with numbers, and do not decide it.

6. **Say what the fixture should now claim — do not change it.**
   `fixtures/arxiv-150k.fixture.yaml` explains its byte differences by
   naming embedding non-determinism across hardware. That is now known to
   be one of two causes. Draft the replacement wording — both causes
   named, which values each moves, and what a rebuild should expect — and
   put it in the report for the developer to rule on. The published values
   stay: they are correct within their stated tolerances, and recomputing
   them would invalidate the three-build receipt that makes the fixture's
   claim checkable. That is the developer's decision, not yours; present
   it, do not take it.

7. **Docs.** `docs/MODELS.md`: what `deterministic=True` now guarantees
   for each family, and what it costs. Add the cross-environment claim
   only if step 4 proved it.

## Acceptance
- The divergence reproduced (or the attempt reported), the cause named
  with what was and was not established.
- Both sharded families deterministic by construction; two local runs
  byte-identical across `simulate.json`, state columns and centroids.
- Cross-environment identity proved on a pod, or the residual reported.
- Costs measured at both sizes, beside 012's figures.
- Draft fixture wording in the report; the spec unchanged.
- Suite green, guard clean, identifier scan runs rather than skips.

## Do not
- Widen a tolerance. Change a published value. Touch `main`, the tag,
  `task-020`, `task-028`, or `site/`. Decide the fixture question.
