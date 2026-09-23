# Report: 044-crispness-distribution

## Repo state expected vs found

Expected, and found:

- `CRISP_RATIO = 1.20` and `N_CENTROIDS = 256` in
  `oneground/measures/crispness.py`, under `# Definitions, not parameters.`
  Found, exactly as task 036 reported.
- Three fixtures publishing `boundary_crispness` at tolerance ±0.02: 0.036,
  0.0115, 0.1073. Found.
- The fixture spec's definition prose naming 1.20, and the teaser's caption
  naming 1.20. Found — both, as the brief said, already labelled readings.

**One thing the brief did not know, and it improved the ruling's cost.**

Every fixture already publishes a **`ratio` column for every base vector** in
`ground_view_base.parquet` — `arxiv-150k`, `arxiv-smoke`, `sec-filings-10k`
and `stackexchange-150k`, 150,000 rows each (2,000 for the smoke). That is the
exact quantity the distribution is built from.

So the loss recorded against option C — *"a consumer holding only the
artifacts cannot see the distribution"* — is **smaller than recorded**: for
every published fixture the ratio is already in the published artifacts. The
loss applies only to a user's own run, where they hold their own vectors
anyway. It also meant the verification below could run against the published
artifacts for **all four** fixtures, including the two whose vectors are not
on this machine.

## What was done

`oneground/measures/crispness.py` gains the distribution and the reading;
`boundary_crispness` is untouched. `characterize` reports where the threshold
fell. 15 tests. Nothing is stored, and nothing published moved.

## Measurements

### Every published value reproduces, and is recoverable from the distribution

Run against the published `ratio` columns
(`tasks/scratch/044-verify-against-fixtures.py`):

| fixture | published | from ratios | recovered from distribution | delta | threshold percentile | vectors above |
|---|---|---|---|---|---|---|
| arxiv-150k | 0.036 | 0.0363 | 0.0363 | 0.00000 | 96.37 | 5,441 |
| arxiv-smoke | 0.5295 | 0.5295 | 0.5283 | 0.00117 | 47.17 | 1,059 |
| sec-filings-10k | 0.1073 | 0.1073 | 0.1075 | 0.00012 | 89.25 | 16,102 |
| stackexchange-150k | 0.0115 | 0.0114 | 0.0117 | 0.00026 | 98.83 | 1,717 |

The grid is 201 quantiles at 0.5% spacing, which bounds the recomputation
error at **0.005** — four times inside the ±0.02 tolerance every published
crispness carries. Worst observed error 0.00117.

**`boundary_crispness` computes exactly what it computed before**, and is
asserted unchanged by a test that fails if `CRISP_RATIO` or `N_CENTROIDS`
moves at all.

### The threshold's position is the number that carries the finding

| corpus / model | threshold percentile |
|---|---|
| arxiv-smoke (bge) | 47.17 |
| sec-filings-10k (bge) | 89.25 |
| arxiv-150k (bge) | 96.37 |
| stackexchange-150k (bge) | 98.83 |
| arxiv, e5-base-v2 (task 036) | ~99.4 |

This is reported always, and it is never used to judge the corpus. It is the
fact that says whether a *different embedding* would read anything at this
threshold, which is what task 036 found and what this task exists to surface.

## The criterion I got wrong, and how the measurement caught it

The first implementation flagged a reading whose threshold sat **above the
distribution's 95th percentile** as not discriminating. It was a plausible
rule and it is wrong, and running it against the published fixtures said so
immediately:

```
arxiv-150k          p95 1.1858   threshold 1.20   -> NOT discriminating
stackexchange-150k  p95 1.1501   threshold 1.20   -> NOT discriminating
```

**Two of the three published fixtures, under the anchor model itself.** And
those two demonstrably *do* discriminate: task 036's instrument check showed
they order consistently and reproducibly across five subsample sizes from
1,000 to 20,000, converging on the published gap. A criterion that calls a
working measurement broken is a worse defect than the one it was written for.

It was **replaced, not tuned**. What actually separates the two cases is the
**absolute count**: arxiv at 0.0363 of 150,000 is 5,441 vectors; task 036's
e5 at 0.0007 of 3,000 is two. Both sit deep in the tail of their
distributions; only one is a measurement. So the flag is now
`n_above >= MIN_VECTORS_ABOVE` (30, the conventional floor for estimating a
proportion), and the threshold's percentile is reported alongside without
being used to judge anything.

The wrong criterion and why it was replaced are recorded in the constant's own
comment, so the next person to find a quantile rule attractive meets the
measurement that refuted it.

## Verification

| check | result |
|---|---|
| The three published values reproduce | **PASS** — and the smoke fixture too, all within ±0.02 |
| The count is recoverable from the distribution alone | **PASS** — worst error 0.00117 against a 0.005 bound |
| `boundary_crispness` unchanged | **PASS** — asserted, plus a test that fails if either constant moves |
| The threshold is recorded beside the count | **PASS** — `reading()` returns `threshold` and `threshold_percentile` |
| A non-resolvable reading is couldn't-check on the *reading* | **PASS** — synthetic two-vector case, and it says "the distribution was measured" |
| A tail count over many vectors is **not** flagged | **PASS** — the 5,441-vector case, the mirror test that would have caught my wrong criterion |
| `site/teaser/` byte-identical | **PASS** — `git status site/` empty; no teaser file was opened |
| `fixtures/` byte-identical | **PASS** — `git status fixtures/` empty |
| Nothing stored | **PASS** — no artifact gains a field; `characterization.json` unchanged |
| Full suite | **1367 passed, 40 skipped, 1 failed** — the failure is pre-existing and is not this task's; established rather than assumed, below |

### The one failure, and it is not 044's

`oneground/lab/test_evidence.py::test_every_couldnt_check_claim_carries_a_remedy`
fails on `runs/arxiv-150k-via-characterize` with claims `[33, 34]`.

**Established, not assumed:** it fails *identically* with 044's changes
stashed. 044 only prints; it writes into no artifact, so it cannot move a
claim in a workdir.

Two things about it are worth recording because they are not obvious:

- **It is a new test against an old workdir.** `test_evidence.py` arrived with
  041, which landed on `main` after task 036 branched — which is why task
  036's full runs were green on the same machine with the same run directory.
- **It fails only here.** `_draw` skips an untracked workdir when it is
  absent, and `runs/arxiv-150k-via-characterize` is local and untracked. On a
  fresh clone the test skips; on this machine it runs and fails. A check that
  is green in CI and red on the developer's laptop is worth naming as that
  rather than as a flake.

What it caught looks real. Both claims are `to_resolve` entries reading:

> *"To decide latency_p95: this configuration was not the one verified — the
> verify run built hnsw in a single namespace, which is not a hash_sharded
> deployment. This row's architecture was simulated and never built, so a
> measurement of the built index says nothing about it."*

That names **the obstacle**, thoroughly, and never names an action. A remedy
would be *verify this configuration, built as hash_sharded, on a real engine*.
The sentence explains why the question is open and leaves the reader with
nothing to do, which is exactly what 041's test was written to catch.

Not fixed: it is outside this task and belongs to whoever owns the
`how_to_resolve` text for the not-verifiable-here case.

**Couldn't check:**

- **`check_hosted.py` against the live page.** It needs the network and this
  task changed no teaser byte, so the byte-identity argument is `git status`
  rather than a fetch. If a teaser check is wanted before merge, it is one
  command and it is the developer's to run.

## Observed, not done

- **Whether a user's own run should *store* the distribution.** The ruling was
  "derived on demand" and its stated reason was that nothing published should
  change. A user's own workdir is not published, so writing it there would
  violate neither the letter's purpose nor any digest — but it was not put to
  the developer and is not assumed here. Today `characterize` **prints** the
  reading and its percentile; a user who wants the distribution later
  recomputes it or reads a ground view's `ratio` column. This is the one open
  question the task leaves.
- **`N_CENTROIDS = 256` was not examined**, as the brief required it not be.
  Whether the same class of defect applies to it is unknown, and unknown is
  what this says.
- **`ambiguous_query_rate` uses a ratio rule of the same family**
  (`AMBIGUOUS_RATIO`, `d2 <= ratio × d1`) and is the obvious next candidate.
  Named, not touched — scoped as 044b.
- **The report and lab render the count, not the distribution.** Making them
  render it is a presentation change this task did not make; the measure is
  available to them now.
- **Two `to_resolve` claims name an obstacle and no remedy**, failing 041's
  own test on this machine. Detailed under Verification. Not this task's, and
  worth its own small brief — the fix is a sentence, and the interesting part
  is that the only workdir exercising the test is untracked, so the check is
  green in CI and red on the laptop.

## Repo now contains

Changed:

- `oneground/measures/crispness.py` — `ratios`, `ratio_distribution`,
  `count_at`, `count_from_quantiles`, `threshold_percentile`, `reading`,
  `RATIO_QUANTILES`, `MIN_VECTORS_ABOVE`. `boundary_crispness`,
  `CRISP_RATIO` and `N_CENTROIDS` unchanged.
- `oneground/measures/__init__.py` — the new names exported
- `oneground/characterize.py` — reports the reading and its percentile

New:

- `oneground/measures/test_crispness_distribution.py` — 15 tests
- `tasks/044-crispness-distribution.report.md` — this file

Scratch: `tasks/scratch/044-verify-against-fixtures.py`.

**Unchanged, and checked:** every file under `fixtures/` and `site/`.

## Blocked on developer

Nothing. One question is open and is named above: whether a user's own run
should store the distribution in its own workdir. The ruling covered published
artifacts; this does not assume it extends.
