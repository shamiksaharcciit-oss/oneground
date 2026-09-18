"""Contract tests for the pre-chunking near-duplicate measure (task 030)."""

import numpy as np

from oneground.measures import duplicates as dup

SEED = 20260919


def words(n, start=0):
    return " ".join(f"w{i}" for i in range(start, start + n))


def test_a_document_is_its_own_duplicate():
    s = dup.shingles(words(500))
    assert dup.exact_jaccard(s, s) == 1.0


def test_disjoint_documents_score_zero():
    a = dup.shingles(words(500, 0))
    b = dup.shingles(words(500, 10_000))
    assert dup.exact_jaccard(a, b) == 0.0


def test_synthetic_half_shared_document_scores_near_a_third():
    """Two documents sharing half their text: the shared half is in both, the
    two unshared halves in one each, so Jaccard tends to 1/3."""
    a = dup.shingles(words(1000, 0))
    b = dup.shingles(words(500, 0) + " " + words(500, 50_000))
    assert 0.28 < dup.exact_jaccard(a, b) < 0.38


def test_shingling_is_case_and_whitespace_insensitive():
    a = dup.shingles("The Company  reports\n annual RESULTS here now")
    b = dup.shingles("the company reports annual results here now")
    assert dup.exact_jaccard(a, b) == 1.0


def test_shingles_stay_inside_the_prime():
    """The 32-bit construction is what keeps MinHash in uint64 arithmetic; a
    shingle at or above the prime would wrap and the measure would be wrong."""
    s = dup.shingles(words(5000))
    assert s.dtype == np.uint64
    assert s.max() < int(dup._PRIME)


def test_minhash_signature_estimates_jaccard():
    a = words(2000, 0)
    b = words(1400, 0) + " " + words(600, 90_000)
    sa, sb = dup.shingles(a), dup.shingles(b)
    true = dup.exact_jaccard(sa, sb)
    pa, pb = dup._permutations(SEED)
    est = (dup.signature(sa, pa, pb) == dup.signature(sb, pa, pb)).mean()
    assert abs(est - true) < 0.12, (est, true)


def test_a_duplicate_pair_is_found_and_scored_exactly():
    texts = [words(2000, 0), words(1900, 0) + " " + words(100, 70_000),
             words(2000, 200_000)]
    res = dup.near_duplicate_rate(texts, seed=SEED)
    at80 = res["by_threshold"]["0.80"]
    assert at80["pairs"] == 1
    assert at80["documents"] == 2
    assert at80["rate"] == 2 / 3


def test_thresholds_are_nested():
    """A pair at 0.90 is also a pair at 0.80. Rates cannot increase."""
    texts = [words(2000, 0), words(1500, 0) + " " + words(500, 70_000),
             words(1900, 0) + " " + words(100, 80_000), words(2000, 300_000)]
    res = dup.near_duplicate_rate(texts, seed=SEED)
    rates = [res["by_threshold"][f"{t:.2f}"]["rate"] for t in dup.THRESHOLDS]
    assert rates == sorted(rates, reverse=True), rates


def test_low_thresholds_are_labelled_a_lower_bound_not_a_rate():
    """LSH can miss a pair, and at 0.50 it misses one in eight. That is a
    couldn't-check on part of the number and it is labelled, never rounded up."""
    res = dup.near_duplicate_rate([words(300, 0), words(300, 9000)], seed=SEED)
    assert res["by_threshold"]["0.50"]["kind"] == "lower bound"
    assert res["by_threshold"]["0.80"]["kind"] == "exact"
    assert res["by_threshold"]["0.50"]["lsh_recall"] < dup.EXACT_RECALL
    assert res["by_threshold"]["0.80"]["lsh_recall"] >= dup.EXACT_RECALL


def test_recall_is_monotone_in_similarity():
    xs = [dup.recall_at(s) for s in (0.3, 0.5, 0.7, 0.8, 0.9)]
    assert xs == sorted(xs)
    assert xs[-1] > 0.9999


def test_the_measure_is_deterministic_under_its_seed():
    texts = [words(800, 0), words(700, 0) + " " + words(100, 50_000)]
    a = dup.near_duplicate_rate(texts, seed=SEED)
    b = dup.near_duplicate_rate(texts, seed=SEED)
    assert a == b


def test_empty_and_tiny_documents_do_not_raise():
    res = dup.near_duplicate_rate(["", "one two", words(300)], seed=SEED)
    assert res["documents"] == 3
    assert res["by_threshold"]["0.80"]["rate"] == 0.0
