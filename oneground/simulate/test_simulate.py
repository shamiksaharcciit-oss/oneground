"""End-to-end tests for `oneground simulate`, on a 2k synthetic corpus.

**Synthetic throughout.** These check the command's contract: that it refuses
without a characterization, that every row carries its decomposition, that
budgets drop configurations loudly rather than quietly, and — the one this
task most needs — that **no verdict language reaches the output**.

    python oneground/simulate/test_simulate.py
    pytest oneground/simulate/test_simulate.py
"""

import io
import json
import os
import sys
import tempfile

import numpy as np
import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import characterize, simulate  # noqa: E402
from oneground.fixture import verify as fv  # noqa: E402
from oneground.simulate import inverse_ratio_at, recall_at  # noqa: E402

SEED = 20260910


def _quiet(msg):
    pass


def _corpus(tmp, n=2000, dim=32, n_q=60, seed=SEED):
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(4, dim))
    x = np.vstack([c + rng.normal(0, 0.13, size=(n // 4 + 1, dim))
                   for c in centres])[:n].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = x[rng.choice(n, size=n_q, replace=False)].copy()
    vp, qp = os.path.join(tmp, "v.npy"), os.path.join(tmp, "q.npy")
    np.save(vp, x)
    np.save(qp, q)
    return vp, qp


def _req(tmp, vp, qp, simulate_block=None):
    d = {
        "oneground": 1,
        "run": {"name": "sim-synth", "seed": SEED,
                "workdir": os.path.join(tmp, "out")},
        "corpus": {"sample": {
            "kind": "receipt",
            "vectors": {"path": vp, "normalized": True},
            "queries": {"path": qp, "count_min": 50},
            "target_sample_size": 2000,
        }},
        "simulate": simulate_block if simulate_block is not None else {
            "families": ["single_node_hnsw", "hash_sharded"],
            "node_counts": [2],
            "ground_truth_k": 20,
            "grid": {"single_node_hnsw": {"M": [16], "efSearch": [64]},
                     "hash_sharded": {"M": [16], "efSearch": [64]}},
        },
    }
    p = os.path.join(tmp, "requirements.yaml")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(d, f, sort_keys=False)
    return p


def _capture(fn, *a, **kw):
    buf, orig = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        out = fn(*a, **kw)
    finally:
        sys.stdout = orig
    return out, buf.getvalue()


def _prepared(tmp, simulate_block=None):
    vp, qp = _corpus(tmp)
    req = _req(tmp, vp, qp, simulate_block)
    _capture(characterize.run, req, log_fn=_quiet)
    return req


# ------------------------------------------------------------------ refusal
def test_simulate_refuses_without_a_characterization_and_names_the_command_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        vp, qp = _corpus(tmp, n=200, n_q=60)
        req = _req(tmp, vp, qp)
        try:
            simulate.run(req, log_fn=_quiet)
        except simulate.SimulateError as e:
            assert "oneground characterize" in str(e), e
            return
        raise AssertionError("simulate ran without a characterization")


# ----------------------------------------------------------------- end to end
def test_simulate_writes_receipts_that_verify_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(simulate.run, req, log_fn=_quiet)
        for n in ("simulate.json", "simulate_info.json", "MANIFEST.sha256"):
            assert os.path.exists(os.path.join(wd, n)), n
        entries = fv.read_manifest(os.path.join(wd, "MANIFEST.sha256"))
        names = {n for _, n in entries}
        assert {"simulate.json", "simulate_info.json"} <= names, names
        # characterize's receipts must still be listed after simulate rewrites
        assert "characterization.json" in names, names
        for digest, name in entries:
            assert fv.sha256_file(os.path.join(wd, name)) == digest, name


def test_every_row_carries_its_decomposition_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(simulate.run, req, log_fn=_quiet)
        rows = json.load(open(os.path.join(wd, "simulate.json"),
                              encoding="utf-8"))["rows"]
        assert rows
        for r in rows:
            for key in ("recall_at_1", "recall_at_10", "recall_at_100",
                        "ceiling_at_10", "routing_loss", "index_loss",
                        "inv_ratio_at_10", "storage_amplification",
                        "est_memory_bytes", "fanout", "build_seconds",
                        "query_seconds"):
                assert key in r, f"{r['config']} missing {key}"
            # The invariant the whole interface exists for.
            assert r["ceiling_at_10"] >= r["recall_at_10"] - 1e-9, r
            assert abs(r["routing_loss"] - (1 - r["ceiling_at_10"])) < 1e-6, r
            assert abs(r["index_loss"]
                       - (r["ceiling_at_10"] - r["recall_at_10"])) < 1e-6, r
            assert 0.0 <= r["inv_ratio_at_10"] <= 1.0, r


def test_full_reach_families_show_zero_routing_loss_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(simulate.run, req, log_fn=_quiet)
        rows = json.load(open(os.path.join(wd, "simulate.json"),
                              encoding="utf-8"))["rows"]
        for r in rows:
            if r["family"] in ("single_node_hnsw", "hash_sharded"):
                assert r["routing_loss"] < 1e-6, (
                    f"{r['config']} reaches everything but reports routing "
                    f"loss {r['routing_loss']}")


def test_rows_are_sorted_by_family_then_recall_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(simulate.run, req, log_fn=_quiet)
        rows = json.load(open(os.path.join(wd, "simulate.json"),
                              encoding="utf-8"))["rows"]
        keys = [(r["family"], -r["recall_at_10"]) for r in rows]
        assert keys == sorted(keys)


# ------------------------------------------------------------- no verdicts
VERDICT_WORDS = ("meets", "fails", "pass", "recommend", "best", "winner",
                 "should use", "verdict", "better than", "optimal")


def test_output_contains_no_verdict_language_synthetic():
    """The acceptance criterion. `simulate` measures; deciding is task 010."""
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, text = _capture(simulate.run, req, log_fn=_quiet)
        low = text.lower()
        for w in VERDICT_WORDS:
            assert w not in low, f"verdict word {w!r} in the table:\n{text}"
        blob = open(os.path.join(wd, "simulate.json"), encoding="utf-8").read()
        for w in VERDICT_WORDS:
            assert w not in blob.lower(), f"verdict word {w!r} in simulate.json"


# ---------------------------------------------------------------- budgets
def test_max_configs_drops_loudly_with_a_recorded_rule_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp, simulate_block={
            "families": ["single_node_hnsw", "hash_sharded"],
            "node_counts": [2, 3, 4],
            "ground_truth_k": 20,
            "budget": {"max_configs": 2},
        })
        wd, text = _capture(simulate.run, req, log_fn=_quiet)
        info = json.load(open(os.path.join(wd, "simulate_info.json"),
                              encoding="utf-8"))
        assert info["dropped"], "nothing was dropped despite max_configs=2"
        for d in info["dropped"]:
            assert d["reason"] == "couldnt_check: budget"
            assert "max_configs" in d["rule"], d
        assert info["configs_measured"] < info["configs_planned"]
        assert "couldnt_check: budget" in text


def test_max_minutes_stops_the_sweep_and_marks_the_rest_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp, simulate_block={
            "families": ["single_node_hnsw", "hash_sharded"],
            "node_counts": [2, 3, 4],
            "ground_truth_k": 20,
            "budget": {"max_minutes": 0.0},      # expire immediately
        })
        wd, _ = _capture(simulate.run, req, log_fn=_quiet)
        info = json.load(open(os.path.join(wd, "simulate_info.json"),
                              encoding="utf-8"))
        assert info["dropped"], "max_minutes=0 measured everything"
        assert any("max_minutes" in d["rule"] for d in info["dropped"])


def test_unknown_family_is_refused_by_name_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp, simulate_block={"families": ["no_such_family"]})
        try:
            simulate.run(req, log_fn=_quiet)
        except simulate.SimulateError as e:
            assert "no_such_family" in str(e) and "Registered" in str(e)
            return
        raise AssertionError("an unknown family was accepted")


# ---------------------------------------------------------------- metrics
def test_recall_at_counts_padding_as_a_miss_synthetic():
    gt = np.array([[1, 2, 3], [4, 5, 6]])
    assert recall_at(np.array([[1, 2, 3], [4, 5, 6]]), gt, 3) == 1.0
    assert recall_at(np.array([[1, -1, -1], [4, -1, -1]]), gt, 3) == 2 / 6


def test_inverse_ratio_is_one_for_an_exact_match_synthetic():
    gt = np.array([[0.9, 0.8, 0.7]], dtype=np.float32)
    assert abs(inverse_ratio_at(gt.copy(), gt, 3) - 1.0) < 1e-9


def test_inverse_ratio_is_below_one_for_a_worse_neighbour_synthetic():
    gt = np.array([[0.9, 0.8, 0.7]], dtype=np.float32)
    worse = np.array([[0.9, 0.8, 0.2]], dtype=np.float32)
    v = inverse_ratio_at(worse, gt, 3)
    assert 0.0 < v < 1.0, v


def test_inverse_ratio_scores_a_short_result_as_zero_synthetic():
    gt = np.array([[0.9, 0.8, 0.7]], dtype=np.float32)
    short = np.array([[0.9, 0.8, -np.inf]], dtype=np.float32)
    assert inverse_ratio_at(short, gt, 3) == 0.0


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
