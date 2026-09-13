# Report: 019-claim-invariant

## Repo state expected vs found

| the brief expected | found |
|---|---|
| `main` after 018 and 018b | **after 018c as well.** 018c was committed first, in this same session, at the developer's instruction: `718a445 task 018c: a spawn budget and a readiness budget are not the same number`. |
| tree clean | yes |
| tag `v0.1.0` local and unpushed | yes, on `6ddcb5e`. **Not moved.** `origin` carries only `v0.1.0-preview`. |
| 764 passed, 1 skipped | 768 passed, 1 skipped — 018c added four |

`origin/main` is at `643e96f`; 018b, 018c and this task are unpushed. Nothing
here is pushed, published, or tagged.

## What was done

### Why the presentation layer needed an oracle

The measurement layer has one. Recall is checked against exact k-NN, an
artifact against its digest, a published value against the fixture that
published it. A wrong number **moves**, and something notices.

A sentence does not move. "Does this say something true about these rows" is
not computable once the sentence is a string, so every test that could be
written about one asserted **presence** — the names appear, the page renders,
no verdict word in a couldn't-check row — rather than **correspondence**. That
is why both defects passed every test in the repository, and why 018 fixing
*coverage* did not fix this: knowing every rendering path is driven says
nothing about whether what they render is true.

### 1. Claims before prose

`oneground/report/claims.py`. A `Claim` carries the predicate, the quantifier,
the `scope` it is about, the `holds_for` it is true of, the `cites` (each
value with its member, outcome and **source field**), and — where a sentence
asserts more than one thing — `parts`.

**Fourteen claim kinds** are rendered, and `render()` raises on a kind it does
not know, so a new sentence is a new renderer rather than an f-string
somewhere else:

    analogy · capacity · engine_comparison · engines_meeting · fails ·
    indistinguishable · meets · meets_environment · no_engine_comparison ·
    not_run · qps_max · recommendation · scope · to_resolve

plus four presentation surfaces that assert exactly what a sentence does —
the HTML verdict cell, the recommendation rows, the console option row, and
the runner-up lines. **017e's defect was in a cell**, so a cell is rendered
here too.

**The prose is byte-identical to before.** This is a refactor of where
sentences are composed, not of what they say; the existing report tests, which
assert exact fragments, pass unchanged.

**A sentence that asserts several things is several claims.** The first run of
the invariant reported 203 violations and almost all of it was one modelling
gap rather than bad prose:

> … qdrant is the better of 2 engines … **Both** were measured on the same
> sample, on the same host, sequentially. The verdicts differ …

Three assertions quantifying over two different sets: existential over the
engines, universal over the engines, and a denial. One `quantifier` field
cannot be true of all three, and stretching the audit to tolerate it would
have been weakening the check to fit the sentence. So a Claim may carry
`parts`, each with its own quantifier, its own set and its own fragment; the
universal-word audit runs **per fragment**, which is the grain at which
"both" means anything, and the composite is required to actually contain its
parts' fragments so parts cannot become decoration.

**The grep-guard.** `test_claims.py` walks the AST of `report/__init__.py` and
`report/html.py` and fails on any f-string, `%`-format or `.format()` whose
interpolated expression touches `.outcome`, `.engine`, `.value`, `.reason`,
`.verdicts`, `.engines_meeting` or `.holds_for`. It reads expressions rather
than text, because a regex would flag the docstrings that quote the defects —
including the guard's own — and be relaxed on its first day. A negative
control proves it catches `%` and `.format()` as well as f-strings, since a
guard that knew only about f-strings would teach people to write `%`.

It found **20 sites**, all now routed through the renderer: `_not_on_every_engine`,
`_how_to_resolve`, `runner_up_lines`, the console `_summary` rows, and four
places in `html.py`. What the HTML gets back is a plain presentation structure
— strings already chosen — so the page assembles tags and reaches into no
Verdict. That boundary is stated in `docs/CLAIMS.md` so it is not discovered
later as a loophole.

`html._label` became dead in the process and was **removed** rather than left
orphaned; 018b's execution counter caught it, which is the guard from the
previous task doing its job on this one.

### 2. The invariant

`claims.check(claim, rows)` returns every way a claim fails to follow from its
rows. Seven rules; the two that were added because a mutant survived are
marked:

1. `holds_for` is part of `scope`.
2. Every member quantified over appears in the cited rows.
3. A **universal** is admissible only if the predicate holds for every member;
   an **existential** must name the members it holds for.
4. A **negation** is recognised as a negation and never checked as the
   assertion it contains — the guard that could not tell "the verdicts differ"
   from a uniformity claim is itself a defect this repository shipped (017f).
5. Every cited value, outcome and source matches the row at its stated field.
6. **`holds_for` is recomputed from the rows, not believed** — *added after a
   mutant survived*. The rule it is recomputed under is named on the claim:
   `any`, `all` or `no_fails`.
7. **A number printed beside a member's name is that member's** — *added after
   a mutant survived* — compared at the precision the prose printed.

Violations **raise before `report.json` is written**. A report whose sentences
do not follow from its own rows is not produced.

### 3. Adversarial generation

`test_claims.py` generates **188 row sets** covering the space the brief names
— 1 to 5 options; every combination of meets/fails/couldn't-check; one and two
engines; identical outcomes; a single option; an option with no measurement;
two engines where one is unanswerable; values that tie exactly; values
differing by less than the calibration tolerance — and checks **1,294 claims**
across them. A separate probe walks all **81** two-engine outcome combinations
over two constraints: **716 claims, 0 violations**.

The generation asserts the two historical shapes are present rather than
hoping they are, and the floor on the count is set *below* what the generator
produces, so a generator that quietly shrank fails rather than the number
being tuned up to whatever today happens to be.

### 4. Mutation testing

`tasks/scratch/019-mutants.py`. Six faults, installed by monkeypatching so the
repository is never left broken, each offered to ten named tests.

| mutant | caught by |
|---|---|
| restore `{best.outcome}` | `test_claims.test_the_invariant_holds_on_every_generated_row_set`, `…on_the_shape_both_defects_had`, `test_015_report_said_both_carry_meets_when_one_failed` |
| restore first-verdict-per-constraint | `test_claims.test_017e_html_showed_flat_green_when_pgvector_missed_by_40x`, `test_no_lent_outcomes.test_every_surface_that_shows_a_mixed_constraint_names_both_engines`, `…test_the_options_table_cell_shows_every_engines_verdict` |
| swap two members' values | `test_claims.test_the_invariant_holds_on_every_generated_row_set`, `…on_the_shape_both_defects_had`, `test_015_report_said_both_carry_meets_when_one_failed` |
| cited source field moved to a neighbour | `test_claims.test_the_invariant_holds_on_every_generated_row_set`, `…on_the_shape_both_defects_had` |
| existential turned into a universal | `test_claims.test_the_invariant_holds_on_every_generated_row_set`, `…on_the_shape_both_defects_had` |
| a failing option dropped from a summary | `test_no_lent_outcomes.test_the_meets_line_says_when_it_is_not_true_of_every_engine` |

**6 mutants, 0 survivors.** Getting there took three rounds, and all three are
worth recording because two were gaps and one was a bad mutant:

- **"existential turned into a universal" survived the first run.** Setting
  `quantifier=UNIVERSAL` and `holds_for=scope` passed, because every rule read
  `holds_for` as given. *A claim that supplies its own truth condition is not
  being checked.* Closed by rule 6.
- **"swap two members' values" survived the first run.** The prose read
  `qdrant 119.10 (meets); pgvector 200.00 (fails)` — each number is one the
  claim cites, attached to the wrong member. The check asked "is this number
  cited *anywhere*" when the question is "is it cited *for this member*",
  which is the same species as the defect the module exists for. Closed by
  rule 7.
- **Then it survived again — and that time the mutant was broken.** It patched
  `cite_list`, which with two engines is called twice with one cite each, so
  `len(cites) >= 2` was never true and nothing was mutated. **A mutant that
  does not mutate is a test result that means nothing**, and it read exactly
  like a gap in the guard. Rewritten to swap the values on the built claim,
  where the swap is real; caught immediately.

### 5. Reconstructibility

`report.json` gains a `claims` block beside `decision_log`. Three tests:

- every decision-log sentence on the rendered page is in the record, verbatim;
- claims round-tripped through `as_dict`/`from_dict` produce identical text
  and identical log entries, and **re-render identically from their own
  record** — so the record carries what the renderer needs, not just the
  finished string;
- a negative control: a claim with a field the renderer needs removed must
  fail to re-render, or the round trip proves nothing.

### 6. The two historical defects, named

`test_015_report_said_both_carry_meets_when_one_failed` — with pgvector's
**112.63** of an offered 200, the row task 015's report said "both carry
meets" about. It asserts the claim is `EXISTENTIAL`, that the sentence carries
`112.63 (fails)` and "the verdicts differ", **and** that the invariant refuses
the 015 sentence if it is forged by hand.

`test_017e_html_showed_flat_green_when_pgvector_missed_by_40x` — qdrant at
**7.72 ms** against the 40 ms budget, pgvector at **317.41 ms**. It asserts
both engines and the failing number are on the page, and that the structured
record carries both verdicts so the cell can be rebuilt from it.

### 7. Docs

`docs/CLAIMS.md`: what a Claim is, the seven-rule invariant, why the
presentation layer needs an oracle when the measurement layer does not, the
two defects verbatim, what is enforced mechanically, a section for anyone
adding a rendering surface, and — deliberately — **what this does not do**.
Linked from `CONTRIBUTING.md` as a gate, in the list of rules that follow from
the three-outcome rule.

## Measurements

### The suite

| point | passed | skipped |
|---|---|---|
| after 018c | 768 | 1 |
| after 019 | **780** | 1 |

**+12**, all in `test_claims.py`. `pytest --collect-only` reports **781
collected**, which is 780 run plus the one skip (the live RunPod test). The
two tests that read the real `runs/` workdir ran rather than skipping, because
this checkout has one; on a fresh clone they skip and name the command that
produces one.

### The invariant

| where | claims | violations |
|---|---|---|
| 188 generated row sets (`test_claims`) | **1,294** | 0 |
| 81 two-engine outcome combinations (probe) | **716** | 0 |
| `runs/arxiv-150k-via-characterize` (real, two engines) | 37 | 0 |
| `runs/stackexchange-150k-via-characterize` (real) | 16 | 0 |
| `runs/arxiv-smoke` (real) | 8 | 0 |

**61 claims across three real reports, 0 violations.** All three were
regenerated through the invariant, which now raises on the way out.

### What the invariant found while being built

It went red 203 times on its first run and every round of fixing it found
something. The counts, in order: **203 → 183 → 111 → 49 → 16 → 0**. What each
round was:

| red | what it was |
|---|---|
| 203 | sentences asserting several things at once — the modelling gap, fixed with `parts` |
| 183 | two parts of mine citing no rows, and an existential attached to the clause that names nobody |
| 111 | parts quantifying over **constraints** while citing rows keyed by **engine** |
| 49 | `meets` quantifying over every engine while citing only the meeting ones — the 015 shape, in my own builder |
| 16 | "Every constraint was decidable" declared as quantifying over nothing |

Then, pointed at the **real** arXiv report, it found one more that no
synthetic fixture had: **`rows_from_options` keyed facts by member alone**, so
with eight configurations the same engine's eight verdicts collapsed into one
and every claim was checked against whichever option was written last. That is
one row standing in for a set — the defect this module exists for — in the
checker. Fixed with `RowIndex`, keyed per option.

**And then the probe script written to check the library made the same
mistake**, flat-keying rows rebuilt from `report.json` and reporting 14
violations against a correct report. Worth recording: the flat shape is the
one that comes to hand, which is why it needed a type rather than a
convention.

### The grep-guard

```
before: 20 sites formatting a verdict into a string
  oneground/report/__init__.py   9  (_not_on_every_engine, _how_to_resolve,
                                     runner_up_lines, the console rows,
                                     compare_engine_claims' predicate)
  oneground/report/html.py      11  (_recommendation, _verdict_cell,
                                     _options_table)
after:  0
```

## Verification

**Passed.**

- The grep-guard finds nothing, and its own negative control proves it sees
  `%` and `.format()` as well as f-strings.
- The invariant holds on 1,294 generated claims, 716 probe claims and 61 real
  ones, and raises before a report is written.
- All six mutants caught; every one named with the test that caught it.
- The page and the console are reconstructible from `report.json`, with a
  negative control proving the round trip is not vacuous.
- The prose is unchanged: the report tests that assert exact sentence
  fragments pass without edits.
- 018b's execution counter and rendering-path registry both caught this task's
  refactor and were updated deliberately rather than relaxed.

**Couldn't check.**

- **`Verdict.reason` is not checked here.** A reason is the verdict layer's own
  sentence, composed in the layer that holds the values, and quoting it
  verbatim is what makes the log traceable to `verify.json`. The claim layer is
  forbidden from *adding* a quantifier or a number, not from repeating one. A
  false reason would pass here and fail in `test_verdict.py`. Stated in
  `docs/CLAIMS.md` under "what this does not do".
- **`holds_rule: no_fails` mirrors `verdict.engines_meeting`.** A rule wrong in
  both places would pass. What the check buys is that the rule is written down
  beside the sentence rather than living only in a function three files away.
- **Nothing ran on a pod.** The real reports are regenerated from workdirs
  already on disk; no session was created and no money was spent.
- **Tier 2's `_declared_log` still uses the `add()` path** for sentences that
  are not about rows — an analogy is about a fixture, not about this run's
  measurements. Those claims carry `quantifier=none` and no cites, so rules 5
  to 7 have nothing to check. See *Observed, not done*.

## Observed, not done

- **Tier 2 sentences are claims in name only.** `_declared_log` builds them
  through the compatibility `add()` helper with no scope and no cites. They
  assert things about a *fixture's* published values rather than this run's
  rows, so the invariant has nothing to compare them against — which is
  correct, and also means the guard does not cover them. Giving them a rows
  source (the fixture spec) would extend the invariant there; the brief scopes
  this task to the report's own rows.
- **The HTML's colour is a claim, and it is only checked indirectly.** A cell's
  CSS token comes from the renderer's collapsed outcome, so a wrong colour
  requires a wrong outcome — but nothing asserts that `teal` means `meets`
  beyond `OUTCOME_TOKEN` itself. A reader who cannot see the text sees only the
  colour.
- **`qps_max`'s stop reason quotes p99 numbers the claim does not cite.** They
  are declared as `literal_numbers` rather than modelled, because they belong
  to the ramp rather than to any member. A cite per rung would model them
  properly.
- **The invariant runs on `report`, not on `verify` or `characterize`.** Both
  print sentences about measurements. Neither compares rows across members, so
  neither has shown this defect — but neither is covered.
- **188 row sets is not the whole space.** Three or more engines, and options
  that differ in which constraints they carry at all, are not generated. Both
  are reachable shapes; neither has occurred.

## Repo now contains

New:

    oneground/report/claims.py              the Claim, the invariant, the only
                                            renderer; 14 sentence kinds and 4
                                            presentation surfaces
    oneground/report/test_claims.py         12 tests: the grep-guard and its
                                            control, adversarial generation,
                                            the two named regressions,
                                            reconstructibility, the real
                                            reports
    docs/CLAIMS.md                          the rule in one page
    tasks/019-claim-invariant.report.md     this report

Changed:

    oneground/report/__init__.py            decision_claims / compare_engine_claims
                                            / qps_max_claims build Claims;
                                            report.json carries them; the run
                                            raises on a violation before writing
    oneground/report/html.py                the page assembles tags from the
                                            renderer's strings; `_label` removed
    oneground/report/test_no_lent_outcomes.py  the kind walk reads the Claim
                                            shape; `_outcome_cell` classified
    CONTRIBUTING.md                         CLAIMS.md as a gate

Not tracked (`.gitignore:62`):

    tasks/scratch/019-invariant-probe.py    81 combinations, 716 claims
    tasks/scratch/019-real-reports.py       the invariant over the real reports
    tasks/scratch/019-mutants.py            six mutants, ten candidate tests

## Blocked on developer

Nothing new, and nothing in this task touches the release artifacts. The 018
list stands: push `main` and the `v0.1.0` tag, create the release with both
assets, paste `RELEASE_NOTES.md`, `twine upload`. The tag still points at
`6ddcb5e`; 018b, 018c and 019 sit above it and are **not** part of `0.1.0`.
