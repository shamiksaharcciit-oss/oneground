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

from ..base import (BUILD, BuiltIndex, Candidates, Config, Footprint,
                    Param, declare_parameters, estimate_memory_bytes,
                    exact_over, resolve_deterministic, single_threaded_faiss)

NAME = "single_node_hnsw"

DEFAULT_GRID = {"M": (16, 32), "efSearch": (64, 128, 256)}
EF_CONSTRUCTION = 200

# Every key this family reads (task 026). Ranges are validity bounds, not
# recommendations. `efConstruction` is a real setting here -- `build` reads it
# -- but the generated grid always builds at EF_CONSTRUCTION, so it is pinned
# by an `include` entry, never swept.
PARAMETERS = declare_parameters(NAME, (
    Param("M", int, minimum=1, swept=True,
          note="HNSW links per node"),
    Param("efSearch", int, minimum=1, swept=True,
          note="search beam width"),
    Param("efConstruction", int, minimum=1,
          note="build beam width; pinned by include, not swept"),
    Param("deterministic", bool, role=BUILD,
          note="single-threaded build; see base.DETERMINISTIC_DEFAULT"),
))


@dataclass
class SingleNodeHNSW:
    name: str = NAME

    # -- sweep -------------------------------------------------------------
    def configs(self, space):
        grid = {**DEFAULT_GRID, **space.for_family(NAME)}
        seen, out = set(), []
        for params in space.included_for(NAME):
            p = {"M": 32, "efConstruction": EF_CONSTRUCTION, "efSearch": 128}
            p.update(params)
            c = Config.make(NAME, p)
            if c.label not in seen:
                seen.add(c.label)
                out.append(c)
        for M in grid["M"]:
            for ef in grid["efSearch"]:
                c = Config.make(NAME, {"M": int(M),
                                       "efConstruction": EF_CONSTRUCTION,
                                       "efSearch": int(ef)})
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
        import faiss
        t0 = time.time()
        det = resolve_deterministic(config, deterministic)
        idx = faiss.IndexHNSWFlat(vectors.shape[1], int(config.get("M", 32)),
                                  faiss.METRIC_INNER_PRODUCT)
        idx.hnsw.efConstruction = int(config.get("efConstruction",
                                                 EF_CONSTRUCTION))
        with single_threaded_faiss(det):
            if add_chunk:
                n = vectors.shape[0]
                for i in range(0, n, int(add_chunk)):
                    idx.add(np.ascontiguousarray(vectors[i:i + int(add_chunk)]))
                    if progress:
                        progress(min(i + int(add_chunk), n), n,
                                 time.time() - t0)
            else:
                idx.add(vectors)
        idx.hnsw.efSearch = int(config.get("efSearch", 128))
        return BuiltIndex(family=NAME, config=config, n_base=len(vectors),
                          dim=vectors.shape[1],
                          state={"index": idx, "vectors": vectors,
                                 "deterministic": det},
                          build_seconds=time.time() - t0)

    # -- search ------------------------------------------------------------
    def search(self, built, queries, k, config):
        idx = built.state["index"]
        idx.hnsw.efSearch = int(config.get("efSearch", 128))
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
        M = int(built.config.get("M", 32))
        return Footprint(
            stored_vectors=built.n_base,
            amplification=1.0,
            memory_bytes=estimate_memory_bytes(built.n_base, built.dim, M),
            fanout=1.0,
            shards=1,
        )


MODEL = SingleNodeHNSW()
