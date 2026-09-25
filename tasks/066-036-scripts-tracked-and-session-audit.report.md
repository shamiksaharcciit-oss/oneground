# Report: 066-036-scripts-tracked-and-session-audit

## Repo state expected vs found

Expected task 065's merged state: `sessions/036-models.yaml` and
`corpora/run_036_models.sh` repriced and fixed on `main`, with the actual
measuring code (`036-ordering-experiment.py`, `036-truncation-per-model.py`,
`036-render-ordering.py`) still living under `tasks/scratch/`, gitignored,
reached only by the `inputs:` scp mechanism task 065 added. Found exactly
that, and the developer's own read of it: the `inputs:` fix gets the run
working but does not put "the code producing a published measurement" in
git history, so a run that already happened could not be reproduced or
audited from the repository -- only from whichever laptop's local disk
still had the scratch file. Branch `task-066` from `main` at `47fe1ff`.

## What was done

**Moved the three scripts `run_036_models.sh` depends on (plus the one
that turns the raw numbers into a verdict) out of `tasks/scratch/` and
into `corpora/`, tracked and committed:**

- `corpora/036-ordering-experiment.py` (the measuring instrument)
- `corpora/036-truncation-per-model.py` (the confound check)
- `corpora/036-render-ordering.py` (turns the raw cells into the ordering
  verdict -- never runs on the pod, so strictly outside "what the session
  depends on," but it is exactly as much "the code producing a published
  measurement" as the other two: a run whose numbers cannot be read back
  into a verdict without a script nobody can find is not fully reproducible
  either. Moved for the same reason, not asked for by name.)

Fixed every cross-reference: `036-truncation-per-model.py`'s dynamic
import (`importlib.util.spec_from_file_location`) now points at
`corpora/036-ordering-experiment.py`; `run_036_models.sh`'s two `python`
invocations now name the `corpora/` paths. Left unchanged, deliberately:
the scripts' own default **output** paths (`tasks/scratch/
036-ordering-results.json`, `tasks/scratch/036-truncation-results.json`) --
those are regenerable measurement results, not code, and stay in the
gitignored scratch directory the same way every other run's receipts do
before they are written up.

`sessions/036-models.yaml`'s `inputs:` block no longer names the two
scripts -- they travel in the git bundle like any other tracked file now,
which is the entire point. `036-price.json` stays declared there,
`optional: true`: it is a local pricing receipt, not code, so it does not
need the stricter fix.

Verified working from the new location, not assumed: `py_compile` on all
three; `036-render-ordering.py` run against the real (old-shape) results
file, unchanged behaviour; `measure()` run against synthetic vectors from
`corpora/036-ordering-experiment.py` directly, correct keys;
`036-truncation-per-model.py` imported and run far enough to load both
corpora and start resolving a model, confirming the dynamic import path
resolves -- no `FileNotFoundError`, no `ModuleNotFoundError`.

**Audited every other session spec for the same class of bug** (a `run:`
or `inputs:`-eligible dependency on a path under `tasks/scratch/`, which
`git bundle create --all` never carries, with no `inputs:` entry covering
it): grepped `tasks/scratch` across all nine `run_*.sh` scripts driven by
the eleven files in `sessions/*.yaml`, then read every match in context
rather than trusting the grep count.

    session                              status
    027-emit-state-arxiv.yaml            already fixed -- inputs: for
                                          027_acceptance.py (precedent this
                                          task's fix follows)
    029-kmeans-second-environment.yaml   already fixed -- inputs: for
                                          029_pod_kmeans.py
    029-determinism-proof.yaml           clean -- run_029_proof.sh has no
                                          tasks/scratch reference
    032b-state-proof.yaml                clean -- same
    036-models.yaml                      task 065's original find, fixed
                                          properly this task (above)
    arxiv-build.yaml                     clean -- SOURCE unset, defaults to
                                          a volume path, not a repo path
    chunking-sec-filings.yaml            clean -- run_chunking.sh has no
                                          tasks/scratch reference
    sec-filings-build.yaml               clean -- run_fixture_build.sh's
                                          tasks/scratch mention is a
                                          documentation comment for the
                                          SOURCE pattern, unused here; the
                                          one tasks/scratch path in this
                                          session is a fetch DESTINATION
                                          (session log), not a pod-side
                                          dependency
    stackexchange-build.yaml             clean -- same as above
    verify-arxiv-150k-two-engines.yaml   clean -- run_verify_pod.sh's
                                          tasks/scratch mention is a
                                          historical citation inside a
                                          comment (task 011), not a runtime
                                          path
    verify-arxiv-smoke-via-product-path.yaml   clean -- same
    smoke.yaml                           REAL, LIVE BUG -- see below

**`smoke.yaml`: confirmed broken, and its own comment said the opposite.**
`run: ... SOURCE=tasks/scratch/001-synthetic-source.json ...
bash corpora/run_arxiv_150k.sh`, and the session's own top comment
asserted "The build's inputs are both committed" naming that exact path as
one of the two. `tasks/scratch/` is entirely gitignored
(`.gitignore`); `git ls-files tasks/scratch/` returns nothing;
`git check-ignore -v` confirms this specific file matches the
`tasks/scratch/` rule. The claim in the comment was false, and there was
no `inputs:` block at all. `run_arxiv_150k.sh` does not regenerate a
missing `SOURCE` -- it only checks `[ ! -f "$SOURCE" ]` and refuses by
name -- so `oneground pod up sessions/smoke.yaml` would create a pod, bill
for setup, and fail at that check, the identical failure shape task 065
found for `036-models.yaml`. This is the session's own docstring calling
it "the session to run first after any change to `oneground/pod/`" -- a
regression test for the pod tooling itself, not a one-off -- and it has
apparently not been re-run since task 027 established the `inputs:`
pattern this same file's own comment claimed (wrongly) it did not need.

Fixed the same way 027 and 029 fixed the identical problem: added
`inputs:` for `tasks/scratch/001-synthetic-source.json`, and corrected
the comment to say what is actually committed versus declared. **Not**
moved into a tracked path the way the 036 scripts were: this file is
generator output (`corpora/make_synthetic_source.py --out ...`, tracked,
seeded), not the measuring instrument itself -- data regenerable from a
tracked recipe is exactly what the `inputs:` mechanism and this project's
receipts-vs-declared distinction both already cover, and moving 2.7 MB of
regenerable synthetic JSON into git would be the wrong fix for a right
reason. Verified: `sessionmod.load('sessions/smoke.yaml')` succeeds, the
new input resolves to the real local file.

**Re-ran `oneground pod plan sessions/036-models.yaml`** after all of the
above. See Measurements.

## Measurements

- `oneground pod plan sessions/036-models.yaml`: RTX PRO 4500,
  $0.34-$0.72/hr (confirmed at $0.72/hr top of range), cost cap
  `2h x $0.72/hr = up to $1.44`, within `max_usd 3.00`. **Nothing was
  created.** (Task 065's report already noted two live GPU-availability
  fluctuations between calls in this same datacenter; this call landed on
  the same clean reading task 065's first call did. Re-run once more,
  close to the actual `y`, since that volatility is real and unrelated to
  anything fixed this task.)
- `git status --short` before this task's commit showed exactly the
  expected set: two modified tracked files
  (`corpora/run_036_models.sh`, `sessions/036-models.yaml`) plus one more
  (`sessions/smoke.yaml`) and three new tracked files under `corpora/`.

## Verification

Passed: `py_compile` on all three moved scripts; `036-render-ordering.py`
run from its new path against the real subsample results, unchanged
output; `measure()` run against synthetic vectors from the new path,
correct keys; `036-truncation-per-model.py`'s dynamic import resolved and
began executing (no `FileNotFoundError`/`ModuleNotFoundError`);
`oneground.pod.session.load()` on both `sessions/036-models.yaml` and
`sessions/smoke.yaml`; `oneground pod plan sessions/036-models.yaml`
prices within cap and creates nothing.

Not run: the pytest full suite / `test_environment.py` /
`identifier_findings()` / `site/teaser/` diff -- as task 065's report
established, nothing in `oneground/` references any of these session,
`corpora/run_*.sh`, or (now) `corpora/036-*.py` files, so there is nothing
in that suite these changes could affect. Re-checked this task: still
true after the move (grepped `oneground/` for the new filenames too).

## Observed, not done

- The nine-session audit above checked `tasks/scratch` dependencies
  specifically, because that is the exact class of bug named. It did not
  re-verify every session's `inputs:`/`outputs:` block for unrelated
  problems (stale remote paths, wrong caps, etc.) -- out of scope for what
  was asked.
- `corpora/036-price-the-full-run.py` (the standalone pricing script) was
  left in `tasks/scratch/`. It is not invoked by `run_036_models.sh` --
  nothing about the pod session depends on it -- but it is arguably "code
  producing a published measurement" in the same sense the three moved
  scripts are, since this task's own repriced numbers came from it. Not
  moved because the instruction was scoped to what the session depends on;
  flagged here since the same reasoning could extend to it.

## Repo now contains

- `corpora/036-ordering-experiment.py`,
  `corpora/036-truncation-per-model.py`,
  `corpora/036-render-ordering.py` (new, tracked -- moved from
  `tasks/scratch/`, cross-references fixed).
- `corpora/run_036_models.sh` (modified) -- both `python` invocations now
  name `corpora/`, not `tasks/scratch/`.
- `sessions/036-models.yaml` (modified) -- `inputs:` reduced to the one
  genuinely-still-data entry (`036-price.json`, optional); comments
  updated to describe the tracked-path fix and why it goes further than
  task 065's `inputs:`-only one.
- `sessions/smoke.yaml` (modified) -- `inputs:` added for
  `001-synthetic-source.json`; corrected comment.
- `tasks/066-036-scripts-tracked-and-session-audit.report.md` (new).

## Blocked on developer

The `y` at the terminal for `oneground pod up sessions/036-models.yaml`,
same as task 065. Re-running `pod plan` once more immediately before typing
it is worth doing, given the observed live price/availability volatility.
