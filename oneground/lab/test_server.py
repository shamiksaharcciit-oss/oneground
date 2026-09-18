"""`oneground lab`, tested (task 024).

**Synthetic throughout**, except the tests that read the shipped modules and
the interface's own files. The server is proven on real runs in task 024's
report.

The properties:

    read-only   a session that exercises every endpoint changes no file and
                creates none, and no write is attempted in the process
    transport   the server sends the views' drawings byte for byte, imports
                nothing that measures, and the contract's guard passes over
                everything it imports
    token       every request without this session's token is refused
    paths       traversal, absolute paths and directory listings are refused
    host        non-loopback needs --i-know; an unexpected Host is refused
    methods     only GET; no CORS; a strict Content-Security-Policy
    mode        chosen by several readings against a frame with a margin,
                shown in the caption, and overridable with the same caption
                behaviour
    offline     the interface asks for nothing from another origin

    python oneground/lab/test_server.py
    python -m pytest oneground/lab/test_server.py
"""

import builtins
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(
    __file__)), "..", ".."))
sys.path.insert(0, REPO)

from oneground.lab import contract, guard, server        # noqa: E402
from oneground.lab import test_lab as T                   # noqa: E402
from oneground.lab.runs import LabRunError, LoadedRun     # noqa: E402
from oneground.lab.views import (GroundView, QueryIndexView,  # noqa: E402
                                 QueryTraceView)

TOKEN = "test-token-not-a-secret"
ROUTES = ("/", "/static/lab.css", "/static/lab.js", "/api/check", "/api/run",
          "/api/ground", "/api/trace", "/api/query-index", "/api/ids?rows=0")


def _manifest(directory, names):
    with open(os.path.join(directory, "MANIFEST.sha256"), "w",
              encoding="utf-8", newline="\n") as f:
        for name in names:
            with open(os.path.join(directory, name), "rb") as g:
                f.write(f"{hashlib.sha256(g.read()).hexdigest()}  {name}\n")


def _workdir(root, name="run", eps=0.2, seconds=(240.0, 60.0),
             receipts=False):
    """A run directory as characterize and simulate --emit-state leave it.

    `receipts` adds what characterize writes beside the characterization:
    the declared ambiguity ratio, and the corpus's own ids for the 12 base
    rows and 3 queries."""
    state_dir, _ = T._run(root, name, eps, seconds, "requirements.synthetic.yaml")
    wd = os.path.dirname(state_dir)
    characterization = {"characterization": {}}
    files = [("simulate.json", {"rows": []})]
    if receipts:
        characterization["definitions"] = {"ambiguity_ratio": 1.17}
        files += [("sample_ids.json", [f"doc-{i}" for i in range(12)]),
                  ("queries_ids.json", ["q-alpha", "q-beta", "q-gamma"])]
    files.append(("characterization.json", characterization))
    for fname, body in files:
        with open(os.path.join(wd, fname), "w", encoding="utf-8") as f:
            json.dump(body, f)
    _manifest(wd, [f for f, _ in files] + ["simulate_info.json"])
    _manifest(state_dir, ["synthetic.state.npz", "state_info.json"])
    return wd


def _digests(root):
    out = {}
    for base, _, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as f:
                out[os.path.relpath(path, root)] = \
                    hashlib.sha256(f.read()).hexdigest()
    return out


def _lab(wd, also=(), **kw):
    run = LoadedRun(wd, also=also)
    return server.LabServer(run, draws=4, token=TOKEN, **kw).start()


def _get(lab, path, token=TOKEN, header=True, host=None, method="GET",
         extra=None):
    conn = http.client.HTTPConnection("127.0.0.1", lab.port, timeout=30)
    headers = {"Host": host or f"127.0.0.1:{lab.port}"}
    if token is not None and header:
        headers[server.TOKEN_HEADER] = token
    elif token is not None:
        path = path + ("&" if "?" in path else "?") + f"token={token}"
    headers.update(extra or {})
    conn.request(method, path, headers=headers)
    response = conn.getresponse()
    body = response.read()
    result = (response.status, dict(response.getheaders()), body)
    conn.close()
    return result


# --------------------------------------------------------------- read-only
def test_a_full_session_writes_nothing_synthetic():
    """Every endpoint, refused requests included, while every way this process
    could write a file is watched. The workdir and the other run's directory
    come out byte for byte as they went in, with no file added."""
    with tempfile.TemporaryDirectory() as tmp:
        wd = _workdir(tmp, "run", 0.2, receipts=True)
        also = _workdir(tmp, "other", 0.1, (90.0, 30.0))
        before = _digests(tmp)

        attempts = []
        real_open = builtins.open
        watched = {name: getattr(os, name) for name in (
            "makedirs", "mkdir", "remove", "unlink", "rename", "replace",
            "rmdir")}

        def guarded_open(file, mode="r", *args, **kwargs):
            if any(flag in str(mode) for flag in "wax+"):
                attempts.append(("open", str(file), mode))
            return real_open(file, mode, *args, **kwargs)

        def refuse(name):
            def watcher(*args, **kwargs):
                attempts.append((name, args))
                return watched[name](*args, **kwargs)
            return watcher

        lab = _lab(wd, also=[also])
        builtins.open = guarded_open
        for name in watched:
            setattr(os, name, refuse(name))
        try:
            statuses = []
            for path in ("/", "/static/lab.css", "/static/lab.js",
                         "/api/check", "/api/run"):
                statuses.append(_get(lab, path)[0])
            for eps in ("", "0", "0.1", "0.15", "0.2", "0.5"):
                statuses.append(_get(lab, f"/api/ground?epsilon={eps}")[0])
                statuses.append(
                    _get(lab, f"/api/query-index?epsilon={eps}")[0])
                for q in (0, 1, 2):
                    statuses.append(
                        _get(lab, f"/api/trace?query={q}&epsilon={eps}")[0])
            statuses.append(_get(lab, "/api/ids?rows=0,5,11")[0])
            refused = [_get(lab, "/api/run", token=None)[0],
                       _get(lab, "/../simulate.json")[0],
                       _get(lab, "/api/run", method="POST")[0],
                       _get(lab, "/api/trace?query=99")[0]]
        finally:
            builtins.open = real_open
            for name, fn in watched.items():
                setattr(os, name, fn)
            lab.stop()

        assert all(s == 200 for s in statuses), statuses
        assert refused == [403, 404, 405, 400], refused
        assert attempts == [], f"the lab tried to write: {attempts}"
        assert _digests(tmp) == before, "a file changed or appeared"


# --------------------------------------------------------------- transport
def test_the_server_sends_the_views_drawings_unchanged_synthetic():
    """A transport: each response is the view's own drawing, serialised, byte
    for byte -- the ground recounted, a simulated trace from its own state,
    and a trace between simulated epsilons."""
    with tempfile.TemporaryDirectory() as tmp:
        wd = _workdir(tmp, "run", 0.2)
        also = _workdir(tmp, "other", 0.1, (90.0, 30.0))
        lab = _lab(wd, also=[also])
        try:
            run = lab.run

            def expected(drawing):
                return json.dumps(drawing.as_dict(), allow_nan=False,
                                  separators=(",", ":")).encode("utf-8")

            for eps in (0.05, 0.15, 0.2):
                want = contract.draw(
                    GroundView(run.epsilon_set(eps), k=10,
                               render=lab.render), *run.base)
                status, _, body = _get(lab, f"/api/ground?epsilon={eps}")
                assert status == 200 and body == expected(want), eps

            for q, eps in ((0, 0.1), (1, 0.15), (2, 0.2)):
                want = contract.draw(
                    QueryTraceView(q, 10, eps=run.epsilon_set(eps),
                                   ambiguity=run.ambiguity),
                    *run.trace_state(eps))
                status, _, body = _get(lab,
                                       f"/api/trace?query={q}&epsilon={eps}")
                assert status == 200 and body == expected(want), (q, eps)

            for eps in (0.1, 0.15, 0.2):
                want = contract.draw(
                    QueryIndexView(10, eps=run.epsilon_set(eps),
                                   ambiguity=run.ambiguity),
                    *run.trace_state(eps))
                status, _, body = _get(lab,
                                       f"/api/query-index?epsilon={eps}")
                assert status == 200 and body == expected(want), eps
            panel = json.loads(_get(lab, "/api/trace?query=0&epsilon=0.15")
                               [2])["panels"]["recall"]
            assert panel["status"] == contract.NOT_SIMULATED
            assert panel["simulated_epsilons"] == [0.1, 0.2]
            assert panel["cost_minutes"]["low"] == 2.0
            assert panel["action"]["command"].startswith("oneground simulate")
        finally:
            lab.stop()


def test_the_server_modules_pass_the_transport_guard():
    """Not synthetic: the shipped server and run reader."""
    assert guard.check_views() == {}
    found = guard.check_transport()
    assert found == {}, found


def test_the_transport_guard_catches_computation_synthetic():
    cases = {
        "import numpy as np\n": "import",
        "from oneground.measures.crispness import centroid_dists\n": "import",
        "from ..models import state\n": "import",
        "import faiss\n": "import",
        "def f(a, b):\n    return a @ b\n": "vector-arithmetic",
        "def f(x):\n    return x.dot(x)\n": "vector-arithmetic",
        "def f(s):\n    return s.centroids\n": "vector-data",
        "def f(s):\n    return s['partition.centroids']\n": "vector-data",
        "def f(s):\n    return eval(s)\n": "dynamic-code",
    }
    for source, rule in cases.items():
        got = guard.transport_violations(source)
        assert any(r == rule for _, r, _ in got), (source, got)
    # a server may read files and speak HTTP; a view may do neither
    assert guard.transport_violations(
        "import http.server, json, os\n"
        "def f(p):\n    return open(p).read()\n") == []


def test_everything_the_server_imports_passes_the_guard():
    """Not synthetic: a clean process imports the server, and every oneground
    module it pulled in is read with the transport rules (numpy allowed below
    the server itself). Nothing that measures may be loaded at all."""
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {REPO!r})\n"
        "import oneground.lab.server\n"
        "mods = {n: getattr(m, '__file__', None) for n, m in "
        "list(sys.modules.items()) if n.startswith('oneground')}\n"
        "print(json.dumps(mods))\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=300, cwd=REPO)
    assert r.returncode == 0, r.stderr
    modules = json.loads(r.stdout.strip().splitlines()[-1])

    measuring = [n for n in modules
                 if any(n == m or n.startswith(m + ".")
                        for m in guard.MEASURING)]
    assert measuring == [], f"the server loaded measuring code: {measuring}"

    checked, problems = [], []
    for name, path in sorted(modules.items()):
        if not path:
            continue
        rel = os.path.relpath(path, REPO).replace("\\", "/")
        allowed, _ = guard.TRANSPORT_ALLOWLIST.get(rel, (set(), ""))
        with open(path, encoding="utf-8") as f:
            found = [v for v in guard.transport_violations(
                f.read(), path, package=name.rpartition(".")[0] or name,
                allow_numpy=True) if v[1] not in allowed]
        checked.append(rel)
        if found:
            problems.append((rel, found))
    assert "oneground/lab/server.py" in checked
    assert "oneground/lab/views/ground.py" in checked
    assert problems == [], problems


# ------------------------------------------------------------------- token
def test_every_request_needs_this_sessions_token_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        lab = _lab(_workdir(tmp))
        try:
            for path in ROUTES:
                assert _get(lab, path, token=None)[0] == 403, path
                assert _get(lab, path, token="wrong")[0] == 403, path
                assert _get(lab, path, token="")[0] == 403, path
                assert _get(lab, path)[0] == 200, path
                assert _get(lab, path, header=False)[0] == 200, path
            # the page hands the token to its own assets, and only those
            status, _, page = _get(lab, "/")
            assert TOKEN.encode() in page
            assert server.TOKEN_PLACEHOLDER.encode() not in page
        finally:
            lab.stop()


# ------------------------------------------------------------------- paths
def test_traversal_absolute_paths_and_listings_are_refused_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        wd = _workdir(tmp)
        state_file = os.path.join(wd, "state", "synthetic.state.npz")
        lab = _lab(wd)
        try:
            attempts = [
                "/../simulate.json", "/static/../simulate.json",
                "/static/../../state/synthetic.state.npz",
                "/static/..%2F..%2Fsimulate.json", "/%2e%2e/simulate.json",
                "/static/%2e%2e/%2e%2e/state/synthetic.state.npz",
                "/simulate.json", "/state/synthetic.state.npz",
                "/MANIFEST.sha256", "//etc/passwd", "/C:/Windows/win.ini",
                "/" + state_file.replace("\\", "/"),
                "/" + state_file,
                "/static/", "/static", "/state/", "/api/", "/api",
                "/static/lab.css/..", "/static/index.html",
            ]
            for path in attempts:
                status, _, body = _get(lab, path)
                assert status == 404, (path, status)
                assert not body.startswith(b"PK"), path
                assert b"synthetic.state.npz" not in body, path
        finally:
            lab.stop()


# -------------------------------------------------------------------- host
def test_a_non_loopback_host_needs_i_know_synthetic():
    for host in ("127.0.0.1", "localhost", "::1", "[::1]", "127.0.0.2"):
        assert server.check_host(host) is None, host
    for host in ("0.0.0.0", "192.168.1.10", "::", "example.org"):
        try:
            server.check_host(host)
        except server.LabRefused as e:
            assert "--i-know" in str(e)
        else:
            raise AssertionError(f"{host} was allowed without --i-know")
    warning = server.check_host("0.0.0.0", i_know=True)
    assert warning.startswith("WARNING")
    for named in ("network", "token", "drawing", "digests"):
        assert named in warning, named


def test_the_command_refuses_a_non_loopback_host_before_binding_synthetic():
    from oneground import cli
    with tempfile.TemporaryDirectory() as tmp:
        wd = _workdir(tmp)
        code = subprocess.run(
            [sys.executable, "-m", "oneground.cli", "lab", wd,
             "--host", "0.0.0.0"],
            capture_output=True, text=True, timeout=300, cwd=REPO)
        assert code.returncode == 2, (code.returncode, code.stdout,
                                      code.stderr)
        assert "--i-know" in code.stderr
        assert "http://" not in code.stdout, "it started anyway"
    assert "oneground lab" in cli.UNGUARDED


def test_an_unexpected_host_header_is_refused_synthetic():
    """A page elsewhere that rebinds its name to this machine sends its own
    Host; the lab answers only the addresses it bound."""
    with tempfile.TemporaryDirectory() as tmp:
        lab = _lab(_workdir(tmp))
        try:
            assert _get(lab, "/api/run",
                        host=f"evil.example:{lab.port}")[0] == 403
            assert _get(lab, "/api/run", host="127.0.0.1:1")[0] == 403
            assert _get(lab, "/api/run",
                        host=f"localhost:{lab.port}")[0] == 200
        finally:
            lab.stop()


# ----------------------------------------------------------------- methods
def test_only_get_no_cors_and_a_strict_policy_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        lab = _lab(_workdir(tmp))
        try:
            for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                assert _get(lab, "/api/run", method=method)[0] == 405, method
            status, headers, _ = _get(
                lab, "/api/run", extra={"Origin": "https://evil.example"})
            assert status == 200
            assert not [h for h in headers
                        if h.lower().startswith("access-control-")], headers
            policy = headers["Content-Security-Policy"]
            for part in ("default-src 'none'", "connect-src 'self'",
                         "script-src 'self'", "frame-ancestors 'none'"):
                assert part in policy, part
            assert headers["Referrer-Policy"] == "no-referrer"
            assert headers["Cache-Control"] == "no-store"
        finally:
            lab.stop()


def test_bad_parameters_are_refused_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        lab = _lab(_workdir(tmp))
        try:
            for path in ("/api/trace?query=99", "/api/trace?query=-1",
                         "/api/trace?query=x", "/api/ground?epsilon=x",
                         "/api/ground?epsilon=5", "/api/ground?epsilon=nan",
                         "/api/ground?epsilon=-0.1",
                         "/api/query-index?epsilon=x",
                         "/api/query-index?epsilon=2", "/api/ids",
                         "/api/ids?rows=x", "/api/ids?rows=12",
                         "/api/ids?rows=-1",
                         "/api/ids?rows=" + ",".join(["0"] * 101)):
                assert _get(lab, path)[0] == 400, path
        finally:
            lab.stop()


def test_the_receipts_are_passed_through_as_declared_synthetic():
    """Task 025. The query ids, the base rows' ids and the ambiguity ratio are
    what characterize declared, handed on unchanged; where a run lacks them the
    interface is told so rather than given a guess."""
    with tempfile.TemporaryDirectory() as tmp:
        lab = _lab(_workdir(tmp, "with", receipts=True))
        try:
            run = json.loads(_get(lab, "/api/run")[2])
            assert run["query_ids"] == ["q-alpha", "q-beta", "q-gamma"]
            assert run["ambiguity"] == 1.17
            ids = json.loads(_get(lab, "/api/ids?rows=11,0,5")[2])
            assert ids == {"ids": ["doc-11", "doc-0", "doc-5"]}
            trace = json.loads(_get(lab, "/api/trace?query=2")[2])
            assert trace["figures"]["ambiguous"] is True
        finally:
            lab.stop()

        lab = _lab(_workdir(tmp, "without"))
        try:
            run = json.loads(_get(lab, "/api/run")[2])
            assert run["query_ids"] is None
            assert run["ambiguity"].startswith(contract.COULDNT_CHECK)
            ids = json.loads(_get(lab, "/api/ids?rows=0")[2])
            assert ids["ids"] is None
            assert ids["why"].startswith(contract.COULDNT_CHECK)
            trace = json.loads(_get(lab, "/api/trace?query=2")[2])
            assert "ambiguous" not in trace["figures"]
            assert trace["gaps"]["ambiguous"] == run["ambiguity"]
        finally:
            lab.stop()


# -------------------------------------------------------------------- mode
def test_the_mode_needs_every_reading_inside_the_margin_synthetic():
    """Task 024b: redraw on move only when every reading's p95 is within the
    threshold, which is 25% inside the frame. Readings that straddle it, or
    that fit the frame but not the margin, render on release."""
    t = contract.THRESHOLD_MS
    assert abs(t - contract.FRAME_MS * 0.75) < 1e-9
    assert round(t, 1) == 12.5

    within = server.choose_mode([t - 2, t - 1, t, t - 3, t - 0.5], 20)
    assert within.mode == contract.MOVE and within.verdict == contract.WITHIN
    assert within.p95_ms == t, "the decision turns on the highest reading"

    straddled = server.choose_mode([t - 2, t - 1, t + 0.1], 20)
    assert straddled.mode == contract.RELEASE
    assert straddled.verdict == contract.STRADDLED

    # the case 024 hit: every reading fits the frame, none fits the margin
    frame_only = server.choose_mode([16.3, 16.0, 16.6], 20)
    assert frame_only.mode == contract.RELEASE
    assert frame_only.verdict == contract.ABOVE

    # 024's four real readings at 20k: once inside the frame, three times not
    assert server.choose_mode([16.3, 17.8, 36.3, 26.2], 20).mode == \
        contract.RELEASE

    forced = server.choose_mode([40.0], 20, contract.MOVE)
    assert forced.mode == contract.MOVE and forced.chosen_by == "--mode"
    assert forced.measured == contract.RELEASE
    assert forced.readings_ms == (40.0,)

    try:
        server.choose_mode([], 20)
    except ValueError:
        pass
    else:
        raise AssertionError("a mode was chosen from no reading")

    assert server.p95([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
                       16, 17, 18, 19, 100]) == 19


def test_measuring_stops_at_the_first_reading_above_the_threshold_synthetic():
    """A reading above the threshold settles the decision, so a slow host
    does not pay for the rest; a fast one takes every reading."""
    with tempfile.TemporaryDirectory() as tmp:
        run = LoadedRun(_workdir(tmp))
        calls = []
        real = server.contract.draw

        def slow_draw(view, header, columns):
            calls.append(1)
            time.sleep(0.02)                 # 20 ms: above the threshold
            return real(view, header, columns)

        server.contract.draw = slow_draw
        try:
            slow = server.measure_render_mode(run, draws=4, readings=5)
        finally:
            server.contract.draw = real
        assert slow.mode == contract.RELEASE
        assert len(slow.readings_ms) == 1, slow.readings_ms
        assert slow.verdict == contract.ABOVE

        fast = server.measure_render_mode(run, draws=4, readings=5)
        if fast.verdict == contract.WITHIN:
            assert len(fast.readings_ms) == 5
            assert fast.mode == contract.MOVE


def test_the_measured_mode_is_printed_and_in_the_ground_caption_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        wd = _workdir(tmp)
        lab = _lab(wd)
        try:
            r = lab.render
            assert r.chosen_by == "measurement" and r.p95_ms is not None
            assert r.mode == (
                contract.MOVE if all(x <= contract.THRESHOLD_MS
                                     for x in r.readings_ms)
                else contract.RELEASE)
            line = lab.startup_line(1.0, "run")
            assert lab.url in line and r.mode in line
            assert f"p95 {r.p95_ms:.1f} ms" in line
            assert r.verdict in line and "threshold 12.5 ms" in line
            run = json.loads(_get(lab, "/api/run")[2])
            assert run["render"]["mode"] == r.mode
            caption = json.loads(_get(lab, "/api/ground?epsilon=0.15")[2]
                                 )["caption"]
            assert "Rendering:" in caption and r.mode in caption
            assert contract.NOT_SIMULATED in caption
        finally:
            lab.stop()
        forced = _lab(wd, mode=contract.RELEASE)
        try:
            caption = json.loads(_get(forced, "/api/ground")[2])["caption"]
            assert "chosen by --mode" in caption
            assert "chosen by --mode" in forced.startup_line(1.0, "run")
        finally:
            forced.stop()


# ----------------------------------------------------------------- offline
def test_the_interface_asks_for_nothing_from_another_origin():
    """Not synthetic: the shipped interface files."""
    for name in ("index.html", "lab.css", "lab.js"):
        with open(os.path.join(server.STATIC_DIR, name),
                  encoding="utf-8") as f:
            source = f.read()
        for needle in ("http://", "https://", "@import", "@font-face",
                       "//cdn", "fonts.googleapis"):
            assert needle not in source, (name, needle)
    with open(os.path.join(server.STATIC_DIR, "index.html"),
              encoding="utf-8") as f:
        page = f.read()
    assert "style=" not in page, "inline style would be refused by the CSP"
    assert page.count("<script") == page.count("<script src="), \
        "inline script would be refused by the CSP"


def test_the_interface_script_parses():
    """Not synthetic: the shipped lab.js, parsed by node.

    Task 024b wrote a string literal that broke the whole script while every
    other test here passed: they read the file as text and never run it. A
    script that does not parse is a page that shows nothing. Where node is not
    installed this skips and says so; it does not pass.
    """
    node = shutil.which("node")
    if node is None:
        import pytest
        pytest.skip("node is not on PATH, so lab.js was not parsed")
    result = subprocess.run(
        [node, "--check", os.path.join(server.STATIC_DIR, "lab.js")],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


# ----------------------------------------------------------------- workdir
def test_a_directory_that_is_not_a_run_is_refused_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            LoadedRun(tmp)
        except LabRunError as e:
            for named in ("state/", "simulate.json", "characterization.json",
                          "--emit-state"):
                assert named in str(e), named
        else:
            raise AssertionError("an empty directory was served")


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
        except BaseException as e:            # pytest.skip outside pytest
            if type(e).__name__ != "Skipped":
                raise
            print(f"skip  {name}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
