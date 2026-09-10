"""The published ANN-Benchmarks hnswlib points, and what they will not tell us.

ANN-Benchmarks publishes no results file. Task 012 probed
`glove-100-angular_10_angular.csv`, `res.csv`, `results.csv` and the repo's
`results.csv`: all 404. The results exist only as JavaScript embedded in the
per-dataset HTML page, so *that page is the results file*, its sha256 is what
the fixture records, and this module is the parser.

Three properties of that page decide what can be compared at all:

1. **The plotted series is a Pareto frontier, not a sweep.** A point that no
   other hnswlib configuration dominates is drawn; the rest are dropped. The
   headline Recall/QPS chart shows exactly one M=16 point, not nine.

2. **efSearch is not in the point labels.** A label reads
   `hnswlib ({'M': 12, 'efConstruction': 500})`. The query-time parameter that
   produced the point is not published anywhere on the page.

3. **efConstruction is 500 for every M.** ANN-Benchmarks' own
   `ann_benchmarks/algorithms/hnswlib/config.yml` sets `efConstruction: 500`
   in all nine run groups, with `query_args: [[10, 20, 40, 80, 120, 200, 400,
   600, 800]]`. There is no efConstruction=200 hnswlib run to compare against.

Recovering the sweep
--------------------
The page draws thirteen charts, and the frontier is recomputed per chart
because it depends on the y-axis. A point dominated on QPS may survive on
build time. Taking the union over every chart whose x-axis is plain `Recall`
(the `Relative Error` and `Epsilon * Recall` charts use a different x and are
excluded) recovers more of each sweep than any single chart shows.

For **M=12, efConstruction=500** the union recovers nine distinct recall
values against a nine-value ef grid, strictly increasing. Recall is monotone
in ef, so that is a forced one-to-one mapping and the only configuration on
this page whose per-ef sweep is fully determined. Every other M recovers fewer
points than its grid has ef values, so which ef each surviving point belongs
to is ambiguous, and this module refuses to guess: an incomplete series yields
no reference points rather than a plausible alignment.

That refusal is the substance of the module. Assigning eight recovered M=96
points to the first eight ef values would look like a reference curve and
would be fiction.
"""

import re

# ANN-Benchmarks' hnswlib query-time grid, from its config.yml (all run
# groups share it). Recorded here because the plotted points do not carry it.
ANN_BENCHMARKS_EF_GRID = (10, 20, 40, 80, 120, 200, 400, 600, 800)

# The x-axis label of a chart whose x really is recall@k.
RECALL_AXIS = "Recall"

_CHART = re.compile(r"new Chart\(")
_XAXIS = re.compile(r"xAxes:\s*\[\{.*?labelString:\s*'([^']*)'", re.S)
_POINT = re.compile(
    r'\{\s*x:\s*([0-9.eE+-]+)\s*,\s*y:\s*([0-9.eE+-]+)\s*,'
    r'\s*label:\s*"([^"]*)"\s*\}')
_PARAMS = re.compile(r"'M':\s*(\d+).*?'efConstruction':\s*(\d+)")


def _series_blocks(section, algorithm):
    pat = re.compile(
        r'label:\s*"' + re.escape(algorithm) + r'",\s*\n\s*fill: false,'
        r'.*?data:\s*\[(.*?)\n\s*\]', re.S)
    return [m.group(1) for m in pat.finditer(section)]


def recall_points(html, algorithm="hnswlib"):
    """Union of published (M, efConstruction) -> {recall} over recall charts.

    Returns {(M, efConstruction): sorted list of distinct recall values}.
    """
    starts = [m.start() for m in _CHART.finditer(html)]
    bounds = list(zip(starts, starts[1:] + [len(html)]))
    out = {}
    for a, b in bounds:
        section = html[a:b]
        m = _XAXIS.search(section)
        if not m or m.group(1).strip() != RECALL_AXIS:
            continue
        for body in _series_blocks(section, algorithm):
            for x, _y, label in _POINT.findall(body):
                p = _PARAMS.search(label)
                if not p:
                    continue
                key = (int(p.group(1)), int(p.group(2)))
                out.setdefault(key, set()).add(round(float(x), 6))
    return {k: sorted(v) for k, v in out.items()}


def complete_sweeps(html, algorithm="hnswlib", ef_grid=ANN_BENCHMARKS_EF_GRID):
    """The (M, efConstruction) whose sweep is fully recovered, mapped to ef.

    A sweep qualifies only when the number of distinct published recall values
    equals the number of ef values in the grid and the recalls are strictly
    increasing. Both conditions are required: equal counts alone would still
    admit a series with a tie, where the order is not a bijection.

    Returns {(M, efConstruction): {ef: recall}}.
    """
    sweeps = {}
    for key, recalls in recall_points(html, algorithm).items():
        if len(recalls) != len(ef_grid):
            continue
        if any(b <= a for a, b in zip(recalls, recalls[1:])):
            continue
        sweeps[key] = {int(ef): float(r) for ef, r in zip(ef_grid, recalls)}
    return sweeps


def reference_for(html, M, ef_construction, ef_values,
                  algorithm="hnswlib", ef_grid=ANN_BENCHMARKS_EF_GRID):
    """Published recall@10 per requested efSearch, or None where unpublished.

    None is the honest answer for a point ANN-Benchmarks never published at
    this configuration, and the caller turns it into `couldnt_check`. It is
    never filled in by interpolation: a reference point that was interpolated
    is not a reference point.
    """
    sweeps = complete_sweeps(html, algorithm, ef_grid)
    got = sweeps.get((int(M), int(ef_construction)))
    if got is None:
        return {int(ef): None for ef in ef_values}
    return {int(ef): got.get(int(ef)) for ef in ef_values}


def describe(html, algorithm="hnswlib", ef_grid=ANN_BENCHMARKS_EF_GRID):
    """What the page holds, for the report and for `calibrate reference`."""
    pts = recall_points(html, algorithm)
    full = complete_sweeps(html, algorithm, ef_grid)
    return {
        "algorithm": algorithm,
        "ef_grid": list(ef_grid),
        "configurations": sorted(
            [{"M": m, "efConstruction": efc,
              "published_points": len(v),
              "sweep_complete": (m, efc) in full}
             for (m, efc), v in pts.items()],
            key=lambda d: (d["M"], d["efConstruction"])),
        "complete_sweeps": [{"M": m, "efConstruction": efc,
                             "points": full[(m, efc)]}
                            for (m, efc) in sorted(full)],
    }
