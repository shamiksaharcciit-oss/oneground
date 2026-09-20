# Task 043 — The provenance foundation: what three positions are waiting on

## Setup
Branch `task-043` from `main`. Commit `task 043:` and push after every
commit. No pod. The work is in `oneground/report/claims.py` and its tests;
nothing here measures a corpus.

## Why

Three separate positions have now independently arrived at the same missing
machinery, and each one wrote around it:

- **`docs/BRIDGE.md` §4** — a VectorDBBench row and an oneground row may share
  a table only when both used the same ground truth, query subset and corpus
  digest. The paper states plainly that *the claim invariant cannot enforce
  this*, because 019 checks that a sentence follows from the rows it cites and
  **a row's provenance is not one of its inputs**. It had to fall back to a
  structural refusal at construction.
- **`docs/LIBRARY.md` §2.2** — the three-valued comparability verdict
  (`comparable` / `not_comparable` / `couldnt_check`) is defined and
  **implemented nowhere**. The only `comparable()` in the tree is
  `calibrate/history.py`, which compares engine identity, not provenance: the
  right shape and the wrong subject.
- **`docs/MODELS.md`, the both-scales rule (task 039b)** — a gap must be
  reported on both the difference and the ratio scale. Task 039b measured that
  `claims.check` cannot enforce it: a `Cite` carries a value with a `source`
  path into a run's artifacts, and **a difference has no such path**. Four
  mutants of a proposal card's `delta` — inflated tenfold, sign-reversed, and
  a ratio silently substituted for a difference while the prose still read
  "rises by" — all returned *no problems*.

Task 039b declined to build a presence-check against `Claim.extra`, because it
would confirm a second number was present while checking neither was right —
the exact defect `claims.py` exists to refuse, wearing the rule's badge.

**Three mentions is enough. This is the task that builds the thing.**

There is also a live beneficiary that is none of the three: the proposal card
already quotes an unchecked derived number. `proposals/verdict.py:97` computes
`delta` as `round((b - a), DECIMALS)` and judges it against a difference
threshold, and nothing verifies the arithmetic or records that a scale was
chosen. It is correct today. Nothing would notice if it were not.

## Do

### 1. The derived cite

A cite whose value is **computed from other cites by a recorded operation that
`check()` re-executes**. Today a `Cite` is
`(member, value, source, outcome, constraint, reason)` and `check()` step 5
compares `value` against what is at `source`. A derived cite has no `source`
because no artifact holds it; what it has instead is an operation and its
operands.

Required behaviour:

- It records **which operation** (`difference`, `ratio`, at least) and **which
  cites** it is over, in an order that matters — `a - b` is not `b - a`.
- `check()` **recomputes** it from the operands and compares to the stated
  value, at a declared tolerance. This is step 5b's move applied to
  arithmetic: 5b stopped believing `holds_for` and derived it from the rows,
  for the reason given there — *a claim that supplies its own truth condition
  is not being checked*.
- The operands are themselves ordinary cites, so they are already checked
  against their sources. A derived cite is therefore checked **all the way
  down to the artifacts**, which is the property that makes it worth building.
- A derived cite quoted in prose is subject to the existing step 6 (a printed
  number must be one the claim cites) and step 7 (a number printed beside a
  member's name must be that member's), without those rules changing.

**Acceptance is the four mutants.** Re-run task 039b's script
(`tasks/scratch/039b-can-the-invariant-see-a-gap.py`, reproduced in this
task's own scratch): the honest delta passes; the inflated, the sign-reversed
and the ratio-substituted-for-a-difference all fail, each naming what it
recomputed and what it got.

### 2. The cross-run row index

`RowIndex` is `{subject: {member: {constraint: fact}}}`, built by
`rows_from_options()` from **one report's** options. A between-corpora gap
spans two runs and cannot be expressed: the two sides cannot both be present.

Required behaviour:

- Rows can be held from **more than one run**, each row knowing which run it
  came from.
- A row carries its **provenance**: at minimum the corpus digest, the ground
  truth it was measured against, and the query subset. `BRIDGE.md` §3.3 says
  the query subset is **not expressible from today's receipts** — no seed, no
  size, no selection is recorded, because no command has ever taken one. Say
  in the report whether that blocks this piece or is additive to it; do not
  invent the receipt here.
- Existing single-run callers keep working unchanged. `report/__init__.py` and
  `proposals/propose.py` are the only two call sites of
  `raise_on_violation`, and neither should need to know this happened.

### 3. The comparability verdict

With (1) and (2) in place, `LIBRARY.md` §2.2's verdict becomes implementable
for the first time: given two rows, are they `comparable`, `not_comparable`,
or `couldnt_check`?

Required behaviour:

- **Three values, and the third is never rounded up.** Two rows whose
  provenance is *unknown* are `couldnt_check`, not `not_comparable` and
  certainly not `comparable`. Missing information is not a verdict about the
  rows.
- It is the **one** implementation. `BRIDGE.md` §4 already states the rule
  that whichever of the three positions is built first builds it and the other
  two cite it rather than deriving a second answer. This task is the first, so
  this task builds it.
- `calibrate/history.py:comparable()` stays where it is and keeps its name;
  it answers a different question (engine identity). Say in the report whether
  the two should share a name, and do not rename either without being asked.

### 4. Point the three positions at it

Each of the three documents currently says the machinery does not exist.
Update each to say what now does and what still does not:

- `docs/BRIDGE.md` §4 — whether the table rule can now be enforced by the
  invariant, or still needs the structural refusal, and why.
- `docs/LIBRARY.md` §2.2 — the verdict is implemented; name where.
- `docs/MODELS.md`, the both-scales rule — its **Status: written, not
  executable** paragraph is the one to revisit. If the rule is now executable
  for claims, say so and say it is still only written for hand-authored
  documents, which is where task 039's own violations were.

### 5. The live beneficiary

Make the proposal card's `delta` a derived cite. This is the smallest real use
of (1) and it is worth doing on its own merits: it is the one artifact in the
project that states a difference and judges against a difference threshold.

Report, do not fix unasked: whether `by_at_least` being a difference —
scale-blind in exactly the way task 039's prediction was — should become a
declared choice. A policy author is currently in the position the 039 brief's
author was in.

## What this may not do

- **Ship a presence-check.** A check that confirms a second number is there
  without checking either number is right is the defect `claims.py` was
  written to refuse, and 039b declined it for that reason. If a piece of this
  can only be built that way, that is a finding and the piece is not built.
- **Rename or repurpose `calibrate/history.py:comparable()`.**
- **Invent the query-subset receipt.** `BRIDGE.md` §3.3 names what would have
  to be added and in what shape. Adding it is a different task.
- **Change `docs/` beyond the four paragraphs named in step 4.**
- Weaken step 6 or step 7 to accommodate a derived cite.

## Acceptance

- The four 039b mutants: one passes, three fail, each naming the recomputation.
- A derived cite is checked to the artifacts through its operands, and there
  is a test that breaks an operand and shows the derived value failing with it.
- `RowIndex` holds rows from two runs, each carrying provenance, and both
  existing call sites are untouched.
- The comparability verdict returns three values, with `couldnt_check` for
  unknown provenance, and a test for each.
- The proposal card's `delta` is a derived cite, and the card's output is
  unchanged in every existing test.
- The three documents say what exists and what does not.
- Full suite green.

## Do not
- Build a check that cannot fail. Every new rule gets a mutant that breaks it,
  on task 042's finding: a check that passed for the wrong reason is worse
  than one that fails.
