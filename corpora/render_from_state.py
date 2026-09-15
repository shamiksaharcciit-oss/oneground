#!/usr/bin/env python3
"""The teaser's two figures, drawn from simulator state through the lab's
rendering contract. Task 020 step 4, reshaped into views by task 021.

This is the acceptance test for the simulator state, not a demo. It is given a
`state/` directory written by `oneground simulate --emit-state`, and nothing
else:

    no base.bin, no export script, no fixture parquet, no vectors,
    no ground-truth file, and no import of any model family

It adds nothing of its own. It composes two views over `oneground/lab`,
`ground` and `query_trace`, and every number it prints is a figure one of them
drew from state. Before drawing anything it runs the contract's guard over
every view module, and it refuses to draw if one of them measures.

A figure the state cannot support is a `couldnt_check` gap. A gap is reported,
never filled, and the script exits non-zero.

The two figures:

    ground         every base vector's copy count at the configuration's
                   epsilon, and the counters: copies histogram, vectors copied,
                   storage amplification, p99 copies, boundary crispness
    query_trace    one query's routed region, the regions probed and why, its
                   true neighbours, and how many lie outside the routed region
                   -- drawn for the named query and for every query

The JSON it writes keeps the shape task 020 gave it (`ground`, `query`,
`every_query`), so the acceptance comparison reads it unchanged. It adds
`drawings`, each view's provenance: the columns it read and what moving epsilon
asks of it.

What it deliberately does not draw: the teaser places points with a UMAP
projection that the fixture spec declares illustrative. That projection is not
simulator state, so no position is drawn and nothing here claims a pixel match.

    python corpora/render_from_state.py runs/020-ref-arxiv/state \\
        --family semantic_sharded --query 15 --out runs/020-ref-arxiv/render.json
"""

import argparse
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from oneground.lab import contract, guard                    # noqa: E402
from oneground.lab.views import GroundView, QueryTraceView    # noqa: E402

COULDNT_CHECK = contract.COULDNT_CHECK

# The teaser's recall depth for "true neighbours".
K_TRUE = 10


def find_state(state_dir, family):
    """The one state file for `family` in `state_dir`.

    Resolved through `state_info.json` when it is present, and through the
    headers otherwise. More than one configuration of the family is refused
    rather than picked from: the two figures are about one configuration.
    """
    info_p = os.path.join(state_dir, "state_info.json")
    paths = []
    if os.path.exists(info_p):
        with open(info_p, encoding="utf-8") as f:
            info = json.load(f)
        for entry in info.get("configurations", []):
            if entry.get("family") == family and entry.get("file"):
                paths.append(os.path.join(state_dir, entry["file"]))
    else:
        for p in sorted(glob.glob(os.path.join(state_dir, "*.state.npz"))):
            head, _ = contract.load_state(p)
            if head["family"] == family:
                paths.append(p)
    if not paths:
        raise SystemExit(f"no {family} state in {state_dir}")
    if len(paths) > 1:
        raise SystemExit(f"{len(paths)} {family} configurations in "
                         f"{state_dir}; pass --file to name one")
    return paths[0]


def _figures_and_gaps(drawing):
    out = dict(drawing.figures)
    out.update(drawing.gaps)
    return out


def draw_ground(head, cols):
    d = contract.draw(GroundView(), head, cols)
    return d, contract._jsonable(_figures_and_gaps(d))


def draw_query(head, cols, q, k=K_TRUE):
    d = contract.draw(QueryTraceView(q, k), head, cols)
    out = _figures_and_gaps(d)
    region, link, point = d.marks
    out["probed"] = [{"region": r, "reason": why} for r, why in
                     zip(link.data["region"], link.data["reason"])]
    out["scored"] = [{"region": r, "distance": x} for r, x in
                     zip(region.data["region"], region.data["distance"])]
    out["true_neighbours"] = [
        {"rank": rank, "id": vid, "home_region": home,
         "outside_routed_region": outside, "missed_by_route": missed}
        for rank, vid, home, outside, missed in zip(
            point.data["rank"], point.data["vector_id"],
            point.data["home_region"], point.data["outside_routed_region"],
            point.data["missed_by_route"])]
    return d, contract._jsonable(out)


def draw_every_query(head, cols, k=K_TRUE):
    """The query trace, drawn once per query, and the column of figures the
    acceptance comparison checks against all 2,000 published ones."""
    n_q = int(head["n_queries"])
    routed, outside, located, from_candidates = [], [], 0, 0
    for q in range(n_q):
        d = contract.draw(QueryTraceView(q, k), head, cols)
        routed.append(d.figures["routed_region"])
        count = d.figures.get("outside_routed_region")
        outside.append(count)
        located += count is not None
        from_candidates += bool(d.figures["answerable_from_candidates_alone"])
    return {
        "routed_region": routed,
        "outside_routed_region": outside,
        "queries_fully_located": located,
        "queries_not_fully_located": n_q - located,
        "true_ids_in_state": "candidates.true_ids" in cols,
        "answerable_from_candidates_alone": from_candidates,
        "note": ("answerable_from_candidates_alone is how many queries the "
                 "state as first specified in task 020 could have answered: "
                 "without candidates.true_ids, a true neighbour is visible "
                 "only if a probed shard returned it"),
    }


def _provenance(d):
    return {"reads": d.reads, "on_epsilon": d.epsilon, "params": d.params,
            "source": d.source}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("state_dir")
    ap.add_argument("--family", default="semantic_sharded")
    ap.add_argument("--file", help="a specific .state.npz, if the directory "
                                   "holds several of the family")
    ap.add_argument("--query", type=int, default=15)
    ap.add_argument("--out", help="write the rendering as JSON here")
    ap.add_argument("--drawings", help="also write each view's full drawing "
                                       "(marks included) into this directory")
    args = ap.parse_args()

    broken = guard.check_views()
    if broken:
        print("REFUSED: view modules break the rendering contract:",
              file=sys.stderr)
        for module, found in sorted(broken.items()):
            for line, rule, detail in found:
                print(f"    {module}:{line}  {rule}  {detail}",
                      file=sys.stderr)
        return 2

    path = args.file or find_state(args.state_dir, args.family)
    head, cols = contract.load_state(path)
    print(f"state   {os.path.basename(path)}")
    print(f"config  {head['config_label']}   n_base {head['n_base']:,}   "
          f"n_queries {head['n_queries']:,}")

    ground_d, ground = draw_ground(head, cols)
    query_d, trace = draw_query(head, cols, args.query)
    every = draw_every_query(head, cols)

    print("\n-- the ground (view: ground) --")
    print(f"  epsilon {ground['epsilon']}   cap {ground['max_assign']}")
    print("  copies histogram " + "  ".join(
        f"{c}:{n:,} ({p}%)" for c, (n, p) in enumerate(
            zip(ground["copies_histogram"], ground["copies_histogram_pct"]),
            1)))
    print(f"  vectors copied    {ground['vectors_copied']:,}")
    print(f"  storage           {ground['storage_amplification']:.6f}x")
    print(f"  p99 copies        {ground['p99_copies']}")
    print(f"  crispness         {ground['boundary_crispness']}")
    print(f"  moving epsilon    {ground_d.epsilon}")

    print(f"\n-- query {args.query} (view: query_trace) --")
    print(f"  routed region {trace['routed_region']}   probed "
          f"{trace['probed_regions']}")
    print(f"  true neighbours {trace['true_neighbours_located']} of {K_TRUE}; "
          f"missed by the route {trace['missed_by_route']}")
    print(f"  outside routed region   {trace['outside_routed_region']}")
    print(f"  moving epsilon    {query_d.epsilon}")

    print("\n-- every query (view: query_trace, once per query) --")
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
                       "every_query": every,
                       "drawings": {"ground": _provenance(ground_d),
                                    "query_trace": _provenance(query_d)}},
                      f, indent=1)
        print(f"\nwritten {args.out}")
    if args.drawings:
        os.makedirs(args.drawings, exist_ok=True)
        for d in (ground_d, query_d):
            p = os.path.join(args.drawings, f"{d.view}.drawing.json")
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                json.dump(d.as_dict(), f)
            print(f"written {p} ({os.path.getsize(p):,} bytes)")

    gaps = []
    if "boundary_crispness" in ground_d.gaps:
        gaps.append("boundary_crispness")
    if "outside_routed_region" in query_d.gaps:
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
