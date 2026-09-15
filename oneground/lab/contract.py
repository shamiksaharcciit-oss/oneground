"""The lab's rendering contract: its types, and the one way a view is drawn.

The rules and the reasons for them are in `oneground/lab/__init__.py`.
"""

import copy
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np

COULDNT_CHECK = "couldnt_check"

# State columns that hold vectors. A view is never handed one: without a
# vector in reach, no view can do arithmetic on one, whatever its source says.
VECTOR_COLUMNS = frozenset({"partition.centroids"})

MARK_KINDS = frozenset({"point", "region", "link", "bar"})

# A panel's two states (task 021b). Recall, candidates and the true neighbours
# a route missed are what each shard's index returned, and moving epsilon
# rebuilds every index: they exist only at epsilons that were simulated. The
# lab's epsilon control is a declared set for them, rendered on request.
# Between simulated epsilons a panel says so, with the cost of simulating one
# and the action that would -- never blank, never interpolated. `draw`
# enforces both, for every view.
SIMULATED = "simulated"
NOT_SIMULATED = "not simulated at this epsilon"

# ---------------------------------------------------------------- epsilon
# What moving epsilon does to each state column (task 021). Epsilon is the
# closure rule's one parameter: it decides which regions a vector is copied
# into, and nothing upstream of that. So:
#
#   unchanged   k-means, routing, distances, the nearest regions and the true
#               neighbours do not depend on it
#   recount     copy counts, copy sets and the vectors each shard holds follow
#               from stored distances and nearest regions alone
#   rebuild     candidates are what each shard's HNSW graph returned, and the
#               graph is built from the shard's members; new members, new
#               graph, new candidates. Only a new `simulate` run knows them.
#
# Task 021's report measures the recount and times the rebuild; its runs
# check this table against states emitted at other epsilons.
UNCHANGED = "unchanged"
RECOUNT = "recount from state"
REBUILD = "rebuild: a new simulate run"
_SEVERITY = {UNCHANGED: 0, RECOUNT: 1, REBUILD: 2}

ON_EPSILON = {
    "partition.region_ids": UNCHANGED,
    "partition.region_sizes": UNCHANGED,
    "partition.centroids": UNCHANGED,
    "assignment.home_region": UNCHANGED,
    "assignment.centroid_dist": UNCHANGED,
    "assignment.nearest_region": UNCHANGED,
    "assignment.copy_count": RECOUNT,
    "assignment.copy_set": RECOUNT,
    "route.scored_region": UNCHANGED,
    "route.scored_dist": UNCHANGED,
    "route.probed_region": UNCHANGED,
    "route.probe_reason": UNCHANGED,
    "candidates.true_ids": UNCHANGED,
    "candidates.offsets": REBUILD,
    "candidates.cand_id": REBUILD,
    "candidates.cand_shard": REBUILD,
    "candidates.cand_score": REBUILD,
    "candidates.survived_dedupe": REBUILD,
    "candidates.true_rank": REBUILD,
    "load.shard_id": UNCHANGED,
    "load.vectors_held": RECOUNT,
    "load.queries_served": UNCHANGED,
    "load.candidates_contributed": REBUILD,
}


class ContractError(RuntimeError):
    """A view broke the rendering contract."""


class VectorColumn(ContractError):
    """A view asked for a column that holds vectors."""


class UndeclaredColumn(ContractError):
    """A view read a column it did not declare in `reads`."""


def on_epsilon(columns):
    """The most a change of epsilon asks of a drawing that read `columns`."""
    worst = UNCHANGED
    for c in columns:
        effect = ON_EPSILON.get(c)
        if effect is None:
            raise ContractError(f"{c} has no entry in ON_EPSILON; say what "
                                "moving epsilon does to it before a view "
                                "reads it")
        if _SEVERITY[effect] > _SEVERITY[worst]:
            worst = effect
    return worst


def same_epsilon(a, b):
    """Two epsilons are the same simulated value. Compared at six decimals --
    the precision simulate writes -- because a slider's float and a requirements
    file's 0.1 must meet, and nothing between two simulated values may."""
    if a is None or b is None:
        return False
    return round(float(a), 6) == round(float(b), 6)


# ------------------------------------------------------------- the state
def state_format():
    """`oneground/models/state.py`, loaded by path.

    By path, not `import oneground.models.state`: importing that package runs
    `oneground/models/__init__.py`, which imports every model family. A
    renderer depends on the state's encoding and on nothing a family
    implements.
    """
    name = "oneground_lab_state_format"
    mod = sys.modules.get(name)
    if mod is None:
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "models", "state.py")
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


def load_state(path):
    """(header, columns) of one `.state.npz`."""
    return state_format().read_state(path)


class StateColumns:
    """The state as a view sees it.

    * only the columns the view declared in `reads`: anything else raises
      `UndeclaredColumn`, so a drawing's provenance is what it says it is
    * never a vector column: `VectorColumn`, raised even if declared
    * every array read-only: a view draws the state, it does not edit it
    * `header` is the view's own copy

    `read` records the columns actually read, which `draw` puts on the
    drawing.
    """

    def __init__(self, header, columns, reads):
        reads = frozenset(reads)
        declared_vectors = sorted(reads & VECTOR_COLUMNS)
        if declared_vectors:
            raise VectorColumn(f"a view may not declare a vector column: "
                               f"{declared_vectors}")
        self.header = copy.deepcopy(header)
        self._columns = columns
        self._reads = reads
        self.read = set()

    def _allowed(self, name):
        if name in VECTOR_COLUMNS:
            raise VectorColumn(
                f"{name} holds vectors, and a view is never handed one. What "
                "a view needs from them was measured by simulate and is in "
                "the state already.")
        if name not in self._reads:
            raise UndeclaredColumn(f"{name} is not in this view's `reads`")

    def has(self, name):
        """Whether the state carries a declared column. A state written
        before a column existed simply lacks it."""
        self._allowed(name)
        return name in self._columns

    def __getitem__(self, name):
        self._allowed(name)
        if name not in self._columns:
            raise KeyError(f"{name} is not in this state; check `has` first")
        self.read.add(name)
        arr = self._columns[name].view()
        arr.flags.writeable = False
        return arr


# ------------------------------------------------------------ the drawing
@dataclass
class Mark:
    """One layer of a drawing: marks of one `kind`, their data as equal-length
    columns, and which data column drives which visual channel."""

    kind: str
    data: Dict[str, Any]
    encoding: Dict[str, str] = field(default_factory=dict)


@dataclass
class Drawing:
    """What a view returns: a declarative drawing, not pixels.

    `marks` are what is drawn. `figures` are the numbers it states in words.
    `gaps` are what it could not draw from this state, each a `couldnt_check`
    reason; a name is a figure or a gap, never both. `draw` fills in `params`,
    `reads`, `source` and `epsilon`, so a view cannot misstate them.

    `panels` are figures that exist only at a simulated epsilon, each with a
    `status`: `SIMULATED`, with its `figures`, or `NOT_SIMULATED`, with the
    simulated epsilons, the cost in minutes and the action to run one. `draw`
    checks every panel against the state it was drawn from.
    """

    view: str
    marks: List[Mark]
    figures: Dict[str, Any]
    gaps: Dict[str, str] = field(default_factory=dict)
    panels: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    reads: List[str] = field(default_factory=list)
    source: Dict[str, Any] = field(default_factory=dict)
    epsilon: str = ""

    def as_dict(self):
        return _jsonable({
            "view": self.view, "params": self.params, "source": self.source,
            "reads": self.reads, "on_epsilon": self.epsilon,
            "figures": self.figures, "gaps": self.gaps, "panels": self.panels,
            "notes": self.notes,
            "marks": [{"kind": m.kind, "encoding": m.encoding,
                       "data": m.data} for m in self.marks]})


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    return o


class View:
    """Subclass, set `name` and `reads`, implement `render(state)`."""

    name = ""
    reads = ()

    def params(self):
        return {}

    def render(self, state):                          # pragma: no cover
        raise NotImplementedError


def draw(view, header, columns):
    """Draw `view` over one state. The only way a drawing is made."""
    state = StateColumns(header, columns, view.reads)
    d = view.render(state)
    if not isinstance(d, Drawing):
        raise ContractError(f"{view.name}: render returned "
                            f"{type(d).__name__}, not a Drawing")
    if d.view != view.name:
        raise ContractError(f"{view.name}: drawing names view {d.view!r}")
    for m in d.marks:
        if m.kind not in MARK_KINDS:
            raise ContractError(f"{view.name}: unknown mark kind {m.kind!r}")
        lengths = {len(v) for v in m.data.values()}
        if len(lengths) > 1:
            raise ContractError(f"{view.name}: a {m.kind} mark's columns have "
                                f"different lengths {sorted(lengths)}")
        unbound = sorted(set(m.encoding.values()) - set(m.data))
        if unbound:
            raise ContractError(f"{view.name}: a {m.kind} mark encodes "
                                f"columns it does not carry: {unbound}")
    both = sorted(set(d.figures) & set(d.gaps))
    if both:
        raise ContractError(f"{view.name}: {both} is both a figure and a gap")
    for name, reason in d.gaps.items():
        if not str(reason).startswith(COULDNT_CHECK):
            raise ContractError(f"{view.name}: gap {name!r} is not a "
                                f"{COULDNT_CHECK} reason")
    d.params = dict(view.params())
    d.reads = sorted(state.read)
    d.source = {k: header.get(k) for k in ("family", "config_label",
                                           "state_version", "n_base",
                                           "n_queries")}
    d.epsilon = on_epsilon(d.reads)
    _check_panels(view, d, header)
    return d


def _check_panels(view, d, header):
    """Every panel is simulated at this state's epsilon, or says it is not.

    A simulated panel must carry figures, and only for the epsilon its state
    was simulated at: figures for any other epsilon would be interpolation. A
    not-simulated panel must carry no figures, must name the epsilon asked
    for, the epsilons that were simulated, the cost in minutes and the action
    that would simulate it -- a blank panel is not allowed -- and its drawing
    must not have read any column that epsilon rebuilds.
    """
    state_eps = (header.get("assignment") or {}).get("epsilon")
    for name, panel in d.panels.items():
        where = f"{view.name}: panel {name!r}"
        status = panel.get("status")
        if status == SIMULATED:
            if not panel.get("figures"):
                raise ContractError(f"{where} is {SIMULATED} and empty; a "
                                    "panel is never blank")
            if state_eps is not None and not same_epsilon(
                    panel.get("epsilon"), state_eps):
                raise ContractError(
                    f"{where} shows figures for epsilon "
                    f"{panel.get('epsilon')} from a state simulated at "
                    f"{state_eps}; that is interpolation")
        elif status == NOT_SIMULATED:
            if panel.get("figures"):
                raise ContractError(f"{where} is {NOT_SIMULATED!r} and still "
                                    "carries figures; it is never "
                                    "interpolated")
            for key in ("epsilon", "simulated_epsilons", "cost_minutes",
                        "action"):
                if panel.get(key) in (None, "", [], {}):
                    raise ContractError(f"{where} is {NOT_SIMULATED!r} with "
                                        f"no {key}; it is never blank")
            if same_epsilon(panel["epsilon"], state_eps):
                raise ContractError(
                    f"{where} says {NOT_SIMULATED!r} at {panel['epsilon']}, "
                    "the epsilon this state was simulated at")
            rebuilt = sorted(c for c in d.reads
                             if ON_EPSILON.get(c) == REBUILD)
            if rebuilt:
                raise ContractError(
                    f"{where} is {NOT_SIMULATED!r}, yet the drawing read "
                    f"columns epsilon rebuilds: {rebuilt}")
        else:
            raise ContractError(f"{where} has status {status!r}; it must be "
                                f"{SIMULATED!r} or {NOT_SIMULATED!r}")
