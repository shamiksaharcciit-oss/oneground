# Report: 022g-known-limit-and-the-post-release-task

## Repo state expected vs found

`main` at `72a7e3c` (022f), clean apart from the untracked
`tasks/020-simulator-state.md`: found, both.

`v0.1.0`: **read this time, not carried over.** `git rev-parse v0.1.0` gives
the annotated tag `6b83e56`, pointing at commit `1fe8e26` (026c) — the
developer's retag after 026c. The 022e and 022f reports each said it was on
`872e7a6`, which was wrong when written: the line came from the 026c report's
text rather than from git. Both lines are corrected in this commit, each saying
what it first said. No number, measurement or conclusion in either report
depended on it.

`RELEASE_NOTES.md` with a *Known limits* section of seven bullets: found.

## What was done

1. **`RELEASE_NOTES.md`**, an eighth bullet at the end of *Known limits*:

   > **`pytest` is the supported test runner.** Running a test file directly
   > (`python oneground/fixture/test_verify.py`) collects only the tests
   > defined above that file's `__main__` block, which in several modules is a
   > fraction of them; CI and the release checks run `pytest`, which collects
   > every test.

   It names a file that still has the defect rather than
   `test_environment.py`, which 022f fixed.

2. **`tasks/post-v0.1-script-mode-collection.md`**, the post-release task,
   recorded with the seven modules and their counts, and four items: move each
   runner section; generalise
   `test_script_mode_collects_every_test_pytest_does` to walk every test module
   with a `__main__` block, so the fix and the guard land together; decide
   whether script mode's pytest-free claim is dropped or made true, given
   `import pytest` at module scope, with the docstrings and the claim agreeing
   at the end; and remove the *Known limits* bullet in the same commit that
   makes it false. It carries no task number — `post-v0.1-` instead — because
   the numbering is the developer's and 023–025 are unused. Rename it when it
   is scheduled.

No code changed. No gate, threshold, tolerance, seed or fixture value was
touched, and no dependency added.

## Measurements

- `python -m pytest oneground/test_packaging.py oneground/test_environment.py -q`
  → **62 passed** in 20.9 s. `test_packaging.py` holds `RELEASE_ASSETS` and the
  release notes to each other, so it is what an edit to that file can break.
- `tasks/scratch/018-docs-numbers.py` → **ALL CHECKS PASSED** (the numbers and
  quoted lines in the docs against the fixtures).
- Identifier scan with everything below staged: `env.identifier_findings()` →
  **0 findings**, over the 327 paths `env.tracked_files()` returned.
- Full suite not re-run: this commit changes one prose bullet, two report
  lines and adds a task brief; no code, no test. It passed at 875 on `72a7e3c`
  (022f report).

## Verification

- Passed: the bullet is in `RELEASE_NOTES.md` under *Known limits*, and says
  what it was asked to say — direct runs collect part of a file, `pytest` is
  supported and is what CI and the release checks run.
- Passed: the post-release task exists, names all seven modules with counts,
  and carries the generalisation and the `import pytest` decision as items.
- Passed: the two wrong tag lines are corrected and say they were corrected.
- Passed, by reading the workflow: `.github/workflows/calibration.yml` runs
  `python -m pytest -q` (lines 110 and 200) and `python -m pytest -q
  .github/scripts` (120, 210). No workflow runs a test file directly.
- Couldn't check: no CI run was triggered from here, so this is what the
  workflow says, not a job observed.

## Observed, not done

The seven modules themselves, deliberately: v0.1.1, per the brief.

## Repo now contains

    RELEASE_NOTES.md                                          the eighth Known limits bullet
    tasks/post-v0.1-script-mode-collection.md                 the post-release task
    tasks/022e-scan-fails-when-git-cannot-run.report.md       tag line corrected
    tasks/022f-script-mode-collects-the-whole-file.report.md  tag line corrected
    tasks/022g-known-limit-and-the-post-release-task.report.md  this report

## Blocked on developer

Retag `v0.1.0` at this commit instead of `72a7e3c`.
