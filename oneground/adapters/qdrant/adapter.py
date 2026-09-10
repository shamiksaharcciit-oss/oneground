"""Qdrant, via the official `qdrant-client`.

The first adapter, and therefore the one that shaped the protocol. Anything
awkward here is documented in `ADAPTER.md` rather than smoothed over, because
the awkward parts are what a second adapter needs to know.

Everything the engine says about itself — its version, its HNSW parameters,
its point count, its shard layout — is `declared`. Everything oneground timed
or computed is measured. `describe()` keeps the raw response so a later reader
can check a claim this file did not anticipate.
"""

import time
from typing import Any, Dict, Optional

import numpy as np

from ..base import (AdapterError, Candidates, EngineFacts, NotConnected,
                    UpsertStats, register)

NAME = "qdrant"

# Metric names oneground uses -> Qdrant's. oneground's vectors are
# L2-normalized, so inner product and cosine rank identically; both are
# offered because an engine's own choice changes what it stores.
METRICS = {"inner_product": "Dot", "dot": "Dot", "ip": "Dot",
           "cosine": "Cosine", "l2": "Euclid", "euclid": "Euclid"}

DEFAULT_BATCH = 512


class QdrantAdapter:
    """One connection, many namespaces."""

    name = NAME

    def __init__(self, timeout=120.0, batch_size=DEFAULT_BATCH,
                 prefer_grpc=False):
        self._client = None
        self._version = "unknown"
        self._timeout = timeout
        self._batch_size = int(batch_size)
        self._prefer_grpc = prefer_grpc

    # -- lifecycle ---------------------------------------------------------
    def connect(self, endpoint, credentials_env=None):
        """Connect. The API key, if any, comes from the environment only."""
        import os

        from qdrant_client import QdrantClient

        api_key = None
        if credentials_env:
            api_key = os.environ.get(credentials_env)
            if not api_key:
                raise AdapterError(
                    f"qdrant: {credentials_env} is named as the credentials "
                    "environment variable but is not set. oneground reads "
                    "keys from the environment only, never from the "
                    "requirements file.")
        try:
            self._client = QdrantClient(url=endpoint, api_key=api_key,
                                        timeout=self._timeout,
                                        prefer_grpc=self._prefer_grpc)
            # Qdrant's root endpoint carries the version; it is the cheapest
            # call that proves the connection is real rather than lazy.
            self._version = self._read_version(endpoint)
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"qdrant: could not connect to {endpoint}: "
                               f"{e}") from None

    def _read_version(self, endpoint=None):
        """The engine's own version string, for the declared record.

        Qdrant serves it from the REST root. The client object does not expose
        it, so this reads the endpoint directly rather than reaching into the
        client's private attributes -- which is both more stable across client
        versions and honest about where the fact comes from.

        A version that cannot be read is recorded as "unknown", never guessed:
        "recall 0.98 on Qdrant" means nothing without which Qdrant.
        """
        url = (endpoint or "").rstrip("/")
        if url:
            try:
                import json as _json
                import urllib.request
                with urllib.request.urlopen(url + "/", timeout=10) as r:
                    v = (_json.loads(r.read().decode("utf-8")) or {}).get(
                        "version")
                    if v:
                        return str(v)
            except Exception:                         # noqa: BLE001
                pass
        try:
            self._client.get_collections()            # proves the connection
            return "unknown"
        except Exception:                             # noqa: BLE001
            return "unknown"

    @property
    def version(self):
        return self._version

    def _need(self):
        if self._client is None:
            raise NotConnected("qdrant: connect() first")
        return self._client

    # -- namespaces --------------------------------------------------------
    def create_namespace(self, ns, dim, metric="inner_product",
                         index_params=None):
        from qdrant_client import models as qm

        c = self._need()
        p = dict(index_params or {})
        try:
            distance = getattr(qm.Distance, METRICS[str(metric).lower()].upper())
        except KeyError:
            raise AdapterError(
                f"qdrant: unsupported metric {metric!r}; use one of "
                f"{sorted(set(METRICS))}") from None

        hnsw = None
        if any(k in p for k in ("m", "ef_construct", "full_scan_threshold")):
            hnsw = qm.HnswConfigDiff(
                m=p.get("m"),
                ef_construct=p.get("ef_construct"),
                full_scan_threshold=p.get("full_scan_threshold"))

        # `indexing_threshold` is the knob that decides whether an HNSW graph
        # is ever built. It is a segment size in KILOBYTES and defaults to
        # 20,000 (20 MB): below it Qdrant answers every search with an exact
        # scan, and `indexed_vectors_count` stays 0 while `status` reports
        # "green". Measured during task 009 -- a 5,000 x 64 collection (1.3 MB)
        # returned recall 1.0000 at ef=4, which is not HNSW being good, it is
        # HNSW never being consulted.
        #
        # oneground therefore sets it explicitly whenever the caller asks for
        # an index, rather than inheriting a default that silently turns a
        # measurement of an index into a measurement of a linear scan.
        optimizers = None
        if "indexing_threshold" in p:
            optimizers = qm.OptimizersConfigDiff(
                indexing_threshold=int(p["indexing_threshold"]))
        try:
            c.create_collection(
                collection_name=ns,
                vectors_config=qm.VectorParams(size=int(dim),
                                               distance=distance),
                hnsw_config=hnsw,
                optimizers_config=optimizers)
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"qdrant: create_collection({ns}): {e}") from None

    def delete_namespace(self, ns):
        c = self._need()
        try:
            c.delete_collection(collection_name=ns)
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"qdrant: delete_collection({ns}): {e}") from None

    def namespace_exists(self, ns):
        c = self._need()
        try:
            return c.collection_exists(collection_name=ns)
        except Exception:                             # noqa: BLE001
            names = {x.name for x in c.get_collections().collections}
            return ns in names

    def wait_for_index(self, ns, timeout=120.0, poll=0.5):
        """Block until every point is in the HNSW graph, or say it is not.

        Returns (indexed, points, seconds). **`status: green` is not the
        signal**: Qdrant reports green with `indexed_vectors_count == 0`,
        because green means "no operations pending", not "indexed". The only
        field that answers the question is `indexed_vectors_count`.

        A caller that measures without waiting measures an exact scan and
        calls it an index. `verify` waits and records how long it took, so a
        run that never finished indexing is visible in the receipt rather than
        showing up as suspiciously perfect recall.
        """
        c = self._need()
        t0 = time.time()
        indexed = points = 0
        while time.time() - t0 < timeout:
            info = c.get_collection(collection_name=ns)
            indexed = int(getattr(info, "indexed_vectors_count", 0) or 0)
            points = int(getattr(info, "points_count", 0) or 0)
            if points and indexed >= points:
                return indexed, points, time.time() - t0
            time.sleep(poll)
        return indexed, points, time.time() - t0

    # -- ingest ------------------------------------------------------------
    def upsert(self, ns, ids, vectors, payload=None):
        """Batched upsert with `wait=True`.

        `wait=True` on every batch is deliberate and it costs throughput. With
        `wait=False` the call returns before the write is durable and the
        measured "ingest rate" would be the rate of *accepting* vectors, not
        of storing them -- a number that flatters the engine and means
        nothing. See ADAPTER.md.
        """
        from qdrant_client import models as qm

        c = self._need()
        vectors = np.ascontiguousarray(np.asarray(vectors, dtype=np.float32))
        ids = [int(i) for i in ids]
        n, batches = len(ids), 0
        t0 = time.time()
        try:
            for start in range(0, n, self._batch_size):
                end = min(start + self._batch_size, n)
                points = qm.Batch(
                    ids=ids[start:end],
                    vectors=vectors[start:end].tolist(),
                    payloads=(list(payload[start:end]) if payload is not None
                              else None))
                c.upsert(collection_name=ns, points=points, wait=True)
                batches += 1
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"qdrant: upsert({ns}): {e}") from None
        seconds = time.time() - t0

        reported = None
        try:
            reported = int(c.count(collection_name=ns, exact=True).count)
        except Exception:                             # noqa: BLE001
            pass
        return UpsertStats(n_vectors=n, seconds=seconds, batches=batches,
                           engine_reported_count=reported)

    # -- search ------------------------------------------------------------
    def search(self, ns, queries, k, params=None):
        """One query at a time, timed client-side.

        Sequential and single-client on purpose: this measures latency
        *shape*, and batching or concurrency here would produce a number that
        looks like latency and behaves like throughput.
        """
        from qdrant_client import models as qm

        c = self._need()
        p = dict(params or {})
        search_params = None
        if "ef" in p or "hnsw_ef" in p or "exact" in p:
            search_params = qm.SearchParams(
                hnsw_ef=p.get("hnsw_ef", p.get("ef")),
                exact=bool(p.get("exact", False)))

        queries = np.ascontiguousarray(np.asarray(queries, dtype=np.float32))
        n_q = len(queries)
        ids = np.full((n_q, k), -1, dtype=np.int64)
        scores = np.full((n_q, k), -np.inf, dtype=np.float32)
        lat = np.zeros(n_q, dtype=np.float64)

        for i in range(n_q):
            t0 = time.perf_counter()
            try:
                res = c.query_points(collection_name=ns,
                                     query=queries[i].tolist(),
                                     limit=k, search_params=search_params,
                                     with_payload=False,
                                     with_vectors=False).points
            except Exception as e:                    # noqa: BLE001
                raise AdapterError(f"qdrant: search({ns}): {e}") from None
            lat[i] = (time.perf_counter() - t0) * 1000.0
            for j, pt in enumerate(res[:k]):
                ids[i, j] = int(pt.id)
                scores[i, j] = float(pt.score)
        return Candidates(ids=ids, scores=scores, latencies_ms=lat)

    # -- facts -------------------------------------------------------------
    def describe(self, ns):
        c = self._need()
        try:
            info = c.get_collection(collection_name=ns)
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"qdrant: get_collection({ns}): {e}") from None

        raw = _model_dump(info)
        vectors_cfg = (((raw.get("config") or {}).get("params") or {})
                       .get("vectors") or {})
        hnsw = ((raw.get("config") or {}).get("hnsw_config") or {})

        # Qdrant reports several counts; `points_count` is the one that means
        # "rows you can search". See ADAPTER.md on why it can lag.
        point_count = raw.get("points_count")
        if point_count is None:
            try:
                point_count = int(c.count(collection_name=ns,
                                          exact=True).count)
            except Exception:                         # noqa: BLE001
                point_count = None

        nodes = None
        shards = ((raw.get("config") or {}).get("params") or {}).get(
            "shard_number")
        replicas = ((raw.get("config") or {}).get("params") or {}).get(
            "replication_factor")
        try:
            cluster = _model_dump(c.get_collection_cluster_info(
                collection_name=ns))
            raw["cluster"] = cluster
            peers = cluster.get("peer_id")
            local = cluster.get("local_shards") or []
            remote = cluster.get("remote_shards") or []
            shards = shards or (len(local) + len(remote)) or None
            nodes = 1 + len({r.get("peer_id") for r in remote
                             if isinstance(r, dict)}) if remote else (
                1 if peers is not None else None)
        except Exception:                             # noqa: BLE001
            pass          # single-node deployments may not expose cluster info

        raw["indexed_vectors_count"] = getattr(info, "indexed_vectors_count",
                                               None)
        raw["status"] = str(getattr(info, "status", ""))
        return EngineFacts(
            engine=NAME, version=self._version, namespace=ns,
            point_count=point_count,
            dim=vectors_cfg.get("size"),
            metric=vectors_cfg.get("distance"),
            index_type="hnsw",
            index_params={k: v for k, v in hnsw.items() if v is not None},
            shards=shards, replicas=replicas, nodes=nodes, raw=raw)

    # -- scroll ------------------------------------------------------------
    def scroll(self, ns, limit):
        """Read `limit` points back out, with their vectors. Read-only."""
        c = self._need()
        ids, vecs, offset = [], [], None
        try:
            while len(ids) < limit:
                page, offset = c.scroll(
                    collection_name=ns,
                    limit=min(1024, limit - len(ids)),
                    offset=offset, with_payload=False, with_vectors=True)
                if not page:
                    break
                for pt in page:
                    v = pt.vector
                    if isinstance(v, dict):          # named vectors
                        v = next(iter(v.values()))
                    ids.append(int(pt.id))
                    vecs.append(v)
                if offset is None:
                    break
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"qdrant: scroll({ns}): {e}") from None
        if not ids:
            return np.zeros(0, dtype=np.int64), np.zeros((0, 0),
                                                         dtype=np.float32)
        return (np.asarray(ids, dtype=np.int64),
                np.ascontiguousarray(np.asarray(vecs, dtype=np.float32)))


def _model_dump(obj):
    """pydantic v2, v1, or a plain object -- adapters see all three."""
    for attr in ("model_dump", "dict"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:                         # noqa: BLE001
                pass
    return dict(getattr(obj, "__dict__", {}) or {})


register(NAME, QdrantAdapter)
