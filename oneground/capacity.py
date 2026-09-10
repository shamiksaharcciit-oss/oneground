"""Capacity arithmetic from a declared corpus.

Tier 2 knows two numbers about the user's corpus — `size_now` and `dimension` —
and nothing else. From those it can say how much memory each architecture
would need, how many nodes that is at a stated budget, and what those nodes
cost. That is arithmetic, not measurement, and every value this module
produces carries `kind: derived_from_declared`.

WHERE THE STRUCTURE COMES FROM, AND WHAT THAT COSTS
---------------------------------------------------
For a family whose layout does not depend on what the vectors mean, the
structure is obtained by building it on a **synthetic sample** at the declared
dimension and asking `footprint()`. Memory then scales linearly: bytes are the
vector payload plus an HNSW graph term, both proportional to stored vectors.

That is exact for `single_node_hnsw` (amplification is 1.0 by construction)
and for `hash_sharded` (a hash spreads vectors evenly regardless of what they
mean). It is **not** exact for `semantic_sharded`, which is therefore not
built at all — its fan-out and shard count are read from the configuration,
where they are stated rather than derived, and its amplification is refused:

    semantic_sharded replicates a vector into every region whose centroid is
    within (1+epsilon) of its nearest. How many regions that is depends on how
    the corpus clusters -- which is the geometry Tier 1 measures and Tier 2
    does not have. On isotropic random vectors, which is what a synthetic
    sample is, the answer is close to uniform and bears no relation to what
    real text embeddings do.

So for that family the amplification from the synthetic sample is reported as
`couldnt_check`, and if a fixture analogy was chosen its **measured**
amplification is offered instead, labelled as the fixture's own. An arithmetic
result that depends on unmeasured geometry is not a result.
"""

import math

import numpy as np

from . import models as models_pkg
from .models.base import estimate_memory_bytes

DERIVED = "derived_from_declared"
COULDNT_CHECK = "couldnt_check"

# Vectors in the synthetic sample. Large enough for k-means to produce the
# configured number of regions and for the structural numbers to settle,
# small enough that Tier 2 stays a seconds-long command.
SYNTHETIC_SAMPLE = 4096

# Families whose replication depends on the corpus's geometry rather than on
# its configuration. For these, a synthetic sample cannot answer.
GEOMETRY_DEPENDENT = {"semantic_sharded"}


def synthetic_sample(dimension, n=SYNTHETIC_SAMPLE, seed=0):
    """Unit-norm isotropic vectors at the declared dimension.

    Isotropic on purpose: this sample exists to exercise a family's structure,
    not to stand in for the user's corpus. Anything that depends on how it
    clusters is refused rather than read off it.
    """
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(int(n), int(dimension))).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    return np.ascontiguousarray(x)


def _structure(family, config, dimension, seed=0, log_fn=None):
    """(footprint, note) from one family built on a synthetic sample."""
    model = models_pkg.get(family)
    sample = synthetic_sample(dimension, seed=seed)
    if log_fn:
        log_fn(f"capacity: {family} structure on {len(sample):,} synthetic "
               f"vectors, dim {dimension}")
    built = model.build(sample, dict(config), seed=seed)
    return model.footprint(built)


def for_family(family, config, declared, analogy_surface=None, seed=0,
               log_fn=None):
    """One family's capacity entry.

    `analogy_surface` is the chosen fixture's published `reference_results`
    when there is one, used only to offer a *measured* amplification for a
    geometry-dependent family, labelled as the fixture's.
    """
    size_now = int(declared["size_now"])
    dim = int(declared["dimension"])
    cfg = dict(config)
    M = int(cfg.get("M", 32))

    if family in GEOMETRY_DEPENDENT:
        # Not built at all. Its amplification is refused below, and building
        # it would run a 256-region k-means over isotropic noise to produce a
        # number this function then throws away -- work whose only visible
        # effect is a faiss warning that the sample is too small to cluster.
        # Fan-out and shard count come from the configuration, where they are
        # stated rather than derived.
        fanout = float(cfg.get("probe", 1))
        shards = int(cfg.get("centroids", 1))
        basis = (f"fan-out and shards from the configuration; scaled to the "
                 f"declared size_now {size_now:,}")
    else:
        fp = _structure(family, cfg, dim, seed=seed, log_fn=log_fn)
        fanout, shards = fp.fanout, fp.shards
        basis = (f"structure from {SYNTHETIC_SAMPLE:,} synthetic vectors at "
                 f"dim {dim}; scaled to the declared size_now {size_now:,}")

    entry = {
        "family": family,
        "config": cfg,
        "kind": DERIVED,
        "basis": basis,
        "fanout": fanout,
        "shards": shards,
    }

    if family in GEOMETRY_DEPENDENT:
        # The number the synthetic sample produces is arithmetic over noise.
        entry["amplification"] = (
            f"{COULDNT_CHECK}: {family} replicates by how the corpus clusters, "
            "and this run has no corpus to cluster. A synthetic sample is "
            "isotropic, so its replication says nothing about real embeddings.")
        measured = (analogy_surface or {}).get(family, {}).get(
            "storage_amplification")
        if measured is not None:
            entry["amplification_from_analogy"] = {
                "value": float(measured),
                "kind": "declared",
                "note": ("measured on the analogy fixture, not on your "
                         "corpus. Shown so the arithmetic below has a number "
                         "to stand on; it is the fixture's number."),
            }
            stored = int(round(size_now * float(measured)))
        else:
            entry["stored_vectors"] = entry["amplification"]
            entry["memory_bytes"] = entry["amplification"]
            entry["note"] = ("no analogy fixture supplied a measured "
                             "amplification, so there is no defensible "
                             "multiplier and the storage arithmetic is not "
                             "attempted.")
            return entry
    else:
        entry["amplification"] = float(fp.amplification)
        stored = int(round(size_now * float(fp.amplification)))

    entry["stored_vectors"] = stored
    entry["memory_bytes"] = estimate_memory_bytes(stored, dim, M)
    entry["memory_gb"] = entry["memory_bytes"] / (1024 ** 3)
    entry["memory_note"] = ("an estimate: vector payload plus an HNSW graph "
                            "term, not an allocator's real behaviour")
    return entry


def nodes_needed(memory_bytes, memory_budget_gb, headroom=0.70):
    """How many nodes hold `memory_bytes` at a per-node budget.

    `headroom` is the share of a node's memory the index may occupy; the rest
    is the process, the OS and the space an index needs to be rebuilt in. A
    node filled to 100% is a node that cannot compact.
    """
    if not memory_budget_gb:
        return None
    usable = float(memory_budget_gb) * (1024 ** 3) * float(headroom)
    if usable <= 0:
        return None
    return max(1, int(math.ceil(memory_bytes / usable)))


def plan(declared, constraints, families, configs=None, prices=None,
         analogy_surface=None, seed=0, log_fn=None, error_band=None):
    """The whole Tier-2 capacity block.

    Returns a dict per family plus a `note` making the tier explicit. Never
    returns a verdict: the budget line carries the cost and the threshold and
    an outcome of couldnt_check, because the input is declared.
    """
    configs = configs or {}
    memory_budget_gb = (constraints or {}).get("memory_budget_gb")
    out = {"kind": DERIVED, "families": {},
           "declared": {"size_now": int(declared["size_now"]),
                        "dimension": int(declared["dimension"])},
           "note": ("Tier 2. Every number here is arithmetic over what you "
                    "declared, not a measurement of your corpus. No verdict "
                    "can be issued from it.")}

    for family in families:
        cfg = configs.get(family) or _default_config(family)
        entry = for_family(family, cfg, declared,
                           analogy_surface=analogy_surface, seed=seed,
                           log_fn=log_fn)
        mem = entry.get("memory_bytes")
        if isinstance(mem, int) and memory_budget_gb:
            entry["nodes_at_memory_budget"] = nodes_needed(
                mem, memory_budget_gb)
            entry["memory_budget_gb"] = memory_budget_gb
        elif memory_budget_gb:
            entry["nodes_at_memory_budget"] = (
                f"{COULDNT_CHECK}: no defensible memory estimate for this "
                "family without a corpus")
        out["families"][family] = entry

    if prices is not None:
        _add_cost(out, prices, memory_budget_gb, error_band)
    return out


def _default_config(family):
    """The configuration a family is sized at when the file names none.

    These are the same reference configurations the fixtures publish, so a
    Tier-2 number and a Tier-1 number describe the same architecture.
    """
    if family == "single_node_hnsw":
        return {"M": 32, "efConstruction": 200, "efSearch": 128}
    if family == "semantic_sharded":
        return {"centroids": 256, "epsilon": 0.2, "probe": 2, "M": 32,
                "efSearch": 96}
    if family == "hash_sharded":
        return {"shards": 3, "M": 32, "efSearch": 96}
    return {"M": 32}


def _add_cost(out, prices, memory_budget_gb, error_band=None):
    """Cost per family from the price table, with its error band.

    `size_and_cost` does its own node sizing -- it picks the cheapest node type
    in the table that can hold the index, which may not be the size the user
    named. Both numbers are kept: `nodes_at_memory_budget` is how many nodes of
    the size the user said they would run, and the cost block is the cheapest
    way the table can hold it. They answer different questions and a reader
    should see both.
    """
    from .cost import DEFAULT_ERROR_BAND, size_and_cost
    band = DEFAULT_ERROR_BAND if error_band is None else float(error_band)
    for family, entry in out["families"].items():
        mem = entry.get("memory_bytes")
        if not isinstance(mem, int):
            entry["cost"] = (f"{COULDNT_CHECK}: no memory estimate for this "
                             "family without a corpus")
            continue
        cost, why = size_and_cost({"est_memory_bytes": mem}, prices,
                                  error_band=band,
                                  memory_budget_gb=memory_budget_gb)
        if cost is None:
            entry["cost"] = f"{COULDNT_CHECK}: {why}"
        else:
            entry["cost"] = dict(cost.as_dict() if hasattr(cost, "as_dict")
                                 else cost)
            entry["cost"]["kind"] = DERIVED
            entry["cost"]["note"] = (
                "derived from the declared size_now and dimension, priced "
                "against a declared list-price table. The budget verdict a "
                "Tier-1 run would issue from this is couldnt_check here, "
                "because the input is declared.")


def epsilon_sweep(declared, epsilons, analogy_surface=None, seed=0):
    """Storage at each epsilon for semantic_sharded.

    Every entry is couldnt_check unless the analogy fixture published a
    measured amplification at that epsilon: how far the closure reaches is a
    property of the corpus's geometry, and Tier 2 has no corpus.
    """
    size_now = int(declared["size_now"])
    rows = []
    published = (analogy_surface or {}).get("epsilon_sweep") or {}
    for eps in epsilons:
        measured = published.get(str(eps)) or published.get(eps)
        if measured is None:
            rows.append({
                "epsilon": eps,
                "amplification": (
                    f"{COULDNT_CHECK}: the epsilon closure's reach is a "
                    "property of how your corpus clusters, which Tier 2 has "
                    "not measured"),
                "kind": DERIVED})
        else:
            rows.append({
                "epsilon": eps,
                "amplification": float(measured),
                "stored_vectors": int(round(size_now * float(measured))),
                "kind": "declared",
                "note": "amplification measured on the analogy fixture"})
    return rows
