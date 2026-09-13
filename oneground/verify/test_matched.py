"""Matched-environment rules and the load generator, on synthetic data.

**Synthetic throughout.** The properties under test are the ones that decide
whether a latency number may be believed:

    a row from another environment never settles a latency constraint
    throughput needs a load phase, and a matching concurrency
    the load generator excludes warm-up and never measures recall

    python oneground/verify/test_matched.py
    pytest oneground/verify/test_matched.py
"""

import os
import tempfile
import sys
import time

import numpy as np

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

try:
    import pytest
except ImportError:                                       # pragma: no cover
    class _Skipped(Exception):
        pass

    class pytest:                                         # noqa: N801
        @staticmethod
        def skip(msg):
            raise _Skipped(msg)
else:
    class _Skipped(Exception):
        pass

from oneground.adapters import get as get_engine, namespace_for  # noqa: E402
from oneground.report import verdict as vd  # noqa: E402
from oneground.verify import load as loadgen  # noqa: E402
from oneground.verify import runpod as rp  # noqa: E402

MEETS, FAILS, CC = vd.MEETS, vd.FAILS, vd.COULDNT_CHECK


def sim_row(config="single_node_hnsw[M=32]"):
    return {"family": "single_node_hnsw", "config": config,
            "params": {"M": 32}, "recall_at_10": 0.99,
            "storage_amplification": 1.0, "est_memory_bytes": 6.7e6,
            "fanout": 1.0}


def verify_on(pod_id, p95=12.0, qps=210.0, concurrency=32, k=10):
    return {
        "environment_id": pod_id,
        "searches": {f"k={k}": {
            f"recall_at_{k}": 0.99,
            "latency_shape_single_client": {
                "p50_ms": 5.0, "p95_ms": p95, "p99_ms": p95 * 1.2,
                "mean_ms": 6.0, "n_queries": 2000,
                "concurrency": concurrency, "note": "under load"}}},
        "load": {"achieved_qps": qps, "concurrency": concurrency,
                 "target_qps": 200.0, "errors": 0, "error_rate": 0.0},
    }


# ------------------------------------------- the same-environment rule
def test_a_latency_row_from_another_pod_is_refused_synthetic():
    """The brief's acceptance criterion: cross-pod latency comparison is
    refused. Two pods are two machines with two sets of neighbours."""
    c = {"latency": {"p95_ms": 40, "environment_id": "pod-A"}}
    v = vd.latency_p95(sim_row(), verify_on("pod-B", p95=5.0), c)
    assert v.outcome == CC, (
        "a latency row measured on pod-B settled a constraint targeting "
        "pod-A")
    assert "pod-B" in v.reason and "pod-A" in v.reason
    assert "different machines" in v.reason
    assert v.value is None, "a cross-environment latency value leaked through"


def test_a_latency_row_from_the_named_pod_is_accepted_synthetic():
    c = {"latency": {"p95_ms": 40, "environment_id": "pod-A"}}
    v = vd.latency_p95(sim_row(), verify_on("pod-A", p95=12.0), c)
    assert v.outcome == MEETS
    assert "pod-A" in v.reason


def test_an_unrecorded_environment_cannot_satisfy_a_named_one_synthetic():
    c = {"latency": {"p95_ms": 40, "environment_id": "pod-A"}}
    data = verify_on("pod-A")
    data.pop("environment_id")
    v = vd.latency_p95(sim_row(), data, c)
    assert v.outcome == CC and "unrecorded" in v.reason


def test_qps_from_another_pod_is_refused_synthetic():
    c = {"latency": {"at_qps": 200, "environment_id": "pod-A"}}
    v = vd.qps_target(sim_row(), verify_on("pod-B", qps=500.0), c)
    assert v.outcome == CC and "pod-A" in v.reason


def test_a_constraint_with_no_environment_id_accepts_any_row_synthetic():
    """A user who does not name an environment gets a verdict from whatever
    was measured -- and the reason names the environment, so the omission is
    visible rather than silent."""
    c = {"latency": {"p95_ms": 40}}
    v = vd.latency_p95(sim_row(), verify_on("pod-Z", p95=9.0), c)
    assert v.outcome == MEETS
    assert "pod-Z" in v.reason


# --------------------------------------------------------------- throughput
def test_qps_meets_and_fails_synthetic():
    c = {"latency": {"at_qps": 200, "concurrency": 32}}
    assert vd.qps_target(sim_row(), verify_on("p", qps=210.0), c).outcome == MEETS
    assert vd.qps_target(sim_row(), verify_on("p", qps=150.0), c).outcome == FAILS


def test_qps_is_couldnt_check_without_a_load_phase_synthetic():
    """A single-client run has no throughput to report, and says which
    command produces one."""
    data = verify_on("p")
    data.pop("load")
    v = vd.qps_target(sim_row(), data, {"latency": {"at_qps": 200}})
    assert v.outcome == CC
    assert "no load phase" in v.reason or "load phase" in v.reason
    assert "runpod" in v.reason


def test_qps_at_the_wrong_concurrency_is_couldnt_check_synthetic():
    """Throughput at one concurrency does not transfer to another."""
    c = {"latency": {"at_qps": 200, "concurrency": 32}}
    v = vd.qps_target(sim_row(), verify_on("p", qps=400.0, concurrency=4), c)
    assert v.outcome == CC
    assert "concurrency 4" in v.reason and "32" in v.reason


def test_latency_under_load_is_labelled_as_such_synthetic():
    c = {"latency": {"p95_ms": 40}}
    v = vd.latency_p95(sim_row(), verify_on("p", concurrency=32), c)
    assert "under load at concurrency 32" in v.reason
    assert "not throughput" not in v.reason      # that caveat is for k=1


# ---------------------------------------------------------- load generator
def _engine_with(n=400, dim=16, latency_ms=0.0):
    e = get_engine("stub")(latency_ms=latency_ms)
    e.connect("memory://")
    ns = namespace_for("loadtest", "ns")
    rng = np.random.default_rng(11)
    x = rng.normal(size=(n, dim)).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    e.create_namespace(ns, dim, "inner_product")
    e.upsert(ns, range(n), x)
    q = x[:40].copy()
    return e, ns, q


def test_load_reports_qps_latency_and_errors_synthetic():
    e, ns, q = _engine_with()
    r = loadgen.run_load(e, ns, q, k=10, concurrency=4, target_qps=0,
                         duration_minutes=0.05, warmup_seconds=0.2)
    d = r.as_dict()
    assert d["completed"] > 0
    assert d["achieved_qps"] > 0
    assert d["concurrency"] == 4
    assert d["error_rate"] == 0.0
    for key in ("p50_ms", "p95_ms", "p99_ms"):
        assert key in d["latency_under_load"]


def test_load_never_measures_recall_synthetic():
    """Recall must come from the sequential pass, so a query slowed or
    dropped under load can never be counted as a recall miss."""
    e, ns, q = _engine_with()
    r = loadgen.run_load(e, ns, q, k=10, concurrency=2, target_qps=0,
                         duration_minutes=0.03, warmup_seconds=0.1)
    d = r.as_dict()
    assert not any("recall" in k for k in d), d.keys()
    assert "Recall is not measured here" in d["note"]


def test_load_excludes_the_warmup_synthetic():
    """Counters are reset when measurement starts, so warm-up queries do not
    inflate the completed count or the duration."""
    e, ns, q = _engine_with()
    r = loadgen.run_load(e, ns, q, k=10, concurrency=2, target_qps=0,
                         duration_minutes=0.03, warmup_seconds=0.5)
    assert r.warmup_seconds == 0.5
    assert 1.0 < r.duration_seconds < 4.0, r.duration_seconds
    assert r.as_dict()["warmup_seconds_excluded"] == 0.5


def test_the_token_bucket_holds_the_target_rate_synthetic():
    b = loadgen.TokenBucket(rate=50)
    t0 = time.perf_counter()
    for _ in range(25):
        assert b.take(timeout=5.0)
    elapsed = time.perf_counter() - t0
    # 25 tokens at 50/s cannot arrive faster than the burst allowance permits.
    assert elapsed < 2.0, elapsed


def test_load_reports_a_shortfall_against_the_target_synthetic():
    """When the achieved rate falls well short, the row says so rather than
    letting a reader assume the target was met."""
    e, ns, q = _engine_with(latency_ms=20.0)
    r = loadgen.run_load(e, ns, q, k=10, concurrency=1, target_qps=1000,
                         duration_minutes=0.05, warmup_seconds=0.1)
    d = r.as_dict()
    assert "shortfall" in d, d
    assert "does not diagnose it" in d["shortfall"]


def test_docker_stats_parsing_synthetic():
    assert loadgen._parse_bytes("123.4MiB") == int(123.4 * 1024 ** 2)
    assert loadgen._parse_bytes("2GiB") == 2 * 1024 ** 3
    assert loadgen._parse_bytes("nonsense") == 0


# ------------------------------------------------------------ session spec
class _Req:
    """Enough of `intake.Requirements` for the generator to be exercised.

    `vectors`/`queries`/`resolve` are part of that surface now: the session
    spec asks the requirements file which corpus files git will not carry, so
    a stub without them tests a generator nobody runs.
    """

    name = "t"
    path = "requirements.t.yaml"
    data = {"constraints": {"latency": {"concurrency": 32, "at_qps": 200}}}
    # Absent from disk, so `git_carries` reports them untracked -- fine here:
    # these tests are about caps, the load profile and the engine list.
    vectors = {"path": "./fixtures/t/vectors.npy"}
    queries = {"path": "./fixtures/t/queries.npy"}

    def resolve(self, path):
        if not path:
            return None
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(os.getcwd(), path))


def test_session_spec_caps_at_one_hour_synthetic():
    """The brief forbids raising caps beyond max_hours 1.0, so the generator
    clamps rather than trusting the config."""
    spec = rp.session_spec(_Req(), "runs/x", {"caps": {"max_hours": 8}},
                           ["qdrant"], "img")
    assert spec["caps"]["max_hours"] == 1.0


def test_session_spec_carries_the_load_profile_synthetic():
    spec = rp.session_spec(_Req(), "runs/x", {"duration_minutes": 5},
                           ["qdrant"], "img")
    assert spec["env"]["ONEGROUND_CONCURRENCY"] == "32"
    assert spec["env"]["ONEGROUND_TARGET_QPS"] == "200"
    assert spec["env"]["ONEGROUND_DURATION_MIN"] == "5"
    assert spec["env"]["ONEGROUND_ENGINES"] == "qdrant"
    assert spec["done_marker"] == "DONE"
    # The pod must be told WHICH requirements file to verify. Without this it
    # fell back to a default and a smoke session ran the arXiv requirements,
    # whose vector path does not exist on Linux (task 011, first session).
    assert spec["env"]["ONEGROUND_REQUIREMENTS"] == "requirements.t.yaml"


def test_session_spec_handles_a_list_of_engines_synthetic():
    """Only qdrant exists, but the code path must not assume one engine."""
    spec = rp.session_spec(_Req(), "runs/x", {}, ["qdrant", "future"], "img")
    assert spec["env"]["ONEGROUND_ENGINES"] == "qdrant,future"


def test_the_session_generator_creates_nothing_synthetic():
    """It writes a file and prints instructions. No API call, no pod."""
    import inspect
    src = inspect.getsource(rp)
    for forbidden in ("create_pod", "allow_create", "RunPodClient"):
        assert forbidden not in src, (
            f"the session generator references {forbidden}; only "
            "`oneground pod up` may create a pod")


# ------------------------------------------- corpus inputs (session ...205151)
def _git_repo(tmp, ignore="fixtures/*/vectors.npy\nruns/\n"):
    """A real repository, because the thing under test is what git says."""
    import subprocess
    run = lambda *a: subprocess.run(["git", "-C", tmp] + list(a),
                                    capture_output=True, check=True)
    subprocess.run(["git", "init", "-q", tmp], capture_output=True, check=True)
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    with open(os.path.join(tmp, ".gitignore"), "w", newline="\n") as f:
        f.write(ignore)
    os.makedirs(os.path.join(tmp, "fixtures", "smoke"), exist_ok=True)
    for name in ("vectors.npy", "queries.npy"):
        with open(os.path.join(tmp, "fixtures", "smoke", name), "wb") as f:
            f.write(b"x" * 32)
    run("add", "-A")
    run("commit", "-qm", "init")
    return tmp


def test_git_carries_answers_from_git_not_from_a_comment_synthetic():
    """`requirements.smoke.yaml` says its vectors are committed. They are
    .gitignore line 10. The comment cost a pod."""
    from oneground.verify import runpod as rp
    with tempfile.TemporaryDirectory() as tmp:
        _git_repo(tmp)
        v = os.path.join(tmp, "fixtures", "smoke", "vectors.npy")
        q = os.path.join(tmp, "fixtures", "smoke", "queries.npy")
        assert rp.git_carries(q, tmp) == (True, "tracked")
        assert rp.git_carries(v, tmp) == (False, "git-ignored")


def test_git_carries_reports_untracked_and_outside_separately_synthetic():
    """They need different answers: one is uploaded, one cannot be."""
    from oneground.verify import runpod as rp
    with tempfile.TemporaryDirectory() as tmp:
        _git_repo(tmp)
        new = os.path.join(tmp, "fixtures", "smoke", "extra.npy")
        with open(new, "wb") as f:
            f.write(b"x")
        assert rp.git_carries(new, tmp) == (False, "untracked")
        outside = os.path.join(os.path.dirname(tmp), "elsewhere.npy")
        carried, why = rp.git_carries(outside, tmp)
        assert (carried, why) == (False, "outside the repository")


def _req(tmp, vectors, queries, workdir="./runs/smoke"):
    import yaml
    from oneground import intake
    p = os.path.join(tmp, "requirements.yaml")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump({
            "oneground": 1,
            "run": {"name": "smoke", "mode": "measure", "seed": 1,
                    "workdir": workdir},
            "corpus": {"sample": {"kind": "receipt",
                                  "vectors": {"path": vectors},
                                  "queries": {"path": queries,
                                              "count_min": 1}}},
        }, f)
    return intake.load(p)


def test_only_the_uncarried_corpus_file_becomes_an_input_synthetic():
    """The smoke case exactly: vectors ignored, queries tracked."""
    from oneground.verify import runpod as rp
    with tempfile.TemporaryDirectory() as tmp:
        _git_repo(tmp)
        req = _req(tmp, "./fixtures/smoke/vectors.npy",
                   "./fixtures/smoke/queries.npy")
        inputs, external = rp.corpus_inputs(req, repo_root=tmp)
        assert external == [], external
        assert [i["local"] for i in inputs] == [
            "fixtures/smoke/vectors.npy"], inputs
        # Same relative path on both machines: the pod runs the same
        # requirements file, whose paths are relative to that file.
        assert inputs[0]["remote"] == (
            "/workspace/oneground/fixtures/smoke/vectors.npy"), inputs
        assert inputs[0]["optional"] is False


def test_a_corpus_outside_the_repo_is_never_uploaded_synthetic():
    """The volume-first ruling, enforced rather than remembered.

    arxiv-150k's vectors are 460 MB at an absolute path outside the repo.
    Uploading them up an scp is what that ruling rejected, so they must land
    in `external` and never in `inputs`.
    """
    from oneground.verify import runpod as rp
    with tempfile.TemporaryDirectory() as tmp:
        _git_repo(tmp)
        with tempfile.TemporaryDirectory() as outside:
            v = os.path.join(outside, "vectors.npy")
            q = os.path.join(outside, "queries.npy")
            for p in (v, q):
                with open(p, "wb") as f:
                    f.write(b"x" * 64)
            req = _req(tmp, v, q)
            inputs, external = rp.corpus_inputs(req, repo_root=tmp)
            assert inputs == [], inputs
            assert [lbl for lbl, _p, _w in external] == ["vectors",
                                                         "queries"], external
            assert all(w == "outside the repository"
                       for _l, _p, w in external), external


def test_a_fully_committed_corpus_uploads_nothing_synthetic():
    """No megabytes on the wire for files the bundle already carries."""
    from oneground.verify import runpod as rp
    with tempfile.TemporaryDirectory() as tmp:
        _git_repo(tmp, ignore="runs/\n")
        req = _req(tmp, "./fixtures/smoke/vectors.npy",
                   "./fixtures/smoke/queries.npy")
        inputs, external = rp.corpus_inputs(req, repo_root=tmp)
        assert (inputs, external) == ([], []), (inputs, external)


def test_the_real_smoke_requirements_upload_exactly_the_vectors():
    """Not synthetic: this is the file the next pod session will run.

    `fixtures/*/vectors.npy` is .gitignore line 10 and `queries.npy` is
    tracked, so exactly one corpus file may be uploaded. If this ever comes
    back empty, session 20260909-205151 is about to happen again.
    """
    from oneground.verify import runpod as rp
    from oneground import intake
    req = intake.load("requirements.smoke.yaml")
    inputs, external = rp.corpus_inputs(req)
    assert external == [], external
    assert [i["local"] for i in inputs] == [
        "fixtures/arxiv-smoke/vectors.npy"], inputs


def test_the_real_arxiv_requirements_upload_nothing_and_say_why():
    """Not synthetic: 460 MB of vectors must not go up an scp."""
    from oneground.verify import runpod as rp
    from oneground import intake
    req = intake.load("requirements.arxiv-150k.yaml")
    inputs, external = rp.corpus_inputs(req)
    assert inputs == [], inputs
    assert [lbl for lbl, _p, _w in external] == ["vectors", "queries"], external


# ------------------------------------ the summary crash (session ...213526)
def _result_with_load_row():
    """The shape `_verify_local` produces when a load phase ran.

    `k=10_under_load` carries `recall_at_10` copied from the sequential run --
    the load generator never measures recall -- and a latency shape measured
    under load. This is the row that crashed the summary.
    """
    return {
        "engine": "qdrant", "engine_version": "1.19.1", "mode": "local",
        "ingest": {"vectors_per_second": 2819.0, "n_vectors": 2000,
                   "seconds": 0.7},
        "index": {"indexed_vectors": 2000, "points": 2000, "seconds": 0.5},
        "rtt_baseline_ms": {"p50_ms": 2.89, "p95_ms": 4.19, "n_queries": 50},
        "searches": {
            "k=10": {"recall_at_10": 1.0,
                     "latency_shape_single_client": {"p50_ms": 3.14,
                                                     "p95_ms": 4.38,
                                                     "p99_ms": 5.0}},
            "k=100": {"recall_at_100": 1.0,
                      "latency_shape_single_client": {"p50_ms": 3.71,
                                                      "p95_ms": 5.03,
                                                      "p99_ms": 6.0}},
            # `_verify_local` puts concurrency and a note in this row; the
            # summary reads them to caption it correctly.
            "k=10_under_load": {
                "recall_at_10": 1.0,
                "latency_shape_single_client": {
                    "p50_ms": 4.0, "p95_ms": 5.0, "p99_ms": 7.0,
                    "n_queries": 3000, "concurrency": 8,
                    "note": ("measured UNDER LOAD at concurrency 8; not a "
                             "single-client shape")}},
        },
        "calibration_error_recall": "couldnt_check: no simulate.json",
        # Set by `run()` immediately before it calls _summary.
        "elapsed_seconds": 74.0,
    }


class _Req2:
    name = "arxiv-smoke-via-product-path"


def test_the_summary_survives_an_under_load_row_synthetic():
    """Session 20260909-213526 measured everything and then died here.

        KeyError: 'recall_at_10_under_load'

    `"k=10_under_load".split("=")[1]` is `"10_under_load"`. A string split
    destroyed a completed measurement.
    """
    import io
    import contextlib
    from oneground import verify as V
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        V._summary(_Req2(), _result_with_load_row(), "runs/x")
    out = buf.getvalue()
    assert "k=10_under_load" in out, out
    assert "recall@10" in out, out
    assert "KeyError" not in out


def test_an_under_load_recall_says_where_it_came_from_synthetic():
    """It is the sequential recall, copied. Unlabelled next to load numbers it
    reads as a second measurement of the same thing."""
    import io
    import contextlib
    from oneground import verify as V
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        V._summary(_Req2(), _result_with_load_row(), "runs/x")
    out = buf.getvalue()
    line = [ln for ln in out.splitlines()
            if "recall@10" in ln and "sequential run" in ln]
    assert line, out
    # And the plain k=10 row is not given that caveat, because it earned its
    # number.
    plain = out[out.index("  k=10\n"):out.index("  k=100")]
    assert "sequential run" not in plain, plain


def test_an_under_load_row_is_not_captioned_as_sequential_synthetic():
    """It is measured at the session's concurrency. Printing it under a
    "sequential, 1 client" caption blurs a load measurement into a latency
    shape, which is the distinction this whole target exists to keep."""
    import io
    import contextlib
    from oneground import verify as V
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        V._summary(_Req2(), _result_with_load_row(), "runs/x")
    out = buf.getvalue()
    block = out[out.index("  k=10_under_load"):]
    block = block[:block.index("\n\n")]
    latency = [ln for ln in block.splitlines() if "latency" in ln]
    assert latency, block
    assert "UNDER LOAD at concurrency 8" in latency[0], latency
    # The word belongs in the recall caveat on the line above -- that recall
    # really did come from the sequential run -- but never in the caption of a
    # latency measured under load.
    assert "sequential" not in latency[0], latency
    # And the footer must not claim the opposite of what it just printed.
    assert "Nothing here was measured under load." not in out, out


def test_a_summary_with_no_load_phase_keeps_its_sequential_caveat_synthetic():
    import io
    import contextlib
    from oneground import verify as V
    result = _result_with_load_row()
    del result["searches"]["k=10_under_load"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        V._summary(_Req2(), result, "runs/x")
    out = buf.getvalue()
    assert "Nothing here was measured under load." in out, out
    assert "UNDER LOAD" not in out, out


def test_a_row_with_no_recall_at_all_does_not_crash_synthetic():
    import io
    import contextlib
    from oneground import verify as V
    result = _result_with_load_row()
    del result["searches"]["k=10_under_load"]["recall_at_10"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        V._summary(_Req2(), result, "runs/x")
    assert "k=10_under_load" in buf.getvalue()


def test_every_search_key_shape_parses_to_its_k_synthetic():
    for key, want in (("k=10", "10"), ("k=100", "100"),
                      ("k=10_under_load", "10"),
                      ("k=100_under_load", "100")):
        got = key.split("=", 1)[1].split("_", 1)[0]
        assert got == want, (key, got, want)


# ------------------------------- packaging on failure (session ...213526)
def _bash():
    import shutil
    for c in (os.path.join("C:" + os.sep, "Program Files", "Git", "bin",
                           "bash.exe"), "/usr/bin/bash", "/bin/bash"):
        if os.path.exists(c):
            return c
    return shutil.which("bash")


def _run_package_outputs(files):
    """Source the real runner and call package_outputs on a shell-made fixture.

    Everything -- the workdir, the files, the tarball -- is created inside
    bash. Git Bash's tar reads a `C:/...` argument as `host:path` and goes
    looking for a remote archive, and the runner never sees a Windows path in
    the life it actually leads, so handing it one would be testing the
    harness rather than the runner.

    Returns the CompletedProcess, or None where there is no POSIX shell.
    """
    import subprocess
    bash = _bash()
    if not bash:
        return None
    runner = os.path.abspath("corpora/run_verify_pod.sh").replace("\\", "/")
    touch = "\n".join('printf "{}" > "$WD/%s"' % f for f in files)
    script = (
        'ONEGROUND_RUNNER_LIB=1 . "%s"\n'
        'TMP="$(mktemp -d)"\n'
        'WD="$TMP/runs/smoke"\n'
        'TARBALL="$TMP/out.tgz"\n'
        'mkdir -p "$WD"\n'
        '%s\n'
        # The sourced runner carries `set -e`, so a non-zero package_outputs
        # would abort this harness before it could report the code. Captured
        # the same way the runner itself captures it.
        'rc=0\n'
        'package_outputs "$WD" "$TARBALL" || rc=$?\n'
        'echo "rc=$rc"\n'
        'if [ -f "$TARBALL" ]; then\n'
        '    echo "tarball=yes"\n'
        '    tar -tzf "$TARBALL" | sed "s/^/member=/"\n'
        'else\n'
        '    echo "tarball=no"\n'
        'fi\n'
        'rm -rf "$TMP"\n'
        % (runner, touch))
    return subprocess.run([bash, "-c", script], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def test_the_runner_packages_a_complete_pair():
    p = _run_package_outputs(["verify.json", "verify_info.json"])
    if p is None:
        return                          # no POSIX shell here
    assert "rc=0" in p.stdout, (p.stdout, p.stderr)
    assert "packaged 2 file(s)" in p.stdout, p.stdout
    assert "tarball=yes" in p.stdout, p.stdout
    assert "member=verify.json" in p.stdout, p.stdout
    assert "member=verify_info.json" in p.stdout, p.stdout


def test_the_runner_packages_what_survived_a_crash():
    """`verify` writes verify.json before it prints the summary, so a crash in
    the summary still leaves a complete measurement. It must come home.

    This is session 20260909-213526: everything measured, everything written,
    and `set -e` then killed the script before any of it was packaged.
    """
    p = _run_package_outputs(["verify.json"])
    if p is None:
        return
    assert "rc=0" in p.stdout, (p.stdout, p.stderr)
    assert "packaged 1 file(s)" in p.stdout, p.stdout
    assert "missing: verify_info.json" in p.stdout, p.stdout
    assert "tarball=yes" in p.stdout, p.stdout
    assert "member=verify.json" in p.stdout, p.stdout


def test_the_runner_reports_when_there_is_nothing_to_package():
    p = _run_package_outputs([])
    if p is None:
        return
    assert "rc=1" in p.stdout, (p.stdout, p.stderr)
    assert "nothing to package" in p.stdout, p.stdout
    assert "tarball=no" in p.stdout, p.stdout


def test_done_is_printed_only_on_a_successful_verify():
    """DONE is what `watch` fetches and terminates on. It means the run
    succeeded, not merely that it stopped."""
    src = open("corpora/run_verify_pod.sh", encoding="utf-8").read()
    tail = src[src.index("VERIFY_RC=0"):]
    done = tail.index('echo "DONE"')
    guard = tail.index('if [ "$VERIFY_RC" -ne 0 ]; then')
    assert guard < done, "DONE is printed before the failure guard"
    assert 'exit "$VERIFY_RC"' in tail[guard:done], tail[guard:done]


# ------------------------------------------------- the corpus preflight
# Not synthetic in the part that matters: the preflight source is read out of
# corpora/run_verify_pod.sh and executed, so these test what ships. Only the
# corpus is a fixture -- a real 483 MB tarball is not something a test suite
# should carry, and the code cannot tell the difference.
def _preflight_source():
    src = open("corpora/run_verify_pod.sh", encoding="utf-8").read()
    marker = "<<'ONEGROUND_PREFLIGHT'"
    start = src.index(marker) + len(marker)
    return src[start:src.index("\nONEGROUND_PREFLIGHT\n", start)]


def _corpus_fixture(tmp, corrupt=False, make_tarball=True, loose=False):
    """A requirements file, a release tarball, and a manifest.

    Mirrors the confirmed volume layout: the corpus lives inside a tarball
    under a `fixtures/<name>/` prefix, and there is no loose directory unless
    `loose` asks for one.
    """
    import hashlib
    import tarfile
    import yaml

    corpus = os.path.join(tmp, "workspace", "tiny")
    staging = os.path.join(tmp, "staging", "fixtures", "tiny")
    os.makedirs(staging)
    bodies = {"vectors.npy": b"V" * 4096, "queries.npy": b"Q" * 1024}
    for name, body in bodies.items():
        with open(os.path.join(staging, name), "wb") as f:
            f.write(body)

    tarball = os.path.join(tmp, "workspace", "tiny-large.tgz")
    os.makedirs(os.path.dirname(tarball), exist_ok=True)
    if make_tarball:
        with tarfile.open(tarball, "w:gz") as tf:
            for name in bodies:
                tf.add(os.path.join(staging, name),
                       arcname="fixtures/tiny/" + name)
            # A third member the run never reads; it must not be extracted.
            extra = os.path.join(staging, "sample.jsonl.zst")
            with open(extra, "wb") as f:
                f.write(b"Z" * 2048)
            tf.add(extra, arcname="fixtures/tiny/sample.jsonl.zst")

    if loose:
        os.makedirs(corpus, exist_ok=True)
        for name, body in bodies.items():
            with open(os.path.join(corpus, name), "wb") as f:
                f.write(b"X" * len(body) if corrupt else body)

    manifest = os.path.join(tmp, "MANIFEST.sha256")
    with open(manifest, "w", encoding="utf-8", newline="\n") as f:
        for name, body in bodies.items():
            f.write("%s  %s\n" % (hashlib.sha256(body).hexdigest(), name))

    req = os.path.join(tmp, "requirements.pod.yaml")
    with open(req, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump({
            "oneground": 1,
            "run": {"name": "tiny", "mode": "measure", "seed": 1,
                    "workdir": "./runs/tiny"},
            "corpus": {"sample": {
                "kind": "receipt",
                "vectors": {"path": os.path.join(corpus, "vectors.npy"),
                            "normalized": True},
                "queries": {"path": os.path.join(corpus, "queries.npy"),
                            "count_min": 1}}},
        }, f)
    return req, tarball, manifest, corpus


def _run_preflight(req, tarball, manifest):
    import subprocess
    env = dict(os.environ)
    if tarball:
        env["ONEGROUND_CORPUS_TARBALL"] = tarball
    else:
        env.pop("ONEGROUND_CORPUS_TARBALL", None)
    if manifest:
        env["ONEGROUND_CORPUS_MANIFEST"] = manifest
    else:
        env.pop("ONEGROUND_CORPUS_MANIFEST", None)
    return subprocess.run([sys.executable, "-c", _preflight_source(), req],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=300)


def test_the_preflight_extracts_the_corpus_from_the_release_tarball():
    """The confirmed layout: a tarball on the volume, no loose directory."""
    with tempfile.TemporaryDirectory() as tmp:
        req, tarball, manifest, corpus = _corpus_fixture(tmp)
        p = _run_preflight(req, tarball, manifest)
        assert p.returncode == 0, (p.stdout, p.stderr)
        assert "extracting from" in p.stdout, p.stdout
        assert os.path.exists(os.path.join(corpus, "vectors.npy")), p.stdout
        assert os.path.exists(os.path.join(corpus, "queries.npy")), p.stdout
        # The member prefix is stripped -- no fixtures/tiny/ under the target.
        assert not os.path.exists(os.path.join(corpus, "fixtures")), \
            os.listdir(corpus)
        # And only what the run reads: 50 MB of source records stay packed.
        assert not os.path.exists(os.path.join(corpus, "sample.jsonl.zst")), \
            os.listdir(corpus)


def test_the_preflight_verifies_digests_against_the_repo_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        req, tarball, manifest, _corpus = _corpus_fixture(tmp)
        p = _run_preflight(req, tarball, manifest)
        assert p.returncode == 0, (p.stdout, p.stderr)
        assert p.stdout.count("matches MANIFEST.sha256") == 2, p.stdout


def test_a_corpus_that_is_not_the_one_the_ground_truth_came_from_stops_the_run():
    """The gap the volume-first decision recorded, now closed.

    A partial extraction left by a terminated session is the likely way this
    happens, which is why the check runs on every pass and not only after an
    extraction of this run's own making.
    """
    with tempfile.TemporaryDirectory() as tmp:
        req, tarball, manifest, corpus = _corpus_fixture(
            tmp, corrupt=True, loose=True)
        p = _run_preflight(req, tarball, manifest)
        assert p.returncode == 3, (p.returncode, p.stdout)
        assert "not the corpus this" in p.stdout, p.stdout
        assert "expected " in p.stdout and "actual   " in p.stdout, p.stdout
        # Both digests printed, so the mismatch can be identified off the pod.
        import hashlib
        want = hashlib.sha256(b"V" * 4096).hexdigest()
        got = hashlib.sha256(b"X" * 4096).hexdigest()
        assert want in p.stdout and got in p.stdout, p.stdout


def test_an_already_extracted_corpus_is_not_re_extracted():
    with tempfile.TemporaryDirectory() as tmp:
        req, tarball, manifest, _corpus = _corpus_fixture(tmp, loose=True)
        p = _run_preflight(req, tarball, manifest)
        assert p.returncode == 0, (p.stdout, p.stderr)
        assert "extracting from" not in p.stdout, p.stdout
        assert p.stdout.count("matches MANIFEST.sha256") == 2, p.stdout


def test_neither_corpus_nor_tarball_lists_the_volume_and_exits_3():
    """The original path, kept: one cheap pod reports the real layout."""
    with tempfile.TemporaryDirectory() as tmp:
        req, tarball, manifest, _corpus = _corpus_fixture(
            tmp, make_tarball=False)
        p = _run_preflight(req, tarball, manifest)
        assert p.returncode == 3, (p.returncode, p.stdout)
        assert "neither is the tarball" in p.stdout, p.stdout
        assert "What is actually on the volume" in p.stdout, p.stdout


def test_a_tarball_without_the_wanted_members_lists_what_it_has():
    with tempfile.TemporaryDirectory() as tmp:
        import tarfile
        req, tarball, manifest, _corpus = _corpus_fixture(
            tmp, make_tarball=False)
        junk = os.path.join(tmp, "junk.txt")
        with open(junk, "w") as f:
            f.write("x")
        with tarfile.open(tarball, "w:gz") as tf:
            tf.add(junk, arcname="fixtures/tiny/something-else.npy")
        p = _run_preflight(req, tarball, manifest)
        assert p.returncode == 3, (p.returncode, p.stdout)
        assert "does not contain what this session needs" in p.stdout, p.stdout
        assert "something-else.npy" in p.stdout, p.stdout


def test_a_session_with_no_manifest_says_couldnt_check_not_ok():
    """No manifest is not a pass. It is an unanswered question, named."""
    with tempfile.TemporaryDirectory() as tmp:
        req, tarball, _m, _corpus = _corpus_fixture(tmp)
        p = _run_preflight(req, tarball, None)
        assert p.returncode == 0, (p.stdout, p.stderr)
        assert "couldnt-check" in p.stdout, p.stdout


ARXIV_SESSION = "sessions/verify-arxiv-150k-two-engines.yaml"


def test_the_arxiv_session_declares_a_tarball_and_a_manifest():
    """Not synthetic: this is the session about to be run.

    Renamed in task 015 from verify-arxiv-150k-via-characterize: the session
    is now named for what it does rather than for the workdir it came from,
    because it will be read months later beside task 011's single-engine one.
    """
    import yaml
    spec = yaml.safe_load(open(ARXIV_SESSION, encoding="utf-8"))
    env = spec["env"]
    assert env["ONEGROUND_CORPUS_TARBALL"] == "/workspace/arxiv-150k-large.tgz"
    assert env["ONEGROUND_CORPUS_MANIFEST"] == \
        "fixtures/arxiv-150k/MANIFEST.sha256"
    assert env["ONEGROUND_REQUIREMENTS"] == "requirements.arxiv-150k.pod.yaml"
    assert env["ONEGROUND_CONCURRENCY"] == "32"
    assert env["ONEGROUND_TARGET_QPS"] == "200"
    assert env["ONEGROUND_DURATION_MIN"] == "5"
    # Two engines, in order, measured sequentially on one pod. This is the
    # whole point of the session, and it is the one field that would silently
    # halve the run if it were wrong.
    assert env["ONEGROUND_ENGINES"] == "qdrant,pgvector"
    # The manifest has to reach the pod, and it does so only if git carries it.
    from oneground.verify import runpod as rp
    carried, why = rp.git_carries("fixtures/arxiv-150k/MANIFEST.sha256")
    assert carried, why


def test_the_smoke_session_declares_neither():
    """Its corpus travels in the input archive; there is no volume step."""
    import yaml
    spec = yaml.safe_load(
        open("sessions/verify-arxiv-smoke-via-product-path.yaml",
             encoding="utf-8"))
    assert "ONEGROUND_CORPUS_TARBALL" not in spec["env"], spec["env"]


# ------------------------------- ruling 1: a load constraint needs a load row
def verify_with_load_row(pod_id="pod-A", seq_p95=7.18, load_p95=38.22,
                         concurrency=32, k=10, completed=59999,
                         target_qps=200.0, duration=300.0, errors=0):
    """The shape session 20260909-225058 produced.

    The sequential row is a noise refusal (a string, as `verify` writes it
    when the RTT dominates) and the under-load row is a real measurement.
    """
    return {
        "environment_id": pod_id,
        "rtt_baseline_ms": {"p50_ms": 4.53, "p95_ms": 6.99, "n_queries": 50},
        "searches": {
            f"k={k}": {
                f"recall_at_{k}": 0.99935,
                "latency_shape_single_client": (
                    "couldnt_check: environment noise -- the baseline RTT p95 "
                    f"(6.99 ms) is 97% of the query p95 ({seq_p95} ms)")},
            f"k={k}_under_load": {
                f"recall_at_{k}": 0.99935,
                "latency_shape_single_client": {
                    "p50_ms": 22.75, "p95_ms": load_p95, "p99_ms": 48.48,
                    "n_queries": completed, "concurrency": concurrency,
                    "note": "measured UNDER LOAD"}},
        },
        "load": {"achieved_qps": 199.99, "target_qps": target_qps,
                 "concurrency": concurrency, "completed": completed,
                 "duration_seconds": duration, "errors": errors,
                 "error_rate": 0.0 if not errors else 1.0},
    }


def test_a_load_constraint_is_answered_by_the_under_load_row_synthetic():
    """The arxiv-150k case. The sequential row was refused as noise at 97%
    while the under-load row was attributable at 18%; reading the sequential
    one threw the answer away."""
    c = {"latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32},
         "recall_at_k": {"k": 10}}
    v = vd.latency_p95(sim_row(), verify_with_load_row(), c)
    assert v.outcome == MEETS, v.reason
    assert abs(v.value - 38.22) < 1e-9, v.value
    assert "k=10_under_load" in v.reason, v.reason
    assert "concurrency 32" in v.reason, v.reason
    # The source must name the row that answered, not the one that did not.
    assert "k=10_under_load" in v.source, v.source


def test_a_load_constraint_never_falls_back_to_the_sequential_row_synthetic():
    """No fallback, by ruling. The two measure different things, and
    substituting one for the other answers a question nobody asked."""
    c = {"latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32},
         "recall_at_k": {"k": 10}}
    data = verify_with_load_row()
    del data["searches"]["k=10_under_load"]      # only the sequential row left
    v = vd.latency_p95(sim_row(), data, c)
    assert v.outcome == CC, v.reason
    assert "no k=10_under_load" in v.reason, v.reason
    assert "not a substitute" in v.reason, v.reason
    assert v.value is None, "a sequential p95 leaked into a load verdict"


def test_a_load_constraint_names_what_is_missing_synthetic():
    c = {"latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32},
         "recall_at_k": {"k": 10}}
    data = verify_with_load_row()
    del data["searches"]["k=10_under_load"]
    v = vd.latency_p95(sim_row(), data, c)
    assert "at_qps 200" in v.reason and "concurrency 32" in v.reason, v.reason
    assert "k=10" in v.reason, v.reason


def test_a_constraint_without_at_qps_still_reads_the_sequential_row_synthetic():
    """Unchanged by the ruling: no at_qps means no claim about load."""
    c = {"latency": {"p95_ms": 40}, "recall_at_k": {"k": 10}}
    data = verify_with_load_row()
    # The sequential row here is a noise refusal, and must be carried as one
    # rather than quietly replaced by the under-load row that does exist.
    v = vd.latency_p95(sim_row(), data, c)
    assert v.outcome == CC, v.reason
    assert "k=10" in v.reason and "under_load" not in v.reason, v.reason


def test_an_under_load_row_at_the_wrong_concurrency_is_refused_synthetic():
    """The queue is most of the number, so it does not transfer."""
    c = {"latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32},
         "recall_at_k": {"k": 10}}
    v = vd.latency_p95(sim_row(), verify_with_load_row(concurrency=8), c)
    assert v.outcome == CC, v.reason
    assert "concurrency 8" in v.reason and "32" in v.reason, v.reason


def test_a_load_row_over_the_cap_still_fails_synthetic():
    """The ruling changes which row is read, not the threshold."""
    c = {"latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32},
         "recall_at_k": {"k": 10}}
    v = vd.latency_p95(sim_row(), verify_with_load_row(load_p95=41.0), c)
    assert v.outcome == FAILS, v.reason
    assert "41.00 ms > 40" in v.reason, v.reason


# ------------------------------------ ruling 2: a throttled run is a sustain
def test_a_throttled_run_short_by_one_query_sustains_synthetic():
    """arxiv-150k: 59,999 of 60,000 in five minutes, reported as
    `200.0 qps achieved < 200 target` -- wrong, and self-contradictory as
    printed."""
    c = {"latency": {"at_qps": 200, "concurrency": 32}}
    v = vd.qps_target(sim_row(), verify_with_load_row(), c)
    assert v.outcome == MEETS, v.reason
    assert "sustained" in v.reason, v.reason
    # Both numbers unrounded, so a reader can re-derive the verdict.
    assert "59999 of 60000" in v.reason, v.reason
    assert "short by 1" in v.reason, v.reason
    assert "tolerance of 300" in v.reason, v.reason
    assert "one query per second" in v.reason, v.reason
    assert "199.99" in v.reason, v.reason


def test_the_tolerance_is_one_query_per_second_of_duration_synthetic():
    """Exactly at the tolerance meets; one query beyond it fails."""
    c = {"latency": {"at_qps": 200, "concurrency": 32}}
    at = verify_with_load_row(completed=60000 - 300)      # short by 300
    assert vd.qps_target(sim_row(), at, c).outcome == MEETS
    over = verify_with_load_row(completed=60000 - 301)    # short by 301
    v = vd.qps_target(sim_row(), over, c)
    assert v.outcome == FAILS, v.reason
    assert "did not sustain" in v.reason, v.reason
    assert "short by 301" in v.reason, v.reason


def test_any_error_fails_a_sustain_check_synthetic():
    """Zero errors is not a tolerance; it is the condition."""
    c = {"latency": {"at_qps": 200, "concurrency": 32}}
    v = vd.qps_target(sim_row(), verify_with_load_row(errors=1), c)
    assert v.outcome == FAILS, v.reason
    assert "1 error(s)" in v.reason, v.reason


def test_a_sustain_verdict_says_it_is_not_a_ceiling_synthetic():
    """A throttled run cannot exceed what it was offered, and the reason must
    not let a reader mistake it for the engine's maximum."""
    c = {"latency": {"at_qps": 200, "concurrency": 32}}
    v = vd.qps_target(sim_row(), verify_with_load_row(), c)
    assert "cannot exceed what it was offered" in v.reason, v.reason
    assert "qps_max" in v.reason, v.reason


def test_an_unthrottled_run_is_still_a_plain_ceiling_comparison_synthetic():
    """With no offered rate the achieved number really is a ceiling."""
    c = {"latency": {"at_qps": 200, "concurrency": 32}}
    data = verify_with_load_row(target_qps=0.0)
    data["load"]["achieved_qps"] = 250.0
    v = vd.qps_target(sim_row(), data, c)
    assert v.outcome == MEETS, v.reason
    assert "unthrottled" in v.reason and "ceiling" in v.reason, v.reason

    data["load"]["achieved_qps"] = 150.0
    assert vd.qps_target(sim_row(), data, c).outcome == FAILS


def test_qps_max_is_documented_as_not_implemented():
    """The gap is visible in the source rather than folded into `qps`."""
    src = open("oneground/report/verdict.py", encoding="utf-8").read()
    assert "qps_max" in src, "qps_max is not documented"
    assert "NOT IMPLEMENTED" in src, src[:0]
    assert not hasattr(vd, "qps_max"), \
        "qps_max exists; the ruling said document it, not implement it"


# --------------- ruling 3: a measurement belongs to the config it was made on
def info_built(m=32, ef_construct=200, hnsw_ef=128, index_type="hnsw"):
    """verify_info.json as the arxiv-150k pod wrote it.

    `engine_facts.index_params` is what the engine reported about itself;
    `engine_params` is what oneground asked for. efSearch is query-time, so
    Qdrant lists it only in the second.
    """
    return {
        "engine": "qdrant",
        "engine_params": {"m": m, "ef_construct": ef_construct,
                          "hnsw_ef": hnsw_ef, "indexing_threshold": 1},
        "engine_facts": {
            "index_type": index_type,
            "index_params": {"m": m, "ef_construct": ef_construct,
                             "full_scan_threshold": 10000, "on_disk": False},
        },
    }


def hnsw_row(M=32, efConstruction=200, efSearch=128):
    return {"family": "single_node_hnsw",
            "config": f"single_node_hnsw[M={M},efConstruction={efConstruction},"
                      f"efSearch={efSearch}]",
            "params": {"M": M, "efConstruction": efConstruction,
                       "efSearch": efSearch},
            "recall_at_10": 0.99935, "storage_amplification": 1.0,
            "est_memory_bytes": 6.7e8, "fanout": 1.0}


LOAD_C = {"latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32},
          "recall_at_k": {"k": 10}}


def test_the_built_configuration_gets_the_measurement_synthetic():
    v = vd.latency_p95(hnsw_row(), verify_with_load_row(), LOAD_C,
                       "runpod", info_built())
    assert v.outcome == MEETS, v.reason
    assert abs(v.value - 38.22) < 1e-9, v.value


def test_a_sharded_family_never_claims_a_single_namespace_measurement_synthetic():
    """The arxiv-150k bug. A pod that built one Qdrant collection did not
    build a sharded anything, and six semantic_sharded rows plus one
    hash_sharded row were reading its latency as their own."""
    for family in ("semantic_sharded", "hash_sharded"):
        row = {"family": family, "config": f"{family}[M=32]",
               "params": {"M": 32, "efSearch": 96},
               "recall_at_10": 0.93, "storage_amplification": 1.0,
               "est_memory_bytes": 1.0, "fanout": 3.0}
        for fn in (vd.latency_p95, vd.qps_target):
            v = fn(row, verify_with_load_row(), LOAD_C, "runpod", info_built())
            assert v.outcome == CC, (family, fn.__name__, v.reason)
            assert "was not the one verified" in v.reason, v.reason
            assert family in v.reason, v.reason
            assert v.value is None, "a measured value leaked to %s" % family
            assert "engine_facts.index_params" in v.source, v.source


def test_a_different_efsearch_does_not_claim_the_measurement_synthetic():
    """efSearch is query-time, so Qdrant reports it in engine_params rather
    than index_params. Ignoring it would let a row measured at 128 be claimed
    by one specifying 64 -- the same defect in a subtler place."""
    v = vd.latency_p95(hnsw_row(efSearch=64), verify_with_load_row(), LOAD_C,
                       "runpod", info_built(hnsw_ef=128))
    assert v.outcome == CC, v.reason
    assert "efSearch=64" in v.reason and "hnsw_ef=128" in v.reason, v.reason


def test_a_different_build_parameter_does_not_claim_the_measurement_synthetic():
    for row, key in ((hnsw_row(M=16), "m=32"),
                     (hnsw_row(efConstruction=100), "ef_construct=200")):
        v = vd.latency_p95(row, verify_with_load_row(), LOAD_C, "runpod",
                           info_built())
        assert v.outcome == CC, v.reason
        assert "not the ones the engine was built with" in v.reason, v.reason
        assert key in v.reason, v.reason


def test_the_engines_own_report_is_the_authority_not_the_request_synthetic():
    """`engine_params` is what oneground asked for; an engine may clamp or
    ignore it. `index_params` is what it says it built."""
    info = info_built()
    info["engine_facts"]["index_params"]["m"] = 16      # what it really built
    v = vd.latency_p95(hnsw_row(M=32), verify_with_load_row(), LOAD_C,
                       "runpod", info)
    assert v.outcome == CC, v.reason
    assert "M=32" in v.reason and "m=16" in v.reason, v.reason


def test_a_verify_run_with_no_engine_facts_is_not_refused_synthetic():
    """An older verify.json cannot be checked against. Refusing every option
    on that basis would be inventing a mismatch rather than finding one -- and
    the source string still says where the check would have looked."""
    for info in (None, {}, {"engine": "qdrant"}):
        v = vd.latency_p95(hnsw_row(), verify_with_load_row(), LOAD_C,
                           "runpod", info)
        assert v.outcome == MEETS, (info, v.reason)


def test_the_mismatch_is_checked_before_the_row_is_read_synthetic():
    """A configuration that was not verified must not be reported as a
    latency number that happens to pass, nor as a noise refusal."""
    row = {"family": "semantic_sharded", "config": "semantic_sharded[x]",
           "params": {"M": 32}, "recall_at_10": 0.9,
           "storage_amplification": 1.0, "est_memory_bytes": 1.0,
           "fanout": 3.0}
    data = verify_with_load_row()
    del data["searches"]["k=10_under_load"]     # would otherwise be "missing"
    v = vd.latency_p95(row, data, LOAD_C, "runpod", info_built())
    assert "was not the one verified" in v.reason, v.reason
    assert "no k=10_under_load" not in v.reason, v.reason


def test_the_real_arxiv_workdir_gives_one_option_the_measurement_needs_local_run():
    """Not synthetic: the run this ruling came from.

    Exactly one of the eight simulated options was built in Qdrant, and only
    that one may carry a latency or throughput verdict.

    `runs/` is gitignored -- a workdir is a local artifact, not a fixture --
    so on a fresh clone there is nothing to read. That is an absent artifact,
    not a failure, and the name says the test needs one.
    """
    import json
    wd = "runs/arxiv-150k-via-characterize"
    missing = [n for n in ("simulate.json", "verify.json", "verify_info.json")
               if not os.path.exists(os.path.join(wd, n))]
    if missing:
        pytest.skip("no local arxiv-150k workdir: %s has no %s. Run "
                    "`oneground verify requirements.arxiv-150k.yaml` on a pod "
                    "to produce one." % (wd, ", ".join(missing)))
    sim = json.load(open(os.path.join(wd, "simulate.json"), encoding="utf-8"))
    data = json.load(open(os.path.join(wd, "verify.json"), encoding="utf-8"))
    info = json.load(open(os.path.join(wd, "verify_info.json"),
                          encoding="utf-8"))
    c = {"latency": {"p95_ms": 40, "at_qps": 200, "concurrency": 32},
         "recall_at_k": {"k": 10, "min": 0.95}}

    # The rule is about which option may CARRY a measurement, not about which
    # way the measurement then goes. Asserting MEETS conflated the two, and
    # task 015's pod run made that visible: the same configuration measured
    # 38.22 ms on one pod and 42.82 ms on another, so an assertion on MEETS
    # against a 40 ms threshold was testing the machine, not the rule.
    # Task 017e: a SUBSET of {built}, not exactly it.
    #
    # `== [built]` asserted that some option always carries a measurement, and
    # that is a property of the workdir on disk rather than of the rule. On
    # pod 1ombs4scr257a5 qdrant's latency was refused outright as environment
    # noise -- the pod was fast enough that a 4.62 ms HTTP round trip was 60%
    # of a 7.72 ms under-load p95 -- so NO option carried one and the test
    # failed while the code was right.
    #
    # The rule is one-directional: an option that was not built must never
    # carry a measurement. Zero options carrying one satisfies it. This is the
    # third time a test here has asserted the state of a gitignored workdir
    # instead of the rule (015b, then the price table in 017b); the shape to
    # watch for is an assertion that some measurement EXISTS.
    built = "single_node_hnsw[M=32,efConstruction=200,efSearch=128]"
    for engine, block in vd.engine_blocks(data):
        einfo = dict(vd.engine_info_blocks(info)).get(engine)
        settled = [r["config"] for r in sim["rows"]
                   if vd.latency_p95(r, block, c, "runpod", einfo,
                                     engine=engine).outcome != CC]
        assert set(settled) <= {built}, (
            "%s: an architecture that was never built carried a latency "
            "measurement: %s" % (engine, sorted(set(settled) - {built})))

    # And it is the configuration each engine reported building.
    for engine, einfo in vd.engine_info_blocks(info):
        ip = (einfo.get("engine_facts") or {}).get("index_params") or {}
        m = ip.get("m")
        efc = ip.get("ef_construct", ip.get("ef_construction"))
        assert m == 32 and efc == 200, (engine, ip)
        assert einfo["engine_params"]["hnsw_ef"] == 128, einfo["engine_params"]

    # Task 015b: what this file records about its own shape must be true of
    # it. Which engines a local workdir happens to hold is not a rule -- it is
    # whichever run the developer last did. Asserting `["qdrant", "pgvector"]`
    # made a green suite depend on that, and an 011-shape workdir (one engine,
    # no `engines` list) is exactly as legitimate an artifact as a fresh
    # clone's absent one, which this test already skips for. `engine_blocks`
    # reads both shapes on purpose; so does this.
    measured = [e for e, _ in vd.engine_blocks(data)]
    assert measured and all(measured), measured

    declared = data.get("engines_measured")
    if declared is None:
        # Pre-015 file: it declares no engine list, so there is nothing to
        # check against. Couldn't-check, and it is not rounded up to a pass.
        assert data.get("engines") is None, (
            "a file with an `engines` list must also declare "
            "`engines_measured`: %r" % (data.get("engines"),))
    else:
        assert declared == measured, (declared, measured)
        # Only a multi-engine run makes a claim about ordering.
        if len(measured) > 1:
            assert data.get("sequential") is True, data.get("sequential")

    # Either shape has to say where it ran; the same-environment rule is the
    # whole point of this workdir, and it is what `latency_p95` gates on above.
    assert data.get("environment_id") or all(
        b.get("environment_id") for _, b in vd.engine_blocks(data))


def _main():
    """Run every test in this file without a test-runner dependency.

    Defined at the end of the file on purpose. It collects `globals()`, so
    anything defined below it does not exist yet when it runs -- and for a
    long while this block sat mid-file and silently skipped every test
    appended after it.
    """
    skip_types = (_Skipped,)
    if getattr(pytest, "skip", None) is not None:
        # Under real pytest, `pytest.skip` raises its own Skipped exception.
        try:
            import _pytest.outcomes
            skip_types = (_Skipped, _pytest.outcomes.Skipped)
        except ImportError:                               # pragma: no cover
            pass

    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except skip_types as e:
            skipped += 1
            print(f"skip  {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed - skipped} passed, {failed} failed, "
          f"{skipped} skipped  (of {len(tests)} collected)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())


# ---------- a committed session spec must agree with its requirements (017b)
# A session YAML is GENERATED from a requirements file, then committed. The two
# can then drift with nothing noticing, and a drift is only discovered on a pod
# that is already billing.
#
# Session 20260912-171431 is the worked example. requirements.smoke.yaml has
# said `engines: [qdrant, pgvector]` since task 015; the smoke session spec was
# generated 2026-09-09 and still said `ONEGROUND_ENGINES: qdrant`. So
# run_verify_pod.sh started only qdrant, `verify` read both engines out of the
# requirements, and the run died on "pgvector: connection refused" -- after the
# baked image, the setup and the venv had all worked perfectly.

def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def _session_specs():
    import glob
    import yaml
    root = _repo_root()
    for path in sorted(glob.glob(os.path.join(root, "sessions", "*.yaml"))):
        with open(path, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        if not isinstance(spec, dict):
            continue
        env = spec.get("env") or {}
        req = env.get("ONEGROUND_REQUIREMENTS")
        if not req:
            continue                    # not a verify session
        rpath = os.path.join(root, req)
        if not os.path.exists(rpath):
            continue
        with open(rpath, encoding="utf-8") as f:
            reqs = yaml.safe_load(f)
        yield os.path.basename(path), env, (reqs.get("verify") or {})


def test_every_session_engine_list_matches_its_requirements():
    """The one that cost a pod."""
    for name, env, cfg in _session_specs():
        want = ",".join(str(e) for e in
                        (cfg.get("engines") or [cfg.get("engine", "qdrant")]))
        got = str(env.get("ONEGROUND_ENGINES", ""))
        assert got == want, (
            "%s says ONEGROUND_ENGINES=%r but %s says %r. The session starts "
            "the engines in its own list and `verify` measures the ones in the "
            "requirements; when they differ the run dies on a connection "
            "refused, on a pod, after everything else has worked."
            % (name, got, env.get("ONEGROUND_REQUIREMENTS"), want))


def test_every_session_load_shape_matches_its_requirements():
    """The same class of drift, on the numbers rather than the engine list.

    These variables are descriptive -- the pod echoes them and `verify` reads
    the requirements -- which is exactly why they can rot unnoticed. A session
    record that says `concurrency 8` for a run made at 32 is a receipt that
    lies, quietly, forever.
    """
    import yaml
    for name, env, cfg in _session_specs():
        root = _repo_root()
        with open(os.path.join(root, env["ONEGROUND_REQUIREMENTS"]),
                  encoding="utf-8") as f:
            whole = yaml.safe_load(f)
        lat = (whole.get("constraints") or {}).get("latency") or {}
        checks = (
            ("ONEGROUND_CONCURRENCY", str(lat.get("concurrency", 8))),
            ("ONEGROUND_TARGET_QPS", str(lat.get("at_qps", 0))),
            ("ONEGROUND_DURATION_MIN", str(cfg.get("duration_minutes", 5))),
            ("ONEGROUND_RUNS", str(cfg.get("runs", 1))),
            ("ONEGROUND_MEASURE_CEILING",
             "1" if cfg.get("measure_ceiling") else "0"),
        )
        for key, want in checks:
            got = str(env.get(key, ""))
            assert got == want, (name, key, got, want)


def test_the_smoke_session_asks_for_the_spread_and_the_ceiling():
    """Not a drift check: what this session exists to measure.

    `runs: 1` would produce no spread and `measure_ceiling: false` no qps_max,
    and both would look like a successful run that simply had nothing to say.
    """
    for name, env, cfg in _session_specs():
        if "smoke" not in name:
            continue
        assert int(cfg.get("runs", 1)) >= 3, (name, cfg.get("runs"))
        assert cfg.get("measure_ceiling") is True, name
        assert env.get("ONEGROUND_ENGINE_RESTART_COMMAND"), (
            "%s asks for repeated runs with no way to restart the engine "
            "between them" % name)


ROOT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


# ---------------------------------------------------- the pod image (017d)
# `docker/pod/IMAGE.lock` is the single source of truth for what a session
# pulls. When it names no digest, `_prepare_runpod` refuses rather than
# quietly substituting the base tag: a session on the base image has no
# Postgres, no pgvector, no Qdrant and no venv, so it presents as an
# environment fault several minutes in -- the failure mode that cost two pods
# in task 015. `oneground/pod/image.py` already stated this rule; this was its
# one caller, and it was deciding implicitly.

def _image_cfg(**over):
    cfg = {"target": "runpod", "engines": ["qdrant"],
           "pod_endpoints": {"qdrant": "http://127.0.0.1:6333"}}
    cfg.update(over)
    return cfg


def _resolve_image(monkeypatch, cfg, baked, ref=None):
    """Drive just the image-resolution branch of `_prepare_runpod`."""
    from oneground import verify as V
    from oneground.pod import image as podimage

    monkeypatch.setattr(podimage, "is_baked", lambda *a, **k: baked)
    if ref is not None:
        monkeypatch.setattr(podimage, "reference", lambda *a, **k: ref)

    seen = {}

    def fake_write_session(req, workdir, cfg_, engines, image, **kw):
        seen["image"] = image
        raise _Stop()

    monkeypatch.setattr(V.runpod_target, "write_session", fake_write_session)
    lines = []
    try:
        V._prepare_runpod({}, cfg, ".", "requirements.yaml", lines.append)
    except _Stop:
        pass
    return seen.get("image"), "\n".join(lines)


class _Stop(Exception):
    """Stop `_prepare_runpod` once the image has been chosen."""


def test_a_locked_digest_is_what_the_session_runs_synthetic(monkeypatch):
    from oneground import verify as V
    ref = "ghcr.io/owner/oneground-pod@sha256:" + "c" * 64
    image, log = _resolve_image(monkeypatch, _image_cfg(), baked=True, ref=ref)
    assert image == ref, image
    assert "pinned by digest" in log, log


def test_no_digest_refuses_rather_than_falling_back_synthetic(monkeypatch):
    """The whole point of 017d item 6."""
    from oneground import verify as V
    try:
        _resolve_image(monkeypatch, _image_cfg(), baked=False)
    except V.VerifyError as e:
        msg = str(e)
        assert "IMAGE.lock" in msg, msg
        assert "rebuild.sh" in msg, msg
        # It must name the explicit opt-in rather than just refusing.
        assert "verify:" in msg and V.POD_IMAGE in msg, msg
        return
    raise AssertionError("an unlocked image silently fell back to the base tag")


def test_the_base_tag_still_runs_when_someone_names_it_synthetic(monkeypatch):
    """The fallback is not removed, only made explicit -- and it then appears
    in the receipt as something a person chose."""
    from oneground import verify as V
    image, log = _resolve_image(
        monkeypatch, _image_cfg(image=V.POD_IMAGE), baked=False)
    assert image == V.POD_IMAGE, image
    assert "named in verify.image" in log, log


def test_an_explicit_image_wins_over_the_lock_synthetic(monkeypatch):
    from oneground import verify as V
    ref = "ghcr.io/owner/oneground-pod@sha256:" + "d" * 64
    image, log = _resolve_image(
        monkeypatch, _image_cfg(image="my/own:tag"), baked=True, ref=ref)
    assert image == "my/own:tag", image


def test_pod_image_is_still_the_documented_base_tag():
    """It is the fallback a user names explicitly, so it has to stay a real
    reference and stay the one the docs and the lock both cite."""
    from oneground import verify as V
    from oneground.pod import image as podimage
    assert V.POD_IMAGE.startswith("runpod/pytorch:")
    assert podimage.fallback(ROOT_DIR) == V.POD_IMAGE
