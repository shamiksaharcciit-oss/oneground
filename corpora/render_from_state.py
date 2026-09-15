#!/usr/bin/env python3
"""The teaser's two views, rendered from simulator state alone. Task 020 step 4.

This is the acceptance test for `oneground/models/state.py`, not a demo. The
teaser draws the ground and a query's trace from a parquet baked by a one-off
export script, with the geometry recomputed in the browser. The lab must draw
the same things as a *rendering of state*. So this script is given a `state/`
directory written by `oneground simulate --emit-state`, and nothing else:

    no base.bin, no export script, no fixture parquet, no vectors,
    no ground-truth file, and no import of any model family

It reads the state through `oneground/models/state.py`, imported by file path
so that not one line of a family's code is loaded. If a figure cannot be
derived from what the state holds, this script does not go and get it: it
says `couldnt_check`, names what was missing, and exits non-zero. A gap found
that way is a defect in the state, which is the finding step 4 exists to make.

The two views
-------------
the ground     every base vector's copy count at the configuration's epsilon,
               and the counters: vectors copied, storage amplification, p99
               copies, the copies histogram, and boundary crispness

one query      its routed region, the regions probed and why, its true
               neighbours, and how many of them lie outside the routed region

What step 4 found missing, and how this script still measures it
----------------------------------------------------------------
The five parts as first specified named a true neighbour only as a *returned
candidate*. A neighbour no probed shard returned had no id in the state, so a
query that lost one had no answerable "outside the routed region" count --
and those are the queries a routing view exists to show. `state.py` now
carries `candidates.true_ids`. This script uses it, and ALSO reports how many
queries the candidates alone could have answered, so the size of the gap is
measured on every run rather than asserted once.

What this deliberately does not reproduce
-----------------------------------------
The teaser places points in 2-D with a UMAP projection. The fixture spec
declares that projection illustrative -- it is not a measurement, and the
simulator does not produce one -- so it is not simulator state and it is not
here. The ground is rendered as per-point copy counts without positions, and
nothing below claims a pixel match with the teaser.

    python corpora/render_from_state.py runs/020-ref-arxiv/state \\
        --family semantic_sharded --query 15 --out runs/020-ref-arxiv/render.json
"""

import argparse
import glob
import importlib.util
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The state format, by file path: the renderer depends on the encoding and on
# nothing a model family implements.
_spec = importlib.util.spec_from_file_location(
    "oneground_state", os.path.join(REPO, "oneground", "models", "state.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

COULDNT_CHECK = "couldnt_check"

# A *definition*, not data: the fixture spec's boundary_crispness is the
# fraction of vectors whose second-nearest centroid is more than 1.20x as far
# as the nearest. The distances it is taken over are state; the threshold is
# the published definition of the number being reproduced.
CRISP_RATIO = 1.20

# The teaser's recall depth for "true neighbours".
K_TRUE = 10


def find_state(state_dir, family):
    """The one state file for `family` in `state_dir`.

    Resolved through `state_info.json` when it is present, by the headers
    otherwise. More than one configuration of the family is refused rather
    than picked from, because the two views are about one configuration.
    """
    info_p = os.path.join(state_dir, "state_info.json")
    paths = []
    if os.path.exists(info_p):
        info = json.load(open(info_p, encoding="utf-8"))
        for entry in info.get("configurations", []):
            if entry.get("family") == family:
                paths.append(os.path.join(state_dir, entry["file"]))
    else:
        for p in sorted(glob.glob(os.path.join(state_dir, "*.state.npz"))):
            head, _ = S.read_state(p)
            if head["family"] == family:
                paths.append(p)
    if not paths:
        raise SystemExit(f"no {family} state in {state_dir}")
    if len(paths) > 1:
        raise SystemExit(f"{len(paths)} {family} configurations in "
                         f"{state_dir}; pass --file to name one")
    return paths[0]


def render_ground(head, cols):
    """The ground view: copy counts and the counters, from AssignmentState."""
    n = int(head["n_base"])
    ma = int(head["assignment"]["max_assign"])
    copies = cols["assignment.copy_count"].astype(np.int64)
    out = {
        "n_base": n,
        "epsilon": head["assignment"]["epsilon"],
        "max_assign": ma,
        "copy_count_per_point": "assignment.copy_count (one per base vector)",
        "copies_histogram": [int((copies == c).sum()) for c in range(1, ma + 1)],
        "vectors_copied": int((copies > 1).sum()),
        "storage_amplification": float(copies.sum() / n),
        # method="lower", as the teaser counts it: p99 of an integer copy
        # count is a copy count, not an interpolation between two.
        "p99_copies": int(np.percentile(copies, 99, method="lower")),
        "positions": (f"{COULDNT_CHECK}: not simulator state -- the teaser's "
                      "2-D placement is a UMAP projection the fixture spec "
                      "declares illustrative, so it is not in the state and "
                      "no position is rendered"),
    }
    out["copies_histogram_pct"] = [round(100.0 * c / n, 1)
                                   for c in out["copies_histogram"]]

    part = head["partition"]
    dist = cols["assignment.centroid_dist"]
    if part["kind"] != "kmeans":
        out["boundary_crispness"] = (
            f"{COULDNT_CHECK}: a {part['kind']} partition has no centroids, "
            "so there is no second-nearest centroid distance to take a ratio "
            "of")
    elif dist.shape[1] < 2 or np.isnan(dist[:, :2]).any():
        out["boundary_crispness"] = (
            f"{COULDNT_CHECK}: the state holds fewer than two centroid "
            "distances per vector")
    elif head.get("distance_convention") != S.DISTANCE:
        out["boundary_crispness"] = (
            f"{COULDNT_CHECK}: the state's distances are "
            f"{head.get('distance_convention')!r}, and the 1.20 definition is "
            "a ratio of non-squared distances")
    else:
        out["boundary_crispness"] = float(
            np.mean(dist[:, 1] > CRISP_RATIO * dist[:, 0]))
    return out


def _query_rows(cols, q):
    lo = int(cols["candidates.offsets"][q])
    hi = int(cols["candidates.offsets"][q + 1])
    return slice(lo, hi)


def true_neighbours_from_candidates(cols, q, k=K_TRUE):
    """{rank: id} for query q's true top-k, from returned candidates ONLY.

    This is all the five parts as first specified could say. A neighbour that
    no probed shard returned is not a candidate, so its id is absent and its
    rank is missing from the result. Kept so every run measures how much of
    the answer the candidates alone carry.
    """
    rows = _query_rows(cols, q)
    ids = cols["candidates.cand_id"][rows]
    ranks = cols["candidates.true_rank"][rows]
    found = {}
    for vid, r in zip(ids.tolist(), ranks.tolist()):
        if 0 <= r < k and r not in found:
            found[int(r)] = int(vid)
    return found


def true_neighbours(cols, q, k=K_TRUE):
    """{rank: id} for query q's true top-k.

    From `candidates.true_ids`, which states every query's true neighbours
    whether or not the route reached them. A state written before step 4 has
    no such column, and then this falls back to the candidates -- and the
    caller reports the resulting gap rather than filling it.
    """
    if "candidates.true_ids" in cols:
        row = cols["candidates.true_ids"][q][:k]
        return {r: int(v) for r, v in enumerate(row.tolist()) if v >= 0}
    return true_neighbours_from_candidates(cols, q, k)


def render_query(head, cols, q, k=K_TRUE):
    """One query's trace, from RouteState, CandidateState and AssignmentState."""
    if not 0 <= q < int(head["n_queries"]):
        raise SystemExit(f"query {q} is not in [0, {head['n_queries']})")
    probed = cols["route.probed_region"][q]
    reasons = cols["route.probe_reason"][q]
    scored = cols["route.scored_region"][q]
    sdist = cols["route.scored_dist"][q]
    home = cols["assignment.home_region"]

    routed = int(probed[0])
    probed_set = set(int(r) for r in probed if r >= 0)
    rows = _query_rows(cols, q)
    returned = set(int(v) for v in cols["candidates.cand_id"][rows].tolist())
    trace = {
        "query": q,
        "routed_region": routed,
        "probed": [{"region": int(r),
                    "reason": head["route_reasons"][str(int(w))]}
                   for r, w in zip(probed, reasons) if r >= 0],
        "scored": [{"region": int(r), "distance": float(d)}
                   for r, d in zip(scored, sdist) if r >= 0],
    }

    found = true_neighbours(cols, q, k)
    located = []
    for rank in sorted(found):
        vid = found[rank]
        h = int(home[vid])
        located.append({
            "rank": rank, "id": vid, "home_region": h,
            "outside_routed_region": h != routed,
            # "the route missed it": no probed shard returned it, which for a
            # replicating family is not the same as its home being unprobed.
            "missed_by_route": vid not in returned,
        })
    trace["true_neighbours"] = located
    trace["true_neighbours_unlocated_ranks"] = [r for r in range(k)
                                                if r not in found]
    outside_seen = sum(1 for x in located if x["outside_routed_region"])
    trace["missed_by_route"] = sum(1 for x in located if x["missed_by_route"])

    if len(found) == k:
        trace["outside_routed_region"] = outside_seen
    else:
        missing = k - len(found)
        trace["outside_routed_region"] = (
            f"{COULDNT_CHECK}: {missing} of this query's {k} true neighbours "
            "are not in the state. It names a true neighbour only as a "
            "candidate some probed shard returned (candidates.true_rank), so "
            "a neighbour no probed shard returned has no id here and its home "
            f"region cannot be looked up. At least {outside_seen} are outside "
            f"the routed region; the other {missing} cannot be placed")
        trace["outside_routed_region_lower_bound"] = outside_seen
    return trace


def render_all_queries(head, cols, k=K_TRUE):
    """Routed region and `outside_routed_region` for every query, and the size
    of the gap the state had before `candidates.true_ids`."""
    n_q = int(head["n_queries"])
    counts, routed, unlocated, cand_only = [], [], 0, 0
    for q in range(n_q):
        trace = render_query(head, cols, q, k)
        routed.append(trace["routed_region"])
        v = trace["outside_routed_region"]
        if isinstance(v, int):
            counts.append(v)
        else:
            counts.append(None)
            unlocated += 1
        if len(true_neighbours_from_candidates(cols, q, k)) == k:
            cand_only += 1
    return {
        "routed_region": routed,
        "outside_routed_region": counts,
        "queries_fully_located": n_q - unlocated,
        "queries_not_fully_located": unlocated,
        "true_ids_in_state": "candidates.true_ids" in cols,
        "answerable_from_candidates_alone": cand_only,
        "note": ("answerable_from_candidates_alone is how many queries the "
                 "five parts as first specified could have answered: without "
                 "candidates.true_ids, a true neighbour is visible only if a "
                 "probed shard returned it"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("state_dir")
    ap.add_argument("--family", default="semantic_sharded")
    ap.add_argument("--file", help="a specific .state.npz, if the directory "
                                   "holds several of the family")
    ap.add_argument("--query", type=int, default=15)
    ap.add_argument("--out", help="write the rendering as JSON here")
    args = ap.parse_args()

    path = args.file or find_state(args.state_dir, args.family)
    head, cols = S.read_state(path)
    print(f"state   {os.path.basename(path)}")
    print(f"config  {head['config_label']}   n_base {head['n_base']:,}   "
          f"n_queries {head['n_queries']:,}")

    ground = render_ground(head, cols)
    trace = render_query(head, cols, args.query)
    every = render_all_queries(head, cols)

    print("\n-- the ground --")
    print(f"  epsilon {ground['epsilon']}   cap {ground['max_assign']}")
    print("  copies histogram " + "  ".join(
        f"{c}:{n:,} ({p}%)" for c, (n, p) in enumerate(
            zip(ground["copies_histogram"], ground["copies_histogram_pct"]), 1)))
    print(f"  vectors copied    {ground['vectors_copied']:,}")
    print(f"  storage           {ground['storage_amplification']:.6f}x")
    print(f"  p99 copies        {ground['p99_copies']}")
    print(f"  crispness         {ground['boundary_crispness']}")

    print(f"\n-- query {args.query} --")
    print(f"  routed region {trace['routed_region']}   probed "
          f"{[p['region'] for p in trace['probed']]}")
    print(f"  true neighbours {len(trace['true_neighbours'])} of {K_TRUE}; "
          f"missed by the route {trace['missed_by_route']}")
    print(f"  outside routed region   {trace['outside_routed_region']}")

    print("\n-- every query --")
    print(f"  fully located {every['queries_fully_located']:,} of "
          f"{head['n_queries']:,}")
    print(f"  answerable from candidates alone (the state as first "
          f"specified): {every['answerable_from_candidates_alone']:,} of "
          f"{head['n_queries']:,}")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"state_file": os.path.basename(path),
                       "config_label": head["config_label"],
                       "ground": ground, "query": trace,
                       "every_query": every}, f, indent=1)
        print(f"\nwritten {args.out}")

    gaps = []
    if not isinstance(ground["boundary_crispness"], float):
        gaps.append("boundary_crispness")
    if not isinstance(trace["outside_routed_region"], int):
        gaps.append(f"query {args.query} outside_routed_region")
    if every["queries_not_fully_located"]:
        gaps.append(f"{every['queries_not_fully_located']} queries' outside "
                    "counts")
    if gaps:
        print("\nSTATE INSUFFICIENT for: " + "; ".join(gaps), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
