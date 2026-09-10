"""Capacity arithmetic from a declared corpus.

**Synthetic throughout**, which is also the point: the sample this module
builds on is synthetic by design, and the tests here pin down what may and may
not be concluded from it.

    python oneground/test_capacity.py
    pytest oneground/test_capacity.py
"""

import os
import sys

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground import capacity as C              # noqa: E402
from oneground.models.base import estimate_memory_bytes   # noqa: E402

DECLARED = {"size_now": 2100000, "dimension": 768}


def test_the_synthetic_sample_is_unit_norm_at_the_declared_dimension():
    x = C.synthetic_sample(64, n=128)
    assert x.shape == (128, 64)
    import numpy as np
    assert np.allclose(np.linalg.norm(x, axis=1), 1.0, atol=1e-5)


def test_single_node_amplification_is_one_by_construction():
    e = C.for_family("single_node_hnsw", {"M": 32}, DECLARED)
    assert e["amplification"] == 1.0
    assert e["stored_vectors"] == 2100000
    assert e["kind"] == C.DERIVED


def test_memory_scales_from_the_synthetic_sample_to_the_declared_size():
    """The sample gives the shape; size_now gives the scale."""
    e = C.for_family("single_node_hnsw", {"M": 32}, DECLARED)
    assert e["memory_bytes"] == estimate_memory_bytes(2100000, 768, 32)
    assert 6.0 < e["memory_gb"] < 7.0, e["memory_gb"]
    assert "estimate" in e["memory_note"]


def test_a_hash_shard_spreads_evenly_whatever_the_vectors_mean():
    e = C.for_family("hash_sharded", {"shards": 3, "M": 32}, DECLARED)
    assert e["amplification"] == 1.0
    assert e["shards"] == 3
    assert e["fanout"] == 3.0


def test_semantic_sharded_amplification_is_refused_not_guessed():
    """Its replication depends on how the corpus clusters, and Tier 2 has no
    corpus. A synthetic sample is isotropic and says nothing about it."""
    e = C.for_family("semantic_sharded",
                     {"centroids": 256, "epsilon": 0.2, "probe": 2, "M": 32},
                     DECLARED)
    amp = e["amplification"]
    assert isinstance(amp, str) and amp.startswith("couldnt_check"), amp
    assert "clusters" in amp
    # No storage arithmetic is attempted on a refused multiplier.
    assert isinstance(e["stored_vectors"], str)
    assert isinstance(e["memory_bytes"], str)


def test_a_geometry_dependent_family_is_not_built_at_all():
    """Building it would run a 256-region k-means over noise to produce a
    number that is then thrown away."""
    calls = []
    e = C.for_family("semantic_sharded",
                     {"centroids": 256, "epsilon": 0.2, "probe": 2},
                     DECLARED, log_fn=calls.append)
    assert calls == [], calls
    # Fan-out and shards still come through, from the configuration.
    assert e["fanout"] == 2.0 and e["shards"] == 256
    assert "from the configuration" in e["basis"]


def test_an_analogy_can_lend_a_measured_amplification_labelled_as_its_own():
    surface = {"semantic_sharded": {"storage_amplification": 3.715147}}
    e = C.for_family("semantic_sharded",
                     {"centroids": 256, "epsilon": 0.2, "probe": 2, "M": 32},
                     DECLARED, analogy_surface=surface)
    lent = e["amplification_from_analogy"]
    assert lent["value"] == 3.715147
    assert lent["kind"] == "declared"
    assert "not on your corpus" in lent["note"]
    # The arithmetic now stands on the fixture's number, and says so.
    assert e["stored_vectors"] == int(round(2100000 * 3.715147))
    # And the family's own amplification is still refused.
    assert isinstance(e["amplification"], str)


def test_nodes_needed_leaves_headroom():
    """A node filled to 100% is a node that cannot compact."""
    gb = 1024 ** 3
    assert C.nodes_needed(10 * gb, 64) == 1
    # 64 GB at 70% is 44.8 usable, so 100 GB needs three nodes, not two.
    assert C.nodes_needed(100 * gb, 64) == 3
    assert C.nodes_needed(1, 64) == 1
    assert C.nodes_needed(10 * gb, None) is None
    assert C.nodes_needed(10 * gb, 0) is None


def test_the_plan_never_returns_a_verdict():
    """The property the tier exists to hold."""
    p = C.plan(DECLARED, {"memory_budget_gb": 64},
               ["single_node_hnsw", "hash_sharded", "semantic_sharded"])
    assert p["kind"] == C.DERIVED
    assert "No verdict" in p["note"]
    blob = repr(p)
    for word in ("meets", "fails", "recommended"):
        assert word not in blob, word


def test_every_family_entry_says_where_its_numbers_came_from():
    p = C.plan(DECLARED, {"memory_budget_gb": 64},
               ["single_node_hnsw", "semantic_sharded"])
    for family, e in p["families"].items():
        assert e["kind"] == C.DERIVED, family
        assert e["basis"], family
        assert "declared size_now 2,100,000" in e["basis"], (family, e["basis"])


def test_nodes_are_couldnt_check_when_memory_is():
    p = C.plan(DECLARED, {"memory_budget_gb": 64}, ["semantic_sharded"])
    n = p["families"]["semantic_sharded"]["nodes_at_memory_budget"]
    assert isinstance(n, str) and n.startswith("couldnt_check"), n


def test_no_memory_budget_means_no_node_count():
    p = C.plan(DECLARED, {}, ["single_node_hnsw"])
    assert "nodes_at_memory_budget" not in p["families"]["single_node_hnsw"]


def test_the_epsilon_sweep_is_couldnt_check_without_a_measured_corpus():
    """How far the closure reaches is geometry, and Tier 2 has none."""
    rows = C.epsilon_sweep(DECLARED, [0.0, 0.1, 0.2])
    assert [r["epsilon"] for r in rows] == [0.0, 0.1, 0.2]
    for r in rows:
        assert isinstance(r["amplification"], str), r
        assert r["amplification"].startswith("couldnt_check"), r
        assert "clusters" in r["amplification"], r


def test_the_epsilon_sweep_uses_the_analogys_published_values_when_it_has_them():
    surface = {"epsilon_sweep": {"0.2": 3.715147}}
    rows = C.epsilon_sweep(DECLARED, [0.0, 0.2], analogy_surface=surface)
    by_eps = {r["epsilon"]: r for r in rows}
    assert isinstance(by_eps[0.0]["amplification"], str)
    assert by_eps[0.2]["amplification"] == 3.715147
    assert by_eps[0.2]["kind"] == "declared"
    assert "analogy fixture" in by_eps[0.2]["note"]
    assert by_eps[0.2]["stored_vectors"] == int(round(2100000 * 3.715147))


def test_default_configs_match_the_published_reference_ones():
    """A Tier-2 number and a Tier-1 number must describe the same
    architecture, or they cannot be compared later."""
    assert C._default_config("single_node_hnsw") == {
        "M": 32, "efConstruction": 200, "efSearch": 128}
    sem = C._default_config("semantic_sharded")
    assert sem["centroids"] == 256 and sem["epsilon"] == 0.2
    assert sem["probe"] == 2 and sem["M"] == 32


def _main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed "
          f"(of {len(tests)} collected)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
