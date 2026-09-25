"""`oneground propose translate`: a policy written by a model, from a
sentence. `docs/PROPOSALS.md` §2.1's second path, ruled 19 September 2026.

**After translation, path 2 *is* path 1.** This module produces exactly
one artifact, `policy.yaml`, in the shape `oneground.proposals.policy`
already validates -- the same file a user would have written by hand. It
then stops. The second phase -- measuring the change, judging the
prediction, writing the card -- is `oneground propose <workdir> --policy
... --prediction ...`, built by task 028, unchanged, and this module does
not call it: `translate` writes a policy for a human to read and does not
run one.

**No default model.** `--model` is required; there is no fallback, no
environment variable consulted for a default, and no silent choice. A
local endpoint is as first class as a hosted one:

    --model ollama:<name>                  resolves to localhost's Ollama,
                                           an OpenAI-compatible endpoint
                                           every recent Ollama ships
    --model <name> --endpoint <url>        any other OpenAI-compatible
                                           endpoint, named explicitly

Neither is a special case of the other; both take the same request shape
below and neither is preferred by this module's own logic.

**What the model is shown, and nothing else** (§2.1): the corpus's
characterization -- five measures, six numbers, drift is a pair -- the
current configuration (`manifest.yaml`'s `recommended`), the constraint
set (`requirements.yaml`'s `constraints` block), and the user's sentence.
Not vectors, not text, not ids, not filenames. `_payload_for_model` builds
exactly this and nothing this module has access to besides it ever
reaches `_call_model`.

**The closed sampling-parameter list**: `temperature`, `top_p`, `seed`,
`max_tokens`, and a digest of the system prompt. Each is recorded, `null`
where the caller did not set it -- adding to this list is a deliberate
change to this module, not whatever a request happens to carry.
"""

import hashlib
import json
import os
import urllib.error
import urllib.request

from ..provenance import invocation
from ..receipts import producing_version, write_json_stable

PROVIDER_NOT_SET = (
    "translate refuses without an explicit --model: no model is bundled, "
    "none is default, and a user who has not chosen gets a refusal, never "
    "a surprise (docs/PROPOSALS.md §2.1).")

SAMPLING_PARAMETERS = ("temperature", "top_p", "seed", "max_tokens",
                       "system_prompt_digest")

OLLAMA_LOCAL_ENDPOINT = "http://localhost:11434/v1"

SYSTEM_PROMPT = (
    "You translate a one-sentence description of a retrieval-architecture "
    "change into a oneground policy: a family and a parameter change over "
    "one of its declared configurations. Reply with the policy as YAML, "
    "in this exact shape, and nothing else:\n\n"
    "policy:\n"
    "  family: <one of the families listed below>\n"
    "  configuration: {<every parameter of the family, named>}\n"
    "  changes:\n"
    "    - param: <name>\n"
    "      from: <value>\n"
    "      to: <value>\n"
    "  rationale: \"<your reason, in your own words>\"\n\n"
    "You may name only a family and parameters that are listed below. If "
    "the described change needs something not on this list -- a subset of "
    "queries, a new kind of index, anything this list does not name -- "
    "say so in prose instead of producing YAML: this requires a family or "
    "a parameter that does not exist.")


class TranslateError(ValueError):
    """`translate` refused. `docs/PROPOSALS.md` §2.1's own refusals."""


def _read_json(path, name):
    if not os.path.exists(path):
        raise TranslateError(
            f"{path} does not exist -- run `oneground characterize` (and "
            f"`simulate`, `report`) on this workdir before translating a "
            f"sentence against it. {name} is what this reads.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _six_numbers(characterization):
    """The five measures, six numbers -- drift is a pair. Nothing else
    from `characterization.json` reaches the model: no per-vector data, no
    distributions, just the five headline readings."""
    drift = characterization.get("drift")
    drift_before = drift_after = None
    if isinstance(drift, dict):
        drift_before = drift.get("drift_before")
        drift_after = drift.get("drift_after")
    return {
        "intrinsic_dimensionality": characterization.get(
            "intrinsic_dimensionality"),
        "boundary_crispness": characterization.get("boundary_crispness"),
        "skew_top10_share": characterization.get("skew_top10_share"),
        "ambiguous_query_rate": characterization.get("ambiguous_query_rate"),
        "drift_before": drift_before,
        "drift_after": drift_after,
    }


def _current_configuration(workdir):
    import yaml
    manifest_path = os.path.join(workdir, "manifest.yaml")
    if not os.path.exists(manifest_path):
        raise TranslateError(
            f"{manifest_path} does not exist -- run `oneground report` on "
            "this workdir first. translate shows the model the "
            "*recommended* configuration, and only report decides one.")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    recommended = manifest.get("recommended")
    if not recommended:
        raise TranslateError(
            f"{manifest_path} carries no recommended configuration "
            f"({manifest.get('reason', 'no reason recorded')}) -- there is "
            "nothing for a described change to be a change FROM.")
    return recommended


def _resolve_requirements_path(workdir, requirements_path):
    """The same resolution `oneground.proposals.propose.plan_proposal`
    already uses: an explicit path wins, otherwise `simulate_info.json`'s
    own `requirements_file.path` -- the requirements file `simulate`
    itself was run against, not a second copy this module keeps."""
    if requirements_path:
        return requirements_path
    info_path = os.path.join(workdir, "simulate_info.json")
    if not os.path.exists(info_path):
        return None
    info = _read_json(info_path, "simulate_info")
    return (info.get("requirements_file") or {}).get("path")


def _payload_for_model(workdir, requirements_path=None):
    """§2.1: characterization, current configuration, constraints. Nothing
    else -- this function's return value is the whole of what `_call_model`
    receives about the corpus."""
    characterization = _read_json(
        os.path.join(workdir, "characterization.json"), "characterization")
    req_path = _resolve_requirements_path(workdir, requirements_path)
    constraints = {}
    if req_path and os.path.exists(req_path):
        import yaml
        with open(req_path, encoding="utf-8") as f:
            constraints = (yaml.safe_load(f) or {}).get("constraints", {})
    from ..param import PARAMETER
    families = {name: [p.name for p in table.values()
                       if p.role == PARAMETER]
               for name, table in _family_tables().items()}
    return {
        "characterization": _six_numbers(characterization),
        "current_configuration": _current_configuration(workdir),
        "constraints": constraints,
        "families": families,
    }


def _family_tables():
    from .. import models
    from ..models.base import parameter_table
    return {name: parameter_table(name) for name in models.families()}


def _resolve_endpoint(model, endpoint):
    """`ollama:<name>` resolves without an explicit endpoint; anything
    else needs one, named -- no provider is guessed from a bare name."""
    if model.startswith("ollama:"):
        if endpoint:
            raise TranslateError(
                "--model ollama:<name> already names its endpoint; "
                "--endpoint is for a model name with no provider prefix")
        return OLLAMA_LOCAL_ENDPOINT, model[len("ollama:"):]
    if not endpoint:
        raise TranslateError(
            f"--model {model!r} names no provider prefix (ollama:<name>) "
            "and no --endpoint was given. " + PROVIDER_NOT_SET)
    return endpoint.rstrip("/"), model


def _call_model(endpoint, model_name, sentence, payload, sampling,
                log_fn=None):
    """One chat-completions request, OpenAI's own shape -- the shape both
    Ollama's compatibility layer and every hosted provider this module
    treats as first class already speak. Returns
    `(response_text, request_body, raw_response)`.
    """
    def say(msg):
        if log_fn:
            log_fn(msg)

    user_message = (
        "Corpus and constraints:\n" + json.dumps(payload, indent=2) +
        "\n\nDescribed change:\n" + sentence)
    body = {
        "model": model_name,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                     {"role": "user", "content": user_message}],
    }
    for key in ("temperature", "top_p", "seed", "max_tokens"):
        if sampling.get(key) is not None:
            body[key] = sampling[key]

    url = endpoint + "/chat/completions"
    say(f"translate: calling {url} (model {model_name!r})")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise TranslateError(f"{url}: request failed -- {e}") from None

    try:
        text = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise TranslateError(
            f"{url}: response is not shaped like a chat completion "
            f"({e}); raw response: {json.dumps(raw)[:500]}") from None
    return text, body, raw


def _extract_policy_yaml(text):
    """The model's reply, as YAML text, for `policy.load_policy`-shaped
    validation. A fenced code block is unwrapped; anything else is passed
    through as-is, because refusing on unexpected formatting would be this
    module inventing a rule the position paper does not state -- validation
    of the *policy itself* is `policy.validate_policy`'s job, not this
    function's."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t


def translate(workdir, describe, model, endpoint=None, temperature=None,
             top_p=None, seed=None, max_tokens=None, out_dir=None,
             requirements_path=None, log_fn=None):
    """`oneground propose translate`. Writes `policy.yaml` and the
    disclosure receipts; runs nothing and approves nothing. Returns a dict
    of everything written, with each file's sha256.

    Raises `TranslateError` for every refusal §2.1/§2.1's "what path 2
    must refuse" names that this function can check before a model is
    ever called: no model, an unparseable or unfamilied-and-parameterless
    response. A response naming a real family with an invalid parameter is
    NOT refused here -- it is written to `policy.yaml` exactly as
    produced, because the second phase's own `validate_policy` is the one
    place a policy is validated, and this module does not run a second
    implementation of that rule beside it.
    """
    def say(msg):
        if log_fn:
            log_fn(msg)

    if not model:
        raise TranslateError(PROVIDER_NOT_SET)
    if not describe or not describe.strip():
        raise TranslateError("translate refuses an empty --describe: "
                             "there is no sentence to translate.")

    endpoint_url, model_name = _resolve_endpoint(model, endpoint)
    payload = _payload_for_model(workdir, requirements_path)

    system_digest = hashlib.sha256(
        SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    sampling = {"temperature": temperature, "top_p": top_p, "seed": seed,
               "max_tokens": max_tokens,
               "system_prompt_digest": system_digest}
    assert set(sampling) == set(SAMPLING_PARAMETERS), sampling

    text, request_body, raw_response = _call_model(
        endpoint_url, model_name, describe, payload, sampling, log_fn=say)
    policy_yaml = _extract_policy_yaml(text)

    import yaml
    try:
        policy_doc = yaml.safe_load(policy_yaml)
    except yaml.YAMLError as e:
        raise TranslateError(
            f"the model's reply does not parse as YAML ({e}). This is "
            "refused here -- not written as an unparseable policy.yaml -- "
            f"because there is nothing downstream that could read it.\n\n"
            f"Reply:\n{text}") from None
    if not isinstance(policy_doc, dict) or "policy" not in policy_doc:
        raise TranslateError(
            "the model's reply parsed as YAML but does not have a "
            "top-level `policy` key -- most often the model explained why "
            "the change cannot be expressed rather than producing a "
            f"policy, which is the correct refusal for it to make.\n\n"
            f"Reply:\n{text}")

    out = out_dir or workdir
    os.makedirs(out, exist_ok=True)
    policy_path = os.path.join(out, "policy.yaml")
    with open(policy_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(policy_doc, f, sort_keys=False)

    # docs/PROPOSALS.md §2.1 "What the model reports, unreported": provider
    # version is often not in a chat-completions response at all; declared
    # null with a reason, not guessed and not refused over.
    provider_version = raw_response.get("model") if isinstance(
        raw_response, dict) else None
    version_reason = (None if provider_version else
                      "the endpoint's response carried no model/version "
                      "field; ollama and OpenAI-compatible servers report "
                      "this inconsistently, and a local endpoint may "
                      "report none at all")

    disclosure = {
        "kind": "declared",
        "oneground": producing_version(),
        "invocation": invocation(),
        "authored_by": "model",
        "provider_endpoint": endpoint_url,
        "model_name": model_name,
        "model_version": provider_version,
        "model_version_reason": version_reason,
        "sampling_parameters": sampling,
        "sentence": describe,
        "policy_produced": policy_doc,
        "prompt_sent": request_body,
        "response_received": raw_response,
        "approved": False,
        "approved_note": ("translate writes this file and stops. Approval "
                          "is reading policy.yaml and choosing to run "
                          "`oneground propose <workdir> --policy "
                          "policy.yaml --prediction <file>` -- an act "
                          "this module cannot perform or record on a "
                          "user's behalf."),
    }
    disclosure_path = os.path.join(out, "translation_card.json")
    write_json_stable(disclosure_path, disclosure)

    say(f"translate: wrote {policy_path}")
    say(f"translate: wrote {disclosure_path}")
    say("translate: stopping here. Read policy.yaml; approval is running "
       "`oneground propose` on it yourself.")

    return {"policy_path": policy_path, "disclosure_path": disclosure_path,
           "policy": policy_doc, "disclosure": disclosure}
