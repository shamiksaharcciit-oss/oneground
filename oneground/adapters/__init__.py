"""Engines, each behind the one `VectorEngine` protocol.

    stub      in-process exact search; what CI runs against
    qdrant    the official qdrant-client
    pgvector  Postgres + the pgvector extension, via psycopg

No engine of our own, no favourite, no sponsored defaults. An adapter earns
its place by passing `conformance.py`, and nothing here picks an engine for
the user.

See `docs/ADAPTERS.md` for the protocol and the contribution gate.
"""

from . import base, stub
from .base import (AdapterError, Candidates, EngineFacts, NotConnected,
                   UnknownEngine, UpsertStats, VectorEngine, engines,
                   get, managed_namespace, namespace_for, register)

# Both engine adapters are imported lazily: their clients are optional
# dependencies, and a machine with neither must still run the stub suite.
try:                                                  # pragma: no cover
    from . import qdrant                              # noqa: F401
except Exception:                                     # noqa: BLE001
    qdrant = None

try:                                                  # pragma: no cover
    from . import pgvector                            # noqa: F401
except Exception:                                     # noqa: BLE001
    pgvector = None

__all__ = ["AdapterError", "Candidates", "EngineFacts", "NotConnected",
           "UnknownEngine", "UpsertStats", "VectorEngine", "base", "engines",
           "get", "managed_namespace", "namespace_for", "pgvector", "qdrant",
           "register", "stub"]
