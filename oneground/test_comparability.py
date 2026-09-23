"""The comparability verdict (docs/LIBRARY.md §2.2, built by task 041).

§2.2 specifies this verdict, says it is "written here and implemented
nowhere", and says whichever of the three positions depending on it is built
first builds it. These tests hold it to what §2.2 actually requires, which is
mostly a set of refusals.
"""
import os

import pytest

from oneground import comparability as C

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.path.join(REPO, "runs", "041-ui")


def _facts(**kw):
    base = {"run": "r", "code": "0.1.0+abc", "libraries": {"numpy": "2.5.3"},
            "settings": "deadbeef", "sample": "cafe", "platform": "win",
            "python_version": "3.12.10", "environment_id": "pod-1",
            "pod": "pod-1"}
    base.update(kw)
    return base


# ------------------------------------------------------------- the three values
def test_everything_known_and_equal_is_comparable_synthetic():
    v = C.verdict(_facts(), _facts())
    assert v["verdict"] == C.COMPARABLE
    assert v["differing"] == [] and v["unknown"] == []


def test_one_difference_is_enough_to_be_not_comparable_synthetic():
    v = C.verdict(_facts(), _facts(sample="other"))
    assert v["verdict"] == C.NOT_COMPARABLE
    assert v["differing"] == ["sample"]
    assert "not attributable" in v["reason"]


def test_an_unknown_required_ingredient_is_couldnt_check_synthetic():
    v = C.verdict(_facts(code=None), _facts())
    assert v["verdict"] == C.COULDNT_CHECK
    assert v["unknown"] == ["code"]


def test_an_unknown_is_never_rounded_up_to_comparable_synthetic():
    """A missing version is never read as a match -- the whole point of the
    third value."""
    for missing in ("code", "libraries", "settings", "sample"):
        v = C.verdict(_facts(**{missing: None}), _facts())
        assert v["verdict"] != C.COMPARABLE, missing


def test_a_difference_outranks_an_unknown_synthetic():
    """Knowing they differ beats not knowing: `not_comparable` is the safe
    and more useful answer, and it never rounds an unknown up."""
    v = C.verdict(_facts(code=None), _facts(code=None, sample="other"))
    assert v["verdict"] == C.NOT_COMPARABLE
    assert "code" in v["unknown"] and "sample" in v["differing"]


def test_an_optional_ingredient_unknown_does_not_block_comparable_synthetic():
    v = C.verdict(_facts(platform=None), _facts())
    assert v["verdict"] == C.COMPARABLE


# ------------------------------------------------------- what cannot be asserted
def test_a_local_environment_id_is_never_the_same_machine_synthetic():
    """`local:<os>-<arch>` is a class, not an identity: two different laptops
    share one."""
    a = _facts(environment_id="local:windows-amd64", pod=None)
    b = _facts(environment_id="local:windows-amd64", pod=None)
    v = C.verdict(a, b)
    assert v["verdict"] == C.COULDNT_CHECK
    assert "machine" in v["unknown"]
    machine = next(f for f in v["findings"] if f["ingredient"] == "machine")
    assert machine["state"] == C.UNKNOWN
    assert "class rather than an identity" in machine["note"]


def test_a_recorded_pod_id_does_identify_a_machine_synthetic():
    v = C.verdict(_facts(pod="pod-7", environment_id="pod-7"),
                  _facts(pod="pod-7", environment_id="pod-7"))
    assert v["verdict"] == C.COMPARABLE
    v2 = C.verdict(_facts(pod="pod-7", environment_id="pod-7"),
                   _facts(pod="pod-8", environment_id="pod-8"))
    assert v2["verdict"] == C.NOT_COMPARABLE and v2["differing"] == ["machine"]


def test_every_unknown_carries_a_sentence_not_just_the_word_synthetic():
    v = C.verdict(_facts(code=None, settings=None), _facts())
    for f in v["findings"]:
        if f["state"] == C.UNKNOWN:
            assert f["note"] and len(f["note"]) > 30, f


def test_this_is_not_the_calibration_comparable():
    """§2.2 calls `calibrate.history.comparable` the right shape and the wrong
    subject. It compares engine identity; this compares provenance. The two
    must not be conflated, so the ingredient sets must not overlap."""
    from oneground.calibrate import history
    assert callable(history.comparable)
    mine = {k for k, _, _ in C.INGREDIENTS}
    theirs = {"check", "dataset", "engine", "engine_version", "config"}
    assert mine & theirs == set()


# ------------------------------------------------------------------ real runs
def _runs():
    if not os.path.isdir(LOCAL):
        pytest.skip("no local runs/041-ui")
    return sorted(d for d in os.listdir(LOCAL)
                  if os.path.isdir(os.path.join(LOCAL, d)))


def test_no_run_on_this_machine_records_the_version_that_measured_it():
    """§2.2 predicted this: today the honest value is couldnt_check, on the
    code, because no artifact records the oneground version."""
    for name in _runs():
        facts = C.facts_of(os.path.join(LOCAL, name))
        assert facts["code"] is None, (name, facts["code"])


def test_no_pair_of_local_runs_can_reach_comparable():
    """Not one pair, including a run against itself: the verdict cannot be
    earned until the 033 field is present on both sides."""
    import itertools
    names = _runs()
    for a, b in itertools.combinations(names, 2):
        v = C.compare_workdirs(os.path.join(LOCAL, a), os.path.join(LOCAL, b))
        assert v["verdict"] != C.COMPARABLE, (a, b)
        assert "code" in v["unknown"], (a, b)


def test_two_copies_of_the_same_run_are_still_only_couldnt_check():
    """The sharpest form of the finding. Everything knowable agrees -- same
    libraries, same settings digest, same sample digest, same platform -- and
    the pair is still couldnt_check.

    What this protects is the reason, which is two facts and not a tally:
    `code` is unanswerable because neither workdir records a released version,
    and `machine` IS answerable, because task 043 made `facts_of` read the
    measuring machine rather than the reporting one.

    It asserts those two and not the whole `unknown` set. The set is a current
    state: an earlier version asserted it entire, and 043 broke this test by
    making a third ingredient answerable -- a legitimate change, and the
    property above never moved. See `docs/PRACTICE.md` section 2, warning 7.
    """
    left = os.path.join(REPO, "runs", "arxiv-150k-via-characterize")
    right = os.path.join(LOCAL, "arxiv-150k-via-characterize")
    if not (os.path.isdir(left) and os.path.isdir(right)):
        pytest.skip("no local arxiv workdir pair")
    v = C.compare_workdirs(left, right)
    assert v["verdict"] == C.COULDNT_CHECK
    assert v["differing"] == []
    assert "code" in v["unknown"], (
        "code unanswerable is why this pair cannot reach comparable")
    assert "machine" not in v["unknown"], (
        "043 made the measuring machine answerable; docs/PRACTICE.md 4")
    states = {f["ingredient"]: f["state"] for f in v["findings"]}
    assert states["libraries"] == C.SAME
    assert states["settings"] == C.SAME
    assert states["sample"] == C.SAME
