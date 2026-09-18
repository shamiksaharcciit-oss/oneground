# Report: 022e-scan-fails-when-git-cannot-run

## Repo state expected vs found

Expected `main` at `1fe8e26` (026c), clean apart from the untracked
`tasks/020-simulator-state.md`: found, both. `v0.1.0` was on `1fe8e26`, where
the developer had retagged it after 026c, and was not moved by this task.
(Corrected in 022g: this line first said `872e7a6`, carried over from the 026c
report instead of read from `git rev-parse v0.1.0`.)

Expected the three tests the brief names, in `oneground/test_environment.py`,
behaving as it describes: found.

- `test_no_tracked_file_carries_a_machine_identifier` and
  `test_the_scan_actually_reads_the_tree` each skipped on
  `identifier_findings()` / `tracked_files()` returning `None`, and
  `oneground/environment.py`'s `tracked_files` returned `None` both for "no
  `.git`" and for "git could not be run", so the two were indistinguishable.
- `test_the_tracked_scan_opens_tracked_archives_synthetic` called
  `subprocess.run(["git", "init", ...], check=True)` with nothing around it.

Measured on the code as found, before any edit (method under *Measurements*):
on this checkout with an empty `PATH`, the first two **skipped green**, saying
"not a git checkout; nothing to scan" inside a checkout, and the third ended
in a bare `FileNotFoundError`.

## What was done

`oneground/environment.py`:

- **`checkout_root(start=None)`** (line 604), new: the nearest directory at or
  above `start` holding a `.git`, else `None`. It walks upward, because a
  command may run from a subdirectory, and it accepts a `.git` file as well as
  a directory, because that is what a worktree and a submodule have.
- **`GitUnavailable(RuntimeError)`** (line 594), new.
- **`tracked_files`** (line 621) now separates the two answers. `None` still
  means "not a checkout". When git cannot be launched, or exits non-zero, and
  `checkout_root` finds a `.git`, it raises `GitUnavailable` naming the command
  tried, the directory, and the error — `_raise_if_checkout`, line 656. Paths
  in that message are relativised (`_relative`, line 647) so a message people
  paste into a report does not carry a home directory.
- **`identifier_findings`** (line 668) is unchanged except in its docstring: it
  calls `tracked_files`, so it propagates.

`oneground/test_environment.py`:

- The two tree tests (lines 456, 468) now skip on `env.checkout_root() is
  None` — the question they actually meant — and let `GitUnavailable` fail
  them. Each also asserts the scan did not hand back `None` on a checkout.
- **`test_a_tree_with_no_git_is_not_a_checkout_synthetic`** (505): the skip
  branch that stays a skip.
- **`test_a_checkout_whose_git_cannot_run_is_an_error_synthetic`** (513): a
  `.git` with an empty `PATH`; both `tracked_files` and `identifier_findings`
  must raise, and the message must name `git ls-files` and the error.
- **`test_a_git_that_answers_from_a_subdirectory_is_still_a_checkout_synthetic`**
  (533): `checkout_root` walks up.
- **`test_the_tree_tests_fail_rather_than_skip_when_git_cannot_run`** (543),
  not synthetic: calls the two tree tests themselves with `PATH` emptied, and
  fails if either passes *or* skips. Asserting only about `tracked_files` would
  have left the tests free to go on skipping.
- **`test_the_tracked_scan_opens_tracked_archives_synthetic`** (722) builds its
  synthetic checkout through **`_git_or_skip`** (697): git that cannot be
  launched skips, naming the command and the error, because without git this
  test's fixture cannot be built and there is no real tree it could be
  reporting green about; git that runs and fails is an assertion failure. The
  temporary directory is shown as `<tmp>` in the skip reason — a skip reason
  gets pasted into reports, and `tempfile.gettempdir()` is under a home
  directory on this platform.
- `_main`, the script runner, now reports a skip as `skip` instead of stopping
  on it: `pytest.skip` raises a `BaseException`, which its `except Exception`
  did not catch, so the first skip would have ended the run with a traceback.

No gate, threshold, tolerance, seed or fixture value was touched. No new
dependency.

## Measurements

All runs on this machine, `.venv\Scripts\python.exe` (Python 3.12, numpy
2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0: pinned).

**The behaviour before the change**, measured rather than recalled: a detached
worktree of `1fe8e26` (`git worktree add --detach`, since removed and pruned),
with `tasks/scratch/022e-empty-path.py` copied in and run there. That script
runs each named test in a subprocess whose `PATH` is `""`, in a checkout.

| test | on `1fe8e26` | after this change |
|---|---|---|
| `test_no_tracked_file_carries_a_machine_identifier` | `SKIPPED ... not a git checkout; nothing to scan`, exit 0 | `FAILED`, exit 1 |
| `test_the_scan_actually_reads_the_tree` | `SKIPPED ... not a git checkout; nothing to scan`, exit 0 | `FAILED`, exit 1 |
| `test_the_tracked_scan_opens_tracked_archives_synthetic` | `FileNotFoundError: [WinError 2] ...`, exit 1 | `SKIPPED ... git could not be run (git init -q <tmp>): FileNotFoundError: [WinError 2] The system cannot find the file specified`, exit 0 |

The failure message both tree tests now carry, as printed:

```
E       oneground.environment.GitUnavailable: git ls-files -z in '.' failed,
        and '.' holds a .git: FileNotFoundError: [WinError 2] The system
        cannot find the file specified. A scan that reads nothing is not a
        clean scan.
```

**The other branch still skips.** `python -m pytest <abs path>::test_the_scan_actually_reads_the_tree
::test_no_tracked_file_carries_a_machine_identifier` run with the working
directory set to a fresh temporary directory (no `.git` at or above it), `PATH`
intact: `2 skipped`, both reasons `not a git checkout; nothing to scan`.

**Module**: `python -m pytest oneground/test_environment.py -q` → **43 passed**
in 29.8 s; four of the 43 are new here.

**Suite**: `python -m pytest -q` from the repo root → **874 passed, 1 skipped**
in 469 s (7 m 49 s). The skip is `oneground/pod/test_pod.py:2089`,
`RUNPOD_API_KEY not set; live test skipped`, unrelated to this task. 875
collected, against the 871 the 026c report records on `1fe8e26`: the four new
tests, no test removed.

**Identifier scan**, with everything below staged:
`env.identifier_findings()` → **0 findings**, over the 325 paths
`env.tracked_files()` returned.

## Verification

- Passed: the distinction the brief asks for, in both directions — no `.git`
  skips with that reason, `.git` present and git unrunnable fails naming
  `git ls-files -z` and the `FileNotFoundError`. Measured above, by emptying
  `PATH`, and asserted by the two new tests that do the same in-process.
- Passed: `test_the_tracked_scan_opens_tracked_archives_synthetic` no longer
  raises `FileNotFoundError`; it skips with the command and the error named.
- Passed: the full suite, 874, with no test changed other than the three named
  and no behaviour change on a machine that has git — every one of those 874
  ran with git on `PATH` and none moved.
- Couldn't check: nothing here was run on a machine that genuinely lacks git,
  or on a broken repository where git runs and exits non-zero. Both were
  simulated — an empty `PATH` for the first, and `_raise_if_checkout` takes the
  same path for either, with the exit code and stderr in place of the
  exception text. A real `git ls-files` failure inside a valid checkout was not
  produced.

## Observed, not done

1. **`oneground/verify/test_matched.py:402`, `_skip_unless_a_git_checkout`,
   has the same shape** — it skips on `environment.tracked_files() is None`.
   It now inherits the fix: on a checkout with no runnable git it raises rather
   than skipping, because the distinction lives in `tracked_files`. Its skip
   text still says "not a git checkout (no .git)", which is now exactly what
   the skip means. The brief named only `test_environment.py`, so the file was
   not edited.
2. **Script mode collects 21 of the 43 tests in the file.**
   `if __name__ == "__main__": sys.exit(_main())` sits at line 344, above the
   task-014, 017 and 022b sections, so `_main` never sees the identifier-scan
   tests at all — including the two this task is about. `python -m pytest`
   collects all 43. Moving the block to the end of the file would fix it; that
   is a change to the file's shape and the brief did not ask for it.
3. `tasks/scratch/` is `.gitignore` line 62, so
   `tasks/scratch/022e-empty-path.py` stays local, as scratch scripts here
   always have.

## Repo now contains

    oneground/environment.py                          checkout_root, GitUnavailable, the raising tracked_files
    oneground/test_environment.py                     the three tests fixed, four new, _main reports skips
    tasks/022e-scan-fails-when-git-cannot-run.report.md   this report
    tasks/scratch/022e-empty-path.py                  the empty-PATH diagnosis (untracked, .gitignore:62)

## Blocked on developer

Retag `v0.1.0` at this commit.
