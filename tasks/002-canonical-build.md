# Task 002 — Canonical arXiv-150k build

Two halves. Part A is yours (local, no credentials, no spend). Part B is
**developer runs** on RunPod; you prepare it and never execute it.

## Expected repo state
Tasks 001 and 001b committed. `oneground/fixture_verify.py` has the `kind`
column; `characterization.json` / `build_info.json` split is in place.
If 001b is not committed, stop and report.

---

## Part A — pre-flight (agent)

### A1. Newline pinning
`corpora/build_fixture.py`: write `MANIFEST.sha256` with `newline="\n"`,
same as `write_json_stable()`. Audit every other text write in the builder
(`sample.jsonl.zst` content, `query_ids.json`) and pin any that is not
already LF. Rebuild the smoke fixture once and confirm every text artifact
contains zero CRLF (`grep -c $'\r'` or a small Python check).

### A2. Projection kind
`oneground/fixture_verify.py`: classify `projection.npy` as `declared`, not
`receipt`. Reason: UMAP is seeded but not guaranteed bit-identical across
BLAS builds, and the spec marks it illustrative. Digest-checked, exempt from
reproduction. Update `test_fixture_verify.py` accordingly.

### A3. Spec corrections (named edits only)
`fixtures/arxiv-150k.fixture.yaml`:
- replace the stale comment `# computed values with estimator versions` on
  the `characterization.json` artifact line with `# measurement only; versions in build_info.json`
- add `build_info.json` line comment `# declared` if not already present
- set `source.snapshot_date: "2026-09-05"` (the Kaggle dump's last-updated
  date, confirmed by the developer). Leave `snapshot_sha256` as TO_BE_FILLED.
Apply the same comment fix to `arxiv-smoke.fixture.yaml`. No other edits.

### A4. Pod run script
Create `corpora/run_arxiv_150k.sh` — the exact command sequence for the pod,
so the developer runs one script. It must:
- `set -euo pipefail`; `cd` to the repo; activate `.venv`; `mkdir -p logs`
- verify the source exists at `/workspace/arxiv-metadata-oai-snapshot.json`
  and print its size and sha256 before starting (this sha256 is the
  `snapshot_sha256` value)
- run `corpora/build_fixture.py --spec fixtures/arxiv-150k.fixture.yaml
  --source /workspace/arxiv-metadata-oai-snapshot.json --out fixtures/`
  with output tee'd to `logs/build-arxiv-150k.log`
- on success, run `oneground/fixture_verify.py arxiv-150k`
- on success, tar the small artifacts to `/workspace/arxiv-150k-small.tgz`:
  MANIFEST.sha256, characterization.json, build_info.json, query_ids.json,
  ground_truth.npy, projection.npy, and the log
- print `DONE` and the path of the tarball as the last line
Test the script's *logic* locally against the smoke spec by parameterising
spec and source via env vars with the arxiv-150k values as defaults
(`SPEC=fixtures/arxiv-smoke.fixture.yaml SOURCE=tasks/scratch/001-synthetic-source.json`).
It must run to DONE on the smoke fixture on this machine (Git Bash or WSL
is fine; note which).

### A5. Pod setup notes
Create `corpora/POD_SETUP.md` with the developer's steps, in order, no
prose beyond what is needed: create the bundle on the laptop
(`git bundle create oneground.bundle --all`), upload it, clone on the pod,
create `.venv`, `pip install -r requirements.txt`, install `kaggle`,
place `~/.kaggle/kaggle.json` with `chmod 600`, download the dataset with
`kaggle datasets download -d Cornell-University/arxiv -p /workspace --unzip`,
then `nohup bash corpora/run_arxiv_150k.sh > logs/run.log 2>&1 &` and
`tail -f logs/run.log`. Include the expected wall-clock (from your 001
extrapolation, ~2–3 h on 16 vCPU) and the memory guard: if free RAM drops
below 2 GB during embedding, the developer should stop and report rather
than let it swap.

### A6. Report Part A
Standard format. Then stop. Do not proceed to Part B.

---

## Part B — the build (developer runs)

The developer follows `corpora/POD_SETUP.md` on a 16 vCPU / 40 GB RunPod
CPU pod with the `vecbench` network volume, then:
- downloads `/workspace/arxiv-150k-small.tgz` into the local repo
- terminates the pod (the volume keeps vectors.npy, queries.npy,
  sample.jsonl.zst for the release asset)
- pastes the `TO_BE_FILLED` block and the last 40 log lines to the
  orchestrator

Task 003 (publish values, flip `status: built`) follows the orchestrator's
review of those numbers.

## Acceptance for Part A
- Smoke rebuild: zero CRLF in any text artifact; verifier 7 verified with
  `projection.npy` absent, and a unit test asserting its `declared` kind.
- `run_arxiv_150k.sh` reaches DONE on the smoke fixture locally.
- `POD_SETUP.md` exists and contains every step above.
- Spec diff for arxiv-150k shows exactly the three named edits.

## Do not
- Run anything against the real dump. It is not on this machine and must
  not be downloaded here.
- Change seeds, tolerances, thresholds, or any measurement logic.
