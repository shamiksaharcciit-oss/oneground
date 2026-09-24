# Report: 050-guard-package-resolution

## Repo state expected vs found

Expected `main` at `0d6cd8b` (task 049's merge) with
`oneground/lab/test_server.py:287`'s package-resolution bug exactly as
task 049's report described it, untouched. Found exactly that.

## What was done

**The fix.** `_import_package_for(name, path)`
(`oneground/lab/test_server.py`) replaces the inline
`name.rpartition(".")[0] or name` at the one call site
(`test_everything_the_server_imports_passes_the_guard`). An `__init__.py`'s
`__package__` is its own full dotted name — `oneground.intake`, not
`oneground` — because the file *is* its package; `rpartition` strips one
component too many for exactly this shape and is unchanged (still correct)
for every ordinary module.

**The mutant.** `test_the_package_used_for_relative_imports_is_right_for_
init_py` proves the fix against the guard the old line fed, not against a
restatement of it: `oneground.intake`'s real case from task 049
(`from .. import analogy`) resolves clean under `_import_package_for`'s
answer and is wrongly flagged under the old line's answer, reproduced
inline so the test does not depend on `intake/__init__.py` still
containing a relative import to exercise it (it does not — task 049 routed
around the bug with an absolute import once it was found, which is why
this mutant reconstructs the case rather than pointing at live source).

**What I could not build, and did not fake.** Asked for: a mutant where
the *old* code silently passes a forbidden import that the fixed code
catches. I searched for one — brute-forced across package depths 1–5,
import levels 1–6, and each of `MEASURING`'s sample names, comparing
`guard.transport_violations` under the correct package against the old
line's package for every combination — and found none. The reason is
structural: `name.rpartition(".")[0]` is always exactly **one path
component shorter** than the correct `__package__`, and every name in
`guard.MEASURING` is exactly two components (`oneground.X`). Reaching a
two-component forbidden name from a relative import's dots requires
stripping the correct package down to exactly `oneground` before
appending the tail; the old (one-component-shorter) package always needs
to strip *one component past what it has*, which `importlib.util.
resolve_name` refuses with `ImportError` — and `transport_violations`
treats that `ImportError` as a violation too (the generic `"import"` rule,
row 138–140 in `guard.py`), so it is still caught, only mislabeled. The
bug's only realized failure mode in this tree is the one it actually
produced: a **false positive**, refusing a legitimate import task 049 hit
directly. I am reporting this rather than constructing a mutant against a
claim my own testing does not support.

## Measurements

None beyond the brute-force search above, which is a coverage claim
(package depths 1–5, levels 1–6, four `MEASURING` sample names, both
import forms) rather than a proof for every conceivable case — named as
such, not overstated.

## Verification

`oneground/lab/test_server.py -q`: full file green (202 tests across
`oneground/lab/` overall, 37 skipped — unaffected files unchanged).

Full suite, guard, identifier scan and `site/teaser/` — see the merge
verification below; this report is written before the merge, per the
established pattern.

## Observed, not done — the class, and the search

**The class.** This was a coverage claim inside the guard that checks
coverage claims: `guard.transport_violations` is meant to hold every
module the server transitively imports to the same rules, and the one
call site computing which package a module's relative imports resolve
against had never been exercised on an `__init__.py`, because nothing in
the server's import graph had used a relative import from inside one —
until task 049 gave it a first, real case. A check that has never seen
the input shape its own logic handles specially is not evidence about
that shape, which is `docs/PRACTICE.md` §4's own subject applied to the
guard itself rather than to what the guard checks.

**The search for a second instance.** `guard.py` has one other
`resolve_name`-with-`node.level` site (`violations()`, for view modules),
but its only two callers (`oneground/lab/test_lab.py`) always pass the
fixed constant `VIEWS_PACKAGE`, never a per-module computed package — so
it is never subject to the same defect; there is nothing dynamic there to
get wrong. A repo-wide grep for the exact pattern
(`rpartition(".")[0]`) finds exactly the one site this task fixed. No
second instance found. Stopped here, per instruction — not widened into
an audit of every place a package name is inferred from a module name.

## Repo now contains

Changed:

- `oneground/lab/test_server.py` — `_import_package_for()` added; the one
  call site in `test_everything_the_server_imports_passes_the_guard` uses
  it; one new test, `test_the_package_used_for_relative_imports_is_right_
  for_init_py`
- `tasks/050-guard-package-resolution.report.md` — this file

## Blocked on developer

Nothing. Committed, pushed to `task-050`, and merged into `main` once its
checks were green, per standing instruction — see the commit and merge
head reported alongside this file.
