# Report: 044d-band-edge

## It was both endpoints, not one

**Leading, because it corrects what 044c reported to the developer.**

044c found `stackexchange-150k` reading outside its own ambiguity band and
wrote that *"the other three of the four cases land inside only because their
rounding happened to go the other way."* **That was wrong.** 044c measured the
positions from its own sweep, which only reaches the two fixtures whose
vectors are local. Step 1's test reads the published ground views instead, so
it reaches all three — and failed on `sec-filings-10k` on its first run, a
fixture 044c had never checked.

Both endpoints of the ambiguity band read outside it:

| band | fixture | measured | stored | rounded | verdict |
|---|---|---|---|---|---|
| ambiguity 1.10 | `sec-filings-10k` | 65.436356 | `65.44` | **UP** | below the low edge — **OUTSIDE** |
| ambiguity 1.10 | `arxiv-150k` | 89.277750 | `89.28` | up | interior — safe |
| ambiguity 1.10 | `stackexchange-150k` | 90.871567 | `90.87` | **down** | above the high edge — **OUTSIDE** |
| crispness 1.20 | `sec-filings-10k` | 89.253265 | `89.25` | down | low edge, rounds outward — safe |
| crispness 1.20 | `arxiv-150k` | 96.373005 | `96.37` | down | interior — safe |
| crispness 1.20 | `stackexchange-150k` | 98.829571 | `98.83` | **up** | high edge, rounds outward — safe |

### The rule the rounding had to satisfy, which nobody stated

**An endpoint is safe if and only if the low edge rounds down and the high
edge rounds up.** The interior fixture cannot fail however it rounds, because
it is not an edge of anything.

So there are exactly **four endpoint slots** across the two tables, each an
independent coin flip on the direction of its own rounding. Crispness won
both. Ambiguity lost both. That is the developer's framing measured out: a
defect that survives by the direction of a rounding is not fixed, it is lucky
— and here the luck was two-for-four, not three-for-four.

The consequence is what makes it worth a task. `oneground characterize` on
either of those two fixtures, at the published settings, on the published
vectors, prints *"This reading is being taken somewhere the measure has never
been calibrated"* — **about a corpus that calibrated it.** 044b's own argument
is that a false alarm degrades a warning faster than silence does, and this is
the false alarm fired at the two corpora the warning cannot be wrong about.

## Repo state expected vs found

| expected | found |
|---|---|
| the defect reproduces on `stackexchange-150k` | yes, and on `sec-filings-10k` too, which the brief did not predict |
| the agreement test is `abs=0.05` as the brief quotes | yes, `test_ambiguity_distribution.py:171` |
| `PUBLISHED_PERCENTILE_BASIS` carries the stale sentence | yes, `crispness.py:296–304` |
| branch from `main` once 044c merges | **no** — 044c is unmerged pending review, so this is stacked on `task-044c`. No file overlap: 044c never touched `crispness.py` or `ambiguity.py`, and 044d does not touch `skew.py` or any spec. |

## What was done

### Step 1 — the failing test, written first

`oneground/measures/test_band_edge.py`, committed before the fix and failing
on the branch for the stated reason:

```
FAILED test_every_published_fixture_reads_inside_the_band_it_is_part_of[ground_view_queries…]
FAILED test_the_stored_edges_are_the_measured_extremes[ground_view_queries…]
  stored low edge 65.440000 is above the measured minimum 65.436356 (sec-filings-10k)
2 failed, 5 passed
```

It is **a second file rather than an extra assert in the existing one**,
because the two ask different questions and one assertion cannot ask both.
`test_the_published_percentile_constants_still_match_the_fixtures` asks *are
the constants about right* — staleness after a rebuild — and is correct about
that. This asks *does the comparison they drive give the right answer on its
own sources*. The existing test keeps its subject and its `abs=0.05`
untouched, per the brief.

Four tests:

- **inside its own band**, for both tables, recomputed from the parquet rather
  than from the stored constant, which is the thing under test;
- **the stored edges bound the measured extremes** — the narrower statement,
  and the one that actually has to hold. Asserting it directly means a future
  rounding in the wrong direction is caught *at the constant*, not at
  whichever consequence someone happens to test. This is 043's
  assert-the-ordering-not-the-behaviour form;
- **the check actually read the ground views** — PRACTICE §2 warning 6, a
  check that skips where it would fail. Two tests that skipped every fixture
  would both pass;
- **a genuinely outside reading is still reported** — 044b's e5 at the 97.74th
  percentile. The signal must survive the fix, and a remedy that widened the
  band until nothing fell outside would have removed it.

### Step 2 — the remedy, and why the other two were refused

**Chosen: store at measured precision, with a declared epsilon.** The stored
percentiles now carry six decimals, taken from the published
`ground_view_*.parquet` — the same source the test recomputes from, and *not*
from a fresh k-means, which lands a few ten-thousandths away and would
reintroduce the same disagreement by another route.

`EDGE_EPSILON = 1e-6` in `crispness.py`, used once, in `against_published`.
It absorbs two bounded things and nothing else: the half-unit of the stored
decimals (5e-7) and last-bit differences between numpy versions recomputing
the same percentile. It is 500,000× finer than the 0.5 percentile-point grid
the distribution is reported on, **so it cannot absorb a disagreement anyone
could measure.** Its docstring says widening it is the move this task exists
to forbid.

| option | cost | verdict |
|---|---|---|
| store at measured precision | longer literals; still a literal that can go stale on a rebuild, which the existing agreement test already guards | **chosen** |
| an explicit rounding allowance, alone | fixes the symptom while the stored value stays a different number from the measured one; and an allowance sized to make a case pass is the thing the brief forbids | refused as the primary remedy; survives only as `EDGE_EPSILON`, sized to storage granularity rather than to any observed gap |
| derive the edges from the ground views at import | **impossible, not merely costly** — see below | **refused, on a check** |

**The third option is dead, and the brief was right to demand it be checked.**
`MANIFEST.in`'s allowlist ships `*.fixture.yaml`, `MANIFEST.sha256`,
`characterization.json`, `build_info.json`, `query_ids.json` and
`ground_truth.npy`. It does **not** ship `ground_view_*.parquet`. Those files
are committed in the repository and absent from the sdist and the wheel. And
`against_published` runs inside `characterize`, which is the installed path —
so deriving the band at import would raise on every installed copy while
passing in every developer checkout, which is the worst available failure
mode. Independently, `pyarrow` is an optional extra (`view = [...]`), not a
hard dependency, so the reader is not guaranteed either.

### Step 3 — the second instance, same file

`PUBLISHED_PERCENTILE_BASIS`'s comment said the threshold's drift with sample
size *"has not been measured. That is task 044c's question."* Wrong twice:
**044b measured it and set `MIN_N_FOR_TRANSFER` from it, with the table, three
declarations below**, and 044c's question was the centroid count.

Rewritten to state what each task measured, and — the part that is not
bookkeeping — **what the comparison still assumes.** The old text treated
*"`characterize` always uses `N_CENTROIDS`, so the centroid count matches by
construction"* as a reason not to worry. 044c measured that the construction
is load-bearing rather than incidental: arXiv's own threshold position runs
from the 85.69th percentile at k=16 to the 96.53rd at k=512. The count
matching is now doing real work, and the comment says so. What remains
assumed is that three full fixtures bound the band, which is the thin-reference
limit `docs/FIXTURES.md` already records.

The old sentence is quoted in the new comment rather than deleted, because two
comments in one module disagreeing about whether a thing is measured is
PRACTICE §4's mechanism in a smaller key, and the instance is the evidence.

### Step 4 — the survey. **Its first version would not have found its own
motivating case.**

Worth leading with, because a survey that cannot find the defect it is
modelled on is PRACTICE §2 in one line.

The first version looked for a rounded literal whose **name appears in a
comparison in the same module**. `PUBLISHED_AMBIGUITY_PERCENTILES` lives in
`ambiguity.py`; the comparison that bit is in `crispness.against_published`,
reached by passing the table as an argument. Same-module comparison describes
**where the defect happened to be caught, not what it is.** It reported nine
candidates, all of them chosen thresholds, and zero true positives — a clean
bill of health from a predicate that excluded the patient.

Rewritten to select on **provenance**: is this literal a rounded copy of a
quantity the project can recompute? "Compared somewhere" is then automatic,
because anything worth storing gets used. The distinction that does the work:

> **A choice is not a copy.** `CRISP_RATIO = 1.20` is a rounded-looking
> literal compared against a recomputed ratio, and it is not this defect —
> nothing recomputes "the true value of `CRISP_RATIO`". The defect needs both
> sides to be the same quantity, one stored short and one computed long.

**Result: no second instance of this shape exists.** 36 module-level short
float literals in `oneground/`; 31 are chosen constants; 5 flagged as
possibly-measured and judged individually:

| candidate | judgement |
|---|---|
| `crispness.RATIO_QUANTILE_STEP = 0.5` | a declared grid, chosen — not a copy |
| `verdict.CALIBRATION_TOLERANCE = 0.01` | chosen tolerance |
| `verdict.MARGIN_FRACTION = 0.1` | chosen fraction |
| `lab/views/ground.py:39 CRISP_RATIO = 1.20` | **a copy, but of a constant, not of a measurement** — see below |
| `characterize.py:77 PROJECTION_PARAMS` | **a copy of the specs' `projection.params`** — see below |

The two copies are a **different and milder shape** — a second literal of a
value defined elsewhere, where both sides are short literals so there is no
full-precision version to disagree with. Reported, not fixed; the brief covers
the rounding shape only.

- **`lab/views/ground.py:39`** re-declares `CRISP_RATIO = 1.20`, which
  `measures.crispness` already exports. **What would make it fail:** any
  change to the canonical constant. The lab view would then draw a band
  disagreeing with the fixture's published definition, silently, because the
  two agree today and nothing compares them. This is PRACTICE §2 warning 2 —
  *call the function the tool already uses* — and the one-line repair is an
  import.
- **`characterize.py:77`** copies `{n_neighbors: 30, min_dist: 0.08,
  metric: cosine}` from the fixture specs, and says so in its comment.
  **What would make it fail:** a spec changing its `projection.params`, after
  which a user's ground view is drawn differently from the published one while
  the comment claims it is drawn the same way. Weaker, because the projection
  is declared and illustrative and nothing is decided from it.

## Measurements

All from `tasks/scratch/044d_survey_bands.py` and
`044d_survey_literals.py`, reading the published ground views. Percentiles are
`threshold_percentile(ratio_distribution(...))` — project code, unmodified.

| | before | after |
|---|---|---|
| fixtures reading outside their own band | **2 of 6** | 0 of 6 |
| endpoint slots where the rounding went the wrong way | **2 of 4** | 0 of 4 |
| largest stored-vs-measured gap | 0.003644 (`sec-filings-10k`, ambiguity) | < 5e-7 by construction |
| `EDGE_EPSILON` as a fraction of the quantile grid step | — | 2 × 10⁻⁶ |

## Verification

| check | result |
|---|---|
| The new test fails on the unfixed tree for the stated reason | **PASS** — 2 failed, 5 passed, naming `sec-filings-10k` and the measured minimum |
| It passes after the fix | **PASS** |
| Both fixtures read inside their own band | **PASS** — recomputed from the parquets, not from the constants |
| The stored edges bound the measured extremes | **PASS** — asserted as the ordering |
| A genuinely outside reading is still flagged | **PASS** — 044b's e5 at 97.74 still outside |
| The check is not vacuous | **PASS** — asserts ≥ 2 ground views were actually read |
| The existing agreement test is untouched | **PASS** — same subject, same `abs=0.05`, still passing |
| No tolerance widened to make a case pass | **PASS** — `EDGE_EPSILON` is sized to the storage granularity, not to the 0.003644 gap it had to clear; the gap was removed by storing precisely |
| No published value moved | **PASS** — no fixture spec, `characterization.json` or MANIFEST touched |
| The survey reported whether or not it found anything | **PASS** — it found nothing of this shape, and two of an adjacent one |
| Full suite | see below |

## Observed, not done

1. **`lab/views/ground.py` re-declares `CRISP_RATIO`.** One-line repair, named
   above; not this brief's shape.
2. **`characterize.PROJECTION_PARAMS` copies the specs' projection block.**
   Named above.
3. **The band is still bounded by three fixtures.** `EDGE_EPSILON` fixes the
   arithmetic; it does nothing about a reference spanning 65 to 91 on the
   ambiguity side. 044b recorded that limit and `docs/FIXTURES.md` carries it;
   044c added a second argument for a fourth and fifth full fixture.
4. **`docs/FIXTURES.md:360–361` displays the bands at two decimals.** Still a
   correct rounding of the stored values, so not edited — and the brief does
   not name the file.

## Repo now contains

| path | what |
|---|---|
| `oneground/measures/test_band_edge.py` | new, 4 tests (7 with parametrisation), written before the fix |
| `oneground/measures/crispness.py` | percentiles at measured precision; `EDGE_EPSILON`; `against_published` uses it; `PUBLISHED_PERCENTILE_BASIS` comment corrected |
| `oneground/measures/ambiguity.py` | percentiles at measured precision, with the two-endpoint instance recorded beside them |
| `tasks/044d-band-edge.report.md` | this report |
| `tasks/scratch/044d_*.py` | two scratch scripts (gitignored) |

## Blocked on developer

Nothing. 044d is stacked on `task-044c`; if 044c merges first this rebases
trivially, and if the two are merged together the order does not matter —
they share no file.
