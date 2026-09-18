# Report: 021-lab-rendering-contract

## Repo state expected vs found

- **Branch:** as expected. The worktree `oneground-v2` is on `task-020` at `4122ced` (tasks 020 and 020b squashed, accepted), with a clean tree. The main checkout and `main` were not touched.
- **The brief:** there is no file. It is the developer's message: three items, commit on `task-020`, no pod needed.
- **The state:** as expected, apart from what item 3 found missing (below).

## What was done

**(1) The renderer interface: `oneground/lab/`.**
- **The contract (`contract.py`).** A view takes state and returns a drawing, through one entry point, `draw(view, header, columns)`.
- **A view** is a `View` with a `name`, the state columns it `reads`, and `render(state) -> Drawing`.
- **The state a view is handed (`StateColumns`):**
  - it exposes the declared columns and no others, raising `UndeclaredColumn`;
  - it never exposes a vector column (`partition.centroids`), raising `VectorColumn` even if the column is declared;
  - every array it returns is read-only.
- **A `Drawing`** is declarative, not pixels:
  - `marks`: point, region, link or bar layers, each with equal-length data columns and a channel-to-column encoding;
  - `figures`: the numbers it states;
  - `gaps`: what it could not draw, each a `couldnt_check` reason.
  
  `draw` validates the drawing, then stamps on the columns the view actually read, the state's identity, and `on_epsilon`.
- **Tallying versus measuring.** A view may tally state: select, gather by stored id, compare, count, sum, and take fractions or percentiles of stored columns. It may not measure: nothing that needs a vector. Crispness is a tally in this sense: the share of vectors whose stored second centroid distance exceeds 1.20 × the first. The distances were measured by the family; the view only counts them.
- **The guard (`guard.py`)** reads the source of every module in `oneground/lab/views/`, registered or not. It names each line that does one of these:
  - vector arithmetic: `@`, dot/inner/outer/einsum, `linalg`, norms, distances, clustering, projection, faiss index types;
  - an import outside a short allow-list (numpy, stdlib basics, `oneground.lab`), which keeps out faiss, scikit-learn, scipy, torch, the model families and every measuring module;
  - vector data: a vector column or a value named centroids, vectors, queries or embeddings;
  - file I/O;
  - dynamic code.
  
  `test_lab.py::test_every_view_module_passes_the_guard` runs it over the shipped views, so a view that measures fails the build. `render_from_state.py` also refuses to draw (exit 2) while any view module breaks it.
- **The guard's limit.** It checks names and syntax and cannot infer types: `a * b` over two vectors would pass. The runtime refusal of vector columns is therefore the primary guarantee. A view is never handed a vector to multiply.

**(2) `render_from_state.py` became two views over the contract.**
- **The views:** `views/ground.py` (`GroundView`) and `views/query_trace.py` (`QueryTraceView`).
- **The script is now a composer.** It draws the ground once and the query trace for the named query and for every query, and adds nothing of its own. Its JSON keeps task 020's shape (`ground`, `query`, `every_query`) and adds each view's provenance: columns read, and `on_epsilon`.
- **The acceptance test is unchanged.** Task 020's `tasks/scratch/020-acceptance.py` was not edited (sha256 `9fc0a0d9…`), and it passes on the views' output. See Verification.

**(3) When ε moves, what recomputes: measured.**

**What the state was missing.** `copy_set` names a region only inside the closure at the emitted ε (0.2). A recount could lower ε, but it could not raise it: it had the distance to a region a vector would now be copied into, and no idea which region that was.
- **The fix.** `AssignmentState.nearest_region` (N × `max_assign`, int32) now holds the regions `centroid_dist` measures, whether copied or not. The families fill it.
- **The contract.** It checks every copy against it, and a conformance test recounts each family's own ε from it.
- **Versioning.** The column is additive, so `state_version` stays 1. A state without it still reads: the views don't need it, and a recount reports it missing.

**`ON_EPSILON` in `contract.py`** classifies every state column by what a change of ε does to it, and `draw` stamps each drawing with the worst class among the columns it read. The ground is "recount from state"; the query trace is "rebuild", because "missed by the route" reads what shards returned.

| class | columns |
|---|---|
| unchanged | centroids, region ids and home populations, home region, centroid distances, nearest regions, every route column, true neighbours, shard ids, queries served |
| recount from state | copy count, copy set, vectors each shard holds |
| rebuild (a new `simulate` run) | every candidate column, `true_rank`, candidates contributed |

**The recount** (`tasks/scratch/021-epsilon.py`) reproduces semantic_sharded's closure rule byte for byte, from stored float32 distances and nearest regions. It produces copy counts, the histogram, storage amplification, p99, vectors per shard, and the routing ceiling@10: which true neighbours some probed region holds a copy of. It was checked against real runs, not assumed:
- Both reference fixtures were re-emitted with the column, proven additive.
- Semantic states were emitted at ε 0.0, 0.1 and 0.3 (StackExchange 20k) and at ε 0.1 and 0.3 (arXiv 150k), in fresh workdirs.
- A recount from the ε 0.2 state matched every one of them.

**The incremental update.** A pre-sorted index of the ε at which each (vector, slot) pair joins its closure. A move re-tests only the pairs whose threshold lies between the old and new ε, with the exact float32 rule, and touches only their vectors, regions and (query, rank) entries. Every timed move was checked against a full recount at the same ε.

## Measurements

**Is the recount right?** It is exact at every ε measured. "Unchanged" means every column `ON_EPSILON` calls unchanged is identical between the ε 0.2 state and the emitted one.

| fixture | ε | copy count / copy set / vectors per shard | storage, recounted = `simulate.json` | ceiling@10, recounted = `simulate.json` | unchanged columns |
|---|---|---|---|---|---|
| StackExchange 20k | 0.0 | exact | 1.000000 = 1.0 | 0.528150 = 0.52815 | identical |
| StackExchange 20k | 0.1 | exact | 2.871900 = 2.8719 | 0.749900 = 0.7499 | identical |
| StackExchange 20k | 0.3 | exact | 3.994900 = 3.9949 | 0.805150 = 0.80515 | identical |
| arXiv 150k | 0.1 | exact | 2.667153 = 2.667153 | 0.895250 = 0.89525 | identical |
| arXiv 150k | 0.3 | exact | 3.970260 = 3.97026 | 0.935750 = 0.93575 | identical |

The ε 0.3 rows are the recount the state could not do before `nearest_region`.

**How long does it take?** The table gives medians, with p95 in brackets.
- **Machine and protocol:** the developer's laptop with nothing else running; `semantic_sharded` at the reference configuration; 101 ε values for the full recount.
- **Incremental moves:** 200 slider steps (0 → 0.5 → 0 in steps of 0.005) and 200 random jumps in [0, 0.5], seed 21.
- **Checked:** all 800 moves equal a full recount.

| | StackExchange 20k | arXiv 150k |
|---|---|---|
| load the `.state.npz` | 15.0 ms (36.9) | 27.4 ms (48.1) |
| **full recount**: ground figures | 0.82 ms (1.09) | 8.64 ms (10.92) |
| **full recount**: ceiling@10, all 2,000 queries | 0.54 ms (0.89) | 0.94 ms (1.25) |
| **full recount, total** | **1.48 ms (2.03)** | **9.58 ms (11.83)** |
| incremental index, built once | 12.9 ms | 93.2 ms |
| **incremental**, slider step 0.005 | 0.12 ms (0.54); 102 pairs flip | 0.70 ms (5.79); 1,671 pairs flip |
| **incremental**, random jump | 1.40 ms (10.17); 7,485 pairs flip | **28.99 ms (160.7)**; 86,421 pairs flip |
| draw the ground view | 0.6 ms | 4.4 ms |
| draw one query trace | 0.24 ms | 0.66 ms |
| **rebuild one ε**: a `simulate` run's build + query for one semantic config (declared timings, one run each) | 3.1 s (ε 0.0) · 9.7 s (0.1) · 20.7 s (0.3) | 193.6 s (ε 0.1) · 360.3 s (0.2) · 397.8 s (0.3) |

**Sizes** (bytes).

| | StackExchange 20k | arXiv 150k |
|---|---|---|
| semantic state, before → with `nearest_region` | 10,798,405 → 11,118,942 | 15,625,035 → 18,025,573 |
| single-node state, before → with `nearest_region` | 5,695,757 → 5,776,294 | 7,385,762 → 7,986,300 |
| columns the recount reads | 2,256,000 | 6,416,000 |
| incremental index in memory | 2,185,800 | 14,204,944 |
| ground drawing as JSON (one point per vector) | 281,501 | 2,224,477 |

**The answer, from these numbers.**
- **Interactive: everything ε changes that the state can recount.** That covers copy counts and the ground's colours, the histogram, storage, p99, shard sizes and the routing ceiling@10. A full recount plus a ground redraw is about 14 ms at 150k and about 2 ms at 20k: inside a 16 ms frame at both sizes. A frame budget is a reference here, not a gate.
- **No incremental index.** It wins only on small slider steps, 0.7 ms against 9.6 ms at 150k. It loses on jumps (29 ms median, 161 ms p95), because scattering 86k flips through `np.add.at` costs more than recounting 600k comparisons. It also costs 14 MB and 93 ms to build. A full recount per move is simpler and never slower than 12 ms at p95.
- **Render-on-request: everything that depends on what the shards return.** That is recall, index loss, candidates, "missed by the route", and candidates contributed. Changing ε changes shard membership, which changes every HNSW graph. The state cannot know the new candidates; only a `simulate` run can, and it takes 3–21 s at 20k and 3–7 minutes at 150k per ε.
- **What the lab can therefore offer.** An ε control that redraws the ground and the routing ceiling live. Recall and the query trace's misses can be shown only at ε values that were actually simulated, and labelled as such. Interpolating between them would be a view computing a number no run measured.

**One observation on the table.** On arXiv, `cand_shard`, `offsets` and `candidates_contributed` came out identical across ε. Every probed shard holds more than 100 vectors, so each query gets exactly 2 × 100 candidates from the same shards. On StackExchange at ε 0.0 they differ. "Rebuild" means a recount cannot guarantee a column, not that it always changes.

## Verification

- **`oneground/lab/test_lab.py`: 14 of 14.**
  - the guard is clean over every shipped view module, and catches each rule: 18 injected violations, and a new file dropped into `views/`;
  - it leaves docstrings and ordinary tallies alone;
  - vector columns, undeclared columns and writes are refused, and malformed drawings rejected;
  - both views' figures match a hand-countable state;
  - a state without `true_ids` gives a gap, not a guess;
  - every state column is in `ON_EPSILON`;
  - drawing both views in a clean process loads no faiss, scikit-learn, scipy, torch, umap, model family, measures, truth, simulate or characterize module.
- **`oneground/models/test_conformance.py`: 23 of 23.** New: each family's ε recounted from `nearest_region` reproduces its copy sets at ε 0.0, 0.1 and 0.5, and the contract names a missing or wrong `nearest_region`.
- **`oneground/simulate/test_simulate.py`: 14 of 14.**
- **Full suite** (`pytest oneground corpora`, from the worktree root, on an idle CPU after the benchmarks): **810 passed, 3 skipped, 0 failed**, in 454.5 s. That is 16 more than 020b's 794: the 14 lab tests and the 2 new conformance tests. The 3 skips are the same environment gates as before: no local `runs/arxiv-150k-via-characterize` verify or report workdir, at `oneground/report/test_claims.py:443`, `oneground/report/test_end_to_end.py:348` and `oneground/verify/test_matched.py:1182`.
- **The column addition is additive.** `simulate.json` is byte-identical to 020b on both fixtures. Every existing state column is identical, and only `assignment.nearest_region` is added, in all four reference state files (`tasks/scratch/021-additive.py`).
- **Step 4 through the views.** The views' JSON equals task 020's `render.json` in all 24 compared fields, including all 2,000 queries (`tasks/scratch/021-render-equivalence.py`). Task 020's unchanged acceptance script passes 20 of 20. Both checks held on the re-emitted arXiv state and on the saved 020b state, which lacks the new column.
- **The ε recount** is validated at 5 ε values across 2 fixtures (table above), and the incremental update at 800 moves against a full recount.
- **The identifier scan** was run over every new and changed file before tracking, and again after the commit.

## Observed, not done

- **`docs/STATE.md` is now incomplete, and the brief does not name it,** so under the project's rules I didn't edit it. It lists `nearest_region` nowhere. Its "Not settled" section still lists "incremental recomputation as ε moves" as open, and this report answers that. It also doesn't mention the lab contract.
- **The measurement code is in scratch.** The recount, the incremental update, the validation and the benchmark are in `tasks/scratch/021-epsilon.py`, which is gitignored, like task 020's acceptance script. The numbers above are reproducible from it, but not from tracked code. If the lab's ε control is built, the recount belongs in tracked code as a declared state transform, outside `views/`, since a view may not do it.
- **`ON_EPSILON` describes `semantic_sharded`.** `hash_sharded` and `single_node_hnsw` have no ε. Their states carry the column trivially (their one region), and the table's "unchanged" is vacuously true for them.
- **The guard's line between tally and measure is a judgement.** It enforces "no vectors" mechanically. It cannot tell a legitimate tally over stored distances (crispness) from a new measurement built out of stored numbers. That boundary is written into `oneground/lab/__init__.py`, and review holds it.
- **The ground drawing at 150k is 2.2 MB of JSON**, one point per vector. That is a data point for the unsettled browser question, not a decision.
- **Timings are single-laptop numbers.** The rebuild timings are single unrepeated `simulate` runs. The ε 0.2 re-emit on arXiv (360 s) ran while this report's lighter checks were also running.
- **Older states still render.** Earlier state directories (`runs/020-synth20k`, `runs/020-live-*`) lack `nearest_region` and were not re-emitted.

## Repo now contains

On `task-020`, not pushed, one new commit after `4122ced`:
- `oneground/lab/`:
  - `__init__.py`: the contract's rules;
  - `contract.py`: the types, `draw`, `StateColumns`, `ON_EPSILON`;
  - `guard.py`;
  - `test_lab.py`;
  - `views/__init__.py`, `views/ground.py`, `views/query_trace.py`.
- `corpora/render_from_state.py`, now a composer over the views.
- `oneground/models/state.py`: `nearest_region`, and its contract check.
- The three families' `model.py`: fill `nearest_region`.
- `oneground/models/test_conformance.py`: two new tests.
- This report.

No measured value, tolerance, seed, gate, fixture file or published figure was changed.

## Blocked on developer

- **`docs/STATE.md`.** Whether to update it for `nearest_region`, the lab contract and the ε answer. It needs the brief to name the file and the change.
- **Recall for other ε.** Whether the lab should offer it as a declared, precomputed ε grid (a `simulate` run per ε, minutes each at 150k), as render-on-request, or not at all. The measurement says it cannot be live.
