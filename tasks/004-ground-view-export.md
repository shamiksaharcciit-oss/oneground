# Task 004 — Ground-view export

## Expected repo state
Task 003c committed; tree clean.

## Why
The hero image (the ground view) must be drawn from the fixture's real
geometry: each point's k-means region, its closure copy count, and its
category. Those need `vectors.npy` and `sample.jsonl.zst`, which live on
the pod's volume, not the laptop. This task adds an export that computes a
small per-point table on the pod, so rendering (task 005) runs locally on a
few megabytes.

## Do
1. Create `corpora/export_ground_view.py`:
   - inputs: `--spec <fixture yaml>` and `--dir fixtures/<id>/` (must
     contain vectors.npy, queries.npy, sample.jsonl.zst, projection.npy,
     ground_truth.npy).
   - recompute, with the spec's seeds and definitions exactly (import the
     functions from `build_fixture.py` unmodified): k-means-256 centroids;
     per base vector: region id (nearest centroid), d1, d2, closure copy
     count at ε = 0.20 / MAX_ASSIGN 4; per query: nearest region, d1, d2,
     ambiguous flag at τ = 1.10, recall@10 at one-region exact routing.
   - per base vector also: `primary_category` and `top_level_category`
     (the part before the dot, e.g. `cs`, `math`, `physics`) from
     `sample.jsonl.zst`, and `update_year`.
   - project queries into the 2-D space: fit is not re-run; use the saved
     projection for base points only, and for queries set x,y to the mean
     projection of their 10 true nearest neighbours (from ground_truth.npy).
     Document this in the file header as an illustrative placement.
   - project centroids the same way: mean 2-D position of their members.
   - write `fixtures/<id>/ground_view.parquet` with two tables, or two
     files if simpler: `ground_view_base.parquet` (150k rows: x, y,
     region, d1, d2, ratio, copies, top_level_category, primary_category,
     update_year) and `ground_view_queries.parquet` (2k rows: x, y,
     region, ratio, ambiguous, recall10_one_region). Plus
     `ground_view_centroids.parquet` (256 rows: region, x, y, size).
     Use pyarrow (add to requirements.txt, pinned).
   - append their digests to `MANIFEST.sha256` as **declared** (they are
     derived, illustrative, and recomputable). Extend `fixture_verify.py`'s
     kind classification for `ground_view_*.parquet` → declared, with a test.
   - print a summary: rows, copies histogram (1/2/3/4), ambiguous rate,
     mean one-region recall — these must agree with the spec's published
     values (crispness, ambiguity 0.891, drift-style recall ≈ 0.52–0.55)
     within tolerance when run on arxiv-150k; assert this in the script
     and fail loudly if not.
2. Run it on the smoke fixture (all inputs present locally). Report the
   summary and confirm the three parquet files exist and verify as declared.
3. `corpora/run_arxiv_150k.sh`: after the verifier step and before the
   tarball, run the export; add the three parquet files to the tarball.
   Also add `vectors.npy`, `queries.npy`, `sample.jsonl.zst` to a **second**
   tarball `/workspace/arxiv-150k-large.tgz` (the release asset). Test the
   script logic on the smoke fixture as in task 002 A4.
4. `corpora/POD_SETUP.md`: add the build-3 instructions as a short
   section: isolated venv honouring the pins (no `--system-site-packages`),
   `pip install -r requirements.txt`, the version check line, then the run
   script; note that this build records torch and produces both tarballs.

## Acceptance
- Export runs on smoke; parquet files present, declared, verified.
- Assertions against published values are in the script (they will be
  exercised for real on the pod).
- Run script produces both tarballs on the smoke fixture locally.
- `requirements.txt` gains exactly one pinned line (pyarrow).

## Do not
- Change any measurement in `build_fixture.py`. Rebuild arxiv-150k locally.
