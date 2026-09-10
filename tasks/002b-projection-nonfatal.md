# Task 002b — Projection cannot sink the build

## Expected repo state
Task 002 Part A committed; working tree clean. If not clean, stop and report.

## Why
UMAP over 150,000 × 768 has never been run. In `corpora/build_fixture.py` it
executes before `characterization.json` and `MANIFEST.sha256` are written, so
a runtime failure (memory, a numba/pynndescent edge case, a version quirk)
at hour three would leave every receipt artifact on disk but unmanifested.
The projection is declared and illustrative; it must not be able to fail the
receipts.

## Do
1. Reorder `corpora/build_fixture.py` so that `characterization.json`,
   `build_info.json`, and `MANIFEST.sha256` are written **before** the
   projection step, covering every artifact that exists at that point.
2. Wrap the projection step in a try/except that catches any `Exception`,
   logs the traceback to the build log, and continues. On success, save
   `projection.npy` and **append** its digest line to `MANIFEST.sha256`
   (LF-pinned). On failure, print a clearly labelled line
   `PROJECTION FAILED — fixture is complete without it` and add
   `"projection": "failed"` to `build_info.json` (rewrite it; it is
   declared, so this is allowed).
3. Add elapsed-time logging around the projection step and around the
   embedding step, so the log states how long each took.
4. `oneground/fixture_verify.py`: verification must pass whether or not
   `projection.npy` is present — it verifies what the MANIFEST lists.
   Confirm with a test, if one does not already cover it.
5. Rebuild the smoke fixture **with** projection (no `SKIP_PROJECTION`) so
   UMAP runs at least once on this machine, at small scale. Report its
   wall-clock and peak RSS (in-process). Then rebuild with
   `SKIP_PROJECTION=1` and confirm the verifier passes on both.
6. Simulate the failure path: run once with a deliberately broken UMAP
   (e.g. an env var the builder reads to raise inside the projection step,
   removed afterwards — or a scratch monkeypatch importing the builder
   unmodified). Confirm the build completes, the MANIFEST covers every
   receipt artifact, `build_info.json` records the failure, and the
   verifier passes.

## Acceptance
- Order of writes: receipts + MANIFEST first, projection last, appended.
- A projection failure yields a complete, verifiable fixture minus
  `projection.npy`, with the failure recorded in `build_info.json`.
- Smoke build with projection ran to DONE; wall-clock and RSS reported.
- No seed, tolerance, threshold, or measurement logic changed.

## Report
Standard format. Under Measurements: embedding and projection elapsed
times from the smoke run with projection, and the failure-path evidence
(MANIFEST contents and verifier output from step 6).
