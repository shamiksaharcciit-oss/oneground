"""The evidence drawer (task 041, step 5).

The rules being tested are the reformulated step 5 — every claim gets an
entry, and every entry either resolves to a file and field or names which
non-field kind it is — plus the one that makes it worth having: an entry
whose cited figure and whose field disagree is named, not smoothed over.
"""
import json
import os

import pytest

from oneground.lab import citations, guard
from oneground.lab.receipt import draw_receipt
from oneground.lab.views.evidence import (KINDS, NAVIGABLE, EvidenceDrawerView,
                                          _agrees)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TIER1 = os.path.join(REPO, "runs", "arxiv-150k-via-characterize")
TIER2 = os.path.join(REPO, "runs", "041-ui", "support-tickets-2026q3")
#: The report as it was published before this task fixed its citations, kept
#: beside the runs rather than inside one: the browsing corpus should hold the
#: corrected report, and this is a regression fixture, not a run.
DEFECTIVE = os.path.join(REPO, "runs", "041-pre-fix-report.json")


def _draw(workdir, report_path=None):
    path = report_path or os.path.join(workdir, "report.json")
    if not os.path.isfile(path):
        pytest.skip(f"no local {path}")
    with open(path, encoding="utf-8") as f:
        report = json.load(f)
    return draw_receipt(EvidenceDrawerView(),
                        citations.resolve_citations(workdir, report))


def _entries(drawing):
    m = drawing.marks[1].data
    return [{k: v[i] for k, v in m.items()} for i in range(len(m["source"]))]


# ------------------------------------------------------- every claim, an entry
def test_every_claim_gets_an_entry_tier_one():
    d = _draw(TIER1)
    assert d.figures["n_claims"] == 37
    assert "entries" not in d.gaps, d.gaps
    claims = d.marks[0].data
    assert all(n >= 1 for n in claims["n_entries"])


def test_every_claim_gets_an_entry_tier_two():
    """Tier 2 records constraints rather than claims, and arrives in the same
    shape so the drawer draws one thing."""
    d = _draw(TIER2)
    assert d.figures["tier"] == 2
    assert d.figures["n_claims"] == 6
    assert all(n >= 1 for n in d.marks[0].data["n_entries"])


def test_a_claim_with_no_citation_at_all_is_a_gap_synthetic():
    doc = {"kind": "citations", "workdir": ".", "run": "r", "tier": 1,
           "claims": [{"index": 0, "kind": "scope", "text": "t",
                       "constraint": None, "outcome": None, "remedy": None,
                       "entries": []}]}
    d = draw_receipt(EvidenceDrawerView(), doc)
    assert "entries" in d.gaps
    assert d.gaps["entries"].startswith("couldnt_check")


# --------------------------------------------- the non-field kinds are visible
def test_the_non_field_kinds_are_not_navigable_and_say_what_they_are():
    """A reader who selects `(rule)` and gets an inert link learns that some
    citations are broken. One that is told it follows from a rule rather than
    from a row learns what a citation is."""
    entries = _entries(_draw(TIER1))
    by_kind = {}
    for e in entries:
        by_kind.setdefault(e["kind"], []).append(e)
    assert "rule" in by_kind, "the recommendation claim cites (rule)"
    for kind, got in by_kind.items():
        for e in got:
            if kind in NAVIGABLE:
                assert e["navigable"] is True and e["file"], e
            else:
                assert e["navigable"] is False, e
                assert e["note"], f"{kind} entry with no explanation: {e}"
    rule = by_kind["rule"][0]
    assert "rule" in rule["note"] and "row" in rule["note"], rule["note"]


def test_every_rendered_kind_is_one_the_view_declares():
    """No entry falls through to a default the page has not been designed
    for."""
    for wd in (TIER1, TIER2):
        for e in _entries(_draw(wd)):
            assert e["kind"] in KINDS, e


def test_the_requirements_file_is_its_own_kind_not_a_missing_receipt():
    entries = _entries(_draw(TIER1))
    req = [e for e in entries if e["kind"] == "requirements"]
    assert req, "the scope claim cites requirements:constraints"
    assert req[0]["navigable"] is False
    assert "input" in req[0]["note"]


def test_a_wildcard_is_named_rather_than_reported_as_broken():
    entries = _entries(_draw(TIER1))
    wild = [e for e in entries if e["kind"] == "every_option"]
    assert wild, "options[*] appears in this report"
    assert all("every option" in e["note"] for e in wild)


def test_a_source_naming_a_container_names_the_member_it_cited():
    entries = _entries(_draw(TIER1))
    within = [e for e in entries if e["kind"] == "within"]
    assert within, "p95_across_runs is cited by its min"
    for e in within:
        assert e["within"], e
        assert e["agrees"] is True


# ---------------------------------------------------------------- the point
def test_the_drawer_flags_a_citation_whose_field_holds_another_value():
    """The regression this whole drawer earned its place by finding.

    Against the report as it was published, four citations name
    `verify.json:load.completed` while carrying `load.achieved_qps`'s value.
    The drawer must say so rather than render 119.1 beside a field holding
    35731 without comment.
    """
    if not os.path.isfile(DEFECTIVE):
        pytest.skip("no copy of the pre-fix report on this machine")
    d = _draw(TIER1, DEFECTIVE)
    assert d.figures["disagreeing"], "the drawer missed the defect it found"
    assert set(d.figures["disagreeing"]) == {"verify.json:load.completed"}
    bad = [e for e in _entries(d) if e["agrees"] is False]
    assert len(bad) == 4
    for e in bad:
        assert e["cited_value"] != e["field_value"]
        assert e["navigable"] is True, "it resolves; it just disagrees"


def test_the_fixed_report_has_no_disagreeing_citation():
    assert _draw(TIER1).figures["disagreeing"] == []


def test_agrees_is_none_when_there_is_nothing_to_compare_synthetic():
    """None is not yes: a claim citing no value has nothing to compare, and
    saying so differs from saying the two matched."""
    assert _agrees("field", None, 5) is None
    assert _agrees("rule", None, None) is None
    assert _agrees("field", 5, 5) is True
    assert _agrees("field", 5, 6) is False
    assert _agrees("field", 1.0, 1.0 + 1e-12) is True
    assert _agrees("field", 119.1, {"a": 1}) is False


# ------------------------------------------------------------- couldn't-check
def test_every_couldnt_check_claim_carries_a_remedy():
    """Selecting a couldn't-check is meant to be the most informative click on
    the page, and a reason without a remedy ends in nothing to do."""
    for wd in (TIER1, TIER2):
        d = _draw(wd)
        assert d.figures["couldnt_check_claims"], wd
        assert d.figures["couldnt_check_without_remedy"] == [], wd


def test_a_report_wide_remedy_is_only_used_when_every_option_agrees_synthetic():
    report = {
        "run": "r", "schema": 1,
        "claims": [{"kind": "to_resolve", "constraint": "qps", "cites": [],
                    "source": "(rule)", "text": "t", "holds_for": [],
                    "subject": None, "asserts_outcome": None}],
        "options": [
            {"config": "a", "judgement": {"constraints": [
                {"constraint": "qps", "remedy": "do X",
                 "couldnt_check_kind": "k"}]}},
            {"config": "b", "judgement": {"constraints": [
                {"constraint": "qps", "remedy": "do Y",
                 "couldnt_check_kind": "k"}]}}]}
    doc = citations.resolve_citations(TIER1, report)
    assert doc["claims"][0]["remedy"] is None, \
        "two different remedies must not be summarised into one"
    report["options"][1]["judgement"]["constraints"][0]["remedy"] = "do X"
    doc = citations.resolve_citations(TIER1, report)
    assert doc["claims"][0]["remedy"]["remedy"] == "do X"
    assert doc["claims"][0]["remedy"]["scope"] == "every option"


# ------------------------------------------------------------------ the split
def test_transport_does_not_compare():
    """The comparison belongs to the view: transport carries both recorded
    values and decides nothing between them."""
    if not os.path.isdir(TIER1):
        pytest.skip("no local run")
    with open(os.path.join(TIER1, "report.json"), encoding="utf-8") as f:
        doc = citations.resolve_citations(TIER1, json.load(f))
    for c in doc["claims"]:
        for e in c["entries"]:
            assert "agrees" not in e and "navigable" not in e, e


def test_the_view_reads_every_path_it_declares():
    v = EvidenceDrawerView()
    d = _draw(TIER1)
    assert set(v.reads) - set(d.reads) == set()


def test_the_drawer_modules_pass_their_own_guard():
    assert guard.check_views() == {}
    assert guard.check_transport() == {}
    assert "citations.py" in guard.TRANSPORT_MODULES
    assert guard.unclassified_modules() == []
