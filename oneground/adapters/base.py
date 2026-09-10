"""`VectorEngine` — the one protocol every engine sits behind.

Simulation predicts; engines are reality. This is the seam between them: a
small, deliberately boring interface that any vector store can implement, so
that comparing two engines is comparing two adapters rather than two
benchmarking scripts.

**No engine of our own, no favourite, no sponsored defaults.** Nothing in this
package picks an engine for the user, and no adapter is privileged over
another. An adapter earns its place by passing the conformance suite, not by
being first.

Measured vs. declared
---------------------
The split runs through every method, and it is the reason this protocol looks
the way it does:

    measured    what oneground timed or computed itself: ingest rate, recall
                against exact ground truth, client-side latency.
    declared    what the engine *said* about itself: its version, its index
                type and parameters, its point count, its shard layout.

`EngineFacts` and `UpsertStats` carry `kind: "declared"` on the engine-reported
half because an engine reporting `hnsw.m = 16` is an engine's claim, not a
measurement — a bug, a silent clamp, or a version difference can make it
false, and the receipt has to say which side of the line each number came from.

Namespaces and cleanup
----------------------
Every namespace an adapter creates is prefixed `oneground-<session-id>-`, so a
run can never collide with a user's real collection and an abandoned run is
identifiable by name. Creation happens inside a `try` whose `finally` deletes
it — including when the body raises, which the conformance suite proves by
injecting a failure mid-run rather than trusting the code to look right.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Protocol, Sequence, Tuple

import numpy as np

DECLARED = "declared"
MEASURED = "measured"

# Every namespace this project creates anywhere, ever.
NAMESPACE_PREFIX = "oneground-"


class AdapterError(RuntimeError):
    """An engine operation failed. The message names the engine and the call."""


class NotConnected(AdapterError):
    """A method was called before `connect`."""


def namespace_for(session_id, name="verify"):
    """`oneground-<session-id>-<name>`.

    The prefix is not cosmetic: it is what lets `ls`-style cleanup find
    abandoned collections, and what guarantees a run cannot write over a
    collection someone actually uses.
    """
    sid = str(session_id).strip().replace(" ", "-")
    return f"{NAMESPACE_PREFIX}{sid}-{name}"


def is_oneground_namespace(ns):
    return str(ns).startswith(NAMESPACE_PREFIX)


@dataclass
class UpsertStats:
    """What ingesting cost. `seconds` and `rate` are measured; the rest is
    what the engine reported back."""

    n_vectors: int
    seconds: float
    batches: int
    engine_reported_count: Optional[int] = None
    kind: str = DECLARED           # engine_reported_count is the engine's claim

    @property
    def vectors_per_second(self):
        return self.n_vectors / self.seconds if self.seconds > 0 else float("nan")

    def as_dict(self):
        return {
            "n_vectors": int(self.n_vectors),
            "seconds": float(self.seconds),
            "batches": int(self.batches),
            "vectors_per_second": float(self.vectors_per_second),
            "engine_reported_count": self.engine_reported_count,
            "engine_reported_count_kind": self.kind,
        }


@dataclass
class Candidates:
    """What a search returned.

    `ids` and `scores` are (n_queries, k), -1 / -inf padded.
    `latencies_ms` is one wall-clock measurement per query, taken client-side.
    It is a latency *shape*, not a throughput figure: one client, sequential,
    no concurrency. Nothing in this package may report it as throughput.
    """

    ids: np.ndarray
    scores: np.ndarray
    latencies_ms: np.ndarray


@dataclass
class EngineFacts:
    """What the engine says about itself. Declared, all of it.

    `raw` keeps the engine's own response so a receipt can be re-read later
    against a claim this dataclass did not anticipate.
    """

    engine: str
    version: str
    namespace: str
    point_count: Optional[int] = None
    dim: Optional[int] = None
    metric: Optional[str] = None
    index_type: Optional[str] = None
    index_params: Dict[str, Any] = field(default_factory=dict)
    shards: Optional[int] = None
    replicas: Optional[int] = None
    nodes: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    kind: str = DECLARED

    def as_dict(self):
        return {
            "engine": self.engine,
            "version": self.version,
            "namespace": self.namespace,
            "point_count": self.point_count,
            "dim": self.dim,
            "metric": self.metric,
            "index_type": self.index_type,
            "index_params": dict(self.index_params),
            "shards": self.shards,
            "replicas": self.replicas,
            "nodes": self.nodes,
            "kind": self.kind,
            "note": ("every field here is what the engine reported about "
                     "itself, not something oneground measured"),
        }


class VectorEngine(Protocol):
    """The protocol. See `docs/ADAPTERS.md` for the contribution gate."""

    name: str
    version: str

    def connect(self, endpoint: str,
                credentials_env: Optional[str] = None) -> None:
        """Open a connection. Credentials come from the **environment
        variable named by `credentials_env`**, never from the requirements
        file and never as a literal — a key that can be written in a config is
        a key that can be committed."""
        ...

    def create_namespace(self, ns: str, dim: int, metric: str,
                         index_params: Optional[Dict[str, Any]] = None) -> None:
        ...

    def upsert(self, ns: str, ids: Sequence[int], vectors: np.ndarray,
               payload: Optional[Sequence[Dict[str, Any]]] = None
               ) -> UpsertStats:
        ...

    def search(self, ns: str, queries: np.ndarray, k: int,
               params: Optional[Dict[str, Any]] = None) -> Candidates:
        ...

    def describe(self, ns: str) -> EngineFacts:
        ...

    def scroll(self, ns: str, limit: int) -> Tuple[np.ndarray, np.ndarray]:
        """(ids, vectors) for `existing_collection` mode. Read-only."""
        ...

    def delete_namespace(self, ns: str) -> None:
        ...

    def namespace_exists(self, ns: str) -> bool:
        """Whether `ns` exists. Required, not duck-typed.

        The conformance suite has to prove a namespace was deleted, and an
        engine that cannot answer this cannot be checked -- falling back to
        "describe() raised, so it must be gone" cannot tell a deleted
        namespace from an unreachable engine.
        """
        ...

    def wait_for_index(self, ns: str, timeout: float = 600.0,
                       poll: float = 0.5) -> Tuple[int, int, float]:
        """Block until the index is usable. `(indexed, points, seconds)`.

        **Required for every engine**, promoted from an optional method in
        task 015. It was duck-typed while Qdrant was the only adapter, and
        pgvector showed why that was wrong: the two engines are unready in
        completely different ways, and an adapter that simply does not
        implement this would have its unreadiness silently skipped.

            Qdrant    indexes in the background. `status: green` means "no
                      operations pending", not "indexed"; only
                      `indexed_vectors_count` answers the question.
            pgvector  `CREATE INDEX` is synchronous, so the index usually
                      exists by the time anyone asks -- but an interrupted
                      build leaves it `indisvalid = false`, Postgres refuses
                      to use it, and every query becomes a sequential scan
                      that returns exact answers and measures nothing.

        Both failures produce the same symptom: recall that looks perfect
        because the index was never consulted. An engine that is genuinely
        always ready returns `(points, points, 0.0)` and says so in its
        ADAPTER.md; that is a claim it has to make, not a method it may omit.
        """
        ...


class managed_namespace:
    """Create a namespace and delete it in a `finally`, whatever happens.

    Written as a context manager rather than left to callers because "the
    cleanup ran" is a property the conformance suite has to be able to prove,
    and a `finally` scattered across six call sites cannot be proved once.

    Deletion failures are swallowed *after* being recorded on the object: a
    run that succeeded should not fail because teardown could not reach the
    engine, but a namespace that outlived its run must be visible somewhere.
    """

    def __init__(self, engine, ns, dim, metric, index_params=None):
        self.engine, self.ns = engine, ns
        self.dim, self.metric, self.index_params = dim, metric, index_params
        self.deleted = False
        self.delete_error = None

    def __enter__(self):
        if not is_oneground_namespace(self.ns):
            raise AdapterError(
                f"refusing to create {self.ns!r}: every namespace oneground "
                f"creates must start with {NAMESPACE_PREFIX!r}, so a run can "
                "never write over a collection someone actually uses")
        self.engine.create_namespace(self.ns, self.dim, self.metric,
                                     self.index_params)
        return self.ns

    def __exit__(self, exc_type, exc, tb):
        try:
            self.engine.delete_namespace(self.ns)
            self.deleted = True
        except Exception as e:                       # noqa: BLE001
            self.delete_error = str(e)
        return False        # never swallow the original exception


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------

_REGISTRY: Dict[str, Any] = {}


class UnknownEngine(KeyError):
    """A requirements file named an engine with no adapter."""


def register(name, factory):
    _REGISTRY[name] = factory


def get(name):
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownEngine(
            f"no adapter for engine {name!r}. Registered: "
            f"{', '.join(sorted(_REGISTRY)) or 'none'}") from None


def engines():
    return sorted(_REGISTRY)
