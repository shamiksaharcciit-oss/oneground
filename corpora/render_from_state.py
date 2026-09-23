#!/usr/bin/env python3
"""The teaser's two figures, drawn from simulator state through the lab's
rendering contract. Task 020 step 4, reshaped into views by task 021; the
epsilon control's declared set added by task 021b; the ground's live recount
by task 023. Its run reader moved into `oneground/lab/runs.py` in task 024, so
this script and `oneground lab` read a run the same way.

This is the acceptance test for the simulator state, not a demo. It is given
`state/` directories written by `oneground simulate --emit-state`, and nothing
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

    ground         every base vector's copy count, recounted at the epsilon
                   asked for, and the counters: copies histogram, vectors
                   copied, storage amplification, p99 copies, boundary
                   crispness, routing ceiling@10
    query_trace    one query's routed region, the regions probed and why, its
                   true neighbours, how many lie outside the routed region, and
                   its recall panel -- drawn for the named query and for every
                   query

Epsilon. `--epsilon` is where the lab's control stands. The `state_dir` and
every `--simulated` directory together declare the epsilons this configuration
was simulated at, and both views are drawn with that one set. The ground
recounts at the epsilon asked for. The query trace is drawn from the state
simulated there when there is one; otherwise its recall panel says
`not simulated at this epsilon`, with the measured cost in minutes and the
command that would simulate it.

The JSON keeps the shape task 020 gave it (`ground`, `query`, `every_query`),
so the acceptance comparison reads it unchanged, and adds `epsilon` and
`drawings` (each view's provenance).

What it deliberately does not draw: the teaser places points with a UMAP
projection the fixture spec declares illustrative. That projection is not
simulator state, so no position is drawn and nothing here claims a pixel match.

    python corpora/render_from_state.py runs/020-ref-arxiv/state \\
        --family semantic_sharded --query 15 --out runs/020-ref-arxiv/render.json
    python corpora/render_from_state.py runs/020-ref-arxiv/state \\
        --simulated runs/021-eps-arxiv/state --epsilon 0.15 --query 15
"""

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from oneground.lab import contract, guard                    # noqa: E402
from oneground.lab.runs import (declared_set, find_state,     # noqa: E402
                                plan, states_in)
from oneground.lab.views import GroundView, QueryTraceView    # noqa: E402
from oneground.receipts import public_path                    # noqa: E402

__all__ = ["declared_set", "find_state", "plan", "states_in", "draw_ground",
           "draw_query", "draw_every_query", "main"]

COULDNT_CHECK = contract.COULDNT_CHECK

# The teaser's recall depth for "true neighbours".
K_TRUE = 10


def _figures_and_gaps(drawing):
    out = dict(drawing.figures)
    out.update(drawing.gaps)
    return out


def draw_ground(p, k=K_TRUE):
    """The ground, recounted from the base state at the epsilon asked for.

    Always the base state: the closure at any epsilon follows from the stored
    distances and nearest regions, so the ground does not need the state that
    was simulated at this epsilon -- and there may not be one.
    """
    head, cols = p["base"]
    d = contract.draw(GroundView(p["eps"], k=k), head, cols)
    out = contract._jsonable(_figures_and_gaps(d))
    out["caption"] = d.caption
    return d, out


def _trace_view(p, q, k):
    # the same EpsilonSet the ground is drawn with: one source, not two
    return QueryTraceView(q, k, eps=p["eps"])


def draw_query(p, q, k=K_TRUE):
    head, cols = p["trace"]
    d = contract.draw(_trace_view(p, q, k), head, cols)
    out = _figures_and_gaps(d)
    panel = d.panels["recall"]
    region, link, point = d.marks
    out["probed"] = [{"region": r, "reason": why} for r, why in
                     zip(link.data["region"], link.data["reason"])]
    out["scored"] = [{"region": r, "distance": x} for r, x in
                     zip(region.data["region"], region.data["distance"])]
    neighbours = [
        {"rank": rank, "id": vid, "home_region": home,
         "outside_routed_region": outside}
        for rank, vid, home, outside in zip(
            point.data["rank"], point.data["vector_id"],
            point.data["home_region"], point.data["outside_routed_region"])]
    if panel["status"] == contract.SIMULATED:
        f = panel["figures"]
        for entry, missed in zip(neighbours, f["missed_by_route_by_rank"]):
            entry["missed_by_route"] = missed
        out["missed_by_route"] = f["missed_by_route"]
        out["answerable_from_candidates_alone"] = \
            f["answerable_from_candidates_alone"]
        out["recall_at_k"] = f["recall_at_k"]
    out["true_neighbours"] = neighbours
    out["recall_panel"] = panel
    return d, contract._jsonable(out)


def draw_every_query(p, k=K_TRUE):
    """The query trace, drawn once per query: the column of figures the
    acceptance comparison checks against all 2,000 published ones, and, at a
    simulated epsilon, recall over every query."""
    head, cols = p["trace"]
    n_q = int(head["n_queries"])
    routed, outside, located = [], [], 0
    from_candidates, hits, status = 0, 0, None
    for q in range(n_q):
        d = contract.draw(_trace_view(p, q, k), head, cols)
        routed.append(d.figures["routed_region"])
        count = d.figures.get("outside_routed_region")
        outside.append(count)
        located += count is not None
        panel = d.panels["recall"]
        status = panel["status"]
        if status == contract.SIMULATED:
            f = panel["figures"]
            from_candidates += bool(f["answerable_from_candidates_alone"])
            hits += f["hits"]
    out = {
        "routed_region": routed,
        "outside_routed_region": outside,
        "queries_fully_located": located,
        "queries_not_fully_located": n_q - located,
        "true_ids_in_state": "candidates.true_ids" in cols,
        "recall_panel_status": status,
    }
    if status == contract.SIMULATED:
        out["answerable_from_candidates_alone"] = from_candidates
        out["recall_at_k_mean"] = hits / (n_q * k)
        out["note"] = ("answerable_from_candidates_alone is how many queries "
                       "the state as first specified in task 020 could have "
                       "answered: without candidates.true_ids, a true "
                       "neighbour is visible only if a probed shard returned "
                       "it")
    return out


def _provenance(d):
    return {"reads": d.reads, "on_epsilon": d.epsilon, "params": d.params,
            "source": d.source,
            "panels": {name: panel["status"]
                       for name, panel in d.panels.items()}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("state_dir")
    ap.add_argument("--family", default="semantic_sharded")
    ap.add_argument("--file", help="a specific .state.npz, if the directory "
                                   "holds several of the family")
    ap.add_argument("--simulated", action="append", default=[],
                    help="another state/ directory of the same configuration "
                         "at other epsilons; repeatable")
    ap.add_argument("--epsilon", type=float,
                    help="where the lab's epsilon control stands (default: "
                         "the base state's own)")
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

    base_path = args.file or find_state(args.state_dir, args.family)
    p = plan(base_path, args.simulated, args.family, args.epsilon)
    head, cols = p["base"]
    print(f"state   {os.path.basename(base_path)}")
    print(f"config  {head['config_label']}   n_base {head['n_base']:,}   "
          f"n_queries {head['n_queries']:,}")
    if p["epsilon"] is not None:
        print(f"epsilon {p['epsilon']}   simulated at {p['simulated']}   "
              f"query trace drawn from "
              f"{os.path.relpath(p['trace_path'], os.getcwd())}")

    ground_d, ground = draw_ground(p)
    query_d, trace = draw_query(p, args.query)
    every = draw_every_query(p)

    print("\n-- the ground (view: ground) --")
    print(f"  epsilon {ground['epsilon']}   cap {ground['max_assign']}   "
          f"recounted from state {ground['recounted_from_state']}")
    print("  copies histogram " + "  ".join(
        f"{c}:{n:,} ({pct}%)" for c, (n, pct) in enumerate(
            zip(ground["copies_histogram"], ground["copies_histogram_pct"]),
            1)))
    print(f"  vectors copied    {ground['vectors_copied']:,}")
    print(f"  storage           {ground['storage_amplification']:.6f}x")
    print(f"  p99 copies        {ground['p99_copies']}")
    print(f"  crispness         {ground['boundary_crispness']}")
    print(f"  ceiling@{ground.get('k', K_TRUE)}         "
          f"{ground.get('routing_ceiling_at_k')}")
    print(f"  moving epsilon    {ground_d.epsilon}")
    print(f"  caption           {ground['caption']}")

    panel = trace["recall_panel"]
    print(f"\n-- query {args.query} (view: query_trace) --")
    print(f"  routed region {trace['routed_region']}   probed "
          f"{trace['probed_regions']}")
    print(f"  true neighbours {trace['true_neighbours_located']} of "
          f"{K_TRUE}; outside routed region "
          f"{trace.get('outside_routed_region')}")
    if panel["status"] == contract.SIMULATED:
        f = panel["figures"]
        print(f"  recall panel      simulated at epsilon {panel['epsilon']}: "
              f"recall@{f['k']} {f['recall_at_k']:.2f}, missed by the route "
              f"{f['missed_by_route']}")
    else:
        cost = panel["cost_minutes"]
        cost_text = (f"{cost['low']}-{cost['high']} min" if
                     isinstance(cost, dict) else cost)
        print(f"  recall panel      {panel['status']} {panel['epsilon']} "
              f"(simulated: {panel['simulated_epsilons']}); "
              f"cost {cost_text}")
        print(f"                    run: {panel['action']['command']}  "
              f"with epsilon {panel['action']['epsilon']}")

    print("\n-- every query (view: query_trace, once per query) --")
    print(f"  fully located {every['queries_fully_located']:,} of "
          f"{head['n_queries']:,}")
    if every["recall_panel_status"] == contract.SIMULATED:
        print(f"  answerable from candidates alone (the state as first "
              f"specified): {every['answerable_from_candidates_alone']:,} of "
              f"{head['n_queries']:,}")
        print(f"  recall@{K_TRUE}, every query     "
              f"{every['recall_at_k_mean']:.6f}")
    else:
        print(f"  recall            {every['recall_panel_status']}")

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            # public_path, not os.path.basename: a basename is half of it
            # written by hand, and the half it drops is which file inside the
            # checkout this was. Found by `receipts.pathguard` (task 044f) --
            # `query_trace_state` below is the instance the guard's key-name
            # detector could not see and its provenance detector could.
            json.dump({"state_file": public_path(base_path),
                       "config_label": head["config_label"],
                       "epsilon": {"requested": p["epsilon"],
                                   "simulated": p["simulated"],
                                   "query_trace_state": public_path(
                                       p["trace_path"])},
                       "ground": ground, "query": trace,
                       "every_query": every,
                       "drawings": {"ground": _provenance(ground_d),
                                    "query_trace": _provenance(query_d)}},
                      f, indent=1)
        print(f"\nwritten {args.out}")
    if args.drawings:
        os.makedirs(args.drawings, exist_ok=True)
        for d in (ground_d, query_d):
            path = os.path.join(args.drawings, f"{d.view}.drawing.json")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(d.as_dict(), f)
            print(f"written {path} ({os.path.getsize(path):,} bytes)")

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
