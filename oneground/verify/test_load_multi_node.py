"""`oneground.verify.load.run_load_per_node`. `docs/MULTI_NODE.md` §6.

Live only: runs against a real three-node Qdrant cluster
(`oneground/verify/compose/qdrant-cluster.yml`) when
`ONEGROUND_QDRANT_CLUSTER_URLS` names its three node endpoints,
comma-separated. Never faked -- the position paper this task builds from
was written specifically against a real cluster's real return types, not a
mock, and the function it grounds is tested the same way.

    docker compose -f oneground/verify/compose/qdrant-cluster.yml up -d
    ONEGROUND_QDRANT_CLUSTER_URLS=http://localhost:16333,http://localhost:16343,http://localhost:16353 \
        pytest oneground/verify/test_load_multi_node.py -v
    docker compose -f oneground/verify/compose/qdrant-cluster.yml down -v
"""

import os
import sys
import uuid

import numpy as np
import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.adapters.qdrant.adapter import QdrantAdapter  # noqa: E402
from oneground.verify import load as loadgen                  # noqa: E402

CLUSTER_URLS_ENV = "ONEGROUND_QDRANT_CLUSTER_URLS"
DIM = 16
N_VECTORS = 500
N_QUERIES = 40


def _cluster_urls():
    raw = os.environ.get(CLUSTER_URLS_ENV, "")
    urls = [u.strip() for u in raw.split(",") if u.strip()]
    return urls


def _corpus(seed=20260925):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, size=(N_VECTORS, DIM)).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = rng.normal(0, 1, size=(N_QUERIES, DIM)).astype(np.float32)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    return x, q


# --------------------------------------------------------------- couldnt_check
def test_fewer_than_two_endpoints_is_couldnt_check_not_a_guess():
    """The mutant for docs/MULTI_NODE.md §4.2's own rule: a single shared
    entrypoint is not a smaller version of the measurement."""
    result = loadgen.run_load_per_node(
        lambda: None, ["http://localhost:6333"], "ns", [np.zeros(8)])
    assert result["outcome"] == "couldnt_check"
    assert "fewer than two" in result["reason"]
    assert result["nodes"] == []

    result = loadgen.run_load_per_node(lambda: None, [], "ns", [np.zeros(8)])
    assert result["outcome"] == "couldnt_check"


# ----------------------------------------------------------- the live cluster
@pytest.mark.skipif(len(_cluster_urls()) < 3,
                    reason=f"{CLUSTER_URLS_ENV} not set to 3 endpoints")
def test_per_node_fan_out_against_a_real_three_node_cluster():
    urls = _cluster_urls()
    ns = "oneground-057-" + uuid.uuid4().hex[:8]
    x, q = _corpus()

    setup = QdrantAdapter()
    setup.connect(urls[0])
    try:
        setup.create_namespace(ns, DIM, "cosine",
                               {"m": 16, "ef_construct": 100})
        setup.upsert(ns, list(range(N_VECTORS)), x)
        setup.wait_for_index(ns, timeout=60, poll=1.0)

        result = loadgen.run_load_per_node(
            QdrantAdapter, urls, ns, list(q), k=5,
            concurrency=4, target_qps=0, duration_minutes=0.15,
            warmup_seconds=2.0)

        assert result["outcome"] == "measured"
        assert len(result["nodes"]) == 3
        for i, row in enumerate(result["nodes"]):
            assert row["node_index"] == i
            assert row["endpoint"] == urls[i]
            assert row["completed"] > 0, (
                f"node {i} ({urls[i]}) completed no queries -- fan-out "
                "cannot be measured from an empty result")

        fan_out = result["fan_out"]
        assert fan_out["min_achieved_qps"] <= fan_out["mean_achieved_qps"]
        assert fan_out["slowest_node_by_qps"]["endpoint"] in urls
        if fan_out["slowest_node_by_latency"]:
            assert fan_out["max_p95_ms"] >= fan_out["mean_p95_ms"]
    finally:
        setup.delete_namespace(ns)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
