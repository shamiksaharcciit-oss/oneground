# Task 003 — Publish arXiv-150k values

## Expected repo state
Task 002b committed; `fixtures/arxiv-150k/` present locally with the small
artifacts extracted from the pod tarball: `MANIFEST.sha256`,
`characterization.json`, `build_info.json`, `query_ids.json`,
`ground_truth.npy`, `projection.npy` (if UMAP completed). If any of the
first five is missing, stop and report.

## Context you need
The canonical build ran on RunPod. Two deviations from the spec as written
are recorded here deliberately; both go into the spec via this task:
1. **Device.** The 32-vCPU CPU pod was host-contended (load average ~130 on
   256 hardware threads; torch at 32 threads but ~18 cores effective),
   projecting ~10 h for embedding. The build moved to an RTX 4090 pod;
   embedding took 6m 11s. `embedding.device` becomes `cuda` with a comment.
2. **Python.** Pod ran Python 3.12.3; `build_info.json` records it.

## Do
1. Read `fixtures/arxiv-150k/characterization.json` and `build_info.json`.
   Confirm every value below matches what the log printed (developer will
   paste the TO_BE_FILLED block into the task file under "Values"). Any
   mismatch → stop and report.
2. Edit `fixtures/arxiv-150k.fixture.yaml` — only these fields:
   - `fixture.status: built`
   - `source.snapshot_sha256`, `sampling.sample_sha256`,
     `embedding.weights_sha256`, `embedding.library_version`,
     `embedding.vectors_sha256`, `queries.queries_sha256`,
     `ground_truth.ground_truth_sha256` — from the values block.
   - `embedding.device: cuda` with comment
     `# canonical build on RTX 4090; CPU pod was host-contended (see task 003 report)`
   - every `characterization.*.value` (and `drift.value_before` /
     `value_after`) and every `reference_results.*` value — from the block,
     at the precision printed. Add `p50_copies` and `p95_copies` lines
     under `semantic_sharded` (they were measured; the spec should list
     what the fixture publishes).
   - `changelog`: append `- version: 1, date: 2026-09-08, note: Canonical
     build completed on RunPod (RTX 4090). Values published. Device changed
     cpu→cuda; see report.`
   Do not touch seeds, tolerances, definitions, or sampling rules.
3. Add a `findings:` block at the end of the spec (new, allowed) with these
   four lines, verbatim in meaning, your wording:
   - boundary crispness 0.036 and ambiguous-query rate 0.891: under
     k-means-256, this embedding space has almost no crisp region
     boundaries; distances concentrate (LID 32.6).
   - semantic-sharded reaches 0.932 only at 3.72× storage with the closure
     cap saturated (p50 copies = 4); single-node HNSW reaches 0.997 at 1×.
     On this fixture the semantic-sharded family loses.
   - drift pair 0.523 / 0.549: no routing penalty for post-2019 queries
     against pre-2019 centroids on this fixture.
   - index loss is zero (recall = routing ceiling); all loss is partitioning.
4. Run `oneground fixture verify arxiv-150k` against the local directory.
   The large artifacts (`vectors.npy`, `queries.npy`, `sample.jsonl.zst`)
   are not present locally; the verifier must report those as
   **couldn't-check — artifact not present**, not contradicted, and report
   the present files as verified. If it fails hard on a missing file, fix
   the verifier so absence is couldn't-check (this is the behaviour a
   contributor without the release asset will see), with a test.
5. Update `docs/CHARTER.md` status table: 002 B done, 003 done; add one
   sentence under findings recording the crispness result. No other edits.
6. Rebuild nothing. This task publishes; it does not recompute.

## Acceptance
- Spec has no remaining `TO_BE_FILLED` except none; `status: built`.
- Verifier: present files verified, absent large files couldn't-check,
  exit 0.
- Diff of the spec touches only the named fields plus `findings` and
  `changelog`.
- Report lists every value written, side by side with the log's value.

## Values
Pasted from logs/build-arxiv-150k.log (canonical build, RTX 4090 pod,
2026-09-08T19:54:41Z → 20:07:08Z).

    source.snapshot_sha256:               99dc9b05b10f5ddf4726e09f57ede4fa25aae6151fe0b93ff4048b9f8d54ef7b
    sampling.sample_sha256:               404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655
    embedding.weights_sha256:             c7c1988aae201f80cf91a5dbbd5866409503b89dcaba877ca6dba7dd0a5167d7
    embedding.library_version:            6.0.1
    embedding.vectors_sha256:             90ffb2567aba9b8e8ab057391687f61cc3c0958f57b17b617809186d2fe1f573
    queries.queries_sha256:               f1b7b0151db515bee5ba1ce7ae54d949b3f1d1b81912848f037285c5327ccfed
    ground_truth.ground_truth_sha256:     ff231cc9a613d688c7ebd508d9cbe71689e98309fa29ed582b887d1cc97021df
    characterization.intrinsic_dimensionality.value: 32.55
    characterization.boundary_crispness.value:       0.036
    characterization.ambiguous_query_rate.value:     0.891
    characterization.skew_top10_share.value:         0.075
    characterization.drift.value_before:             0.523  (n=965)
    characterization.drift.value_after:              0.549  (n=1035)
    reference_results.single_node_hnsw.recall_at_10: 0.997
    reference_results.semantic_sharded.recall_at_10: 0.932
    reference_results.semantic_sharded.routing_ceiling: 0.932
    reference_results.semantic_sharded.storage_amplification: 3.715
    reference_results.semantic_sharded.p50_copies: 4
    reference_results.semantic_sharded.p95_copies: 4
    reference_results.semantic_sharded.p99_copies_per_vector: 4

Also from the log, for the report and build_info cross-check:
    eligible records: 2,761,565 across 19 years
    base 150,000 · queries 2,000 · hot categories 8
    embedding: 6m 11s for 152,000 texts (cuda)
    verifier on the pod: 8 verified, 0 contradicted, 0 couldn't-check
