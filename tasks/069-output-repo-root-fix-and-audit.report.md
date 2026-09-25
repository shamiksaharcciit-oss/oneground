# Report: 069-output-repo-root-fix-and-audit

## Repo state expected vs found

Expected `main` at `6e4c503` (task 068's merge), with `sessions/
036-volume-inspect.yaml` already exhibiting the defect the developer
reported by hand (its `outputs:` tarball landing at repo root, blocking
the next `up` until manually cleared), and `sessions/036-models.yaml`
carrying the same unfixed line, unchanged since before task 065. Found
exactly that. Branch `task-069` from `main` at `6e4c503`.

## What was done

**Fixed both in the same commit, as instructed: `036-models.yaml`'s
`036-models.tgz` output and `036-volume-inspect.yaml`'s
`036-volume-inspect.tgz` output now land under `tasks/scratch/`, matching
`036-place-corpora.yaml`'s own outputs and the pattern every other
session's `local:` already follows for output kinds that are not meant to
become tracked repo content.**

    036-models.yaml:          local: ./  ->  local: tasks/scratch/036-session-log/
    036-volume-inspect.yaml:  local: ./  ->  local: tasks/scratch/036-volume-inspect-log/

Both now share their tarball's destination with the log output already
declared beside it, the same shape `036-place-corpora.yaml` used from the
start. Verified: both specs still load
(`oneground.pod.session.load`), and `oneground pod plan sessions/
036-models.yaml` resolves and prices identically to before the fix --
this changes where a fetch writes, not what the session costs or does.

**Audited every session spec for the same defect on the output side** --
a `local:` that lands an `extract: true` tarball at the repository root
whose internal member paths are a flat, top-level directory name rather
than a path already routed to somewhere tracked-for-review or gitignored.
Read every `outputs:` block in full, not just grepped for `local: ./`,
because that pattern alone does not distinguish a defect from a correct
use of it:

    session                                    outputs land                   status
    027-emit-state-arxiv.yaml                  runs/027-arxiv-projection-pod/  clean (explicit runs/, gitignored)
    029-determinism-proof.yaml                 runs/029-proof-pod/             clean
    029-kmeans-second-environment.yaml         runs/029-kmeans-pod/            clean
    032b-state-proof.yaml                      runs/032b-state-pod/            clean
    verify-arxiv-150k-two-engines.yaml         runs/arxiv-150k-via-characterize/  clean
    verify-arxiv-smoke-via-product-path.yaml   runs/arxiv-smoke/               clean
    arxiv-build.yaml                           local: ./, tarball routes to fixtures/arxiv-150k/...  clean --
                                                the tracked review-then-commit destination, by design
    sec-filings-build.yaml                     local: ./, tarball routes to fixtures/sec-filings-10k/...  clean, same reason
    stackexchange-build.yaml                   local: ./, tarball routes to fixtures/stackexchange-150k/...  clean, same reason
    smoke.yaml                                 local: ./, tarball routes to fixtures/arxiv-smoke/...  clean, same reason
    chunking-sec-filings.yaml                  local: ./, tarball routes to runs/chunking-sec-filings-10k/ + logs/chunking.log  clean --
                                                confirmed by reading corpora/run_chunking.sh's own `pack()`
                                                (tars from `-C "$REPO"` with members already prefixed
                                                `runs/...`/`logs/...`, both gitignored)
    036-models.yaml                            was: local: ./, tarball is a flat `036-models/...`  WAS BROKEN, fixed this task
    036-volume-inspect.yaml                    was: local: ./, tarball is a flat `036-volume-inspect/...`  WAS BROKEN, fixed this task
    036-place-corpora.yaml                     tasks/scratch/036-place-corpora-log/ for both  already correct

**The pattern does not generalise past the two already found.** Every
`local: ./` elsewhere in `sessions/*.yaml` is a deliberate, correct use of
the mechanism -- the tarball's own internal paths already carry a
`fixtures/<corpus>/` or `runs/...`/`logs/...` prefix, so extracting at
repo root reconstructs a tracked-for-review or gitignored destination, not
a loose top-level dump. What distinguishes the two broken ones is that
`corpora/run_036_models.sh` and `corpora/run_036_volume_inspect.sh` both
build their tarball with `tar -czf ... -C /workspace <name>` -- a flat
name with no routing prefix at all -- which is fine on the pod, where
`/workspace/<name>/` is exactly where the receipt belongs, and becomes
the defect only once the SAME flat name is asked to extract at the repo
root on the laptop side, where nothing routes it anywhere.

**Why this was found by accident twice rather than checked once.** The
task-065/066 `inputs:` audit checked one direction (does a gitignored
local file reach the pod); this checks the other (does a fetched output
land somewhere the dirty-tree guard tolerates) -- and nothing in
`oneground/pod/` checks either automatically. `Output`'s own class
(`oneground/pod/session.py`) has an `is_inside_repo()` method already,
used elsewhere to note when an output is deliberately outside the repo
(the release-asset tarballs to `../oneground-assets/`), but nothing calls
it to warn when an output lands *inside* the repo at a path `git status`
would call dirty. Not built this task -- flagged, since it is the
mechanical version of the same audit, not requested.

**Re-priced `036-models.yaml`** after the fix, per the brief.

## Measurements

- `oneground pod plan sessions/036-models.yaml` (post-fix): RTX PRO 4500,
  $0.34-$0.72/hr, cost cap `2h x $0.72/hr = up to $1.44`, within
  `max_usd 3.00`. Nothing created. Identical price to the pre-fix card --
  this change affects only where a fetch writes.

## Verification

Passed: `oneground.pod.session.load()` on both fixed specs;
`oneground pod plan sessions/036-models.yaml`, prices within cap, creates
nothing; the full-session output audit above, read in full rather than
grepped, including tracing `chunking-sec-filings.yaml`'s tarball
construction back through `corpora/run_chunking.sh`'s `pack()` and
`requirements.chunking-sec-filings.yaml`'s own `workdir` to confirm its
`local: ./` is correct rather than assuming it from the pattern alone.

Not run: the pytest full suite / `test_environment.py` /
`identifier_findings()` / `site/teaser/` diff -- as with every session-spec
task this cycle, nothing in `oneground/` references these files.

## Observed, not done

- `Output.is_inside_repo()` exists and is unused for exactly the check
  that would have caught this mechanically (an output whose `local:`
  resolves inside the repo and is not already gitignored, checked at
  `plan` or `up` time, before the fetch that creates the dirty tree).
  Not built -- flagged as a candidate for whoever next touches
  `oneground/pod/cli.py`'s fetch path, since two independent instances of
  the same defect, found by hand, is the shape this project's own practice
  treats as worth a mechanism rather than a third manual catch.

## Repo now contains

- `sessions/036-models.yaml` (modified) -- output fixed, comment added.
- `sessions/036-volume-inspect.yaml` (modified) -- output fixed, comment
  added.
- `tasks/069-output-repo-root-fix-and-audit.report.md` (new).

## Blocked on developer

None. `036-models.yaml`'s card is ready: cost cap $1.44, within
`max_usd 3.00`. Nothing created.
