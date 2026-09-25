"""`oneground bridge export` / `oneground bridge import` -- the commands.

`test_export.py` and `test_import_result.py` prove the functions;
this proves the CLI reaches them, per `docs/BRIDGE.md` §7's stated lean
toward "its own command" (`oneground/bridge/cli.py`'s own docstring).

    python oneground/bridge/test_cli.py
    pytest oneground/bridge/test_cli.py
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

from oneground import characterize          # noqa: E402
from oneground import cli as top_cli        # noqa: E402
from oneground import provenance            # noqa: E402
from oneground.bridge import cli            # noqa: E402
from oneground.bridge.test_import_result import _case, _result_file  # noqa: E402

SEED = 20260925


@pytest.fixture(autouse=True)
def _restore_invocation_global():
    """`oneground.cli.main` sets `provenance._INVOCATION`, a module
    global, once per real process -- fine in production, where there is
    one invocation per process. `test_a_missing_requirements_file_is_a_
    refusal_not_a_traceback` below is the one test in this suite that
    calls it for real, and without this, the global it sets (an argv
    naming a machine-local temp path) survives for the rest of this
    pytest process and reaches `test_propose.py::test_a_card_carries_
    no_machine_identifier_synthetic`, which assumes -- correctly, for
    every test that only imports and calls functions -- that `_INVOCATION`
    is still `None` (`provenance.invocation`'s own docstring: "a receipt
    written by a library caller has no invocation"). Found by running the
    full suite, not by reading either module."""
    before = provenance._INVOCATION
    yield
    provenance._INVOCATION = before


def _capture(fn, *a, **kw):
    buf, orig_out = io.StringIO(), sys.stdout
    err_buf, orig_err = io.StringIO(), sys.stderr
    sys.stdout, sys.stderr = buf, err_buf
    try:
        rc = fn(*a, **kw)
    finally:
        sys.stdout, sys.stderr = orig_out, orig_err
    return rc, buf.getvalue() + err_buf.getvalue()


def _characterized_req(tmp, n=400, dim=12, n_queries=40, seed=SEED):
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(3, dim))
    x = np.vstack([c + rng.normal(0, 0.15, size=(n // 3 + 1, dim))
                  for c in centres])[:n].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = rng.normal(0, 1, size=(n_queries, dim)).astype(np.float32)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    vec_p, q_p = os.path.join(tmp, "v.npy"), os.path.join(tmp, "q.npy")
    np.save(vec_p, x)
    np.save(q_p, q)
    workdir = os.path.join(tmp, "out")
    req_path = os.path.join(tmp, "r.yaml")
    with open(req_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump({"oneground": 1,
                        "run": {"name": "cli-synth", "seed": seed,
                                "workdir": workdir},
                        "corpus": {"sample": {
                            "kind": "receipt",
                            "vectors": {"path": vec_p, "normalized": True},
                            "queries": {"path": q_p, "count_min": 10}}}}, f)
    characterize.run(req_path, log_fn=lambda m: None)
    return req_path, workdir


# ------------------------------------------------------------------- export
def test_export_writes_the_card_and_prints_it():
    with tempfile.TemporaryDirectory() as tmp:
        req_path, workdir = _characterized_req(tmp)
        rc, out = _capture(cli.main, [
            "export", req_path,
            "--query-subset-seed", "1", "--query-subset-size", "10"])
        assert rc == 0, out
        wrote_lines = [ln for ln in out.splitlines()
                      if ln.startswith("wrote ")]
        assert wrote_lines, out
        card_path = wrote_lines[0][len("wrote "):].strip()
        assert os.path.exists(card_path), out


def test_a_missing_requirements_file_is_a_refusal_not_a_traceback():
    """`oneground/refusals.py`: `intake.RequirementsError` is printed once,
    by the top-level `main`, not by `bridge/cli.py` itself -- "a refusal
    is produced where it is raised, once." Going through `bridge.cli.main`
    directly (as every other test here does) would prove nothing about
    that contract, since only `oneground.cli.main` wraps `_dispatch` in
    the declared-refusal catch this exercises."""
    with tempfile.TemporaryDirectory() as tmp:
        req_path = os.path.join(tmp, "missing.yaml")
        rc, out = _capture(top_cli.main, [
            "bridge", "export", req_path,
            "--query-subset-seed", "1", "--query-subset-size", "10"])
        assert rc != 0
        assert req_path in out
        assert "Traceback" not in out


# ------------------------------------------------------------------- import
def test_import_prints_raw_numbers_and_a_summary():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "result_run-1.json")
        _result_file(p, [_case(), _case(qps=1.0, recall=0.1)])
        rc, out = _capture(cli.main, ["import", p])
        assert rc == 0, out
        payload = json.loads(out.split("\n\n", 1)[0])
        assert len(payload["cases"]) == 2, payload
        assert all(c["outcome"] == "measured" for c in payload["cases"])


def test_import_refuses_a_file_that_is_not_a_result_file():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "not-a-result.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"unrelated": True}, f)
        rc, out = _capture(cli.main, ["import", p])
        assert rc != 0
        assert "refused" in out


def test_import_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "result_run-1.json")
        _result_file(p, [_case()])
        before = sorted(os.listdir(tmp))
        _capture(cli.main, ["import", p])
        after = sorted(os.listdir(tmp))
        assert before == after


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
