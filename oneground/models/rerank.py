"""The rerank stage: exact scoring over a candidate set (task 035).

Retrieve `k x candidates` approximately, score those candidates exactly
against the query with the corpus's own metric, keep the best `k`. It is one
of the two standard uses of exact search and the simulator was silent on it.

**The exact pass is task 034's `flat` index applied to a candidate set rather
than to the corpus.** Same arithmetic — inner product over float32 vectors —
restricted to the ids the first pass returned. Nothing here is approximate
except what the first pass returned, which is the whole point.

It is not `exact_over`, though that is the same idea. `exact_over` scores one
subset shared by every query, which is what a routing ceiling needs; a rerank
has a *different* candidate set per query, so it is a batched gather and dot
rather than an index search.

WHAT RERANKING CAN AND CANNOT RECOVER
-------------------------------------
This is the finding the stage exists to produce, and it is exact rather than
empirical. Recall's gap from 1.0 splits three ways:

    routing_loss    = 1 - ceiling            never reachable
    candidate_loss  = ceiling - candidate_recall
                                             reachable, absent from the
                                             candidate set
    ordering_loss   = candidate_recall - recall
                                             in the candidate set, ranked out
                                             of the top k

and the three sum to `1 - recall` by construction.

**Exact reranking recovers the ordering term and nothing else.** Not
approximately: a true top-k neighbour that is in the candidate set is scored
by its true score, and the only vectors that can outrank it are ones with a
higher true score, which are themselves in the true top-k. So after an exact
rescore, ordering loss is zero and recall equals candidate recall.

The consequence is the useful one: **a corpus whose loss is mostly candidate
loss cannot be helped by reranking, however it is tuned.** More `candidates`
is the only lever on candidate loss, and it is bought with latency. That is a
more useful answer to a team than any recall number.

One mechanical corollary worth measuring rather than assuming: an index whose
returned scores are already the true inner products of the vectors it found —
`hnsw` and `ivf` both return exact distances for the nodes they visit — has no
ordering loss to recover. Only a quantised index (`ivf_pq`, which scores from
codes) can have any. The sweep reports it either way.
"""

import time

import numpy as np

from .base import RERANK_EXACT, RERANK_NONE


def mode_of(config, default=RERANK_NONE):
    return str(config.get("rerank", default) or default)


def multiplier_of(config, default=1):
    return int(config.get("candidates", default) or default)


def is_on(config):
    return mode_of(config) == RERANK_EXACT


def depth_for(k, config):
    """How many candidates the first pass must return for a top-k rerank."""
    return int(k) * multiplier_of(config) if is_on(config) else int(k)


def rescore(vectors, cand_ids, queries, k, batch=64):
    """Exactly score each query's own candidates; return its best `k`.

    `cand_ids` is (n_queries, C) int64 with -1 padding, as `Candidates.ids`
    is. Returns (ids, scores) shaped (n_queries, k), -1 and -inf padded.

    Batched over queries because the gather is the expensive part: at 2,000
    queries, 500 candidates and 768 dimensions, materialising every candidate
    vector at once is 3 GB to compute 2,000 dot products.
    """
    n_q, width = cand_ids.shape
    out_ids = np.full((n_q, k), -1, dtype=np.int64)
    out_scores = np.full((n_q, k), -np.inf, dtype=np.float32)
    if width == 0:
        return out_ids, out_scores
    take = min(k, width)
    for lo in range(0, n_q, batch):
        hi = min(lo + batch, n_q)
        ids = cand_ids[lo:hi]
        safe = np.where(ids >= 0, ids, 0)
        # (b, C, d) . (b, d) -> (b, C); the exact inner product, which is what
        # `flat` computes, over this query's candidates only.
        got = np.einsum("bcd,bd->bc", vectors[safe], queries[lo:hi],
                        optimize=True).astype(np.float32)
        got[ids < 0] = -np.inf
        order = np.argsort(-got, axis=1, kind="stable")[:, :take]
        rows = np.arange(hi - lo)[:, None]
        picked = ids[rows, order]
        picked_scores = got[rows, order]
        # A padded slot must stay padded, not become id 0 at -inf.
        picked = np.where(picked_scores > -np.inf, picked, -1)
        out_ids[lo:hi, :take] = picked
        out_scores[lo:hi, :take] = picked_scores
    return out_ids, out_scores


def rerank_candidates(built, cand, queries, k):
    """Rescore a family's candidates exactly. Returns (ids, scores, seconds).

    Every family keeps the corpus in `built.state["vectors"]`, which is what
    makes this one implementation rather than three.
    """
    vectors = built.state["vectors"]
    t0 = time.time()
    ids, scores = rescore(vectors, cand.ids, queries, k)
    return ids, scores, time.time() - t0


def present_at(cand_ids, gt_ids, k):
    """Fraction of each query's true top-`k` present ANYWHERE in `cand_ids`.

    The ceiling reranking cannot exceed. Distinct from `recall_at`, which asks
    whether they are in the top `k` *as returned*: this asks only whether the
    candidate set contains them at all, which is what `candidates` buys.
    """
    n_q = gt_ids.shape[0]
    if n_q == 0:
        return 0.0
    hits = 0
    for q in range(n_q):
        truth = set(int(i) for i in gt_ids[q, :k] if i >= 0)
        if not truth:
            continue
        got = set(int(i) for i in cand_ids[q] if i >= 0)
        hits += len(truth & got)
    denom = sum(1 for q in range(n_q)
                for i in gt_ids[q, :k] if i >= 0)
    return hits / denom if denom else 0.0


def decomposition(ceiling, candidate_recall, first_pass_recall):
    """The three terms, and what each means for a decision.

    They decompose what **the first pass** lost, and sum to
    `1 - first_pass_recall`. That is the subtlety, and getting it wrong makes
    the whole measure useless: after an exact rescore ordering loss is zero by
    construction, so a decomposition of the POST-rerank recall reports
    `ordering_loss: 0` on every reranked row and the one term the stage exists
    to expose is never visible. Measured on a quantised index it did exactly
    that -- recall rose 0.3133 to 0.6450 and ordering_loss read 0.0000 in both
    rows.

    So `first_pass_recall` is the recall of the first pass's own top-k, before
    rescoring reordered it, and `ordering_loss` is what the rescore recovered.
    The reranked recall is then `1 - routing_loss - candidate_loss`, exactly.

    Without reranking the candidate set IS the returned top-k, so
    candidate_recall == first_pass_recall, ordering_loss is zero, and this
    reduces to the two-way split the simulator reported before task 035 --
    which is why no published value moves.
    """
    routing = 1.0 - ceiling
    candidate = ceiling - candidate_recall
    ordering = candidate_recall - first_pass_recall
    return {
        "routing_loss": routing,
        "candidate_loss": candidate,
        "ordering_loss": ordering,
        "recoverable_by_rerank": ordering,
    }


#: The caption the report prints beside the three terms. NOT returned into the
#: row: a row carries measurements, and a paragraph repeated once per
#: configuration is neither a measurement nor readable. It also tripped the
#: verdict-language guard on the word "pass", which is the guard being right
#: for a reason adjacent to the one it was written for -- prose in a receipt
#: is prose nobody reviewed as prose.
DECOMPOSITION_NOTE = (
    "routing_loss is what the partition made unreachable and reranking "
    "cannot touch it. candidate_loss is reachable but absent from the "
    "candidate set: only a larger `candidates` reaches it, and that is "
    "bought with latency. ordering_loss is present in the candidate set and "
    "ranked out of the top k, and it is the ONLY term exact reranking "
    "recovers. A corpus whose loss is mostly candidate_loss cannot be helped "
    "by reranking however it is tuned. The three decompose what the first "
    "retrieval lost and sum to 1 - recall_before_rerank; the recall after an "
    "exact rescore is 1 - routing_loss - candidate_loss.")


def apply(built, cand, queries, k, config):
    """Rescore `cand` exactly and return the top `k`, or pass it through.

    The one implementation the three families share. Each family's `search`
    retrieves `depth_for(k, config)` results and calls this; when reranking is
    off it returns the candidates unchanged, so the path a configuration
    without `rerank` takes is the path it took before task 035.

    This lives in the family's search rather than in the simulator because
    that is where the keys are read, and a declared key no family reads is the
    accept-and-ignore defect task 026 exists to refuse. One implementation,
    three one-line call sites -- the same shape as `indexes.set_search`.
    """
    from .base import Candidates
    if not is_on(config):
        return cand
    ids, scores, seconds = rerank_candidates(built, cand, queries, k)
    return Candidates(ids=ids, scores=scores,
                      reranked_from=cand.ids, rerank_seconds=seconds)
