"""Side by side only if they may be (task 041, step 7).

The rule under test is structural: a mark holding both runs' numbers exists
only when the verdict is `comparable`. A rule enforced only by layout is one
stylesheet away from being lost.
"""
import os

import pytest

from oneground.lab import guard
from oneground.lab import runs as runsmod
from oneground.lab.receipt import draw_receipt
from oneground.lab.views.compare import (COMPARABLE, COULDNT_CHECK,
                                         NOT_COMPARABLE, ComparisonView)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = os.path.join(REPO, "runs", "041-ui")


def _doc(a, b):
    for p in (a, b):
        if not os.path.isdir(p):
            pytest.skip(f"no local {p}")
    return runsmod.comparison_document(a, b)


def _draw(a, b):
    return draw_receipt(ComparisonView(), _doc(a, b))


def _joined(drawing):
    """Marks that hold values for both runs in one row."""
    return [m for m in drawing.marks
            if "left" in m.data and "right" in m.data
            and "ingredient" not in m.data]


def test_a_not_comparable_pair_is_never_joined_into_one_row():
    d = _draw(os.path.join(LOCAL, "arxiv-smoke"),
              os.path.join(LOCAL, "stackexchange-150k-via-characterize"))
    assert d.figures["verdict"] == NOT_COMPARABLE
    assert d.figures["paired"] is False
    assert _joined(d) == [], "a renderer was handed a row holding both runs"
    # one mark per run instead
    per_run = [m for m in d.marks if "run" in m.data]
    assert len(per_run) == 2


def test_a_couldnt_check_pair_is_not_joined_either():
    """Unknown is not permission. The pair that agrees on everything knowable
    still does not get a comparison table."""
    d = _draw(os.path.join(REPO, "runs", "arxiv-150k-via-characterize"),
              os.path.join(LOCAL, "arxiv-150k-via-characterize"))
    assert d.figures["verdict"] == COULDNT_CHECK
    assert d.figures["paired"] is False
    assert _joined(d) == []


def test_only_a_comparable_verdict_produces_a_joined_mark_synthetic():
    doc = {"kind": "comparison", "verdict": COMPARABLE,
           "reason": "everything agrees",
           "findings": [{"ingredient": "code", "state": "same",
                         "required": True, "left": "v", "right": "v",
                         "note": None}],
           "runs": [{"name": "a", "n_base": 10, "stages": {"report": True},
                     "report": None, "manifest": {"all_verified": True},
                     "problems": []},
                    {"name": "b", "n_base": 10, "stages": {"report": True},
                     "report": None, "manifest": {"all_verified": True},
                     "problems": []}]}
    d = draw_receipt(ComparisonView(), doc)
    assert d.figures["paired"] is True
    assert len(_joined(d)) == 1
    assert "comparison" not in d.gaps


def test_the_verdict_leads_and_carries_its_reason():
    d = _draw(os.path.join(LOCAL, "arxiv-smoke"),
              os.path.join(LOCAL, "support-tickets-2026q3"))
    assert d.caption.startswith(d.figures["verdict"])
    assert d.figures["reason"]
    assert d.figures["means"]
    assert "comparison" in d.gaps
    assert d.gaps["comparison"].startswith("couldnt_check")
    assert "on the reader's behalf" in d.gaps["comparison"]


def test_the_ingredient_table_is_always_drawn_whatever_the_verdict():
    """A reader is told which part is unknown, not only that something is."""
    d = _draw(os.path.join(LOCAL, "arxiv-smoke"),
              os.path.join(LOCAL, "stackexchange-150k-via-characterize"))
    table = d.marks[0].data
    assert "code" in table["ingredient"]
    assert "machine" in table["ingredient"]
    assert len(table["state"]) == len(table["ingredient"])


def test_the_view_reads_every_path_it_declares():
    v = ComparisonView()
    d = _draw(os.path.join(LOCAL, "arxiv-smoke"),
              os.path.join(LOCAL, "stackexchange-150k-via-characterize"))
    assert set(v.reads) - set(d.reads) == set()


def test_the_comparison_modules_pass_their_own_guard():
    assert guard.check_views() == {}
    assert guard.check_transport() == {}
    assert guard.unclassified_modules() == []
