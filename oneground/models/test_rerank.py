"""The rerank stage (task 035).

Synthetic corpora throughout except where named otherwise. The load-bearing
claim is that exact reranking recovers the ordering term and nothing else, so
that is tested by construction rather than by observing one corpus.
"""

import numpy as np
import pytest

from oneground.models import Config, rerank as R
from oneground.models.base import (RERANK_EXACT, RERANK_NONE, ParameterError,
                                   parameter_table)


def corpus(n=200, dim=16, seed=3):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, dim)).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    return x


# ---------------------------------------------------------- the declaration

@pytest.mark.parametrize("family", ["single_node_hnsw", "semantic_sharded",
                                    "hash_sharded"])
def test_every_family_declares_rerank(family):
    t = parameter_table(family)
    assert t["rerank"].choices == (RERANK_NONE, RERANK_EXACT)
    assert t["rerank"].default == RERANK_NONE
    assert t["candidates"].belongs_to == ("rerank", (RERANK_EXACT,))


def test_rerank_none_does_not_relabel_synthetic():
    """Task 032's rule, and the reason no published fixture value moves."""
    base = {"M": 32, "efConstruction": 200, "efSearch": 128}
    a = Config.make("single_node_hnsw", base)
    b = Config.make("single_node_hnsw", dict(base, rerank="none"))
    assert a.label == b.label


def test_rerank_exact_does_relabel_synthetic():
    base = {"M": 32, "efConstruction": 200, "efSearch": 128}
    a = Config.make("single_node_hnsw", base)
    c = Config.make("single_node_hnsw",
                    dict(base, rerank="exact", candidates=8))
    assert c.label != a.label
    assert "rerank=exact" in c.label and "candidates=8" in c.label


def test_an_unknown_rerank_mode_is_refused_with_the_declared_list():
    with pytest.raises(ParameterError) as e:
        Config.make("single_node_hnsw",
                    {"M": 32, "efConstruction": 200, "efSearch": 128,
                     "rerank": "cross_encoder"})
    msg = str(e.value)
    assert "cross_encoder" in msg and "none" in msg and "exact" in msg


def test_candidates_is_refused_when_reranking_is_off():
    """A knob the chosen mode does not read is refused, not ignored -- the
    same rule as an IVF knob under hnsw."""
    with pytest.raises(ParameterError):
        Config.make("single_node_hnsw",
                    {"M": 32, "efConstruction": 200, "efSearch": 128,
                     "candidates": 10})


def test_depth_is_k_when_off_and_k_times_multiplier_when_on():
    off = Config.make("single_node_hnsw",
                      {"M": 32, "efConstruction": 200, "efSearch": 128})
    on = Config.make("single_node_hnsw",
                     {"M": 32, "efConstruction": 200, "efSearch": 128,
                      "rerank": "exact", "candidates": 12})
    assert R.depth_for(10, off) == 10
    assert R.depth_for(10, on) == 120
    assert R.is_on(on) and not R.is_on(off)


# ------------------------------------------------------------ the rescoring

def test_rescore_returns_the_exact_top_k_of_the_candidate_set_synthetic():
    x = corpus()
    q = x[:5].copy()
    cand = np.tile(np.arange(40, dtype=np.int64), (5, 1))
    ids, scores = R.rescore(x, cand, q, k=10)
    for i in range(5):
        truth = np.argsort(-(x[:40] @ q[i]))[:10]
        assert list(ids[i]) == [int(t) for t in truth]
        assert np.allclose(scores[i], (x[:40] @ q[i])[truth], atol=1e-5)


def test_rescore_is_the_same_arithmetic_as_flat_over_that_subset_synthetic():
    """The exact pass IS task 034's flat index, restricted to a candidate
    set. Same inner product, same float32 vectors."""
    import faiss
    x = corpus()
    q = x[:4].copy()
    subset = np.arange(0, 60, dtype=np.int64)
    cand = np.tile(subset, (4, 1))
    ids, scores = R.rescore(x, cand, q, k=5)
    flat = faiss.IndexFlatIP(x.shape[1])
    flat.add(x[subset])
    fs, floc = flat.search(q, 5)
    assert list(ids[0]) == [int(subset[j]) for j in floc[0]]
    assert np.allclose(scores[0], fs[0], atol=1e-5)


def test_padding_stays_padding_rather_than_becoming_id_zero():
    x = corpus()
    q = x[:2].copy()
    cand = np.full((2, 6), -1, dtype=np.int64)
    cand[:, 0] = 7
    ids, scores = R.rescore(x, cand, q, k=4)
    assert ids[0, 0] == 7
    assert list(ids[0, 1:]) == [-1, -1, -1]
    assert np.all(np.isneginf(scores[0, 1:]))


def test_rescore_handles_a_candidate_set_narrower_than_k():
    x = corpus()
    q = x[:2].copy()
    cand = np.tile(np.arange(3, dtype=np.int64), (2, 1))
    ids, scores = R.rescore(x, cand, q, k=10)
    assert (ids[0] >= 0).sum() == 3
    assert list(ids[0, 3:]) == [-1] * 7


# ------------------------------------------------------- the decomposition

def test_the_three_terms_sum_to_one_minus_the_first_pass_recall():
    d = R.decomposition(ceiling=0.90, candidate_recall=0.80,
                        first_pass_recall=0.70)
    total = d["routing_loss"] + d["candidate_loss"] + d["ordering_loss"]
    assert total == pytest.approx(1.0 - 0.70)


def test_without_reranking_it_reduces_to_the_old_two_way_split():
    """The candidate set IS the returned top-k, so ordering loss is zero and
    candidate loss is exactly what `index_loss` was. Published values do not
    move because the arithmetic did not."""
    d = R.decomposition(ceiling=0.90, candidate_recall=0.70,
                        first_pass_recall=0.70)
    assert d["ordering_loss"] == 0.0
    assert d["candidate_loss"] == pytest.approx(0.90 - 0.70)


def test_only_the_ordering_term_is_named_recoverable():
    d = R.decomposition(ceiling=0.9, candidate_recall=0.8,
                        first_pass_recall=0.7)
    assert d["recoverable_by_rerank"] == d["ordering_loss"]
    assert "decomposition_note" not in d, (
        "a row carries measurements; the caption belongs in the report")
    assert "ONLY term exact reranking recovers" in R.DECOMPOSITION_NOTE
    assert "mostly candidate_loss cannot be helped" in R.DECOMPOSITION_NOTE


def test_exact_reranking_drives_ordering_loss_to_zero_synthetic():
    """The load-bearing claim, by construction rather than by observation: a
    true top-k neighbour present in the candidate set is scored by its true
    score, and only vectors with a higher true score can outrank it -- and
    those are themselves in the true top-k."""
    rng = np.random.default_rng(11)
    x = corpus(n=300, dim=24, seed=5)
    q = x[rng.choice(300, 20, replace=False)].copy()
    gt = np.argsort(-(x @ q.T).T, axis=1)[:, :10].astype(np.int64)

    # a deliberately BADLY ORDERED candidate set: the right ids, shuffled
    cand = np.empty((20, 50), dtype=np.int64)
    for i in range(20):
        pool = np.argsort(-(x @ q[i]))[:50]
        cand[i] = rng.permutation(pool)

    before = R.present_at(cand[:, :10], gt, 10)      # top-10 as returned
    contained = R.present_at(cand, gt, 10)           # anywhere in the set
    ids, _ = R.rescore(x, cand, q, k=10)
    after = R.present_at(ids[:, :10], gt, 10)

    assert contained == 1.0, "the fixture should contain every true neighbour"
    assert before < 1.0, "the fixture should be badly ordered to begin with"
    assert after == pytest.approx(1.0), "exact rescore must recover all of it"
    d = R.decomposition(1.0, contained, after)
    assert d["ordering_loss"] == pytest.approx(0.0)


def test_reranking_cannot_recover_candidate_loss_synthetic():
    """The useful half of the finding: what is not in the candidate set is
    not reachable by rescoring it, however the rescore is done."""
    x = corpus(n=300, dim=24, seed=5)
    q = x[:15].copy()
    gt = np.argsort(-(x @ q.T).T, axis=1)[:, :10].astype(np.int64)
    # a candidate set deliberately missing each query's true best neighbour
    cand = np.empty((15, 30), dtype=np.int64)
    for i in range(15):
        pool = [int(j) for j in np.argsort(-(x @ q[i]))[:31] if j != gt[i, 0]]
        cand[i] = pool[:30]
    contained = R.present_at(cand, gt, 10)
    ids, _ = R.rescore(x, cand, q, k=10)
    after = R.present_at(ids[:, :10], gt, 10)
    assert contained < 1.0
    assert after == pytest.approx(contained), (
        "rescoring recovered something absent from the candidate set")


def test_present_at_asks_only_whether_the_set_contains_them():
    gt = np.array([[1, 2, 3]], dtype=np.int64)
    assert R.present_at(np.array([[9, 3, 8, 1, 2]], dtype=np.int64), gt, 3) == 1.0
    assert R.present_at(np.array([[9, 8, 7]], dtype=np.int64), gt, 3) == 0.0
    assert R.present_at(np.array([[1, 9, 8]], dtype=np.int64), gt, 3) == pytest.approx(1 / 3)


def test_the_decomposition_describes_the_first_pass_not_the_rescored_result():
    """The defect this catches made the whole measure useless.

    After an exact rescore ordering loss is zero by construction, so a
    decomposition of the POST-rerank recall reports `ordering_loss: 0` on
    every reranked row and the one term the stage exists to expose is never
    visible. Measured on a quantised index it did exactly that: recall rose
    0.3133 to 0.6450 and ordering_loss read 0.0000 in both rows.
    """
    # a first pass that found the neighbours but ranked them badly
    d = R.decomposition(ceiling=1.0, candidate_recall=0.65,
                        first_pass_recall=0.31)
    assert d["ordering_loss"] == pytest.approx(0.34), (
        "the recovered term is invisible; the decomposition is describing "
        "the rescored result instead of the first pass")
    assert d["routing_loss"] + d["candidate_loss"] + d["ordering_loss"] == \
        pytest.approx(1.0 - 0.31)
    # and the reranked recall is what is left after the two it cannot recover
    assert 1.0 - d["routing_loss"] - d["candidate_loss"] == pytest.approx(0.65)


def test_the_note_says_which_recall_the_terms_sum_to():
    assert "recall_before_rerank" in R.DECOMPOSITION_NOTE
