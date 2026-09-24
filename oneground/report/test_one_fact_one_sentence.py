"""Task 045, finding 4: one fact, stated once, however many rows carry it.

Fifteen of the arXiv report's 37 claims were the same sentence -- *"<config>:
<constraint> was not compared across engines because fewer than two engines
produced a value"* -- differing only in the configuration and the constraint.
3,959 characters for one fact, against 3,659 for every claim in the report
that states a verdict. A reader arriving for the verdicts was outnumbered by a
restatement.

**The acceptance is the mutant, and the mutant is the obvious repair.**
Grouping those fifteen on the shape of the sentence collapses all fifteen into
one, and fourteen of them do cite the same thing: two engines, neither of
which produced a value. The fifteenth cites pgvector at 316.87 with `fails`.
One sentence over all fifteen therefore prints *pgvector (couldn't-check)* of
a row where pgvector produced a number -- a lent outcome, which is the defect
this module is named for, arriving at a new grain because of a change made to
tidy the page. `test_the_mutant_...` below is that collapse, and the invariant
has to refuse it.

Not synthetic: every test here reads `fixtures/arxiv-150k/report/`, which is
tracked, so the case fails for everyone or for no one.
"""

import json
import os

from .. import report as rep
from . import claims as cl
from . import verdict as vd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
WORKDIR = os.path.join(ROOT, "fixtures", "arxiv-150k", "report")

ODD_ROW = "single_node_hnsw[M=32,efConstruction=200,efSearch=128]"


def _report():
    with open(os.path.join(WORKDIR, "report.json"), encoding="utf-8") as f:
        return json.load(f)


def _options(doc):
    """The report's options, rebuilt as the objects that produced them."""
    out = []
    for o in doc["options"]:
        verdicts = [
            vd.Verdict(constraint=c["constraint"], outcome=c["outcome"],
                       reason=c.get("reason", ""), source=c.get("source", ""),
                       value=c.get("value"), threshold=c.get("threshold"),
                       kind=c.get("kind", "receipt"), engine=c.get("engine"),
                       couldnt_check_kind=c.get("couldnt_check_kind"),
                       remedy=c.get("remedy", ""))
            for c in o["judgement"]["constraints"]]
        out.append(vd.Option(
            family=o["family"], config=o["config"],
            params=o.get("params") or {},
            measurement=o.get("measurement") or {}, verdicts=verdicts,
            outcome=o["judgement"].get("outcome", vd.COULDNT_CHECK),
            engines_meeting=list(
                o["judgement"].get("engines_meeting") or ())))
    return out


def _no_comparison_rows(options):
    """Every `(config, constraint, verdicts)` the report has no comparison for.

    The same selection `compare_engine_claims` makes, spelled out here so a
    test can regroup the rows differently from the way the code does.
    """
    rows = []
    for opt in options:
        scoped = [v for v in opt.verdicts if v.engine is not None]
        if len({v.engine for v in scoped}) < 2:
            continue
        for constraint in dict.fromkeys(v.constraint for v in scoped):
            group = [v for v in scoped if v.constraint == constraint]
            usable = [v for v in group
                      if v.outcome != vd.COULDNT_CHECK and v.value is not None]
            if len(usable) < 2:
                rows.append((opt.config, constraint, tuple(group)))
    return rows


def _built(doc=None):
    doc = doc or _report()
    options = _options(doc)
    env_id = (doc.get("environment") or {}).get("id")
    with open(os.path.join(WORKDIR, "verify_info.json"), encoding="utf-8") as f:
        verify_info = json.load(f)
    return options, rep.compare_engine_claims(options, env_id, verify_info)


def _rows_of(claim):
    if claim.extra.get("collapsed"):
        return [(p.subject, p.constraint) for p in claim.parts]
    return [(claim.subject, claim.constraint)]


# --------------------------------------------------------------------------
# the acceptance
# --------------------------------------------------------------------------

def test_the_mutant_one_sentence_states_an_outcome_of_a_row_that_lacks_it():
    """The fifteen collapsed on the sentence rather than on what they cite.

    This is the repair anyone would reach for first, and the fifteenth row is
    why it is wrong. The test proves the defect is real before it proves the
    invariant catches it: a check that fires on a sentence nobody would have
    printed has caught nothing.
    """
    options, _ = _built()
    rows = _no_comparison_rows(options)
    assert len(rows) == 15, (
        "the arXiv report has 15 rows with no engine comparison; this one has "
        "%d, so the case below is not the case this test was written for"
        % len(rows))

    mutant = rep.no_comparison_claim(rows)

    # 1. The defect is real: the sentence states, of every one of the fifteen
    #    rows it names, an outcome one of them did not have.
    assert mutant.text, "the renderer produced nothing: the proof below would"\
                        " be vacuous"
    assert "pgvector (couldn't-check) in each" in mutant.text
    assert "%s: latency_p95" % ODD_ROW in mutant.text
    odd = [p for p in mutant.parts if p.subject == ODD_ROW]
    assert len(odd) == 1
    assert [(c.member, c.value, c.outcome) for c in odd[0].cites] == [
        ("qdrant", None, "couldnt_check"), ("pgvector", 316.8743, "fails")], (
        "the fifteenth row cites a pgvector value with `fails`; if it no "
        "longer does, this test is checking nothing")

    # 2. The invariant refuses it, and says which row disagrees.
    bad = cl.check(mutant, cl.rows_from_options(options))
    assert bad, "the collapse that lends an outcome was accepted"
    joined = " ".join(bad)
    assert "do not share it" in joined, joined
    assert ODD_ROW in joined, joined


# --------------------------------------------------------------------------
# what the code does instead
# --------------------------------------------------------------------------

def test_the_fifteen_become_three_and_state_the_same_fifteen_rows():
    doc = _report()
    options, built = _built(doc)
    now = [c for c in built if c.kind == "no_engine_comparison"]
    stored = [d for d in doc["claims"]
              if d.get("kind") == "no_engine_comparison"]

    assert len(stored) == 15
    assert len(now) == 3, [c.text[:60] for c in now]

    was = {(d["subject"], d["constraint"]) for d in stored}
    is_ = {pair for c in now for pair in _rows_of(c)}
    assert is_ == was, "rows dropped: %s; rows invented: %s" % (
        sorted(was - is_), sorted(is_ - was))

    # The point of the collapse, measured rather than asserted: 3,959
    # characters become 2,309 today, a 42% reduction over three sentences
    # instead of fifteen.
    #
    # It was 1,739 before the group was made to state its basis, and the 570
    # characters that bought back are the best-spent ones here: they say why
    # these rows are one row, which is the only thing that makes the collapse
    # checkable. The bound is a third rather than a half so that a longer
    # reason -- a better one -- does not fail a test about repetition.
    before = sum(len(d["text"]) for d in stored)
    after = sum(len(c.text) for c in now)
    assert after < before * 2 / 3, (before, after)


def test_the_row_that_cites_something_else_stays_its_own_sentence():
    """Substance, not shape. The fifteenth row is not collapsed with anything.

    Nor are the two hash_sharded rows merged with the twelve semantic_sharded
    ones: their engines and outcomes agree, and their `reason` does not -- one
    names a hash_sharded deployment and the other a semantic_sharded one. A
    sentence that carried neither would have dropped the only part of a
    couldn't-check a reader can use.
    """
    _, built = _built()
    now = [c for c in built if c.kind == "no_engine_comparison"]
    sizes = sorted(len(_rows_of(c)) for c in now)
    assert sizes == [1, 2, 12], sizes

    alone = [c for c in now if len(_rows_of(c)) == 1]
    assert len(alone) == 1
    assert alone[0].subject == ODD_ROW
    assert not alone[0].parts
    assert not alone[0].extra.get("collapsed")
    assert "pgvector (fails)" in alone[0].text

    families = [{p.subject.split("[")[0] for p in c.parts}
                for c in now if c.extra.get("collapsed")]
    assert all(len(f) == 1 for f in families), families


# --------------------------------------------------------------------------
# a collapse states what makes the group a group, once
# --------------------------------------------------------------------------

def test_the_collapsed_sentence_states_its_basis_exactly_once():
    """The ruling on finding 4's open question.

    Twelve rows sharing a reason and stating it **zero** times is the same
    defect as fifteen rows stating it fifteen times, approached from the other
    side. The grouping is itself a claim -- *these belong together because
    they share this* -- and a sentence that hides its own basis is harder to
    check than the repetition it replaced: a reader who cannot see why twelve
    rows belong together cannot see that a thirteenth does not.
    """
    _, built = _built()
    collapsed = [c for c in built
                 if c.kind == "no_engine_comparison"
                 and c.extra.get("collapsed")]
    assert collapsed

    for c in collapsed:
        assert c.detail, "the group states no basis: %s" % c.text[:80]
        core = c.detail.rstrip(".")
        assert c.text.count(core) == 1, (
            "the basis is stated %d times, and once is the point"
            % c.text.count(core))
        # It is the reason every row actually carries, not a summary of them.
        assert {x.reason for p in c.parts for x in p.cites} == {c.detail}
        # And it names the family that makes this group this group.
        assert c.parts[0].subject.split("[")[0] in c.detail

    # The two groups' bases differ, which is why they are two groups.
    assert len({c.detail for c in collapsed}) == len(collapsed)


def test_the_mutant_a_collapse_that_hides_its_basis_is_refused():
    """The rule, in the direction the first version of the collapse failed."""
    options, built = _built()
    c = [x for x in built if x.extra.get("collapsed")][0]
    rows = cl.rows_from_options(options)
    assert not cl.check(c, rows)

    c.detail = ""
    cl.render(c)
    bad = cl.check(c, rows)
    assert any("states no basis" in m for m in bad), bad


def test_the_mutant_a_collapse_that_states_a_basis_its_rows_lack_is_refused():
    """And in the other direction, because saying anything would satisfy the
    first rule as cheaply as saying nothing."""
    options, built = _built()
    c = [x for x in built if x.extra.get("collapsed")][0]
    c.detail = "because it was convenient to group them"
    cl.render(c)
    bad = cl.check(c, cl.rows_from_options(options))
    assert any("basis its rows do not carry" in m for m in bad), bad


def test_every_member_keeps_its_own_citation():
    """One sentence, but not one citation: each row still cites its own rows.

    Without this the collapse would be a summary rather than a claim, and
    nothing downstream could resolve the fifteenth row's 316.87 back to a
    receipt.
    """
    options, built = _built()
    by_row = {(cfg, con): verdicts
              for cfg, con, verdicts in _no_comparison_rows(options)}
    seen = 0
    for c in built:
        if c.kind != "no_engine_comparison" or not c.extra.get("collapsed"):
            continue
        for p in c.parts:
            want = by_row[(p.subject, p.constraint)]
            assert [(x.member, x.value, x.outcome, x.source) for x in p.cites]\
                == [(v.engine, v.value, v.outcome, v.source) for v in want]
            seen += 1
    assert seen == 14


# --------------------------------------------------------------------------
# the collapse does not supply its own truth condition
# --------------------------------------------------------------------------

def test_step_5b_still_derives_each_rows_membership_from_the_rows():
    """Move one row's outcome and the claim that stands in for it fails.

    The collapse's members are its parts, and a part carries its own subject
    and its own `asserts_outcome`, so 5b reaches that option's rows rather
    than the parent's. A collapsed claim whose membership were merely asserted
    would survive this.
    """
    options, built = _built()
    collapsed = [c for c in built
                 if c.kind == "no_engine_comparison"
                 and c.extra.get("collapsed")][0]
    rows = cl.rows_from_options(options)
    assert not cl.check(collapsed, rows), cl.check(collapsed, rows)

    victim = collapsed.parts[0]
    rows[victim.subject]["qdrant"][victim.constraint]["outcome"] = vd.MEETS
    bad = cl.check(collapsed, rows)
    assert bad, "a row's outcome moved and the sentence over it did not care"
    assert any("the rows say" in m for m in bad), bad


def test_a_collapse_over_one_row_is_refused():
    """A sentence that stands in for one row is that row's sentence.

    `no_comparison_claim` never builds one; the invariant refuses it anyway,
    because `collapsed` is a promise about the shape and a promise no check
    reads is decoration.
    """
    options, _ = _built()
    rows = _no_comparison_rows(options)
    one = rep.no_comparison_claim([rows[0]])
    assert not one.extra.get("collapsed")

    one.extra["collapsed"] = True
    bad = cl.check(one, cl.rows_from_options(options))
    assert any("part(s)" in m for m in bad), bad


def test_a_row_added_to_holds_for_without_a_part_is_refused():
    options, built = _built()
    collapsed = [c for c in built
                 if c.kind == "no_engine_comparison"
                 and c.extra.get("collapsed")][0]
    collapsed.scope = collapsed.scope + ("invented[]: qps",)
    collapsed.holds_for = collapsed.holds_for + ("invented[]: qps",)
    bad = cl.check(collapsed, cl.rows_from_options(options))
    assert any("its parts are" in m for m in bad), bad


# --------------------------------------------------------------------------
# step 8 reaches the parts, and is silent when it cannot run
# --------------------------------------------------------------------------

def test_step_8_reads_the_source_a_part_cites():
    """Finding 1's check has to follow the citations finding 4 moved.

    The engine facts used to sit on the claim; after the collapse they sit on
    its parts. A step 8 that only read `claim.cites` would have gone quiet on
    fourteen rows of the arXiv report on the day this landed, and nothing
    would have said so.
    """
    options, built = _built()
    collapsed = [c for c in built
                 if c.kind == "no_engine_comparison"
                 and c.extra.get("collapsed")][0]
    part = collapsed.parts[0]
    part.cites = (cl.Cite(
        member="pgvector", value=999.0, constraint=part.constraint,
        outcome="fails",
        source="verify.json:searches[k=10_under_load]."
               "latency_shape_single_client.p95_across_runs.min"),)

    bad = cl.check(collapsed, None, workdir=WORKDIR)
    assert any("999.00" in m and "316.87" in m for m in bad), bad


def test_without_a_workdir_the_citation_check_is_silent_not_passing():
    """The absence is an absence. Task 045's carry-forward.

    A conditional check reports nothing when its input is missing, and the
    cheap half of the coverage rule is a test that says so out loud -- so that
    "no problems" and "not looked" cannot be read as the same result.
    """
    options, built = _built()
    collapsed = [c for c in built
                 if c.kind == "no_engine_comparison"
                 and c.extra.get("collapsed")][0]
    collapsed.parts[0].cites = (cl.Cite(
        member="pgvector", value=999.0,
        constraint=collapsed.parts[0].constraint, outcome="couldnt_check",
        source="verify.json:searches[k=10_under_load]."
               "latency_shape_single_client.p95_across_runs.min"),)

    quiet = cl.check(collapsed, None)
    assert not any("999.00" in m for m in quiet), quiet

    loud = cl.check(collapsed, None, workdir=WORKDIR)
    assert any("999.00" in m for m in loud), loud
