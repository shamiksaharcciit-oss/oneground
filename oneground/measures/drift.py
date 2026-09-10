"""Drift: what a partition trained on the past does to queries from the future.

Train the 256 centroids on records from before a cutoff, then measure
one-region recall separately for queries from before and after it. If recall
falls after the cutoff, the partition has gone stale and the corpus needs
re-clustering on some schedule -- which is a real operational cost that a
recall number measured on a static snapshot never shows.

On arXiv it does *not* fall (0.522 before, 0.549 after), which is a finding
rather than a null result: it says the fixture's semantic drift is small
enough that re-clustering is not what makes semantic sharding lose. Crispness
is.

Moved from corpora/build_fixture.py unchanged.
"""

from collections import defaultdict

import numpy as np

from .crispness import centroid_dists


def one_region_exact_recall(base, queries, cents, gt10):
    """Exact search restricted to the query's nearest region.

    This is the routing ceiling at P=1: not what an index achieves, but what
    *any* index could achieve if it only ever looked in one region. It is
    therefore an upper bound on single-region routing, and the gap between it
    and 1.0 is attributable entirely to routing rather than to the index.
    """
    import faiss
    _, base_r = centroid_dists(base, cents, 1)
    _, q_r = centroid_dists(queries, cents, 1)
    members = defaultdict(list)
    for i, r in enumerate(base_r[:, 0]):
        members[int(r)].append(i)
    pred = np.full((len(queries), 10), -1, dtype=np.int64)
    for qi in range(len(queries)):
        ids = np.asarray(members[int(q_r[qi, 0])], dtype=np.int64)
        if len(ids) == 0:
            continue
        sub = faiss.IndexFlatIP(base.shape[1])
        sub.add(base[ids])
        _, loc = sub.search(queries[qi:qi + 1], min(10, len(ids)))
        pred[qi, :len(loc[0])] = ids[loc[0]]
    return recall(pred, gt10)


def recall(pred, gt):
    """Recall@k as a fraction of all (query, true-neighbour) pairs.

    -1 entries in `pred` are padding for queries whose region held fewer than
    k vectors; they count as misses, which is correct -- the search genuinely
    did not return them.
    """
    hits = sum(len(set(p[p >= 0]) & set(g)) for p, g in zip(pred, gt))
    return hits / (gt.shape[0] * gt.shape[1])


def drift_pair(base, queries, base_before_mask, q_before_mask, gt10, seed,
               n_centroids=256, kmeans_fn=None):
    """The drift measurement: centroids from `before`, recall on both halves.

    Split out of `characterize()` so the product path and the fixture path run
    the same code. The call order -- kmeans on the pre-cutoff base, then
    before-queries, then after-queries -- is preserved exactly, because faiss
    k-means consumes the seed and reordering would change the centroids.
    """
    if kmeans_fn is None:
        from .crispness import kmeans as kmeans_fn
    cents_pre = kmeans_fn(base[base_before_mask], n_centroids, seed)
    before = one_region_exact_recall(base, queries[q_before_mask], cents_pre,
                                     gt10[q_before_mask])
    after = one_region_exact_recall(base, queries[~q_before_mask], cents_pre,
                                    gt10[~q_before_mask])
    return {
        "drift_before": before,
        "drift_after": after,
        "drift_n_before": int(q_before_mask.sum()),
        "drift_n_after": int((~q_before_mask).sum()),
    }
