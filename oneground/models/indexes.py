"""The index algorithm, as a declared choice (task 034).

Until 034 every family built HNSW underneath, and `M`, `efConstruction` and
`efSearch` were the only index knobs a user could turn. That was right for
the question the project started from — hold the index constant so a
partition's effect is isolated — and it left out the trade a team actually
argues about, which is memory against recall.

Four algorithms, one builder, used by all three families:

    flat     exact. Recall 1.0 by construction, and the memory and query cost
             of not approximating. The reference point the other three are
             read against.
    hnsw     the current behaviour, unchanged. Every published fixture value
             was measured under it, so this path must stay bit-for-bit what
             it was: same construction, same order, same parameters.
    ivf      `nlist` cells by k-means, `nprobe` of them searched.
    ivf_pq   the same, with the residuals product-quantised into `m`
             sub-vectors of `nbits` bits — an order of magnitude smaller, and
             lossy in a way that depends on the distribution it trained on.

WHAT IS MEASURED RATHER THAN ESTIMATED
--------------------------------------
`measured_bytes` serialises the built index and reports its length. With
quantisation, memory stopped being `vectors x dim x 4` and a formula would be
a guess about faiss's internals; this is faiss's own answer. The estimate the
report has always carried stays beside it, marked `estimated`, because the
two answer different questions and one of them is now checkable.

DETERMINISM
-----------
IVF trains a k-means and IVF-PQ trains a second one, so both inherit exactly
what task 029 found: faiss's BLAS path is where two environments diverge, and
`deterministic=True` has to keep the arithmetic out of it. Both trainings run
under `deterministic_faiss`, and both are seeded from the run's seed rather
than from faiss's global default, so a rebuild is a rebuild.
"""

import numpy as np

from .base import (FLAT, HNSW, INDEX_ALGORITHMS, INDEX_KNOBS, IVF, IVF_PQ,
                   ParameterError, deterministic_faiss, index_params)

# The declared defaults for the keys 034 adds, read from the one table that
# defines them rather than repeated here. A `Config` already carries them --
# `canonical_params` fills them in -- but `build` is also called with plain
# dicts in tests and scratch scripts, and two copies of a default is how the
# value a run uses stops being the value its label names.
_INDEX_DEFAULTS = {p.name: p.default for p in index_params()}
# The HNSW knobs belong to each family (their defaults differ per family), so
# only their validity floor lives here; a family that reads one passes its own
# via `knobs=` or carries it in the config.
_HNSW_FALLBACK = {"M": 32, "efConstruction": 200, "efSearch": 128}


def algorithm_of(config, default=HNSW):
    """The configuration's declared algorithm."""
    return str(config.get("index", default) or default)


def _knob(config, name, knobs=None):
    """This index's value for `name`.

    `knobs` wins over the config: a family that *fixes* a knob for every index
    it builds (semantic_sharded's and hash_sharded's `efConstruction`, which
    026 declares CONSTANT and refuses in a config) passes it that way, so the
    constant stays in the family module that owns it.
    """
    if knobs and name in knobs:
        return int(knobs[name])
    default = _INDEX_DEFAULTS.get(name, _HNSW_FALLBACK.get(name))
    return int(config.get(name, default))


def _in(where):
    """The `in region 3` clause of a refusal, or nothing.

    A sharded family builds one index per region, and "nlist 1024 over 812
    vectors" is only actionable when a reader knows which region it was.
    """
    return (" in " + where) if where else ""


class IndexTooSmall(ParameterError):
    """A training set smaller than the cells it was asked to learn.

    Its own error rather than faiss's, because faiss's says nothing about the
    configuration a user wrote or the shard it landed in.
    """


def build(vectors, config, *, seed, deterministic, dim=None, add_chunk=None,
          progress=None, where="", knobs=None):
    """The configuration's index, built over `vectors`.

    `where` names the shard a refusal is about; see `_in`.
    `knobs` are values the family fixes for every index it builds; see `_knob`.
    """
    import faiss

    algorithm = algorithm_of(config)
    if algorithm not in INDEX_ALGORITHMS:
        raise ParameterError(
            "unknown index %r; the declared algorithms are %s"
            % (algorithm, ", ".join(INDEX_ALGORITHMS)))
    dim = int(dim if dim is not None else vectors.shape[1])
    n = int(len(vectors))

    with deterministic_faiss(deterministic):
        if algorithm == FLAT:
            index = faiss.IndexFlatIP(dim)
        elif algorithm == HNSW:
            index = faiss.IndexHNSWFlat(dim, _knob(config, "M", knobs),
                                        faiss.METRIC_INNER_PRODUCT)
            index.hnsw.efConstruction = _knob(config, "efConstruction", knobs)
        else:
            nlist = _knob(config, "nlist", knobs)
            if nlist > n:
                raise IndexTooSmall(
                    "index=%s asks for nlist=%d cells over %d vector(s)%s; "
                    "faiss cannot train more cells than it has points. Lower "
                    "nlist, or choose a partition with larger shards."
                    % (algorithm, nlist, n, _in(where)))
            quantizer = faiss.IndexFlatIP(dim)
            if algorithm == IVF:
                index = faiss.IndexIVFFlat(quantizer, dim, nlist,
                                           faiss.METRIC_INNER_PRODUCT)
            else:
                m = _knob(config, "m", knobs)
                if dim % m:
                    raise ParameterError(
                        "index=ivf_pq asks for m=%d sub-quantisers over "
                        "dimension %d; the dimension must divide by m" % (m, dim))
                nbits = _knob(config, "nbits", knobs)
                # The PQ trains its own k-means, of 2**nbits centroids, over
                # the same points. It is a second size floor and a much
                # higher one than nlist's: nbits=8 wants 256 points where
                # nlist=8 wants 8, and faiss's own message for it names
                # neither the configuration nor the shard.
                if 2 ** nbits > n:
                    raise IndexTooSmall(
                        "index=ivf_pq asks for nbits=%d, which is %d PQ "
                        "centroids per sub-quantiser, over %d vector(s)%s; "
                        "faiss cannot train more centroids than it has "
                        "points. Lower nbits, or choose a partition with "
                        "larger shards." % (nbits, 2 ** nbits, n, _in(where)))
                index = faiss.IndexIVFPQ(quantizer, dim, nlist, m, nbits,
                                         faiss.METRIC_INNER_PRODUCT)
                # The PQ's own clustering, seeded for the same reason the
                # coarse one is.
                index.pq.cp.seed = int(seed)
                index.pq.cp.verbose = False
            index.cp.seed = int(seed)
            index.cp.verbose = False
            index.train(vectors)

        _add(index, vectors, add_chunk, progress)

    set_search(index, config, knobs)
    return index


def _add(index, vectors, add_chunk, progress):
    """Add the corpus, in slices when asked, so a memmap is never
    materialised whole. Adds stay sequential either way."""
    import time
    t0 = time.time()
    n = len(vectors)
    if not add_chunk:
        index.add(vectors)
        if progress:
            progress(n, n, time.time() - t0)
        return
    step = int(add_chunk)
    for i in range(0, n, step):
        index.add(np.ascontiguousarray(vectors[i:i + step]))
        if progress:
            progress(min(i + step, n), n, time.time() - t0)


def set_search(index, config, knobs=None):
    """Put the configuration's search-time knob on a built index.

    Called before every search rather than once at build, which is what the
    families did with `efSearch` before 034: `search`, `state` and a caller
    holding a `BuiltIndex` can each pass a different config, and a knob left
    over from the previous call would be measured as this one's.
    """
    algorithm = algorithm_of(config)
    if algorithm == HNSW:
        index.hnsw.efSearch = _knob(config, "efSearch", knobs)
    elif algorithm in (IVF, IVF_PQ):
        index.nprobe = _knob(config, "nprobe", knobs)


def code_size(config):
    """Bytes per vector this algorithm stores.

    `dim * 4` for anything that keeps the vectors -- flat, HNSW, and IVF,
    whose lists hold full float32 vectors. For IVF-PQ it is the PQ code, which
    faiss packs as `ceil(m * nbits / 8)` bytes and which is not a vector at
    all. `dim` is needed only for the first case.
    """
    algorithm = algorithm_of(config)
    if algorithm != IVF_PQ:
        return None
    return -(-_knob(config, "m") * _knob(config, "nbits") // 8)


def stored_vector_bytes(config, n, dim):
    """What the built index holds as vector data, in bytes.

    Not "what these vectors would cost stored raw": that is the estimate, and
    for a quantised index it is wrong by an order of magnitude. Measured
    against it, `overhead_bytes` came out at -453 MB for an IVF-PQ index over
    150,000 arXiv vectors -- a number that is not wrong by a little, it is a
    sign the definition did not fit the algorithm.

    With this, the overhead is the thing a reader wants: the graph for HNSW,
    the coarse quantiser and the list structure for IVF, and for IVF-PQ the
    codebooks -- which on a 256-shard partition cost more than the codes.
    """
    bytes_each = code_size(config)
    if bytes_each is None:
        bytes_each = int(dim) * 4
    return int(n) * int(bytes_each)


def measured_bytes(index):
    """The built index's size, as faiss reports it.

    Serialised rather than computed: with quantisation the arithmetic that
    used to give the answer -- vectors x dimension x 4 -- is wrong by an order
    of magnitude, and a formula over faiss's internals would be a guess.
    """
    import faiss
    return int(faiss.serialize_index(index).nbytes)


def knobs_in_use(config):
    """The knobs the configuration's algorithm actually reads, with values."""
    algorithm = algorithm_of(config)
    out = {"index": algorithm}
    for name in INDEX_KNOBS.get(algorithm, ()):
        value = config.get(name)
        if value is not None:
            out[name] = value
    return out
