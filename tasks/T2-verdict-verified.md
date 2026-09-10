# Task T2 — The verdict, verified

## Expected repo state
Task 011 committed; `runs/arxiv-150k-via-characterize/report.json` holds the
verified decision (1 meets, 6 fails, 1 couldn't-check; recommended
`single_node_hnsw[M=32,efConstruction=200,efSearch=128]`; environment
`tf8sd2usxbblsm`). Teaser at `620d06d`+ on master.

## Do
1. `corpora/export_teaser_data.py --report-only`: regenerates
   `values.json` (and its MANIFEST line) from the named `report.json` and
   `verify.json`, touching nothing else. Assert the untouched files'
   digests are unchanged before and after.
2. Quoted decision-log entries: replace the `to_resolve` requirement with
   a fourth `kind` chosen in this order: the `meets_environment` entry for
   `latency_p95` (the pod-id sentence) if present, else `to_resolve`. The
   export still refuses if fewer than four entries can be quoted.
3. `values.json` gains the verify facts the page will show: pod id, RTT
   baseline p95, p95 under load, achieved vs offered qps, concurrency,
   recall@10 measured, calibration error, ingest rate, Qdrant version.
4. The page:
   - heading is data-driven: `Three options. One recommended.` /
     `Nothing recommended.` from `report.json`.
   - the recommendation block names the configuration, the engine and
     version, the pod id, and the two measured numbers (p95 under load,
     sustained qps) with their sources on hover.
   - the runner-up line carries its outcome: "indistinguishable on recall
     from hash_sharded — couldn't-check on latency and qps: this
     configuration was not the one verified."
   - a new small panel under the verdict, "the number this run existed
     to settle": RTT baseline p95 vs query p95 sequential (97%, noise)
     vs under load (18.3%, attributable), with the one-sentence rule:
     single-client latency is unattributable on loopback; loaded latency
     is not.
   - the calibration line in the footer becomes real: "simulator vs
     Qdrant 1.19.1 on this corpus: −0.0018 recall@10, measured
     2026-09-10, environment tf8sd2usxbblsm".
5. Re-run the bounds check and measurements; commit `T2:` on master.

## Acceptance
- Only `values.json` and its MANIFEST line changed in `site/teaser/data/`.
- Heading reads `One recommended.`; every number in the new panel and the
  footer traces to `values.json` with a source.
- No section overlap at the five viewports; slider still < 100 ms.

## Do not
- Re-derive `base.bin`, `queries.json`, `centroids.json`. Touch the package.
