"""Family conformance: what every family must do, run by one command.

    oneground models conformance
    oneground models conformance --family hash_sharded
    python -m oneground.models.conformance --family semantic_sharded

WHY THIS EXISTS
---------------
An engine adapter must pass a conformance suite before it is usable: namespace
lifecycle, recall against exact truth, index readiness, cleanup on failure. A
**family** is the same kind of contribution unit in the charter, and until this
module it relied on whatever acceptance criteria its own task carried. That was
adequate while every family was written by this team and is not adequate for
anyone else.

WHAT A CHECK IS
---------------
Each check says **what it measured**, **what that means**, and on failure
**which protocol requirement was violated** -- not which assertion tripped. A
reader who has never seen this codebase should be able to act on the output.

Outcomes are the project's three and are never rounded up:

    passes         the requirement is met, and the measurement is shown
    fails          the requirement is violated. A finding about the family.
    couldnt_check  not decidable on this machine, with what would settle it

**Synthetic data throughout.** These check the protocol's contract, not any
published number: a family that passes has not been shown to be a good
architecture, only a correctly implemented one.

ON RUNNING THIS AGAINST A NEW FAMILY
------------------------------------
Nothing here names a shipped family. The corpus is small and blobby, the grid
is a superset of the knobs the three shipped families read, and a family that
reads none of them falls back to its own `DEFAULT_GRID`. A family whose
partition needs values this grid does not supply should say so in its
`MODEL.md`; the suite reports what it could not cover rather than passing it.
"""

import argparse
import contextlib
import os
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import models                                   # noqa: E402
from oneground.models import state as S                        # noqa: E402
from oneground.models.base import (                            # noqa: E402
    BUILD, CONSTANT, INDEX_KNOB_KEYS, NO_DEFAULT, PARAMETER, RUN, Config,
    ConfigSpace, ParameterError, _belonging_problem, parameter_table)
from oneground.truth import exact_knn                          # noqa: E402

# --------------------------------------------------------------------------
# outcomes
# --------------------------------------------------------------------------

PASSES = "passes"
FAILS = "fails"
COULDNT_CHECK = "couldnt_check"

OUTCOME_LABEL = {PASSES: "passes", FAILS: "FAILS",
                 COULDNT_CHECK: "couldn't-check"}


@dataclass
class CheckResult:
    """One check against one family.

    `requirement` is the protocol requirement in words -- what a contributor
    has to satisfy -- and is printed on failure instead of a traceback.
    """

    check: str
    outcome: str
    requirement: str
    measured: str = ""
    meaning: str = ""
    detail: str = ""

    def as_dict(self):
        return {"check": self.check, "outcome": self.outcome,
                "requirement": self.requirement, "measured": self.measured,
                "meaning": self.meaning, "detail": self.detail}


# --------------------------------------------------------------------------
# the synthetic corpus and the covering grid
# --------------------------------------------------------------------------

SEED = 20260920
K = 10
N_BASE = 1500
DIM = 32
N_QUERIES = 40

# Small enough that every family builds in seconds, and large enough that an
# IVF coarse quantiser has something to train on inside the smallest shard.
# `m` divides DIM; `2**nbits` is well under the per-shard vector count, which
# is what `indexes.build` refuses on.
GRID = {
    "index": ("flat", "hnsw", "ivf", "ivf_pq"),
    "nlist": (8,), "nprobe": (4,), "m": (8,), "nbits": (4,),
    # The three shipped families' partition knobs, at values this corpus can
    # carry. A family that reads none of these uses its own DEFAULT_GRID.
    "centroids": (8,), "epsilon": (0.2,), "probe": (2,),
    "shards": (3,), "M": (16,), "efSearch": (64,),
}

# Every state column the lab's views read without first asking `has()`.
# Derived from `lab/views/{ground,query_trace,query_index}.py` rather than
# chosen here: a family that omits one of these is drawable nowhere, and the
# view fails at read time rather than at build time.
LAB_REQUIRED_COLUMNS = (
    "partition.region_ids",
    "assignment.home_region", "assignment.centroid_dist",
    "assignment.nearest_region", "assignment.copy_count",
    "route.probed_region", "route.probe_reason",
    "route.scored_region", "route.scored_dist",
    "candidates.offsets", "candidates.cand_id", "candidates.cand_score",
    "candidates.survived_dedupe", "candidates.true_rank",
    "candidates.true_ids",
    "load.vectors_held",
)


def synthetic_corpus(n=N_BASE, dim=DIM, n_q=N_QUERIES, seed=SEED, blobs=6):
    """Blobby and normalized: a partition has something to find."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(blobs, dim))
    x = np.vstack([c + rng.normal(0, 0.12, size=(n // blobs + 1, dim))
                   for c in centres])[:n].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = x[rng.choice(n, size=n_q, replace=False)].copy()
    return np.ascontiguousarray(x), np.ascontiguousarray(q)


def _recall(pred, gt):
    if pred is None or not len(pred):
        return 0.0
    hits = sum(len(set(p[p >= 0].tolist()) & set(g.tolist()))
               for p, g in zip(pred, gt))
    return hits / float(gt.shape[0] * gt.shape[1])


@contextlib.contextmanager
def _recording_reads():
    """Record every `(family, key)` a family reads through `Config.get`.

    Patched rather than wrapped because a family receives the `Config` the
    framework built; there is no seam to inject a recorder through, and a
    subclass would not be what `Config.make` returns. Restored in `finally`.
    """
    seen: Dict[str, set] = {}
    original = Config.get

    def recording(self, key, default=None):
        seen.setdefault(self.family, set()).add(key)
        return original(self, key, default)

    Config.get = recording
    try:
        yield seen
    finally:
        Config.get = original


def _partition_key(config):
    """A config's parameters with the index axis removed.

    Two configs with the same partition key describe the same partition under
    different index algorithms, which is what the routing-loss check needs.
    """
    drop = set(INDEX_KNOB_KEYS) | {"index"}
    return tuple(sorted((k, v) for k, v in config.params.items()
                        if k not in drop))


# --------------------------------------------------------------------------
# the runner: one corpus, one build cache, eight checks
# --------------------------------------------------------------------------

@dataclass
class _Ctx:
    family: str
    model: Any
    x: np.ndarray
    q: np.ndarray
    gt: np.ndarray
    configs: List[Config] = field(default_factory=list)
    built: Dict[str, Any] = field(default_factory=dict)
    searched: Dict[str, Any] = field(default_factory=dict)
    ceilings: Dict[str, Any] = field(default_factory=dict)
    footprints: Dict[str, Any] = field(default_factory=dict)
    reads: set = field(default_factory=set)
    notes: List[str] = field(default_factory=list)

    def build(self, config):
        if config.label not in self.built:
            self.built[config.label] = self.model.build(
                self.x, config, seed=SEED)
        return self.built[config.label]

    def search(self, config):
        if config.label not in self.searched:
            self.searched[config.label] = self.model.search(
                self.build(config), self.q, K, config)
        return self.searched[config.label]

    def ceiling(self, config):
        if config.label not in self.ceilings:
            self.ceilings[config.label] = self.model.ceiling(
                self.build(config), self.q, K)
        return self.ceilings[config.label]

    def footprint(self, config):
        if config.label not in self.footprints:
            self.footprints[config.label] = self.model.footprint(
                self.build(config))
        return self.footprints[config.label]


def grid_for(family):
    """`GRID`, narrowed to the keys this family declares.

    A grid naming a key a family does not declare is refused, and rightly --
    task 026's rule reaches grids, so an unread sweep axis is caught at plan
    time rather than silently ignored. The suite therefore offers a superset
    and hands each family only its own share; whatever it does not supply, the
    family's own `DEFAULT_GRID` does.
    """
    table = parameter_table(family)
    return {k: v for k, v in GRID.items() if k in table}


def _belonging_satisfied(config, param):
    """Whether this configuration could read `param` at all.

    A key declared `belongs_to=("rerank", ("exact",))` is unreadable in a
    configuration that reranks none -- not because the family ignores it, but
    because the family is right not to read it. Asking whether it was read
    without asking whether it *could* be is how a check reports a defect that
    is its own blind spot.

    Delegated to the validator's own `_belonging_problem` rather than compared
    against `params` here. A key at its default may be **absent** from params
    -- `index` elides at `hnsw` so that adding it rewrote no published label
    (task 034) -- and a naive `params.get("index") in ("hnsw",)` therefore
    reports `M` and `efSearch` as unreachable in every HNSW configuration.
    It did, before this used the real thing.
    """
    if param.belongs_to is None:
        return True
    return _belonging_problem(config.family,
                              parameter_table(config.family),
                              param, config.params) is None


def _coverage_extras(family, configs):
    """Configurations that reach declared keys the family's own grid does not.

    `candidates` is read only when `rerank` is `exact`, and no family crosses
    the rerank axis in `configs()`. Without this the suite would report
    `candidates` as a knob that does nothing, which is false -- it is a knob
    this suite had not switched on. Built with `Config.make` from a real
    configuration, so every value is one the family would accept.
    """
    table = parameter_table(family)
    base = _pick(configs, prefer="hnsw")
    extras, reached = [], []
    for name, param in sorted(table.items()):
        if param.role != PARAMETER or param.belongs_to is None:
            continue
        if any(_belonging_satisfied(c, param) for c in configs + extras):
            continue
        key, values = param.belongs_to
        params = dict(base.params)
        params[key] = values[0]
        if param.default is not NO_DEFAULT:
            params[name] = param.default
        try:
            extras.append(Config.make(family, params))
            reached.append("%s (via %s=%s)" % (name, key, values[0]))
        except (ParameterError, Exception):                    # noqa: BLE001
            continue
    return extras, reached


def _covering_configs(family, model):
    """Every configuration the suite exercises, from the family's own `configs`.

    The family generates them, so a family with knobs this module has never
    heard of is covered by its own `DEFAULT_GRID` rather than by a list here.
    Keys gated behind a `belongs_to` the grid never satisfies are reached by
    `_coverage_extras`.
    """
    space = ConfigSpace(seed=SEED, node_counts=GRID["shards"],
                        grid={family: grid_for(family)})
    configs = list(model.configs(space))
    extras, reached = _coverage_extras(family, configs)
    return configs + extras, reached


# ---------------------------------------------------------------- check (a)
def check_parameter_table(ctx):
    """Every parameter the family reads is declared; every one declared is read."""
    requirement = (
        "Every key a family reads must be declared in its parameter table, "
        "and every non-constant key it declares must be read. A knob that "
        "exists and is undeclared cannot be swept or validated; a knob "
        "declared and never read silently does nothing, and a sweep over it "
        "measures the same architecture repeatedly under different labels.")
    table = parameter_table(ctx.family)
    read = set(ctx.reads)
    # `Config.get` refuses an undeclared key at read time (task 026), so the
    # first direction cannot fail here -- it fails at the read. Recording it
    # confirms the guarantee rather than assuming it.
    undeclared = sorted(read - set(table))
    readable_roles = (PARAMETER, RUN, BUILD)
    # Only a key some configuration could actually read is expected to be
    # read. A key gated behind a `belongs_to` this suite never satisfied is
    # uncovered, not dead -- reported as such rather than as a failure.
    coverable, uncovered = set(), []
    for name, param in table.items():
        if param.role not in readable_roles:
            continue
        if any(_belonging_satisfied(c, param) for c in ctx.configs):
            coverable.add(name)
        else:
            uncovered.append(name)
    never_read = sorted(coverable - read)
    constants_read = sorted(
        n for n in read if n in table and table[n].role == CONSTANT)

    measured = ("%d declared keys, %d read across %d configurations; "
                "%d coverable and never read, %d not reachable by this suite"
                % (len(table), len(read), len(ctx.configs), len(never_read),
                   len(uncovered)))
    if undeclared:
        return CheckResult(
            "parameter table", FAILS, requirement, measured,
            "a key was read that the table does not declare",
            "read but undeclared: %s" % ", ".join(undeclared))
    if never_read:
        return CheckResult(
            "parameter table", FAILS, requirement, measured,
            "a declared knob does nothing: a sweep over it would produce "
            "distinct labels for identical work",
            "declared but never read: %s%s"
            % (", ".join(never_read),
               ("; constants read from the config: " + ", ".join(constants_read))
               if constants_read else ""))
    if uncovered:
        return CheckResult(
            "parameter table", COULDNT_CHECK, requirement, measured,
            "every key this suite could reach is declared and read, but "
            "some are gated behind a value it never set",
            "not reachable here: %s. What would settle it: a configuration "
            "satisfying each key's `belongs_to`" % ", ".join(sorted(uncovered)))
    return CheckResult(
        "parameter table", PASSES, requirement, measured,
        "the table and the code agree in both directions"
        + (" (%s reached by a constructed configuration)"
           % ", ".join(ctx.notes) if ctx.notes else ""))


# ---------------------------------------------------------------- check (b)
def check_defaults_and_omissions(ctx):
    """A parameter at its default and the same parameter omitted are one label."""
    requirement = (
        "A parameter written at its declared default must produce the same "
        "config label as its omission (task 032). Otherwise a sweep measures "
        "identical work twice and reports it as two configurations.")
    table = parameter_table(ctx.family)
    # `NO_DEFAULT` is a sentinel instance, not a type: compared by identity.
    with_default = [(n, p) for n, p in table.items()
                    if p.role == PARAMETER and p.default is not NO_DEFAULT]

    compared, mismatches, skipped = 0, [], 0
    for config in ctx.configs:
        for name, param in with_default:
            explicit = dict(config.params)
            explicit[name] = param.default
            omitted = {k: v for k, v in config.params.items() if k != name}
            try:
                a = Config.make(ctx.family, explicit).label
                b = Config.make(ctx.family, omitted).label
            except ParameterError:
                # The key does not belong to this configuration's algorithm;
                # neither spelling is legal, so there is nothing to compare.
                skipped += 1
                continue
            compared += 1
            if a != b:
                mismatches.append("%s: %s != %s" % (name, a, b))
    measured = ("%d (key, configuration) pairs compared, %d not applicable, "
                "%d disagreed" % (compared, skipped, len(mismatches)))
    if mismatches:
        return CheckResult(
            "defaults and omissions", FAILS, requirement, measured,
            "two spellings of one architecture produce two labels",
            "; ".join(sorted(set(mismatches))[:6]))
    if not compared:
        return CheckResult(
            "defaults and omissions", COULDNT_CHECK, requirement, measured,
            "the family declares no parameter with a default, so there are "
            "two spellings of nothing",
            "what would settle it: a family with at least one defaulted "
            "parameter, or a declaration that it has none by design")
    return CheckResult(
        "defaults and omissions", PASSES, requirement, measured,
        "every defaulted key canonicalises to one label either way")


# ---------------------------------------------------------------- check (c)
def check_ceiling(ctx):
    """`ceiling()` is never below the recall the family's own search achieved."""
    requirement = (
        "`ceiling()` must return exact k-NN over everything the routing can "
        "reach, and must therefore be >= the family's measured recall at "
        "every configuration. A ceiling below its own recall means the "
        "decomposition is lying, and every routing-loss figure in every "
        "report depends on it.")
    rows, violations = [], []
    for config in ctx.configs:
        cand = ctx.search(config)
        ids = getattr(cand, "ids", cand)
        recall = _recall(ids, ctx.gt)
        ceil = _recall(ctx.ceiling(config), ctx.gt)
        rows.append((config.label, recall, ceil))
        if ceil + 1e-9 < recall:
            violations.append("%s: ceiling %.4f < recall %.4f"
                              % (config.label, ceil, recall))
    ceils = [c for _, _, c in rows]
    measured = ("%d configurations; ceiling recall %.4f..%.4f, "
                "search recall %.4f..%.4f"
                % (len(rows), min(ceils), max(ceils),
                   min(r for _, r, _ in rows), max(r for _, r, _ in rows)))
    if violations:
        return CheckResult("ceiling", FAILS, requirement, measured,
                           "the family returned neighbours its own routing "
                           "says are unreachable",
                           "; ".join(violations[:4]))
    full = [c for c in ceils if abs(c - 1.0) < 1e-9]
    meaning = ("routing loss is well defined at every configuration"
               + (" and is zero by measurement at %d of %d (this family "
                  "reaches everything there)" % (len(full), len(ceils))
                  if full else ""))
    return CheckResult("ceiling", PASSES, requirement, measured, meaning)


# ---------------------------------------------------------------- check (d)
def check_routing_loss_invariant(ctx):
    """The same partition returns the same ceiling under every index algorithm."""
    requirement = (
        "Routing loss is a property of the partition, not of the index. Four "
        "algorithms over one partition must return the same ceiling ids -- if "
        "they do not, the decomposition is attributing index loss to routing "
        "or the reverse. Task 034 observed this for the shipped families; "
        "here it is a requirement.")
    groups: Dict[Any, List[Config]] = {}
    for config in ctx.configs:
        groups.setdefault(_partition_key(config), []).append(config)
    comparable = {k: v for k, v in groups.items() if len(v) > 1}
    if not comparable:
        return CheckResult(
            "routing loss is index-invariant", COULDNT_CHECK, requirement,
            "%d partition(s), none with more than one index algorithm"
            % len(groups),
            "the family produced no two configurations sharing a partition",
            "what would settle it: a family whose `configs()` crosses its "
            "partition with the `index` axis, which `index_combinations` "
            "does for a family that declares the index parameters")
    problems, checked = [], 0
    for key, configs in sorted(comparable.items(), key=lambda kv: str(kv[0])):
        base = ctx.ceiling(configs[0])
        for other in configs[1:]:
            checked += 1
            got = ctx.ceiling(other)
            if np.shape(base) != np.shape(got) or not np.array_equal(base, got):
                moved = (int(np.count_nonzero(np.asarray(base)
                                              != np.asarray(got)))
                         if np.shape(base) == np.shape(got) else -1)
                problems.append(
                    "%s vs %s: %s"
                    % (configs[0].label, other.label,
                       ("%d ceiling ids differ" % moved) if moved >= 0
                       else "ceiling shapes differ"))
    measured = ("%d partition(s) with >1 index algorithm, %d comparisons"
                % (len(comparable), checked))
    if problems:
        return CheckResult(
            "routing loss is index-invariant", FAILS, requirement, measured,
            "the index changed what the routing can reach, which it cannot",
            "; ".join(problems[:4]))
    return CheckResult(
        "routing loss is index-invariant", PASSES, requirement, measured,
        "every index algorithm over one partition reaches the same vectors")


# ---------------------------------------------------------------- check (e)
def check_determinism(ctx):
    """With `deterministic=True`, two builds produce byte-identical state."""
    requirement = (
        "With the declared `deterministic` flag set, two builds from the same "
        "(vectors, config, seed) on one machine must produce byte-identical "
        "emitted state. The cross-environment half of the contract -- "
        "identical decisions and scored floats within a couple of ulps -- is "
        "`docs/STATE.md` and is not decidable here.")
    table = parameter_table(ctx.family)
    if "deterministic" not in table:
        return CheckResult(
            "determinism", COULDNT_CHECK, requirement,
            "the family declares no `deterministic` key", "",
            "what would settle it: declare `deterministic` with role BUILD, "
            "as the three shipped families do")
    config = _pick(ctx.configs, prefer="hnsw")
    params = dict(config.params)
    params["deterministic"] = True
    try:
        det = Config.make(ctx.family, params)
    except ParameterError as e:
        return CheckResult("determinism", COULDNT_CHECK, requirement,
                           "could not construct a deterministic config", "",
                           "%s: %s" % (type(e).__name__, e))
    digests = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in (0, 1):
            built = ctx.model.build(ctx.x, det, seed=SEED)
            st = ctx.model.state(built, ctx.q, K, det, ctx.gt, SEED)
            path = os.path.join(tmp, "run%d.npz" % i)
            S.write_state(path, st)
            with open(path, "rb") as fh:
                import hashlib
                digests.append(hashlib.sha256(fh.read()).hexdigest())
    same = digests[0] == digests[1]
    measured = ("two builds of %s: sha256 %s and %s"
                % (det.label, digests[0][:12], digests[1][:12]))
    if not same:
        return CheckResult(
            "determinism (this machine)", FAILS, requirement, measured,
            "a build declared deterministic is not reproducible on one "
            "machine, so no artifact it produces can be compared to another",
            "the two emitted states differ; `corpora/compare_state.py` names "
            "the differing columns")
    return CheckResult(
        "determinism (this machine)", PASSES, requirement, measured,
        "byte-identical within this environment")


def check_determinism_across_environments(ctx):
    """The half of the state contract one machine cannot answer.

    Reported as its own couldn't-check rather than folded into the sentence
    above. `docs/STATE.md` is two claims, not one, and a suite that answered
    the easy one and mentioned the hard one in passing would be rounding a
    couldn't-check up to a pass.
    """
    requirement = (
        "`docs/STATE.md` is a two-part contract: byte-identical **within** an "
        "environment, and identical decisions with scored floats within a "
        "couple of ulps **across** environments. The second is a claim about "
        "two machines and cannot be decided on one.")
    return CheckResult(
        "determinism (across environments)", COULDNT_CHECK, requirement,
        "not measurable here: one machine, one BLAS, one faiss build",
        "the family may or may not reproduce elsewhere; this run says "
        "nothing either way, and that is not a pass",
        "what would settle it: build the same configuration on a second "
        "environment -- `oneground pod` runs one -- and compare with "
        "`corpora/compare_state.py --cross-environment`, which folds the "
        "scored columns to a ulp tolerance and requires the ordering "
        "columns to be identical")


def _pick(configs, prefer="hnsw"):
    """A representative config, preferring one index algorithm."""
    for c in configs:
        if c.params.get("index", "hnsw") == prefer:
            return c
    return configs[0]


# ---------------------------------------------------------------- check (f)
def check_footprint_is_measured(ctx):
    """`footprint()` reports what was built, not a formula over n and dim."""
    requirement = (
        "`footprint()` must report `index_bytes` derived from the built "
        "artifact, not computed from vector count and dimension. A formula "
        "cannot see quantisation: measured against an estimate, a single "
        "IVF-PQ index came out 61x smaller than the estimate said (task 034), "
        "and a family reporting only the estimate would have reported the "
        "wrong number with no way to notice.")
    by_algorithm: Dict[str, List[Tuple[str, Any]]] = {}
    missing = []
    for config in ctx.configs:
        fp = ctx.footprint(config)
        algorithm = config.params.get("index", "hnsw")
        if fp.index_bytes is None:
            missing.append(config.label)
        by_algorithm.setdefault(algorithm, []).append((config.label, fp))
    if missing:
        return CheckResult(
            "footprint is measured", FAILS, requirement,
            "%d of %d configurations report no `index_bytes`"
            % (len(missing), len(ctx.configs)),
            "the family reports only an estimate, so its memory figure "
            "cannot be reconciled with anything that was built",
            "; ".join(missing[:4]))

    # A formula over (n, dim) cannot distinguish a flat index from a
    # quantised one. If the measured figure does, it was measured.
    sizes = {a: int(np.median([fp.index_bytes for _, fp in v]))
             for a, v in by_algorithm.items()}
    estimates = {a: int(np.median([fp.memory_bytes for _, fp in v]))
                 for a, v in by_algorithm.items()}
    measured = ("index_bytes by algorithm: "
                + ", ".join("%s %.1f MB" % (a, sizes[a] / 1e6)
                            for a in sorted(sizes))
                + "; est_memory_bytes: "
                + ", ".join("%s %.1f MB" % (a, estimates[a] / 1e6)
                            for a in sorted(estimates)))
    if len(sizes) < 2:
        return CheckResult(
            "footprint is measured", COULDNT_CHECK, requirement, measured,
            "only one index algorithm was exercised, so a measured figure "
            "and a formula would look the same",
            "what would settle it: a family whose configs cross the `index` "
            "axis, giving at least a flat and a quantised build to compare")
    if len(set(sizes.values())) == 1:
        return CheckResult(
            "footprint is measured", FAILS, requirement, measured,
            "the reported size is identical across index algorithms that "
            "store different things, which is what a formula over n and dim "
            "would produce",
            "a quantised index stores codes, not vectors; if it reports the "
            "same bytes as a flat index the figure did not come from the "
            "artifact")
    quantised = sizes.get("ivf_pq")
    flat = sizes.get("flat")
    ratio = ("; flat/ivf_pq = %.1fx" % (flat / quantised)
             if quantised and flat else "")
    return CheckResult(
        "footprint is measured", PASSES, requirement, measured + ratio,
        "the figure tracks what was actually built: it changes with the "
        "algorithm, which a formula over vector count and dimension cannot")


# ---------------------------------------------------------------- check (g)
def check_state_is_emitted_and_renders(ctx):
    """State meets its contract and carries every column the lab draws from."""
    requirement = (
        "`state()` must return a `ModelState` that satisfies "
        "`state.contract_violations` against the family's own footprint, and "
        "must carry every column the lab's views read. A family that cannot "
        "be drawn is usable and invisible.")
    config = _pick(ctx.configs, prefer="hnsw")
    try:
        st = ctx.model.state(ctx.build(config), ctx.q, K, config, ctx.gt, SEED)
    except Exception as e:                                     # noqa: BLE001
        return CheckResult(
            "state is emitted and renders", FAILS, requirement,
            "state() raised on %s" % config.label,
            "the family emits no state at all, so it can never be drawn",
            "%s: %s" % (type(e).__name__, e))
    violations = S.contract_violations(st, ctx.footprint(config))
    head = S.header(st)
    columns = set(head.get("columns") or {})
    absent = [c for c in LAB_REQUIRED_COLUMNS if c not in columns]
    measured = ("%d columns emitted, %d contract violations, %d of %d "
                "lab-required columns present"
                % (len(columns), len(violations),
                   len(LAB_REQUIRED_COLUMNS) - len(absent),
                   len(LAB_REQUIRED_COLUMNS)))
    if violations:
        return CheckResult(
            "state is emitted and renders", FAILS, requirement, measured,
            "the emitted state contradicts what the family measured",
            "; ".join(violations[:4]))
    if absent:
        return CheckResult(
            "state is emitted and renders", FAILS, requirement, measured,
            "the lab's views read these columns without asking, so this "
            "family's runs fail at draw time rather than at build time",
            "missing: %s" % ", ".join(absent))
    return CheckResult(
        "state is emitted and renders", PASSES, requirement, measured,
        "the state contract holds and every column the ground and trace "
        "views read is present")


# ---------------------------------------------------------------- check (h)
def check_refusals_not_crashes(ctx):
    """An impossible configuration is refused with a reason, not crashed on."""
    requirement = (
        "A configuration the family cannot build -- more shards than "
        "vectors, more regions than the sample -- must be refused with a "
        "`ParameterError` naming what is wrong. A crash aborts a sweep; a "
        "refusal drops one row and the sweep reports it (task 034).")
    table = parameter_table(ctx.family)
    impossible = []
    for key in ("shards", "centroids", "nlist"):
        if key in table and table[key].role == PARAMETER:
            impossible.append((key, ctx.x.shape[0] + 1))
    if not impossible:
        return CheckResult(
            "refusals, not crashes", COULDNT_CHECK, requirement,
            "the family declares no partition-size knob this suite knows how "
            "to make impossible", "",
            "what would settle it: a family declaring `shards`, `centroids` "
            "or `nlist`, or a hand-written impossible configuration in its "
            "own tests")
    outcomes, bad = [], []
    for key, value in impossible:
        # The knob must BELONG to the configuration under test, or the refusal
        # that comes back is about belonging and says nothing about size --
        # `nlist` set on an HNSW config is refused for being an IVF setting,
        # and a check that accepted that would pass without testing anything.
        param = table[key]
        base = next((c for c in ctx.configs
                     if _belonging_satisfied(c, param)), None)
        if base is None:
            outcomes.append("%s: no configuration this suite built can carry "
                            "it" % key)
            continue
        params = dict(base.params)
        params[key] = value
        try:
            config = Config.make(ctx.family, params)
        except ParameterError as e:
            outcomes.append("%s=%d refused at config: %s"
                            % (key, value, str(e)[:60]))
            continue
        except Exception as e:                                 # noqa: BLE001
            bad.append("%s=%d: Config.make raised %s, not ParameterError: %s"
                       % (key, value, type(e).__name__, e))
            continue
        try:
            ctx.model.build(ctx.x, config, seed=SEED)
            bad.append("%s=%d: built without refusing" % (key, value))
        except ParameterError as e:
            outcomes.append("%s=%d refused at build: %s"
                            % (key, value, str(e)[:60]))
        except Exception as e:                                 # noqa: BLE001
            bad.append("%s=%d: build raised %s, not ParameterError: %s"
                       % (key, value, type(e).__name__, str(e)[:80]))
    measured = "%d impossible configuration(s) tried" % len(impossible)
    if bad:
        return CheckResult(
            "refusals, not crashes", FAILS, requirement, measured,
            "an impossible configuration aborts the sweep instead of being "
            "dropped from it", "; ".join(bad[:4]))
    return CheckResult(
        "refusals, not crashes", PASSES, requirement, measured,
        "; ".join(outcomes[:3]))


CHECKS = (
    check_parameter_table,
    check_defaults_and_omissions,
    check_ceiling,
    check_routing_loss_invariant,
    check_determinism,
    check_determinism_across_environments,
    check_footprint_is_measured,
    check_state_is_emitted_and_renders,
    check_refusals_not_crashes,
)


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------

def run_conformance(family, model=None, corpus=None, verbose=True):
    """Every check against one family. Returns `[CheckResult]`.

    Reports rather than raises: one family failing a check is a finding about
    that family, and the remaining checks still have something to say.
    """
    model = model or models.get(family)
    x, q = corpus if corpus is not None else synthetic_corpus()
    gt = exact_knn(x, q, K)
    ctx = _Ctx(family=family, model=model, x=x, q=q, gt=gt)

    def say(msg):
        if verbose:
            print(msg, flush=True)

    with _recording_reads() as seen:
        try:
            ctx.configs, ctx.notes = _covering_configs(family, model)
        except Exception as e:                                 # noqa: BLE001
            return [CheckResult(
                "configs", FAILS,
                "`configs(space)` must yield at least one labelled Config.",
                "configs() raised", "the family cannot be swept at all",
                "%s: %s" % (type(e).__name__, e))]
        if not ctx.configs:
            return [CheckResult(
                "configs", FAILS,
                "`configs(space)` must yield at least one labelled Config.",
                "0 configurations", "the family cannot be swept at all", "")]
        # Exercise the whole protocol once so the read-recording is complete
        # before the parameter-table check reads it.
        for config in ctx.configs:
            ctx.search(config)
            ctx.ceiling(config)
            ctx.footprint(config)
        ctx.reads = set(seen.get(family, ()))

    results = []
    for check in CHECKS:
        try:
            results.append(check(ctx))
        except Exception as e:                                 # noqa: BLE001
            results.append(CheckResult(
                check.__name__.replace("check_", "").replace("_", " "),
                FAILS, "the check must be able to run against any family.",
                "the check itself raised",
                "this is a defect in the suite or a family that breaks the "
                "protocol in a way the check did not anticipate",
                "%s: %s" % (type(e).__name__, e)))
    return results


def format_results(family, results, width=78):
    lines = ["", "=" * width, "family: %s" % family, "=" * width]
    for r in results:
        lines.append("")
        lines.append("  [%s] %s" % (OUTCOME_LABEL[r.outcome], r.check))
        if r.measured:
            lines.append("      measured:    %s" % r.measured)
        if r.meaning:
            lines.append("      means:       %s" % r.meaning)
        if r.outcome != PASSES:
            lines.append("      requirement: %s" % r.requirement)
        if r.detail:
            lines.append("      detail:      %s" % r.detail)
    counts = _counts(results)
    lines.append("")
    lines.append("  %s: %d passes, %d fails, %d couldn't-check"
                 % (family, counts[PASSES], counts[FAILS],
                    counts[COULDNT_CHECK]))
    return "\n".join(lines)


def _counts(results):
    out = {PASSES: 0, FAILS: 0, COULDNT_CHECK: 0}
    for r in results:
        out[r.outcome] = out.get(r.outcome, 0) + 1
    return out


def load_module_family(path):
    """`(name, MODEL)` from a family's `model.py`, without registering it.

    A contributed family is a file before it is a registry entry, and the
    suite has to be runnable at that point or it is not a contribution gate.
    Importing the module runs its `declare_parameters`, which is what puts its
    parameter table where the checks can read it.
    """
    import importlib.util
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location(
        "oneground_family_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = getattr(module, "MODEL", None)
    name = getattr(module, "NAME", None) or getattr(model, "name", None)
    if model is None or name is None:
        raise AttributeError(
            "%s defines no MODEL and NAME. A family module exports `NAME` "
            "and `MODEL = YourFamily()`." % path)
    return name, model


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(
        prog="oneground models conformance",
        description="Run the family conformance suite against one family or "
                    "all registered families.")
    ap.add_argument("--family", action="append", default=None,
                    help="only this family; repeatable. Default: all "
                         "registered.")
    ap.add_argument("--module", action="append", default=None,
                    help="path to an unregistered family's model.py; "
                         "repeatable. This is how a contribution is checked "
                         "before it is registered.")
    ap.add_argument("--quiet", action="store_true",
                    help="print only the per-family summary line")
    args = ap.parse_args(argv)

    loaded = []
    for path in (args.module or ()):
        try:
            loaded.append(load_module_family(path))
        except Exception as e:                                 # noqa: BLE001
            print("cannot load %s: %s: %s" % (path, type(e).__name__, e))
            return 2

    wanted = args.family or ([] if loaded else models.families())
    unknown = [f for f in wanted if f not in models.REGISTRY]
    if unknown:
        print("unknown family: %s. Registered: %s. An unregistered family is "
              "run with --module path/to/model.py"
              % (", ".join(unknown), ", ".join(models.families())))
        return 2
    targets = [(f, None) for f in wanted] + loaded

    print("family conformance: %d family(ies), %d checks each, on a "
          "synthetic %d x %d corpus"
          % (len(targets), len(CHECKS), N_BASE, DIM))
    total = {PASSES: 0, FAILS: 0, COULDNT_CHECK: 0}
    for family, model in targets:
        results = run_conformance(family, model=model,
                                  verbose=not args.quiet)
        if args.quiet:
            c = _counts(results)
            print("  %-20s %d passes, %d fails, %d couldn't-check"
                  % (family, c[PASSES], c[FAILS], c[COULDNT_CHECK]))
        else:
            print(format_results(family, results))
        for key, value in _counts(results).items():
            total[key] = total.get(key, 0) + value

    print("")
    print("total: %d passes, %d FAILS, %d couldn't-check"
          % (total[PASSES], total[FAILS], total[COULDNT_CHECK]))
    if total[FAILS]:
        print("a failure is a finding about the family it names. It is not a "
              "reason to weaken the check.")
    return 1 if total[FAILS] else 0


if __name__ == "__main__":                                    # pragma: no cover
    sys.exit(main())
