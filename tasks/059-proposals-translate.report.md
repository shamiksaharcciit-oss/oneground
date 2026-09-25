# Report: 059-proposals-translate

## Repo state expected vs found

Expected `main` at `f9121a8` (task 058's merge) with `docs/PROPOSALS.md`
§2.1's ruling in place, tier 1 (`oneground/proposals/propose.py`,
task 028) built and unchanged, and no `translate` module anywhere. Found
exactly that; branch `task-059` created from `main` at that commit.

## What was done

**Two existing guards caught this module arriving, correctly, and both
needed a real update rather than a workaround.**

1. `oneground/test_invocation.py::test_every_receipt_writer_records_it_
   beside_the_version` hardcodes a site count (`oneground/test_
   invocation.py`, task 051's own precedent for this exact assertion,
   "12 to 14"). `translate.py`'s disclosure correctly pairs `oneground`/
   `invocation`, the 15th such site; the count is updated from 14 to 15,
   the same one-line fix task 051 made for the same reason.
2. `oneground/proposals/test_propose.py::test_the_proposals_package_has_
   no_model_no_api_call_and_no_prompt` scanned every `.py` file in
   `oneground/proposals/` for a network import or a model-shaped word,
   asserting the whole package carried neither — tier 1's own guard
   against tier 2 starting silently, per its own docstring: *"An HTTP
   import or a prompt string here would mean tier 2 had started without
   anyone deciding to."* Tier 2 has now been decided, explicitly, and
   this task is that decision. The test correctly failed against
   `translate.py`'s `urllib` import and its `SYSTEM_PROMPT` string — the
   exact thing it was built to catch — and against `test_translate.py`
   for the same reason, since a test exercising a model module
   necessarily uses the same words. Renamed to `test_tier_1_has_no_
   model_no_api_call_and_no_prompt`, scope narrowed to exclude exactly
   `translate.py` and `test_translate.py` (named explicitly, not by a
   broad `test_*` pattern that would have also stopped checking `test_
   proposals.py`), with a comment stating why and that `test_translate.
   py` is now the guard for what `translate.py` itself may and may not
   do. Every other tier-1 file is still scanned, unchanged.

**`oneground/proposals/translate.py`** — `oneground propose translate`'s
library function. Writes exactly one artifact a human reads,
`policy.yaml`, plus a disclosure receipt, and stops — it does not call
tier 1's `oneground propose <workdir> --policy ... --prediction ...`,
per §2.1's own instruction: "After translation, path 2 *is* path 1,"
unchanged, built by task 028.

**No default model, checked first, before any network call.** `--model`
required; a bare name with no `ollama:` prefix and no `--endpoint` is
refused naming both missing pieces. `--model ollama:<name>` resolves to
`localhost:11434/v1` without an endpoint argument; supplying `--endpoint`
alongside it is refused rather than silently combined (which one would
win is exactly the kind of silent choice §2.1 rules out). Neither path is
preferred in the code: both produce the same `(endpoint, model_name)`
pair `_call_model` treats identically.

**What the model is shown, and nothing else.** `_payload_for_model`
builds: the five measures, six numbers (`intrinsic_dimensionality`,
`boundary_crispness`, `skew_top10_share`, `ambiguous_query_rate`,
`drift_before`, `drift_after` — drift is a pair), `manifest.yaml`'s
`recommended` configuration, `requirements.yaml`'s `constraints` block
(resolved the same way `oneground.proposals.propose.plan_proposal`
already resolves it — an explicit path, or `simulate_info.json`'s own
`requirements_file.path`, not a second copy this module invents), and the
declared families' parameter names. Nothing else from `characterization.
json` is read into this structure. Tested directly: a workdir's
`characterization.json` carries a fake vector path and raw ids
specifically so a test can assert neither ever reaches the wire.

**The closed sampling-parameter list**: `temperature`, `top_p`, `seed`,
`max_tokens`, `system_prompt_digest` — asserted as a set equality against
what the disclosure records, so a parameter added to the request body
without being added to this list would fail loudly. Each is `null` when
the caller did not set it, never omitted.

**Two-phase, and this module enforces its own half of the boundary.**
`translate` writes `policy.yaml` and a `translation_card.json` disclosure
carrying `"approved": false` and a note naming what approval actually is
— reading the policy and choosing to run `propose` on it — and states
plainly that this module "cannot perform or record" that act. There is
no `--yes`, no flag that runs the second phase automatically, and no code
path from `translate` into `propose.run`.

**The disclosure** (`translation_card.json`, `kind: declared`): provider
endpoint, model name, `authored_by: model`, the sentence as typed, the
policy as produced verbatim, the full prompt sent and response received,
the sampling parameters, and `oneground`/`invocation` (the pairing every
other declared-receipt writer in this codebase carries — confirmed by
`oneground/test_invocation.py`'s own site-count test, which counted this
module as the 15th correctly-paired site).

**An unreported model version is `null` with a stated reason, not a
refusal.** Read from the response's own `model` field (many
OpenAI-compatible servers echo a resolved, versioned string here; a bare
local server need not). Tested directly against a scripted response
carrying no `model` key at all.

**Two refusals this module makes, and one it deliberately does not.**
Refused: a reply that does not parse as YAML; a reply with no top-level
`policy` key (the shape a model correctly declining an unrepresentable
change takes — tested with exactly such a reply). **Not refused here**: a
policy naming a real-looking but invalid family or parameter. That
validation is `oneground.proposals.policy.validate_policy`'s job, already
built by task 026/028, and this module writes the policy exactly as
produced rather than running a second implementation of that rule beside
it — tested by producing a policy naming `not_a_real_family` and showing
it writes cleanly, then fails `validate_policy` (the second phase's own
job) when that command is what would actually be run against it.

## Measurements

14 of 14 tests pass, against a **real local HTTP server** (`http.server`,
a genuine socket, not a mocked function) standing in for the
OpenAI-compatible endpoint the position paper names as first class — no
real provider, no spend. Two real bugs were found and fixed while writing
these tests: a synthetic policy fixture named `shards` as a
`single_node_hnsw` parameter, which the real parameter table does not
have (`M`, `efSearch`, `efConstruction`, `index`, `m`, `nbits`, `nlist`,
`nprobe`, `rerank`, `candidates` — checked against
`oneground.models.base.parameter_table` directly, not guessed); and a
test's expected-refusal-message regex that did not match the actual
wording. Both are fixed in the committed test file.

Ollama itself is not installed on this machine (checked); the
`ollama:<name>` **resolution** is tested directly
(`_resolve_endpoint("ollama:llama3", None)` → the right URL and model
name), and the request/response/disclosure pipeline is tested end to end
against the real local server, which speaks the same wire shape Ollama's
own OpenAI-compatibility layer does. The distinction is stated rather
than blurred: this task did not verify against a running Ollama.

## Verification

`oneground/proposals/test_translate.py`: 14 passed. Full suite, guard,
identifier scan and `site/teaser/`: reported at the merge, per the
established pattern.

## Observed, not done

**No CLI wiring.** `oneground propose translate <workdir> --describe ...
--model ...` does not exist as a command; `translate()` is a library
function, callable the way `oneground.proposals.propose.run` was before
the CLI wrapped it. Matches the scope this batch's other two tasks (057,
058) were built at — the measurement/validator first, the command surface
named as unbuilt rather than assumed.

**Hosted providers with their own auth schemes** (an API key header
rather than a bare POST) are not built — `_call_model` sends no
authentication header at all. Every hosted provider that speaks the
OpenAI-compatible shape over a bare endpoint (many self-hosted
gateways, and some proxies in front of real providers) works today;
one requiring `Authorization: Bearer <key>` does not yet, and adding it
is a small, separate change this task did not make since it was not
named in the ruling.

**No Ollama-specific behavior beyond the URL resolution.** Ollama's own
non-OpenAI-compatible API (`/api/chat`, its native shape) is not used;
`ollama:<name>` resolves to Ollama's OpenAI-compatibility layer
(`/v1/chat/completions`), which recent Ollama versions ship, per this
module's own docstring — not independently confirmed against a running
instance.

## Repo now contains

Changed:

- `oneground/test_invocation.py` — site count 14 → 15
- `oneground/proposals/test_propose.py` — the "no model in the package"
  guard renamed and narrowed to tier 1's own files

New:

- `oneground/proposals/translate.py`
- `oneground/proposals/test_translate.py` — 14 tests, against a real
  local HTTP server
- `tasks/059-proposals-translate.report.md` — this file

## Blocked on developer

Nothing. Committing, pushing to `task-059`, and merging into `main` once
its checks are green, per standing instruction.
