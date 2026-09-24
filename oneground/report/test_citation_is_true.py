"""The invariant checks that a cited field holds the cited value (045, #1).

**What this closes.** Task 019's invariant made every sentence a `Claim`
carrying the rows it cites, and `check()` verified that the sentence follows
from what it cites. It never opened the file a cite named. So a `Cite` could
carry `source="verify.json:load.completed"` and `value=119.1` while that field
held 35731, and the invariant, two other real-report tests, a published
fixture and the teaser all passed. The defect surfaced only when task 041
asked a UI to render the source and the value side by side.

Two such pairings existed in `verdict.py` and both were fixed in 041 as
one-line repairs. **The gap that let them through was not**, and this is it.

THE ACCEPTANCE IS A MUTANT, and it leads this file: reintroduce
`verdict.py:606`'s pairing and the invariant must fail, naming both numbers. A
check that passes on a healthy tree and was never watched fail is not evidence
(`docs/FAMILIES.md` section 4.1).
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.report import claims as cl                       # noqa: E402

MEMBER = "single_node_hnsw[M=32,efConstruction=200,efSearch=128]"


def _run(tmp_path, verify=None, report=None):
    """A workdir with the receipts a citation can name."""
    wd = tmp_path / "run"
    wd.mkdir(exist_ok=True)
    (wd / "verify.json").write_text(json.dumps(verify or {
        "environment_id": "pod-1",
        "load": {"completed": 35731, "achieved_qps": 119.1,
                 "offered": 60000},
        "searches": {"k=10_under_load": {"latency_shape_single_client": {
            "p95_ms": 317.41,
            "p95_across_runs": {"min": 316.87, "median": 317.41,
                                "max": 332.23}}}},
    }), encoding="utf-8")
    (wd / "report.json").write_text(json.dumps(report or {
        "options": [{"config": MEMBER, "judgement": {"outcome": "meets"}}],
        "costs": {MEMBER: {"monthly": 412.0}},
    }), encoding="utf-8")
    return str(wd)


def _claim(cite):
    return cl.Claim(kind="verify_metric", predicate="held", subject=MEMBER,
                    scope=(MEMBER,), holds_for=(MEMBER,), cites=(cite,))


# ========================================================== THE MUTANT
def test_the_mutant_verdict_606(tmp_path):
    """`verdict.py:606` as it was: a source naming `load.completed` while
    carrying `load.achieved_qps`'s value. The invariant must fail and must
    name both numbers."""
    wd = _run(tmp_path)
    mutant = cl.Cite(member=MEMBER, value=119.1,
                     source="verify.json:load.completed")
    problems = cl.check(_claim(mutant), workdir=wd)

    assert problems, "the mutant passed: the citation is still unchecked"
    joined = " ".join(problems)
    assert "119.1" in joined, joined
    assert "35731" in joined, joined
    assert "verify.json:load.completed" in joined, joined


def test_the_honest_pairing_passes(tmp_path):
    """The mirror. Without it the test above passes against a check that
    fails everything."""
    wd = _run(tmp_path)
    honest = cl.Cite(member=MEMBER, value=35731,
                     source="verify.json:load.completed")
    assert cl.check(_claim(honest), workdir=wd) == []


def test_the_mutant_verdict_670(tmp_path):
    """The second 041 defect: a source naming a key that never existed.

    `costs["config"]` was never a key -- the config label is, and `config` is
    the name of the field holding it. A source naming a field that is not
    there is a violation distinct from the four legitimate non-field shapes.
    """
    wd = _run(tmp_path)
    mutant = cl.Cite(member=MEMBER, value=412.0,
                     source="report.json:costs[config].monthly")
    problems = cl.check(_claim(mutant), workdir=wd)
    assert problems, "a source naming a key that does not exist passed"
    assert "not there" in " ".join(problems), problems


# =============================== the four shapes that are NOT violations
@pytest.mark.parametrize("source,why", [
    ("(rule)", "the conclusion follows from a rule, not a row"),
    ("requirements:constraints", "an input the user wrote"),
    ("report.json:options[*].outcome", "a wildcard over every option"),
    ("(not run)", "the stage was not run"),
])
def test_a_legitimate_non_field_source_is_not_a_violation(tmp_path, source,
                                                          why):
    """A check that failed these would be wrong three times to catch one."""
    wd = _run(tmp_path)
    c = cl.Cite(member=MEMBER, value=0.93, source=source)
    assert cl.check(_claim(c), workdir=wd) == [], why


def test_a_container_source_is_reported_as_under_specified(tmp_path):
    """The fourth shape, and it is neither a pass nor a plain mismatch.

    `p95_across_runs` holds min/median/max and a claim cites the min. The
    source is under-specified rather than wrong, and naming which member it
    is tells the author how to tighten it -- which "cited 316.87 but the file
    holds {...}" would not.
    """
    wd = _run(tmp_path)
    c = cl.Cite(
        member=MEMBER, value=316.87,
        source=("verify.json:searches[k=10_under_load]."
                "latency_shape_single_client.p95_across_runs"))
    problems = cl.check(_claim(c), workdir=wd)
    assert problems, "an under-specified source should still be reported"
    joined = " ".join(problems)
    assert "container" in joined and "'min'" in joined, joined


# ------------------------------------------------- it is not vacuous
def test_without_a_workdir_nothing_is_read(tmp_path):
    """Step 8 is optional for the same reason `rows` is, and its absence must
    be silent rather than a false pass that looks like a check."""
    mutant = cl.Cite(member=MEMBER, value=119.1,
                     source="verify.json:load.completed")
    assert cl.check(_claim(mutant)) == []


def test_a_missing_receipt_is_a_violation_not_a_skip(tmp_path):
    """A citation naming a file this run does not have is unresolved, and
    unresolved is a finding. Silently skipping it is how the gap reopens."""
    wd = _run(tmp_path)
    c = cl.Cite(member=MEMBER, value=1.0,
                source="simulate.json:rows[x].recall_at_10")
    problems = cl.check(_claim(c), workdir=wd)
    assert problems and "not in this run" in " ".join(problems), problems


def test_a_derived_cite_is_left_to_step_4b(tmp_path):
    """A difference has no path into the artifacts -- that is why derived
    cites exist and why step 4b recomputes them. Step 8 must not also demand
    a source for one."""
    wd = _run(tmp_path)
    after = cl.Cite(member=MEMBER, value=0.8623, source="(rule)")
    before = cl.Cite(member=MEMBER, value=0.8500, source="(rule)")
    d = cl.derive(cl.DIFFERENCE, after, before)
    assert cl.check(_claim(d), workdir=wd) == []
