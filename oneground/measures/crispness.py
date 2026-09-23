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


#: How many standard errors a rate must sit from its degenerate value to be
#: read as a proportion at all.
#:
#: TWO CRITERIA WERE TRIED BEFORE THIS AND BOTH WERE WRONG IN THE SAME WAY:
#: they called a working measurement broken, which is a worse defect than the
#: one they were written for. Both were caught by measurement rather than by
#: review, and both are recorded so neither is re-proposed.
#:
#: **A quantile rule** (task 044): flag a reading whose threshold sits above
#: the distribution's 95th percentile. That flags `arxiv-150k` (p95 1.1858)
#: and `stackexchange-150k` (p95 1.1501) as non-discriminating under the
#: anchor model itself -- two corpora that order consistently and reproducibly
#: across five subsample sizes (task 036's instrument check).
#:
#: **An absolute-count rule** (`n >= 30`, task 044): that flags
#: `arxiv-smoke`'s published ambiguity of 0.935, where 13 of 200 queries fall
#: outside the threshold. Thirteen is a small count and 0.935 over 200 has a
#: standard error of 0.017, which puts it 3.7 sigma from 1.0 -- a measurement.
#: The rule conflated a small SAMPLE with a saturated MEASURE. Found by 044b's
#: tests, against a fixture 044 had already passed.
#:
#: What both were reaching for is whether the rate is distinguishable from the
#: value it degenerates to -- zero for a tail count, one for a saturating one
#: -- and that is a standard error, not a count and not a quantile. It gets
#: all four known cases right: arxiv crispness 75 sigma, arxiv-smoke ambiguity
#: 3.7 sigma, task 036's e5 crispness 1.45 sigma, a saturated 0.999 over 2,000
#: at 1.41 sigma.
DISTINGUISHABILITY_SIGMA = 3.0

#: Below this many on the informative side, no standard error means anything
#: and the answer is couldn't-check regardless of arithmetic.
MIN_INFORMATIVE_COUNT = 5


def distinguishable(value, n, degenerate=0.0):
    """Is a proportion readable, or is it its own degenerate value?

    `degenerate` is what the reading collapses to when its threshold leaves
    the distribution: 0.0 for a count of a tail (crispness), 1.0 for a rate
    that saturates (ambiguity). Returns `(resolvable, n_informative, sigma)`.
    """
    n = int(n)
    p = float(value)
    distance = p if degenerate == 0.0 else (1.0 - p)
    n_informative = int(round(distance * n))
    if n <= 0 or n_informative < MIN_INFORMATIVE_COUNT:
        return False, n_informative, 0.0
    se = float(np.sqrt(max(p * (1.0 - p), 1e-12) / n))
    sigma = distance / se if se > 0 else 0.0
    return bool(sigma >= DISTINGUISHABILITY_SIGMA), n_informative, sigma


#: Where 1.20 sits in each published fixture's own base ratio distribution.
#: Derived from the published `ground_view_base.parquet` files, recorded here
#: with its provenance, and re-checked against them by a test.
#:
#: This is the reference a single corpus is weighed against, and it exists
#: because **no single-corpus quantity can separate a working reading deep in
#: a tail from a broken one** (task 044b). `arxiv-150k`'s published crispness
#: sits at the 96.37th percentile and works; e5's ambiguity sits at the 97.74th
#: and has stopped transferring. Both are statistically sound and both are deep
#: in a tail. What differs is whether the reading discriminates BETWEEN
#: corpora, which is not a property of one corpus -- so the only thing a single
#: reading can be compared against is where the same threshold falls on corpora
#: whose values are frozen.
#: **Smoke fixtures are excluded, deliberately.** `arxiv-smoke` puts this
#: threshold at the 47.17th percentile, and including it widened the band to
#: 47.2-98.8 -- a range spanning half the distribution, which barely
#: discriminates anything. A 2,000-vector smoke fixture exists to check that a
#: command runs, not to calibrate a measure, and a band computed over both
#: kinds is dominated by the looser one. So the reference is the full fixtures
#: only, and this comment is where that choice is recorded rather than
#: inferred from an absence.
#: **Stored at the precision they were measured (task 044d), not rounded.**
#:
#: THE ENDPOINT RULE, which nobody stated and nobody designed for
#: ---------------------------------------------------------------
#: `against_published` weighs a corpus against the range these values span,
#: and the values spanning it ARE published corpora. So a fixture in this
#: table is calibrated ground by construction and can never legitimately read
#: outside. Whether it does is decided entirely by which way its stored
#: literal was rounded:
#:
#:     an endpoint is safe IF AND ONLY IF the low edge rounds DOWN
#:     and the high edge rounds UP -- outward, away from the band's interior.
#:
#: Two tables, two edges each: **four independent coin flips, and not a
#: property anyone chose.** Crispness won both of its. Ambiguity lost both --
#: `sec-filings-10k` measured 65.436356 and was stored as `65.44` (up, so
#: above the low edge) and `stackexchange-150k` measured 90.871567 and was
#: stored as `90.87` (down, so below the high edge), and each told a user that
#: the measure had never been calibrated on the corpus that calibrated it.
#:
#: The interior fixture cannot fail however it rounds, which is why only the
#: two edges of each table are at risk and why the luck ran at two-for-four
#: rather than one-in-six. A defect that survives by the direction of a
#: rounding is not fixed, it is lucky.
#:
#: Storing at measured precision removes the flip rather than compensating for
#: it. `test_the_stored_edges_are_the_measured_extremes` asserts the rule
#: directly -- as an ordering between the stored edges and the measured
#: extremes -- so a future rounding in the wrong direction is caught at the
#: constant rather than at whichever consequence someone happens to test.
#:
#: Derived from the published `ground_view_*.parquet`, which is also what that
#: test recomputes them from -- not from a fresh k-means, which lands a few
#: ten-thousandths away and would reintroduce the same disagreement by another
#: route.
PUBLISHED_CRISP_PERCENTILES = {
    "arxiv-150k": 96.373005,
    "sec-filings-10k": 89.253265,
    "stackexchange-150k": 98.829571,
}

#: How far outside the stored band a reading may sit and still count as inside.
#:
#: **Not a tolerance on the comparison, and not tunable.** It absorbs two
#: bounded things and nothing else: the half-unit of the stored decimals
#: (5e-7 at six places) and the last-bit differences between numpy versions
#: recomputing the same percentile. It is 500,000 times finer than the 0.5
#: percentile-point grid the distribution is reported on, so it cannot absorb
#: a disagreement anyone could measure.
#:
#: Widening this is the move task 044d exists to forbid: the band was never
#: too tight, the literals were too short.
EDGE_EPSILON = 1e-6

#: What the comparison assumes, and it is not nothing.
#:
#: These percentiles were measured at the published settings: 150,000 vectors
#: and `N_CENTROIDS` regions. Both halves of that have now been measured, and
#: this comment said otherwise until task 044d.
#:
#: **Sample size: measured by 044b**, which set `MIN_N_FOR_TRANSFER` from the
#: drift table three declarations below. The comparison is simply not made
#: below that floor, so this is discharged rather than assumed.
#:
#: **Centroid count: measured by 044c.** `characterize` always uses
#: `N_CENTROIDS`, so the counts match by construction -- but "matches by
#: construction" was doing more work here than anyone had checked. 044c swept
#: k from 16 to 4096 and found this band moves a great deal with it: arxiv's
#: own threshold position runs from the 85.69th percentile at k=16 to the
#: 96.53rd at k=512. So the construction is load-bearing, not incidental, and
#: the thing that discharges it is that one constant feeds every caller.
#:
#: What is still assumed: that three full fixtures are enough to bound the
#: band. They are not many -- `ambiguity.PUBLISHED_AMBIGUITY_PERCENTILES`
#: records the same limit, and `docs/FIXTURES.md` carries it as a stated
#: limit rather than a wish.
#:
#: (Until 044d this comment read that the sample-size drift "has not been
#: measured. That is task 044c's question" -- wrong twice over, three lines
#: above the constant 044b set from measuring it, and about a task whose
#: question was the centroid count. Recorded because two comments in one
#: module disagreeing about whether a thing is measured is the
#: `docs/PRACTICE.md` section 4 mechanism in a smaller key.)
PUBLISHED_PERCENTILE_BASIS = (
    "measured on the full published fixtures at 150,000 vectors and "
    "N_CENTROIDS regions; smoke fixtures excluded. The threshold's position "
    "drifts upward with sample size at a fixed centroid count and converges "
    "on the published value, so the comparison is only made at or above "
    "MIN_N_FOR_TRANSFER.")

#: Below this many vectors the transfer comparison is not made at all.
#:
#: **Measured, not guessed** (task 044b), on the published vectors at the
#: production centroid count, which isolates sample size:
#:
#:     arxiv-150k          n=5,000   87.46   OUTSIDE its own band
#:                        n=10,000   93.40   inside
#:                        n=20,000   95.79   inside
#:                        n=50,000   96.42   inside   (published 96.37)
#:     stackexchange-150k  n=5,000   91.45 .. n=50,000 98.64 (published 98.83)
#:
#: At 5,000 vectors **arxiv's own published corpus reads outside its own band
#: under the anchor model** -- a false alarm on precisely the signal this
#: comparison exists to give, and a false alarm degrades a warning faster than
#: silence does. The position converges from below as n grows, so the floor is
#: set where the measurement shows the drift has stopped mattering, which is
#: also the sample size this project already recommends.
MIN_N_FOR_TRANSFER = 10000


def published_range(per_fixture):
    return (min(per_fixture.values()), max(per_fixture.values()))


def against_published(pct, per_fixture, threshold, what, n=None):
    """How this corpus's threshold position compares with the published ones.

    It is **not a verdict**: a position outside the published band is a reason
    to weigh the reading, not a demonstration that it is wrong, and nothing
    measurable on one corpus could demonstrate that.

    Below `MIN_N_FOR_TRANSFER` the comparison is **not made** -- it is
    couldn't-check, because the measured drift shows a small sample lands
    outside the band for reasons of sample size.
    """
    lo, hi = published_range(per_fixture)
    out = {
        "threshold_percentile": pct,
        "published_range": [lo, hi],
        "published_per_fixture": dict(per_fixture),
        "basis": PUBLISHED_PERCENTILE_BASIS,
    }
    if n is not None and int(n) < MIN_N_FOR_TRANSFER:
        out["outside_published_range"] = None
        out["outcome"] = "couldnt_check"
        out["note"] = (
            "not compared: %d vectors is below the %d this comparison needs. "
            "The threshold's position drifts upward with sample size and "
            "converges on the published value, so a smaller sample lands "
            "below the band for reasons of sample size rather than of "
            "embedding -- measured: arxiv-150k reads the 87.46th percentile "
            "at 5,000 vectors against its own published 96.37th. Comparing "
            "here would raise a false alarm on the one signal this block "
            "exists to give. The threshold still sits at the %.2fth "
            "percentile of this corpus, which is reported above."
            % (int(n), MIN_N_FOR_TRANSFER, pct))
        return out
    # EDGE_EPSILON, because the endpoints of this band ARE published fixtures
    # and a strict comparison made two of them read outside it (task 044d).
    outside = not (lo - EDGE_EPSILON <= pct <= hi + EDGE_EPSILON)
    out["outside_published_range"] = outside
    if outside:
        out["note"] = (
            "%.2f sits at the %.2fth percentile of this corpus's ratio "
            "distribution. On the published corpora the same threshold sits "
            "between the %.1fth and the %.1fth. This reading is being taken "
            "somewhere the measure has never been calibrated, so a %s here "
            "does not mean what the same number means on those corpora. It is "
            "a reason to read the distribution rather than the number; it is "
            "not a demonstration that the number is wrong, and no measurement "
            "of one corpus could be."
            % (threshold, pct, lo, hi, what))
    else:
        out["note"] = (
            "%.2f sits at the %.2fth percentile here, inside the %.1fth to "
            "%.1fth the published corpora span, so this reading is being "
            "taken where the measure has been calibrated."
            % (threshold, pct, lo, hi))
    return out


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
      `transfer`              where the same threshold sits on the published
                              corpora, and whether this one is outside that
                              band -- the only thing a single reading can be
                              weighed against, and not a verdict

    `resolvable` is a **couldn't-check on the reading, not on the measure**:
    the distribution was measured fine and it is the count that cannot be
    read. Those are different outcomes and this project does not round one
    into the other.
    """
    dist = ratio_distribution(d_base)
    value = count_at(d_base, threshold)
    n = int(dist["n"])
    pct = threshold_percentile(dist, threshold)
    resolvable, n_above, sigma = distinguishable(value, n, degenerate=0.0)
    out = {
        "value": value,
        "threshold": float(threshold),
        "of": "the ratio distribution",
        "n": n,
        "n_above": n_above,
        "sigma_from_zero": sigma,
        "threshold_percentile": pct,
        "resolvable": resolvable,
        "transfer": against_published(pct, PUBLISHED_CRISP_PERCENTILES,
                                      threshold, "count", n=n),
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
            "only %d of %d vectors are above %.2f -- %.2f standard errors "
            "from zero, under the %.1f needed -- so this count is not "
            "distinguishable from zero and must not be reported as one. The "
            "threshold sits at the %.2fth percentile of this corpus's "
            "distribution. This is a couldn't-check on the reading: the "
            "distribution was measured and is the number to read."
            % (n_above, n, threshold, sigma, DISTINGUISHABILITY_SIGMA, pct))
    if with_distribution:
        out["distribution"] = dist
    return out

