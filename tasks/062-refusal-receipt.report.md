# Report: 062-refusal-receipt

## Repo state expected vs found

Expected `main` at `7526753` (task 061's merge) with `docs/TRIAGE.md`'s
three defaults freshly ruled and no refusal receipt anywhere in
`oneground/proposals/`. Found exactly that; branch `task-062` created
from `main` at that commit, carrying the still-uncommitted ruling update
to `docs/TRIAGE.md` §3 along with it.

## What was done

**`docs/TRIAGE.md` §3 updated to record the ruling**, dated 25 September
2026: each of the three defaults is now stated as **Ruled**, with the
developer's own reason quoted at the point of the ruling rather than this
paper's reasoning substituted for it, and the rejected alternative kept
below each as a record of what it would have cost. §7's "not before the
three defaults are ruled" is removed — they are.

**`oneground/proposals/refusal.py`** — §7's first item, and only that
item. `write_refusal_receipt(workdir, policy_path, problems, log_fn)`
writes one JSON receipt, called from exactly one place:
`oneground/proposals/propose.py::plan_proposal`'s `except PolicyError`
block, the point `validate_policy`'s refusal actually happens. No
grouping, no counting, no output shape — one call writes one file.

**Every `PolicyError` gets a receipt, not only the family/parameter
ones** — a deliberate, stated choice, not scope creep. `docs/TRIAGE.md`
§3.1 scopes future *triage* to `validate_policy`'s family/parameter
refusals; it does not say other policy refusals (a malformed
configuration, a no-op change) should go unrecorded. Rather than have
this module re-decide, by parsing prose, which refusal is "the kind
triage cares about," every refusal gets a receipt, and a separate field
— `named_as_missing` — answers §3.1's question structurally, so a later
reader (or the reading pass §7 defers) filters on that field rather than
this module guessing on its behalf.

**`named_as_missing` reads the parsed policy against the real registry
and parameter tables — never `validate_policy`'s prose.** Confirmed
directly why this matters, not assumed: regex-matching an error string
is exactly the fragile shape `docs/PRACTICE.md`'s own practice warns
against ("a check must run the rule, not search for it"). This function
re-derives the same fact `validate_policy` already computed, from the
same source (`oneground.models.REGISTRY`, `parameter_table`), independent
of how any message happens to be worded. It returns a typed list —
`{"kind": "family"|"parameter"|"scope", ...}` — never a string to be
re-parsed again downstream.

**`authored_by` is read, not asserted**, from `docs/PROPOSALS.md`
§2.1's own disclosure convention: a policy `translate` produced sits
beside its own `translation_card.json`. Its presence means `authored_by:
model`, and the card's own `sentence` is carried onto the receipt too;
its absence means a hand-written policy, `authored_by: user`. Tested
both ways.

**Both provenance lists come from `oneground.comparability.facts_of`/
`provenance_of` — task 041/043's own mechanism, reused rather than
reimplemented.** Confirmed it works at refusal time, before `verify`/
`report` exist: `facts_of` already falls back across every `*_info.json`
file, including `simulate_info.json` and `build_info.json`, both of
which `propose`'s own preconditions guarantee are present.

**`--dry-run` writes no receipt.** Found while wiring the hook in, not
assumed safe: `plan_proposal` is called unconditionally before `run()`
ever checks `dry_run`, so the first version of this hook would have
written a receipt on every dry run — a direct violation of `docs/
PROPOSALS.md` §2.1's own stated contract for the flag, *"validate
everything, print what would run, write nothing."* `plan_proposal` now
takes `dry_run` explicitly and skips the receipt under it; the mutant
proving this (`test_dry_run_writes_no_receipt`) asserts the whole
`refusals/` directory does not exist, not merely that it is empty.

**A receipt that fails to write cannot turn a refusal into a crash.**
The write is wrapped and any exception is logged, never raised — the
`ProposeError` the caller is waiting for is still the whole of what a
refused `propose` invocation reports. Proven with a real mutant
(`monkeypatch` forcing the write to raise), not asserted from reading
the code.

## The question asked: does path 2's `translate` reach the same receipt?

**No — by two independent, structural reasons, not a gap in wiring.**

1. **`translate` never calls `validate_policy` at all.** Confirmed
   directly in `oneground/proposals/translate.py` (task 059): it writes
   whatever policy the model produced, valid or not, exactly as
   produced — task 059's own report states this explicitly, and the
   reason is that `validate_policy` is `propose`'s job, run once, not
   duplicated. A model producing a policy naming an invalid family does
   not refuse at `translate` time; `translate` succeeds, writes
   `policy.yaml`, and stops, per its own two-phase design.
2. **`translate` has no CLI command calling it.** Task 059 built it as a
   library function only — confirmed, no `oneground propose translate`
   subcommand exists in `cli.py`. Nothing currently invokes `translate`
   outside its own tests, so there is no live path from a model's
   sentence to this receipt at all today.

**What actually happens, precisely, per `docs/TRIAGE.md` §0's own
sentence:** a model-produced policy naming an invalid family reaches
this receipt only **later**, and only **if** a human takes the
`policy.yaml` `translate` wrote and runs `oneground propose <workdir>
--policy policy.yaml --prediction <file>` against it themselves — the
same `plan_proposal` path a hand-written policy takes, hitting the same
`validate_policy` refusal, at that later moment. Until then, an invalid
model-produced policy sits on disk, unrefused, unattempted, unrecorded.
This report's own test (`test_a_policy_beside_a_translation_card_is_
authored_by_model`) exercises exactly this: a policy written beside a
`translation_card.json`, refused by `propose` directly (standing in for
that later, human-initiated run), correctly reads `authored_by: model`
and the original sentence off the card.

## Two real regressions, caught by the full suite, not assumed clean

**A receipt field holding a machine-local path.** The full suite (not
this task's own new tests, which never touch this guard) caught
`oneground/receipts/test_pathguard.py::test_no_receipt_write_site_
records_a_machine_local_path` failing against this module: the first
version wrote `"policy_path": os.path.abspath(policy_path)` — this
machine's real temp/workdir path, into a receipt, exactly the defect
task 043 built this guard to catch project-wide. Fixed with `oneground.
receipts.public_path` — repo-relative inside the checkout, a basename
outside it — applied to both `policy_path` and `translation_card`, with
the same `path_note` `public_paths_in` already uses elsewhere, so a
reader of this receipt sees the same disclosure any other sanitised path
in this codebase carries. `oneground/proposals/test_refusal.py`'s own
`authored_by: model` test compared against the wrong (raw) path once
this landed and was fixed in the same pass — a real bug in the test, not
only in the module it was testing.

**The receipt-writer site count.** `oneground/test_invocation.py`'s
hardcoded count, task 051/055/059's own recurring precedent, updated
15 → 16 for this module's own correctly-paired `oneground`/`invocation`
fields.

## Measurements

6 of 6 new tests pass (`oneground/proposals/test_refusal.py`), all
against the real `propose.run`/`validate_policy` path on a real
characterized-and-simulated synthetic workdir, not a hand-constructed
receipt. `oneground/proposals/` full suite: 88 of 88 pass (82 pre-
existing + 6 new), confirming the `plan_proposal` signature change
(`log_fn`, `dry_run` added, both defaulted) broke nothing already there.

A real receipt, inspected directly: carries the full `characterization.
json` (including its distribution arrays — the brief's own words, "the
corpus characterization it refused against"), both provenance lists
(`measured`: sample/ground_truth/query_subset; `measuring`: code/
libraries/settings/platform/python_version/machine), `oneground`/
`invocation` (the same pairing every other declared receipt in this
codebase carries — `oneground/test_invocation.py`'s own site-count test
passed unchanged, confirming this file is counted correctly).

## Verification

`oneground/proposals/test_refusal.py`: 6 passed, including three real
mutants (a receipt-writing failure not crashing the refusal; `--dry-run`
writing nothing, checked by directory absence; the structural family/
parameter/scope extraction proven against three distinct real refusal
shapes). `oneground/proposals/` full suite: 88 passed. Full suite, guard,
identifier scan and `site/teaser/`: reported at the merge, per the
established pattern.

## Observed, not done

**No grouping, counting, or output shape** — exactly as instructed.
Reading the record — filtering by `named_as_missing`, counting per
family/parameter, the §5 "count, don't rank" output — is explicitly
deferred, per the instruction that the reading comes after there is
something to read.

**No `oneground propose translate` CLI command was added.** Not asked
for here, and adding it would be the thing that finally gives path 2's
own refusals a live path to reach this receipt at all (per the finding
above) — a separate, later decision.

**The receipt's `problems` list is the raw `PolicyError.problems`
strings**, unparsed beyond what `named_as_missing` extracts separately.
A reader wanting the exact wording a terminal showed has it verbatim; a
reader wanting the structural fact has `named_as_missing` instead of
having to parse it back out.

## Repo now contains

Changed:

- `docs/TRIAGE.md` — §3's three defaults recorded as rulings, dated,
  with the developer's own reasons; §7 updated to reflect they are ruled
- `oneground/proposals/propose.py` — `plan_proposal` gains `log_fn` and
  `dry_run` parameters; the refusal-receipt hook in its `except
  PolicyError` block
- `oneground/test_invocation.py` — site count 15 → 16

New:

- `oneground/proposals/refusal.py` — the receipt writer
- `oneground/proposals/test_refusal.py` — 6 tests
- `tasks/062-refusal-receipt.report.md` — this file

## Blocked on developer

Nothing. Committing, pushing to `task-062`, and merging into `main` once
its checks are green, per standing instruction.
