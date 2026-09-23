# Task 044c — Is `N_CENTROIDS = 256` load-bearing or incidental?

**Not before 042d.** Measure first; bring a migration only if a published
number moves.

## Setup
Branch `task-044c` from `main`. Commit `task 044c:` and push after every
commit. No pod: the published fixtures ship what this needs, and where they do
not, the vectors are local.

## Why

`oneground/measures/crispness.py` declares three constants under one comment:

```python
# Definitions, not parameters. See the module docstring in measures/__init__.
N_CENTROIDS = 256
CRISP_RATIO = 1.20
```

That comment has now produced **one confirmed defect and one near-miss**:

- **`CRISP_RATIO` (task 044)** — a fixed threshold against a distribution
  whose scale is a property of the embedding. Under `e5-base-v2` the 95th
  percentile of the ratio is 1.15 and the threshold is 1.20, so the count
  returned a near-zero for every corpus regardless of what was in it. A user
  would read *"my corpus has no boundary structure"* from an instrument that
  had stopped reading.
- **`AMBIGUOUS_RATIO` (task 044b)** — the same family, mirrored. It has not
  failed, and 1.10 already sits at the **89th–94th percentile** of the query
  ratio on three of four published fixtures under the anchor model, so it sits
  closer to failing than crispness did when crispness failed.

**Nobody has asked the same question of the third constant.** And it is
upstream of both: crispness, ambiguity and `skew_top10_share` are all computed
against a k-means whose cluster count is that number. If 256 is itself a
property of the embedding or of the corpus rather than of the method, then the
two findings above are symptoms of something one level down.

Two consecutive reports have recorded it as unexamined. That is the whole
reason for this task.

## Do

### 1. Measure the readings against the centroid count

On the published fixtures, sweeping `N_CENTROIDS`, with everything else held:

- `boundary_crispness` and its `threshold_percentile`;
- `ambiguous_query_rate` and its `threshold_percentile`;
- the ratio distribution's median and p95, base and query side;
- `skew_top10_share`, which reads the same k-means from a third angle.

Sweep a range that brackets 256 by at least an order of magnitude each way —
the point is to find where behaviour changes, not to confirm it near the
declared value.

`arxiv-150k` and `stackexchange-150k` have local vectors; `sec-filings-10k`
does not, and its published `ground_view_*.parquet` carry `ratio` at 256 only,
so its sweep is **couldn't-check** unless its vectors are obtained. Say which
fixtures were swept and which were not.

### 2. Answer the two questions the task exists for

- **Does either reading change materially with the centroid count?** Material
  means: by more than the ±0.02 tolerance the published values carry.
- **Is there a count at which either degenerates?** Degenerate has a
  definition already — `crispness.distinguishable`, the standard-error test
  from 044b. Use it rather than inventing a third criterion; **two of the
  three criteria tried so far were wrong and both were caught by a fixture
  rather than by review** (`docs/FIXTURES.md`, *Why the published values are
  frozen*).

### 3. If 256 is load-bearing, the comment is the finding

If the readings move materially with the count, then **three constants under
one comment reading "definitions, not parameters" have each turned out to be
a parameter**, and the comment is no longer a description of them — it is the
thing that stopped three separate questions being asked.

Say that plainly, and propose what replaces it: not a different number, but
what a constant of this kind has to carry beside it. Task 044's answer for
`CRISP_RATIO` was *report the distribution and label the count as a reading of
it at a stated threshold*; whether the same shape fits a cluster count is the
open question and the report should take a position.

If instead 256 turns out to be incidental — the readings stable across a wide
range — that is equally reportable and is the first of the three constants to
come back clean. Say so, and say over what range it was checked, because
"stable" without a range is not a measurement.

**But report the comment as a defect either way.** A benign answer does not
retire the finding, because the finding is not about the number. Three
constants sat under one line reading *"definitions, not parameters"*; two of
them turned out to be parameters, and the third went unexamined through two
consecutive tasks that were explicitly looking for exactly this class of
defect. **A comment that stopped a question being asked is a defect even when
the answer is benign** — the cost was the two tasks that did not ask, and that
cost was paid whatever 256 turns out to be.

So the report takes a position on the comment regardless of the measurement,
and the two are kept apart: what the sweep found, and what the comment did.

### 4. The other two measures, named not audited

`skew_top10_share` reads the same k-means and is in scope for the sweep above.
`intrinsic_dimensionality` (TwoNN LID) does not use the ratio or the k-means
at all and is probably immune — **name that as probably, not as checked**,
unless it is checked.

## What this may not do

- **Change `N_CENTROIDS`, `CRISP_RATIO` or `AMBIGUOUS_RATIO`.** Rule 3, and
  every published value depends on all three.
- **Invent a fourth resolvability criterion.** Use
  `crispness.distinguishable`.
- **Move a published value without bringing the migration first.**
- **Report "stable" without the range it was stable over**, or "immune"
  without a measurement.

## Acceptance

- The sweep is run on every fixture whose vectors are available, and the
  fixtures not swept are named as couldn't-check with the reason.
- Both questions answered with numbers: does either reading move materially,
  and is there a count at which either degenerates.
- A position taken on whether 256 is load-bearing or incidental, over a stated
  range.
- **A position taken on the comment, whichever the answer is**, kept separate
  from the measurement. If load-bearing: the comment named as the finding,
  with a proposal for what a constant of this kind carries beside it. If
  incidental: the comment still named as the defect that stopped two tasks
  asking, because that cost was paid regardless.
- No published value moved, or a migration brought before one is.
- Full suite green.

## Do not

- Tune a constant to make a reading behave. The two findings before this one
  were both *reported* rather than fixed, and both were the more useful for it.
