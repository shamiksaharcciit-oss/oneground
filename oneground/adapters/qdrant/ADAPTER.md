# Qdrant adapter

Via the official `qdrant-client`, pinned in `requirements.txt` alongside the
server image pinned in `oneground/verify/compose/qdrant.yml`. The two move
together — see "Client and server pins" below.

## What is measured, what is declared

| | source |
|---|---|
| **measured** | ingest wall clock and rate, recall against exact ground truth, per-query client-side latency, time to finish indexing |
| **declared** | engine version, point count, `indexed_vectors_count`, HNSW parameters, distance metric, shard/replica counts, everything in `EngineFacts.raw` |

Everything in the declared column is what Qdrant *said*. `describe()` keeps the
raw response so a later reader can check a claim this adapter did not
anticipate.

## Parameters

`create_namespace(ns, dim, metric, index_params)`:

| key | goes to | notes |
|---|---|---|
| `m` | `hnsw_config.m` | links per node |
| `ef_construct` | `hnsw_config.ef_construct` | build-time candidate depth |
| `full_scan_threshold` | `hnsw_config.full_scan_threshold` | KB; minimum **10**, see quirks |
| `indexing_threshold` | `optimizers_config.indexing_threshold` | KB; **the one that decides whether an index exists at all** |

`search(ns, queries, k, params)`:

| key | goes to |
|---|---|
| `hnsw_ef` or `ef` | `SearchParams.hnsw_ef` |
| `exact` | `SearchParams.exact` |

Metrics: `inner_product` / `dot` / `ip` → `Dot`, `cosine` → `Cosine`,
`l2` / `euclid` → `Euclid`. oneground's vectors are L2-normalized, so Dot and
Cosine rank identically; both are offered because which one the collection is
*created* with changes what the engine stores and reports.

---

## Known quirks, all found while building this

### 1. A small collection is never indexed, and nothing tells you

**This is the one that matters.** Qdrant only builds an HNSW graph for a
segment once that segment exceeds `optimizers_config.indexing_threshold`
kilobytes. The default is **20,000 KB (20 MB)**.

A 5,000 × 64 float32 collection is 1.3 MB. So on the conformance corpus, and
on any small fixture, Qdrant answers **every search with an exact scan** and
recall is 1.0 by construction. Measured during task 009:

```
indexing_threshold=20000 KB -> indexed_vectors_count=0
    ef=4    recall@10 = 1.0000        <- not HNSW being good
    ef=512  recall@10 = 1.0000        <- HNSW never consulted
indexing_threshold=1 KB     -> indexed_vectors_count=5000
```

A conformance suite that did not set this would be green forever while proving
nothing about the index, and a `verify` run would report "Qdrant HNSW recall
1.0" for a linear scan. Both now set `indexing_threshold` explicitly.

### 2. `status: green` does not mean indexed

The obvious signal is wrong. Qdrant reports `status: green` with
`indexed_vectors_count == 0`, because green means "no operations pending", not
"the index is built". Measured:

```
t= 0.0s  status=green  points=5000  indexed=0
t=14.0s  status=green  points=5000  indexed=0
```

The only field that answers the question is **`indexed_vectors_count`**.
`wait_for_index()` polls it and returns `(indexed, points, seconds)`; `verify`
records all three, so a run that measured before indexing finished is visible
in the receipt instead of showing up as suspiciously perfect recall.

### 3. `full_scan_threshold` has a minimum of 10

`hnsw_config.full_scan_threshold: 1` is rejected with HTTP 422:

```
Validation error in JSON body:
  [hnsw_config.full_scan_threshold: value 1 invalid, must be 10 or larger]
```

It is also **not** the knob you want — see quirk 1. It is a different
threshold, in KB, and setting it does not cause a graph to be built.

### 4. Ingest rate is measured with `wait=True`, deliberately

Every batch is upserted with `wait=True`. This costs throughput and it is the
point: with `wait=False` the call returns before the write is durable, and the
measured "ingest rate" would be the rate of *accepting* vectors rather than of
storing them — a number that flatters the engine and cannot be compared to
anything.

Measured on the smoke fixture (2,000 × 768, Docker Desktop on Windows):
**~500 vectors/s durable**. The same run with `wait=False` would report a
much larger number for less work.

### 5. Client and server pins move together

`qdrant-client` refuses to vouch for a server more than one minor version
away and warns at import:

```
UserWarning: Qdrant client version 1.19.0 is incompatible with server
version 1.15.1. Major versions should match and minor version difference
must not exceed 1.
```

A pinned client and a pinned server that the vendor calls incompatible is a
pin that is not doing its job, so the compose image tracks the client. Today:
client **1.19.0**, image **qdrant/qdrant:v1.19.1**.

### 6. The client does not expose the server version

There is no `client.version`. `describe()` reads it from the REST root of the
endpoint the adapter was given, rather than reaching into the client's private
attributes — more stable across client versions, and honest about where the
fact comes from. A version that cannot be read is recorded as `"unknown"`,
never guessed: "recall 0.98 on Qdrant" means nothing without which Qdrant.

### 7. `scroll` returns named vectors as a dict

A collection created with named vectors returns `point.vector` as
`{name: [...]}` rather than a list. The adapter takes the first value, which
is right for single-vector collections and **wrong for multi-vector ones** —
those are not supported, and a multi-vector collection would silently be read
as its first vector. Worth fixing before anyone points this at one.

---

## Index families (task 034)

`simulate` measures four index algorithms — `flat`, `hnsw`, `ivf`, `ivf_pq`.
`index_families()` asks the engine which of them it builds, by creating a
probe collection under the `oneground-` prefix and reading back the
configuration Qdrant returns for it; the index structures in that
configuration are the answer, and the configuration itself is kept in `raw`
so a later reader can check this reading rather than trust it. The probe
collection is deleted in a `finally`, like every other namespace.

**This adapter ships `not_resolved`.** The machine it was written on has no
Docker and no reachable Qdrant, so the question has never been put to a
running engine. Every family is therefore `unresolved`, which `verify`
reports as couldn't-check — not as a capability and not as a refusal.
`oneground adapters coverage --engine qdrant --endpoint <url>` is what
replaces it, and the record it writes names the version that answered.

A quantization block, if the engine returns one, is deliberately **not** read
as an index family: it is a modifier on the HNSW graph rather than a separate
index, and mapping it onto `ivf_pq` would claim a correspondence nobody has
measured.

---

## Not supported

- Multi-vector (named vector) collections — see quirk 7.
- Payload filters. `filtering` in the requirements schema is Phase 3.
- Quantization, on-disk vectors, sparse vectors.
- gRPC. The adapter accepts `prefer_grpc` but nothing in oneground sets it,
  and it is untested.
- Distributed Qdrant. `describe()` reads cluster info when the endpoint
  exposes it, but every measurement in task 009 was single-node.
