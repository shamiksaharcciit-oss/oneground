"""random_sharded — the worked example. A deliberately bad architecture.

WHY THIS EXISTS
---------------
It is the reference implementation of the family protocol, written to be read
rather than deployed. Every method the protocol requires is here, in the order
`docs/FAMILIES.md` introduces them, with the reasoning beside it. It passes
`oneground models conformance`, which is the point: a contributor can run the
suite against this file, see it green, and then change one thing at a time.

**It is not registered and must not be.** It is not in `oneground/models/`, it
is not in `REGISTRY`, and no requirements file can name it, so nobody can
deploy it by accident. Run the suite against it by path:

    oneground models conformance --module examples/random_sharded/model.py

WHY A BAD ARCHITECTURE IS THE RIGHT EXAMPLE
-------------------------------------------
A good example family would teach the protocol and hide the thing the protocol
is *for*. This one partitions at random and routes at random: the partition
carries no information about the vectors, so probing `probe` of `shards`
regions reaches a uniformly random `probe/shards` of the corpus, and the
neighbours in the other shards are unreachable no matter how the index is
tuned.

That is **routing loss**, and this family exists to make it visible:

    routing loss  ~=  1 - probe/shards        (this family, by construction)
    routing loss  ~=  small                   (semantic_sharded, when the
                                               partition matches the corpus)

Both are measured the same way, by `ceiling()`. The difference between them is
the whole question the tool exists to answer, and a family that always reaches
everything -- as all three shipped families do at their published settings --
can never show it. `random_sharded` is the negative control.

Its recall is worse than `hash_sharded`'s on any corpus, at the same shard
count, and that is not a defect to be fixed. `hash_sharded` fans out to every
shard and loses nothing to routing; this one probes a subset of a meaningless
partition and loses most of it. Measuring both is how "scale out horizontally"
stops being a slogan.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
No closure, no replication, no routing intelligence, no reranking logic of its
own. Every one of those is a real technique and every one would obscure the
protocol. `semantic_sharded` is where to read those.
"""

import time
from dataclasses import dataclass

import numpy as np

from oneground.models import indexes, rerank
from oneground.models import state as S
from oneground.models.base import (BUILD, CONSTANT, HNSW, HNSW_ONLY,
                                   BuiltIndex, Candidates, Config, Footprint,
                                   Param, ParameterError, coherent,
                                   declare_parameters, deterministic_faiss,
                                   estimate_memory_bytes, exact_over,
                                   index_combinations, index_params,
                                   merge_candidates, rerank_params,
                                   resolve_deterministic)

NAME = "random_sharded"

SHARD_DEPTH = 30
EF_CONSTRUCTION = 200

DEFAULT_GRID = {"M": (32,), "efSearch": (96,), "shards": (8,), "probe": (2,)}

# Every key this family reads, declared with its type, its validity bounds and
# its role (task 026). A key that is not here cannot be read -- `Config.get`
# refuses it -- and a key here that nothing reads is a knob that does nothing,
# which `oneground models conformance` will tell you about.
#
# `index_params()` and `rerank_params()` are shared declarations: the index
# algorithm and the rerank stage are properties of the search path rather than
# of a partition, so every family gets the same ones rather than writing its
# own.
PARAMETERS = declare_parameters(NAME, (
    Param("shards", int, minimum=1, swept=True, default=8,
          note="how many regions the corpus is split into, at random"),
    Param("probe", int, minimum=1, swept=True, default=2,
          note="how many regions each query searches. Chosen at random, "
               "because this family has nothing better to choose them by"),
    Param("M", int, minimum=1, swept=True, default=32, belongs_to=HNSW_ONLY,
          note="HNSW links per node, per shard"),
    Param("efSearch", int, minimum=1, swept=True, default=96,
          belongs_to=HNSW_ONLY, note="search beam width, per shard"),
    Param("shard_depth", int, role=CONSTANT,
          fixed=f"max({SHARD_DEPTH}, k), computed per search",
          note="not read from the config"),
    Param("efConstruction", int, role=CONSTANT, fixed=EF_CONSTRUCTION,
          note="every shard is built at EF_CONSTRUCTION"),
    Param("deterministic", bool, role=BUILD,
          note="single-threaded build; see base.DETERMINISTIC_DEFAULT"),
) + index_params() + rerank_params())


def _d(key):
    """This family's declared default for `key`.

    Read from the table rather than repeated at each `config.get` call, so the
    value a config is labelled with and the value the build uses cannot drift
    apart (task 032).
    """
    return PARAMETERS[key].default


def assign_regions(n_vectors, n_shards, seed):
    """Region per vector: uniform, seeded, and carrying no information.

    Seeded from the run's seed so two runs agree -- a partition that changed
    between runs would make every comparison meaningless. `default_rng` rather
    than `np.random`, because the global RNG is shared state and another
    library drawing from it would move this partition.
    """
    return np.random.default_rng(int(seed)).integers(
        0, int(n_shards), size=int(n_vectors), dtype=np.int64)


def route(n_queries, n_shards, probe, seed):
    """(scored keys, probed regions) per query -- random routing, seeded.

    Every region is "scored" with a random key and the lowest `probe` are
    searched. The keys are meaningless by design; what matters is that the
    choice is recorded, because `state()` has to say which regions a query
    probed and why, and "it picked some" is not an answer the lab can draw.
    """
    rng = np.random.default_rng(int(seed) + 1)
    keys = rng.random((int(n_queries), int(n_shards))).astype(np.float32)
    probed = np.argsort(keys, axis=1)[:, :int(probe)].astype(np.int32)
    return keys, probed


@dataclass
class RandomSharded:
    name: str = NAME

    # -- sweep -------------------------------------------------------------
    def configs(self, space):
        """Every configuration this family offers for the given space.

        Two rules worth copying. The index axis is the OUTER loop and goes
        through `index_combinations`, which crosses the algorithms with only
        the knobs each one reads -- crossing every knob with every algorithm
        produces configurations that are refused on sight. And every config is
        built through `Config.make`, which canonicalises defaults so that a
        parameter written at its default and the same parameter omitted are
        one label and therefore one row.
        """
        grid = {**DEFAULT_GRID, **space.for_family(NAME)}
        node_counts = grid.get("shards", space.node_counts)
        seen, out = set(), []
        for params in space.included_for(NAME):
            c = Config.make(NAME, dict(params))
            if c.label not in seen:
                seen.add(c.label)
                out.append(c)
        for idx in index_combinations(NAME, grid):
            for n in node_counts:
                for p in grid["probe"]:
                    for M in grid["M"]:
                        for ef in grid["efSearch"]:
                            c = Config.make(NAME, coherent(NAME, dict(
                                idx, shards=int(n), probe=int(p), M=int(M),
                                efSearch=int(ef))))
                            if c.label not in seen:
                                seen.add(c.label)
                                out.append(c)
        return out

    # -- build -------------------------------------------------------------
    def build(self, vectors, config, seed, context=None, deterministic=None):
        """One index per region. Deterministic given (vectors, config, seed).

        The refusal at the top is the protocol's rule, not this family's
        preference: a configuration that cannot be built is refused with a
        `ParameterError` naming what is wrong, so a sweep **drops one row and
        reports it** instead of aborting (task 034). Raising anything else --
        or letting faiss raise for you -- ends the run.
        """
        n_shards = int(config.get("shards", _d("shards")))
        probe = int(config.get("probe", _d("probe")))
        if n_shards > len(vectors):
            raise ParameterError(
                f"{NAME}: shards={n_shards} over {len(vectors)} vector(s); a "
                f"partition cannot have more regions than there are vectors "
                f"to put in them. Lower shards to at most {len(vectors)}.")
        if probe > n_shards:
            raise ParameterError(
                f"{NAME}: probe={probe} of shards={n_shards}; a query cannot "
                f"search more regions than exist. Lower probe to at most "
                f"{n_shards}.")

        t0 = time.time()
        det = resolve_deterministic(config, deterministic)
        assign = assign_regions(len(vectors), n_shards, seed)

        shards, ids_of = {}, {}
        with deterministic_faiss(det):
            for r in range(n_shards):
                member = np.where(assign == r)[0].astype(np.int64)
                if len(member) == 0:
                    continue
                shards[r] = indexes.build(
                    vectors[member], config, seed=seed, deterministic=det,
                    dim=vectors.shape[1], where=f"region {r}",
                    knobs={"efConstruction": EF_CONSTRUCTION})
                ids_of[r] = member

        return BuiltIndex(
            family=NAME, config=config, n_base=len(vectors),
            dim=vectors.shape[1],
            state={"shards": shards, "ids_of": ids_of, "assign": assign,
                   "vectors": vectors, "deterministic": det,
                   "n_shards": n_shards},
            build_seconds=time.time() - t0)

    # -- search ------------------------------------------------------------
    def search(self, built, queries, k, config):
        """The top `k` this architecture actually returns.

        `rerank.depth_for` decides how deep the first pass goes: at
        `rerank: none` it is `k` and this is what the family always did. The
        stage is applied through `rerank.apply`, one implementation shared by
        every family, so a family does not write its own second pass.
        """
        st = built.state
        shards, ids_of = st["shards"], st["ids_of"]
        for s in shards.values():
            indexes.set_search(s, config)

        probe = int(config.get("probe", _d("probe")))
        _, probed = route(len(queries), st["n_shards"], probe,
                          built.config.get("shards", _d("shards")))
        width = rerank.depth_for(k, config)
        depth = max(SHARD_DEPTH, width)
        ids = np.full((len(queries), width), -1, dtype=np.int64)
        scores = np.full((len(queries), width), -np.inf, dtype=np.float32)
        for qi in range(len(queries)):
            cid, csc = [], []
            for r in probed[qi]:
                s = shards.get(int(r))
                if s is None:                      # an empty region
                    continue
                n = min(depth, s.ntotal)
                sc, loc = s.search(queries[qi:qi + 1], n)
                cid.append(ids_of[int(r)][loc[0]])
                csc.append(sc[0])
            if cid:
                ids[qi], scores[qi] = merge_candidates(cid, csc, width)
        return rerank.apply(built, Candidates(ids=ids, scores=scores),
                            queries, k, config)

    # -- ceiling -----------------------------------------------------------
    def ceiling(self, built, queries, k):
        """Exact k-NN over what each query's routing can reach. NOT optional.

        This is the method that makes `routing_loss` mean something. It answers
        "if the index inside every probed region were perfect, what is the best
        this architecture could have returned?" -- so the gap from 1.0 splits
        into what the partition made unreachable (here: most of it) and what
        the index failed to find.

        A family that returns exact k-NN over the whole corpus here, when its
        routing does not reach the whole corpus, reports its routing loss as
        zero and its index loss as everything. The conformance suite checks
        `ceiling >= recall`, which catches the opposite mistake; nothing but
        care catches this one.
        """
        st = built.state
        probe = int(built.config.get("probe", _d("probe")))
        _, probed = route(len(queries), st["n_shards"], probe,
                          built.config.get("shards", _d("shards")))
        out = np.full((len(queries), k), -1, dtype=np.int64)
        for qi in range(len(queries)):
            reach = [st["ids_of"][int(r)] for r in probed[qi]
                     if int(r) in st["ids_of"]]
            subset = (np.concatenate(reach) if reach
                      else np.empty(0, dtype=np.int64))
            ids, _ = exact_over(st["vectors"], subset, queries[qi:qi + 1], k)
            out[qi] = ids[0]
        return out

    # -- footprint ---------------------------------------------------------
    def footprint(self, built):
        """What this costs, measured from the artifact where it can be.

        `index_bytes` is what faiss reports for the indexes actually built --
        not a formula over vector count and dimension, which cannot see
        quantisation and was wrong by 61x on a quantised index (task 034).
        `memory_bytes` stays, and stays labelled an estimate.

        `fanout` is `probe`, not `shards`: the cost a recall number never
        shows is how many regions each query had to search.
        """
        st = built.state
        algorithm = indexes.algorithm_of(built.config)
        M = int(built.config.get("M", _d("M"))) if algorithm == HNSW else 0
        probe = int(built.config.get("probe", _d("probe")))
        return Footprint(
            stored_vectors=built.n_base,           # no replication
            amplification=1.0,
            memory_bytes=estimate_memory_bytes(built.n_base, built.dim, M),
            fanout=float(min(probe, len(st["shards"]))),
            shards=len(st["shards"]),
            index_bytes=sum(indexes.measured_bytes(s)
                            for s in st["shards"].values()),
            vector_bytes=indexes.stored_vector_bytes(
                built.config, built.n_base, built.dim),
        )

    # -- state -------------------------------------------------------------
    def state(self, built, queries, k, config, gt_ids, seed):
        """What this configuration did, for the lab to draw (task 020).

        It measures nothing new: every array here is a record of a decision
        the build and the search already made. A `state()` that recomputed a
        routing decision could disagree with the row beside it, which is why
        `state.contract_violations` checks the candidates merge back to what
        `search` returned.
        """
        st = built.state
        n, dim = st["vectors"].shape
        nq = len(queries)
        n_shards = st["n_shards"]
        assign = st["assign"].astype(np.int32)
        shards, ids_of = st["shards"], st["ids_of"]

        partition = S.PartitionState(
            family=NAME, kind="random", seed=int(seed),
            params={"shards": n_shards,
                    "probe": int(config.get("probe", _d("probe")))},
            region_ids=np.arange(n_shards, dtype=np.int32),
            region_sizes=np.bincount(
                assign, minlength=n_shards).astype(np.int64))
        # One copy of every vector, and no centroid distance: there are no
        # centroids. NaN rather than 0.0, because 0.0 is a distance and this
        # is the absence of one.
        assignment = S.AssignmentState(
            home_region=assign, copy_count=np.ones(n, dtype=np.uint8),
            copy_set=assign.reshape(-1, 1),
            centroid_dist=np.full((n, 1), np.nan, dtype=np.float32),
            max_assign=1, nearest_region=assign.reshape(-1, 1))

        probe = int(config.get("probe", _d("probe")))
        keys, probed = route(nq, n_shards, probe,
                             config.get("shards", _d("shards")))
        # Every probed region must appear in `scored_region`, or the state
        # contract fails: a region that was searched and never scored is a
        # decision with no record of how it was made. The keys are random, and
        # saying so is better than pretending they are distances.
        reasons = np.full(probed.shape, S.ROUTE_PROBE, dtype=np.uint8)
        reasons[:, 0] = S.ROUTE_DEFAULT
        route_state = S.RouteState(
            scored_region=np.tile(np.arange(n_shards, dtype=np.int32),
                                  (nq, 1)),
            scored_dist=keys,
            probed_region=probed,
            probe_reason=reasons)

        for s in shards.values():
            indexes.set_search(s, config)
        per_query, padded = S.collect_candidates(
            shards, ids_of, queries, probed, max(SHARD_DEPTH, k))
        candidates = S.build_candidates(per_query, gt_ids,
                                        int(np.shape(gt_ids)[1]))
        return S.ModelState(
            family=NAME, config_label=config.label,
            params=config.declared(), seed=int(seed), n_base=int(n),
            n_queries=int(nq), dim=int(dim), partition=partition,
            assignment=assignment, route=route_state, candidates=candidates,
            load=S.build_load(partition.region_ids, assignment, route_state,
                              candidates),
            notes=["scored_dist holds the random routing keys, not "
                   "distances: this family has no centroids and chooses its "
                   "regions at random, which is the point of it",
                   f"faiss padding slots mapped through ids_of as search "
                   f"maps them: {padded}"])


MODEL = RandomSharded()
