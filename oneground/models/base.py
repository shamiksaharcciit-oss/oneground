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

`hash_sharded` and `semantic_sharded` build `IndexHNSWFlat` per shard and were
converted in task 015 (`dc85609`): each wraps its whole build --- the k-means,
the closure and every shard's adds --- in the same `single_threaded_faiss`
helper. These two lines said they had *not* been converted until task 028c,
a week after they had; task 029's brief then quoted the stale sentence as a
recorded gap, which is the cost of a comment that outlives what it describes.

What `deterministic=True` guarantees, per family, all of it measured on one
machine (tasks 012, 015, 028b):

    single_node_hnsw    two builds from the same (vectors, config, seed)
                        return the same ids. Task 012: 37% of ids differed at
                        efSearch=10 without it.
    semantic_sharded    the k-means, the epsilon closure and every shard's
                        graph are built under one thread, so the regions, the
                        copy counts and each shard's ids are the same. Task
                        028b: two builds of one 5,219-vector shard differed on
                        3.455% of returned ids at efSearch=96 under four
                        threads, and were identical under one.
    hash_sharded        the same wrapper over the same kind of per-shard
                        build; converted by the same commit, not separately
                        measured.

What it does not guarantee: the same numbers on a *different* machine. A pod
run and a laptop run produced different k-means centroids from the same seed
and the same vectors -- task 027's report, on the `task-020` branch until it
merges, gives distances differing by up to 0.004463 and 35 of 150,000 home
regions moving --
and single threading does not address that. Within one machine the k-means is
stable: two runs of it are bit-identical, threaded or not (028b). Searching an
already-built index is deterministic either way (028b). The cross-environment
question is open.
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


# --------------------------------------------------------------------------
# parameter tables (task 026)
# --------------------------------------------------------------------------
# Until 026 a configuration key no family read was accepted, folded into the
# label, and silently ignored: `probez: 3` in a requirements file produced a
# config called `semantic_sharded[...,probez=3]` measured exactly like one
# without it. A proposal loop built on that would publish a result for a
# change that was never applied. So every family declares the keys it reads,
# and a configuration naming anything else is refused, with the declared set.

# What a key is to a family.
PARAMETER = "parameter"    # the architecture; the only role a policy changes
RUN = "run"                # set per run by the simulator, uniform across it
BUILD = "build"            # how the index is built, not what it is
CONSTANT = "constant"      # fixed inside the family; refused in any config

ROLES = (PARAMETER, RUN, BUILD, CONSTANT)


class ParameterError(ValueError):
    """A configuration names or sets a key its family does not accept."""


@dataclass(frozen=True)
class Param:
    """One declared key.

    `minimum`/`maximum` are validity bounds -- what the family can build at
    all -- not recommendations. `swept` says whether the family's `configs()`
    reads a requirements grid for it; a declared key that is not swept can
    still be pinned by an `include` entry. `fixed` is a constant's value, for
    the message that refuses it.
    """

    name: str
    type: type
    role: str = PARAMETER
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    swept: bool = False
    fixed: Any = None
    note: str = ""


# family name -> {key: Param}. Filled by each family at import.
PARAMETER_TABLES: Dict[str, Dict[str, Param]] = {}


def declare_parameters(family, params):
    """Register a family's parameter table. Returns it, keyed by name."""
    table = {}
    for p in params:
        if p.role not in ROLES:
            raise ValueError(f"{family}.{p.name}: unknown role {p.role!r}")
        if p.name in table:
            raise ValueError(f"{family}.{p.name} declared twice")
        table[p.name] = p
    PARAMETER_TABLES[family] = table
    return table


def parameter_table(family):
    try:
        return PARAMETER_TABLES[family]
    except KeyError:
        raise ParameterError(
            f"no parameter table for family {family!r}; declared: "
            f"{', '.join(sorted(PARAMETER_TABLES)) or 'none'}") from None


def _describe_table(family, table, roles=None):
    names = sorted(n for n, p in table.items()
                   if roles is None or p.role in roles)
    return f"{family} declares: {', '.join(names) or 'nothing'}"


def check_value(family, param, value):
    """A problem with one value for one declared key, or None."""
    import numbers
    where = f"{family}.{param.name}"
    if param.role == CONSTANT:
        return (f"{where} is a constant fixed at {param.fixed} inside the "
                f"family; it is not configurable (given {value!r})")
    if param.type is bool:
        ok = isinstance(value, bool)
    elif param.type is int:
        ok = (isinstance(value, numbers.Integral)
              and not isinstance(value, bool))
    elif param.type is float:
        ok = isinstance(value, numbers.Real) and not isinstance(value, bool)
    else:                                             # pragma: no cover
        ok = isinstance(value, param.type)
    if not ok:
        return (f"{where} must be {param.type.__name__}, not "
                f"{type(value).__name__} {value!r}")
    if param.minimum is not None and value < param.minimum:
        return f"{where} must be at least {param.minimum} (given {value!r})"
    if param.maximum is not None and value > param.maximum:
        return f"{where} must be at most {param.maximum} (given {value!r})"
    return None


def parameter_problems(family, params):
    """Every problem with a configuration's keys and values, as sentences."""
    table = parameter_table(family)
    problems = []
    for key in sorted(params):
        param = table.get(key)
        if param is None:
            problems.append(f"{family} has no parameter {key!r}. "
                            + _describe_table(family, table))
            continue
        problem = check_value(family, param, params[key])
        if problem:
            problems.append(problem)
    return problems


def validate_params(family, params):
    problems = parameter_problems(family, params)
    if problems:
        raise ParameterError("; ".join(problems))


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

    def __post_init__(self):
        # Task 026: however a Config is made -- `make`, or directly, as the
        # simulator does to add `shard_depth` -- its keys are the family's.
        validate_params(self.family, self.params)

    @staticmethod
    def make(family, params):
        bits = ",".join(f"{k}={params[k]}" for k in sorted(params))
        return Config(family=family, params=dict(params),
                      label=f"{family}[{bits}]")

    def declares(self, key):
        """Whether this config's family declares `key` at all -- including a
        constant it fixes and refuses."""
        return key in parameter_table(self.family)

    def accepts(self, key):
        """Whether a value for `key` may be set: declared, and not a
        constant. The question a caller adding a key has to ask."""
        param = parameter_table(self.family).get(key)
        return param is not None and param.role != CONSTANT

    def get(self, key, default=None):
        """A declared key's value. An undeclared key is refused, naming the
        declared ones: reading a key the table does not list is how a family
        comes to depend on a setting nobody can validate."""
        table = parameter_table(self.family)
        if key not in table:
            raise ParameterError(
                f"{self.family} does not declare {key!r}. "
                + _describe_table(self.family, table))
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
        """This family's grid, refused where a key would be ignored.

        A grid key the family does not declare, or declares but does not
        sweep, used to vanish: `configs()` loops over the keys it knows, so
        `efConstruction: [400]` in a single_node_hnsw grid built every config
        at 200 and said nothing (task 026).
        """
        grid = dict(self.grid.get(family) or {})
        table = parameter_table(family)
        problems = []
        for key in sorted(grid):
            param = table.get(key)
            if param is None:
                problems.append(f"{family} has no parameter {key!r}. "
                                + _describe_table(family, table))
            elif param.role == CONSTANT:
                problems.append(check_value(family, param, grid[key]))
            elif not param.swept:
                problems.append(
                    f"{family}.{key} is declared but not swept: its "
                    f"configs() reads no grid for it, so the values would be "
                    f"ignored. Pin it with an `include` entry instead. "
                    + _describe_table(family, {n: p for n, p in table.items()
                                               if p.swept}))
            else:
                values = grid[key]
                if not isinstance(values, (list, tuple)):
                    values = [values]
                for v in values:
                    problem = check_value(family, param, v)
                    if problem:
                        problems.append(problem)
        if problems:
            raise ParameterError("; ".join(problems))
        return grid

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
