"""Unit tests for the five measures, on synthetic inputs with known answers.

**Every test here runs on synthetic data**, and that is stated in the names
rather than left to the reader: passing says the estimator behaves the way its
definition says on geometry we constructed, not that any number published
about a real corpus is right. The fixture is what checks that.

The point of these is that each measure has a shape you can reason about
independently:

    crispness   two well-separated blobs -> ~1.0; one isotropic blob -> ~0.0
    lid         points on a k-dimensional plane in 768-space -> ~k
    skew        one giant region -> high; equal regions -> ~10/256
    ambiguity   queries at blob centres -> ~0; queries midway between -> ~1

    python oneground/measures/test_measures.py
    pytest oneground/measures/test_measures.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.measures import (  # noqa: E402
    boundary_crispness, centroid_dists, kmeans, two_nn_lid)
from oneground.measures.ambiguity import ambiguous_query_rate  # noqa: E402
from oneground.measures.drift import one_region_exact_recall, recall  # noqa: E402
from oneground.measures.skew import skew_top10_share  # noqa: E402

SEED = 20260910


def _normalize(a):
    n = np.linalg.norm(a, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (a / n).astype(np.float32)


def _blobs(n_per, centres, spread=0.02, seed=SEED, dim=64):
    """Tight blobs around given centres in `dim` dimensions."""
    rng = np.random.default_rng(seed)
    parts = []
    for c in centres:
        centre = np.zeros(dim, dtype=np.float32)
        centre[:len(c)] = c
        parts.append(centre + rng.normal(0, spread, size=(n_per, dim)))
    return _normalize(np.vstack(parts).astype(np.float32))


# ------------------------------------------------------------- crispness
def test_crispness_of_two_separated_blobs_is_near_one_synthetic():
    """Well-separated groups: every point's 2nd centroid is far away."""
    x = _blobs(400, [(1, 0, 0), (-1, 0, 0)], spread=0.01)
    cents = kmeans(x, 2, SEED)
    d, _ = centroid_dists(x, cents, 2)
    c = boundary_crispness(d)
    assert c > 0.95, f"expected ~1.0 for two separated blobs, got {c}"


def test_crispness_of_one_isotropic_blob_is_near_zero_synthetic():
    """One undifferentiated cloud cut in two: points sit on the boundary."""
    rng = np.random.default_rng(SEED)
    x = _normalize(rng.normal(0, 1, size=(1500, 32)).astype(np.float32))
    cents = kmeans(x, 16, SEED)
    d, _ = centroid_dists(x, cents, 2)
    c = boundary_crispness(d)
    assert c < 0.35, f"expected a low value for an isotropic cloud, got {c}"


def test_crispness_is_a_ratio_test_at_exactly_1_20_synthetic():
    """The definition is d2 > 1.20 * d1, strictly. Pin the boundary."""
    d = np.array([[1.0, 1.19], [1.0, 1.20], [1.0, 1.21]], dtype=np.float32)
    assert abs(boundary_crispness(d) - 1 / 3) < 1e-6, \
        "only the 1.21 row is crisp: > is strict and 1.20 is not > 1.20"


# ------------------------------------------------------------------- lid
def test_lid_recovers_a_low_dimensional_plane_synthetic():
    """Points spanning 4 directions inside a 768-dim space estimate near 4."""
    rng = np.random.default_rng(SEED)
    k = 4
    coords = rng.normal(0, 1, size=(4000, k))
    basis = rng.normal(0, 1, size=(k, 768))
    x = _normalize((coords @ basis).astype(np.float32))
    est = two_nn_lid(x, SEED)
    assert 2.5 < est < 6.0, f"expected ~{k}, got {est}"


def test_lid_of_a_higher_dimensional_manifold_is_larger_synthetic():
    """Monotonicity is the property that matters, not the exact value."""
    rng = np.random.default_rng(SEED)

    def est(k):
        coords = rng.normal(0, 1, size=(4000, k))
        basis = rng.normal(0, 1, size=(k, 256))
        return two_nn_lid(_normalize((coords @ basis).astype(np.float32)), SEED)

    assert est(3) < est(12), "LID did not increase with true dimensionality"


# ------------------------------------------------------------------ skew
def test_skew_of_equal_regions_is_the_even_share_synthetic():
    """256 equal regions: the top ten hold 10/256."""
    regions = np.repeat(np.arange(256), 10)
    s = skew_top10_share(regions, len(regions))
    assert abs(s - 10 / 256) < 1e-6, s


def test_skew_of_one_dominant_region_is_near_one_synthetic():
    regions = np.concatenate([np.zeros(900, dtype=int), np.arange(1, 101)])
    s = skew_top10_share(regions, len(regions))
    assert s > 0.9, s


# ------------------------------------------------------------- ambiguity
def test_ambiguity_of_queries_at_blob_centres_is_near_zero_synthetic():
    x = _blobs(400, [(1, 0, 0), (-1, 0, 0)], spread=0.01)
    cents = kmeans(x, 2, SEED)
    d_q, _ = centroid_dists(cents, cents, 2)     # queries = the centres
    assert ambiguous_query_rate(d_q) == 0.0


def test_ambiguity_of_queries_between_blobs_is_near_one_synthetic():
    x = _blobs(400, [(1, 0, 0), (-1, 0, 0)], spread=0.01)
    cents = kmeans(x, 2, SEED)
    midpoint = _normalize(((cents[0] + cents[1]) / 2)[None, :]
                          + np.zeros((20, cents.shape[1]), dtype=np.float32))
    d_q, _ = centroid_dists(midpoint, cents, 2)
    assert ambiguous_query_rate(d_q) == 1.0


def test_ambiguity_is_a_ratio_test_at_exactly_1_10_synthetic():
    d = np.array([[1.0, 1.09], [1.0, 1.10], [1.0, 1.11]], dtype=np.float32)
    assert abs(ambiguous_query_rate(d) - 2 / 3) < 1e-6, \
        "1.09 and 1.10 are ambiguous: <= is inclusive"


# ----------------------------------------------------------------- recall
def test_recall_counts_pairs_and_treats_padding_as_a_miss_synthetic():
    gt = np.array([[1, 2], [3, 4]])
    assert recall(np.array([[1, 2], [3, 4]]), gt) == 1.0
    assert recall(np.array([[1, 9], [3, 9]]), gt) == 0.5
    # -1 is padding for a region that held fewer than k vectors: a real miss.
    assert recall(np.array([[1, -1], [3, -1]]), gt) == 0.5


def test_one_region_recall_is_perfect_when_regions_match_truth_synthetic():
    """Two separated blobs, queries inside them: one region holds every
    true neighbour, so restricting to it loses nothing."""
    x = _blobs(200, [(1, 0, 0), (-1, 0, 0)], spread=0.01)
    cents = kmeans(x, 2, SEED)
    q = x[:5]
    from oneground.truth import exact_knn
    gt10 = exact_knn(x, q, 10)
    r = one_region_exact_recall(x, q, cents, gt10)
    assert r > 0.99, f"expected ~1.0 when the partition matches truth, got {r}"


def _main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
