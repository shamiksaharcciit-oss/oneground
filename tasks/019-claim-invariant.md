# Task 019 — The claim invariant

## Expected repo state
`main` after 018 and 018b, tree clean, tag `v0.1.0` local and unpushed.
Work on `main`; commit `task 019:`; do not push, publish, or move the tag.
This task must be complete before v0.2 work begins; the lab is almost
entirely presentation, and this is the class of defect it will attract.

## Why
Three tasks running have produced the same defect: a generated sentence or
a rendered cell asserting one option's outcome of another. `{best.outcome}`
said "both carry meets" about an engine that failed, and shipped in a
report. `_options_table` rendered the first verdict for a constraint and
showed a flat green row where one engine met the budget and the other
missed it by an order of magnitude. Both passed every test in the repo.

The measurement layer has an external oracle — ground truth, digests,
exact search — so a wrong number moves and a test catches it. The
presentation layer has none: "does this sentence say something true about
these rows" is not computable from the rows. So the tests that existed
asserted *presence* (the names appear, the page renders, no verdict words
in a couldn't-check row) rather than *correspondence*. 018 fixed coverage.
This task fixes the invariant.

A written rule does not fail a build. `collapse_by_constraint`'s own
docstring stated the precondition it was violating.

## Do

1. **Make claims structured before they are prose.** Every generated
   sentence in the report, the decision log, the HTML, and the console
   summary is produced from a `Claim` object carrying: the predicate, the
   set of options it quantifies over, the constraint, the value(s) cited,
   and the source field(s). Prose is rendered *from* the Claim; no module
   may format a sentence about rows any other way. Grep-guard it: a test
   fails on any f-string or `%`-format in the rendering modules that
   interpolates an outcome, a verdict, an engine name, or a measured value
   outside the `Claim` renderer.

2. **The invariant, as an executable check.** For every `Claim` produced
   by a run:
   - every option named or quantified over appears in the cited rows;
   - every value cited equals the value at its stated source field;
   - a universal quantifier ("both", "all", "every", "each", "neither",
     "none") is admissible only if the predicate holds for **every**
     member of the set — computed from the rows, not from the winner;
   - an existential ("one", "the better of", "only") names the members it
     holds for;
   - a negation ("do not all", "not every") is recognised as a negation
     and is not checked as the corresponding assertion — the guard that
     couldn't tell an assertion from its negation is itself a known
     defect in this repo.
   Run it over every Claim in every report generated in the suite, and
   over the two fixtures' real reports.

3. **Adversarial generation, not example tests.** A property test builds
   row sets across the full outcome space — 1 to 5 options; every
   combination of meets/fails/couldn't-check; identical outcomes; a single
   option; an option with no measurement; two engines where one is
   unanswerable; values that tie exactly; values differing by less than
   the calibration tolerance — renders the full report for each, and
   asserts the invariant on every Claim. It must exercise the paths that
   produced both historical defects, and the report must state how many
   combinations were generated and checked.

4. **Mutation testing, scoped to the rendering layer.** Introduce
   deliberate faults and assert the suite catches each: restore
   `{best.outcome}`; restore first-verdict-per-constraint; swap two
   options' values; change a cited source field to a neighbouring one;
   turn an existential into a universal; drop a failing option from a
   summary. Each mutant must fail at least one test, and the report must
   name which test caught which mutant. A mutant that survives is a gap to
   close in this task, not to record.

5. **Reconstructibility of the whole document.** A check that, given only
   `report.json`, every sentence in `report.html` and in the console
   output can be regenerated identically. Nothing in the rendered surfaces
   may exist that the structured record does not contain — this is the
   same principle as the fixture's receipts, applied to prose.

6. **The historical defects as named regression tests**, each with the
   report it shipped in and the sentence it produced, so a future reader
   knows what the test is protecting against:
   `test_015_report_said_both_carry_meets_when_one_failed`,
   `test_017e_html_showed_flat_green_when_pgvector_missed_by_40x`.

7. **Docs.** `docs/CLAIMS.md`: the rule in one page — what a Claim is, the
   invariant, why the presentation layer needs one when the measurement
   layer does not, and the two defects that motivated it. Link it from
   CONTRIBUTING.md as a gate for any contribution that renders text about
   rows.

## Acceptance
- No sentence about rows is produced outside the `Claim` renderer; the
  grep-guard proves it.
- The invariant runs over every Claim in every generated report in the
  suite and over both fixtures' real reports; report the counts.
- Adversarial generation covers the stated combination space; report the
  number generated.
- Every mutant is caught; each named with the test that caught it.
- `report.html` and the console are fully reconstructible from
  `report.json`.
- `docs/CLAIMS.md` exists and is linked from CONTRIBUTING.md.

## Do not
- Weaken a check to make a mutant pass. Allowlist a sentence rather than
  fix it. Push, publish, or move the tag.
