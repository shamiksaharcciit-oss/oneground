"""The interface every architecture family implements.

A *model* simulates a retrieval architecture on a corpus of embeddings against
exact k-NN ground truth, so an architecture can be scored before any real
engine is stood up. One family per directory; adding a family is the
contribution unit of this project (see `docs/MODELS.md`).

The five methods, and why each is on the interface rather than optional:

    configs     what to sweep. The family decides its own grid, because only
                it knows which of its parameters interact.
    build       vectors -> a BuiltIndex. Deterministic: same vectors, config
                and seed must give the same index.
    search      what the architecture actually returns for a query.
    ceiling     what the architecture's *routing* makes reachable at all,
                searched exactly.
    footprint   what it costs: stored copies, memory, fan-out.

`ceiling` is mandatory
----------------------
A model that cannot say what its routing makes reachable cannot be in the
table. Without it, a recall of 0.932 is a single number with no decomposition:
you cannot tell whether the index missed neighbours it could have reached, or
whether the router never sent the query where they live. With it, the gap
splits in two:

    1.0 - ceiling        routing loss   -- the neighbours are in shards that
                                          were not probed. No index tuning
                                          recovers these.
    ceiling - recall     index loss     -- reachable, and the index did not
                                          return them. efSearch might.

On arxiv-150k the semantic-sharded ceiling is 0.9324 against a recall of
0.9320: 8 of 20,000 slots are index loss and the rest is routing. That single
comparison is what says "tuning HNSW will not save this architecture", and it
is why the method is required rather than nice to have.

Determinism
-----------
Every family takes a seed and must use it for every random choice, and two
builds from the same (vectors, config, seed) must produce the same
measurements; the fixture's byte-identical rebuild depends on it.

For an HNSW build the seed is not enough. faiss adds under OpenMP, and
parallel insertion lets two threads link against different partial graphs, so
the result depends on thread scheduling rather than on anything seeded. Task
012 measured the consequence: 37% of returned ids differed between two builds
at efSearch=10. `single_node_hnsw` therefore builds single-threaded by
default (`deterministic=True`, via `single_threaded_faiss`), and pays a
measured build-time penalty for it -- see `docs/MODELS.md`.

`hash_sharded` and `semantic_sharded` build `IndexHNSWFlat` per shard and have
not been converted; they take the same helper when someone does.
"""

import contextlib
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence

import numpy as np

# Whether a build must be reproducible by default. Task 012 measured that it
# was not: two `single_node_hnsw` builds from the same (vectors, config, seed)
# differed in 37% of returned ids at efSearch=10 and moved recall by up to
# 0.0047, because faiss adds to an HNSW graph under OpenMP and thread
# scheduling decides which neighbours a node sees. The Determinism section of
# this module's docstring was a promise the code did not keep.
DETERMINISTIC_DEFAULT = True


@contextlib.contextmanager
def single_threaded_faiss(enabled=True):
    """Pin faiss to one OpenMP thread for the duration, then restore.

    This is what makes an HNSW build reproducible: insertion order is already
    sequential, but parallel insertion lets two threads observe different
    partial graphs while linking, so the result depends on scheduling. One
    thread removes the race and the same inputs give the same graph.

    It is a real cost, not a free switch -- see `docs/MODELS.md` and task 012b
    for the measured build-time penalty. The restore is in a `finally` because
    leaking a one-thread setting into the rest of a process would silently
    slow every later search as well.
    """
    if not enabled:
        yield
        return
    import faiss
    prev = faiss.omp_get_max_threads()
    faiss.omp_set_num_threads(1)
    try:
        yield
    finally:
        faiss.omp_set_num_threads(prev)


def resolve_deterministic(config, override=None):
    """Explicit argument wins, then the config, then the project default."""
    if override is not None:
        return bool(override)
    if config is not None and config.get("deterministic") is not None:
        return bool(config.get("deterministic"))
    return DETERMINISTIC_DEFAULT


@dataclass(frozen=True)
class Config:
    """One point in a family's sweep.

    `label` is what appears in the table and in `simulate.json`; it must be
    stable across runs, because it is how a row is identified when a sweep is
    re-run with a different budget.
    """

    family: str
    params: Dict[str, Any]
    label: str

    @staticmethod
    def make(family, params):
        bits = ",".join(f"{k}={params[k]}" for k in sorted(params))
        return Config(family=family, params=dict(params),
                      label=f"{family}[{bits}]")

    def get(self, key, default=None):
        return self.params.get(key, default)


@dataclass
class ConfigSpace:
    """What a sweep is allowed to explore.

    `grid` lets a requirements file override a family's default sweep without
    the family knowing about requirements files. `include` pins specific
    configurations that must appear whatever the grid says -- the fixture's two
    published reference configurations arrive that way.
    """

    seed: int
    node_counts: Sequence[int] = (1, 3, 5)
    grid: Dict[str, Dict[str, Sequence[Any]]] = field(default_factory=dict)
    include: List[Dict[str, Any]] = field(default_factory=list)

    def for_family(self, family):
        return dict(self.grid.get(family) or {})

    def included_for(self, family):
        out = []
        for spec in self.include:
            if spec.get("family") == family:
                p = {k: v for k, v in spec.items() if k != "family"}
                out.append(p)
        return out


@dataclass
class Candidates:
    """What a search returned, per query.

    ids      (n_queries, k) int64, -1 padded where fewer than k were found
    scores   (n_queries, k) float32 inner-product similarity, -inf where padded
    """

    ids: np.ndarray
    scores: np.ndarray


@dataclass
class Footprint:
    """What an architecture costs to run, independent of how well it recalls.

    stored_vectors   total vectors held across all shards, counting copies
    amplification    stored_vectors / base vectors. 1.0 means no replication.
    memory_bytes     estimated resident bytes. An estimate, and labelled as
                     one everywhere it is printed: it counts the vector
                     payload and an HNSW graph term, not the allocator's
                     real behaviour.
    fanout           shards touched per query. The cost the recall number
                     never shows: a fan-out of 3 at equal recall is three
                     times the query work.
    shards           how many shards exist.
    copies_p50/p95/p99   distribution of copies per vector, where a family
                     replicates. All 1 where it does not.
    """

    stored_vectors: int
    amplification: float
    memory_bytes: int
    fanout: float
    shards: int
    copies_p50: int = 1
    copies_p95: int = 1
    copies_p99: int = 1

    def as_dict(self):
        return {
            "stored_vectors": int(self.stored_vectors),
            "storage_amplification": float(self.amplification),
            "est_memory_bytes": int(self.memory_bytes),
            "fanout": float(self.fanout),
            "shards": int(self.shards),
            "p50_copies": int(self.copies_p50),
            "p95_copies": int(self.copies_p95),
            "p99_copies_per_vector": int(self.copies_p99),
        }


@dataclass
class BuiltIndex:
    """The result of `build`. Families put whatever they need in `state`.

    `n_base` and `dim` are on the outside because the framework needs them for
    footprint arithmetic without knowing the family's internals.
    """

    family: str
    config: Config
    n_base: int
    dim: int
    state: Dict[str, Any] = field(default_factory=dict)
    build_seconds: float = 0.0


class Model(Protocol):
    """The protocol. See the module docstring for why `ceiling` is required."""

    name: str

    def configs(self, space: ConfigSpace) -> Iterable[Config]:
        ...

    def build(self, vectors: np.ndarray, config: Config, seed: int,
              context: Optional[Dict[str, Any]] = None) -> BuiltIndex:
        """Deterministic given (vectors, config, seed).

        `context` is an optional escape hatch for work the caller has already
        done -- the fixture builder passes the k-means centroids it computed
        during characterization rather than making the model recompute a
        256-way clustering over 150,000 vectors. A model must produce the same
        result with or without it; it is a speed and identity concession, not
        a behaviour switch.
        """
        ...

    def search(self, built: BuiltIndex, queries: np.ndarray, k: int,
               config: Config) -> Candidates:
        ...

    def ceiling(self, built: BuiltIndex, queries: np.ndarray,
                k: int) -> np.ndarray:
        """Exact search over everything this architecture's routing can reach.

        Returns (n_queries, k) ids, -1 padded. For a family that reaches
        everything, this is exact k-NN over the whole corpus and routing loss
        is zero by definition.
        """
        ...

    def footprint(self, built: BuiltIndex) -> Footprint:
        ...


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

# Bytes per float32, and the HNSW graph's per-vector link cost. M links per
# node at 4 bytes each on the base layer, doubled for level 0, which is how
# faiss lays out IndexHNSWFlat. An estimate; see Footprint.memory_bytes.
BYTES_PER_FLOAT32 = 4
HNSW_LINK_BYTES = 4


def estimate_memory_bytes(stored_vectors, dim, M):
    """Vector payload plus an HNSW graph term. Explicitly an estimate."""
    payload = stored_vectors * dim * BYTES_PER_FLOAT32
    graph = stored_vectors * 2 * int(M) * HNSW_LINK_BYTES
    return int(payload + graph)


def merge_candidates(per_shard_ids, per_shard_scores, k):
    """Score-merge with id dedupe -- the shard-merge every family shares.

    Sorted by descending inner product, first occurrence of an id wins. This
    is the same merge the fixture builder has always used; it is here so all
    three families do it identically rather than three times slightly
    differently.
    """
    if not per_shard_ids:
        return np.full(k, -1, dtype=np.int64), np.full(k, -np.inf,
                                                       dtype=np.float32)
    cid = np.concatenate(per_shard_ids)
    csc = np.concatenate(per_shard_scores)
    seen, out_ids, out_scores = set(), [], []
    for j in np.argsort(-csc):
        vid = int(cid[j])
        if vid < 0 or vid in seen:
            continue
        seen.add(vid)
        out_ids.append(vid)
        out_scores.append(float(csc[j]))
        if len(out_ids) == k:
            break
    ids = np.full(k, -1, dtype=np.int64)
    scores = np.full(k, -np.inf, dtype=np.float32)
    ids[:len(out_ids)] = out_ids
    scores[:len(out_scores)] = out_scores
    return ids, scores


def exact_over(vectors, subset_ids, queries, k):
    """Exact inner-product search restricted to `subset_ids`.

    The primitive every `ceiling` is built from.
    """
    import faiss
    if len(subset_ids) == 0:
        return (np.full((len(queries), k), -1, dtype=np.int64),
                np.full((len(queries), k), -np.inf, dtype=np.float32))
    idx = faiss.IndexFlatIP(vectors.shape[1])
    idx.add(vectors[subset_ids])
    n = min(k, len(subset_ids))
    sc, loc = idx.search(queries, n)
    ids = np.full((len(queries), k), -1, dtype=np.int64)
    scores = np.full((len(queries), k), -np.inf, dtype=np.float32)
    ids[:, :n] = np.asarray(subset_ids)[loc]
    scores[:, :n] = sc
    return ids, scores
