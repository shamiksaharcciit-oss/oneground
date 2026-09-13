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
import time

import yaml

from .. import analogy
from .. import capacity
from .. import cost as costmod
from .. import environment
from .. import intake
from ..receipts import (MANIFEST_NAME, library_versions, round_floats,
                        sha256_file, write_json_stable, write_manifest)
from . import verdict as vd
from .html import render_html

COULDNT_CHECK = vd.COULDNT_CHECK

INPUT_FILES = ["characterization.json", "build_info.json", "sample_ids.json",
               "queries_ids.json", "simulate.json", "simulate_info.json",
               "verify.json", "verify_info.json"]

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
    """An ordered list of sentences, each one a rule firing.

    Every entry names the constraint, the value, the threshold and the source
    file and field, so the log can be checked against the workdir line by
    line. The final entries say what would turn each couldn't-check into a
    verdict -- a log that only records what was decided is half a log.
    """
    lines = []

    def add(kind, text, source=""):
        lines.append({"kind": kind, "text": text, "source": source})

    n = len(options)
    judged = _judged_constraint_names(options, constraints)
    add("scope",
        f"{n} configuration(s) were measured and judged against "
        f"{len(judged)} constraint(s): "
        f"{', '.join(judged) or 'none'}.",
        source="requirements:constraints")

    for row in not_run_rows:
        add("not_run",
            f"{row['family']} was requested but produced no rows, so it is "
            f"not judged: {row['reason']}",
            source="simulate_info.json:dropped")

    for opt in options:
        for v in opt.verdicts:
            if v.outcome == vd.FAILS:
                where = (f" Measured in environment {env_id}."
                         if env_id and v.constraint in ("latency_p95", "qps")
                         else "")
                # With two engines an unqualified "fails latency_p95" appears
                # twice with different numbers and no way to tell them apart.
                on = f" on {v.engine}" if v.engine else ""
                add("fails",
                    f"{opt.config} fails {v.constraint}{on}: "
                    f"{v.reason}.{where}",
                    source=v.source)

    # Latency and throughput verdicts name the environment they came from,
    # whichever way they went: a p95 is a fact about a machine, and a reader
    # who cannot see which machine cannot use it.
    for opt in options:
        for v in opt.verdicts:
            if v.constraint in ("latency_p95", "qps") and v.outcome == vd.MEETS:
                on = f" on {v.engine}" if v.engine else ""
                add("meets_environment",
                    f"{opt.config} meets {v.constraint}{on} in environment "
                    f"{env_id or 'unrecorded'}: {v.reason}.",
                    source=v.source)

    for opt in options:
        if opt.outcome == vd.MEETS:
            add("meets",
                f"{opt.config} meets every constraint that could be checked: "
                + "; ".join(f"{v.constraint} {v.reason}"
                            for v in opt.verdicts if v.outcome == vd.MEETS)
                + ".",
                source=f"simulate.json:rows[{opt.config}]")

    # indistinguishability, stated once per group rather than per pair
    seen = set()
    for opt in options:
        if not opt.indistinguishable_from:
            continue
        group = tuple(sorted([opt.config] + opt.indistinguishable_from))
        if group in seen:
            continue
        seen.add(group)
        vals = []
        for cfg in group:
            for o in options:
                if o.config == cfg:
                    vals.append(f"{cfg} {o.measurement.get(f'recall_at_{k}'):.4f}")
        add("indistinguishable",
            "These options are indistinguishable on recall: "
            + "; ".join(vals)
            + f". Their recall differs by less than the calibration tolerance "
              f"({tolerance}), which is what this project can currently "
              "defend, so choosing between them on recall would be reading "
              "noise. They are separated only where they differ measurably. "
            + "Overall: "
            + "; ".join(f"{cfg} {o.outcome}" for cfg in group
                        for o in options if o.config == cfg)
            + " -- indistinguishable on recall is not indistinguishable "
              "overall.",
            source=f"simulate.json:rows[*].recall_at_{k}")

    # Two engines, one environment, one configuration: the comparison the
    # same-environment and same-configuration rules exist to make safe.
    for entry in compare_engines(options, env_id, verify_info):
        add(entry["kind"], entry["text"], source=entry["source"])

    if recommended is None:
        add("recommendation",
            "No option meets every constraint, so nothing is recommended. "
            "Recommending an option whose constraints could not all be "
            "checked would be rounding couldn't-check up to a verdict.",
            source="(rule)")
    else:
        margins = [v.constraint for v in recommended.verdicts
                   if vd.at_margin(v)]
        add("recommendation",
            f"Recommended: {recommended.config}. It meets every constraint "
            f"that could be checked, and was ranked first by: fewest "
            f"constraints at margin ({len(margins)}"
            + (f": {', '.join(margins)}" if margins else "")
            + f"), then lowest storage amplification "
              f"({recommended.measurement.get('storage_amplification'):.2f}x), "
              f"then lowest fan-out "
              f"({recommended.measurement.get('fanout'):.0f}).",
            source=f"simulate.json:rows[{recommended.config}]")

    # What would turn each couldn't-check into a verdict.
    unresolved = {}
    for opt in options:
        for v in opt.verdicts:
            if v.outcome == COULDNT_CHECK:
                unresolved.setdefault(v.constraint, v)
    for name, v in sorted(unresolved.items()):
        add("to_resolve", _how_to_resolve(name, v, verify_info),
            source=v.source)

    if not unresolved:
        add("to_resolve",
            "Every constraint was decidable from this workdir; nothing is "
            "outstanding.", source="(rule)")
    return lines


def runner_up_lines(recommended, options):
    """The "indistinguishable on recall from ..." line, with what it costs.

    Naming an alternative beside a recommendation reads as an endorsement, so
    the line has to say what the alternative's overall outcome is. On the
    arxiv-150k report the runner-up is `couldnt_check`: it was not the
    configuration the engine was built as, so its latency and throughput were
    never measured. "indistinguishable on recall from hash_sharded[...]" alone
    invited a reader to treat it as an equally supported choice.

    Recall really is indistinguishable -- that part of the claim stands. What
    was missing is everything the comparison does not cover.
    """
    if not recommended or not recommended.indistinguishable_from:
        return []
    by_config = {o.config: o for o in options or []}
    out = ["    indistinguishable on recall from: "
           + ", ".join(recommended.indistinguishable_from)]
    for cfg in recommended.indistinguishable_from:
        opt = by_config.get(cfg)
        if opt is None:
            continue
        if opt.outcome == vd.MEETS:
            out.append(f"      {cfg}: meets every constraint that could be "
                       "checked")
            continue
        unchecked = [v.constraint for v in opt.verdicts
                     if v.outcome == vd.COULDNT_CHECK]
        failed = [v.constraint for v in opt.verdicts if v.outcome == vd.FAILS]
        bits = []
        if failed:
            bits.append("fails " + ", ".join(failed))
        if unchecked:
            bits.append("could not be checked on " + ", ".join(unchecked))
        out.append(f"      {cfg}: {opt.outcome}"
                   + (" -- " + "; ".join(bits) if bits else "")
                   + ". Indistinguishable on recall is not "
                     "indistinguishable overall.")
    return out


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


def _tuning_note(verify_info, engines):
    """One sentence on how the engines were configured.

    Reads `engine_facts.runtime_settings.tuning` where an adapter or a
    backfill recorded it, and says so plainly when nothing did -- an absent
    tuning note must not read as "defaults confirmed".
    """
    blocks = {b.get("engine"): b for b in ((verify_info or {}).get("engines")
                                           or [])}
    notes, unknown = [], []
    for name in engines:
        rs = ((blocks.get(name) or {}).get("engine_facts") or {}).get(
            "runtime_settings") or {}
        t = rs.get("tuning")
        if t:
            notes.append(f"{name}: {t.split('.')[0].strip().lower()}")
        else:
            unknown.append(name)
    parts = []
    if notes:
        parts.append("Both ran on engine defaults except where the receipt "
                     "says otherwise -- " + "; ".join(notes)
                     + " -- so this compares two default deployments, not "
                       "two tuned ones, and a tuned row for either engine "
                       "would be a different measurement")
    if unknown:
        parts.append(f"how {', '.join(unknown)} was configured is not "
                     f"recorded in this run, so it is couldnt_check rather "
                     f"than assumed to be default")
    return (". ".join(parts) + ".") if parts else ""


def compare_engines(options, env_id, verify_info=None):
    """Which engine met a constraint at a better number, where two were
    measured on the same configuration in the same environment.

    This is the comparison task 015 exists to make possible, and it is
    deliberately narrow. It fires only when:

      * the same simulated configuration was verified on more than one
        engine -- the same-configuration rule from task 011, so the two rows
        describe the same architecture rather than two different indexes;
      * both rows come from the same `environment_id` -- the same-environment
        rule from task 011, so the numbers are comparable at all;
      * both engines produced an actual value for the constraint, not a
        `couldnt_check`.

    Anything else produces a sentence saying why no comparison was made,
    rather than silence. A missing comparison and an unfavourable one look
    identical if only the favourable ones are printed.
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
                unchecked = [f"{v.engine} ({v.outcome})" for v in group]
                out.append({
                    "kind": "no_engine_comparison",
                    "text": (
                        f"{opt.config}: {constraint} was not compared across "
                        f"engines because fewer than two engines produced a "
                        f"value -- {', '.join(unchecked)}. A comparison here "
                        f"would be between a number and an absence"),
                    "source": "verify.json:engines[*]"})
                continue
            lower_is_better = constraint in ("latency_p95",)
            best = (min(usable, key=lambda v: float(v.value))
                    if lower_is_better
                    else max(usable, key=lambda v: float(v.value)))
            # Each engine's OWN outcome, next to its own number.
            #
            # This used to end "and both carry {best.outcome} against the
            # constraint", which takes the WINNER's verdict and asserts it of
            # everyone. So a comparison where qdrant met the constraint and
            # pgvector missed it read "both carry meets". It shipped in task
            # 015's report saying that about a pgvector row which sustained
            # 112.63 of an offered 200 -- a fail -- and would have said it
            # again in 017e at 119.10. The ranking was right both times; the
            # sentence describing it was wrong, and the sentence is what gets
            # read.
            others = "; ".join(
                f"{v.engine} {float(v.value):.2f} ({v.outcome})"
                for v in usable if v is not best)
            outcomes = {v.outcome for v in usable}
            verdicts = (
                f"All {len(usable)} carry {best.outcome} against the "
                "constraint." if len(outcomes) == 1 else
                "They do not all carry the same verdict -- a better number "
                "here is not the same as a passing one.")
            # Naming the tuning is not a courtesy. "qdrant beats pgvector"
            # read without it is a claim about the engines; what was measured
            # is a claim about two default deployments, and the gap between
            # those two sentences is most of what a reader would do next.
            tuning = _tuning_note(verify_info, [v.engine for v in usable])
            out.append({
                "kind": "engine_comparison",
                "text": (
                    f"{opt.config}: on {constraint}, {best.engine} is the "
                    f"better of {len(usable)} engines measured in environment "
                    f"{env_id or 'unrecorded'} -- {best.engine} "
                    f"{float(best.value):.2f} ({best.outcome}) against "
                    f"{others}. Both were measured on the same sample, on the "
                    f"same host, sequentially. {verdicts} {tuning}"),
                "source": "verify.json:engines[*]"})
        if opt.engines_meeting:
            out.append({
                "kind": "engines_meeting",
                "text": (
                    f"{opt.config} meets every engine-scoped constraint on: "
                    f"{', '.join(opt.engines_meeting)}. Deploying it means "
                    f"choosing one of those; the others were measured and did "
                    f"not clear"),
                "source": "report.json:options[*].judgement.engines_meeting"})
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
    """The sentence that says what is missing. Specific, not generic."""
    if name == "latency_p95":
        if "no verify run" in v.reason:
            return ("To decide latency_p95: run `oneground verify` against a "
                    "real engine in the environment the constraint targets. "
                    "Latency is never taken from simulation.")
        if "could not attribute" in v.reason:
            env = (verify_info or {}).get("platform", "this machine")
            return ("To decide latency_p95: re-run `oneground verify` where "
                    "the round trip to the engine is small relative to the "
                    "query. On " + env + " the baseline RTT was a large "
                    "fraction of the query p95, so the number measured the "
                    "path rather than the engine. A pod session with the "
                    "client and engine in the same environment is the way to "
                    "settle it (task 011).")
        if "constraint targets" in v.reason:
            return ("To decide latency_p95: measure in the environment the "
                    "constraint names. " + v.reason + ".")
        return f"To decide latency_p95: {v.reason}."
    if name == "monthly_budget":
        return ("To decide monthly_budget: a cost model with error bands is "
                "not in this build (task 011). Nothing here estimates cost, "
                "because a confident number from list prices would be "
                "fiction.")
    return f"To decide {name}: {v.reason}."


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
    lines = []
    for engine, block in vd.engine_blocks(verify_data):
        ceiling = (block or {}).get("qps_max")
        if not isinstance(ceiling, dict) or ceiling.get("qps_max") is None:
            continue
        who = f"{engine}: " if engine else ""
        lines.append({
            "kind": "qps_max",
            "text": (f"{who}{ceiling['qps_max']:.1f} qps at concurrency "
                     f"{ceiling['at_concurrency']} (p99 "
                     f"{ceiling.get('p99_ms_at_max') or 0:.1f} ms). Ramp "
                     f"stopped because {ceiling['stopped_because']}. "
                     f"{ceiling.get('caveat', '')}"),
            "source": "verify.json:qps_max",
        })
    return lines


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

    options = [vd.judge_option(row, verify_data, constraints, env,
                              costs=costs, verify_info=verify_info)
               for row in sim.get("rows", [])]
    vd.mark_indistinguishable(options, k=k)

    requested = list((req.data.get("simulate") or {}).get("families") or [])
    not_run_rows = vd.not_run(requested, options,
                              (sim_info or {}).get("dropped"))

    recommended = vd.recommend(options, k=k)
    dlog = decision_log(options, not_run_rows, recommended, constraints,
                        verify_info, k=k, env_id=env_id)
    # Appended rather than built inside `decision_log`, which is given the
    # judged options and not the raw verify document. The ceiling is not a
    # judgement of any option -- it is a property of the engine on this host.
    dlog.extend(qps_max_lines(verify_data))

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
        "price_table": (prices.as_dict() if prices is not None
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
        bits = " ".join(
            f"{v.constraint}{'@' + str(v.engine) if v.engine else ''}"
            f"={v.outcome}" for v in o.verdicts)
        print(f"  {o.config:<56} {o.outcome:<14} {bits}")
        if o.engines_meeting:
            print(f"  {'':<56} {'':<14} "
                  f"-> meets every engine-scoped constraint on: "
                  f"{', '.join(o.engines_meeting)}")
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
