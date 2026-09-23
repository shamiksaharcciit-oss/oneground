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


def test_the_published_percentile_constants_still_match_the_fixtures():
    """NOT synthetic. The reference is a published value and is checked like one.

    Both constants were derived from the published ground views once. If a
    fixture is ever rebuilt, they go stale silently and every `transfer` block
    starts weighing a corpus against a band that no longer exists.
    """
    pq = pytest.importorskip("pyarrow.parquet")
    for stem, table, threshold in (
            ("ground_view_base", C.PUBLISHED_CRISP_PERCENTILES, C.CRISP_RATIO),
            ("ground_view_queries", A.PUBLISHED_AMBIGUITY_PERCENTILES,
             A.AMBIGUOUS_RATIO)):
        for name, recorded in table.items():
            path = os.path.join(REPO, "fixtures", name, stem + ".parquet")
            if not os.path.exists(path):
                pytest.skip("%s absent" % path)
            r = pq.read_table(path, columns=["ratio"])["ratio"].to_numpy()
            got = C.threshold_percentile(
                C.ratio_distribution(_dists(r)), threshold)
            assert got == pytest.approx(recorded, abs=0.05), (
                "%s/%s: recorded %.2f, fixture says %.2f"
                % (name, stem, recorded, got))


def test_a_reading_outside_the_published_band_says_so_synthetic():
    """The signal the block exists for, and it must not be a verdict.

    Measured in 044b: e5's ambiguity threshold lands at the 97.74th percentile
    against a published band of 65.4-93.9. The user meets 0.978 with something
    to weigh it against, which is the whole point — and the note must stop
    short of claiming the number is wrong, because no measurement of one
    corpus could establish that.
    """
    got = C.against_published(97.74, A.PUBLISHED_AMBIGUITY_PERCENTILES,
                              A.AMBIGUOUS_RATIO, "rate")
    assert got["outside_published_range"] is True
    assert "never been calibrated" in got["note"]
    assert "not a demonstration that the number is wrong" in got["note"]
    # and it carries what the comparison assumes, unasked
    assert "sample size" in got["basis"]

    inside = C.against_published(80.0, A.PUBLISHED_AMBIGUITY_PERCENTILES,
                                 A.AMBIGUOUS_RATIO, "rate")
    assert inside["outside_published_range"] is False
    assert "has been calibrated" in inside["note"]


def test_a_small_sample_is_not_compared_against_the_band():
    """Measured in 044b: the threshold's position drifts upward with sample
    size and converges on the published value. At 5,000 vectors `arxiv-150k`
    reads the 87.46th percentile against its own published 96.37th — so a
    small sample would be flagged as outside the band for reasons of sample
    size, which is a false alarm on the one signal the block exists to give.
    """
    small = C.against_published(87.46, C.PUBLISHED_CRISP_PERCENTILES,
                                C.CRISP_RATIO, "count", n=5000)
    assert small["outside_published_range"] is None
    assert small["outcome"] == "couldnt_check"
    assert "false alarm" in small["note"]
    # the percentile itself is still reported; only the comparison is withheld
    assert small["threshold_percentile"] == 87.46

    big = C.against_published(87.46, C.PUBLISHED_CRISP_PERCENTILES,
                              C.CRISP_RATIO, "count", n=150000)
    assert big["outside_published_range"] is True
    assert "outcome" not in big


def test_smoke_fixtures_are_excluded_from_the_reference_band():
    """Ruled in 044b: a 2,000-vector fixture checks that a command runs, it
    does not calibrate a measure, and a band over both kinds is dominated by
    the looser one. Including `arxiv-smoke` widened crispness's band to
    47.2-98.8 — half the distribution, which barely discriminates.
    """
    for table in (C.PUBLISHED_CRISP_PERCENTILES,
                  A.PUBLISHED_AMBIGUITY_PERCENTILES):
        assert "arxiv-smoke" not in table, table
        assert len(table) == 3, table
    lo, hi = C.published_range(C.PUBLISHED_CRISP_PERCENTILES)
    assert lo > 80.0, (lo, hi)       # 89.25 with the smoke fixture excluded


def test_every_reading_carries_its_transfer_block_synthetic():
    rng = np.random.default_rng(13)
    d = _dists(1.0 + rng.gamma(1.5, 0.05, size=3000))
    for got in (A.reading(d), C.reading(d)):
        assert "transfer" in got
        assert "published_range" in got["transfer"]
        assert "outside_published_range" in got["transfer"]


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
