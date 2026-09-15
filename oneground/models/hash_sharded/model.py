"""hash_sharded — N shards by a seeded hash of the vector id.

The deliberately dumb partition. Vectors are split across N shards by hashing
their id, so the partition carries no semantic information at all: every query
must fan out to **all N shards**, and the results are merged.

Why a family that cannot possibly route well is worth measuring
---------------------------------------------------------------
Because it is the honest control. Its recall is essentially the single-node
baseline's -- nothing is unreachable, only spread out -- at a fan-out of N and
no storage amplification. So it isolates the one question semantic sharding is
supposed to answer:

    semantic_sharded is worth its complexity only if it beats hash_sharded's
    recall at a *lower* fan-out, or matches it at lower cost.

On a corpus where semantic sharding routes well, `probe=1` beats fan-out N. On
arxiv-150k, where 89% of queries are ambiguous, it does not -- and hash
sharding is what makes that comparison concrete rather than rhetorical. This
family is the reason "scale out horizontally" has a measured price tag in the
table instead of a shrug.

Definition
----------
Shard assignment is `blake2b(str(vector_id)) mod N`, seeded with the run seed
so two runs agree and two different seeds give different partitions. The id is
the vector's row index in the sample unless the caller supplies ids. There is
no replication: every vector lives in exactly one shard, so storage
amplification is 1.0 and copies are 1 at every percentile.

Ceiling is the full set: every shard is probed, so nothing is unreachable and
routing loss is zero by definition. Any gap from 1.0 is index loss.

Known limits
------------
- A hash partition ignores the data entirely, so shard sizes are even only in
  expectation; with small N and few vectors they can be visibly uneven.
- Fan-out is N by construction. This family has no way to probe fewer shards,
  which is the whole point of it, but it means `node_counts` is the only knob
  that trades cost against anything.
"""

import hashlib
import time
from dataclasses import dataclass

import numpy as np

from ..base import (BUILD, CONSTANT, BuiltIndex, Candidates, Config,
                    Footprint, Param, declare_parameters,
                    estimate_memory_bytes, exact_over, merge_candidates,
                    resolve_deterministic, single_threaded_faiss)

NAME = "hash_sharded"

SHARD_DEPTH = 30
EF_CONSTRUCTION = 200

DEFAULT_GRID = {"M": (32,), "efSearch": (96,)}

# Every key this family reads, and the two it fixes (task 026). Unlike
# semantic_sharded, this family never read `shard_depth` from a config: its
# per-shard depth is max(SHARD_DEPTH, k), computed in `search`. The simulator
# used to add the key anyway, where it was ignored.
PARAMETERS = declare_parameters(NAME, (
    Param("shards", int, minimum=1, swept=True,
          note="N shards by seeded hash; every query fans out to all"),
    Param("M", int, minimum=1, swept=True,
          note="HNSW links per node, per shard"),
    Param("efSearch", int, minimum=1, swept=True,
          note="search beam width, per shard"),
    Param("shard_depth", int, role=CONSTANT,
          fixed=f"max({SHARD_DEPTH}, k), computed per search",
          note="not read from the config"),
    Param("efConstruction", int, role=CONSTANT, fixed=EF_CONSTRUCTION,
          note="every shard is built at EF_CONSTRUCTION"),
    Param("deterministic", bool, role=BUILD,
          note="single-threaded build; see base.DETERMINISTIC_DEFAULT"),
))


def shard_of(vector_id, n_shards, seed):
    """Seeded, stable assignment of one vector to one shard.

    blake2b rather than Python's `hash()`: `hash()` is randomized per process
    unless PYTHONHASHSEED is set, which would make a "deterministic" model
    silently non-reproducible across runs.
    """
    h = hashlib.blake2b(str(vector_id).encode("utf-8"),
                        digest_size=8,
                        key=str(int(seed)).encode("utf-8")[:64])
    return int.from_bytes(h.digest(), "big") % int(n_shards)


def assign_shards(n_vectors, n_shards, seed, ids=None):
    """Shard id per vector row, as an int64 array."""
    src = ids if ids is not None else range(n_vectors)
    return np.fromiter((shard_of(v, n_shards, seed) for v in src),
                       dtype=np.int64, count=n_vectors)


@dataclass
class HashSharded:
    name: str = NAME

    # -- sweep -------------------------------------------------------------
    def configs(self, space):
        grid = {**DEFAULT_GRID, **space.for_family(NAME)}
        node_counts = grid.get("shards", space.node_counts)
        seen, out = set(), []
        for params in space.included_for(NAME):
            p = {"shards": 3, "M": 32, "efSearch": 96}
            p.update(params)
            c = Config.make(NAME, p)
            if c.label not in seen:
                seen.add(c.label)
                out.append(c)
        for n in node_counts:
            for M in grid["M"]:
                for ef in grid["efSearch"]:
                    c = Config.make(NAME, {"shards": int(n), "M": int(M),
                                           "efSearch": int(ef)})
                    if c.label not in seen:
                        seen.add(c.label)
                        out.append(c)
        return out

    # -- build -------------------------------------------------------------
    def build(self, vectors, config, seed, context=None, deterministic=None):
        """One HNSW per shard.

        `deterministic` (default True) adds single-threaded, for the reason
        task 012 measured on `single_node_hnsw`: faiss links an HNSW graph
        under OpenMP, so a parallel add depends on thread scheduling and two
        builds from identical inputs return different neighbours. The shard
        assignment was already seeded and deterministic; the graphs inside the
        shards were not.
        """
        import faiss
        t0 = time.time()
        det = resolve_deterministic(config, deterministic)
        n_shards = int(config.get("shards", 3))
        ids = (context or {}).get("ids")
        assign = assign_shards(len(vectors), n_shards, seed, ids)

        shards, ids_of = {}, {}
        with single_threaded_faiss(det):
            for r in range(n_shards):
                member = np.where(assign == r)[0].astype(np.int64)
                if len(member) == 0:
                    continue
                s = faiss.IndexHNSWFlat(vectors.shape[1],
                                        int(config.get("M", 32)),
                                        faiss.METRIC_INNER_PRODUCT)
                s.hnsw.efConstruction = EF_CONSTRUCTION
                s.add(vectors[member])
                s.hnsw.efSearch = int(config.get("efSearch", 96))
                shards[r], ids_of[r] = s, member

        return BuiltIndex(
            family=NAME, config=config, n_base=len(vectors),
            dim=vectors.shape[1],
            state={"shards": shards, "ids_of": ids_of, "assign": assign,
                   "vectors": vectors, "deterministic": det},
            build_seconds=time.time() - t0)

    # -- search ------------------------------------------------------------
    def search(self, built, queries, k, config):
        shards, ids_of = built.state["shards"], built.state["ids_of"]
        for s in shards.values():
            s.hnsw.efSearch = int(config.get("efSearch", 96))

        ids = np.full((len(queries), k), -1, dtype=np.int64)
        scores = np.full((len(queries), k), -np.inf, dtype=np.float32)
        depth = max(SHARD_DEPTH, k)
        for qi in range(len(queries)):
            cid, csc = [], []
            for r, s in shards.items():          # every shard, every query
                n = min(depth, s.ntotal)
                sc, loc = s.search(queries[qi:qi + 1], n)
                cid.append(ids_of[r][loc[0]])
                csc.append(sc[0])
            ids[qi], scores[qi] = merge_candidates(cid, csc, k)
        return Candidates(ids=ids, scores=scores)

    # -- ceiling -----------------------------------------------------------
    def ceiling(self, built, queries, k):
        """Every shard is probed, so everything is reachable."""
        ids, _ = exact_over(built.state["vectors"],
                            np.arange(built.n_base), queries, k)
        return ids

    # -- footprint ---------------------------------------------------------
    def footprint(self, built):
        M = int(built.config.get("M", 32))
        n_shards = int(built.config.get("shards", 3))
        return Footprint(
            stored_vectors=built.n_base,          # no replication
            amplification=1.0,
            memory_bytes=estimate_memory_bytes(built.n_base, built.dim, M),
            fanout=float(n_shards),               # the cost this family shows
            shards=len(built.state["shards"]),
        )

    # -- state -------------------------------------------------------------
    def state(self, built, queries, k, config, gt_ids, seed):
        """What this configuration did, as a `state.ModelState` (task 020).

        A hash partition has no centroids and routes nothing: every vector has
        one copy and no centroid distance (NaN, not zero), and every query
        probes every shard for reason fan-out, with nothing scored because
        nothing is chosen. The candidates are search's per-shard calls,
        repeated at search's depth. Nothing is measured here that the row did
        not already measure.
        """
        from .. import state as S
        st = built.state
        n, dim = st["vectors"].shape
        nq = len(queries)
        n_shards = int(config.get("shards", 3))
        assign = st["assign"].astype(np.int32)
        shards, ids_of = st["shards"], st["ids_of"]

        partition = S.PartitionState(
            family=NAME, kind="hash", seed=int(seed),
            params={"shards": n_shards},
            region_ids=np.arange(n_shards, dtype=np.int32),
            region_sizes=np.bincount(assign,
                                     minlength=n_shards).astype(np.int64))
        assignment = S.AssignmentState(
            home_region=assign, copy_count=np.ones(n, dtype=np.uint8),
            copy_set=assign.reshape(-1, 1),
            centroid_dist=np.full((n, 1), np.nan, dtype=np.float32),
            max_assign=1, nearest_region=assign.reshape(-1, 1))
        # search iterates `shards.items()`; the probe order is that order
        order = np.asarray(list(shards), dtype=np.int32)
        probed = np.tile(order, (nq, 1))
        route = S.RouteState(
            scored_region=np.zeros((nq, 0), dtype=np.int32),
            scored_dist=np.zeros((nq, 0), dtype=np.float32),
            probed_region=probed,
            probe_reason=np.full(probed.shape, S.ROUTE_FANOUT,
                                 dtype=np.uint8))

        for s in shards.values():
            s.hnsw.efSearch = int(config.get("efSearch", 96))
        per_query, padded = S.collect_candidates(
            shards, ids_of, queries, probed, max(SHARD_DEPTH, k))
        candidates = S.build_candidates(per_query, gt_ids,
                                        int(np.shape(gt_ids)[1]))
        return S.ModelState(
            family=NAME, config_label=config.label,
            params=dict(config.params), seed=int(seed), n_base=int(n),
            n_queries=int(nq), dim=int(dim), partition=partition,
            assignment=assignment, route=route, candidates=candidates,
            load=S.build_load(partition.region_ids, assignment, route,
                              candidates),
            notes=[f"faiss padding slots mapped through ids_of as search "
                   f"maps them: {padded}"])


MODEL = HashSharded()
