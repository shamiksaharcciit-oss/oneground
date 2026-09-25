"""`oneground propose <workdir> --policy <file> --prediction <file>`.

Tier 1 of the proposal loop: **the user writes the policy themselves.** There
is no model in this command, no API call and no prompt. Tier 1 exists to prove
the receipt machinery -- the pre-registered prediction, the baseline citation,
the two-run verdict, the card -- before a model is anywhere near it.

WHAT IT DOES
    Validates both files against what ships, refuses with everything wrong
    named at once (the 022 precondition rule), writes the prediction into the
    proposal's own directory, measures **only the changed configuration** on
    the sample the workdir already holds, judges it against the baseline row
    that is already there, and writes a card.

WHAT IT DOES NOT DO
    Re-run the baseline. The workdir holds that row already; re-measuring it
    would cost an hour, produce a second number for the same configuration,
    and leave a reader asking which one the verdict used. The row is cited by
    digest instead -- the file's and the row's -- and a row that has moved
    since the prediction was written is a refusal, not a silent comparison.

THE PRECONDITIONS, ALL OF THEM AT ONCE
    A refusal names every problem it found, because someone fixing a policy
    should learn its whole shape from one run rather than one problem per run.
    The checks are: both files parse and validate; the workdir is one
    `characterize` and `simulate` have both written; the baseline row exists;
    the requirements file the baseline run recorded is readable and still
    names this workdir and this seed; the corpus files still hash to what
    `characterize` recorded; the pinned libraries are the ones the baseline
    row was measured under; and this proposal's directory does not already
    hold a prediction that says something else.

    The last one is what makes a prediction pre-registered rather than
    decorative: a second run against the same directory with a different
    prediction is refused, and a new prediction is a new proposal directory.
"""

import os
import time

from .. import intake
# The one implementation of task 018's rule for writing a path into an
# artifact: repository-relative inside the tree, unchanged outside it, `/`
# separators. Imported rather than copied -- a second copy of this rule is how
# one of them drifts and puts a home directory back into a file.
from ..calibrate.history import _portable_source
from ..environment import PINNED
from ..models import get as get_model
from ..proposals import card as card_mod
from ..receipts import (library_versions, producing_version, round_floats,
                        sha256_file, write_json_stable, write_manifest)
from ..provenance import invocation
from ..report.verdict import CALIBRATION_TOLERANCE
from .policy import PolicyError, canonical_json, load_policy
from .prediction import PREDICTION_NAME, PredictionError, write_prediction
from .verdict import COULDNT_CHECK, judge

PROPOSALS_DIR = "proposals"
INFO_NAME = "propose_info.json"

# What `simulate` wrote, and what this command reads back.
REQUIRED = ("characterization.json", "sample_ids.json", "simulate.json",
            "simulate_info.json", "build_info.json")


class ProposeError(RuntimeError):
    """Every reason a proposal was refused, together."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("proposal refused:\n  - "
                         + "\n  - ".join(self.problems))


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _read_json(path):
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _slug(policy):
    """A directory name a reader recognises: what changed, from what, to what."""
    bits = [policy.family] + ["%s-%s-to-%s" % (p, f, t)
                              for p, f, t in policy.changes]
    text = "_".join(str(b) for b in bits)
    return "".join(ch if (ch.isalnum() or ch in "-_.") else "-"
                   for ch in text)


def row_digest(row):
    """The baseline row's own digest, over its canonical JSON.

    The file's digest changes when any row in it changes; this one changes
    only when the row the prediction is judged against changes, which is the
    thing a reader of the card needs to know did not move.
    """
    import hashlib
    return hashlib.sha256(canonical_json(row).encode("ascii")).hexdigest()


class Plan:
    """Everything the run needs, with every precondition already checked."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _named_file(recorded):
    """A corpus file as a card may name it: its name and its digest.

    Not its path. `build_info.json` records an absolute one, which on this
    machine runs through a home directory, and a card is published -- task
    014's rule, applied to the artifact this task adds.
    """
    recorded = recorded or {}
    path = recorded.get("path") or ""
    return {"name": os.path.basename(str(path).replace("\\", "/")),
            "sha256": recorded.get("sha256")}


def plan_proposal(workdir, policy_path, prediction_path, name=None,
                  requirements_path=None, tolerance=CALIBRATION_TOLERANCE,
                  log_fn=None, dry_run=False):
    """A `Plan`, or `ProposeError` naming every problem at once.

    `dry_run` gates the refusal receipt (`docs/TRIAGE.md` §7) the same
    way it gates everything else here: `docs/PROPOSALS.md` §2.1's own
    contract for the flag is "validate everything, print what would run,
    write nothing," and a receipt is a write. A dry run still shows every
    problem `--dry-run` always showed; it just leaves nothing behind.
    """
    import yaml

    problems = []
    workdir = os.path.normpath(workdir)
    missing = [f for f in REQUIRED
               if not os.path.exists(os.path.join(workdir, f))]
    if not os.path.isdir(workdir):
        problems.append(
            "%s is not a directory. A proposal is measured in a workdir that "
            "has already been characterized and simulated" % workdir)
    elif missing:
        problems.append(
            "%s has no %s. A proposal compares against a baseline that is "
            "already there, so run this first:\n        oneground simulate "
            "<requirements.yaml>" % (workdir, ", ".join(missing)))

    policy = None
    try:
        policy = load_policy(policy_path)
    except OSError as e:
        problems.append("--policy %s: %s" % (policy_path, e))
    except PolicyError as e:
        problems.extend("--policy %s: %s" % (policy_path, p)
                        for p in e.problems)
        # docs/TRIAGE.md §7's first item: a refusal used to be printed and
        # discarded. This is the receipt, written where the refusal
        # happens rather than reconstructed later from nothing -- a
        # workdir this far along already has what the receipt needs
        # (characterization.json, simulate_info.json). Skipped under
        # --dry-run, whose own contract (docs/PROPOSALS.md §2.1) is
        # "write nothing," and a receipt is a write.
        if not dry_run:
            from .refusal import write_refusal_receipt
            try:
                write_refusal_receipt(workdir, policy_path, e.problems,
                                      log_fn=log_fn)
            except Exception as receipt_error:                # noqa: BLE001
                # A receipt that fails to write must never turn a refusal
                # into a crash -- the original ProposeError below is
                # still the whole of what the caller needs to see.
                if log_fn:
                    log_fn("propose: refusal receipt not written -- "
                          f"{receipt_error}")
    except yaml.YAMLError as e:
        problems.append("--policy %s is not valid YAML: %s" % (policy_path, e))

    spec = None
    try:
        with open(prediction_path, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
    except OSError as e:
        problems.append("--prediction %s: %s" % (prediction_path, e))
    except yaml.YAMLError as e:
        problems.append("--prediction %s is not valid YAML: %s"
                        % (prediction_path, e))
    if spec is not None:
        from .prediction import validate_prediction
        try:
            spec = validate_prediction(spec, tolerance)
        except PredictionError as e:
            problems.extend("--prediction %s: %s" % (prediction_path, p)
                            for p in e.problems)
            spec = None

    if missing or not os.path.isdir(workdir):
        raise ProposeError(problems)

    simulate_json = _read_json(os.path.join(workdir, "simulate.json"))
    info = _read_json(os.path.join(workdir, "simulate_info.json"))
    build = _read_json(os.path.join(workdir, "build_info.json"))

    baseline_row, baseline_cite = None, None
    if policy is not None:
        label = policy.from_config.label
        for row in simulate_json.get("rows") or ():
            if row.get("config") == label:
                baseline_row = row
                break
        if baseline_row is None:
            have = ", ".join(sorted(r.get("config", "")
                                    for r in simulate_json.get("rows") or ()))
            problems.append(
                "no baseline row for %s in %s/simulate.json. The policy's "
                "`configuration` is the one being changed, and it has to have "
                "been measured. Rows there: %s. To measure it, add it to "
                "`simulate.include` in the requirements file and run:\n"
                "        oneground simulate <requirements.yaml>"
                % (label, workdir, have or "none"))
        else:
            baseline_cite = {
                "file": "simulate.json",
                "sha256": sha256_file(os.path.join(workdir, "simulate.json")),
                "config": label,
                "row_sha256": row_digest(baseline_row),
            }

    req_path = requirements_path or (info.get("requirements_file") or {}).get(
        "path")
    req = None
    if not req_path:
        problems.append(
            "%s/simulate_info.json records no requirements file, so the "
            "corpus this sample was drawn from cannot be found. Pass "
            "--requirements <requirements.yaml>" % workdir)
    elif not os.path.exists(req_path):
        problems.append(
            "the requirements file the baseline run recorded is not there: "
            "%s. Pass --requirements <requirements.yaml>" % req_path)
    else:
        try:
            req = intake.load(req_path)
        except Exception as e:                        # intake raises its own
            problems.append("--requirements %s: %s" % (req_path, e))

    sample, seed = {}, simulate_json.get("seed")
    if req is not None:
        req_workdir = os.path.normpath(req.resolve(req.workdir))
        if os.path.abspath(req_workdir) != os.path.abspath(workdir):
            problems.append(
                "%s says its workdir is %s, not %s: that requirements file "
                "and this workdir are not the same run"
                % (req_path, req_workdir, workdir))
        if req.seed != seed:
            problems.append(
                "%s has seed %s, and the baseline row was measured at seed "
                "%s. A proposal is measured on the same sample, seed and "
                "ground truth as its baseline" % (req_path, req.seed, seed))
        problems.extend(_corpus_problems(req, build))
        sample = {
            "n_base": simulate_json.get("n_base"),
            "n_queries": simulate_json.get("n_queries"),
            "ground_truth_k": simulate_json.get("ground_truth_k"),
            "seed": seed,
            "vectors": _named_file((build.get("inputs") or {}).get("vectors")),
            "queries": _named_file((build.get("inputs") or {}).get("queries")),
            "sample_ids_sha256": sha256_file(
                os.path.join(workdir, "sample_ids.json")),
        }

    problems.extend(_version_problems(info))

    from .. import simulate as sim
    recorded_depth = info.get("shard_depth")
    # Named without the workdir: this string is read back in the card, and a
    # workdir given as an absolute path would put a home directory in it.
    if recorded_depth is None:
        shard_depth, depth_source = sim.FAMILY_DEFAULT, (
            "the family's own default: simulate_info.json records no "
            "shard_depth, so the baseline row was measured under it")
    else:
        shard_depth, depth_source = int(recorded_depth), (
            "simulate_info.json: the value the baseline row was measured "
            "under")

    out_dir = os.path.join(workdir, PROPOSALS_DIR,
                           name or (_slug(policy) if policy else "proposal"))
    if policy is not None and spec is not None:
        problems.extend(_existing_prediction_problems(
            out_dir, policy, spec, baseline_cite))

    if problems:
        raise ProposeError(problems)

    return Plan(workdir=workdir, out_dir=out_dir, policy=policy, spec=spec,
                requirements_path=req_path, req=req, seed=seed,
                simulate_json=simulate_json, simulate_info=info,
                build_info=build, baseline_row=baseline_row,
                baseline_cite=baseline_cite, sample=sample,
                shard_depth=shard_depth, shard_depth_source=depth_source,
                tolerance=tolerance)


def _corpus_problems(req, build):
    """The sample's own files, still hashing to what `characterize` recorded.

    The requirements file may have been edited since the baseline run -- ours
    had been -- and most edits cannot move a number. A different vectors file
    can, so that is what is checked, rather than the requirements file's own
    digest.
    """
    out = []
    recorded = build.get("inputs") or {}
    for which, path in (("vectors", req.resolve(req.vectors.get("path"))),
                        ("queries", req.resolve((req.queries or {}).get(
                            "path")))):
        want = (recorded.get(which) or {}).get("sha256")
        if not path:
            out.append("the requirements file names no %s path" % which)
            continue
        if not os.path.exists(path):
            out.append("%s: %s is not there, so the sample the baseline row "
                       "was measured on cannot be loaded" % (which, path))
            continue
        if not want:
            out.append("build_info.json records no digest for %s, so this "
                       "run cannot show it is measuring the same sample"
                       % which)
            continue
        got = sha256_file(path)
        if got != want:
            out.append(
                "%s at %s hashes %s, and characterize recorded %s: this is "
                "not the file the baseline row was measured on. Re-run:\n"
                "        oneground characterize <requirements.yaml>"
                % (which, path, got[:12] + "...", want[:12] + "..."))
    return out


def _version_problems(info):
    """The pinned libraries, then and now.

    `environment.PINNED` is the project's own list of what can move a number.
    A baseline row measured under a different numpy is not a row this run's
    number can be subtracted from.
    """
    out = []
    then = info.get("library_versions") or {}
    now, _torch = library_versions(log=None)
    for pkg in PINNED:
        a, b = then.get(pkg), now.get(pkg)
        if a and b and a != b:
            out.append(
                "the baseline row was measured under %s %s and this "
                "environment has %s. A difference in a pinned library can "
                "move a measured number, so the two rows cannot be "
                "subtracted" % (pkg, a, b))
    return out


def _existing_prediction_problems(out_dir, policy, spec, baseline_cite):
    """A directory that already holds a prediction saying something else."""
    path = os.path.join(out_dir, PREDICTION_NAME)
    if not os.path.exists(path):
        return []
    try:
        old = _read_json(path)
    except (OSError, ValueError) as e:                # pragma: no cover
        return ["%s could not be read: %s" % (path, e)]
    out = []
    if old.get("policy_sha256") != policy.sha256():
        out.append("%s pre-registers a different policy (%s...). A prediction "
                   "is written once; a different policy is a different "
                   "proposal, so pass --name <another-name>"
                   % (path, str(old.get("policy_sha256"))[:12]))
    if {"expects": old.get("expects"),
            "side_effects": old.get("side_effects")} != spec:
        out.append("%s pre-registers a different prediction. A prediction is "
                   "written once, before the run; pass --name <another-name>"
                   % path)
    old_base = old.get("baseline") or {}
    if baseline_cite and old_base.get("row_sha256") != \
            baseline_cite["row_sha256"]:
        out.append(
            "%s was written against baseline row %s... and the row in "
            "simulate.json is now %s...: the baseline moved after the "
            "prediction was written, so this prediction cannot be judged "
            "against it. Start a new proposal with --name, or re-run:\n"
            "        oneground simulate <requirements.yaml>"
            % (path, str(old_base.get("row_sha256"))[:12],
               baseline_cite["row_sha256"][:12]))
    return out


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def row_and_timing(measured):
    """`(row, timing)` from whatever `measure_config` returned.

    Two shapes, deliberately both accepted. On this branch `measure_config`
    returns the row; task 020b, on `task-020`, moved the timing fields out of
    the row and returns `(row, timing)`. Git merges the two branches without a
    conflict -- the changes are in different functions -- and the merged tree
    then fails every proposal test on a tuple reaching `judge()`, which is
    what the release rehearsal found (`tasks/release-rehearsal.report.md`).

    Accepting both is what makes that merge hands-off. It is a shim with a
    known end: once 020b has landed, `measure_config` returns one shape and
    this can go back to unpacking it.
    """
    if isinstance(measured, tuple):
        return measured
    return measured, None


def measure_changed(plan, log_fn=log):
    """The one configuration this command measures.

    Loaded and measured through `simulate`'s own functions, on the sample the
    workdir holds and the ground truth it cached, so the row is produced by
    the same code the baseline row was.
    """
    import numpy as np

    from .. import simulate as sim
    from ..sample import loaders

    req, workdir = plan.req, plan.workdir
    vec_path = req.resolve(req.vectors.get("path"))
    log_fn("loading vectors %s" % vec_path)
    full = loaders.load_vectors(vec_path)
    idx = sim._sample_indices(workdir, len(full))
    base = np.ascontiguousarray(full[idx])
    if not req.vectors.get("normalized", False):
        base = loaders.normalize_rows(base)
    del full

    qcfg = dict(req.queries)
    qcfg["path"] = req.resolve(qcfg["path"])
    queries, _ = loaders.load_queries(qcfg)
    queries = loaders.normalize_rows(np.ascontiguousarray(queries))
    log_fn("%d vectors, %d queries, dim %d"
           % (len(base), len(queries), base.shape[1]))

    gt_k = int(plan.sample.get("ground_truth_k") or 100)
    gt_ids, gt_scores = sim._ground_truth(workdir, base, queries, gt_k, log_fn)

    config = plan.policy.to_config
    context = sim._centroid_cache(base, plan.seed, log_fn)(config)
    log_fn("measuring %s" % config.label)
    return row_and_timing(sim.measure_config(
        get_model(plan.policy.family), config, base, queries, gt_ids,
        gt_scores, plan.seed, context=context, log_fn=log_fn,
        shard_depth=plan.shard_depth))


def failed_judgement(prediction, reason):
    """A judgement for a run that did not produce a row.

    The same shape `judge` returns, so a card built from a failure carries
    every row a card built from a measurement does -- each one couldn't-check,
    naming why. There is no path that produces nothing.
    """
    rows = [{"kind": "expects", "metric": e["metric"],
             "outcome": COULDNT_CHECK, "detail": reason}
            for e in prediction.get("expects") or ()]
    rows += [{"kind": "side_effect", "metric": s["metric"],
              "outcome": COULDNT_CHECK, "detail": reason}
             for s in prediction.get("side_effects") or ()]
    return {"outcome": COULDNT_CHECK, "reason": reason, "rows": rows}


def run(workdir, policy_path, prediction_path, name=None, dry_run=False,
        requirements_path=None, env_stamp=None, log_fn=log, measure=None):
    """Validate, measure the changed configuration, judge it, write the card."""
    t0 = time.time()
    plan = plan_proposal(workdir, policy_path, prediction_path, name=name,
                         requirements_path=requirements_path, log_fn=log_fn,
                         dry_run=dry_run)
    if dry_run:
        _print_plan(plan)
        return 0

    os.makedirs(plan.out_dir, exist_ok=True)
    pred_path = os.path.join(plan.out_dir, PREDICTION_NAME)
    # An existing prediction that says the same thing is *reused*, never
    # rewritten. `plan_proposal` has already refused one that says anything
    # else, so reaching here means this proposal is being measured again --
    # after a run that could not complete, usually -- and rewriting the file
    # would destroy the only evidence that it was written first.
    written_here = not os.path.exists(pred_path)
    if written_here:
        pred_path, pred_sha = write_prediction(
            plan.workdir, plan.policy, plan.spec, plan.seed,
            tolerance=plan.tolerance, out_dir=plan.out_dir,
            baseline=plan.baseline_cite)
        log_fn("prediction written and read: %s sha256 %s"
               % (pred_path, pred_sha[:12]))
    else:
        pred_sha = sha256_file(pred_path)
        log_fn("prediction already written, reused unchanged: %s sha256 %s"
               % (pred_path, pred_sha[:12]))
        log_fn("this run replaces the card in %s" % plan.out_dir)
    prediction = _read_json(pred_path)

    changed_row, changed_timing, failure = None, None, None
    try:
        # Either shape, from `measure_changed` or from a caller's own
        # measurement: see `row_and_timing`.
        changed_row, changed_timing = row_and_timing(
            (measure or measure_changed)(plan, log_fn))
    except Exception as e:                            # a card is still written
        failure = "%s: %s" % (type(e).__name__, e)
        log_fn("the run did not complete: %s" % failure)

    if failure is None:
        simulate_like = {"seed": plan.seed,
                         "rows": [plan.baseline_row, changed_row]}
        info_like = {"prediction": {"file": PREDICTION_NAME,
                                    "sha256": pred_sha,
                                    "read": "before the changed configuration "
                                            "was measured"}}
        judgement = judge(prediction, pred_sha, simulate_like, info_like)
    else:
        judgement = failed_judgement(
            prediction,
            "the changed configuration could not be measured (%s). What would "
            "settle it: run this proposal again on a machine that can "
            "complete the measurement, against the same workdir -- the "
            "prediction is already written and is not rewritten by a second "
            "run" % failure)

    card = build_card(plan, prediction, pred_sha, changed_row, judgement,
                      env_stamp=env_stamp, elapsed=time.time() - t0,
                      failure=failure, written_here=written_here)
    # The page is rendered from the card as written, not from the card in
    # memory: `card.html` is then a rendering of the bytes in `card.json`, and
    # a reader who has the receipt can rebuild the page and see they agree.
    card_path = os.path.join(plan.out_dir, card_mod.CARD_NAME)
    write_json_stable(card_path, round_floats(card))
    written = _read_json(card_path)
    with open(os.path.join(plan.out_dir, card_mod.CARD_HTML), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(card_mod.render_card_html(written))
    write_json_stable(os.path.join(plan.out_dir, INFO_NAME),
                      _info(plan, pred_sha, failure, time.time() - t0,
                            timing=changed_timing))
    write_manifest(plan.out_dir, [PREDICTION_NAME, card_mod.CARD_NAME,
                                  card_mod.CARD_HTML, INFO_NAME])
    _print_card(card, plan)
    return 0


def build_card(plan, prediction, pred_sha, changed_row, judgement,
               env_stamp=None, elapsed=None, failure=None, written_here=True):
    """The card, as a dict. Every sentence in it is built from these rows."""
    from ..environment import stamp as env_stamp_now

    from_label = plan.policy.from_config.label
    to_label = plan.policy.to_config.label
    card = {
        "oneground_card": 1,
        "kind": {card_mod.CARD_NAME: "receipt", card_mod.CARD_HTML: "receipt",
                 PREDICTION_NAME: "declared", INFO_NAME: "declared"},
        "run": plan.simulate_json.get("run"),
        "proposal": os.path.basename(plan.out_dir),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "outcome": judgement["outcome"],
        "judgement": judgement,
        "policy": plan.policy.as_dict()["policy"],
        "policy_sha256": plan.policy.sha256(),
        "prediction": {
            "file": PREDICTION_NAME,
            "sha256": pred_sha,
            "cited_by_run": ("yes: read before the changed configuration was "
                             "measured" + ("" if written_here else
                                           ", and written by an earlier run "
                                           "of this proposal, unchanged")),
            "expects": prediction.get("expects"),
            "side_effects": prediction.get("side_effects"),
            "calibration_tolerance": prediction.get("calibration_tolerance"),
        },
        "configurations": {
            "baseline": dict(
                plan.baseline_cite,
                label=from_label,
                params=dict(plan.policy.from_config.params),
                source="simulate.json:rows[%s]" % from_label,
                file_sha256=plan.baseline_cite["sha256"],
                measured_at=plan.simulate_info.get("run_at"),
                # What it was measured under. The run refuses when a pinned
                # library differs from this, so a reader can see the two rows
                # were produced by the same versions rather than take it.
                library_versions=plan.simulate_info.get("library_versions"),
                # And which oneground produced it (task 033). A card is the
                # one receipt that must carry two of these -- the baseline
                # row's and the changed row's -- because a comparability
                # verdict is a statement about both, and a card with one of
                # them cannot support one (docs/LIBRARY.md §2.2). A workdir
                # written before 033 has none, and says so rather than
                # reading as a match.
                oneground=plan.simulate_info.get("oneground") or {
                    "version": None, "commit": None, "dirty": None,
                    "source": "unknown",
                    "note": "the run that measured this row was written "
                            "before task 033, so it recorded no version"},
                re_run=False),
            "changed": {
                "label": to_label,
                "params": dict(plan.policy.to_config.params),
                "measured_here": failure is None,
                "shard_depth": plan.shard_depth,
                "shard_depth_source": plan.shard_depth_source,
                # This run's, against the baseline's above: the two a
                # comparability verdict is about (task 033).
                "oneground": producing_version(),
                # Which command wrote this, for the replay rule (task 046,
                # docs/INTERFACE.md section 2). Beside the version rather than
                # inside it: it is not a fact about the version.
                "invocation": invocation(),
            },
        },
        "sample": plan.sample,
        "measured": {"baseline": plan.baseline_row, "changed": changed_row},
        "calibration": _calibration(plan),
        "environment": env_stamp or env_stamp_now(),
        "elapsed_seconds": elapsed,
        "failure": failure,
    }
    claims = card_mod.build_claims(card, judgement, from_label, to_label)
    rows = card_mod.build_rows(judgement, plan.baseline_row, changed_row,
                               from_label, to_label)
    from ..report import claims as cl
    # Task 045. The workdir turns on step 8 here too, so a card's citation
    # into `simulate.json` is read rather than trusted. `card.json` itself is
    # `pending`: it is the file this check is a precondition for writing.
    cl.raise_on_violation(claims, rows, where="the proposal card",
                          workdir=plan.workdir,
                          pending=(card_mod.CARD_NAME,))
    card["claims"] = [c.as_dict() for c in claims]
    card["text"] = [c.text for c in claims]
    violations = card_mod.card_violations(card)
    if violations:                                    # pragma: no cover
        raise cl.ClaimViolation(
            "a card says what a card may never say:\n  "
            + "\n  ".join(violations))
    return card


def _calibration(plan):
    """The calibration line the verdicts were judged under.

    The tolerance is the number the two-run rule uses, and the line is what
    this installation last measured the policy's family against. Absence is
    stated: a card that printed nothing would read as a card that needed
    nothing.
    """
    from ..calibrate import history as H

    family = plan.policy.family
    out = {"tolerance": plan.tolerance, "history_path": H.DEFAULT_PATH,
           "family": family, "family_line": None, "statements": []}
    try:
        lines = H.read(H.DEFAULT_PATH)
    except (OSError, ValueError) as e:
        out["statements"].append("The calibration history at %s could not be "
                                 "read: %s." % (H.DEFAULT_PATH, e))
        return out
    hits = [ln for ln in lines
            if ln.get("check") == "glove_curve"
            and str(ln.get("config", "")).startswith(family)
            and ln.get("outcome_scope", H.BLOCKING) == H.BLOCKING]
    if not hits:
        out["statements"].append(
            "There is no calibration line for %s in %s, so how far this "
            "installation's %s sits from published numbers has not been "
            "measured here." % (family, H.DEFAULT_PATH, family))
        return out
    line = hits[-1]
    out["family_line"] = line
    out["statements"].append(
        "Last calibrated %s on %s as %s: %s, deviation %s against tolerance "
        "%s." % (line.get("date"), line.get("dataset"), line.get("config"),
                 line.get("outcome"), line.get("deviation"),
                 line.get("tolerance")))
    return out


def _info(plan, pred_sha, failure, elapsed, timing=None):
    import platform
    versions, torch_info = library_versions(log=None)
    return {
        "kind": {INFO_NAME: "declared"},
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": "oneground propose",
        "workdir": str(plan.workdir).replace("\\", "/"),
        "requirements_file": {
            # Portable, for the reason calibration lines are: a path through a
            # home directory says whose machine wrote the file.
            "path": _portable_source(plan.requirements_path),
            "sha256": sha256_file(plan.requirements_path),
            "recorded_by_the_baseline_run": (
                plan.simulate_info.get("requirements_file") or {}).get(
                    "sha256"),
        },
        "prediction": {"file": PREDICTION_NAME, "sha256": pred_sha,
                       "read": "at the start of the run, before the changed "
                               "configuration was measured"},
        # None on this branch, where `measure_config` keeps its timings in the
        # row; the pair task 020b returns once that lands. Timings belong in
        # the declared file either way -- a card compares rows.
        "timing": timing,
        "baseline": plan.baseline_cite,
        "measured": [plan.policy.to_config.label],
        "not_measured": [plan.policy.from_config.label],
        "not_measured_reason": "the baseline row is already in "
                               "simulate.json and is cited by digest",
        "shard_depth": plan.shard_depth,
        "shard_depth_source": plan.shard_depth_source,
        "library_versions": versions,
        "oneground": producing_version(),
        # Which command wrote this, for the replay rule (task 046,
        # docs/INTERFACE.md section 2). Beside the version rather than
        # inside it: it is not a fact about the version.
        "invocation": invocation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "torch_cuda": torch_info["torch_cuda"],
        "elapsed_seconds": elapsed,
        "failure": failure,
    }


# --------------------------------------------------------------------------
# what the console prints
# --------------------------------------------------------------------------

def _print_plan(plan):
    print()
    print("dry run: nothing was measured and nothing was written.")
    print()
    print("  workdir            %s" % plan.workdir)
    print("  requirements       %s" % plan.requirements_path)
    print("  baseline (not run) %s" % plan.policy.from_config.label)
    print("                     simulate.json sha256 %s..., row %s..."
          % (plan.baseline_cite["sha256"][:12],
             plan.baseline_cite["row_sha256"][:12]))
    print("  would measure      %s" % plan.policy.to_config.label)
    print("  seed               %s" % plan.seed)
    print("  shard_depth        %s (%s)" % (plan.shard_depth,
                                            plan.shard_depth_source))
    print("  would write        %s" % os.path.join(plan.out_dir, "card.json"))
    print()
    for e in plan.spec["expects"]:
        print("  expects            %s %s by at least %s"
              % (e["metric"], e["direction"], e["by_at_least"]))
    for s in plan.spec["side_effects"]:
        bound = [k for k in s if k != "metric"][0]
        print("  budget             %s %s %s" % (s["metric"], bound, s[bound]))
    print()


def _print_card(card, plan):
    print()
    print("=" * 78)
    for line in card["text"]:
        print(line)
        print()
    print("=" * 78)
    print("  card.json + card.html in %s" % plan.out_dir)
    print()
