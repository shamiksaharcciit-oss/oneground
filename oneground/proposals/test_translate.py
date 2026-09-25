"""`oneground.proposals.translate`. `docs/PROPOSALS.md` §2.1.

A real local HTTP server stands in for the OpenAI-compatible endpoint --
genuine sockets and JSON over HTTP, not a mocked Python function -- because
`--model ollama:<name>, or any OpenAI-compatible URL` is a claim about a
real wire protocol, and the module's own docstring says it speaks the
shape "both Ollama's compatibility layer and every hosted provider... "
already speak. No real provider or real spend is used: the server this
file starts is the local endpoint the position paper says is first class.

    python oneground/proposals/test_translate.py
    pytest oneground/proposals/test_translate.py
"""

import http.server
import json
import os
import sys
import tempfile
import threading
import yaml

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.proposals import translate as tr  # noqa: E402


# --------------------------------------------------------------- the server
class _ScriptedHandler(http.server.BaseHTTPRequestHandler):
    """Replies with whatever `reply()` was primed with, and records the
    request body it received -- so a test can assert on both halves of the
    real HTTP exchange."""

    def log_message(self, *a):
        pass                                          # keep test output quiet

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.server.last_request = body
        status, payload = self.server.next_reply
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))


class ScriptedServer:
    """A real HTTP server on localhost, primed with one reply at a time."""

    def __init__(self):
        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), _ScriptedHandler)
        self.httpd.next_reply = (200, {})
        self.httpd.last_request = None
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_port}/v1"

    def reply(self, content, status=200, model="test-model-v1"):
        self.httpd.next_reply = (status, {
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": content}}],
        })

    def reply_raw(self, payload, status=200):
        self.httpd.next_reply = (status, payload)

    @property
    def last_request(self):
        return self.httpd.last_request

    def close(self):
        self.httpd.shutdown()
        self.thread.join(timeout=5)


@pytest.fixture
def server():
    s = ScriptedServer()
    yield s
    s.close()


# ------------------------------------------------------------------ workdir
POLICY_REPLY = """```yaml
policy:
  family: single_node_hnsw
  configuration: {index: hnsw, M: 32, efConstruction: 200, efSearch: 128}
  changes:
    - param: efSearch
      from: 128
      to: 256
  rationale: "probe more candidates for higher recall"
```"""


def _workdir(tmp, recommended=True, with_requirements=True):
    os.makedirs(tmp, exist_ok=True)
    with open(os.path.join(tmp, "characterization.json"), "w",
             encoding="utf-8") as f:
        json.dump({
            "intrinsic_dimensionality": 12.4, "boundary_crispness": 0.021,
            "skew_top10_share": 0.31, "ambiguous_query_rate": 0.07,
            "drift": {"drift_before": 0.02, "drift_after": 0.05,
                     "cutoff": "2026-08-01"},
            # Deliberately present, to prove the payload boundary: these
            # must NOT reach the model.
            "sample_vector_path": "/should/never/be/sent.npy",
            "raw_ids": [1, 2, 3, 4, 5],
        }, f)
    manifest = {
        "recommended": ({"family": "single_node_hnsw",
                        "params": {"index": "hnsw", "M": 32,
                                  "efConstruction": 200, "efSearch": 128}}
                       if recommended else None),
        "reason": "meets every constraint" if recommended else
                 "no option met every constraint; nothing is recommended",
    }
    with open(os.path.join(tmp, "manifest.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(manifest, f)
    if with_requirements:
        req_path = os.path.join(tmp, "req.yaml")
        with open(req_path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"constraints": {"recall_at_k": {"k": 10,
                                                            "min": 0.95}}}, f)
        with open(os.path.join(tmp, "simulate_info.json"), "w",
                 encoding="utf-8") as f:
            json.dump({"requirements_file": {"path": req_path}}, f)
    return tmp


# ------------------------------------------------------------------ refusals
def test_no_model_is_refused_never_a_default():
    with pytest.raises(tr.TranslateError, match="no model is bundled"):
        tr.translate("/does/not/matter", "probe more", model=None)


def test_empty_describe_is_refused():
    with pytest.raises(tr.TranslateError, match="empty --describe"):
        tr.translate("/does/not/matter", "   ", model="ollama:llama3")


def test_a_bare_name_with_no_provider_and_no_endpoint_is_refused():
    with pytest.raises(tr.TranslateError, match="no model is bundled"):
        tr.translate("/does/not/matter", "probe more", model="gpt-4o")


def test_ollama_prefix_with_an_explicit_endpoint_is_refused_not_silently_combined():
    with pytest.raises(tr.TranslateError, match="already names its endpoint"):
        tr.translate("/does/not/matter", "probe more",
                     model="ollama:llama3", endpoint="http://elsewhere:9")


def test_no_recommended_configuration_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp, recommended=False)
        with pytest.raises(tr.TranslateError, match="no recommended"):
            tr.translate(tmp, "probe more", model="x", endpoint="http://x")


# --------------------------------------------------------- the real request
def test_translate_calls_the_local_endpoint_and_writes_a_valid_policy(server):
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp)
        server.reply(POLICY_REPLY)

        result = tr.translate(tmp, "probe more candidates for recall",
                              model="my-model", endpoint=server.url,
                              temperature=0.1, seed=7)

        assert os.path.exists(result["policy_path"])
        assert result["policy"]["policy"]["family"] == "single_node_hnsw"
        assert result["policy"]["policy"]["changes"][0]["param"] == "efSearch"

        from oneground.proposals.policy import validate_policy
        validate_policy(result["policy"])          # raises if invalid


def test_ollama_prefix_resolves_without_an_endpoint_argument():
    """Can't hit a real Ollama here, but proves the resolution itself --
    the URL and model name the request WOULD go to -- rather than assuming
    it from the string."""
    url, name = tr._resolve_endpoint("ollama:llama3", None)
    assert url == tr.OLLAMA_LOCAL_ENDPOINT
    assert name == "llama3"


# ---------------------------------------------------- the payload boundary
def test_only_the_six_numbers_and_configuration_reach_the_model(server):
    """docs/PROPOSALS.md §2.1: not vectors, not text, not ids, not
    filenames. The workdir's characterization.json carries a fake vector
    path and raw ids specifically so this test can prove they never leave
    this process."""
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp)
        server.reply(POLICY_REPLY)

        tr.translate(tmp, "probe more", model="my-model", endpoint=server.url)

        sent = json.dumps(server.last_request)
        assert "sample_vector_path" not in sent
        assert "should/never/be/sent" not in sent
        assert "raw_ids" not in sent
        assert "single_node_hnsw" in sent            # the configuration IS sent
        assert "recall_at_k" in sent                 # the constraints ARE sent


# --------------------------------------------------- the sampling parameters
def test_sampling_parameters_are_the_closed_list_null_when_unset(server):
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp)
        server.reply(POLICY_REPLY)

        result = tr.translate(tmp, "probe more", model="my-model",
                              endpoint=server.url)
        sampling = result["disclosure"]["sampling_parameters"]
        assert set(sampling) == set(tr.SAMPLING_PARAMETERS)
        assert sampling["temperature"] is None
        assert sampling["seed"] is None
        assert sampling["system_prompt_digest"]      # always present

        result2 = tr.translate(tmp, "probe more", model="my-model",
                               endpoint=server.url, temperature=0.2, seed=3)
        assert result2["disclosure"]["sampling_parameters"]["temperature"] == 0.2
        assert result2["disclosure"]["sampling_parameters"]["seed"] == 3

        req = server.last_request
        assert req["temperature"] == 0.2
        assert req["seed"] == 3


# -------------------------------------------------------------- disclosure
def test_the_disclosure_carries_the_sentence_prompt_response_and_approval_state(server):
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp)
        server.reply(POLICY_REPLY)

        result = tr.translate(tmp, "probe more candidates for recall",
                              model="my-model", endpoint=server.url)
        d = result["disclosure"]
        assert os.path.exists(result["disclosure_path"])
        assert d["authored_by"] == "model"
        assert d["sentence"] == "probe more candidates for recall"
        assert d["prompt_sent"]["messages"][1]["content"].endswith(
            "probe more candidates for recall")
        assert d["response_received"]["choices"][0]["message"]["content"] \
            == POLICY_REPLY
        assert d["approved"] is False
        assert "oneground" in d and "invocation" in d


def test_an_unreported_model_version_is_null_with_a_reason(server):
    """§2.1: 'An unreported version is null with a stated reason, not a
    refusal.'"""
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp)
        server.reply_raw({"choices": [{"message": {"role": "assistant",
                                                    "content": POLICY_REPLY}}]})
        # no "model" key in the raw response at all

        result = tr.translate(tmp, "probe more", model="my-model",
                              endpoint=server.url)
        assert result["disclosure"]["model_version"] is None
        assert "not recorded" not in result["disclosure"][
            "model_version_reason"]  # sanity: it says SOMETHING, not this
        assert result["disclosure"]["model_version_reason"]


# ---------------------------------------------------------- model refusals
def test_a_reply_explaining_why_rather_than_a_policy_is_refused(server):
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp)
        server.reply("This requires a family that does not exist: "
                     "filtering by a metadata field is not something any "
                     "shipped family supports.")

        with pytest.raises(tr.TranslateError,
                          match="does not have a top-level"):
            tr.translate(tmp, "filter by category", model="my-model",
                        endpoint=server.url)


def test_unparseable_yaml_is_refused(server):
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp)
        server.reply("policy:\n  family: [unterminated")

        with pytest.raises(tr.TranslateError, match="does not parse as YAML"):
            tr.translate(tmp, "probe more", model="my-model",
                        endpoint=server.url)


def test_an_invalid_family_or_parameter_is_written_not_refused_here(server):
    """The second implementation-avoidance rule stated in the module's own
    docstring: `translate` does not re-validate a policy's family/
    parameters, because `oneground propose`'s own `validate_policy` is the
    one place that happens."""
    bad_reply = """policy:
  family: not_a_real_family
  configuration: {x: 1}
  changes:
    - param: x
      from: 1
      to: 2
  rationale: "test"
"""
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp)
        server.reply(bad_reply)

        result = tr.translate(tmp, "probe more", model="my-model",
                              endpoint=server.url)
        assert result["policy"]["policy"]["family"] == "not_a_real_family"

        from oneground.proposals.policy import validate_policy, PolicyError
        with pytest.raises(PolicyError):
            validate_policy(result["policy"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
