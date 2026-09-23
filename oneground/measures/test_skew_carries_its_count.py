"""The centroid count travels with the skew value (task 044c).

Task 044c swept `N_CENTROIDS` from 16 to 4096 and found that of the three
constants under the old "definitions, not parameters" comment, this measure is
the one that holds no tolerance away from 256 at all -- it leaves the
published +/-0.02 at the first step in either direction, on both fixtures
whose vectors are local and in both arms of the sweep.

So these tests are about the COUNT being present and the two readings being
refused a comparison across counts. They are not about the arithmetic of
`skew_top10_share`, which is unchanged and covered by `test_measures.py`.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.measures import skew as sk                         # noqa: E402
from oneground.measures.crispness import N_CENTROIDS              # noqa: E402


def _regions(sizes):
    """Region ids with the given per-region populations."""
    return np.concatenate([np.full(n, i, dtype=np.int64)
                           for i, n in enumerate(sizes)])


# ------------------------------------------------- the published value stands
def test_the_published_function_is_unchanged_synthetic():
    """044c may not move a published value, and this is the guard on that.

    Ten regions of 100 out of 256, the rest empty: the ten largest hold
    everything.
    """
    r = _regions([100] * 10)
    assert sk.skew_top10_share(r, len(r), 256) == pytest.approx(1.0)


def test_an_even_partition_reads_the_uniform_baseline_synthetic():
    r = _regions([10] * 256)
    assert sk.skew_top10_share(r, len(r), 256) == pytest.approx(10 / 256)


# ----------------------------------------------------- the count is carried
def test_the_reading_carries_the_count_it_is_a_share_of():
    r = _regions([10] * 256)
    got = sk.reading(r, len(r), 256)
    assert got["n_centroids"] == 256
    assert got["value"] == pytest.approx(sk.skew_top10_share(r, len(r), 256))
    assert "256" in got["of"] and "256" in got["note"]


def test_the_default_count_is_the_one_characterize_uses():
    """A reading that defaulted to something else would carry a true number
    about a partition nobody built."""
    r = _regions([10] * N_CENTROIDS)
    assert sk.reading(r, len(r))["n_centroids"] == N_CENTROIDS


def test_the_same_partition_at_two_counts_gives_two_different_readings():
    """The measured fact that makes the count load-bearing, in miniature.

    An even partition into 64 regions and one into 256 are both perfectly
    even, and their skew values differ by a factor of four -- so a reader
    comparing the two numbers without the counts compares nothing.
    """
    small = sk.reading(_regions([40] * 64), 64 * 40, 64)
    large = sk.reading(_regions([10] * 256), 256 * 10, 256)
    assert small["value"] == pytest.approx(10 / 64)
    assert large["value"] == pytest.approx(10 / 256)
    assert small["value"] / large["value"] == pytest.approx(4.0)
    assert small["n_centroids"] != large["n_centroids"]


def test_the_uniform_baseline_does_not_make_the_two_comparable():
    """The refuted rescaling, asserted as refuted.

    Dividing by 10/k makes these two synthetic even partitions agree, which is
    exactly why the real sweep is the evidence and not this: on arxiv-150k the
    same ratio climbs 1.19 to 3.10 over k from 16 to 4096. The test records
    that `excess_over_uniform` is reported as a convenience and is NOT a
    licence to compare across counts -- the reading says so itself.
    """
    small = sk.reading(_regions([40] * 64), 64 * 40, 64)
    large = sk.reading(_regions([10] * 256), 256 * 10, 256)
    assert small["excess_over_uniform"] == pytest.approx(1.0)
    assert large["excess_over_uniform"] == pytest.approx(1.0)
    for got in (small, large):
        assert "and nothing else" in got["comparable_with"]
        assert str(got["n_centroids"]) in got["comparable_with"]


def test_skew_is_never_couldnt_check():
    """Unlike its two siblings. There is no threshold here to empty out, so a
    resolvability key would be a question about nothing -- and this project
    does not report an outcome it cannot mean."""
    got = sk.reading(_regions([10] * 256), 2560, 256)
    assert "resolvable" not in got
    assert "outcome" not in got


# ------------------------------------------------- what the sweep measured
def test_the_module_records_the_range_it_was_measured_over():
    """"Stable" without a range is not a measurement, and neither is
    "load-bearing" without one. 044c's range is in the docstring or the claim
    in it is unsupported."""
    doc = sk.__doc__
    assert "044c" in doc
    assert "16 to 4096" in doc
    for corpus_fact in ("0.1246", "0.0357", "0.0754"):
        assert corpus_fact in doc, corpus_fact
