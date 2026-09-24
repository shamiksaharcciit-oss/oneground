# Report: 047-refusal-contract-repair

No brief file precedes this one. The instruction was given directly, after
task 046 merged (`a9d1a21`) and was ruled on in
`tasks/046-contract-changes.report.md`: take items 4, 5 and 6 as one piece
of work rather than three patches, because they are three places the code
disobeys a table that was already ratified — `oneground/refusals.py`'s
table for who owns a refusal, and `jobs.py`'s exit-code contract for how
one travels.

## Repo state expected vs found

Expected `main` at `a9d1a21` with the three violations exactly as
`tasks/046-contract-changes.report.md` describes them. Found that, and
nothing else had touched `intake/__init__.py`, `jobs.py`, `cli.py`, or
`pod/cli.py` since.

## What was done

**4. `intake.load` accepts a directory.** `os.path.isdir(path)` checked
before the existing `os.path.exists` check, raising `RequirementsError` with
the message `tasks/finding-a-path-check-that-accepts-a-directory.md`
proposed verbatim. `os.path.exists` stayed for the genuinely-missing case;
`isdir` rather than `not isfile`, for the same reason the finding gave — a
path that exists and is neither a directory nor an ordinary file is rare
enough that guessing at its message would invent a case nobody meets, and
letting `open()` fail on it is honest.

**5. `simulate` reported a finding through its exit code.**
`_cmd_simulate` (`oneground/cli.py`) now returns 0 whether or not
configurations were dropped. The stdout message stays — it still names how
many of how many, and points at `simulate.json` and
`simulate_info.json:dropped` — but no longer claims to be an "exit 1".

**6. `pod plan` returned 1 for a refusal.** `cmd_plan`
(`oneground/pod/cli.py`) has **two** places that print `REFUSED:` — the
cost-cap check the report names, and `_mirror_refusal`, one call earlier in
the same function, which the report's prose does not name but which is the
same defect at a second site. Both now `return refusals.REFUSED_EXIT` (2).
Fixing only the named one would have left the other failing
`test_exit_contract.py`'s generic scan, which does not distinguish which
`return` in a function it is reading — the two sites are the same rule,
found by the same test, and it would have been dishonest to patch one and
call the pair done.

**The table, closed rather than left declared.** `jobs.EXIT_CONTRACT` held
two permitted exceptions, one per repaired stage, each existing only because
the rule said it should not. Both are now gone: `EXIT_CONTRACT = {}`.
`EXIT_MEANING[1]` collapsed from two meanings (undecided, resolved by
reading the workdir) to one (`FAILED`, "did not finish"). `jobs.classify`
dropped its now-unread `workdir` parameter rather than keep it for a case
that no longer exists — `oneground/supervisor.py`'s one call site updated
to match. `STAGE_RECEIPT`, which existed only to resolve the row `classify`
no longer needs to resolve, is deleted.

**One test for item 4** (`test_a_directory_is_a_refusal_not_a_permission_error`
in `test_refusals.py`), in the same style and the same file as the missing-
file case it sits beside, driving the real CLI as a subprocess the way the
defect was found. **No new test for items 5 and 6** — the mechanism that
would have caught both already exists:
`test_exit_contract.py::test_a_stage_returns_zero_or_a_declared_non_zero`
walks every stage handler's literal `return` statements by AST and refuses
any non-zero, non-`REFUSED_EXIT` value that is not declared in
`EXIT_CONTRACT`. Closing the table to `{}` is what makes that test the
enforcement for both repairs: it would have failed the moment either fix
was incomplete, which is what happened once, mid-work, on the unnamed
`_mirror_refusal` site in `cmd_plan` — see Verification.

**`docs/PRACTICE.md` §7.5, corrected — named for this task rather than
found and left.** Its worked example was `jobs.classify(stage, exit_code,
workdir)` deciding exit 1 by reading the workdir, reproducing the eleventh
test (`test_the_workdir_actually_decides_it`) that this same task deletes —
the section would have described a function signature the tree no longer
has, which is §1's own defect (*a section that states a current state goes
stale silently*) landing on a code example instead of prose. The
methodology the section teaches is untouched; the paragraph now says, in
the past tense, that the instance held through task 046 and was resolved by
this one, rather than presenting a deleted test as a live example a reader
could run.

## Measurements

None beyond the suite counts below. This task changed control flow and
exit codes, not anything the project measures a value for.

## Verification

Full suite: **1777 passed, 41 skipped**, `.venv\Scripts\python.exe -m pytest -q`,
307s. (1779 before this task's changes; net −2 from consolidating fourteen
now-obsolete exit-1-disambiguation tests in `test_refusals.py` into three.)

The pinned-environment guard: 54/54 in `test_environment.py`.

The tracked-tree identifier scan: 570 tracked paths, 0 findings, confirmed
running rather than skipped (`test_no_tracked_file_carries_a_machine_identifier`
and `test_the_scan_actually_reads_the_tree` both pass).

**The AST scan caught an incomplete fix, once, before this was committed.**
Fixing only `cmd_plan`'s cost-cap `return 1` and leaving `_mirror_refusal`'s
untouched failed
`test_exit_contract.py::test_a_stage_returns_zero_or_a_declared_non_zero`
immediately — `oneground/pod/cli.py:88: pod plan returns 1, which is not 0
and not declared in jobs.EXIT_CONTRACT`. That is the "one test" doing its
job rather than a coincidence: it is exactly the case `EXIT_CONTRACT`'s
now-empty state exists to make loud.

**This is the argument for the generic check over three named patches, not
just a convenient side effect.** A patch aimed at "item 6" would have read
the report's own prose, seen one named `return 1` (the cost cap), fixed
that one, and stopped — the prose named one site, so a patch scoped to the
prose stops at one site. The scanner has no prose to read; it walks every
literal `return` in the function by AST and asks the same question of each,
so it does not know there is a "named" site and an "other" site, only
`return`s that are 0, `REFUSED_EXIT`, or undeclared. That is what caught
the second one before commit, and it is also what makes three ad hoc tests
strictly worse than this one general one: three patches each answer for
the case they were written against, and a fourth site added to `cmd_plan`
next year is invisible to all three until someone remembers to write a
fourth. The generic scan answers for a site it has never seen, which is
the property "one test, not three patches" was asking for.

Stale assertions found and repaired, each a test whose premise was this
task's contract change:

- `oneground/simulate/test_simulate.py`:
  `test_the_run_exits_non_zero_when_a_configuration_was_not_measured`
  asserted `code == 1` for a dropped configuration — the exact claim item 5
  reverses. Renamed
  `test_a_dropped_configuration_is_named_on_stdout_and_exits_zero`;
  the stdout assertions (the drop is still named, still silent when nothing
  is dropped) kept, only the exit code changed.
- `oneground/pod/test_pod.py`: `test_plan_exit_code_is_1_when_over_cap`
  asserted the old wrong code by name. Renamed
  `test_plan_exit_code_is_2_when_over_cap`, asserting
  `refusals.REFUSED_EXIT`; `refusals` added to the file's imports.
- `oneground/test_refusals.py`: five tests existed only to prove `classify`
  read the workdir to resolve exit 1 — `test_exit_one_with_the_receipt_is_done`
  (parametrized over 5 stages), `test_exit_one_without_the_receipt_is_failed`
  (5 stages), `test_exit_one_is_the_only_code_the_workdir_decides`,
  `test_the_workdir_actually_decides_it` (the row's dedicated mutant), and
  `test_a_stage_with_no_receipt_of_its_own_says_so_rather_than_guessing`.
  All asserted a distinction that no longer exists. Replaced with
  `test_exit_one_is_failed_for_every_stage`, parametrized over all ten
  `jobs.STAGES`, and `test_the_exit_contract_now_has_no_exceptions`.
  `test_every_stage_has_a_receipt_entry` deleted with `STAGE_RECEIPT`.
  `json` import dropped, now unused.
- `oneground/test_supervisor.py`:
  `test_exit_one_with_the_receipt_is_recorded_as_done_with_the_reason` wrote
  a `simulate.json` and asserted `state == "done"` for exit 1 — the same
  premise, through the supervisor. Replaced with
  `test_exit_one_is_failed_whatever_the_workdir_holds`, same setup,
  opposite (now correct) assertion.
- `oneground/test_exit_contract.py`:
  `test_the_declared_exceptions_are_the_ones_that_cost_the_classifier`,
  pinned to the two exceptions existing, replaced with
  `test_the_declared_exceptions_are_gone_and_the_row_collapsed`, pinned to
  their absence.

`site/teaser/` and every fixture were untouched; not re-checked beyond the
identifier scan, which reads them anyway.

## Observed, not done

**`pod/cli.py`'s `cmd_up` keeps its old exit code for the same
`_mirror_refusal` check that `cmd_plan` no longer does** (`return 1`, not
`REFUSED_EXIT`). Deliberately left: `up` is `jobs.NOT_A_JOB` — the one
operation a human runs directly rather than through the supervisor's
`classify` — so it sits outside the ratified table's reach, and touching it
was not asked for. Worth knowing before anyone reads `pod/cli.py` end to
end and notices the same words exit differently depending on which
subcommand printed them.

## Repo now contains

Changed:

- `oneground/intake/__init__.py` — `load()` refuses a directory before the
  existence check
- `oneground/cli.py` — `_cmd_simulate` returns 0 unconditionally; the stdout
  message no longer claims "exit 1"
- `oneground/pod/cli.py` — `cmd_plan`'s two refusal returns now
  `refusals.REFUSED_EXIT`; `refusals` imported; module docstring's exit-code
  table split into "job stages, `jobs.py`'s contract" vs. "the rest, this
  module's own"
- `oneground/jobs.py` — `EXIT_CONTRACT = {}`; `EXIT_MEANING[1]` is
  `(FAILED, ...)`; `STAGE_RECEIPT` deleted; `classify(stage, exit_code)`,
  `workdir` parameter dropped
- `oneground/supervisor.py` — `finish()` calls `classify` with two
  arguments; docstrings updated
- `oneground/test_refusals.py` — one test added (item 4); the six
  workdir-disambiguation tests replaced with two; unused `json` import
  dropped
- `oneground/test_exit_contract.py` — one test's assertion and name updated
  to the closed table
- `oneground/test_supervisor.py` — one test's assertion and name updated
- `oneground/simulate/test_simulate.py` — one test's assertion and name
  updated
- `oneground/pod/test_pod.py` — one test's assertion and name updated;
  `refusals` imported
- `docs/PRACTICE.md` — §7.5's worked example corrected to past tense,
  naming task 047 as what resolved it
- `tasks/047-refusal-contract-repair.report.md` — this file

## Blocked on developer

Nothing. Committed, pushed and merged into `main` on your word, the same
way task 045 was — see the commit and merge head below.
