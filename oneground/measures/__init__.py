"""The five characterization measures, and the geometry they share.

Each measure is a small function over a sample of vectors, moved out of
`corpora/build_fixture.py` in task 007 **with its logic unchanged**. Their
definitions are fixed by the fixture specs and are not tuneable:

    intrinsic_dimensionality   TwoNN (Facco et al. 2017), lid.py
    boundary_crispness         d2 > 1.20 * d1 to the 256 k-means centroids
    ambiguous_query_rate       d2 <= 1.10 * d1, for queries
    skew_top10_share           the ten largest regions' share of the corpus
    drift                      one-region recall before/after a cutoff

The ratios 1.20 and 1.10, and the centroid count 256, are the definitions
themselves rather than parameters to tune: change one and the published
fixture values stop meaning what they say.
"""

from .ambiguity import AMBIGUOUS_RATIO, ambiguous_query_rate
from .crispness import (CRISP_RATIO, DISTINGUISHABILITY_SIGMA, N_CENTROIDS,
                        RATIO_QUANTILES, boundary_crispness, centroid_dists,
                        count_at, count_from_quantiles, kmeans,
                        ratio_distribution, ratios, reading,
                        threshold_percentile)
from .drift import drift_pair, one_region_exact_recall
from .lid import two_nn_lid
from .skew import skew_top10_share

__all__ = [
    "AMBIGUOUS_RATIO", "CRISP_RATIO", "DISTINGUISHABILITY_SIGMA", "N_CENTROIDS",
    "RATIO_QUANTILES",
    "ambiguous_query_rate", "boundary_crispness", "centroid_dists",
    "count_at", "count_from_quantiles",
    "drift_pair", "kmeans", "one_region_exact_recall", "ratio_distribution",
    "ratios", "reading", "skew_top10_share", "threshold_percentile",
    "two_nn_lid",
]

