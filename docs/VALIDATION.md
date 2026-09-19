# Validation — how oneground checks itself, and where it cannot

oneground exists to replace folklore with measurement. That claim is worth
nothing unless the measuring instrument is itself measured, in public, on a
schedule, with its failures kept.

This document says what is validated, against what, how often, and — the part
most benchmark projects leave out — **which numbers have no external reference
at all**. Those are predictions, not validated measures, and they are labelled
as such everywhere they appear.

---

## What gates a release, and what merely gets recorded

Not everything measured here is a gate, and the split is deliberate.

**Blocking — `oneground calibrate layers`.** Three checks, each an assumption
that every recall this project publishes rests on, and each with a correct
answer known before the run:

| check | asks | correct answer | tolerance |
| --- | --- | --- | --- |
| `corpus_reachability` | is every published ground-truth neighbour inside the corpus we index? | 1.0 | 0.0 |
| `metric_agreement` | does exact inner product on normalized vectors reproduce the published angular ordering? | 1.0 | 0.001 |
| `recall_rule_accounting` | can ANN-Benchmarks' distance-based `knn` metric diverge from our id-based intersection? | ~0 | 0.01 |

The tolerances are tight because a real defect in any of them is not
marginal. Index with L2 instead of inner product, or forget to normalize, and
`metric_agreement` collapses toward zero — it does not drift to 0.999. There
is no regime in which one of these fails *slightly*.

**Advisory — `oneground calibrate curve`.** The comparison against published
hnswlib recall runs, is recorded, and never blocks. Task 012 measured it
contradicted at all seven points, and then eliminated every explanation except
one: faiss and hnswlib are different HNSW implementations. Gating oneground's
release on another project's implementation would be gating on the wrong
thing, so the difference is *published as an offset* instead — see
[MODELS.md](MODELS.md#efsearch-is-not-portable-across-implementations).

**The tolerance stayed at 0.02.** It would have been easy to widen it until
the points passed and call the layer green. That would have deleted the
finding. The points still read `contradicted`; what changed is that they no
longer pretend to be a gate on this project.

A healthy run is therefore: **three blocking checks green, seven advisory
contradictions recorded, workflow green.**

---

## The three layers

### Layer 1 — metrics against published definitions and published values

*Are we computing the thing the literature calls by this name, and do we get
the same answer someone else got?*

The check is `oneground calibrate curve`. It builds
`oneground.models.single_node_hnsw` — the module the simulator actually uses,
not a bespoke call written for the test — over the
[`glove-100-angular`](../fixtures/glove-100-angular.fixture.yaml) corpus,
sweeps `efSearch`, and compares recall@10 per point against the published
ANN-Benchmarks hnswlib curve.

What makes this a real check rather than a self-consistency test:

- **The corpus is not ours.** GloVe twitter.27B 100d, packaged by
  ANN-Benchmarks, downloaded by digest.
- **The ground truth is not ours.** It is the HDF5's `neighbors` array,
  recorded as `declared`. oneground does not recompute it; recomputing would
  replace the thing being checked against.
- **The reference is not ours.** Published recall values, extracted from the
  ANN-Benchmarks results page whose sha256 is recorded in the fixture spec.

Three things about that reference are worth knowing before reading any
outcome from it, because all three narrow what can be compared:

1. **ANN-Benchmarks publishes no results file.** Four candidate URLs were
   probed (`glove-100-angular_10_angular.csv`, `res.csv`, `results.csv`, the
   repo's `results.csv`); all 404. The numbers exist only as JavaScript inside
   the per-dataset HTML page, so that page *is* the results file and its
   digest is what the fixture records.
2. **The plotted series is a Pareto frontier, not a sweep.** Dominated points
   are dropped, and the frontier is recomputed per chart because it depends on
   the y-axis. The headline Recall/QPS chart shows one `M=16` point where the
   configuration actually ran nine.
3. **`efSearch` is not published.** A point's label carries `M` and
   `efConstruction` and nothing else. The ef grid
   (`10, 20, 40, 80, 120, 200, 400, 600, 800`) comes from ANN-Benchmarks'
   own `hnswlib/config.yml`, also recorded by digest.

`oneground/calibrate/reference.py` recovers what it can by unioning every
chart whose x-axis is plain Recall, and then **refuses anything ambiguous**: a
sweep is accepted only when the number of distinct recovered recall values
equals the number of ef values in the grid *and* the recalls are strictly
increasing, which makes the mapping forced. On this page exactly one
configuration qualifies — `M=12, efConstruction=500`. Assigning eight
recovered `M=96` points to the first eight ef values would produce something
that looked like a reference curve and was fiction.

**Consequence, stated plainly:** the configuration named in task 012's brief
(`M=16, efConstruction=200`) has no published counterpart at all —
ANN-Benchmarks runs every hnswlib group at `efConstruction=500`. That curve is
still measured, and every one of its points is `couldnt_check`. That is not a
pass and it is not a failure. It is a gap in the reference.

#### What this layer settled, and where it left the disagreement

The comparison came back contradicted at all seven points, one-signed: this
installation scored **higher** than published hnswlib by +0.036 to +0.064,
the gap shrinking as `efSearch` rose. Four layers could have owned that, and
three were eliminated by measurement — every published top-10 id is inside the
corpus (1.000000), exact inner product reproduces the published ordering
(1.000000 on 1,000 queries), and the two recall definitions cannot diverge by
more than the 0.0016 tie rate, in the direction that would *raise* upstream's
number rather than ours.

What is left is the index: **faiss at `efSearch = e` reaches the recall
hnswlib reached at roughly 1.4e to 1.9e**. Task 012b promoted the three clean
layers to the gate and made this comparison advisory, publishing the offset
rather than pretending it is a defect in either project. The full table and
its consequences are in
[MODELS.md](MODELS.md#efsearch-is-not-portable-across-implementations).

### Layer 2 — the simulator against real engines

*Does the architecture we simulated behave like the engine you would actually
deploy?*

The check is `oneground calibrate engine`. It runs `verify` against a real
engine — Qdrant or PostgreSQL + pgvector — on the same sample the simulator
scored, and records

    deviation = simulated recall@10 − measured recall@10

for the **matched configuration only**. Task 011 established the rule this
depends on: a measurement settles a verdict only for the option whose
`(family, params)` match what the engine reported building, read from
`index_params` rather than from what oneground asked for. Without that rule,
one measurement was being credited to eight architectures, seven of which were
never built in any engine.

This layer is where the charter's stop-condition lives:

> A family's simulator cannot be validated against its real-engine counterpart
> within tolerance — that family ships as couldn't-check until it can.

Today there are seven blocking data points, all on one family
(`single_node_hnsw[M=32,efConstruction=200,efSearch=128]`), across two engines
(Qdrant 1.19.1 and pgvector 0.8.6 on PostgreSQL 16.15):

| date | engine | dataset | deviation |
|---|---|---|---|
| 2026-09-10 | qdrant | arxiv-smoke | +0.00000 (×2) |
| 2026-09-10 | pgvector | arxiv-smoke | +0.00000 |
| 2026-09-11 | qdrant | arxiv-150k | −0.00190 |
| 2026-09-11 | pgvector | arxiv-150k | −0.00085 |
| 2026-09-13 | qdrant | arxiv-smoke | +0.00000 |
| 2026-09-13 | pgvector | arxiv-smoke | +0.00000 |

All `verified` against a 0.05 tolerance. **Seven lines on one family are still
a measurement rather than a trend**, most of them on a 2,000-vector smoke
corpus where the deviation is exactly zero because both the simulator and the
engine return every true neighbour. The two that carry information are the
arxiv-150k pair. No family is claimed validated by this layer, and the report
footer cites the latest line **per engine** rather than implying coverage by
silence — with "no calibration line for X" printed where there is none.

What the second engine buys is worth naming, because it is the point of having
more than one: this is a check on the *simulator*, not on the engines. On
arxiv-150k the simulator sat 0.0019 below Qdrant and 0.00085 below pgvector —
same sign, same order, two independent HNSW implementations. A simulator
systematically wrong about this family would have to be wrong against both by
the same amount to produce that, which is a harder coincidence than one
engine's agreement. It is still one family and one corpus.

### Layer 3 — load methodology against VectorDBBench — **not yet done**

*Is our throughput and latency methodology comparable to the field's?*

This layer is named here because it is missing, and a missing layer that is
not named reads as a layer that is not needed.

oneground's load generator (`oneground/verify/load.py`) is closed-loop with a
token bucket, excludes warm-up, reports percentiles and error rate, and
**never measures recall under load** — recall comes from a separate sequential
pass, so a query slowed or dropped under load can never be counted as a recall
miss. Those are defensible choices, and no one outside this project has
checked them.

The case to check them against is
[VectorDBBench](https://github.com/zilliztech/VectorDBBench)'s
**`Performance768D1M`** — *"Search Performance Test (1M Dataset, 768 Dim)"*,
Cohere 1M vectors at 768 dimensions, run at varying parallel levels, reporting
index build time, recall and **maximum QPS**.

It is the right case for three reasons: the dimensionality matches the arXiv
fixture this project already measures; it varies concurrency rather than
fixing it; and it reports a *ceiling* (max QPS).

**`qps_max` now exists** — task 017 implemented the ramped load phase task 011
declined to write, stopping on an error rate over 0.5% or a p99 over five
times the first rung's, and reporting the ceiling as its own row with its own
caveat. What has **not** changed is the thing this layer is about:

- `qps_max` is **never read by the `qps` verdict**. The engine's ceiling and
  the rate it sustained are different numbers and do not share a row; a test
  asserts the verdict cannot reach the ceiling.
- Neither number has been compared to anyone else's. `qps_max` is a ceiling
  *under this load shape on this host* — one namespace, this query set, this
  k, this client — and the row says so in those words.

So oneground's throughput numbers remain **sustain checks plus an
uncalibrated ceiling**, they say so in the decision log, and no claim is made
that either is comparable to a published QPS figure from anywhere else. That
is what Layer 3 would settle, and Layer 3 has not been run.

---

## Which measures are validated, and which are predictions

This is the table to read before quoting any number this tool produces.

| measure | how it is validated | status |
|---|---|---|
| `recall@k` | Layer 1, against published ANN-Benchmarks values on a corpus and ground truth we did not produce | **validated by reference** |
| `recall@k` vs a real engine | Layer 2, against Qdrant and pgvector on the user's own sample | **validated by reference**, a few data points on one family |
| intrinsic dimensionality (TwoNN) | estimator from Facco et al. 2017, implemented to the published definition | **definition published, value not** — measured 44.12 on glove-100-angular, no published TwoNN value to check it against; see below |
| `storage_amplification`, `fanout`, `shards`, copies percentiles | arithmetic over the simulated layout; re-derivable from the same receipts | **derived, not validated** — there is nothing external to compare to |
| `est_memory_bytes` | vector payload plus an HNSW graph term | **an estimate, and labelled one everywhere it is printed** |
| latency shape (p50/p95/p99) | measured, but only attributable when RTT is under 20% of query p95 | **environment-bounded**; see [VERIFY.md](VERIFY.md) |
| throughput (`qps`) | sustain check against an offered rate | **not comparable to published QPS** until Layer 3 runs |
| throughput ceiling (`qps_max`) | ramped until latency or errors break; opt-in | **measured, uncalibrated** — a ceiling under one load shape on one host, and never read by the `qps` verdict |
| latency spread across runs (`p95_across_runs`) | the load phase repeated with the engine restarted between runs | **measured**; the verdict is couldn't-check when the runs straddle the threshold |
| `truncated_count` | counted with the model's own tokenizer before embedding | **exact, or `null`** — `0` means nothing was cut, `null` means nothing looked |
| **boundary crispness** | — | **prediction. No external reference.** |
| **ambiguous query rate** | — | **prediction. No external reference.** |
| **drift** | — | **prediction. No external reference.** |

### The three predictions

Crispness, ambiguity and drift are this project's own definitions. Nobody
publishes a value for them, because nobody else computes them. They are
defined precisely in each fixture spec — thresholds, seeds, centroid counts
and all — so they are **re-derivable**, and two oneground installations must
agree on them to the stated tolerance. That is reproducibility, and it is not
the same thing as validation.

What they claim is predictive: that a corpus with low crispness and high
ambiguity is one where semantic sharding will lose. On arxiv-150k that
prediction was made (crispness 0.036, ambiguity 0.891) and then borne out
(semantic-sharded 0.932 recall at 3.7× storage, against 0.997 at 1×).

Task 016 made the same prediction **in advance on a second corpus**, and this
is the part that matters more than the outcome: `stackexchange-150k`'s spec
was committed with every value `TO_BE_FILLED` before the build ran, so the
answer could not be steered. It came out blurrier (crispness 0.011, ambiguity
0.908) and semantic sharding lost by more (0.869 at 3.9×). The prediction
held. The drift measure disagreed in sign between the two corpora
(0.522→0.549 against 0.485→0.450), which is a finding rather than a
failure — and it is the reason drift is still a prediction here.

**Two corpora are two corpora.** The direction is consistent so far; that is
not the same as validated. Until the same prediction is registered in advance
and checked on several corpora with genuinely different characterizations,
these three measures are hypotheses with numbers attached, and this project
will keep saying so.

### Intrinsic dimensionality: a definition without a public value

TwoNN is a published estimator (Facco, d'Errico, Rodriguez, Laio, 2017), and
`oneground/measures/lid.py` implements that definition. What does not exist,
as far as task 012's search found, is a published **TwoNN** estimate for
GloVe-100 to compare our number against.

There is closely related published work — Aumüller & Ceccarello, *The Role of
Local Intrinsic Dimensionality in Benchmarking Nearest Neighbor Search*
(SISAP 2019, arXiv:1907.07387), Table 1 — which reports for this exact dataset
an **average LID of 18.0** (median 17.8). But it uses the
**maximum-likelihood (Levina–Bickel / Amsaleg) estimator computed from each
point's 100 nearest neighbours and then averaged**: an averaged *local*
estimate at k=100. TwoNN is a *global* estimate built from the ratio of
second- to first-nearest-neighbour distances — effectively k=2.

The two probe different scales and are not interchangeable. This installation
measures TwoNN = **44.12** on the same corpus. The gap to 18.0 is what two
different estimators at two different neighbourhood scales are expected to do,
not evidence about either implementation, so the fixture records
`reference: null` and `couldnt_check` and cites 18.0 as context marked
`comparable: false`.

So the fixture records our measured value with `reference: null` and
`reference_outcome: couldnt_check`, and names the reason. A number invented to
fill that field would be worse than the gap.

---

## What produced an artifact

Every artifact this project writes records the **version and commit that
produced it**, in a field called `oneground`:

    "oneground": {"version": "0.1.0",
                  "commit": "43123b4d458d…" | null,
                  "dirty": true | false | null,
                  "source": "checkout" | "wheel" | "unknown",
                  "note": "<why commit is null, when it is>"}

It is written into the **declared** half of each pair — `build_info.json`,
`simulate_info.json`, `verify_info.json`, `propose_info.json`,
`state/state_info.json`, `report.json`, and every calibration line — and not
into the receipts, because a receipt is what was measured and this is a fact
about the process that measured it. Task 020b made the same ruling about
timings for the same reason, which is why `simulate.json` carries no
`build_seconds`.

**One exception, and it is deliberate.** A proposal card carries *two*: the
version that measured the baseline row and the version that measured the
changed row. A card's whole claim is a difference between two rows, and the
statement that the difference is real rather than a difference of code needs
both.

**`commit: null` is a real answer.** An installed wheel has no git, so the
build hook in `setup.py` writes what it was built from and a wheel answers as
confidently as a checkout. Where neither is possible — a source tree with no
git, a checkout whose git cannot be run — the field is `null` and `note` says
which, in the same habit as every other couldn't-check in this project. **A
consumer may not read a missing or null version as a match.**

**What it never carries:** a branch, a remote, a tag or a build path. A
version and a commit are facts about the code; the others name whose machine
it was, which is what the identifier scan exists to keep out of artifacts.

An artifact written before this was recorded has no such field, and nothing
can add one honestly. It reads as couldn't-check — never as a match, and
never as a mismatch.

## Cadence

| trigger | job | what gates | what is also recorded |
|---|---|---|---|
| change to `requirements.txt`, an adapter, a pinned engine version, or the calibration code | `pins` | unit tests, `calibrate layers`, simulator-vs-engine | the advisory hnswlib curve |
| Monday 06:00 UTC | `weekly` | the same, against current pins | the same |
| 1st of the month 07:00 UTC | `drift` | **nothing** — the whole job is advisory | simulator-vs-engine against `qdrant:latest` |

Defined in [`.github/workflows/calibration.yml`](../.github/workflows/calibration.yml).

The rules, which are the same rules the rest of the project uses:

- A `contradicted` outcome on a **blocking check** fails the workflow and
  opens an issue carrying the offending history line in the body. An
  **advisory** contradiction does neither: it is appended to the history,
  shown by `oneground calibrate show` with an `[advisory]` marker, and never
  displaces a blocking line as the latest outcome for its check.
- **`couldnt_check` never fails anything.** It is a gap in the reference, not
  a defect in this installation. It appears in the history as a gap and in
  `oneground calibrate show` as an outcome.
- The **advisory** monthly job runs against a moving tag and can never block.
  A moving tag is not the contract; the pinned run is. It exists so that a
  breaking upstream change is visible *before* a pin bump walks into it.
- **The harness never writes to master.** Appended lines are committed to the
  `calibration` branch, which master merges from. A scheduled bot cannot move
  the branch a release is cut from.
- **No tolerance is ever widened to clear a contradiction.** If a check goes
  red, the job is to find which layer moved — pins, engine, corpus digest, or
  the simulator — and record the decomposition.

The corpus is fetched by digest on every run
([`.github/scripts/fetch-glove.sh`](../.github/scripts/fetch-glove.sh)). If
upstream silently re-uploads the file, the run fails loudly rather than
producing a recall shift that would read as drift in this tool.

---

## The history

Every check appends one line per point to
[`calibration/history.jsonl`](../calibration/history.jsonl), and

    oneground calibrate show

renders it as a table with the latest outcome per check.

Two properties make the file worth trusting:

**Outcomes are derived at write time**, from `deviation` and `tolerance`, and
`validate()` refuses a line whose stated outcome does not follow from its own
numbers. A tolerance changed next year cannot silently re-judge a line written
today.

**The file is append-only.** A point measured wrongly is corrected by a later
line saying so, never by an edit. That held across task 012's own schema
change: the line task 011 seeded is *translated on read*, not migrated on
disk, and the original bytes are still there.

---

## What a reader can re-run

Nothing here requires credentials, a pod, or money. It needs about 500 MB of
download, roughly 1.5 GB of disk and, on a four-core laptop, about twenty
minutes for the index build.

```sh
# 1. the corpus (463 MB), checked against the digest in the fixture spec
GLOVE_SHA256=544af1d5e84e112cd4749571dcfd8ca109818a572f850af75a3a09e093a953c4 \
  bash .github/scripts/fetch-glove.sh

# 2. build the calibration fixture, and check that our metric convention
#    reproduces the published neighbour ordering before trusting any recall
oneground calibrate fixture \
  --source .cache/glove-100-angular.hdf5 --check-metric

# 3. the BLOCKING checks -- this is the gate, and it should come back green
oneground calibrate layers --fixture glove-100-angular

# 3b. Layer 1, ADVISORY: the hnswlib comparison. Expected to be contradicted
#     at every point; it publishes the per-efSearch implementation offset and
#     cannot fail the run.
oneground calibrate curve --fixture glove-100-angular \
  --config M=12,efConstruction=500

# 3c. the configuration with no published counterpart; every point
#     couldnt_check, on purpose
oneground calibrate curve --fixture glove-100-angular \
  --config M=16,efConstruction=200

# 4. Layer 2: the simulator against a real engine (needs Docker)
oneground calibrate engine requirements.smoke.yaml --engine qdrant

# 5. the history
oneground calibrate show
```

To point step 4 at an engine that is already running, set
`ONEGROUND_QDRANT_URL` and no container is composed.

To see for yourself what the ANN-Benchmarks page does and does not publish:

```sh
oneground calibrate reference --page .cache/glove_page.html
```

---

## Related

- [VERIFY.md](VERIFY.md) — what a verify run can and cannot attribute, the
  same-environment rule, and eight incident records
- [MODELS.md](MODELS.md) — the family interface, and why `ceiling` is required
- [CHARTER.md](CHARTER.md) — including the three conditions that would make
  this project stop or change course
- [`calibration/README.md`](../calibration/README.md) — what a history line
  means and when two lines are comparable
