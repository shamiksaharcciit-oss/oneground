# Report: 015b-two-failures-on-main

## Repo state expected vs found

Expected `main` at the 015 merge with two failing tests. Found `main` at
`77856e9` (merge task-015), clean tree, and both failures reproducible — but
only one of them the way the brief guessed, and neither for the reason the
suite made it look like.

Both were introduced by task 015, both are mine, and both were green on
`task-015` for reasons that had nothing to do with being correct.

## What was done

### 1. `test_the_real_arxiv_workdir_..._needs_local_run`

The brief's hypothesis was right: this checkout's
`runs/arxiv-150k-via-characterize/verify.json` is the 011-shape document — one
engine, flat, no `engines` list. The test's last three lines, which I added in
015, assert:

    assert data.get("engines_measured") == ["qdrant", "pgvector"]
    assert data.get("sequential") is True
    assert data.get("environment_id")

`engines_measured` is `None` there, so it fails on the first line.

**The workdir is not the defect.** `runs/` is gitignored, and the test's own
docstring already says why: "a workdir is a local artifact, not a fixture", and
an absent one is "an absent artifact, not a failure". An *older* workdir is
exactly as legitimate as an absent one. `engine_blocks()` and
`engine_info_blocks()` read both shapes deliberately — "so nothing that already
exists has to be rewritten to be readable". The test was the only thing in the
repo demanding the new shape, and what it was really asserting was **which run
the developer happened to do last**.

That is the same error I made in 015 and already fixed once in this very test:
asserting `MEETS` against a 40 ms threshold tested the machine rather than the
rule. I replaced it with a per-engine `!= COULDNT_CHECK` loop and then, four
lines further down, pinned the file to one specific pair of engines. The
rule-shaped part of the test was fine; the tail I bolted on was not.

Now the tail checks the file against **itself**: the engines it declares are
the engines it holds, a file carrying an `engines` list must declare
`engines_measured`, ordering is only asserted when there is more than one
engine to order, and a pre-015 file that declares no engine list is a
couldn't-check rather than a pass. Copying the two-engine workdir over from the
other checkout would also have turned the suite green; it would have left the
test asserting a local file's contents, and the next developer with an older
workdir would hit it again.

### 2. `test_start_command_actually_works_in_a_real_shell`

Not a workdir problem, and not really a PATH difference either — a PATH
difference is the symptom.

    shutil.which("bash")   from PowerShell  ->  C:\WINDOWS\system32\bash.EXE
                           from Git Bash    ->  Git Bash's own bash

`C:\Windows\System32\bash.exe` is the **WSL launcher**. It is a real bash and
`which` finds it, so the test's `if bash is None: skip` guard never fires — but
it runs in a different filesystem namespace, where the Windows temp path the
test hands it does not exist. It writes the log somewhere this process cannot
read. The test then waits out its full 20-second deadline and asserts on an
empty string:

    AssertionError: the env assignment did not reach the command: ''

which reads like `build_start_command` is broken. It is not; nothing was ever
wrong with the code under test.

So the test silently changed **which bash it was testing** depending on the
shell that launched pytest, and only failed in one of them. I ran the suite
from Git Bash on `task-015`, so I never saw it. That is why it was green.

Fixed by asking each candidate whether it can see the directory rather than
assuming: `_bash_that_shares_this_filesystem(probe_dir)` runs
`test -d "<dir>" && echo SHARED` in each of `which bash` and the usual Git Bash
locations, and returns the first that answers. If none can, the test skips with
the reason — a couldn't-check, not a pass and not a failure.

Confirmed it selects `C:\Program Files\Git\bin\bash.exe` and rejects the WSL
one, so the test still genuinely runs here rather than skipping its way to
green.

## Measurements

Full suite, both shells, this checkout, `.venv\Scripts\python.exe -m pytest -q`:

| | before | after |
| --- | --- | --- |
| PowerShell | 564 passed, **1 failed**, 1 skipped | **565 passed**, 1 skipped (182 s) |
| Git Bash | 565 passed, 1 skipped¹ | **565 passed**, 1 skipped (154 s) |

¹ Git Bash never saw the pod failure — that is the bug in the test, not a
difference in the result.

`.github/scripts` suite (CI runs it separately): **44 passed**, 105 s.

The one skip is `test_pod.py:2075`, the live RunPod test:
`RUNPOD_API_KEY not set; live test skipped`. Unrelated to this task and
skipping before it. (Read from `pytest -rs` — I had guessed it was a
`test_matched.py` skip and it is not.)

## Verification

- Both named tests pass from PowerShell and from Git Bash.
- The pod test **runs** rather than skips on this machine; the selected bash
  was printed and checked.
- `pytest -q` and `pytest -q .github/scripts` — the two commands
  `calibration.yml` runs — are both green.
- CI's engine step still matches the code 015 changed: it sets
  `ONEGROUND_QDRANT_URL` and passes `--engine qdrant`, and
  `calibrate/__init__.py:436` builds exactly `ONEGROUND_<ENGINE>_URL` while
  `--engine` still exists and still defaults to `qdrant`.
- On CI both fixes are inert in the right direction: a fresh clone has no
  `runs/`, so the workdir test skips as designed, and on ubuntu
  `which bash` is `/usr/bin/bash`, which shares the filesystem and passes the
  probe.

Couldn't-check: the `requirements.txt` install itself on Linux. The three new
pins (`psycopg`, `psycopg-binary`, `tzdata`) resolve and are installed here on
Windows; I have not resolved them on ubuntu-latest, which is what the next
dispatch will do.

## Observed, not done

**Two of my 015 tests were green for environmental reasons rather than correct
ones, and in the same way.** One pinned a local artifact's contents, the other
pinned whichever bash the launching shell surfaced first. Both passed on
`task-015` and neither was measuring what its name claims. The pattern worth
naming: a test that reads something outside the repo — a workdir, a PATH entry
— has to state what it requires of it and skip when that is absent, and both
of these asserted instead.

**Nothing scans a test for shell-dependence.** This is the second time in two
tasks that a guard gap of this shape has shown up; 015's report already records
that 014's identifier guards only check what gets written next, never what is
already committed. Not in this brief.

**The 011-shape workdir in this checkout is now untested against the two-engine
path.** The two-engine workdir exists in the other checkout
(`..\oneground-012\runs\arxiv-150k-via-characterize\`). The test now passes on
either, but only one of them exercises the multi-engine branch locally. Copying
it across is a one-line operation and the developer's call, not mine.

## Repo now contains

Changed:

    oneground/verify/test_matched.py   the workdir tail checks the file against
                                       itself, not against one pair of engines
    oneground/pod/test_pod.py          _bash_that_shares_this_filesystem; the
                                       test picks a bash that can see its own
                                       temp dir, or skips saying so

New:

    tasks/015b-two-failures-on-main.report.md   this file

No source under `oneground/` outside those two test files was touched; neither
fix changes any behaviour the package ships.

## Blocked on developer

Nothing. Not pushed, as instructed — `main` is committed locally and ahead of
`origin/main` by the 015b commit.
