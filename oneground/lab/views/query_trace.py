"""One query's trace: where it was routed, what it probed, and where its true
neighbours live.

The teaser's second figure. "Outside the routed region" compares each true
neighbour's stored home region with the query's first probe; "missed by the
route" asks whether any probed shard returned it. Both are lookups into what
the family stored.
"""

from ..contract import COULDNT_CHECK, Drawing, Mark, View

K_TRUE = 10


class QueryTraceView(View):
    name = "query_trace"
    reads = (
        "route.probed_region", "route.probe_reason",
        "route.scored_region", "route.scored_dist",
        "assignment.home_region",
        "candidates.offsets", "candidates.cand_id", "candidates.true_rank",
        "candidates.true_ids",
    )

    def __init__(self, query=15, k=K_TRUE):
        self.query = int(query)
        self.k = int(k)

    def params(self):
        return {"query": self.query, "k": self.k}

    def render(self, state):
        h = state.header
        q, k = self.query, self.k
        n_q = int(h["n_queries"])
        if not 0 <= q < n_q:
            raise ValueError(f"query {q} is not in [0, {n_q})")

        probed = [int(r) for r in state["route.probed_region"][q]]
        reasons = [int(w) for w in state["route.probe_reason"][q]]
        scored = [int(r) for r in state["route.scored_region"][q]]
        scored_dist = [float(x) for x in state["route.scored_dist"][q]]
        home = state["assignment.home_region"]
        offsets = state["candidates.offsets"]
        lo, hi = int(offsets[q]), int(offsets[q + 1])
        cand_id = state["candidates.cand_id"][lo:hi].tolist()
        cand_rank = state["candidates.true_rank"][lo:hi].tolist()

        routed = probed[0]
        returned = set(cand_id)

        # What the candidates alone name: a true neighbour appears only if a
        # probed shard returned it. Kept so every drawing states the gap
        # `candidates.true_ids` was added to close (task 020).
        from_candidates = {}
        for vid, r in zip(cand_id, cand_rank):
            if 0 <= r < k and r not in from_candidates:
                from_candidates[int(r)] = int(vid)
        if state.has("candidates.true_ids"):
            row = state["candidates.true_ids"][q][:k].tolist()
            found = {r: int(v) for r, v in enumerate(row) if v >= 0}
        else:
            found = from_candidates

        ranks = sorted(found)
        ids = [found[r] for r in ranks]
        homes = [int(home[v]) for v in ids]
        outside = [hr != routed for hr in homes]
        missed = [v not in returned for v in ids]

        figures = {
            "query": q,
            "routed_region": routed,
            "probed_regions": [r for r in probed if r >= 0],
            "true_neighbours_located": len(found),
            "missed_by_route": sum(missed),
            "answerable_from_candidates_alone": len(from_candidates) == k,
        }
        gaps = {}
        if len(found) == k:
            figures["outside_routed_region"] = sum(outside)
        else:
            unplaced = k - len(found)
            gaps["outside_routed_region"] = (
                f"{COULDNT_CHECK}: {unplaced} of this query's {k} true "
                "neighbours are not in the state. It names a true neighbour "
                "only as a candidate some probed shard returned, so a "
                "neighbour no probed shard returned has no id here and its "
                "home region cannot be looked up")
            figures["outside_routed_region_lower_bound"] = sum(outside)

        why = h["route_reasons"]
        marks = [
            Mark("region",
                 data={"region": [r for r in scored if r >= 0],
                       "distance": [x for x, r in zip(scored_dist, scored)
                                    if r >= 0]},
                 encoding={"id": "region", "size": "distance"}),
            Mark("link",
                 data={"probe_order": [i for i, r in enumerate(probed)
                                       if r >= 0],
                       "region": [r for r in probed if r >= 0],
                       "reason": [why[str(w)] for w, r in zip(reasons, probed)
                                  if r >= 0]},
                 encoding={"target": "region", "label": "reason",
                           "order": "probe_order"}),
            Mark("point",
                 data={"rank": ranks, "vector_id": ids, "home_region": homes,
                       "outside_routed_region": outside,
                       "missed_by_route": missed},
                 encoding={"id": "vector_id", "group": "home_region",
                           "color": "outside_routed_region",
                           "shape": "missed_by_route"}),
        ]
        return Drawing(view=self.name, marks=marks, figures=figures,
                       gaps=gaps)
