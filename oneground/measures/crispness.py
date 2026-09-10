"""Boundary crispness, and the k-means geometry every other measure reuses.

Crispness asks: when you cut the space into 256 regions, do the vectors sit
clearly inside one region, or on a boundary between two? A vector is crisp
when its second-nearest centroid is more than 1.20x as far as its nearest.

It is the number that decides whether semantic sharding can work at all. On
arXiv with bge-base it is 0.036 -- 96% of vectors sit near a boundary -- which
is why routing to one region loses, and why the categories being visibly
separable in a picture does not make them shardable.
"""

import numpy as np

# Definitions, not parameters. See the module docstring in measures/__init__.
N_CENTROIDS = 256
CRISP_RATIO = 1.20


def kmeans(x, k, seed, niter=20):
    """faiss k-means. Seeded, so two runs over the same vectors agree."""
    import faiss
    km = faiss.Kmeans(x.shape[1], k, niter=niter, seed=seed, verbose=False)
    km.train(x)
    return km.centroids.reshape(k, x.shape[1]).astype(np.float32)


def centroid_dists(x, cents, top):
    """Distances from each row of `x` to its `top` nearest centroids.

    Returns (distances, region_ids). Distances are Euclidean -- faiss returns
    squared, and the sqrt is taken here so callers compare ratios of actual
    distances, which is what the 1.20 and 1.10 definitions mean.
    """
    import faiss
    ci = faiss.IndexFlatL2(cents.shape[1])
    ci.add(cents)
    d, r = ci.search(x, top)
    return np.sqrt(np.maximum(d, 0)), r


def boundary_crispness(d_base):
    """Fraction of vectors whose 2nd centroid is > CRISP_RATIO x the 1st.

    `d_base` is the (n, >=2) distance array from centroid_dists.
    """
    return float(np.mean(d_base[:, 1] > CRISP_RATIO * d_base[:, 0]))
