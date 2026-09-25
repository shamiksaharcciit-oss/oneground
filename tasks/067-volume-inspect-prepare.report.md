# Report: 067-volume-inspect-prepare

## Repo state expected vs found

Expected `main` at `a40d281` (task 066's merge) with no session spec able
to answer what is actually on the `vecbench` volume -- session
20260925-185647 (`036-models.yaml`) refused at its first input check,
`/workspace/arxiv-150k/sample.jsonl.zst` not found, and nothing in the
repo checks the volume's real layout. Found exactly that. Branch
`task-067` from `main` at `a40d281`.

## What was done

**`sessions/036-volume-inspect.yaml` and `corpora/run_036_volume_inspect.sh`
-- a read-only, self-contained inspection session, committed from the
start** (not `tasks/scratch/`, for the same reason 066 moved the 036
scripts: this is the code producing the finding the next decision rests
on, so it belongs where it can be recovered and re-run). It touches no
GPU, loads no model, writes nothing to the volume, and answers exactly the
three things asked, not one:

1. **A recursive listing of `$ONEGROUND_ASSETS`, depth 4, with sizes** --
   `find ... -printf '%y %12s  %p\n'`, excluding the cloned repo and the HF
   model cache (neither is a corpus, both are large enough to bury what
   is). Not "does the expected path exist" -- everything under the volume,
   three levels past the mount point, which reaches a layout as deep as
   `fixtures/arxiv-150k/sample.jsonl.zst` with room to spare.
2. **A name search for the corpus files anywhere on the volume** --
   `sample.jsonl.zst`, `documents.jsonl.zst`, `vectors.npy`, `queries.npy`,
   wherever they sit, not only at the one path `036-models.yaml`'s run
   script checks.
3. **Whether each of the three corpus directories exists anywhere by
   name** (`arxiv-150k`, `stackexchange-150k`, `sec-filings-10k`),
   independent of what it contains -- answers "present under some layout"
   separately from "present at the exact file the models session expects,"
   which is the distinction the brief asked for and the models session's
   own refusal could not make.
4. **`sha256sum` of every file (2) finds**, assembled into a single
   `036-volume-inspect.json` receipt alongside the raw listing/candidate/
   digest text files, so the next attempt at `036-models.yaml` can verify
   it is reading the file it thinks it is, rather than discovering a
   mismatch at a second failure.

**Verified locally, end to end, at no cost**: a fake `$ONEGROUND_ASSETS`
tree (a corpus present under `fixtures/<name>/`, one absent entirely, the
cloned-repo directory correctly excluded from the listing) run through the
actual script (paths patched only for the local filesystem, the logic
untouched) produced a correct listing, correctly found both candidate
files by name, correctly reported one corpus present and two absent by
directory search, and a correctly-assembled JSON receipt -- catching one
real bug in the process: `sha256sum`'s default binary-mode output prefixes
the path with `*` (`<digest> */path`), which the JSON-assembly step's
digest lookup did not strip, so the digest for every found file would have
been silently absent (`null`) from the receipt while the script itself ran
to completion and printed `DONE` -- a failure that would not have shown up
as an error, only as a receipt quietly missing the thing it exists to
report. Fixed (`.lstrip("*")` on the parsed path before the lookup) and
re-verified: digests now populate correctly.

**Priced.** `oneground pod plan sessions/036-volume-inspect.yaml`: RTX PRO
4500, $0.34-$0.72/hr, cost cap `0.25h x $0.72/hr = up to $0.18`, within
`max_usd 0.50`. Nothing was created. Fixed overhead (provisioning, ssh,
bundle sync, venv setup) is the entire cost -- `036-models.yaml`'s own
session measured that at ~250 s; this session's own work (`find` and
`sha256sum` over, at most, a handful of corpus-sized files) adds seconds to
low tens of seconds on top. `max_hours 0.25` (15 min) and `max_usd 0.50`
give roughly triple the estimate in headroom.

**Not done, per the brief**: determining which of the two reconciliations
is right (move the corpus files to where the script expects them, or point
the script at where they actually are), and, if the corpora are absent
entirely, pricing a session to place them. Both require this session's own
output, which does not exist yet. Bringing that finding and that
recommendation is the next report, after a `y`.

## Measurements

- `oneground pod plan sessions/036-volume-inspect.yaml`: cost cap $0.18,
  within `max_usd 0.50`. Nothing created.
- Local dry run (patched paths, real logic): 5 listing entries, 2
  candidate files found and digested, 1 of 3 corpus directories found by
  name, 1 real bug found and fixed (digest-path asterisk stripping).

## Verification

Passed: `bash -n` on the run script; the full local dry run above,
including the JSON-assembly Python step run against the script's own
real intermediate files; `oneground.pod.session.load()` on the new spec;
`oneground pod plan`, prices within cap, creates nothing.

Not run: the pytest full suite / `test_environment.py` /
`identifier_findings()` / `site/teaser/` diff -- as with tasks 065/066,
nothing in `oneground/` references either new file (grepped), so there is
nothing in that suite these changes could affect.

## Observed, not done

None beyond what "Blocked on developer" and the last paragraph of "What
was done" already name.

## Repo now contains

- `sessions/036-volume-inspect.yaml` (new).
- `corpora/run_036_volume_inspect.sh` (new).
- `tasks/067-volume-inspect-prepare.report.md` (new).

## Blocked on developer

The `y` at the terminal for `oneground pod up sessions/036-volume-inspect.
yaml`. Once it runs: the reconciliation call (move files vs point script,
argued from what the volume actually holds) and, if the corpora are not
there at all, a separately-priced session to place them -- neither
decided here, both requiring this session's own result.
