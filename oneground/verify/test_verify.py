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
    """It must fail, and not by importing something that is absent."""
    with pytest.raises(verify.VerifyError):
        verify.probe_ready(
            "pgvector",
            "postgresql://nobody:nobody@127.0.0.1:1/nothing", timeout=1.0)


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
