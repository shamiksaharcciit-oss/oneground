"""`oneground propose translate`, through the real CLI entry point.
`docs/PROPOSALS.md` §2.1. Task 063.

The library function itself (`oneground.proposals.translate.translate`)
is `oneground/proposals/test_translate.py`'s subject, against a real
local HTTP server. This file is the glue: does `cli.main` reach it, print
what §2.1 asks for, and refuse the way every other command line here
refuses -- one line, exit 2, no traceback.
"""

import http.server
import io
import json
import os
import sys
import tempfile
import threading

import pytest
import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground import cli                                       # noqa: E402

POLICY_REPLY = """```yaml
policy:
  family: single_node_hnsw
  configuration: {index: hnsw, M: 32, efConstruction: 200, efSearch: 128}
  changes:
    - param: efSearch
      from: 128
      to: 256
  rationale: probe more candidates
```"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = json.dumps({"model": "test-v1", "choices": [
            {"message": {"content": POLICY_REPLY}}]}).encode("utf-8")
        self.wfile.write(body)


@pytest.fixture
def server():
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_port}/v1"
    httpd.shutdown()


def _workdir(tmp):
    json.dump({
        "intrinsic_dimensionality": 12.4, "boundary_crispness": 0.021,
        "skew_top10_share": 0.31, "ambiguous_query_rate": 0.07,
        "drift": {"drift_before": 0.02, "drift_after": 0.05},
    }, open(os.path.join(tmp, "characterization.json"), "w"))
    yaml.safe_dump({"recommended": {
        "family": "single_node_hnsw",
        "params": {"index": "hnsw", "M": 32, "efConstruction": 200,
                  "efSearch": 128}}},
        open(os.path.join(tmp, "manifest.yaml"), "w"))
    return tmp


def _main(argv):
    buf, orig = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        code = cli.main(argv)
    except SystemExit as e:
        code = e.code
    finally:
        sys.stdout = orig
    return code, buf.getvalue()


# ------------------------------------------------------------ dispatch/refusal
def test_no_model_refuses_with_one_line_exit_2():
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _main(["propose", "translate", _workdir(tmp),
                           "--describe", "probe more"])
        assert code == 2
        assert "no model is bundled" in out
        assert "Traceback" not in out


def test_missing_describe_is_an_argparse_refusal():
    code, _out = _main(["propose", "translate", "/tmp/wd", "--model", "x",
                        "--endpoint", "http://x"])
    assert code == 2


def test_the_command_is_a_real_dispatchable_command():
    assert "oneground propose translate" in cli.dispatchable_commands()


# ---------------------------------------------------------------- the real run
def test_a_successful_translation_shows_the_policy_twice_and_never_runs(
        server):
    with tempfile.TemporaryDirectory() as tmp:
        wd = _workdir(tmp)
        code, out = _main(["propose", "translate", wd, "--describe",
                           "probe more candidates", "--model", "x",
                           "--endpoint", server])
        assert code == 0, out

        policy_path = os.path.join(wd, "policy.yaml")
        assert os.path.exists(policy_path)

        # the plain-English rendering
        assert "This policy proposes a change to single_node_hnsw" in out
        assert "efSearch from 128 to 256" in out
        assert "Rationale, in the proposer's own words:" in out
        assert '"probe more candidates"' in out    # the rationale, quoted

        # the raw file, in full, verbatim
        with open(policy_path, encoding="utf-8") as f:
            raw = f.read()
        assert raw in out
        assert "--- the policy file, in full ---" in out

        # never runs, and names the real next command
        assert "This is not approval, and nothing has run." in out
        assert f"oneground propose {wd} --policy {policy_path} " \
              "--prediction" in out
        assert not os.path.isdir(os.path.join(wd, "proposals"))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
