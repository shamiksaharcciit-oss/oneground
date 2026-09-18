# Task (post-v0.1) — Script mode collects the whole file, everywhere

Recorded during 022g at the developer's instruction, unnumbered: the developer
assigns the number when this is scheduled. **v0.1.1, not v0.1.** CI and the
release checks run `pytest`, which collects every test, so nothing in the
release is affected; `RELEASE_NOTES.md` says so under *Known limits*.

## Expected repo state
`main` at or after `022g`, tree clean. Work on `main`; commit `task NNN:`; do
not push, publish, or move a tag.

## Why
`_main`'s collection reads `globals()`, so a test defined below a module's
`if __name__ == "__main__"` block does not exist as far as the script runner is
concerned. Running such a file directly prints `N passed (of N collected)` over
a fraction of it, with nothing saying what was missed — a green over what it
never looked at, which is the defect 022e and 022f each removed once.

022f fixed `oneground/test_environment.py` and guarded it with
`test_script_mode_collects_every_test_pytest_does`, which compares
`python <file> --list` against `pytest --collect-only` for that one file. Seven
modules still have it.

## What is wrong, measured (022f, 2026-09-18)
Module-level `test_*` functions defined after the `__main__` block, by parsing
each file:

| module | tests | invisible to script mode |
|---|---|---|
| `oneground/fixture/test_verify.py` | 74 | 57 |
| `oneground/verify/test_verify.py` | 47 | 32 |
| `oneground/report/test_verdict.py` | 61 | 23 |
| `oneground/pod/test_pod.py` | 183 | 21 |
| `oneground/verify/test_matched.py` | 73 | 8 |
| `oneground/intake/test_tier2.py` | 21 | 7 |
| `oneground/report/test_end_to_end.py` | 13 | 4 |

Confirmed by running one: `python oneground/intake/test_tier2.py` prints
`14 passed, 0 failed (of 14 collected)`, the 14 the parse predicts, of 21. The
other twelve test modules have nothing after the block.

## What to do
1. Move each module's runner section (`_main` and its `__main__` block, plus
   whatever collection helper it uses) below every test in that file, as 022f
   did, changing nothing else. Re-run each module both ways and report the two
   counts before and after.
2. **Generalise the guard so the fix and the guard land together.** Replace
   022f's single-file test with one that walks every `test_*.py` module in the
   package that has a `__main__` block, and for each compares what script mode
   collects against what `pytest --collect-only` collects. A module with no
   `__main__` block is out of scope, not a failure. It must fail on a file that
   regrows the defect — demonstrate that, as 022f did, with a probe copy rather
   than by argument. Every module gets `--list`, or the walk finds another way
   to ask a module what it collected; decide and say why.
3. **Decide what script mode claims.** `oneground/test_environment.py` imports
   `pytest` at module scope (022, for the skips), so running it without pytest
   installed fails at import — the one situation the script mode exists for.
   Either drop that claim from the docstrings that make it, or make it true
   (a `pytest`-free skip shim). Whichever way, the docstrings and the claim
   must agree at the end of the task. Check the other modules for the same
   import before deciding: the answer may differ per file, and one answer for
   all of them is preferable if it is honest.
4. Remove the *Known limits* bullet from `RELEASE_NOTES.md` in the same commit
   that makes it false, not before.

## Out of scope
Anything about what the tests assert. This is about which of them run.
