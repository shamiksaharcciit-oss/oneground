"""A durable receipt for a policy refusal. `docs/TRIAGE.md` §7's first
item, and the item that closes §0's own finding: before this, a refusal
from `validate_policy` was caught by `cli.py`, printed, and discarded --
nothing recorded that it happened, what was described, or when. This
module writes one receipt per refusal, where the refusal happens, and
does nothing else. No grouping, no counting, no output shape: `docs/
TRIAGE.md` §5 refuses those until there is a record to read from, and
this module is only ever the writing half of that record.

**What is triaged is a different question from what gets a receipt.**
`docs/TRIAGE.md` §3.1 scopes future triage to `validate_policy`'s
refusals for a family or parameter that does not exist. This module
writes a receipt for *every* `PolicyError` `plan_proposal` catches --
including a malformed configuration, a no-op change, a mismatched
`from` -- because refusing to record the ones §3.1 does not care about
would mean re-deriving, here, which refusal is which, a second time.
`named_as_missing` (below) answers that question structurally, once, so
a later reader filters the receipts rather than this module guessing at
triage's own scope on its behalf.
"""

import json
import os
import time
import uuid

import yaml

from ..comparability import facts_of, provenance_of
from ..provenance import invocation
from ..receipts import (PUBLIC_PATH_NOTE, producing_version, public_path,
                        write_json_stable)

REFUSALS_DIR = os.path.join("proposals", "refusals")
TRANSLATION_CARD_NAME = "translation_card.json"


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _authored_by(policy_path):
    """`docs/PROPOSALS.md` §2.1's own disclosure convention, read rather
    than re-declared: a policy `translate` produced sits beside its own
    `translation_card.json`, carrying `authored_by`. Its absence means a
    hand-written policy -- `authored_by: user`, the same value tier 1's
    own card uses for the same fact.
    """
    sibling = os.path.join(os.path.dirname(os.path.abspath(policy_path)),
                           TRANSLATION_CARD_NAME)
    card = _read_json(sibling)
    if card is not None:
        return card.get("authored_by", "model"), sibling, card.get("sentence")
    return "user", None, None


def named_as_missing(policy_path):
    """Which family or parameter this policy named that the simulator
    does not have -- read structurally, from the parsed document against
    `oneground.models`' own registry and parameter tables, never by
    matching `validate_policy`'s prose. The same "read the computed
    value, not the sentence about it" rule this project's own practice
    names elsewhere, applied to a refusal reason instead of a claim.

    Returns a list of `{"kind": "family"|"parameter"|"scope", ...}`,
    empty if the file does not parse, names a real family with no
    unrecognised parameters, or is missing entirely -- `problems` on the
    receipt still carries the full refusal in every one of those cases.
    """
    try:
        with open(policy_path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(doc, dict):
        return []
    p = doc.get("policy")
    if not isinstance(p, dict):
        return []

    from .. import models
    out = []
    if "scope" in p:
        out.append({"kind": "scope", "name": "scope"})

    family = p.get("family")
    if not isinstance(family, str):
        return out
    if family not in models.REGISTRY:
        out.append({"kind": "family", "name": family})
        return out                     # no table to check parameters against

    from ..models.base import parameter_table
    table = parameter_table(family)
    keys = set((p.get("configuration") or {}))
    for ch in (p.get("changes") or []):
        if isinstance(ch, dict) and isinstance(ch.get("param"), str):
            keys.add(ch["param"])
    for key in sorted(keys):
        if key not in table:
            out.append({"kind": "parameter", "name": key, "family": family})
    return out


def write_refusal_receipt(workdir, policy_path, problems, log_fn=None):
    """One receipt per `PolicyError`. Returns the path written.

    `problems` is `PolicyError.problems` -- every reason `validate_policy`
    refused, verbatim, the same strings a terminal sees today (`docs/
    PROPOSALS.md`'s own "every problem is reported together, not the
    first"). Nothing here collapses that list to one reason.
    """
    def say(msg):
        if log_fn:
            log_fn(msg)

    authored_by, translation_card_path, sentence = _authored_by(policy_path)

    policy_text = None
    try:
        with open(policy_path, encoding="utf-8") as f:
            policy_text = f.read()
    except OSError:
        pass

    characterization = _read_json(
        os.path.join(workdir, "characterization.json"))

    facts = facts_of(workdir)
    provenance = provenance_of(facts)

    receipt = {
        "kind": "declared",
        "oneground": producing_version(),
        "invocation": invocation(),
        "id": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-"
             + uuid.uuid4().hex[:8],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # docs/PRACTICE.md/task 043: a receipt field holding a machine-
        # local path cannot be published by running the command that
        # produces it. Sanitised here, where the field is written, so
        # this receipt never contains the absolute path in the first
        # place -- `public_path` reduces to repo-relative inside the
        # checkout, basename outside it.
        "policy_path": public_path(policy_path),
        "policy_declared": policy_text,
        "authored_by": authored_by,
        "translation_card": public_path(translation_card_path),
        "path_note": PUBLIC_PATH_NOTE,
        "sentence": sentence,
        "named_as_missing": named_as_missing(policy_path),
        "problems": list(problems),
        "corpus_characterization": characterization,
        "corpus_characterization_reason": (
            None if characterization is not None else
            "characterization.json not found in this workdir at the time "
            "of the refusal"),
        "provenance": provenance.as_dict(),
    }

    out_dir = os.path.join(workdir, REFUSALS_DIR)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, receipt["id"] + ".json")
    write_json_stable(path, receipt)
    say(f"propose: refusal recorded -- {path}")
    return path
