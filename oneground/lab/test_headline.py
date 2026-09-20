"""A run opens on its finding (task 041, steps 4 and 6).

Two rules are under test. The page never writes the headline -- it is the
report's own sentence, verbatim. And equal weight is a property of the data:
all three outcomes, always, in one order, with nothing in the structure
marking one as lesser, so a renderer cannot mute couldn't-check by accident.
"""
import json
import os

import pytest

from oneground.lab import runs as runsmod
from oneground.lab import server
from oneground.lab.receipt import draw_receipt
from oneground.lab.views.headline import (OUTCOMES, RunHeadlineView,
                                          RunProgressView, _counts_from)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = os.path.join(REPO, "runs", "041-ui")
TIER1 = os.path.join(REPO, "runs", "arxiv-150k-via-characterize", "report.json")
TIER2 = os.path.join(LOCAL, "support-tickets-2026q3", "report.json")
RECOMMENDS = os.path.join(LOCAL, "stackexchange-150k-via-characterize",
                          "report.json")


def _draw(path):
    if not os.path.isfile(path):
        pytest.skip(f"no local {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f), draw_receipt(RunHeadlineView(), json.load(
            open(path, encoding="utf-8")))


# ------------------------------------------------- the page writes no prose
def test_the_headline_is_the_reports_own_sentence_verbatim():
    report, d = _draw(TIER1)
    said = next(c["text"] for c in report["claims"]
                if c["kind"] == "recommendation")
    assert d.figures["headline"] == said
    assert d.caption == said


def test_a_tier_two_headline_is_its_own_recommendation_reason_verbatim():
    report, d = _draw(TIER2)
    assert d.figures["headline"] == report["recommendation_reason"]
    assert d.figures["headline_source"] == "report.json:recommendation_reason"
    assert "guess wearing a verdict's clothes" in d.figures["headline"]


# ------------------------------------------------------- the deciding row
def test_a_recommendation_carries_the_row_that_decided_it():
    report, d = _draw(RECOMMENDS)
    assert d.figures["from_rule"] is False
    assert d.figures["deciding_rows"] == 1
    assert "deciding_rows" not in d.gaps
    row = d.marks[-1].data
    assert row["source"][0].startswith("simulate.json:rows[")
    assert row["member"][0] == report["recommendation"]


def test_no_recommendation_means_no_deciding_row_and_says_why():
    """Nothing records which option came closest, and choosing one would be
    the page ranking options rather than drawing them."""
    _, d = _draw(TIER1)
    assert d.figures["from_rule"] is True
    assert "deciding_rows" not in d.figures, "0 rows is the absence"
    assert "deciding_rows" in d.gaps
    assert "ranking options" in d.gaps["deciding_rows"]


def test_tier_two_explains_its_missing_row_rather_than_leaving_a_blank():
    _, d = _draw(TIER2)
    assert "deciding_rows" in d.gaps
    assert "measured nothing" in d.gaps["deciding_rows"]


def test_every_absence_carries_a_reason():
    """No gap-less absence: a figure the drawing does not carry is either
    genuinely irrelevant or a gap with a sentence."""
    for path in (TIER1, TIER2, RECOMMENDS):
        _, d = _draw(path)
        for name, reason in d.gaps.items():
            assert reason.startswith("couldnt_check"), (path, name)
            assert len(reason) > 30, (path, name, reason)


# -------------------------------------------------------------- equal weight
def test_all_three_counts_always_in_one_order():
    for path in (TIER1, TIER2, RECOMMENDS):
        _, d = _draw(path)
        counts = d.figures["counts"]
        assert [c["outcome"] for c in counts] == list(OUTCOMES), path
        assert all(isinstance(c["n"], int) for c in counts), path


def test_a_zero_is_a_count_and_is_present():
    """`2 meets - 6 fails` is a different statement from
    `2 meets - 6 fails - 0 couldn't check`."""
    _, d = _draw(RECOMMENDS)
    counts = {c["outcome"]: c["n"] for c in d.figures["counts"]}
    assert counts == {"meets": 2, "fails": 6, "couldnt_check": 0}
    _, t2 = _draw(TIER2)
    assert {c["outcome"]: c["n"] for c in t2.figures["counts"]} == \
        {"meets": 0, "fails": 0, "couldnt_check": 6}


def test_nothing_in_the_structure_marks_an_outcome_as_lesser():
    """A renderer that wants to mute couldn't-check has to decide to; the
    data will not help it."""
    _, d = _draw(TIER1)
    for c in d.figures["counts"]:
        assert set(c) == {"outcome", "n"}, c
    # and the mark carries them as equal rows of one kind
    m = d.marks[0].data
    assert m["outcome"] == list(OUTCOMES)
    assert len(m["n"]) == 3


def test_a_partial_summary_is_a_gap_not_three_zeros_synthetic():
    assert _counts_from(summary={"meets": 1, "fails": 2}) is None
    d = draw_receipt(RunHeadlineView(),
                     {"run": "r", "schema": 1,
                      "summary": {"meets": 1, "fails": 2},
                      "claims": [{"kind": "recommendation", "text": "t",
                                  "source": "(rule)", "cites": []}]})
    assert "counts" not in d.figures
    assert "counts" in d.gaps and "showing zeros" in d.gaps["counts"]


# ------------------------------------------------- a run that has not reported
def _index():
    if not os.path.isdir(LOCAL):
        pytest.skip("no local runs/041-ui")
    return runsmod.index_runs(LOCAL, verifier=server.verify_manifests)


def test_a_run_with_no_report_leads_with_its_furthest_stage():
    d = draw_receipt(RunProgressView(run="acme-existing"), _index())
    assert d.figures["furthest_stage"] == "verify"
    assert d.figures["stages_run"] == ["characterize", "verify"]
    assert "report" in d.gaps
    assert d.gaps["report"].startswith("couldnt_check")


def test_the_next_command_is_the_next_stage_not_a_suggestion():
    """Named, not invented: the stage after the last one that ran, and there
    is only one."""
    d = draw_receipt(RunProgressView(run="acme-existing"), _index())
    assert d.figures["next_stage"] == "simulate"
    assert d.figures["next_command"] == \
        "oneground simulate <requirements.yaml>"
    assert d.figures["next_command"] in [c for _, c in RunProgressView.ORDER]


def test_a_run_that_is_not_there_is_a_gap_not_an_empty_page():
    d = draw_receipt(RunProgressView(run="no-such-run"), _index())
    assert "run" in d.gaps and "no run named" in d.gaps["run"]
    assert "run" not in d.figures, "a name that is a gap is not also a figure"


def test_the_progress_view_records_which_run_it_was_asked_for():
    d = draw_receipt(RunProgressView(run="acme-existing"), _index())
    assert d.params == {"run": "acme-existing"}
