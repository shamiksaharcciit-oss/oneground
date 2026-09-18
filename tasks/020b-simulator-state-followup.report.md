# Report: 020b-simulator-state-followup

## Repo state expected vs found

- **Branch and worktree:** as expected. The second worktree `oneground-v2` is on `task-020` at `bba3f37` (task 020, accepted), with a clean tree. The main checkout and `main` were not touched.
- **The 020 brief:** as expected. It is still untracked in the main checkout, with sha256 `15bddc50…a68478` and 5,283 B, unchanged since task 020.
- **The 020b brief:** it has no file. It is the developer's message, and its three items are quoted in this report.
- **Not expected: a home-path leak.** The tracked-tree identifier scan (`test_no_tracked_file_carries_a_machine_identifier`, task 017) failed on `task-020`. Task 020's own report, as committed in the pre-squash commit `bba3f37`, carries an absolute path through the developer's home directory. The 020 suite passed only because the report was still untracked when it ran. Committing the brief (item 2) added a second occurrence. Both are fixed; see What was done and Blocked on developer.

## What was done

**(1) `build_seconds` and `query_seconds` moved from `simulate.json` to `simulate_info.json`, as declared.**
- **Where the timings go now.** `measure_config` returns `(row, timing)`, so wall clock is never written into a row. `run()` declares the timings in `simulate_info.json` under `timings`, keyed by config label and rounded to the rows' 6 decimals, with a `timings_note` saying what they are. The printed table reads its build and query columns from there.
- **Tests.**
  - `test_simulate.py`'s decomposition test now asserts both fields are absent from every row and present in `simulate_info.json`.
  - The `--emit-state` test compares `simulate.json` from two runs **byte for byte**, replacing the timings-masked comparison.
  - `report/test_end_to_end.py`'s synthetic row is updated to the new format.
- **Docs.** [`docs/STATE.md`](../docs/STATE.md) gains "`simulate.json`'s format changes in v0.2": what moved, why, that no measured value moved, and what a reader must change.
- **One visible effect.** `oneground report` counts every row field as a measurement, so it no longer lists the two timings among an option's measurements. They were never measurements, and no verdict used them.

**(2) The brief is committed.** `tasks/020-simulator-state.md` was copied byte for byte from the main checkout and committed (pre-squash `850dabe`). The main checkout's copy is untouched.

**(3) The environment guard refuses a foreign package.**
- **The code** is in `oneground/environment.py`: `package_dir`, `working_tree_root`, `package_tree_mismatch`, `guard_package` and `ForeignPackage`.
- **Two paths, every time.** Every guarded command now prints the imported package's path beside the interpreter's.
- **Where the check runs.** `guard` and `guard_or_exit` run it first, on both paths, before `--allow-unpinned` is consulted. A mismatch prints the working tree, the tree's own package and the imported package, says what to run instead, and exits 2.
- **What it covers.** Every command that goes through `guard_or_exit`:
  - `characterize`, `simulate`, `verify` and `report`;
  - `fixture verify`, `fixture build` and `fixture project`;
  - the four `calibrate` actions.

**The rule, and where it is stricter than the brief's wording.** It applies inside a oneground checkout (a working tree with its own `oneground/__init__.py`, where `.git` may be a directory or a `git worktree` file). There, the imported package must be *that tree's own* `oneground/`.
- **"Under the working tree" is not enough.** A venv inside the checkout puts an installed, possibly stale copy of the package under the tree, and that copy is exactly the code this is meant to stop.
- **Outside a oneground checkout, nothing is judged.** Otherwise a user running a pip-installed oneground from their own git project would be refused for having no second copy to confuse it with.
- **The pod and CI pass unchanged.** Both run `python -m oneground.cli` from the root of a clone and never install oneground as a package. This is from reading `docker/pod/Dockerfile`, `requirements.txt`, `corpora/run_*.sh` and `.github/workflows/calibration.yml`; I didn't run it on a pod.
- **There is no flag past it.** `--allow-unpinned` stamps an artifact made under other library versions. No stamp makes a run of one tree's code an artifact of another's.

**The tests (11, in `oneground/test_environment.py`).**
- **Synthetic cases:**
  - own package passes, including from a subdirectory
  - another tree's package is found
  - a `git worktree` `.git` file counts as a working tree
  - a copy installed inside the tree is foreign
  - outside a oneground checkout, nothing is judged
  - the refusal names both paths and what to run, exiting 2
  - `--allow-unpinned` does not bypass it
  - the package path is printed on every outcome
- **A real process.** `oneground simulate`, run from a staged second checkout, exits 2 before reading its requirements file, names both packages and writes nothing.
- **A check on the test run itself.** It fails if the run imported another checkout's package. Whichever module imports `oneground` first decides that for the whole process.

**Also: the home-path leak, redacted (pre-squash `834a6ae`).** One line in each of `tasks/020-simulator-state.report.md` and `tasks/020-simulator-state.md`. The brief's path is now the placeholder form the scan allows (`C:\Users\<developer>\…`); that is the brief's only change from the original.

## Measurements

**Byte identity, literal, with nothing masked.** For each fixture's two reference configurations:
- "v0.1 A/B" is task 020's two runs of the unmodified tree, with the two fields removed and re-written by simulate's own writer (`tasks/scratch/020b-expected.py`).
- "020b run 1" and "020b run 2" are the new code, the second with `--emit-state`.
- All comparisons are `cmp` (`tasks/scratch/020b-bytes.sh`, log `runs/020b-bytes.log`).

| fixture | comparison | result | sha256 |
|---|---|---|---|
| StackExchange 20k | v0.1 A vs v0.1 B, timings removed | identical | `71100fcc…7dd898` |
| StackExchange 20k | 020b run 1 vs 020b run 2 (`--emit-state`) | identical | `71100fcc…7dd898` |
| StackExchange 20k | 020b run 1 vs v0.1 A | identical | `71100fcc…7dd898` |
| StackExchange 20k | 020b run 2 vs v0.1 B | identical | `71100fcc…7dd898` |
| StackExchange 20k | every `.state.npz` digest, task 020 run vs 020b run 2 | identical | — |
| arXiv 150k | v0.1 A vs v0.1 B, timings removed | identical | `d44d41c9…652d87` |
| arXiv 150k | 020b run 1 vs 020b run 2 (`--emit-state`) | identical | `d44d41c9…652d87` |
| arXiv 150k | 020b run 1 vs v0.1 A | identical | `d44d41c9…652d87` |
| arXiv 150k | 020b run 2 vs v0.1 B | identical | `d44d41c9…652d87` |
| arXiv 150k | every `.state.npz` digest, task 020 run vs 020b run 2 | identical | — |

**0 differences in 10 comparisons.** Moving the timings changed no byte of any measured value on either fixture. The same code writes the same `simulate.json` with or without `--emit-state`, and the state files are reproduced exactly.

`_seconds` fields left in `simulate.json` after the change: 0 on both fixtures. On StackExchange, the timings now sit in `simulate_info.json` as declared, for example `single_node_hnsw`: build 30.89 s, query 1.16 s.

**The trap, measured on this machine.** The venv's editable install maps `oneground` to the main checkout.

| started from | imports | has the 020b guard |
|---|---|---|
| a neutral directory | main checkout | no |
| a subdirectory of `oneground-v2` (`tasks/scratch`) | **main checkout** | no |
| the `oneground-v2` root, `python -m` / `python -c` | `oneground-v2` | yes |

## Verification

- `oneground/test_environment.py`: 42 of 42, including the 11 new tests and a now-clean identifier scan.
- `oneground/simulate/test_simulate.py`: 14 of 14.
- `oneground/test_cli.py`: 8 of 8.
- `oneground/models/test_conformance.py`: 21 of 21.
- Report suites (`test_end_to_end`, `test_verdict`, `test_claims`): 84 passed, 2 skipped. The skips are the existing gates that need a local arXiv verify/report workdir.
- **Full suite** (`pytest oneground corpora`, from the worktree root, after both byte-identity runs): **794 passed, 3 skipped, 0 failed**, in 205.6 s. The 3 skips are the same environment gates as task 020's. This fresh worktree has no local `runs/arxiv-150k-via-characterize` verify or report workdir, so these have nothing to read: `oneground/report/test_claims.py:443`, `oneground/report/test_end_to_end.py:348` and `oneground/verify/test_matched.py:1182`.
- Every byte-identity run printed the guard's new `package` line, showing the worktree's own package.
- **The squash** (`tasks/scratch/020b-squash.sh`). The commit is made only after every one of these checks passes:
  - HEAD was the pre-squash tip, and `383c7a1` is its base.
  - After `git reset --soft 383c7a1`, the staged set equals the 17 files tasks 020 and 020b named.
  - No line of the squashed patch carries a home path.
  - The identifier scan passes against the squashed tree before the commit.
  
  After the commit: exactly one commit sits on `383c7a1`, its tree equals the pre-squash tip plus the 020b files, and the scan is run again. The commit's hash is given in the hand-off, since a commit cannot name itself.

## Observed, not done

- **The guard can't protect this worktree from the main checkout's copy yet.**
  - The check lives in the package it inspects. In the trap as it actually occurs here (a command started in `oneground-v2` that imports the main checkout's package), the code that runs is the main checkout's, and that copy has no package check.
  - Commands are covered in both directions only once `main` carries 020b.
  - The test run is already covered: if another checkout's package was imported first, the new suite-level test fails, either on the mismatch or because that copy lacks the function.
  - Fixing this in the main checkout now would mean editing it, so I didn't.
- **The leaked path is out of history.** On the developer's decision, `task-020` was squashed to one commit on `383c7a1`. The pre-squash commits that carried the path (`bba3f37`, `850dabe`, `834a6ae`) are on no branch now. They stay in this machine's local reflog until git prunes it, and they were never pushed.
- **Older reports still describe timings in `simulate.json`.** `tasks/008-models-simulate.report.md`, `tasks/010-report.report.md` and task 020's report are historical records, and I left them.
- **Other timings are untouched.** `calibration/history.jsonl` and `fixtures/glove-100-angular.fixture.yaml` carry `build_seconds` of their own. They are not `simulate.json`.
- **Task 020 had a gap in its checks.** Its full suite ran before its report was committed, so the tracked-tree scan never read the report. Committing and then re-running `test_environment` should be the last step of a task.

## Repo now contains

On `task-020`, not pushed: **one commit after `383c7a1`**, holding tasks 020 and 020b together.
- Task 020: the state format, the three families' `state()`, `--emit-state`, the state-only renderer, the conformance tests, `docs/STATE.md` and its report.
- 020b:
  - the 020 brief;
  - the timing move (`oneground/simulate/__init__.py`, `oneground/simulate/test_simulate.py`, `oneground/report/test_end_to_end.py`);
  - the package guard (`oneground/environment.py`, `oneground/test_environment.py`);
  - the v0.2 format note in `docs/STATE.md`;
  - this report.

No measured value, tolerance, seed, gate or fixture file was changed.

## Blocked on developer

Nothing. Both open questions are decided:
- **Squash `task-020` before merge.** Done, as above.
- **No escape flag on the package guard.** Built that way. `--allow-unpinned` stamps its output so the result stays honest. There is no honest stamp for "these results may describe different code".

The developer also confirmed both strictness choices as made: the tree's own package, not just a path under the tree; and judging only inside a oneground checkout.
