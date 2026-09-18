"""Task 026: the policy validator, the prediction file, the two-run verdict.

Synthetic throughout, except the test named for docs/PROPOSALS.md's own
example. The end-to-end test runs the real `simulate` on a 2k synthetic
corpus, because the citation it checks is written by that command.
"""

import json
import os
import re
import sys
import tempfile

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from oneground.proposals import (COULDNT_CHECK, DID_NOT_HOLD,  # noqa: E402
                                 HELD, PolicyError, PredictionError, judge,
                                 simulate_include, validate_policy,
                                 validate_prediction, write_prediction)
from oneground.report.verdict import CALIBRATION_TOLERANCE  # noqa: E402

SEMANTIC = {"centroids": 256, "epsilon": 0.2, "probe": 2, "M": 32,
            "efSearch": 96}


def _policy(**over):
    p = {"family": "semantic_sharded", "configuration": dict(SEMANTIC),
         "changes": [{"param": "probe", "from": 2, "to": 3}],
         "rationale": "probe one more region"}
    p.update(over)
    return {"policy": p}


def _refusal(doc):
    with pytest.raises(PolicyError) as e:
        validate_policy(doc)
    return e.value.problems


# ------------------------------------------------------------------ policy
def test_a_valid_policy_names_both_configurations_synthetic():
    pol = validate_policy(_policy())
    assert pol.from_config.label == (
        "semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2]")
    assert pol.to_config.params["probe"] == 3
    assert pol.from_config.label != pol.to_config.label


def test_the_policy_digest_ignores_key_order_synthetic():
    a = validate_policy(_policy())
    reordered = {"policy": dict(reversed(list(_policy()["policy"].items())))}
    assert validate_policy(reordered).sha256() == a.sha256()
    assert validate_policy(_policy(rationale="other words")).sha256() != a.sha256()


def test_a_scope_anywhere_is_refused_as_needing_a_family_that_does_not_exist():
    for doc in (_policy(scope="queries_where_ambiguous"),
                _policy(changes=[{"param": "probe", "from": 2, "to": 3,
                                  "scope": "queries_where_ambiguous"}])):
        problems = _refusal(doc)
        assert any("requires a family that does not exist" in p
                   for p in problems), problems


def test_a_policy_names_only_shipped_families_and_parameters_synthetic():
    assert any("no model family named 'disk_tiered'" in p
               for p in _refusal(_policy(family="disk_tiered")))
    problems = _refusal(_policy(changes=[{"param": "probez", "from": 2,
                                          "to": 3}]))
    assert any("no parameter 'probez'" in p and "probe" in p
               for p in problems), problems


@pytest.mark.parametrize("param, needle", [
    ("efConstruction", "constant fixed at 200"),
    ("shard_depth", "is a run setting"),
    ("deterministic", "is a build setting"),
])
def test_only_architecture_parameters_may_change_synthetic(param, needle):
    problems = _refusal(_policy(changes=[{"param": param, "from": 1,
                                          "to": 2}]))
    assert any(needle in p for p in problems), problems


def test_a_change_must_start_from_the_configuration_and_change_something():
    problems = _refusal(_policy(changes=[{"param": "probe", "from": 1,
                                          "to": 1}]))
    assert any("but the configuration has 2" in p for p in problems)
    assert any("changes nothing" in p for p in problems)


def test_the_whole_configuration_is_required_synthetic():
    partial = dict(SEMANTIC)
    del partial["efSearch"]
    problems = _refusal(_policy(configuration=partial))
    assert any("missing efSearch" in p for p in problems), problems


def test_values_are_checked_against_the_table_synthetic():
    problems = _refusal(_policy(changes=[{"param": "probe", "from": 2,
                                          "to": 0}]))
    assert any("at least 1" in p for p in problems), problems


def test_every_problem_is_reported_at_once_synthetic():
    problems = _refusal({"policy": {
        "family": "semantic_sharded", "configuration": {"centroids": 256},
        "changes": [{"param": "probez", "from": 1, "to": 2},
                    {"param": "efConstruction", "from": 200, "to": 400}],
        "scope": "x", "rationale": 7}})
    assert len(problems) >= 5, problems


def test_every_policy_example_in_docs_proposals_md_is_valid():
    """Not synthetic: the document's own examples, run through the validator,
    so it cannot describe a policy the code refuses.

    Every block, not the only one there used to be: task 028's tier-1 section
    added a second, and a test pinned to a count would have been relaxed into
    a test of the count rather than of the examples.
    """
    text = open(os.path.join(ROOT, "docs", "PROPOSALS.md"),
                encoding="utf-8").read()
    blocks = re.findall(r"```yaml\n(policy:.*?)```", text, re.S)
    assert len(blocks) >= 2, blocks
    first_changes = [validate_policy(yaml.safe_load(b)).changes[0]
                     for b in blocks]
    assert ("probe", 2, 3) in first_changes, first_changes      # §2.2
    assert ("probe", 1, 2) in first_changes, first_changes      # §5a


def test_every_prediction_example_in_docs_proposals_md_is_valid():
    """The other half of the tier-1 section: what a reader would write next."""
    text = open(os.path.join(ROOT, "docs", "PROPOSALS.md"),
                encoding="utf-8").read()
    blocks = re.findall(r"```yaml\n(expects:.*?)```", text, re.S)
    assert len(blocks) >= 1, blocks
    for b in blocks:
        checked = validate_prediction(yaml.safe_load(b))
        assert checked["expects"] and checked["side_effects"]


# -------------------------------------------------------------- prediction
def test_it_will_be_better_is_not_a_prediction_synthetic():
    for spec in ({}, {"expects": []}, {"expects": [{"metric": "recall_at_10"}]}):
        with pytest.raises(PredictionError) as e:
            validate_prediction(spec)
        text = " ".join(e.value.problems)
        assert ("is not a prediction" in text or "names no" in text), text


def test_a_prediction_below_the_tolerance_is_refused_naming_it_synthetic():
    with pytest.raises(PredictionError) as e:
        validate_prediction({"expects": [{"metric": "recall_at_10",
                                          "direction": "rises",
                                          "by_at_least": 0.005}]})
    assert f"calibration tolerance {CALIBRATION_TOLERANCE}" in str(e.value)
    # exactly at the tolerance is a prediction that can be checked
    validate_prediction({"expects": [{"metric": "recall_at_10",
                                      "direction": "rises",
                                      "by_at_least": CALIBRATION_TOLERANCE}]})


def test_a_prediction_names_measured_metrics_and_one_bound_synthetic():
    with pytest.raises(PredictionError) as e:
        validate_prediction({
            "expects": [{"metric": "est_memory_bytes", "direction": "falls",
                         "by_at_least": 1}],
            "side_effects": [{"metric": "fanout", "stays_at_or_below": 3,
                              "stays_at_or_above": 1}]})
    text = " ".join(e.value.problems)
    assert "not a metric this measures" in text and "exactly one of" in text


def test_a_prediction_is_written_once_synthetic():
    pol = validate_policy(_policy())
    spec = {"expects": [{"metric": "recall_at_10", "direction": "rises",
                         "by_at_least": 0.02}]}
    with tempfile.TemporaryDirectory() as tmp:
        path, sha = write_prediction(tmp, pol, spec, seed=11)
        doc = json.load(open(path, encoding="utf-8"))
        assert doc["policy_sha256"] == pol.sha256()
        assert doc["kind"] == "declared"
        assert doc["from_config"]["label"] == pol.from_config.label
        with pytest.raises(PredictionError):
            write_prediction(tmp, pol, spec, seed=11)


def test_simulate_include_measures_both_configurations_synthetic():
    pol = validate_policy(_policy())
    inc = simulate_include(pol)
    assert [e["probe"] for e in inc] == [2, 3]
    assert all(e["family"] == "semantic_sharded" for e in inc)


# ----------------------------------------------------------------- verdict
def _prediction(expects, side=(), tolerance=CALIBRATION_TOLERANCE, seed=5):
    return {"calibration_tolerance": tolerance, "run": {"seed": seed},
            "from_config": {"label": "A"}, "to_config": {"label": "B"},
            "expects": list(expects), "side_effects": list(side)}


def _run(a, b, seed=5, cited="abc"):
    sim = {"seed": seed, "rows": [dict(a, config="A"), dict(b, config="B")]}
    info = {"prediction": {"file": "prediction.json", "sha256": cited}}
    return sim, info


RISE = {"metric": "recall_at_10", "direction": "rises", "by_at_least": 0.02}


@pytest.mark.parametrize("after, outcome", [
    (0.83, HELD),            # delta 0.03 >= T + t
    (0.8299, COULDNT_CHECK),  # delta within t of T
    (0.81, DID_NOT_HOLD),    # delta 0.01 <= T - t
    (0.8101, COULDNT_CHECK),
    (0.79, DID_NOT_HOLD),    # it fell
])
def test_the_two_run_rule_reads_the_delta_against_its_band_synthetic(after,
                                                                    outcome):
    sim, info = _run({"recall_at_10": 0.80}, {"recall_at_10": after})
    got = judge(_prediction([RISE]), "abc", sim, info)
    assert got["outcome"] == outcome, got


def test_a_point_exactly_on_the_band_is_decided_by_the_measurement_synthetic():
    """0.83 - 0.80 - 0.02 is 0.009999999999999915 in floats, just inside the
    band; rounded to 6 decimals it is 0.01, the tolerance itself, which is
    outside it. Without the rounding this would read couldn't-check."""
    sim, info = _run({"recall_at_10": 0.80}, {"recall_at_10": 0.83})
    assert judge(_prediction([RISE]), "abc", sim, info)["outcome"] == HELD


def test_a_side_effect_over_its_bound_is_did_not_hold_synthetic():
    side = [{"metric": "storage_amplification", "stays_at_or_below": 2.0}]
    sim, info = _run({"recall_at_10": 0.80, "storage_amplification": 1.5},
                     {"recall_at_10": 0.90, "storage_amplification": 2.5})
    got = judge(_prediction([RISE], side), "abc", sim, info)
    assert got["outcome"] == DID_NOT_HOLD
    assert [r["outcome"] for r in got["rows"]] == [HELD, DID_NOT_HOLD]


@pytest.mark.parametrize("change, needle", [
    (lambda sim, info: info.pop("prediction"), "cite no prediction"),
    (lambda sim, info: info["prediction"].update(sha256="other"),
     "written or edited after the run"),
    (lambda sim, info: sim.update(seed=6), "seed"),
    (lambda sim, info: sim["rows"].pop(), "no row for B"),
])
def test_no_citation_no_verdict_synthetic(change, needle):
    sim, info = _run({"recall_at_10": 0.80}, {"recall_at_10": 0.90})
    change(sim, info)
    got = judge(_prediction([RISE]), "abc", sim, info)
    assert got["outcome"] == COULDNT_CHECK
    assert needle in got["reason"], got["reason"]
    assert all(r["outcome"] == COULDNT_CHECK for r in got["rows"])


# ------------------------------------------------------------- end to end
def test_the_run_cites_the_prediction_written_before_it_synthetic():
    """The real simulate, on a 2k synthetic corpus: a prediction written
    before the run is cited by simulate_info.json and judged; the same
    prediction edited afterwards is not."""
    from oneground import simulate
    from oneground.fixture import verify as fv
    from oneground.simulate import test_simulate as ts

    pol = validate_policy({"policy": {
        "family": "single_node_hnsw",
        "configuration": {"M": 16, "efConstruction": 200, "efSearch": 16},
        "changes": [{"param": "efSearch", "from": 16, "to": 64}]}})
    spec = {"expects": [{"metric": "recall_at_10", "direction": "rises",
                         "by_at_least": 0.01}],
            "side_effects": [{"metric": "storage_amplification",
                              "stays_at_or_below": 1.5}]}
    with tempfile.TemporaryDirectory() as tmp:
        block = {"families": ["single_node_hnsw"], "ground_truth_k": 20,
                 "grid": {"single_node_hnsw": {"M": [16], "efSearch": [16]}},
                 "include": simulate_include(pol)}
        req = ts._prepared(tmp, block)
        workdir = os.path.join(tmp, "out")
        path, sha = write_prediction(workdir, pol, spec, seed=ts.SEED)
        ts._capture(simulate.run, req, log_fn=ts._quiet)

        info = json.load(open(os.path.join(workdir, "simulate_info.json"),
                              encoding="utf-8"))
        sim = json.load(open(os.path.join(workdir, "simulate.json"),
                             encoding="utf-8"))
        assert info["prediction"]["sha256"] == sha
        assert info["kind"]["prediction.json"] == "declared"
        names = {n for _d, n in fv.read_manifest(
            os.path.join(workdir, "MANIFEST.sha256"))}
        assert "prediction.json" in names

        prediction = json.load(open(path, encoding="utf-8"))
        got = judge(prediction, sha, sim, info)
        assert got["reason"] == "", got
        assert {r["metric"] for r in got["rows"]} == {
            "recall_at_10", "storage_amplification"}
        assert got["rows"][1]["outcome"] == HELD      # 1.0 is well under 1.5

        # Edited after the run: the citation no longer matches.
        prediction["expects"][0]["by_at_least"] = 0.02
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(prediction, f)
        edited = fv.sha256_file(path)
        again = judge(prediction, edited, sim, info)
        assert again["outcome"] == COULDNT_CHECK
        assert "written or edited after the run" in again["reason"]
