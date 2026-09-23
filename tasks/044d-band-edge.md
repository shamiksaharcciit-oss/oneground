# Task 044d — a fixture reading outside the band it is the edge of

**Written up from the developer's ruling on the 044c report**, in the same
form 042d should have had. Branch `task-044d` from `main` once 044c merges.
Commit `task 044d:` and push after every commit. No pod: the published ground
views carry what this needs.

## Why

`oneground characterize`, run on `stackexchange-150k` at the published
settings on the published vectors, tells the user:

> This reading is being taken somewhere the measure has never been
> calibrated.

about the corpus that calibrated it. Measured in 044c
(`tasks/scratch/044c_band_edge.py`):

    stackexchange-150k   measured 90.871567   band 65.44 - 90.87   outside = True

`PUBLISHED_AMBIGUITY_PERCENTILES` stores stackexchange at `90.87`, and that
entry is the **maximum of the table**, so it is the top edge of the band
`against_published` compares against. The stored literal is rounded to two
decimals; what `reading()` computes is not. The corpus sits 0.0016 above its
own recorded position and the comparison is a strict `lo <= pct <= hi`.

**A published fixture reading outside its own band is the transfer warning
firing on the one corpus it cannot be wrong about.** This is the false-alarm
class 044b introduced `MIN_N_FOR_TRANSFER` to prevent, arriving through
rounding instead of through sample size — and 044b's own argument is that a
false alarm degrades a warning faster than silence does.

The other three of the four cases land inside only because their rounding
happened to go the other way: `98.829571` stored as `98.83` rounds **up** and
survives. Three of four are luck.

## Both halves are the finding

**Half one: the stored edge and the measured value disagree at the fifth
decimal**, and a strict inequality turns that into a verdict.

**Half two: the check that should have caught it was written wide enough not
to.** `test_the_published_percentile_constants_still_match_the_fixtures`
(`oneground/measures/test_ambiguity_distribution.py:152`) asserts

```python
assert got == pytest.approx(recorded, abs=0.05)
```

It is right about the fact it checks — that the constants have not gone stale
against a rebuilt fixture — and **ten times looser than the rounding error
that causes the defect**. A 0.05 agreement band cannot see a 0.005 disagreement
at an edge, and the defect is entirely about direction at an edge.

Neither half is interesting alone. A rounding slip is a rounding slip; a loose
test is a loose test. Together they are the shape 043 named: *a test that
checks the right fact with a predicate that cannot see the failure*, and
04c's own finding that an exhaustive absence test cannot catch a wrong value.
Report them as one finding with two halves, not as two findings.

## Do

### 1. Write the failing test first

Before any fix. It must fail on `main` for the stated reason and be named for
the property rather than the function:

- **every published fixture reads inside the band it is part of**, for both
  tables, both thresholds, computed from the published `ground_view_*.parquet`
  rather than from the stored constants. A fixture in the table is by
  construction calibrated ground and can never legitimately be outside.

The existing agreement test stays. It checks staleness, which is a different
fact, and 044d is not a reason to delete a test that is right about its own
subject. **Do not widen or narrow its `abs=0.05`**; if it needs a companion,
add one.

### 2. Decide the remedy on the measurement, not on taste

Three shapes are available and the brief does not pick one:

- store the percentiles at the precision they were measured;
- compare with an explicit allowance for the stored rounding;
- derive the band edges from the published ground views at import.

Say what each costs. In particular: the third removes the literal that can go
stale and adds a parquet read to import, and `against_published` is called on
a user's own run where those files may not be present — check that before
recommending it.

Whichever is chosen, **the stored table is a published-value-adjacent
artifact**: the numbers in it were measured from published bytes, and 044b
records their provenance in the comment beside them. If the values change
form, the comment changes with them.

### 3. Fold in the second instance, same file, same family

`PUBLISHED_PERCENTILE_BASIS` (`oneground/measures/crispness.py:281`) says the
threshold's drift with sample size

> has not been measured. That is task 044c's question and until it is answered
> this comparison carries the assumption rather than having discharged it.

Both clauses are wrong. **044b measured exactly that drift and set
`MIN_N_FOR_TRANSFER` from it** — with the table — **three lines below in the
same file**. And 044c's question was the centroid count, which is now answered
in `tasks/044c-centroid-count.report.md`.

So one module holds two comments disagreeing about whether a thing is
measured, the same mechanism `docs/PRACTICE.md` records from 043 in a smaller
key. Correct the sentence to say what is measured and by which task, and say
what the comparison still assumes — because it does still assume something,
and 044c's measurement changed what: the centroid count matches by
construction only because `characterize` always uses `N_CENTROIDS`, and 044c
measured that the band would move a great deal if it ever did not.

### 4. Survey for the same shape elsewhere. **This step is not optional.**

`PUBLISHED_CRISP_PERCENTILES` has the identical structure — a stored
two-decimal literal, a full-precision recomputation, a strict inequality — and
is inside its band only because `98.829571` rounds **up** to `98.83`. Change
the corpus, the seed or the library version by enough to move that sixth digit
and it fails the way ambiguity already does.

> **A defect that survives by the direction of a rounding is not fixed. It is
> lucky.** The survey is how the ones whose luck runs out later are found
> before they do.

So: find every place in the project where **a stored rounded literal is
compared against a full-precision recomputation under a strict inequality**,
and report them whether or not any is currently failing. A passing one is the
more useful finding here, because it is the one nobody would otherwise look
at.

Fix only what this brief covers. Report the rest with what would make each of
them fail.

## What this may not do

- **Change `CRISP_RATIO`, `AMBIGUOUS_RATIO`, `N_CENTROIDS`,
  `DISTINGUISHABILITY_SIGMA` or `MIN_N_FOR_TRANSFER`.** None of them is
  implicated and rule 3 stands.
- **Widen a tolerance to make the comparison pass.** The band is not too
  tight; the literal is too short. Widening is the move that would make this
  defect invisible again, and it is the one thing this brief forbids outright.
- **Delete or loosen the existing agreement test.**
- **Move a published value.** None should need to.

## Acceptance

- A test that fails on `main` for the stated reason, named for the property,
  committed before the fix.
- `stackexchange-150k` reads inside its own band, demonstrated on the
  published ground view rather than on a constructed number.
- The remedy chosen with its cost stated against the alternatives.
- `PUBLISHED_PERCENTILE_BASIS` corrected, with what the comparison still
  assumes stated rather than dropped.
- The survey in step 4 reported, whether or not it finds anything, with what
  would make each surviving instance fail.
- Full suite green, and no published value moved.

## Do not

- Report the two halves separately. The rounding slip is ordinary; the pair is
  the finding, and the second half is the one that generalises.
