"""`oneground simulate <requirements.yaml>` — run the sweep, emit the table.

Takes a characterized sample and measures every configuration of every
requested family against exact k-NN ground truth, producing one row per
configuration:

    recall@1 / @10 / @100      what the architecture actually returns
    ceiling@10                 what its routing makes reachable, searched exactly
    routing_loss / index_loss  the decomposition (see below)
    inv_ratio@10               how close the returned neighbours are, not just
                               whether they are the right ones
    storage_amplification      stored copies per base vector
    est_memory_bytes           estimated, and labelled so everywhere
    fanout                     shards touched per query
    build_seconds / query_seconds

**This command measures. It does not decide.** There is no "meets", no
"fails", no recommendation and no ranking by goodness — the table is sorted by
family then recall@10 so it reads consistently, and that is the whole of the
opinion in it. Turning measurements into a verdict against a user's
constraints is the report's job (task 010), and keeping the two apart is what
lets the numbers be reused by a decision this command never saw.

The decomposition
-----------------
Every row carries its ceiling, so the gap from perfect recall always splits:

    routing_loss = 1 - ceiling@10      neighbours in shards never probed.
                                       No index tuning recovers these.
    index_loss   = ceiling@10 - recall@10   reachable, and not returned.
                                       efSearch might.

A recall number without this split cannot tell you whether to tune or to
re-architect, which is the question the whole tool exists to answer.

Budgets
-------
`simulate.budget.max_configs` truncates the sweep and `max_minutes` stops it.
Neither silently drops work: the configurations not run are listed in
`simulate_info.json` as `couldnt_check: budget` with the rule that dropped
them, because a sweep that quietly measured less than it was asked to is a
sweep whose absence of a row means nothing.
"""

import json
import os
import platform
import time

import numpy as np

from .. import intake
from ..models import Config, ConfigSpace, UnknownFamily, get as get_model
from ..models.base import ParameterError
from ..receipts import (library_versions, round_floats, sha256_file,
                        write_json_stable, write_manifest)
from ..sample import loaders
from ..truth import exact_knn

COULDNT_CHECK = "couldnt_check"

SIMULATE_FILES = ["simulate.json", "simulate_info.json"]

# The receipts `characterize` wrote, which the manifest must keep listing.
CHARACTERIZE_FILES = ["characterization.json", "sample_ids.json",
                      "queries_ids.json", "build_info.json"]


class SimulateError(RuntimeError):
    """The run cannot proceed. The message says what to do about it."""


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------

def recall_at(pred_ids, gt_ids, k):
    """Fraction of the top-k true neighbours that were returned.

    `-1` entries in `pred_ids` are padding for a search that found fewer than
    k; they count as misses, which is correct -- nothing was returned there.
    """
    gt = gt_ids[:, :k]
    pred = pred_ids[:, :k]
    hits = sum(len(set(p[p >= 0].tolist()) & set(g.tolist()))
               for p, g in zip(pred, gt))
    return hits / (gt.shape[0] * gt.shape[1])


def inverse_ratio_at(pred_scores, gt_scores, k):
    """Mean over queries of (k-th true distance) / (k-th returned distance).

    Recall asks whether the right ids came back. This asks how *close* what
    came back was -- an architecture that misses the true 10th neighbour but
    returns something almost as near is not as wrong as one that returns
    something unrelated, and recall cannot tell them apart.

    Vectors are L2-normalized and scored by inner product, so the Euclidean
    distance is recovered as

        d = sqrt(max(0, 2 - 2 * ip))

    and the value reported is d_true_k / d_returned_k. Because a returned
    neighbour is never nearer than the true k-th, this lies in [0, 1] and
    equals 1.0 exactly when the k-th returned neighbour is as near as the true
    k-th. It is 1/Ratio@k in the usual formulation, reported in that direction
    so that -- like recall -- higher is better and 1.0 is perfect.

    Two edge cases, both resolved toward honesty:
      * a query with fewer than k results contributes 0.0, not a skip
      * a true k-th distance of 0 (duplicate vectors) contributes 1.0 only if
        the returned distance is also 0, else 0.0
    """
    n_q = gt_scores.shape[0]
    out = np.zeros(n_q, dtype=np.float64)
    for i in range(n_q):
        gs = gt_scores[i, :k]
        ps = pred_scores[i, :k]
        if len(ps) < k or not np.isfinite(ps[k - 1]):
            continue                                  # fewer than k returned
        d_true = float(np.sqrt(max(0.0, 2.0 - 2.0 * float(gs[k - 1]))))
        d_pred = float(np.sqrt(max(0.0, 2.0 - 2.0 * float(ps[k - 1]))))
        if d_pred <= 0.0:
            out[i] = 1.0 if d_true <= 0.0 else 0.0
        else:
            out[i] = min(1.0, d_true / d_pred)
    return float(out.mean())


# --------------------------------------------------------------------------
# the sweep
# --------------------------------------------------------------------------

def _space_from(req, seed):
    sim = req.data.get("simulate") or {}
    return ConfigSpace(
        seed=seed,
        node_counts=tuple(sim.get("node_counts") or (1, 3, 5)),
        grid=dict(sim.get("grid") or {}),
        include=list(sim.get("include") or []),
    )


def _pinned_first(model, space, family):
    """Explicitly listed configs first, generated grid after.

    A budget truncates the tail, so the order decides what survives. Anything
    the requirements file named by hand -- the fixture's two published
    reference configurations arrive that way -- is what the run most needs to
    produce, and it must not be the thing a `max_configs` drops because a
    generated grid happened to sort ahead of it.

    A family's `configs()` already emits `include` entries first; this asserts
    the property at the framework level rather than trusting three families to
    keep doing it, and it is stable for families that do.
    """
    cfgs = list(model.configs(space))
    pinned_labels = []
    for params in space.included_for(family):
        for c in cfgs:
            if all(str(c.params.get(k)) == str(v) for k, v in params.items()):
                if c.label not in pinned_labels:
                    pinned_labels.append(c.label)
                break
    if not pinned_labels:
        return cfgs
    by_label = {c.label: c for c in cfgs}
    head = [by_label[lbl] for lbl in pinned_labels]
    tail = [c for c in cfgs if c.label not in set(pinned_labels)]
    return head + tail


def plan_sweep(req, seed):
    """Every configuration the requirements file asks for, in family order.

    Returns (kept, dropped). `max_configs` truncates per family rather than
    globally, so a large first family cannot starve a later one of every row.
    """
    sim = req.data.get("simulate") or {}
    families = list(sim.get("families") or
                    ["single_node_hnsw", "semantic_sharded", "hash_sharded"])
    budget = sim.get("budget") or {}
    max_configs = budget.get("max_configs")
    space = _space_from(req, seed)

    kept, dropped = [], []
    per_family = None
    if max_configs:
        per_family = max(1, int(max_configs) // max(1, len(families)))

    for fam in families:
        try:
            model = get_model(fam)
        except UnknownFamily as e:
            raise SimulateError(str(e)) from None
        try:
            cfgs = _pinned_first(model, space, fam)
        except ParameterError as e:
            # Task 026: a grid or include naming a key the family does not
            # read is refused before anything is measured, not ignored.
            raise SimulateError(str(e)) from None
        if per_family is not None and len(cfgs) > per_family:
            for c in cfgs[per_family:]:
                dropped.append({
                    "config": c.label,
                    "reason": f"{COULDNT_CHECK}: budget",
                    "rule": (f"max_configs={max_configs} over {len(families)} "
                             f"families gives {per_family} per family; this "
                             f"config was at position "
                             f"{cfgs.index(c) + 1} of {len(cfgs)} in "
                             f"{fam}'s sweep order"),
                })
            cfgs = cfgs[:per_family]
        kept.extend((fam, c) for c in cfgs)
    return kept, dropped


def shard_depth_for(ks):
    """The per-shard candidate depth a sweep should use.

    Task 008 measured that `semantic_sharded`'s fixed depth of 30 caps
    recall@k: a query sees at most probe * depth distinct vectors, so
    recall@100 was bounded at probe * 0.30 and reported the constant instead
    of the architecture. Raising it to the largest k reported removes the cap
    from the metric while leaving the family's default -- and every published
    fixture value measured with it -- untouched.

    It is a run-level setting, not a swept dimension: it is derived from which
    ks the run reports, so every row in a run shares it. `simulate_info.json`
    records the value used, and config labels stay stable across runs so two
    sweeps of the same grid remain comparable row for row.
    """
    return max(30, max(ks))


def _cite_prediction(workdir):
    """`{"file", "sha256", "read"}` for a prediction in the workdir, or None.

    Read at the start of `run`, so the digest is of the file as it stood
    before anything was measured.
    """
    from ..proposals.prediction import PREDICTION_NAME
    path = os.path.join(workdir, PREDICTION_NAME)
    if not os.path.exists(path):
        return None
    return {"file": PREDICTION_NAME, "sha256": sha256_file(path),
            "read": "at the start of the run, before any configuration was "
                    "measured"}


def _with_shard_depth(config, depth):
    """A copy of `config` carrying `shard_depth`, with the label unchanged.

    The label is deliberately not recomputed. `shard_depth` is uniform across
    a run and recorded once in `simulate_info.json`; folding it into every
    label would churn every row id for a value that never varies within a run.
    """
    # Task 026: only a family that reads it. hash_sharded computes its own
    # depth and single_node_hnsw has no shards; the key used to be added to
    # both and ignored.
    if not config.accepts("shard_depth") or "shard_depth" in config.params:
        return config
    return Config(family=config.family,
                  params={**config.params, "shard_depth": int(depth)},
                  label=config.label)


def measure_config(model, config, base, queries, gt_ids, gt_scores, seed,
                   ks=(1, 10, 100), context=None, log_fn=log):
    """One row of the table. Every number here is measured, none inferred."""
    k_max = max(ks)
    config = _with_shard_depth(config, shard_depth_for(ks))
    built = model.build(base, config, seed, context=context)

    t0 = time.time()
    cand = model.search(built, queries, k_max, config)
    query_seconds = time.time() - t0

    ceil_ids = model.ceiling(built, queries, 10)
    fp = model.footprint(built)

    row = {
        "family": model.name,
        "config": config.label,
        "params": dict(config.params),
    }
    for k in ks:
        row[f"recall_at_{k}"] = recall_at(cand.ids, gt_ids, k)
    row["ceiling_at_10"] = recall_at(ceil_ids, gt_ids, 10)
    row["routing_loss"] = 1.0 - row["ceiling_at_10"]
    row["index_loss"] = row["ceiling_at_10"] - row["recall_at_10"]
    row["inv_ratio_at_10"] = inverse_ratio_at(cand.scores, gt_scores, 10)
    row.update(fp.as_dict())
    row["build_seconds"] = built.build_seconds
    row["query_seconds"] = query_seconds

    # Release the index before the next config is built: three families over a
    # 150k corpus otherwise hold several HNSW graphs at once on a 7.6 GB
    # laptop.
    built.state.clear()
    return row


# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------

def run(requirements_path, log_fn=log):
    t0 = time.time()
    req = intake.load(requirements_path)
    workdir = req.resolve(req.workdir)

    if not os.path.exists(os.path.join(workdir, "characterization.json")):
        raise SimulateError(
            f"no characterization in {workdir}. `simulate` measures "
            "architectures on a sample that has already been characterized; "
            f"run this first:\n\n    oneground characterize "
            f"{requirements_path}\n")

    # Task 026. A pre-registered prediction is cited by the run's own inputs:
    # its sha256 is read here, before any configuration is measured, and
    # written into simulate_info.json. A prediction written or edited after
    # this point does not match the citation, and the two-run verdict refuses
    # to judge it.
    cited_prediction = _cite_prediction(workdir)

    sim = req.data.get("simulate") or {}
    budget = sim.get("budget") or {}
    max_minutes = budget.get("max_minutes")
    gt_k = int(sim.get("ground_truth_k", 100))
    seed = req.seed

    # ---- the sample, exactly as characterize drew it ----
    vec_path = req.resolve(req.vectors.get("path"))
    if not vec_path:
        raise SimulateError(
            f"{requirements_path}: simulate needs corpus.sample.vectors.path; "
            "the text path is not supported by this command yet")
    log_fn(f"loading vectors {vec_path}")
    full = loaders.load_vectors(vec_path)
    idx = _sample_indices(workdir, len(full))
    base = np.ascontiguousarray(full[idx])
    if not req.vectors.get("normalized", False):
        base = loaders.normalize_rows(base)
    del full

    qcfg = dict(req.queries)
    qcfg["path"] = req.resolve(qcfg["path"])
    queries, _ = loaders.load_queries(qcfg)
    queries = loaders.normalize_rows(np.ascontiguousarray(queries))
    log_fn(f"{len(base):,} vectors, {len(queries):,} queries, dim "
           f"{base.shape[1]}")

    # ---- ground truth ----
    gt_ids, gt_scores = _ground_truth(workdir, base, queries, gt_k, log_fn)

    # ---- the sweep ----
    kept, dropped = plan_sweep(req, seed)
    log_fn(f"{len(kept)} configurations across "
           f"{len(set(f for f, _ in kept))} families"
           + (f", {len(dropped)} dropped by max_configs" if dropped else ""))

    rows, stopped_at = [], None
    # `is not None`, not truthiness: max_minutes: 0 means no time at all, and
    # a falsy check would silently turn the tightest budget into no budget.
    deadline = (t0 + float(max_minutes) * 60
                if max_minutes is not None else None)
    context_for = _centroid_cache(base, seed, log_fn)

    for i, (fam, config) in enumerate(kept, 1):
        if deadline and time.time() > deadline:
            stopped_at = i
            for f2, c2 in kept[i - 1:]:
                dropped.append({
                    "config": c2.label,
                    "reason": f"{COULDNT_CHECK}: budget",
                    "rule": f"max_minutes={max_minutes} elapsed before this "
                            "config was reached",
                })
            log_fn(f"budget: max_minutes={max_minutes} reached, "
                   f"{len(kept) - i + 1} configs not run")
            break
        log_fn(f"[{i}/{len(kept)}] {config.label}")
        rows.append(measure_config(get_model(fam), config, base, queries,
                                   gt_ids, gt_scores, seed,
                                   context=context_for(config),
                                   log_fn=log_fn))

    rows.sort(key=lambda r: (r["family"], -r["recall_at_10"]))

    # ---- receipts ----
    simulate_json = {
        "run": req.name,
        "schema": intake.SCHEMA_VERSION,
        "n_base": int(len(base)),
        "n_queries": int(len(queries)),
        "ground_truth_k": gt_k,
        "seed": seed,
        "rows": rows,
    }
    write_json_stable(os.path.join(workdir, "simulate.json"),
                      round_floats(simulate_json))

    versions, torch_info = library_versions(log=log_fn)
    info = {
        "kind": dict({"simulate.json": "receipt",
                      "simulate_info.json": "declared"},
                     **({cited_prediction["file"]: "declared"}
                        if cited_prediction else {})),
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "library_versions": versions,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "torch_cuda": torch_info["torch_cuda"],
        "cuda_device_name": torch_info["cuda_device_name"],
        "elapsed_seconds": time.time() - t0,
        "shard_depth": shard_depth_for((1, 10, 100)),
        "shard_depth_note": ("per-shard candidate depth used by every "
                             "sharded family in this run; max(30, largest k "
                             "reported). The family default is 30, which is "
                             "what published fixture values were measured "
                             "with."),
        "configs_planned": len(kept) + len(dropped),
        "configs_measured": len(rows),
        "dropped": dropped,
        "budget": dict(budget),
        "stopped_after_config": stopped_at,
        "requirements_file": {"path": os.path.abspath(requirements_path),
                              "sha256": sha256_file(requirements_path)},
        "prediction": cited_prediction,
    }
    write_json_stable(os.path.join(workdir, "simulate_info.json"), info)

    present = [f for f in CHARACTERIZE_FILES + SIMULATE_FILES
               + ([cited_prediction["file"]] if cited_prediction else [])
               if os.path.exists(os.path.join(workdir, f))]
    write_manifest(workdir, present)

    _table(simulate_json, dropped, workdir, time.time() - t0)
    return workdir


def _sample_indices(workdir, n_full):
    """Which rows characterize measured, so simulate measures the same ones."""
    p = os.path.join(workdir, "sample_ids.json")
    with open(p, encoding="utf-8") as f:
        ids = json.load(f)
    if all(isinstance(i, int) for i in ids) and max(ids, default=-1) < n_full:
        return np.asarray(ids, dtype=np.int64)
    # String ids: characterize was given an ids_path. Without the mapping the
    # rows cannot be re-selected, so say so rather than guess an order.
    if len(ids) != n_full:
        raise SimulateError(
            f"{p} lists {len(ids)} ids for {n_full} vectors, and they are not "
            "row indices, so simulate cannot reconstruct the same sample. "
            "Re-run characterize without corpus.sample.vectors.ids_path, or "
            "pass the already-subsampled vectors.")
    return np.arange(n_full)


def _ground_truth(workdir, base, queries, k, log_fn):
    """Exact k-NN, cached in the workdir.

    Cached because it is the most expensive thing in a re-run and it depends
    only on (base, queries, k) -- none of which a sweep changes. The cache is
    keyed by shape and k, and a mismatch recomputes rather than trusting it.
    """
    ids_p = os.path.join(workdir, "ground_truth.npy")
    sc_p = os.path.join(workdir, "ground_truth_scores.npy")
    if os.path.exists(ids_p) and os.path.exists(sc_p):
        ids, sc = np.load(ids_p), np.load(sc_p)
        if ids.shape == (len(queries), k) and sc.shape == ids.shape:
            log_fn(f"ground truth: reusing {ids_p}")
            return ids, sc
        log_fn("ground truth: cached shape does not match, recomputing")
    log_fn(f"ground truth: exact k-NN, k={k} over {len(base):,} vectors")
    import faiss
    index = faiss.IndexFlatIP(base.shape[1])
    index.add(base)
    sc, ids = index.search(queries, k)
    np.save(ids_p, ids.astype(np.int64))
    np.save(sc_p, sc.astype(np.float32))
    return ids.astype(np.int64), sc.astype(np.float32)


def _centroid_cache(base, seed, log_fn):
    """Share k-means centroids across configs that ask for the same count.

    A semantic sweep over epsilon and probe rebuilds its shards for every
    config but wants the *same* regions each time -- they depend only on
    (vectors, centroids, seed). Recomputing a 256-way clustering over 150,000
    vectors six times measures nothing new.

    The model computes exactly this call when no context is given, so a cached
    run and an uncached one produce the same result; the cache is a speed
    concession, not a behaviour switch.
    """
    from ..measures.crispness import kmeans
    cache = {}

    def context_for(config):
        if not config.accepts("centroids"):
            return None
        n = config.get("centroids")
        if n is None:
            return None
        n = int(n)
        if n not in cache:
            log_fn(f"k-means {n} centroids (shared across this family's sweep)")
            cache[n] = kmeans(base, n, seed)
        return {"centroids": cache[n]}

    return context_for


def _table(simulate_json, dropped, workdir, elapsed):
    """The plain-text table. Sorted by family then recall@10, and carrying no
    verdict: no column says whether a row is good enough for anything."""
    rows = simulate_json["rows"]
    print()
    print("=" * 118)
    print(f"simulate — {simulate_json['run']}   "
          f"{simulate_json['n_base']:,} vectors, "
          f"{simulate_json['n_queries']:,} queries, seed "
          f"{simulate_json['seed']}")
    print("=" * 118)
    hdr = (f"{'configuration':<52} {'r@1':>6} {'r@10':>6} {'r@100':>6} "
           f"{'ceil':>6} {'route':>6} {'index':>6} {'1/rat':>6} "
           f"{'ampl':>5} {'fan':>4} {'mem MB':>8} {'build s':>8} {'query s':>8}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['config']:<52} "
              f"{r['recall_at_1']:>6.3f} {r['recall_at_10']:>6.3f} "
              f"{r['recall_at_100']:>6.3f} {r['ceiling_at_10']:>6.3f} "
              f"{r['routing_loss']:>6.3f} {r['index_loss']:>6.3f} "
              f"{r['inv_ratio_at_10']:>6.3f} "
              f"{r['storage_amplification']:>5.2f} {r['fanout']:>4.0f} "
              f"{r['est_memory_bytes'] / 1e6:>8.1f} "
              f"{r['build_seconds']:>8.1f} {r['query_seconds']:>8.1f}")
    print()
    print("  ceil   = routing ceiling@10: exact search over everything the "
          "routing can reach")
    print("  route  = 1 - ceil, unreachable. No index tuning recovers it.")
    print("  index  = ceil - r@10, reachable and not returned. efSearch might.")
    print("  1/rat  = mean (true k-th distance)/(returned k-th distance) at "
          "k=10; 1.0 is exact")
    print("  mem MB = estimated, not observed")
    if dropped:
        print()
        print(f"  {len(dropped)} configuration(s) not measured "
              f"({COULDNT_CHECK}: budget):")
        for d in dropped[:10]:
            print(f"    {d['config']}")
        if len(dropped) > 10:
            print(f"    ... and {len(dropped) - 10} more, listed in "
                  "simulate_info.json")
    print()
    print(f"  {len(rows)} configurations measured in {elapsed / 60:.1f} min. "
          "Every number here is")
    print("  a measurement. No row is judged against your constraints in this "
          "table; that")
    print("  comparison is the report's job, and it is deliberately not made "
          "here.")
    print()
    print(f"  simulate.json + simulate_info.json in {workdir}")
    print()
