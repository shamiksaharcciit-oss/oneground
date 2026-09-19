"""semantic_sharded — k-means regions, epsilon closure, probe P.

Cut the space into `centroids` k-means regions, give each region its own HNSW
index, and route a query to its P nearest regions. A vector whose second-
nearest centroid is within (1+epsilon) of its nearest is *copied* into that
region too, up to MAX_ASSIGN regions -- the closure that buys recall back at
the cost of storage.

This is the architecture that sounds obviously right for a semantically
clustered corpus. On arxiv-150k it loses: 0.932 recall at 3.7x storage against
0.997 at 1x for a single flat index, because 84% of vectors sit within epsilon
of four regions and get replicated to the cap.

Extracted from `oneground/fixture/reference.py` in task 008 **with every
measurement unchanged**: the same closure rule (`within[:, 0] = True`), the
same per-shard `efConstruction = 200` regardless of config, the same
`min(30, ntotal)` per-shard depth, the same score-merge with id dedupe, and
the same ceiling (exact over the union of probed shards). The smoke fixture
rebuilds byte-identically through it.

Known limits
------------
- MAX_ASSIGN is 4. A vector near five regions is copied into four of them, so
  storage amplification saturates at 4.0 and the closure's cost is understated
  for very fuzzy corpora.
- Per-shard search depth defaults to 30 candidates before the merge, and is
  now settable as `shard_depth`. A query whose ten true neighbours are all in
  one shard beyond that rank loses them, and the loss is attributed to the
  index rather than to routing. `oneground simulate` raises it to the largest
  k it reports, so recall@100 measures the architecture rather than the cap.
- `efConstruction` is 200 for every shard and is not swept.
"""

import time
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .. import indexes
from ..base import (BUILD, CONSTANT, HNSW, HNSW_ONLY, RUN, BuiltIndex,
                    Candidates, Config, Footprint, Param, coherent,
                    declare_parameters, deterministic_faiss,
                    estimate_memory_bytes, exact_over, index_combinations,
                    index_params, merge_candidates, resolve_deterministic)

NAME = "semantic_sharded"

# The closure cap: how many regions one vector may be copied into.
MAX_ASSIGN = 4
# Default per-shard candidate depth before the merge.
#
# Task 008 measured that this constant *caps* recall@k: a query never sees more
# than probe * shard_depth distinct vectors, so recall@100 was bounded at
# probe * 0.30 and measured the constant rather than the architecture. Task 009
# made it a Config field so a caller can raise it.
#
# The default stays 30 because every published fixture value was measured with
# it, and `oneground.fixture.reference` builds its Config without the field.
# `oneground simulate` overrides it to max(30, k_max) and records the value it
# used in simulate_info.json.
SHARD_DEPTH = 30
# Every shard is built at this efConstruction, as the fixture always has.
EF_CONSTRUCTION = 200

DEFAULT_GRID = {
    "centroids": (256,),
    "epsilon": (0.0, 0.1, 0.2),
    "probe": (1, 2),
    "M": (32,),
    "efSearch": (96,),
}

# Every key this family reads, and the one it deliberately does not (task
# 026). `shard_depth` is set per run by the simulator from the ks it reports.
# `efConstruction` is fixed for every shard: declared so that naming it gets
# "a constant" rather than "no such parameter", and refused in any config,
# since a config carrying it would be labelled as if it varied.
PARAMETERS = declare_parameters(NAME, (
    Param("centroids", int, minimum=1, swept=True, default=256,
          note="k-means regions"),
    Param("epsilon", float, minimum=0.0, swept=True, default=0.2,
          note="closure: copy a vector into every region within (1+eps)"),
    Param("probe", int, minimum=1, swept=True, default=2,
          note="regions searched per query"),
    Param("M", int, minimum=1, swept=True, default=32,
          belongs_to=HNSW_ONLY, note="HNSW links per node, per shard"),
    Param("efSearch", int, minimum=1, swept=True, default=96,
          belongs_to=HNSW_ONLY, note="search beam width, per shard"),
    Param("shard_depth", int, role=RUN, minimum=1, default=SHARD_DEPTH,
          note="candidates taken from each probed shard; set by simulate"),
    Param("efConstruction", int, role=CONSTANT, fixed=EF_CONSTRUCTION,
          note="every shard is built at EF_CONSTRUCTION"),
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
class SemanticSharded:
    name: str = NAME

    # -- sweep -------------------------------------------------------------
    def configs(self, space):
        grid = {**DEFAULT_GRID, **space.for_family(NAME)}
        seen, out = set(), []
        for params in space.included_for(NAME):
            # No seed dict of defaults here since task 032: `Config.make`
            # fills what an include entry leaves out, from the declared table,
            # so the defaults are written down once rather than three times.
            c = Config.make(NAME, dict(params))
            if c.label not in seen:
                seen.add(c.label)
                out.append(c)
        # The index axis is the outer one (task 034); see single_node_hnsw's
        # `configs` for why `coherent` and the dedupe do the work.
        for idx in index_combinations(NAME, grid):
            for n in grid["centroids"]:
                for eps in grid["epsilon"]:
                    for p_ in grid["probe"]:
                        for M in grid["M"]:
                            for ef in grid["efSearch"]:
                                c = Config.make(NAME, coherent(NAME, dict(
                                    idx, centroids=int(n), epsilon=float(eps),
                                    probe=int(p_), M=int(M),
                                    efSearch=int(ef))))
                                if c.label not in seen:
                                    seen.add(c.label)
                                    out.append(c)
        return out

    # -- build -------------------------------------------------------------
    def build(self, vectors, config, seed, context=None, deterministic=None):
        """k-means, closure, one HNSW per region.

        `context["centroids"]` reuses centroids the caller already computed.
        The fixture builder passes the ones `characterize()` produced, which
        is both faster (no second 256-way clustering over 150,000 vectors) and
        exactly what the published reference results were measured with.

        `deterministic` (default True) runs the whole build single-threaded --
        not only the HNSW adds. k-means is seeded, but its centroid update is
        a floating-point sum over points, and OpenMP does not fix the order in
        which those partial sums combine. A centroid that differs in the last
        bit can move a point across a region boundary, which changes shard
        membership, which changes every graph built from it. Seeding is not
        sufficient for either half; one thread is.
        """
        from ...measures.crispness import centroid_dists, kmeans

        t0 = time.time()
        det = resolve_deterministic(config, deterministic)
        n_cent = int(config.get("centroids", _d("centroids")))
        eps = float(config.get("epsilon", _d("epsilon")))

        with deterministic_faiss(det):
            cents = (context or {}).get("centroids")
            if cents is None or len(cents) != n_cent:
                cents = kmeans(vectors, n_cent, seed)

            # --- closure, unchanged from the fixture builder ---
            d, near = centroid_dists(vectors, cents, MAX_ASSIGN)
            within = d <= d[:, [0]] * (1 + eps)
            within[:, 0] = True
            copies = within.sum(axis=1)
            members = defaultdict(list)
            for col in range(MAX_ASSIGN):
                sel = np.where(within[:, col])[0]
                for vid, r in zip(sel, near[sel, col]):
                    members[int(r)].append(int(vid))

            shards, ids_of = {}, {}
            # Sorted so the regions are built in a fixed order. `members` is a
            # defaultdict filled in numpy-scan order, which is already stable,
            # but relying on that would make determinism depend on an
            # implementation detail of the loop above rather than on a choice.
            for r in sorted(members):
                ids = np.asarray(members[r], dtype=np.int64)
                # Task 034: the algorithm is the configuration's, one per
                # region. `hnsw` is the default and takes the path it took
                # before -- same construction, same efConstruction constant,
                # same efSearch set after the add -- because every published
                # value was measured under it. `where` names the region so an
                # "nlist over too few vectors" refusal is actionable: a
                # semantic partition's regions are not the same size.
                shards[r] = indexes.build(
                    vectors[ids], config, seed=seed, deterministic=det,
                    dim=vectors.shape[1], where=f"region {r}",
                    knobs={"efConstruction": EF_CONSTRUCTION})
                ids_of[r] = ids

        return BuiltIndex(
            family=NAME, config=config, n_base=len(vectors),
            dim=vectors.shape[1],
            state={"shards": shards, "ids_of": ids_of, "centroids": cents,
                   "copies": copies, "vectors": vectors,
                   "deterministic": det},
            build_seconds=time.time() - t0)

    # -- routing -----------------------------------------------------------
    def _probed(self, built, queries, config):
        """The regions this query probes, on the build's arithmetic path.

        The context is here rather than at the three call sites because all
        three need it and one of them did not have it. Task 032b's pod
        session measured the consequence: the base-side `centroid_dists` in
        `state()` was wrapped and its column came back byte-identical across
        an Intel laptop and an AMD pod, while the query-side call beside it
        was not and 3,191 of 4,000 recorded distances differed, by up to
        7.2e-07. The same call on this laptop moves 3,516 of 4,000 distances
        when the context is turned off, which is the whole of that residual.
        It never reached a measurement -- the probed regions are the argsort,
        and the argsort was unchanged -- but the state recorded distances the
        run had not computed on the path it computed everything else on.
        That is the `_centroid_cache` shape again: a determinism context that
        does not reach a call site needing it.

        `search`, `ceiling` and `state` all route through here, so after this
        they agree by construction rather than by coincidence.
        """
        from ...measures.crispness import centroid_dists
        probe = int(config.get("probe", _d("probe")))
        with deterministic_faiss(built.state.get("deterministic", True)):
            _, q_r = centroid_dists(queries, built.state["centroids"], probe)
        return q_r

    # -- search ------------------------------------------------------------
    def search(self, built, queries, k, config):
        shards, ids_of = built.state["shards"], built.state["ids_of"]
        for s in shards.values():
            indexes.set_search(s, config)
        q_r = self._probed(built, queries, config)

        ids = np.full((len(queries), k), -1, dtype=np.int64)
        scores = np.full((len(queries), k), -np.inf, dtype=np.float32)
        for qi in range(len(queries)):
            cid, csc = [], []
            for r in q_r[qi]:
                r = int(r)
                if r not in shards:
                    continue
                n = min(int(config.get("shard_depth", _d("shard_depth"))),
                        shards[r].ntotal)
                sc, loc = shards[r].search(queries[qi:qi + 1], n)
                cid.append(ids_of[r][loc[0]])
                csc.append(sc[0])
            ids[qi], scores[qi] = merge_candidates(cid, csc, k)
        return Candidates(ids=ids, scores=scores)

    # -- ceiling -----------------------------------------------------------
    def ceiling(self, built, queries, k):
        """Exact search over the union of the shards this query probes.

        The upper bound on what any index inside these shards could return.
        The gap between this and `search` is index loss; the gap between this
        and 1.0 is routing loss and no index tuning recovers it.
        """
        vectors, ids_of = built.state["vectors"], built.state["ids_of"]
        q_r = self._probed(built, queries, built.config)
        out = np.full((len(queries), k), -1, dtype=np.int64)
        for qi in range(len(queries)):
            reachable = [ids_of[int(r)] for r in q_r[qi] if int(r) in ids_of]
            if not reachable:
                continue
            u = np.unique(np.concatenate(reachable))
            got, _ = exact_over(vectors, u, queries[qi:qi + 1], k)
            out[qi] = got[0]
        return out

    # -- footprint ---------------------------------------------------------
    def footprint(self, built):
        copies = built.state["copies"]
        stored = int(copies.sum())
        # The estimate stays and stays labelled one; beside it, what faiss
        # reports for the indexes actually built, summed over regions (034).
        # M is an HNSW link count, so it is 0 in the estimate under any other
        # algorithm rather than a number from a formula that does not apply.
        M = int(built.config.get("M", _d("M"))) \
            if indexes.algorithm_of(built.config) == HNSW else 0
        return Footprint(
            stored_vectors=stored,
            amplification=float(stored / built.n_base),
            memory_bytes=estimate_memory_bytes(stored, built.dim, M),
            fanout=float(built.config.get("probe", _d("probe"))),
            shards=len(built.state["shards"]),
            index_bytes=sum(indexes.measured_bytes(s)
                            for s in built.state["shards"].values()),
            vector_bytes=indexes.stored_vector_bytes(
                built.config, stored, built.dim),
            copies_p50=int(np.percentile(copies, 50)),
            copies_p95=int(np.percentile(copies, 95)),
            copies_p99=int(np.percentile(copies, 99)),
        )

    # -- state -------------------------------------------------------------
    def state(self, built, queries, k, config, gt_ids, seed):
        """What this configuration did, as a `state.ModelState` (task 020).

        Nothing here is a new measurement. The closure is recomputed with the
        call `build` made, under the same thread setting, and refused if its
        copy counts differ from build's own. The probed regions come from
        `_probed`, the router search used. The candidates are search's
        per-shard calls, repeated at the same depth.

        Queries are scored against at least two centroids even at probe=1, so
        the ambiguity rule (d2 <= 1.10 * d1) can be drawn from state.
        """
        import inspect

        from ...measures.crispness import centroid_dists, kmeans
        from .. import state as S

        st = built.state
        vectors, cents = st["vectors"], st["centroids"]
        n, dim = vectors.shape
        nq = len(queries)
        n_cent = int(len(cents))
        eps = float(config.get("epsilon", _d("epsilon")))
        probe = int(config.get("probe", _d("probe")))

        # `deterministic_faiss`, not `single_threaded_faiss`: this recomputes
        # the closure and asserts it equals what `build` produced, a few lines
        # below. It therefore has to take the same arithmetic path the build
        # took. Task 029 moved `build` off the BLAS path; leaving this one on
        # it would let `centroid_dists` return distances the build never saw
        # and fire that assertion on a correct state.
        #
        # This line and that import were merged from two branches without a
        # textual conflict -- task 020 added this call site while task 029
        # renamed the helper -- and the merged tree raised NameError. The same
        # class of collision as the `measure_config` shape.
        with deterministic_faiss(st.get("deterministic", True)):
            d, near = centroid_dists(vectors, cents, MAX_ASSIGN)
        within = d <= d[:, [0]] * (1 + eps)
        within[:, 0] = True
        copies = within.sum(axis=1)
        if not np.array_equal(copies, st["copies"]):
            raise RuntimeError(
                "semantic_sharded.state(): the recomputed closure's copy "
                "counts differ from build's, so this state would describe a "
                "different partition from the one measured")
        home = near[:, 0].astype(np.int32)

        partition = S.PartitionState(
            family=NAME, kind="kmeans", seed=int(seed),
            params={"centroids": n_cent, "epsilon": eps, "probe": probe},
            region_ids=np.arange(n_cent, dtype=np.int32),
            region_sizes=np.bincount(home, minlength=n_cent).astype(np.int64),
            centroids=np.asarray(cents, dtype=np.float32),
            distance=S.DISTANCE,
            # build's own call and simulate's shared cache both run kmeans at
            # its default; read the default rather than restate it
            kmeans_niter=int(
                inspect.signature(kmeans).parameters["niter"].default))
        assignment = S.AssignmentState(
            home_region=home, copy_count=copies.astype(np.uint8),
            copy_set=np.where(within, near, -1).astype(np.int32),
            centroid_dist=d.astype(np.float32), max_assign=MAX_ASSIGN,
            epsilon=eps, nearest_region=near.astype(np.int32))

        q_r = self._probed(built, queries, config)
        # The same context as `_probed`'s, for the same reason: these are the
        # distances the state RECORDS, and a recorded distance computed on a
        # path the run did not use is a receipt of something that did not
        # happen. Task 032b measured this one as 3,191 of 4,000 values
        # differing across two machines while every base-side column was
        # byte-identical.
        with deterministic_faiss(st.get("deterministic", True)):
            sd, sr = centroid_dists(queries, cents, max(probe, 2))
        reason = np.full(q_r.shape, S.ROUTE_PROBE, dtype=np.uint8)
        reason[:, 0] = S.ROUTE_DEFAULT
        route = S.RouteState(scored_region=sr.astype(np.int32),
                             scored_dist=sd.astype(np.float32),
                             probed_region=q_r.astype(np.int32),
                             probe_reason=reason)

        shards, ids_of = st["shards"], st["ids_of"]
        for s in shards.values():
            indexes.set_search(s, config)
        per_query, padded = S.collect_candidates(
            shards, ids_of, queries, q_r,
            int(config.get("shard_depth", _d("shard_depth"))))
        candidates = S.build_candidates(per_query, gt_ids,
                                        int(np.shape(gt_ids)[1]))
        return S.ModelState(
            family=NAME, config_label=config.label,
            params=config.declared(), seed=int(seed), n_base=int(n),
            n_queries=int(nq), dim=int(dim), partition=partition,
            assignment=assignment, route=route, candidates=candidates,
            load=S.build_load(partition.region_ids, assignment, route,
                              candidates),
            notes=[f"faiss padding slots mapped through ids_of as search "
                   f"maps them: {padded}"])


MODEL = SemanticSharded()
