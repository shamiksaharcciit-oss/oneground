# Report: 012b-calibration-followup

## Repo state expected vs found

Expected: task 012 accepted and committed on `task-012`; the GloVe curve red
with seven blocking `contradicted` lines; `single_node_hnsw` builds
non-deterministic; `docs/VALIDATION.md` and the CI workflow describing the
curve as the gate.

Found exactly that. HEAD `0139e92` "task 012: the curves, the engine line, the
decomposition, the 012 report", tree clean, 16 history lines (1 schema-1 seed,
7 `glove_curve` contradicted, 7 `glove_curve` couldnt_check, 1
`simulator_vs_engine` verified).

No deviation from the follow-up brief's assumptions. Four items, all done, one
of them with a proposal rather than a decision as instructed.

## What was done

**1. The gate moved to the three clean layers; the curve became advisory.**
`oneground calibrate layers` is new and blocking. The hnswlib comparison still
runs, still at tolerance 0.02, still comes back contradicted — and can no
longer fail anything. The per-efSearch offset is published in the fixture.

**2. Engine lines carry `efSearch` as a required field** from a new schema
version, and `docs/MODELS.md` gained the portability note with the measured
ratio.

**3. `single_node_hnsw` builds single-threaded by default.** Two builds now
return byte-identical ids. The cost is measured below, and the split is
proposed rather than taken.

**4. `docs/VALIDATION.md` and the CI workflow** now describe a run whose
blocking checks are green and whose advisory contradiction is recorded.

## Measurements

### 1. The three blocking checks

`oneground calibrate layers --fixture glove-100-angular`, on the full
1,183,514-vector corpus. Exit **0**.

| check | measured | reference | tolerance | outcome |
| --- | --- | --- | --- | --- |
| `corpus_reachability` | **1.000000** | 1.0 | 0.0 | verified |
| `metric_agreement` | **1.000000** | 1.0 | 0.001 | verified |
| `recall_rule_accounting` | **0.000200** | 0.0 | 0.01 | verified |

Method, per check:

- **corpus_reachability** — mean over 10,000 queries of the share of the
  published top-10 whose ids are below `n_base`. This is the check that would
  have caught task 012's brief's 100k prefix, where it reads 0.086.
- **metric_agreement** — exact `IndexFlatIP` top-10 over all 1,183,514
  normalized vectors for 1,000 queries, intersected with the published
  neighbours. Tolerance 0.001 rather than 0 only because a boundary tie could
  legitimately swap one id; a genuine convention error (L2 instead of inner
  product, or unnormalized vectors) collapses this toward zero rather than
  drifting, which a test pins.
- **recall_rule_accounting** — fraction of queries whose 10th and 11th
  *published* distances coincide. This bounds how far ANN-Benchmarks'
  distance-based `knn` metric can exceed an id-based intersection, which is
  the whole of task 012's layer-3 elimination.

**One number moved from task 012 and the reason is the tie definition.** Task
012's scratch reported a tie rate of 0.0016; this reports 0.000200. The scratch
used `np.isclose` with its default `rtol=1e-05`, which counts near-ties on
distances around 0.43 as ties; the check uses `rtol=0.0, atol=1e-6`, an
absolute float32 tie. The stricter reading is the right one for this purpose —
ANN-Benchmarks' own metric uses an absolute epsilon — and both are far inside
the 0.01 band. Recorded rather than quietly corrected.

### 2. Build determinism — the fix and what it costs

`single_node_hnsw.build` now adds inside `single_threaded_faiss`
(`deterministic=True`, from `DETERMINISTIC_DEFAULT`). Measured with
`tasks/scratch/012b-build-cost.py`, which drives `MODEL.build` directly.

| corpus | n × dim | config | parallel | deterministic | ratio | two deterministic builds → byte-identical ids |
| --- | --- | --- | --- | --- | --- | --- |
| arxiv-smoke | 2,000 × 768 | M=32, efC=200 | 0.97 s | **0.89 s** | **0.91×** | **yes** |
| glove prefix | 100,000 × 100 | M=12, efC=500 | 307.49 s | **576.57 s** | **1.88×** | **yes** |
| glove (full) | 1,183,514 × 100 | M=12, efC=500 | 1,213 s (task 012) | **2,135 s** | **1.76×** | not run as a pair — see Verification |

The full-corpus pair is the number to trust: same machine, same corpus, same
configuration, both through `MODEL.build`, and the two independent estimates
agree — **1.76× at 1.18 M vectors, 1.88× at 100 k**. faiss's parallel HNSW add
gets nowhere near a 4× speedup on four cores, so single-threading gives back
much less than the core count suggests.

**One full-corpus build was thrown away and is not in the table.** An earlier
deterministic build of the same index took 4,127 s while another process on
this machine was competing for CPU and free memory sat at 0.18–0.31 GB;
sampling the process showed it gaining 2 CPU seconds per 45 s of wall clock,
i.e. paging rather than computing. That run is excluded as contaminated rather
than averaged in. The 2,135 s figure is from a later run on a quiet machine.
It is also why `calibrate curve` now caches the built index (below).

**On arxiv-smoke the deterministic build is faster.** At 2,000 vectors faiss
does not meaningfully parallelise the add, so pinning one thread costs
nothing and saves the thread-pool overhead. The same run also found that two
*parallel* builds at that size are already byte-identical — which is exactly
why the existing conformance test
`test_build_is_deterministic_synthetic` passed all the way through task 012
while the model was in fact non-deterministic. The bug lived only in the
regime the test never entered. That test now says so in its docstring.

**Timing variance within the 100k row, stated because it bounds that row's
precision.** The first deterministic 100k build took 576.57 s and the second
329.93 s, on identical inputs producing identical ids — the first materialises
a slice of a 473 MB memmap, the second finds it in page cache. So the 1.88× on
that row is a cold-against-cold reading with roughly ±0.4× of slack in it.
The full-corpus row does not have that problem: 1,213 s and 2,135 s are both
whole-corpus builds with the same access pattern, and they land at 1.76×.

### 3. The advisory curve, rebuilt deterministically

`oneground calibrate curve --fixture glove-100-angular --config
M=12,efConstruction=500`. Full corpus, deterministic build (2,135 s), 10,000
queries per point. **Exit code 0** — seven contradictions, none of which can
fail anything.

| efSearch | measured (012b, deterministic) | published hnswlib | offset | vs 012 (parallel) | outcome |
| --- | --- | --- | --- | --- | --- |
| 10 | 0.42897 | 0.36534 | **+0.06363** | −0.00003 | contradicted (advisory) |
| 20 | 0.55798 | 0.49515 | **+0.06283** | −0.00084 | contradicted (advisory) |
| 40 | 0.67099 | 0.60777 | **+0.06322** | +0.00052 | contradicted (advisory) |
| 80 | 0.76108 | 0.70371 | **+0.05737** | +0.00296 | contradicted (advisory) |
| 120 | 0.80156 | 0.75057 | **+0.05099** | +0.00135 | contradicted (advisory) |
| 200 | 0.84469 | 0.79998 | **+0.04471** | +0.00057 | contradicted (advisory) |
| 400 | 0.89038 | 0.85386 | **+0.03652** | +0.00058 | contradicted (advisory) |

**The tolerance is still 0.02 and every point is still contradicted.** What
changed is that the lines carry `outcome_scope: advisory`, so they are
recorded and cannot gate. Nothing was widened to make a point pass.

**The deterministic rebuild reproduces task 012's parallel run to within
0.00296**, well inside the 0.0047 build-to-build drift task 012 measured with
two parallel builds, and roughly twenty times smaller than the offsets
themselves. The finding was never build noise, and now the numbers behind it
are reproducible.

**The published offset, refreshed.** `implementation_offset` in the fixture
spec now carries these seven values, measured deterministically, with the
build time and environment beside them. A later run reports
`offset_residual` — how far its own offset sits from the published one — so
drift in the *difference between the implementations* becomes visible without
gating on it.

The efSearch equivalence, recomputed from these numbers by interpolating the
published curve:

| our efSearch | 10 | 20 | 40 | 80 | 120 | 200 | 400 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| their efSearch for our recall | ~14 | ~29 | ~63 | ~134 | ~204 | ~355 | ~748 |
| ratio | 1.40× | 1.47× | 1.58× | 1.67× | 1.70× | 1.78× | 1.87× |

This is the table now in `docs/MODELS.md`.

### 4. The engine line

`oneground calibrate engine requirements.smoke.yaml --engine qdrant`, against
the pinned `qdrant/qdrant:v1.19.1`.

| field | value |
| --- | --- |
| config | `single_node_hnsw[M=32,efConstruction=200,efSearch=128]` |
| **efSearch** | **128** |
| `efSearch_source` | `verify_info.engine_params.hnsw_ef` |
| M / efConstruction | 32 / 200 |
| simulated recall@10 | 1.00000 |
| measured recall@10 | 1.00000 |
| deviation | +0.00000, tolerance 0.05, **verified** |

`efSearch` is read from `engine_params.hnsw_ef` rather than from
`engine_facts.index_params`, for the reason task 011 established: Qdrant does
not report the query-time parameter in `index_params`, so the request is the
only record of it. `M` and `efConstruction` come from `index_params` — what
the engine says it built — falling back to the request only if absent.

Still an easy number: 2,000 vectors is small enough that HNSW is effectively
exact at efSearch=128, so both sides sit at 1.0. It confirms the mechanism and
resolves nothing about the simulator. Layer 2 still has one real data point,
task 011's arXiv line.

## Verification

**Test suite.** `python -m pytest -q`: **353 passed, 1 skipped, 1 failed** in
45.7 s (338 passed before 012b; 24 tests added, 3 modified). The skip is the
live RunPod test with no key. The one failure is
`test_the_real_arxiv_workdir_gives_one_option_the_measurement`, which reads the
gitignored `runs/arxiv-150k-via-characterize/` — the item routed to the master
stream and untouched here.

**Against the follow-up brief, item by item.**

- *"The three passed layers become the blocking calibration checks."* Done.
  `oneground calibrate layers` runs `corpus_reachability`,
  `metric_agreement` and `recall_rule_accounting` as blocking, all three
  verified on the real fixture, exit 0. Tolerances live in `layers.TOLERANCES`
  so a run cannot choose its own band, and a test pins that. Two tests show
  the checks catching real defects rather than merely passing: a truncated
  corpus drives `corpus_reachability` to 0.0, and ground truth built under the
  wrong metric collapses `metric_agreement` far below its band.
- *"The hnswlib curve comparison runs advisory ... tolerance unchanged."*
  Done, and the scope is declared in the fixture spec rather than in a CLI
  default, because whether a comparison may block is a property of what is
  being compared. `reference_curve.tolerance` is still 0.02 and a test asserts
  it. The run exits 0 with seven contradictions recorded.
- *"publishing the per-efSearch faiss-vs-hnswlib offset as a known one-signed
  implementation difference."* Done: `implementation_offset` in the fixture
  spec, measured deterministically, all seven values positive; `calibrate
  curve` reports `offset_residual` against them on later runs.
- *"Engine calibration lines carry efSearch explicitly."* Done, as a required
  field from schema 3 — `validate()` refuses a `simulator_vs_engine` line
  without it, and a test guards the committed file.
- *"MODELS.md gains the 'efSearch is not portable' note with your measured
  ratio."* Done, with the refreshed 1.40×–1.87× table and what follows from
  it, plus a Build determinism section.
- *"Fix single_node_hnsw build determinism ... two builds must yield
  byte-identical ids."* Done and measured: byte-identical at 2,000 and at
  100,000 vectors, through `MODEL.build`. Cost measured at three scales.
- *"Update VALIDATION.md and the CI workflow so the first run is green on the
  blocking checks and shows the advisory contradiction in the history."*
  Done — see below.

**The state a first CI run would produce**, reproduced locally by running the
three commands in the workflow's order:

    calibrate layers   3 blocking checks, all verified          exit 0
    calibrate curve    7 advisory contradictions, recorded      exit 0
    calibrate engine   1 blocking check, verified               exit 0
    calibrate show                                              exit 0

`oneground calibrate show` exits **0** with the advisory contradictions
plainly visible and marked `[advisory]`. The history holds **27 lines**: 5
verified, 14 contradicted (7 of them advisory), 7 couldnt_check, 1 schema-1
seed with no verdict.

**A design fault this exposed, found by running it and fixed.**
`latest_by_check` refused to let an advisory line displace a blocking one — a
rule written to stop a `qdrant:latest` reading becoming the answer. It also
made re-scoping impossible: task 012's seven *blocking* contradictions would
have remained the latest word forever, so `calibrate show` would have stayed
red no matter what the curve was re-scoped to. The rule was in the wrong
place. Display now shows the most recent line whatever its scope, and the
safety property is enforced where it actually matters — `_exit_code` and
`latest_for_engine` both ignore advisory lines, so an advisory reading can be
seen but can never gate a release or be cited as a report's calibration. Two
tests cover it, one of them replaying this exact scenario.

**Workflow.** Both YAML files parse. Three jobs with mutually exclusive
triggers (`pins`, `weekly`, `drift`); `pins` and `weekly` now run
`calibrate layers` as a distinct blocking step before the curve, and the curve
step is labelled advisory with the reason. `act` was **not** run — not
installed, and not in scope — so this remains a parse-and-inspect dry run, as
in task 012.

**Couldn't-check.**

- *Whether two full-corpus deterministic builds are byte-identical.* Verified
  at 2,000 and 100,000 vectors. At 1,183,514 it would cost two 35-minute
  builds to re-confirm a property of a code path that does not vary with n,
  and was not run.
- *Whether the CI workflow runs green on GitHub.* It has never executed.
- *The `simulate` sweep cost of determinism on arxiv-150k.* Not measured;
  named in the proposal as the case to watch.
- *Whether `hash_sharded` and `semantic_sharded` are non-deterministic.* Very
  likely — both build `IndexHNSWFlat` — but not measured, because the brief
  scoped the fix to `single_node_hnsw`.

## Observed, not done

### The deterministic/parallel split — proposed, not decided

The brief asked for a proposal with numbers if the cost is severe. **It is not
severe at the scales this project actually builds at, and it is negative at
the small end**, so the recommendation is to keep the current default and
*not* introduce a policy split yet. The mechanism to split already exists
(`deterministic=False`), so nothing is lost by waiting.

What the numbers support:

| where a build happens | scale | measured cost of determinism |
| --- | --- | --- |
| `simulate` sweep on a smoke corpus | 2,000 | **0.91×** — deterministic is *faster* |
| `simulate` sweep on arxiv-150k | 150,000 | not measured; between the two rows below |
| `calibrate curve`, fixture reference builds | 1,183,514 | 1.9× at best measurement, worse under memory pressure |

The shape of it: faiss's parallel HNSW add gets nowhere near linear speedup —
1.88× on four cores at 100,000 vectors — so single-threading gives back less
than the core count suggests. Below roughly a few thousand vectors it gives
back nothing at all, because faiss does not parallelise the add there, which
is also why this bug survived a determinism test for the whole of task 012.

**If the developer wants the split anyway**, the shape I would propose, with
the reasons rather than the decision:

- **Reference builds stay deterministic, always.** Fixture reference results,
  `calibrate curve`, and anything whose number is published or gated. A
  published number that cannot be rebuilt is not a receipt, and this is where
  the cost is highest but the runs are rarest.
- **Sweeps may opt out** — `simulate` over a large grid, where the point is
  the *shape* of the trade-off surface and no single row is a published
  value. At 8 configurations on 150,000 vectors the saving is minutes, not
  hours.
- **The opt-out must be recorded, never inferred.** `BuiltIndex.state` already
  carries `deterministic`, and `glove_curve` lines carry
  `deterministic_build`. A receipt from a parallel build must say so, because
  a reader who tries to reproduce it and gets a different number needs to know
  that is expected rather than a contradiction.
- **The threshold, if one is wanted, is empirical and small.** The cost is
  zero or negative below the size at which faiss parallelises. Nobody should
  pick that number from a table; it is a two-minute measurement on the target
  machine.

What would change the recommendation: a sweep where the deterministic penalty
turns a laptop run into an overnight run. Task 011's arXiv pod sessions are
the case to watch — 150,000 vectors × 8 configurations — and that has not been
measured either way. **Not measured here, and not decided here.**

### Everything else observed and not done

**The full-corpus build cost was measured on a machine that could not hold
still.** Numbers and the confound are under Measurements; the clean
comparison is the 100,000-vector pair. A quiet re-measurement would settle the
full-corpus ratio, and needs nothing but an idle laptop.

**`hash_sharded` and `semantic_sharded` are still non-deterministic.** Both
build `IndexHNSWFlat` per shard and neither was converted — the brief scoped
the fix to `single_node_hnsw`. The helper they need is already in
`models/base.py` and the change is a one-line `with single_threaded_faiss(...)`
per family, plus the cost measurement each deserves. `docs/MODELS.md` says
they are unconverted rather than leaving a reader to assume otherwise.
**Not done: out of scope.**

**The recall-rule check bounds the divergence rather than exercising both
definitions on real candidates.** `recall_rule_divergence_bound` measures the
boundary tie rate, which is the ceiling on how far ANN-Benchmarks' metric can
exceed an id-based intersection — the premise of task 012's layer-3
elimination. A stronger version would compute both definitions on the
candidates an actual index returns; `layers.recall_distance_based` is
implemented and tested for exactly that, but wiring it in means the blocking
check needs an index build, which would turn a two-minute gate into an
hour-long one. **Recorded, not wired.**

**`fixtures/glove-100-angular/ground_truth_distances.npy` was added by a
one-off script rather than a clean rebuild.** `calibrate fixture` now writes
it, but on Windows the 473 MB `vectors.npy` cannot be reopened for writing
while another process has it memory-mapped, which was the case. The array is
byte-identical either way (it is copied verbatim from the HDF5) and the
manifest was recomputed over all six artifacts, so the fixture is complete and
self-consistent; what was not exercised end to end is a *fresh* full build
from the updated builder. **Recorded.**

## Repo now contains

New:

    oneground/calibrate/layers.py            the three blocking checks
    tasks/scratch/012b-build-cost.py         determinism cost + byte-identity
    tasks/scratch/012b-build-cost.json       its measurements
    tasks/scratch/012b-add-distances.py      the one-off artifact addition
    fixtures/glove-100-angular/ground_truth_distances.npy
                                             published distances (gitignored,
                                             re-derivable; needed by the
                                             recall-rule check)

Changed:

    oneground/models/base.py                 single_threaded_faiss,
                                             resolve_deterministic,
                                             DETERMINISTIC_DEFAULT; the
                                             Determinism docstring now matches
                                             the code
    oneground/models/single_node_hnsw/model.py
                                             deterministic + add_chunk +
                                             progress; state records which
    oneground/models/test_conformance.py     4 tests; the old determinism test
                                             now says what it cannot catch
    oneground/calibrate/__init__.py          layers command; curve scope from
                                             the fixture; offsets; engine
                                             lines carry efSearch; build goes
                                             through MODEL.build
    oneground/calibrate/history.py           schema 3; efSearch required on
                                             engine lines
    oneground/calibrate/fixture.py           writes ground_truth_distances.npy
    oneground/calibrate/test_calibrate.py    24 tests
    fixtures/glove-100-angular.fixture.yaml  outcome_scope: advisory, the
                                             published offset, the new
                                             artifact, blocking/advisory
                                             verification blocks
    docs/MODELS.md                           "efSearch is not portable" with
                                             the measured ratio; a Build
                                             determinism section
    docs/VALIDATION.md                       what gates and what is recorded
    calibration/README.md                    blocking vs advisory; schema 3
    calibration/history.jsonl                appended only
    .github/workflows/calibration.yml        layers is the gate; the curve is
                                             labelled advisory in both jobs
    .gitignore                               the new large array

## Blocked on developer

Nothing is blocked. Three decisions are yours, and none was taken here:

1. **Whether to split deterministic/parallel by build purpose.** Proposed
   above with the measured cost (1.76× at 1.18 M vectors, 1.88× at 100 k,
   0.91× at 2 k). My recommendation is *not yet*: the penalty is modest where
   it applies and negative where it does not, the mechanism already exists if
   you want it, and the one case that could change the answer — a `simulate`
   sweep over arxiv-150k — has not been measured.

2. **Whether `hash_sharded` and `semantic_sharded` should be converted.** Both
   build faiss HNSW per shard and both are presumably non-deterministic for
   the same reason. The helper is in place; each needs its own cost
   measurement.

3. **Whether the calibration branch should carry the index cache policy.**
   `calibrate curve` now parks its built index under `.cache/indexes/`
   (~600 MB each). It exists because a 35-minute build was lost to a crash in
   the 2-minute search that followed. On a CI runner the cache is cold every
   time and the file is discarded, so it costs disk and nothing else — but if
   you would rather CI not write it, `run_curve(index_cache=False)` is the
   switch and it needs a flag on the command.

Nothing needs credentials, a pod, or money. **Total spend for this task: $0.**

One note on the environment rather than the work: for about ninety minutes
another Claude session was running task 013 in the main checkout, and this
laptop has 7.5 GB of RAM. One full-corpus build was killed outright and
another was contaminated. Both are described under Measurements, neither is in
a table as a measurement, and the numbers reported were taken on a quiet
machine. Worth knowing if two tasks are ever scheduled in parallel again.
