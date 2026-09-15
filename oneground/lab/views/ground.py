"""The ground: every base vector, and how many regions it is copied into --
recounted from state as epsilon moves (task 023).

Epsilon decides the closure and nothing upstream of it. The distances a
vector's copies are decided by, and the regions those distances were taken
to, are in the state whatever epsilon is asked for. So this view recounts
rather than reading back the copy counts one run happened to emit:

    copies(v) = 1 + #{ j > 0 : d[v, j] <= d[v, 0] * (1 + epsilon) }

written exactly as `semantic_sharded.build` writes it, on the stored float32
distances, so a recount reproduces that run's bits rather than approximating
them. At the state's own epsilon it reproduces the emitted copy counts
exactly; task 023 checked that against every simulated state on both
published fixtures.

What it draws: each vector's copy count (the ground's colour), the copies
histogram, vectors copied, storage amplification, p99 copies, the vectors
each shard holds, boundary crispness, and the routing ceiling at k=10 --
which true neighbours some probed region holds a copy of. The ceiling is the
one recall-shaped number that needs no rebuilt index: it asks where copies
are, not what an index returned.

What it does not draw: recall, candidates, the neighbours a route missed.
Those are what the shards' indexes returned, and epsilon rebuilds every index
(task 021b), so they belong to the query trace's recall panel at simulated
epsilons only. At any other epsilon this view's caption says so.
"""

import numpy as np

from ..contract import (COULDNT_CHECK, NOT_SIMULATED, Drawing, EpsilonSet,
                        Mark, View, same_epsilon)

# A definition, not data: the fixture spec's boundary crispness is the share
# of vectors whose second-nearest centroid is more than 1.20x as far as the
# nearest. The distances it is a share of were measured by the family and
# stored; this is the published threshold they are compared against.
CRISP_RATIO = 1.20
NON_SQUARED = "euclidean (non-squared)"

# The depth the routing ceiling is taken at, as the fixtures publish it.
K_CEILING = 10


def recount(dist, near, epsilon, n_regions):
    """The closure at `epsilon`, from stored distances and nearest regions.

    Written exactly as `semantic_sharded.build` writes it -- the same
    comparison on the same float32 distances, with epsilon a Python float --
    so this reproduces that run's bits rather than approximating them.

    Returns `(within, copies, held)`: the closure mask, each vector's copy
    count, and the vectors each region holds.
    """
    within = dist <= dist[:, [0]] * (1 + float(epsilon))
    within[:, 0] = True
    copies = within.sum(axis=1).astype(np.int64)
    held = np.bincount(near[within], minlength=n_regions)
    return within, copies, held


class GroundView(View):
    name = "ground"
    recounts = True
    reads = ("assignment.centroid_dist", "assignment.nearest_region",
             "assignment.home_region", "assignment.copy_count",
             "partition.region_ids", "route.probed_region",
             "candidates.true_ids", "load.vectors_held")

    def __init__(self, eps=None, k=K_CEILING):
        self.eps = eps or EpsilonSet()
        self.k = int(k)

    def params(self):
        return {"epsilon": self.eps.epsilon, "k": self.k,
                "simulated_epsilons": list(self.eps.simulated)}

    def render(self, state):
        h = state.header
        n = int(h["n_base"])
        cap = int(h["assignment"]["max_assign"])
        state_eps = h["assignment"]["epsilon"]
        want, simulated = self.eps.at(state_eps)
        at_simulated = want is None or any(same_epsilon(want, e)
                                           for e in simulated)

        figures = {"n_base": n, "max_assign": cap, "epsilon": want,
                   "simulated_epsilons": list(simulated)}
        gaps = {
            "positions": (
                f"{COULDNT_CHECK}: not simulator state -- the teaser's 2-D "
                "placement is a UMAP projection the fixture spec declares "
                "illustrative, so it is not in the state and no position is "
                "rendered"),
        }
        home = state["assignment.home_region"]
        regions = state["partition.region_ids"]

        recountable = want is not None and state.has(
            "assignment.nearest_region")
        if recountable:
            dist = state["assignment.centroid_dist"]
            near = state["assignment.nearest_region"]
            within, copies, held = recount(dist, near, want, len(regions))
        else:
            # a family with no epsilon, or a state written before
            # nearest_region: there is nothing to recount it to
            within, copies = None, state["assignment.copy_count"].astype(
                np.int64)
            held = state["load.vectors_held"]
            if want is not None and not same_epsilon(want, state_eps):
                gaps["recount"] = (
                    f"{COULDNT_CHECK}: this state has no "
                    "assignment.nearest_region, so the closure cannot be "
                    f"recounted at epsilon {want}; the figures below are the "
                    f"ones emitted at epsilon {state_eps}")
                figures["epsilon"] = state_eps
                want = state_eps

        figures["recounted_from_state"] = bool(recountable)
        histogram = [int(np.count_nonzero(copies == c))
                     for c in range(1, cap + 1)]
        figures.update({
            "copies_histogram": histogram,
            "copies_histogram_pct": [round(100.0 * c / n, 1)
                                     for c in histogram],
            "vectors_copied": int(np.count_nonzero(copies > 1)),
            "storage_amplification": float(copies.sum() / n),
            # method="lower": the p99 of an integer copy count is a copy count
            "p99_copies": int(np.percentile(copies, 99, method="lower")),
            "vectors_held_total": int(held.sum()),
        })

        kind = h["partition"]["kind"]
        dist_all = state["assignment.centroid_dist"]
        if kind != "kmeans":
            gaps["boundary_crispness"] = (
                f"{COULDNT_CHECK}: a {kind} partition has no centroids, so "
                "there is no second-nearest centroid distance to compare")
        elif dist_all.shape[1] < 2 or np.isnan(dist_all[:, :2]).any():
            gaps["boundary_crispness"] = (
                f"{COULDNT_CHECK}: the state holds fewer than two centroid "
                "distances per vector")
        elif h.get("distance_convention") != NON_SQUARED:
            gaps["boundary_crispness"] = (
                f"{COULDNT_CHECK}: the state's distances are "
                f"{h.get('distance_convention')!r}, and the 1.20 threshold "
                "compares non-squared distances")
        else:
            figures["boundary_crispness"] = float(
                np.mean(dist_all[:, 1] > CRISP_RATIO * dist_all[:, 0]))

        # the routing ceiling: a true neighbour is reachable when some region
        # the query probes holds a copy of it at this epsilon
        if not recountable:
            gaps["routing_ceiling_at_k"] = (
                f"{COULDNT_CHECK}: without assignment.nearest_region there is "
                "no way to say which regions hold a copy of a neighbour")
        elif not state.has("candidates.true_ids"):
            gaps["routing_ceiling_at_k"] = (
                f"{COULDNT_CHECK}: this state has no candidates.true_ids, so "
                "there are no true neighbours to reach")
        else:
            truth = state["candidates.true_ids"][:, :self.k]
            probed = state["route.probed_region"]
            in_probe = (near[truth][..., None]
                        == probed[:, None, None, :]).any(-1)
            reach = (within[truth] & in_probe).any(-1)
            figures["routing_ceiling_at_k"] = float(reach.mean())
            figures["true_neighbours_reachable"] = int(reach.sum())
            figures["k"] = self.k

        marks = [
            Mark("point",
                 data={"vector_id": np.arange(n), "home_region": home,
                       "copy_count": copies},
                 encoding={"id": "vector_id", "color": "copy_count",
                           "group": "home_region"}),
            Mark("bar",
                 data={"region": regions, "vectors_held": held},
                 encoding={"id": "region", "size": "vectors_held"}),
        ]
        return Drawing(view=self.name, marks=marks, figures=figures,
                       gaps=gaps,
                       caption=self._caption(h, want, simulated,
                                             at_simulated, recountable))

    def _caption(self, h, want, simulated, at_simulated, recountable):
        if want is None:
            return (f"The ground for {h['family']}, which has no epsilon: "
                    "copy counts as the run emitted them.")
        if not recountable:
            return (f"The ground at epsilon {want}, as the run emitted it. "
                    "This state predates assignment.nearest_region, so the "
                    "closure cannot be recounted at another epsilon.")
        if at_simulated:
            return (f"The ground at epsilon {want}, recounted from state. "
                    "This epsilon was simulated, so the query trace's recall "
                    "panel holds recall and candidates for it.")
        return (f"The ground at epsilon {want}: the geometry is recounted "
                f"from state, and {NOT_SIMULATED}. No recall, candidate or "
                "missed-neighbour figure exists at this epsilon -- those are "
                "what the shards' indexes returned, and this epsilon would "
                f"rebuild them. Simulated: {list(simulated)}.")
