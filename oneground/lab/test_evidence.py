"""The evidence drawer (task 041, step 5).

The rules being tested are the reformulated step 5 — every claim gets an
entry, and every entry either resolves to a file and field or names which
non-field kind it is — plus the one that makes it worth having: an entry
whose cited figure and whose field disagree is named, not smoothed over.
"""
import hashlib
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

# ---------------------------------------------------------- the regression pair
# Both sides are TRACKED, and the test that uses them fails rather than skips.
#
# The pre-fix report first lived at `runs/041-pre-fix-report.json`: gitignored,
# inside a worktree, and the test skipped without it. That is evidence held in
# a directory whose lifetime is shorter than the claim it supports — the shape
# the proposals stream named after nearly losing two artifacts — and it is
# worse here than usual, because the check that proves the drawer catches the
# published citation defect would have gone *quiet* rather than red. A
# regression fixture that can vanish is not a regression test.
#
# The workdir the citations resolve against is the published fixture's own
# bundle, which is tracked and whose `verify.json` is byte-identical to the
# run's. So the pair needs nothing outside the repository.

#: The published arxiv-150k bundle: characterization, simulate, verify,
#: verify_info and the CORRECTED report.
FIXTURE = os.path.join(REPO, "fixtures", "arxiv-150k", "report")

#: The same report as it was published BEFORE this task fixed its citations.
#: One field is sanitised — `price_table.path`, which recorded the absolute
#: path of the checkout that produced it and would fail the identifier scan.
DEFECTIVE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "testdata", "041-pre-fix-report.json")
DEFECTIVE_SHA256 = \
    "d2a314524089049b55a21693f52af9476f23b59d8a9ab02a7a6bd9fa5d2b8ac0"


def _draw(workdir, report_path=None, required=False):
    """`required=True` for anything tracked: it fails rather than skips.

    A local run under `runs/` may legitimately be absent on another machine,
    and a skip that names it is honest. A tracked fixture may not be, and a
    skip there would let the check that proves this drawer works go quiet
    instead of red — which is the whole reason the fixture is tracked.
    """
    path = report_path or os.path.join(workdir, "report.json")
    if not os.path.isfile(path):
        if required:
            raise AssertionError(
                f"{path} is tracked and is missing. This does not skip: "
                "without it the defect the drawer was built to catch would "
                "go unchecked.")
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
def test_the_regression_fixture_is_present_and_unmodified():
    """It fails rather than skips. A regression fixture that can vanish is
    not a regression test, and a silent skip on the check that proves the
    drawer works is worse than a failure: it goes quiet instead of red."""
    assert os.path.isfile(DEFECTIVE), (
        f"{DEFECTIVE} is missing. It is a tracked fixture, not a local "
        "artifact, and without it the defect this drawer was built to catch "
        "would go unchecked.")
    with open(DEFECTIVE, "rb") as f:
        got = hashlib.sha256(f.read()).hexdigest()
    assert got == DEFECTIVE_SHA256, (
        f"the pre-fix report has changed: {got} != {DEFECTIVE_SHA256}. It is "
        "a frozen record of what was published, and editing it would make "
        "the regression prove something else.")


def test_the_drawer_flags_a_citation_whose_field_holds_another_value():
    """The regression this whole drawer earned its place by finding.

    Against the report as it was published, four citations name
    `verify.json:load.completed` while carrying `load.achieved_qps`'s value.
    The drawer must say so rather than render 119.1 beside a field holding
    35731 without comment.

    Both sides are tracked and this does not skip.
    """
    d = _draw(FIXTURE, DEFECTIVE, required=True)
    assert d.figures["disagreeing"], "the drawer missed the defect it found"
    assert set(d.figures["disagreeing"]) == {"verify.json:load.completed"}
    bad = [e for e in _entries(d) if e["agrees"] is False]
    assert len(bad) == 4
    for e in bad:
        assert e["cited_value"] != e["field_value"]
        assert e["navigable"] is True, "it resolves; it just disagrees"


def test_the_published_fixture_has_no_disagreeing_citation():
    """The other half of the pair, on the same tracked bundle: the rebuilt
    report cites fields that hold the values it cites."""
    assert _draw(FIXTURE, required=True).figures["disagreeing"] == []


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
def test_every_couldnt_check_claim_carries_a_remedy_tracked():
    """The same rule, on a bundle that is in the repository.

    Task 045, finding 5. The version below reads workdirs under `runs/`. In CI
    there are none, so it skips and the suite is green; it is red only on a
    machine that happens to hold one. **A check that passes everywhere it runs,
    and only runs where nobody looks, reported nothing for as long as it
    existed** -- `docs/PRACTICE.md` section 2, warning 6.

    So the rule gets a tracked subject, and this one raises rather than skips.
    """
    d = _draw(FIXTURE, required=True)
    assert d.figures["couldnt_check_claims"]
    assert d.figures["couldnt_check_without_remedy"] == []


def test_every_couldnt_check_claim_carries_a_remedy():
    """Selecting a couldn't-check is meant to be the most informative click on
    the page, and a reason without a remedy ends in nothing to do.

    A report written before `couldnt_check_kind` and `remedy` existed cannot
    satisfy this and never could: the rule is about the code, and reading a
    stale artifact to judge it is measuring the wrong thing. The provenance
    block is the marker -- a report.json with no `oneground` key was produced
    before this build recorded one -- and the skip names the command that
    replaces it rather than passing quietly. The tracked case above is what
    keeps the rule from depending on any of this.
    """
    for wd in (TIER1, TIER2):
        path = os.path.join(wd, "report.json")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            if "oneground" not in json.load(f):
                pytest.skip(
                    "%s was written before the report recorded its own "
                    "provenance, so it predates `remedy` as well. Re-run "
                    "`oneground report` in that workdir to judge the current "
                    "code against it." % path)
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
