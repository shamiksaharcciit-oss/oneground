"""The two-run verdict: did a pre-registered prediction hold?

Task 026. The report's verdicts compare one configuration against absolute
thresholds (`recall_at_k.min`, a p95 cap). A prediction is about a
*difference* between two configurations measured in the same run, and it has
its own rule, which never reuses those thresholds.

For an expected change with threshold T, the observed delta is the policy
row minus the baseline row (baseline minus policy for `falls`). With the
calibration tolerance t that the prediction was validated against:

    |delta - T| < t      couldnt_check: the delta cannot be told from the
                         threshold, the same reading the report gives two
                         recalls closer than t ("indistinguishable")
    delta > T            held          (so delta >= T + t)
    delta < T            did_not_hold  (so delta <= T - t)

A side-effect bound B on the policy row's value reads the same way:
within t of B is couldnt_check, on the right side is held, else did_not_hold.

Deviations are rounded to 6 decimals before the comparison, as
`calibrate.history` does, so a point exactly on the band is decided by the
measurement rather than by float representation.

The whole judgement is couldnt_check, with the reason, when the run's inputs
do not cite this prediction's sha256 -- nothing then shows it was written
before the run -- when the run's seed is not the prediction's, or when a
configuration's row is missing. Overall: did_not_hold if any row did not
hold, else couldnt_check if any row could not be checked, else held.
"""

HELD = "held"
DID_NOT_HOLD = "did_not_hold"
COULDNT_CHECK = "couldnt_check"

DECIMALS = 6


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _band(value, target, tolerance, right_side):
    """held / did_not_hold / couldnt_check for `value` against `target`."""
    gap = round(value - target, DECIMALS)
    if abs(gap) < tolerance:
        return COULDNT_CHECK
    return HELD if right_side(gap) else DID_NOT_HOLD


def judge(prediction, prediction_sha256, simulate_json, simulate_info):
    """`{"outcome", "reason", "rows"}` for one prediction against one run."""
    tolerance = float(prediction["calibration_tolerance"])
    expects = prediction.get("expects") or []
    side = prediction.get("side_effects") or []

    def whole(reason):
        rows = ([{"kind": "expects", "metric": e["metric"],
                  "outcome": COULDNT_CHECK, "detail": reason}
                 for e in expects]
                + [{"kind": "side_effect", "metric": s["metric"],
                    "outcome": COULDNT_CHECK, "detail": reason}
                   for s in side])
        return {"outcome": COULDNT_CHECK, "reason": reason, "rows": rows}

    cited = (simulate_info or {}).get("prediction")
    if not cited:
        return whole("the run's inputs cite no prediction, so nothing shows "
                     "this one was written before the run")
    if cited.get("sha256") != prediction_sha256:
        return whole(f"the run cites prediction {str(cited.get('sha256'))[:12]}"
                     f"..., not this file ({prediction_sha256[:12]}...): it "
                     "was written or edited after the run started")
    seed = prediction.get("run", {}).get("seed")
    if simulate_json.get("seed") != seed:
        return whole(f"the run's seed is {simulate_json.get('seed')}, the "
                     f"prediction's is {seed}")

    by_label = {r.get("config"): r for r in simulate_json.get("rows") or []}
    before = by_label.get(prediction["from_config"]["label"])
    after = by_label.get(prediction["to_config"]["label"])
    for name, row in (("from", before), ("to", after)):
        if row is None:
            label = prediction[f"{name}_config"]["label"]
            return whole(f"the run has no row for {label}")

    rows = []
    for e in expects:
        m, t = e["metric"], e["by_at_least"]
        a, b = before.get(m), after.get(m)
        if not (_number(a) and _number(b)):
            rows.append({"kind": "expects", "metric": m,
                         "outcome": COULDNT_CHECK,
                         "detail": f"{m} is not a number in both rows "
                                   f"({a!r}, {b!r})"})
            continue
        delta = round((b - a) if e["direction"] == "rises" else (a - b),
                      DECIMALS)
        outcome = _band(delta, t, tolerance, lambda gap: gap > 0)
        rows.append({"kind": "expects", "metric": m, "outcome": outcome,
                     "before": a, "after": b, "delta": delta,
                     "detail": f"{m} {e['direction']} by {delta}, predicted at "
                               f"least {t}, tolerance {tolerance}"})
    for s in side:
        m = s["metric"]
        v = after.get(m)
        (bound_name, bound), = [(k, s[k]) for k in s if k != "metric"]
        if not _number(v):
            rows.append({"kind": "side_effect", "metric": m,
                         "outcome": COULDNT_CHECK,
                         "detail": f"{m} is not a number ({v!r})"})
            continue
        below = bound_name == "stays_at_or_below"
        outcome = _band(v, bound, tolerance,
                        (lambda gap: gap < 0) if below else (lambda gap: gap > 0))
        rows.append({"kind": "side_effect", "metric": m, "outcome": outcome,
                     "value": v, "bound": bound,
                     "detail": f"{m} is {v}, bound {bound_name} {bound}, "
                               f"tolerance {tolerance}"})

    outcomes = {r["outcome"] for r in rows}
    if DID_NOT_HOLD in outcomes:
        outcome = DID_NOT_HOLD
    elif COULDNT_CHECK in outcomes:
        outcome = COULDNT_CHECK
    else:
        outcome = HELD
    return {"outcome": outcome, "reason": "", "rows": rows}
