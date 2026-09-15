"""Conformance: what every registered family must do, on synthetic data.

**Synthetic throughout** — these check the interface's contract, not any
published number. Every test is parameterised over `models.REGISTRY`, so a new
family is held to the same bar the moment it is registered, without editing
this file.

The contract:

    configs     yields at least one Config, each labelled and stable
    build       deterministic: same (vectors, config, seed) twice, same result
    search      (n_queries, k) ids and scores, -1/-inf padded, no duplicates
    ceiling     >= search recall, always. A ceiling below what the search
                actually returned would mean the model cannot account for its
                own results.
    footprint   every field present and arithmetically sane

    python oneground/models/test_conformance.py
    pytest oneground/models/test_conformance.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import models  # noqa: E402
from oneground.models import Config, ConfigSpace, Footprint  # noqa: E402
from oneground.truth import exact_knn  # noqa: E402

try:
    import pytest
except ImportError:                                       # pragma: no cover
    pytest = None

SEED = 20260910
K = 10


def _corpus(n=600, dim=32, n_q=40, seed=SEED, blobs=4):
    """Blobby, normalized, small enough that every family builds in seconds."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(blobs, dim))
    x = np.vstack([c + rng.normal(0, 0.12, size=(n // blobs + 1, dim))
                   for c in centres])[:n].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = x[rng.choice(n, size=n_q, replace=False)].copy()
    return np.ascontiguousarray(x), np.ascontiguousarray(q)


def _space():
    # A tiny space: the point is coverage of the interface, not of the grid.
    return ConfigSpace(seed=SEED, node_counts=(2,),
                       grid={"single_node_hnsw": {"M": (16,),
                                                  "efSearch": (64,)},
                             "semantic_sharded": {"centroids": (8,),
                                                  "epsilon": (0.1,),
                                                  "probe": (2,),
                                                  "M": (16,),
                                                  "efSearch": (64,)},
                             "hash_sharded": {"M": (16,), "efSearch": (64,),
                                              "shards": (2,)}})


def _first_config(model):
    return list(model.configs(_space()))[0]


def _recall(pred, gt):
    hits = sum(len(set(p[p >= 0]) & set(g)) for p, g in zip(pred, gt))
    return hits / (gt.shape[0] * gt.shape[1])


ALL = sorted(models.REGISTRY)


def _each(fn):
    """Run `fn(name, model)` for every registered family, collecting failures
    so one broken family does not hide another."""
    problems = []
    for name in ALL:
        try:
            fn(name, models.get(name))
        except Exception as e:                    # noqa: BLE001
            problems.append(f"{name}: {type(e).__name__}: {e}")
    assert not problems, "\n".join(problems)


# ------------------------------------------------------------------ configs
def test_every_family_yields_at_least_one_labelled_config_synthetic():
    def check(name, model):
        cfgs = list(model.configs(_space()))
        assert cfgs, "yielded no configs"
        labels = [c.label for c in cfgs]
        assert len(labels) == len(set(labels)), "duplicate config labels"
        for c in cfgs:
            assert isinstance(c, Config)
            assert c.family == name, f"config.family {c.family} != {name}"
            assert c.label.startswith(name)
    _each(check)


def test_included_configs_are_always_present_synthetic():
    """A pinned configuration must survive whatever the grid says -- this is
    how the fixture's two published reference rows enter a sweep."""
    space = ConfigSpace(
        seed=SEED, node_counts=(2,),
        include=[{"family": "single_node_hnsw", "M": 32, "efSearch": 128},
                 {"family": "semantic_sharded", "centroids": 8,
                  "epsilon": 0.2, "probe": 2, "M": 32, "efSearch": 96}])
    got = {c.label for c in models.get("single_node_hnsw").configs(space)}
    assert any("efSearch=128" in lbl and "M=32" in lbl for lbl in got), got
    got2 = {c.label for c in models.get("semantic_sharded").configs(space)}
    assert any("epsilon=0.2" in lbl and "probe=2" in lbl for lbl in got2), got2


# -------------------------------------------------------------------- build
def test_build_is_deterministic_synthetic():
    """Two builds from the same inputs return the same ids.

    NOTE ON WHAT THIS TEST DOES NOT CATCH. It passed throughout task 012 while
    `single_node_hnsw` was in fact non-deterministic, because the corpus here
    is small enough that faiss does not parallelise the add, and the
    non-determinism only exists under OpenMP. Task 012 found it at 200,000
    vectors -- 37% of returned ids differing between two builds -- which is far
    too slow to run in a unit test. The fix (single-threaded add by default) is
    pinned by the tests below; the at-scale evidence is in
    tasks/012b-calibration-followup.report.md.
    """
    x, q = _corpus()

    def check(name, model):
        cfg = _first_config(model)
        a = model.build(x, cfg, SEED)
        b = model.build(x, cfg, SEED)
        ra = model.search(a, q, K, cfg).ids
        rb = model.search(b, q, K, cfg).ids
        assert np.array_equal(ra, rb), "two builds gave different results"
        fa, fb = model.footprint(a), model.footprint(b)
        assert fa.as_dict() == fb.as_dict(), "footprint differs between builds"
    _each(check)


def test_single_node_hnsw_builds_single_threaded_by_default_synthetic():
    """The switch is on, and it is recorded on the built index.

    Recorded rather than merely applied because a receipt that does not say
    how an index was built cannot be reproduced from it.
    """
    from oneground.models.base import DETERMINISTIC_DEFAULT
    from oneground.models.single_node_hnsw.model import MODEL

    assert DETERMINISTIC_DEFAULT is True
    x, _ = _corpus()
    cfg = _first_config(MODEL)
    assert MODEL.build(x, cfg, SEED).state["deterministic"] is True
    assert MODEL.build(x, cfg, SEED,
                       deterministic=False).state["deterministic"] is False
    # config wins over the default, argument wins over the config
    from oneground.models.base import Config
    off = Config.make(MODEL.name, {**cfg.params, "deterministic": False})
    assert MODEL.build(x, off, SEED).state["deterministic"] is False
    assert MODEL.build(x, off, SEED,
                       deterministic=True).state["deterministic"] is True


def test_single_threaded_faiss_restores_the_thread_count_synthetic():
    """Leaking a one-thread setting would silently slow every later search."""
    import faiss

    from oneground.models.base import single_threaded_faiss

    before = faiss.omp_get_max_threads()
    with single_threaded_faiss(True):
        assert faiss.omp_get_max_threads() == 1
    assert faiss.omp_get_max_threads() == before

    # and it restores even when the body raises
    try:
        with single_threaded_faiss(True):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert faiss.omp_get_max_threads() == before

    # disabled is a no-op, not a pin to the current value
    with single_threaded_faiss(False):
        assert faiss.omp_get_max_threads() == before


def test_add_chunk_does_not_change_the_graph_synthetic():
    """Chunked adds stay sequential, so the index is the same one."""
    from oneground.models.single_node_hnsw.model import MODEL

    x, q = _corpus()
    cfg = _first_config(MODEL)
    whole = MODEL.search(MODEL.build(x, cfg, SEED), q, K, cfg).ids
    sliced = MODEL.search(
        MODEL.build(x, cfg, SEED, add_chunk=max(1, len(x) // 4)),
        q, K, cfg).ids
    assert np.array_equal(whole, sliced)


def test_built_index_reports_its_shape_synthetic():
    x, q = _corpus()

    def check(name, model):
        built = model.build(x, _first_config(model), SEED)
        assert built.family == name
        assert built.n_base == len(x)
        assert built.dim == x.shape[1]
        assert built.build_seconds >= 0
    _each(check)


# ------------------------------------------------------------------- search
def test_search_returns_well_formed_candidates_synthetic():
    x, q = _corpus()

    def check(name, model):
        cfg = _first_config(model)
        cand = model.search(model.build(x, cfg, SEED), q, K, cfg)
        assert cand.ids.shape == (len(q), K), cand.ids.shape
        assert cand.scores.shape == (len(q), K)
        assert cand.ids.dtype == np.int64
        for row in cand.ids:
            real = row[row >= 0]
            assert len(set(real.tolist())) == len(real), "duplicate ids"
            assert real.max(initial=-1) < len(x), "id out of range"
    _each(check)


def test_search_recall_is_reasonable_on_easy_data_synthetic():
    """Not a quality bar -- a floor that catches a family that is simply
    broken. Blobby data with queries drawn from the corpus is easy."""
    x, q = _corpus()
    gt = exact_knn(x, q, K)

    def check(name, model):
        cfg = _first_config(model)
        r = _recall(model.search(model.build(x, cfg, SEED), q, K, cfg).ids, gt)
        assert r > 0.5, f"recall@{K} = {r}, which suggests it is broken"
    _each(check)


# ------------------------------------------------------------------ ceiling
def test_ceiling_is_never_below_search_recall_synthetic():
    """The central invariant. The ceiling is what routing makes *reachable*;
    a search cannot return what it could not reach, so ceiling >= recall
    always. A violation means the model cannot account for its own results."""
    x, q = _corpus()
    gt = exact_knn(x, q, K)

    def check(name, model):
        cfg = _first_config(model)
        built = model.build(x, cfg, SEED)
        r = _recall(model.search(built, q, K, cfg).ids, gt)
        c = _recall(model.ceiling(built, q, K), gt)
        assert c >= r - 1e-9, (
            f"ceiling {c:.6f} < recall {r:.6f}: the model returned neighbours "
            "its own routing says are unreachable")
    _each(check)


def test_ceiling_is_well_formed_synthetic():
    x, q = _corpus()

    def check(name, model):
        built = model.build(x, _first_config(model), SEED)
        ids = model.ceiling(built, q, K)
        assert ids.shape == (len(q), K), ids.shape
        for row in ids:
            real = row[row >= 0]
            assert len(set(real.tolist())) == len(real), "duplicate ids"
    _each(check)


def test_full_reach_families_have_a_ceiling_of_one_synthetic():
    """single_node_hnsw and hash_sharded reach everything by construction, so
    their routing loss is zero and the ceiling is exact k-NN."""
    x, q = _corpus()
    gt = exact_knn(x, q, K)
    for name in ("single_node_hnsw", "hash_sharded"):
        model = models.get(name)
        built = model.build(x, _first_config(model), SEED)
        c = _recall(model.ceiling(built, q, K), gt)
        assert c > 0.999, f"{name} ceiling {c}, expected 1.0 (full reach)"


# ---------------------------------------------------------------- footprint
def test_footprint_fields_are_present_and_sane_synthetic():
    x, q = _corpus()

    def check(name, model):
        f = model.footprint(model.build(x, _first_config(model), SEED))
        assert isinstance(f, Footprint)
        d = f.as_dict()
        for key in ("stored_vectors", "storage_amplification",
                    "est_memory_bytes", "fanout", "shards", "p50_copies",
                    "p95_copies", "p99_copies_per_vector"):
            assert key in d, f"footprint missing {key}"
        assert d["stored_vectors"] >= len(x) or d["storage_amplification"] <= 1.0
        assert d["storage_amplification"] >= 1.0 - 1e-9, d
        assert d["est_memory_bytes"] > 0
        assert d["fanout"] >= 1.0
        assert d["shards"] >= 1
        assert d["p50_copies"] <= d["p95_copies"] <= d["p99_copies_per_vector"]
    _each(check)


def test_replicating_family_reports_amplification_above_one_synthetic():
    """semantic_sharded with a wide closure must show its storage cost."""
    x, q = _corpus()
    model = models.get("semantic_sharded")
    cfg = Config.make("semantic_sharded", {"centroids": 8, "epsilon": 0.5,
                                           "probe": 2, "M": 16, "efSearch": 64})
    f = model.footprint(model.build(x, cfg, SEED))
    assert f.amplification > 1.0, (
        f"epsilon 0.5 replicated nothing (amplification {f.amplification})")
    assert f.stored_vectors > len(x)


def test_hash_sharded_fans_out_to_every_shard_synthetic():
    """Its whole point: fan-out equals the shard count, storage stays 1x."""
    x, q = _corpus()
    model = models.get("hash_sharded")
    for n in (2, 4):
        cfg = Config.make("hash_sharded", {"shards": n, "M": 16,
                                           "efSearch": 64})
        f = model.footprint(model.build(x, cfg, SEED))
        assert f.fanout == float(n), f
        assert f.amplification == 1.0, f
        assert f.shards == n, f


def test_hash_assignment_is_seeded_and_stable_synthetic():
    from oneground.models.hash_sharded.model import assign_shards
    a = assign_shards(500, 4, SEED)
    b = assign_shards(500, 4, SEED)
    c = assign_shards(500, 4, SEED + 1)
    assert np.array_equal(a, b), "same seed gave a different partition"
    assert not np.array_equal(a, c), "a different seed gave the same partition"
    assert set(np.unique(a).tolist()) <= {0, 1, 2, 3}
    # Even in expectation: no shard should be wildly oversized at n=500.
    counts = np.bincount(a, minlength=4)
    assert counts.min() > 500 / 4 * 0.6, counts


# -------------------------------------------------------------------- state
def _state(model, x, q, cfg=None):
    """A family's state for `cfg`, called in the order simulate calls it:
    after search and footprint, before the index is released."""
    cfg = cfg or _first_config(model)
    built = model.build(x, cfg, SEED)
    gt = np.asarray(exact_knn(x, q, K), dtype=np.int64)
    cand = model.search(built, q, K, cfg)
    fp = model.footprint(built)
    return model.state(built, q, K, cfg, gt, SEED), cand, fp


def test_every_family_emits_a_state_that_meets_the_contract_synthetic():
    """The state contract (task 020, docs/STATE.md): every candidate's shard
    exists in the partition, every probed region was scored, copy counts agree
    with the footprint's storage amplification, and candidate ids are a subset
    of the base ids."""
    from oneground.models import state as S

    x, q = _corpus()

    def check(name, model):
        assert callable(getattr(model, "state", None)), \
            "does not implement state()"
        st, _, fp = _state(model, x, q)
        v = S.contract_violations(st, fp)
        assert v == [], v
        assert st.family == name
        assert (st.n_base, st.n_queries, st.dim) == (len(x), len(q),
                                                     x.shape[1])
    _each(check)


def test_state_candidates_reproduce_search_synthetic():
    """A state can meet the contract and still describe a different search.
    Merging its candidates must give exactly what search() returned."""
    from oneground.models.base import merge_candidates

    x, q = _corpus()

    def check(name, model):
        st, cand, _ = _state(model, x, q)
        c = st.candidates
        for qi in range(len(q)):
            lo, hi = int(c.offsets[qi]), int(c.offsets[qi + 1])
            ids, sc = merge_candidates([c.cand_id[lo:hi]],
                                       [c.cand_score[lo:hi]], K)
            assert np.array_equal(ids, cand.ids[qi]), f"query {qi}: ids differ"
            real = cand.ids[qi] >= 0
            assert np.allclose(sc[real], cand.scores[qi][real]), \
                f"query {qi}: scores differ"
    _each(check)


def test_state_names_every_true_neighbour_synthetic():
    """`true_ids` is the exact top-k whether or not the route reached it --
    the field task 020's acceptance test found missing -- and `true_rank`
    agrees with it."""
    x, q = _corpus()
    gt = np.asarray(exact_knn(x, q, K), dtype=np.int64)

    def check(name, model):
        st, _, _ = _state(model, x, q)
        c = st.candidates
        assert np.array_equal(c.true_ids, gt), "true_ids is not the exact top-k"
        for qi in range(len(q)):
            lo, hi = int(c.offsets[qi]), int(c.offsets[qi + 1])
            for vid, r in zip(c.cand_id[lo:hi].tolist(),
                              c.true_rank[lo:hi].tolist()):
                if r >= 0:
                    assert gt[qi, r] == vid, f"query {qi}: rank {r} wrong"
                else:
                    assert vid not in gt[qi], f"query {qi}: {vid} unranked"
    _each(check)


def test_state_encoding_round_trips_and_is_deterministic_synthetic():
    import hashlib
    import tempfile

    from oneground.models import state as S

    x, q = _corpus()

    def check(name, model):
        st, _, _ = _state(model, x, q)
        with tempfile.TemporaryDirectory() as t:
            digests = []
            for fn in ("a.state.npz", "b.state.npz"):
                p = S.write_state(os.path.join(t, fn), st)
                with open(p, "rb") as f:
                    digests.append(hashlib.sha256(f.read()).hexdigest())
            assert digests[0] == digests[1], "same state, different bytes"
            head, cols = S.read_state(os.path.join(t, "a.state.npz"))
        want = S._arrays(st)
        assert set(cols) == set(want) == set(head["columns"])
        for key, arr in want.items():
            got = cols[key]
            assert got.dtype == arr.dtype and got.shape == arr.shape, key
            assert np.array_equal(got, arr,
                                  equal_nan=arr.dtype.kind == "f"), key
        assert head["state_version"] == S.STATE_VERSION
    _each(check)


def test_state_contract_names_each_break_synthetic():
    """Each of the four rules, broken on purpose, is caught and named."""
    import copy

    from oneground.models import state as S

    x, q = _corpus()
    model = models.get("semantic_sharded")
    st, _, fp = _state(model, x, q)
    assert S.contract_violations(st, fp) == []

    def broken(mutate):
        s = copy.deepcopy(st)
        mutate(s)
        return " | ".join(S.contract_violations(s, fp))

    def shard_not_in_partition(s):
        s.candidates.cand_shard[0] = 10_000

    def probed_never_scored(s):
        s.route.scored_region[0, :] = -1

    def one_more_copy(s):
        a = s.assignment
        row = int(np.where(a.copy_count < a.max_assign)[0][0])
        a.copy_set[row, int(a.copy_count[row])] = a.home_region[row]
        a.copy_count[row] += 1

    def id_not_a_base_id(s):
        s.candidates.cand_id[0] = len(x)

    assert "not in the partition" in broken(shard_not_in_partition)
    assert "never scored" in broken(probed_never_scored)
    assert "amplification" in broken(one_more_copy)
    assert "outside [0," in broken(id_not_a_base_id)


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
