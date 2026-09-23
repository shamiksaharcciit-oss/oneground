"""`oneground report <requirements.yaml>` -- the first verdicts.

Every other command measures. This one judges: it reads the workdir's
receipts, compares them to the user's constraints, and produces three outcomes
per option, a decision log, a deployable manifest and an HTML page.

What separates this from a benchmark summary
--------------------------------------------
**Measurement and judgement are separate keys, all the way out.** In
`report.json` every option carries `measurement` (the numbers, re-derivable
from the workdir) and `judgement` (what those numbers mean against constraints
that may change tomorrow). Re-running with a different `constraints` block
changes every judgement and no measurement, and the file's shape makes that
obvious.

**Latency verdicts come only from `verify.json`.** `verdict.latency_p95` takes
verify rows, not simulate rows; there is no code path from a simulated number
to a latency verdict, and a test asserts a simulate-only workdir yields
`couldnt_check` for every option.

**couldn't-check is never rounded up.** It is amber, it is counted, it appears
in the recommendation's own three outcomes, and the decision log's final
entries say exactly what would turn each one into a verdict.

**Families that did not run are listed as not run**, with the reason. A
missing row and a failing row look identical in a table of what ran, and they
mean opposite things.

Outputs, all in the workdir:

    report.json     rows, verdicts, decision log; measurement/judgement split
    manifest.yaml   the recommended configuration in deployable form, with
                    the digest of every input it was derived from
    report.html     one self-contained file, no network calls
"""

import json
import os
import platform
import re
import time

import yaml

from .. import analogy
from .. import capacity
from .. import cost as costmod
from .. import environment
from .. import intake
from ..receipts import (MANIFEST_NAME, library_versions,
                        producing_version, public_paths_in, round_floats,
                        sha256_file, write_json_stable, write_manifest)
from . import claims as cl
from . import verdict as vd
from .html import render_html

COULDNT_CHECK = vd.COULDNT_CHECK

INPUT_FILES = ["characterization.json", "build_info.json", "sample_ids.json",
               "queries_ids.json", "simulate.json", "simulate_info.json",
               "verify.json", "verify_info.json",
               # Task 026: a pre-registered prediction, when the run had one.
               # Declared, per the kind map simulate_info.json records.
               "prediction.json"]

OUTPUT_FILES = ["report.json", "manifest.yaml", "report.html"]


class ReportError(RuntimeError):
    """The report cannot be produced. The message says what to run first."""


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _load(workdir, name):
    p = os.path.join(workdir, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _environment_of(verify_info):
    """A short name for where a verify run happened.

    Used only to decide whether a latency measurement targets the environment
    a constraint is about. Deliberately coarse: `local` on this laptop is not
    `local` on someone else's, and the platform string is carried alongside so
    a reader can see the difference the label hides.
    """
    if not verify_info:
        return None
    target = verify_info.get("target") or "unknown"
    return str(target)


# --------------------------------------------------------------------------
# decision log
# --------------------------------------------------------------------------

def decision_log(options, not_run_rows, recommended, constraints,
                 verify_info, tolerance=vd.CALIBRATION_TOLERANCE, k=10,
                 env_id=None):
    """The decision log as `{kind, text, source}` entries.

    Kept as the shape every existing reader speaks. The sentences themselves
    are rendered from `Claim` objects -- see `decision_claims` and
    `oneground/report/claims.py` -- so that each one can be checked against
    the rows it is about rather than merely spell-checked.
    """
    return [c.as_entry() for c in decision_claims(
        options, not_run_rows, recommended, constraints, verify_info,
        tolerance=tolerance, k=k, env_id=env_id)]


def decision_claims(options, not_run_rows, recommended, constraints,
                    verify_info, tolerance=vd.CALIBRATION_TOLERANCE, k=10,
                    env_id=None):
    """One `Claim` per rule that fired, in order.

    Every entry names the constraint, the value, the threshold and the source
    file and field, so the log can be checked against the workdir line by
    line. The final entries say what would turn each couldn't-check into a
    verdict -- a log that only records what was decided is half a log.

    Task 019: each is built structured and rendered afterwards, because
    "does this sentence say something true about these rows" is not
    computable once the sentence is a string. Two shipped defects say so.
    """
    lines = []

    def add(kind, text, source=""):
        """Kept for the tier-2 log and anything that is not about rows."""
        lines.append(cl.Claim(kind=kind, predicate=kind,
                              quantifier=cl.NONE, text=text, source=source))

    def claim(c):
        cl.render(c)
        lines.append(c)

    n = len(options)
    judged = _judged_constraint_names(options, constraints)
    claim(cl.Claim(
        kind="scope", predicate="were measured and judged",
        quantifier=cl.NONE, source="requirements:constraints",
        extra={"n_options": n, "constraint_names": tuple(judged)}))

    for row in not_run_rows:
        claim(cl.Claim(
            kind="not_run", predicate="produced no rows", quantifier=cl.NONE,
            subject=row["family"], detail=row["reason"],
            source="simulate_info.json:dropped"))

    for opt in options:
        for v in opt.verdicts:
            if v.outcome == vd.FAILS:
                # With two engines an unqualified "fails latency_p95" appears
                # twice with different numbers and no way to tell them apart.
                claim(_verdict_claim("fails", opt, v, env_id))

    # Latency and throughput verdicts name the environment they came from,
    # whichever way they went: a p95 is a fact about a machine, and a reader
    # who cannot see which machine cannot use it.
    for opt in options:
        for v in opt.verdicts:
            if v.constraint in ("latency_p95", "qps") and v.outcome == vd.MEETS:
                claim(_verdict_claim("meets_environment", opt, v, env_id))

    for opt in options:
        if opt.outcome == vd.MEETS:
            claim(_meets_claim(opt))

    # indistinguishability, stated once per group rather than per pair
    seen = set()
    for opt in options:
        if not opt.indistinguishable_from:
            continue
        group = tuple(sorted([opt.config] + opt.indistinguishable_from))
        if group in seen:
            continue
        seen.add(group)
        by_config = {o.config: o for o in options}
        cites = tuple(
            cl.Cite(member=cfg,
                    value=by_config[cfg].measurement.get("recall_at_%d" % k),
                    outcome=by_config[cfg].outcome,
                    constraint="recall_at_%d" % k,
                    source="simulate.json:rows[%s].recall_at_%d" % (cfg, k))
            for cfg in group if cfg in by_config)
        claim(cl.Claim(
            kind="indistinguishable",
            predicate="is indistinguishable on recall from the others",
            # Universal, and admissible only because the group was BUILT as
            # the set whose recall lies within tolerance of each other.
            quantifier=cl.UNIVERSAL,
            constraint="recall_at_%d" % k,
            scope=tuple(c.member for c in cites),
            holds_for=tuple(c.member for c in cites),
            cites=cites,
            source="simulate.json:rows[*].recall_at_%d" % k,
            extra={"tolerance": tolerance,
                   # A configured constant, not a measured value, and the
                   # sentence quotes it. Declared so the "quotes a number it
                   # does not cite" check knows where it came from.
                   "literal_numbers": (str(tolerance),)}))

    # Two engines, one environment, one configuration: the comparison the
    # same-environment and same-configuration rules exist to make safe.
    for c in compare_engine_claims(options, env_id, verify_info):
        lines.append(c)

    if recommended is None:
        claim(cl.Claim(kind="recommendation", predicate="is recommended",
                       quantifier=cl.NONE, subject=None, source="(rule)"))
    else:
        margins = [v.constraint for v in recommended.verdicts
                   if vd.at_margin(v)]
        storage = recommended.measurement.get("storage_amplification")
        claim(cl.Claim(
            kind="recommendation", predicate="is recommended",
            quantifier=cl.NONE, subject=recommended.config,
            scope=(recommended.config,), holds_for=(recommended.config,),
            cites=(cl.Cite(member=recommended.config,
                           outcome=recommended.outcome,
                           source="simulate.json:rows[%s]"
                                  % recommended.config),),
            source="simulate.json:rows[%s]" % recommended.config,
            extra={"margins": margins,
                   "checked_constraints": tuple(dict.fromkeys(
                       v.constraint for v in recommended.verdicts
                       if v.outcome != COULDNT_CHECK)),
                   "storage": storage,
                   "fanout": recommended.measurement.get("fanout"),
                   # The ranking numbers are quoted in the sentence, so the
                   # prose-quotes-an-uncited-number check is told about them.
                   "literal_numbers": ("%.2f" % (storage or 0.0),)}))

    # Task 034: a quantised row is bounded twice over -- by this sample, and
    # by what this sample looks like, because the codebook was learned from
    # it. Said once per run rather than per row: it is one fact about the
    # algorithm, not a judgement of any configuration.
    from ..proposals.card import quantised_in
    quantised = quantised_in(*[opt.params for opt in options])
    if quantised:
        claim(cl.Claim(kind="quantisation_limits", predicate="quantisation",
                       source="simulate.json:rows[*].params.index",
                       extra={"families": quantised}))

    # What would turn each couldn't-check into a verdict.
    unresolved = {}
    for opt in options:
        for v in opt.verdicts:
            if v.outcome == COULDNT_CHECK:
                unresolved.setdefault(v.constraint, v)
    for name, v in sorted(unresolved.items()):
        claim(cl.Claim(kind="to_resolve", predicate="would be decided by",
                       quantifier=cl.NONE, constraint=name,
                       detail=_how_to_resolve(name, v, verify_info),
                       source=v.source))

    if not unresolved:
        # Universal over the constraints, and true by construction: this
        # branch runs only when none of them is couldnt_check. Declaring it
        # NONE let the word "every" into a sentence the checker could not
        # check -- the invariant found it, which is the point of the
        # invariant.
        decided = tuple(dict.fromkeys(
            v.constraint for opt in options for v in opt.verdicts))
        claim(cl.Claim(
            kind="to_resolve", predicate="was decidable from this workdir",
            quantifier=cl.UNIVERSAL, scope=decided, holds_for=decided,
            cites=tuple(cl.Cite(member=n, constraint=n,
                                source="report.json:options[*].judgement")
                        for n in decided),
            source="(rule)",
            detail="Every constraint was decidable from this workdir; "
                   "nothing is outstanding."))
    return lines


def _verdict_claim(kind, opt, v, env_id):
    """One per-verdict claim: `fails` and `meets_environment`.

    The engine rides on the Cite rather than being interpolated by the caller,
    which is what makes "on qdrant" impossible to forget -- and forgetting it
    is exactly how the 015 and 017e defects read.
    """
    member = v.engine if v.engine is not None else opt.config
    return cl.Claim(
        kind=kind, predicate=kind.split("_")[0], quantifier=cl.NONE,
        subject=opt.config, constraint=v.constraint,
        scope=(member,), holds_for=(member,),
        cites=(cl.Cite(member=member, value=v.value, outcome=v.outcome,
                       constraint=v.constraint, source=v.source,
                       reason=v.reason),),
        detail=v.reason, source=v.source, environment=env_id,
        extra={"engine_scoped": v.engine is not None,
               "environment_relevant": v.constraint in ("latency_p95", "qps")})


def _meets_claim(opt):
    """`<config> meets every constraint that could be checked: ...`

    EXISTENTIAL, not universal, and that is the whole point. `Option.outcome`
    is `meets` when each constraint meets on AT LEAST ONE engine -- see
    `collapse_by_constraint` -- so the sentence is "there is an engine on
    which this holds", and it has to name which. Calling it universal is the
    015 defect restated in the type system.
    """
    # EVERY verdict is cited, not only the meeting ones. The sentence lists
    # what meets -- that is what it is for -- but the claim quantifies over
    # every engine, and a set the claim is about with no cited row is exactly
    # the shape of the 015 defect.
    cites = tuple(
        cl.Cite(member=(v.engine if v.engine is not None else opt.config),
                value=v.value, outcome=v.outcome, constraint=v.constraint,
                source=v.source, reason=v.reason)
        for v in opt.verdicts)
    meeting = [v for v in opt.verdicts if v.outcome == vd.MEETS]
    engines = [v.engine for v in opt.verdicts if v.engine is not None]
    scope = tuple(dict.fromkeys(engines)) or (opt.config,)
    holds = tuple(dict.fromkeys(
        v.engine for v in meeting if v.engine is not None)) or (opt.config,)
    return cl.Claim(
        kind="meets", predicate="meets every constraint that could be checked",
        quantifier=cl.EXISTENTIAL if engines else cl.NONE,
        subject=opt.config, scope=scope, holds_for=holds, cites=cites,
        asserts_outcome=vd.MEETS,
        source="simulate.json:rows[%s]" % opt.config,
        extra={"not_on_every_engine": _not_on_every_engine(opt),
               "meets_outcome": vd.MEETS})


def _not_on_every_engine(opt):
    """See `claims.not_on_every_engine`. Kept as a name the report already
    speaks; the sentence itself is composed in the renderer."""
    return cl.not_on_every_engine(opt.verdicts, meets=vd.MEETS)


def runner_up_lines(recommended, options):
    """See `claims.runner_up_lines`."""
    return cl.runner_up_lines(recommended, options, meets=vd.MEETS,
                              couldnt_check=COULDNT_CHECK)


def run_declared(req, requirements_path, workdir, t0, log_fn=log,
                 env_stamp=None):
    """Tier 2: the fixture analogy and the capacity arithmetic. No verdicts.

    Every constraint comes back couldn't-check, because nothing was measured
    on the user's corpus. Nothing is recommended, because a recommendation
    from a description is the thing this project exists not to do. What the
    report gives instead is a nearest published corpus with **its own**
    numbers plainly labelled, arithmetic over what the user declared, and a
    final log entry saying exactly what would turn each couldn't-check into a
    measurement.
    """
    char = _load(workdir, "characterization.json")
    if char is None:
        raise ReportError(
            f"no characterization.json in {workdir}. Run this first:\n\n"
            f"    oneground characterize {requirements_path}\n")
    if char.get("tier") != 2:
        raise ReportError(
            f"{workdir} holds a Tier-1 characterization but "
            f"{requirements_path} is Tier 2 (corpus.declared, no "
            "corpus.sample). Re-run `oneground characterize` so the workdir "
            "and the requirements describe the same run.")

    declared = char.get("declared") or {}
    constraints = req.data.get("constraints") or {}
    log_fn(f"report '{req.name}': Tier 2, declared corpus "
           f"{int(declared['size_now']):,} x {int(declared['dimension'])}d")

    # ---- the analogy ----
    chosen, why = analogy.choose(declared)
    surface, spec = {}, {}
    if chosen is not None:
        with open(chosen.spec_path, encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        surface = analogy.fixture_surface(spec)
        log_fn(f"analogy: {chosen.fixture} ({chosen.score:.2f})")
    else:
        log_fn(f"analogy: none -- {why}")

    analogy_block = {
        "kind": "declared",
        "chosen": chosen.as_dict() if chosen else None,
        "why": why,
        "label": chosen.label() if chosen else None,
        "fixture_characterization": surface,
        "fixture_reference_results": (spec.get("reference_results") or {}
                                      if chosen else {}),
        "note": ("Every value under fixture_* was measured on the fixture "
                 "named above. None of it was measured on your corpus, and "
                 "none of it may be read as if it were."),
    }

    # ---- the arithmetic ----
    families = list((req.data.get("simulate") or {}).get("families")
                    or ["single_node_hnsw"])
    cost_cfg = req.data.get("cost") or (req.data.get("verify") or {}).get(
        "cost") or {}
    prices = None
    if cost_cfg.get("prices"):
        try:
            prices = costmod.load_prices(req.resolve(cost_cfg["prices"]))
        except Exception as e:                        # reported, not raised
            log_fn(f"cost: {e}")
    cap = capacity.plan(
        declared, constraints, families,
        prices=prices,
        analogy_surface=(analogy_block["fixture_reference_results"]
                         if chosen else None),
        seed=req.seed, log_fn=log_fn,
        error_band=cost_cfg.get("error_band"))

    # ---- the verdicts that are not verdicts ----
    names = _constraint_names(constraints)
    verdicts = [{
        "constraint": name,
        "outcome": vd.COULDNT_CHECK,
        "reason": ("nothing was measured on your corpus: this run declared "
                   "it rather than sampling it"),
        "source": "characterization.json:declared",
        "kind": "declared",
    } for name in names]

    dlog = _declared_log(req, declared, constraints, chosen, why, cap, names)

    report = {
        "oneground_report": 1,
        "run": req.name,
        "tier": 2,
        "kind": "declared",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Which interpreter produced this report, and whether it was
        # running the pins. A reader who finds `pinned: false` knows the
        # numbers were judged outside requirements.txt.
        # `run_environment`, not `environment`: the Tier-1 report already
        # uses that key for the verify target's environment, and one of the
        # two would silently win the dict literal. This one is the
        # interpreter that produced the report.
        "run_environment": env_stamp or environment.stamp(),
        # And which oneground judged them (task 033): the stamp above
        # says which interpreter and pins, and said nothing about the
        # code that read the rows.
        "oneground": producing_version(),
        "declared": declared,
        "analogy": analogy_block,
        "capacity": cap,
        "constraints": verdicts,
        "options": [],
        "recommended": None,
        "recommendation_reason": (
            "Tier 2 issues no recommendation. Nothing here was measured on "
            "your corpus, and a recommendation from a description is a guess "
            "wearing a verdict's clothes."),
        "decision_log": dlog,
    }
    write_json_stable(os.path.join(workdir, "report.json"), report)
    listed = write_manifest(workdir, ["characterization.json",
                                      "build_info.json", "report.json"])
    _summary_declared(report, workdir, listed, time.time() - t0)
    return workdir


def _declared_log(req, declared, constraints, chosen, why, cap, names):
    """The Tier-2 decision log. Ends by saying what would make this real."""
    lines = []

    def add(kind, text, source=""):
        lines.append({"kind": kind, "text": text, "source": source})

    add("scope",
        f"Tier 2: the corpus was declared, not sampled. "
        f"{len(names)} constraint(s) were named -- "
        f"{', '.join(names) or 'none'} -- and none of them can be judged, "
        "because nothing here was measured on your corpus.",
        source="characterization.json:declared")

    if chosen is not None:
        add("analogy",
            f"Nearest published corpus: {chosen.fixture}. {why}. Its measured "
            f"values are shown under the label \"{chosen.label()}\". They "
            "describe that corpus. Yours may differ in every one of them.",
            source=f"{chosen.spec_path}:analogy")
    else:
        add("analogy",
            f"No fixture analogy: {why}",
            source="fixtures/*.fixture.yaml:analogy")

    for family, entry in (cap.get("families") or {}).items():
        nodes = entry.get("nodes_at_memory_budget")
        if isinstance(nodes, int):
            add("capacity",
                f"{family}: {entry['stored_vectors']:,} stored vectors, "
                f"{entry['memory_gb']:.1f} GB estimated, {nodes} node(s) at "
                f"the declared {entry['memory_budget_gb']} GB budget. "
                f"Arithmetic over what you declared -- {entry['basis']}.",
                source="report.json:capacity.families." + family)
        else:
            add("capacity",
                f"{family}: no capacity arithmetic. "
                f"{entry.get('amplification') if isinstance(entry.get('amplification'), str) else nodes}",
                source="report.json:capacity.families." + family)

    add("recommendation",
        "Nothing is recommended. Tier 2 has measured nothing on your corpus, "
        "and a recommendation from a description is a guess wearing a "
        "verdict's clothes.",
        source="(rule)")

    # The last entry, and the one the tier exists for.
    add("to_resolve", _what_would_make_this_measurable(constraints, names),
        source="requirements:corpus.sample")
    return lines


def _what_would_make_this_measurable(constraints, names):
    """The final log entry: what a sample buys, per constraint."""
    k = int((constraints.get("recall_at_k") or {}).get("k", 10))
    parts = [
        "To turn these into measurements, add `corpus.sample` to the "
        "requirements file:",
        f"10,000-20,000 vectors drawn stratified from the corpus turns "
        f"recall_at_k (k={k}), storage_amplification and memory_budget into "
        "measurements against exact ground truth;",
        "50 or more real queries -- logged, not invented -- turns "
        "ambiguous_query_rate into a measurement and is the floor below which "
        "it stays couldn't-check;",
        "a timestamp column on both the corpus and the queries turns drift "
        "into a measurement, and corpus timestamps alone are not enough;",
    ]
    if "latency_p95" in names or "qps" in names:
        parts.append(
            "latency_p95 and qps need more than a sample: they need a real "
            "engine in an environment where the round trip is small relative "
            "to the query, which is `oneground verify` with "
            "verify.target: runpod.")
    if "monthly_budget" in names:
        parts.append(
            "monthly_budget stays declared either way -- the price table is "
            "list prices, and the arithmetic above uses the upper bound of "
            "its error band.")
    return " ".join(parts)


def _summary_declared(report, workdir, listed, elapsed):
    d = report["declared"]
    print()
    print("=" * 78)
    print(f"report -- {report['run']}   (Tier 2: declared, no verdicts)")
    print("=" * 78)
    print(f"  declared corpus   {int(d['size_now']):,} vectors, dim "
          f"{int(d['dimension'])}")
    a = report["analogy"]
    if a["chosen"]:
        print(f"  analogy           {a['chosen']['fixture']}  "
              f"(score {a['chosen']['score']:.2f})")
        print(f"                    {a['label']}")
        for field, value in sorted(a["fixture_characterization"].items()):
            shown = (f"{value['value']}" if "value" in value
                     else f"{value.get('value_before')} -> "
                          f"{value.get('value_after')}")
            print(f"      {field:<28} {shown}")
    else:
        print("  analogy           none")
    print()
    print("  capacity (arithmetic over what you declared):")
    for family, e in report["capacity"]["families"].items():
        if isinstance(e.get("memory_gb"), float):
            nodes = e.get("nodes_at_memory_budget")
            print(f"    {family:<20} {e['stored_vectors']:>13,} stored  "
                  f"{e['memory_gb']:>7.1f} GB  "
                  f"{nodes if isinstance(nodes, int) else '-':>3} node(s)")
        else:
            print(f"    {family:<20} couldnt_check")
    print()
    print(f"  {len(report['constraints'])} constraint(s), "
          f"0 judged: every one is couldn't-check.")
    print("  Nothing is recommended.")
    print()
    print("  decision log:")
    for entry in report["decision_log"]:
        print(f"    [{entry['kind']}] {entry['text']}")
        if entry["source"]:
            print(f"        source: {entry['source']}")
    print()
    env = report.get("run_environment") or {}
    if env and not env.get("pinned", True):
        print(f"  ENVIRONMENT      {environment.UNPINNED_NOTE}: "
              + ", ".join(f"{m['package']} {m['running']} (pinned "
                          f"{m['pinned']})"
                          for m in env.get("mismatches", [])))
        print("                   every number above was judged outside "
              "requirements.txt")
        print()
    print(f"  report.json + {MANIFEST_NAME} in {workdir}")
    print(f"  ({elapsed:.1f} s)")
    print()


def _constraint_names(constraints):
    names = []
    c = constraints or {}
    if (c.get("recall_at_k") or {}).get("min") is not None:
        names.append("recall_at_k")
    if "storage_amplification_max" in c:
        names.append("storage_amplification")
    if "memory_budget_gb" in c:
        names.append("memory_budget")
    if (c.get("latency") or {}).get("p95_ms") is not None:
        names.append("latency_p95")
    if (c.get("latency") or {}).get("at_qps") is not None:
        names.append("qps")
    if c.get("monthly_budget"):
        names.append("monthly_budget")
    return names


def _judged_constraint_names(options, constraints):
    """The constraints actually judged, in the order the verdicts carry them.

    Read off the verdicts rather than off the requirements, because those are
    two different questions and only this one describes what the report did.
    `_constraint_names` is a list of `if` branches that has to be extended by
    hand whenever a verdict is added, and in task 011 it was not: `qps_target`
    shipped, every option carried a `qps` verdict, and the scope line went on
    saying "4 constraint(s)" and omitting it.

    Falls back to the declared list when there are no options at all -- with
    nothing judged there is nothing to read, and the requirements are then the
    only honest source.
    """
    seen = []
    for opt in options or []:
        for v in opt.verdicts:
            if v.constraint not in seen:
                seen.append(v.constraint)
    return seen or _constraint_names(constraints)


# Keys in `runtime_settings` that are bookkeeping about the record rather than
# a setting the engine is running under. A block carrying only these has told
# us nothing about the configuration.
_SETTINGS_BOOKKEEPING = frozenset({
    "source", "backfilled_by", "why_not_read_back", "note", "tuning",
    "index_build_note", "couldnt_check",
})


def _recorded_settings(rs):
    """The actual settings in a runtime_settings block."""
    return {k: v for k, v in (rs or {}).items()
            if k not in _SETTINGS_BOOKKEEPING}


def _tuning_note(verify_info, engines):
    """One sentence on how the engines were configured.

    Reads `engine_facts.runtime_settings.tuning` where an adapter or a
    backfill recorded it, and says so plainly when nothing did -- an absent
    tuning note must not read as "defaults confirmed".
    """
    blocks = {b.get("engine"): b for b in ((verify_info or {}).get("engines")
                                           or [])}
    notes, declared_none, unknown = [], [], []
    for name in engines:
        rs = ((blocks.get(name) or {}).get("engine_facts") or {}).get(
            "runtime_settings") or {}
        t = rs.get("tuning")
        if not _recorded_settings(rs) and not t and rs.get("couldnt_check"):
            # The engine SAID it has none, or said why it could not be read.
            # That is a different answer from silence, and reporting it as
            # "not recorded in this run" would lose the reason the engine
            # gave -- which is the whole content of a couldn't-check.
            declared_none.append(f"{name}: {rs['couldnt_check']}")
        elif t:
            # A prose summary, which is what task 015's backfill wrote.
            notes.append(f"{name}: {t.split('.')[0].strip().lower()}")
        elif _recorded_settings(rs):
            # Task 017f: the settings THEMSELVES. This branch did not exist,
            # so the note read `runtime_settings["tuning"]` -- a key only the
            # 015 backfill script ever wrote -- and every live run therefore
            # reported "not recorded" while verify_info.json carried the full
            # settings for both engines. The feature worked exactly once, on
            # backfilled data, and never on a measurement.
            kept = _recorded_settings(rs)
            shown = ", ".join(sorted(kept)[:3])
            build = rs.get("index_build")
            notes.append(
                f"{name}: {len(kept)} settings read from the engine"
                + (f", index build {build}" if build else "")
                + f" ({shown}{', ...' if len(kept) > 3 else ''})")
        else:
            unknown.append(name)
    parts = []
    if notes:
        # NOT "both ran on engine defaults": reading settings back tells you
        # what they WERE, not that they were the vendor's defaults, and this
        # sentence used to assert the second from the first. What is true is
        # that the configuration is on the record and a reader can check it.
        parts.append("How each was configured is on the record -- "
                     + "; ".join(notes)
                     + " -- so this compares these two deployments as they "
                       "were configured; a differently tuned row for either "
                       "engine would be a different measurement")
    if declared_none:
        parts.append("; ".join(declared_none))
    if unknown:
        parts.append(f"how {', '.join(unknown)} was configured is not "
                     f"recorded in this run, so it is couldnt_check rather "
                     f"than assumed to be default")
    return (". ".join(parts) + ".") if parts else ""


def compare_engines(options, env_id, verify_info=None):
    """The comparison entries, as `{kind, text, source}`.

    The shape the decision log and its readers already speak; the sentences
    come from `compare_engine_claims`.
    """
    return [c.as_entry()
            for c in compare_engine_claims(options, env_id, verify_info)]


def compare_engine_claims(options, env_id, verify_info=None):
    """Which engine met a constraint at a better number, as `Claim`s.

    This is the comparison task 015 exists to make possible, and it is
    deliberately narrow. It fires only when:

      * the same simulated configuration was verified on more than one
        engine -- the same-configuration rule from task 011, so the two rows
        describe the same architecture rather than two different indexes;
      * both rows come from the same `environment_id` -- the same-environment
        rule from task 011, so the numbers are comparable at all;
      * both engines produced an actual value for the constraint, not a
        `couldnt_check`.

    Anything else produces a claim saying why no comparison was made, rather
    than silence. A missing comparison and an unfavourable one look identical
    if only the favourable ones are printed.

    **This function is where `{best.outcome}` lived.** It ended "and both
    carry {best.outcome} against the constraint", which takes the WINNER's
    verdict and asserts it of everyone, so a comparison where qdrant met the
    constraint and pgvector missed it read "both carry meets". It shipped in
    task 015's report about a pgvector row that sustained 112.63 of an offered
    200 -- a fail -- and would have said it again in 017e at 119.10. The
    ranking was right both times; the sentence was wrong, and the sentence is
    what gets read. Task 019 makes the quantifier a field rather than a turn
    of phrase, so `check()` can refuse it.
    """
    out = []
    for opt in options:
        scoped = [v for v in opt.verdicts if v.engine is not None]
        if len({v.engine for v in scoped}) < 2:
            continue
        for constraint in dict.fromkeys(v.constraint for v in scoped):
            group = [v for v in scoped if v.constraint == constraint]
            usable = [v for v in group
                      if v.outcome != COULDNT_CHECK and v.value is not None]
            if len(usable) < 2:
                c = cl.Claim(
                    kind="no_engine_comparison",
                    predicate="was not compared across engines",
                    # A denial: it says a comparison was NOT made. Checking it
                    # as the assertion it contains is the 017f mistake.
                    quantifier=cl.NEGATION,
                    subject=opt.config, constraint=constraint,
                    scope=tuple(v.engine for v in group),
                    holds_for=(),
                    cites=tuple(cl.Cite(member=v.engine, value=v.value,
                                        outcome=v.outcome,
                                        constraint=constraint,
                                        source=v.source, reason=v.reason)
                                for v in group),
                    source="verify.json:engines[*]")
                cl.render(c)
                out.append(c)
                continue
            lower_is_better = constraint in ("latency_p95",)
            best = (min(usable, key=lambda v: float(v.value))
                    if lower_is_better
                    else max(usable, key=lambda v: float(v.value)))
            outcomes = {v.outcome for v in usable}
            # The quantifier is decided from the ROWS, never from the winner.
            # When every engine carries the same outcome the sentence may say
            # so universally; otherwise it is existential -- one engine is
            # better -- and the renderer prints the denial.
            uniform = len(outcomes) == 1
            c = cl.Claim(
                kind="engine_comparison",
                predicate=("carry the same outcome against the constraint"
                           if uniform else "is the better of the engines"),
                quantifier=cl.UNIVERSAL if uniform else cl.EXISTENTIAL,
                subject=opt.config, constraint=constraint,
                scope=tuple(v.engine for v in usable),
                holds_for=(tuple(v.engine for v in usable) if uniform
                           else (best.engine,)),
                cites=tuple(cl.Cite(member=v.engine, value=v.value,
                                    outcome=v.outcome, constraint=constraint,
                                    source=v.source, reason=v.reason)
                            for v in usable),
                environment=env_id,
                source="verify.json:engines[*]",
                # Naming the tuning is not a courtesy. "qdrant beats pgvector"
                # read without it is a claim about the engines; what was
                # measured is a claim about two default deployments, and the
                # gap between those sentences is most of what a reader would
                # do next.
                detail=_tuning_note(verify_info, [v.engine for v in usable]),
                extra={"best": best.engine})
            cl.render(c)
            out.append(c)
        if opt.engines_meeting:
            c = cl.Claim(
                kind="engines_meeting",
                predicate="meets every engine-scoped constraint",
                # Existential over the engines: it holds on these and not the
                # others, and the sentence says which.
                quantifier=cl.EXISTENTIAL,
                subject=opt.config,
                scope=tuple(dict.fromkeys(
                    v.engine for v in opt.verdicts if v.engine is not None)),
                holds_for=tuple(opt.engines_meeting),
                asserts_outcome=vd.MEETS, holds_rule="no_fails",
                cites=tuple(
                    cl.Cite(member=e, outcome=vd.MEETS,
                            source="report.json:options[*].judgement."
                                   "engines_meeting")
                    for e in dict.fromkeys(
                        v.engine for v in opt.verdicts
                        if v.engine is not None)),
                source="report.json:options[*].judgement.engines_meeting",
                extra={"engine_scoped_constraints": tuple(dict.fromkeys(
                    v.constraint for v in opt.verdicts
                    if v.engine is not None))})
            cl.render(c)
            out.append(c)
    return out


def _calibration_footer(verify_info, recommended, history_path=None):
    """What this report's numbers were last calibrated against.

    Every report cites the calibration run it was generated under. Two
    citations, because two different things were measured:

        engine  the most recent `simulator_vs_engine` line for the engine this
                run verified against -- how far this installation's simulator
                sat from a real engine, last time anyone checked
        family  the most recent `glove_curve` line for the recommended
                family -- how far it sat from someone else's published numbers

    Either can be absent, and absence is stated, never omitted. A report that
    silently prints no calibration reads as a report that needs none.
    """
    from ..calibrate import history as H

    path = history_path or H.DEFAULT_PATH
    # verify_info holds a list of engines from task 015; the pre-015 shape
    # had one at the top level. Every engine verified in the run is cited,
    # because a report that names one of two engines is worse than one that
    # names neither -- the reader cannot tell which half is missing.
    info_engines = [b.get("engine")
                    for b in ((verify_info or {}).get("engines") or [])
                    if isinstance(b, dict) and b.get("engine")]
    if not info_engines and (verify_info or {}).get("engine"):
        info_engines = [(verify_info or {}).get("engine")]
    engine = info_engines[0] if info_engines else None
    family = None
    if recommended is not None:
        family = str(getattr(recommended, "config", "")).split("[")[0] or None

    out = {
        "tolerance": vd.CALIBRATION_TOLERANCE,
        "note": ("two options whose recall differs by less than the tolerance "
                 "are reported as indistinguishable on recall"),
        "history_path": path,
        "engine": engine,
        "family": family,
        "engine_line": None,
        "family_line": None,
        "statements": [],
    }

    try:
        lines = H.read(path)
    except (OSError, ValueError) as e:
        out["statements"].append(
            f"calibration history at {path} could not be read: {e}")
        return out

    if not lines:
        out["statements"].append(
            f"no calibration history at {path}: nothing has been calibrated "
            f"on this installation")
        return out

    if info_engines:
        out["engines"] = list(info_engines)
        out["engine_lines"] = {}
        for name in info_engines:
            ln = H.latest_for_engine(name, lines)
            out["engine_lines"][name] = ln
            if ln is None:
                out["statements"].append(f"no calibration line for {name}")
            else:
                out["statements"].append(_cite(ln, f"engine {name}"))
        out["engine_line"] = out["engine_lines"].get(engine)
    else:
        out["statements"].append(
            "no engine was verified in this run, so there is no engine "
            "calibration to cite")

    if family:
        hits = [ln for ln in lines
                if ln.get("check") == "glove_curve"
                and str(ln.get("config", "")).startswith(family)
                and ln.get("outcome_scope", H.BLOCKING) == H.BLOCKING]
        out["family_line"] = hits[-1] if hits else None
        if not hits:
            out["statements"].append(f"no calibration line for {family}")
        else:
            out["statements"].append(_cite(hits[-1], f"family {family}"))
    return out


def _cite(line, what):
    """One sentence naming the line, its outcome and the numbers behind it."""
    dev, tol = line.get("deviation"), line.get("tolerance")
    outcome = line.get("outcome", "?")
    scope = ("" if line.get("outcome_scope", "blocking") == "blocking"
             else " [advisory]")
    if dev is None:
        detail = "no reference to compare against"
    else:
        band = "no declared tolerance" if tol is None else f"tolerance {tol}"
        detail = f"deviation {dev:+.5f} against {band}"
    return (f"{what}: last calibrated {line.get('date')} on "
            f"{line.get('dataset')} as {line.get('config')} -- {outcome}, "
            f"{detail}{scope}")


def _how_to_resolve(name, v, verify_info):
    """See `claims.how_to_resolve`."""
    return cl.how_to_resolve(name, v, verify_info)


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------

def build_manifest(recommended, workdir, req, verify_data, verify_info,
                   inputs, env_stamp=None):
    """The recommended configuration in deployable form, with its receipts.

    Every input digest is included so the manifest states what it was derived
    from. A manifest that names a configuration without naming the
    measurements behind it is a recommendation with the evidence detached,
    which is the thing this project exists to replace.
    """
    if recommended is None:
        return {
            "oneground_manifest": 1,
            "run": req.name,
            "recommended": None,
            "reason": ("no option met every constraint; nothing is "
                       "recommended"),
            "inputs": inputs,
        }
    engine = None
    if verify_data:
        engine = {
            "name": verify_data.get("engine"),
            "version": verify_data.get("engine_version"),
            "kind": "declared",
            "verified": True,
            "params": (verify_info or {}).get("engine_params"),
            "image": (verify_info or {}).get("compose_image"),
            "note": ("this configuration was measured against a real engine; "
                     "the engine's own reported facts are declared"),
        }
    return {
        "oneground_manifest": 1,
        "run": req.name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Which interpreter produced this report, and whether it was
        # running the pins. A reader who finds `pinned: false` knows the
        # numbers were judged outside requirements.txt.
        # `run_environment`, not `environment`: the Tier-1 report already
        # uses that key for the verify target's environment, and one of the
        # two would silently win the dict literal. This one is the
        # interpreter that produced the report.
        "run_environment": env_stamp or environment.stamp(),
        # And which oneground judged them (task 033): the stamp above
        # says which interpreter and pins, and said nothing about the
        # code that read the rows.
        "oneground": producing_version(),
        "recommended": {
            "family": recommended.family,
            "config": recommended.config,
            "params": dict(recommended.params),
            "measured": {
                "recall_at_10": recommended.measurement.get("recall_at_10"),
                "ceiling_at_10": recommended.measurement.get("ceiling_at_10"),
                "storage_amplification":
                    recommended.measurement.get("storage_amplification"),
                "fanout": recommended.measurement.get("fanout"),
                "est_memory_bytes":
                    recommended.measurement.get("est_memory_bytes"),
            },
            "outcome": recommended.outcome,
            "constraints": [v.as_dict() for v in recommended.verdicts],
        },
        "engine": engine,
        "inputs": inputs,
        "note": ("`inputs` lists every file this recommendation was derived "
                 "from, with its sha256. Re-deriving the recommendation means "
                 "re-running the commands that wrote them."),
    }


def _input_digests(workdir):
    out = {}
    for name in INPUT_FILES + [MANIFEST_NAME]:
        p = os.path.join(workdir, name)
        if os.path.exists(p):
            out[name] = {"sha256": sha256_file(p),
                         "kind": _kind_of(name, workdir)}
    return out


def _kind_of(name, workdir):
    """receipt or declared, read from the writer's own `kind` map where it
    recorded one rather than assumed here."""
    if name.endswith("_info.json") or name == "build_info.json":
        return "declared"
    if name == MANIFEST_NAME:
        return "receipt"
    for info_name in ("simulate_info.json", "verify_info.json",
                      "build_info.json"):
        info = _load(workdir, info_name)
        kinds = (info or {}).get("kind") or {}
        if name in kinds:
            return kinds[name]
    return "receipt"


# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------

def qps_max_lines(verify_data):
    """Decision-log entries for the measured ceiling. Task 017 item 5.

    A separate row on purpose. `qps` is a sustain check -- did the engine hold
    the rate it was offered -- and `qps_max` is a ceiling found by removing the
    throttle and ramping until the engine degrades. They are different
    questions, and the reason `qps_max` went unimplemented until now is that
    the cheap way to produce one is to read the achieved rate off a throttled
    run, which reports the offer back as if it were the capacity.

    So this is never a verdict: there is no `qps_max` constraint, nothing is
    judged against it, and `latency_p95`/`qps` never read it.
    """
    return [c.as_entry() for c in qps_max_claims(verify_data)]


def qps_max_claims(verify_data):
    """The ceiling, as claims. Never a verdict, so it quantifies over nothing.

    One engine, one number, one host. There is no set here and therefore no
    quantifier: `qps_max` is a measurement of the engine in front of it, and
    the caveat that travels with it says so in the row rather than relying on
    a reader having read this docstring.
    """
    out = []
    for engine, block in vd.engine_blocks(verify_data):
        ceiling = (block or {}).get("qps_max")
        if not isinstance(ceiling, dict) or ceiling.get("qps_max") is None:
            continue
        c = cl.Claim(
            kind="qps_max", predicate="sustained this rate before degrading",
            quantifier=cl.NONE, constraint="qps_max",
            scope=((engine,) if engine else ()),
            holds_for=((engine,) if engine else ()),
            cites=(cl.Cite(member=engine, value=ceiling["qps_max"],
                           constraint="qps_max",
                           source="verify.json:qps_max"),),
            source="verify.json:qps_max",
            detail=ceiling.get("caveat", ""),
            extra={"concurrency": ceiling["at_concurrency"],
                   "p99": ceiling.get("p99_ms_at_max"),
                   "stopped": ceiling["stopped_because"],
                   # The stop reason quotes its own p99 numbers, which the
                   # claim does not cite as values of its own.
                   "literal_numbers": tuple(
                       re.findall(r"\d+\.\d{2}",
                                  str(ceiling["stopped_because"])))})
        cl.render(c)
        out.append(c)
    return out


def _prices_postdate_the_run(prices, verify_info):
    """Why this price table may not price this run, or None. Task 017 item 6.

    A declared price table carries an `as_of` date. When that date is later
    than the run being reported, the cost estimate is quoting prices that did
    not exist when the numbers were taken -- which happens the ordinary way,
    by refreshing `prices.yaml` and re-running `report` over an older
    `verify.json`. The arithmetic is unchanged and the output looks current,
    so nothing about the report says the two came from different weeks.

    Compared against the verify run's `run_at`, because that is when the
    measurements this is pricing were made. With no verify run there is
    nothing to postdate, and `unknown`/malformed dates are couldn't-check
    rather than grounds for rejection.
    """
    as_of = str(getattr(prices, "as_of", "") or "")[:10]
    run_at = str((verify_info or {}).get("run_at") or "")[:10]
    if not as_of or not run_at:
        return None
    try:
        time.strptime(as_of, "%Y-%m-%d")
        time.strptime(run_at, "%Y-%m-%d")
    except ValueError:
        return None
    if as_of <= run_at:                      # ISO dates compare as strings
        return None
    return (f"the price table is dated {as_of}, after the verify run it would "
            f"price ({run_at}). Prices declared after a measurement cannot be "
            "what that measurement cost, so the cost rows and the "
            "monthly_budget verdict are dropped rather than quoted as if the "
            "two were contemporaneous. Re-run verify, or price it with a "
            "table `as_of` the run.")


def run(requirements_path, log_fn=log, env_stamp=None):
    t0 = time.time()
    req = intake.load(requirements_path)
    workdir = req.resolve(req.workdir)

    if req.tier == 2:
        return run_declared(req, requirements_path, workdir, t0, log_fn,
                            env_stamp=env_stamp)

    sim = _load(workdir, "simulate.json")
    if sim is None:
        raise ReportError(
            f"no simulate.json in {workdir}. `report` judges the sweep's "
            "rows against your constraints; run this first:\n\n"
            f"    oneground simulate {requirements_path}\n")

    char = _load(workdir, "characterization.json")
    sim_info = _load(workdir, "simulate_info.json")
    verify_data = _load(workdir, "verify.json")
    verify_info = _load(workdir, "verify_info.json")
    constraints = req.data.get("constraints") or {}
    if not constraints:
        raise ReportError(
            f"{requirements_path}: no `constraints` block. A report is a "
            "comparison of measurements against constraints; without them "
            "there is nothing to judge and `simulate` already printed the "
            "measurements.")

    env = _environment_of(verify_info)
    env_id = (verify_data or {}).get("environment_id")
    k = int((constraints.get("recall_at_k") or {}).get("k", 10))

    # ---- cost model ----
    cost_cfg = (req.data.get("verify") or {}).get("cost") or {}
    costs, prices = costmod.cost_for_options(sim.get("rows", []), cost_cfg,
                                             constraints)
    if isinstance(prices, str):          # a load failure, reported not raised
        log_fn(f"cost: {prices}")
        costs, prices = {}, None
    # Same idiom for a table that postdates the run: reported, not raised, and
    # the costs go rather than being quoted out of their period.
    price_note = _prices_postdate_the_run(prices, verify_info)
    if price_note:
        log_fn(f"cost: {price_note}")
        costs, prices = {}, None
    log_fn(f"report '{req.name}': {len(sim.get('rows', []))} rows, "
           f"{len(_constraint_names(constraints))} constraints"
           + (f", verify on {env}" if env else ", no verify run"))

    # What each engine can build (task 034), so that a couldn't-check on a
    # constraint only an engine can settle says which kind it is: a run that
    # has not happened, or a configuration no engine here could run at all.
    coverages = vd.coverages_from(verify_data, workdir)
    options = [vd.judge_option(row, verify_data, constraints, env,
                              costs=costs, verify_info=verify_info,
                              coverages=coverages)
               for row in sim.get("rows", [])]
    vd.mark_indistinguishable(options, k=k)

    requested = list((req.data.get("simulate") or {}).get("families") or [])
    not_run_rows = vd.not_run(requested, options,
                              (sim_info or {}).get("dropped"))

    recommended = vd.recommend(options, k=k)
    claims = decision_claims(options, not_run_rows, recommended, constraints,
                             verify_info, k=k, env_id=env_id)
    # Appended rather than built inside `decision_claims`, which is given the
    # judged options and not the raw verify document. The ceiling is not a
    # judgement of any option -- it is a property of the engine on this host.
    claims.extend(qps_max_claims(verify_data))

    # The invariant, on the way out. Task 019: every claim is checked against
    # the rows it cites BEFORE the report is written, so a sentence that does
    # not follow from its own rows cannot reach a file. This is the same move
    # as refusing to write a fixture whose digests do not match -- the report
    # is a receipt for the prose, and a receipt that is not checked is a
    # decoration.
    cl.raise_on_violation(claims, cl.rows_from_options(options),
                          where="report %s" % getattr(req, "name", "run"))
    dlog = [c.as_entry() for c in claims]

    inputs = _input_digests(workdir)
    counts = {o: sum(1 for x in options if x.outcome == o)
              for o in vd.OUTCOMES}

    report = {
        "run": req.name,
        "schema": intake.SCHEMA_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Which interpreter produced this report, and whether it was
        # running the pins. A reader who finds `pinned: false` knows the
        # numbers were judged outside requirements.txt.
        # `run_environment`, not `environment`: the Tier-1 report already
        # uses that key for the verify target's environment, and one of the
        # two would silently win the dict literal. This one is the
        # interpreter that produced the report.
        "run_environment": env_stamp or environment.stamp(),
        # And which oneground judged them (task 033): the stamp above
        # says which interpreter and pins, and said nothing about the
        # code that read the rows.
        "oneground": producing_version(),
        "constraints": constraints,
        "environment": {"verify_target": env,
                        "environment_id": env_id,
                        "verify_platform": (verify_info or {}).get("platform"),
                        "note": ("latency and throughput verdicts are only "
                                 "made from a verify run in the environment "
                                 "the constraint targets. environment_id is "
                                 "the pod id for a matched-environment run; "
                                 "rows from different environments are never "
                                 "compared.")},
        "costs": costs,
        # Task 043 step 5. Sanitised HERE, where the field is written, rather
        # than at each of the three boundaries that had to sanitise it on the
        # way out. A receipt that never contains the absolute path has nothing
        # to sanitise anywhere.
        "price_table": (public_paths_in(prices.as_dict()) if prices is not None
                        and not isinstance(prices, str) else None),
        # Present only when a table was rejected. A reader who finds no costs
        # and no price_table would otherwise have to guess whether none were
        # configured or one was refused.
        "price_table_rejected": price_note,
        "calibration": _calibration_footer(verify_info, recommended),
        "summary": {"options": len(options), **counts,
                    "not_run": len(not_run_rows)},
        "options": [o.as_dict() for o in options],
        "not_run": not_run_rows,
        "recommendation": (recommended.config if recommended else None),
        "decision_log": dlog,
        # The structured form of every sentence above. `decision_log` is what
        # a reader reads; this is what a checker checks, and what makes the
        # rendered surfaces reconstructible from the record alone.
        "claims": [c.as_dict() for c in claims],
        "inputs": inputs,
    }
    write_json_stable(os.path.join(workdir, "report.json"),
                      round_floats(report))

    manifest = build_manifest(recommended, workdir, req, verify_data,
                              verify_info, inputs, env_stamp=env_stamp)
    _write_yaml(os.path.join(workdir, "manifest.yaml"), manifest)

    html = render_html(report, options, not_run_rows, recommended, char,
                       verify_data, verify_info, req, workdir=workdir)
    with open(os.path.join(workdir, "report.html"), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(html)

    _summary(report, options, not_run_rows, recommended, workdir,
             time.time() - t0)
    return workdir


def _write_yaml(path, obj):
    import yaml
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# oneground deployable manifest.\n"
                "# The recommended configuration, and the digest of every\n"
                "# measurement it was derived from.\n")
        yaml.safe_dump(round_floats(obj), f, sort_keys=False,
                       default_flow_style=False, allow_unicode=False)


def _summary(report, options, not_run_rows, recommended, workdir, elapsed):
    s = report["summary"]
    print()
    print("=" * 96)
    print(f"report -- {report['run']}")
    print("=" * 96)
    print(f"  {s['options']} option(s): {s[vd.MEETS]} meets, "
          f"{s[vd.FAILS]} fails, {s[vd.COULDNT_CHECK]} couldnt_check"
          + (f"; {s['not_run']} family(ies) not run" if s["not_run"] else ""))
    print()
    hdr = f"  {'configuration':<56} {'outcome':<14} constraints"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for o in options:
        # Composed in the renderer: a console row asserts what a sentence
        # does, and 017e's defect was in a cell rather than in prose.
        row = cl.option_row(o)
        print(f"  {row['config']:<56} {row['outcome']:<14} {row['bits']}")
        if row["engines_meeting"]:
            names = ", ".join(row["engines_meeting"])
            print(f"  {'':<56} {'':<14} "
                  f"-> meets every engine-scoped constraint on: {names}")
    for r in not_run_rows:
        print(f"  {r['family']:<56} {'not_run':<14} {r['reason'][:60]}")
    print()
    if recommended is None:
        print("  No option meets every constraint, so nothing is recommended.")
    else:
        print(f"  Recommended: {recommended.config}")
        for line in runner_up_lines(recommended, options):
            print(line)
    print()
    print("  decision log:")
    for entry in report["decision_log"]:
        text = entry["text"]
        print(f"    [{entry['kind']}] {text}")
        if entry["source"]:
            print(f"        source: {entry['source']}")
    print()
    print("  calibration:")
    for line in report["calibration"]["statements"]:
        print(f"    {line}")
    print()
    env = report.get("run_environment") or {}
    if env and not env.get("pinned", True):
        print(f"  ENVIRONMENT      {environment.UNPINNED_NOTE}: "
              + ", ".join(f"{m['package']} {m['running']} (pinned "
                          f"{m['pinned']})"
                          for m in env.get("mismatches", [])))
        print("                   every verdict above was judged outside "
              "requirements.txt")
        print()
    print(f"  report.json + manifest.yaml + report.html in {workdir}")
    print(f"  ({elapsed:.1f} s)")
    print()
