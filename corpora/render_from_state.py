#!/usr/bin/env python3
"""The teaser's two figures, drawn from simulator state through the lab's
rendering contract. Task 020 step 4, reshaped into views by task 021; the
epsilon control's declared set added by task 021b.

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

    ground         every base vector's copy count at the configuration's
                   epsilon, and the counters: copies histogram, vectors copied,
                   storage amplification, p99 copies, boundary crispness
    query_trace    one query's routed region, the regions probed and why, its
                   true neighbours, how many lie outside the routed region, and
                   its recall panel -- drawn for the named query and for every
                   query

Epsilon (task 021b). `--epsilon` is where the lab's control stands. The
`state_dir` and every `--simulated` directory together declare the epsilons
this configuration was simulated at. The query trace is drawn from the state
simulated at the epsilon asked for, when there is one. Otherwise it is drawn
from the base state, geometric readouts only, and its recall panel says
`not simulated at this epsilon`, with the measured cost of simulating one in
minutes and the command that would. It is never interpolated and never blank.

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
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from oneground.lab import contract, guard                    # noqa: E402
from oneground.lab.views import GroundView, QueryTraceView    # noqa: E402

COULDNT_CHECK = contract.COULDNT_CHECK

# The teaser's recall depth for "true neighbours".
K_TRUE = 10


def states_in(state_dir, family):
    """Every state file of `family` in `state_dir`: through `state_info.json`
    when it is present, and through the headers otherwise."""
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
    return paths


def find_state(state_dir, family):
    """The one state file for `family` in `state_dir`. More than one
    configuration of the family is refused rather than picked from."""
    paths = states_in(state_dir, family)
    if not paths:
        raise SystemExit(f"no {family} state in {state_dir}")
    if len(paths) > 1:
        raise SystemExit(f"{len(paths)} {family} configurations in "
                         f"{state_dir}; pass --file to name one")
    return paths[0]


def _configuration(head):
    """A configuration's parameters with epsilon left out: the states of one
    declared set differ in epsilon and in nothing else."""
    return json.dumps({k: v for k, v in head["params"].items()
                       if k not in ("epsilon", "shard_depth")},
                      sort_keys=True)


def _run_info(state_dir):
    """The declared `simulate_info.json` beside a `state/` directory."""
    p = os.path.join(os.path.dirname(os.path.abspath(state_dir)),
                     "simulate_info.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def declared_set(base_path, simulated_dirs, family):
    """{epsilon: state path} for the base state's configuration, and what
    simulating one of them has cost.

    Collects every state of `family` in the base state's directory and in
    `simulated_dirs` whose parameters match the base state's in everything
    but epsilon. The cost is each such configuration's build and query time,
    read from the declared timings in its run's `simulate_info.json`.
    """
    head0, _ = contract.load_state(base_path)
    key = _configuration(head0)
    by_eps, seconds, requirements = {}, [], None
    for d in [os.path.dirname(os.path.abspath(base_path))] + \
            list(simulated_dirs):
        info = _run_info(d)
        timings = info.get("timings") or {}
        req = (info.get("requirements_file") or {}).get("path")
        if req and requirements is None:
            requirements = re.split(r"[\\/]", req)[-1]
        for p in states_in(d, family):
            h, _ = contract.load_state(p)
            if _configuration(h) != key:
                continue
            eps = h["assignment"]["epsilon"]
            if eps is None:
                continue
            by_eps.setdefault(round(float(eps), 6), p)
            t = timings.get(h["config_label"])
            if t:
                seconds.append(float(t["build_seconds"])
                               + float(t["query_seconds"]))
    return by_eps, seconds, requirements, head0


def plan(base_path, simulated_dirs, family, epsilon=None):
    """Which state each view is drawn from, for the epsilon asked for."""
    by_eps, seconds, requirements, head = declared_set(
        base_path, simulated_dirs, family)
    base_eps = head["assignment"]["epsilon"]
    if base_eps is None and epsilon is not None:
        raise SystemExit(f"{family} has no epsilon; --epsilon does not apply")
    want = base_eps if epsilon is None else float(epsilon)
    trace_path = base_path
    if want is not None and round(float(want), 6) in by_eps:
        trace_path = by_eps[round(float(want), 6)]

    base = contract.load_state(base_path)
    trace = base if trace_path == base_path else \
        contract.load_state(trace_path)

    cost = (f"{COULDNT_CHECK}: no simulate_info.json timings were found for "
            "this configuration")
    if seconds:
        cost = {"low": round(min(seconds) / 60.0, 1),
                "high": round(max(seconds) / 60.0, 1),
                "basis": (f"build and query of this configuration at the "
                          f"{len(seconds)} simulated epsilon(s) with declared "
                          "timings, on the machine that ran them; loading "
                          "vectors, ground truth and k-means add to it")}
    params = {k: v for k, v in head["params"].items() if k != "shard_depth"}
    params["epsilon"] = want
    req = requirements or "<requirements.yaml>"
    action = {"kind": "simulate", "family": family, "epsilon": want,
              "params": params,
              "grid": {family: {k: [v] for k, v in params.items()}},
              "requirements": req,
              "command": f"oneground simulate {req} --emit-state"}
    # One source for which epsilons were simulated, handed to both views, so
    # the ground and the query trace cannot disagree about it (task 023).
    eps = contract.EpsilonSet.make(epsilon=want, simulated=sorted(by_eps),
                                   cost=cost, action=action)
    return {"base_path": base_path, "base": base,
            "trace_path": trace_path, "trace": trace,
            "epsilon": want, "simulated": sorted(by_eps),
            "cost": cost, "action": action, "eps": eps}


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
            json.dump({"state_file": os.path.basename(base_path),
                       "config_label": head["config_label"],
                       "epsilon": {"requested": p["epsilon"],
                                   "simulated": p["simulated"],
                                   "query_trace_state": os.path.basename(
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
