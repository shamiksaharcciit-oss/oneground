"""Verdict rules — the only place in oneground that judges anything.

Every other command measures. This one compares measurements to a user's
constraints and says `meets`, `fails` or `couldnt_check`. The house rules bind
hardest here, so they are enforced in code rather than trusted to the caller:

**Three outcomes, and couldn't-check is never rounded up.** There is no fourth
value, no "probably", and no defaulting to `meets` because nothing said
otherwise. A constraint that cannot be decided from a same-environment
measurement is `couldnt_check` with a reason naming what is missing.

**Latency verdicts come only from `verify.json`.** Never from simulation. A
simulator can tell you how many vectors an architecture touches; it cannot
tell you what a request costs on a machine. `latency_p95` refuses a simulated
row by construction -- it takes `verify_rows`, not `sim_row`, and there is a
test that a simulate-only workdir yields `couldnt_check` for every option.

**Every verdict names its source.** `Verdict.source` is a file and a field
path, so a reader can open the workdir and check the number themselves. A
verdict with no source is a claim.

These are pure functions over dicts. They do no I/O, so the rules can be
tested on synthetic rows for every branch without a workdir.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MEETS = "meets"
FAILS = "fails"
COULDNT_CHECK = "couldnt_check"

OUTCOMES = (MEETS, FAILS, COULDNT_CHECK)

# Two options whose recall differs by less than this are reported as
# indistinguishable on recall. 0.01 until a calibration history exists: it is
# the fixture specs' own tolerance on published reference recall, which is the
# best available statement of how much recall difference this project can
# currently defend. Task 011's calibration history replaces it with a measured
# distribution.
CALIBRATION_TOLERANCE = 0.01

# A constraint is "at margin" when the measured value sits within this
# fraction of its threshold -- it passes, but not with room. Used only for
# ranking, never for a verdict.
MARGIN_FRACTION = 0.10


@dataclass
class Verdict:
    """One constraint, judged against one option."""

    constraint: str
    outcome: str
    reason: str
    source: str = ""
    value: Any = None
    threshold: Any = None
    kind: str = "receipt"
    # Which engine produced the measurement behind this verdict, where one
    # did. Task 015: with two engines verified in the same environment, a
    # latency verdict without an engine name is not a fact anyone can use.
    engine: Any = None

    def as_dict(self):
        return {"constraint": self.constraint, "outcome": self.outcome,
                "reason": self.reason, "source": self.source,
                "value": self.value, "threshold": self.threshold,
                "kind": self.kind, "engine": self.engine}


@dataclass
class Option:
    """One (family, config) row, its measurements and its verdicts.

    `measurement` and `judgement` are kept in separate keys all the way to
    `report.json`: the numbers are re-derivable receipts, the verdicts are a
    reading of them against constraints that may change tomorrow.
    """

    family: str
    config: str
    params: Dict[str, Any]
    measurement: Dict[str, Any]
    verdicts: List[Verdict] = field(default_factory=list)
    outcome: str = COULDNT_CHECK
    indistinguishable_from: List[str] = field(default_factory=list)
    engines_meeting: List[str] = field(default_factory=list)

    def as_dict(self):
        return {
            "family": self.family,
            "config": self.config,
            "params": dict(self.params),
            "measurement": dict(self.measurement),
            "judgement": {
                "outcome": self.outcome,
                "constraints": [v.as_dict() for v in self.verdicts],
                "indistinguishable_from": list(self.indistinguishable_from),
                "engines_meeting": list(self.engines_meeting),
            },
        }

    def verdict_for(self, name):
        for v in self.verdicts:
            if v.constraint == name:
                return v
        return None


# --------------------------------------------------------------------------
# per-constraint rules
# --------------------------------------------------------------------------

def recall_floor(sim_row, constraints):
    """Recall@k against `constraints.recall_at_k.min`.

    Decidable whenever the row exists: recall is measured against exact k-NN
    ground truth by the simulator, which is the same quantity the constraint
    is about. This is the one constraint simulation can settle on its own.
    """
    c = (constraints or {}).get("recall_at_k") or {}
    if "min" not in c:
        return None                  # not asked for; no row in the table
    k = int(c.get("k", 10))
    key = f"recall_at_{k}"
    if key not in sim_row:
        have = sorted(x for x in sim_row if x.startswith("recall_at_"))
        return Verdict("recall_at_k", COULDNT_CHECK,
                       f"the sweep did not report {key}; it reported "
                       f"{', '.join(have) or 'nothing'}",
                       source=f"simulate.json:rows[{sim_row.get('config')}]")
    got, floor = float(sim_row[key]), float(c["min"])
    outcome = MEETS if got >= floor else FAILS
    return Verdict(
        "recall_at_k", outcome,
        f"recall@{k} {got:.4f} {'>=' if outcome == MEETS else '<'} {floor}",
        source=f"simulate.json:rows[{sim_row.get('config')}].{key}",
        value=got, threshold=floor)


def storage_amplification(sim_row, constraints):
    """Stored copies per base vector against
    `constraints.storage_amplification_max`."""
    c = (constraints or {})
    if "storage_amplification_max" not in c:
        return None                  # not asked for; no row in the table
    got = sim_row.get("storage_amplification")
    if got is None:
        return Verdict("storage_amplification", COULDNT_CHECK,
                       "the sweep row has no storage_amplification",
                       source=f"simulate.json:rows[{sim_row.get('config')}]")
    got, cap = float(got), float(c["storage_amplification_max"])
    outcome = MEETS if got <= cap else FAILS
    return Verdict(
        "storage_amplification", outcome,
        f"{got:.2f}x stored copies per vector "
        f"{'<=' if outcome == MEETS else '>'} {cap}x",
        source=f"simulate.json:rows[{sim_row.get('config')}]"
               ".storage_amplification",
        value=got, threshold=cap)


def memory_budget(sim_row, constraints):
    """Estimated resident bytes against `constraints.memory_budget_gb`.

    The estimate is the simulator's (`est_memory_bytes`: vector payload plus
    an HNSW graph term), and the verdict says so. It is not an observed RSS,
    and the reason string carries that word so nobody reads it as one.
    """
    c = (constraints or {})
    if "memory_budget_gb" not in c:
        return None                  # not asked for; no row in the table
    got = sim_row.get("est_memory_bytes")
    if got is None:
        return Verdict("memory_budget", COULDNT_CHECK,
                       "the sweep row has no est_memory_bytes",
                       source=f"simulate.json:rows[{sim_row.get('config')}]")
    gb = float(got) / 1e9
    cap = float(c["memory_budget_gb"])
    outcome = MEETS if gb <= cap else FAILS
    return Verdict(
        "memory_budget", outcome,
        f"estimated {gb:.3f} GB {'<=' if outcome == MEETS else '>'} {cap} GB "
        "(estimate: vector payload plus an HNSW graph term, not observed RSS)",
        source=f"simulate.json:rows[{sim_row.get('config')}]"
               ".est_memory_bytes",
        value=gb, threshold=cap, kind="receipt (estimate)")


# Which simulated option, if any, the engine was actually built as.
#
# Only one family can correspond to a single engine namespace: a sharded
# architecture is a routing layer over several of them, and a pod that built
# one Qdrant collection did not build a sharded anything. Extending this map
# is how a future adapter declares that it can verify a sharded family.
VERIFIABLE_FAMILIES = {"single_node_hnsw"}

# simulate's parameter name -> where the engine reports it.
#   index_params  what the engine says it built (the authority)
#   engine_params what oneground asked for; used only where the engine does
#                 not report the field at all
_PARAM_SOURCES = {
    "M": ("index_params", "m"),
    "efConstruction": ("index_params", "ef_construct"),
    # Query-time, so Qdrant does not list it in index_params. Dropping it
    # would let a row with a different efSearch claim this measurement.
    "efSearch": ("engine_params", "hnsw_ef"),
}


def verified_config_mismatch(sim_row, verify_info):
    """None when this option is the one the engine was built as.

    Otherwise a sentence saying what differs, for a couldnt_check reason.
    Returns None (no refusal) when `verify_info` carries no engine facts at
    all -- an older verify.json cannot be checked against, and refusing every
    option on that basis would be inventing a mismatch rather than finding
    one. The absence is visible in the source string.
    """
    if not verify_info:
        return None
    facts = (verify_info.get("engine_facts") or {})
    index_params = facts.get("index_params")
    engine_params = verify_info.get("engine_params") or {}
    if not index_params and not engine_params:
        return None

    family = sim_row.get("family")
    if family not in VERIFIABLE_FAMILIES:
        built = facts.get("index_type") or "one index"
        return (f"the verify run built {built} in a single namespace, which "
                f"is not a {family} deployment. This row's architecture was "
                "simulated and never built, so a measurement of the built "
                "index says nothing about it")

    sources = {"index_params": index_params or {}, "engine_params": engine_params}
    differences = []
    for name, value in (sim_row.get("params") or {}).items():
        where = _PARAM_SOURCES.get(name)
        if where is None:
            continue                      # not a parameter the engine builds
        table, key = where
        got = sources.get(table, {}).get(key)
        if got is None:
            continue                      # the engine does not report it
        if float(got) != float(value):
            differences.append(f"{name}={value} but the engine was built with "
                               f"{key}={got}")
    if differences:
        return ("this row's parameters are not the ones the engine was built "
                "with: " + "; ".join(differences))
    return None


def engine_blocks(verify_data):
    """[(engine_name, block)] for either verify.json shape.

    Task 015 made verify.json hold `engines`, a list, with no engine promoted
    to the top level -- a format with a primary engine and an also-ran would
    be picking a favourite. Files written before that are a single flat block,
    and are read as a one-engine list so nothing that already exists has to be
    rewritten to be readable.
    """
    if not verify_data:
        return []
    blocks = verify_data.get("engines")
    if isinstance(blocks, list):
        out = []
        for b in blocks:
            if isinstance(b, dict):
                merged = dict(b)
                # environment_id lives at the top of the multi-engine file.
                merged.setdefault("environment_id",
                                  verify_data.get("environment_id"))
                out.append((b.get("engine"), merged))
        return out
    return [(verify_data.get("engine"), verify_data)]


def engine_info_blocks(verify_info):
    """[(engine_name, info_block)] for either verify_info.json shape."""
    if not verify_info:
        return []
    blocks = verify_info.get("engines")
    if isinstance(blocks, list):
        return [(b.get("engine"), b) for b in blocks if isinstance(b, dict)]
    return [(verify_info.get("engine"), verify_info)]


def latency_p95(sim_row, verify_data, constraints, verify_env=None,
                verify_info=None, engine=None):
    """p95 latency against `constraints.latency.p95_ms`.

    **Only from `verify.json`, and only from a same-environment run.** There
    are four ways this returns couldn't-check, and each names what is missing:

        no constraint      nothing to judge against
        no verify row      the workdir has no verify.json, or none at this k
        environment noise  verify itself refused to attribute the number
        wrong environment  measured somewhere the constraint does not target

    Note what this function does *not* take: `sim_row` is accepted only to
    name the option in the source string, and no field of it is ever read for
    a latency value. A simulator has no latency to give.
    """
    c = (constraints or {}).get("latency") or {}
    if "p95_ms" not in c:
        return None                  # not asked for; no row in the table
    cap = float(c["p95_ms"])
    k = int((constraints or {}).get("recall_at_k", {}).get("k", 10))

    # Which row can answer this constraint.
    #
    # A constraint naming at_qps or concurrency is a statement about the
    # engine *under load*, and only a row measured under load at that
    # concurrency can settle it. There is deliberately no fallback to the
    # sequential row: the two measure different things, and substituting one
    # for the other silently answers a question nobody asked. Session
    # 20260909-225058 made the difference plain -- sequential p95 7.18 ms
    # against a 6.99 ms round trip (97%, refused), under load 38.22 ms against
    # the same round trip (18%, attributable).
    under_load = "at_qps" in c or "concurrency" in c
    row_key = f"k={k}_under_load" if under_load else f"k={k}"

    if not verify_data:
        return Verdict(
            "latency_p95", COULDNT_CHECK,
            "no verify run in this workdir. Latency is never taken from "
            "simulation; run `oneground verify` against a real engine.",
            source="verify.json (absent)", threshold=cap, kind="declared", engine=engine)

    # A measurement belongs to the configuration that produced it. Checked
    # before any row is read, so a mismatch is never reported as a latency
    # number that happens to pass.
    mismatch = verified_config_mismatch(sim_row, verify_info)
    if mismatch:
        return Verdict(
            "latency_p95", COULDNT_CHECK,
            f"this configuration was not the one verified -- {mismatch}",
            source="verify_info.json:engine_facts.index_params",
            threshold=cap, kind="declared", engine=engine)

    searches = verify_data.get("searches") or {}
    row = searches.get(row_key)
    if row is None:
        measured = ", ".join(sorted(searches)) or "nothing"
        if under_load:
            asked = []
            if "at_qps" in c:
                asked.append(f"at_qps {c['at_qps']}")
            if "concurrency" in c:
                asked.append(f"concurrency {c['concurrency']}")
            return Verdict(
                "latency_p95", COULDNT_CHECK,
                f"this constraint names {' and '.join(asked)}, so it is a "
                f"statement about latency under load and only a row measured "
                f"under load can settle it. This verify run measured "
                f"{measured}, and no {row_key}. Run `oneground verify` with "
                "verify.target: runpod and a load phase; the sequential row "
                "is not a substitute, because it measures a different thing.",
                source="verify.json:searches", threshold=cap, kind="declared", engine=engine)
        return Verdict(
            "latency_p95", COULDNT_CHECK,
            f"the verify run measured {measured}, not {row_key}",
            source="verify.json:searches", threshold=cap, kind="declared", engine=engine)

    shape = row.get("latency_shape_single_client")
    if isinstance(shape, str):
        # verify already refused to attribute this number. Carry its reason.
        return Verdict(
            "latency_p95", COULDNT_CHECK,
            f"the verify run could not attribute latency in {row_key}: "
            f"{shape}",
            source=f"verify.json:searches[{row_key}]."
                   "latency_shape_single_client",
            threshold=cap, kind="declared", engine=engine)

    want_env = c.get("environment")
    if want_env and verify_env and str(want_env) != str(verify_env):
        return Verdict(
            "latency_p95", COULDNT_CHECK,
            f"measured on {verify_env}, constraint targets {want_env}",
            source="verify_info.json:environment", threshold=cap,
            kind="declared", engine=engine)

    # Same-environment rule. Two rows measured on different pods are two
    # different machines with two different neighbours, and comparing their
    # latency compares the hosts. `environment_id` is the pod id; when a
    # constraint names one, only a row from that environment can settle it.
    want_eid = c.get("environment_id")
    got_eid = verify_data.get("environment_id")
    if want_eid and str(want_eid) != str(got_eid):
        return Verdict(
            "latency_p95", COULDNT_CHECK,
            f"measured in environment {got_eid or 'unrecorded'}, constraint "
            f"targets {want_eid}. Latency rows from different environments "
            "are never compared: they are different machines.",
            source="verify.json:environment_id", threshold=cap,
            kind="declared", engine=engine)

    conc = int(shape.get("concurrency", 1) or 1)
    want_conc = c.get("concurrency")
    if under_load and want_conc and int(want_conc) != conc:
        return Verdict(
            "latency_p95", COULDNT_CHECK,
            f"{row_key} was measured at concurrency {conc}, and the "
            f"constraint specifies {want_conc}. Latency at one concurrency "
            "does not transfer to another -- the queue is most of the "
            "number.",
            source=f"verify.json:searches[{row_key}]."
                   "latency_shape_single_client.concurrency",
            threshold=cap, kind="declared", engine=engine)

    got = float(shape["p95_ms"])
    env = f" on {verify_env}" if verify_env else ""
    if got_eid:
        env += f" (environment {got_eid})"
    how = (f"under load at concurrency {conc}" if conc > 1
           else "sequential, single client -- a latency shape, not throughput")

    # Task 017 item 2. With several runs the verdict is decided by the whole
    # set, never by one of them:
    #
    #     meets          only if the WORST run meets
    #     fails          only if the BEST run fails
    #     couldnt_check  otherwise -- the threshold is inside the spread
    #
    # 015 measured this configuration at 38.22 ms and 42.82 ms against a 40 ms
    # cap, 12% apart, and reported `meets` once and `fails` once with nothing
    # about the architecture changing. Both were single runs, and both were
    # wrong to be stated as flatly as they were. A threshold that falls
    # between two samples is not a verdict, it is a coin toss with a receipt.
    spread = shape.get("p95_across_runs")
    if isinstance(spread, dict) and int(spread.get("n_runs", 0)) > 1:
        per_run = [float(v) for v in spread.get("p95_ms_per_run") or []]
        n = len(per_run) or int(spread["n_runs"])
        lo, hi = float(spread["min"]), float(spread["max"])
        width = float(spread.get("spread", hi - lo))
        meets_in = sum(1 for v in per_run if v <= cap)
        runs_txt = ", ".join(f"{v:.2f}" for v in per_run)
        src = (f"verify.json:searches[{row_key}]."
               "latency_shape_single_client.p95_across_runs")
        if hi <= cap:
            return Verdict(
                "latency_p95", MEETS,
                f"p95 <= {cap} ms in all {n} runs (worst {hi:.2f} ms){env} "
                f"-- runs {runs_txt}; spread {width:.2f} ms "
                f"(from {row_key}: {how})",
                source=src, value=hi, threshold=cap, engine=engine)
        if lo > cap:
            return Verdict(
                "latency_p95", FAILS,
                f"p95 > {cap} ms in all {n} runs (best {lo:.2f} ms){env} "
                f"-- runs {runs_txt}; spread {width:.2f} ms "
                f"(from {row_key}: {how})",
                source=src, value=lo, threshold=cap, engine=engine)
        return Verdict(
            "latency_p95", COULDNT_CHECK,
            f"meets in {meets_in} of {n} runs, spread {width:.2f} ms "
            f"({lo:.2f}-{hi:.2f} ms against a {cap} ms cap){env} -- runs "
            f"{runs_txt}. The threshold falls inside the run-to-run "
            "variation, so this configuration is not measurably on either "
            "side of it. Reported as couldn't-check rather than picked from "
            f"one run (from {row_key}: {how})",
            source=src, value=None, threshold=cap, kind="declared",
            engine=engine)

    outcome = MEETS if got <= cap else FAILS
    return Verdict(
        "latency_p95", outcome,
        f"p95 {got:.2f} ms {'<=' if outcome == MEETS else '>'} {cap} ms{env} "
        f"(from {row_key}: {how})",
        source=f"verify.json:searches[{row_key}]."
               "latency_shape_single_client.p95_ms",
        value=got, threshold=cap, engine=engine)


def qps_target(sim_row, verify_data, constraints, verify_env=None,
               verify_info=None, engine=None):
    """Achieved QPS against `constraints.latency.at_qps`.

    Only from a load phase. A sequential single-client run has no throughput
    to report, and a simulator has less than that -- so a workdir without a
    load phase is couldnt_check, naming what to run.
    """
    c = (constraints or {}).get("latency") or {}
    if "at_qps" not in c:
        return None
    target = float(c["at_qps"])
    if not verify_data:
        return Verdict("qps", COULDNT_CHECK,
                       "no verify run in this workdir",
                       source="verify.json (absent)", threshold=target,
                       kind="declared", engine=engine)
    mismatch = verified_config_mismatch(sim_row, verify_info)
    if mismatch:
        return Verdict(
            "qps", COULDNT_CHECK,
            f"this configuration was not the one verified -- {mismatch}",
            source="verify_info.json:engine_facts.index_params",
            threshold=target, kind="declared", engine=engine)

    load = verify_data.get("load")
    if not load:
        return Verdict(
            "qps", COULDNT_CHECK,
            "this verify run measured a single-client latency shape and no "
            "load phase, so it has no throughput to report. Run "
            "`oneground verify` with verify.target: runpod, which puts the "
            "load generator and the engine in the same environment.",
            source="verify.json:load (absent)", threshold=target,
            kind="declared", engine=engine)

    want_eid = c.get("environment_id")
    got_eid = verify_data.get("environment_id")
    if want_eid and str(want_eid) != str(got_eid):
        return Verdict("qps", COULDNT_CHECK,
                       f"measured in environment {got_eid or 'unrecorded'}, "
                       f"constraint targets {want_eid}",
                       source="verify.json:environment_id", threshold=target,
                       kind="declared", engine=engine)

    got = float(load.get("achieved_qps", 0.0))
    conc = load.get("concurrency")
    want_conc = c.get("concurrency")
    if want_conc and int(want_conc) != int(conc or 0):
        return Verdict(
            "qps", COULDNT_CHECK,
            f"measured at concurrency {conc}, constraint specifies "
            f"{want_conc}. Throughput at one concurrency does not transfer "
            "to another.",
            source="verify.json:load.concurrency", threshold=target,
            kind="declared", engine=engine)

    eid = f" (environment {got_eid})" if got_eid else ""
    offered = float(load.get("target_qps") or 0.0)
    duration = float(load.get("duration_seconds") or 0.0)
    completed = int(load.get("completed") or 0)
    errors = int(load.get("errors") or 0)

    # A throttled run is a sustain check, not a ceiling.
    #
    # The generator holds the offered rate with a token bucket, so achieved
    # can never exceed target and `achieved >= target` is a knife-edge that
    # fails by a hair on essentially every targeted run -- it measures the
    # token bucket, not the engine. arxiv-150k completed 59,999 of 60,000 in
    # five minutes and was reported as `200.0 qps achieved < 200 target`.
    #
    # The question a throttled run answers is whether the engine held the
    # offered rate without errors. The tolerance is one query per second of
    # measured duration: the bucket's own tick granularity, so a run is never
    # failed for landing inside its own resolution.
    if offered > 0 and duration > 0:
        expected = offered * duration
        shortfall = expected - completed
        tolerance = duration                      # one query per second
        if errors:
            outcome = FAILS
            why = (f"{errors} error(s) during the load phase, so the offered "
                   f"rate was not sustained")
        elif shortfall <= tolerance:
            outcome = MEETS
            why = (f"sustained the offered {offered:g} qps at concurrency "
                   f"{conc}: {completed} of {expected:.0f} queries in "
                   f"{duration:g} s, short by {shortfall:.0f} against a "
                   f"tolerance of {tolerance:.0f} (one query per second of "
                   f"duration, the generator's tick), 0 errors")
        else:
            outcome = FAILS
            why = (f"did not sustain the offered {offered:g} qps at "
                   f"concurrency {conc}: {completed} of {expected:.0f} "
                   f"queries in {duration:g} s, short by {shortfall:.0f} "
                   f"against a tolerance of {tolerance:.0f} (one query per "
                   f"second of duration, the generator's tick)")
        return Verdict(
            "qps", outcome,
            f"{why}{eid}. Achieved {got!r} qps against a {target!r} target; "
            "this is a sustain check -- a throttled run cannot exceed what "
            "it was offered, so it is not a measurement of the engine's "
            "ceiling. See qps_max",
            source="verify.json:load.completed", value=got,
            threshold=target, engine=engine)

    # Unthrottled (target_qps 0): achieved really is a ceiling measurement,
    # and the plain comparison is the right one.
    outcome = MEETS if got >= target else FAILS
    return Verdict(
        "qps", outcome,
        f"{got!r} qps achieved {'>=' if outcome == MEETS else '<'} "
        f"{target!r} target at concurrency {conc}{eid} (unthrottled: the "
        "generator offered no rate limit, so this is a ceiling)",
        source="verify.json:load.achieved_qps", value=got,
        threshold=target, engine=engine)


# --------------------------------------------------------------------- qps_max
#
# NOT IMPLEMENTED. Documented here so the gap is visible rather than folded
# into `qps_target`, which answers a different question.
#
# `qps_target` on a throttled run asks: did the engine sustain the rate it was
# offered? That is the right question for a capacity plan built around a known
# arrival rate, and it is what `verify.target: runpod` measures today.
#
# It cannot answer: what is the most this engine will do before latency or
# errors become unacceptable? That needs a different run -- an unthrottled or
# ramped load phase, taking the highest offered rate at which error rate stays
# zero and p95 stays under the constraint, which means several load phases
# rather than one. The engine's ceiling and the offered rate it sustained are
# not the same number and must never be reported in the same row.
#
# When it is implemented it takes its own verdict row (`qps_max`), its own
# source in verify.json (a ramp, not a single `load` block), and it does not
# change the meaning of `qps`.


def monthly_budget_from_cost(sim_row, constraints, costs):
    """Budget against the cost model's **upper bound**.

    Under-running a budget is a pleasant surprise; over-running one is the
    failure the constraint exists to prevent, so the error band is used in the
    direction that can only make the verdict stricter.
    """
    c = (constraints or {}).get("monthly_budget") or {}
    if not c:
        return None
    amount = c.get("amount")
    cur = c.get("currency", "EUR")
    entry = (costs or {}).get(sim_row.get("config"))
    if not entry:
        return Verdict("monthly_budget", COULDNT_CHECK,
                       "no cost model in this run", source="(not run)",
                       threshold=amount, kind="declared")
    if "couldnt_check" in entry:
        return Verdict("monthly_budget", COULDNT_CHECK,
                       entry["couldnt_check"], source="cost",
                       threshold=amount, kind="declared")
    high = float(entry["monthly_high"])
    outcome = MEETS if high <= float(amount) else FAILS
    return Verdict(
        "monthly_budget", outcome,
        f"{entry['rendered']}/month; upper bound {entry['currency']} "
        f"{high:,.0f} {'<=' if outcome == MEETS else '>'} {amount} {cur} "
        f"({entry['basis']})",
        source="report.json:costs[config].monthly_high",
        value=high, threshold=float(amount),
        kind="estimate (declared prices)")


def monthly_budget(sim_row, constraints, cost_model=None):
    """Always couldn't-check in this build: there is no cost model.

    Task 011 adds one with error bands. Until then a budget cannot be judged,
    and guessing from instance list prices would be exactly the kind of
    confident fiction this project exists to avoid.
    """
    c = (constraints or {}).get("monthly_budget") or {}
    if not c:
        return None                      # not asked for; no row in the table
    amount = c.get("amount")
    cur = c.get("currency", "")
    if cost_model is None:
        return Verdict(
            "monthly_budget", COULDNT_CHECK,
            f"no cost model in this build, so {amount} {cur}/month cannot be "
            "judged. Cost with error bands is task 011.",
            source="(not implemented)", threshold=amount, kind="declared")
    raise NotImplementedError("cost model is task 011")


# --------------------------------------------------------------------------
# per-option and cross-option
# --------------------------------------------------------------------------

def collapse_by_constraint(verdicts):
    """One outcome per constraint, folding the per-engine verdicts together.

    A constraint measured on two engines has two verdicts, and the option's
    outcome cannot simply take the worst of them. An architecture whose p95
    clears the budget on Qdrant and misses it on pgvector is not "out" -- it
    is deployable, on Qdrant, and the reader needs to be told which. So for a
    constraint with per-engine verdicts:

        meets          at least one engine meets it
        fails          every engine that could be checked fails it
        couldnt_check  no engine could be checked

    The permissive direction is deliberate and it is only safe because the
    decision log names the engine every time: "meets on qdrant" is a fact,
    "meets" alone would not be. `engines_meeting` on the Option carries the
    same information to report.json.
    """
    by_name = {}
    for v in verdicts:
        by_name.setdefault(v.constraint, []).append(v)
    out = {}
    for name, group in by_name.items():
        if any(v.outcome == MEETS for v in group):
            out[name] = MEETS
        elif all(v.outcome == FAILS for v in group):
            out[name] = FAILS
        else:
            out[name] = COULDNT_CHECK
    return out


def overall(verdicts):
    """`fails` if any constraint fails; `meets` if all meet; else
    `couldnt_check`.

    Note the order: a single failure decides, even if other constraints could
    not be checked. An option that provably breaks a constraint is not
    "unknown" -- it is out.

    Judged per *constraint*, not per verdict, because a constraint may have
    one verdict per engine -- see `collapse_by_constraint`.
    """
    if not verdicts:
        # No constraints were asked for, so nothing has been judged. Calling
        # that `meets` would be a verdict with no evidence behind it.
        return COULDNT_CHECK
    outcomes = collapse_by_constraint(verdicts).values()
    if any(o == FAILS for o in outcomes):
        return FAILS
    if all(o == MEETS for o in outcomes):
        return MEETS
    return COULDNT_CHECK


def engines_meeting(verdicts):
    """Engines that meet every engine-scoped constraint they were judged on.

    The answer to "so which one do I deploy?" when an architecture was
    verified on more than one engine. An engine that failed any engine-scoped
    constraint is not in the list; one whose verdicts were all couldnt_check
    is not either, because could-not-check is not a pass.
    """
    scoped = [v for v in verdicts if v.engine is not None]
    if not scoped:
        return []
    names = []
    for name in dict.fromkeys(v.engine for v in scoped):
        mine = [v for v in scoped if v.engine == name]
        if any(v.outcome == FAILS for v in mine):
            continue
        if any(v.outcome == MEETS for v in mine):
            names.append(name)
    return names


def judge_option(sim_row, verify_data, constraints, verify_env=None,
                 costs=None, verify_info=None):
    """Every constraint, for one option."""
    # A constraint that was not asked for produces no row at all. It is not a
    # check that could not be made -- it is a check nobody requested, and
    # reporting it as couldnt_check would let an absent constraint block every
    # recommendation.
    candidates = [
        recall_floor(sim_row, constraints),
        storage_amplification(sim_row, constraints),
        memory_budget(sim_row, constraints),
    ]

    # One latency and one qps verdict PER ENGINE. An architecture measured on
    # two engines has two latency facts, not one, and collapsing them would
    # either hide a failure or invent a pass. Which engine to deploy on is
    # then a choice the reader makes with both numbers in front of them.
    blocks = engine_blocks(verify_data)
    infos = dict(engine_info_blocks(verify_info))
    if not blocks:
        blocks = [(None, None)]
    for engine_name, block in blocks:
        info = infos.get(engine_name, verify_info if len(infos) <= 1 else None)
        candidates.append(latency_p95(sim_row, block, constraints, verify_env,
                                      info, engine=engine_name))
        candidates.append(qps_target(sim_row, block, constraints, verify_env,
                                     info, engine=engine_name))

    candidates.append(
        monthly_budget_from_cost(sim_row, constraints, costs) if costs
        else monthly_budget(sim_row, constraints))
    verdicts = [v for v in candidates if v is not None]

    measurement = {k: v for k, v in sim_row.items()
                   if k not in ("family", "config", "params")}
    opt = Option(family=sim_row.get("family", "?"),
                 config=sim_row.get("config", "?"),
                 params=sim_row.get("params", {}),
                 measurement=measurement,
                 verdicts=verdicts)
    opt.outcome = overall(verdicts)
    opt.engines_meeting = engines_meeting(verdicts)
    return opt


def mark_indistinguishable(options, tolerance=CALIBRATION_TOLERANCE, k=10):
    """Among `meets` options, group those whose recall is within tolerance.

    Two architectures whose recall differs by less than what this project can
    currently defend are not "one better than the other" -- they are the same
    on recall, and the choice between them has to be made on something else.
    Saying so is more honest than ranking them and letting a reader infer a
    difference that is inside the noise.
    """
    # Options still in contention -- `meets` and `couldnt_check`, not `fails`.
    # Indistinguishability is a claim about *recall*, not about the overall
    # outcome: two options whose latency could not be checked are still
    # identical on recall, and a reader choosing between them needs to know
    # that the recall column cannot separate them. Restricting this to `meets`
    # would silently drop the comparison in exactly the case where the
    # decision is hardest.
    contenders = [o for o in options if o.outcome != FAILS]
    key = f"recall_at_{k}"
    for a in contenders:
        ra = a.measurement.get(key)
        if ra is None:
            continue
        for b in contenders:
            if b is a:
                continue
            rb = b.measurement.get(key)
            if rb is None:
                continue
            if abs(float(ra) - float(rb)) < tolerance:
                if b.config not in a.indistinguishable_from:
                    a.indistinguishable_from.append(b.config)
    return options


def not_run(requested_families, options, dropped=None):
    """Families asked for that produced no rows. Never silently omitted.

    A missing row and a failing row look identical in a table that only lists
    what ran, and they mean opposite things.
    """
    present = {o.family for o in options}
    dropped_by_family = {}
    for d in (dropped or []):
        label = d.get("config", "")
        fam = label.split("[")[0] if "[" in label else label
        dropped_by_family.setdefault(fam, []).append(d)

    out = []
    for fam in (requested_families or []):
        if fam in present:
            continue
        drops = dropped_by_family.get(fam, [])
        if drops:
            reason = (f"{len(drops)} configuration(s) were planned and none "
                      f"was measured: {drops[0].get('reason', 'dropped')}. "
                      f"Rule: {drops[0].get('rule', 'unknown')}")
        else:
            reason = ("the sweep produced no rows for this family and "
                      "recorded no reason")
        out.append({"family": fam, "reason": reason,
                    "outcome": COULDNT_CHECK})
    return out


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------

def at_margin(verdict, fraction=MARGIN_FRACTION):
    """True when a passing constraint passes only just.

    Used for ranking, never for a verdict: an option that clears every
    threshold with room is a safer recommendation than one that scrapes past,
    and that preference should be visible rather than hidden in a sort.
    """
    if verdict.outcome != MEETS or verdict.value is None \
            or verdict.threshold is None:
        return False
    try:
        v, t = float(verdict.value), float(verdict.threshold)
    except (TypeError, ValueError):
        return False
    if t == 0:
        return False
    if verdict.constraint == "recall_at_k":       # higher is better
        return v < t * (1 + fraction)
    return v > t * (1 - fraction)                 # lower is better


def rank_key(option, k=10):
    """Default `rank_by`: fewest constraints at margin, then lowest storage,
    then lowest fan-out. Ties broken by config label so a run is stable."""
    margins = sum(1 for v in option.verdicts if at_margin(v))
    return (margins,
            float(option.measurement.get("storage_amplification", 9e9)),
            float(option.measurement.get("fanout", 9e9)),
            option.config)


def recommend(options, k=10):
    """The top `meets` option, or None with a reason.

    Only `meets` options are ever recommended. A `couldnt_check` option might
    be excellent; the point is that nobody knows, and recommending it would
    be rounding couldn't-check up to a verdict.
    """
    meets = [o for o in options if o.outcome == MEETS]
    if not meets:
        return None
    return sorted(meets, key=lambda o: rank_key(o, k))[0]
