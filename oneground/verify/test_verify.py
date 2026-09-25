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
import time

import numpy as np
import pytest
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


# -------------------------------------- what the engine can build (task 034)
# `simulate` measures four index families and no engine offers all of them. A
# user who takes an `ivf_pq` result to `verify` has to learn that before the
# run, and has to be able to tell "nobody ran it" from "it cannot be run
# here" -- the remedy for the second is a different engine, not a command.

def _stub_coverage():
    engine = get_engine("stub")()
    engine.connect("memory://")
    return engine.index_families()


def test_an_index_the_engine_cannot_build_is_refused_before_anything_exists():
    from oneground.adapters import index_families as IF

    with pytest.raises(verify.VerifyError) as e:
        verify.plan_index_families({"index": IF.IVF_PQ}, ["stub"],
                                   [_stub_coverage()])
    msg = str(e.value)
    assert "cannot build index=ivf_pq" in msg, msg
    assert "it offers flat" in msg, msg          # and what it does offer
    assert "Nothing has been created" in msg, msg
    # the remedy is not a command
    assert "different engine" in msg, msg


def test_a_family_the_engine_builds_is_planned_rather_than_refused():
    from oneground.adapters import index_families as IF

    got = verify.plan_index_families({"index": IF.FLAT}, ["stub"],
                                     [_stub_coverage()])
    assert [d.state for d in got] == [IF.VERIFIABLE], got
    assert got[0].remedy == ""


def test_an_unresolved_coverage_is_couldnt_check_and_not_a_refusal():
    """The distinction the whole feature turns on: nobody asked is not
    cannot be done, and only the second may refuse a run."""
    from oneground.adapters import index_families as IF

    got = verify.plan_index_families(
        {"index": IF.IVF}, ["stub"], [IF.unresolved("stub", "nobody asked")])
    assert [d.state for d in got] == [IF.COVERAGE_UNRESOLVED], got
    assert "has not been asked" in got[0].reason
    assert "resolve the coverage" in got[0].remedy


def test_an_unknown_index_family_is_refused_with_the_declared_list():
    from oneground.models.base import INDEX_ALGORITHMS

    with pytest.raises(verify.VerifyError) as e:
        verify.plan_index_families({"index": "annoy"}, ["stub"],
                                   [_stub_coverage()])
    for name in INDEX_ALGORITHMS:
        assert name in str(e.value), str(e.value)


def test_every_engine_that_cannot_build_it_is_named_at_once():
    """022's precondition rule: one refusal teaches the whole shape."""
    from oneground.adapters import index_families as IF

    a = _stub_coverage()
    b = IF.resolved("other", "9", {}, how="asked")
    with pytest.raises(verify.VerifyError) as e:
        verify.plan_index_families({"index": IF.HNSW}, ["stub", "other"],
                                   [a, b])
    assert "stub" in str(e.value) and "other" in str(e.value), str(e.value)


def test_the_refusal_happens_before_a_pod_session_is_prepared():
    """A refusal that arrives after a run has been paid for is not one.

    A recorded resolution beside the requirements file says the engine cannot
    build the declared family; `verify` must stop without writing a session
    spec, whatever `target` says.
    """
    from oneground.adapters import index_families as IF

    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp, verify_block={
            "kind": "declared", "target": "runpod", "engine": "stub",
            "endpoint": "memory://", "ks": [10], "index": "ivf_pq",
            "engine_params": {"m": 32, "hnsw_ef": 128}})
        os.makedirs(os.path.join(tmp, "adapters"), exist_ok=True)
        IF.write(os.path.join(tmp, "adapters", "index-coverage.json"),
                 [_stub_coverage()])
        try:
            verify.run(req, log_fn=_quiet)
        except verify.VerifyError as e:
            assert "cannot build index=ivf_pq" in str(e), str(e)
            wd = os.path.join(tmp, "out")
            assert not os.path.exists(os.path.join(wd, "verify.json"))
            sessions = os.path.join(tmp, "sessions")
            assert not os.path.isdir(sessions) or not os.listdir(sessions)
            return
        raise AssertionError("a pod session was prepared for an index no "
                             "engine can build")


def test_the_receipt_records_what_each_engine_could_build_synthetic():
    from oneground.adapters import index_families as IF

    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        doc = json.load(open(os.path.join(wd, "verify.json"), encoding="utf-8"))
        block = doc["index"]
        assert block["family"] == "hnsw"
        assert block["kind"] == "declared"
        # The stub ships an unresolved declaration, so the honest answer here
        # is couldn't-check -- not a capability and not a refusal.
        assert [e["state"] for e in block["engines"]] == [
            IF.COVERAGE_UNRESOLVED], block


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


# ------------------------------------------------------- multi-node wiring
# docs/MULTI_NODE.md §6: "a declared list of endpoints in the requirements
# file rather than one." These check the wiring, not the measurement --
# `test_load_multi_node.py::test_per_node_fan_out_against_a_real_three_node_
# cluster` is where a genuine fan-out is measured, against a real cluster.
def test_no_node_endpoints_declared_means_no_load_per_node_key():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        d = _block(json.load(open(os.path.join(wd, "verify.json"),
                                  encoding="utf-8")))
        assert "load_per_node" not in d, d


def test_fewer_than_two_node_endpoints_is_couldnt_check_not_a_guess():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp, verify_block={
            "kind": "declared", "target": "local", "engine": "stub",
            "endpoint": "memory://", "ks": [10],
            "engine_params": {"m": 32, "hnsw_ef": 128},
            "node_endpoints": ["memory://only-one"]})
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        d = _block(json.load(open(os.path.join(wd, "verify.json"),
                                  encoding="utf-8")))
        assert d["load_per_node"]["outcome"] == "couldnt_check", d
        assert d["load_per_node"]["nodes"] == []


def test_two_or_more_node_endpoints_reach_run_load_per_node():
    """Proves the wiring, not the measurement: a fresh stub instance per
    node starts with an empty namespace (`StubEngine.__init__`), so every
    search against it fails -- the same gap `docs/MULTI_NODE.md` §4.2
    describes for a namespace that is not actually shared cluster state,
    which this function "does not check and cannot" (`run_load_per_node`'s
    own docstring).

    This was expected to surface as a raised error and did not: `run_load`
    (`oneground/verify/load.py` line 270) catches every per-request
    exception and counts it as `errors`, by design, so a load run
    degrades under real transient failures instead of aborting. Wiring
    this in surfaces what that means for fan-out specifically and the
    unit tests for `run_load_per_node` alone did not, because they only
    ever exercise it against a real, shared cluster
    (`test_load_multi_node.py`): a node whose namespace was never
    replicated reports `outcome: measured`, `error_rate: 1.0`,
    `achieved_qps: 0.0` -- the identical shape a genuinely healthy-but-
    saturated node would report at concurrency high enough to time
    everything out. Nothing in the row says "this node never had the
    data" versus "this node is failing under load"; a reader has to
    already know the deployment replicated the namespace to tell them
    apart. That asymmetry is worth a finding of its own, not a fix
    invented here: MULTI_NODE.md never promises the two are
    distinguishable, and inventing a distinguishing signal is exactly the
    kind of guess this task's brief says to report instead of build.
    """
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp, verify_block={
            "kind": "declared", "target": "local", "engine": "stub",
            "endpoint": "memory://", "ks": [10],
            "engine_params": {"m": 32, "hnsw_ef": 128},
            "node_endpoints": ["memory://a", "memory://b"]})
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        d = _block(json.load(open(os.path.join(wd, "verify.json"),
                                  encoding="utf-8")))
        lpn = d["load_per_node"]
        assert lpn["outcome"] == "measured", lpn
        assert len(lpn["nodes"]) == 2, lpn
        for node in lpn["nodes"]:
            assert node["error_rate"] == 1.0, node
            assert node["achieved_qps"] == 0.0, node


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


# ------------- the engine restart between load runs (task 017b)
# On a pod the engines are native processes, not containers, so there is
# nothing for `docker restart` to act on. The session supplies the command.

class _FakeEngine:
    """Connects on demand; records how many times it was asked to."""

    def __init__(self, fail_times=0):
        self.connects = 0
        self.fail_times = fail_times

    def connect(self, endpoint, credentials_env=None):
        self.connects += 1
        if self.connects <= self.fail_times:
            raise RuntimeError("not up yet")


class _Ready200:
    """A server that answers 200, so a restart can legitimately succeed.

    Task 017c: the tests below used to point at `http://localhost:1` -- nothing
    listening -- and still assert "restarted via ...". They passed because the
    old reconnect loop claimed reachability on `connect()` alone, which is the
    overstatement 017c removed. Asserting a successful restart now requires
    something that actually answers, which is exactly the point.
    """

    def __enter__(self):
        import http.server
        import threading

        class _H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):                              # noqa: N802
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return "http://127.0.0.1:%d" % self.srv.server_port

    def __exit__(self, *exc):
        self.srv.shutdown()
        return False


def _restart(engine, cfg, name, env=None, endpoint=None, **kw):
    old = os.environ.get("ONEGROUND_ENGINE_RESTART_COMMAND")
    if env is None:
        os.environ.pop("ONEGROUND_ENGINE_RESTART_COMMAND", None)
    else:
        os.environ["ONEGROUND_ENGINE_RESTART_COMMAND"] = env
    try:
        return verify.restart_engine(engine, cfg, name,
                                     endpoint or "http://localhost:1",
                                     log_fn=lambda m: None, **kw)
    finally:
        if old is None:
            os.environ.pop("ONEGROUND_ENGINE_RESTART_COMMAND", None)
        else:
            os.environ["ONEGROUND_ENGINE_RESTART_COMMAND"] = old


def test_the_session_env_var_supplies_the_restart_command():
    """How a pod sets it: there is no container to fall back on.

    Task 017c: the endpoint is now a server that answers, because claiming a
    successful restart requires a probe that succeeded.
    """
    e = _FakeEngine()
    with _Ready200() as ep:
        note = _restart(e, {}, "qdrant", env=sys.executable + ' -c "pass"',
                        endpoint=ep)
    assert note.startswith("restarted via"), note
    assert "reachable again" in note and "-> 200" in note, note
    assert e.connects == 1, "it did not reconnect the adapter"


def test_the_engine_name_is_substituted():
    """One session measures both engines and they restart differently. A
    command that ignored which engine it was restarting would restart the
    wrong one and report success anyway."""
    script = sys.executable + ' -c "import sys; sys.exit(0)" # {engine}'
    # `pgvector` has no probe that an HTTP stub can satisfy, so this asserts
    # the substitution on the failure path: the command name is echoed back
    # either way, and that is what is under test here.
    with pytest.raises(verify.VerifyError) as exc:
        _restart(_FakeEngine(), {}, "pgvector", env=script, timeout=2.0)
    msg = str(exc.value)
    assert "pgvector" in msg, msg
    assert "{engine}" not in msg, msg
    # Task 018c: and it is the READINESS failure, not the spawn failure.
    # Before the budgets were split this assertion could not be made, because
    # on a slow machine the 2.0 s was spent starting the interpreter and the
    # probe loop was never reached -- so the test went red for a reason that
    # had nothing to do with what it is named for.
    assert "did not answer a readiness probe" in msg, msg
    assert "could not be run" not in msg, msg


# ------------------------------------------- the two budgets (task 018c)

def test_the_command_budget_is_never_below_the_floor_or_the_readiness_budget():
    """The rule, as one expression with one test.

    A spawn budget derived as a fraction of the readiness budget would have
    the same defect in a smaller size; a floor that REPLACED the readiness
    budget would shorten what a long-running session asked for. It is a
    maximum of the two, so no caller ever gets less than it got before 018c.
    """
    floor = verify.RESTART_COMMAND_TIMEOUT
    assert floor >= 30.0, "a floor under 30 s is not a floor for a process"
    # The production default, unchanged: the only caller passes no timeout.
    got = verify.restart_command_timeout(180.0)
    assert got == 180.0, (
        "the production path changed: a session's restart command used to get "
        "180 s and now gets %s" % got)
    # A short readiness budget gets the floor, not two seconds.
    for ready in (2.0, 0.0):
        got = verify.restart_command_timeout(ready)
        assert got == floor, (
            "a %.1f s readiness budget gave the command %s s; the two budgets "
            "are still shared" % (ready, got))
    # Never below either input, for any combination.
    for ready in (0.0, 0.5, 2.0, 30.0, 59.9, 60.0, 120.0, 180.0, 3600.0):
        got = verify.restart_command_timeout(ready)
        assert got >= ready, (ready, got)
        assert got >= floor, (ready, got)
    # An explicit budget wins, including a deliberately tiny one: a caller
    # that means "this command must return at once" must be able to say so.
    got = verify.restart_command_timeout(180.0, command_timeout=0.5)
    assert got == 0.5, ("an explicit command budget was overridden: %s" % got)


def test_a_spawn_slower_than_the_readiness_budget_still_reaches_the_probe():
    """The regression, with a command that is genuinely slow rather than a
    mocked one.

    This is task 018b's flake made deterministic. The command sleeps for
    longer than the readiness budget; before 018c that consumed the whole
    budget, `subprocess.run` raised `TimeoutExpired`, `restart_engine`
    RETURNED "not restarted", and a caller waiting for the readiness verdict
    got a sentence about the shell instead.

    No monkeypatching: the slowness is real, so the test cannot pass because a
    stub was wired up wrongly.
    """
    slow = sys.executable + ' -c "import time; time.sleep(2.5)"'
    started = time.time()
    with pytest.raises(verify.VerifyError) as exc:
        _restart(_FakeEngine(), {}, "pgvector", env=slow, timeout=2.0)
    msg = str(exc.value)
    assert "did not answer a readiness probe" in msg, msg
    assert "could not be run" not in msg, msg
    # The command ran to completion, so the whole thing took longer than the
    # readiness budget alone -- which is the point: the two are not shared.
    assert time.time() - started > 2.5, "the command did not actually run"


def test_an_explicit_command_budget_is_honoured_and_says_which_budget():
    """The other half: a command that really will not return is still
    reported, and the sentence names the budget it exceeded.

    "could not be run" against two seconds reads as a broken command; against
    sixty it reads as a stuck one, and they call for different next steps.
    """
    slow = sys.executable + ' -c "import time; time.sleep(30)"'
    note = _restart(_FakeEngine(), {}, "qdrant", env=slow, timeout=2.0,
                    command_timeout=0.5)
    assert note.startswith("not restarted"), note
    assert "could not be run within its 0.5 s command budget" in note, note
    # And a whole number of seconds is printed as one: `60 s`, not `60.0 s`
    # and not `0 s` for a sub-second budget.
    assert "0.0 s" not in note and "its 0 s" not in note, note


def test_the_readiness_budget_is_not_silently_widened():
    """018c must not have bought reliability by waiting longer.

    The flake would also have gone away if the readiness budget had been
    raised, and that would have been moving a threshold to make a test pass.
    It is still 2.0 s in the test above, and a probe that never answers must
    still give up on schedule.
    """
    quick = sys.executable + ' -c "pass"'
    started = time.time()
    with pytest.raises(verify.VerifyError):
        _restart(_FakeEngine(), {}, "pgvector", env=quick, timeout=2.0)
    elapsed = time.time() - started
    # Spawn plus a 2 s readiness wait. Generous at the top for a slow spawn,
    # but nowhere near the 60 s command floor -- which is what it would be if
    # the readiness loop had inherited the larger number.
    assert elapsed < 30.0, (
        "the readiness loop waited %.1f s against a 2.0 s budget; the two "
        "budgets have been crossed the other way" % elapsed)


def test_the_requirements_block_wins_over_the_environment():
    cfg = {"engine_restart_command": sys.executable + ' -c "pass"'}
    with _Ready200() as ep:
        note = _restart(_FakeEngine(), cfg, "qdrant", env="exit 1",
                        endpoint=ep)
    assert note.startswith("restarted via"), note


def test_no_mechanism_says_so_rather_than_claiming_a_restart():
    """The honest case. A spread measured across runs that shared a warm
    process is a different quantity, and the record has to say which."""
    note = _restart(_FakeEngine(), {"engine_container": ""}, "nosuchengine")
    assert note.startswith("not restarted"), note
    assert "no engine_restart_command" in note, note


def test_a_failing_restart_command_is_reported_not_swallowed():
    note = _restart(_FakeEngine(), {}, "qdrant",
                    env=sys.executable + ' -c "import sys; sys.exit(3)"')
    assert note.startswith("not restarted"), note
    assert "exited 3" in note, note


def test_an_engine_that_never_comes_back_fails_the_run():
    """Task 017c: this used to return a sentence and carry on.

    A sentence in `load_restarts` is not a control-flow mechanism. The run
    continued into its next load phase against an engine that had not come
    back, produced a p95 from it, and left the explanation in a field nobody
    reads until after the report has been believed. It now raises.
    """
    e = _FakeEngine(fail_times=99)
    with pytest.raises(verify.VerifyError) as exc:
        _restart(e, {}, "qdrant", env=sys.executable + ' -c "pass"',
                 timeout=2.0)
    msg = str(exc.value)
    assert "qdrant" in msg, msg
    assert "readiness probe" in msg, msg
    assert "reachable" not in msg, msg
    # The elapsed time, because "it did not come back" and "it did not come
    # back within two seconds" are different claims.
    assert " s" in msg, msg


def test_the_two_named_sessions_carry_the_restart_command():
    """Not synthetic: the session files task 017b was asked to set."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    for name in ("verify-arxiv-smoke-via-product-path.yaml",
                 "verify-arxiv-150k-two-engines.yaml"):
        path = os.path.join(root, "sessions", name)
        with io.open(path, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        cmd = (spec.get("env") or {}).get("ONEGROUND_ENGINE_RESTART_COMMAND")
        assert cmd, f"{name} has no restart command"
        assert "{engine}" in cmd, (name, cmd)
        assert os.path.exists(os.path.join(root, "corpora",
                                           "restart_engine.sh")), \
            "the sessions name a script that does not exist"


def test_every_session_that_names_the_baked_image_names_it_by_digest():
    """A floating tag is what the lock exists to make impossible."""
    from oneground.pod import image as podimage
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    import glob
    for path in sorted(glob.glob(os.path.join(root, "sessions", "*.yaml"))):
        with io.open(path, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        img = str(spec.get("image") or "")
        if "oneground-pod" not in img:
            continue                      # still on the documented base image
        assert "@sha256:" in img, (os.path.basename(path), img)
        assert img == podimage.reference(root), (os.path.basename(path), img)


# ------------- readiness probes: a real request, not a constructed client
# Task 017c. `connect()` returning is not evidence. Qdrant's client is lazy --
# constructing it touches no socket -- so the old loop printed "reachable again
# after 0.1 s" against a server it had never spoken to. Two pod sessions in a
# row died of an engine that was not serving, and nothing at the verify layer
# had asked it anything.

def test_a_lazy_client_does_not_count_as_reachable():
    """The property, stated directly: an engine object that connects without
    touching the network must not produce a "reachable" claim.

    `_FakeEngine.connect` is exactly that lazy client -- it returns without
    doing anything. With nothing listening on the endpoint the probe must fail
    and the run must stop, NOT report the 0.1 s reconnect as readiness.
    """
    e = _FakeEngine()                       # connect() always succeeds
    # Port 1 has nothing on it; an http probe cannot succeed.
    old = os.environ.get("ONEGROUND_ENGINE_RESTART_COMMAND")
    os.environ["ONEGROUND_ENGINE_RESTART_COMMAND"] = sys.executable + ' -c "pass"'
    try:
        with pytest.raises(verify.VerifyError) as exc:
            verify.restart_engine(e, {}, "qdrant", "http://127.0.0.1:1",
                                  log_fn=lambda m: None, timeout=2.0)
    finally:
        if old is None:
            os.environ.pop("ONEGROUND_ENGINE_RESTART_COMMAND", None)
        else:
            os.environ["ONEGROUND_ENGINE_RESTART_COMMAND"] = old
    assert e.connects > 0, "the adapter was never reconnected"
    assert "readiness probe" in str(exc.value), str(exc.value)


def test_the_qdrant_probe_sends_a_real_request_and_needs_200():
    """Against a server that answers 200, and one that answers 500."""
    import http.server
    import threading

    class _Handler(http.server.BaseHTTPRequestHandler):
        code = 200

        def do_GET(self):                                  # noqa: N802
            self.send_response(self.code)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):                         # quiet
            pass

    def _serve(code):
        _Handler.code = code
        srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv

    srv = _serve(200)
    try:
        got = verify.probe_ready("qdrant",
                                 "http://127.0.0.1:%d" % srv.server_port)
        assert "-> 200" in got, got
        assert "/readyz" in got or "/collections" in got, got
    finally:
        srv.shutdown()

    srv = _serve(500)
    try:
        with pytest.raises(verify.VerifyError) as exc:
            verify.probe_ready("qdrant",
                               "http://127.0.0.1:%d" % srv.server_port)
        assert "500" in str(exc.value), str(exc.value)
    finally:
        srv.shutdown()


def test_the_qdrant_probe_fails_when_nothing_is_listening():
    with pytest.raises(verify.VerifyError):
        verify.probe_ready("qdrant", "http://127.0.0.1:1", timeout=1.0)


def test_the_pgvector_probe_fails_when_nothing_is_listening():
    """The engine is not answering. Retryable: it may come up a moment later.

    Split from the driver-absent case below (017c follow-up): the two look the
    same from `pytest.raises(VerifyError)` and are different failures, and
    running them as one test meant whichever came first hid the other.
    """
    with pytest.raises(verify.VerifyError) as exc:
        verify.probe_ready(
            "pgvector",
            "postgresql://nobody:nobody@127.0.0.1:1/nothing", timeout=1.0)
    # It is NOT the unperformable kind: the driver is present, the server is
    # not, and that distinction decides whether restart_engine keeps trying.
    assert not isinstance(exc.value, verify.ProbeUnavailable), exc.value
    assert "SELECT 1" in str(exc.value), str(exc.value)


def test_a_missing_driver_is_a_verdict_not_an_ImportError():
    """Running on an interpreter without psycopg.

    The suite went red on the system interpreter with

        ModuleNotFoundError: No module named 'psycopg'

    which names neither the engine nor the interpreter, says nothing about
    whether the engine is up, and is exactly the under-informative failure the
    probe exists to remove. requirements.txt pins psycopg, so a driver missing
    here means the command is running outside the pins -- and the interpreter
    path is the thing that tells the reader which one they are on.
    """
    import builtins
    real_import = builtins.__import__

    def _no_psycopg(name, *a, **kw):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ModuleNotFoundError("No module named 'psycopg'")
        return real_import(name, *a, **kw)

    builtins.__import__ = _no_psycopg
    try:
        with pytest.raises(verify.VerifyError) as exc:
            verify.probe_ready("pgvector",
                               "postgresql://x:y@127.0.0.1:1/z", timeout=1.0)
    finally:
        builtins.__import__ = real_import

    msg = str(exc.value)
    assert isinstance(exc.value, verify.ProbeUnavailable), type(exc.value)
    assert not isinstance(exc.value, ModuleNotFoundError), msg
    assert "pgvector" in msg, msg                      # the engine
    assert "psycopg" in msg, msg                       # the driver
    assert sys.executable in msg, msg                  # the interpreter
    assert "requirements.txt" in msg, msg              # what to do about it
    # And it must not read as a statement about the engine's health.
    assert "reachable" not in msg, msg


def test_a_missing_driver_stops_the_run_without_burning_the_timeout():
    """Unperformable is not retryable.

    A driver will not install itself, so retrying to the end of the restart
    timeout arrives at the same place having spent it -- and ends on the
    generic "did not answer a readiness probe" message rather than the exact
    one naming the driver and the interpreter.
    """
    import builtins
    import time as _time
    real_import = builtins.__import__

    def _no_psycopg(name, *a, **kw):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ModuleNotFoundError("No module named 'psycopg'")
        return real_import(name, *a, **kw)

    builtins.__import__ = _no_psycopg
    t0 = _time.time()
    try:
        with pytest.raises(verify.ProbeUnavailable) as exc:
            _restart(_FakeEngine(), {}, "pgvector",
                     env=sys.executable + ' -c "pass"', timeout=30.0,
                     endpoint="postgresql://x:y@127.0.0.1:1/z")
    finally:
        builtins.__import__ = real_import
    elapsed = _time.time() - t0
    assert elapsed < 15.0, (
        "a 30 s restart timeout was spent retrying an uninstallable driver: "
        "%.1f s" % elapsed)
    assert "not installed in this interpreter" in str(exc.value), exc.value


def test_a_missing_driver_is_never_reachable_and_never_couldnt_check():
    """The two ways this could be wrong, asserted directly.

    Reachable would be a lie. couldnt_check would be worse than a lie on this
    path: `probe_ready` returning a couldnt_check STRING is the no-probe-for-
    this-engine case, and `restart_engine` treats that as a non-fatal note and
    carries on -- into a measurement against an engine nothing checked.
    """
    import builtins
    real_import = builtins.__import__

    def _no_psycopg(name, *a, **kw):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ModuleNotFoundError("No module named 'psycopg'")
        return real_import(name, *a, **kw)

    builtins.__import__ = _no_psycopg
    try:
        try:
            got = verify.probe_ready("pgvector",
                                     "postgresql://x:y@127.0.0.1:1/z",
                                     timeout=1.0)
        except verify.ProbeUnavailable:
            got = None
    finally:
        builtins.__import__ = real_import
    assert got is None, (
        "a missing driver returned %r instead of raising; a returned string "
        "lets the run continue" % (got,))


def test_the_pgvector_probe_executes_select_1_not_pg_isready():
    """What the probe sends, asserted on the source.

    `pg_isready` reports that the postmaster accepts connections, which is
    true seconds before the database will run a statement -- and that gap is
    the state the failed sessions needed to tell apart from "serving".
    """
    import inspect
    src = inspect.getsource(verify._probe_pgvector)
    assert "SELECT 1" in src, src
    assert "pg_isready" not in src.split('"""')[2], "it shells out to pg_isready"


def test_an_engine_with_no_probe_is_couldnt_check_not_reachable():
    got = verify.probe_ready("someenginenobodywrote", "http://localhost:1")
    assert got.startswith("couldnt_check"), got
    assert "reachable" not in got, got


def test_every_registered_engine_has_a_probe():
    """A new adapter with no probe would silently get the couldnt_check path,
    and its restarts would stop being checked at all."""
    from oneground.adapters import engines
    for name in engines():
        if name == "stub":
            continue
        assert name in verify.PROBES, (
            "%s has no readiness probe; its restarts would go unchecked" % name)


# ---- every run records each engine's settings, or says why not (017f)
# Task 015 added runtime_settings and 017e's report then said "how qdrant,
# pgvector was configured is not recorded in this run" about a run whose
# verify_info.json carried the full settings for both engines. The data was
# there; the reader looked for a key only a one-off backfill script wrote.
# Nothing asserted the data was there, so nothing caught it.

def test_a_verify_run_records_runtime_settings_for_every_engine_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        info = json.load(open(os.path.join(wd, "verify_info.json"),
                              encoding="utf-8"))
        assert info["engines"], info
        for block in info["engines"]:
            facts = block.get("engine_facts") or {}
            assert "runtime_settings" in facts, (
                "%s recorded no runtime_settings at all" % block.get("engine"))
            rs = facts["runtime_settings"]
            assert isinstance(rs, dict), rs
            # Either real settings, or an explicit statement that there are
            # none. An empty dict is neither, and is exactly the ambiguity
            # that let a reader report "not recorded" about a run that had
            # them.
            assert rs, (
                "%s left runtime_settings empty: an empty block cannot be "
                "told apart from one nobody filled in" % block.get("engine"))
            if "couldnt_check" in rs:
                assert len(str(rs["couldnt_check"])) > 20, rs


def test_the_report_reads_the_settings_a_run_actually_records_synthetic():
    """The two halves joined up.

    Asserting the writer alone is what allowed this: `verify` wrote the
    settings, the report looked for a different key, and each side was fine on
    its own.
    """
    from oneground import report as rep
    with tempfile.TemporaryDirectory() as tmp:
        req = _prepared(tmp)
        wd, _ = _capture(verify.run, req, log_fn=_quiet)
        info = json.load(open(os.path.join(wd, "verify_info.json"),
                              encoding="utf-8"))
        engines = [b["engine"] for b in info["engines"]]
        note = rep._tuning_note(info, engines)
        assert note, "the report produced no configuration sentence at all"
        # The stub declares it has none, so the sentence must say that rather
        # than claim the run failed to record anything.
        assert "not recorded in this run" not in note, note


def test_a_block_with_only_bookkeeping_is_still_not_recorded_synthetic():
    """The guard must not be fooled by a block that carries only provenance.

    `source`, `backfilled_by` and friends describe the RECORD, not the
    engine. A block holding only those has said nothing about configuration.
    """
    from oneground import report as rep
    info = {"engines": [{"engine": "qdrant", "engine_facts": {
        "runtime_settings": {"source": "somewhere",
                             "backfilled_by": "a script"}}}]}
    note = rep._tuning_note(info, ["qdrant"])
    assert "not recorded in this run" in note, note
    assert rep._recorded_settings(
        info["engines"][0]["engine_facts"]["runtime_settings"]) == {}


def test_real_settings_are_reported_as_recorded_synthetic():
    from oneground import report as rep
    info = {"engines": [{"engine": "pgvector", "engine_facts": {
        "runtime_settings": {"shared_buffers": "256MB", "work_mem": "4MB",
                             "max_connections": "100",
                             "index_build": "synchronous",
                             "source": "read from the engine"}}}]}
    note = rep._tuning_note(info, ["pgvector"])
    assert "not recorded in this run" not in note, note
    assert "4 settings read from the engine" in note, note
    assert "index build synchronous" in note, note
    # And it must not claim they are the vendor's defaults.
    assert "engine defaults" not in note, note


# ---- unanswerable is not the same as noisy (task 017f item 1)
# Session 20260913-161921 refused Qdrant's latency as "environment noise" --
# which reads as a bad day, rerun it somewhere quieter. It was not: the pod was
# fast enough that the round trip was 60% of the p95, and no rerun on that
# class of host would have changed it. That is a question the environment
# cannot answer, and saying so has to name what would.

def _noise_row(p95, rtt, engine, transport):
    shape = {"p50_ms": p95 * 0.6, "p95_ms": p95, "p99_ms": p95 * 1.3,
             "mean_ms": p95 * 0.7, "n_queries": 2000, "concurrency": 1}
    row = {}
    verify._apply_noise_guard(row, shape, {"p95_ms": rtt}, 10,
                              engine=engine, transport=transport)
    return row


def test_the_fastest_transport_makes_it_unanswerable_not_noisy():
    row = _noise_row(7.72, 4.62, "qdrant", "grpc")
    msg = row["latency_shape_single_client"]
    assert isinstance(msg, str), msg
    assert "unanswerable in this environment" in msg, msg
    assert "environment noise" not in msg, msg
    assert row.get("latency_unanswerable_here") is True
    # It must say what WOULD answer it, or it is just a nicer refusal.
    for hint in ("larger corpus", "higher k", "in-process", "bottleneck"):
        assert hint in msg, (hint, msg)
    assert "not by re-running this one" in msg, msg


def test_a_slower_transport_is_still_noise_and_names_the_faster_one():
    """HTTP with gRPC available is a client choice, not a dead end."""
    row = _noise_row(7.72, 4.62, "qdrant", "http")
    msg = row["latency_shape_single_client"]
    assert "environment noise" in msg, msg
    assert "unanswerable" not in msg, msg
    assert "grpc would lower the round trip" in msg.lower(), msg
    assert row.get("latency_unanswerable_here") is None


def test_pgvector_on_libpq_is_unanswerable_when_the_path_dominates():
    """Not a Qdrant special case: the rule is about the fastest transport an
    adapter has, whichever engine it is."""
    row = _noise_row(1.0, 0.5, "pgvector", "libpq")
    assert "unanswerable in this environment" in row[
        "latency_shape_single_client"]


def test_a_clean_row_is_untouched_and_records_the_transport():
    row = _noise_row(100.0, 0.5, "qdrant", "grpc")
    assert isinstance(row["latency_shape_single_client"], dict), row
    assert row["transport"] == "grpc"
    assert row.get("latency_unanswerable_here") is None
    assert "latency_measured_but_not_attributable" not in row


def test_an_unknown_transport_falls_back_to_the_noise_wording():
    """Not knowing the transport must not upgrade a refusal to unanswerable:
    that claim rests on having already used the fastest client available."""
    row = _noise_row(7.72, 4.62, "qdrant", None)
    assert "environment noise" in row["latency_shape_single_client"]
    assert "unanswerable" not in row["latency_shape_single_client"]


def test_the_qdrant_adapter_defaults_to_trying_grpc():
    """`prefer_grpc=None` means try it and find out. It was False, so the
    faster transport was never attempted on any run."""
    import inspect
    from oneground.adapters.qdrant import adapter as qa
    sig = inspect.signature(qa.QdrantAdapter.__init__)
    assert sig.parameters["prefer_grpc"].default is None
    src = inspect.getsource(qa.QdrantAdapter.connect)
    # And it must PROVE the channel rather than trust a lazily built client.
    assert "get_collections()" in src, src[-400:]
    assert "_transport" in src
