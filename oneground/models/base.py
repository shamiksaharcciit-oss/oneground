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
converted the same way by task 015 (`dc85609`): each wraps its whole build --
the k-means, the closure and every shard's adds -- in the same helper. All
three families are deterministic by default.

These lines said the sharded families had *not* been converted until task
028c, a week after they had, and task 029's brief then quoted the stale
sentence as a recorded gap. Two streams went looking for an HNSW defect that
015 had already fixed. A stale claim in the place people check claims costs
more than it looks.

What `deterministic=True` guarantees, per family, measured on one machine
(tasks 012, 015, 028b, 029):

    single_node_hnsw    two builds from the same (vectors, config, seed)
                        return the same ids. Task 012: 37% of ids differed at
                        efSearch=10 without it.
    semantic_sharded    the k-means, the epsilon closure and every shard's
                        graph are built under one thread, so the regions, the
                        copy counts and each shard's ids are the same. Task
                        028b: two builds of one 5,219-vector shard differed on
                        3.455% of returned ids at efSearch=96 under four
                        threads, and were identical under one. Task 029, at
                        20,000 vectors: 691 of 20,000 ids differ at four
                        threads and none at one, at 2.6x the build time.
    hash_sharded        the same wrapper over the same kind of per-shard
                        build; converted by the same commit, not separately
                        measured.

ACROSS MACHINES, WHICH ONE THREAD DOES NOT COVER
------------------------------------------------
Single threading fixes the order of work *within* a process. It says nothing
about which kernel does the arithmetic, and that is chosen per machine.

Task 027 found the consequence: a pod and this laptop produced different
k-means centroids from the same seed and the same vectors -- distances
differing by up to 0.004463, 35 of 150,000 home regions moving, eight
published values in the sixth decimal -- while every run on each machine
reproduced bitwise.

Task 029 established the cause and closed it. It is not SIMD dispatch, which
was disproved: all four `FAISS_OPT_LEVEL` settings give bitwise identical
centroids on one machine, with the BLAS path on and off. It is the BLAS path
itself. Above `distance_compute_blas_threshold` faiss hands the assignment
step to the bundled BLAS as a GEMM, and OpenBLAS -- the same library family on
both sides, confirmed by `ldd` -- selects its kernel by microarchitecture at
run time. So `deterministic=True` now enters `deterministic_faiss`, which is
both halves: one OpenMP thread, and the assignment kept off the BLAS path.

Proved, not predicted: with both halves, an Intel laptop with AVX512 and an
AMD EPYC pod without it produce bitwise identical centroids and a
byte-identical `simulate.json`. The cost is not one-signed -- ~4.9x slower at
150,000 vectors on four cores, ~5.8x faster on forty-eight -- and
`docs/MODELS.md` carries both numbers. `simulate_info.json` records which path
each configuration was built on.
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


# The threshold above which faiss hands a distance computation to the bundled
# BLAS as a GEMM. Raising it past any batch this project will ever pass keeps
# the arithmetic in faiss's own kernels.
#
# It is a C `int` on the faiss side, so it has to fit in one: 1 << 40 raises
# OverflowError. 2**30 is ~1.07e9, against the largest batch here of 150,000
# vectors x 256 centroids = 3.84e7 -- two orders of headroom, inside int32.
_NO_BLAS_THRESHOLD = 2 ** 30


@contextlib.contextmanager
def deterministic_blas(enabled=True):
    """Keep faiss's distance computations off the BLAS path, then restore.

    This is the half task 029 found, and it is the half that crosses machines.
    One thread fixes the order of work *within* a process; it says nothing
    about which kernel does the arithmetic. Above
    `distance_compute_blas_threshold` faiss hands the k-means assignment step
    to the bundled BLAS as a GEMM, and OpenBLAS picks its kernel by
    microarchitecture at run time -- an AVX512 kernel on one machine, a Zen
    kernel on another -- so the same floats are summed in a different order
    and the centroids differ.

    Measured (task 029, 12 runs on two machines, same faiss-cpu 1.15.0 and
    numpy 2.5.3): with BLAS in play, an Intel AVX512 laptop and an AMD EPYC
    pod produced centroids differing by 0.00104, each machine reproducing
    itself exactly. With BLAS off, the two produced **bitwise identical**
    centroids. The faiss dispatch level (`FAISS_OPT_LEVEL`) changed nothing on
    either machine, with BLAS on or off: faiss's own kernels agree across
    these two instruction sets and the BLAS does not.

    The cost is real and it is not one-signed -- see `docs/MODELS.md`. On a
    4-core laptop this path is ~4.9x slower at 150,000 vectors; on a 48-thread
    pod it is ~5.8x *faster*, because BLAS loses to its own threading over a
    65,536-point subsample.

    `distance_compute_blas_threshold` is a process-wide faiss global, so the
    restore is in a `finally` for the same reason the thread count's is.
    """
    if not enabled:
        yield
        return
    import faiss
    prev = faiss.cvar.distance_compute_blas_threshold
    faiss.cvar.distance_compute_blas_threshold = _NO_BLAS_THRESHOLD
    try:
        yield
    finally:
        faiss.cvar.distance_compute_blas_threshold = prev


@contextlib.contextmanager
def deterministic_faiss(enabled=True):
    """Both halves of a reproducible build: one thread, and no BLAS.

    One thread (task 012) makes a build reproduce on the machine that ran it.
    No BLAS (task 029) makes it reproduce on a different machine as well.
    A family that wants byte-identity wants both; `deterministic=False` keeps
    the fast path for a sweep that does not.
    """
    with single_threaded_faiss(enabled), deterministic_blas(enabled):
        yield


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


class _NoDefault:
    """A declared key the family has no default for: it must be named."""

    def __repr__(self):                               # pragma: no cover
        return "<no default>"


NO_DEFAULT = _NoDefault()


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
    # What the family uses when a config does not name this key. Declared
    # here so there is one of it: before task 032 the same number appeared in
    # the family's `config.get(key, X)` calls, again in the dict `configs()`
    # seeds an `include` entry from, and nowhere a reader could look it up.
    # `NO_DEFAULT` means the key must be named.
    default: Any = NO_DEFAULT
    # Whether this key appears in a label when it is at its default.
    #
    # Task 032 canonicalised a label by *filling* the defaults, so that a
    # parameter written at its default and the same parameter omitted are one
    # label and one row. Task 034 then added `index`, whose default is the
    # behaviour every published label was measured under -- and filling it
    # would append `index=hnsw` to labels that are a public interface, while
    # eliding every default would collapse those same labels to `family[]`,
    # since each is composed entirely of parameters at their defaults.
    #
    # So the table says which, per key, and the invariant holds either way:
    # `always` fills a missing default, `when_set` elides one, and both make
    # the two spellings of a default one label. The direction that does not
    # move a label already published is the one a new key takes.
    in_label_at_default: bool = True
    # Which value of another key this one belongs to: ("index", ("ivf",
    # "ivf_pq")) means the key is accepted only when `index` is one of those.
    # A knob an algorithm would ignore is refused rather than accepted (034),
    # for the reason 026 refuses a key no family reads.
    belongs_to: Optional[Any] = None
    # The closed set of values this key may take, for a key whose type does
    # not bound it. `minimum`/`maximum` bound a number; nothing bounded a
    # string until 034 declared `index`, and an unknown algorithm accepted
    # and then quietly built as HNSW is the accept-and-ignore defect 026
    # exists to stop.
    choices: Optional[Any] = None
    note: str = ""


# --------------------------------------------------------------------------
# index algorithms (task 034)
# --------------------------------------------------------------------------
# Until 034 every family built HNSW underneath and `M`, `efConstruction` and
# `efSearch` were the only index knobs a user could turn. That was right for
# the question the project started from -- hold the index constant so a
# partition's effect is isolated -- and wrong for the one asked more often,
# which is what quantisation costs in recall on *this* corpus.
#
# The algorithm is a declared parameter of every family. `hnsw` is the
# default because every published value was measured under it, and it is
# declared `in_label_at_default=False` so that adding the key rewrites no
# published label.

FLAT = "flat"
HNSW = "hnsw"
IVF = "ivf"
IVF_PQ = "ivf_pq"

INDEX_ALGORITHMS = (FLAT, HNSW, IVF, IVF_PQ)

# Which knobs each algorithm reads. A configuration naming a knob its chosen
# algorithm does not read is refused; the table below is what the refusal
# quotes back.
INDEX_KNOBS = {
    FLAT: (),
    HNSW: ("M", "efConstruction", "efSearch"),
    IVF: ("nlist", "nprobe"),
    IVF_PQ: ("nlist", "nprobe", "m", "nbits"),
}


HNSW_ONLY = ("index", (HNSW,))
IVF_ONLY = ("index", (IVF, IVF_PQ))
PQ_ONLY = ("index", (IVF_PQ,))


def index_params():
    """The `index` key and the knobs 034 adds, for a family's declared table.

    One definition, three families: an algorithm and its knobs are a property
    of faiss rather than of a partition, and three copies of this list would
    drift. A family's **own** HNSW knobs stay where they are -- their roles
    and defaults differ (`efSearch` is 128 for one index and 96 per shard;
    `efConstruction` is a parameter in one family and a constant in two) --
    and each gains `belongs_to=HNSW_ONLY` in place.
    """
    return (
        Param("index", str, default=HNSW, in_label_at_default=False,
              swept=True, choices=INDEX_ALGORITHMS,
              note="flat | hnsw | ivf | ivf_pq; hnsw is what every published "
                   "value was measured under, and naming it changes no label"),
        Param("nlist", int, minimum=1, swept=True, default=1024,
              belongs_to=IVF_ONLY,
              note="IVF cells; a k-means over the corpus"),
        Param("nprobe", int, minimum=1, swept=True, default=8,
              belongs_to=IVF_ONLY, note="IVF cells probed per query"),
        Param("m", int, minimum=1, swept=True, default=16,
              belongs_to=PQ_ONLY,
              note="PQ sub-quantisers; the dimension must divide by it"),
        Param("nbits", int, minimum=1, maximum=16, swept=True, default=8,
              belongs_to=PQ_ONLY, note="PQ bits per sub-quantiser"),
    )


# The keys `index_params` adds beside `index` itself. A family's own HNSW
# knobs are swept by its own `configs()` loops; these are crossed in by
# `index_combinations` instead, because which of them exist depends on the
# algorithm.
INDEX_KNOB_KEYS = ("nlist", "nprobe", "m", "nbits")


def index_combinations(family, grid):
    """Every index setting a grid asks for, as coherent parameter dicts.

    A grid that never names `index` yields exactly one combination at the
    declared default, so a requirements file written before 034 produces the
    configurations it produced before 034, under the labels it produced
    before: `index` elides at its default (`in_label_at_default=False`).

    A grid that does name it yields the cross product of the algorithms with
    the knobs *that algorithm reads* -- `nlist x nprobe` for `ivf`, those two
    plus `m x nbits` for `ivf_pq`, nothing for `flat`. Crossing every knob
    with every algorithm would produce configurations that are refused on
    sight, from a grid nobody wrote that way.
    """
    import itertools

    table = parameter_table(family)
    algorithms = list(grid.get("index") or (table["index"].default,))
    combos = []
    for algorithm in algorithms:
        keys = [k for k in INDEX_KNOB_KEYS
                if k in table and algorithm in tuple(table[k].belongs_to[1])]
        axes = [[(k, v) for v in (grid[k] if k in grid
                                  else (table[k].default,))] for k in keys]
        for chosen in (itertools.product(*axes) if axes else [()]):
            combos.append(dict(chosen, index=algorithm))
    return combos


def coherent(family, params):
    """`params` with the keys the chosen algorithm does not read removed.

    For a *generator*, not for a validator. `configs()` crosses a family's own
    axes with the index axis, and `M` simply is not part of an IVF
    configuration; dropping it there is not the same act as accepting it in a
    configuration a user wrote, which is refused -- see `_belonging_problem`.
    """
    table = parameter_table(family)
    return {k: v for k, v in params.items()
            if k not in table
            or _belonging_problem(family, table, table[k], params) is None}


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


def default_of(family, key):
    """A family's declared default for `key`, or `NO_DEFAULT`.

    The one place a default is written down. A family reads its own through
    this rather than repeating the literal at every `config.get` call, so the
    number in the label and the number the build uses cannot drift apart.
    """
    param = parameter_table(family).get(key)
    return NO_DEFAULT if param is None else param.default


def canonical_params(family, params):
    """`params` in the one form that names this configuration.

    What is measured does not depend on whether a parameter was written at its
    default or left out, so neither does the label. Two directions, declared
    per key (`Param.in_label_at_default`), and both reach one form:

        always    a missing default is filled in, so the two spellings
                  expand to the same label -- task 032's rule, and what
                  every published label already reads
        when_set  a value equal to the default is dropped, so the two
                  spellings elide to the same label -- what a key added
                  after those labels were published must do, or it would
                  rewrite them

    Keys of other roles, and keys of an unregistered family, are passed
    through exactly as given -- see `Config.make` for why.
    """
    table = PARAMETER_TABLES.get(family) or {}
    out = dict(params)
    for name, param in table.items():
        if param.role != PARAMETER or param.default is NO_DEFAULT:
            continue
        # A knob the chosen algorithm does not read is not filled in: task
        # 034. Filling `M` into an IVF configuration would produce a
        # configuration the validator then refuses, from a spelling the user
        # never wrote.
        if _belonging_problem(family, table, param, out) is not None:
            continue
        if param.in_label_at_default:
            out.setdefault(name, param.default)
        elif name in out and out[name] == param.default:
            del out[name]
    return out


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
    if param.choices is not None and value not in tuple(param.choices):
        return (f"{where} must be one of {', '.join(map(str, param.choices))} "
                f"(given {value!r})")
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
            continue
        problem = _belonging_problem(family, table, param, params)
        if problem:
            problems.append(problem)
    return problems


def _belonging_problem(family, table, param, params):
    """Why this key does not belong with the rest of the configuration.

    Task 034: `nprobe` is an IVF knob and `M` is an HNSW one, and a
    configuration naming a knob the chosen algorithm does not read is refused
    rather than accepted -- the same rule as 026's, for the same reason. A key
    accepted and ignored is a run that reports numbers as if it had been
    applied.
    """
    if not param.belongs_to:
        return None
    owner, wanted = param.belongs_to
    owning = table.get(owner)
    chosen = params.get(owner)
    if chosen is None and owning is not None and owning.default is not NO_DEFAULT:
        chosen = owning.default
    if chosen in tuple(wanted):
        return None
    belongs = sorted(n for n, p in table.items()
                     if p.belongs_to and p.belongs_to[0] == owner
                     and chosen in tuple(p.belongs_to[1]))
    return (f"{family}.{param.name} is a {' or '.join(tuple(wanted))} "
            f"setting and this configuration has {owner}={chosen!r}, which "
            f"does not read it. {owner}={chosen!r} reads: "
            + (", ".join(belongs) if belongs else "no knobs of its own"))


def _grid_belonging_problems(family, table, grid):
    """Swept keys in `grid` that no algorithm `grid` names would read (034).

    `nprobe: [4, 8]` in a grid whose `index` list is `[hnsw]` -- or absent,
    which means the same thing -- sweeps nothing: `configs()` crosses a knob
    in only for the algorithms that read it. That is the accept-and-ignore
    defect `for_family` exists to stop, one key further out.
    """
    owner = "index"
    if owner not in table:
        return []
    chosen = set(grid.get(owner) or (table[owner].default,))
    out = []
    for key in sorted(grid):
        param = table.get(key)
        if param is None or not param.belongs_to:
            continue
        holder, wanted = param.belongs_to
        if holder != owner or chosen & set(wanted):
            continue
        out.append(
            f"{family}.{key} is a {' or '.join(tuple(wanted))} setting and "
            f"this grid sweeps {owner}={sorted(chosen)}, so its values would "
            f"be ignored. Name an {owner} that reads it, or drop the key.")
    return out


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
        """A config, with every declared parameter present at its value.

        Task 032. A parameter left out and the same parameter written at its
        declared default are the same architecture, and used to be two labels
        and therefore two rows: a sweep could measure identical work twice and
        present it as two configurations. `canonical_params` fills what was
        left out, so the two spellings produce one label and one row.

        Only keys whose role is `parameter` are filled. A build setting is not
        filled, because `deterministic=False` is a different build and must
        stay a different label, and one written at its default is a run
        someone asked for explicitly; a run-level setting is not filled
        because the simulator adds it without changing the label.
        """
        params = canonical_params(family, params)
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

    def declared(self):
        """Every parameter this configuration carries, as a mapping.

        For recording the configuration's identity, not for reading a setting:
        a state header (task 021) has to write down the whole parameter set,
        and a family reaching into `.params` to do it would be going around
        the table that task 026 put in front of every read. `__post_init__`
        has already validated these keys against the family's table, so what
        comes back is declared by construction. Reading one key still goes
        through `get`.
        """
        return dict(self.params)

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
        problems.extend(_grid_belonging_problems(family, table, grid))
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
    # Measured, not estimated (task 034). `index_bytes` is what faiss reports
    # for the built index, summed over shards; `vector_bytes` is the vector
    # data it holds -- float32 vectors for flat, HNSW and IVF, PQ codes for
    # IVF-PQ, which are not vectors at all; `overhead_bytes` is the difference
    # -- the graph, the coarse quantiser, the list structure, the codebooks.
    #
    # `vector_bytes` is deliberately not "what these vectors would cost stored
    # raw". Measured that way the overhead of an IVF-PQ index came out at -453
    # MB, which is not a number that is wrong by a little: it is a definition
    # that did not fit the algorithm. See `indexes.stored_vector_bytes`.
    #
    # With quantisation `memory_bytes` above stopped being a description of
    # anything, so it keeps its name, keeps being labelled an estimate, and
    # sits beside these three.
    index_bytes: Optional[int] = None
    vector_bytes: Optional[int] = None

    @property
    def overhead_bytes(self):
        if self.index_bytes is None or self.vector_bytes is None:
            return None
        return int(self.index_bytes) - int(self.vector_bytes)

    def as_dict(self):
        measured = {}
        if self.index_bytes is not None:
            measured["index_bytes"] = int(self.index_bytes)
            measured["vector_bytes"] = int(self.vector_bytes or 0)
            measured["overhead_bytes"] = int(self.overhead_bytes or 0)
        return {
            "stored_vectors": int(self.stored_vectors),
            "storage_amplification": float(self.amplification),
            "est_memory_bytes": int(self.memory_bytes),
            **measured,
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

    def state(self, built: BuiltIndex, queries: np.ndarray, k: int,
              config: Config, gt_ids: np.ndarray, seed: int):
        """What this configuration did, as a `state.ModelState` (task 020).

        Where every vector went, how every query was routed, and every
        candidate each shard returned -- what the lab draws. Called by
        `simulate --emit-state` after the row is measured and before the index
        is released. It must not change anything the family measures, must
        meet `state.contract_violations` against the family's own footprint,
        and its candidates must merge back to exactly what `search` returned.
        See docs/STATE.md.
        """
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

    Equal scores keep the order the shards' results were concatenated in: the
    sort is stable (task 021c). Numpy's default argsort is not, and leaves
    tied candidates in whatever order its algorithm happens to -- which can
    differ between numpy builds and CPUs, so a receipt counted from it could
    change without any input changing. Exact ties are real: copies of one
    vector score identically, and so do duplicate vectors under different
    ids. `oneground/lab/test_lab.py` holds this merge and the query-trace
    view's recall to one written-out rule on deliberately tied scores.
    """
    if not per_shard_ids:
        return np.full(k, -1, dtype=np.int64), np.full(k, -np.inf,
                                                       dtype=np.float32)
    cid = np.concatenate(per_shard_ids)
    csc = np.concatenate(per_shard_scores)
    seen, out_ids, out_scores = set(), [], []
    for j in np.argsort(-csc, kind="stable"):
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
