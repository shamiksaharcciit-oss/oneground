"""One query's trace: where it was routed, what it probed, where its true
neighbours live -- and, only at an epsilon that was simulated, what came back.

The view is split by what moving epsilon does to each half
(`contract.ON_EPSILON`):

  geometric   the routed and probed regions, the true neighbours, their home
              regions, and how many lie outside the routed region. None of it
              depends on epsilon, so it is drawn at whatever epsilon the lab's
              control is at.
  recall      the `recall` panel: recall@k, the candidates returned, and the
              true neighbours the route missed. These are what each shard's
              index returned, and epsilon rebuilds every index, so they are
              drawn only from a state simulated at the epsilon asked for.

Recall at other epsilons is a declared set, rendered on request. Asked for an
epsilon between simulated values, the view does not interpolate and does not
leave the panel blank. The panel says `not simulated at this epsilon`, lists
the epsilons that were simulated, gives the measured cost of simulating one in
minutes, and carries the action that would run it. Asked for an epsilon that
was simulated, but over a state simulated at a different one, the view
refuses: that recall is in the other state, not here.
`contract.draw` enforces all of this.

Which epsilons count as simulated comes from the `EpsilonSet` the composer
builds once and hands to every view, so this view and the ground cannot
disagree about it (task 023).

Ambiguity (task 025): given the ratio the run declared (`characterization.json`
`definitions.ambiguity_ratio`), the trace says whether the query is ambiguous
by the same definition the characterization measured -- its second-nearest
centroid within that ratio of its nearest, on non-squared distances -- read
from the two distances `route.scored_dist` holds. Given a `couldnt_check`
reason instead, it carries the reason as a gap. Given nothing, it says nothing
about ambiguity, as before.
"""

import numpy as np

from ..contract import (COULDNT_CHECK, NOT_SIMULATED, SIMULATED, Drawing,
                        EpsilonSet, Mark, View, same_epsilon)

K_TRUE = 10
NON_SQUARED = "euclidean (non-squared)"


class QueryTraceView(View):
    name = "query_trace"
    reads = (
        "route.probed_region", "route.probe_reason",
        "route.scored_region", "route.scored_dist",
        "assignment.home_region",
        "candidates.true_ids",
        # the recall panel's columns, read only at a simulated epsilon
        "candidates.offsets", "candidates.cand_id", "candidates.cand_score",
        "candidates.survived_dedupe", "candidates.true_rank",
    )

    def __init__(self, query=15, k=K_TRUE, eps=None, ambiguity=None):
        """`eps` is the `EpsilonSet`: where the control stands, which epsilons
        were simulated, and the cost and action the recall panel offers
        between them. Default: this state's own epsilon.

        `ambiguity` is the run's declared ambiguity ratio, a `couldnt_check`
        reason why there is none, or None to leave ambiguity out."""
        self.query = int(query)
        self.k = int(k)
        self.eps = eps or EpsilonSet()
        self.ambiguity = ambiguity

    def params(self):
        out = {"query": self.query, "k": self.k,
               "epsilon": self.eps.epsilon,
               "simulated_epsilons": list(self.eps.simulated)}
        if self.ambiguity is not None:
            out["ambiguity"] = self.ambiguity
        return out

    def render(self, state):
        h = state.header
        q, k = self.query, self.k
        n_q = int(h["n_queries"])
        if not 0 <= q < n_q:
            raise ValueError(f"query {q} is not in [0, {n_q})")

        state_eps = h["assignment"]["epsilon"]
        want, simulated = self.eps.at(state_eps)
        if state_eps is None:
            if self.eps.epsilon is not None:
                raise ValueError(f"{h['family']} has no epsilon; draw its "
                                 "trace without one")
            at_state = True
        else:
            at_state = same_epsilon(want, state_eps)
            if not at_state and any(same_epsilon(want, e) for e in simulated):
                raise ValueError(
                    f"epsilon {want} was simulated: draw the query trace over "
                    f"the state emitted at {want}, not over the one simulated "
                    f"at {state_eps}")

        # ---- geometric: nothing here depends on epsilon ----
        probed = [int(r) for r in state["route.probed_region"][q]]
        reasons = [int(w) for w in state["route.probe_reason"][q]]
        scored = [int(r) for r in state["route.scored_region"][q]]
        scored_dist = [float(x) for x in state["route.scored_dist"][q]]
        home = state["assignment.home_region"]
        routed = probed[0]

        gaps = {}
        found = located(state, q, k, at_state)
        if found is None:
            found = {}
            gaps["true_neighbours"] = (
                f"{COULDNT_CHECK}: this state has no candidates.true_ids, and "
                "at an epsilon it was not simulated at the returned "
                "candidates cannot stand in for them")

        ranks = sorted(found)
        ids = [found[r] for r in ranks]
        homes = [int(home[v]) for v in ids]
        outside = [hr != routed for hr in homes]

        figures = {
            "query": q,
            "epsilon": want,
            "simulated_epsilons": list(simulated),
            "routed_region": routed,
            "probed_regions": [r for r in probed if r >= 0],
            "true_neighbours_located": len(found),
        }
        if self.ambiguity is not None:
            ambiguity(h, scored, scored_dist, self.ambiguity, figures, gaps)
        if len(found) == k:
            figures["outside_routed_region"] = sum(outside)
        elif "true_neighbours" not in gaps:
            gaps["outside_routed_region"] = (
                f"{COULDNT_CHECK}: {k - len(found)} of this query's {k} true "
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
                       "outside_routed_region": outside},
                 encoding={"id": "vector_id", "group": "home_region",
                           "color": "outside_routed_region"}),
        ]

        # ---- recall: only at the epsilon this state was simulated at ----
        if at_state:
            panel = self._recall(state, q, k, want, ids)
        else:
            panel = {
                "status": NOT_SIMULATED,
                "epsilon": want,
                "simulated_epsilons": list(simulated),
                "cost_minutes": self.eps.cost or (
                    f"{COULDNT_CHECK}: no measured simulate timings were "
                    "declared for this configuration"),
                "action": self.eps.action or self._default_action(h, want),
            }
        return Drawing(view=self.name, marks=marks, figures=figures,
                       gaps=gaps, panels={"recall": panel})

    @staticmethod
    def _ranked_from_candidates(state, q, k):
        offsets = state["candidates.offsets"]
        lo, hi = int(offsets[q]), int(offsets[q + 1])
        found = {}
        for vid, r in zip(state["candidates.cand_id"][lo:hi].tolist(),
                          state["candidates.true_rank"][lo:hi].tolist()):
            if 0 <= r < k and r not in found:
                found[int(r)] = int(vid)
        return found

    @staticmethod
    def _recall(state, q, k, want, ids):
        offsets = state["candidates.offsets"]
        lo, hi = int(offsets[q]), int(offsets[q + 1])
        cand = state["candidates.cand_id"][lo:hi]
        score = state["candidates.cand_score"][lo:hi]
        kept = state["candidates.survived_dedupe"][lo:hi]
        rank = state["candidates.true_rank"][lo:hi]

        # the merged result: first occurrences, best score first, top k
        order = np.argsort(-score[kept], kind="stable")[:k]
        top_ids = cand[kept][order]
        top_ranks = rank[kept][order]
        hits = int(np.count_nonzero((top_ranks >= 0) & (top_ranks < k)))

        returned = set(cand.tolist())
        missed = [v not in returned for v in ids]
        in_top = set(top_ids.tolist())
        named = set(int(r) for r in rank.tolist() if 0 <= r < k)
        return {
            "status": SIMULATED,
            "epsilon": want,
            "figures": {
                "recall_at_k": hits / k,
                "hits": hits,
                "k": k,
                "returned_top_k": top_ids.tolist(),
                "candidates_returned": int(hi - lo),
                "missed_by_route": sum(missed),
                "missed_by_route_by_rank": missed,
                # task 025: which of the true neighbours, by rank, are in the
                # merged top k -- what the trace marks found or not found
                "found_by_rank": [v in in_top for v in ids],
                "answerable_from_candidates_alone": len(named) == k,
            },
        }

    @staticmethod
    def _default_action(h, want):
        params = {key: v for key, v in h["params"].items()
                  if key != "shard_depth"}
        params["epsilon"] = want
        return {"kind": "simulate", "family": h["family"], "epsilon": want,
                "params": params,
                "command": "oneground simulate <requirements.yaml> "
                           "--emit-state"}


def ambiguity(h, scored, scored_dist, declared, figures, gaps):
    """The query's ambiguity by the run's declared definition, into `figures`,
    or why not, into `gaps`. Shared with the query index, so the two cannot
    disagree about a query.

    `scored` and `scored_dist` are the query's scored regions and their
    distances, nearest first, as `route.scored_*` store them.
    """
    if isinstance(declared, str):
        gaps["ambiguous"] = declared
        return
    pairs = [(r, d) for r, d in zip(scored, scored_dist) if r >= 0]
    if len(pairs) < 2:
        gaps["ambiguous"] = (
            f"{COULDNT_CHECK}: the state scored this query against "
            f"{len(pairs)} region(s), and ambiguity compares the nearest two")
        return
    if h.get("distance_convention") != NON_SQUARED:
        gaps["ambiguous"] = (
            f"{COULDNT_CHECK}: the state's distances are "
            f"{h.get('distance_convention')!r}, and the declared ratio "
            "compares non-squared distances")
        return
    (r1, d1), (r2, d2) = pairs[0], pairs[1]
    figures["second_region"] = int(r2)
    figures["ambiguity_ratio"] = float(declared)
    figures["distance_ratio"] = float(d2 / d1) if d1 > 0 else None
    figures["ambiguous"] = bool(d2 <= declared * d1)


def located(state, q, k, at_state):
    """Query `q`'s true neighbours this state can name, as {rank: vector id},
    or None when it cannot name them at this epsilon. Shared with the query
    index, so the two locate the same neighbours."""
    if state.has("candidates.true_ids"):
        row = state["candidates.true_ids"][q][:k].tolist()
        return {r: int(v) for r, v in enumerate(row) if v >= 0}
    if at_state:
        # a state written before task 020 added true_ids: the returned
        # candidates name what they can, at the epsilon they were returned at
        return QueryTraceView._ranked_from_candidates(state, q, k)
    return None
