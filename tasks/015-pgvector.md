# Task 015 — pgvector, and the first two-engine comparison

## Setup
Worktree `..\oneground-012` on branch `task-015` from master ≥ `700b367`.
Commit on `task-015`; never touch master. The developer merges.

## Step 1 — carried from 012b
`hash_sharded` and `semantic_sharded` build faiss HNSW per shard through
the same helper `single_node_hnsw` used; make both deterministic by
default the same way, measure the cost on arxiv-smoke and on a 20k
synthetic sample (the size a user's sweep runs at), and prove
byte-identical ids across two builds for each. Rerun the arxiv-150k
reference configs through `simulate` and confirm the published
`semantic_sharded` values still reproduce within tolerance.

## Why
v0.1 promises a second engine. pgvector is the one most RAG teams
already have (it's in their Postgres). The adapter also makes the
matched-environment comparison real: two engines, one pod, one sample,
one load profile — the honest version of "should we switch?".

## Do
2. **`oneground/adapters/pgvector/`** — via `psycopg` (pinned) against
   Postgres 16 + pgvector 0.8.x (pin the image tag after resolving it
   live). `create_namespace` → a table per namespace with a `vector(dim)`
   column and an HNSW index (`m`, `ef_construction`); search via
   `SET hnsw.ef_search`; metric operators for cosine / ip / l2; `describe`
   pulls index params from `pg_indexes` and row count; `scroll` via
   keyset pagination. `ADAPTER.md`: what is measured, what is declared,
   quirks found (expect: index build is synchronous — record build time;
   `ef_search` is a session setting, not an index property — say how the
   receipt records it).
3. **Conformance** — the suite from 009 passes against pgvector in
   Docker (compose file added). Include the `wait_for_index` requirement:
   for pgvector, index existence is not readiness if `maintenance_work_mem`
   forced a partial build — check `pg_stat_progress_create_index` empty
   and the index valid. If a conformance check needs an adapter-specific
   step, add it to the protocol as a required method, not a special case.
4. **Local verify** on arxiv-smoke with `engines: [qdrant, pgvector]`
   sequentially; both rows in `verify.json` with the same
   `environment_id`; report the two recall@10 and two RTT ratios.
5. **Matched-environment pod run** (developer gives one `y`): session
   `verify-arxiv-150k-two-engines.yaml` — same sample, concurrency 32,
   200 qps, 5 min, both engines sequentially on the same pod
   (Qdrant native binary as in 011; Postgres via the official binary
   tarball or an apt install into the pod — no Docker — resolve which
   works and record it). Report per engine: RTT ratio, p95 under load,
   sustained qps, recall, ingest rate, calibration error. Then
   `oneground report` with the full constraint set: the two
   `single_node_hnsw` rows are now *both* verified, in the same
   environment — the same-environment and same-configuration rules
   should let the report compare them and say which meets at lower
   p95, with the decision log naming the pod. Paste the log.
6. **Calibration**: append pgvector's engine line to `history.jsonl`;
   `report` cites both engines' latest lines.
7. Docs: ADAPTERS.md gains pgvector; VERIFY.md gains the two-engine
   procedure and what "matched" guarantees and doesn't (same host, same
   client, sequential not concurrent — the engines never contend).

## Acceptance
- Step 1: both sharded models deterministic; costs reported; arxiv-150k
  reference values reproduce.
- pgvector conformance passes live in Docker; stub in CI.
- Two-engine `verify.json` from one pod; report issues a comparative
  latency verdict between two verified rows, or says why not.
- History has a pgvector line; report cites both.

## Do not
- Rank engines by anything not measured in the same environment.
  Change Qdrant's adapter behaviour. Merge to master.
