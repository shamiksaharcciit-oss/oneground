"""Derived cites, and the four mutants that are this step's acceptance (043).

Task 039b measured that `claims.check` could not see a gap at all: a `Cite`
carries a value and a `source` path into a run's artifacts, and **a difference
has no such path**. So a delta lived in `Claim.extra` and nothing checked it.
Four mutants of a proposal card's metric claim, with the two cited values held
fixed and only the derived number varied, all returned *no problems*:

    rises by 0.0123   truthful                              no problems
    rises by 0.1230   inflated tenfold                      no problems
    rises by -0.0123  sign reversed                         no problems
    rises by 1.0145   a RATIO where a difference is claimed no problems

The fourth is the both-scales defect executed: the scale silently changed, the
prose still says "rises by", and the oracle is silent.

**Those four are the acceptance criterion for step 2 and they lead this file.**
One passes; three fail, each naming what was recomputed and what it got.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.report import claims as cl                       # noqa: E402

BEFORE, AFTER = 0.8500, 0.8623
FROM, TO = "baseline_cfg", "changed_cfg"


def _operands():
    return (cl.Cite(member=TO, value=AFTER,
                    source="card.json:measured.changed.recall_at_10"),
            cl.Cite(member=FROM, value=BEFORE,
                    source="simulate.json:rows[%s].recall_at_10" % FROM))


def _claim_with(delta_cite):
    after, before = _operands()
    return cl.Claim(
        kind="proposal_metric", predicate="held", subject=TO,
        constraint="recall_at_10", scope=(TO,), holds_for=(TO,),
        cites=(after, before, delta_cite))


# ------------------------------------------------------- the four mutants
def test_the_honest_delta_passes():
    after, before = _operands()
    honest = cl.derive(cl.DIFFERENCE, after, before)
    assert honest.value == pytest.approx(AFTER - BEFORE)
    assert cl.check(_claim_with(honest)) == []


@pytest.mark.parametrize("label,value", [
    ("inflated tenfold", 0.1230),
    ("sign reversed", -0.0123),
    ("a ratio where a difference is claimed", AFTER / BEFORE),
])
def test_a_dishonest_delta_now_fails(label, value):
    """The three 039b mutants that used to pass. Each must name its own sum."""
    after, before = _operands()
    mutant = cl.Cite(member=TO, value=value, op=cl.DIFFERENCE,
                     of=(after, before))
    problems = cl.check(_claim_with(mutant))
    assert problems, "%s was not caught" % label
    joined = " ".join(problems)
    assert "difference" in joined and "derived cite" in joined, joined


def test_the_ratio_is_legal_when_it_says_it_is_a_ratio():
    """The fourth mutant fails because the OPERATION was wrong, not the number.

    The same value, declared as a ratio, is a correct derived cite. That is
    the distinction the whole step exists to make: a gap is not wrong for
    being a ratio, it is wrong for being a ratio labelled a difference.
    """
    after, before = _operands()
    honest_ratio = cl.derive(cl.RATIO, after, before)
    assert honest_ratio.value == pytest.approx(AFTER / BEFORE)
    assert cl.check(_claim_with(honest_ratio)) == []


# ------------------------------------------------------- the chain to disk
def test_a_derived_cite_is_checked_all_the_way_down(tmp_path):
    """Break an OPERAND and the derived value fails with it.

    This is the property that makes a derived cite worth building: its
    operands are ordinary cites checked against their sources at step 5, so
    the arithmetic is checked against the artifacts rather than against
    itself.
    """
    after, before = _operands()
    delta = cl.derive(cl.DIFFERENCE, after, before)
    claim = _claim_with(delta)
    rows = {TO: {"recall_at_10": {"value": 0.99, "outcome": None}}}
    problems = cl.check(claim, rows)
    assert any("but the row says" in p for p in problems), problems


# --------------------------------------------------------- the refusals
def test_an_unknown_operation_is_refused_at_construction():
    after, before = _operands()
    with pytest.raises(cl.ClaimViolation) as e:
        cl.derive("sideways", after, before)
    assert "added deliberately" in str(e.value)


def test_an_unknown_operation_smuggled_past_derive_is_caught_by_check():
    after, before = _operands()
    smuggled = cl.Cite(member=TO, value=0.0123, op="sideways",
                       of=(after, before))
    assert any("unknown operation" in p
               for p in cl.check(_claim_with(smuggled)))


def test_the_operand_order_matters():
    """`a - b` is not `b - a`, and a cite that reverses them is wrong."""
    after, before = _operands()
    backwards = cl.Cite(member=TO, value=AFTER - BEFORE,
                        op=cl.DIFFERENCE, of=(before, after))
    assert cl.check(_claim_with(backwards)), (
        "a difference taken in the wrong order must not pass")


def test_a_derived_cite_over_the_wrong_number_of_operands_is_caught():
    after, before = _operands()
    lonely = cl.Cite(member=TO, value=0.0123, op=cl.DIFFERENCE, of=(after,))
    assert any("exactly two" in p for p in cl.check(_claim_with(lonely)))


def test_a_derived_cite_serialises_with_its_operands():
    after, before = _operands()
    d = cl.derive(cl.DIFFERENCE, after, before).as_dict()
    assert d["op"] == cl.DIFFERENCE
    assert [c["value"] for c in d["of"]] == [AFTER, BEFORE]


def test_an_ordinary_cite_is_unaffected():
    """Nothing about a cite with a source changes. Every existing claim in the
    project is one of these, and step 2 must be invisible to them."""
    plain = cl.Cite(member=TO, value=1.0, source="x.json:y")
    assert plain.derived is False
    assert "op" not in plain.as_dict()
