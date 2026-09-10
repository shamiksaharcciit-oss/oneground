# Report: 012-calibration

## Repo state expected vs found

Expected, from the brief: task 011 on master; `calibration/history.jsonl`
seeded with one line (−0.0018, Qdrant 1.19.1, pod `tf8sd2usxbblsm`,
2026-09-10) and a README.

Found: exactly that. Branch `task-012` at `e09bde9` (master merged in), tree
clean, one seeded history line with those values, `calibration/README.md`
present. The brief itself was absent on the first attempt at this task and the
blocked report has been replaced by this one.

**Two of the brief's own assumptions did not survive contact with the upstream
data.** Both were measured before anything was built on them, both changed
what got built, and both are the substance of this task:

1. **The corpus cannot be a 100k prefix.** The published ground truth indexes
   the full train split.
2. **There is no published hnswlib curve at `efConstruction=200`.**
   ANN-Benchmarks runs every hnswlib group at 500.

A third, smaller correction: the licence is PDDL, not CC BY-SA.

Details and numbers under Measurements. Nothing was widened, and no gate was
moved, to work around either.

## What was done

All eight steps of the brief, with the two forced deviations above.

**1. Calibration fixture** — `fixtures/glove-100-angular.fixture.yaml` and
`oneground/calibrate/fixture.py`, built from the ANN-Benchmarks HDF5. Ground
truth is `declared`: taken verbatim from the file's `neighbors` array, never
recomputed. `--check-metric` confirms our metric convention reproduces the
published neighbour ordering before any recall is trusted.

**2. Reference curve** — `oneground calibrate curve`, comparing
`oneground.models.single_node_hnsw` (the module the simulator actually uses,
not a bespoke faiss call) against published hnswlib recall@10 per efSearch.
`oneground/calibrate/reference.py` recovers the published points and refuses
the ambiguous ones.

**3. LID reference** — TwoNN on the corpus, literature searched, result
recorded as `couldnt_check` with the near-miss cited and marked not
comparable.

**4. Simulator-vs-engine** — `oneground calibrate engine`, which runs `verify`
locally against the pinned Qdrant and appends the line rather than leaving it
to be transcribed by hand, which is how the first one got there.
`ONEGROUND_QDRANT_URL` points it at an already-running engine.

**5. History schema** — `oneground/calibrate/history.py`. Outcomes derived at
write time, append-only, `oneground calibrate show` renders it.

**6. CI** — `.github/workflows/calibration.yml`, three triggers as three jobs,
plus `.github/scripts/fetch-glove.sh` and a composite action that pushes to a
`calibration` branch and opens an issue on a contradiction.

**7. Docs** — `docs/VALIDATION.md`, linked from `README.md`.

**8. Report wiring** — `oneground report` now cites the calibration it was
generated under, per engine and per recommended family, or says there is none.

## Measurements

### The two brief assumptions, measured

**Step 1 — a 100k prefix is not a corpus, it is a truncation.** Method:
`tasks/scratch/012-inspect-glove.py`, reading the downloaded HDF5 directly.

| | |
| --- | --- |
| train split | **1,183,514** × 100 (not 100,000) |
| published `neighbors` index range | 0 … 1,183,513 |
| GT neighbours with index < 100,000 | **0.084673** |
| queries whose entire top-10 is < 100,000 | **0.000000** (0 of 10,000) |
| mean count of a query's top-10 < 100,000 | **0.8617** of 10 |

So indexing the first 100,000 vectors and scoring against the published
ground truth caps recall@10 at about **0.086** whatever the index does. Every
point of the reference curve would have read ~0.086, and the comparison to a
published curve running 0.36–0.96 would have been a contradiction manufactured
entirely by the setup.

The fixture therefore holds the **full train split**. `--subset` is kept so
the arithmetic can be re-run, `build_info.json` records
`published_top10_fully_reachable` on every build (**1.000000** for the real
fixture), and `calibrate curve` refuses to run against a corpus that cannot
reach its own ground truth rather than reporting the truncation as a recall.

Consequence for naming: "GloVe-100" is 100 *dimensions*, not 100k vectors, so
the brief's `glove-100k` would have named a 1.18M-vector fixture. The fixture
is `glove-100-angular`, matching the upstream dataset name, so a reader
comparing our numbers to ann-benchmarks.com sees the same name on both sides.
**This renames a deliverable the brief named; flagged here rather than done
quietly.**

**Step 2 — what ANN-Benchmarks actually publishes.** Three findings, each of
which narrows what can be compared:

- *No results file exists.* Probed `glove-100-angular_10_angular.csv`,
  `res.csv`, `results.csv`, and the repo's `results.csv`. All 404. The numbers
  live only as JavaScript inside the per-dataset HTML page, so **the page is
  the results file** and its sha256 is what the fixture records.
- *`efConstruction` is 500, never 200.* From
  `ann_benchmarks/algorithms/hnswlib/config.yml`: all nine run groups set
  `efConstruction: 500`, sharing
  `query_args: [[10, 20, 40, 80, 120, 200, 400, 600, 800]]`. The brief's
  efSearch grid is the first seven of that list and is correct; its
  `efConstruction=200` has no published counterpart at all.
- *The plotted series is a Pareto frontier, not a sweep, and `efSearch` is not
  in the labels.* A label reads `hnswlib ({'M': 12, 'efConstruction': 500})`
  and nothing more.

Recovery method and result. The page draws thirteen charts and recomputes the
frontier per chart, so a point dominated on QPS can survive on build time.
Taking the union over every chart whose x-axis is plain `Recall` (excluding
the `Relative Error` and `Epsilon * Recall` charts):

| M (efC=500) | published points recovered | of a 9-value ef grid |
| --- | --- | --- |
| 4 | 2 | incomplete |
| 8 | 3 | incomplete |
| **12** | **9** | **complete** |
| 16 | 1 | incomplete |
| 24 | 7 | incomplete |
| 36 | 6 | incomplete |
| 48 | 3 | incomplete |
| 64 | 7 | incomplete |
| 96 | 8 | incomplete |

Exactly one configuration is fully determined: **M=12, efConstruction=500**,
nine strictly increasing recall values against nine ef values. Recall is
monotone in ef, so that mapping is forced. `reference.py` accepts a sweep only
when the counts match *and* the recalls strictly increase, and otherwise
yields no reference points — aligning eight recovered M=96 points to the first
eight ef values would look like a reference curve and be fiction.

Digests recorded in the fixture spec:

    corpus HDF5     544af1d5e84e112cd4749571dcfd8ca109818a572f850af75a3a09e093a953c4  (485,413,888 bytes)
    results page    00967aecd518cb6172be4a29f11c85cd16d30d58ae5a6b7462dad73e15566ca5
    hnswlib config  ff836e262140caae7cbee8825ef454b877f8c58e288ea8e1c50b300b39148521

**Licence.** The brief says CC BY-SA. Verified otherwise: ANN-Benchmarks'
`datasets.py::glove` builds this dataset from `glove.twitter.27B.zip`, and
Stanford NLP's GloVe README states the pre-trained vectors are released under
the **Public Domain Dedication and License (PDDL)**; the ANN-Benchmarks
harness itself is MIT. Recorded as PDDL. The fixture redistributes no vectors
in any case — the arrays are re-derived locally from the digest-checked HDF5.

### The fixture

Built by `oneground calibrate fixture --source .cache/glove-100-angular.hdf5
--check-metric` on this laptop (Windows 11, Python 3.12.10, 4 cores).

| | |
| --- | --- |
| corpus | 1,183,514 × 100 float32, L2-normalized |
| queries | 10,000 × 100, from the HDF5 `test` split |
| ground truth | 10,000 × 100 int64, **declared**, not recomputed |
| raw vector norms | 2.1658 … 11.4011 (not normalized upstream) |
| TwoNN intrinsic dimensionality | **44.1248** of 100 declared |
| build time | ~2 min (normalize + write + characterize) |

**Metric convention, checked rather than assumed.** ANN-Benchmarks calls the
dataset `angular` and ships unnormalized vectors; we store unit vectors and
search with `METRIC_INNER_PRODUCT`. Exact inner-product top-10 over the whole
corpus, compared to the published neighbours:

    200 queries (fixture build)      agreement 1.000000
    1,000 queries (decomposition)    agreement 1.000000

This is the single most load-bearing number in the task. It says our corpus,
our ground-truth alignment and our metric convention are exactly upstream's,
so any deviation found later belongs somewhere else.

### The reference curve — all seven points contradicted

`oneground calibrate curve --fixture glove-100-angular --config
M=12,efConstruction=500`. Index build 1,183,514 vectors in ~19 min; 10,000
queries per efSearch point; recall@10 against the published ground truth.

| efSearch | measured | published | deviation | tolerance | outcome |
| --- | --- | --- | --- | --- | --- |
| 10 | 0.42900 | 0.36534 | **+0.06366** | 0.02 | contradicted |
| 20 | 0.55882 | 0.49515 | **+0.06367** | 0.02 | contradicted |
| 40 | 0.67047 | 0.60777 | **+0.06270** | 0.02 | contradicted |
| 80 | 0.75812 | 0.70371 | **+0.05441** | 0.02 | contradicted |
| 120 | 0.80021 | 0.75057 | **+0.04964** | 0.02 | contradicted |
| 200 | 0.84412 | 0.79998 | **+0.04414** | 0.02 | contradicted |
| 400 | 0.88980 | 0.85386 | **+0.03594** | 0.02 | contradicted |

**The brief's acceptance criterion — "all seven points verified within 0.02" —
is not met. Nothing was widened.** The brief's own instruction covers this
case: *"a real disagreement is a finding, not a reason to widen tolerance"*,
and the decomposition follows.

Every deviation is positive: this installation scores **higher** than
published hnswlib at the same nominal parameters, by 3.6 to 6.4 points, and
the gap shrinks monotonically as efSearch rises.

### Decomposition — which layer owns the gap

Method: `tasks/scratch/012-curve-decomposition.py`, which imports project code
unmodified and eliminates the layers in order.

| layer | check | result | owns the gap? |
| --- | --- | --- | --- |
| corpus | is every published top-10 id inside the indexed corpus? | reachable share **1.000000** | no |
| metric | does exact normalized IP reproduce the published ordering? | agreement **1.000000** on 1,000 queries | no |
| recall rule | does our definition differ from ANN-Benchmarks' `knn`? | see below | no |
| **index** | faiss `IndexHNSWFlat` vs hnswlib | everything above leaves | **yes** |

On the recall rule: ANN-Benchmarks' `knn` metric is *distance-based* — a
returned neighbour counts when its distance is within epsilon of the true
k-th distance — which is tie-generous and can only make **their** number
larger than an id-based intersection. It cannot explain ours being larger. The
tie rate is small in any case: queries whose 10th and 11th true distances
coincide, **0.0016**.

So the deviation is entirely in the index layer, and it is worth stating as
something sharper than "implementations differ". Interpolating the published
curve to ask *at what efSearch would hnswlib have reached our recall*:

| our efSearch | our recall | their equivalent efSearch | ratio |
| --- | --- | --- | --- |
| 10 | 0.42900 | ~14 | 1.4× |
| 20 | 0.55882 | ~30 | 1.5× |
| 40 | 0.67047 | ~63 | 1.6× |
| 80 | 0.75812 | ~130 | 1.6× |
| 120 | 0.80021 | ~201 | 1.7× |
| 200 | 0.84412 | ~353 | 1.8× |
| 400 | 0.88980 | ~740 | 1.9× |

**faiss `IndexHNSWFlat` at efSearch = e reaches the recall hnswlib reached at
roughly 1.4e to 1.9e**, and the multiplier grows with e. A nominal efSearch
buys measurably more search in one implementation than the other. That is the
finding, and it is a substantive one for this project: `efSearch` is not a
portable number, so a simulated recall at a given efSearch does not predict an
engine's recall at the same efSearch unless the engine uses the same HNSW
implementation.

What this decomposition does **not** separate is stated under *Observed, not
done*: whether the residual is faiss-vs-hnswlib as implementations, or
faiss-now vs the older hnswlib build ANN-Benchmarks ran. Both live in the
index layer.

### The brief's configuration — M=16, efConstruction=200

Run because the brief named it, and every point is `couldnt_check` because
ANN-Benchmarks never ran hnswlib at `efConstruction=200`.

| efSearch | measured | published | outcome |
| --- | --- | --- | --- |
| 10 | 0.48025 | none | couldnt_check |
| 20 | 0.60699 | none | couldnt_check |
| 40 | 0.70924 | none | couldnt_check |
| 80 | 0.79124 | none | couldnt_check |
| 120 | 0.82900 | none | couldnt_check |
| 200 | 0.86684 | none | couldnt_check |
| 400 | 0.90922 | none | couldnt_check |

Exit code **0**: `couldnt_check` never fails, by design and by test.

Worth noting beside the M=12 curve, since both were measured on the same
corpus: `M=16, efConstruction=200` beats `M=12, efConstruction=500` at every
efSearch (0.48025 vs 0.42900 at ef=10; 0.90922 vs 0.88980 at ef=400). On this
corpus more graph degree buys more than more construction effort. That is a
measurement, not a recommendation, and it is not compared to anything
published because nothing published exists at either setting to compare it to.

### Simulator against a real engine

`oneground calibrate engine requirements.smoke.yaml --engine qdrant`, which
composes the pinned `qdrant/qdrant:v1.19.1`, runs `verify`, and appends the
line. arxiv-smoke, 2,000 vectors, dim 768.

| | |
| --- | --- |
| config (matched) | `single_node_hnsw[M=32,efConstruction=200,efSearch=128]` |
| simulated recall@10 | 1.00000 |
| measured recall@10 (Qdrant 1.19.1) | 1.00000 |
| deviation | **+0.00000** |
| tolerance | 0.05 |
| outcome | **verified** |

The configuration is the matched one — the engine built exactly
`M=32, efConstruction=200, efSearch=128` and the simulator row scored is that
row, per task 011's same-configuration rule.

**This number is easy and should be read as such.** 2,000 vectors is small
enough that HNSW is effectively exact at efSearch=128, so both sides sit at
1.0 and the check confirms the *mechanism* works end to end rather than
resolving anything about the simulator. The meaningful engine calibration
point in the history is still task 011's arXiv-150k line (−0.0018 on 150,000
vectors), and that one carries no tolerance, so it reaches no verdict. Layer 2
has one real data point and this is not a second one.

**Also run and recorded:** `ONEGROUND_QDRANT_URL` was implemented as the
brief specifies (point the run at an already-running engine, compose nothing);
the local Docker path is what was exercised here.

### Intrinsic dimensionality — a definition without a public value

Measured: **TwoNN = 44.1248** (seed 20260910, 20,000-point sample, 10%
discard), on the same corpus.

A published LID value for this exact dataset exists: **18.0 average** (median
17.8), Aumüller & Ceccarello, *The Role of Local Intrinsic Dimensionality in
Benchmarking Nearest Neighbor Search*, SISAP 2019, Table 1 (arXiv:1907.07387).

It is **not a reference for our number**, and is recorded as such. That paper
uses the maximum-likelihood (Levina–Bickel / Amsaleg) estimator computed from
each point's **100 nearest neighbours and then averaged** — an averaged
*local* estimate at k=100. TwoNN is a *global* estimate from the ratio of
second- to first-nearest-neighbour distances, effectively k=2. The two probe
different neighbourhood scales, and a deviation between them would be a
statement about estimators, not about this installation.

No published **TwoNN** estimate for GloVe-100 was found. The fixture records
`reference: null`, `reference_outcome: couldnt_check`, and cites 18.0 in a
`related_published_value` block marked `comparable: false`. A number invented
to fill that field would be worse than the gap.

## Verification

**Test suite.** `python -m pytest -q`: **338 passed, 1 skipped, 1 failed** in
46.5 s (was 302 passed before this task; 36 tests added). The skip is the live
RunPod test with no key. The one failure is
`test_the_real_arxiv_workdir_gives_one_option_the_measurement`, which reads
the gitignored `runs/arxiv-150k-via-characterize/` — absent in this worktree.
Reported in the blocked 012 report, and the developer has routed it to the
master stream, so it is untouched here.

**Against the brief's acceptance list.**

- *"GloVe curve: all seven points verified within 0.02 (or the contradiction
  reported with the decomposition — a real disagreement is a finding, not a
  reason to widen tolerance)."* — **The second branch.** Seven of seven
  contradicted; the decomposition is above and isolates the index layer,
  quantified as an efSearch-equivalence of 1.4× to 1.9×. The tolerance is
  still 0.02 in the fixture and nothing was moved.
- *"`history.jsonl` has the GloVe lines and the smoke engine line; `show`
  renders them."* — Yes. 16 lines: the seeded task-011 line, 7 `glove_curve`
  contradicted (M=12/efC=500), 7 `glove_curve` couldnt_check (M=16/efC=200),
  1 `simulator_vs_engine` verified. `oneground calibrate show` renders the
  table and the latest outcome per check.
- *"Workflow file validates (`act` or a dry run); the three triggers are
  distinct jobs."* — Both YAML files parse; jobs are `pins`, `weekly`,
  `drift`, with mutually exclusive conditions (`event_name != 'schedule'`;
  `schedule == '0 6 * * 1'`; `schedule == '0 7 1 * *'`). **`act` was not
  run** — it is not installed and installing it was not in scope — so this is
  a parse-and-inspect dry run, not an execution. Stated rather than implied.
- *"VALIDATION.md exists and names the VectorDBBench case as not yet done."* —
  Yes: `Performance768D1M` ("Search Performance Test (1M Dataset, 768 Dim)",
  Cohere 1M × 768, varying parallel levels, reports max QPS), named as Layer 3
  and marked not yet done, with the link to task 011's unimplemented `qps_max`.

**Against the brief's "Do not" list.** No tolerance was widened. The
ANN-Benchmarks ground truth was not recomputed — the fixture stores their
`neighbors` array verbatim and marks it `declared`; the only exact k-NN run on
this corpus was a 200- and 1,000-query metric-convention check whose result is
discarded, and a subset truth inside the determinism scratch script, neither
of which enters the fixture. No pod was created. No arxiv-150k artifact was
touched.

**Reproducibility of the curve — measured, and it is not clean.**
`tasks/scratch/012-determinism.py` builds the same index twice from the same
(vectors, config, seed) on 200,000 vectors and compares:

| efSearch | recall A | recall B | \|Δrecall\| | share of returned ids differing |
| --- | --- | --- | --- | --- |
| 10 | 0.485550 | 0.480900 | **0.004650** | 0.3683 |
| 40 | 0.718300 | 0.719250 | 0.000950 | 0.2539 |
| 200 | 0.883000 | 0.883650 | 0.000650 | 0.1446 |

`oneground/models/base.py` states: *"Two builds from the same (vectors,
config, seed) are expected to produce the same measurements."* For
`single_node_hnsw` that is **not true** — faiss adds to the HNSW graph under
OpenMP, and thread scheduling changes the graph. Two consequences, both
stated rather than assumed:

1. **The contradiction survives it comfortably.** Build-to-build drift is at
   most 0.0047; the deviations being reported are 0.036 to 0.064, eight to
   fourteen times larger and all one-signed. The finding is not build noise.
2. **The CI gate has less headroom than it looks.** At efSearch=10 the drift
   is 23% of the 0.02 tolerance. That will not flap the M=12 comparison, whose
   deviation is 3.2× the tolerance, but a future check calibrated close to its
   band could flap. Recorded under *Observed, not done*.

**Couldn't-check.**

- *Whether the index-layer gap is faiss-vs-hnswlib or faiss-vs-a-stale-run.*
  See *Observed, not done*; it needs hnswlib installed and a comparison run.
- *Whether the CI workflow runs green on GitHub.* It has never executed. The
  jobs were validated by parsing, not by running, and the GloVe steps in
  particular (463 MB download, ~19 min index build) have only been exercised
  as local commands.
- *Whether the published ANN-Benchmarks numbers are current.* They are
  `declared` with the page digest and retrieval date recorded. The page states
  no run date for the hnswlib series.
- *Whether the two `pins_sha256` values in this task's history lines matter.*
  The seven M=12 lines carry the `requirements.txt` digest as it stood before
  `h5py` was pinned (`f0f9d6c7…`); the eight later lines carry the digest
  after (`95411c6b…`). The field records the file's state at write time and
  does so correctly. `h5py` is imported only by `calibrate fixture`, never by
  the curve or the engine check, so the pin does not bear on any measurement
  here, and `comparable()` does not key on `pins_sha256`. Not re-run: a
  20-minute rebuild to make a bookkeeping field cosmetically uniform would
  have bought nothing, and given the determinism result above it would not
  even have reproduced the same numbers.

## Observed, not done

**The residual inside the index layer is not split.** The decomposition
establishes that corpus, metric convention and recall definition are all
exactly upstream's, so the +0.036…+0.064 belongs to the index. It does not
separate two candidates inside that layer: faiss-vs-hnswlib as implementations,
versus this faiss build versus whatever hnswlib version ANN-Benchmarks ran,
whenever they ran it. Settling it means `pip install hnswlib`, building the
same M=12/efConstruction=500 index over the same 1.18M vectors, and sweeping
the same ef grid — about 25 minutes and one dependency that would exist only
for diagnosis. It would convert "our HNSW differs from their published run"
into either "our HNSW differs from hnswlib" or "their published run is stale",
which are different problems with different fixes. **Not done: no brief names
it, and it adds a dependency.**

**0.02 was specified for a narrower thing than it is being asked to absorb.**
The brief set the tolerance for "implementation and build-order noise between
faiss HNSW and hnswlib". The measured cross-implementation difference is 1.8×
to 3.2× that at every point and systematically one-signed, which is not noise.
Whether the right response is a wider band, a per-ef band, or comparing
recall-at-matched-effort instead of recall-at-matched-efSearch is a product
decision. **Nothing was changed; the tolerance in the fixture is still 0.02
and the seven lines still read `contradicted`.**

**An MLE LID estimator would turn a couldnt_check into a real check.** There
is a published LID value for this exact corpus (18.0) and the only reason it
cannot be used is that oneground implements TwoNN and the paper used MLE over
100-NN. Implementing that estimator is perhaps ten lines, but *which* LID
oneground reports is a characterization decision with a schema, a fixture
field and a docs entry behind it. **Recorded, not done.**

**`single_node_hnsw` builds are not deterministic, and `models/base.py` says
they are.** Measured: two builds from the same (vectors, config, seed) on
200,000 vectors differ in 37% of returned ids at efSearch=10 and move recall
by up to 0.0047 (table under Verification). faiss adds under OpenMP and thread
scheduling changes the graph. This does not threaten the curve's finding —
0.0047 against deviations of 0.036–0.064 — but it means the CI gate's headroom
at efSearch=10 is 4×, not the ∞ that a deterministic build would give, and it
means the interface docstring's determinism promise is not kept by the family
that most depends on it. Fixing it (a single-threaded build path, or a
softened promise plus a documented per-point noise floor) touches the model
interface contract. **Recorded, not done.**

**`fixtures/arxiv-smoke/vectors.npy` had to be brought into this worktree.**
It is gitignored, so `characterize` on the smoke corpus could not run in a
fresh worktree. It was copied from the main checkout and its sha256 verified
against the committed `MANIFEST.sha256`
(`d9f44ded9e68af7495544c9a90da5bfee3798204f77ce0efbd219508268d7a6e`, matches).
This is the same class of issue as the `runs/` test the developer has routed
to the master stream, and it is left alone here.

**`report`'s calibration footer prints no family line when nothing is
recommended.** With no recommendation there is no family to cite, so the
footer carries only the engine statement. Correct, but worth a look if the
footer is ever expected to enumerate every family that ran.

## Repo now contains

New:

    oneground/calibrate/__init__.py          curve, engine, show, fixture, reference
    oneground/calibrate/history.py           schema, append-only writer, renderer
    oneground/calibrate/reference.py         published-point recovery, and its refusals
    oneground/calibrate/fixture.py           GloVe fixture builder + metric check
    oneground/calibrate/test_calibrate.py    34 tests
    fixtures/glove-100-angular.fixture.yaml  the calibration fixture spec
    fixtures/glove-100-angular/              build_info, characterization, MANIFEST
                                             (arrays gitignored, 486 MB, re-derivable)
    docs/VALIDATION.md                       the three layers; what is prediction
    .github/workflows/calibration.yml        three triggers, three jobs
    .github/scripts/fetch-glove.sh           corpus fetch with digest refusal
    .github/actions/record-calibration/action.yml
                                             calibration-branch push, issue on contradiction
    tasks/scratch/012-inspect-glove.py       the step-1 measurement
    tasks/scratch/012-curve-decomposition.py the layer decomposition
    tasks/scratch/012-determinism.py         two builds, same inputs, compared
    tasks/scratch/012-hnswlib-series.txt     the raw recovered published points

Changed:

    oneground/cli.py              `calibrate` dispatched like `fixture` and `pod`
    oneground/verify/__init__.py  target_override / endpoint_override for calibrate engine
    oneground/report/__init__.py  calibration footer, cited per engine and per family
    oneground/report/html.py      footer renders the citation instead of a placeholder
    oneground/report/test_verdict.py  the placeholder assertion replaced by the contract
    calibration/README.md         the task-012 schema, the four rules, the two eras
    calibration/history.jsonl     appended only
    requirements.txt              h5py==3.16.0 (new; requires only numpy)
    README.md                     links docs/VALIDATION.md
    .gitignore                    the two large glove arrays, scoped to that fixture

## Blocked on developer

Nothing is blocked. Four decisions are the developer's rather than mine, and
all four are recorded above rather than taken here:

1. **The fixture is named `glove-100-angular`, not `glove-100k`, and holds
   1,183,514 vectors rather than 100,000.** Forced by the published ground
   truth (0 of 10,000 queries keep their top-10 in a 100k prefix). Rename it
   if you disagree; the id appears in the spec filename, in `dataset` on every
   `glove_curve` line, and in `docs/VALIDATION.md`.

2. **The GloVe curve is red and will stay red.** Seven blocking
   `contradicted` lines are committed, so the `pins` and `weekly` CI jobs
   would fail on their first run and open an issue. That is the harness
   working as specified. If it should not gate a release until the index-layer
   question is settled, the lever is `--advisory` on that job — *not* the
   tolerance.

3. **Whether to settle the index-layer residual.** ~25 minutes and one
   diagnostic dependency (`hnswlib`) separate "our HNSW differs from hnswlib"
   from "ANN-Benchmarks' published run is stale". Different problems, different
   fixes.

4. **Whether `efSearch` should be treated as portable at all.** The measured
   1.4×–1.9× equivalence between faiss and hnswlib at the same nominal
   `efSearch` bears directly on the simulator's premise: a simulated recall at
   a given `efSearch` predicts an engine's recall at that `efSearch` only when
   the engine shares the implementation. Qdrant uses its own HNSW. Task 011's
   arXiv calibration point (−0.0018) suggests the effect is small there, but
   that is one point at one setting.

Also for a future task, not blocking: `oneground/models/base.py` promises
build determinism that `single_node_hnsw` does not deliver (measured above).
The docstring and the model disagree; which one should move is not a decision
this task should make.

Nothing needs credentials, a pod, or money. Total spend for this task: **$0**.
