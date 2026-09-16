# Models — the simulator's contribution unit

A **model** simulates a retrieval architecture on a corpus of embeddings
against exact k-NN ground truth, so an architecture can be scored before any
real engine is stood up.

One directory per family under `oneground/models/`. Adding a family is a
self-contained change — a `model.py`, a `MODEL.md`, and tests — that requires
no edit to the simulator, the CLI, or any other family. That is deliberate:
the proposal loop in Phase 5 turns "I have an idea for a sharding scheme" into
exactly this shape.

Registered today:

| family | routes on | fan-out | replicates |
|---|---|---|---|
| [`single_node_hnsw`](../oneground/models/single_node_hnsw/MODEL.md) | nothing — one index | 1 | no |
| [`semantic_sharded`](../oneground/models/semantic_sharded/MODEL.md) | k-means regions | `probe` | yes, ε closure |
| [`hash_sharded`](../oneground/models/hash_sharded/MODEL.md) | a seeded hash | N | no |

---

## The interface

```python
class Model(Protocol):
    name: str

    def configs(self, space: ConfigSpace) -> Iterable[Config]
    def build(self, vectors, config, seed, context=None,
              deterministic=None) -> BuiltIndex
    def search(self, built, queries, k, config) -> Candidates
    def ceiling(self, built, queries, k) -> Ids
    def footprint(self, built) -> Footprint
```

`Config`, `ConfigSpace`, `Candidates`, `Footprint` and `BuiltIndex` are
dataclasses in [`oneground/models/base.py`](../oneground/models/base.py).

**`configs`** — the family decides its own sweep, because only it knows which
of its parameters interact. `ConfigSpace` carries the seed, the requested
`node_counts`, any per-family `grid` override from the requirements file, and
`include`: configurations that must appear whatever the grid says. The
fixture's two published reference configurations enter a sweep that way.

**`build`** — must be deterministic given `(vectors, config, seed)`. Two
builds must produce the same measurements; the fixture's byte-identical
rebuild depends on it. Use the seed for every random choice, and never
`hash()` (randomized per process unless `PYTHONHASHSEED` is set).

For an HNSW family the seed is not sufficient — see **Build determinism**
below. `single_node_hnsw` takes `deterministic` (default `True`) and adds
single-threaded; a family that builds a faiss graph should do the same.

`context` is an optional escape hatch for work the caller has already done —
the fixture builder passes the k-means centroids `characterize()` computed
rather than making the model recompute a 256-way clustering over 150,000
vectors. **A model must produce the same result with or without it.** It is a
speed and identity concession, not a behaviour switch.

**`search`** — what the architecture actually returns: `(n_queries, k)` ids and
inner-product scores, `-1` and `-inf` padded, no duplicate ids in a row.

**`footprint`** — what it costs, independent of how well it recalls:
`stored_vectors`, `storage_amplification`, `est_memory_bytes` (an estimate,
and labelled as one everywhere it is printed), `fanout`, `shards`, and the
copies distribution.

---

## The ceiling rule

> **A model that cannot state what its routing makes reachable cannot be in
> the table.**

`ceiling` is required, not optional. It returns exact k-NN over everything the
architecture's routing can reach for each query — for a family that reaches
everything, that is exact k-NN over the whole corpus.

Without it, a recall of 0.932 is one number with no decomposition. With it,
the gap from perfect always splits in two:

```
routing_loss = 1 - ceiling@10          the neighbours are in shards that were
                                       never probed. No index tuning recovers
                                       these.

index_loss   = ceiling@10 - recall@10  reachable, and not returned.
                                       efSearch might.
```

This is the difference between "tune it" and "re-architect", which is the
question the whole tool exists to answer. On arxiv-150k, semantic sharding's
ceiling is 0.9324 against a recall of 0.9320: **8 of 20,000 slots are index
loss and the rest is routing**, so no HNSW parameter saves that architecture
on that corpus. A table without ceilings could not have said so.

The conformance test enforces the invariant that makes the number meaningful:
`ceiling >= recall`, always. A model that returns neighbours its own routing
says are unreachable is not describing itself correctly.

For families that reach everything, say so in code and in `MODEL.md`: routing
loss is zero **by definition**, not by measurement.

---

## Adding a family

1. `oneground/models/<name>/model.py` — implement the five methods, export
   `MODEL` and `NAME`.
2. **Declare the family's parameters** in the same file, with
   `declare_parameters(NAME, (Param(...), ...))` from `models/base.py`. Every
   key the family reads needs an entry: its type, its validity bounds, whether
   `configs()` sweeps it from a grid, and its role — `parameter` (the
   architecture), `run` (set per run by the simulator), `build` (how the
   index is built) or `constant` (fixed inside the family, and refused in any
   configuration). A configuration naming an undeclared key is refused, and
   `Config.get` refuses to read one, so a family without a table cannot be
   built. The rule the table enforces: a key is either read, or refused —
   never accepted and ignored.
3. `oneground/models/<name>/__init__.py` — `from .model import MODEL, NAME`.
4. Register it in `oneground/models/__init__.py`'s `REGISTRY`.
5. `oneground/models/<name>/MODEL.md` — the four sections every family has:
   **what the family represents**, **definition** (precise enough to
   reimplement), **parameters** (with what is swept and what is fixed), and
   **known limits**.
6. Tests. The conformance suite picks the family up automatically from the
   registry; add per-family tests for anything the interface cannot check.
   `models/test_parameters.py` records every key the family reads while it
   builds, searches, ceilings and footprints, and fails unless that set is
   exactly the declared non-constant keys.

### On `MODEL.md`'s "known limits"

Write them honestly and specifically. `semantic_sharded`'s cap of four copies
means it *understates* storage cost on very fuzzy corpora; `hash_sharded`'s
recall can drift slightly above the single-node baseline at equal `efSearch`
because N smaller graphs searched to depth 30 can hold more candidates than
one large graph. Both are real, both would otherwise be read as bugs, and both
belong in the document rather than in a reviewer's head.

A family whose limits section is empty has not been thought about.

---

## `efSearch` is not portable across implementations

**Measured, task 012.** On the `glove-100-angular` fixture (1,183,514 vectors,
100 dimensions), `single_node_hnsw` — faiss `IndexHNSWFlat` — was swept at
M=12, efConstruction=500 and compared against the published ANN-Benchmarks
hnswlib curve at *the same nominal parameters*:

| our efSearch | our recall@10 | published hnswlib recall@10 | offset | their efSearch for our recall |
| --- | --- | --- | --- | --- |
| 10 | 0.42897 | 0.36534 | +0.06363 | ~14 (**1.40×**) |
| 20 | 0.55798 | 0.49515 | +0.06283 | ~29 (**1.47×**) |
| 40 | 0.67099 | 0.60777 | +0.06322 | ~63 (**1.58×**) |
| 80 | 0.76108 | 0.70371 | +0.05737 | ~134 (**1.67×**) |
| 120 | 0.80156 | 0.75057 | +0.05099 | ~204 (**1.70×**) |
| 200 | 0.84469 | 0.79998 | +0.04471 | ~355 (**1.78×**) |
| 400 | 0.89038 | 0.85386 | +0.03652 | ~748 (**1.87×**) |

(Measured in task 012 and re-measured in 012b with a deterministic build; the
two runs agree to within 0.00296. The offsets are published in the fixture
spec as `reference_curve.configurations[].implementation_offset`.)

**faiss at efSearch = e reaches the recall hnswlib reached at roughly 1.40e to
1.87e**, and the multiplier grows with e. The difference is not measurement
error and not build noise: the corpus, the metric convention and the recall
accounting were all checked against upstream and all reproduce it exactly
(they are now the blocking checks in `oneground calibrate layers`), and
build-to-build drift is an order of magnitude smaller than the gap. A nominal
`efSearch` simply buys more search in one implementation than in the other.

### What follows from it

- **A simulated recall at a given `efSearch` predicts an engine's recall at
  that `efSearch` only when the engine shares the implementation.** Qdrant
  does not use faiss. Neither does Weaviate, Vespa, or pgvector.
- **Every calibration point must record the `efSearch` it was taken at**, as
  its own field and not only inside a configuration label. `calibrate engine`
  writes `efSearch` on every line for this reason; two points at different
  `efSearch` are not comparable even for the same engine and version.
- **`efSearch` is a knob, not a unit.** When comparing architectures across
  implementations, compare at matched *recall* or matched *measured effort*,
  never at matched `efSearch`. Within one implementation it is fine — which is
  what the simulator's own sweep does, and why the sweep is still meaningful.
- **This is a bound on the simulator's transferability, not a defect in it.**
  Task 011's arXiv calibration point put simulated-minus-measured recall at
  −0.0018 against Qdrant, so the effect need not be large in practice. That is
  one point at one configuration, and `docs/VALIDATION.md` says so.

The comparison that produced this table runs **advisory**, permanently: it
measures a difference between two projects' HNSW implementations, and gating
oneground's release on another project's implementation would be gating on the
wrong thing. The offset is published instead.

---

## Build determinism

`base.py` requires that two builds from the same `(vectors, config, seed)`
produce the same measurements. For an HNSW build the seed is not enough:
faiss adds under OpenMP, and parallel insertion lets two threads link against
different partial graphs, so the graph depends on thread scheduling.

**Measured, task 012:** two `single_node_hnsw` builds from identical inputs on
200,000 vectors differed in **37% of returned ids** at efSearch=10, moving
recall by up to 0.0047.

`single_node_hnsw` therefore adds single-threaded by default
(`deterministic=True`, via `single_threaded_faiss`). Two builds now return
byte-identical ids. The measured cost and the sizes it was measured at are in
`tasks/012b-calibration-followup.report.md`; `deterministic=False` is
available for sweeps where a rebuild is not needed, and any receipt produced
that way should say so.

`hash_sharded` and `semantic_sharded` build `IndexHNSWFlat` per shard and have
**not** been converted. They take the same helper when someone does.

---

## What models do not do

- **No verdicts.** A model reports what it measured. Whether a configuration
  meets someone's latency budget is the report's job, and `oneground simulate`
  deliberately emits no ranking by goodness.
- **No defaults and no favourites.** No family is preferred, and none is
  selected for the user. `simulate.families` in the requirements file decides
  what runs.
- **No engine of our own.** These are simulators over faiss primitives, used
  to compare *architectures*. Comparing real engines is the verification
  runner's job, behind the `VectorEngine` adapter protocol.
