"""A fixture must read inside the band it is itself an edge of (task 044d).

`against_published` weighs a corpus's threshold position against the range the
published fixtures span. The range's endpoints ARE published fixtures. So a
fixture in the table is calibrated ground by construction and can never
legitimately read outside — if one does, the comparison is warning about the
one corpus it cannot be wrong about.

WHY THIS IS A SECOND FILE AND NOT AN EXTRA ASSERT
-------------------------------------------------
`test_ambiguity_distribution.py` already checks these constants against the
fixtures, with `approx(recorded, abs=0.05)`. It is right about the fact it
checks -- that a rebuild has not left them stale -- and it is **ten times
looser than the rounding that causes this defect**. A 0.05 agreement band
cannot see a 0.005 disagreement, and this defect is entirely about direction
at an edge.

So that test keeps its subject and its tolerance, and this one has its own:
not *are the constants about right* but *does the comparison they drive give
the right answer on its own sources*. Those are different questions and one
assert cannot ask both.
"""

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

#: (stem, table, threshold, what) for each published reference band.
BANDS = (
    ("ground_view_base", C.PUBLISHED_CRISP_PERCENTILES, C.CRISP_RATIO,
     "count"),
    ("ground_view_queries", A.PUBLISHED_AMBIGUITY_PERCENTILES,
     A.AMBIGUOUS_RATIO, "rate"),
)


def _dists(ratios):
    r = np.asarray(ratios, dtype=np.float64)
    return np.column_stack([np.ones_like(r), r])


def _measured_percentile(fixture, stem, threshold):
    """Where the threshold falls, recomputed from the published ground view.

    From the parquet rather than from the stored constant, because the stored
    constant is the thing under test.
    """
    pq = pytest.importorskip("pyarrow.parquet")
    path = os.path.join(REPO, "fixtures", fixture, stem + ".parquet")
    if not os.path.exists(path):
        pytest.skip("%s absent" % path)
    r = pq.read_table(path, columns=["ratio"])["ratio"].to_numpy()
    return C.threshold_percentile(C.ratio_distribution(_dists(r)), threshold)


# ------------------------------------------------------------ the defect
@pytest.mark.parametrize("stem,table,threshold,what", BANDS)
def test_every_published_fixture_reads_inside_the_band_it_is_part_of(
        stem, table, threshold, what):
    """NOT synthetic. The sources of the band, weighed against the band.

    Measured in 044c: stackexchange-150k's query ratio puts 1.10 at the
    90.871567th percentile, and the table stores its own entry as 90.87 --
    which is the table's maximum, so it is the top edge. `lo <= pct <= hi` is
    strict, so the corpus that calibrated the band reads outside it and the
    user is told the measure has never been calibrated here.
    """
    outside = []
    for fixture in table:
        pct = _measured_percentile(fixture, stem, threshold)
        got = C.against_published(pct, table, threshold, what,
                                  n=C.MIN_N_FOR_TRANSFER)
        if got["outside_published_range"]:
            lo, hi = got["published_range"]
            outside.append(
                "%s: measured %.6f, stored %.2f, band %.2f-%.2f"
                % (fixture, pct, table[fixture], lo, hi))
    assert outside == [], (
        "a published fixture reads outside the band it is an endpoint of -- "
        "the transfer warning firing on the corpus that calibrated it:\n  "
        + "\n  ".join(outside))


@pytest.mark.parametrize("stem,table,threshold,what", BANDS)
def test_the_stored_edges_are_the_measured_extremes(stem, table, threshold,
                                                    what):
    """The narrower statement, which is what actually has to hold.

    It is not enough that each fixture lands inside: the band's endpoints must
    be at or outside the measured extremes, or the endpoint fixture is the one
    that fails. Asserting this directly means a future rounding that goes the
    other way is caught at the constant rather than at whichever consequence
    happens to be tested.
    """
    measured = {f: _measured_percentile(f, stem, threshold) for f in table}
    lo, hi = C.published_range(table)
    assert lo <= min(measured.values()) + 1e-9, (
        "stored low edge %.6f is above the measured minimum %.6f (%s)"
        % (lo, min(measured.values()), min(measured, key=measured.get)))
    assert hi + 1e-9 >= max(measured.values()), (
        "stored high edge %.6f is below the measured maximum %.6f (%s) -- "
        "that fixture reads outside its own band"
        % (hi, max(measured.values()), max(measured, key=measured.get)))


# --------------------------------------------- the check cannot be vacuous
@pytest.mark.parametrize("stem,table,threshold,what", BANDS)
def test_the_check_actually_read_the_ground_views(stem, table, threshold,
                                                  what):
    """A test that skipped every fixture would pass the two above.

    `docs/PRACTICE.md` section 2, warning 6: a check that skips where it would
    fail. The published fixtures ship these parquets, so reading none of them
    is a broken test rather than an absent one.
    """
    read = 0
    for fixture in table:
        path = os.path.join(REPO, "fixtures", fixture, stem + ".parquet")
        if os.path.exists(path):
            read += 1
    assert read >= 2, (
        "only %d of %d %s.parquet present; this check needs the published "
        "ground views to mean anything" % (read, len(table), stem))


def test_a_corpus_genuinely_outside_the_band_is_still_reported_synthetic():
    """The signal must survive the fix.

    044b's e5 reading at the 97.74th percentile against a 65.4-90.9 band is
    the case this comparison exists to flag, and a fix that widened the band
    until nothing ever fell outside would have removed it. Synthetic only in
    that the percentile is passed in rather than recomputed; the number is
    044b's measurement.
    """
    got = C.against_published(97.74, A.PUBLISHED_AMBIGUITY_PERCENTILES,
                              A.AMBIGUOUS_RATIO, "rate",
                              n=C.MIN_N_FOR_TRANSFER)
    assert got["outside_published_range"] is True
    assert "never been calibrated" in got["note"]
