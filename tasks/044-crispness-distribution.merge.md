# Merge report: task-044 → main

Merged at `26b9a61`. Pushed.

## Merged onto a red suite, knowingly

**Suite: 1367 passed, 40 skipped, 1 failed**, twice, identically.

The failure is
`oneground/lab/test_evidence.py::test_every_couldnt_check_claim_carries_a_remedy`
on `runs/arxiv-150k-via-characterize`, and it is **not this task's**. Three
things establish that rather than assert it:

1. **It reproduces with 044's changes stashed.** Run on the same tree with
   `git stash push -u`, same failure, same two claims.
2. **044 cannot have caused it.** It writes into no artifact a claim is built
   from — the only file it adds a field to is a *user's own workdir's*
   `characterization.json`, and the failing claims come from
   `verify_info.json:engine_facts.index_params`.
3. **It post-dates the workdir.** `test_evidence.py` arrived with 041, which
   is why task 036's full runs were green on this machine with the same run
   directory present.

Holding a clean change hostage to another task's defect is worse than merging
onto it knowingly and saying so — which is this section.

It is **green in CI and red only here**: `_draw` skips an untracked workdir
when it is absent, and that run directory is local. A test green in CI and red
only where an untracked workdir happens to exist is a test that has not really
been run, and that point is in the 045 addition as a request for a tracked
case.

## What the interface stream found, which is larger than what was sent

The addition was written around two claims and a lead — that
`how_to_resolve` already returns a remedy for the `not_verifiable_here` kind,
so the defect might be routing rather than prose, and the routing should be
checked **before any text is written**.

The interface stream ran it down: **all 29 couldn't-check verdicts in
`verdict.py` set neither `remedy` nor `couldnt_check_kind`** — fields that
have existed since task 034 and are populated by exactly one path. Several
carry the action inside `reason`: the right words in the wrong field, which
reads as done and is invisible to anything looking for a remedy.

So the two claims were not the defect; they were the two anyone happened to
look at. 045 now covers all 29, and nothing further is owed here.

That is also the vindication of the instruction order. A hand-written sentence
for those two claims would have passed the test, read well, and left 27 other
verdicts unrouted and invisible.

## What landed

- `boundary_crispness`, `CRISP_RATIO` and `N_CENTROIDS` **unchanged**, with a
  test that fails if either constant moves.
- The ratio distribution on a declared 201-point grid, `count_at`,
  `count_from_quantiles`, `threshold_percentile`, and `reading()` — the count
  with its threshold and where that threshold sits.
- A user's own run **stores** it; published fixtures keep deriving on demand.
- 16 tests.

## Published bytes

`git status fixtures/ site/` is **empty** after the merge. Not one fixture or
teaser byte moved, which was the constraint the whole design was built to
meet.

Every published value verified against the fixtures' own `ratio` columns —
all four, including the two whose vectors are not on this machine. Worst
recomputation error 0.00117 against a 0.005 grid bound, four times inside the
published ±0.02.

## The criterion that was replaced

Recorded here because it is the part most likely to be re-proposed: a rule
flagging a reading whose threshold sat above the distribution's 95th
percentile was written, measured against the published fixtures, and **flagged
`arxiv-150k` and `stackexchange-150k` as non-discriminating under the anchor
model itself** — two corpora that demonstrably discriminate, ordering
consistently across five subsample sizes.

It was replaced rather than tuned, by the absolute count above the threshold.
The refuted rule and the measurement that killed it are in the constant's own
comment, so the next person to find a quantile rule attractive meets the
evidence against it rather than the rule.

## Next

044b: `ambiguous_query_rate`. The audit is done and it is the same family —
`d2 <= 1.10 × d1` counts everything *below* a fixed point where crispness
counts the tail *above* one, so a compressed distribution saturates it instead
of emptying it. 1.10 already sits at the 89th–94th percentile of the query
ratio on three of four fixtures, under the anchor.
