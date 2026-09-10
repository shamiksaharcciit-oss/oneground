# Task 003c — Torch in the receipt, and loose ends

## Expected repo state
Task 003b committed; tree clean.

## Do
1. `corpora/build_fixture.py`: extend the recorded `library_versions` with
   `torch` and add `torch_cuda: torch.version.cuda` (None on CPU) and
   `cuda_device_name: torch.cuda.get_device_name(0)` when cuda is
   available, into `build_info.json`. Keep `build_info.json` declared.
   Rebuild the smoke fixture once (`SKIP_PROJECTION=1`) and confirm the
   new fields appear. Do not touch `fixtures/arxiv-150k/build_info.json` —
   it is a build artifact and is not hand-edited.
2. `fixtures/arxiv-150k.fixture.yaml`: under `embedding`, add
   `torch_version: "2.14.0+cu130"   # developer-reported for build 2; the builder did not record torch until task 003c. A future build (build 3) replaces this with a recorded value.`
   and `cuda_device: "NVIDIA GeForce RTX 4090"   # developer-reported, same caveat`.
   Add to `findings` one line: build 2's torch version is declared by the
   developer, not recorded by the builder; recorded from build 3 onward.
3. `changelog`: relabel the three `version: 1` entries as
   `build: 1-prep`, `build: 1`, `build: 2` (keep dates and notes), and add
   a `changelog` comment: `# 'version' is the fixture schema version;
   'build' is the canonical build number`.
4. `docs/CHARTER.md`: `002b` row → done; add `003c | torch in receipts,
   loose ends | done`; add a roadmap line under Phase 1: `build 3 —
   same pinned environment, records torch; third reproducibility data
   point` (planned, not scheduled).
5. Run the full test suite and the verifier (default). Report results.

## Acceptance
- Smoke `build_info.json` shows `torch`, `torch_cuda`, and (on cpu)
  `cuda_device_name` absent or null — report which.
- arxiv-150k spec diff: the two `embedding` lines, one finding, changelog
  relabel + comment; nothing else.
- Tests pass; verifier default exit 0.

## Do not
- Rebuild arxiv-150k. Edit any measured value. Touch requirements.txt.
