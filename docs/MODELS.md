# Models — the simulator's contribution unit

> **Two different things are called a model in this field, and this page is
> only one of them.** Here a *model* is an **architecture family** — a way of
> arranging vectors across shards and deciding which shards a query reaches.
> It is not the **embedding model** that turned text into those vectors. The
> two are independent: any family runs over any embedding, and the embedding
> is chosen before any family sees it.
>
> For the embedding model, and for what can and cannot be compared when it
> changes, see **[EMBEDDINGS.md](EMBEDDINGS.md)**. For writing a family, see
> [FAMILIES.md](FAMILIES.md).
>
> The collision is in the field's vocabulary, not only in this repository, and
> renaming either one here would make this project's documents disagree with
> everything a reader has already read. So both keep their names and every
> page that says "model" says which it means in its first sentence.

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
and labelled as one everywhere it is printed), `fanout`, `shards`, the copies
distribution, and — since task 034 — `index_bytes`, `vector_bytes` and
`overhead_bytes`, which are **measured** rather than estimated. See
**The index algorithm** below.

---

## The rerank stage (task 035)

A production pipeline often retrieves `k x n` approximately, scores those
candidates exactly, and keeps the best `k`. `rerank: none | exact` is a
declared parameter of every family; `none` is the default and does not
re-label, so a configuration written before task 035 is the configuration it
was. `candidates` is a **multiplier of k**, refused when reranking is off.

The exact pass is task 034's `flat` index applied to a candidate set rather
than to the corpus: the same inner product over the same float32 vectors,
restricted to the ids the first retrieval returned.

### Recall splits three ways, and only one of them is recoverable

    routing_loss    1 - ceiling                      never reachable
    candidate_loss  ceiling - candidate_recall       reachable, not retrieved
    ordering_loss   candidate_recall - recall        retrieved, ranked out

The three decompose what the **first retrieval** lost and sum to
`1 - recall_before_rerank`. That is not a detail: after an exact rescore
ordering loss is zero by construction, so a decomposition of the post-rerank
recall would print `ordering_loss: 0` on every reranked row and hide the one
term the stage exists to expose.

**Exact reranking recovers the ordering term and nothing else**, and this is
mechanical rather than empirical. A true top-k neighbour present in the
candidate set is scored by its true score, and the only vectors that can
outrank it have higher true scores — so they are themselves in the true top-k.
The reranked recall is therefore `1 - routing_loss - candidate_loss`, exactly.

**A corpus whose loss is mostly candidate loss cannot be helped by reranking,
however it is tuned.** Only a larger `candidates` reaches that term, and that
is bought with latency.

### Which indexes have any ordering to recover, and why

This follows from what each index returns, not from any corpus:

| index | scores it returns | ordering loss possible |
|---|---|---|
| `flat` | exact, over everything | none — it is already the answer |
| `hnsw` | **true** inner products of the nodes it visited | **none** |
| `ivf` | **true** inner products of the cells it probed | **none** |
| `ivf_pq` | **approximate**, computed from quantised codes | **yes** |

An index that returns true scores for what it found cannot have mis-ordered
what it holds; its loss is entirely in what it did not find, which is
candidate loss. Only a quantised index scores from codes and can rank a
neighbour it already retrieved below one it should not have.

So for three of the four declared algorithms, **reranking buys latency and
nothing else** — and the report prices it in the same row as the recall it
recovers, precisely so that a zero gain appears beside its cost.

### Do not approximate at all, when that is the answer

`flat` over the whole corpus is one of the four algorithms rather than a
separate mode, so every sweep reports it. At 150,000 vectors of 768
dimensions it answers exactly, and a report that treated approximation as the
premise would never have shown that it is sometimes both faster and better
than an approximate index with reranking on top. The sweep says which.

## The index algorithm

Until task 034 every family built HNSW underneath, and `M`, `efConstruction`
and `efSearch` were the only index knobs a user could turn. That was right for
the question the project started from — hold the index constant so a
partition's effect is isolated — and it left out the trade a team actually
argues about, which is memory against recall.

The algorithm is now a declared parameter of every family, with its own knobs
per algorithm. One builder, [`oneground/models/indexes.py`](../oneground/models/indexes.py),
is used by all three families, because an algorithm and its knobs are a
property of faiss rather than of a partition.

| `index` | what it is | knobs | determinism (measured, task 034) |
|---|---|---|---|
| `flat` | exact. Every vector scored. | none | byte-identical with the switch on **or off** — there is no training and no graph, so nothing to diverge |
| `hnsw` | a navigable small-world graph. **The default**, and what every published fixture value was measured under. | `M`, `efConstruction`, `efSearch` | byte-identical **only** with `deterministic=True`; two builds differ otherwise (task 012b, re-confirmed) |
| `ivf` | `nlist` k-means cells, `nprobe` of them searched | `nlist`, `nprobe` | trains a k-means, so it inherits task 029: seeded from the run's seed, trained under `deterministic_faiss`. Byte-identical either way at 2,000 vectors on one machine — which is not a claim about two machines |
| `ivf_pq` | the same, with the residuals product-quantised | `nlist`, `nprobe`, `m`, `nbits` | trains a **second** clustering for the PQ, seeded the same way; same result as `ivf` |

### What they cost, measured

Both published fixtures, 150,000 vectors, 2,000 queries, one operating point
per algorithm. `idx MB` is what faiss reports for the built index, summed over
shards; `over MB` is that minus the vector data it holds.

| corpus | family | index | recall@10 | routing loss | index loss | idx MB | over MB | build s |
|---|---|---|---|---|---|---|---|---|
| arxiv | single_node | flat | 1.0000 | 0.0000 | 0.0000 | 460.8 | 0.0 | 0 |
| arxiv | single_node | hnsw | 0.9968 | 0.0000 | 0.0032 | 501.6 | 40.8 | 210 |
| arxiv | single_node | ivf | 0.8569 | 0.0000 | 0.1431 | 465.2 | 4.4 | 250 |
| arxiv | single_node | ivf_pq | 0.2872 | 0.0000 | 0.7128 | **7.5** | 5.1 | 427 |
| arxiv | semantic | flat | 0.9328 | 0.0672 | 0.0000 | 1711.8 | 0.0 | 13 |
| arxiv | semantic | hnsw | 0.9324 | 0.0672 | 0.0004 | 1863.2 | 151.3 | 322 |
| arxiv | semantic | ivf | 0.7446 | 0.0672 | 0.1882 | 1766.8 | 55.0 | 116 |
| arxiv | semantic | ivf_pq | 0.4324 | 0.0672 | 0.5004 | 265.2 | **256.3** | 630 |
| arxiv | hash | flat | 1.0000 | 0.0000 | 0.0000 | 460.8 | 0.0 | 1 |
| arxiv | hash | hnsw | 0.9984 | 0.0000 | 0.0016 | 501.6 | 40.8 | 135 |
| arxiv | hash | ivf | 0.9397 | 0.0000 | 0.0603 | 464.4 | 3.6 | 62 |
| arxiv | hash | ivf_pq | 0.2461 | 0.0000 | 0.7539 | 8.3 | 5.9 | 360 |
| stackexchange | single_node | flat | 1.0000 | 0.0000 | 0.0000 | 460.8 | 0.0 | 0 |
| stackexchange | single_node | hnsw | 0.9938 | 0.0000 | 0.0062 | 501.6 | 40.8 | 347 |
| stackexchange | single_node | ivf | 0.7587 | 0.0000 | 0.2414 | 465.2 | 4.4 | 275 |
| stackexchange | single_node | ivf_pq | 0.2772 | 0.0000 | 0.7228 | 7.5 | 5.1 | 703 |
| stackexchange | semantic | flat | 0.8692 | 0.1308 | 0.0000 | 1795.9 | 0.0 | 28 |
| stackexchange | semantic | hnsw | 0.8688 | 0.1308 | 0.0004 | 1954.7 | 158.8 | 338 |
| stackexchange | semantic | ivf | 0.6554 | 0.1308 | 0.2138 | 1851.1 | 55.2 | 74 |
| stackexchange | semantic | ivf_pq | 0.3880 | 0.1308 | 0.4812 | 265.9 | 256.5 | 867 |
| stackexchange | hash | flat | 1.0000 | 0.0000 | 0.0000 | 460.8 | 0.0 | 2 |
| stackexchange | hash | hnsw | 0.9966 | 0.0000 | 0.0034 | 501.6 | 40.8 | 459 |
| stackexchange | hash | ivf | 0.8448 | 0.0000 | 0.1552 | 464.4 | 3.6 | 204 |
| stackexchange | hash | ivf_pq | 0.2473 | 0.0000 | 0.7527 | 8.3 | 5.9 | 831 |

**One operating point, not a curve.** Every IVF row is `nprobe=8`, which for
`nlist=1024` is 0.8% of the cells; every IVF-PQ row is `m=16, nbits=8`. These
numbers say what those settings cost on these corpora. They do not say what
IVF-PQ costs, and a reader who reads them as a property of the algorithm will
be wrong about a different `nprobe`.

**And where that point sits on the curve is now measured (task 039).** Swept
over `nprobe` 1–64 on both corpora, the between-corpora IVF gap **rises before
it falls, peaking in mid-range**, and the `nprobe` these rows use sits at or
within 9% of that peak in all three families — exactly at the peak for
single_node, 99.8% of it for semantic. So the 0.0982 single_node IVF gap in
this table (0.8569 against
0.7587) is the **largest** value that gap takes anywhere in the range, not a
typical one. Read on the other scale it points the other way: the ratio of
index losses, which does not compress as both curves approach the ceiling,
**widens monotonically** across the whole range, 1.686 here and 5.833 at
`nprobe=64`. Both belong to any statement about these two corpora diverging —
the difference supports "they converge as more cells are probed", the ratio
supports "they diverge", and neither is reported alone. See
[`tasks/039-nprobe-sweep.report.md`](../tasks/039-nprobe-sweep.report.md).

**The estimate is not the measurement.** `est_memory_bytes` is 460.8 MB for
every single-node row, including the IVF-PQ one that measures 7.5 MB — wrong
by 61×. That is the whole reason `footprint()` stopped being arithmetic.

---

## Quantisation does not survive sharding

**The compression a product quantiser gives you is a property of the
partition it is paired with, not of the algorithm — and nothing in the
algorithm warns you.**

A single IVF-PQ index over arxiv-150k measures **7.5 MB** where the vectors
would cost 460.8 MB: **61× compression**, which is the number anyone would
quote. The same corpus under the same algorithm, cut into the 256 regions the
semantic partition uses, measures **265.2 MB**: **6.5×**.

The codes did not change. Every one of the 557,231 stored vectors is still 16
bytes, and they total 8.9 MB. What changed is that there are now 256
codebooks instead of one, and each shard trains and stores its own:

```
        coarse quantiser    nlist × dim × 4   =  64 × 768 × 4      =  197 KB
        PQ codebook         m × 2^nbits × (dim/m) × 4
                                              =  16 × 256 × 48 × 4 =  786 KB
                                                                  ----------
        per shard                                                    983 KB
        × 256 shards                                              ≈  252 MB

        measured overhead                          256.3 MB
        codes being compressed                       8.9 MB
```

**The codebooks cost 29× more than the codes they compress.** Measured on
stackexchange-150k too: 256.5 MB of overhead against 9.4 MB of codes, within
0.2 MB of arxiv — as expected, because this is arithmetic over the knobs and
not over the data.

The shape of it: per-shard overhead is `nlist × dim × 4 + m × 2^nbits ×
(dim/m) × 4`, which does not shrink as shards get smaller, while the codes in
each shard do. There is a shard size below which quantisation costs memory
rather than saving it, and a team that read "60× smaller" from a single-index
benchmark and then sharded 256 ways will walk into it.

What this does **not** say: that sharding is wrong, that 256 regions is too
many, or that IVF-PQ should not be used with a partition. It says the two
interact, that the interaction is measurable on your own corpus, and that the
number you get from one index is not the number you get from many.

---

Three rules hold across the four:

- **`hnsw` is the default and does not re-label.** Every published label is
  composed entirely of parameters at their declared defaults, so task 032's
  rule of *filling* a missing default would have appended `index=hnsw` to a
  public interface. The direction is declared per key
  (`Param.in_label_at_default`) and a key added after a label was published
  elides at its default instead. `index: hnsw` written out and `index` left
  out are one configuration: one label, one params dict, one set of returned
  ids, one footprint.
- **A knob belongs to an algorithm.** `nprobe` under HNSW is refused rather
  than accepted and ignored, and an unknown algorithm is refused with the
  declared list. This is task 026's rule, for task 026's reason: a key
  accepted and ignored is a run that reports numbers as if it had been
  applied. The same check applies to a sweep grid — `nprobe: [4, 8]` with no
  IVF among the swept `index` values is refused at plan time.
- **Routing loss is a property of the partition, not of the index.** The
  ceiling is exact search over what a query can reach, and what it can reach
  is the partition's business. Four algorithms over one partition return the
  same ceiling ids; if they did not, the decomposition would be attributing
  index loss to routing or the reverse, and that would be a defect rather
  than a finding about an algorithm.

Two size floors are refused with their own message rather than faiss's, which
names neither the configuration nor the shard: `nlist` greater than the number
of vectors in the shard, and `2**nbits` greater than it — the PQ's own
clustering needs at least as many training points as it has centroids, and for
a sharded family the shard is what has to hold them.

**Memory stopped being arithmetic.** With quantisation, `vectors × dimension ×
4` is wrong by an order of magnitude and a formula over faiss's internals
would be a guess. `footprint()` therefore reports what faiss says about the
index it built (`faiss.serialize_index(...).nbytes`, summed over shards), the
vector payload it holds, and the difference. The old estimate stays, keeps its
name `est_memory_bytes`, and keeps being labelled an estimate everywhere it is
printed — the two answer different questions and one of them is now checkable.

**What the simulator can say about an engine.** These are faiss's four
families. No engine offers all of them, and an engine's nearest equivalent is
not the same index: see [ADAPTERS.md](ADAPTERS.md#index-families).

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

### Both scales, or neither (task 039)

> **A gap between two measured numbers is reported on both scales — the
> difference and the ratio — or it is not reported. Each is stated with the
> sentence it supports.**

The ceiling rule exists because one number without its decomposition cannot
tell you whether to tune or re-architect. A gap has the same defect one level
up: **it does not say which direction it points until a scale is chosen, and
the choice is usually invisible.**

Measured. Task 039 swept `nprobe` from 1 to 64 on both published fixtures and
compared the two corpora's IVF loss. On one scale they converge; on the other
they diverge; the rows are the same 84 rows:

| | at `nprobe=8` | at `nprobe=64` | direction | the sentence it supports |
|---|---|---|---|---|
| difference of recall | +0.0982 | +0.0435 | closing | *"the two corpora converge as more cells are probed"* |
| ratio of index loss | 1.686 | 5.833 | widening, monotonically | *"the two corpora diverge as more cells are probed"* |

Both sentences are true of the measurements. Neither is wrong. **This rule
does not decide which is correct** — that depends on the question being asked,
and for these two corpora it is still open. What it forbids is publishing one
of them without the other, because a reader given only the first has been
handed a direction that the same data reverses.

Why a rule and not a habit: the defect is invisible from inside. Task 039's
own prediction was written in differences, stated a threshold in differences,
and recorded neither that a scale had been chosen nor that another existed —
so the prediction could only ever have been settled on the scale that
flattered it. Nothing in the process caught that; the sweep did, by accident.

It is the same defect as an alignment rate quoted without its ceiling: the
number is true, the sentence it licenses is not, and nothing in the artifact
tells a reader which one they are holding.

**Status: executable for claims, written for documents.**

Task 039b measured that `claims.check` could not see a gap at all — a `Cite`
carries a value with a `source` path into a run's artifacts, and a difference
has no such path, so a proposal card's `delta` mutated tenfold, sign-reversed
or silently replaced by a ratio all passed unchanged.

Task 043 built the **derived cite**: a cite carrying an operation and its
operands, which `check()` re-executes rather than believes. Its operands are
ordinary cites checked against their sources, so a derived number is now
checked **down to the artifacts**. The three dishonest mutants fail, each
naming what was recomputed. And the ratio-for-a-difference mutant fails for
the right reason — *the operation was wrong, not the number*: the same value
declared as a ratio is a correct cite, which is exactly the distinction this
rule exists to make.

`oneground/proposals/verdict.py`'s `delta` — the one live instance in code, a
difference judged against a difference threshold — is a derived cite as of
043, so the card's arithmetic is checked.

**Still only written, for hand-authored documents.** Nothing renders this page
from a `Claim`, so the rule binds a human here and a checker in the report.
That gap is the one task 039's own violations fell into, and it is not closed.

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

`hash_sharded` and `semantic_sharded` were converted the same way by **task
015**; both build inside `single_threaded_faiss(det)`. (This paragraph said
they had not been, until task 029 — 015 landed the fix and did not update the
sentence, and two streams then went looking for a defect that was already
fixed.)

### What one thread does not cover: the machine (task 029)

Single threading fixes the order of work *within* a process. It says nothing
about **which kernel does the arithmetic**, and that is decided per machine.

Above `distance_compute_blas_threshold`, faiss hands a distance computation to
the bundled BLAS as a GEMM. OpenBLAS selects its GEMM kernel by
microarchitecture at run time, so the same floats are summed in a different
order on a different CPU. For `semantic_sharded` that lands on the k-means
that decides the regions, and a shifted centroid moves the vectors nearest a
boundary into a different shard.

**Measured, task 029**, twelve k-means over the same 150,000 × 768 at seed
20260908, same `faiss-cpu 1.15.0` and `numpy 2.5.3`, on an Intel laptop with
AVX512 and an AMD EPYC pod without it:

| | result |
|---|---|
| BLAS path, the two machines | centroids differ by 0.00104; 35 of 150,000 vectors change home region; eight published values move in the sixth decimal |
| BLAS path, each machine twice | bitwise identical — each machine reproduces itself |
| **no BLAS, the two machines** | **bitwise identical centroids** |
| `FAISS_OPT_LEVEL` (generic / AVX2 / AVX512) | no effect on either machine, with BLAS on **or** off |

So `deterministic=True` now enters `deterministic_faiss`, which is both
halves: one OpenMP thread, and `distance_compute_blas_threshold` raised so the
arithmetic stays in faiss's own kernels. `deterministic=False` keeps the fast
path, and `simulate_info.json` records which each configuration was built on.

**What it costs, and the cost is not one-signed.** Five runs each, median:

| corpus | machine | BLAS | no BLAS | ratio |
|---|---|---|---|---|
| 20,000 × 768, k=256 | laptop, 4 cores | 1.39 s | 8.45 s | **6.1× slower** |
| 150,000 × 768, k=256 | laptop, 4 cores | 6.82 s | 33.50 s | **4.9× slower** |
| 150,000 × 768, k=256 | pod, 48 threads | 39.46 s | 6.85 s | **5.8× faster** |

**The deterministic path is slower on a few-core machine and faster on a
many-core one.** On four cores BLAS is winning; on forty-eight it loses to its
own threading over a 65,536-point subsample, and faiss's kernels do not. Beside
task 012's HNSW figures — 1.8× slower on 1.18M, faster at 20k — this is the
same shape: determinism here is not a uniform tax, and on the machines that
run canonical builds it is cheaper.

`single_node_hnsw` takes the thread half only. It has no k-means, and task 029
was scoped to the families that do; changing its arithmetic would move its
published values for no reason.

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
