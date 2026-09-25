# Report: 058-library-card-validator

## Repo state expected vs found

Expected `main` with `docs/LIBRARY.md` as the position and no
`oneground/library/` package. Found exactly that; branch `task-058`
created from `main`.

## What was done

**`oneground/library/card_schema.py`** — the card schema and its
validator, per §7's own sequencing ("the card schema and its validator...
the refusals before the capability").

**A library card is a different artifact from the private `card.json`
`propose` writes**, per §2.0's own instruction, and this module treats it
that way: it validates whatever dict a caller submits against §2's
required shape. It does not read a workdir, does not build a card from
one, and does not transform a private card into a public one — per §2.0,
the private card "carries citations that prove internal consistency and
almost nothing a stranger can check... the wrong shape for a public one,"
so reusing its shape here would have built the validator around the thing
§2 says must not ship.

**Every required field from §2.1 (corpus), §2.2 (instrument) and §2.3
(finding)**, as dotted paths walked generically against the submitted
dict — the same declarative shape `oneground/intake/__init__.py`'s
`DECLARED_REQUIRED` already uses for "name the field, refuse rather than
guess." A field absent at any level is missing; `embedding_model` and
`finding.decomposition` are declared `MAY_BE_NULL` — the key must be
present, the value may honestly be `None` (§2.1: "A requirement that
refuses most cards is a defect in the requirement").

**The three refusals the brief named as the point, each with its own
test:**

1. **No corpus characterization → refused, every missing field named at
   once.** `test_a_card_with_no_corpus_characterization_is_refused_
   naming_every_field` deletes the whole characterization block and
   asserts all four headline fields are named in one raised message —
   §3's own instance: "A card without a characterization is not
   published; it is rejected at submission, with the missing fields
   named."
2. **A prediction digest not cited by the run that produced it is not a
   card.** `_prediction_problem` refuses when `prediction.cited_by_run`
   is not `True`, quoting §5 directly in the refusal message. Tested by
   flipping the flag and by removing the digest outright.
3. **The denominator is carried or explicitly withheld — never partial,
   never silently absent.** `_denominator_problem` accepts either both
   integer counts or the literal string `"withheld"`; a missing
   denominator, a partial one (one count present, one absent), and a
   wrong-shaped one (a bare integer) are each refused, each with its own
   test.

**One further refusal §5 names explicitly, added for the same reason the
other two were named rather than left implicit:** a card whose
comparability verdict is `not_comparable` is refused as a result — "the
card says so and is not published as a result. It may be published as an
observation" (this module does not build the observation path, per scope
below). `couldnt_check` is accepted, not refused, per §5's own correction
of the naive rule: "a rule that refused it would refuse everything." Both
directions are tested (`test_not_comparable_is_refused_as_a_result`,
`test_couldnt_check_comparability_is_accepted`), plus a card carrying an
unrecognised verdict string.

## Measurements

13 of 13 tests pass. Nine are mutants proving a specific refusal fires for
the reason claimed (missing characterization, missing/uncited prediction
digest, `not_comparable`, an unrecognised verdict string, a missing/
partial/wrong-shaped denominator, `embedding_model` absent vs. present-
and-null); the remaining four prove the well-formed card and each
legitimate variant (`denominator: withheld`, `comparability: couldnt_
check`, `embedding_model: null`) are accepted rather than refused —
without these, a validator that refused everything would also pass the
refusal tests.

## Verification

`oneground/library/test_card_schema.py`: 13 passed. Full suite, guard,
identifier scan and `site/teaser/`: reported at the merge, per the
established pattern.

## Observed, not done

**§7 sequences the library "not before proposals tier 2,"** and this task
was built anyway, per explicit instruction: that sequencing is about the
library's transport and submission surface, which depend on tier-2 triage
existing to have proposals worth publishing at scale; the card schema and
its validator are a question about what a card must contain, and answer
it regardless of whether tier 2 exists yet. Nothing in §2 or §5 reads as
conditional on tier 2.

**The denominator ledger (§2.4: "written by `propose` on every run...
living beside the corpus") was not built.** This task's `denominator`
check validates the *shape* a card's denominator must have; it does not
count proposals, does not touch `oneground/proposals/propose.py`, and
does not create the append-only ledger §2.4 specifies. A caller supplies
the counts (or `"withheld"`); where they come from is unbuilt.

**No private-card-to-library-card transformation.** `oneground/proposals/
card.py`'s existing card does not carry most of §2's required fields
(characterization, denominator, card id, publisher, licence, an explicit
comparability verdict as opposed to its ingredients). Building that
transformation — reading `characterization.json`, computing the
comparability verdict via `oneground.comparability`, assembling this
module's expected shape — is a separate task this one does not attempt,
consistent with §7's phased sequencing: refusals before capability.

**No submission surface.** `submit_card` validates and raises; nothing
writes an accepted card anywhere, per §6's own "the transport... is its
own decision," left unsettled there and untouched here.

## Repo now contains

New:

- `oneground/library/__init__.py`
- `oneground/library/card_schema.py`
- `oneground/library/test_card_schema.py` — 13 tests
- `tasks/058-library-card-validator.report.md` — this file

## Blocked on developer

Nothing. Committing, pushing to `task-058`, and merging into `main` once
its checks are green and task 057 has already merged, per standing
instruction.
