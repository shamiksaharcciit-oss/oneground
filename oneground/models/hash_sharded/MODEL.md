# hash_sharded

N shards by a seeded hash of the vector id. Every query fans out to all N.

## What the family represents

The honest control, and the reason "just scale out horizontally" has a price
tag in the table instead of a shrug.

A hash partition carries **no semantic information at all**, so it cannot
route: every query must ask every shard. Recall is therefore essentially the
single-node baseline's — nothing is unreachable, only spread out — but the
query work is N times larger.

That makes it the yardstick for semantic sharding. Semantic sharding is worth
its complexity only if it beats hash sharding's recall at a *lower* fan-out,
or matches it at lower cost. On a corpus that clusters cleanly, `probe=1`
beats fan-out N. On arxiv-150k, where 89% of queries are ambiguous, it does
not.

## Definition

```
shard(v) = blake2b(str(id(v)), key=seed) mod N
```

`blake2b` rather than Python's `hash()`: `hash()` is randomized per process
unless `PYTHONHASHSEED` is set, which would make a family documented as
deterministic silently irreproducible between runs.

The id is the vector's row index in the sample unless the caller supplies ids
through `context["ids"]`. There is **no replication** — every vector lives in
exactly one shard.

Each shard gets its own `IndexHNSWFlat` (`METRIC_INNER_PRODUCT`,
`efConstruction=200`). A query searches every shard for
`max(30, k)` candidates, and the results are merged by descending inner
product with first-occurrence id dedupe — the same merge `semantic_sharded`
uses.

## Parameters

| parameter | swept by default | meaning |
|---|---|---|
| `shards` | `simulate.node_counts` (1, 3, 5) | N; also the fan-out |
| `M` | 32 | links per node |
| `efSearch` | 96 | per-shard search depth |

## Ceiling

Exact k-NN over the whole corpus. Every shard is probed, so nothing is
unreachable and **routing loss is zero by definition**. Any gap is index loss,
spread across N graphs.

## Footprint

- `storage_amplification` 1.0 — no replication
- `fanout` **N** — the number this family exists to expose
- `shards` N
- copies are 1 at every percentile

## Known limits

- Shard sizes are even only in expectation. With small N and few vectors they
  can be visibly uneven, and the conformance test only asserts the smallest
  shard is within 40% of the mean.
- Fan-out is N by construction; there is no way to probe fewer shards. That is
  the point of the family, but it means `node_counts` is the only knob that
  trades cost against anything.
- Per-shard depth is `max(30, k)`. A query whose true neighbours are all in one
  shard beyond that rank loses them, and the loss is attributed to the index.
- Recall can drift slightly *above* single-node at the same `efSearch`,
  because N smaller graphs each searched to depth 30 can collectively hold more
  candidates than one large graph searched to `efSearch`. That is a real
  effect of the architecture, not an error, but it makes "hash ≈ baseline" an
  approximation rather than an identity.
