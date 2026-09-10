# semantic_sharded

k-means regions, epsilon closure, probe the P nearest regions per query.

## What the family represents

The architecture that sounds obviously right. If a corpus has semantic
structure, put semantically similar vectors on the same machine and send each
query only where it belongs — one shard's work instead of N.

On arxiv-150k it loses, and *why* it loses is the fixture's whole point:

| | recall@10 | storage | fan-out |
|---|---|---|---|
| `single_node_hnsw` | 0.997 | 1.0x | 1 |
| `semantic_sharded` (ε=0.2, P=2) | 0.932 | 3.7x | 2 |

The categories separate visibly in the ground view, which is why the idea
looks obviously right. But boundary crispness is 0.036 — 96% of vectors sit
near a region boundary — so the closure copies **84% of the corpus into four
regions**, and the routing still misses. The measured ceiling (0.9324) sits
0.0004 above the measured recall, so essentially *all* the loss is routing:
tuning HNSW cannot save this architecture on this corpus.

## Definition

1. **Regions.** `centroids`-way k-means over the sample, seeded from
   `run.seed`. The fixture reuses the centroids `characterize()` already
   computed, passed through `context["centroids"]`.
2. **Closure.** A vector is assigned to its nearest region, and additionally
   to any of its next `MAX_ASSIGN - 1` nearest regions whose distance is
   within `(1 + ε)` of the nearest:

   ```
   within = d <= d[:, [0]] * (1 + epsilon)
   within[:, 0] = True          # the nearest region always
   ```

   `MAX_ASSIGN = 4`, so a vector is copied into at most four regions.
   `copies.sum() / n` is the storage amplification.
3. **Shards.** One `IndexHNSWFlat` (`METRIC_INNER_PRODUCT`,
   `efConstruction=200`) per non-empty region.
4. **Routing.** A query goes to its `probe` nearest centroids.
5. **Merge.** Each probed shard returns `min(30, ntotal)` candidates; they are
   merged by descending inner product with first-occurrence id dedupe, and the
   top k kept.

Every one of these steps is the fixture builder's, unchanged — task 008
extracted the family from `oneground/fixture/reference.py` and the smoke
fixture rebuilds byte-identically through it.

## Parameters

| parameter | swept by default | meaning |
|---|---|---|
| `centroids` | 256 | number of regions |
| `epsilon` | 0.0, 0.1, 0.2 | closure width; 0.0 means no replication |
| `probe` | 1, 2 | regions searched per query; also the fan-out |
| `M` | 32 | links per node |
| `efSearch` | 96 | per-shard search depth |

The fixture's published configuration is `centroids=256, epsilon=0.2,
probe=2, M=32, efSearch=96`.

## Ceiling

Exact search over the **union of the shards this query probes**. This is the
upper bound on what any index inside those shards could return, so:

- `1 - ceiling` is **routing loss** — the true neighbours live in regions the
  query never asked. No amount of index tuning recovers them.
- `ceiling - recall` is **index loss** — reachable and not returned. A higher
  `efSearch` or a deeper per-shard candidate list might.

This family is the reason the ceiling is mandatory on the interface. Without
it, 0.932 is a single number that says nothing about whether to tune or to
abandon the architecture.

## Footprint

- `storage_amplification` = stored copies / base vectors; 3.715 on
  arxiv-150k at ε=0.2
- `fanout` = `probe`
- `shards` = non-empty regions
- `copies_p50/p95/p99` = the replication distribution. On arxiv-150k these are
  4/4/4: the closure saturates at the cap for most of the corpus, which is
  where the 3.7x comes from.

## Known limits

- **`MAX_ASSIGN` is 4 and is not a parameter.** A vector near five regions is
  copied into four, so amplification saturates at 4.0 and the closure's true
  cost is *understated* on very fuzzy corpora. A corpus whose real closure
  would be 6x reports 4x.
- **Per-shard depth is fixed at 30** candidates before the merge, regardless
  of k or `efSearch`. A query whose ten true neighbours are all in one shard
  beyond rank 30 loses them, and that loss is attributed to the index rather
  than to routing.
- **`efConstruction` is 200 for every shard** and is not swept.
- Small shards get the same HNSW parameters as large ones; `M=32` over a
  200-vector region is mostly wasted structure.
- k-means is seeded but not bit-stable across BLAS implementations. Two
  environments agree on values, not bytes — the same result tasks 003b, 006b
  and 007 measured elsewhere in this project.
