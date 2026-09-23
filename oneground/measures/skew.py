"""Region size skew.

What share of the corpus falls into the ten largest of the 256 regions. Even
partitioning would put 10/256 = 3.9% there; more than that means some shards
carry disproportionate load, which is a capacity question rather than a recall
one.

THE COUNT IS PART OF THE MEASURE, NOT A SETTING BEHIND IT (task 044c)
---------------------------------------------------------------------
Crispness and ambiguity threshold a scale-invariant ratio, so a change in the
centroid count moves them but does not rob them of meaning. This one names a
fixed ten out of a variable k, and that is a different kind of dependence:
**10 regions of 4096 is not a weaker version of 10 of 256, it is a different
question.**

Task 044c swept k from 16 to 4096 on both fixtures whose vectors are local.
Of the three constants under the old "definitions, not parameters" comment,
this is the measure that came back worst:

    boundary_crispness    holds its published +/-0.02 over k in [32, 2048]  64x
    ambiguous_query_rate  holds it over k in [256, 1024], k isolated         4x
    skew_top10_share      holds it at k = 256                                1x

It leaves tolerance at the first step in either direction -- 0.1246 at k=128
and 0.0357 at k=512 against arxiv-150k's published 0.0754 -- and spans 0.0076
to 0.7465 across the sweep. Unanimous on both fixtures and in both arms.

**The obvious rescaling was refuted rather than left untried.** Dividing by
the uniform baseline 10/k does not make it comparable across counts: on
arxiv-150k `skew/(10/k)` climbs 1.19, 1.36, 1.55, 1.59, 1.93, 1.83, 2.27,
2.77, 3.10 over that sweep. There is no normalisation that rescues the number,
so the count travels with it.

So `skew_top10_share` is unchanged -- every published value depends on it
computing exactly what it computed before -- and `reading` sits beside it
carrying the count, exactly as 044 and 044b did for the other two.
"""

import numpy as np

from .crispness import N_CENTROIDS


def skew_top10_share(region_ids, n_base, n_centroids=N_CENTROIDS):
    """`region_ids` is the nearest-centroid column from centroid_dists.

    **Unchanged by task 044c**, deliberately: this is the published reading
    and every fixture value and tolerance depends on it. What 044c added sits
    beside it.
    """
    sizes = np.bincount(region_ids, minlength=n_centroids)
    return float(np.sort(sizes)[-10:].sum() / n_base)


def reading(region_ids, n_base, n_centroids=N_CENTROIDS):
    """The share, with the region count it is a share of.

    The mirror of `crispness.reading` and `ambiguity.reading`, and the reason
    is the same: a number whose meaning depends on a constant must carry the
    constant, or a reader compares two of them that are not comparable.

    It differs from those two in what it does **not** report. There is no
    resolvability test here, because there is nothing for one to be about: the
    share is not a count above a threshold that can empty, it is always ten
    regions' worth of something. A skew reading is never couldn't-check; it is
    either comparable with another at the same `n_centroids` or not comparable
    at all.
    """
    value = skew_top10_share(region_ids, n_base, n_centroids)
    uniform = 10.0 / int(n_centroids)
    sizes = np.bincount(np.asarray(region_ids), minlength=int(n_centroids))
    return {
        "value": value,
        "n_centroids": int(n_centroids),
        "of": "the 10 largest of %d regions" % int(n_centroids),
        "uniform_baseline": uniform,
        "excess_over_uniform": value / uniform if uniform else float("nan"),
        "empty_regions": int(np.count_nonzero(sizes == 0)),
        "largest_region": int(sizes.max()) if len(sizes) else 0,
        "comparable_with": (
            "another skew_top10_share measured at n_centroids=%d, and nothing "
            "else" % int(n_centroids)),
        "note": (
            "the share of vectors in the 10 largest of %d regions. The region "
            "count is part of this reading rather than a setting behind it: "
            "measured in task 044c, this value spans two orders of magnitude "
            "over k from 16 to 4096 and leaves the published +/-0.02 "
            "tolerance at the first step in either direction from 256. "
            "Dividing by the uniform baseline does not make it comparable "
            "across counts either -- that ratio climbs 1.19 to 3.10 over the "
            "same sweep. Two of these are comparable only at equal "
            "n_centroids." % int(n_centroids)),
    }
