"""The simulator's state, as a receipted artifact. Task 020.

A model's `simulate.json` row says *how well* an architecture did. It does not
say what the architecture *did*: where each vector went, how a query was
routed, what came back and from which shard. The lab (v0.2) draws exactly
those things, and the rule for the lab is the rule the report already keeps
for sentences:

    every view is a rendering of this state, never a second computation.

So a family exposes its state here, and a renderer reads it and nothing else.
If a renderer finds it needs something that is not in the state, the state is
missing a field -- that is a defect in this file, not a licence for the
renderer to go back to the vectors.

WHAT IS IN IT
-------------
One `ModelState` per configuration, made of five parts:

    PartitionState    the regions: ids, home populations, centroids where the
                      family has them, and the seed and parameters that made
                      them
    AssignmentState   per base vector: home region, copy set, copy count, and
                      its distances to its nearest `max_assign` centroids
    RouteState        per query: the regions scored (with their distances),
                      the regions probed, in order, and why each was probed
    CandidateState    per query: its exact top-k neighbour ids, and every
                      candidate a shard returned before the merge -- its
                      shard, its score, whether it survived dedupe, and its
                      rank in the true top-k
    LoadState         per shard: vectors held, queries served, candidates
                      contributed, under this configuration's query stream

Every field is a measurement or a declared parameter.

THE FIELD THE ACCEPTANCE TEST FOUND MISSING
-------------------------------------------
`CandidateState.true_ids`. The brief specified candidates with "whether it is
in the true top-k", which names a true neighbour only when some probed shard
*returned* it. A neighbour the routing never reached is, by definition, not a
candidate -- so its id was nowhere in the state, and neither "how many true
neighbours lie outside the routed region" nor "which of them the route
missed" could be answered for any query that lost one. Those are exactly the
queries a routing view exists to show. Task 020 step 4 measured the gap and
added the field; see `docs/STATE.md`.

THE FIELD TASK 021 ADDED
------------------------
`AssignmentState.nearest_region`. Moving epsilon is the lab's first control,
and task 021 asked what recomputes when it moves. The copy counts at any
epsilon follow from `centroid_dist` alone. The copy SETS -- which regions a
vector lands in, and so shard membership, load and which true neighbours a
route can reach -- need the ids of the regions those distances were taken to.
`copy_set` holds an id only inside the closure at the emitted epsilon, so a
recount could lower epsilon and could not raise it.

The column is additive. It does not change `state_version`: every reader
works from the header's column map, and a state written before it simply
lacks the column, which a view that needs it reports as `couldnt_check`.

THE ENCODING
------------
One file per configuration, `<family>__<id8>.state.npz`: an uncompressed zip
holding `header.json` and one `.npy` per column. Columnar because the base
side is 150,000 rows and the candidate side is hundreds of thousands, and a
JSON list of that many objects is an order of magnitude larger and slower to
read than the columns it describes.

Written deterministically -- every zip entry carries a fixed timestamp and the
entries are sorted -- so the same state produces the same bytes and its
sha256 in `MANIFEST.sha256` means something.

`header.json` carries `state_version`, the identity of the configuration, the
scalars of each part, and `columns`: for every array, its dtype, its shape and
what it means. A reader never has to guess a layout.

Distances are **non-squared Euclidean**, as `measures.crispness.centroid_dists`
returns them. faiss returns squared distances; the ratios that define
crispness (1.20) and the closure rule (1 + epsilon) are ratios of actual
distances, and a squared distance would square every ratio. The header says
which, so a renderer never has to know.
"""

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

STATE_VERSION = 1

# Why a region was probed. One byte per probed slot.
ROUTE_DEFAULT = 0      # the nearest region: every routed family's first probe
ROUTE_PROBE = 1        # an additional region, because the config's probe > 1
ROUTE_FANOUT = 2       # every shard, because the family does not route at all
ROUTE_AMBIGUITY = 3    # reserved for a family that probes by the ambiguity
                       # rule; no current family does, so it is never written
ROUTE_PAD = 255        # no probe in this slot

ROUTE_REASONS = {
    ROUTE_DEFAULT: "default: the nearest region",
    ROUTE_PROBE: "probe: an additional region because probe > 1",
    ROUTE_FANOUT: "fan-out: every shard, the family does not route",
    ROUTE_AMBIGUITY: "ambiguity rule (reserved; no current family uses it)",
}

DISTANCE = "euclidean (non-squared)"

# A fixed timestamp for every zip entry, so identical state gives identical
# bytes. 1980-01-01 is the earliest date the zip format can represent.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


# --------------------------------------------------------------------------
# the five parts
# --------------------------------------------------------------------------

@dataclass
class PartitionState:
    """The regions an architecture cuts the corpus into.

    `kind` says what a region is: `kmeans` (a centroid region, with
    `centroids`), `hash` (a hash shard, no centroid) or `single` (one region
    that holds everything). A renderer must not assume centroids exist.
    """

    family: str
    kind: str
    seed: int
    params: Dict[str, Any]
    region_ids: np.ndarray                 # int32 (R,)
    region_sizes: np.ndarray               # int64 (R,) home population
    centroids: Optional[np.ndarray] = None  # float32 (R, dim), kmeans only
    distance: Optional[str] = None
    kmeans_niter: Optional[int] = None


@dataclass
class AssignmentState:
    """Where each base vector went.

    `copy_set` and `centroid_dist` are (N, max_assign), in nearest-first
    order; slot 0 is the home region. `copy_set` is -1 where a vector was not
    copied into that slot's region. `centroid_dist` is NaN for a family with
    no centroids -- not zero, because zero would read as "on the centroid".

    `nearest_region` is (N, max_assign): the regions `centroid_dist` measures
    the distance to, nearest first, whether or not the vector was copied into
    them. `copy_set` names a region only inside the closure at this state's
    epsilon, so without this column a recount at a LARGER epsilon has the
    distance to a region it would now copy into and no idea which region that
    is. Task 021 found that; see the module docstring.
    """

    home_region: np.ndarray                # int32 (N,)
    copy_count: np.ndarray                 # uint8 (N,)
    copy_set: np.ndarray                   # int32 (N, max_assign)
    centroid_dist: np.ndarray              # float32 (N, max_assign)
    max_assign: int
    epsilon: Optional[float] = None
    nearest_region: Optional[np.ndarray] = None   # int32 (N, max_assign)


@dataclass
class RouteState:
    """How each query was routed.

    `scored_region`/`scored_dist` are the regions the router computed a
    distance to, nearest first. `probed_region` is the regions actually
    searched, in probe order, and `probe_reason` says why each was. Every
    probed region is also a scored one, except under fan-out, where nothing is
    scored because nothing is chosen.
    """

    scored_region: np.ndarray              # int32 (Q, S), -1 padded
    scored_dist: np.ndarray                # float32 (Q, S), NaN padded
    probed_region: np.ndarray              # int32 (Q, P), -1 padded
    probe_reason: np.ndarray               # uint8 (Q, P), ROUTE_PAD padded


@dataclass
class CandidateState:
    """Each query's true neighbours, and every candidate a shard returned.

    `true_ids` is (Q, true_k): the query's exact top-`true_k` neighbour ids,
    nearest first. It is stated for every query whether or not the routing
    reached those neighbours, and that is the whole point of it: without it a
    true neighbour is visible only as a returned candidate, so the neighbours
    a route MISSED -- the ones a routing view exists to show -- have no id in
    the state at all. Task 020 step 4 found that gap; see the module
    docstring.

    Candidates are ragged per query, so flattened: query q's candidates are
    rows `offsets[q]:offsets[q + 1]`. `true_rank` is a candidate's rank in
    `true_ids[q]`, or -1 if it is not in it -- "in the true top-k" for any
    k <= true_k is `0 <= true_rank < k`.
    """

    offsets: np.ndarray                    # int64 (Q + 1,)
    cand_id: np.ndarray                    # int64 (C,)
    cand_shard: np.ndarray                 # int32 (C,)
    cand_score: np.ndarray                 # float32 (C,) inner product
    survived_dedupe: np.ndarray            # bool (C,)
    true_rank: np.ndarray                  # int16 (C,), -1 if not in top-k
    true_ids: np.ndarray                   # int64 (Q, true_k)
    true_k: int


@dataclass
class LoadState:
    """What each shard did under this configuration's query stream."""

    shard_id: np.ndarray                   # int32 (R,)
    vectors_held: np.ndarray               # int64 (R,), counting copies
    queries_served: np.ndarray             # int64 (R,)
    candidates_contributed: np.ndarray     # int64 (R,), before the merge


@dataclass
class ModelState:
    """One configuration's complete state."""

    family: str
    config_label: str
    params: Dict[str, Any]
    seed: int
    n_base: int
    n_queries: int
    dim: int
    partition: PartitionState
    assignment: AssignmentState
    route: RouteState
    candidates: CandidateState
    load: LoadState
    notes: List[str] = field(default_factory=list)
    state_version: int = STATE_VERSION


# --------------------------------------------------------------------------
# helpers the families share
# --------------------------------------------------------------------------

def true_ranks(cand_ids, gt_ids):
    """Rank of each candidate in its query's exact top-k, or -1.

    `cand_ids` is a list of per-query int64 arrays; `gt_ids` is (Q, true_k).
    """
    out = []
    for q, ids in enumerate(cand_ids):
        rank_of = {int(v): r for r, v in enumerate(gt_ids[q].tolist())}
        out.append(np.fromiter((rank_of.get(int(v), -1) for v in ids),
                               dtype=np.int16, count=len(ids)))
    return out


def dedupe_mask(ids, scores):
    """True where a candidate is the first occurrence of its id by score.

    The same rule as `base.merge_candidates`: descending score, first
    occurrence wins, padding (-1) never survives.
    """
    keep = np.zeros(len(ids), dtype=bool)
    seen = set()
    for j in np.argsort(-scores, kind="stable"):
        vid = int(ids[j])
        if vid < 0 or vid in seen:
            continue
        seen.add(vid)
        keep[j] = True
    return keep


def build_candidates(per_query, gt_ids, true_k):
    """CandidateState from `per_query`: a list of (ids, shards, scores)."""
    offsets = np.zeros(len(per_query) + 1, dtype=np.int64)
    ids_l, sh_l, sc_l, dd_l = [], [], [], []
    for q, (ids, shards, scores) in enumerate(per_query):
        ids = np.asarray(ids, dtype=np.int64)
        shards = np.asarray(shards, dtype=np.int32)
        scores = np.asarray(scores, dtype=np.float32)
        real = ids >= 0                       # drop faiss padding outright
        ids, shards, scores = ids[real], shards[real], scores[real]
        ids_l.append(ids)
        sh_l.append(shards)
        sc_l.append(scores)
        dd_l.append(dedupe_mask(ids, scores))
        offsets[q + 1] = offsets[q] + len(ids)
    gt = np.asarray(gt_ids)[:, :true_k]
    ranks = true_ranks(ids_l, gt)
    cat = (lambda parts, dt: np.concatenate(parts).astype(dt)
           if parts else np.zeros(0, dtype=dt))
    return CandidateState(
        offsets=offsets,
        cand_id=cat(ids_l, np.int64),
        cand_shard=cat(sh_l, np.int32),
        cand_score=cat(sc_l, np.float32),
        survived_dedupe=cat(dd_l, bool),
        true_rank=cat(ranks, np.int16),
        true_ids=np.ascontiguousarray(gt, dtype=np.int64),
        true_k=int(true_k))


def collect_candidates(shards, ids_of, queries, probed, depth):
    """Every probed shard's answer for every query, as a sharded search asks.

    The same shards in the same order (`probed[q]`), the same depth, one query
    at a time, and faiss padding mapped through `ids_of` exactly as the
    families' `search()` maps it -- so merging these candidates reproduces
    what `search()` returned. The caller sets efSearch first, as search does.

    Returns `(per_query, padded)`: the list `build_candidates` takes, and how
    many padding slots were mapped, which a family reports in its notes.
    """
    def cat(parts, dt):
        return (np.concatenate(parts).astype(dt) if parts
                else np.zeros(0, dtype=dt))

    per_query, padded = [], 0
    for qi in range(len(queries)):
        ids_l, sh_l, sc_l = [], [], []
        for r in probed[qi]:
            r = int(r)
            if r not in shards:
                continue
            nn = min(int(depth), shards[r].ntotal)
            sc, loc = shards[r].search(queries[qi:qi + 1], nn)
            padded += int((loc[0] < 0).sum())
            ids_l.append(ids_of[r][loc[0]])
            sh_l.append(np.full(len(loc[0]), r, dtype=np.int32))
            sc_l.append(sc[0])
        per_query.append((cat(ids_l, np.int64), cat(sh_l, np.int32),
                          cat(sc_l, np.float32)))
    return per_query, padded


def build_load(region_ids, assignment, route, candidates):
    """LoadState, counted from the other three parts.

    Stated as its own part because it is what a capacity view reads, and
    counted here from the columns rather than separately inside a family, so
    it cannot disagree with them.
    """
    region_ids = np.asarray(region_ids, dtype=np.int32)
    pos = {int(r): i for i, r in enumerate(region_ids.tolist())}
    held = np.zeros(len(region_ids), dtype=np.int64)
    for r in assignment.copy_set[assignment.copy_set >= 0].tolist():
        held[pos[int(r)]] += 1
    served = np.zeros(len(region_ids), dtype=np.int64)
    for row in route.probed_region:
        for r in set(int(v) for v in row if v >= 0):
            served[pos[r]] += 1
    contributed = np.zeros(len(region_ids), dtype=np.int64)
    for r in candidates.cand_shard.tolist():
        contributed[pos[int(r)]] += 1
    return LoadState(shard_id=region_ids, vectors_held=held,
                     queries_served=served,
                     candidates_contributed=contributed)


# --------------------------------------------------------------------------
# the contract
# --------------------------------------------------------------------------

def contract_violations(state, footprint=None):
    """Every way `state` breaks the state contract. Empty means it holds.

    The four the brief names, plus the shape checks that make them
    well-defined:

      * every candidate's shard exists in the partition
      * every probed region was scored (fan-out excepted: it scores nothing)
      * copy counts agree with the footprint's storage amplification
      * candidate ids are a subset of the base ids
    """
    v = []
    p, a, r, c, ld = (state.partition, state.assignment, state.route,
                      state.candidates, state.load)
    n, q = state.n_base, state.n_queries
    regions = set(int(x) for x in p.region_ids.tolist())

    # shapes
    if a.home_region.shape != (n,):
        v.append(f"home_region shape {a.home_region.shape} != ({n},)")
    if a.copy_set.shape != (n, a.max_assign):
        v.append(f"copy_set shape {a.copy_set.shape} != ({n}, {a.max_assign})")
    if c.offsets.shape != (q + 1,) or int(c.offsets[0]) != 0:
        v.append("candidate offsets are not a (Q+1,) array starting at 0")
    elif int(c.offsets[-1]) != len(c.cand_id):
        v.append(f"offsets end at {int(c.offsets[-1])} but there are "
                 f"{len(c.cand_id)} candidates")
    elif np.any(np.diff(c.offsets) < 0):
        v.append("candidate offsets decrease")

    # every candidate's shard exists in the partition
    bad = set(int(x) for x in np.unique(c.cand_shard).tolist()) - regions
    if bad:
        v.append(f"candidates came from shards not in the partition: "
                 f"{sorted(bad)[:10]}")

    # candidate ids are a subset of the base ids
    if len(c.cand_id) and (int(c.cand_id.min()) < 0
                           or int(c.cand_id.max()) >= n):
        v.append(f"candidate ids outside [0, {n}): min "
                 f"{int(c.cand_id.min())}, max {int(c.cand_id.max())}")

    # the true neighbours are stated for every query, and are base ids
    if c.true_ids.shape != (q, c.true_k):
        v.append(f"true_ids shape {c.true_ids.shape} != ({q}, {c.true_k})")
    elif c.true_ids.size and (int(c.true_ids.min()) < 0
                              or int(c.true_ids.max()) >= n):
        v.append(f"true_ids outside [0, {n})")

    # every probed region was scored
    for qi in range(r.probed_region.shape[0]):
        probed = [int(x) for x, why in zip(r.probed_region[qi],
                                           r.probe_reason[qi])
                  if x >= 0 and why != ROUTE_FANOUT]
        scored = set(int(x) for x in r.scored_region[qi] if x >= 0)
        missing = [x for x in probed if x not in scored]
        if missing:
            v.append(f"query {qi}: probed regions {missing} were never scored")
            break

    # home region is in the partition, and is slot 0 of the copy set
    if not set(int(x) for x in np.unique(a.home_region).tolist()) <= regions:
        v.append("a home region is not in the partition")
    if np.any(a.copy_set[:, 0] != a.home_region):
        v.append("copy_set slot 0 is not the home region")

    # every copy is in one of the nearest regions, in the slot it names
    nr = a.nearest_region
    if nr is None:
        v.append("assignment.nearest_region is missing: a recount at another "
                 "epsilon could not say which region a new copy lands in")
    elif nr.shape != a.copy_set.shape:
        v.append(f"nearest_region shape {nr.shape} != copy_set shape "
                 f"{a.copy_set.shape}")
    else:
        if np.any(nr[:, 0] != a.home_region):
            v.append("nearest_region slot 0 is not the home region")
        used = a.copy_set >= 0
        if np.any(a.copy_set[used] != nr[used]):
            v.append("copy_set names a region that nearest_region does not "
                     "hold in that slot")

    # copy counts agree with the footprint's storage amplification
    counted = int((a.copy_set >= 0).sum())
    if int(a.copy_count.astype(np.int64).sum()) != counted:
        v.append(f"copy_count sums to {int(a.copy_count.sum())} but copy_set "
                 f"holds {counted} entries")
    if footprint is not None:
        amp = float(a.copy_count.astype(np.int64).sum()) / max(1, n)
        want = float(getattr(footprint, "amplification", amp))
        if abs(amp - want) > 1e-9:
            v.append(f"copy counts give amplification {amp:.9f}, footprint "
                     f"says {want:.9f}")

    # load is consistent with the parts it is counted from
    if int(ld.vectors_held.sum()) != counted:
        v.append(f"load holds {int(ld.vectors_held.sum())} vectors, the copy "
                 f"sets {counted}")
    if int(ld.candidates_contributed.sum()) != len(c.cand_id):
        v.append(f"load counts {int(ld.candidates_contributed.sum())} "
                 f"candidates, the candidate state {len(c.cand_id)}")
    return v


# --------------------------------------------------------------------------
# encoding
# --------------------------------------------------------------------------

_MEANINGS = {
    "partition.region_ids": "region / shard id",
    "partition.region_sizes": "home population of each region",
    "partition.centroids": "centroid vector (kmeans partitions only)",
    "assignment.home_region": "each base vector's home region",
    "assignment.copy_count": "regions each base vector is stored in",
    "assignment.copy_set": "regions it is stored in, nearest first; -1 unused",
    "assignment.centroid_dist": "non-squared Euclidean distance to its "
                                "nearest max_assign centroids; NaN if none",
    "assignment.nearest_region": "the regions centroid_dist measures, nearest "
                                 "first, whether or not the vector was copied "
                                 "into them; what a recount at another "
                                 "epsilon needs",
    "route.scored_region": "regions the router scored, nearest first",
    "route.scored_dist": "non-squared Euclidean distance to each; NaN pad",
    "route.probed_region": "regions searched, in probe order; -1 pad",
    "route.probe_reason": "why each was probed (ROUTE_*); 255 pad",
    "candidates.offsets": "query q's candidates are rows offsets[q]:"
                          "offsets[q+1]",
    "candidates.cand_id": "base vector id",
    "candidates.cand_shard": "shard the candidate came from",
    "candidates.cand_score": "inner-product score",
    "candidates.survived_dedupe": "first occurrence of this id by score",
    "candidates.true_rank": "rank in the exact top-true_k, -1 if absent",
    "candidates.true_ids": "each query's exact top-true_k neighbour ids, "
                           "nearest first, whether or not the route reached "
                           "them",
    "load.shard_id": "shard id",
    "load.vectors_held": "vectors stored, counting copies",
    "load.queries_served": "queries that probed it",
    "load.candidates_contributed": "candidates it returned before the merge",
}

_PARTS = (("partition", ("region_ids", "region_sizes", "centroids")),
          ("assignment", ("home_region", "copy_count", "copy_set",
                          "centroid_dist", "nearest_region")),
          ("route", ("scored_region", "scored_dist", "probed_region",
                     "probe_reason")),
          ("candidates", ("offsets", "cand_id", "cand_shard", "cand_score",
                          "survived_dedupe", "true_rank", "true_ids")),
          ("load", ("shard_id", "vectors_held", "queries_served",
                    "candidates_contributed")))


def _arrays(state):
    out = {}
    for part, names in _PARTS:
        obj = getattr(state, part)
        for n in names:
            arr = getattr(obj, n)
            if arr is not None:
                out[f"{part}.{n}"] = np.ascontiguousarray(arr)
    return out


def header(state):
    """The JSON half of the encoding: identity, scalars, and the column map."""
    arrays = _arrays(state)
    p, a, c = state.partition, state.assignment, state.candidates
    return {
        "state_version": state.state_version,
        "family": state.family,
        "config_label": state.config_label,
        "params": state.params,
        "seed": int(state.seed),
        "n_base": int(state.n_base),
        "n_queries": int(state.n_queries),
        "dim": int(state.dim),
        "partition": {"kind": p.kind, "seed": int(p.seed),
                      "params": p.params, "distance": p.distance,
                      "kmeans_niter": p.kmeans_niter,
                      "n_regions": int(len(p.region_ids))},
        "assignment": {"max_assign": int(a.max_assign),
                       "epsilon": a.epsilon},
        "candidates": {"true_k": int(c.true_k)},
        "route_reasons": {str(k): v for k, v in ROUTE_REASONS.items()},
        "distance_convention": DISTANCE,
        "columns": {name: {"dtype": str(arr.dtype), "shape": list(arr.shape),
                           "meaning": _MEANINGS.get(name, "")}
                    for name, arr in sorted(arrays.items())},
        "notes": list(state.notes),
    }


def state_filename(family, config_label):
    """`<family>__<first 8 hex of sha256(label)>.state.npz`.

    A digest rather than the label, because labels carry `[`, `]`, `=` and
    `,`, and a filename that has to survive every filesystem should not.
    The label is in the header, so nothing is lost.
    """
    tag = hashlib.sha256(config_label.encode("utf-8")).hexdigest()[:8]
    return f"{family}__{tag}.state.npz"


def write_state(path, state):
    """Write deterministically: sorted entries, fixed timestamps, stored."""
    arrays = _arrays(state)
    head = json.dumps(header(state), indent=2, sort_keys=True,
                      ensure_ascii=True).encode("utf-8") + b"\n"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        entries = [("header.json", head)]
        for name, arr in sorted(arrays.items()):
            buf = io.BytesIO()
            np.lib.format.write_array(buf, arr, allow_pickle=False)
            entries.append((name + ".npy", buf.getvalue()))
        for name, data in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    return path


def read_state(path):
    """(header dict, {column name: array}). The renderer's only input."""
    with zipfile.ZipFile(path, "r") as z:
        head = json.loads(z.read("header.json").decode("utf-8"))
        if head.get("state_version") != STATE_VERSION:
            raise ValueError(
                f"{path}: state_version {head.get('state_version')}, this "
                f"reader understands {STATE_VERSION}")
        cols = {}
        for info in z.infolist():
            if info.filename.endswith(".npy"):
                cols[info.filename[:-4]] = np.lib.format.read_array(
                    io.BytesIO(z.read(info.filename)), allow_pickle=False)
    return head, cols
