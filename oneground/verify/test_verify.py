"""Tests for `oneground verify`, against the stub engine.

**Synthetic and stub throughout** — these check the command's contract, not any
engine's performance. The stub is exact and in-process, so its recall is 1.0
and its latencies are microseconds; what is being checked here is that the
receipt says the right things, that the noise guard fires, that no verdict
language escapes, and that nothing is ever reported as throughput.

Live engine behaviour is `adapters/conformance.py`'s job.

    python oneground/verify/test_verify.py
    pytest oneground/verify/test_verify.py
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

from oneground import characterize, verify  # noqa: E402
from oneground.adapters import get as get_engine  # noqa: E402
from oneground.fixture import verify as fv  # noqa: E402
from oneground.verify import (NOISE_FRACTION, latency_shape,  # noqa: E402
                              recall_at, _apply_noise_guard)

SEED = 20260911



def _block(verify_json, engine=None):
    """The one engine's block out of verify.json.

    Task 015 made verify.json hold `engines`, a list, with no engine promoted
    to the top level: a format with a primary engine and an also-ran would be
    picking a favourite. These tests run one engine, so they take the one
    block -- and say so, rather than reaching for keys that moved.
    """
    blocks = verify_json["engines"]
    assert isinstance(blocks, list) and blocks, verify_json
    if engine is None:
        assert len(blocks) == 1, [b.get("engine") for b in blocks]
        return blocks[0]
    return next(b for b in blocks if b.get("engine") == engine)

def _quiet(msg):
    pass


def _corpus(tmp, n=800, dim=32, n_q=60, seed=SEED):
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(5, dim))
    x = np.vstack([c + rng.normal(0, 0.15, size=(n // 5 + 1, dim))
                   for c in centres])[:n].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = x[rng.choice(n, size=n_q, replace=False)].copy()
    vp, qp = os.path.join(tmp, "v.npy"), os.path.join(tmp, "q.npy")
    np.save(vp, x)
    np.save(qp, q)
    return vp, qp


def _req(tmp, verify_block=None):
    vp, qp = _corpus(tmp)
    d = {
        "oneground": 1,
        "run": {"name": "verify-synth", "seed": SEED,
                "workdir": os.path.join(tmp, "out")},
        "corpus": {"sample": {
            "kind": "receipt",
            "vectors": {"path": vp, "normalized": True},
            "queries": {"path": qp, "count_min": 50},
            "target_sample_size": 800}},
        "simulate": {
            "families": ["single_node_hnsw"], "ground_truth_k": 100,
            "grid": {"single_node_hnsw": {"M": [32], "efSearch": [128]}}},
        "verify": verify_block if verify_block is not None else {
            "kind": "declared", "target": "local", "engine": "stub",
            "endpoint": "memory://", "ks": [10],
            "engine_params": {"m": 32, "hnsw_ef": 128}},
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


def _prepared(tmp, verify_block=None, with_simulate=True):
    req = _req(tmp, verify_block)
    _capture(characterize.run, req, log_fn=_quiet)
    if with_simulate:
        from oneground import simulate
        _capture(simulate.run, req, log_fn=_quiet)
    return req


# ------------------------------------------------------------------ refusal
def test_verify_refuses_without_a_characterization_and_names_the_command():
    with tempfile.TemporaryDirectory() as tmp:
        req = _req(tmp)
        try:
            verify.run(req, log_fn=_quiet)
        except verify.VerifyError as e:
            assert "oneground characterize" in str(e)
            return
        raise AssertionError("verify ran without a characterization")


def test_unsupported_target_is_refused_by_name():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp, verify_block={"target": "cloud",
                                           "engine": "stub"})
        try:
            verify.run(req, log_fn=_quiet)
        except verify.VerifyError as e:
            # Task 011 added `runpod`, so the message now names the three
            # supported targets rather than pointing forward to a future task.
            assert "cloud" in str(e)
            for supported in ("local", "runpod", "existing"):
                assert supported in str(e), supported
            return
        raise AssertionError("an unsupported target was accepted")


# ----------------------------------------------------------------- end to end
def test_verify_writes_receipts_that_verify_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        for n in ("verify.json", "verify_info.json", "MANIFEST.sha256"):
            assert os.path.exists(os.path.join(wd, n)), n
        entries = fv.read_manifest(os.path.join(wd, "MANIFEST.sha256"))
        names = {n for _, n in entries}
        assert {"verify.json", "verify_info.json"} <= names, names
        # characterize's and simulate's receipts stay listed
        assert {"characterization.json", "simulate.json"} <= names, names
        for digest, name in entries:
            assert fv.sha256_file(os.path.join(wd, name)) == digest, name


def test_verify_reports_recall_ingest_and_a_baseline_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        d = _block(json.load(open(os.path.join(wd, "verify.json"),
                                  encoding="utf-8")))
        assert d["mode"] == "local"
        assert d["ingest"]["vectors_per_second"] > 0
        assert "rtt_baseline_ms" in d
        row = d["searches"]["k=10"]
        assert row["recall_at_10"] == 1.0        # the stub is exact
        assert "latency_shape_single_client" in row


def test_engine_facts_are_labelled_declared_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        info = json.load(open(os.path.join(wd, "verify_info.json"),
                              encoding="utf-8"))
        assert len(info["engines"]) == 1, info["engines"]
        facts = info["engines"][0]["engine_facts"]
        assert facts["kind"] == "declared", facts
        assert "not something oneground measured" in facts["note"]
        assert info["kind"]["verify_info.json"] == "declared"


def test_calibration_error_is_simulated_minus_measured_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        d = _block(json.load(open(os.path.join(wd, "verify.json"),
                                  encoding="utf-8")))
        c = d["calibration"]
        assert d["calibration_error_recall"] == (
            c["simulated_recall_at_10"] - c["measured_recall_at_10"])
        assert c["definition"] == "simulated - measured"


def test_calibration_is_couldnt_check_without_a_simulate_run_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp, with_simulate=False)
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        d = _block(json.load(open(os.path.join(wd, "verify.json"),
                                  encoding="utf-8")))
        cal = d["calibration_error_recall"]
        assert isinstance(cal, str) and cal.startswith("couldnt_check")
        assert "simulate.json" in cal


# -------------------------------------------------------------- noise guard
def test_noise_guard_fires_when_the_baseline_dominates():
    """The guard's whole point: a latency number that is mostly the path to
    the engine is not a measurement of the engine."""
    row = {}
    shape = latency_shape([10.0] * 100)               # query p95 = 10 ms
    baseline = latency_shape([9.0] * 100)             # baseline p95 = 9 ms
    _apply_noise_guard(row, shape, baseline, 10)
    assert isinstance(row["latency_shape_single_client"], str)
    assert row["latency_shape_single_client"].startswith("couldnt_check")
    assert "environment noise" in row["latency_shape_single_client"]
    # The numbers are kept, just not attributed.
    assert row["latency_measured_but_not_attributable"]["p95_ms"] == 10.0


def test_noise_guard_stays_quiet_when_the_engine_dominates():
    row = {}
    shape = latency_shape([100.0] * 100)
    baseline = latency_shape([1.0] * 100)             # 1% of query p95
    _apply_noise_guard(row, shape, baseline, 10)
    assert isinstance(row["latency_shape_single_client"], dict)
    assert row["rtt_share_of_p95"] < NOISE_FRACTION


def test_recall_is_reported_even_when_latency_is_couldnt_check_synthetic():
    """Noise moves latency, not recall, so recall must survive the guard."""
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp, verify_block={
            "kind": "declared", "target": "local", "engine": "stub",
            "endpoint": "memory://", "ks": [10],
            "engine_params": {"m": 32, "hnsw_ef": 128}})
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        row = _block(json.load(open(os.path.join(wd, "verify.json"),
                                    encoding="utf-8")))["searches"]["k=10"]
        assert row["recall_at_10"] == 1.0


# --------------------------------------------------------- no verdicts, no tps
VERDICT_WORDS = ("meets", "fails", "recommend", "winner", "should use",
                 "verdict", "better than", "optimal", "passes the")

THROUGHPUT_WORDS = ("throughput", "qps", "queries per second",
                    "requests per second", "rps")


def test_output_contains_no_verdict_language_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, text = _capture(verify.run, req, log_fn=_quiet)
        low = text.lower()
        for w in VERDICT_WORDS:
            assert w not in low, f"verdict word {w!r} in the output:\n{text}"
        blob = open(os.path.join(wd, "verify.json"), encoding="utf-8").read()
        for w in VERDICT_WORDS:
            assert w not in blob.lower(), f"{w!r} in verify.json"


def test_latency_is_never_presented_as_throughput_synthetic():
    """The brief forbids measuring or claiming throughput. The only place the
    word may appear is a disclaimer saying it is *not* being measured."""
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, text = _capture(verify.run, req, log_fn=_quiet)
        d = _block(json.load(open(os.path.join(wd, "verify.json"),
                                  encoding="utf-8")))
        shape = d["searches"]["k=10"]["latency_shape_single_client"]
        if isinstance(shape, dict):
            assert shape["concurrency"] == 1
            assert "not throughput" in shape["note"]
        assert "not throughput" in text
        # No key anywhere may name a rate of queries.
        blob = json.dumps(d).lower()
        for w in THROUGHPUT_WORDS:
            if w in blob:
                assert "not throughput" in blob, (
                    f"{w!r} appears without the disclaimer")


# ---------------------------------------------------------------- metrics
def test_recall_at_counts_padding_as_a_miss():
    gt = np.array([[1, 2, 3], [4, 5, 6]])
    assert recall_at(np.array([[1, 2, 3], [4, 5, 6]]), gt, 3) == 1.0
    assert recall_at(np.array([[1, -1, -1], [4, -1, -1]]), gt, 3) == 2 / 6


def test_latency_shape_is_labelled_single_client():
    s = latency_shape([1.0, 2.0, 3.0, 4.0])
    assert s["concurrency"] == 1
    assert s["n_queries"] == 4
    assert "not throughput" in s["note"]


# ------------------------------------------------------------------ cleanup
def test_the_verify_namespace_is_gone_afterwards_synthetic():
    """verify creates a namespace; it must not leave one behind."""
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        engines = []
        orig = verify.get_engine

        def spy(name):
            factory = orig(name)

            def make(*a, **kw):
                e = factory(*a, **kw)
                engines.append(e)
                return e
            return make

        verify.get_engine = spy
        try:
            _capture(verify.run, req, log_fn=_quiet)
        finally:
            verify.get_engine = orig
        assert engines, "no engine was constructed"
        for e in engines:
            leftover = [n for n in getattr(e, "_ns", {})]
            assert not leftover, f"namespaces left behind: {leftover}"


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
