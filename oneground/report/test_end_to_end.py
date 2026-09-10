"""`oneground report` end to end, on a workdir that produces a recommendation.

**Synthetic throughout.** The numbers are chosen so exactly one option meets
every constraint; nothing here is a measurement of anything.

WHY THIS FILE EXISTS
--------------------
Task 013b added a `run_environment` stamp to every report dict carrying a
`generated_at`, and one of those lives in `build_manifest`, which has a
different signature. The result was

    NameError: name 'env_stamp' is not defined
      oneground/report/__init__.py:718 in build_manifest

on any report with a recommendation. It shipped, and a 452-test suite stayed
green over it, because `build_manifest` returns early through its
"nothing recommended" branch and every existing test took that branch --
including the smoke report the change was demonstrated on.

So the flagship path had no end-to-end coverage at all: the one report shape a
user most wants to produce, the one that names a configuration and writes a
deployable manifest, was never driven by a test. This file drives it.
"""

import json
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import report as rep                      # noqa: E402

ENV = "pod-e2e"
WINNER = "single_node_hnsw[M=32,efConstruction=200,efSearch=128]"
LOSER = "semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2]"


def _row(config, family, params, recall, storage, memory, fanout):
    return {
        "config": config, "family": family, "params": params,
        "recall_at_1": recall, "recall_at_10": recall,
        "recall_at_100": recall, "ceiling_at_10": recall,
        "inv_ratio_at_10": 1.0, "routing_loss": 0.0, "index_loss": 0.0,
        "storage_amplification": storage, "stored_vectors": 150000,
        "est_memory_bytes": memory, "fanout": fanout, "shards": 1,
        "p50_copies": 1, "p95_copies": 1, "p99_copies_per_vector": 1,
        "build_seconds": 1.0, "query_seconds": 1.0,
    }


def _workdir(tmp, recall_floor=0.95, p95_ms=40.0, at_qps=200):
    """A workdir where exactly one of two options meets every constraint."""
    wd = os.path.join(tmp, "runs", "e2e")
    os.makedirs(wd)

    _dump(wd, "characterization.json", {
        "run": "e2e", "schema": 1, "n_base": 150000, "n_queries": 2000,
        "dimension": 768,
        "definitions": {"centroids": 256, "crispness_ratio": 1.2,
                        "ambiguity_ratio": 1.1, "seed": 1},
        "characterization": {"intrinsic_dimensionality": 32.5,
                             "boundary_crispness": 0.036,
                             "skew_top10_share": 0.075,
                             "ambiguous_query_rate": 0.89,
                             "drift": "couldnt_check: no timestamp_field"}})

    _dump(wd, "simulate.json", {
        "run": "e2e", "schema": 1, "seed": 1, "n_base": 150000,
        "n_queries": 2000, "ground_truth_k": 100,
        "rows": [
            # Meets everything.
            _row(WINNER, "single_node_hnsw",
                 {"M": 32, "efConstruction": 200, "efSearch": 128},
                 0.999, 1.0, 6.7e8, 1.0),
            # Fails recall and storage, so the recommendation is unambiguous.
            _row(LOSER, "semantic_sharded",
                 {"M": 32, "centroids": 256, "efSearch": 96,
                  "epsilon": 0.2, "probe": 2},
                 0.93, 3.7, 2.4e9, 2.0),
        ]})

    # The engine was built as the winner, so only the winner may carry a
    # latency or throughput verdict (task 011's same-configuration rule).
    _dump(wd, "verify.json", {
        "environment_id": ENV, "engine": "qdrant", "engine_version": "1.19.1",
        "mode": "local", "elapsed_seconds": 60.0,
        "rtt_baseline_ms": {"p50_ms": 4.5, "p95_ms": 6.9, "n_queries": 50},
        "searches": {
            "k=10": {"recall_at_10": 0.999,
                     "latency_shape_single_client":
                         "couldnt_check: environment noise"},
            "k=10_under_load": {
                "recall_at_10": 0.999,
                "latency_shape_single_client": {
                    "p50_ms": 22.0, "p95_ms": 38.0, "p99_ms": 48.0,
                    "n_queries": 60000, "concurrency": 32,
                    "note": "measured UNDER LOAD at concurrency 32"}}},
        "load": {"achieved_qps": 199.99, "target_qps": float(at_qps),
                 "concurrency": 32, "completed": 59999,
                 "duration_seconds": 300.0, "errors": 0, "error_rate": 0.0,
                 "latency_under_load": {"p50_ms": 22.0, "p95_ms": 38.0,
                                        "p99_ms": 48.0, "max_ms": 200.0}},
        "calibration_error_recall": "couldnt_check: synthetic"})

    _dump(wd, "verify_info.json", {
        "engine": "qdrant", "target": "runpod", "kind": "declared",
        "platform": "synthetic", "run_at": "2026-09-10T00:00:00Z",
        "engine_params": {"m": 32, "ef_construct": 200, "hnsw_ef": 128,
                          "indexing_threshold": 1},
        "engine_facts": {"index_type": "hnsw",
                         "index_params": {"m": 32, "ef_construct": 200}}})

    req = os.path.join(tmp, "requirements.yaml")
    with open(req, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump({
            "oneground": 1,
            "run": {"name": "e2e", "seed": 1, "workdir": "./runs/e2e"},
            "corpus": {"sample": {
                "kind": "receipt",
                "vectors": {"path": "./v.npy"},
                "queries": {"path": "./q.npy", "count_min": 1}}},
            "constraints": {
                "kind": "declared",
                "recall_at_k": {"k": 10, "min": recall_floor},
                "storage_amplification_max": 2.0,
                "latency": {"p95_ms": p95_ms, "at_qps": at_qps,
                            "concurrency": 32}},
        }, f)
    # `intake` needs the vector files to exist, not to contain anything real.
    import numpy as np
    for name in ("v.npy", "q.npy"):
        np.save(os.path.join(tmp, name), np.zeros((2, 2), dtype=np.float32))
    return req, wd


def _dump(wd, name, obj):
    with open(os.path.join(wd, name), "w", encoding="utf-8",
              newline="\n") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def _run(tmp, **kw):
    req, wd = _workdir(tmp, **kw)
    rep.run(req, log_fn=lambda *a, **k: None)
    with open(os.path.join(wd, "report.json"), encoding="utf-8") as f:
        report = json.load(f)
    with open(os.path.join(wd, "manifest.yaml"), encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    return report, manifest, wd


# ------------------------------------------------------------ the flagship
def _verdicts(report, config):
    """{constraint: outcome} for one option, from the Tier-1 shape."""
    for o in report["options"]:
        if o["config"] == config:
            return {v["constraint"]: v["outcome"]
                    for v in o["judgement"]["constraints"]}
    raise AssertionError(f"{config} is not among the report's options")


def test_a_report_with_a_recommendation_runs_end_to_end_synthetic():
    """The path that crashed under a green suite."""
    with tempfile.TemporaryDirectory() as tmp:
        report, manifest, wd = _run(tmp)
        assert report["recommendation"] == WINNER, report["recommendation"]
        assert manifest["recommended"]["config"] == WINNER


def test_build_manifest_is_reached_and_writes_a_manifest_synthetic():
    """`build_manifest`'s full branch -- the one with a recommendation -- was
    never executed by a test, which is why a NameError in it shipped."""
    with tempfile.TemporaryDirectory() as tmp:
        _report, manifest, wd = _run(tmp)
        assert os.path.exists(os.path.join(wd, "manifest.yaml"))
        assert manifest["oneground_manifest"] == 1
        # The full branch carries the evidence; the early one carries a reason.
        assert "reason" not in manifest, manifest
        assert manifest["inputs"], "the manifest names nothing it derives from"
        assert manifest["engine"]["name"] == "qdrant"
        assert manifest["engine"]["verified"] is True


def test_the_manifest_carries_the_run_environment_synthetic():
    """The field whose absence from `build_manifest`'s signature was the bug."""
    with tempfile.TemporaryDirectory() as tmp:
        _report, manifest, _wd = _run(tmp)
        env = manifest["run_environment"]
        # `environment_id`, not `executable`: an absolute interpreter path is
        # a machine identifier and does not belong in a published artifact.
        assert env["environment_id"], env
        assert "pinned" in env
        assert "executable" not in env and "prefix" not in env, env


def test_all_three_output_files_are_written_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _report, _manifest, wd = _run(tmp)
        for name in rep.OUTPUT_FILES:
            assert os.path.exists(os.path.join(wd, name)), name


# --------------------------------------------- the verdicts behind it
def test_the_recommendation_rests_on_five_settled_constraints_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        report, _manifest, _wd = _run(tmp)
        got = _verdicts(report, WINNER)
        assert got.get("recall_at_k") == "meets", got
        assert got.get("storage_amplification") == "meets", got
        assert got.get("latency_p95") == "meets", got
        assert got.get("qps") == "meets", got


def test_only_the_verified_configuration_carries_latency_and_qps_synthetic():
    """Task 013's same-configuration rule, exercised through the real run."""
    with tempfile.TemporaryDirectory() as tmp:
        report, _manifest, _wd = _run(tmp)
        win, lose = _verdicts(report, WINNER), _verdicts(report, LOSER)
        assert win["latency_p95"] == "meets", win
        assert lose["latency_p95"] == "couldnt_check", lose
        assert lose["qps"] == "couldnt_check", lose


def test_the_scope_entry_counts_every_constraint_judged_synthetic():
    """Task 013's fix, through the real run rather than a hand-built log."""
    with tempfile.TemporaryDirectory() as tmp:
        report, _manifest, _wd = _run(tmp)
        scope = [e for e in report["decision_log"]
                 if e["kind"] == "scope"][0]["text"]
        assert "4 constraint(s)" in scope, scope
        for name in ("recall_at_k", "storage_amplification", "latency_p95",
                     "qps"):
            assert name in scope, (name, scope)


def test_the_report_cites_its_calibration_synthetic():
    """Task 012's footer, through the real run."""
    with tempfile.TemporaryDirectory() as tmp:
        report, _manifest, _wd = _run(tmp)
        cal = report["calibration"]
        assert cal["statements"], cal
        assert isinstance(cal["tolerance"], float)


def test_a_report_that_recommends_nothing_still_writes_a_manifest_synthetic():
    """The other branch, so both are covered rather than one."""
    with tempfile.TemporaryDirectory() as tmp:
        # An unreachable recall floor: nothing meets everything.
        report, manifest, _wd = _run(tmp, recall_floor=0.9999999)
        assert report["recommendation"] is None, report["recommendation"]
        assert manifest["recommended"] is None
        assert "reason" in manifest, manifest


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
    print(f"\n{len(tests) - failed} passed, {failed} failed "
          f"(of {len(tests)} collected)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
