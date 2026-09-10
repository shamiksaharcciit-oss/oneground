# Report: 009-adapter-qdrant-verify

## Repo state expected vs found

| Expected | Found |
|---|---|
| task 008 committed | yes — `c73c71e task 008: models as plugins, oneground simulate, hash-sharded baseline` |
| tree clean | yes, apart from the untracked brief |
| Docker Desktop availability unknown — check `docker info` | **available and working** |

### Docker — checked first, as instructed

| | |
|---|---|
| client / server | **20.10.17** |
| compose | **v2.10.2** |
| container run | `docker run --rm hello-world` → "Hello from Docker!" |
| daemon | Docker Desktop, x86_64, **4 CPUs, 3.87 GB** |

So **every live step was in scope** and nothing goes under "Blocked on
developer" for Docker: live Qdrant conformance, a real `oneground verify`, a
live `existing_collection` run, and a real calibration error rather than a stub
one.

The 3.87 GB daemon allocation is worth recording: fine for 5,000 conformance
vectors and the 2,000-vector smoke fixture, nowhere near enough for
arXiv-150k. That bounds what task 011 can do locally.

## What was done

Every step, including all the live ones.

### Step 1 — the three carried-over fixes

**`oneground/README.md`** rewritten to the root README's exists/planned split.
Present tense for `characterize` and `simulate` only; `verify` and `report`
are under "what is planned", with "nothing here is implemented, and this
package does not imply otherwise".

**`shard_depth` is now a `Config` field**, default 30. `simulate` sets it to
`max(30, k_max)` and records it in `simulate_info.json` as a run-level field
with a note. Config **labels are deliberately unchanged**: `shard_depth` is
uniform across a run and recorded once, so folding it into every label would
churn every row id for a value that never varies within a run — and two sweeps
of the same grid would stop being comparable row for row.

**Sweep ordering**: `_pinned_first` puts explicitly-listed configs ahead of the
generated grid, at framework level rather than trusting each family to keep
doing it. A budget truncates the tail, so ordering decides what survives, and
what a requirements file named by hand is what the run most needs.

### Step 2 — `oneground/adapters/base.py`

The `VectorEngine` protocol, plus `UpsertStats`, `Candidates`, `EngineFacts`,
`managed_namespace` and a registry. `EngineFacts.kind` is `"declared"` and
carries a note saying so in the receipt.

`managed_namespace` **refuses any namespace outside the `oneground-` prefix**,
in code rather than by convention, and deletes in a `finally`.

### Step 3 — `oneground/adapters/qdrant/`

Via the official `qdrant-client` 1.19.0, pinned with its transitive closure.
Metrics inner_product/cosine/l2; HNSW `m`, `ef_construct`, `full_scan_threshold`
and search `hnsw_ef`. `describe()` pulls collection info plus cluster info when
the endpoint exposes it, and keeps the raw response.

`ADAPTER.md` documents seven quirks found while building, with the measurements
that found them.

### Step 4 — the conformance suite

All seven checks (a)–(g), parametrised over registered adapters. Stub always;
live Qdrant only when `ONEGROUND_QDRANT_URL` is set, **skipping** otherwise.
Check (g) is proved twice — a failure injected from the caller, and one
injected inside the engine mid-`upsert`, because those are different code paths.

### Step 5 — `oneground verify`, local target

Compose file with a pinned image, ingest rate, recall at k=10 and k=100
against the workdir's exact ground truth, client-side sequential single-client
latency reported as `latency_shape_single_client`, and a 50-ping
`rtt_baseline_ms` against an empty collection with the 20% noise guard.

### Step 6 — `existing_collection` mode

Read-only. Scroll a sample, compute exact ground truth over it, search the live
collection, score against that. Tested live against a collection oneground did
not create.

### Step 7 — calibration error

`calibration_error_recall = simulated − measured`, matched on M and efSearch.

### Step 8 — `docs/ADAPTERS.md`

The protocol, the measured/declared table per method, the conformance suite as
the contribution gate, how to add an adapter, and "no engine of our own, no
favourite, no sponsored defaults."

### Deviations

- **Step 1's "byte-identical `simulate.json` rows" does not hold literally**,
  and cannot. See Measurements — the published reference *values* are
  unchanged, but `recall_at_100` moves, which is the entire point of the fix.
- **The compose image moved from my first pick (v1.15.1) to v1.19.1** to match
  the pinned client, which warns it is incompatible otherwise.
- **`requirements.smoke.yaml` is new** — the brief assumes a smoke workdir for
  steps 5 and 7 and none existed.

## Measurements

### Step 1: does `shard_depth` move the reference rows?

`tasks/scratch/009-shard-depth-invariance.py`, both configs measured at depth
30 and depth 100 on smoke.

My assumption going in was that smoke's shards are too small for the depth to
bind. **That was wrong, and the measurement caught it:**

    semantic_sharded shard sizes on smoke: n=256  min=1  median=13  max=56
    depth 30 binds on 24 shards; depth 100 binds on 0

24 of 256 shards exceed 30 vectors. So the depth *does* bind, and one field
moves:

| field | depth 30 | depth 100 | |
|---|---|---|---|
| `recall_at_10` | 0.6345 | 0.6345 | same |
| `ceiling_at_10` | 0.6345 | 0.6345 | same |
| `storage_amplification` | 1.906 | 1.906 | same |
| p50/p95/p99 copies | 1/4/4 | 1/4/4 | same |
| `inv_ratio_at_10` | 0.969223080 | 0.969223080 | same |
| **`recall_at_100`** | **0.32785** | **0.33860** | **moved** |

Every other field, and both `single_node_hnsw` rows, identical.

**The published reference values are unchanged.** The fixture publishes
`recall_at_10`, `routing_ceiling`, `storage_amplification` and the copy
percentiles; all six are byte-identical, confirmed independently by
`tasks/scratch/008-ref-equivalence.py` against the committed
`characterization.json`:

    single_node_hnsw.recall_at_10          delta 0.000000000
    semantic_sharded.recall_at_10          delta 0.000000000
    semantic_sharded.routing_ceiling       delta 0.000000000
    semantic_sharded.storage_amplification delta 0.000000000
    p50 / p95 / p99 copies                 delta 0.000000000
    IDENTICAL

The brief's two clauses — "reference rows must not move" and "simulate sets
`shard_depth = max(30, k_max)`" — cannot both hold for `recall@100`, because
raising the depth is *designed* to change exactly that number. Task 008
measured that `r@100` was capped at `probe × 0.30` and reported the constant
rather than the architecture; this is the cap coming off. I read the
parenthetical as protecting the published values, which it does.

The fixture builder is untouched by this: `reference.py` builds its Config
without `shard_depth`, gets the default 30, and measures at k=10.

### Live conformance — both engines

    conformance: 2 engine(s) reachable
      stub (in-process)
        (a) created oneground-conf-...-conformance
        (b) upserted 5000 at 2,491,271/s
        (c) recall@10 1.0000 >= 0.95
        (d) describe: 5000 points, dim 64, index exact
        (e) scrolled 100 vectors, all match
        (f) namespace deleted
        (g) namespace deleted after an exception
        PASS
      qdrant (http://localhost:6333)
        (a) created oneground-conf-...-conformance
        (b) upserted 5000 at 4,448/s
            indexed 5000/5000 in 0.6s
        (c) recall@10 1.0000 >= 0.95
        (d) describe: 5000 points, dim 64, index hnsw
            {'m': 16, 'ef_construct': 200, ...}
        (e) scrolled 100 vectors, all match
        (f) namespace deleted
        (g) namespace deleted after an exception
        PASS

Without a URL, the Qdrant test **skips and says so**:

    SKIPPED [1] ONEGROUND_QDRANT_URL not set; live Qdrant not contacted

### The finding this task exists to have produced

**Qdrant was answering every search with an exact scan, and check (c) was
green for it.**

`optimizers_config.indexing_threshold` decides whether an HNSW graph is built
at all. It is a segment size in **kilobytes**, default **20,000 (20 MB)**. The
conformance corpus is 5,000 × 64 float32 = **1.3 MB**, so no graph was ever
built. Measured (`tasks/scratch/009-indexing-threshold.py`):

    indexing_threshold=20000 KB -> indexed_vectors_count=0
        ef=4    recall@10 = 1.0000        <- not HNSW being good
        ef=512  recall@10 = 1.0000        <- HNSW never consulted
    indexing_threshold=1 KB     -> indexed_vectors_count=5000

And the obvious signal is wrong. Qdrant reports `status: green` with zero
vectors indexed, because green means "no operations pending"
(`tasks/scratch/009-index-timing.py`):

    t= 0.0s  status=green  points=5000  indexed=0
    t=14.0s  status=green  points=5000  indexed=0

The only field that answers the question is `indexed_vectors_count`. The
adapter now takes `indexing_threshold`, exposes `wait_for_index()` returning
`(indexed, points, seconds)`, and both the conformance suite and `verify` wait
before measuring and record the result.

Had this not been found, every "Qdrant HNSW recall" this project ever reported
on a small fixture would have been a linear scan.

Two smaller ones: `full_scan_threshold: 1` is rejected with HTTP 422
(`must be 10 or larger`) and is not the knob anyway; and `qdrant-client` 1.19.0
warns that server 1.15.1 — my first image pick — is incompatible, so the
compose tag now tracks the client at **v1.19.1**.

### `oneground verify` on smoke, live Qdrant v1.19.1

    ingest            509 vectors/s (2,000 in 3.9 s, durable writes)
    indexed           2000/2000 in 1.1 s
    rtt baseline      p50 16.60 ms  p95 37.18 ms  (empty collection, 50 pings)

    k=10    recall@10   1.0000
            latency     couldnt_check: environment noise
    k=100   recall@100  1.0000
            latency     couldnt_check: environment noise

    calibration       simulated 1.0000 - measured 1.0000 = +0.0000
                      (single_node_hnsw[M=32,efConstruction=200,efSearch=128])

**`calibration_error_recall = +0.0000`**, which is inside the brief's ~0.01
expectation — but it is inside it for an uninteresting reason: smoke is 2,000
vectors and both the simulated HNSW and Qdrant's return every true neighbour,
so the comparison is 1.0 against 1.0. It establishes the number and the
plumbing; it does not yet exercise them. arXiv-150k, where simulated recall is
0.9973 rather than 1.0, is where this becomes informative.

**The noise guard fired, and it is right to have.** The empty-collection RTT
p95 (37.18 ms) is **132%** of the k=10 query p95 (28.08 ms). Latency here is
the Windows Docker NAT round trip, not Qdrant, so it is reported as
`couldnt_check: environment noise` while recall — which noise cannot move — is
still reported. The measured shape is kept under
`latency_measured_but_not_attributable` rather than discarded.

That is a finding about this environment, not a defect: **this laptop cannot
produce attributable latency numbers for a containerised engine**, which is
precisely why task 011 moves to a pod.

### `existing_collection`, live and read-only

Against `acme-support-tickets`, a 3,000-point collection created outside
oneground with no `oneground-` prefix:

    collections before verify: ['acme-support-tickets']
    existing collection acme-support-tickets: 3000 points, dim 64
    scrolling 2,000 vectors (read-only)
    rtt baseline (read-only) p50 10.66 ms, p95 32.17 ms
      recall@10 0.7247 (over the sample)
    collections after verify : ['acme-support-tickets']
    READ-ONLY HELD: True; acme-support-tickets still has 3000 points

The 0.7247 is not a defect and the receipt says why. Ground truth is computed
over the 2,000 scrolled vectors while the engine searches all 3,000, so a
genuinely-nearer neighbour outside the sample is scored as a **miss**. The
receipt now labels it `LOWER BOUND` and records `sample_fraction`.

### Tests

| suite | result |
|---|---|
| `pytest oneground/ -m "not live"` | **140 passed, 1 deselected** |
| `oneground/adapters/conformance.py` (stub only) | 5 passed, 1 skipped |
| `oneground/adapters/conformance.py` (with Qdrant) | **6 passed** |
| `oneground/verify/test_verify.py` | 15 passed |
| everything from tasks 007–008 | still passing |

### Four defects I introduced and fixed

1. **`existing_collection` was not read-only.** My RTT baseline created and
   searched an empty collection — a write, in a mode the brief calls
   read-only. Replaced with a `describe()` round trip and labelled as a
   different measurement, since a collection-info call is not a search.
2. **My own scope note was false.** It said an out-of-sample neighbour "is
   counted as neither a hit nor a miss". The code counts it as a **miss**.
   Corrected to say the recall is a lower bound, and why.
3. **The summary crashed on a Unicode minus** (`U+2212`) under cp1252 — the
   third time this project has been bitten by Windows console encoding. All
   non-ASCII punctuation removed from output strings.
4. **The noise guard only wrote on failure**, silently doing nothing when
   called on a dict the caller had not pre-populated. It now sets the key
   either way.

Also: the adapter reported `engine_version: "unknown"` because it reached for a
client-private attribute; it now reads the REST root of the endpoint it was
given, and reports `1.19.1`.

## Verification

**Passed**

- Step-1 fixes landed; **published reference values byte-identical** (7 fields,
  delta 0.000000000).
- Stub conformance passes with no Docker and no network; **live Qdrant
  conformance passes all seven checks** against v1.19.1, with the index
  genuinely built (5000/5000 indexed) rather than brute-forced.
- Without `ONEGROUND_QDRANT_URL` the live test **skips**, reported as a skip.
- `oneground verify` on smoke produces `verify.json` with recall, latency
  shape, RTT baseline and calibration error; **no verdict language** in stdout
  or in the JSON.
- **Nothing is reported as throughput**: `latency_shape_single_client` carries
  `concurrency: 1` and "not throughput", asserted by a test that scans the
  JSON for rate vocabulary.
- Cleanup-on-failure passes, from both the caller and inside the engine.
- Namespace prefix enforced: an unprefixed name is refused, not created.
- `existing_collection` is genuinely read-only — verified by listing
  collections and point counts before and after.
- 140 tests pass. Both docs exist. `oneground --help` lists five commands.
- **`fixtures/` untouched.**
- The container was torn down: `docker ps --filter name=oneground` → 0.

**Failed**

Nothing at the end. Four defects failed during the work, all mine, all above.

**Couldn't check**

- **Latency attributable to Qdrant.** The noise guard fired on every search:
  the RTT baseline p95 was 132% of the k=10 query p95. Nothing in this task
  measured engine latency; it measured the path to a container on Windows.
- **Whether the calibration error is meaningful.** +0.0000 on a fixture where
  both sides return perfect recall establishes the plumbing, not the
  quantity.
- **Approximate-index behaviour on the smoke verify.** With
  `indexing_threshold: 1` the graph is built, but 2,000 × 768 with queries
  drawn from the corpus is easy enough that recall is 1.0 at every ef tried.
  No run here produced a Qdrant recall below 1.0, so nothing exercised the
  gap the calibration error exists to track.
- **Throughput, deliberately.** Not measured, not estimated, not claimed.
- **Multi-vector collections, payload filters, gRPC, distributed Qdrant** —
  all unsupported and listed in `ADAPTER.md`.
- **Whether a full smoke fixture *rebuild* is still byte-identical.** The
  reference-result equivalence was checked directly at full precision, which
  is the part `semantic_sharded` touches, but no ~10-minute end-to-end rebuild
  was run in this task.

## Observed, not done

- **`recall_at_100` moves for `semantic_sharded` in any new sweep**
  (0.32785 → 0.33860 on smoke). Task 008's arXiv `simulate.json` was measured
  at the old depth, so its `r@100` column is not comparable with future runs.
  Nothing records which depth a historical run used except
  `simulate_info.json` going forward.
- **`shard_depth` is not in the config label.** Deliberate, and it means two
  runs at different depths produce rows with identical ids and different
  numbers. The value is in `simulate_info.json`; a reader comparing two
  `simulate.json` files without it would be misled.
- **The RTT baseline and the query path are not the same shape.** The baseline
  searches an empty collection at k=1; the queries search a full one at k=10
  and k=100. The 20% rule compares them anyway, which is why the k=100 guard
  fired at 25% while k=10 fired at 132% — a longer query makes the same
  baseline look smaller. Defensible as a floor on path cost, but it is not a
  like-for-like subtraction.
- **`verify` does not re-check that the ingested vectors match the sample.**
  It trusts the upsert. A conformance-style scroll-and-compare after ingest
  would close that, at the cost of a second pass over the corpus.
- **`_simulated_recall` matches only `single_node_hnsw`.** Calibrating a
  sharded family against a real engine needs the engine to be sharded the same
  way, which is task 011 territory.
- **The stub is registered as an engine.** A requirements file could name
  `engine: stub` and get a receipt full of exact-search numbers labelled as an
  engine measurement. It is obvious in the output (`engine: stub`), but nothing
  refuses it.
- **`requirements.txt` gained 13 pinned lines** for `qdrant-client` and its
  closure, including `pywin32`, which is Windows-only and will not install on
  the Linux pod. That will need a marker before task 011.
- **`docs/CHARTER.md`'s Phase 1 line "VectorEngine adapter protocol + Qdrant
  adapter + conformance test" is now done** and the status table has no row
  for tasks 007–009.
- **The root `README.md` does not mention `simulate` or `verify`** under "what
  exists today".

## Repo now contains

New:

    oneground/adapters/__init__.py
    oneground/adapters/base.py                  the VectorEngine protocol
    oneground/adapters/stub.py                  in-process engine for CI
    oneground/adapters/conformance.py           the contribution gate
    oneground/adapters/qdrant/{__init__,adapter}.py
    oneground/adapters/qdrant/ADAPTER.md
    oneground/verify/__init__.py                the verify command
    oneground/verify/test_verify.py
    oneground/verify/compose/qdrant.yml         pinned image
    docs/ADAPTERS.md
    requirements.smoke.yaml
    tasks/009-adapter-qdrant-verify.report.md
    tasks/scratch/009-{shard-depth-invariance,is-hnsw-used,index-timing,
                       indexing-threshold,existing-collection}.py

Modified:

    oneground/README.md                     exists/planned split
    oneground/models/semantic_sharded/model.py   shard_depth as a Config field
    oneground/simulate/__init__.py          pinned-first ordering, shard_depth
                                            injection and recording
    oneground/cli.py                        `verify` added
    requirements.txt                        qdrant-client 1.19.0 + closure

Written outside the repo (git-ignored `runs/`):

    runs/arxiv-smoke/{characterization,simulate,verify}*.json + MANIFEST
    runs/acme-existing/                     the existing_collection run

Unchanged: `fixtures/` entirely, `corpora/`, `oneground/{characterize,intake,
measures,receipts,sample,truth,embed,fixture,models,pod}` apart from the one
model file above.

### Dependencies added

`qdrant-client==1.19.0` and its transitive closure: `grpcio==1.83.1`,
`protobuf==7.36.1`, `pydantic==2.13.5`, `pydantic-core==2.46.5`,
`annotated-types==0.8.0`, `h2==4.4.1`, `hpack==4.2.0`, `hyperframe==6.1.0`,
`portalocker==3.2.0`, `pywin32==312`, `typing-inspection==0.4.4`,
`urllib3==2.7.0`. All pinned in `requirements.txt`. `pywin32` is Windows-only
— see "Observed, not done".

Docker image `qdrant/qdrant:v1.19.1`, pinned in the compose file.

### Not committed

Nothing was committed.

## Blocked on developer

Nothing was blocked — Docker was available and every live step ran.

Five things to decide:

1. **Whether the `recall@100` movement is the intended reading** of step 1's
   "reference rows must not move". The published values did not move; that one
   metric did, by design.
2. **`pywin32` in `requirements.txt`** will break `pip install -r` on the pod.
   It needs `; sys_platform == "win32"` before task 011.
3. **Latency on this machine is not measurable** — the RTT baseline exceeds
   the query p95. Task 011's pod work is not an enhancement here, it is the
   only way to get a latency number that means anything.
4. **Whether `engine: stub` should be refused** in a real requirements file.
5. **The charter's Phase 1 adapter line is now complete**, and the status
   table has no rows for tasks 007–009.
