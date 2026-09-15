"""The ground: every base vector, and how many regions it is copied into.

The teaser's first figure. Its counters -- the copies histogram, vectors
copied, storage amplification, p99 copies and boundary crispness -- are tallies
of what the family stored per vector. None of them is measured here.
"""

import numpy as np

from ..contract import COULDNT_CHECK, Drawing, Mark, View

# A definition, not data: the fixture spec's boundary crispness is the share
# of vectors whose second-nearest centroid is more than 1.20x as far as the
# nearest. The distances it is a share of were measured by the family and
# stored; this is the published threshold they are compared against.
CRISP_RATIO = 1.20
NON_SQUARED = "euclidean (non-squared)"


class GroundView(View):
    name = "ground"
    reads = ("assignment.copy_count", "assignment.home_region",
             "assignment.centroid_dist")

    def render(self, state):
        h = state.header
        n = int(h["n_base"])
        cap = int(h["assignment"]["max_assign"])
        copies = state["assignment.copy_count"].astype(np.int64)
        home = state["assignment.home_region"]

        histogram = [int(np.count_nonzero(copies == c))
                     for c in range(1, cap + 1)]
        figures = {
            "n_base": n,
            "epsilon": h["assignment"]["epsilon"],
            "max_assign": cap,
            "copies_histogram": histogram,
            "copies_histogram_pct": [round(100.0 * c / n, 1)
                                     for c in histogram],
            "vectors_copied": int(np.count_nonzero(copies > 1)),
            "storage_amplification": float(copies.sum() / n),
            # method="lower": the p99 of an integer copy count is a copy count
            "p99_copies": int(np.percentile(copies, 99, method="lower")),
        }
        gaps = {
            "positions": (
                f"{COULDNT_CHECK}: not simulator state -- the teaser's 2-D "
                "placement is a UMAP projection the fixture spec declares "
                "illustrative, so it is not in the state and no position is "
                "rendered"),
        }

        kind = h["partition"]["kind"]
        dist = state["assignment.centroid_dist"]
        if kind != "kmeans":
            gaps["boundary_crispness"] = (
                f"{COULDNT_CHECK}: a {kind} partition has no centroids, so "
                "there is no second-nearest centroid distance to compare")
        elif dist.shape[1] < 2 or np.isnan(dist[:, :2]).any():
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
                np.mean(dist[:, 1] > CRISP_RATIO * dist[:, 0]))

        marks = [Mark(
            "point",
            data={"vector_id": np.arange(n), "home_region": home,
                  "copy_count": copies},
            encoding={"id": "vector_id", "color": "copy_count",
                      "group": "home_region"})]
        return Drawing(view=self.name, marks=marks, figures=figures,
                       gaps=gaps)
