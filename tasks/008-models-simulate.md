# Task 008 — Models as plugins, and `oneground simulate`

## Expected repo state
Task 007 committed; tree clean; `oneground/README.md` no longer claims
simulate/verify/decide in the present tense. Report the current contents
of `oneground/fixture/build.py`'s reference-results section — the two
models to extract live there.

## Why
The simulator is the core the advisor, the lab, and the proposal loop all
draw from. This task gives it a stable shape: one `Model` interface, three
families behind it, one command that runs a configuration sweep on a
characterized sample and emits the trade-off table — with the routing
ceiling per configuration so loss is always decomposed.

## Do
1. **`oneground/models/base.py`** — the interface every family implements:
       class Model(Protocol):
           name: str
           def configs(self, space: ConfigSpace) -> Iterable[Config]      # what to sweep
           def build(self, vectors, config, seed) -> BuiltIndex              # deterministic
           def search(self, built, queries, k, config) -> Candidates         # ids + scores
           def ceiling(self, built, queries, k) -> Ids                       # exact over reachable set
           def footprint(self, built) -> Footprint                           # stored copies, est. memory bytes, fan-out per query
   `Candidates`, `Footprint`, `Config` are dataclasses in `base.py`.
   `ceiling` is mandatory, not optional: a model that cannot state what
   its routing makes reachable cannot be in the table.
2. **Three families**, each in `oneground/models/<name>/model.py` with a
   `MODEL.md` (definition, parameters, what the family represents, known
   limits) and tests:
   - `single_node_hnsw` — extracted from the builder unchanged; ceiling is
     the full set (routing loss = 0 by definition). Sweep: M, efSearch.
   - `semantic_sharded` — extracted unchanged (k-means centroids, closure
     ε, MAX_ASSIGN, probe P, per-shard HNSW, score-merge + ID dedupe).
     Sweep: centroids, ε, P, efSearch. Ceiling as already implemented.
   - `hash_sharded` — new: vectors assigned to N shards by a seeded hash
     of the vector id; per-shard HNSW; every query fans out to all N
     shards; merge as above. Ceiling is the full set. Its point is
     fan-out cost at equal recall — `footprint.fanout = N`. Sweep: N,
     M, efSearch.
3. **`oneground/simulate/`** — `oneground simulate <requirements.yaml>`:
   - loads the characterize workdir (must exist; else refuse naming the
     command to run first), the sample vectors/queries/ground truth.
   - reads `simulate.families`, `simulate.node_counts`, `simulate.budget`
     from the requirements file; each family's `configs()` generates the
     sweep; `max_configs` truncates it with a recorded rule (report which
     configs were dropped), `max_minutes` stops the sweep and marks the
     remaining as `couldnt_check: budget`.
   - per config: recall@1/@10/@100, routing ceiling@10, 1/Ratio@10
     (mean over queries of the ratio of the k-th true distance to the k-th
     returned distance — define it precisely in code comments and MODEL.md),
     storage amplification, est. memory, fan-out, build seconds, query
     seconds — all measured, seeds from `run.seed`.
   - writes `simulate.json` (rows, measurement only), `simulate_info.json`
     (declared: versions, device, timings, dropped configs), MANIFEST
     lines; and a plain-text table to stdout sorted by family then
     recall@10.
   - no verdicts, no recommendation, no "meets"/"fails" — that is the
     report's job (task 010). This command measures.
4. **Fixture builder** calls `oneground.models` for its two reference
   results. Regression proof as in 007: smoke rebuild byte-identical on
   all six receipts.
5. **Run it on arXiv-150k** (release asset path from 007) with the
   spec's two reference configurations included in the sweep, plus
   `hash_sharded N=3` and a small grid (ε ∈ {0, 0.1, 0.2}, P ∈ {1, 2},
   centroids 256). The two reference rows must match the fixture's
   published `reference_results` within tolerance. Report the full
   table; keep runtime reasonable (this is 150k vectors on the laptop —
   if the semantic-sharded sweep exceeds ~30 minutes, reduce the grid and
   say so).
6. **`docs/MODELS.md`**: the interface, how to add a family (the
   contribution unit), and the ceiling requirement stated as a rule.
7. Tests: interface conformance test that any registered model must pass
   (build → search → ceiling ≥ search recall on synthetic data; footprint
   fields present); per-family tests; simulate end-to-end on 2k synthetic.

## Acceptance
- Three families registered; conformance test passes for all.
- Smoke rebuild byte-identical through the extracted models.
- arXiv reference rows within tolerance of published values.
- `oneground simulate` output contains no verdict language.
- Tests pass; MODELS.md exists.

## Do not
- Change any measurement in the two extracted models. Add verdict logic.
- Touch arxiv-150k artifacts or the spec.
