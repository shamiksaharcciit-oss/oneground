"""The lab's rendering contract, tested (tasks 021, 021b, 021c and 023).

**Synthetic throughout**, except the two tests that read the shipped view
modules and the subprocess test. The published figures are checked from real
state by `corpora/render_from_state.py` and task 020's acceptance comparison.

The properties:

    guard      every view module is clean, and each kind of violation is caught
    contract   a view gets declared columns only, never a vector, never a
               writable array; a malformed drawing is refused
    views      the ground and query trace draw the right figures from a state
               small enough to count by hand, and a missing column is a gap
    epsilon    every state column says what moving epsilon does to it; the
               ground recounts continuously; recall is drawn only at an
               epsilon that was simulated, and between them the panel says so
               -- never interpolated, never blank -- while the ground's
               caption says it too
    ties       tied scores merge one way in simulate and in the view
    hygiene    drawing loads no model family, faiss or measuring code

    python oneground/lab/test_lab.py
    python -m pytest oneground/lab/test_lab.py
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(
    __file__)), "..", ".."))
sys.path.insert(0, REPO)

from oneground.lab import contract, guard               # noqa: E402
from oneground.lab.views import (VIEWS, GroundView,      # noqa: E402
                                 QueryIndexView, QueryTraceView)

S = contract.state_format()
SIMULATED, NOT_SIMULATED = contract.SIMULATED, contract.NOT_SIMULATED
EpsilonSet = contract.EpsilonSet


def _label(eps):
    return f"semantic_sharded[centroids=4,epsilon={eps},probe=2]"


def _synthetic(tmp, eps=0.2):
    """A semantic_sharded state of 12 vectors, 4 regions, 3 queries, built so
    every figure can be counted by hand.

    Vector v's home is region v % 4 and its second-nearest is (v + 1) % 4.
    Even vectors sit 1.15x as far from their second centroid as their first,
    odd ones 1.3x: at epsilon 0.2 the even six are copied twice and the odd
    six once (at 0.1, none is copied), and at the 1.20 crispness threshold
    only the odd six are crisp. Written to `tmp/synthetic.state.npz`.
    """
    n, r, cap = 12, 4, 2
    near = np.stack([np.arange(n) % r, (np.arange(n) + 1) % r],
                    axis=1).astype(np.int32)
    d0 = np.linspace(1.0, 2.0, n).astype(np.float32)
    ratio = np.array([1.15, 1.3] * 6, dtype=np.float32)
    dist = np.stack([d0, d0 * ratio], axis=1).astype(np.float32)
    within = dist <= dist[:, [0]] * (1 + eps)
    within[:, 0] = True
    assignment = S.AssignmentState(
        home_region=near[:, 0].copy(),
        copy_count=within.sum(axis=1).astype(np.uint8),
        copy_set=np.where(within, near, -1).astype(np.int32),
        centroid_dist=dist, max_assign=cap, epsilon=eps,
        nearest_region=near)
    params = {"centroids": 4, "epsilon": eps, "probe": 2}
    partition = S.PartitionState(
        family="semantic_sharded", kind="kmeans", seed=1, params=params,
        region_ids=np.arange(r, dtype=np.int32),
        region_sizes=np.bincount(near[:, 0], minlength=r).astype(np.int64),
        centroids=np.zeros((r, 8), dtype=np.float32), distance=S.DISTANCE,
        kmeans_niter=20)
    probed = np.array([[0, 1], [1, 2], [3, 0]], dtype=np.int32)
    route = S.RouteState(
        scored_region=probed.copy(),
        scored_dist=np.array([[0.5, 0.6], [0.4, 0.9], [0.3, 0.35]],
                             dtype=np.float32),
        probed_region=probed,
        probe_reason=np.array([[0, 1]] * 3, dtype=np.uint8))
    truth = np.array([[0, 1, 4], [5, 2, 6], [3, 7, 11]], dtype=np.int64)
    per_query = [
        (np.array([0, 4, 8]), np.array([0, 0, 0]), np.array([0.9, 0.8, 0.1])),
        (np.array([5, 1]), np.array([1, 1]), np.array([0.9, 0.5])),
        (np.array([3, 7, 11, 0]), np.array([3, 3, 3, 0]),
         np.array([0.9, 0.8, 0.7, 0.2])),
    ]
    candidates = S.build_candidates(per_query, truth, 3)
    state = S.ModelState(
        family="semantic_sharded", config_label=_label(eps), params=params,
        seed=1, n_base=n, n_queries=3, dim=8,
        partition=partition, assignment=assignment, route=route,
        candidates=candidates,
        load=S.build_load(partition.region_ids, assignment, route,
                          candidates))
    assert S.contract_violations(state) == [], S.contract_violations(state)
    path = S.write_state(os.path.join(tmp, "synthetic.state.npz"), state)
    return S.read_state(path)


def _state(eps=0.2):
    with tempfile.TemporaryDirectory() as tmp:
        return _synthetic(tmp, eps)


# ------------------------------------------------------------------ guard
def test_every_view_module_passes_the_guard():
    """Not synthetic: the shipped view modules. A view that measures fails
    the build here."""
    found = guard.check_views()
    assert found == {}, "view modules break the rendering contract:\n" + \
        "\n".join(f"  {m}:{line}  {rule}  {detail}"
                  for m, v in sorted(found.items())
                  for line, rule, detail in v)
    # __init__, ground, query_index, query_trace
    assert len(guard.view_modules()) >= 4


def test_the_guard_catches_each_kind_of_measuring_synthetic():
    cases = {
        "import numpy as np\ndef f(a, b):\n    return a @ b\n":
            "vector-arithmetic",
        "import numpy as np\ndef f(a, b):\n    return np.dot(a, b)\n":
            "vector-arithmetic",
        "import numpy as np\ndef f(a):\n    return np.linalg.norm(a)\n":
            "vector-arithmetic",
        "from numpy.linalg import norm\n": "vector-arithmetic",
        "import numpy as np\ndef f(a, b):\n    return np.einsum('ij,ij->i', a, b)\n":
            "vector-arithmetic",
        "import faiss\n": "import",
        "from scipy.spatial.distance import cdist\n": "import",
        "from sklearn.cluster import KMeans\n": "import",
        "from oneground.models import state\n": "import",
        "from ...models.semantic_sharded import model\n": "import",
        "from oneground.measures.crispness import centroid_dists\n": "import",
        "def f(state):\n    return state['partition.centroids']\n":
            "vector-data",
        "def f(s):\n    return s.centroids\n": "vector-data",
        "def f():\n    return open('base.bin', 'rb').read()\n": "file-io",
        "import numpy as np\ndef f():\n    return np.load('vectors.npy')\n":
            "file-io",
        "def f():\n    return __import__('faiss')\n": "dynamic-code",
        "import importlib\n": "dynamic-code",
        "def f(s):\n    return eval(s)\n": "dynamic-code",
    }
    for source, rule in cases.items():
        got = guard.violations(source)
        assert any(r == rule for _, r, _ in got), (source, got)


def test_the_guard_leaves_docstrings_and_ordinary_tallies_alone_synthetic():
    source = (
        '"""Draws centroids and vectors; never computes a dot product @ all."""\n'
        "import numpy as np\n"
        "from ..contract import Drawing, Mark, View\n"
        "def f(state):\n"
        '    """queries, embeddings, linalg: words, not code."""\n'
        "    copies = state['assignment.copy_count'].astype(np.int64)\n"
        "    return float(copies.sum() / len(copies)), "
        "int(np.percentile(copies, 99, method='lower'))\n")
    assert guard.violations(source) == [], guard.violations(source)


def test_a_new_file_in_the_views_package_is_read_synthetic():
    """Registered or not, a module sitting in views/ is a view module."""
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "sneaky.py"), "w", encoding="utf-8") as f:
            f.write("import numpy as np\ndef f(a, b):\n    return a @ b\n")
        saved = guard.VIEWS_DIR
        guard.VIEWS_DIR = tmp
        try:
            found = guard.check_views()
        finally:
            guard.VIEWS_DIR = saved
    assert "sneaky.py" in found, found


# --------------------------------------------------------------- contract
class _Reads(contract.View):
    name = "reads"

    def __init__(self, reads, column):
        self.reads, self.column = reads, column

    def render(self, state):
        state[self.column]
        return contract.Drawing(view=self.name, marks=[], figures={})


def test_a_view_is_never_handed_a_vector_column_synthetic():
    head, cols = _state()
    for reads in (("partition.centroids",), ("assignment.copy_count",)):
        try:
            contract.draw(_Reads(reads, "partition.centroids"), head, cols)
        except contract.VectorColumn:
            continue
        raise AssertionError(f"a vector column was handed over ({reads})")


def test_the_ground_is_refused_a_vector_column_at_run_time_synthetic():
    """Task 023: the ground recounts the closure, which is what centroids
    decide -- so the one view with a reason to want them must still be
    refused them, declared or not."""
    head, cols = _state()
    assert "partition.centroids" not in GroundView.reads

    class Declares(GroundView):
        reads = GroundView.reads + ("partition.centroids",)

    class Reaches(GroundView):
        def render(self, state):
            state["partition.centroids"]
            return super().render(state)

    for view in (Declares(), Reaches()):
        try:
            contract.draw(view, head, cols)
        except contract.VectorColumn:
            continue
        raise AssertionError(f"{type(view).__name__} got a vector column")


def test_a_view_cannot_read_what_it_did_not_declare_synthetic():
    head, cols = _state()
    try:
        contract.draw(_Reads(("assignment.copy_count",),
                             "assignment.home_region"), head, cols)
    except contract.UndeclaredColumn:
        return
    raise AssertionError("an undeclared column was read")


def test_the_state_a_view_is_handed_is_read_only_synthetic():
    head, cols = _state()

    class Writes(contract.View):
        name = "writes"
        reads = ("assignment.copy_count",)

        def render(self, state):
            state["assignment.copy_count"][0] = 4
            return contract.Drawing(view=self.name, marks=[], figures={})

    try:
        contract.draw(Writes(), head, cols)
    except ValueError:
        assert cols["assignment.copy_count"][0] == 2
        return
    raise AssertionError("a view wrote into the state")


def _refused(drawing, reads=(), head_cols=None, recounts=False):
    """Whether `draw` refuses `drawing`, returned by a view that declares and
    reads `reads`."""
    head, cols = head_cols or _state()

    class V(contract.View):
        name = "v"

        def render(self, state):
            for c in reads:
                state[c]
            return drawing
    V.reads = tuple(reads)
    V.recounts = recounts
    try:
        contract.draw(V(), head, cols)
    except contract.ContractError:
        return True
    return False


def test_a_malformed_drawing_is_refused_synthetic():
    D, M = contract.Drawing, contract.Mark
    assert _refused({"figures": {}})
    assert _refused(D(view="other", marks=[], figures={}))
    assert _refused(D(view="v", marks=[M("blob", data={})], figures={}))
    assert _refused(D(view="v", marks=[M("point", data={"a": [1, 2],
                                                        "b": [1]})],
                      figures={}))
    assert _refused(D(view="v", marks=[M("point", data={"a": [1]},
                                         encoding={"color": "b"})],
                      figures={}))
    assert _refused(D(view="v", marks=[], figures={"x": 1},
                      gaps={"x": "couldnt_check: both"}))
    assert _refused(D(view="v", marks=[], figures={},
                      gaps={"x": "unknown, probably fine"}))


# ------------------------------------------------------------------ views
def test_the_ground_view_tallies_the_state_synthetic():
    head, cols = _state()
    d = contract.draw(GroundView(), head, cols)
    f = d.figures
    assert f["copies_histogram"] == [6, 6], f
    assert f["copies_histogram_pct"] == [50.0, 50.0], f
    assert f["vectors_copied"] == 6
    assert f["storage_amplification"] == 1.5
    assert f["p99_copies"] == 2
    assert f["boundary_crispness"] == 0.5
    assert f["recounted_from_state"] is True
    assert f["vectors_held_total"] == 18
    assert "positions" in d.gaps
    points, bars = d.marks
    assert len(points.data["vector_id"]) == 12
    assert list(points.data["copy_count"]) == [2, 1] * 6
    # each region homes three vectors; the six even ones copy into region 1
    # or 3, so those two hold six each
    assert list(bars.data["vectors_held"]) == [3, 6, 3, 6], bars.data
    assert set(d.reads) <= set(GroundView.reads)
    assert d.epsilon == contract.RECOUNT
    assert d.source["config_label"] == _label(0.2)


def test_the_ground_recount_equals_the_state_it_was_emitted_from_synthetic():
    """Task 023: recounted at the state's own epsilon, the ground reproduces
    the copy counts and shard sizes that run emitted -- exactly."""
    for eps in (0.0, 0.1, 0.2, 0.5):
        head, cols = _state(eps)
        d = contract.draw(GroundView(), head, cols)
        points, bars = d.marks
        assert np.array_equal(points.data["copy_count"],
                              cols["assignment.copy_count"].astype(np.int64))
        assert np.array_equal(bars.data["vectors_held"],
                              cols["load.vectors_held"])


def test_the_ground_recounts_to_another_epsilon_synthetic():
    """Drawn from the 0.2 state at 0.1, the ground shows what the run at 0.1
    emitted: the closure follows from stored distances, not from the run."""
    at_02 = _state(0.2)
    at_01 = _state(0.1)
    eps = EpsilonSet.make(epsilon=0.1, simulated=[0.1, 0.2])
    recounted = contract.draw(GroundView(eps), *at_02)
    emitted = contract.draw(GroundView(), *at_01)
    for key in ("copies_histogram", "vectors_copied", "storage_amplification",
                "p99_copies", "vectors_held_total", "routing_ceiling_at_k"):
        assert recounted.figures[key] == emitted.figures[key], key
    assert np.array_equal(recounted.marks[0].data["copy_count"],
                          at_01[1]["assignment.copy_count"].astype(np.int64))
    assert recounted.figures["copies_histogram"] == [12, 0]
    # and the ground at 0.2 is the other closure, so the test is not vacuous
    assert contract.draw(GroundView(), *at_02) \
        .figures["copies_histogram"] == [6, 6]


def test_the_ground_states_in_its_caption_when_epsilon_was_not_simulated_synthetic():
    head, cols = _state()
    at = contract.draw(GroundView(EpsilonSet.make(
        epsilon=0.2, simulated=[0.1, 0.2])), head, cols)
    assert NOT_SIMULATED not in at.caption
    assert "recounted from state" in at.caption

    between = contract.draw(GroundView(EpsilonSet.make(
        epsilon=0.15, simulated=[0.1, 0.2])), head, cols)
    assert NOT_SIMULATED in between.caption
    assert "recount" in between.caption.lower()
    assert "recall" in between.caption.lower()
    assert between.figures["epsilon"] == 0.15


def test_the_contract_refuses_a_recount_that_hides_it_synthetic():
    """A recounting view must caption what it is showing, and at an epsilon
    nobody simulated the caption must say so."""
    D = contract.Drawing
    figures = {"epsilon": 0.15, "simulated_epsilons": [0.1, 0.2]}
    assert _refused(D(view="v", marks=[], figures=figures), recounts=True)
    assert _refused(D(view="v", marks=[], figures=figures,
                      caption="The ground at epsilon 0.15."), recounts=True)
    assert _refused(D(view="v", marks=[], figures=figures,
                      caption=f"The ground at 0.15, {NOT_SIMULATED}."),
                    recounts=True)
    assert not _refused(
        D(view="v", marks=[], figures=figures,
          caption=f"Recounted from state; {NOT_SIMULATED}."), recounts=True)
    assert not _refused(
        D(view="v", marks=[], figures={"epsilon": 0.2,
                                       "simulated_epsilons": [0.1, 0.2]},
          caption="Recounted from state at a simulated epsilon."),
        recounts=True)


def test_the_query_trace_view_draws_each_query_synthetic():
    head, cols = _state()
    # query: routed, outside, and in the recall panel: missed, answerable
    # from candidates alone, recall@3
    expect = {0: (0, 1, 1, False, 2 / 3), 1: (1, 2, 2, False, 1 / 3),
              2: (3, 0, 0, True, 1.0)}
    for q, (routed, outside, missed, from_candidates, recall) in \
            expect.items():
        d = contract.draw(QueryTraceView(q, k=3), head, cols)
        f = d.figures
        assert f["routed_region"] == routed, (q, f)
        assert f["outside_routed_region"] == outside, (q, f)
        assert d.gaps == {}, d.gaps
        panel = d.panels["recall"]
        assert panel["status"] == SIMULATED and panel["epsilon"] == 0.2
        pf = panel["figures"]
        assert pf["missed_by_route"] == missed, (q, pf)
        assert pf["answerable_from_candidates_alone"] is from_candidates, q
        assert abs(pf["recall_at_k"] - recall) < 1e-12, (q, pf)
        assert d.epsilon == contract.REBUILD, "it read what shards returned"


def test_a_state_without_true_ids_is_a_gap_not_a_guess_synthetic():
    head, cols = _state()
    del cols["candidates.true_ids"]
    d = contract.draw(QueryTraceView(0, k=3), head, cols)
    assert "outside_routed_region" in d.gaps
    assert d.gaps["outside_routed_region"].startswith(contract.COULDNT_CHECK)
    assert d.figures["outside_routed_region_lower_bound"] == 0
    d2 = contract.draw(QueryTraceView(2, k=3), head, cols)
    assert d2.figures["outside_routed_region"] == 0, "all three were returned"
    # between simulated epsilons the candidates cannot stand in for them
    d3 = contract.draw(QueryTraceView(
        0, k=3, eps=EpsilonSet.make(epsilon=0.15)), head, cols)
    assert d3.gaps["true_neighbours"].startswith(contract.COULDNT_CHECK)
    assert d3.panels["recall"]["status"] == NOT_SIMULATED
    # the ground still recounts the geometry there, and reports the ceiling
    # as a gap rather than inventing one without true neighbours
    g = contract.draw(GroundView(EpsilonSet.make(epsilon=0.15)), head, cols)
    assert g.figures["copies_histogram"] == [6, 6]
    assert g.gaps["routing_ceiling_at_k"].startswith(contract.COULDNT_CHECK)


def test_every_view_declares_only_state_columns_and_no_vectors():
    known = set(S._MEANINGS)
    for name, cls in VIEWS.items():
        assert set(cls.reads) <= known, (name, set(cls.reads) - known)
        assert not set(cls.reads) & contract.VECTOR_COLUMNS, name


# ---------------------------------------------------------------- epsilon
def test_every_state_column_says_what_moving_epsilon_does_to_it():
    assert set(contract.ON_EPSILON) == set(S._MEANINGS), \
        set(contract.ON_EPSILON) ^ set(S._MEANINGS)
    assert contract.on_epsilon(["route.probed_region"]) == contract.UNCHANGED
    assert contract.on_epsilon(["route.probed_region",
                                "assignment.copy_count"]) == contract.RECOUNT
    assert contract.on_epsilon(["assignment.copy_count",
                                "candidates.cand_id"]) == contract.REBUILD


def test_one_epsilon_set_answers_for_both_views_synthetic():
    """Task 023: the ground and the query trace take the same EpsilonSet, so
    they cannot disagree about which epsilons were simulated."""
    head, cols = _state()
    eps = EpsilonSet.make(epsilon=0.15, simulated=[0.1, 0.2], cost=_COST,
                          action=_ACTION)
    g = contract.draw(GroundView(eps), head, cols)
    t = contract.draw(QueryTraceView(0, k=3, eps=eps), head, cols)
    assert g.figures["simulated_epsilons"] == t.figures["simulated_epsilons"]
    assert g.figures["epsilon"] == t.figures["epsilon"] == 0.15
    assert NOT_SIMULATED in g.caption
    assert t.panels["recall"]["status"] == NOT_SIMULATED
    assert t.panels["recall"]["simulated_epsilons"] == \
        g.figures["simulated_epsilons"]


_COST = {"low": 3.2, "high": 6.6, "basis": "measured"}
_ACTION = {"kind": "simulate", "epsilon": 0.15,
           "command": "oneground simulate requirements.yaml --emit-state"}


def test_between_simulated_epsilons_recall_is_not_drawn_synthetic():
    """The trace at an epsilon nobody simulated: every geometric readout,
    no recall, no candidates, no missed neighbours -- and a panel that says
    so, with the cost and the action, rather than a blank."""
    head, cols = _state()
    at = contract.draw(QueryTraceView(0, k=3), head, cols)
    d = contract.draw(QueryTraceView(0, k=3, eps=EpsilonSet.make(
        epsilon=0.15, simulated=[0.1, 0.2], cost=_COST, action=_ACTION)),
        head, cols)
    panel = d.panels["recall"]
    assert panel["status"] == NOT_SIMULATED
    assert panel["epsilon"] == 0.15
    assert panel["simulated_epsilons"] == [0.1, 0.2]
    assert panel["cost_minutes"] == _COST
    assert panel["action"] == _ACTION
    assert "figures" not in panel
    for key in ("routed_region", "outside_routed_region", "probed_regions"):
        assert d.figures[key] == at.figures[key], key
    drawn = json.dumps(d.as_dict())
    for leak in ("recall_at_k", "missed_by_route", "returned_top_k",
                 "answerable_from_candidates_alone"):
        assert leak not in drawn, f"{leak} drawn at an unsimulated epsilon"
    assert not [c for c in d.reads
                if contract.ON_EPSILON[c] == contract.REBUILD], d.reads
    assert d.epsilon == contract.UNCHANGED


def test_the_recall_panel_is_never_blank_synthetic():
    """With no declared cost or action, the panel still carries both: a
    `couldnt_check` cost and a runnable action."""
    head, cols = _state()
    d = contract.draw(QueryTraceView(
        1, k=3, eps=EpsilonSet.make(epsilon=0.05)), head, cols)
    panel = d.panels["recall"]
    assert panel["status"] == NOT_SIMULATED
    assert panel["cost_minutes"].startswith(contract.COULDNT_CHECK)
    assert panel["action"]["kind"] == "simulate"
    assert panel["action"]["epsilon"] == 0.05
    assert panel["action"]["params"]["epsilon"] == 0.05


def test_a_simulated_epsilon_is_drawn_from_its_own_state_synthetic():
    """Epsilon 0.1 was simulated; its recall is in the 0.1 state. Asked over
    the 0.2 state, the view refuses rather than drawing anything for 0.1."""
    head, cols = _state()
    try:
        contract.draw(QueryTraceView(0, k=3, eps=EpsilonSet.make(
            epsilon=0.1, simulated=[0.1, 0.2])), head, cols)
    except ValueError as e:
        assert "0.1" in str(e)
        return
    raise AssertionError("recall for a simulated epsilon was drawn from a "
                         "different state")


def test_the_contract_refuses_interpolated_or_blank_recall_synthetic():
    D = contract.Drawing

    def drawing(panel):
        return D(view="v", marks=[], figures={}, panels={"recall": panel})

    not_sim = {"status": NOT_SIMULATED, "epsilon": 0.15,
               "simulated_epsilons": [0.2], "cost_minutes": _COST,
               "action": _ACTION}
    # well-formed panels are drawn
    assert not _refused(drawing(dict(not_sim)),
                        reads=("route.probed_region",))
    assert not _refused(drawing({"status": SIMULATED, "epsilon": 0.2,
                                 "figures": {"recall_at_k": 0.5}}),
                        reads=("candidates.cand_id",))
    # interpolation: figures for an epsilon this state was not simulated at
    assert _refused(drawing({"status": SIMULATED, "epsilon": 0.15,
                             "figures": {"recall_at_k": 0.5}}))
    assert _refused(drawing({**not_sim, "figures": {"recall_at_k": 0.6}}))
    # blank
    assert _refused(drawing({"status": SIMULATED, "epsilon": 0.2,
                             "figures": {}}))
    for key in ("epsilon", "simulated_epsilons", "cost_minutes", "action"):
        assert _refused(drawing({k: v for k, v in not_sim.items()
                                 if k != key})), key
    # "not simulated" at the epsilon the state was simulated at
    assert _refused(drawing({**not_sim, "epsilon": 0.2}))
    # "not simulated", but drawn from what the shards returned
    assert _refused(drawing(dict(not_sim)), reads=("candidates.cand_id",))
    # a status that is neither
    assert _refused(drawing({**not_sim, "status": "pending"}))


def _run(root, name, eps, build_query_seconds, requirements):
    """A run directory as simulate --emit-state leaves it: state/ with the
    state and state_info.json, and simulate_info.json beside it."""
    state_dir = os.path.join(root, name, "state")
    os.makedirs(state_dir)
    _synthetic(state_dir, eps)
    with open(os.path.join(state_dir, "state_info.json"), "w",
              encoding="utf-8") as f:
        json.dump({"configurations": [{"family": "semantic_sharded",
                                       "config_label": _label(eps),
                                       "file": "synthetic.state.npz"}]}, f)
    build, query = build_query_seconds
    with open(os.path.join(root, name, "simulate_info.json"), "w",
              encoding="utf-8") as f:
        json.dump({"timings": {_label(eps): {"build_seconds": build,
                                             "query_seconds": query}},
                   "requirements_file": {"path": requirements}}, f)
    return state_dir, os.path.join(state_dir, "synthetic.state.npz")


def _renderer():
    spec = importlib.util.spec_from_file_location(
        "render_from_state_under_test",
        os.path.join(REPO, "corpora", "render_from_state.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_renderer_draws_recall_only_from_the_state_simulated_at_it_synthetic():
    """`corpora/render_from_state.py` over a declared set of two runs:
    epsilon 0.1 is drawn from the 0.1 run; 0.15, simulated by neither, gets
    the base state's geometry and a panel with the measured cost and the
    command -- and the same routed regions and outside counts."""
    R = _renderer()
    with tempfile.TemporaryDirectory() as tmp:
        _, base = _run(tmp, "a", 0.2, (240.0, 60.0), "requirements.a.yaml")
        b_dir, b_path = _run(tmp, "b", 0.1, (90.0, 30.0),
                             "requirements.b.yaml")

        at_01 = R.plan(base, [b_dir], "semantic_sharded", 0.1)
        assert at_01["trace_path"] == b_path
        assert at_01["simulated"] == [0.1, 0.2]
        _, q01 = R.draw_query(at_01, 0, k=3)
        assert q01["recall_panel"]["status"] == SIMULATED
        assert q01["recall_panel"]["epsilon"] == 0.1

        between = R.plan(base, [b_dir], "semantic_sharded", 0.15)
        assert between["trace_path"] == base
        _, q015 = R.draw_query(between, 0, k=3)
        panel = q015["recall_panel"]
        assert panel["status"] == NOT_SIMULATED
        assert panel["simulated_epsilons"] == [0.1, 0.2]
        assert (panel["cost_minutes"]["low"],
                panel["cost_minutes"]["high"]) == (2.0, 5.0)
        assert panel["action"]["command"] == \
            "oneground simulate requirements.a.yaml --emit-state"
        assert panel["action"]["grid"]["semantic_sharded"]["epsilon"] == \
            [0.15]
        for leak in ("recall_at_k", "missed_by_route",
                     "answerable_from_candidates_alone"):
            assert leak not in q015, leak
        for entry in q015["true_neighbours"]:
            assert "missed_by_route" not in entry

        every_between = R.draw_every_query(between, k=3)
        every_base = R.draw_every_query(R.plan(base, [b_dir],
                                               "semantic_sharded"), k=3)
        assert every_between["recall_panel_status"] == NOT_SIMULATED
        assert "recall_at_k_mean" not in every_between
        assert every_base["recall_panel_status"] == SIMULATED
        assert abs(every_base["recall_at_k_mean"] - 6 / 9) < 1e-12
        for key in ("routed_region", "outside_routed_region"):
            assert every_between[key] == every_base[key], key


def test_the_renderer_recounts_the_ground_as_epsilon_moves_synthetic():
    """Task 023: the ground follows the control continuously, from the base
    state, and captions an unsimulated epsilon. Both views are drawn with the
    one EpsilonSet the plan built."""
    R = _renderer()
    with tempfile.TemporaryDirectory() as tmp:
        _, base = _run(tmp, "a", 0.2, (240.0, 60.0), "requirements.a.yaml")
        b_dir, _ = _run(tmp, "b", 0.1, (90.0, 30.0), "requirements.b.yaml")

        at_02 = R.plan(base, [b_dir], "semantic_sharded")
        at_01 = R.plan(base, [b_dir], "semantic_sharded", 0.1)
        between = R.plan(base, [b_dir], "semantic_sharded", 0.15)
        below = R.plan(base, [b_dir], "semantic_sharded", 0.05)

        g02 = R.draw_ground(at_02)[1]
        g01 = R.draw_ground(at_01)[1]
        g015 = R.draw_ground(between)[1]
        g005 = R.draw_ground(below)[1]
        # the even six sit 1.15x out: copied at 0.15 and 0.2, not at 0.1 or
        # 0.05, so the ground moves with the control rather than with a run
        assert g02["copies_histogram"] == [6, 6]
        assert g015["copies_histogram"] == [6, 6], "recounted at 0.15"
        assert g01["copies_histogram"] == [12, 0], "recounted at 0.1"
        assert g005["copies_histogram"] == [12, 0], "recounted at 0.05"
        assert g01["epsilon"] == 0.1 and g015["epsilon"] == 0.15
        assert NOT_SIMULATED not in g01["caption"]
        assert NOT_SIMULATED in g015["caption"]
        assert NOT_SIMULATED in g005["caption"]
        # one source: the ground and the trace report the same set
        _, trace = R.draw_query(between, 0, k=3)
        assert g015["simulated_epsilons"] == \
            trace["recall_panel"]["simulated_epsilons"]
        assert between["eps"].simulated == (0.1, 0.2)


# ------------------------------------------------------------------- ties
def _tied(tmp, n=400, n_q=3, per_shard=150, copies=30):
    """A state whose candidates tie on score everywhere (task 021c).

    Every vector's score is one of three values, fixed per vector, so a vector
    returned by two shards -- a copy -- carries the same score both times, as
    a real copy does, and every k boundary cuts through a run of equal
    scores. Each query takes `per_shard` candidates from each of two shards,
    `copies` of the second shard's being vectors the first also returned.
    """
    rng = np.random.default_rng(21)
    r = 4
    home = (np.arange(n) % r).astype(np.int32)
    score_of = rng.choice(np.array([0.25, 0.5, 0.75], dtype=np.float32),
                          size=n)
    assignment = S.AssignmentState(
        home_region=home, copy_count=np.ones(n, dtype=np.uint8),
        copy_set=home.reshape(-1, 1).copy(),
        centroid_dist=np.ones((n, 1), dtype=np.float32), max_assign=1,
        epsilon=0.2, nearest_region=home.reshape(-1, 1).copy())
    params = {"centroids": r, "epsilon": 0.2, "probe": 2}
    partition = S.PartitionState(
        family="semantic_sharded", kind="kmeans", seed=1, params=params,
        region_ids=np.arange(r, dtype=np.int32),
        region_sizes=np.bincount(home, minlength=r).astype(np.int64),
        centroids=np.zeros((r, 8), dtype=np.float32), distance=S.DISTANCE,
        kmeans_niter=20)
    probed = np.tile(np.array([[0, 1]], dtype=np.int32), (n_q, 1))
    route = S.RouteState(
        scored_region=probed.copy(),
        scored_dist=np.ones(probed.shape, dtype=np.float32),
        probed_region=probed,
        probe_reason=np.tile(np.array([[0, 1]], dtype=np.uint8), (n_q, 1)))
    per_query, truth = [], []
    for _ in range(n_q):
        first = rng.choice(n, size=per_shard, replace=False)
        again = rng.choice(first, size=copies, replace=False)
        rest = rng.choice(np.setdiff1d(np.arange(n), first),
                          size=per_shard - copies, replace=False)
        second = rng.permutation(np.concatenate([again, rest]))
        ids = np.concatenate([first, second]).astype(np.int64)
        shards = np.array([0] * per_shard + [1] * per_shard, dtype=np.int32)
        per_query.append((ids, shards, score_of[ids]))
        truth.append(np.argsort(-score_of, kind="stable")[:100])
    candidates = S.build_candidates(per_query,
                                    np.array(truth, dtype=np.int64), 100)
    state = S.ModelState(
        family="semantic_sharded", config_label=_label(0.2), params=params,
        seed=1, n_base=n, n_queries=n_q, dim=8, partition=partition,
        assignment=assignment, route=route, candidates=candidates,
        load=S.build_load(partition.region_ids, assignment, route,
                          candidates))
    assert S.contract_violations(state) == [], S.contract_violations(state)
    path = S.write_state(os.path.join(tmp, "tied.state.npz"), state)
    return S.read_state(path)


def _merge_spec(ids, scores, k):
    """How candidates merge, written out: the first occurrence of each id,
    best score first, and equal scores in the order the shards' results were
    concatenated. Nothing about it depends on a sort's internals."""
    seen, out = set(), []
    for j in sorted(range(len(ids)), key=lambda j: (-float(scores[j]), j)):
        vid = int(ids[j])
        if vid < 0 or vid in seen:
            continue
        seen.add(vid)
        out.append(vid)
        if len(out) == k:
            break
    return out


def test_tied_scores_merge_one_way_in_simulate_and_in_the_view_synthetic():
    """Task 021c. `base.merge_candidates` produces the ids simulate's recall
    is counted from; the query-trace view recounts recall from state. On
    scores that tie across the k boundary, both must pick exactly the ids
    `_merge_spec` picks. A merge whose ties fall however the sort happens to
    leave them is a receipt that can change between two runs of the same
    code, which is the class of defect task 012b closed for the faiss build.
    """
    # imported here, not at the top: the hygiene test imports this module in
    # a clean process and must not find the model package loaded
    from oneground.models.base import merge_candidates

    with tempfile.TemporaryDirectory() as tmp:
        head, cols = _tied(tmp)
    offsets = cols["candidates.offsets"]
    boundary_ties = 0
    for q in range(int(head["n_queries"])):
        lo, hi = int(offsets[q]), int(offsets[q + 1])
        ids = cols["candidates.cand_id"][lo:hi]
        scores = cols["candidates.cand_score"][lo:hi]
        shard = cols["candidates.cand_shard"][lo:hi]
        by_id = {}
        for vid, s in zip(ids.tolist(), scores.tolist()):
            by_id.setdefault(vid, s)
        ranked = sorted(by_id.values(), reverse=True)
        for k in (1, 10, 50, 100):
            spec = _merge_spec(ids, scores, k)
            # split by shard, as a family calls it
            merged, _ = merge_candidates(
                [ids[shard == 0], ids[shard == 1]],
                [scores[shard == 0], scores[shard == 1]], k)
            assert merged.tolist() == spec, (
                f"merge_candidates breaks tied scores differently from the "
                f"spec (query {q}, k {k})")
            drawn = contract.draw(QueryTraceView(q, k=k), head, cols) \
                .panels["recall"]["figures"]["returned_top_k"]
            assert drawn == spec, (f"the view breaks tied scores differently "
                                   f"from the spec (query {q}, k {k})")
            boundary_ties += ranked[k - 1] == ranked[k]
    assert boundary_ties > 0, ("no k boundary fell inside a run of tied "
                               "scores; the test would prove nothing")


# ------------------------------------------------------------ query index
def test_the_query_index_states_what_the_trace_states_for_every_query_synthetic():
    """Task 025. The picker lists every query by the query index's rows; the
    trace draws one. Drawn at a simulated and at an unsimulated epsilon, each
    row must equal the trace drawn for that query, figure for figure, or the
    list would send a person to a query that is not what it said.

    By hand, at ratio 1.17: query 2 scores 0.30 and 0.35 (d2/d1 1.167), so it
    alone is ambiguous; queries 0 (1.2) and 1 (2.25) are not. Query 0's true
    neighbours 0, 1, 4 against its merged top three 0, 4, 8: found, not
    found, found.
    """
    head, cols = _state(0.2)
    for eps in (EpsilonSet.make(epsilon=0.2, simulated=[0.1, 0.2]),
                EpsilonSet.make(epsilon=0.15, simulated=[0.1, 0.2],
                                cost={"low": 1.0, "high": 2.0, "basis": "b"},
                                action={"command": "oneground simulate x"})):
        index = contract.draw(QueryIndexView(k=3, eps=eps, ambiguity=1.17),
                              head, cols)
        row = index.marks[0].data
        panel = index.panels["recall"]
        simulated = panel["status"] == SIMULATED
        assert simulated == (eps.epsilon == 0.2)
        for q in range(3):
            t = contract.draw(QueryTraceView(q, k=3, eps=eps, ambiguity=1.17),
                              head, cols)
            f = t.figures
            assert row["routed_region"][q] == f["routed_region"], q
            assert row["true_neighbours_located"][q] == \
                f["true_neighbours_located"], q
            assert row["outside_routed_region"][q] == \
                f.get("outside_routed_region"), q
            assert row["distance_ratio"][q] == f["distance_ratio"], q
            assert row["ambiguous"][q] == f["ambiguous"], q
            if simulated:
                tf = t.panels["recall"]["figures"]
                assert panel["figures"]["hits"][q] == tf["hits"], q
                assert panel["figures"]["missed_by_route"][q] == \
                    tf["missed_by_route"], q
            else:
                assert t.panels["recall"]["status"] == NOT_SIMULATED
                assert "figures" not in panel
                assert panel["cost_minutes"] == eps.cost
        assert row["ambiguous"] == [False, False, True]
        assert index.figures["ambiguous_queries"] == 1

    t0 = contract.draw(QueryTraceView(0, k=3, ambiguity=1.17), head, cols)
    assert t0.panels["recall"]["figures"]["found_by_rank"] == \
        [True, False, True]
    assert t0.figures["second_region"] == 1


def test_an_undeclared_ambiguity_is_a_gap_not_a_guess_synthetic():
    """A run whose characterization declares no ratio: neither the trace nor
    the index calls a query ambiguous, and both say why."""
    head, cols = _state(0.2)
    reason = f"{contract.COULDNT_CHECK}: no ratio declared"
    t = contract.draw(QueryTraceView(0, k=3, ambiguity=reason), head, cols)
    i = contract.draw(QueryIndexView(k=3, ambiguity=reason), head, cols)
    for d in (t, i):
        assert d.gaps["ambiguous"] == reason
        assert "ambiguous" not in d.figures
    assert "ambiguous" not in i.marks[0].data
    plain = contract.draw(QueryTraceView(0, k=3), head, cols)
    assert "ambiguous" not in plain.figures and "ambiguous" not in plain.gaps


# ---------------------------------------------------------------- hygiene
def test_drawing_loads_no_model_family_or_measuring_code():
    """Not synthetic: a clean process draws both views and is then asked what
    it imported."""
    code = (
        "import sys, tempfile\n"
        f"sys.path.insert(0, {REPO!r})\n"
        "from oneground.lab import contract\n"
        "from oneground.lab import test_lab as T\n"
        "from oneground.lab.views import (GroundView, QueryIndexView, "
        "QueryTraceView)\n"
        "with tempfile.TemporaryDirectory() as tmp:\n"
        "    head, cols = T._synthetic(tmp)\n"
        "eps = contract.EpsilonSet.make(epsilon=0.15, simulated=[0.2])\n"
        "contract.draw(GroundView(), head, cols)\n"
        "contract.draw(GroundView(eps), head, cols)\n"
        "contract.draw(QueryTraceView(1, k=3), head, cols)\n"
        "contract.draw(QueryTraceView(1, k=3, eps=eps), head, cols)\n"
        "contract.draw(QueryIndexView(k=3, ambiguity=1.1), head, cols)\n"
        "contract.draw(QueryIndexView(k=3, eps=eps, ambiguity=1.1), head, "
        "cols)\n"
        "bad = ('faiss', 'sklearn', 'scipy', 'torch', 'umap', "
        "'oneground.models', 'oneground.measures', 'oneground.truth', "
        "'oneground.simulate', 'oneground.characterize')\n"
        "loaded = sorted(m for m in sys.modules if any(m == b or "
        "m.startswith(b + '.') for b in bad))\n"
        "print('LOADED', loaded)\n"
        "sys.exit(1 if loaded else 0)\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=300, cwd=REPO)
    assert r.returncode == 0, r.stdout + r.stderr


def _main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
