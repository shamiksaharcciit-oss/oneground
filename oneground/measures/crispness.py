"""Boundary crispness, and the k-means geometry every other measure reuses.

Crispness asks: when you cut the space into 256 regions, do the vectors sit
clearly inside one region, or on a boundary between two? The quantity is the
**ratio** of each vector's second-nearest centroid distance to its nearest.

It is the number that decides whether semantic sharding can work at all. On
arXiv with bge-base the fraction above 1.20x is 0.036 -- 96% of vectors sit
near a boundary -- which is why routing to one region loses, and why the
categories being visibly separable in a picture does not make them shardable.

THE DISTRIBUTION IS THE MEASUREMENT; A COUNT IS A READING OF IT (task 044)
--------------------------------------------------------------------------
`boundary_crispness` counts the vectors whose ratio exceeds 1.20. Task 036
measured what that costs under a different embedding:

    bge-base-en-v1.5   count 0.1487   median ratio 1.1035   p95 1.2631
    e5-base-v2         count 0.0063   median ratio 1.0565   p95 1.1475

**Under e5 the 95th percentile is 1.15 and the threshold is 1.20**, so the
threshold sits above almost the entire distribution and the count returns a
near-zero for every corpus regardless of what is in it. Truncation was ruled
out (bge and e5 truncate identically) and protocol was ruled out (both e5
prefixes tested). The ratio is scale-invariant -- a quotient of two distances
-- so this is not a units artifact: e5 genuinely places these vectors more
equidistantly between centroids, and a fixed threshold converts that real
difference into `0.0000`.

The defect was what a user could read from it. Crispness near zero on every
corpus they own supports only one reading as the tool presented it -- *my
corpus has no boundary structure* -- when the true statement is *this
threshold does not fit my embedding's scale*.

So the distribution is what is measured, and the 1.20 count is retained as a
**named reading with its threshold stated beside it**. Every published value
keeps its meaning, because the count is still computed exactly as before and
is also recomputable from the distribution.

**This makes the implementation match the documentation.** The fixture spec's
published definition already said *"exceeds 1.20 x their nearest centroid
distance"*, and the teaser's caption already said *"a second centroid inside
1.20x of the first"*. Both were labelled readings before anyone noticed that
only this module called the threshold a definition.

A threshold derived from the corpus was considered and **refused**: it makes
the measure self-referential, so two corpora measured that way cannot be
compared, which is the property crispness exists to provide.
"""

import numpy as np

# Definitions, not parameters. See the module docstring in measures/__init__.
N_CENTROIDS = 256

#: The threshold of the published reading. **Not a parameter**, and not to be
#: changed: every published fixture value and the teaser's own caption state
#: it, so moving it moves them. What task 044 added is the distribution the
#: reading is a reading *of*, not a different threshold.
CRISP_RATIO = 1.20

#: The quantile grid the distribution is reported on. Declared and fixed, for
#: the same reason the threshold is: a grid that varied by corpus would make
#: two corpora's distributions incomparable, which is the defect the
#: corpus-derived threshold was refused for.
#:
#: Half-percent spacing bounds the error of recomputing a count from the grid
#: at 0.005 -- see `count_from_quantiles`, which is four times inside the
#: +/-0.02 tolerance every published crispness value carries.
RATIO_QUANTILE_STEP = 0.5
RATIO_QUANTILES = tuple(round(q, 1) for q in
                        np.arange(0.0, 100.0 + RATIO_QUANTILE_STEP / 2,
                                  RATIO_QUANTILE_STEP))


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

    **Unchanged by task 044**, deliberately: this is the published reading and
    every fixture value, tolerance and teaser figure depends on it computing
    exactly what it computed before. What 044 added sits beside it.
    """
    return float(np.mean(d_base[:, 1] > CRISP_RATIO * d_base[:, 0]))


# --------------------------------------------------------------------------
# the distribution, and readings of it (task 044)
# --------------------------------------------------------------------------

def ratios(d_base):
    """Each vector's 2nd-nearest centroid distance over its nearest.

    The quantity `boundary_crispness` thresholds. Scale-invariant by
    construction, which is what makes it comparable across embeddings when a
    count at a fixed threshold is not.

    A vector exactly on a centroid has a zero nearest distance; its ratio is
    unbounded rather than undefined, and it is as un-boundary-like as a vector
    can be. Reported as `inf` rather than dropped, so the count of vectors is
    the count of vectors.
    """
    d = np.asarray(d_base)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = d[:, 1] / d[:, 0]
    # 0/0 -- a duplicate of a centroid at zero distance from both. Neither
    # crisp nor on a boundary; recorded as 1.0, the ratio of two equal
    # distances, which is what it is.
    return np.where((d[:, 0] == 0) & (d[:, 1] == 0), 1.0, r)


def ratio_distribution(d_base, quantiles=RATIO_QUANTILES):
    """The measured object: the ratio distribution, on the declared grid.

    Returns the quantiles, the vector count, and the fraction at or below 1.0
    -- which a reader needs because a distribution squeezed against 1.0 is
    exactly what makes a fixed threshold stop discriminating.
    """
    r = np.asarray(ratios(d_base), dtype=np.float64)
    finite = r[np.isfinite(r)]
    qs = (np.percentile(finite, list(quantiles)).tolist() if len(finite)
          else [float("nan")] * len(quantiles))
    return {
        "quantiles": {str(q): float(v) for q, v in zip(quantiles, qs)},
        "quantile_grid": list(quantiles),
        "n": int(len(r)),
        "n_infinite": int(np.count_nonzero(~np.isfinite(r))),
        "min": float(finite.min()) if len(finite) else float("nan"),
        "max": float(finite.max()) if len(finite) else float("nan"),
        "note": ("the ratio of each vector's second-nearest centroid distance "
                 "to its nearest, on a declared fixed quantile grid. This is "
                 "the measurement; a count at a threshold is a reading of it."),
    }


def count_at(d_base, threshold=CRISP_RATIO):
    """The fraction above `threshold`, computed exactly from the ratios.

    `count_at(d, CRISP_RATIO)` is `boundary_crispness(d)`. The generalisation
    exists so a reader can ask what a different threshold would have said
    about the same geometry, without anyone editing a constant.
    """
    return float(np.mean(np.asarray(ratios(d_base)) > float(threshold)))


def count_from_quantiles(distribution, threshold=CRISP_RATIO):
    """The count at `threshold`, recovered from the distribution alone.

    This is what makes the distribution sufficient: the published reading is
    recomputable from it without the vectors. Linear interpolation of the
    quantile grid's inverse, so the error is bounded by the grid spacing --
    `RATIO_QUANTILE_STEP / 100`, which is 0.005.
    """
    grid = [float(q) for q in distribution["quantile_grid"]]
    vals = [float(distribution["quantiles"][str(q)]) for q in grid]
    t = float(threshold)
    if t <= vals[0]:
        return 1.0
    if t >= vals[-1]:
        # Everything at or below the top of the grid; whatever sits above the
        # 100th percentile is nothing, so the count is the infinite tail only.
        return float(distribution.get("n_infinite", 0)) / max(
            distribution.get("n", 1), 1)
    # `vals` is non-decreasing; find where the threshold falls and read off
    # the percentile, then the count is everything above it.
    pct = float(np.interp(t, vals, grid))
    above = (100.0 - pct) / 100.0
    return above


#: Vectors above the threshold, below which the count is not resolvable from
#: zero and must not be read as one. Thirty is the conventional floor for
#: estimating a proportion at all.
#:
#: A QUANTILE RULE WAS TRIED FIRST AND WAS WRONG. The first version of this
#: flagged a reading whose threshold sat above the distribution's 95th
#: percentile. Measured against the published fixtures, that flags
#: `arxiv-150k` (p95 1.1858) and `stackexchange-150k` (p95 1.1501) as not
#: discriminating -- and those two demonstrably do discriminate: they order
#: consistently and reproducibly across five subsample sizes (task 036's
#: instrument check). A criterion that calls a working measurement broken is
#: a worse defect than the one it was written for, so it was replaced rather
#: than tuned.
#:
#: What actually separated the two cases was the **absolute count**. arxiv at
#: 0.0363 of 150,000 is 5,445 vectors; e5 at 0.0007 of 3,000 is two. Both sit
#: in the tail of their distribution; only one is a measurement.
MIN_VECTORS_ABOVE = 30


def threshold_percentile(distribution, threshold=CRISP_RATIO):
    """Where the threshold falls in the distribution, as a percentile.

    Reported always, and never used to judge the corpus. It is the number that
    says whether a *different embedding* would read anything here: a threshold
    at the 99.4th percentile is reading a different part of the distribution
    than one at the 47th, and that is a fact about the pairing of threshold
    and embedding rather than about the data.
    """
    grid = [float(q) for q in distribution["quantile_grid"]]
    vals = [float(distribution["quantiles"][str(q)]) for q in grid]
    t = float(threshold)
    if t <= vals[0]:
        return 0.0
    if t >= vals[-1]:
        return 100.0
    return float(np.interp(t, vals, grid))


def reading(d_base, threshold=CRISP_RATIO, with_distribution=False):
    """The count, with the threshold beside it and where that threshold sits.

    `with_distribution` embeds the quantile grid. A **user's own run stores
    it** -- a fresh workdir has no published bytes to protect, and a user
    whose corpus ships no `ratio` column is exactly the person who needs the
    distribution rather than a count they cannot situate. The published
    fixtures keep deriving it on demand, because their bytes are the thing the
    storage ruling protects and their ground views already carry the ratio.

    Reports three things and judges only one of them:

      `value`                 the count -- the published reading, unchanged
      `threshold`             what it counted above, stated rather than implied
      `threshold_percentile`  where that sits in this corpus's distribution
      `resolvable`            whether enough vectors are above it to be a
                              proportion at all

    `resolvable` is a **couldn't-check on the reading, not on the measure**:
    the distribution was measured fine and it is the count that cannot be
    read. Those are different outcomes and this project does not round one
    into the other.
    """
    dist = ratio_distribution(d_base)
    value = count_at(d_base, threshold)
    n = int(dist["n"])
    n_above = int(round(value * n))
    pct = threshold_percentile(dist, threshold)
    resolvable = n_above >= MIN_VECTORS_ABOVE
    out = {
        "value": value,
        "threshold": float(threshold),
        "of": "the ratio distribution",
        "n": n,
        "n_above": n_above,
        "threshold_percentile": pct,
        "resolvable": resolvable,
        "note": ("a count of the vectors above %.2f, which is the %.2fth "
                 "percentile of this corpus's ratio distribution under this "
                 "embedding. A different embedding places the same threshold "
                 "somewhere else in its distribution, so this count is a "
                 "reading and the distribution is the measurement."
                 % (threshold, pct)),
    }
    if not resolvable:
        out["outcome"] = "couldnt_check"
        out["why"] = (
            "only %d of %d vectors are above %.2f, which is fewer than the %d "
            "needed to read a proportion at all, so this count is not "
            "distinguishable from zero and must not be reported as one. The "
            "threshold sits at the %.2fth percentile of this corpus's "
            "distribution. This is a couldn't-check on the reading: the "
            "distribution was measured and is the number to read."
            % (n_above, n, threshold, MIN_VECTORS_ABOVE, pct))
    if with_distribution:
        out["distribution"] = dist
    return out
