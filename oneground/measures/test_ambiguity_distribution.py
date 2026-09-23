"""The ambiguity rate as a reading, and the mirror of 044's defect (044b).

`ambiguous_query_rate` thresholds the same ratio as `boundary_crispness`, from
the other side: crispness counts the tail ABOVE 1.20, ambiguity counts
everything AT OR BELOW 1.10. So the failure is mirrored — a compressed
distribution empties one and saturates the other — and the tests are mirrored
with it, because a saturated reading is the one that looks like a finding.
"""

import glob
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.measures import ambiguity as A                   # noqa: E402
from oneground.measures import crispness as C                   # noqa: E402

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _dists(ratios):
    r = np.asarray(ratios, dtype=np.float64)
    return np.column_stack([np.ones_like(r), r])


# ---------------------------------------------------------- nothing changed
def test_ambiguous_query_rate_is_unchanged_synthetic():
    """<= 1.10, so the boundary value itself counts as ambiguous."""
    d = _dists([1.0, 1.10, 1.11, 2.0])
    assert A.ambiguous_query_rate(d) == pytest.approx(2 / 4)


def test_rate_at_the_declared_threshold_is_the_published_measure_synthetic():
    rng = np.random.default_rng(4)
    d = _dists(1.0 + rng.gamma(1.5, 0.05, size=4000))
    assert A.rate_at(d, A.AMBIGUOUS_RATIO) == pytest.approx(
        A.ambiguous_query_rate(d))


def test_the_threshold_is_not_a_parameter_anyone_moved():
    assert A.AMBIGUOUS_RATIO == 1.10


# ------------------------------------------------- the two are one family
def test_both_measures_threshold_the_same_quantity_from_opposite_sides():
    """The finding of 044b, as an assertion rather than a paragraph.

    One ratio, two constants, two directions. Everything at or below 1.10 is
    ambiguous; everything above 1.20 is crisp; the band between belongs to
    neither, and nothing in either measure reports where the distribution
    actually sits.
    """
    d = _dists([1.05, 1.15, 1.25])
    assert A.ambiguous_query_rate(d) == pytest.approx(1 / 3)
    assert C.boundary_crispness(d) == pytest.approx(1 / 3)
    # the middle vector is in neither reading, and both use the same ratio
    assert list(C.ratios(d)) == [1.05, 1.15, 1.25]


# ------------------------------------------------- the reading says what it is
def test_the_reading_states_its_threshold_and_where_that_sits_synthetic():
    rng = np.random.default_rng(9)
    d = _dists(1.0 + rng.gamma(1.5, 0.05, size=4000))
    got = A.reading(d)
    assert got["threshold"] == A.AMBIGUOUS_RATIO
    assert 0.0 <= got["threshold_percentile"] <= 100.0
    assert got["value"] == pytest.approx(A.ambiguous_query_rate(d))
    assert "reading" in got["note"] and "measurement" in got["note"]


def test_a_saturated_rate_is_couldnt_check_not_a_finding_synthetic():
    """The mirror of 044's two-vector case, and the more dangerous one.

    A rate of 0.999 over 2,000 queries is two queries NOT ambiguous. Reporting
    it as a proportion tells a user every query they have is ambiguous, which
    is a claim about their corpus; what it says is that the threshold sits
    above almost their whole distribution.
    """
    ratios = np.full(2000, 1.02)      # everything inside 1.10
    ratios[:2] = 1.5                  # two outside
    got = A.reading(_dists(ratios))
    assert got["n_outside"] == 2
    assert got["resolvable"] is False
    assert got["outcome"] == "couldnt_check"
    assert "not distinguishable from 1.0" in got["why"]
    # and it names the misreading it is there to prevent
    assert "every query is" in got["why"]
    assert "the distribution was measured" in got["why"]


def test_a_high_but_resolvable_rate_is_not_flagged_synthetic():
    """0.891 over 2,000 queries is 218 queries outside. High is not saturated,
    and 044's replaced criterion is the reason this test exists."""
    ratios = np.full(2000, 1.02)
    ratios[:218] = 1.5
    got = A.reading(_dists(ratios))
    assert got["n_outside"] == 218
    assert got["resolvable"] is True
    assert "outcome" not in got


def test_the_distribution_is_stored_when_asked_synthetic():
    d = _dists(1.0 + np.random.default_rng(2).gamma(1.5, 0.05, size=500))
    assert "distribution" not in A.reading(d)
    got = A.reading(d, with_distribution=True)
    assert len(got["distribution"]["quantiles"]) == len(C.RATIO_QUANTILES)


# ------------------------------------------- against the published fixtures
def _fixtures_with_query_ratio():
    out = []
    for path in sorted(glob.glob(os.path.join(
            REPO, "fixtures", "*", "ground_view_queries.parquet"))):
        chj = os.path.join(os.path.dirname(path), "characterization.json")
        if os.path.exists(chj):
            out.append((os.path.basename(os.path.dirname(path)), path, chj))
    return out


@pytest.mark.parametrize("name,parquet,chj", _fixtures_with_query_ratio())
def test_every_published_ambiguity_reproduces_and_is_resolvable(name, parquet,
                                                                chj):
    """NOT synthetic. No published value may move, and none does.

    Also asserts every published fixture's rate is currently *resolvable* — if
    one were not, this task would have found a published number that should
    not be read as a finding.
    """
    pq = pytest.importorskip("pyarrow.parquet")
    ch = json.load(open(chj, encoding="utf-8"))
    ch = ch.get("characterization", ch)
    published = ch.get("ambiguous_query_rate")
    if isinstance(published, dict):
        published = published.get("value")
    if published is None:
        pytest.skip("%s publishes no ambiguous_query_rate" % name)

    r = pq.read_table(parquet, columns=["ratio"])["ratio"].to_numpy()
    d = _dists(r)
    assert A.ambiguous_query_rate(d) == pytest.approx(published, abs=0.02), (
        "%s: the published value must still reproduce" % name)
    assert A.reading(d)["resolvable"] is True, name


def test_the_threshold_already_sits_high_in_every_fixture():
    """The finding this task exists to record, as a check rather than prose.

    1.10 is at the 65th-94th percentile of the query ratio on the published
    fixtures, under the anchor model. This measure has not failed and is
    closer to failing than crispness was when crispness failed — which is a
    fact about the family, not about either member. If a future change moved
    these percentiles down, that would be worth noticing, so it is asserted.
    """
    pq = pytest.importorskip("pyarrow.parquet")
    seen = {}
    for name, parquet, _ in _fixtures_with_query_ratio():
        r = pq.read_table(parquet, columns=["ratio"])["ratio"].to_numpy()
        dist = C.ratio_distribution(_dists(r))
        seen[name] = C.threshold_percentile(dist, A.AMBIGUOUS_RATIO)
    assert seen, "no fixture published a query ratio column"
    assert min(seen.values()) > 60.0, seen
    assert max(seen.values()) > 85.0, seen
