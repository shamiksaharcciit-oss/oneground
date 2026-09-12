"""Tests for the verdict rules and the rendered report.

**Synthetic rows throughout.** These check the rules, not any corpus: every
branch of every constraint, the overall-outcome rule, indistinguishability,
not-run, ranking, and the two properties the house rules turn on —

    couldn't-check is never rounded up
    no latency verdict is ever derived from a simulated number

    python oneground/report/test_verdict.py
    pytest oneground/report/test_verdict.py
"""

import io
import json
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.report import verdict as vd  # noqa: E402
from oneground.report import html as rhtml  # noqa: E402

MEETS, FAILS, CC = vd.MEETS, vd.FAILS, vd.COULDNT_CHECK


def row(config="single_node_hnsw[M=32]", family="single_node_hnsw",
        recall10=0.99, ampl=1.0, mem=6.7e6, fanout=1.0, **extra):
    d = {"family": family, "config": config, "params": {"M": 32},
         "recall_at_1": recall10, "recall_at_10": recall10,
         "recall_at_100": recall10, "ceiling_at_10": 1.0,
         "storage_amplification": ampl, "est_memory_bytes": mem,
         "fanout": fanout}
    d.update(extra)
    return d


def verify_ok(p95=12.0, k=10):
    return {"searches": {f"k={k}": {
        f"recall_at_{k}": 0.99,
        "latency_shape_single_client": {"p50_ms": 5.0, "p95_ms": p95,
                                        "p99_ms": p95 * 1.2, "mean_ms": 6.0,
                                        "n_queries": 200, "concurrency": 1,
                                        "note": "not throughput"}}}}


def verify_noisy(k=10):
    return {"searches": {f"k={k}": {
        f"recall_at_{k}": 0.99,
        "latency_shape_single_client":
            "couldnt_check: environment noise -- the baseline RTT p95 is 132% "
            "of the query p95"}}}


# ---------------------------------------------------------------- recall
def test_recall_meets_and_fails_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.95}}
    assert vd.recall_floor(row(recall10=0.99), c).outcome == MEETS
    assert vd.recall_floor(row(recall10=0.90), c).outcome == FAILS
    # exactly on the floor meets: the constraint is ">= min"
    assert vd.recall_floor(row(recall10=0.95), c).outcome == MEETS


def test_recall_not_asked_for_produces_no_row_synthetic():
    """An unasked-for constraint is not a check that could not be made."""
    assert vd.recall_floor(row(), {}) is None
    assert vd.storage_amplification(row(), {}) is None
    assert vd.memory_budget(row(), {}) is None
    assert vd.latency_p95(row(), verify_ok(), {}) is None


def test_recall_at_an_unmeasured_k_is_couldnt_check_synthetic():
    v = vd.recall_floor(row(), {"recall_at_k": {"k": 50, "min": 0.9}})
    assert v.outcome == CC
    assert "recall_at_50" in v.reason


def test_every_verdict_names_its_source_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.9},
         "storage_amplification_max": 2.0, "memory_budget_gb": 1.0,
         "latency": {"p95_ms": 40}}
    opt = vd.judge_option(row(), verify_ok(), c)
    for v in opt.verdicts:
        assert v.source, f"{v.constraint} has no source"


# --------------------------------------------------------------- storage
def test_storage_meets_and_fails_synthetic():
    c = {"storage_amplification_max": 2.0}
    assert vd.storage_amplification(row(ampl=1.0), c).outcome == MEETS
    assert vd.storage_amplification(row(ampl=2.0), c).outcome == MEETS
    assert vd.storage_amplification(row(ampl=3.72), c).outcome == FAILS


def test_memory_verdict_says_it_is_an_estimate_synthetic():
    v = vd.memory_budget(row(mem=6.7e6), {"memory_budget_gb": 1.0})
    assert v.outcome == MEETS
    assert "estimate" in v.reason and "not observed RSS" in v.reason
    assert "estimate" in v.kind


def test_memory_fails_when_over_budget_synthetic():
    v = vd.memory_budget(row(mem=2.0e9), {"memory_budget_gb": 1.0})
    assert v.outcome == FAILS


# --------------------------------------------------------------- latency
def test_latency_meets_and_fails_from_a_verify_row_synthetic():
    c = {"latency": {"p95_ms": 40}}
    assert vd.latency_p95(row(), verify_ok(12.0), c).outcome == MEETS
    assert vd.latency_p95(row(), verify_ok(90.0), c).outcome == FAILS


def test_latency_is_couldnt_check_without_a_verify_run_synthetic():
    v = vd.latency_p95(row(), None, {"latency": {"p95_ms": 40}})
    assert v.outcome == CC
    assert "never taken from simulation" in v.reason


def test_latency_is_couldnt_check_when_verify_refused_to_attribute_synthetic():
    v = vd.latency_p95(row(), verify_noisy(), {"latency": {"p95_ms": 40}})
    assert v.outcome == CC
    assert "environment noise" in v.reason


def test_latency_is_couldnt_check_at_a_different_k_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.9}, "latency": {"p95_ms": 40}}
    v = vd.latency_p95(row(), verify_ok(k=100), c)
    assert v.outcome == CC and "k=10" in v.reason


def test_latency_is_couldnt_check_in_the_wrong_environment_synthetic():
    c = {"latency": {"p95_ms": 40, "environment": "production"}}
    v = vd.latency_p95(row(), verify_ok(5.0), c, verify_env="local")
    assert v.outcome == CC
    assert "measured on local" in v.reason
    assert "constraint targets production" in v.reason


def test_NO_LATENCY_VERDICT_IS_EVER_DERIVED_FROM_SIMULATION_synthetic():
    """The acceptance criterion, asserted directly.

    A simulate row carrying every plausible latency-shaped field, and no
    verify data at all, must still yield couldnt_check -- not a verdict
    invented from the simulator's timings.
    """
    sim = row(query_seconds=0.0001, build_seconds=1.0,
              latency_p95_ms=0.5, p95_ms=0.5,
              latency_shape_single_client={"p95_ms": 0.5})
    v = vd.latency_p95(sim, None, {"latency": {"p95_ms": 40}})
    assert v.outcome == CC, (
        "a latency verdict was produced from a simulate row: " + v.reason)
    assert v.value is None, "a simulated latency value leaked into the verdict"


def test_a_simulate_only_workdir_leaves_every_option_couldnt_check_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.9}, "latency": {"p95_ms": 40}}
    opts = [vd.judge_option(row(config="a"), None, c),
            vd.judge_option(row(config="b"), None, c)]
    assert all(o.outcome == CC for o in opts)
    assert vd.recommend(opts) is None


# ------------------------------------------------------- overall outcome
def test_overall_fails_beats_couldnt_check_synthetic():
    """A provably broken constraint decides, even with unknowns present."""
    vs = [vd.Verdict("a", FAILS, ""), vd.Verdict("b", CC, "")]
    assert vd.overall(vs) == FAILS


def test_overall_meets_only_when_every_constraint_meets_synthetic():
    assert vd.overall([vd.Verdict("a", MEETS, ""),
                       vd.Verdict("b", MEETS, "")]) == MEETS
    assert vd.overall([vd.Verdict("a", MEETS, ""),
                       vd.Verdict("b", CC, "")]) == CC


def test_no_constraints_is_couldnt_check_not_meets_synthetic():
    """Nothing judged is not the same as everything passing."""
    assert vd.overall([]) == CC
    assert vd.judge_option(row(), None, {}).outcome == CC


def test_couldnt_check_is_never_rounded_up_synthetic():
    """The house rule, end to end: an option with one unknown constraint is
    never recommended, however good the rest of it is."""
    c = {"recall_at_k": {"k": 10, "min": 0.9}, "latency": {"p95_ms": 40}}
    opt = vd.judge_option(row(recall10=1.0), verify_noisy(), c)
    assert opt.outcome == CC
    assert vd.recommend([opt]) is None


# --------------------------------------------------- indistinguishability
def test_indistinguishable_within_tolerance_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.9}}
    a = vd.judge_option(row(config="a", recall10=0.9984), None, c)
    b = vd.judge_option(row(config="b", recall10=0.9976), None, c)
    vd.mark_indistinguishable([a, b])
    assert b.config in a.indistinguishable_from
    assert a.config in b.indistinguishable_from


def test_distinguishable_outside_tolerance_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.5}}
    a = vd.judge_option(row(config="a", recall10=0.99), None, c)
    b = vd.judge_option(row(config="b", recall10=0.93), None, c)
    vd.mark_indistinguishable([a, b])
    assert not a.indistinguishable_from and not b.indistinguishable_from


def test_failed_options_are_not_marked_indistinguishable_synthetic():
    """A failing option is out; comparing its recall to a contender's would
    invite reading it as still in the running."""
    c = {"recall_at_k": {"k": 10, "min": 0.95},
         "storage_amplification_max": 2.0}
    good = vd.judge_option(row(config="good", recall10=0.99, ampl=1.0),
                           None, c)
    bad = vd.judge_option(row(config="bad", recall10=0.991, ampl=9.0), None, c)
    assert bad.outcome == FAILS
    vd.mark_indistinguishable([good, bad])
    assert bad.config not in good.indistinguishable_from


# ---------------------------------------------------------------- not run
def test_not_run_families_are_listed_with_a_reason_synthetic():
    opts = [vd.judge_option(row(family="single_node_hnsw"), None,
                            {"recall_at_k": {"k": 10, "min": 0.9}})]
    rows = vd.not_run(["single_node_hnsw", "hash_sharded"], opts,
                      dropped=[{"config": "hash_sharded[shards=3]",
                                "reason": "couldnt_check: budget",
                                "rule": "max_minutes=45 elapsed"}])
    assert len(rows) == 1
    assert rows[0]["family"] == "hash_sharded"
    assert "budget" in rows[0]["reason"] and "max_minutes" in rows[0]["reason"]
    assert rows[0]["outcome"] == CC


def test_not_run_without_a_recorded_reason_says_so_synthetic():
    rows = vd.not_run(["hash_sharded"], [], dropped=[])
    assert "recorded no reason" in rows[0]["reason"]


# --------------------------------------------------------------- ranking
def test_at_margin_detects_a_narrow_pass_synthetic():
    tight = vd.Verdict("recall_at_k", MEETS, "", value=0.905, threshold=0.90)
    roomy = vd.Verdict("recall_at_k", MEETS, "", value=0.999, threshold=0.90)
    assert vd.at_margin(tight)
    assert not vd.at_margin(roomy)
    # lower-is-better constraints work the other way round
    assert vd.at_margin(vd.Verdict("storage_amplification", MEETS, "",
                                   value=1.95, threshold=2.0))
    assert not vd.at_margin(vd.Verdict("storage_amplification", MEETS, "",
                                       value=1.0, threshold=2.0))


def test_at_margin_never_applies_to_a_non_meets_verdict_synthetic():
    assert not vd.at_margin(vd.Verdict("x", FAILS, "", value=1, threshold=2))
    assert not vd.at_margin(vd.Verdict("x", CC, "", value=None, threshold=2))


def test_recommendation_prefers_room_then_storage_then_fanout_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.90},
         "storage_amplification_max": 4.0}
    roomy = vd.judge_option(row(config="roomy", recall10=0.999, ampl=1.0,
                                fanout=3), None, c)
    tight = vd.judge_option(row(config="tight", recall10=0.905, ampl=1.0,
                                fanout=1), None, c)
    assert vd.recommend([tight, roomy]).config == "roomy"

    # same margins -> lower storage wins
    a = vd.judge_option(row(config="a", recall10=0.999, ampl=2.0, fanout=1),
                        None, c)
    b = vd.judge_option(row(config="b", recall10=0.999, ampl=1.0, fanout=3),
                        None, c)
    assert vd.recommend([a, b]).config == "b"


def test_only_meets_options_are_recommended_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.95}}
    fail = vd.judge_option(row(config="f", recall10=0.5), None, c)
    assert vd.recommend([fail]) is None


# ------------------------------------------------------------------ HTML
def _report_bundle(constraints, verify_data=None, verify_info=None,
                   history_path=None):
    from oneground import report as rep
    opts = [vd.judge_option(row(config="alpha", family="single_node_hnsw"),
                            verify_data, constraints),
            vd.judge_option(row(config="beta", family="semantic_sharded",
                                recall10=0.4, ampl=3.7), verify_data,
                            constraints)]
    vd.mark_indistinguishable(opts)
    nr = vd.not_run(["single_node_hnsw", "semantic_sharded", "hash_sharded"],
                    opts, [])
    rec = vd.recommend(opts)
    report = {
        "run": "html-test", "generated_at": "2026-09-11T00:00:00Z",
        "constraints": constraints,
        "environment": {"verify_target": None, "verify_platform": None},
        "calibration": rep._calibration_footer(
            verify_info, rec,
            history_path=(history_path or "does/not/exist/history.jsonl")),
        "summary": {"options": len(opts),
                    MEETS: sum(1 for o in opts if o.outcome == MEETS),
                    FAILS: sum(1 for o in opts if o.outcome == FAILS),
                    CC: sum(1 for o in opts if o.outcome == CC),
                    "not_run": len(nr)},
        "options": [o.as_dict() for o in opts],
        "not_run": nr,
        "recommendation": rec.config if rec else None,
        "decision_log": rep.decision_log(opts, nr, rec, constraints, None),
        "inputs": {"simulate.json": {"sha256": "a" * 64, "kind": "receipt"},
                   "build_info.json": {"sha256": "b" * 64,
                                       "kind": "declared"}},
    }
    return report, opts, nr, rec


def test_html_is_self_contained_and_offline_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.9}}
    report, opts, nr, rec = _report_bundle(c)
    page = rhtml.render_html(report, opts, nr, rec, None, None, None,
                             type("R", (), {"name": "html-test"})())
    low = page.lower()
    for bad in ("http://", "https://", "//cdn", "<script", "fonts.googleapis"):
        assert bad not in low, f"the report reaches out: {bad!r}"
    assert page.startswith("<!doctype html>")


def test_html_contains_the_receipt_table_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.9}}
    report, opts, nr, rec = _report_bundle(c)
    page = rhtml.render_html(report, opts, nr, rec, None, None, None,
                             type("R", (), {"name": "x"})())
    assert "Receipt" in page
    assert "a" * 64 in page and "b" * 64 in page
    assert "simulate.json" in page and "build_info.json" in page
    assert ">receipt<" in page and ">declared<" in page


def test_html_never_labels_a_couldnt_check_row_with_a_verdict_word_synthetic():
    """A couldn't-check cell must not read as meets or fails."""
    c = {"recall_at_k": {"k": 10, "min": 0.9}, "latency": {"p95_ms": 40}}
    report, opts, nr, rec = _report_bundle(c, verify_data=None)
    page = rhtml.render_html(report, opts, nr, rec, None, None, None,
                             type("R", (), {"name": "x"})())
    # Every couldnt_check *constraint* cell renders the escaped
    # "couldn't-check" label. Only constraint cells carry a title attribute,
    # so the pattern matches those and not the "not run" row -- and it stops
    # at the first "<" so it cannot run into the embedded ground image.
    assert "couldn&#39;t-check" in page
    import re
    cells = re.findall(r'<td class="v amber" title="[^"]*">([^<]*)<', page)
    assert cells, "no couldnt_check constraint cell was rendered"
    for cell in cells:
        text = cell.strip().lower()
        assert text.startswith("couldn"), (
            f"an amber constraint cell reads as a verdict: {text!r}")
    # "not run" is its own label and is not a verdict word.
    assert ">not run<" in page


def test_html_applies_the_design_tokens_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.9}}
    report, opts, nr, rec = _report_bundle(c)
    page = rhtml.render_html(report, opts, nr, rec, None, None, None,
                             type("R", (), {"name": "x"})())
    for token in ("#1B2432", "#243040", "#E7EAEF", "#8B96A5", "#C99A3B",
                  "#4FC1AD", "#E36C5E", "#D9A441"):
        assert token in page, f"design token {token} missing"
    assert "Space Grotesk" in page and "IBM Plex Mono" in page


def test_html_states_the_calibration_status_synthetic():
    """Task 012 replaced the placeholder with a citation. The contract is that
    the footer is never silent: with no history at all, it says so."""
    c = {"recall_at_k": {"k": 10, "min": 0.9}}
    report, opts, nr, rec = _report_bundle(c)
    page = rhtml.render_html(report, opts, nr, rec, None, None, None,
                             type("R", (), {"name": "x"})())
    assert "Calibration this report was generated under" in page
    assert "no calibration history" in page


def test_report_names_an_engine_with_no_calibration_line_synthetic(tmp_path):
    """The brief's wording: cite the latest line, or say `no calibration line
    for <engine>`. Never silent."""
    from oneground import report as rep
    from oneground.calibrate import history as H

    hp = str(tmp_path / "history.jsonl")
    H.append(H.make_line(check="simulator_vs_engine", dataset="d",
                         engine="qdrant", engine_version="1.19.1",
                         config="single_node_hnsw[M=32]", measured=0.99,
                         reference=0.99, tolerance=0.05,
                         definition="simulated - measured",
                         extra={"efSearch": 128}), hp)

    cal = rep._calibration_footer({"engine": "pgvector"}, None, history_path=hp)
    assert cal["engine_line"] is None
    assert any("no calibration line for pgvector" in s
               for s in cal["statements"])

    cal = rep._calibration_footer({"engine": "qdrant"}, None, history_path=hp)
    assert cal["engine_line"] is not None
    assert any("last calibrated" in s for s in cal["statements"])


def test_report_cites_the_family_curve_when_one_exists_synthetic(tmp_path):
    from oneground import report as rep
    from oneground.calibrate import history as H

    hp = str(tmp_path / "history.jsonl")
    H.append(H.make_line(check="glove_curve", dataset="glove-100-angular",
                         engine="oneground/single_node_hnsw",
                         engine_version="faiss-cpu 1.15.0",
                         config="single_node_hnsw[M=12,efConstruction=500,"
                                "efSearch=80]",
                         measured=0.70, reference=0.70371, tolerance=0.02,
                         definition="measured - reference"), hp)
    rec = type("Rec", (), {"config": "single_node_hnsw[M=32,efSearch=128]"})()
    cal = rep._calibration_footer({"engine": "qdrant"}, rec, history_path=hp)
    assert cal["family"] == "single_node_hnsw"
    assert cal["family_line"] is not None
    assert any("family single_node_hnsw" in s for s in cal["statements"])
    # and an unrelated family is stated as absent rather than omitted
    rec2 = type("Rec", (), {"config": "hash_sharded[M=32,shards=3]"})()
    cal2 = rep._calibration_footer({"engine": "qdrant"}, rec2, history_path=hp)
    assert any("no calibration line for hash_sharded" in s
               for s in cal2["statements"])


def test_html_lists_families_that_did_not_run_synthetic():
    c = {"recall_at_k": {"k": 10, "min": 0.9}}
    report, opts, nr, rec = _report_bundle(c)
    page = rhtml.render_html(report, opts, nr, rec, None, None, None,
                             type("R", (), {"name": "x"})())
    assert "hash_sharded" in page and "not run" in page


# --------------------------------------------- the ground is this run's own
def test_html_shows_no_ground_view_without_this_runs_projection_synthetic():
    """Task 010 embedded the published arxiv-150k image into every report,
    captioned "the ground" -- on the smoke report that was a picture of a
    different corpus. A report with no projection of its own says so."""
    import tempfile
    c = {"recall_at_k": {"k": 10, "min": 0.9}}
    report, opts, nr, rec = _report_bundle(c)
    with tempfile.TemporaryDirectory() as tmp:          # no projection.npy
        page = rhtml.render_html(report, opts, nr, rec, None, None, None,
                                 type("R", (), {"name": "x"})(), workdir=tmp)
    assert "data:image/png;base64," not in page, (
        "a report with no projection of its own embedded an image anyway")
    assert "no ground view here" in page
    assert "picture of something else" in page


def test_html_embeds_only_the_runs_own_projection_synthetic():
    import tempfile
    import numpy as np
    c = {"recall_at_k": {"k": 10, "min": 0.9}}
    report, opts, nr, rec = _report_bundle(c)
    with tempfile.TemporaryDirectory() as tmp:
        rng = np.random.default_rng(11)
        np.save(os.path.join(tmp, "projection.npy"),
                rng.normal(size=(400, 2)).astype("float32"))
        page = rhtml.render_html(report, opts, nr, rec, None, None, None,
                                 type("R", (), {"name": "x"})(), workdir=tmp)
    assert page.count("data:image/png;base64,") == 1
    assert "this run" in page.lower()
    assert "no ground view here" not in page


def test_no_published_image_path_is_referenced_anywhere_synthetic():
    """Guard the regression directly: nothing in the renderer may point at a
    file under docs/img."""
    import ast
    src = open(rhtml.__file__, encoding="utf-8").read()
    # Comments and docstrings may name the old file -- the history is worth
    # documenting. What must not exist is code that builds such a path, so the
    # check runs over string *literals* in the parsed module, not the text.
    tree = ast.parse(src)
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            d = ast.get_docstring(node)
            if d:
                docstrings.add(d)
    code_literals = [s for s in literals if s not in docstrings]
    for lit in code_literals:
        assert "ground_b_copies" not in lit, f"path to a published image: {lit!r}"
        assert lit != "img", "the renderer still builds a docs/img path"
    assert not hasattr(rhtml, "GROUND_IMAGE")


def _main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())


# ------------------------------------------------ 011 leftovers (task 013)
def _opt(config, outcome, verdicts):
    # The measurement carries what a simulate.json row always carries: the
    # recommendation log entry formats storage_amplification and fanout, and a
    # fixture without them tests a code path nobody runs.
    o = vd.Option(family=config.split("[")[0], config=config, params={},
                  measurement={"recall_at_10": 0.99,
                               "storage_amplification": 1.0,
                               "est_memory_bytes": 6.7e8, "fanout": 1.0},
                  verdicts=verdicts)
    o.outcome = outcome
    return o


def _v(name, outcome, reason="r"):
    return vd.Verdict(name, outcome, reason, source=f"verify.json:{name}")


def test_the_scope_entry_counts_the_constraints_actually_judged():
    """It said "4 constraint(s)" and omitted `qps` while every option carried
    five verdicts. The list was a hand-maintained set of `if` branches and
    task 011 added a verdict without adding a branch."""
    from oneground import report as rep
    opts = [_opt("single_node_hnsw[M=32]", vd.MEETS, [
        _v("recall_at_k", vd.MEETS), _v("storage_amplification", vd.MEETS),
        _v("latency_p95", vd.MEETS), _v("qps", vd.MEETS),
        _v("monthly_budget", vd.MEETS)])]
    log = rep.decision_log(opts, [], opts[0], {}, None)
    scope = [e for e in log if e["kind"] == "scope"][0]["text"]
    assert "5 constraint(s)" in scope, scope
    assert "qps" in scope, scope


def test_the_scope_entry_follows_the_verdicts_not_a_hand_list():
    """A verdict added in future is counted without editing anything."""
    from oneground import report as rep
    opts = [_opt("x[M=1]", vd.MEETS, [_v("recall_at_k", vd.MEETS),
                                      _v("some_future_constraint", vd.MEETS)])]
    log = rep.decision_log(opts, [], opts[0], {}, None)
    scope = [e for e in log if e["kind"] == "scope"][0]["text"]
    assert "2 constraint(s)" in scope, scope
    assert "some_future_constraint" in scope, scope


def test_the_declared_list_now_includes_qps():
    """The pre-flight log line runs before any option exists and still reads
    the requirements, so its branch had to be added too."""
    from oneground import report as rep
    names = rep._constraint_names(
        {"recall_at_k": {"min": 0.9}, "latency": {"p95_ms": 40, "at_qps": 200},
         "monthly_budget": {"amount": 1200}})
    assert names == ["recall_at_k", "latency_p95", "qps", "monthly_budget"], names


def test_the_scope_entry_falls_back_to_the_requirements_with_no_options():
    from oneground import report as rep
    log = rep.decision_log([], [], None,
                           {"latency": {"p95_ms": 40, "at_qps": 200}}, None)
    scope = [e for e in log if e["kind"] == "scope"][0]["text"]
    assert "2 constraint(s)" in scope, scope
    assert "latency_p95" in scope and "qps" in scope, scope


def test_the_runner_up_line_carries_its_outcome():
    """Naming an alternative beside a recommendation reads as an endorsement.

    On the arxiv-150k report the runner-up was couldnt_check on latency and
    qps -- it was not the configuration verified -- and the line said only
    "indistinguishable on recall from: hash_sharded[...]".
    """
    from oneground import report as rep
    rec = _opt("single_node_hnsw[M=32]", vd.MEETS, [_v("recall_at_k", vd.MEETS)])
    rec.indistinguishable_from = ["hash_sharded[M=32,shards=3]"]
    runner = _opt("hash_sharded[M=32,shards=3]", vd.COULDNT_CHECK, [
        _v("recall_at_k", vd.MEETS),
        _v("latency_p95", vd.COULDNT_CHECK),
        _v("qps", vd.COULDNT_CHECK)])
    lines = rep.runner_up_lines(rec, [rec, runner])
    text = "\n".join(lines)
    assert "indistinguishable on recall from" in text, text
    assert "couldnt_check" in text, text
    assert "could not be checked on latency_p95, qps" in text, text
    assert "not indistinguishable overall" in text, text


def test_a_runner_up_that_meets_says_so_plainly():
    from oneground import report as rep
    rec = _opt("a[M=1]", vd.MEETS, [_v("recall_at_k", vd.MEETS)])
    rec.indistinguishable_from = ["b[M=1]"]
    runner = _opt("b[M=1]", vd.MEETS, [_v("recall_at_k", vd.MEETS),
                                       _v("qps", vd.MEETS)])
    text = "\n".join(rep.runner_up_lines(rec, [rec, runner]))
    assert "meets every constraint that could be checked" in text, text
    assert "not indistinguishable overall" not in text, text


def test_a_runner_up_that_fails_names_the_failure():
    from oneground import report as rep
    rec = _opt("a[M=1]", vd.MEETS, [_v("recall_at_k", vd.MEETS)])
    rec.indistinguishable_from = ["b[M=1]"]
    runner = _opt("b[M=1]", vd.FAILS, [
        _v("storage_amplification", vd.FAILS),
        _v("latency_p95", vd.COULDNT_CHECK)])
    text = "\n".join(rep.runner_up_lines(rec, [rec, runner]))
    assert "fails storage_amplification" in text, text
    assert "could not be checked on latency_p95" in text, text


def test_no_runner_up_produces_no_lines():
    from oneground import report as rep
    rec = _opt("a[M=1]", vd.MEETS, [_v("recall_at_k", vd.MEETS)])
    assert rep.runner_up_lines(rec, [rec]) == []
    assert rep.runner_up_lines(None, []) == []


def test_the_indistinguishable_log_entry_states_overall_outcomes():
    from oneground import report as rep
    rec = _opt("a[M=1]", vd.MEETS, [_v("recall_at_k", vd.MEETS)])
    rec.indistinguishable_from = ["b[M=1]"]
    runner = _opt("b[M=1]", vd.COULDNT_CHECK, [
        _v("recall_at_k", vd.MEETS), _v("qps", vd.COULDNT_CHECK)])
    runner.indistinguishable_from = ["a[M=1]"]
    log = rep.decision_log([rec, runner], [], rec, {}, None)
    entry = [e for e in log if e["kind"] == "indistinguishable"]
    assert entry, [e["kind"] for e in log]
    text = entry[0]["text"]
    assert "Overall:" in text, text
    assert "couldnt_check" in text, text
    assert "not indistinguishable overall" in text, text


# ------------- the latency verdict across repeated runs (task 017 item 2)
# 015 measured one configuration at 38.22 ms and 42.82 ms against a 40 ms cap,
# 12% apart, and stated `meets` once and `fails` once. Nothing about the
# architecture changed between them. A threshold inside the run-to-run spread
# is not a verdict.

_LAT_C = {"latency": {"p95_ms": 40.0, "at_qps": 200, "concurrency": 32},
          "recall_at_k": {"k": 10}}


def _verify_with_runs(per_run, concurrency=32):
    """A verify.json carrying `runs` p95 values under load."""
    from oneground import verify as vfy
    spread = vfy.p95_spread(per_run)
    shape = {"p50_ms": 10.0, "p95_ms": spread["median"], "p99_ms": 99.0,
             "mean_ms": 12.0, "max_ms": 120.0,
             "n_queries": 60000, "concurrency": concurrency,
             "note": "measured UNDER LOAD", "p95_across_runs": spread}
    return {"environment_id": "pod-1", "engine": "qdrant",
            "searches": {"k=10_under_load": {
                "recall_at_10": 0.99,
                "latency_shape_single_client": shape,
                "rtt_share_of_p95": 0.05}}}


def _row():
    return {"config": "single_node_hnsw[M=32,efConstruction=200,efSearch=128]",
            "family": "single_node_hnsw",
            "params": {"M": 32, "efConstruction": 200, "efSearch": 128}}


def _info():
    return {"engine_facts": {"index_params": {"m": 32, "ef_construct": 200}},
            "engine_params": {"hnsw_ef": 128}}


def test_meets_only_when_the_worst_run_meets():
    v = vd.latency_p95(_row(), _verify_with_runs([35.0, 38.2, 39.9]),
                       _LAT_C, "runpod", _info())
    assert v.outcome == MEETS, v.reason
    assert "all 3 runs" in v.reason and "39.90" in v.reason, v.reason
    assert v.value == 39.9, v.value          # the worst, not the median


def test_fails_only_when_the_best_run_fails():
    v = vd.latency_p95(_row(), _verify_with_runs([41.0, 44.0, 52.0]),
                       _LAT_C, "runpod", _info())
    assert v.outcome == FAILS, v.reason
    assert "all 3 runs" in v.reason and "41.00" in v.reason, v.reason
    assert v.value == 41.0, v.value          # the best, not the median


def test_a_threshold_inside_the_spread_is_couldnt_check_not_a_coin_toss():
    """The 015 case: 38.22 and 42.82 straddling a 40 ms cap."""
    v = vd.latency_p95(_row(), _verify_with_runs([38.22, 42.82]),
                       _LAT_C, "runpod", _info())
    assert v.outcome == CC, v.reason
    assert "meets in 1 of 2 runs" in v.reason, v.reason
    assert "4.60" in v.reason, v.reason       # the spread
    assert v.value is None, "a couldn't-check must not carry a number"


def test_the_straddling_verdict_never_reports_the_median_as_the_answer():
    """Three runs, median under the cap, max over it. Reporting the median
    would turn a straddle into a pass."""
    data = _verify_with_runs([30.0, 39.0, 55.0])
    shape = data["searches"]["k=10_under_load"]["latency_shape_single_client"]
    assert shape["p95_ms"] == 39.0            # the median is under the cap
    v = vd.latency_p95(_row(), data, _LAT_C, "runpod", _info())
    assert v.outcome == CC, v.reason
    assert "meets in 2 of 3 runs" in v.reason, v.reason


def test_one_run_keeps_the_old_two_way_rule():
    """`runs: 1` is every earlier run's shape and must be unchanged."""
    from oneground import verify as vfy
    assert vfy.p95_spread([41.0])["n_runs"] == 1
    data = _verify_with_runs([41.0])
    # a single-run file carries no p95_across_runs at all
    shape = data["searches"]["k=10_under_load"]["latency_shape_single_client"]
    shape.pop("p95_across_runs")
    v = vd.latency_p95(_row(), data, _LAT_C, "runpod", _info())
    assert v.outcome == FAILS and v.value == 41.0, v.reason


def test_p95_spread_arithmetic():
    from oneground import verify as vfy
    s = vfy.p95_spread([42.82, 38.22, 40.0])
    assert s["min"] == 38.22 and s["max"] == 42.82
    assert s["median"] == 40.0
    assert abs(s["spread"] - 4.6) < 1e-9
    assert s["n_runs"] == 3
    assert s["p95_ms_per_run"] == [42.82, 38.22, 40.0]   # unsorted, as measured
    assert vfy.p95_spread([]) is None
    assert vfy.p95_spread([10.0, 20.0])["median"] == 15.0


# ------------------- qps_max is a separate row, never the verdict (017/5)

def _verify_with_ceiling(achieved=200.0, target=200.0, ceiling=1750.0):
    return {"environment_id": "pod-1", "engine": "qdrant",
            "load": {"concurrency": 32, "target_qps": target,
                     "achieved_qps": achieved, "completed": int(achieved * 300),
                     "errors": 0, "duration_seconds": 300.0},
            "qps_max": {"qps_max": ceiling, "at_concurrency": 64,
                        "p99_ms_at_max": 180.0, "baseline_p99_ms": 12.0,
                        "stopped_because": "error rate 1.20% exceeded 0.5% "
                                           "at concurrency 128",
                        "caveat": "the ceiling under THIS load shape",
                        "ladder": []},
            "searches": {"k=10": {"recall_at_10": 0.99}}}


def test_the_qps_verdict_never_reads_the_ceiling():
    """A sustain check is against the offered rate. If `qps_max` ever leaked
    into it, an engine that sustained its offer would start reporting the
    ceiling as the achieved rate, which is the bug qps_max exists to avoid."""
    data = _verify_with_ceiling(achieved=112.63, target=200.0, ceiling=9999.0)
    c = {"qps": {"target": 200.0, "concurrency": 32},
         "latency": {"p95_ms": 40.0, "at_qps": 200, "concurrency": 32},
         "recall_at_k": {"k": 10}}
    v = vd.qps_target(_row(), data, c, "runpod", _info())
    assert v is not None
    assert v.outcome == FAILS, v.reason
    assert "9999" not in v.reason, "the ceiling reached the sustain verdict"
    assert v.value != 9999.0


def test_the_ceiling_is_reported_as_its_own_row_with_its_caveat():
    from oneground import report as rep
    lines = rep.qps_max_lines(_verify_with_ceiling())
    assert len(lines) == 1, lines
    line = lines[0]
    assert line["kind"] == "qps_max"
    assert "1750.0 qps at concurrency 64" in line["text"], line["text"]
    assert "error rate 1.20%" in line["text"], line["text"]
    assert "THIS load shape" in line["text"], line["text"]
    assert line["source"] == "verify.json:qps_max"


def test_no_ceiling_measured_means_no_row():
    from oneground import report as rep
    assert rep.qps_max_lines({"engine": "qdrant", "searches": {}}) == []
    assert rep.qps_max_lines({"engine": "q", "qps_max": {"qps_max": None}}) == []
