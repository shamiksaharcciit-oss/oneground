# Task 043 — The provenance foundation

## Setup
Branch `task-043` from `main`. Commit `task 043:` and push after every
commit. No pod — and that is load-bearing here rather than incidental: one of
this task's rulings exists precisely so that a developer without a rented
machine is not locked out of a published feature.

## Why

Three positions independently arrived at the same missing machinery and each
wrote around it. Since the first draft of this brief a fourth thing has
happened: **041 shipped part of it**, so one piece changes from *build* to
*cite and extend*.

- **`docs/BRIDGE.md` §4** — a VectorDBBench row and an oneground row may share
  a table only when both used the same ground truth, query subset and corpus
  digest. The paper states plainly that the claim invariant cannot enforce
  this, because **a row's provenance is not one of its inputs**, and falls
  back to a structural refusal.
- **`docs/MODELS.md`, the both-scales rule (task 039b)** — measured: a `Cite`
  carries a value with a `source` path into a run's artifacts, and **a
  difference has no such path**. Four mutants of a proposal card's `delta` —
  inflated tenfold, sign-reversed, and a ratio silently substituted for a
  difference while the prose still read "rises by" — all returned *no
  problems*.
- **`docs/LIBRARY.md` §2.2** — the three-valued comparability verdict.
  **This one is now built**: 041 shipped `oneground/comparability.py` with
  `COMPARABLE / NOT_COMPARABLE / COULDNT_CHECK`, `facts_of(workdir)`,
  `INGREDIENTS`, `verdict(a, b)` and `compare_workdirs(left, right)`. It is
  not to be rebuilt, reimplemented or renamed here.

Task 039b declined to build a presence-check against `Claim.extra`, because it
would confirm a second number was present while checking neither was right —
the exact defect `claims.py` exists to refuse, wearing the rule's badge. That
refusal stands and this task is what replaces it.

There is also a live beneficiary that is none of the three: the proposal card
already quotes an unchecked derived number. `proposals/verdict.py:97` computes
`delta` as `round((b - a), DECIMALS)` and judges it against a difference
threshold, and nothing verifies the arithmetic or records that a scale was
chosen. It is correct today. Nothing would notice if it were not.

## Where this sits in the queue

**After 042d, before 044c.** 042d is five lines and a test and stays where it
is. 044c's centroid question is good and **blocks nothing**; this task
unblocks a feature that is already merged, tested and answering
`couldnt_check` to every question because two fields are missing from the
receipts — and the whole write slice behind it.

## The order of work, and why it is not negotiable

**Step 1 lands first.** It is a receipt change, and until receipts can record
a machine identity the other pieces answer `couldnt_check` to everything: a
row cannot say what produced it, so two rows cannot be compared, so the
verdict returns "unknown" for every pair and the derived cite has nothing to
be checked against. Building the checkers first would produce machinery that
is correct and permanently silent.

**And step 1 stops for a demonstration before the rest is built.** Once the
receipt change lands, produce **one run on this machine that records a
clean-tree commit and a machine digest**, and show the side-by-side verdict
**flip** — `couldnt_check` before, a real verdict after, on the same pair of
runs. Report that and stop.

That is not ceremony. It is the proof that the foundation is the right one:
the whole task rests on the claim that two missing fields are what make the
verdict silent, and a flip on real receipts demonstrates it where an argument
cannot. If the verdict does not flip, the diagnosis is wrong and steps 2–7
are built on it.

## Do

### 1. Machine identity in the receipt — **first, and the ruling is made**

`comparability.INGREDIENTS` already names the defect exactly:

> `machine`: `environment_id` is `local:<os>-<arch>`, a class rather than an
> identity, so two different machines share one; only a recorded pod id
> identifies a machine.

**The ruling, which is decided and not open:**

A **per-installation salted one-way digest**. Generated once, stored locally.
The machine identifier is **never published and never written into a
receipt**. What the receipt records is a **truncated
`sha256(salt + machine identifier)`**.

Two alternatives were considered and both are refused:

- **The platform class** (`local:<os>-<arch>`, today's behaviour) — refused
  because it **asserts a sameness it cannot see**. Two unrelated machines
  share one string, so the verdict would report `same` for runs that have
  nothing in common, which is worse than reporting `unknown`.
- **Pod id only** (today's only identity) — refused because it makes a
  published feature **a demonstration for anyone not renting a machine**. A
  user comparing two of their own local runs would get `couldnt_check`
  forever, for a question their machine can answer.

Required behaviour:

- The salt is generated **once per installation**, stored locally, and is
  never transmitted, published, printed or written to any artifact.
- The digest is **truncated**: enough to distinguish installations, not enough
  to be a stable long-lived fingerprint.
- It must survive the identifier scan and
  `test_no_tracked_file_carries_a_machine_identifier`, by construction rather
  than by redaction.
- **State what it can and cannot assert.** Because the salt is
  per-installation, two installations on one machine produce two digests. The
  field therefore supports *"not the same installation"* and does **not**
  support *"not the same machine"*. Write that where the field is defined, not
  only in this brief. A field whose strength is overstated is the same defect
  as the platform class, one step quieter.

### 2. The derived cite

A cite whose value is **computed from other cites by a recorded operation that
`check()` re-executes**. A derived cite has no `source`, because no artifact
holds it; what it has instead is an operation and its operands.

- It records **which operation** (`difference`, `ratio`, at least) and **which
  cites**, in an order that matters — `a - b` is not `b - a`.
- `check()` **recomputes** it from the operands and compares to the stated
  value at a declared tolerance. This is step 5b's move applied to arithmetic:
  5b stopped believing `holds_for` and derived it from the rows, because *a
  claim that supplies its own truth condition is not being checked*.
- The operands are ordinary cites, already checked against their sources, so a
  derived cite is checked **all the way down to the artifacts**. That property
  is the reason it is worth building.
- Existing steps 6 and 7 apply to it unchanged.

**Acceptance is the four 039b mutants**
(`tasks/scratch/039b-can-the-invariant-see-a-gap.py`): the honest delta
passes; the inflated, the sign-reversed, and the ratio-substituted-for-a-
difference all fail, each naming what it recomputed and what it got.

### 3. The cross-run row index, carrying **two** provenance lists

`RowIndex` is `{subject: {member: {constraint: fact}}}`, built by
`rows_from_options()` from **one report's** options. A between-corpora gap
spans two runs and cannot be expressed.

Required behaviour:

- Rows can be held from **more than one run**, each knowing which run it came
  from.
- **A row carries two provenance lists, and neither subsumes the other:**

  | | what it answers |
  |---|---|
  | **what was measured** | the corpus digest, the ground truth, the query subset |
  | **what did the measuring** | the code version, the library versions, the settings digest, the machine digest from step 1 |

  Two rows can agree completely on one list and differ on the other, in both
  directions: the same corpus measured by two different builds, or two
  different corpora measured by one build. Collapsing them into a single
  "provenance" field would make those two cases indistinguishable, and they
  license entirely different sentences.
- `BRIDGE.md` §3.3 records that **the query subset is not expressible from
  today's receipts** — no seed, no size, no selection, because no command has
  ever taken one. Report whether that blocks this piece or is additive to it.
  **Do not invent the receipt here.**
- Existing single-run callers keep working unchanged.
  `report/__init__.py:1222` and `proposals/propose.py:607` are the only two
  call sites of `raise_on_violation`, and neither should need to know this
  happened.

### 4. The comparability verdict — **cite and extend, do not rebuild**

041 shipped `oneground/comparability.py`. It answers *may these two **runs** be
placed side by side*, from their `_info.json` receipts, and it is the one
implementation.

What this task adds:

- **Row-level, not only run-level.** `facts_of(workdir)` reads a run. A table
  places **rows** beside each other, and the rows in one report may come from
  different runs. Extend the verdict to take the two provenance lists of step
  3 rather than only a workdir's facts.
- **The `machine` ingredient becomes decidable** once step 1 lands — its
  current reason string describes the defect step 1 removes, and it should be
  rewritten to describe what the digest does and does not assert.
- **`BRIDGE.md` §4's table rule cites this verdict** rather than deriving a
  second answer, which is the rule §4 already states.
- `calibrate/history.py:comparable()` stays where it is and keeps its name; it
  answers a different question (engine identity). Say in the report whether
  the two should share a name. **Do not rename either.**

### 5. The machine-local path in a receipt — one implementation, at write time

`report.json` records `price_table.path` as the absolute path of the checkout
that produced it. 041's finding 3 states the general rule:

> **A receipt field holding a machine-local path cannot be published by
> running the command that produces it.**

It has now forced a sanitization at **three separate boundaries in one task**,
each borrowing one function whose own note names a different caller:

1. `corpora/export_teaser_data.public_price_table` — the original. Its
   `path_note` says "rewritten by the teaser export", which is false for every
   other caller.
2. The fixture rebuild — reused it and replaced only that note.
3. `oneground/lab/test_evidence.py`'s tracked `041-pre-fix-report.json` —
   sanitised by hand so a tracked test fixture would not fail the identifier
   scan.

**The ruling: one implementation, applied where the field is WRITTEN rather
than where it is published.** Sanitising at publish time is what produced
three boundaries, and it will produce a fourth, because every new consumer of
the receipt is a new place to remember. A receipt that never contains the
absolute path has nothing to sanitise anywhere.

- Move the transform out of the teaser exporter into one place the receipt
  writer uses. Repo-relative inside the repository, basename outside — the
  existing behaviour is right; only its home and its note are wrong.
- The note must name the transform, not a caller.
- 043 is opening receipt-writing anyway, which is why this is settled here
  rather than in a task of its own.
- **Say what this does to reproducibility.** 041 recorded that two checkouts
  of the same commit produce different `report.json` bytes from their
  locations alone. Writing the field relative removes that; say so, and say
  whether the field then belongs in the "must be byte-identical" list rather
  than the "may differ" one.

### 6. Point the positions at what now exists

- `docs/BRIDGE.md` §4 — whether the table rule can now be enforced by the
  invariant, or still needs the structural refusal, and why.
- `docs/LIBRARY.md` §2.2 — the verdict is implemented; name where, and that
  043 extended it to rows.
- `docs/MODELS.md`, the both-scales rule — its **Status: written, not
  executable** paragraph. If the rule is now executable for claims, say so,
  and say it is still only *written* for hand-authored documents, which is
  where task 039's own violations were.

### 7. The live beneficiary

Make the proposal card's `delta` a derived cite. It is the smallest real use
of step 2 and worth doing on its own merits: it is the one artifact in the
project that states a difference and judges against a difference threshold.

Report, do not fix unasked: whether `by_at_least` being a difference — scale-
blind in exactly the way task 039's prediction was — should become a declared
choice.

## What this may not do

- **Ship a presence-check.** A check that confirms a second number is there
  without checking either number is right is the defect `claims.py` was
  written to refuse. If a piece can only be built that way, that is a finding
  and the piece is not built.
- **Rebuild, reimplement or rename `oneground/comparability.py`.** 041 built
  it; this task cites and extends it.
- **Rename or repurpose `calibrate/history.py:comparable()`.**
- **Publish, transmit or print the machine identifier or the salt**, or write
  either into any artifact, including a log.
- **Invent the query-subset receipt.** `BRIDGE.md` §3.3 names what would have
  to be added and in what shape. Adding it is a different task.
- **Sanitise a machine-local path at publish time.** That is the shape being
  replaced, and adding a fourth boundary while removing three is not progress.
- **Change `docs/` beyond the paragraphs named in step 6** and the field
  definitions steps 1 and 5 require.

## Acceptance

- The machine digest lands **first**, is salted per installation, is truncated,
  never leaves the machine, and the identifier scan and
  `test_no_tracked_file_carries_a_machine_identifier` both pass on a tree
  containing a real receipt.
- What the digest can and cannot assert is written where the field is defined.
- The four 039b mutants: one passes, three fail, each naming the recomputation.
- A derived cite is checked to the artifacts through its operands, with a test
  that breaks an operand and shows the derived value failing with it.
- `RowIndex` holds rows from two runs, each carrying **both** provenance
  lists, with a test for each of the two cases that a single collapsed field
  could not tell apart.
- `comparability.verdict` decides row pairs as well as run pairs, and the
  `machine` ingredient's reason describes the digest rather than the class.
- `price_table.path` is repo-relative **as written**, all three existing
  sanitization boundaries are removed rather than left beside the new one, and
  the note names the transform rather than a caller.
- The proposal card's `delta` is a derived cite and the card's output is
  unchanged in every existing test.
- Full suite green.

## Do not

- Build a check that cannot fail. Every new rule gets a mutant that breaks it,
  on task 042's finding: **a check that passed for the wrong reason is worse
  than one that fails.**
- Let the machine digest assert more than it can. "Not the same installation"
  is what it supports.
