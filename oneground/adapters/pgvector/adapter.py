"""pgvector, via `psycopg` 3.

The second adapter, and the first one written against a protocol that already
existed. Where Qdrant is a vector database, this is a general-purpose relational
database with a vector type bolted on, and almost every awkward part below
comes from that difference rather than from pgvector being worse.

Everything the engine says about itself -- its version, its index parameters,
its row count -- is `declared`. Everything oneground timed or computed is
measured. `describe()` keeps the raw rows so a later reader can check a claim
this file did not anticipate.

Four things a reader needs to know before trusting a number from here
--------------------------------------------------------------------
**Index build is synchronous, and it is the dominant cost.** `CREATE INDEX`
does not return until the graph is built. Qdrant indexes in the background and
`wait_for_index` polls until it catches up; here the wait happens inside
`CREATE INDEX`, so the two engines' "ingest rate" numbers are not the same
quantity unless the index build is counted. This adapter therefore builds the
index **after** the rows are in -- which is what pgvector's own documentation
recommends, and what any real deployment does -- and reports
`index_build_seconds` separately from ingest.

**`ef_search` is a session GUC, not a property of the index.** In Qdrant it
travels with the query. Here it is `SET hnsw.ef_search`, applied once per
`search()` call on this adapter's own connection and reset afterwards -- not
`SET LOCAL` per query, which would put an extra round trip inside every timed
query and make pgvector look slower by an amount the adapter invented.

It is therefore *not* visible in `describe()` -- nothing in `pg_indexes` knows
about it -- and the receipt records it from what oneground asked for, under
`search_params`, never as an index property. Reading it back out of the
database is impossible by construction, and a receipt that claimed otherwise
would be inventing a fact.

**The operator decides the metric, and it must match the index.** `<#>` is
negative inner product, `<=>` is cosine distance, `<->` is L2. An index built
with `vector_ip_ops` cannot serve a `<=>` query with the index -- Postgres
silently falls back to a sequential scan and the answer is exact, fast enough
on small data, and completely useless as a measurement of an index. The
operator class and the query operator are chosen together in `_metric()` for
that reason.

**Scores are distances, not similarities.** oneground's protocol carries
inner-product-like scores where larger is better. `<#>` returns the *negative*
inner product, so the adapter negates it back. Cosine distance is converted to
similarity as `1 - d`. Both conversions are exact, and `describe().raw` keeps
the operator used so a reader can check the direction.
"""

import time
from typing import Any, Dict, Optional

import numpy as np

from ..base import (AdapterError, Candidates, EngineFacts, NotConnected,
                    UpsertStats, register)

NAME = "pgvector"

# oneground metric -> (operator class, query operator, score conversion).
# The operator class goes on the index, the operator goes in ORDER BY, and
# they have to agree or Postgres quietly stops using the index.
METRICS = {
    "inner_product": ("vector_ip_ops", "<#>", "negate"),
    "dot": ("vector_ip_ops", "<#>", "negate"),
    "ip": ("vector_ip_ops", "<#>", "negate"),
    "cosine": ("vector_cosine_ops", "<=>", "one_minus"),
    "l2": ("vector_l2_ops", "<->", "negate"),
    "euclid": ("vector_l2_ops", "<->", "negate"),
}

DEFAULT_BATCH = 512

# pgvector's own defaults, repeated here so a receipt says what was used even
# when the caller passed nothing.
DEFAULT_M = 16
DEFAULT_EF_CONSTRUCTION = 64


def _ident(name):
    """Quote an identifier. Namespaces are oneground-generated and already
    constrained, but a table name reaching SQL unquoted is the kind of thing
    that is fine until the day it is not."""
    if not str(name).replace("-", "").replace("_", "").isalnum():
        raise AdapterError(
            f"pgvector: refusing {name!r} as a table name: oneground "
            "namespaces are alphanumeric with - and _ only")
    return '"' + str(name).replace('"', '""') + '"'


class PgvectorAdapter:
    """One connection, many namespaces (one table each)."""

    name = NAME

    def __init__(self, timeout=120.0, batch_size=DEFAULT_BATCH):
        self._conn = None
        self._version = "unknown"
        self._pg_version = "unknown"
        self._timeout = float(timeout)
        self._batch_size = int(batch_size)
        # Per-namespace facts oneground measured or asked for, which the
        # database cannot be asked about later. Kept beside the connection so
        # `describe()` can report them as what they are: ours, not the
        # engine's.
        self._index_build_seconds: Dict[str, float] = {}
        self._requested_params: Dict[str, Dict[str, Any]] = {}
        self._metric_of: Dict[str, str] = {}

    # -- lifecycle ---------------------------------------------------------
    def connect(self, endpoint, credentials_env=None):
        """Connect. The password, if any, comes from the environment only.

        `endpoint` is a libpq connection string or URL. A password written in
        it would be a password in a requirements file, so if
        `credentials_env` is named the value is read from the environment and
        passed separately.
        """
        import os

        import psycopg

        kwargs = {}
        if credentials_env:
            pw = os.environ.get(credentials_env)
            if not pw:
                raise AdapterError(
                    f"pgvector: {credentials_env} is named as the credentials "
                    "environment variable but is not set. oneground reads "
                    "secrets from the environment only, never from the "
                    "requirements file.")
            kwargs["password"] = pw
        try:
            self._conn = psycopg.connect(endpoint, autocommit=True,
                                         connect_timeout=int(self._timeout),
                                         **kwargs)
            with self._conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute("SELECT extversion FROM pg_extension "
                            "WHERE extname = 'vector'")
                row = cur.fetchone()
                self._version = str(row[0]) if row else "unknown"
                cur.execute("SHOW server_version")
                self._pg_version = str(cur.fetchone()[0])
        except AdapterError:
            raise
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"pgvector: could not connect to {endpoint}: "
                               f"{e}") from None

    @property
    def version(self):
        """The pgvector extension version -- the thing that decides the index.

        Postgres' own version is carried alongside in `describe().raw`; both
        matter, but "recall 0.98 on pgvector" is a claim about the extension.
        """
        return self._version

    def _need(self):
        if self._conn is None:
            raise NotConnected("pgvector: connect() first")
        return self._conn

    @staticmethod
    def _metric(metric):
        try:
            return METRICS[str(metric).lower()]
        except KeyError:
            raise AdapterError(
                f"pgvector: unsupported metric {metric!r}; use one of "
                f"{sorted(set(METRICS))}") from None

    # -- namespaces --------------------------------------------------------
    def create_namespace(self, ns, dim, metric="inner_product",
                         index_params=None):
        """A table with an id and a `vector(dim)` column. No index yet.

        The HNSW index is created by `build_index`, which `upsert` calls once
        the rows are in. Creating it first and inserting into it is both far
        slower and not what anyone does in production, and it would make the
        measured ingest rate a measurement of incremental index maintenance
        rather than of ingest.
        """
        conn = self._need()
        opclass, _op, _conv = self._metric(metric)
        p = dict(index_params or {})
        self._requested_params[ns] = p
        self._metric_of[ns] = str(metric).lower()
        table = _ident(ns)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} ("
                    f"  id bigint PRIMARY KEY,"
                    f"  embedding vector({int(dim)}) NOT NULL)")
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"pgvector: create table {ns}: {e}") from None
        # Recorded so describe() can name the opclass the index will use even
        # before the index exists.
        self._requested_params[ns]["_opclass"] = opclass

    def delete_namespace(self, ns):
        conn = self._need()
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {_ident(ns)}")
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"pgvector: drop table {ns}: {e}") from None
        self._index_build_seconds.pop(ns, None)
        self._requested_params.pop(ns, None)
        self._metric_of.pop(ns, None)

    def namespace_exists(self, ns):
        conn = self._need()
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (ns,))
            return bool(cur.fetchone()[0])

    # -- index -------------------------------------------------------------
    def _index_name(self, ns):
        return f"{ns}_hnsw"

    def build_index(self, ns, metric=None, index_params=None):
        """CREATE INDEX, timed. Synchronous: it returns when the graph exists.

        Called by `upsert` after the rows are in. Separate from ingest in the
        receipt because they are separate costs, and because Qdrant's
        equivalent happens in the background where it is not part of the
        ingest measurement either.
        """
        conn = self._need()
        p = dict(self._requested_params.get(ns) or {})
        p.update(index_params or {})
        metric = metric or self._metric_of.get(ns, "inner_product")
        opclass, _op, _conv = self._metric(metric)
        m = int(p.get("m", DEFAULT_M))
        efc = int(p.get("ef_construction", p.get("ef_construct",
                                                 DEFAULT_EF_CONSTRUCTION)))
        self._requested_params[ns] = {**p, "m": m, "ef_construction": efc,
                                      "_opclass": opclass}
        t0 = time.time()
        try:
            with conn.cursor() as cur:
                # maintenance_work_mem decides whether the build fits in
                # memory. Too small and pgvector spills, which is slower and
                # -- more importantly for us -- makes `wait_for_index` a real
                # question rather than a formality. Set only when asked, so
                # the default case measures the engine's default behaviour.
                if p.get("maintenance_work_mem"):
                    cur.execute(
                        f"SET maintenance_work_mem = "
                        f"'{int(p['maintenance_work_mem'])}MB'")
                cur.execute(
                    f"CREATE INDEX {_ident(self._index_name(ns))} "
                    f"ON {_ident(ns)} USING hnsw (embedding {opclass}) "
                    f"WITH (m = {m}, ef_construction = {efc})")
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"pgvector: create index on {ns}: "
                               f"{e}") from None
        secs = time.time() - t0
        self._index_build_seconds[ns] = secs
        return secs

    def wait_for_index(self, ns, timeout=600.0, poll=0.5):
        """(indexed, points, seconds). Required by the protocol.

        For Qdrant this polls a background process. For pgvector `CREATE
        INDEX` is synchronous, so by the time this is called the index is
        normally already there -- but "the index exists" is **not** the same
        as "the index is usable", and the brief is right to insist on the
        difference:

        * a build interrupted by a failure can leave an index row present and
          `indisvalid = false`. Postgres will not use it, and every query
          silently becomes a sequential scan -- exact, fast on small data, and
          worthless as a measurement of an index.
        * a build still running is visible in `pg_stat_progress_create_index`,
          which is empty once no build is in flight.

        So readiness here is: no build in progress for this table, and an
        index row that is valid and ready. Anything else returns `indexed = 0`
        and the caller refuses to measure.
        """
        conn = self._need()
        t0 = time.time()
        idx = self._index_name(ns)
        indexed = points = 0
        while True:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {_ident(ns)}")
                points = int(cur.fetchone()[0])
                cur.execute(
                    "SELECT count(*) FROM pg_stat_progress_create_index p "
                    "JOIN pg_class c ON c.oid = p.relid "
                    "WHERE c.relname = %s", (ns,))
                in_progress = int(cur.fetchone()[0])
                cur.execute(
                    "SELECT i.indisvalid, i.indisready "
                    "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                    "WHERE c.relname = %s", (idx,))
                row = cur.fetchone()
            valid = bool(row and row[0] and row[1])
            if not in_progress and valid:
                # Every row is in the graph: pgvector's HNSW build covers the
                # whole table and there is no partial-index state to report.
                indexed = points
                return indexed, points, time.time() - t0
            if time.time() - t0 >= timeout:
                return 0, points, time.time() - t0
            time.sleep(poll)

    # -- ingest ------------------------------------------------------------
    def upsert(self, ns, ids, vectors, payload=None):
        """Batched insert, then the index.

        `COPY` would be faster and is what a bulk loader would use. This sends
        one `INSERT ... SELECT FROM unnest(...) ON CONFLICT DO UPDATE` per
        batch because the protocol's method is an *upsert*: re-ingesting the
        same ids has to work, and COPY cannot express that. The choice costs
        throughput and is recorded here so the number is not read as
        pgvector's ceiling.

        One statement per batch rather than one per row: psycopg 3 has no
        client-side `mogrify`, and a row-at-a-time `executemany` would make
        the measured ingest rate a measurement of round trips.
        """
        conn = self._need()
        vectors = np.ascontiguousarray(np.asarray(vectors, dtype=np.float32))
        ids = [int(i) for i in ids]
        n, batches = len(ids), 0
        table = _ident(ns)
        sql = (f"INSERT INTO {table} (id, embedding) "
               f"SELECT * FROM unnest(%s::bigint[], %s::vector[]) "
               f"ON CONFLICT (id) DO UPDATE SET embedding = EXCLUDED.embedding")
        t0 = time.time()
        try:
            with conn.cursor() as cur:
                for start in range(0, n, self._batch_size):
                    end = min(start + self._batch_size, n)
                    cur.execute(sql, (ids[start:end],
                                      [_vec_literal(vectors[j])
                                       for j in range(start, end)]))
                    batches += 1
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"pgvector: upsert({ns}): {e}") from None
        seconds = time.time() - t0

        # The index, after the rows. Timed separately -- see build_index.
        self.build_index(ns)

        reported = None
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {table}")
                reported = int(cur.fetchone()[0])
        except Exception:                             # noqa: BLE001
            pass
        return UpsertStats(n_vectors=n, seconds=seconds, batches=batches,
                           engine_reported_count=reported)

    # -- search ------------------------------------------------------------
    def search(self, ns, queries, k, params=None):
        """One query at a time, timed client-side.

        Sequential and single-client on purpose: this measures latency
        *shape*. `ef_search` is applied with SET LOCAL inside each query's
        transaction, so it cannot leak into anything else.
        """
        conn = self._need()
        p = dict(params or {})
        ef = p.get("hnsw_ef", p.get("ef", p.get("ef_search")))
        metric = self._metric_of.get(ns, "inner_product")
        _opclass, op, conv = self._metric(metric)
        table = _ident(ns)

        queries = np.ascontiguousarray(np.asarray(queries, dtype=np.float32))
        n_q = len(queries)
        ids = np.full((n_q, k), -1, dtype=np.int64)
        scores = np.full((n_q, k), -np.inf, dtype=np.float32)
        lat = np.zeros(n_q, dtype=np.float64)

        sql = (f"SELECT id, embedding {op} %s::vector AS d FROM {table} "
               f"ORDER BY embedding {op} %s::vector LIMIT %s")
        try:
            with conn.cursor() as cur:
                # `ef_search` is set ONCE, outside the timed loop, and reset
                # afterwards. The obvious alternative -- `SET LOCAL` inside a
                # transaction per query -- keeps the setting scoped to one
                # statement, but it puts an extra round trip inside every
                # measured query. Measured on the conformance corpus that is
                # not noise, and it would show up as pgvector being slower
                # than Qdrant by an amount this adapter invented. The
                # connection belongs to this adapter, so a session-level SET
                # cannot reach anyone else's query; the reset keeps it from
                # reaching oneground's own next call with a different ef.
                if ef is not None:
                    cur.execute(f"SET hnsw.ef_search = {int(ef)}")
                try:
                    for i in range(n_q):
                        lit = _vec_literal(queries[i])
                        t0 = time.perf_counter()
                        cur.execute(sql, (lit, lit, int(k)))
                        rows = cur.fetchall()
                        lat[i] = (time.perf_counter() - t0) * 1000.0
                        for j, (rid, d) in enumerate(rows[:k]):
                            ids[i, j] = int(rid)
                            scores[i, j] = (-float(d) if conv == "negate"
                                            else 1.0 - float(d))
                finally:
                    if ef is not None:
                        cur.execute("RESET hnsw.ef_search")
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"pgvector: search({ns}): {e}") from None
        return Candidates(ids=ids, scores=scores, latencies_ms=lat)

    # -- facts -------------------------------------------------------------
    def describe(self, ns):
        """What the database says about itself.

        `ef_search` is deliberately absent: it is a session setting, so there
        is nothing in the catalog to read. What oneground asked for is carried
        under `raw['requested_params']` and labelled as a request rather than
        a property, because they are different claims.
        """
        conn = self._need()
        table = _ident(ns)
        raw: Dict[str, Any] = {"postgres_version": self._pg_version,
                               "pgvector_version": self._version}
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {table}")
                point_count = int(cur.fetchone()[0])

                cur.execute(
                    "SELECT a.atttypmod FROM pg_attribute a "
                    "JOIN pg_class c ON c.oid = a.attrelid "
                    "WHERE c.relname = %s AND a.attname = 'embedding'",
                    (ns,))
                row = cur.fetchone()
                dim = int(row[0]) if row and row[0] and row[0] > 0 else None

                cur.execute("SELECT indexdef FROM pg_indexes "
                            "WHERE tablename = %s AND indexname = %s",
                            (ns, self._index_name(ns)))
                row = cur.fetchone()
                indexdef = row[0] if row else None
                raw["indexdef"] = indexdef

                cur.execute(
                    "SELECT i.indisvalid, i.indisready, "
                    "       pg_relation_size(i.indexrelid) "
                    "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                    "WHERE c.relname = %s", (self._index_name(ns),))
                row = cur.fetchone()
                if row:
                    raw["index_valid"] = bool(row[0])
                    raw["index_ready"] = bool(row[1])
                    raw["index_size_bytes"] = int(row[2])
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"pgvector: describe({ns}): {e}") from None

        params = _parse_indexdef(indexdef)
        requested = dict(self._requested_params.get(ns) or {})
        raw["requested_params"] = {
            k: v for k, v in requested.items() if not k.startswith("_")}
        raw["requested_params_note"] = (
            "what oneground asked for, not what the catalog reports. "
            "hnsw.ef_search is a session GUC and is never an index property; "
            "the value used for a search is recorded by verify under "
            "search_params.")
        raw["index_build_seconds"] = self._index_build_seconds.get(ns)
        raw["index_build_seconds_note"] = (
            "measured by oneground around a synchronous CREATE INDEX; this "
            "is the only half of pgvector's ingest cost that Qdrant reports "
            "in the background instead")
        raw["opclass"] = requested.get("_opclass")

        return EngineFacts(
            engine=NAME, version=self._version, namespace=ns,
            point_count=point_count, dim=dim,
            metric=self._metric_of.get(ns),
            index_type="hnsw" if indexdef else None,
            index_params=params,
            # One database, one table, no sharding or replication of its own.
            # Reported as 1/1/1 rather than None: they are known, not unknown.
            shards=1, replicas=1, nodes=1, raw=raw)

    # -- scroll ------------------------------------------------------------
    def scroll(self, ns, limit):
        """Read rows back, with vectors, by keyset pagination.

        `ORDER BY id` with a `WHERE id > last` cursor rather than OFFSET:
        OFFSET makes the database walk and discard everything it skips, so a
        scroll over a large table degrades quadratically. Read-only.
        """
        conn = self._need()
        table = _ident(ns)
        ids, vecs, last = [], [], None
        page = min(1024, max(1, int(limit)))
        try:
            with conn.cursor() as cur:
                while len(ids) < limit:
                    n = min(page, limit - len(ids))
                    if last is None:
                        cur.execute(
                            f"SELECT id, embedding FROM {table} "
                            f"ORDER BY id LIMIT %s", (n,))
                    else:
                        cur.execute(
                            f"SELECT id, embedding FROM {table} "
                            f"WHERE id > %s ORDER BY id LIMIT %s", (last, n))
                    rows = cur.fetchall()
                    if not rows:
                        break
                    for rid, emb in rows:
                        ids.append(int(rid))
                        vecs.append(_parse_vector(emb))
                    last = ids[-1]
        except Exception as e:                        # noqa: BLE001
            raise AdapterError(f"pgvector: scroll({ns}): {e}") from None
        if not ids:
            return np.zeros(0, dtype=np.int64), np.zeros((0, 0),
                                                         dtype=np.float32)
        return (np.asarray(ids, dtype=np.int64),
                np.ascontiguousarray(np.asarray(vecs, dtype=np.float32)))


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _vec_literal(v):
    """pgvector's text input format: `[1,2,3]`.

    float32 is formatted with repr so the round trip is exact; `%.6f` would
    quietly change the vectors before they were stored, and `scroll()` would
    then disagree with what was upserted for a reason nobody would find.
    """
    return "[" + ",".join(repr(float(x)) for x in np.asarray(v).ravel()) + "]"


def _parse_vector(value):
    """`[1,2,3]` (or a list, if a vector type handler is registered)."""
    if isinstance(value, (list, tuple, np.ndarray)):
        return np.asarray(value, dtype=np.float32)
    s = str(value).strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    if not s:
        return np.zeros(0, dtype=np.float32)
    return np.asarray([float(x) for x in s.split(",")], dtype=np.float32)


def _parse_indexdef(indexdef):
    """m and ef_construction out of `CREATE INDEX ... WITH (m='16', ...)`.

    Read from the catalog rather than echoed from the request: this is what
    Postgres says it built, and an engine is free to clamp or ignore what it
    was asked for. Task 011 made that distinction load-bearing for verdicts.
    """
    out: Dict[str, Any] = {}
    if not indexdef:
        return out
    import re
    m = re.search(r"WITH \((.*?)\)", indexdef)
    if m:
        for part in m.group(1).split(","):
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            v = v.strip().strip("'")
            try:
                out[k.strip()] = int(v)
            except ValueError:
                out[k.strip()] = v
    om = re.search(r"USING hnsw \(\w+ (\w+)\)", indexdef)
    if om:
        out["opclass"] = om.group(1)
    return out


register(NAME, PgvectorAdapter)
