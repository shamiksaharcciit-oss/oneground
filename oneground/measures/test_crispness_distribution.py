"""The ratio distribution, and the count as a reading of it (task 044).

**Synthetic except where it is not, and the exceptions say so.** The tests
that matter most run against the published fixtures' own `ground_view_base`
`ratio` column, because the constraint this task had to meet is that not one
published value moves.

The shape of the file follows the constraint: first that nothing changed, then
that the distribution is sufficient to recover what did not change, then that
the reading declares what it assumes, and last that the resolvability flag
fires where it should and stays quiet where it should.
"""

import glob
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.measures import crispness as C                   # noqa: E402

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _dists(ratios):
    """A distance array whose quotient is `ratios`."""
    r = np.asarray(ratios, dtype=np.float64)
    return np.column_stack([np.ones_like(r), r])


# ---------------------------------------------------------- nothing changed
def test_boundary_crispness_is_unchanged_synthetic():
    """The published reading must compute exactly what it always computed."""
    d = _dists([1.0, 1.19, 1.20, 1.21, 3.0])
    # strictly greater than 1.20: the 1.20 itself does not count
    assert C.boundary_crispness(d) == pytest.approx(2 / 5)


def test_count_at_the_declared_threshold_is_boundary_crispness_synthetic():
    rng = np.random.default_rng(7)
    d = _dists(1.0 + rng.gamma(2.0, 0.08, size=5000))
    assert C.count_at(d, C.CRISP_RATIO) == pytest.approx(
        C.boundary_crispness(d))


def test_the_threshold_is_not_a_parameter_anyone_moved():
    """If this fails, every published value and the teaser caption moved."""
    assert C.CRISP_RATIO == 1.20
    assert C.N_CENTROIDS == 256


# ------------------------------------------------ the distribution suffices
def test_the_quantile_grid_is_declared_and_fixed():
    """A grid that varied by corpus would make two corpora incomparable --
    the same defect the corpus-derived threshold was refused for."""
    assert C.RATIO_QUANTILES[0] == 0.0
    assert C.RATIO_QUANTILES[-1] == 100.0
    steps = {round(b - a, 6) for a, b in zip(C.RATIO_QUANTILES,
                                             C.RATIO_QUANTILES[1:])}
    assert steps == {C.RATIO_QUANTILE_STEP}


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_count_is_recoverable_from_the_distribution_alone_synthetic(seed):
    rng = np.random.default_rng(seed)
    d = _dists(1.0 + rng.gamma(2.0, 0.09, size=20000))
    dist = C.ratio_distribution(d)
    direct = C.count_at(d, C.CRISP_RATIO)
    recovered = C.count_from_quantiles(dist, C.CRISP_RATIO)
    # bounded by the grid spacing, and far inside the published +/-0.02
    assert abs(recovered - direct) <= C.RATIO_QUANTILE_STEP / 100.0


def test_a_ratio_of_exactly_one_is_neither_crisp_nor_dropped_synthetic():
    """A vector equidistant from two centroids is on the boundary, and a
    duplicate of a centroid is at 0/0. Both are vectors and both are counted;
    neither is crisp."""
    d = np.array([[0.0, 0.0], [1.0, 1.0], [1.0, 2.0]])
    r = C.ratios(d)
    assert r[0] == 1.0 and r[1] == 1.0 and r[2] == 2.0
    assert C.ratio_distribution(d)["n"] == 3


# --------------------------------------------- the reading says what it is
def test_the_reading_states_its_threshold_and_where_that_sits_synthetic():
    rng = np.random.default_rng(11)
    d = _dists(1.0 + rng.gamma(2.0, 0.09, size=20000))
    got = C.reading(d)
    assert got["threshold"] == C.CRISP_RATIO
    assert 0.0 <= got["threshold_percentile"] <= 100.0
    assert "reading" in got["note"] and "measurement" in got["note"]
    assert got["value"] == pytest.approx(C.boundary_crispness(d))


def test_a_count_of_two_vectors_is_couldnt_check_not_zero_synthetic():
    """Task 036's e5 case: 0.0007 of 3,000 records is two vectors.

    Two vectors above a threshold is not a proportion, and reporting it as one
    is how a user reads 'my corpus has no structure' off an instrument that
    did not read.
    """
    ratios = np.full(3000, 1.05)
    ratios[:2] = 1.9
    got = C.reading(_dists(ratios))
    assert got["n_above"] == 2
    assert got["resolvable"] is False
    assert got["outcome"] == "couldnt_check"
    assert "not distinguishable from zero" in got["why"]
    # and it is couldn't-check on the READING, not on the measure
    assert "the distribution was measured" in got["why"]


def test_a_tail_count_over_many_vectors_is_resolvable_synthetic():
    """The mirror, and the reason the first criterion was replaced.

    A threshold deep in the tail is still a measurement when enough vectors
    are above it. `arxiv-150k` is 3.6% of 150,000 -- 5,441 vectors at the
    96th percentile -- and calling that unreadable would have been a worse
    defect than the one this task exists for.
    """
    ratios = np.full(150000, 1.05)
    ratios[:5441] = 1.9
    got = C.reading(_dists(ratios))
    assert got["n_above"] == 5441
    assert got["resolvable"] is True
    assert "outcome" not in got


# ------------------------------------------- against the published fixtures
def _fixtures_with_ratio():
    out = []
    for path in sorted(glob.glob(os.path.join(
            REPO, "fixtures", "*", "ground_view_base.parquet"))):
        chj = os.path.join(os.path.dirname(path), "characterization.json")
        if os.path.exists(chj):
            out.append((os.path.basename(os.path.dirname(path)), path, chj))
    return out


@pytest.mark.parametrize("name,parquet,chj", _fixtures_with_ratio())
def test_every_published_crispness_reproduces_and_is_recoverable(name, parquet,
                                                                 chj):
    """NOT synthetic. The constraint that decided this task's whole design.

    Every fixture ships a `ratio` column for all its base vectors, so the
    distribution is checkable against the published artifacts rather than
    re-derived -- including for fixtures whose vectors are not on this machine.
    """
    pq = pytest.importorskip("pyarrow.parquet")
    ch = json.load(open(chj, encoding="utf-8"))
    ch = ch.get("characterization", ch)
    published = ch.get("boundary_crispness")
    if isinstance(published, dict):
        published = published.get("value")
    if published is None:
        pytest.skip("%s publishes no boundary_crispness" % name)

    r = pq.read_table(parquet, columns=["ratio"])["ratio"].to_numpy()
    d = _dists(r)
    direct = C.count_at(d, C.CRISP_RATIO)
    assert direct == pytest.approx(published, abs=0.02), (
        "%s: the published value must still reproduce" % name)

    dist = C.ratio_distribution(d)
    recovered = C.count_from_quantiles(dist, C.CRISP_RATIO)
    assert abs(recovered - direct) <= C.RATIO_QUANTILE_STEP / 100.0, (
        "%s: the count must be recoverable from the distribution" % name)

    # and every published fixture's reading is resolvable -- if one were not,
    # this task would have found a published number that should not be read
    assert C.reading(d)["resolvable"] is True, name
