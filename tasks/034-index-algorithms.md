# Task 034 — The index algorithm becomes a choice

## Setup
Branch `task-034` from `main`. Commit `task 034:` and push after every
commit. No pod is required for the work; one may be needed for the 150k
measurements, and that is a developer's `y`.

## Why
`simulate` varies the architecture — one index, hash-partitioned,
semantically partitioned — and HNSW's parameters within each. It does not
vary the index algorithm. All three families build HNSW underneath, and
`M`, `efConstruction` and `efSearch` are the only index knobs a user can
turn.

That was right for the question the project started from: hold the index
constant so the partition's effect can be isolated. It is now a limit,
and a large one, because the algorithm choice is where the
memory-versus-recall trade-off actually lives. HNSW is fast, accurate and
expensive in RAM. IVF-PQ is an order of magnitude smaller and loses
recall in ways that depend on the corpus. A flat index is exact and does
not scale. A team choosing between them gets nothing from oneground
today, and it is a question asked more often than sharding.

It also suits what the tool is good at: recall against exact ground truth,
memory measured rather than estimated, and a cost that is
corpus-dependent — which is precisely the kind of thing folklore gets
wrong.

## Do

1. **The index becomes a declared parameter of every family**, in 026's
   parameter-table form, with its own knobs declared per algorithm:
   - `flat` — exact, no parameters. The reference point: recall 1.0 by
     construction, and the memory and query cost of not approximating.
   - `hnsw` — `M`, `efConstruction`, `efSearch`. The current behaviour,
     and it must remain bit-for-bit what it is today: every published
     fixture value was measured under it and none of them may move.
   - `ivf` — `nlist`, `nprobe`.
   - `ivf_pq` — `nlist`, `nprobe`, `m` (sub-quantisers), `nbits`.
   An unknown index or a knob belonging to another algorithm is refused
   with the declared list, as 026 refuses an unknown parameter. A knob
   that an algorithm ignores is refused rather than accepted — the same
   rule, for the same reason.

2. **Determinism, per algorithm, measured not assumed.** 029 established
   that faiss's BLAS path is what diverges across environments and that
   `deterministic=True` must keep the arithmetic out of it. IVF training
   is a k-means and inherits that directly. PQ training is a second
   clustering and must be checked the same way. For each algorithm,
   report whether two runs on one machine are byte-identical, and whether
   the pod and the laptop agree — the 029 apparatus already exists, so
   this is a measurement rather than a new investigation.

3. **`footprint()` stops being arithmetic.** With quantisation, memory is
   no longer vectors × dimension × 4. Report per configuration: the index
   size as faiss reports it, the stored vector bytes, and the overhead —
   measured from the built index, not estimated from a formula. Where a
   figure can only be estimated, say so and mark it `estimated`, as the
   report already does for `est_memory_bytes`.

4. **The decomposition must survive.** `ceiling()` is mandatory and
   already separates routing loss from index loss. With four algorithms
   the second term becomes the interesting one: a semantic partition at
   0.93 ceiling with a flat index loses nothing to the index; the same
   partition with IVF-PQ loses something measurable, and the report must
   show which is which. Verify on both fixtures that routing loss is
   identical across index choices for the same partition — it must be, by
   definition, and if it is not, that is a defect in the decomposition.

5. **Run the sweep on both fixtures** and paste the table: four
   algorithms × the three families, recall@10, routing loss, index loss,
   measured memory, build time, query time. Then write the findings from
   the numbers, in particular: what IVF-PQ costs in recall on each
   corpus, and whether the two corpora agree about it. They disagreed
   about drift and agreed about architecture; whether they agree about
   quantisation is not something anyone here knows.

6. **What the report may not say**, tested as the claim invariant is
   tested: that one algorithm is better than another (they trade
   differently and the trade is the finding); that a memory figure for
   one corpus transfers to another; that a quantisation result at 150k
   holds at 10M. The sample caveat already exists — this adds the
   quantisation caveat beside it, because PQ's error depends on the
   distribution it was trained on.

7. **Published values do not move.** Both fixtures' reference results
   were measured with HNSW at declared parameters. Adding `index` as a
   parameter must not change a single one — prove it by re-running the
   reference configurations and diffing `simulate.json`, and if a label
   changes because `index` now appears in it, 032's canonicalisation rule
   applies: a parameter at its default produces the same label as its
   omission, so `index: hnsw` must be the default and must not re-label.

8. **Docs.** `docs/MODELS.md` gains the four algorithms, what each is
   for, its knobs, its determinism status and its measured cost.
   `docs/CHARTER.md`'s roadmap loses "more engine adapters" as the only
   named index work and gains this.

## Acceptance
- Four algorithms declared, their knobs in the parameter tables, unknown
  and foreign knobs refused.
- Determinism reported per algorithm, one machine and cross-environment.
- Memory measured from the built index, estimates marked as such.
- Routing loss identical across index choices for the same partition.
- The sweep on both fixtures, pasted, with findings written from the
  numbers.
- Every published fixture value unchanged; labels unchanged for the
  reference configurations.

## Do not
- Rank the algorithms. Change a published value or tolerance. Let
  `index: hnsw` re-label an existing configuration. Estimate a memory
  figure that can be measured.
