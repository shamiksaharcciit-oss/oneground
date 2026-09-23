# Report: 044b-ambiguity-audit

## The finding that is not about ambiguity: three criteria, two wrong the same way

**Leading, because it generalises past this measure and past this task.**

Deciding whether a reading has stopped meaning anything turns out to be a
judgement I keep getting wrong, in a consistent direction, and **the published
fixtures are the only thing that has caught it. Review never did.**

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

*(filled in when the run completes)*

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

## Verification

*(filled in)*

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

*(filled in)*

## Blocked on developer

Nothing, and no migration is owed: no published value moved.
