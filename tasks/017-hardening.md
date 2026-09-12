# Task 017 — v0.1 hardening

## Setup
Worktree `..\oneground-012`: `git checkout -b task-017 main` from main at
or after `65fc33f`. Commit on `task-017`; never touch `main`. The
developer merges.

## Why
Five things the preview week's evidence says v0.1 needs. Each is a
measured finding from tasks 011–016, not a feature.

## Do

1. **Pre-baked pod image** (the durable fix for six environment faults).
   `docker/pod/Dockerfile` from `runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404`
   with: the pinned Python deps from `requirements.txt` (isolated venv at
   `/opt/oneground-venv`), Qdrant 1.19.1 native binary, PostgreSQL 16.15 +
   pgvector 0.8.6 from PGDG (the scoped-update recipe from 015, baked),
   postgres data/log directories pre-created under `/var/lib/postgresql`,
   `git`, `runpodctl`. No repo inside the image — the bundle still syncs.
   A GitHub workflow `.github/workflows/pod-image.yml` builds and pushes
   to GHCR (`ghcr.io/<owner>/oneground-pod`) on changes to
   `docker/pod/**` or `requirements.txt`, tagged with the short SHA and
   the digest recorded in `docker/pod/IMAGE.lock`. Sessions reference the
   image by **digest** (`image: ghcr.io/…@sha256:…`), never a floating
   tag; `plan` prints it. `run_verify_pod.sh` and `run_fixture_build.sh`
   detect the baked image (a marker file) and skip apt/pip entirely.
   Measure on smoke via a pod session (developer's `y`): time from
   RUNNING to `run started` before vs. after. Record both engine versions
   as engine facts from the image, not from apt.
   The developer must make GHCR packages public for the repo; say so under
   "Blocked on developer" with the exact setting.

2. **Repeated-run latency spread.** `verify` gains `runs: N` (default 1;
   session spec may set 3). Each run is a separate load phase on the same
   pod, same sample, engine restarted between runs; `verify.json` keeps
   every run and reports p95 as `{min, median, max, spread}`. `verdict.py`:
   a latency constraint is `meets` only if the **max** across runs meets;
   `fails` only if the **min** fails; otherwise `couldnt_check: meets in
   k of N runs, spread X ms` — never picked from one run. Report shows all
   three. Document in VERIFY.md next to the 38.22/42.82 note. Test with
   synthetic runs straddling the threshold.

3. **Truncation accounting** for text intake. In `embed/`, count records
   exceeding the model's `max_seq_length`; write `truncated_count`,
   `max_seq_length`, `model` to `build_info.json` (declared) and print a
   warning at run time naming the count and "if these are documents
   rather than chunks, chunk them first". `docs/INTAKE.md` gains the
   one-paragraph rule: one record = one vector; bring chunks. Test on a
   synthetic corpus with a known number of over-length records.

4. **Tracked-tree identifier scan.** `oneground/environment.py` (or a
   `.github/scripts/` script — you choose, but it runs in the suite):
   walk every tracked file and fail on a developer path, hostname
   (`platform.node()` value and the `DESKTOP-` pattern), or a bare
   `C:\Users\<name>` — the same `_machine_identifiers()` set 014 guards
   at write time — with an allowlist for the docs that quote the trap by
   name. This is the guard 015 found missing: a branch forked before a
   redaction would have carried identifiers into the public tree.

5. **`qps_max`.** An unthrottled load phase (open-loop, ramp until error
   rate > 0.5% or p99 exceeds 5× baseline), reported as a separate row
   `qps_max` with its own caveat ("the ceiling under this load shape, on
   this host"); never used by the `qps` sustain verdict. Optional per
   session (`load.measure_ceiling: true`). Run it once on smoke locally;
   the arXiv number waits for the next matched pod session.

6. Small items carried: the `scope` decision-log count (verify it's fixed
   on the current arXiv `report.json`; if not, fix); the price table
   `as_of` must not postdate the run (assert in `report`); the `runs/`
   test name and skip reason (done in 015b — confirm).

## Acceptance
- Image builds in CI, digest locked, sessions reference it by digest;
  smoke session shows setup time before/after.
- `runs: 3` produces spread and the three-way verdict rule; tests pass.
- Truncation count appears in `build_info.json` and the warning fires.
- Identifier scan passes on the current tree and fails on an injected path.
- `qps_max` row exists on smoke, separate from `qps`.

## Do not
- Change any published value or tolerance. Merge to main. Run the arXiv
  matched session (it's a later `y`). Use a floating image tag anywhere.
