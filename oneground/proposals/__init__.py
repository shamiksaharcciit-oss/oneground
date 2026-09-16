"""Proposals: the parts of the loop that have no model in them (task 026).

docs/PROPOSALS.md is the position this is built against. The sequencing there
puts the refusals before the capabilities, so this package is only:

    policy       a parameter change over a whole configuration of a shipped
                 family, validated against that family's parameter table.
                 Not code, never executed, no scopes.
    prediction   what the change is expected to do, written before the run,
                 refused below the calibration tolerance or without a metric,
                 a direction and a threshold. The run cites its sha256.
    verdict      the two-run rule: held / did not hold / couldn't check,
                 from a baseline row and a policy row of the same run, never
                 from the report's absolute thresholds.

There is no command, no model and no card. Nothing here translates a sentence
or publishes anything.
"""

from .policy import Policy, PolicyError, load_policy, validate_policy
from .prediction import (PREDICTION_NAME, PredictionError, simulate_include,
                         validate_prediction, write_prediction)
from .verdict import COULDNT_CHECK, DID_NOT_HOLD, HELD, judge

__all__ = ["COULDNT_CHECK", "DID_NOT_HOLD", "HELD", "PREDICTION_NAME",
           "Policy", "PolicyError", "PredictionError", "judge", "load_policy",
           "simulate_include", "validate_policy", "validate_prediction",
           "write_prediction"]
