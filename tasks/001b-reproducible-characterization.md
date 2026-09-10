# Task 001b — Make characterization.json reproducible

## Expected repo state
Task 001 complete and committed. `corpora/build_fixture.py`,
`oneground/fixture_verify.py`, `fixtures/arxiv-smoke/` present. If task 001
is not committed, stop and report.

## Why
Your task 001 report showed the pipeline is byte-deterministic for five of
six artifacts; `characterization.json` differs only by its `built_at`
timestamp. That makes the canonical fixture's measurement artifact
un-verifiable from a rebuild — the receipt property fails at the file where
it matters most. This must be fixed before the real build (task 002).

## Do
1. In `corpora/build_fixture.py`, split the output of the characterization
   step into two files:
   - `characterization.json` — measurement only: `fixture`, `version`,
     `characterization`, `reference_results`, `hot_categories`. No
     timestamps, no versions, no host information. Keys sorted, fixed
     float formatting (round to 6 decimals) so the bytes are stable.
   - `build_info.json` — `built_at`, `library_versions`, `python_version`,
     `platform`, `device`, and the sha256 of the source snapshot. This file
     is *declared*: recorded, listed in the MANIFEST, but exempt from
     reproduction.
2. Update the MANIFEST writer to include `build_info.json`.
3. In `oneground/fixture_verify.py`, add a `kind` column to the per-file
   output: `receipt` for reproducible artifacts, `declared` for
   `build_info.json`. Digest checks still apply to both; the distinction is
   for the future value-reproduction task, which will skip declared files.
4. Update `fixtures/arxiv-150k.fixture.yaml` and `fixtures/arxiv-smoke.fixture.yaml`:
   add `build_info.json` to `artifacts.files` with a comment `# declared`.
   This is the only permitted edit to the arxiv-150k spec in this task.
5. Rebuild the smoke fixture twice from scratch (delete the output directory
   between runs, `--skip-projection`). Diff the two `fixtures/arxiv-smoke/`
   directories.
6. Run `fixture_verify.py` on the second build.

## Acceptance
- Two clean rebuilds produce byte-identical `characterization.json`,
  `ground_truth.npy`, `vectors.npy`, `queries.npy`, `query_ids.json`,
  `sample.jsonl.zst`. Only `build_info.json` may differ, and only in
  `built_at`.
- `fixture_verify.py` reports verified for every file, with the `kind`
  column present.
- The arxiv-150k spec diff shows exactly one added line plus comment.

## Do not
- Change any seed, tolerance, threshold, or measured value.
- Touch the builder's sampling, embedding, ground-truth, or characterization
  logic beyond the output split.

## Report
Standard format. Under Measurements: the diff output between the two
rebuilds (file list with identical/differs), and the verifier output. Use
in-process self-measurement for any memory figure; do not probe across
process boundaries on this machine.
