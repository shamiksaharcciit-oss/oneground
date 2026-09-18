"""Every query at once, as the query picker lists them (task 025).

One row per query, carrying what a person needs to find an interesting one:
the region it was routed to, whether it is ambiguous, how many of its true
neighbours live outside the routed region, and -- only at an epsilon that was
simulated -- how many of them the probed regions returned.

Nothing here is a new figure. Each row is what `QueryTraceView` states about
that query, derived by the same functions (`located`, `ambiguity`, and the
trace's own recall), so the list and the trace cannot disagree; a test draws
both for every query and compares them. The split by epsilon is the trace's
too: the geometric columns are drawn at any epsilon, and the found and missed
counts only in a `recall` panel over a state simulated at the epsilon asked
for. Between simulated values that panel says `not simulated at this epsilon`,
with the simulated values, the cost and the action, and the list orders by
geometry alone.
"""

from ..contract import (COULDNT_CHECK, NOT_SIMULATED, SIMULATED, Drawing,
                        EpsilonSet, Mark, View, same_epsilon)
from .query_trace import K_TRUE, QueryTraceView, ambiguity, located


class QueryIndexView(View):
    name = "query_index"
    reads = QueryTraceView.reads

    def __init__(self, k=K_TRUE, eps=None, ambiguity=None):
        self.k = int(k)
        self.eps = eps or EpsilonSet()
        self.ambiguity = ambiguity

    def params(self):
        out = {"k": self.k, "epsilon": self.eps.epsilon,
               "simulated_epsilons": list(self.eps.simulated)}
        if self.ambiguity is not None:
            out["ambiguity"] = self.ambiguity
        return out

    def render(self, state):
        h = state.header
        k = self.k
        n_q = int(h["n_queries"])
        state_eps = h["assignment"]["epsilon"]
        want, simulated = self.eps.at(state_eps)
        if state_eps is None:
            at_state = True
        else:
            at_state = same_epsilon(want, state_eps)
            if not at_state and any(same_epsilon(want, e) for e in simulated):
                raise ValueError(
                    f"epsilon {want} was simulated: draw the query index over "
                    f"the state emitted at {want}, not over the one simulated "
                    f"at {state_eps}")

        probed = state["route.probed_region"]
        scored = state["route.scored_region"]
        scored_dist = state["route.scored_dist"]
        home = state["assignment.home_region"]

        routed, outside, located_n = [], [], []
        ratio, ambiguous = [], []
        hits, missed = [], []
        gaps = {}
        unlocated = 0
        ambiguity_reason = None
        for q in range(n_q):
            r0 = int(probed[q][0])
            routed.append(r0)
            found = located(state, q, k, at_state)
            if found is None:
                found = {}
                unlocated += 1
            ids = [found[r] for r in sorted(found)]
            located_n.append(len(ids))
            outside.append(sum(int(home[v]) != r0 for v in ids)
                           if len(ids) == k else None)

            if self.ambiguity is not None:
                f, g = {}, {}
                ambiguity(h, [int(x) for x in scored[q]],
                          [float(x) for x in scored_dist[q]],
                          self.ambiguity, f, g)
                ratio.append(f.get("distance_ratio"))
                ambiguous.append(f.get("ambiguous"))
                if g and ambiguity_reason is None:
                    ambiguity_reason = g["ambiguous"]

            if at_state:
                recall = QueryTraceView._recall(state, q, k, want, ids)
                hits.append(recall["figures"]["hits"])
                missed.append(recall["figures"]["missed_by_route"])

        data = {"query": list(range(n_q)), "routed_region": routed,
                "true_neighbours_located": located_n,
                "outside_routed_region": outside}
        encoding = {"id": "query", "group": "routed_region",
                    "size": "outside_routed_region"}
        figures = {"n_queries": n_q, "k": k, "epsilon": want,
                   "simulated_epsilons": list(simulated)}
        if unlocated:
            gaps["true_neighbours"] = (
                f"{COULDNT_CHECK}: {unlocated} of {n_q} queries' true "
                "neighbours cannot be named at this epsilon from this state")
        if any(v is None for v in outside) and not unlocated:
            gaps["outside_routed_region"] = (
                f"{COULDNT_CHECK}: some queries have fewer than {k} true "
                "neighbours in the state; their rows carry none")
        if self.ambiguity is not None:
            if ambiguity_reason is None:
                data["distance_ratio"] = ratio
                data["ambiguous"] = ambiguous
                encoding["color"] = "ambiguous"
                figures["ambiguity_ratio"] = float(self.ambiguity)
                figures["ambiguous_queries"] = sum(bool(a) for a in ambiguous)
            else:
                gaps["ambiguous"] = ambiguity_reason

        if at_state:
            panel = {"status": SIMULATED, "epsilon": want,
                     "figures": {"k": k, "hits": hits,
                                 "missed_by_route": missed}}
        else:
            panel = {
                "status": NOT_SIMULATED,
                "epsilon": want,
                "simulated_epsilons": list(simulated),
                "cost_minutes": self.eps.cost or (
                    f"{COULDNT_CHECK}: no measured simulate timings were "
                    "declared for this configuration"),
                "action": self.eps.action or QueryTraceView._default_action(
                    h, want),
            }
        return Drawing(view=self.name,
                       marks=[Mark("point", data=data, encoding=encoding)],
                       figures=figures, gaps=gaps, panels={"recall": panel})
