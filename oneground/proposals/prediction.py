"""The pre-registered prediction, and the file the run cites.

docs/PROPOSALS.md §2.3, as ruled in task 026. A prediction names, for a
validated policy:

    expects:
      - metric: recall_at_10
        direction: rises          # rises | falls
        by_at_least: 0.02
    side_effects:
      - metric: storage_amplification
        stays_at_or_below: 4.0    # or stays_at_or_above

Refused before anything runs, with every reason at once:
  - no expected change, or one missing its metric, direction or threshold
    ("it will be better" is not a prediction);
  - a threshold below the calibration tolerance -- a smaller difference cannot
    be told from noise, so the prediction could never be checked. The
    tolerance is named in the refusal;
  - a metric this command does not measure.

`write_prediction` puts `prediction.json` in the workdir, declared -- it is a
statement, not re-derivable -- and refuses to overwrite one. The digest is
not what proves the prediction came first: `simulate` reads the file's sha256
at the start of its run and records it in `simulate_info.json`, so the run's
own inputs cite it. A prediction written or edited after the run does not
match that citation, and the two-run verdict says so.
"""

import os

from ..receipts import sha256_file, write_json_stable
from ..report.verdict import CALIBRATION_TOLERANCE

PREDICTION_NAME = "prediction.json"

# The simulate row fields a prediction may name. All four are fractions or
# ratios, on the scale the calibration tolerance is defined on; memory bytes
# and timings are not, and are not predictable here.
METRICS = {
    "recall_at_10": "share of the true top-10 returned",
    "ceiling_at_10": "share of the true top-10 the routing can reach",
    "storage_amplification": "stored copies per base vector",
    "fanout": "shards touched per query",
}
DIRECTIONS = ("rises", "falls")
BOUNDS = ("stays_at_or_below", "stays_at_or_above")

# The workdir files that identify the sample the run measures.
CORPUS_FILES = ("characterization.json", "sample_ids.json", "queries_ids.json")


class PredictionError(ValueError):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("prediction refused:\n  - "
                         + "\n  - ".join(self.problems))


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_prediction(spec, tolerance=CALIBRATION_TOLERANCE):
    """`{"expects": [...], "side_effects": [...]}`, or `PredictionError`."""
    problems = []
    if not isinstance(spec, dict):
        raise PredictionError(["a prediction is a mapping with `expects` and "
                               "optionally `side_effects`"])
    for key in sorted(set(spec) - {"expects", "side_effects"}):
        problems.append(f"a prediction has no field {key!r}; its fields are "
                        "expects, side_effects")

    expects = spec.get("expects")
    if not isinstance(expects, list) or not expects:
        problems.append(
            "a prediction expects at least one change, each with a metric, a "
            "direction and a threshold. \"It will be better\" is not a "
            "prediction: nothing it says could turn out false")
        expects = []
    out_expects, named = [], set()
    for i, e in enumerate(expects):
        where = f"expects[{i}]"
        if not isinstance(e, dict):
            problems.append(f"{where} must be a mapping of metric, direction, "
                            "by_at_least")
            continue
        for key in sorted(set(e) - {"metric", "direction", "by_at_least"}):
            problems.append(f"{where} has no field {key!r}")
        absent = [f for f in ("metric", "direction", "by_at_least")
                  if e.get(f) is None]
        if absent:
            problems.append(f"{where} names no {', '.join(absent)}")
            continue
        metric, direction, by = e["metric"], e["direction"], e["by_at_least"]
        bad = False
        if metric not in METRICS:
            problems.append(f"{where}: {metric!r} is not a metric this "
                            "measures; it measures " + ", ".join(METRICS))
            bad = True
        elif metric in named:
            problems.append(f"{where}: {metric} is predicted twice")
            bad = True
        if direction not in DIRECTIONS:
            problems.append(f"{where}: direction {direction!r} is not one of "
                            + ", ".join(DIRECTIONS))
            bad = True
        if not _number(by) or by <= 0:
            problems.append(f"{where}: by_at_least must be a positive number, "
                            f"not {by!r}")
            bad = True
        elif by < tolerance:
            problems.append(
                f"{where}: {metric} {direction} by at least {by} is below the "
                f"calibration tolerance {tolerance}. A smaller difference "
                "cannot be told from noise, so this prediction could never be "
                "checked")
            bad = True
        if not bad:
            named.add(metric)
            out_expects.append({"metric": metric, "direction": direction,
                                "by_at_least": by})

    side = spec.get("side_effects", [])
    if not isinstance(side, list):
        problems.append("`side_effects` must be a list")
        side = []
    out_side = []
    for i, s in enumerate(side):
        where = f"side_effects[{i}]"
        if not isinstance(s, dict):
            problems.append(f"{where} must be a mapping of metric and one "
                            "bound")
            continue
        for key in sorted(set(s) - {"metric", *BOUNDS}):
            problems.append(f"{where} has no field {key!r}")
        metric = s.get("metric")
        bounds = [b for b in BOUNDS if b in s]
        if metric not in METRICS:
            problems.append(f"{where}: {metric!r} is not a metric this "
                            "measures; it measures " + ", ".join(METRICS))
            continue
        if metric in named:
            problems.append(f"{where}: {metric} is both predicted to move and "
                            "bounded; name it once")
            continue
        if len(bounds) != 1:
            problems.append(f"{where} needs exactly one of "
                            + ", ".join(BOUNDS))
            continue
        if not _number(s[bounds[0]]):
            problems.append(f"{where}: {bounds[0]} must be a number")
            continue
        out_side.append({"metric": metric, bounds[0]: s[bounds[0]]})

    if problems:
        raise PredictionError(problems)
    return {"expects": out_expects, "side_effects": out_side}


def simulate_include(policy):
    """The two `simulate.include` entries that measure a policy: before, after."""
    return [dict({"family": policy.family}, **policy.from_config.params),
            dict({"family": policy.family}, **policy.to_config.params)]


def write_prediction(workdir, policy, spec, seed,
                     tolerance=CALIBRATION_TOLERANCE):
    """Write `prediction.json` once. Returns (path, sha256)."""
    checked = validate_prediction(spec, tolerance)
    path = os.path.join(workdir, PREDICTION_NAME)
    if os.path.exists(path):
        raise PredictionError([
            f"{path} already exists. A prediction is written once, before the "
            "run; a new prediction is a new workdir"])
    corpus = {name: sha256_file(os.path.join(workdir, name))
              for name in CORPUS_FILES
              if os.path.exists(os.path.join(workdir, name))}
    doc = {
        "oneground_prediction": 1,
        "kind": "declared",
        "note": ("Written before the run. simulate records this file's "
                 "sha256 in simulate_info.json at the start of its run; a "
                 "verdict is given only when that citation matches this "
                 "file."),
        "policy": policy.as_dict()["policy"],
        "policy_sha256": policy.sha256(),
        "from_config": {"label": policy.from_config.label,
                        "params": dict(policy.from_config.params)},
        "to_config": {"label": policy.to_config.label,
                      "params": dict(policy.to_config.params)},
        "expects": checked["expects"],
        "side_effects": checked["side_effects"],
        "calibration_tolerance": tolerance,
        "run": {"seed": int(seed), "corpus": corpus},
    }
    write_json_stable(path, doc)
    return path, sha256_file(path)
