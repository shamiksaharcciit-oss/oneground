# Report: 020-simulator-state

## Repo state expected vs found

- **Branch.** As briefed, the second worktree `oneground-v2` is on `task-020`, created from `main` at `383c7a1`, with a clean tree. The main checkout was not edited, nor were `main`, the tag or `site/teaser/`.
- **The brief is not in the worktree** and is committed on no branch. `tasks/020-simulator-state.md` exists only as an untracked file in the main checkout. I read it there without modifying it. It is not copied into `task-020`, to stay clear of the master stream.
- **Assets.** `~/oneground-assets/arxiv-150k/` and `~/oneground-assets/stackexchange-150k/` were present.
- **The answer key.** The teaser's published values were read from `site/teaser/data/values.json` and `queries.json` and copied into `runs/020-teaser-targets.json`. That copy is read only by the step 4 comparison, never by the renderer.

## What was done

**Step 1: the state.**
- [`oneground/models/state.py`](../oneground/models/state.py) defines the format.
  - It holds `PartitionState`, `AssignmentState`, `RouteState`, `CandidateState` and `LoadState` inside a versioned `ModelState` (`STATE_VERSION = 1`).
  - Every field is a measurement or a declared parameter.
- Assignment and candidates are stored as columns: one row per vector, and a flat, offset-indexed candidate table.
- The encoding:
  - Each state is an uncompressed zip with `header.json` and one `.npy` per column.
  - Files are written deterministically: sorted entries and fixed timestamps.
  - The header documents every column's dtype, shape and meaning, the distance convention and the probe-reason codes.
- `contract_violations()` implements the state contract.

**Step 2: emitting it.**
- `oneground simulate <req> --emit-state` is off by default.
- It writes `state/<family>__<sha8(label)>.state.npz` for each configuration, plus `state/state_info.json` (declared) and `state/MANIFEST.sha256`.
- The top-level manifest is unchanged.
- Each state is written through a `state_sink` in `measure_config`. The sink runs after the row is complete and before the index is released, so it cannot reach a measured value.
- Each state is checked against the contract as it is written. A violation is recorded in `state_info.json`, and the command then fails.

**Step 3: every family implements `state()`.**
- The method is in all three `model.py` files and in the protocol in `base.py`. `semantic_sharded` and `hash_sharded` share `state.collect_candidates`.
- None of them adds a new measurement:
  - `semantic_sharded` recomputes the closure with build's own call under the same thread setting, and refuses to continue if the copy counts differ from build's.
  - Routes come from `_probed`.
  - Candidates repeat search's per-shard calls.
- The conformance suite gains five state tests, run for all three families:
  - the contract holds against each family's own footprint
  - merging a state's candidates reproduces `search()` exactly
  - `true_ids` is the exact top-k, and `true_rank` agrees with it
  - the encoding round-trips and is byte-deterministic
  - each of the four rules, broken on purpose, is caught and named
- `test_simulate.py` gains an end-to-end `--emit-state` test.

**Step 4: acceptance.**
- [`corpora/render_from_state.py`](../corpora/render_from_state.py) renders the ground and a query's trace from a `state/` directory.
  - It imports `state.py` by file path.
  - It loads no model code, vectors, `base.bin`, export script, parquet or ground-truth file.
  - If a figure cannot be derived from the state, it reports `couldnt_check`, names the missing field and exits 1. It never fills a gap.
- `tasks/scratch/020-acceptance.py` compares the rendering with the answer key.

**The state was missing something, and the render found it: `CandidateState.true_ids`.**
- As briefed, candidates carried "whether it is in the true top-k". That names a true neighbour only if a probed shard *returned* it.
- A neighbour the route never reached had no id anywhere in the state. So its home region could not be looked up, and neither "how many true neighbours lie outside the routed region" nor "which ones the route missed" could be answered.
- I found the gap first on a synthetic harness: 58 of 60 queries were answerable, and all 58 matched an independent raw-vector count.
- The fix adds each query's exact top-`true_k` ids, int64 (Q, true_k). The renderer still reports how many queries the candidates alone could have answered, so the gap is re-measured on every run.
- At scale it affects 30% of arXiv queries (Measurements).

**Step 5: live runs.** One sequential script, `tasks/scratch/020-emit-runs.sh`:
- arXiv 150k: the before/after proof, render and acceptance.
- StackExchange sample: the before/after proof.
- The whole path (characterize, then `simulate --emit-state`, then render) on a 20k × 768 synthetic corpus built with the CI recipe (`tasks/scratch/020-make-synth20k.py`), and on the StackExchange sample in a fresh workdir.

**Step 6: docs.**
- [`docs/STATE.md`](../docs/STATE.md) covers:
  - what the state is
  - the rule that every lab view renders state and never recomputes
  - the five parts, the contract, emission and the encoding
  - the missing field and its measured size
  - what state deliberately leaves out: vectors, 2-D positions and metadata
  - what is not settled: interactivity, recomputation as ε moves, the browser, and the reserved ambiguity reason

**The before/after method.**
- A literally byte-identical `simulate.json` is impossible, because every row carries `build_seconds` and `query_seconds`, which are wall clock.
- So I ran the unmodified tree twice per fixture (A and B) with scratch requirements pinned to the two reference configurations. The pinning keeps a time budget from changing which rows exist.
- The comparison (`tasks/scratch/020-diff-simulate.py`) checks byte identity first. It then compares field by field and labels every difference as either one of those two timing fields or a measured value.
- Every run logged its package path and `git diff --stat` beforehand.

## Measurements

**Step 4: the teaser's figures, rendered from the arXiv 150k state alone.** Configuration: `semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2]`.

| figure | rendered from state | published | teaser export | rule | result |
|---|---|---|---|---|---|
| boundary crispness | 0.03624667 | 0.036 | 0.0362467 | ± 0.02 (published tolerance) | PASS |
| storage amplification | 3.71516× | 3.715× | 3.71516 | ± 0.01 (published tolerance) | PASS |
| copies = 1 | 3.6 % (5,437) | 3.6 % | 5,437 | published precision; count exact | PASS |
| copies = 2 | 5.6 % (8,363) | 5.6 % | 8,363 | published precision; count exact | PASS |
| copies = 3 | 6.5 % (9,689) | 6.5 % | 9,689 | published precision; count exact | PASS |
| copies = 4 | 84.3 % (126,511) | 84.3 % | 126,511 | published precision; count exact | PASS |
| vectors copied | 144,563 | — | 144,563 | exact | PASS |
| p99 copies | 4 | 4 | 4 | exact | PASS |
| query 15 ("Democracy from topology"): routed region | 131 | 131 | — | exact | PASS |
| query 15: true neighbours outside the routed region | 10 | 10 | — | exact | PASS |
| routed region, all 2,000 queries | 2,000 agree | 2,000 | — | every query exact | PASS |
| outside count, all 2,000 queries | 2,000 agree | 2,000 | — | every query exact | PASS |
| outside-count distribution | identical | 222/196/194/196/185/218/200/190/159/149/91 | — | exact | PASS |
| storage = `simulate.json` row | 3.71516 | 3.71516 | — | exact at 6 decimals | PASS |
| vectors held = `stored_vectors` | 557,274 | 557,274 | — | exact | PASS |

The full table has 20 rows (each copies bucket is compared as a percentage and as a count): **20 of 20 pass**. The spec publishes no tolerance for the histogram, so it was compared at its published precision, and I invented none.

**The missing field, at scale.** Queries whose outside count the state can answer:

| corpus | from candidates alone (as first specified) | with `true_ids` |
|---|---|---|
| synthetic harness, 1,200 × 32 | 58 of 60 | 60 of 60 |
| arXiv 150k | **1,391 of 2,000** | 2,000 of 2,000 |
| StackExchange 20k sample | **628 of 2,000** | 2,000 of 2,000 |
| synthetic 20k × 768 | 1,946 of 2,000 | 2,000 of 2,000 |

**Query 15's trace, from state.**
- Routed to region 131; probed 131, then 215.
- All 10 true neighbours have their home outside region 131.
- 4 of the 10 were returned by no probed shard, so the route missed them. The other 6 came back through the second probe or through copies.

**Before/after: `simulate.json` with timing fields masked.**

| fixture | compared | byte-identical | identical, timings masked | measured differences |
|---|---|---|---|---|
| arXiv 150k | unmodified A vs unmodified B | no | yes | 0 |
| arXiv 150k | unmodified A vs after, `--emit-state` | no | yes | 0 |
| arXiv 150k | unmodified B vs after, `--emit-state` | no | yes | 0 |
| StackExchange 20k | unmodified A vs unmodified B | no | yes | 0 |
| StackExchange 20k | unmodified A vs after, `--emit-state` | no | yes | 0 |
| StackExchange 20k | unmodified B vs after, `--emit-state` | no | yes | 0 |

In every comparison, the only fields that differ are `build_seconds` and `query_seconds`, in both rows.

**State sizes** (bytes, uncompressed).

| corpus | `single_node_hnsw` | `semantic_sharded` | `hash_sharded` | total `state/` |
|---|---|---|---|---|
| arXiv 150k × 768 | 7,385,762 | 15,625,035 | not in the reference configurations | 23.0 MB |
| StackExchange 20k × 768 | 5,695,757 | 10,798,405 | — | 16.5 MB |
| synthetic 20k × 768 | 5,695,757 | 10,744,730 | 13,315,902 | 29.8 MB |

- **Nothing reaches the 50 MB threshold.** The largest file is 15.6 MB, so no columnar or sampled form is proposed.
- **What the size scales with.** Candidate columns scale with queries × probes × per-shard depth (2,000 × 2 × 100 for `semantic_sharded`), not with the corpus. Per-vector columns cost about 13 B a vector at `max_assign = 4`.
- **`hash_sharded` at 150k was not measured.** From those column shapes it would be roughly 15 MB. That is an estimate.

**Wall clock** (seconds; this laptop, one run each).

| path | characterize | `simulate --emit-state` | of which, writing state | render | whole path |
|---|---|---|---|---|---|
| arXiv 150k, 2 reference configurations | 144 (unmodified baseline) | 1,154.3 | 78.8 (semantic 76.4, single 2.4) | 1.1 | 1,299 |
| StackExchange 20k, reference workdir | — | 86.1 | 5.2 | — | — |
| **synthetic 20k × 768, 3 families** | 22.3 | 74.9 | 8.3 | 0.7 | **97.9** |
| **StackExchange 20k, fresh workdir** | 28.7 | 98.9 | 7.7 | 0.9 | **128.5** |

- **The arXiv characterize time** comes from the unmodified-tree baseline log. `characterize` was not changed by this task and was not re-run on arXiv, since its workdir held the before/after proof.
- **Writing state at 150k** is dominated by `semantic_sharded` repeating 4,000 per-shard searches one query at a time.

## Verification

- **Conformance suite:** 21 of 21, including the 5 new state tests, each run for all 3 families. Passed both under `pytest` and via the file's `_main`.
- **`oneground/simulate/test_simulate.py`:** 14 of 14, including the new `--emit-state` test. That test covers three families and checks four things: no `state/` without the flag, `simulate.json` equal with timings masked, a state per row that meets the contract, and a `state/` manifest that verifies.
- **Other suites touching the changed code:** `oneground/test_cli.py` 8 of 8, `oneground/verify/test_verify.py` 47 of 47, `oneground/test_packaging.py` 13 of 13.
- **Full suite** (`pytest oneground corpora`, from the worktree): **784 passed, 3 skipped, 0 failed**, in 272.7 s. The 3 skips all sit behind the same environment gate: this fresh worktree has no local `runs/arxiv-150k-via-characterize` workdir from a real verify or report session. They are `oneground/verify/test_matched.py:1182`, `oneground/report/test_claims.py:443` and `oneground/report/test_end_to_end.py:349`, each named by re-running with `-rs`. None is in code this task changed.
- **The format's self-test** (`tasks/scratch/020-state-selftest.py`): 19 of 19 checks. It covers the contract, dedupe, `true_rank`, deterministic bytes, column round-trips, refusal of an unknown version, each deliberate break being named, and the fan-out exemption.
- **Package guard.** Every run imported the worktree's package, checked by path from inside the module actually executed. Runs used `python -m oneground.cli` from the worktree root, as the baselines did.
- **Emitted states:** every one in steps 4 and 5 met the contract as written (`state_info.json`: `"contract": "holds"`), across 9 configurations.
- **The render is independent.** It reproduced the figures with no access to vectors, ground truth, parquet or model code. The acceptance script compares the render's JSON with the answer key, and nothing else.

## Observed, not done

- **Byte-identity is unreachable while timings live in `simulate.json`.** Two runs of unmodified code already differ in bytes. If literal byte-identity matters for future proofs, moving `build_seconds`/`query_seconds` to `simulate_info.json` would make it achievable. That would change a published receipt's shape, so I didn't do it.
- **Timings here are noisy enough not to mean much.**
  - `semantic_sharded` `query_seconds` on arXiv was 55.4, 76.9 and 111.2 s across three runs of identical measured code.
  - `single_node_hnsw` was 11.1, 1.3 and 1.0 s.
  - None of this is attributable to `--emit-state`, which runs after both timings are taken.
- **`_centroid_cache` runs k-means outside `single_threaded_faiss`.** `semantic_sharded.build`'s own docstring says OpenMP k-means is not bit-reproducible. It did not show here: three arXiv runs gave identical copy counts, storage and recall, matching the teaser's export exactly. I did not change it.
- **The editable install makes the entry point matter.** The venv's `oneground` console script, or an import from outside the worktree root, resolves the package to the main checkout. Anyone working in a second worktree needs `python -m oneground.cli` from its root, or they will be measuring the wrong tree.
- **Search maps faiss padding through `ids_of`.** A padded slot (-1) becomes the shard's last id instead of being dropped. Every run here mapped 0 such slots, since depth ≤ shard size. The state repeats search faithfully and counts the slots in its notes. Fixing it would change `search()`, so I didn't.
- **The teaser's "outside the routed region" is a one-region geometry.** It ignores probe 2 and copies. For query 15 all 10 neighbours are "outside", but only 4 were missed. The state carries both, so the lab can show both without recomputing.
- **The UMAP positions the teaser uses are not state**, and are not rendered. The spec declares that projection illustrative, so nothing here claims a pixel match.
- **`ROUTE_AMBIGUITY` (code 3) is reserved.** No family probes by the ambiguity rule, so it is never written.
- **The comparison scripts are not committed.** The acceptance comparison, the diff and the runner live in `tasks/scratch/`, which is gitignored per the project convention.

## Repo now contains

One commit on `task-020`, not pushed:

- **New:**
  - `oneground/models/state.py`: the format, the contract, the encoding.
  - `corpora/render_from_state.py`: the state-only renderer.
  - `docs/STATE.md`
  - this report
- **Changed:**
  - `oneground/models/base.py`: `state` added to the protocol.
  - `oneground/models/semantic_sharded/model.py`, `hash_sharded/model.py`, `single_node_hnsw/model.py`: `state()`.
  - `oneground/simulate/__init__.py`: `--emit-state`, the state sink, `state_info.json`, the state manifest.
  - `oneground/cli.py`: the flag.
  - `oneground/models/test_conformance.py`: 5 state tests.
  - `oneground/simulate/test_simulate.py`: the emit-state test.

No measured value, tolerance, seed, gate or fixture file was changed. Nothing under `site/teaser/` was touched.

## Blocked on developer

Nothing is blocking. Two decisions are yours:

- **Whether the brief should be committed.** `tasks/020-simulator-state.md` exists only untracked in the main checkout, and I left it there.
- **Whether wall-clock timings should move out of `simulate.json`**, so a future "byte-identical" acceptance can be literal rather than timings-masked.
