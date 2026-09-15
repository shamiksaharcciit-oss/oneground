"""The lab's rendering contract, tested (task 021).

**Synthetic throughout**, except the two tests that read the shipped view
modules and the subprocess test. The published figures are checked from real
state by `corpora/render_from_state.py` and task 020's acceptance comparison.

The properties:

    guard      every view module is clean, and each kind of violation is caught
    contract   a view gets declared columns only, never a vector, never a
               writable array; a malformed drawing is refused
    views      the ground and query trace draw the right figures from a state
               small enough to count by hand, and a missing column is a gap
    epsilon    every state column says what moving epsilon does to it
    hygiene    drawing loads no model family, faiss or measuring code

    python oneground/lab/test_lab.py
    python -m pytest oneground/lab/test_lab.py
"""

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
                                 QueryTraceView)

S = contract.state_format()


def _synthetic(tmp):
    """A semantic_sharded state of 12 vectors, 4 regions, 3 queries, built so
    every figure can be counted by hand.

    Vector v's home is region v % 4 and its second-nearest is (v + 1) % 4.
    Even vectors sit 1.1x as far from their second centroid as their first,
    odd ones 1.3x: at epsilon 0.2 the even six are copied twice and the odd
    six once, and at the 1.20 crispness threshold only the odd six are crisp.
    """
    n, r, cap, eps = 12, 4, 2, 0.2
    near = np.stack([np.arange(n) % r, (np.arange(n) + 1) % r],
                    axis=1).astype(np.int32)
    d0 = np.linspace(1.0, 2.0, n).astype(np.float32)
    ratio = np.array([1.1, 1.3] * 6, dtype=np.float32)
    dist = np.stack([d0, d0 * ratio], axis=1).astype(np.float32)
    within = dist <= dist[:, [0]] * (1 + eps)
    within[:, 0] = True
    assignment = S.AssignmentState(
        home_region=near[:, 0].copy(),
        copy_count=within.sum(axis=1).astype(np.uint8),
        copy_set=np.where(within, near, -1).astype(np.int32),
        centroid_dist=dist, max_assign=cap, epsilon=eps,
        nearest_region=near)
    partition = S.PartitionState(
        family="semantic_sharded", kind="kmeans", seed=1, params={},
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
        family="semantic_sharded", config_label="semantic_sharded[synthetic]",
        params={}, seed=1, n_base=n, n_queries=3, dim=8,
        partition=partition, assignment=assignment, route=route,
        candidates=candidates,
        load=S.build_load(partition.region_ids, assignment, route,
                          candidates))
    assert S.contract_violations(state) == [], S.contract_violations(state)
    path = S.write_state(os.path.join(tmp, "synthetic.state.npz"), state)
    return S.read_state(path)


def _state():
    with tempfile.TemporaryDirectory() as tmp:
        return _synthetic(tmp)


# ------------------------------------------------------------------ guard
def test_every_view_module_passes_the_guard():
    """Not synthetic: the shipped view modules. A view that measures fails
    the build here."""
    found = guard.check_views()
    assert found == {}, "view modules break the rendering contract:\n" + \
        "\n".join(f"  {m}:{line}  {rule}  {detail}"
                  for m, v in sorted(found.items())
                  for line, rule, detail in v)
    assert len(guard.view_modules()) >= 3      # __init__, ground, query_trace


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


def test_a_malformed_drawing_is_refused_synthetic():
    head, cols = _state()

    def refused(drawing):
        class V(contract.View):
            name = "v"
            reads = ()

            def render(self, state):
                return drawing
        try:
            contract.draw(V(), head, cols)
        except contract.ContractError:
            return True
        return False

    D, M = contract.Drawing, contract.Mark
    assert refused({"figures": {}})
    assert refused(D(view="other", marks=[], figures={}))
    assert refused(D(view="v", marks=[M("blob", data={})], figures={}))
    assert refused(D(view="v", marks=[M("point", data={"a": [1, 2],
                                                       "b": [1]})],
                     figures={}))
    assert refused(D(view="v", marks=[M("point", data={"a": [1]},
                                        encoding={"color": "b"})],
                     figures={}))
    assert refused(D(view="v", marks=[], figures={"x": 1},
                     gaps={"x": "couldnt_check: both"}))
    assert refused(D(view="v", marks=[], figures={},
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
    assert "positions" in d.gaps
    (points,) = d.marks
    assert len(points.data["vector_id"]) == 12
    assert list(points.data["copy_count"]) == [2, 1] * 6
    assert d.reads == sorted(GroundView.reads)
    assert d.epsilon == contract.RECOUNT
    assert d.source["config_label"] == "semantic_sharded[synthetic]"


def test_the_query_trace_view_draws_each_query_synthetic():
    head, cols = _state()
    expect = {0: (0, 1, 1, False), 1: (1, 2, 2, False), 2: (3, 0, 0, True)}
    for q, (routed, outside, missed, from_candidates) in expect.items():
        d = contract.draw(QueryTraceView(q, k=3), head, cols)
        f = d.figures
        assert f["routed_region"] == routed, (q, f)
        assert f["outside_routed_region"] == outside, (q, f)
        assert f["missed_by_route"] == missed, (q, f)
        assert f["answerable_from_candidates_alone"] is from_candidates, q
        assert d.gaps == {}, d.gaps
        assert d.epsilon == contract.REBUILD, "it reads what shards returned"


def test_a_state_without_true_ids_is_a_gap_not_a_guess_synthetic():
    head, cols = _state()
    del cols["candidates.true_ids"]
    d = contract.draw(QueryTraceView(0, k=3), head, cols)
    assert "outside_routed_region" in d.gaps
    assert d.gaps["outside_routed_region"].startswith(contract.COULDNT_CHECK)
    assert d.figures["outside_routed_region_lower_bound"] == 0
    d2 = contract.draw(QueryTraceView(2, k=3), head, cols)
    assert d2.figures["outside_routed_region"] == 0, "all three were returned"


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


# ---------------------------------------------------------------- hygiene
def test_drawing_loads_no_model_family_or_measuring_code():
    """Not synthetic: a clean process draws both views and is then asked what
    it imported."""
    code = (
        "import sys, tempfile\n"
        f"sys.path.insert(0, {REPO!r})\n"
        "from oneground.lab import contract\n"
        "from oneground.lab import test_lab as T\n"
        "from oneground.lab.views import GroundView, QueryTraceView\n"
        "with tempfile.TemporaryDirectory() as tmp:\n"
        "    head, cols = T._synthetic(tmp)\n"
        "contract.draw(GroundView(), head, cols)\n"
        "contract.draw(QueryTraceView(1, k=3), head, cols)\n"
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
