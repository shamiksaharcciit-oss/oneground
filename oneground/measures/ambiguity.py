"""Ambiguous query rate.

The mirror of crispness, asked of the queries instead of the corpus: a query
is ambiguous when its two nearest regions are within 1.10x of each other, so
routing it to one region is close to a coin flip.

On arXiv it is 0.891. That is the number behind the fixture's headline: nine
queries in ten cannot be routed confidently to a single shard.

THE SAME FAMILY AS CRISPNESS, AND THE FAILURE IS MIRRORED (task 044b)
---------------------------------------------------------------------
Both measures threshold the same quantity -- the ratio of a vector's second
nearest centroid distance to its nearest -- at a fixed constant:

    crispness   d2 >  1.20 x d1     counts the UPPER TAIL
    ambiguity   d2 <= 1.10 x d1     counts EVERYTHING BELOW a fixed point

So a distribution compressed toward 1.0 **empties** the first and **fills**
the second. Task 044 found crispness returning a near-zero for every corpus
under an embedding whose ratios compress; this measure does not collapse under
the same conditions, it **saturates**.

Collapse and saturation are the same defect and only one of them looks like
an absence. **The saturated reading is the more dangerous of the two for a
user**: "my queries are all ambiguous" reads as a finding about their corpus
and invites action, where a crispness of 0.0000 at least invites the question
of whether the number is right.

And this threshold is **nearer its failure than crispness was**. Measured on
the published fixtures' own query ground views, 1.10 already sits at the
89th to 94th percentile of the query ratio distribution on three of the four,
under the anchor model itself -- so most queries are already inside it before
any model changes. Crispness had already failed; this one is closer to failing
and has not yet. That is a finding about the family of measures rather than
about either member.

So, as in 044: **the distribution is the measurement and the rate is a named
reading of it.** `ambiguous_query_rate` is unchanged -- every published value
and the fixture definition prose depend on it computing exactly what it
computed before -- and what is added sits beside it.
"""

import numpy as np

from .crispness import (DISTINGUISHABILITY_SIGMA, distinguishable,
                        ratio_distribution, threshold_percentile)

#: The threshold of the published reading. **Not a parameter.** Every
#: published `ambiguous_query_rate` and the fixture specs' definition prose
#: state it, so moving it moves them. What 044b added is the distribution the
#: reading is a reading *of*.
AMBIGUOUS_RATIO = 1.10


def ambiguous_query_rate(d_queries):
    """Fraction of queries whose 2nd centroid is within AMBIGUOUS_RATIO of the
    1st. `d_queries` is the (n_q, >=2) distance array from centroid_dists.

    **Unchanged by task 044b**, deliberately: this is the published reading.
    """
    return float(np.mean(d_queries[:, 1] <= AMBIGUOUS_RATIO * d_queries[:, 0]))


def rate_at(d_queries, threshold=AMBIGUOUS_RATIO):
    """The rate at any threshold. `rate_at(d, AMBIGUOUS_RATIO)` is the above.

    Exists so a reader can ask what a different threshold would say about the
    same geometry without anyone editing a constant.
    """
    d = np.asarray(d_queries)
    return float(np.mean(d[:, 1] <= float(threshold) * d[:, 0]))


def reading(d_queries, threshold=AMBIGUOUS_RATIO, with_distribution=False):
    """The rate, with its threshold and where that threshold sits.

    The mirror of `crispness.reading`, and the resolvability test is mirrored
    with it: crispness cannot be read when too few vectors are ABOVE its
    threshold, and this cannot be read when too few are OUTSIDE its threshold.
    A rate of 0.999 over 2,000 queries is two queries not ambiguous, which is
    no more a proportion than two queries crisp would be.
    """
    dist = ratio_distribution(d_queries)
    value = rate_at(d_queries, threshold)
    n = int(dist["n"])
    pct = threshold_percentile(dist, threshold)
    # `degenerate=1.0`: this reading saturates where crispness collapses, so
    # the question is distance from one rather than from zero.
    resolvable, n_outside, sigma = distinguishable(value, n, degenerate=1.0)
    out = {
        "value": value,
        "threshold": float(threshold),
        "of": "the query ratio distribution",
        "n": n,
        "n_outside": n_outside,
        "sigma_from_one": sigma,
        "threshold_percentile": pct,
        "resolvable": resolvable,
        "note": ("a rate of the queries at or below %.2f, which is the %.2fth "
                 "percentile of this corpus's query ratio distribution under "
                 "this embedding. A different embedding places the same "
                 "threshold somewhere else in its distribution, so this rate "
                 "is a reading and the distribution is the measurement."
                 % (threshold, pct)),
    }
    if not resolvable:
        out["outcome"] = "couldnt_check"
        out["why"] = (
            "only %d of %d queries fall outside %.2f -- %.2f standard errors "
            "from 1.0, under the %.1f needed -- so this rate is not "
            "distinguishable from 1.0 and must not be reported as a finding "
            "about the corpus. A saturated rate reads as 'every query is "
            "ambiguous', which is a claim about the queries; what it says "
            "here is that the threshold sits at the %.2fth percentile of "
            "their distribution. This is a couldn't-check on the reading: the "
            "distribution was measured and is the number to read."
            % (n_outside, n, threshold, sigma, DISTINGUISHABILITY_SIGMA, pct))
    if with_distribution:
        out["distribution"] = dist
    return out
