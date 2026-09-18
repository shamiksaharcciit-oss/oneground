# Report: 022f-script-mode-collects-the-whole-file

## Repo state expected vs found

Expected `main` at `df84e2d` (022e), clean apart from the untracked
`tasks/020-simulator-state.md`: found, both. `v0.1.0` still on `872e7a6`.

Expected `_main` and its `if __name__ == "__main__"` block in the middle of
`oneground/test_environment.py`, above the task-014, 017 and 022b sections, and
script mode reporting a green over the tests defined before it: found.
Measured on the file as found: `21 passed, 0 failed, 0 skipped (of 21
collected)` against 43 under pytest.

## What was done

`oneground/test_environment.py`, the move:

- The runner section — now `_collect`, `_main` and the `__main__` block — is at
  the end of the file, after every test. `_main` was chosen over refusing to
  run: the module docstring has advertised
  `python oneground/test_environment.py` since 013, and the point of the
  script mode is a check that runs without pytest installed.
- **`_collect`** (new) is the collection `_main` used to do inline, named so
  the test below can talk about it, with the reason it must stay at the bottom
  in its docstring. A comment above the `__main__` block says nothing may be
  defined under it.
- **`_main(argv=())`** takes `--list`: collect, print one test name per line,
  run nothing, exit 0. It exists so the test can ask script mode what it sees
  without executing 44 tests inside a test — and, because it runs nothing, it
  cannot recurse into itself.
- The module docstring records the third invocation and names the test that
  holds the two runners together.

The test, **`test_script_mode_collects_every_test_pytest_does`**: runs this
file two ways in subprocesses — `python <file> --list`, whose collection
happens under `__main__` exactly as a full script run's does, and
`python -m pytest --collect-only -q <file>` — and asserts the two name sets are
equal, naming the symmetric difference when they are not. A floor of >40 as
well, so the test cannot pass by both runners collecting nothing.

Nothing else was touched: no gate, threshold, tolerance, seed or fixture value,
and no new dependency.

## Measurements

All runs on this machine, `.venv\Scripts\python.exe` (Python 3.12; numpy
2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0: pinned).

**The defect, and the fix, on this file:**

| | script mode | pytest | missed by script mode |
|---|---|---|---|
| on `df84e2d` (as found) | 21 | 43 | 22 |
| after this change | 44 | 44 | 0 |

Script mode's own line now reads `44 passed, 0 failed, 0 skipped (of 44
collected)`; `python -m pytest oneground/test_environment.py -q` reads
`44 passed in 17.4 s`. 44 is 43 plus the one test added here.

**The negative control**, `tasks/scratch/022f-half-collection.py`: copies this
file into the package as a probe with the runner section moved back to where it
was, collects it both ways, and runs the new test against the probe. The probe
is deleted again in a `finally`. As printed:

```
  as it is now: script mode 44, pytest 44, missed by script mode 0
    old layout: script mode 22, pytest 44, missed by script mode 22

the test itself, against the old layout: exit 1
    E  AssertionError: script mode and pytest disagree about what this file
       contains; only one of them saw: test_a_checkout_whose_git_cannot_run...
    1 failed in 0.67s
```

So the test fails on the layout this task removed, and the failure names the
tests that went missing.

**Suite**: `python -m pytest -q` from the repo root → **875 passed, 1 skipped**
in 287 s (4 m 47 s). The skip is `oneground/pod/test_pod.py:2089`,
`RUNPOD_API_KEY not set; live test skipped`, unrelated. 876 collected against
875 on `df84e2d`: the one new test, none removed.

**Identifier scan**: `env.identifier_findings()` → **0 findings** over the 325
paths `env.tracked_files()` returned.

## Verification

- Passed: script mode and pytest collect the same 44 tests, asserted by a test
  that runs both.
- Passed: the new test fails on the old layout — measured, above, not argued.
- Passed: the full suite, 875, with no test removed and none changed but the
  file's runner.
- Passed: `python oneground/test_environment.py` still works as the docstring
  says, now over the whole file, and `--list` exits 0 printing 44 names.
- Couldn't check: nothing here was run without pytest installed, which is the
  case script mode exists for. This file imports pytest at module scope (022:
  the skips need it), so script mode does not in fact survive a missing pytest
  today — see below.

## Observed, not done

1. **Seven other test modules have the same defect, and two of them badly.**
   Measured by parsing each file: the number of module-level `test_*` functions
   defined after the `if __name__ == "__main__"` block, which is the number
   script mode cannot see.

   | module | tests | invisible to script mode |
   |---|---|---|
   | `oneground/fixture/test_verify.py` | 74 | **57** |
   | `oneground/verify/test_verify.py` | 47 | **32** |
   | `oneground/report/test_verdict.py` | 61 | 23 |
   | `oneground/pod/test_pod.py` | 183 | 21 |
   | `oneground/verify/test_matched.py` | 73 | 8 |
   | `oneground/intake/test_tier2.py` | 21 | 7 |
   | `oneground/report/test_end_to_end.py` | 13 | 4 |

   Confirmed on one of them by running it: `python oneground/intake/test_tier2.py`
   prints `14 passed, 0 failed (of 14 collected)` — the 14 the parse predicts,
   of 21. The other twelve test modules have nothing after the block. The brief
   named `test_environment.py`, so none of these was edited, and the new test
   guards only its own file. A follow-up that moved each block and lifted the
   collection test into a shared check would cover all twenty.

2. **Script mode does not survive a missing pytest.** `import pytest` is at
   module scope (022, for the skips), so on a machine without it the script
   run fails at import — the situation the script mode is for. Unchanged by
   this task and not in the brief.

3. `tasks/scratch/` is `.gitignore` line 62, so
   `tasks/scratch/022f-half-collection.py` stays local.

## Repo now contains

    oneground/test_environment.py                             runner section moved to the end, _collect, --list, the collection test
    tasks/022f-script-mode-collects-the-whole-file.report.md  this report
    tasks/scratch/022f-half-collection.py                     the negative control (untracked, .gitignore:62)

## Blocked on developer

Retag `v0.1.0` at this commit.
