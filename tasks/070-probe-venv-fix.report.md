# Report: 070-probe-venv-fix

## Repo state expected vs found

Expected `main` at `204fc3a` (task 069's merge) with `sessions/
036-models.yaml` re-priced and both corpora correctly placed on the volume
(task 068). Session 20260925-200837 (pod `ybs7k62hvsymty`), bundled at
`204fc3a`, was already up and running when this task started. Watched,
fetched, pod terminated. Elapsed ~8 min; ~$0.10, well inside the $3.00
cap. Branch `task-070` from `main` at `204fc3a`.

## What was done

**The run died at the probe, before any measurement. None of the
requested findings exist, and none are inferred below.** The log in full:

    [20:12:43] checking inputs under /workspace
    [20:12:43]   ok  48M  /workspace/arxiv-150k/sample.jsonl.zst
    [20:12:43]   ok  26M  /workspace/stackexchange-150k/sample.jsonl.zst
    [20:12:43] probing throughput before committing to the run
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    ModuleNotFoundError: No module named 'numpy'

The one thing this confirms cleanly: **task 068's placement held.** Both
corpora were found this time, at the sizes the manifests declare (48M
arxiv-150k/sample.jsonl.zst against a declared 49,920,799 bytes, 26M
stackexchange-150k/sample.jsonl.zst against a declared 26,813,350 bytes --
`du -h` rounding, not a discrepancy). The input check that killed the
first attempt (task 065's report) is not what killed this one.

**Going through the brief's order, honestly: none of it is answerable.**
Not whether `reading()` was reached -- the probe that precedes the
ordering experiment entirely never got past its own first line. Not e5's
counts or σ. Not the ordering or the transfer verdicts. Not a sentence
about what a held ordering would and would not establish, because nothing
was measured to hold. Writing any of it now would be inventing a result
this run never produced.

**Root cause: `corpora/run_036_models.sh` never activated the venv, and
nothing upstream of it does either.** Every other run script that calls a
bare `python` activates the venv first
(`corpora/run_arxiv_150k.sh`, `corpora/run_fixture_build.sh`:
`. .venv/bin/activate` / the Git-Bash fallback) or calls the venv's
python by its explicit path (`corpora/run_027_emit_state.sh`,
`corpora/run_029_kmeans.sh`: `PY=.venv/bin/python`). `run_036_models.sh`
did neither -- it called bare `python` three times (the throughput probe,
and the two `corpora/036-*.py` invocations) and relied on nothing.
Traced the actual launch path to confirm this is not a one-off: `_setup_
script` (`oneground/pod/cli.py`) builds or symlinks the venv over its own
ssh connection and activates it there, but that activation cannot survive
past that connection closing; `start_run`/`build_start_command`
(`oneground/pod/sshx.py`) launches the run command fresh, over a
**separate** connection, with no activation carried over and nothing in
the launch payload that puts the venv on `PATH`. So a bare `python` in any
run script resolves to the pod's system interpreter, which has no numpy --
this was always going to fail the first time `run_036_models.sh` actually
reached its probe on a real pod, and nothing before session 20260925-185647
(task 065's first attempt) ever had, because that one died earlier, at the
input check.

**Why "prepare, do not run" could not have caught this.** Every local
verification this task cycle ran against `.venv/Scripts/python.exe`
explicitly, on this laptop -- which is exactly the class of thing "does a
bare `python` resolve correctly in a pod's default shell" cannot be tested
by, the same way `pod plan` cannot inspect the volume's real layout. Two
of three defects a real run has now found (this one and the missing
corpus) share that shape: correct locally, because local testing never
exercises the one difference between a laptop and a fresh pod shell that
matters.

**Fixed.** `corpora/run_036_models.sh` now activates the venv immediately
after `cd /workspace/oneground`, mirroring `run_arxiv_150k.sh`'s own block
exactly (Linux path, Git-Bash fallback, hard refusal if neither exists).
Every bare `python` call downstream inherits the activated `PATH`, so the
fix is one block rather than three call-site changes.
`corpora/run_036_volume_inspect.sh` and `corpora/run_036_place_corpora.sh`
were checked and do not share this defect: both call `python3` for a
JSON-assembly step that imports only `json`/`os`/`sys` -- stdlib, no venv
needed -- which is also why both of those sessions already ran clean on a
real pod.

**Verified, not just asserted.** Sourced the same activation block locally
(both branches syntax-checked with `bash -n`) and confirmed `python -c
"import numpy"` resolves to the venv's own numpy rather than erroring,
which is the exact failure this fix removes -- the closest local proxy
available for a check that ultimately needs the next pod run to confirm
for real, the same limit named above.

## Measurements

- Session 20260925-200837: ~8 min elapsed, ~$0.10, terminated. Nothing
  measured.
- Local proxy verification of the venv-activation fix: `python -c "import
  numpy"` after sourcing `.venv/Scripts/activate` resolves to this
  project's pinned numpy (2.5.3), not a system interpreter.

## Verification

Passed: `bash -n` on the fixed script; the local activation-block proxy
check above.

Not verifiable without another pod run: whether the probe itself now
succeeds and the run proceeds past it. That is what the next attempt is
for.

## Observed, not done

None beyond what is already named above.

## Repo now contains

- `corpora/run_036_models.sh` (modified) -- venv activation added.
- `tasks/070-probe-venv-fix.report.md` (new).

## Blocked on developer

The `y` at the terminal for `oneground pod up sessions/036-models.yaml`,
same as before. The card is unchanged by this fix (it changes what the run
does, not what it costs); re-run `oneground pod plan` immediately before
typing it regardless, given the GPU-availability volatility already
logged this cycle.
