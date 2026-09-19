"""A policy: a parameter change over a whole configuration, and nothing else.

docs/PROPOSALS.md §2.2, as ruled in task 026:

    policy:
      family: semantic_sharded
      configuration: {centroids: 256, epsilon: 0.2, probe: 2, M: 32, efSearch: 96}
      changes:
        - param: probe
          from: 2
          to: 3
      rationale: "..."

Every field is checked against what ships: the family against the model
registry, every key and value against that family's parameter table
(`models.base`). A policy may change only keys whose role is `parameter` -- the
architecture -- never a constant the family fixes, the run-level
`shard_depth`, or the build's `deterministic`. There are no scopes: a change to
a subset of queries or vectors requires a family that does not exist, and the
refusal says so.

`configuration` is the whole configuration being changed, every parameter
named. It is what makes `from` checkable and what gives both configurations
the same label a run gives them.

Every problem is reported together, not the first: a reader fixing a policy
should learn its whole shape from one refusal.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from .. import models
from ..models.base import (CONSTANT, PARAMETER, Config, ParameterError,
                           canonical_params, check_value, parameter_table)

POLICY_FIELDS = ("family", "configuration", "changes", "rationale")
CHANGE_FIELDS = ("param", "from", "to")

NO_SCOPE = ("a policy has no scope: it is a parameter change over a whole "
            "configuration. A change to a subset of queries or vectors "
            "requires a family that does not exist")


class PolicyError(ValueError):
    """Every reason a policy was refused."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("policy refused:\n  - " + "\n  - ".join(self.problems))


def canonical_json(obj):
    """One byte string per value, whatever the key order it arrived in."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


@dataclass(frozen=True)
class Policy:
    family: str
    configuration: Dict[str, Any]
    changes: Tuple[Tuple[str, Any, Any], ...]
    rationale: str
    from_config: Config
    to_config: Config

    def as_dict(self):
        return {"policy": {
            "family": self.family,
            "configuration": dict(self.configuration),
            "changes": [{"param": p, "from": f, "to": t}
                        for p, f, t in self.changes],
            "rationale": self.rationale,
        }}

    def sha256(self):
        """The policy's digest, over its canonical JSON."""
        return hashlib.sha256(
            canonical_json(self.as_dict()).encode("ascii")).hexdigest()


def _key_problem(family, table, key, where):
    """Why `key` cannot appear in a policy for this family, or None."""
    param = table.get(key)
    if param is None:
        return (f"{where}: {family} has no parameter {key!r}; its parameters "
                "are " + ", ".join(sorted(n for n, p in table.items()
                                          if p.role == PARAMETER)))
    if param.role == CONSTANT:
        return f"{where}: " + check_value(family, param, None).replace(
            " (given None)", "")
    if param.role != PARAMETER:
        return (f"{where}: {family}.{key} is a {param.role} setting, not part "
                "of the architecture a policy changes")
    return None


def validate_policy(doc):
    """A `Policy`, or `PolicyError` naming every problem."""
    problems = []
    if not isinstance(doc, dict) or set(doc) != {"policy"}:
        extra = sorted(set(doc) - {"policy"}) if isinstance(doc, dict) else []
        problems.append("a policy document has exactly one top-level field, "
                        "`policy`" + (f"; found {extra}" if extra else ""))
        raise PolicyError(problems)
    p = doc["policy"]
    if not isinstance(p, dict):
        raise PolicyError(["`policy` must be a mapping"])

    for key in sorted(set(p) - set(POLICY_FIELDS)):
        problems.append(NO_SCOPE if key == "scope" else
                        f"policy has no field {key!r}; its fields are "
                        + ", ".join(POLICY_FIELDS))

    family = p.get("family")
    table = None
    if not isinstance(family, str):
        problems.append("policy names no family")
    elif family not in models.REGISTRY:
        problems.append(f"no model family named {family!r}. Registered: "
                        + ", ".join(models.families()))
    else:
        table = parameter_table(family)

    configuration = p.get("configuration")
    if not isinstance(configuration, dict):
        problems.append("policy names no configuration: a policy changes a "
                        "whole configuration, so it has to say which")
        configuration = None
    elif table is not None:
        for key in sorted(configuration):
            problem = _key_problem(family, table, key, "configuration")
            if problem:
                problems.append(problem)
                continue
            problem = check_value(family, table[key], configuration[key])
            if problem:
                problems.append(f"configuration: {problem}")
        # "Every parameter" is what the *chosen* index algorithm reads, not
        # every row of the table (task 034). `nlist` is a parameter of an IVF
        # configuration and not of an HNSW one, and `index` itself elides at
        # its default, so a policy over a published configuration names
        # neither. `canonical_params` is the one function that knows which
        # keys a configuration consists of; asking it here means a policy and
        # a label cannot disagree about what "complete" means.
        complete = canonical_params(family, dict(configuration))
        missing = sorted(n for n in complete
                         if n in table and table[n].role == PARAMETER
                         and n not in configuration)
        if missing:
            problems.append(
                f"configuration is missing {', '.join(missing)}: a policy "
                "names every parameter of the configuration it changes, so "
                "the run and the prediction mean the same one")

    changes = p.get("changes")
    parsed = []
    if not isinstance(changes, list) or not changes:
        problems.append("a policy changes at least one parameter; `changes` "
                        "is empty or missing")
        changes = []
    seen = set()
    for i, ch in enumerate(changes):
        where = f"changes[{i}]"
        if not isinstance(ch, dict):
            problems.append(f"{where} must be a mapping of param, from, to")
            continue
        for key in sorted(set(ch) - set(CHANGE_FIELDS)):
            problems.append(f"{where}: " + (
                NO_SCOPE if key == "scope" else
                f"a change has no field {key!r}; its fields are "
                + ", ".join(CHANGE_FIELDS)))
        absent = [f for f in CHANGE_FIELDS if f not in ch]
        if absent:
            problems.append(f"{where} names no {', '.join(absent)}")
            continue
        name, old, new = ch["param"], ch["from"], ch["to"]
        if name in seen:
            problems.append(f"{where} changes {name!r} twice")
            continue
        seen.add(name)
        if table is None:
            continue
        problem = _key_problem(family, table, name, where)
        if problem:
            problems.append(problem)
            continue
        problem = check_value(family, table[name], new)
        if problem:
            problems.append(f"{where}: {problem}")
        if configuration is not None and configuration.get(name) != old:
            problems.append(
                f"{where}: says {name} from {old!r}, but the configuration "
                f"has {configuration.get(name)!r}")
        if old == new:
            problems.append(f"{where}: {name} from {old!r} to {new!r} changes "
                            "nothing")
        parsed.append((name, old, new))

    rationale = p.get("rationale", "")
    if not isinstance(rationale, str):
        problems.append("`rationale` is quoted text, and must be a string")

    if problems:
        raise PolicyError(problems)

    try:
        from_config = Config.make(family, dict(configuration))
        to_params = dict(configuration)
        to_params.update({n: new for n, _old, new in parsed})
        to_config = Config.make(family, to_params)
    except ParameterError as e:                       # pragma: no cover
        raise PolicyError([str(e)]) from None
    return Policy(family=family, configuration=dict(configuration),
                  changes=tuple(parsed), rationale=rationale,
                  from_config=from_config, to_config=to_config)


def load_policy(path):
    import yaml
    with open(path, encoding="utf-8") as f:
        return validate_policy(yaml.safe_load(f))
