# pgvector

Postgres with the `vector` extension, via `psycopg` 3. The second adapter in
the project, and the first written against a protocol that already existed.

**Pinned:** `pgvector/pgvector:0.8.6-pg16`
(`sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b`),
Postgres 16.15, pgvector 0.8.6, client `psycopg==3.3.5`. Compose file:
[`oneground/verify/compose/pgvector.yml`](../../verify/compose/pgvector.yml).

Why this engine is worth an adapter: most teams running RAG already have a
Postgres, so "should we add a vector database?" is a real question with a real
alternative, and this is the alternative. It is also the adapter that made the
protocol honest — see *What this adapter changed in the protocol*.

---

## What is measured and what is declared

| | |
|---|---|
| **measured** | ingest seconds and rate, index build seconds, per-query client-side latency, recall against exact ground truth |
| **declared** | pgvector extension version, Postgres version, `m` and `ef_construction` read back from `pg_indexes`, row count, index size, index validity |

`describe()` returns `kind: "declared"` and keeps the raw catalog rows under
`raw` so a later reader can check a claim this file did not anticipate.

Two facts in `describe().raw` are **oneground's, not the engine's**, and are
labelled so:

- `requested_params` — what oneground asked for. Distinct from
  `index_params`, which is parsed out of the catalog's `indexdef`, i.e. what
  Postgres says it actually built. Task 011 made that distinction
  load-bearing: a measurement settles a verdict only for the configuration
  the engine reports building.
- `index_build_seconds` — timed by oneground around `CREATE INDEX`.

---

## Quirks found, and what they cost

### 1. Index build is synchronous, and it is a separate cost from ingest

`CREATE INDEX ... USING hnsw` does not return until the graph is built.
Qdrant, by contrast, indexes in the background: its `upsert` returns and
`wait_for_index` polls `indexed_vectors_count` until it catches up.

So **"ingest rate" is not the same quantity in the two engines** unless the
index build is counted, and this adapter refuses to blur them:

- rows are inserted first, then the index is built — which is what pgvector's
  own documentation recommends and what any real deployment does;
- `UpsertStats.seconds` covers the inserts only;
- `index_build_seconds` is reported separately in `describe().raw`.

A reader comparing ingest rates between the two engines has to add pgvector's
index build to get a comparable number, and the receipt gives them both halves
to do it with.

### 2. `ef_search` is a session setting, not an index property

In Qdrant the search parameter travels with the query. In pgvector it is a
GUC: `hnsw.ef_search`, scoped to a session or a transaction. Consequences:

- **It cannot appear in `describe()`.** Nothing in `pg_indexes` or `pg_index`
  knows about it. The receipt records the value oneground *used*, under
  `search_params` in `verify.json`, and never as an index property. A
  `describe()` that reported it would be inventing a fact.
- **It is set once per `search()` call, not per query.** The obvious
  alternative — `SET LOCAL` inside a transaction per query — keeps the setting
  scoped to a single statement, but puts an extra round trip inside every
  timed query. **Measured on the 5,000-vector conformance corpus: p50 latency
  19.49 ms with `SET LOCAL` per query, 11.25 ms with one `SET` per call.**
  That 8 ms is the adapter's own overhead, and reporting it as pgvector's
  latency would have made the engine look slower by an amount oneground
  invented. The connection belongs to the adapter, so a session-level `SET`
  cannot reach anyone else; a `RESET` in a `finally` keeps it from reaching
  oneground's own next call with a different `ef`.

### 3. The operator must match the operator class, or the index is skipped

`<#>` is negative inner product, `<=>` cosine distance, `<->` L2. An index
built with `vector_ip_ops` **cannot** serve a `<=>` query. Postgres does not
error: it falls back to a sequential scan, returns exact answers, and is fast
enough on small data to look fine.

That failure mode is indistinguishable from a good index by recall alone —
recall would be a perfect 1.0 — which is the same trap Qdrant's
`indexing_threshold` set in task 009. `_metric()` therefore picks the operator
class and the query operator together, from one table, so they cannot drift
apart.

Verified rather than assumed: `EXPLAIN (ANALYZE)` on the conformance corpus
reports `Index Scan using "..._hnsw"`, not `Seq Scan`.

### 3b. `ORDER BY` must repeat the expression, and the obvious fix is a trap

The query sends the vector **twice** — once in the `SELECT` for the distance
and once in the `ORDER BY`. At 768 dimensions that is roughly 9 KB of text
literal, sent twice per query, and it is the single largest avoidable-looking
cost in this adapter.

The obvious fix is to order by the output alias:

```sql
SELECT id, embedding <#> $1::vector AS d FROM t ORDER BY d LIMIT $2
```

**It is faster and it is wrong.** Measured on arxiv-smoke (2,000 × 768):

| form | p50 | p95 | plan |
|---|---|---|---|
| expression repeated | 91.20 ms | 360.46 ms | `Index Scan using ..._hnsw` |
| `ORDER BY d` (alias) | 69.69 ms | 120.49 ms | **`Sort`** |

Ordering by the alias makes Postgres materialise every row, sort it, and take
the top k. On 2,000 rows that is faster than walking an HNSW graph and the
answers are *exact*, so recall goes **up**. Every signal a careless reader
would check says the change was an improvement. It has simply stopped
measuring the index.

This is the third form of the same trap in this project: Qdrant's
`indexing_threshold` (task 009), the operator/opclass mismatch above, and this.
All three produce fast, exact, perfect-recall answers from a code path that
never touches the index. `EXPLAIN` is the only thing that tells them apart,
which is why it is in the conformance evidence rather than in someone's
memory.

### 4. Scores are distances; the adapter converts them back

The protocol carries inner-product-like scores where larger is better. `<#>`
returns the *negative* inner product, so the adapter negates it. Cosine
distance becomes `1 - d`. Both conversions are exact and the operator used is
kept in `describe().raw`.

### 5. `mogrify` does not exist in psycopg 3

The obvious way to build a multi-row `INSERT` — client-side rendering with
`cursor.mogrify` — is a psycopg 2 API. Ingest instead sends one
`INSERT ... SELECT * FROM unnest(%s::bigint[], %s::vector[]) ON CONFLICT ...`
per batch: one statement and one round trip per 512 rows.

`COPY` would be faster and is what a bulk loader would use, but the protocol's
method is an **upsert** — re-ingesting the same ids has to work — and `COPY`
cannot express `ON CONFLICT`. That choice costs throughput, and it is written
down here so the measured rate is not read as pgvector's ceiling.

**Measured effect of getting this wrong:** a first implementation that fell
back to one statement per row ingested at 535 vectors/s; the batched form does
1,942 vectors/s on the same corpus and machine.

### 6. Vectors are written as text literals with `repr`

pgvector's text input format is `[1,2,3]`. The adapter formats float32 with
`repr` rather than a fixed precision: `%.6f` would quietly change the vectors
on the way in, and `scroll()` would then disagree with what was upserted for a
reason nobody would find.

### 7. `scroll()` uses keyset pagination

`ORDER BY id` with a `WHERE id > last` cursor, not `OFFSET`. `OFFSET` makes
Postgres walk and discard everything it skips, so a scroll over a large table
degrades quadratically.

### 8. The host port is 55432, not 5432

A developer machine very often already has a Postgres on the default port —
this one did. Binding over it would either fail or, worse, point a run at the
wrong database.

---

## What this adapter changed in the protocol

`wait_for_index` and `namespace_exists` were **optional, duck-typed methods**
while Qdrant was the only adapter: the conformance suite probed for them with
`getattr` and skipped the check when absent. Task 015 promoted both to
required protocol methods, because pgvector is unready in a completely
different way:

| engine | how it is not ready | how you find out |
|---|---|---|
| Qdrant | background indexing has not caught up | `indexed_vectors_count < points_count`; `status: green` does **not** mean indexed |
| pgvector | an interrupted build left the index `indisvalid = false`, or a build is still running | `pg_index.indisvalid`/`indisready`; `pg_stat_progress_create_index` non-empty |

Both produce the same symptom — recall that looks perfect because the index
was never consulted — and an adapter that simply did not implement the method
would have had its unreadiness silently skipped. That is precisely the check
that must not be skippable, so it is now a method every adapter has to answer.

An engine that is genuinely always ready (the stub) returns
`(points, points, 0.0)` and says so. That is a claim it makes, not a method it
omits.

`wait_for_index` here checks **both** conditions the brief names: no build in
progress for this table, and an index row that is valid and ready. Anything
else returns `indexed = 0`, and the conformance suite refuses to measure.

---

## Conformance

Passes all seven checks live against `pgvector/pgvector:0.8.6-pg16`:

```
(a) created oneground-conf-b7379693-conformance
(b) upserted 5000 at 1,942/s
    indexed 5000/5000 in 0.0s
(c) recall@10 1.0000 >= 0.95
(d) describe: 5000 points, dim 64, index hnsw
    {'m': 16, 'ef_construction': 200, 'opclass': 'vector_ip_ops'}
(e) scrolled 100 vectors, all match
(f) namespace deleted
(g) namespace deleted after an exception
```

Run it:

```sh
docker compose -f oneground/verify/compose/pgvector.yml up -d
ONEGROUND_PGVECTOR_URL=postgresql://oneground:oneground@localhost:55432/oneground \
  pytest oneground/adapters/conformance.py -q
```

Recall is 1.0000 because 5,000 vectors at `ef_search=512` is an easy problem,
not because the index was skipped — `EXPLAIN` confirms an `Index Scan`. A
stub-only pass proves the protocol; only a live engine proves the engine.

---

## Index families (task 034)

`simulate` measures four index algorithms — `flat`, `hnsw`, `ivf`, `ivf_pq`.
Postgres answers which of them this server can build exactly, so
`index_families()` asks it rather than reading release notes:

```sql
SELECT amname FROM pg_am WHERE amtype = 'i';
```

The rows it returns are kept in `raw`. `hnsw` maps onto the family of the
same name. `ivfflat` maps onto `ivf` and is recorded **approximate**, with
what differs stated: the two clusterings are trained by different code from
different samples, the parameters are named and scoped differently (a build
reloption `lists` against faiss's `nlist`; a session GUC `ivfflat.probes`
against an attribute on the index object), and oneground has not measured
that the two return the same candidate set for any corpus. A recall figure
simulated on faiss's IVF is not a prediction of this one, and the declaration
says so rather than implying a correspondence.

`flat` is deliberately **not** claimed. An unindexed pgvector table is scanned
exhaustively, which is exact — but that is the absence of an index rather than
an index family, and `pg_am`, which is what was asked, does not list it.

**This adapter ships `not_resolved`.** The machine it was written on has no
Docker and no reachable Postgres, so the query has never been run against a
server. `oneground adapters coverage --engine pgvector --endpoint
postgresql://...` is what replaces it, and the record names the pgvector
version that answered.

---

## Known limits

- **One table per namespace, one database.** No sharding or replication of
  its own, so `describe()` reports `shards=1, replicas=1, nodes=1` — known
  values, not unknown ones. Postgres read replicas exist and are not modelled.
- **Ingest is not tuned.** No `COPY`, no unlogged tables, no
  `synchronous_commit=off`. All three would raise the number and none is what
  a durable deployment does.
- **`maintenance_work_mem` is set in the compose file** (512 MB) because
  pgvector spills the HNSW build to disk when it is too small, which makes
  build time depend on a setting nobody recorded. A user pointing oneground at
  their own Postgres inherits their own value, and the receipt records the
  build time it actually saw.
- **No filtered search.** pgvector's strongest argument against a dedicated
  vector store is that a `WHERE` clause is just SQL. oneground does not
  measure filtered search yet for any engine, so this adapter does not either
  — and the comparison it enables is therefore narrower than the real choice
  a team faces.
