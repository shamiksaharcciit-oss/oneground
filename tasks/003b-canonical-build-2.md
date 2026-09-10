# Task 003b — Canonical build 2: republish, record, reconcile

## Expected repo state
Task 003 committed. `fixtures/arxiv-150k/` contains build 2's small
artifacts (extracted over build 1). `docs/CHARTER.md` present. If the
charter is missing, stop and report.

## Context
Build 1 (task 003) ran with the pod template's numpy 2.1.2 via
`--system-site-packages`. Build 2 ran in an isolated venv honouring every
pin in `requirements.txt` (numpy 2.5.3). Build 2 is canonical. The two
builds are the first cross-environment reproducibility evidence the project
has, and it is recorded as a finding, not discarded.

## Values (build 2, canonical)
    embedding.vectors_sha256:             414e1484d94964df6d5d60e64899347096bf0388f241250cac84184236eb5b4e
    queries.queries_sha256:               87718975fe2cc2513abcc28de138a072c8f2d223e09744862b431305626c1b0b
    ground_truth.ground_truth_sha256:     ecb93315c6650175b6029ea9ccd4058ae6b84bcaa1d2bb332b3370334b1e6c37
    characterization.drift.value_before:  0.524  (n=965)
    characterization.drift.value_after:   0.551  (n=1035)
All other values identical to build 1 at printed precision:
    source 99dc9b05…, sample 404cb92e…, weights c7c1988a…, library 6.0.1,
    LID 32.55, crispness 0.036, ambiguity 0.891, skew 0.075,
    single-node 0.997, semantic-sharded 0.932 / 0.932 / 3.715 / 4 / 4 / 4.
Build 1 values for the finding:
    vectors 90ffb256…, queries f1b7b015…, ground truth ff231cc9…,
    drift 0.523 / 0.549.

## Do
1. `fixtures/arxiv-150k.fixture.yaml`:
   - replace the three digests and two drift values with build 2's.
   - confirm `characterization.json` on disk carries build 2's drift values
     (0.524 / 0.551 at the file's own precision) and the recall/ceiling
     pair; report the exact recall and ceiling values from the file.
   - add a comment on every array `*_sha256` field: `# digest of the raw
     array bytes; MANIFEST.sha256 holds the .npy file digest (with header)`.
   - `changelog`: append `- version: 1, date: 2026-09-08, note: Build 2 in
     the pinned environment (numpy 2.5.3) supersedes build 1 (numpy 2.1.2);
     canonical artifacts are build 2. See findings.`
   - `findings`: append two items, your wording, this meaning:
     (a) Two builds on the same GPU model in different environments
         produced byte-identical sampling receipts (sample.jsonl.zst,
         query_ids.json) but different embedding bytes, and therefore
         different ground-truth and downstream digests; every published
         value agreed to printed precision except the drift pair, which
         moved by ≤ 0.002, inside tolerance. Artifact digests are
         environment-specific; value reproduction within tolerance is the
         cross-environment claim this fixture makes.
     (b) Index loss on build 2: state recall and ceiling from the file, and
         that the difference is negligible, not zero (keep task 003's
         wording; update the numbers if they changed).
   - `build_info` cross-check: confirm `build_info.json` records
     numpy 2.5.3 and torch 2.14.0+cu130, device cuda. Report them.
2. `CLAUDE.md` — replace the line
   `Canonical fixture builds are CPU, single deterministic path. GPU may be used for exploration only, never for a published artifact.`
   with exactly:
   `Canonical fixture builds run in the pinned environment (requirements.txt honoured exactly, isolated venv). The device is recorded in build_info.json and the spec; CPU is preferred, GPU is permitted when recorded. Artifact digests are environment-specific; published values are the cross-environment contract.`
3. `docs/CHARTER.md` — status table: mark 002 B and 003 done, add rows
   `003b | republish build 2, reconcile docs | done`. Under the findings
   paragraph add one sentence: crispness 0.036 / ambiguity 0.891 on arXiv
   with bge-base; semantic-sharded loses on this fixture (0.932 at 3.7×
   vs 0.997 at 1×); two builds agree on values, not bytes. No other edits.
4. `oneground/fixture_verify.py` — add `--strict`: exit 2 if any file is
   couldn't-check (absent). Default stays exit 0 when nothing is
   contradicted. Test both paths.
5. Run the verifier (default and `--strict`) on the local directory; the
   three large artifacts are absent locally, so default → exit 0 with 3
   couldn't-check, `--strict` → exit 2.
6. `requirements.txt` — no change. But report whether `pip freeze` on the
   developer's laptop venv matches the pod's `build_info.json` versions for
   numpy, torch, faiss-cpu, sentence-transformers, umap-learn. Mismatches
   are reported, not fixed.

## Acceptance
- Spec: build 2 digests and drift values; both findings present; array
  digest comment on every array field; changelog appended; nothing else
  changed (diff shows only these).
- CLAUDE.md line replaced verbatim.
- Charter updated as specified.
- Verifier: default exit 0 (5 verified, 3 couldn't-check); `--strict` exit 2.
- Report includes recall/ceiling from characterization.json and the
  build_info versions.
