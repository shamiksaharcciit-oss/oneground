"""Reference architecture results for a fixture.

Two architectures run against the fixture's own exact ground truth, so the
published numbers are measurements rather than claims:

    single_node_hnsw   one HNSW index over everything -- the baseline that
                       semantic sharding has to beat
    semantic_sharded   k-means regions with epsilon-closure replication,
                       probing P regions per query

On arxiv-150k the baseline wins (0.997 at 1x storage against 0.932 at 3.7x),
which is the fixture's point: the architecture that sounds obviously right for
a semantically clustered corpus loses on one that is measured.

These live under `fixture/` rather than `models/` because they are the
fixture's reference results, not yet the runnable simulator family. Phase 2's
`models/semantic_sharded/` is where the sweepable version goes.

Moved from corpora/build_fixture.py unchanged.
"""

import numpy as np

from ..measures.drift import recall
from ..models import HASH_SHARDED, SEMANTIC_SHARDED, SINGLE_NODE_HNSW
from ..models.base import Config


def ref_single_node(base, queries, gt10, p):
    """The published single-node reference row, via oneground.models.

    Task 008 replaced the inline faiss calls with the registered family. The
    family was extracted from this function, so the computation is the same
    one; the smoke fixture rebuilds byte-identically through it.
    """
    cfg = Config.make(SINGLE_NODE_HNSW.name, {
        "M": p["M"], "efConstruction": p["efConstruction"],
        "efSearch": p["efSearch"]})
    built = SINGLE_NODE_HNSW.build(base, cfg, seed=0)
    return recall(SINGLE_NODE_HNSW.search(built, queries, 10, cfg).ids, gt10)


def ref_semantic_sharded(base, queries, gt10, cents, p, max_assign=4):
    """The published semantic-sharded reference row, via oneground.models.

    `cents` are the centroids `characterize()` already computed; they are
    handed to the model through `context` rather than recomputed, which is
    both faster and exactly what the published values were measured with.
    """
    cfg = Config.make(SEMANTIC_SHARDED.name, {
        "centroids": len(cents), "epsilon": p["epsilon"], "probe": p["probe"],
        "M": p["M"], "efSearch": p["efSearch"]})
    built = SEMANTIC_SHARDED.build(base, cfg, seed=0,
                                   context={"centroids": cents})
    cand = SEMANTIC_SHARDED.search(built, queries, 10, cfg)
    ceil = SEMANTIC_SHARDED.ceiling(built, queries, 10)
    fp = SEMANTIC_SHARDED.footprint(built)
    return {
        "recall_at_10": recall(cand.ids, gt10),
        "routing_ceiling": recall(ceil, gt10),
        "storage_amplification": fp.amplification,
        "p50_copies": fp.copies_p50,
        "p95_copies": fp.copies_p95,
        "p99_copies_per_vector": fp.copies_p99,
    }
