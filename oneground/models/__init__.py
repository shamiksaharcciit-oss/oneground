"""Architecture families, and the registry that finds them.

One directory per family, each implementing `base.Model`. A family is the
contribution unit of this project: adding one is a self-contained change —
a `model.py`, a `MODEL.md`, and tests — that needs no edit to the simulator.

    single_node_hnsw   one index over everything; the baseline
    semantic_sharded   k-means regions with epsilon closure, probe P
    hash_sharded       N shards by seeded hash; fans out to all of them

`ceiling` is required of every family. See `base.py` and `docs/MODELS.md` for
why a model that cannot state what its routing makes reachable cannot appear
in the trade-off table.
"""

from . import base
from .base import (BuiltIndex, Candidates, Config, ConfigSpace, Footprint,
                   Model)
from .hash_sharded import MODEL as HASH_SHARDED
from .semantic_sharded import MODEL as SEMANTIC_SHARDED
from .single_node_hnsw import MODEL as SINGLE_NODE_HNSW

REGISTRY = {
    SINGLE_NODE_HNSW.name: SINGLE_NODE_HNSW,
    SEMANTIC_SHARDED.name: SEMANTIC_SHARDED,
    HASH_SHARDED.name: HASH_SHARDED,
}


class UnknownFamily(KeyError):
    """A requirements file named a family that is not registered."""


def get(name):
    try:
        return REGISTRY[name]
    except KeyError:
        raise UnknownFamily(
            f"no model family named {name!r}. Registered: "
            f"{', '.join(sorted(REGISTRY))}") from None


def families():
    return sorted(REGISTRY)


__all__ = ["BuiltIndex", "Candidates", "Config", "ConfigSpace", "Footprint",
           "Model", "REGISTRY", "UnknownFamily", "base", "families", "get",
           "HASH_SHARDED", "SEMANTIC_SHARDED", "SINGLE_NODE_HNSW"]
