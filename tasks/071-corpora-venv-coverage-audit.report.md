# Report: 071-corpora-venv-coverage-audit

## Repo state expected vs found

Expected `main` at `2c3fecf` (task 070's merge), `run_036_models.sh`
fixed, and no check anywhere confirming the fix was the only place this
defect lived -- task 070 checked the two sibling `036-*.sh` scripts
because they were the immediate neighbours, and found them clean, but for
a reason (stdlib-only imports) that would not have caught a script that
*does* need the venv and also does not activate it. That gap is what this
task closes. Found exactly that state. Branch `task-071` from `main` at
`2c3fecf`.

## What was done

**Every script in `corpora/` (12 `.sh` files; the `.py` files are never a
session's own `run:` target -- always invoked by one of these, so their
correctness is inherited from whichever script calls them, checked as
part of each row below rather than separately), classified on two
questions: does it reach the venv (activation or an explicit interpreter
path), and does it need to.**

    script                        venv handling                need non-stdlib?   verdict
    restart_engine.sh             none -- calls no python at all               no    clean, needs none
    run_027_emit_state.sh         PY=.venv/bin/python, every call               yes (faiss, numpy)   clean
    run_029_kmeans.sh             PY=.venv/bin/python, every call               yes (faiss, numpy)   clean
    run_029_proof.sh              PY=.venv/bin/python, every call               yes (faiss, numpy)   clean
    run_032b_state_proof.sh       PY=.venv/bin/python, every call               yes (faiss, numpy)   clean
    run_036_models.sh             activates (task 070's fix)                    yes (numpy, torch, sentence-transformers via oneground.embed)   clean, was broken
    run_036_place_corpora.sh      none -- calls no python at all               no    clean, needs none
    run_036_volume_inspect.sh     none -- bare python3, stdlib only (json/os/sys)   no    clean, needs none
    run_arxiv_150k.sh             activates, before its first python call       yes (yaml, oneground.*)   clean
    run_chunking.sh               activates, before its first python call       yes (yaml, oneground.*)   clean
    run_fixture_build.sh          activates, before its first python call       yes (yaml, oneground.fixture)   clean
    run_verify_pod.sh             activates, before its first python call       yes (oneground.cli, verify)   clean

**No other instance was found.** For the four scripts using the explicit-
path pattern (`PY=.venv/bin/python`) I did not stop at the first
assignment -- grepped each file for every remaining bare `python`
invocation after it and found none: every call in all four consistently
goes through `$PY`. For the four that activate, checked the activation
line's position against every later `python` call and confirmed activation
comes first in each. For the three needing neither (`restart_engine.sh`,
`run_036_place_corpora.sh`, `run_036_volume_inspect.sh`), read each in
full rather than trusting the absence of a grep match: `restart_engine.sh`
is pure bash against `pkill`/`curl`/`su`/`pg_ctl`, no interpreter at all;
`run_036_place_corpora.sh` is `find`/`tar`/`sha256sum`, no interpreter at
all; `run_036_volume_inspect.sh`'s one `python3` call imports only `json`,
`os`, `sys`.

**The record this task asked for, stated the way it asked for it: a
script that does not need the venv is recorded as fine for that reason,
not by omission.** All three no-python scripts are fine because nothing
in them ever asks for a third-party package, not because a grep happened
to find nothing near a `python` keyword -- the distinction the brief drew
explicitly, since the same absence-of-a-match was what made task 070's
first pass over the two sibling `036-*.sh` scripts correct by luck rather
than by a check that would have caught the opposite case.

**Re-priced `sessions/036-models.yaml`** after confirming no further code
changes were needed -- this task found nothing left to fix, only
confirmed the fix already made was complete.

## Measurements

- 12 `.sh` scripts in `corpora/`, all 12 classified, 0 additional defects
  found.
- `oneground pod plan sessions/036-models.yaml`: cost cap $1.44, within
  `max_usd 3.00`. Nothing created. (See Verification for the exact
  figures pulled from this run.)

## Verification

Passed: full read of every `corpora/*.sh` file's python-invocation
pattern, not a grep-only pass; ordering check (activation/explicit-path
precedes every use) for the eight scripts that need the venv; full read
of the three scripts that don't, confirming no third-party import rather
than inferring it from a missing keyword; `oneground pod plan
sessions/036-models.yaml`, prices within cap, creates nothing.

Not run: the pytest full suite / `test_environment.py` /
`identifier_findings()` / `site/teaser/` diff -- no code changed this
task, only the audit above and a re-price.

## Observed, not done

None. This task closed a coverage gap in task 070's own check rather than
finding new work.

## Repo now contains

- `tasks/071-corpora-venv-coverage-audit.report.md` (new). No other files
  changed.

## Blocked on developer

The `y` at the terminal for `oneground pod up sessions/036-models.yaml`.
Card: cost cap $1.44, within `max_usd 3.00`. Nothing created.
