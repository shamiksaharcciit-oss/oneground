"""Task 045, finding 5: a couldn't-check whose remedy restates the obstacle.

The remedy is the only part of a couldn't-check a reader can act on. Two
claims in the arXiv report read

    To decide latency_p95: this configuration was not the one verified --
    the verify run built hnsw in a single namespace, which is not a
    hash_sharded deployment.

which begins with the grammar of an instruction and never becomes one. What
follows the colon is the obstacle. **That is worse than a blank**, because a
blank is obviously missing: a reader skimming, and a reviewer checking that
remedies exist, both see a sentence shaped like an action.

**The acceptance is the mutant, and there are two of them**, because the
finding has two halves and they fail in the same direction:

  * `test_the_mutant_the_action_in_the_reason_field` -- the action written
    into `reason` where nothing looking for a remedy finds it. Right words,
    wrong field.
  * `test_the_mutant_a_reason_wearing_a_remedys_opening_words` -- the
    fall-through sentence. Right shape, wrong content.

A check that asks *is there a remedy?* answers yes to both, which is why
neither was caught by the one that existed.

Synthetic inputs, real rules: every verdict below comes out of `verdict.py`
rather than being written by hand, so a rule that stops setting a remedy
fails here.
"""

import ast
import json
import os

from . import claims as cl
from . import verdict as vd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
FIXTURE = os.path.join(ROOT, "fixtures", "arxiv-150k", "report")

HASH_SHARDED = {"config": "hash_sharded[M=32,efSearch=96,shards=3]",
                "family": "hash_sharded", "params": {}}
BUILT_SOMETHING_ELSE = {"engine_facts": {"index_type": "hnsw",
                                         "index_params": {"m": 32}}}


# --------------------------------------------------------------------------
# the two mutants
# --------------------------------------------------------------------------

def test_the_mutant_a_reason_wearing_a_remedys_opening_words():
    """The sentence the finding is named for, and what replaces it.

    The mutant is the old fall-through: `"To decide %s: %s" % (name, reason)`.
    It is reproduced here rather than described, so the comparison is between
    two strings this repository can produce and not between a claim and a
    memory of one.
    """
    v = vd.latency_p95(HASH_SHARDED, {"searches": {}},
                       {"latency": {"p95_ms": 40}},
                       verify_info=BUILT_SOMETHING_ELSE)
    assert v.outcome == vd.COULDNT_CHECK
    assert v.reason.startswith("this configuration was not the one verified")

    mutant = "To decide %s: %s." % (v.constraint, v.reason)
    # The defect is real: the sentence opens as an instruction and every word
    # after the colon is the obstacle.
    assert mutant.startswith("To decide latency_p95:")
    assert v.reason in mutant

    now = cl.how_to_resolve(v.constraint, v)
    assert now != mutant
    assert v.reason not in now, (
        "the sentence still ends in the obstacle: %s" % now)
    # It names what to do, and what to build.
    assert "oneground verify" in now
    assert "hash_sharded" in now


def test_the_mutant_the_action_in_the_reason_field():
    """An action recorded where nothing looking for a remedy will find it.

    `latency_p95`'s no-verify-run rule used to end its reason with *"run
    `oneground verify` against a real engine"*. The sentence a reader saw was
    fine. Every check that asked whether a remedy existed said no, and every
    reader who checked the prose said yes, so the disagreement was invisible
    from both sides.
    """
    v = vd.latency_p95({"config": "c", "family": "single_node_hnsw"}, None,
                       {"latency": {"p95_ms": 40}})
    assert v.outcome == vd.COULDNT_CHECK

    # The obstacle stays in `reason` and the action is not in it any more.
    assert "no verify run" in v.reason
    assert "oneground verify" not in v.reason, (
        "the action is back in the reason: %s" % v.reason)
    # It is in the field a reader, a renderer and a check all look in.
    assert "oneground verify" in v.remedy
    assert v.couldnt_check_kind == vd.NOT_VERIFIED


# --------------------------------------------------------------------------
# the routing
# --------------------------------------------------------------------------

def test_every_kind_that_carries_a_remedy_is_routed():
    """Routing on the presence of the remedy, not on a list of two kinds.

    `not_verified` was the third kind and the only one whose remedy is always
    an action, and it was the one the list left out -- so filling the field in
    would have changed nothing until this changed too.
    """
    for kind in (vd.NOT_VERIFIED, vd.NOT_VERIFIABLE_HERE,
                 "coverage_unresolved", "a_kind_invented_next_year", None):
        v = vd.Verdict("latency_p95", vd.COULDNT_CHECK, "the obstacle",
                       couldnt_check_kind=kind, remedy="do the thing")
        assert cl.how_to_resolve("latency_p95", v) == \
            "To decide latency_p95: do the thing.", kind


def test_with_no_remedy_recorded_the_absence_is_the_sentence():
    """A blank is obviously missing; a sentence shaped like an action is not.

    So when nothing is recorded the claim says that, in those words, instead
    of borrowing a remedy's opening clause for the obstacle.
    """
    v = vd.Verdict("recall_at_k", vd.COULDNT_CHECK, "the sweep row is empty")
    out = cl.how_to_resolve("recall_at_k", v)
    assert not out.startswith("To decide")
    assert "no remedy for it is recorded" in out
    assert "the sweep row is empty" in out


def test_every_constraint_a_couldnt_check_can_reach_carries_a_remedy():
    """The larger half: routing covered two constraints out of six.

    `classify_couldnt_checks` runs over `ENGINE_CONSTRAINTS` alone, which is
    right -- it asks whether an engine can build an index family, and that
    question is meaningless for a recall figure the sweep did not report. What
    was wrong is that it was the ONLY place a remedy was ever set, so the four
    constraints outside it reached a reader with no kind, no remedy and a
    fall-through sentence restating the obstacle.

    Each case below is produced by the rule that produces it in a real run.
    """
    cases = {
        "recall_at_k": vd.recall_floor(
            {"config": "c", "recall_at_5": 0.9},
            {"recall_at_k": {"min": 0.9, "k": 10}}),
        "storage_amplification": vd.storage_amplification(
            {"config": "c"}, {"storage_amplification_max": 2.0}),
        "memory_budget": vd.memory_budget(
            {"config": "c"}, {"memory_budget_gb": 8}),
        "monthly_budget": vd.monthly_budget(
            {"config": "c"},
            {"monthly_budget": {"amount": 1200, "currency": "EUR"}}),
        "monthly_budget (unpriced row)": vd.monthly_budget_from_cost(
            {"config": "c"}, {"monthly_budget": {"amount": 1200}}, {}),
        "latency_p95": vd.latency_p95(
            {"config": "c", "family": "single_node_hnsw"}, None,
            {"latency": {"p95_ms": 40}}),
        "qps": vd.qps_target(
            {"config": "c", "family": "single_node_hnsw"}, {"searches": {}},
            {"latency": {"at_qps": 200}}),
    }
    assert set(cases) - {"monthly_budget (unpriced row)"} <= set(
        vd.ENGINE_CONSTRAINTS + vd.OFF_ENGINE_CONSTRAINTS), (
        "a constraint this test drives is in neither set, so nothing records "
        "whether the coverage routing is meant to reach it")
    for name, v in cases.items():
        assert v is not None and v.outcome == vd.COULDNT_CHECK, name
        assert v.remedy, "%s: no remedy recorded" % name
        assert v.couldnt_check_kind, "%s: no kind recorded" % name
        sentence = cl.how_to_resolve(v.constraint, v)
        assert sentence.startswith("To decide %s:" % v.constraint), name
        assert v.reason.rstrip(".") not in sentence, (
            "%s: the sentence is still the obstacle" % name)


def test_every_couldnt_check_verdict_in_the_module_records_a_remedy():
    """Derived from the source, so a new rule cannot be written without one.

    The list of cases above is a list somebody maintains, and a check whose
    subject is a list is a check that falls behind the code the first time
    nobody remembers it -- which is how `not_verified` kept an empty remedy
    from task 034 to task 045. This walks every `Verdict(..., COULDNT_CHECK,
    ...)` in `verdict.py` instead, so the rule applies to sites that do not
    exist yet.
    """
    with open(vd.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    bad = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Verdict"):
            continue
        if not any(isinstance(a, ast.Name) and a.id == "COULDNT_CHECK"
                   for a in node.args):
            continue
        kws = {k.arg for k in node.keywords}
        missing = {"remedy", "couldnt_check_kind"} - kws
        if missing:
            bad.append((node.lineno, sorted(missing)))
    assert not bad, (
        "couldn't-check verdicts built without %s: %s. A reason without a "
        "remedy ends in nothing to do, and the field is the only place a "
        "reader, a renderer or a check looks."
        % ("a remedy or a kind", bad))


def test_the_coverage_routing_still_wins_where_it_applies():
    """A construction-site remedy does not displace the coverage decision.

    An engine that cannot build the family is a deeper obstacle than the run
    that was not made, and 034's classification is what knows it. This is the
    order, asserted, so a later edit cannot quietly invert it.
    """
    from oneground.adapters import index_families as IF

    row = {"config": "c", "family": "single_node_hnsw",
           "params": {"index": "ivf_pq"}}
    opt = vd.judge_option(row, None,
                          {"latency": {"p95_ms": 40}},
                          coverages=[IF.unresolved("qdrant", "nobody asked")])
    v = [x for x in opt.verdicts if x.constraint == "latency_p95"][0]
    assert v.couldnt_check_kind == IF.COVERAGE_UNRESOLVED, v.as_dict()
    assert "oneground adapters coverage" in v.remedy
    assert "To decide latency_p95: qdrant has not been asked" in \
        cl.how_to_resolve("latency_p95", v)


# --------------------------------------------------------------------------
# tracked, so it fails for everyone or for no one
# --------------------------------------------------------------------------

def _fixture(name):
    p = os.path.join(FIXTURE, name)
    if not os.path.isfile(p):
        raise AssertionError(
            "%s is tracked and is missing. This does not skip: without it the "
            "routing goes unchecked wherever `runs/` is empty." % p)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _judged(coverages):
    report, simulate = _fixture("report.json"), _fixture("simulate.json")
    verify, verify_info = _fixture("verify.json"), _fixture("verify_info.json")
    return [vd.judge_option(r, verify, report["constraints"],
                            verify_env=(verify_info or {}).get("environment"),
                            costs=report.get("costs") or None,
                            verify_info=verify_info, coverages=coverages)
            for r in simulate["rows"]]


def test_the_tracked_bundle_exercises_the_mismatch_branch():
    """The branch finding 5 is about, driven by tracked receipts.

    **Not `not_verifiable_here`, and not `coverage_unresolved`.** Both already
    routed and already carried a remedy before this task, so a case built on
    either passes the day it is written and proves that a different branch was
    taken. The branch that was unrouted is the `else` -- `not_verified` -- and
    the arXiv bundle reaches it: its simulated architectures are sharded and
    the verify run built one hnsw namespace, so `verified_config_mismatch`
    fires on every row.

    `coverages=None` is how a run with no adapter coverage judges, and it is
    what isolates the branch: with coverages present the classification
    afterwards replaces the kind with `coverage_unresolved`, which is the
    reason a regenerated report hides this rather than resolving it.

    `fixtures/arxiv-150k/report/` is tracked, so this raises rather than
    skips, and it judges the rows now rather than reading the report.json
    written before the change -- which would measure the artifact, not the
    code.
    """
    options = _judged(coverages=None)
    mismatched = [(o.config, v) for o in options for v in o.verdicts
                  if v.outcome == vd.COULDNT_CHECK
                  and v.reason.startswith("this configuration was not the one "
                                          "verified")]
    assert len(mismatched) >= 15, (
        "the tracked bundle stopped exercising the mismatch branch; this test "
        "is then checking a branch nobody reaches (%d rows)" % len(mismatched))
    for config, v in mismatched:
        assert v.couldnt_check_kind == vd.NOT_VERIFIED, (config, v.as_dict())
        assert v.remedy, (config, v.as_dict())
        sentence = cl.how_to_resolve(v.constraint, v)
        assert v.reason.rstrip(".") not in sentence, sentence
        assert "oneground verify" in sentence, sentence
        assert config.split("[")[0] in sentence, (
            "the remedy does not name the family that has to be built: %s"
            % sentence)


def test_the_tracked_arxiv_bundle_routes_every_couldnt_check():
    """And with the coverage this run records, nothing is left unrouted."""
    verify = _fixture("verify.json")
    options = _judged(vd.coverages_from(verify, FIXTURE))
    unchecked = [v for opt in options for v in opt.verdicts
                 if v.outcome == vd.COULDNT_CHECK]
    assert unchecked, "the arXiv report has couldn't-checks; this one has none"
    bare = [(o.config, v.constraint) for o in options for v in o.verdicts
            if v.outcome == vd.COULDNT_CHECK and not v.remedy]
    assert bare == [], bare
    for v in unchecked:
        assert v.couldnt_check_kind, v.as_dict()
        assert cl.how_to_resolve(v.constraint, v).startswith("To decide ")
