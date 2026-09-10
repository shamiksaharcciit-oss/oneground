"""Ambiguous query rate.

The mirror of crispness, asked of the queries instead of the corpus: a query
is ambiguous when its two nearest regions are within 1.10x of each other, so
routing it to one region is close to a coin flip.

On arXiv it is 0.891. That is the number behind the fixture's headline: nine
queries in ten cannot be routed confidently to a single shard.
"""

import numpy as np

AMBIGUOUS_RATIO = 1.10


def ambiguous_query_rate(d_queries):
    """Fraction of queries whose 2nd centroid is within AMBIGUOUS_RATIO of the
    1st. `d_queries` is the (n_q, >=2) distance array from centroid_dists."""
    return float(np.mean(d_queries[:, 1] <= AMBIGUOUS_RATIO * d_queries[:, 0]))
