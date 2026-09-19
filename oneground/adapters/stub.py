"""An in-process engine that implements `VectorEngine` exactly.

Not a mock. It stores the vectors, searches them with exact inner product, and
reports facts about itself the same way a real engine does — so the
conformance suite has something to run against in CI, on a machine with no
Docker, and so a change to the protocol fails fast without a container.

What it deliberately does *not* do is pretend to be Qdrant. It is exact, so
its recall is 1.0 and it can never surface an approximate-index bug; it is
in-process, so its latencies are microseconds and mean nothing. **A stub pass
is not an engine pass**, and the conformance suite reports which one it ran.

`fail_on` exists for one test: proving that namespace cleanup runs when the
body raises. Injecting the failure inside the engine is the only way to make
that test exercise the real `finally` rather than a rehearsal of it.
"""

import time
from typing import Any, Dict, Optional

import numpy as np

from . import index_families as IF
from .base import (AdapterError, Candidates, EngineFacts, NotConnected,
                   UpsertStats, register)

NAME = "stub"


class StubEngine:
    """Exact search over in-memory numpy. Implements the whole protocol."""

    name = NAME

    def __init__(self, fail_on=None, latency_ms=0.0):
        self._ns: Dict[str, Dict[str, Any]] = {}
        self._connected = False
        self._version = "stub-1"
        # Method name that should raise, for the cleanup-on-failure test.
        self.fail_on = fail_on
        self._latency_ms = float(latency_ms)
        self.deleted_namespaces = []

    @property
    def version(self):
        return self._version

    def _maybe_fail(self, method):
        if self.fail_on == method:
            raise AdapterError(f"stub: injected failure in {method}()")

    def _need(self, ns=None):
        if not self._connected:
            raise NotConnected("stub: connect() first")
        if ns is not None and ns not in self._ns:
            raise AdapterError(f"stub: no namespace {ns!r}")
        return self._ns.get(ns)

    # -- what this engine can build (task 034) ------------------------------
    # The stub searches exhaustively and approximates nothing, so the one
    # family it builds is `flat` and the honest answer for the other three is
    # that it cannot build them. This is a real answer rather than a
    # placeholder: an adapter whose coverage says "everything" would make the
    # plan-time refusal untestable on a machine with no engine.
    INDEX_COVERAGE = IF.unresolved(
        NAME, "resolved by calling index_families(); the stub is in-process, "
              "so the resolution costs nothing and is never skipped")

    def index_families(self):
        """The stub answers about itself directly: it is exact, and that is
        the whole of what it builds."""
        self._need()
        return IF.resolved(
            NAME, self._version,
            {IF.FLAT: IF.FamilySupport(
                family=IF.FLAT, status=IF.BUILDS, engine_name="exact scan",
                params={},
                note="the stub scores every vector; there is no index and "
                     "nothing to tune")},
            how="the stub's search is an exhaustive inner product, by "
                "construction rather than by configuration",
            raw={"exhaustive": True})

    # -- lifecycle ---------------------------------------------------------
    def connect(self, endpoint, credentials_env=None):
        self._maybe_fail("connect")
        if credentials_env:
            import os
            if not os.environ.get(credentials_env):
                raise AdapterError(
                    f"stub: {credentials_env} is named as the credentials "
                    "environment variable but is not set")
        self._connected = True

    def create_namespace(self, ns, dim, metric="inner_product",
                         index_params=None):
        self._maybe_fail("create_namespace")
        if not self._connected:
            raise NotConnected("stub: connect() first")
        if ns in self._ns:
            raise AdapterError(f"stub: namespace {ns!r} already exists")
        self._ns[ns] = {"dim": int(dim), "metric": str(metric),
                        "index_params": dict(index_params or {}),
                        "ids": np.zeros(0, dtype=np.int64),
                        "vectors": np.zeros((0, int(dim)), dtype=np.float32)}

    def delete_namespace(self, ns):
        self._maybe_fail("delete_namespace")
        if not self._connected:
            raise NotConnected("stub: connect() first")
        self._ns.pop(ns, None)
        self.deleted_namespaces.append(ns)

    def wait_for_index(self, ns, timeout=600.0, poll=0.5):
        """Always ready: there is no index. `(points, points, 0.0)`.

        Required by the protocol from task 015, and the stub is the case the
        protocol note describes -- an engine that is genuinely always ready
        says so, rather than omitting the method and having its readiness go
        unchecked. The stub searches exactly, so there is no graph to wait
        for and no state in which its answers would be a scan pretending to
        be an index.
        """
        self._maybe_fail("wait_for_index")
        store = self._need(ns)
        n = len(store["ids"])
        return n, n, 0.0

    def namespace_exists(self, ns):
        return ns in self._ns

    # -- ingest ------------------------------------------------------------
    def upsert(self, ns, ids, vectors, payload=None):
        self._maybe_fail("upsert")
        st = self._need(ns)
        v = np.ascontiguousarray(np.asarray(vectors, dtype=np.float32))
        i = np.asarray([int(x) for x in ids], dtype=np.int64)
        if v.shape[1] != st["dim"]:
            raise AdapterError(
                f"stub: dim {v.shape[1]} does not match namespace "
                f"dim {st['dim']}")
        t0 = time.time()
        # Upsert semantics: an id present twice keeps the last write.
        keep = ~np.isin(st["ids"], i)
        st["ids"] = np.concatenate([st["ids"][keep], i])
        st["vectors"] = np.vstack([st["vectors"][keep], v])
        return UpsertStats(n_vectors=len(i), seconds=max(time.time() - t0,
                                                         1e-9),
                           batches=1, engine_reported_count=len(st["ids"]))

    # -- search ------------------------------------------------------------
    def search(self, ns, queries, k, params=None):
        self._maybe_fail("search")
        st = self._need(ns)
        q = np.ascontiguousarray(np.asarray(queries, dtype=np.float32))
        n_q = len(q)
        ids = np.full((n_q, k), -1, dtype=np.int64)
        scores = np.full((n_q, k), -np.inf, dtype=np.float32)
        lat = np.zeros(n_q, dtype=np.float64)
        if len(st["ids"]) == 0:
            return Candidates(ids=ids, scores=scores, latencies_ms=lat)
        for i in range(n_q):
            t0 = time.perf_counter()
            sims = st["vectors"] @ q[i]
            n = min(k, len(sims))
            top = np.argpartition(-sims, n - 1)[:n]
            top = top[np.argsort(-sims[top])]
            if self._latency_ms:
                time.sleep(self._latency_ms / 1000.0)
            lat[i] = (time.perf_counter() - t0) * 1000.0
            ids[i, :n] = st["ids"][top]
            scores[i, :n] = sims[top]
        return Candidates(ids=ids, scores=scores, latencies_ms=lat)

    # -- facts -------------------------------------------------------------
    def describe(self, ns):
        self._maybe_fail("describe")
        st = self._need(ns)
        return EngineFacts(
            engine=NAME, version=self._version, namespace=ns,
            point_count=int(len(st["ids"])), dim=st["dim"],
            metric=st["metric"], index_type="exact",
            index_params=dict(st["index_params"]),
            shards=1, replicas=1, nodes=1,
            # Task 017f: an empty runtime_settings cannot be told apart from
            # "nobody recorded any", and that ambiguity is half of why the
            # report said "not recorded in this run" about runs whose settings
            # were sitting in verify_info.json. The stub has no runtime
            # configuration, so it says so rather than leaving {} behind for a
            # reader to interpret.
            runtime_settings={
                "couldnt_check": "the stub engine has no runtime "
                                 "configuration: it is in-process, searches "
                                 "exactly and builds no index, so there are "
                                 "no settings that could move a number",
            },
            raw={"note": "in-process stub; exact search, no index"})

    # -- scroll ------------------------------------------------------------
    def scroll(self, ns, limit):
        self._maybe_fail("scroll")
        st = self._need(ns)
        n = min(int(limit), len(st["ids"]))
        return st["ids"][:n].copy(), st["vectors"][:n].copy()


register(NAME, StubEngine)
