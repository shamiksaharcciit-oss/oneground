# Adapters — the seam between simulation and reality

Simulation predicts. Engines are reality. An **adapter** is the one place those
two meet: a small, deliberately boring interface that any vector store can
implement, so that comparing two engines is comparing two adapters rather than
two benchmarking scripts written by two people with two different ideas of
what "recall" means.

**No engine of our own, no favourite, no sponsored defaults.** Nothing in
oneground picks an engine for you, no adapter is privileged over another, and
no engine appears in a default configuration anywhere. An adapter earns its
place by passing the conformance suite — not by being first, not by being
popular, and not by anyone's arrangement with anyone.

Implemented today:

| engine | where | notes |
|---|---|---|
| `stub` | [`oneground/adapters/stub.py`](../oneground/adapters/stub.py) | in-process exact search; what CI runs against |
| `qdrant` | [`oneground/adapters/qdrant/`](../oneground/adapters/qdrant/ADAPTER.md) | official client, pinned |
| `pgvector` | [`oneground/adapters/pgvector/`](../oneground/adapters/pgvector/ADAPTER.md) | Postgres 16 + pgvector 0.8.6 via psycopg 3, pinned |

---

## The protocol

```python
class VectorEngine(Protocol):
    name: str
    version: str                       # what the engine reports; declared

    def connect(self, endpoint, credentials_env=None) -> None
    def create_namespace(self, ns, dim, metric, index_params) -> None
    def upsert(self, ns, ids, vectors, payload=None) -> UpsertStats
    def search(self, ns, queries, k, params) -> Candidates
    def describe(self, ns) -> EngineFacts
    def scroll(self, ns, limit) -> (ids, vectors)
    def delete_namespace(self, ns) -> None
    def namespace_exists(self, ns) -> bool
    def wait_for_index(self, ns, timeout, poll) -> (indexed, points, seconds)
```

`UpsertStats`, `Candidates` and `EngineFacts` are dataclasses in
[`oneground/adapters/base.py`](../oneground/adapters/base.py).

### Measured or declared, per method

The split runs through the whole protocol, and it is why the return types look
the way they do.

| method | measured by oneground | declared by the engine |
|---|---|---|
| `connect` | — | `version` |
| `create_namespace` | — | — |
| `upsert` | wall clock, vectors/second, batch count | `engine_reported_count` |
| `search` | per-query client-side latency; recall, computed against exact ground truth oneground owns | the scores it returns |
| `describe` | — | **all of it**: point count, index type and params, shards, replicas, nodes |
| `scroll` | — | the vectors it hands back |

`EngineFacts.kind` is `"declared"` and its `note` says so in the receipt,
because an engine reporting `hnsw.m = 16` is a claim, not a measurement — a
bug, a silent clamp, or a version difference can make it false. `describe()`
also keeps the engine's raw response, so a later reader can check a claim the
dataclass did not anticipate.

Recall is never declared. It is computed by oneground against exact k-NN
ground truth it computed itself, from the same vectors it ingested.

### Credentials

`connect(endpoint, credentials_env)` takes the **name of an environment
variable**, never a key. A key that can be written in a requirements file is a
key that can be committed, and the requirements file is meant to be checked in.

### Namespaces and cleanup

Every namespace oneground creates is prefixed `oneground-<session-id>-`.
`managed_namespace` refuses anything else:

```python
with managed_namespace(engine, ns, dim, metric, index_params):
    ...        # deleted in a finally, including when this raises
```

Two reasons the prefix is enforced in code rather than by convention: a run can
never write over a collection someone actually uses, and an abandoned run is
identifiable by name afterwards.

---

## The conformance suite is the contribution gate

[`oneground/adapters/conformance.py`](../oneground/adapters/conformance.py).
An engine is not supported because someone wrote an adapter; it is supported
because the adapter passes here.

Seven checks, in the order a real run exercises them:

| | check |
|---|---|
| a | creates a namespace under the `oneground-` prefix |
| b | upserts 5,000 synthetic vectors |
| c | searches 200 queries, **recall@10 ≥ 0.95** against exact ground truth with a generous `ef` |
| d | `describe()` reports the point count and the index params it was given |
| e | `scroll()` returns the same vectors that went in |
| f | `delete()` and the namespace is gone |
| g | the namespace is deleted **even when the body raises** |

Check (g) is proved by injecting a failure, not by reading the code — once
from the caller and once from inside the engine itself, mid-`upsert`, because
those are different code paths and only one of them is obvious.

### Where it runs, and what a pass means

- Against the in-process **stub**, always. No Docker, no network, no account.
- Against a **live engine** only when its URL variable is set —
  `ONEGROUND_QDRANT_URL`, `ONEGROUND_PGVECTOR_URL`. Otherwise those tests
  **skip**, and a skip is reported as a skip.

> **A stub pass is not an engine pass.** The stub is exact, so its recall is
> 1.0 by construction and it can never surface an approximate-index bug. It
> proves the protocol. Only a live engine proves the engine, and the suite
> prints which engines it actually reached.

Nothing here fakes a pass for an engine that was never contacted.

### A trap the suite had to be taught — three times now

Check (c) is worthless if the engine never builds its index, and **every
engine has a way of not building it that looks like success**. All three known
instances produce the same symptom: fast, exact answers and perfect recall,
from a code path that never touches the index.

| # | engine | how the index gets skipped | how you catch it |
|---|---|---|---|
| 1 | Qdrant | a collection below `indexing_threshold` (20 MB default) is answered by an exact scan — recall 1.0000 at `ef=4` | set the threshold; wait for `indexed_vectors_count` |
| 2 | pgvector | the query operator does not match the index's operator class (`<=>` against a `vector_ip_ops` index) | choose operator and opclass together, from one table |
| 3 | pgvector | `ORDER BY` the SELECT alias instead of repeating the distance expression — 25% *faster*, exact answers | `EXPLAIN` shows `Sort`, not `Index Scan` |

The third is the nastiest, because every signal a careless reader checks says
the change was an improvement. Recall goes **up**. Latency goes **down**.
`EXPLAIN` is the only thing that tells them apart.

Expect every engine to have one of these. Find it, document it in
`ADAPTER.md` with the measurement that found it, and make the suite defeat it.

### Two methods that are required *because* they are skippable

`wait_for_index` and `namespace_exists` were optional, duck-typed methods
while Qdrant was the only adapter: the suite probed with `getattr` and skipped
the check when absent. Task 015 promoted both to protocol methods, because
pgvector is unready in a completely different way from Qdrant — an interrupted
`CREATE INDEX` leaving `indisvalid = false`, versus background indexing that
has not caught up — and an adapter that simply omitted the method would have
had its unreadiness silently skipped.

That is exactly the check that must not be skippable. An engine that is
genuinely always ready (the stub) returns `(points, points, 0.0)` and says so
in its `ADAPTER.md`. That is a claim it makes, not a method it omits.

**The general rule, from the brief that forced it:** if a conformance check
needs an adapter-specific step, it becomes a required protocol method, not a
special case in the suite.

---

## Adding an adapter

1. `oneground/adapters/<engine>/adapter.py` implementing the seven methods;
   call `register(NAME, YourAdapter)` at import.
2. `oneground/adapters/<engine>/__init__.py` re-exporting it.
3. Import it from `oneground/adapters/__init__.py` — lazily, inside a
   `try`, so a machine without that engine's client can still run the stub
   suite.
4. `ADAPTER.md` with four sections: **what is measured / what is declared**,
   **parameters** and where each one goes, **known quirks found while
   building**, and **not supported**.
5. Run the suite against a live instance and put the result in your PR. A
   stub-only pass is not a supported engine.

### On "known quirks"

Write them specifically, with the measurement that found them. Qdrant's
`ADAPTER.md` says `status: green` coexists with `indexed_vectors_count == 0`
and shows the fifteen-second poll that proves it. That is the section a second
implementer actually reads, and an empty one means the adapter has not been
understood yet.

---

## What adapters are not for

- **Not for verdicts.** An adapter measures. Whether 12 ms p95 meets someone's
  budget is the report's job.
- **Not for throughput.** `oneground verify` measures latency *shape*:
  sequential, one client, client-side. The field is named
  `latency_shape_single_client` so that nobody can quote it as a rate. Real
  throughput needs concurrency and a machine that is not also running the
  client — task 011, on a pod.
- **Not for the engine's own benchmark numbers.** Nothing an engine publishes
  about itself enters a oneground receipt except through `describe()`, where
  it is labelled declared.
