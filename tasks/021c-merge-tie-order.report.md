# Report: 021c-merge-tie-order

## Repo state expected vs found

- **Branch:** as expected. The worktree `oneground-v2` is on `task-020` at `7394617` (task 021b, accepted), with a clean tree. The main checkout and `main` were not touched.
- **The brief:** there is no file. It is the developer's message: turn the tie-order caveat into a test, fix the sort stability if the two paths disagree, add the sufficiency rule to `docs/STATE.md`, then stand by.
- **The finding was confirmed.** `base.merge_candidates` was the only unstable sort feeding a receipt. It used `np.argsort(-scores)`, numpy's default, which is not stable. `state.dedupe_mask` and the query-trace view's recall already sorted stably. The fixture builder has no merge of its own: `oneground/fixture/reference.py` goes through the families' `search`.

## What was done

**The test (`oneground/lab/test_lab.py`).**
- **`_tied` builds a synthetic state whose candidates tie everywhere.** Each of 400 vectors has one of three scores, fixed per vector. Each query takes 150 candidates from each of two shards, 30 of the second shard's being copies of the first's. A copy carries the same score from both shards, as a real copy does.
- **`_merge_spec` writes out the rule:** the first occurrence of each id, best score first, and equal scores in the order the shards' results were concatenated. It doesn't depend on any sort's internals.
- **`test_tied_scores_merge_one_way_in_simulate_and_in_the_view_synthetic`** checks every query at k = 1, 10, 50 and 100. `merge_candidates`, called per shard as a family calls it, must equal the spec, and so must the view's `returned_top_k`. It also asserts that some k boundary actually falls inside a run of tied scores, so the test can't pass vacuously.

**The two paths disagreed.**
- **Against the unchanged code, the test failed** at the first query and the first k. For query 0 at k = 1, `merge_candidates` returned id 182 where the rule picks id 128: two candidates tied on the best score, and the unstable sort put the later one first.
- **The view already followed the rule.**

**The fix: `merge_candidates` now sorts stably** (`np.argsort(-csc, kind="stable")`). Its docstring states the tie rule and why it is needed: numpy's default sort leaves tied candidates in an order that can differ between numpy builds and CPUs, so a receipt counted from it could change with no input changing. Exact ties are real: copies of one vector score identically, and so do duplicate vectors under different ids. Both paths now follow one rule, and the test passes.

**Did the fix change anything measured?** A stable merge can change which of two tied candidates wins, so this was checked before landing.
- **Offline, on every emitted state** (`tasks/scratch/021c-ties.py`). Every query of every state whose family merges shard results was re-merged three ways at k = 100: the pre-021c merge, the fixed merge, and the written rule. The candidates are the ones the state records, in the family's concatenation order.
- **End to end** (`tasks/scratch/021c-runs.sh`). Both reference fixtures were simulated again with the stable merge. `simulate.json` had to be byte-identical to task 021's, and every state digest unchanged.

**`docs/STATE.md`.** The rule section now carries the line, as a callout: **"The only test of whether the state is sufficient is a renderer that needs the column."** It explains why: the state contract and the conformance suite check that a state is internally consistent, and both passed the two states that turned out not to hold enough. A change to the state lands with the rendering that needs it, and a column no renderer reads has not been tested for anything.

## Measurements

**Offline: the pre-021c merge against the fixed merge, per state, at k = 100.**

| state | queries | top-100 *order* differs | recall@1/10/100 set or rank-10 score changes | fixed merge departs from the rule |
|---|---|---|---|---|
| StackExchange 20k, ε 0.2 (reference) | 2,000 | 6 | **0** | 0 |
| StackExchange 20k, ε 0.0 | 2,000 | 4 | **0** | 0 |
| StackExchange 20k, ε 0.1 | 2,000 | 5 | **0** | 0 |
| StackExchange 20k, ε 0.3 | 2,000 | 5 | **0** | 0 |
| StackExchange 20k, ε 0.2 (live-path run) | 2,000 | 6 | **0** | 0 |
| arXiv 150k, ε 0.2 (reference) | 2,000 | 11 | **0** | 0 |
| arXiv 150k, ε 0.1 | 2,000 | 13 | **0** | 0 |
| arXiv 150k, ε 0.3 | 2,000 | 9 | **0** | 0 |
| synthetic 20k, semantic_sharded | 2,000 | 26 | **0** | 0 |
| synthetic 20k, hash_sharded | 2,000 | 17 | **0** | 0 |
| **total** | **20,000** | **102** | **0** | **0** |

- **The unstable sort already reordered real receipts' inputs.** In 102 real queries, tied candidates inside the top 100 came out in a different order under the old merge. That is the latent nondeterminism, present in real data, not only in the synthetic test.
- **None of it reached a measured value.** In no query did a tie between distinct ids fall on the k = 1, 10 or 100 boundary, so no recall set and no rank-10 score moves. Every published value is computed from those.
- **A different corpus could have had such a tie,** and its recall would have depended on the sort's internals. The test now fails if that can happen.

**End to end: byte identity after the fix.**

Both reference fixtures were simulated again with the stable merge (`tasks/scratch/021c-runs.sh`, log `runs/021c-runs.log`), from the worktree root with `python -m oneground.cli`:

| fixture | `simulate.json` vs task 021's run | sha256 | every `.state.npz` digest vs task 021 |
|---|---|---|---|
| StackExchange 20k | **byte-identical** | `71100fcc…7dd898` | identical |
| arXiv 150k | **byte-identical** | `d44d41c9…652d87` | identical |

**0 differences.** These are the same `simulate.json` bytes tasks 020b and 021 recorded. The stable merge changed nothing `simulate` writes on either published fixture. The state files are unchanged too, as expected: they record each shard's raw candidates, not the merge.

## Verification

- **`oneground/lab/test_lab.py`: 20 of 20,** including the new tie test. It failed before the fix and passes after.
- **`oneground/models/test_conformance.py`: 23 of 23.** This includes merging each family's state candidates, which reproduces `search()` exactly: both now use the stable merge.
- **`oneground/simulate/test_simulate.py`: 14 of 14.**
- **The offline check:** 0 measured changes and 0 departures from the rule, across 20,000 queries (table above).
- **The end-to-end runs:** see Measurements.
- **Full suite** (`pytest oneground corpora`, from the worktree root, after both simulate runs): **816 passed, 3 skipped, 0 failed**, in 570.0 s. That is one more than task 021b's 815: the tie test. The 3 skips are the same environment gates as before: no local `runs/arxiv-150k-via-characterize` verify or report workdir, at `oneground/report/test_claims.py:443`, `oneground/report/test_end_to_end.py:348` and `oneground/verify/test_matched.py:1182`.
- **Identifier scan:** run over every changed file before commit, and again against the committed tree.

## Observed, not done

- **Three unstable `argsort` calls remain outside the receipt path.** I didn't change them.
  - **`oneground/adapters/stub.py:141`** orders the test stub adapter's results by similarity. It is a test double, not an engine a published measurement comes from.
  - **`oneground/adapters/conformance.py:217`** sorts ids that are unique, so ties cannot occur.
  - **`corpora/render_ground.py:245`** picks the 8 largest centroids for a display. A tie there could reorder two labels in a picture, and no number.
- **The ordering change is visible outside `simulate.json`.** 102 real queries' merged top-100 ids now come out in a different order among tied candidates, visible to anything that reads a family's `search()` output in order. Nothing stored does: fixture reference results and calibration count recall as sets.

## Repo now contains

On `task-020`, not pushed, one new commit after `7394617`:
- `oneground/models/base.py`: `merge_candidates` sorts stably, with the rule in its docstring.
- `oneground/lab/test_lab.py`: `_tied`, `_merge_spec` and the tie test (20 tests).
- `docs/STATE.md`: the sufficiency line.
- This report.

No measured value, tolerance, seed, gate, fixture file or published figure was changed. Recall@1/10/100 and inv_ratio@10 are unchanged on every emitted state, and `simulate.json` is unchanged on both fixtures.

## Blocked on developer

Nothing. Standing by:
- `task-020` holds until the 23 September release.
- On release day, before anything else, `task-020` is rebased onto `main`. It will be four commits deep: 020, 021, 021b, 021c.
- The next brief is the ground's live recount.
