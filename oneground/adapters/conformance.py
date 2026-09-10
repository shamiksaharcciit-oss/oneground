"""The conformance suite: what an adapter must do to be in the project.

This is the contribution gate. An engine is not supported because someone
wrote an adapter; it is supported because the adapter passes here.

Seven checks, in the order a real run exercises them:

    a  create a namespace under the oneground- prefix
    b  upsert 5,000 synthetic vectors
    c  search 200 queries, recall@10 >= 0.95 against exact ground truth
       with a generous ef
    d  describe() reports the point count and the index params it was given
    e  scroll() returns the same vectors that went in
    f  delete() and confirm it is gone
    g  the namespace is deleted even when the body raises

**Where it runs.** Always against the in-process `stub`, so the protocol is
checked on every machine with no Docker and no network. Against a live engine
only when its URL variable is set -- `ONEGROUND_QDRANT_URL`,
`ONEGROUND_PGVECTOR_URL` -- otherwise those tests **skip**, and a skip is
reported as a skip. Nothing here fakes a pass for an engine that was never
contacted, and the suite prints which engines it actually reached.

**`wait_for_index` is required, not probed.** Task 015 promoted it (and
`namespace_exists`) from duck-typed optional methods to protocol methods,
because pgvector is unready in a completely different way from Qdrant -- a
background build that has not caught up, versus an index row left
`indisvalid = false` by an interrupted build -- and both produce the same
symptom: recall that looks perfect because the index was never consulted. An
adapter that simply did not implement the method would have had its
unreadiness skipped silently, which is the one failure this check exists to
prevent.

**A stub pass is not an engine pass.** The stub is exact, so recall is 1.0 by
construction and it can never surface an approximate-index bug. It proves the
protocol; only a live engine proves the engine.

    pytest oneground/adapters/conformance.py                  # stub only
    ONEGROUND_QDRANT_URL=http://localhost:6333 pytest ...     # + Qdrant
    ONEGROUND_PGVECTOR_URL=postgresql://... pytest ...        # + pgvector
"""

import os
import sys
import uuid

import numpy as np

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.adapters import (AdapterError, get, managed_namespace,  # noqa: E402
                                namespace_for)
from oneground.adapters.base import NAMESPACE_PREFIX  # noqa: E402
from oneground.truth import exact_knn  # noqa: E402

try:
    import pytest
except ImportError:                                   # pragma: no cover
    pytest = None

# The brief's numbers. Small enough to run in seconds against a container,
# large enough that an HNSW index is actually built rather than brute-forced.
N_VECTORS = 5000
N_QUERIES = 200
DIM = 64
K = 10
RECALL_FLOOR = 0.95
GENEROUS_EF = 512
SEED = 20260911

QDRANT_URL_ENV = "ONEGROUND_QDRANT_URL"
PGVECTOR_URL_ENV = "ONEGROUND_PGVECTOR_URL"

# Every live engine and the variable that points at it. Adding an engine here
# is the only wiring a new adapter needs in this file.
LIVE_ENGINES = (("qdrant", QDRANT_URL_ENV), ("pgvector", PGVECTOR_URL_ENV))


def _corpus(seed=SEED):
    """Blobby, normalized. Normalized because inner product then ranks the
    same as cosine, which keeps the metric choice from changing the answer."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(12, DIM))
    x = np.vstack([c + rng.normal(0, 0.25, size=(N_VECTORS // 12 + 1, DIM))
                   for c in centres])[:N_VECTORS].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = x[rng.choice(N_VECTORS, size=N_QUERIES, replace=False)].copy()
    return np.ascontiguousarray(x), np.ascontiguousarray(q)


def _recall(pred, gt):
    hits = sum(len(set(p[p >= 0].tolist()) & set(g.tolist()))
               for p, g in zip(pred, gt))
    return hits / (gt.shape[0] * gt.shape[1])


def available_engines():
    """(name, factory, how) for every engine this machine can actually reach.

    `how` is 'in-process' or the endpoint, and it is printed, because "the
    suite passed" means nothing without it.
    """
    out = [("stub", lambda: get("stub")(), "in-process")]
    for engine_name, var in LIVE_ENGINES:
        url = os.environ.get(var)
        if url:
            out.append((engine_name,
                        (lambda n=engine_name: get(n)()), url))
    return out


def _endpoint_for(name):
    for engine_name, var in LIVE_ENGINES:
        if name == engine_name:
            return os.environ.get(var, "")
    return "memory://"


def _connect(name, factory):
    engine = factory()
    engine.connect(_endpoint_for(name))
    return engine


def _session():
    """A fresh session id per run, so two suites cannot collide."""
    return "conf-" + uuid.uuid4().hex[:8]


# --------------------------------------------------------------------------
# the seven checks, as one function so a real engine is set up once
# --------------------------------------------------------------------------

def run_conformance(name, factory, endpoint_desc, verbose=True):
    """Run every check against one engine. Returns a dict of results.

    Raises on failure -- this is a gate, not a report.
    """
    def say(msg):
        if verbose:
            print(f"    [{name}] {msg}", flush=True)

    results = {"engine": name, "endpoint": endpoint_desc}
    x, q = _corpus()
    gt = exact_knn(x, q, K)

    engine = _connect(name, factory)
    ns = namespace_for(_session(), "conformance")

    # (a) create under the prefix
    assert ns.startswith(NAMESPACE_PREFIX), ns
    # `indexing_threshold: 1` (KB) makes the engine actually build its index.
    # Qdrant's default is 20,000 KB, so a 5,000 x 64 collection (1.3 MB) is
    # never indexed and check (c) would report recall 1.0 without an HNSW
    # graph ever being consulted -- a green test that proves nothing about the
    # index. Measured during task 009; see qdrant/ADAPTER.md.
    with managed_namespace(engine, ns, DIM, "inner_product",
                           {"m": 16, "ef_construct": 200,
                            "indexing_threshold": 1}) as namespace:
        say(f"(a) created {namespace}")

        # (b) upsert
        stats = engine.upsert(namespace, range(N_VECTORS), x)
        assert stats.n_vectors == N_VECTORS, stats
        assert stats.vectors_per_second > 0
        results["ingest_vectors_per_second"] = stats.vectors_per_second
        say(f"(b) upserted {N_VECTORS} at "
            f"{stats.vectors_per_second:,.0f}/s")

        # Wait for the index before measuring, or (c) measures a linear scan.
        # Required, not probed: an adapter without this method fails here
        # rather than having its unreadiness skipped.
        assert callable(getattr(engine, "wait_for_index", None)), (
            f"{name}: wait_for_index is a required protocol method. An engine "
            "that is always ready returns (points, points, 0.0) and says so "
            "in its ADAPTER.md -- it does not omit the method.")
        indexed, points, secs = engine.wait_for_index(namespace)
        results["indexed_vectors"] = indexed
        results["index_seconds"] = secs
        assert points == N_VECTORS, (
            f"wait_for_index reports {points} points, upserted {N_VECTORS}")
        assert indexed >= points, (
            f"only {indexed}/{points} vectors indexed after {secs:.1f}s; "
            "measuring here would measure an exact scan, not the index")
        say(f"    indexed {indexed}/{points} in {secs:.1f}s")

        # (c) recall with a generous ef
        cand = engine.search(namespace, q, K, {"hnsw_ef": GENEROUS_EF})
        assert cand.ids.shape == (N_QUERIES, K), cand.ids.shape
        assert cand.latencies_ms.shape == (N_QUERIES,)
        recall = _recall(cand.ids, gt)
        results["recall_at_10"] = recall
        results["latency_p50_ms"] = float(np.percentile(cand.latencies_ms, 50))
        assert recall >= RECALL_FLOOR, (
            f"recall@{K} {recall:.4f} < {RECALL_FLOOR} at ef={GENEROUS_EF}. "
            "With a generous ef this is not a tuning miss -- something in the "
            "adapter's ingest, metric or id mapping is wrong.")
        say(f"(c) recall@{K} {recall:.4f} >= {RECALL_FLOOR}")

        # (d) describe reports what was set
        facts = engine.describe(namespace)
        assert facts.point_count == N_VECTORS, (
            f"describe() says {facts.point_count} points, upserted "
            f"{N_VECTORS}")
        assert facts.dim == DIM, facts
        assert facts.kind == "declared", (
            "engine-reported facts must be labelled declared")
        results["describe"] = facts.as_dict()
        say(f"(d) describe: {facts.point_count} points, dim {facts.dim}, "
            f"index {facts.index_type} {facts.index_params}")

        # (e) scroll returns what went in
        got_ids, got_vecs = engine.scroll(namespace, 100)
        assert len(got_ids) == 100, len(got_ids)
        assert got_vecs.shape == (100, DIM), got_vecs.shape
        order = np.argsort(got_ids)
        expect = x[got_ids[order]]
        assert np.allclose(got_vecs[order], expect, atol=1e-5), (
            "scroll() returned vectors that differ from what was upserted")
        say(f"(e) scrolled {len(got_ids)} vectors, all match")

    # (f) deleted on the way out
    assert not _exists(engine, ns), f"{ns} still exists after the block"
    say("(f) namespace deleted")
    results["deleted"] = True

    # (g) cleanup runs when the body raises
    ns2 = namespace_for(_session(), "cleanup")
    engine2 = _connect(name, factory)
    raised = False
    try:
        with managed_namespace(engine2, ns2, DIM, "inner_product"):
            raise RuntimeError("injected: the body failed")
    except RuntimeError as e:
        raised = "injected" in str(e)
    assert raised, "the injected failure did not propagate"
    assert not _exists(engine2, ns2), (
        f"{ns2} survived a failing body -- the finally did not run")
    say("(g) namespace deleted after an exception")
    results["cleanup_on_failure"] = True
    return results


def _exists(engine, ns):
    """Required, not probed.

    The old fallback -- call describe() and treat any exception as "gone" --
    could not tell a deleted namespace from an unreachable engine, so check
    (f) would have passed against a database that had simply fallen over.
    """
    checker = getattr(engine, "namespace_exists", None)
    assert callable(checker), (
        f"{getattr(engine, 'name', engine)}: namespace_exists is a required "
        "protocol method; the conformance suite has to be able to prove a "
        "namespace was deleted")
    return checker(ns)


# --------------------------------------------------------------------------
# pytest surface
# --------------------------------------------------------------------------

def test_stub_conformance():
    """Always runs. Proves the protocol, not an engine."""
    run_conformance("stub", lambda: get("stub")(), "in-process", verbose=False)


def test_qdrant_conformance_live():
    """Runs only when ONEGROUND_QDRANT_URL is set. Never faked."""
    url = os.environ.get(QDRANT_URL_ENV)
    if not url:
        if pytest is not None:
            pytest.skip(f"{QDRANT_URL_ENV} not set; live Qdrant not contacted")
        return
    run_conformance("qdrant", lambda: get("qdrant")(), url, verbose=False)


def test_pgvector_conformance_live():
    """Runs only when ONEGROUND_PGVECTOR_URL is set. Never faked."""
    url = os.environ.get(PGVECTOR_URL_ENV)
    if not url:
        if pytest is not None:
            pytest.skip(f"{PGVECTOR_URL_ENV} not set; live pgvector not "
                        "contacted")
        return
    run_conformance("pgvector", lambda: get("pgvector")(), url, verbose=False)


def test_every_registered_adapter_implements_the_whole_protocol():
    """The protocol is a list of methods, and this is what makes it one.

    Written after task 015 promoted `wait_for_index` and `namespace_exists`
    from duck-typed optional methods: an adapter that omits a required method
    should fail here, on any machine, rather than only in whichever live check
    happened to call it.
    """
    from oneground.adapters import engines as registered

    required = ("connect", "create_namespace", "upsert", "search", "describe",
                "scroll", "delete_namespace", "namespace_exists",
                "wait_for_index")
    for engine_name in registered():
        adapter = get(engine_name)()
        missing = [m for m in required
                   if not callable(getattr(adapter, m, None))]
        assert not missing, f"{engine_name} is missing {', '.join(missing)}"
        assert getattr(adapter, "name", None) == engine_name


def test_namespace_prefix_is_enforced():
    """A namespace outside the prefix must be refused, not created."""
    engine = _connect("stub", lambda: get("stub")())
    try:
        with managed_namespace(engine, "someones-real-collection", 8,
                               "inner_product"):
            pass
    except AdapterError as e:
        assert NAMESPACE_PREFIX in str(e)
        assert not engine.namespace_exists("someones-real-collection")
        return
    raise AssertionError("an unprefixed namespace was created")


def test_cleanup_runs_when_the_body_raises():
    """(g) on its own, so a failure here names the right thing."""
    engine = _connect("stub", lambda: get("stub")())
    ns = namespace_for(_session(), "boom")
    try:
        with managed_namespace(engine, ns, 8, "inner_product"):
            raise RuntimeError("injected")
    except RuntimeError:
        pass
    assert ns in engine.deleted_namespaces
    assert not engine.namespace_exists(ns)


def test_cleanup_runs_when_the_engine_itself_fails_mid_run():
    """The harder case: the failure comes from inside the engine, during
    upsert, rather than from the caller's code."""
    engine = get("stub")(fail_on="upsert")
    engine.connect("memory://")
    ns = namespace_for(_session(), "enginefail")
    try:
        with managed_namespace(engine, ns, 8, "inner_product"):
            engine.upsert(ns, [1], np.zeros((1, 8), dtype=np.float32))
    except AdapterError:
        pass
    assert not engine.namespace_exists(ns), (
        "an engine-side failure left the namespace behind")


def test_credentials_come_from_the_environment_only():
    engine = get("stub")()
    try:
        engine.connect("memory://", credentials_env="ONEGROUND_NO_SUCH_KEY")
    except AdapterError as e:
        assert "ONEGROUND_NO_SUCH_KEY" in str(e)
        return
    raise AssertionError("a missing credentials env var was tolerated")


def main(argv=None):
    """Run against every engine this machine can reach, and say which."""
    argv = sys.argv[1:] if argv is None else argv
    found = available_engines()
    print(f"conformance: {len(found)} engine(s) reachable")
    failures = 0
    for name, factory, how in found:
        print(f"  {name} ({how})")
        try:
            run_conformance(name, factory, how)
            print(f"    PASS")
        except Exception as e:                        # noqa: BLE001
            failures += 1
            print(f"    FAIL {type(e).__name__}: {e}")
    if not os.environ.get(QDRANT_URL_ENV):
        print(f"  qdrant SKIPPED: {QDRANT_URL_ENV} not set "
              "(a skip, not a pass)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
