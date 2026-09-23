# Report: 044b-ambiguity-audit

## The finding: no single-corpus quantity can tell a working reading from a broken one

**Leading, because it is the reason every criterion this task tried was wrong,
and because it decides what the tool can and cannot warn a user about.**

Two readings, both sitting deep in the tail of their own distribution, both
statistically sound:

| reading | value | threshold percentile | n informative | σ from degenerate |
|---|---|---|---|---|
| `arxiv-150k` crispness — **works** | 0.0363 | 96.37 | 5,441 | 75.17 |
| e5 ambiguity — **stopped transferring** | 0.9780 | 97.74 | 44 | 6.71 |

Nothing measurable on one corpus separates them. Both clear every statistical
test; both sit at almost the same percentile. What differs is whether the
reading **discriminates between corpora** — and that is not a property of one
corpus. **The tool measures one corpus at a time, so no single-corpus check
can see it**, and adding a second flag to the artifact would be inventing a
signal that is not there.

That has a direct consequence for what can be built. The only thing a single
reading can be weighed against is **where the same threshold falls on corpora
whose values are frozen**. That is what this task shipped, and the frozen
published values are not an input to it but *the whole of it*.

### And it explains why three criteria were tried and two were wrong

Deciding whether a reading has stopped meaning anything is a judgement this
task got wrong twice in the same direction, and **the published fixtures are
the only thing that caught it. Review never did.**

| # | criterion | what it claimed | what caught it |
|---|---|---|---|
| 1 | threshold above the distribution's **95th percentile** | `arxiv-150k` and `stackexchange-150k` are non-discriminating — under the anchor model | the published fixtures, in 044 |
| 2 | fewer than **30** on the informative side | `arxiv-smoke`'s published ambiguity of 0.935 cannot be read | the published fixtures, in 044b |
| 3 | fewer than **3 standard errors** from the degenerate value | *(all four known cases correct)* | — |

Both failures are the **same failure**: a criterion that calls a working
measurement broken, which is a worse defect than the one it was written for,
because it converts a real number into a couldn't-check and a reader loses
something they had.

And both were reached for the same way. The question is *is this proportion
distinguishable from the value it degenerates to* — and a quantile answers
"where does the threshold sit", a count answers "how much data is there".
Both are adjacent, both are plausible at a glance, and neither is the
question. Only the third is.

**The argument this makes for the fixtures.** Neither wrong criterion was
caught by reading the code, by writing the tests, or by thinking harder about
the definition. Each was caught by running the rule against numbers this
project had already published and watching it contradict them. A corpus with
frozen published values is not only a way to check an installation — it is
the only instrument here that has ever caught this class of error, twice.

The replaced rules and the case that killed each are in the constant's own
comment in `measures/crispness.py`, so a future reader meets the evidence
against them rather than the rules.

---

## Repo state expected vs found

Expected, and found:

- `AMBIGUOUS_RATIO = 1.10` in `oneground/measures/ambiguity.py` with the rule
  `d2 <= 1.10 × d1`. Found.
- Four fixtures publishing `ambiguous_query_rate`: 0.8915, 0.935, 0.6545,
  0.9085. Found, all four reproduce exactly.
- Task 044's distribution machinery on `main` to mirror. Found.

**One thing that was not expected:** every fixture publishes a **`ratio`
column for every query** in `ground_view_queries.parquet`, as the base side
does in `ground_view_base.parquet`. So the query-side audit ran against the
published artifacts for all four fixtures without embedding anything.

**One thing to flag:** `task-036` is **still unmerged**, so
`oneground.embed.registry` is not on `main`. This task's measurement script
used `embed.load_model` directly instead. Noted because 036's machinery —
the three registers, the model resolver, the cost projection — is finished and
reported and is sitting on a branch.

## What was done

The audit, the e5 query-side measurement, and the symmetric implementation:
`ambiguity.reading()` mirroring `crispness.reading()`, the distribution stored
in a user's own run, `ambiguous_query_rate` untouched.

**No published value moved, so there is no migration to bring.** The four
published rates reproduce exactly; the only behaviour that changed is the
`resolvable` flag, and no published fixture's crispness flag changes under the
new criterion.

## Measurements

### The same family, thresholded from opposite sides

```
crispness   d2 >  1.20 x d1     counts the UPPER TAIL     -> empties
ambiguity   d2 <= 1.10 x d1     counts BELOW a point      -> saturates
```

One quantity, two constants, two directions. A distribution compressed toward
1.0 empties the first and fills the second.

### 1.10 is nearer its failure than 1.20 was

Measured on the published query ground views, under the anchor model:

| fixture | median ratio | p95 | rate | **1.10 sits at** |
|---|---|---|---|---|
| arxiv-150k | 1.0339 | 1.1299 | 0.8915 | **89.3rd pct** |
| arxiv-smoke | 1.0236 | 1.1071 | 0.9350 | **93.9th pct** |
| sec-filings-10k | 1.0609 | 1.2884 | 0.6545 | 65.4th pct |
| stackexchange-150k | 1.0303 | 1.1215 | 0.9085 | **90.9th pct** |

On three of four, **most queries are already inside the threshold before any
model changes**. Crispness had already failed under a second embedding; this
one has not, and sits closer to failing than crispness did when it failed.

**A measure that has not failed and is closer to failing than one that has is
a finding about the family of measures, not about either member.** Both are
fixed constants against a distribution whose scale is a property of the
embedding, and neither reports where its threshold falls. That is the shared
defect; which one has tipped over is an accident of where the constants were
set.

Asserted as a test rather than left as prose:
`test_the_threshold_already_sits_high_in_every_fixture`.

### The query side is far more compressed than the base side

arxiv under the anchor: query median ratio **1.0339** against a base median of
**1.1035**. That is why one corpus reads crispness 0.036 and ambiguity 0.891 —
the two measures are reading differently-shaped distributions, not disagreeing
about the corpus.

### The e5 query side, measured rather than inferred

**Do not compare these numbers with the published values.** They are measured
at N=1,000 base vectors and 16 centroids; the published values are 150,000 and
256. The absolute reading moves with the instrument's settings, so seeing
0.1840 here beside a published 0.036 is a difference in the instrument, not a
disagreement about the corpus. **What this run measures is the difference
between two models at fixed settings**, and only that comparison is licensed.

Said as its own line because a reader who sees the two numbers next to each
other will make the comparison unless told not to, and the report that let
them is the report at fault.

| model | base median | base p95 | crispness | 1.20 at | query median | query p95 | ambiguity | 1.10 at |
|---|---|---|---|---|---|---|---|---|
| bge-base-en-v1.5 | 1.1126 | 1.2769 | 0.1840 | 81.6th | 1.0656 | 1.1792 | 0.6780 | 67.8th |
| e5-base-v2 | 1.0623 | 1.1473 | **0.0060** | **99.5th** | 1.0304 | 1.0879 | **0.9780** | **97.7th** |

The prediction held and the measurement sharpened it. Crispness collapses and
ambiguity saturates, as predicted — but **they do not fail together**:

| | value | σ from degenerate | outcome |
|---|---|---|---|
| e5 crispness | 0.0060 | **2.46** | **refuses to be read** |
| e5 ambiguity | 0.9780 | **6.71** | **reads** |

At the same settings under the same model, crispness trips its own
couldn't-check and goes quiet, while ambiguity passes every soundness check
and returns 0.978 — which a user reads as *"essentially every query I have is
ambiguous"*.

**The saturating measure is the one that does not warn.** That inverts the
usual intuition about which failure is worse: a confident wrong number that
passes its own soundness check is worse than a silent one, because nothing in
the artifact invites suspicion. Verified with `distinguishable` rather than
arithmetic: `tasks/scratch/044b-sigma-and-the-gap.py`.

### The compression asymmetry is the structural reason

Under the anchor, at these settings, the **query** ratio distribution is
tighter against 1.0 than the **base** one: median **1.0656** against
**1.1126**, p95 **1.1792** against **1.2769**.

That is not a detail about arxiv. **The distribution the query-side measure
reads is systematically more compressed than the one the base-side measure
reads**, so a fixed threshold has less room on the query side before it runs
out of distribution. It relocates the family question: not *"is 1.10 set too
high"* — moving one constant trades one arbitrary position for another — but
whether any fixed threshold is the right shape for a query-side measure at
all.

## Saturation is the more dangerous failure for a user

Stated plainly because it decides which of the two matters more.

- A collapsed crispness reads **0.0000**, which at least invites the question
  of whether the number is right.
- A saturated ambiguity reads **0.98**, and *"my queries are all ambiguous"*
  sounds like a finding about the user's corpus. It invites action —
  abandoning semantic sharding, say — rather than suspicion.

The right words in the wrong register: a number that reads as a strong result
and is an instrument that has stopped discriminating. The couldn't-check on
the reading names that misreading explicitly rather than only reporting a
flag.

## What was built: the transfer block, and the two defects building it exposed

`reading()` on both measures now reports where this corpus's threshold sits
**against the published band**. Not a new signal — the only signal there is.

```
1.10 sits at the 97.74th percentile of this corpus's ratio distribution. On
the published corpora the same threshold sits between the 65.4th and the
90.9th. This reading is being taken somewhere the measure has never been
calibrated, so a rate here does not mean what the same number means on those
corpora. It is a reason to read the distribution rather than the number; it is
not a demonstration that the number is wrong, and no measurement of one corpus
could be.
```

That final clause is tested, not decorative: the block stops short of a
verdict because the structural finding says nothing measurable on one corpus
could support one.

### Defect 1 — the band was too wide to discriminate, and a smoke fixture did it

Computed over all four fixtures, crispness's band was **47.2 – 98.8** — half
the distribution. A discriminator spanning half the distribution barely
discriminates, and e5's 99.47 cleared it only barely.

`arxiv-smoke` alone did that: it puts the threshold at the **47.17th**
percentile, and one 2,000-vector fixture dragged the floor down fifty points.

**Ruled and implemented: smoke fixtures are excluded.** A 2,000-vector fixture
exists to check that a command runs, not to calibrate a measure, and a band
computed over both kinds is dominated by the looser one. The bands became:

| | with the smoke fixture | full fixtures only |
|---|---|---|
| crispness 1.20 | 47.2 – 98.8 | **89.25 – 98.83** |
| ambiguity 1.10 | 65.4 – 93.9 | **65.44 – 90.87** |

**This is the sharpest form yet of the fixtures being load-bearing.** The
other instances said the fixtures *caught* something. This one says the
reference is **too thin to catch the next thing**: three full corpora, and
ambiguity's band still spans a quarter of the distribution, so it can say
e5's 97.7 is outside and cannot say much finer. That is a stated limit, now in
`docs/FIXTURES.md`, and a concrete argument for a fourth and fifth full
fixture.

### Defect 2 — the tightened band flagged the anchor model, and the cause was sample size

The moment the band tightened, a bge run landed outside it. So the drift was
measured directly, on the published vectors at the production centroid count,
which isolates sample size:

| corpus | n=5,000 | n=10,000 | n=20,000 | n=50,000 | published (150,000) |
|---|---|---|---|---|---|
| arxiv-150k | **87.46** | 93.40 | 95.79 | 96.42 | 96.37 |
| stackexchange-150k | 91.45 | 97.28 | 98.28 | 98.64 | 98.83 |

**At 5,000 vectors `arxiv-150k` reads outside its own band, under the anchor
model, on its own published corpus.** The position drifts upward with n and
converges on the published value.

So the comparison as first built would have raised a false alarm on precisely
the signal it exists to give, and **a false alarm degrades a warning faster
than silence does**. Fixed with a measured floor: below
`MIN_N_FOR_TRANSFER = 10,000` the comparison is **not made** — couldn't-check,
with this table as its justification — while the threshold's percentile is
still reported. The floor is where the drift stops mattering, which is also
the sample size this project already recommends.

**Three times in two tasks, something plausible was built and a published
fixture refuted it before it shipped**: the quantile criterion, the count
criterion, and now the un-floored band. None was caught by review.

## Verification

| check | result |
|---|---|
| The four published `ambiguous_query_rate` values reproduce | **PASS** — 0.8915, 0.935, 0.6545, 0.9085 |
| `ambiguous_query_rate` unchanged | **PASS** — asserted, plus a test that fails if the constant moves |
| Every published reading is resolvable under the new criterion | **PASS**, including `arxiv-smoke`, which the replaced criterion failed |
| The published percentile constants still match the fixtures | **PASS** — re-derived by a test, so a rebuilt fixture cannot stale them silently |
| A small sample is not compared against the band | **PASS** — couldn't-check below 10,000, percentile still reported |
| Smoke fixtures excluded from the band | **PASS** — asserted |
| e5 query side measured, not inferred | **PASS** — both models embedded in one environment |
| No published value moved | **PASS** — only the `resolvable` flag's basis, and no fixture's flag changes |
| Measures tests | **PASS** — 58 |

**Couldn't check:** whether the drift table generalises past the two corpora
with local vectors. `sec-filings-10k` has none here.

## Observed, not done

- **`N_CENTROIDS = 256` remains unexamined**, now in two tasks' reports.
  Every measure here is computed against a k-means whose cluster count is a
  fixed constant under the same comment, and nobody has asked whether 256 is
  a property of the embedding either.
- **`skew_top10_share` and `intrinsic_dimensionality` are not audited.** Skew
  reads the same k-means; LID does not use the ratio at all and may well be
  immune, but "may well be" is not a measurement.
- **`task-036` is unmerged.** Its machinery is finished and reported.

## Repo now contains

Changed:

- `oneground/measures/ambiguity.py` — `rate_at`, `reading`, the published
  percentile reference, the mirrored resolvability test
- `oneground/measures/crispness.py` — `distinguishable` replacing the count
  rule, `against_published`, `threshold_percentile`, the band constants and
  `MIN_N_FOR_TRANSFER`, each carrying the measurement behind it
- `oneground/measures/__init__.py` — the new names exported
- `oneground/characterize.py` — the ambiguity reading stored and reported

New:

- `oneground/measures/test_ambiguity_distribution.py` — 15 tests
- `tasks/044b-ambiguity-audit.report.md` — this file

Scratch: the audit, the e5 query-side run and its log, the σ verification, the
published-range derivation, the transfer check, the sample-size drift.

**Unchanged and checked:** every file under `fixtures/` and `site/`.

## Blocked on developer

Nothing, and no migration is owed: no published value moved.
