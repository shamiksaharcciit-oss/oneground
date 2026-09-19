"""single_node_hnsw — one HNSW index over everything.

The baseline every other family has to beat. There is no routing, so the
routing ceiling is exact k-NN over the whole corpus and routing loss is zero by
definition: every miss is index loss, recoverable by raising efSearch.

Extracted from `oneground/fixture/reference.py` in task 008 with the search
path unchanged -- `IndexHNSWFlat` with METRIC_INNER_PRODUCT, efConstruction
from the config, efSearch set after `add`.

Task 012b changed one thing about the *build*: it adds single-threaded by
default, because a parallel faiss add is not reproducible (measured: 37% of
returned ids differed between two builds from identical inputs). The search
path is still untouched.
"""

import time
from dataclasses import dataclass

import numpy as np

from .. import indexes
from ..base import (BUILD, HNSW, HNSW_ONLY, BuiltIndex, Candidates, Config,
                    Footprint, Param, coherent, declare_parameters,
                    estimate_memory_bytes, exact_over, index_combinations,
                    index_params, resolve_deterministic)

NAME = "single_node_hnsw"

DEFAULT_GRID = {"M": (16, 32), "efSearch": (64, 128, 256)}
EF_CONSTRUCTION = 200

# Every key this family reads (task 026). Ranges are validity bounds, not
# recommendations. `efConstruction` is a real setting here -- `build` reads it
# -- but the generated grid always builds at EF_CONSTRUCTION, so it is pinned
# by an `include` entry, never swept.
PARAMETERS = declare_parameters(NAME, (
    Param("M", int, minimum=1, swept=True, default=32,
          belongs_to=HNSW_ONLY, note="HNSW links per node"),
    Param("efSearch", int, minimum=1, swept=True, default=128,
          belongs_to=HNSW_ONLY, note="search beam width"),
    Param("efConstruction", int, minimum=1, default=EF_CONSTRUCTION,
          belongs_to=HNSW_ONLY,
          note="build beam width; pinned by include, not swept"),
    Param("deterministic", bool, role=BUILD,
          note="single-threaded build; see base.DETERMINISTIC_DEFAULT"),
) + index_params())


def _d(key):
    """This family's declared default for `key` (task 032).

    Read from the parameter table rather than repeated at each call site, so
    the value a config is labelled with and the value the build uses are the
    same one by construction.
    """
    return PARAMETERS[key].default


@dataclass
class SingleNodeHNSW:
    name: str = NAME

    # -- sweep -------------------------------------------------------------
    def configs(self, space):
        grid = {**DEFAULT_GRID, **space.for_family(NAME)}
        seen, out = set(), []
        for params in space.included_for(NAME):
            # No seed dict of defaults since task 032: `Config.make` fills
            # what an include entry leaves out, from the declared table.
            c = Config.make(NAME, dict(params))
            if c.label not in seen:
                seen.add(c.label)
                out.append(c)
        # The index axis is the outer one (task 034). `coherent` drops this
        # family's HNSW knobs from a configuration whose algorithm does not
        # read them, so an IVF row is one configuration per (nlist, nprobe)
        # rather than one per M -- the dedupe by label is what collapses the
        # repetition, and it is also what keeps a grid that never names
        # `index` producing exactly the configurations it produced before.
        for idx in index_combinations(NAME, grid):
            for M in grid["M"]:
                for ef in grid["efSearch"]:
                    c = Config.make(NAME, coherent(NAME, dict(
                        idx, M=int(M), efConstruction=EF_CONSTRUCTION,
                        efSearch=int(ef))))
                    if c.label not in seen:
                        seen.add(c.label)
                        out.append(c)
        return out

    # -- build -------------------------------------------------------------
    def build(self, vectors, config, seed, context=None, deterministic=None,
              add_chunk=None, progress=None):
        """Build the index.

        `deterministic` (default True, from `DETERMINISTIC_DEFAULT`) adds
        single-threaded. Task 012 measured that a parallel add is not
        reproducible -- 37% of returned ids differed between two builds from
        identical inputs at efSearch=10 -- because faiss links under OpenMP and
        two threads see different partial graphs. The seed cannot fix that; only
        one thread can. Pass `deterministic=False` for a sweep where speed
        matters more than a byte-identical rebuild, and say so in the receipt.

        `add_chunk` feeds the corpus in slices so a memmapped array is never
        materialised whole. Adds stay sequential either way, so the graph is
        unchanged by chunking. `progress(added, total, seconds)` is called after
        each slice: a single-threaded build over a million vectors takes tens
        of minutes, and a run that prints nothing for that long is
        indistinguishable from a hung one.
        """
        t0 = time.time()
        det = resolve_deterministic(config, deterministic)
        # Task 034: the algorithm is the configuration's. `hnsw` is the
        # default and takes exactly the path it took before -- same
        # construction, same sequential adds, same knobs -- because every
        # published value was measured under it.
        idx = indexes.build(vectors, config, seed=seed, deterministic=det,
                            add_chunk=add_chunk, progress=progress)
        return BuiltIndex(family=NAME, config=config, n_base=len(vectors),
                          dim=vectors.shape[1],
                          state={"index": idx, "vectors": vectors,
                                 "deterministic": det},
                          build_seconds=time.time() - t0)

    # -- search ------------------------------------------------------------
    def search(self, built, queries, k, config):
        idx = built.state["index"]
        indexes.set_search(idx, config)
        scores, ids = idx.search(queries, k)
        return Candidates(ids=ids.astype(np.int64),
                          scores=scores.astype(np.float32))

    # -- ceiling -----------------------------------------------------------
    def ceiling(self, built, queries, k):
        """Everything is reachable, so the ceiling is exact k-NN over all of
        it. Routing loss is zero by construction, not by measurement."""
        vectors = built.state["vectors"]
        ids, _ = exact_over(vectors, np.arange(built.n_base), queries, k)
        return ids

    # -- footprint ---------------------------------------------------------
    def footprint(self, built):
        # The estimate stays and stays labelled one; beside it, what faiss
        # reports for the index it actually built (task 034).
        M = int(built.config.get("M", _d("M"))) \
            if indexes.algorithm_of(built.config) == HNSW else 0
        return Footprint(
            stored_vectors=built.n_base,
            amplification=1.0,
            memory_bytes=estimate_memory_bytes(built.n_base, built.dim, M),
            fanout=1.0,
            shards=1,
            index_bytes=indexes.measured_bytes(built.state["index"]),
            vector_bytes=int(built.n_base) * int(built.dim) * 4,
        )

    # -- state -------------------------------------------------------------
    def state(self, built, queries, k, config, gt_ids, seed):
        """What this configuration did, as a `state.ModelState` (task 020).

        One region holding everything, one copy of every vector, one probe per
        query for reason fan-out, and the index's own top-k as the candidates:
        search's call, repeated. faiss padding (-1) is not a candidate and is
        dropped, as it is from a recall count.
        """
        from .. import state as S
        idx, vectors = built.state["index"], built.state["vectors"]
        n, dim = vectors.shape
        nq = len(queries)

        partition = S.PartitionState(
            family=NAME, kind="single", seed=int(seed), params={},
            region_ids=np.array([0], dtype=np.int32),
            region_sizes=np.array([n], dtype=np.int64))
        assignment = S.AssignmentState(
            home_region=np.zeros(n, dtype=np.int32),
            copy_count=np.ones(n, dtype=np.uint8),
            copy_set=np.zeros((n, 1), dtype=np.int32),
            centroid_dist=np.full((n, 1), np.nan, dtype=np.float32),
            max_assign=1, nearest_region=np.zeros((n, 1), dtype=np.int32))
        route = S.RouteState(
            scored_region=np.zeros((nq, 0), dtype=np.int32),
            scored_dist=np.zeros((nq, 0), dtype=np.float32),
            probed_region=np.zeros((nq, 1), dtype=np.int32),
            probe_reason=np.full((nq, 1), S.ROUTE_FANOUT, dtype=np.uint8))

        indexes.set_search(idx, config)
        scores, ids = idx.search(queries, k)
        per_query = [(ids[q], np.zeros(len(ids[q]), dtype=np.int32),
                      scores[q]) for q in range(nq)]
        candidates = S.build_candidates(per_query, gt_ids,
                                        int(np.shape(gt_ids)[1]))
        return S.ModelState(
            family=NAME, config_label=config.label,
            params=config.declared(), seed=int(seed), n_base=int(n),
            n_queries=int(nq), dim=int(dim), partition=partition,
            assignment=assignment, route=route, candidates=candidates,
            load=S.build_load(partition.region_ids, assignment, route,
                              candidates))


MODEL = SingleNodeHNSW()
