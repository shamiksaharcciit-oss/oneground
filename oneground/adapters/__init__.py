"""Engines, each behind the one `VectorEngine` protocol.

    stub     in-process exact search; what CI runs against
    qdrant   the official qdrant-client

No engine of our own, no favourite, no sponsored defaults. An adapter earns
its place by passing `conformance.py`, and nothing here picks an engine for
the user.

See `docs/ADAPTERS.md` for the protocol and the contribution gate.
"""

from . import base, stub
from .base import (AdapterError, Candidates, EngineFacts, NotConnected,
                   UnknownEngine, UpsertStats, VectorEngine, engines,
                   get, managed_namespace, namespace_for, register)

# Qdrant is imported lazily: the client is an optional dependency, and a
# machine with no qdrant-client must still be able to run the stub suite.
try:                                                  # pragma: no cover
    from . import qdrant                              # noqa: F401
except Exception:                                     # noqa: BLE001
    qdrant = None

__all__ = ["AdapterError", "Candidates", "EngineFacts", "NotConnected",
           "UnknownEngine", "UpsertStats", "VectorEngine", "base", "engines",
           "get", "managed_namespace", "namespace_for", "qdrant", "register",
           "stub"]
