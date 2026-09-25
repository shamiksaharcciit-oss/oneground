# Report: 072-syspath-reconciliation-and-finding

## Repo state expected vs found

Expected `main` at `a1da9af` (task 071's merge), with session
20260925-204013's third failure unfixed: `python corpora/
036-ordering-experiment.py`, run as a file the way `run_036_models.sh`
actually runs it, unable to import `oneground` at all --
`ModuleNotFoundError: No module named 'oneground'`, one line after the
probe's own, separate `python` invocation had successfully imported
`oneground.embed.registry` and `oneground.embed`. Found exactly that.
Branch `task-072` from `main` at `a1da9af`.

## What was done

**Fixed the class, not the line, per the brief.** The failure's real
shape: every local check of `corpora/036-ordering-experiment.py` reached
the code by a route that supplied something the pod's actual invocation
does not -- an explicit `sys.path.insert(0, '.')` in an ad hoc local
snippet, or `importlib.util.spec_from_file_location`, which never touches
`sys.path[0]` the way `python <path>` does. `python corpora/
036-ordering-experiment.py`, run as a real subprocess from the repo root,
puts the script's own directory (`corpora/`) on `sys.path[0]`, not the
repository root -- and `oneground` is never pip-installed (`pip install
-r requirements.txt` only), so nothing else makes it importable.

**Reconciled the two scripts to one convention, not two.**
`corpora/036-ordering-experiment.py` had no `sys.path.insert` at all;
`corpora/036-truncation-per-model.py` had `sys.path.insert(0,
os.path.abspath("."))`, which happened to work only because
`run_036_models.sh` always `cd`s to the repo root before calling it --
a cwd-dependent convenience, not a correctness argument. Checked which
convention is actually the majority one in `corpora/` before picking
either: `build_fixture.py`, `export_ground_view.py`, and `run_chunking.py`
all anchor to `__file__` --

    sys.path.insert(0, os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

-- so that is the convention both `036-*.py` scripts now use, not a
second `sys.path.insert` bolted on to make the symptom go away.
`036-truncation-per-model.py`'s dynamic import of its sibling
(`importlib.util.spec_from_file_location("ordering", ...)`) was also
switched from a bare relative string (`"corpora/036-ordering-
experiment.py"`, itself cwd-dependent) to a path built from the same
`__file__`-derived directory. `corpora/036-render-ordering.py` was
checked and needs no change: it imports only `json`/`os`/`sys`, never
`oneground`, so this class of bug cannot reach it.

**Verified by running the script the way the pod runs it -- a real
subprocess, not an import, not a heredoc, not `spec_from_file_location`
-- exactly as instructed, and exactly what should have been done from the
start:**

    ONEGROUND_ASSETS=<empty dir> ONEGROUND_036_N=1 ONEGROUND_036_CENTROIDS=2 \
      .venv/Scripts/python.exe corpora/036-ordering-experiment.py

Before the fix this would have failed at the import with
`ModuleNotFoundError: No module named 'oneground'`, reproducing session
20260925-204013's own failure locally, for free. After the fix, the
process gets past every `oneground.*` import
(`oneground.chunk.strategies`, `oneground.embed`, `oneground.embed.
registry`, `oneground.measures.crispness`, `oneground.measures.lid`,
`oneground.measures.skew`) and fails at the controlled point an empty
`ONEGROUND_ASSETS` predicts: `FileNotFoundError` on
`arxiv-150k/sample.jsonl.zst`, the same shape as the first pod failure
(task 065) -- reached locally, at zero cost, exactly as this method
promises. Ran `corpora/036-truncation-per-model.py` the identical way,
confirming its own imports (including the fixed dynamic import of its
sibling) now resolve too, failing at the same controlled point.

**Wrote up the shape, where the findings live:**
`tasks/finding-a-check-that-takes-a-different-route-than-production.md`.
The claim: a check that reaches the code being checked by a different
route than production takes is a check of a different program, not a
weaker check of the same one. Evidence: this task's own three pod
failures, in order, each with the specific route its local check took
and the specific thing production's own route does not supply. Recorded
in particular: the probe's successful import of `oneground.embed.
registry` one line before the failure made the failure look impossible --
same pod, same venv, same directory, same package on disk -- because
`python -` (the probe's heredoc) and `python <path>` (the ordering
experiment's own invocation) are different programs with respect to
`sys.path`, and only one of them is what the failing line actually ran.

**Re-priced `sessions/036-models.yaml`** after the fix verified. No
change to the session spec was needed -- this is a code fix inside a
script `run_036_models.sh` already names correctly.

## Measurements

- Real subprocess verification, `.venv/Scripts/python.exe corpora/
  036-ordering-experiment.py` and `.venv/Scripts/python.exe corpora/
  036-truncation-per-model.py`, from the repo root, `ONEGROUND_ASSETS`
  pointed at an empty directory: both pass every `oneground.*` import and
  fail at the expected, controlled `FileNotFoundError`. **This is the
  check that should have existed before session 20260925-204013's own
  attempt** -- it would have caught the failure for free.
- `oneground pod plan sessions/036-models.yaml`: cost cap $1.44, within
  `max_usd 3.00`. Nothing created.

## Verification

Passed: `py_compile` on both fixed scripts; the real-subprocess
verification above, run and read, not assumed; `oneground pod plan`,
prices within cap, creates nothing.

**It passed a real subprocess run locally before this report asked for
the `y`**, per the brief's explicit instruction to say so.

Not run: the pytest full suite / `test_environment.py` /
`identifier_findings()` / `site/teaser/` diff -- nothing in `oneground/`
references either `corpora/036-*.py` file.

## Observed, not done

- Whether to build a standing, mechanised version of the real-subprocess
  check (running every `corpora/*.sh`-invoked script as a real subprocess
  before a session is priced) is named in the finding's own "What is not
  decided here" and left there, not decided in this report.

## Repo now contains

- `corpora/036-ordering-experiment.py` (modified) -- `sys.path` fix.
- `corpora/036-truncation-per-model.py` (modified) -- `sys.path` fix,
  sibling-import path fix.
- `tasks/finding-a-check-that-takes-a-different-route-than-production.md`
  (new).
- `tasks/072-syspath-reconciliation-and-finding.report.md` (new).

## Blocked on developer

The `y` at the terminal for `oneground pod up sessions/036-models.yaml`.
Card: cost cap $1.44, within `max_usd 3.00`. Nothing created. The fix
passed a real subprocess run locally, stated above per the brief, before
this ask.
