# Claims — the rule for any sentence about rows

A number in this project has an oracle. Recall is checked against exact k-NN;
an artifact is checked against its digest; a published value is checked against
the fixture that published it. A wrong number *moves*, and something notices.

**A sentence has no oracle.** "Does this say something true about these rows"
is not computable once the sentence is a string, so every test that could be
written about one asserted **presence** — the names appear, the page renders,
no verdict word shows up in a couldn't-check row — rather than
**correspondence**. That gap shipped twice.

---

## The two defects

**Task 015.** `compare_engines` ended `and both carry {best.outcome}` — the
*winner's* verdict, asserted of every engine. The report said:

> qdrant 200.00 is the better of 2 engines … **and both carry meets**

about a pgvector row that had sustained **112.63** of an offered 200, which is
a `fails`. The ranking was right. The sentence was wrong, and the sentence is
what gets read. It was quoted in task 015's own report without being caught.

**Task 017e.** `html._options_table` rendered `Option.verdict_for(name)` — the
**first** verdict for a constraint. On a configuration whose p95 met the 40 ms
budget on Qdrant at **7.72 ms** and missed it on pgvector at **317.41 ms**, the
page showed one flat green `meets` cell. The failing number appeared nowhere.

Both passed every test in the repository.

---

## The rule

> **A sentence about rows is built as a `Claim` and rendered from it.**

`oneground/report/claims.py` is the only module that may turn a verdict into
words. A `Claim` carries:

| field | what it is |
|---|---|
| `predicate` | what is asserted |
| `quantifier` | `universal` / `existential` / `negation` / `none` |
| `scope` | every member the claim is about |
| `holds_for` | the members the predicate is true of — **computed from the rows** |
| `cites` | each value, its member, its outcome and its **source field** |
| `constraint`, `subject`, `environment` | what and where |
| `parts` | a sentence that asserts several things is several claims |

Prose is rendered *from* the Claim. `report.json` carries every Claim beside
the `decision_log` it produced, so the record is a receipt for the prose in
exactly the way `MANIFEST.sha256` is a receipt for the bytes.

## The invariant

`claims.check(claim, rows)` returns every way a claim fails to follow from the
rows it cites:

1. **`holds_for` is part of `scope`.** A claim true of somebody outside the
   set it is about is not a claim about that set.
2. **Every member quantified over appears in the cited rows.**
3. **A universal is admissible only if the predicate holds for every member**,
   and an **existential must name the members it holds for** — "the better of
   two" without saying which is not a statement anyone can use.
4. **A negation is recognised as a negation** and is never checked as the
   assertion it contains. The guard that could not tell "the verdicts differ"
   from a uniformity claim is itself a defect this repository has shipped
   (task 017f).
5. **Every cited value equals the value at its stated source field**, and
   every cited outcome and source matches the row.
6. **`holds_for` is recomputed from the rows, not believed.** A claim that
   supplies its own truth condition is not being checked; the rule it is
   recomputed under (`any`, `all`, `no_fails`) is named on the claim.
7. **A number printed beside a member's name is that member's**, compared at
   the precision the prose printed. "Is this number cited anywhere" is not the
   question.

Violations raise before `report.json` is written. A report whose sentences do
not follow from its own rows does not get produced.

## What is enforced mechanically

- **The grep-guard.** `test_claims.py` walks the AST of `report/__init__.py`
  and `report/html.py` and fails on any f-string, `%`-format or `.format()`
  that interpolates `.outcome`, `.engine`, `.value`, `.reason`, `.verdicts`,
  `.engines_meeting` or `.holds_for`. It reads expressions rather than text,
  because a regex would flag the docstrings that quote the defects — this page
  included — and be relaxed on its first day.

  The boundary, stated so it is not discovered later as a loophole: **a
  rendering module may not interpolate a Verdict or Option attribute.** Once
  the renderer has turned rows into strings, using those strings is what
  rendering is.

- **Adversarial generation.** 188 row sets — 1 to 5 options, every combination
  of meets/fails/couldn't-check, one and two engines, an option with no
  measurement, an engine that is unanswerable, values that tie exactly and
  values inside the calibration tolerance — with all **1,294** claims checked.

- **Mutation testing.** Six deliberate faults, each caught: restoring
  `{best.outcome}`, restoring first-verdict-per-constraint, swapping two
  members' values, moving a cited source field, turning an existential into a
  universal, and dropping a failing option from a summary.

- **Reconstructibility.** Every sentence on the page is in `report.json`
  verbatim, and every Claim re-renders identically from its own record.

## If you are adding something that renders text about rows

1. Build a `Claim`. Compute `holds_for` from the rows — never from the winner,
   never from the first row, never from the one you already had in hand.
2. Add a renderer in `claims.py`. There is no second place to put it; the
   guard will find one.
3. If your sentence asserts more than one thing — and "X is the better of two,
   and both were measured the same way" is two things — give it `parts`. Each
   part carries its own quantifier and its own fragment, because "both" means
   something only at the grain of the clause containing it.
4. If your claim asserts an outcome, set `asserts_outcome` and `holds_rule` so
   the checker recomputes rather than believes you.

## A paragraph inside a measurement row is prose nobody reviewed as prose

A narrower rule than the claim invariant, arrived at the same way — by a guard
catching it. Task 035 attached an explanatory note to the return value of its
decomposition, so every measured row carried the paragraph explaining what its
three numbers meant. It seemed helpful: the explanation travelled with the
thing it explained.

It was caught by the verdict-language guard, on the word **"pass"** in "what
the first pass lost". The guard was right for a reason adjacent to the one it
was written for, and the word was the symptom rather than the fault.

**A row carries measurements. A caption is a module constant that the report
prints beside them.** Three reasons, in increasing order of importance:

1. A paragraph repeated once per configuration is not readable, and a
   twelve-row sweep carries it twelve times.
2. A receipt is compared byte for byte across runs. Prose in it is prose that
   has to be identical forever, or a wording improvement moves a digest.
3. **Nobody reviews it as prose.** A sentence in a document is read by someone
   deciding whether it is true. The same sentence inside a dict literal,
   beside four floats, is read as plumbing — which is exactly how a claim
   about what a number means avoids every check the project has for claims
   about what a number means.

The third is the general form and the reason this rule is here rather than in
a style guide. It applies wherever a note is convenient to attach to a row,
which is everywhere, because attaching it there is always the shortest path.

## What this does not do

- **It does not check `Verdict.reason`.** A reason is the verdict layer's own
  sentence, composed from the values it measured, in the layer that has the
  oracle; quoting it verbatim is what makes the log traceable to `verify.json`.
  The claim layer is forbidden from *adding* a quantifier or a number, not
  from repeating one. A false reason would pass here and fail in
  `test_verdict.py`, which is the right place for it.
- **`holds_rule: no_fails` mirrors `verdict.engines_meeting`.** A rule wrong in
  both places would pass. What the check buys is that the rule is written
  beside the sentence instead of living only in a function three files away —
  which is the difference between the 015 defect being visible and invisible.
- **It says nothing about whether a sentence is worth writing.** It checks that
  what is written follows from the rows.

## Related

- [`oneground/report/claims.py`](../oneground/report/claims.py) — the module
- [`oneground/report/test_claims.py`](../oneground/report/test_claims.py) — the
  guard, the generation, the two named regressions
- [VERIFY.md](VERIFY.md) — the same-environment and same-configuration rules,
  which decide whether two rows may be compared at all
- [../CONTRIBUTING.md](../CONTRIBUTING.md)
