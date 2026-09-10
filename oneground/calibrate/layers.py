"""The three blocking calibration checks.

Task 012 ran a four-layer decomposition to find which layer owned a
contradiction against published ANN-Benchmarks values. Three layers came back
clean and one did not, and 012b promotes the three clean ones to the gate:

    corpus_reachability     is every published ground-truth neighbour actually
                            in the corpus we index?
    metric_agreement        does our metric convention reproduce the published
                            neighbour ordering?
    recall_rule_accounting  can ANN-Benchmarks' distance-based `knn` metric
                            diverge from our id-based intersection by enough
                            to matter?

Why these three and not the curve
---------------------------------
Each of them checks something that would make **every** recall this project
publishes silently wrong, and each has a correct answer known in advance:
1.0, 1.0, and ~0. They are the assumptions the measurements rest on.

The hnswlib curve is different in kind. It compares two HNSW implementations,
and task 012 measured that they genuinely differ -- faiss at efSearch=e
reaches the recall hnswlib reached at roughly 1.4e to 1.9e. That difference is
real, one-signed and now published as a known offset; gating a release on it
would be gating on someone else's implementation. It runs advisory.

Failure modes these catch are not subtle
----------------------------------------
A metric-convention error does not drift, it collapses: index with L2 instead
of inner product, or forget to normalize, and agreement goes to near zero, not
to 0.999. The tolerances below are therefore tight, and tight is safe -- there
is no regime in which a real defect here produces a small deviation.
"""

import os

import numpy as np

from . import history as H

# Distances that agree to within this are treated as tied. ANN-Benchmarks uses
# 1e-10 in its own `knn` metric; this is looser because the published
# distances are float32 and a float32 tie is not exact at 1e-10.
TIE_EPSILON = 1e-6

# Tolerances. Declared here rather than per-run so a check cannot have its band
# chosen after its number is known.
TOLERANCES = {
    # A published neighbour is either in the corpus or it is not. No float
    # arithmetic is involved, so anything other than exactly 1.0 is a real
    # defect -- and the one that task 012 caught.
    "corpus_reachability": 0.0,
    # Exact search must reproduce the published ordering. 0.001 rather than 0
    # only because a tie at the k-th boundary could legitimately swap one id;
    # a genuine convention error would land near 0, nowhere near 0.999.
    "metric_agreement": 0.001,
    # How far the two recall definitions can diverge. Measured at 0.0016 on
    # this corpus in task 012; 0.01 leaves room for upstream to change without
    # letting the accounting argument quietly stop holding.
    "recall_rule_accounting": 0.01,
}

CHECKS = tuple(TOLERANCES)


def _arrays(fixture_id, fixtures_dir):
    d = os.path.join(fixtures_dir, fixture_id)
    need = ["vectors.npy", "queries.npy", "ground_truth.npy",
            "ground_truth_distances.npy"]
    missing = [n for n in need if not os.path.exists(os.path.join(d, n))]
    if missing:
        from . import CalibrateError
        raise CalibrateError(
            f"{d} is missing {', '.join(missing)}. Build it with:\n\n"
            f"    oneground calibrate fixture --fixture {fixture_id} "
            f"--source <glove-100-angular.hdf5>\n")
    return (np.load(os.path.join(d, "vectors.npy"), mmap_mode="r"),
            np.load(os.path.join(d, "queries.npy")),
            np.load(os.path.join(d, "ground_truth.npy")),
            np.load(os.path.join(d, "ground_truth_distances.npy")))


# --------------------------------------------------------------------------
# the measurements
# --------------------------------------------------------------------------

def corpus_reachability(vectors, gt, k):
    """Mean share of a query's published top-k that the corpus actually holds.

    1.0 means recall is bounded by the index and nothing else. Anything less
    means part of what is being scored against is not present, and every
    recall measured on the fixture is capped below 1 for a reason that has
    nothing to do with retrieval.
    """
    return float((gt[:, :k] < vectors.shape[0]).sum(axis=1).mean() / k)


def metric_agreement(vectors, queries, gt, k, n_queries, chunk=100_000):
    """Agreement between exact inner-product top-k and the published top-k.

    The fixture stores L2-normalized vectors and searches inner product, while
    upstream computed angular distance on unnormalized ones. The orderings are
    the same in theory; this measures it.
    """
    import faiss
    q = np.ascontiguousarray(queries[:n_queries])
    truth = gt[:n_queries, :k]
    index = faiss.IndexFlatIP(vectors.shape[1])
    for i in range(0, vectors.shape[0], chunk):
        index.add(np.ascontiguousarray(vectors[i:i + chunk]))
    _, ids = index.search(q, k)
    return float(np.mean([len(set(a.tolist()) & set(b.tolist())) / k
                          for a, b in zip(ids, truth)]))


def recall_rule_divergence_bound(gt_distances, k, epsilon=TIE_EPSILON):
    """Fraction of queries whose k-th and (k+1)-th true distances tie.

    This bounds the whole layer-3 argument. ANN-Benchmarks' `knn` metric counts
    a returned neighbour as correct when its distance is within epsilon of the
    k-th true distance, so it is *tie-generous*: it can only score a given
    candidate set at or above an id-based intersection. Where there is no tie
    at the boundary the two definitions agree exactly, so the tie rate is the
    ceiling on how far they can diverge -- and therefore on how much of any
    disagreement with published values could be an accounting artefact rather
    than a real difference.
    """
    if gt_distances.shape[1] <= k:
        return 0.0
    a = gt_distances[:, k - 1].astype(np.float64)
    b = gt_distances[:, k].astype(np.float64)
    return float(np.mean(np.isclose(a, b, rtol=0.0, atol=epsilon)))


def recall_distance_based(pred_ids, pred_scores, gt_distances, k,
                          epsilon=TIE_EPSILON):
    """ANN-Benchmarks' `knn` metric, for comparison against `recall_at`.

    Their distances are angular and ours are inner-product similarities on
    unit vectors. For unit vectors ANN-Benchmarks' angular distance is
    sqrt(2 - 2*cos), so a returned candidate's distance is recovered from its
    inner product without needing the vectors again.
    """
    sim = np.clip(pred_scores[:, :k].astype(np.float64), -1.0, 1.0)
    dist = np.sqrt(np.maximum(2.0 - 2.0 * sim, 0.0))
    threshold = gt_distances[:pred_ids.shape[0], k - 1].astype(np.float64)
    ok = (pred_ids[:, :k] >= 0) & (dist <= threshold[:, None] + epsilon)
    return float(ok.sum() / (ok.shape[0] * k))


# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------

def run_layers(fixture_id="glove-100-angular", k=10, n_queries=1000,
               fixtures_dir="fixtures", append=True,
               history_path=H.DEFAULT_PATH, outcome_scope=H.BLOCKING,
               log_fn=print):
    """Run the three blocking checks and return their history lines."""
    vectors, queries, gt, gtd = _arrays(fixture_id, fixtures_dir)
    n_queries = min(int(n_queries), queries.shape[0])
    log_fn(f"layers on {fixture_id}: {vectors.shape[0]} x {vectors.shape[1]}, "
           f"k={k}, {n_queries} queries for the exact pass")

    reach = corpus_reachability(vectors, gt, k)
    log_fn(f"  corpus_reachability     {reach:.6f}  (want 1.0)")

    agree = metric_agreement(vectors, queries, gt, k, n_queries)
    log_fn(f"  metric_agreement        {agree:.6f}  (want 1.0)")

    tie = recall_rule_divergence_bound(gtd, k)
    log_fn(f"  recall_rule_accounting  {tie:.6f}  (want ~0)")

    common = dict(dataset=fixture_id, engine="oneground/calibrate",
                  engine_version=_version(), outcome_scope=outcome_scope,
                  source=os.path.join(fixtures_dir, fixture_id))

    lines = [
        H.make_line(
            check="corpus_reachability",
            config=f"published_gt[k={k}]",
            measured=reach, reference=1.0,
            tolerance=TOLERANCES["corpus_reachability"],
            definition="mean share of a query's published top-k that the "
                       "indexed corpus actually holds; 1.0 means recall is "
                       "bounded by the index and nothing else",
            extra={"k": k, "n_base": int(vectors.shape[0]),
                   "n_queries": int(gt.shape[0])},
            **common),
        H.make_line(
            check="metric_agreement",
            config=f"exact_ip[k={k},n={n_queries}]",
            measured=agree, reference=1.0,
            tolerance=TOLERANCES["metric_agreement"],
            definition="agreement between exact inner-product top-k on "
                       "L2-normalized vectors and the published angular "
                       "top-k; a convention error collapses this, it does "
                       "not drift",
            extra={"k": k, "n_queries": int(n_queries)},
            **common),
        H.make_line(
            check="recall_rule_accounting",
            config=f"knn_tie_bound[k={k},eps={TIE_EPSILON}]",
            measured=tie, reference=0.0,
            tolerance=TOLERANCES["recall_rule_accounting"],
            definition="fraction of queries whose k-th and (k+1)-th published "
                       "distances tie; bounds how far ANN-Benchmarks' "
                       "distance-based knn metric can exceed an id-based "
                       "intersection",
            extra={"k": k, "epsilon": TIE_EPSILON,
                   "n_queries": int(gtd.shape[0])},
            **common),
    ]
    for ln in lines:
        log_fn(f"  {ln['check']:<24} {ln['outcome']}")
    if append:
        H.append_all(lines, history_path)
        log_fn(f"appended {len(lines)} line(s) to {history_path}")
    return {"fixture": fixture_id, "k": k, "lines": lines,
            "measured": {"corpus_reachability": reach,
                         "metric_agreement": agree,
                         "recall_rule_accounting": tie}}


def _version():
    try:
        import importlib.metadata as md
        return f"faiss-cpu {md.version('faiss-cpu')}"
    except Exception:                            # pragma: no cover - env
        return "unknown"
