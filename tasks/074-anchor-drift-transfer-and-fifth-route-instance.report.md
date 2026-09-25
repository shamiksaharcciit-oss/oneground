# Report: 074-anchor-drift-transfer-and-fifth-route-instance

## Repo state expected vs found

Expected `main` at `2e997e4` (task 073's merge), with task 073's own
report carrying the bge-outside-its-own-band observation as a cross-check
paragraph rather than a fixtures-level finding, no explicit statement
that the e5 transfer block had just been exercised for real for the
first time, and the render tool's stale-truncation-file defect diagnosed
but not fixed. Found exactly that. No branch needed for the docs/report
edits; the two script fixes are the only code change, made directly
against `main` at that commit per the developer's own three-item
follow-up to the accepted task 073 result.

## What was done, per the three items asked

**1. The anchor-drift observation moved to `docs/FIXTURES.md`, beside the
band's own definition.** Added immediately after the published-band table
(the same place `arxiv-smoke`'s exclusion and the sample-size floor are
recorded), stating the gap precisely -- `bge-base-en-v1.5`'s own
re-embedding of `stackexchange-150k` reads the crispness threshold at the
99.19th percentile against a published 98.83rd, **0.36 percentile points
outside the band's own upper edge, which that same corpus's own value
set** -- and stating plainly that it was found by cross-checking a
different result against the band, not by testing the band itself.
Task 073's report was edited to drop the full discussion and point here
instead, per the instruction that it does not belong in a cross-check
paragraph.

**2. Said plainly, in task 073's report: the e5 distinction is the
transfer machinery earning its existence.** `transfer` (task 044) had, by
task 073, only ever been exercised against in-band or synthetic readings.
Both e5 cells landing outside the calibrated band on a real full-scale
embedding is the first time the mechanism has answered the question it
was built to answer, for real -- and it answered as designed: a count
with its own percentile stated, not a refusal and not a silent number.

**3. The render tool's stale-truncation-file defect: fixed, and added as
a fourth instance to the finding.** `corpora/036-truncation-per-model.py`
gained an overridable output path (`ONEGROUND_036_TRUNC_OUT`, mirroring
`036-ordering-experiment.py`'s own `ONEGROUND_036_OUT`); `run_036_models.
sh` now sets it to `$OUT_DIR/036-truncation-results.json` before running
the truncation script, so the fresh file is packed into `036-models.tgz`
alongside the ordering results, not left outside it; `corpora/
036-render-ordering.py` gained the matching read-side override so a
specific fetch's own copy can be named. `tasks/finding-a-check-that-
takes-a-different-route-than-production.md` now carries this as evidence
item 4, with the count corrected throughout ("three" to "four" wherever
it appeared), and the intro paragraph records the developer's own count
of a related fifth instance -- the `tasks/scratch/` git-bundle gap found
in tasks 065-066, the same shape met first on the input side.

## Measurements

- Anchor-drift gap: 99.186... - 98.829571 = 0.357 percentile points.
- `docs/FIXTURES.md`: one new paragraph, placed beside the band table
  it discusses.
- Finding document: evidence count 3 -> 4, every reference to "three"
  corrected, one new item added with its own fix description.

## Verification

Passed: `py_compile` on both modified `corpora/036-*.py` files;
`bash -n` on `run_036_models.sh`; confirmed by direct read that
`036-truncation-per-model.py`'s `OUT` and `036-render-ordering.py`'s
`TRUNC` now read the identical environment variable name
(`ONEGROUND_036_TRUNC_OUT`), so a value `run_036_models.sh` sets for the
writer is the same name a reader would set to find that writer's output.
`identifier_findings()`: `[]`.

Not run: a full pod session to re-exercise the writer/reader path for
real -- the developer's brief was to fix the packaging and record the
finding, not to re-run `036-models.yaml` again; task 073's result already
stands and is not being re-measured.

## Observed, not done

None. This closes the follow-up the developer asked for on the accepted
task 073 result.

## Repo now contains

- `docs/FIXTURES.md` (modified) -- anchor-drift finding beside the band
  table.
- `tasks/073-036-full-size-ordering-result.report.md` (modified) -- the
  transfer-block sentence added; the anchor-drift paragraph replaced with
  a pointer to `docs/FIXTURES.md`.
- `corpora/036-truncation-per-model.py` (modified) -- overridable `OUT`.
- `corpora/036-render-ordering.py` (modified) -- overridable `TRUNC`.
- `corpora/run_036_models.sh` (modified) -- sets
  `ONEGROUND_036_TRUNC_OUT` into `$OUT_DIR` before the truncation step.
- `tasks/finding-a-check-that-takes-a-different-route-than-production.md`
  (modified) -- fourth evidence item, count corrected, fifth-instance
  note added to the intro.
- `tasks/074-anchor-drift-transfer-and-fifth-route-instance.report.md`
  (new).

## Blocked on developer

None. Per the developer's own instruction, this closes task 036's
outstanding thread; no further work is queued.
