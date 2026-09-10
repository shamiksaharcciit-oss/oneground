# single_node_hnsw

One HNSW index over the whole corpus. No partition, no routing, no
replication.

## What the family represents

The baseline. Every distributed architecture has to justify its complexity
against this, and on many corpora it wins outright — arxiv-150k included,
where it reaches 0.997 recall@10 at 1x storage while semantic sharding manages
0.932 at 3.7x.

It is also the family that makes "index loss" legible: because nothing is
unreachable, every miss is the index's, and raising `efSearch` is the lever
that recovers it.

## Definition

`faiss.IndexHNSWFlat` with `METRIC_INNER_PRODUCT`, built over L2-normalized
vectors so inner product ranks identically to cosine.

- `efConstruction` is fixed at **200** and not swept, matching the fixture's
  published reference configuration.
- `efSearch` is set after `add`, and re-set on every search, so one built
  index can be measured at several search depths.

## Parameters

| parameter | swept by default | meaning |
|---|---|---|
| `M` | 16, 32 | links per node; graph density and memory |
| `efSearch` | 64, 128, 256 | candidates held during search; the recall/latency dial |
| `efConstruction` | 200, fixed | build-time candidate depth |

The fixture's published configuration is `M=32, efConstruction=200,
efSearch=128`.

## Ceiling

Exact k-NN over the entire corpus. **Routing loss is zero by definition**, not
by measurement: there is no router. Any gap between recall and 1.0 is index
loss.

## Footprint

- `storage_amplification` 1.0 — no replication, ever
- `fanout` 1.0 — one index, one query
- `shards` 1
- `est_memory_bytes` — vector payload plus an HNSW graph term. An estimate.

## Known limits

- Memory is estimated from `n * dim * 4 + n * 2M * 4`, which is the payload
  and link budget, not faiss's real allocation. It ignores the level-0
  overhead distribution and the allocator.
- `efConstruction` is not swept, so build-time/quality trade-offs are
  invisible in this family's rows.
- Single-node by construction: it says nothing about what happens when the
  corpus exceeds one machine, which is the situation the other two families
  exist for.
