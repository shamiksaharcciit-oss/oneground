# Report: 008-models-simulate

## Repo state expected vs found

| Expected | Found |
|---|---|
| task 007 committed | yes — `969fbf5 task 007: oneground package, characterize CLI, product path == fixture path` |
| tree clean | yes, apart from the untracked brief |
| `oneground/README.md` no longer claims simulate/verify/decide in the present tense | **no — it still does** |
| the two models to extract live in `oneground/fixture/build.py`'s reference-results section | **no — they live in `oneground/fixture/reference.py`** |

### The README mismatch

`oneground/README.md` is unchanged since before task 007 and still reads:

> "It characterizes a corpus of embeddings, **simulates** retrieval
> architectures on it against exact k-NN ground truth, **verifies** finalists
> against real engines, and **produces a decision** with its evidence
> attached."

Task 007's report raised this as its first "Observed, not done" and its first
"Blocked on developer" item; it was not acted on. I did not stop the task over
it (CLAUDE.md rule 1) because it is one paragraph of documentation that no
deliverable here depends on, and stopping would have traded the whole task for
a sentence. I also did not fix it: rule 2, and it is not in the Do list.

Worth noting that this task changes its status. After 008 the package really
does simulate, so one of the three false claims becomes true; "verifies
finalists against real engines" and "produces a decision" remain false.

### Where the models actually were

The brief says the two models live in `build.py`'s reference-results section.
Task 007 moved them to **`oneground/fixture/reference.py`** (96 lines,
`ref_single_node` and `ref_semantic_sharded`); `build.py` only calls them, at
lines 176–183. That is where the extraction was done from.

For the record, the section as found:

    oneground/fixture/reference.py
      ref_single_node(base, queries, gt10, p)          -> float
          IndexHNSWFlat, METRIC_INNER_PRODUCT, efConstruction from params,
          efSearch set after add, search k=10, recall against gt10.

      ref_semantic_sharded(base, queries, gt10, cents, p, max_assign=4) -> dict
          closure (within = d <= d[:,[0]]*(1+eps); within[:,0] = True),
          one IndexHNSWFlat per region at efConstruction=200,
          probe P regions, min(30, ntotal) candidates per shard,
          score-merge with id dedupe, top 10;
          ceiling = exact over the union of probed shards;
          returns recall_at_10, routing_ceiling, storage_amplification,
          p50/p95/p99 copies.

`models/` at the repo root holds only a `README.md`. The brief places the
families at `oneground/models/`, inside the package, which is where they went;
the root directory is now a README describing something that lives elsewhere.

## What was done

All seven steps.

### 1. `oneground/models/base.py`

`Model` as a Protocol with the five methods, and `Config`, `ConfigSpace`,
`Candidates`, `Footprint`, `BuiltIndex` as dataclasses. Shared helpers:
`merge_candidates` (the score-merge with id dedupe that two families share),
`exact_over` (the primitive every `ceiling` is built from), and
`estimate_memory_bytes`.

`build` takes an optional `context`. That is a superset of the brief's
signature and it exists for one reason: the fixture builder passes the k-means
centroids `characterize()` already computed rather than making the model
recompute a 256-way clustering over 150,000 vectors. A model must return the
same result with or without it — it is a speed and identity concession, not a
behaviour switch, and `MODELS.md` says so as a rule.

### 2. Three families

| family | routes on | ceiling | replicates |
|---|---|---|---|
| `single_node_hnsw` | nothing | full corpus, routing loss 0 by definition | no |
| `semantic_sharded` | k-means regions | union of probed shards | yes, ε closure |
| `hash_sharded` | `blake2b(id, key=seed) mod N` | full corpus, routing loss 0 by definition | no |

Each has a `model.py`, a `MODEL.md` with the four sections (what it
represents, definition, parameters, known limits), and test coverage.

`hash_sharded` uses `blake2b` rather than Python's `hash()` deliberately:
`hash()` is randomized per process unless `PYTHONHASHSEED` is set, which would
make a family documented as deterministic silently irreproducible between
runs.

### 3. `oneground/simulate/`

`oneground simulate <requirements.yaml>`. Refuses without a characterization,
naming the command to run first. Reads `simulate.families`, `node_counts`,
`grid`, `include` and `budget`. Per config it measures recall@1/@10/@100,
ceiling@10, routing/index loss, 1/Ratio@10, storage amplification, estimated
memory, fan-out, build seconds and query seconds. Writes `simulate.json`
(receipt), `simulate_info.json` (declared) and rewrites `MANIFEST.sha256` to
cover both commands' outputs.

Budgets drop loudly: every unmeasured config is listed with
`couldnt_check: budget` and the rule that dropped it.

### 4. Fixture builder calls the models

`reference.py` now builds a `Config`, calls the registered family, and derives
the published fields from `search`/`ceiling`/`footprint`. Regression proof
below.

### 5. Run on arXiv-150k

Eight configurations, 45.1 minutes. Full table below.

### 6. `docs/MODELS.md`

The interface, the ceiling rule stated as a rule, and how to add a family.

### 7. Tests

26 new (13 conformance, 13 simulate end-to-end + metric units). 125 pass.

### Deviations

- **`build` gained an optional `context` parameter**, above.
- **Reference results were extracted from `reference.py`**, not `build.py`.
- Two defects I introduced and fixed before shipping, both in Measurements.

## Measurements

### The regression gate: smoke rebuild through the extracted models

Rebuilt with `corpora/build_fixture.py --spec fixtures/arxiv-smoke.fixture.yaml
--source tasks/scratch/001-synthetic-source.json --skip-projection` into a
scratch directory.

| artifact | committed | rebuilt | |
|---|---|---|---|
| `sample.jsonl.zst` | `b6383e22…` | `b6383e22…` | **identical** |
| `vectors.npy` | `d9f44ded…` | `d9f44ded…` | **identical** |
| `queries.npy` | `2359ce71…` | `2359ce71…` | **identical** |
| `query_ids.json` | `0081604b…` | `0081604b…` | **identical** |
| `ground_truth.npy` | `13919bb5…` | `13919bb5…` | **identical** |
| `characterization.json` | `07b576e2…` | `07b576e2…` | **identical** |

**All six byte-identical.** The extraction changed no measurement.

A cheaper check ran first, before committing to a 10-minute rebuild:
`tasks/scratch/008-ref-equivalence.py` recomputes both reference rows from the
committed smoke artifacts and diffs them against the committed
`characterization.json` at full precision. All **7 fields identical to
0.000000000**.

### The arXiv-150k sweep — 8 configurations, 45.1 min

150,000 vectors, 2,000 queries, seed 20260908, ground truth k=100. Sorted by
family then recall@10, as emitted.

| configuration | r@1 | r@10 | r@100 | ceil | route | index | 1/rat | ampl | fan | mem MB | build s | query s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `hash_sharded` N=3 | 0.999 | **0.998** | 0.994 | 1.000 | 0.000 | 0.002 | 1.000 | 1.00 | 3 | 499 | 98.7 | 7.0 |
| `semantic_sharded` ε=0.2 P=2 | 0.951 | **0.932** | 0.421 | 0.932 | 0.068 | 0.000 | 0.998 | 3.72 | 2 | 1855 | 315.5 | 386.8 |
| `semantic_sharded` ε=0.1 P=2 | 0.922 | 0.895 | 0.453 | 0.895 | 0.105 | 0.000 | 0.996 | 2.67 | 2 | 1331 | 292.5 | 36.1 |
| `semantic_sharded` ε=0.2 P=1 | 0.875 | 0.838 | 0.298 | 0.838 | 0.162 | 0.000 | 0.994 | 3.72 | 1 | 1855 | 375.8 | 129.8 |
| `semantic_sharded` ε=0.1 P=1 | 0.826 | 0.775 | 0.296 | 0.776 | 0.224 | 0.000 | 0.991 | 2.67 | 1 | 1331 | 125.5 | 24.8 |
| `semantic_sharded` ε=0.0 P=2 | 0.762 | 0.720 | 0.432 | 0.721 | 0.279 | 0.000 | 0.988 | 1.00 | 2 | 499 | 24.1 | 4.3 |
| `semantic_sharded` ε=0.0 P=1 | 0.593 | 0.547 | 0.272 | 0.547 | 0.453 | 0.000 | 0.977 | 1.00 | 1 | 499 | 26.4 | 1.3 |
| `single_node_hnsw` M=32 ef=128 | 0.999 | **0.998** | 0.983 | 1.000 | 0.000 | 0.002 | 1.000 | 1.00 | 1 | 499 | 310.6 | 1.9 |

Nothing was dropped: `configs_planned 8, configs_measured 8, dropped 0`. The
last config started at 18:45:09 against a 18:47:07 deadline — **118 seconds of
margin** on a 45-minute budget, which is closer than it should have been and
is noted under "Observed, not done".

### The reference rows against the fixture's published values

| value | published | measured | delta | tolerance | |
|---|---|---|---|---|---|
| `single_node_hnsw.recall_at_10` | 0.997 | 0.99755 | 0.00055 | 0.01 | OK |
| `semantic_sharded.recall_at_10` | 0.932 | 0.93185 | 0.00015 | 0.01 | OK |
| `semantic_sharded.routing_ceiling` | 0.932 | 0.9323 | 0.00030 | 0.01 | OK |
| `semantic_sharded.storage_amplification` | 3.715 | 3.71516 | 0.00016 | 0.01 | OK |
| `p50 / p95 / p99 copies` | 4 / 4 / 4 | 4 / 4 / 4 | 0 | 0.01 | OK |

**All within tolerance**, the largest at 5.5% of its allowance. The
amplification and copy percentiles are exact: those depend only on the
closure, which is integer arithmetic over distances, not on any float-sensitive
search.

### What the sweep found

Three things the table says that the fixture's two published rows could not.

**1. A hash partition beats semantic sharding on this corpus, outright.**
`hash_sharded` N=3 reaches **0.998 recall@10 at 1.00x storage**, against
semantic sharding's best of **0.932 at 3.72x**. The dumb partition wins on
recall *and* on storage; it pays only in fan-out (3 against 2).

That comparison is the reason the family exists. "Semantic sharding is worth
its complexity only if it beats a hash partition's recall at a lower fan-out"
is now a measured statement about arxiv-150k rather than an argument, and the
answer is no.

**2. The loss is entirely routing, at every ε and P.** The `index` column is
**0.000 in all six semantic rows** — every neighbour the routing could reach
was returned. Raising `efSearch` cannot recover anything, because there is
nothing reachable left to find. The whole gap is in the `route` column, from
0.068 at ε=0.2 P=2 to 0.453 at ε=0.0 P=1.

This is the decomposition earning its place on the interface. Without the
ceiling, six numbers between 0.547 and 0.932 would look like a tuning problem.

**3. The ε cost curve is steep and non-linear in wall clock.**

| ε | amplification | build+query, P=1 | build+query, P=2 |
|---|---|---|---|
| 0.0 | 1.00x | 28 s | 28 s |
| 0.1 | 2.67x | 150 s | 329 s |
| 0.2 | 3.72x | 506 s | 702 s |

Going from ε=0.1 to ε=0.2 buys 0.037 recall (0.895 → 0.932) for 1.4x the
storage and 2.1x the time. The closure's cost is superlinear in what it buys.

### `1/Ratio@10` behaves as defined

Monotonic with recall across all eight rows, and strictly more forgiving:
`semantic_sharded` ε=0.0 P=1 recalls 0.547 of the right ids but scores 0.977
on distance ratio — the neighbours it returns instead are nearly as close.
That is the column doing its job: it separates "returned something almost as
good" from "returned something unrelated", which recall cannot.

### A measured artifact: `r@100` is capped for `semantic_sharded`

The `r@100` column is uninformative for that family, and the reason is
structural, not a bug. `SHARD_DEPTH` is 30 candidates per probed shard, so a
query can never see more than `probe × 30` distinct vectors.

Measured rather than inferred (`tasks/scratch/008-shard-depth-cap.py`):

    SHARD_DEPTH = 30
      probe=1   measured fill: mean 30.0  max 30   -> r@100 bounded by 0.30
      probe=2   measured fill: mean 60.0  max 60   -> r@100 bounded by 0.60
      probe=3   measured fill: mean 90.0  max 90   -> r@100 bounded by 0.90

The arXiv rows sit right under those bounds: 0.272–0.298 at P=1 (cap 0.30) and
0.421–0.453 at P=2 (cap 0.60). So `r@100` there measures `SHARD_DEPTH`, not the
architecture.

I did not change `SHARD_DEPTH` — the brief forbids changing the extracted
models' measurements, and it is the value every published fixture number was
measured with. It is documented as a known limit in
`semantic_sharded/MODEL.md`, and it is the clearest candidate for the family's
first real parameter.

### Two defects I introduced and fixed

**A falsy-zero budget bug.** `deadline = ... if max_minutes else None` treated
`max_minutes: 0` as *no budget* rather than *no time*, so the tightest possible
budget silently became the loosest. Caught by the test that sets it to 0 and
expects everything to be dropped. Now `is not None`.

**My own disclaimer contained verdict vocabulary.** The table footer read "not
a recommendation: no row here is marked as meeting or failing anything" — a
negated disclaimer, but the acceptance criterion is that the output contains
no verdict language, and a strict test cannot tell a disclaimer from a claim. I
reworded the footer rather than adding an exception to the test, on the grounds
that a strict test is worth more than a clever sentence.

### Tests

| suite | result |
|---|---|
| `pytest oneground/ -m "not live"` | **125 passed, 1 deselected** |
| `oneground/models/test_conformance.py` | 13 passed |
| `oneground/simulate/test_simulate.py` | 13 passed |
| everything from task 007 | still passing |

The conformance suite is parameterised over `models.REGISTRY`, so a new family
is held to the same bar the moment it is registered, with no edit to the test
file. It collects failures across families rather than stopping at the first,
so one broken family cannot hide another.

The invariant it exists for — **`ceiling >= recall`, always** — is asserted for
every registered family. A model that returned neighbours its own routing calls
unreachable is not describing itself correctly.

### Sizes

    oneground/models/base.py                 208
    oneground/models/single_node_hnsw/model.py    94
    oneground/models/semantic_sharded/model.py   204
    oneground/models/hash_sharded/model.py       173
    oneground/simulate/__init__.py           465
    oneground/models/test_conformance.py     297
    oneground/simulate/test_simulate.py      269
    docs/MODELS.md                           138
    MODEL.md x 3                             ~250

## Verification

**Passed**

- Three families registered; **conformance passes for all three**, including
  the `ceiling >= recall` invariant and full footprint field coverage.
- **Smoke rebuild byte-identical on all six receipts** through the extracted
  models.
- **All 7 published reference values within tolerance** on arXiv-150k.
- `oneground simulate` output contains **no verdict language** — checked
  against the real arXiv stdout and `simulate.json`, not only the synthetic
  test.
- Every row carries its decomposition, and `routing_loss + index_loss`
  reconciles with `1 - recall@10` to 1e-6 on every row.
- Full-reach families (`single_node_hnsw`, `hash_sharded`) report routing loss
  0.000, as their definition requires.
- Budgets drop loudly: `max_configs` and `max_minutes` both produce
  `couldnt_check: budget` entries with the rule that dropped them.
- `simulate` refuses without a characterization and names
  `oneground characterize` as the command to run.
- The manifest covers both commands' receipts after simulate rewrites it.
- 125 tests pass. `oneground --help` lists four commands.
- **`fixtures/` untouched**, spec untouched — `git status --porcelain
  fixtures/` empty and `git diff` on the spec clean.

**Failed**

Nothing at the end. Two defects failed during the work, both mine, both above.

**Couldn't check**

- **Whether the canonical 150k fixture rebuilds byte-identically** through the
  models. The gate ran on smoke, as the brief specifies. The 150k path differs
  only in scale, and the reference rows match the published values — but that
  is agreement on *values*, not bytes, and a canonical rebuild is a multi-hour
  pod run.
- **Whether `est_memory_bytes` resembles real resident memory.** It is
  `n*dim*4 + n*2M*4`, a payload and link budget. Nothing in this task measured
  actual RSS, and the column is labelled an estimate everywhere it appears.
- **`build_seconds` and `query_seconds` are single unrepeated timings** on a
  laptop that was also running a test suite for part of the sweep. They are
  order-of-magnitude, not benchmarks; `semantic_sharded` ε=0.2 P=2's 386.8 s
  query time in particular sat alongside other work.
- **Whether `hash_sharded`'s recall genuinely equals the single-node
  baseline's** in general. Here both are 0.998, but N smaller graphs each
  searched to depth 30 can collectively hold more candidates than one graph at
  efSearch=128, so the equality is a coincidence of this configuration rather
  than an identity. `MODEL.md` says so.
- **Larger `centroids` values.** The grid fixes 256, matching the fixture. The
  family's behaviour at 64 or 1024 centroids is untested at scale.

## Observed, not done

- **`oneground/README.md` still overclaims**, unchanged from task 007's report.
  After this task, `simulate` is real, so the sentence is wrong in two places
  rather than three.
- **The 45-minute budget was 118 seconds from truncating the sweep.** Every
  config was measured, but only just, and the margin was luck rather than
  design: `hash_sharded` N=3 — a config the brief explicitly asks for — would
  have been dropped had `semantic_sharded` ε=0.2 P=1 taken two more minutes.
  A budget that orders cheap configs first, or one that reserves time per
  family, would make that outcome not depend on ordering.
- **`SHARD_DEPTH = 30` should probably be a swept parameter.** It caps `r@100`
  as measured above, and it is the one constant in `semantic_sharded` that
  silently bounds a reported metric. Out of scope here — changing it changes
  the extracted model's measurements.
- **`simulate` caches `ground_truth.npy` and `ground_truth_scores.npy` in the
  workdir but does not list them in the MANIFEST.** They are a cache,
  re-derivable from (base, queries, k), so leaving them unlisted is
  defensible — but the verifier now reports two files present and not listed,
  and the fixture *does* manifest its ground truth. The two conventions
  disagree.
- **`Model` is a Protocol but nothing checks conformance statically.** The
  conformance test is runtime-only; a family missing `ceiling` fails at call
  time, not at registration. A `runtime_checkable` check at import would fail
  earlier.
- **`plan_sweep` divides `max_configs` evenly across families**, so a family
  with two configs and one with forty each get half. That is deliberate (a
  large first family cannot starve a later one) but it means `max_configs=10`
  over three families gives 3 each and drops nothing from a family that only
  had 2.
- **`models/` at the repo root is now a README describing code that lives in
  `oneground/models/`.** CLAUDE.md's layout section lists the root directory;
  the brief placed the families inside the package. The two disagree.
- **`node_counts` only affects `hash_sharded`.** The other two families ignore
  it, which is correct — neither has a node count — but a requirements file
  setting `node_counts: [1, 3, 5]` gets three rows, not nine.
- **The root `README.md`'s "what exists today" section does not mention
  `simulate`.** Not in the brief's Do list.

## Repo now contains

New:

    oneground/models/__init__.py                   registry
    oneground/models/base.py                       the interface
    oneground/models/test_conformance.py
    oneground/models/single_node_hnsw/{__init__,model}.py + MODEL.md
    oneground/models/semantic_sharded/{__init__,model}.py + MODEL.md
    oneground/models/hash_sharded/{__init__,model}.py + MODEL.md
    oneground/simulate/__init__.py                 the command
    oneground/simulate/test_simulate.py
    docs/MODELS.md
    tasks/008-models-simulate.report.md
    tasks/scratch/008-{ref-equivalence,reference-rows,shard-depth-cap}.py

Modified:

    oneground/fixture/reference.py    now calls oneground.models
    oneground/cli.py                  `simulate` added
    requirements.arxiv-150k.yaml      simulate block: families, grid,
                                      include (the two reference configs),
                                      budget

Written outside the repo (git-ignored `runs/`):

    runs/arxiv-150k-via-characterize/simulate.json
    runs/arxiv-150k-via-characterize/simulate_info.json
    runs/arxiv-150k-via-characterize/ground_truth{,_scores}.npy   (cache)

Unchanged: `fixtures/` entirely including the spec, `corpora/`,
`oneground/{characterize,intake,measures,receipts,sample,truth,embed}`,
`oneground/fixture/build.py`, `oneground/pod/`.

### Dependencies added

None.

### Not committed

Nothing was committed.

## Blocked on developer

Nothing was blocked.

Four things to decide:

1. **`oneground/README.md`**, still overclaiming after two tasks of flagging
   it. One paragraph.
2. **Whether `SHARD_DEPTH` becomes a `semantic_sharded` parameter.** It
   currently caps `r@100` at `probe × 0.30`, which makes that column
   meaningless for the family. Changing it changes measurements, so it needs
   its own brief and a decision about whether the published reference row is
   re-measured.
3. **Whether the simulate budget should reserve time per family** rather than
   running in order. This sweep finished with 118 seconds to spare.
4. **Whether `simulate` should manifest its ground-truth cache**, to match the
   fixture's convention, or keep it unlisted as a derived cache.
