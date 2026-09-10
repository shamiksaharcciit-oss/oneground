"""Region size skew.

What share of the corpus falls into the ten largest of the 256 regions. Even
partitioning would put 10/256 = 3.9% there; more than that means some shards
carry disproportionate load, which is a capacity question rather than a recall
one.
"""

import numpy as np

from .crispness import N_CENTROIDS


def skew_top10_share(region_ids, n_base, n_centroids=N_CENTROIDS):
    """`region_ids` is the nearest-centroid column from centroid_dists."""
    sizes = np.bincount(region_ids, minlength=n_centroids)
    return float(np.sort(sizes)[-10:].sum() / n_base)
