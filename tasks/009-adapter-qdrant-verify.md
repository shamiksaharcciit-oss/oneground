# Task 009 — `VectorEngine`, the Qdrant adapter, and `oneground verify` (local)

## Expected repo state
Task 008 committed; tree clean. Docker Desktop availability on the
developer's machine is unknown — check `docker info`; if absent, list it
under "Blocked on developer" and do everything except the live Docker
steps (the adapter is still fully testable against a stub; the live
conformance run then happens on a pod session in a later task).

## Step 1 — three carried-over fixes (do first, one commit)
- `oneground/README.md`: rewrite to match the root README's
  exists/planned split. Present tense only for characterize and simulate.
- `semantic_sharded`: `shard_depth` becomes a `Config` field, default 30
  (reference rows must not move — rerun the two reference configs on
  smoke and confirm byte-identical `simulate.json` rows). `simulate` sets
  `shard_depth = max(30, k_max)` where `k_max` is the largest k reported,
  and records it in `simulate_info.json`.
- `simulate` ordering: reference configs and explicitly listed configs
  first, generated grid after; truncation reports which were dropped.

## Why
Simulation predicts; engines are reality. This task adds the seam between
them: one adapter protocol every engine implements, the first adapter
(Qdrant), a conformance suite any contributed adapter must pass, and
`oneground verify` in its local form — recall against exact ground truth
and latency *shape* on a single node. Cloud/matched-environment targets
and throughput at concurrency come in task 011 via `oneground pod`.

## Do
2. **`oneground/adapters/base.py`** — the protocol:
       class VectorEngine(Protocol):
           name: str; version: str                          # reported by the engine, recorded declared
           def connect(self, endpoint, credentials_env) -> None
           def create_namespace(self, ns, dim, metric, index_params) -> None
           def upsert(self, ns, ids, vectors, payload=None) -> UpsertStats     # ingest rate
           def search(self, ns, queries, k, params) -> Candidates             # ids, scores, per-query latency
           def describe(self, ns) -> EngineFacts                              # index type/params, point count, node/shard info as reported
           def scroll(self, ns, limit) -> (ids, vectors)                      # for existing_collection mode
           def delete_namespace(self, ns) -> None
   Every method's result carries `kind: declared` for engine-reported
   facts. Namespaces are always prefixed `oneground-<session-id>-` and
   deleted by a `finally` — a test must prove cleanup runs on failure.
3. **`oneground/adapters/qdrant/`** — via the official `qdrant-client`,
   pinned. Support `metric` inner_product/cosine/l2 and HNSW params
   (m, ef_construct, ef search). `describe` pulls collection info and
   cluster info if the endpoint exposes it. `ADAPTER.md`: what is
   measured, what is declared, known quirks found while building.
4. **Conformance suite** `oneground/adapters/conformance.py`: parametrized
   over registered adapters; against any engine it (a) creates a
   namespace with a distinct prefix, (b) upserts 5k synthetic vectors,
   (c) searches 200 queries and checks recall@10 ≥ 0.95 against exact
   ground truth with a generous ef, (d) checks `describe` returns the
   point count and index params it set, (e) scrolls and gets the same
   vectors back, (f) deletes and confirms gone, (g) proves the `finally`
   cleanup by injecting a failure mid-run. Runs against a **stub engine**
   in CI always, and against a live Qdrant when `ONEGROUND_QDRANT_URL`
   is set (skip otherwise, never fake a pass).
5. **`oneground verify` — local target only in this task.**
   `verify.target: local` → `docker compose` file under
   `oneground/verify/compose/qdrant.yml` with the pinned image; `existing`
   → connect to `verify.endpoint`. For the target, on the characterize
   sample: ingest (record rate), run the query set at k=10 and k=100 with
   the chosen engine params, measure recall against the workdir's exact
   ground truth, per-query latency p50/p95/p99 **from the client side,
   sequential, single client** — reported as `latency_shape_single_client`
   and explicitly not as throughput. Baseline: 50 empty-collection pings
   before the run, reported as `rtt_baseline_ms`; if its p95 exceeds 20%
   of the query p95, latency is `couldnt_check: environment noise` while
   recall is still reported.
   Output: `verify.json` (measurement), `verify_info.json` (declared:
   engine facts, image tag, params, host), MANIFEST lines. No verdicts.
6. **`existing_collection` mode** (read-only): `scroll` a stratified
   sample out, hand it to `characterize` as vectors, compute exact ground
   truth over the sample, then `search` the live collection with the
   sample's queries and score recall against that ground truth. The
   receipt states that recall is measured over sampled neighbours.
   Implement; test against the stub; live test only if Docker is present.
7. **Calibration error, first appearance.** After a local verify on the
   smoke fixture (Docker present) or the stub (absent), compute
   `simulated_recall − measured_recall` for the matching
   `single_node_hnsw` config and write it to `verify.json` as
   `calibration_error_recall`. On smoke with a real Qdrant this should be
   within ~0.01; report what it is. This is the number the calibration
   history will track.
8. `docs/ADAPTERS.md`: the protocol, the conformance suite as the
   contribution gate, the receipt/declared boundary per method, and the
   line "no sponsored defaults" in the house voice.

## Acceptance
- Step-1 fixes landed; reference rows byte-identical.
- Stub conformance passes in CI; live conformance passes against Qdrant
  in Docker if available (report which).
- `oneground verify` on smoke produces `verify.json` with recall, latency
  shape, rtt baseline, calibration error; no verdict language.
- Cleanup-on-failure test passes.
- Tests pass; two docs exist.

## Do not
- Add any engine besides Qdrant. Measure throughput or claim it. Change
  model measurements. Touch arxiv-150k artifacts.
