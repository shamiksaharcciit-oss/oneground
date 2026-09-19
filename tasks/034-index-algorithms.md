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

There is a gap on the other side of it. Those four are faiss's four, and
the simulation is honest about them; engines offer something else. Qdrant
builds HNSW and nothing else — its quantisation is a modifier on that
graph, not a separate index family. pgvector offers HNSW and IVFFlat, and
its IVFFlat is not faiss's IVF: different construction, different
parameter names, different behaviour. So without the engine half of this
task, a user simulates `ivf_pq`, learns it costs 3% of recall for a fifth
of the memory on their corpus, takes that to `verify`, and finds out only
afterwards that neither engine they are considering can build it. The
simulation answered a question about the algorithm class; the deployment
question is about what their engine implements, and the tool should say
so before the run rather than after.

The rules for that already exist and need no invention. The
same-configuration rule already refuses to let a measurement settle a
constraint for an option the engine was not built with, so an `ivf_pq`
row verified on Qdrant is already impossible. What is missing is that the
refusal should be **early, named, and distinguishable from an absence**.

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

6. **Each adapter declares its index families**, in the same shape as the
   parameter tables: which families it can build, and for each, the
   engine's own parameter names beside the family's declared ones. An
   adapter that does not declare them cannot be used to verify an
   indexed configuration — the conformance suite enforces the
   declaration, as it enforces every other protocol requirement.

   Do not guess what an engine supports. Resolve it live against the
   pinned versions, and where the mapping from a family's parameter to an
   engine's is not exact, record it as approximate with what differs —
   pgvector's IVFFlat is not faiss's IVF and the declaration must say so
   rather than implying a correspondence.

   This does not add engine-specific index families to `simulate`. If an
   engine builds something faiss cannot, that is a gap in what the
   simulator can predict and it is named as one — not papered over by
   simulating something adjacent and calling it the same.

7. **`verify` refuses before it creates anything.** A configuration whose
   index family the engine cannot build is refused at plan time, naming
   the family, the engine, and what the engine does offer. This is the
   022 precondition rule and the money boundary applied together: the
   refusal must come before a pod is created, not after a run has been
   paid for.

8. **The report distinguishes three states, not two.** Today a
   constraint is `meets`, `fails`, or `couldnt_check`. The third now
   carries a reason that separates:
   - **not verified** — this configuration could have been verified and
     was not. Remedy: run it.
   - **not verifiable here** — no engine in this run can build this index
     family. Remedy: name the engines that could, or state that none of
     the adapters can and that this remains a simulation result.
   A reader must be able to tell "nobody ran it" from "it cannot be run
   here", because the actions are different and one of them is *choose a
   different engine*.

   None of this makes a simulation result less valid. An `ivf_pq` row
   measured against exact ground truth is a true statement about that
   algorithm on that corpus, and it stays in the report with its recall
   and its measured memory. What changes is that the report no longer
   implies it is a deployable option without saying where it could be
   deployed.

9. **Say it in the decision log**, in the sentence that already names
   what would settle a couldn't-check. For a not-verifiable-here row,
   what would settle it is not a command — it is a different engine, or
   an adapter that does not exist. The log should say which, and it
   should name the adapter as a contribution unit where that is the
   honest answer.

10. **What the report may not say**, tested as the claim invariant is
    tested: that one algorithm is better than another (they trade
    differently and the trade is the finding); that a memory figure for
    one corpus transfers to another; that a quantisation result at 150k
    holds at 10M. The sample caveat already exists — this adds the
    quantisation caveat beside it, because PQ's error depends on the
    distribution it was trained on.

11. **Published values do not move.** Both fixtures' reference results
    were measured with HNSW at declared parameters. Adding `index` as a
    parameter must not change a single one — prove it by re-running the
    reference configurations and diffing `simulate.json`, and if a label
    changes because `index` now appears in it, 032's canonicalisation rule
    applies: a parameter at its default produces the same label as its
    omission, so `index: hnsw` must be the default and must not re-label.

12. **Docs.** `docs/MODELS.md` gains the four algorithms, what each is
    for, its knobs, its determinism status and its measured cost.
    `docs/CHARTER.md`'s roadmap loses "more engine adapters" as the only
    named index work and gains this. `docs/ADAPTERS.md` gains the coverage
    table: the four families against the adapters, showing which
    combinations are verifiable today. That table is a fact about the
    ecosystem rather than about the corpus, and it belongs where someone
    choosing an engine will meet it.

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
- Every adapter declares its index families, resolved live, with
  approximate mappings marked as approximate and what differs stated.
- A configuration the engine cannot build is refused at plan time, before
  any billable resource exists.
- The report separates *not verified* from *not verifiable here*, and the
  decision log says what would settle each.
- The coverage table is in `docs/ADAPTERS.md`.

## Do not
- Rank the algorithms. Change a published value or tolerance. Let
  `index: hnsw` re-label an existing configuration. Estimate a memory
  figure that can be measured.
- Guess an engine's capabilities from documentation rather than
  resolving them. Map a family onto an engine's nearest equivalent and
  call it the same. Let a not-verifiable-here row read as a run that
  simply has not happened yet.
