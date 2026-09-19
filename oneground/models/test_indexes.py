"""The four index algorithms, and what may not change because of them.

Task 034. Until 034 every family built HNSW underneath and the only index
knobs were `M`, `efConstruction` and `efSearch`. The algorithm is now declared,
which puts three properties at risk, and each of them is a test here:

  - `hnsw` is the default and must not re-label anything. Every published
    value was measured under it, so `index: hnsw` written out and `index`
    left out have to be one configuration -- one label, one params dict, one
    set of returned ids, one footprint.
  - a knob belongs to an algorithm. `nprobe` under HNSW is refused rather
    than accepted and ignored, for the reason 026 refuses an unknown key.
  - routing loss is a property of the partition, not of the index. The same
    partition under four algorithms must reach the same vectors, so
    `ceiling()` must return the same ids.

Synthetic corpora throughout. What each algorithm costs on a real corpus is
the fixture sweep's business, not this file's.
"""

import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from oneground import models                                   # noqa: E402
from oneground.models import Config, ConfigSpace, indexes       # noqa: E402
from oneground.models.base import (FLAT, HNSW, INDEX_ALGORITHMS,  # noqa: E402
                                   IVF, IVF_PQ, ParameterError,
                                   exact_over, parameter_table)

FAMILIES = sorted(models.REGISTRY)

# Small enough for the 240-vector corpus below and for one shard of it; see
# test_parameters.SMALL_KNOBS for why the declared defaults do not fit here.
SMALL_KNOBS = {
    FLAT: {},
    HNSW: {},
    IVF: {"nlist": 4, "nprobe": 2},
    IVF_PQ: {"nlist": 4, "nprobe": 2, "m": 4, "nbits": 4},
}


def _corpus(n=240, dim=16, n_q=12, seed=7):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, dim)).astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    return x, x[:n_q].copy()


def _small_config(family):
    space = ConfigSpace(seed=1, node_counts=(2,),
                        grid={"semantic_sharded": {"centroids": [4],
                                                   "probe": [2]}})
    return list(models.get(family).configs(space))[0]


def _config_for(family, algorithm):
    """The family's small config, re-pointed at `algorithm`."""
    table = parameter_table(family)
    params = {}
    for name, value in _small_config(family).params.items():
        owned = table[name].belongs_to
        if owned and algorithm not in tuple(owned[1]):
            continue
        params[name] = value
    params["index"] = algorithm
    params.update(SMALL_KNOBS[algorithm])
    return Config.make(family, params)


# ------------------------------------------------------ the builder itself
@pytest.mark.parametrize("algorithm", INDEX_ALGORITHMS)
def test_every_declared_algorithm_builds_and_searches_synthetic(algorithm):
    x, q = _corpus()
    cfg = Config.make("single_node_hnsw", dict(SMALL_KNOBS[algorithm],
                                               index=algorithm))
    idx = indexes.build(x, cfg, seed=1, deterministic=True)
    assert idx.ntotal == len(x)
    _, ids = idx.search(q, 10)
    assert ids.shape == (len(q), 10)


def test_flat_is_exact_by_construction_synthetic():
    """The reference point: recall 1.0, not approximately 1.0."""
    x, q = _corpus()
    cfg = Config.make("single_node_hnsw", {"index": FLAT})
    idx = indexes.build(x, cfg, seed=1, deterministic=True)
    _, got = idx.search(q, 10)
    want, _ = exact_over(x, np.arange(len(x)), q, 10)
    assert np.array_equal(got, want)


def test_an_unknown_algorithm_is_refused_with_the_declared_list_synthetic():
    with pytest.raises(ParameterError) as e:
        Config.make("single_node_hnsw", {"index": "annoy"})
    assert "annoy" in str(e.value)
    # and the builder refuses it too, for a config that never went through
    # `Config.make` -- a scratch script's dict
    with pytest.raises(ParameterError) as e:
        indexes.build(_corpus()[0], {"index": "annoy"}, seed=1,
                      deterministic=True)
    for name in INDEX_ALGORITHMS:
        assert name in str(e.value), str(e.value)


@pytest.mark.parametrize("params, needle", [
    ({"index": "hnsw", "nprobe": 4},
     "single_node_hnsw.nprobe is a ivf or ivf_pq setting"),
    ({"index": "ivf", "nlist": 4, "nprobe": 2, "M": 16},
     "single_node_hnsw.M is a hnsw setting"),
    ({"index": "ivf", "nlist": 4, "nprobe": 2, "m": 4},
     "single_node_hnsw.m is a ivf_pq setting"),
    ({"index": "flat", "efSearch": 64},
     "no knobs of its own"),
])
def test_a_knob_of_another_algorithm_is_refused_synthetic(params, needle):
    """The same rule as 026's: accepted-and-ignored is a reported number for
    a change that was never applied."""
    with pytest.raises(ParameterError) as e:
        Config.make("single_node_hnsw", params)
    assert needle in str(e.value), str(e.value)


def test_more_cells_than_points_is_its_own_refusal_synthetic():
    """faiss's own message names neither the configuration nor the shard."""
    x, _ = _corpus(n=64)
    cfg = Config.make("single_node_hnsw", {"index": IVF, "nlist": 1024,
                                           "nprobe": 8})
    with pytest.raises(indexes.IndexTooSmall) as e:
        indexes.build(x, cfg, seed=1, deterministic=True, where="region 3")
    msg = str(e.value)
    assert "nlist=1024" in msg and "64 vector" in msg and "region 3" in msg


def test_a_pq_asked_for_more_centroids_than_points_is_refused_synthetic():
    """The second size floor, and the much higher one. `nbits=8` wants 256
    training points per sub-quantiser where `nlist=8` wants 8, and faiss
    raises from inside `train` naming neither the config nor the shard."""
    x, _ = _corpus(n=128)
    cfg = Config.make("single_node_hnsw", {"index": IVF_PQ, "nlist": 8,
                                           "nprobe": 2, "m": 4, "nbits": 8})
    with pytest.raises(indexes.IndexTooSmall) as e:
        indexes.build(x, cfg, seed=1, deterministic=True, where="region 9")
    msg = str(e.value)
    assert "nbits=8" in msg and "256" in msg and "128 vector" in msg, msg
    assert "region 9" in msg, msg


def test_a_dimension_that_does_not_divide_by_m_is_refused_synthetic():
    x, _ = _corpus(dim=18)
    cfg = Config.make("single_node_hnsw", {"index": IVF_PQ, "nlist": 4,
                                           "nprobe": 2, "m": 4, "nbits": 4})
    with pytest.raises(ParameterError) as e:
        indexes.build(x, cfg, seed=1, deterministic=True)
    assert "m=4" in str(e.value) and "18" in str(e.value)


# ------------------------------------------------- hnsw does not re-label
def test_the_default_algorithm_written_and_omitted_are_one_config_synthetic():
    """The load-bearing property of 034: adding the key moved no label."""
    for family, params in (
            ("single_node_hnsw", {"M": 32, "efConstruction": 200,
                                  "efSearch": 128}),
            ("semantic_sharded", {"centroids": 256, "epsilon": 0.2,
                                  "probe": 2, "M": 32, "efSearch": 96}),
            ("hash_sharded", {"shards": 3, "M": 32, "efSearch": 96})):
        omitted = Config.make(family, dict(params))
        written = Config.make(family, dict(params, index=HNSW))
        assert written.label == omitted.label, family
        assert written.params == omitted.params, family
        assert "index" not in omitted.label, family


@pytest.mark.parametrize("family", FAMILIES)
def test_naming_the_default_algorithm_measures_the_same_thing(family):
    """Not only the label: the same ids and the same footprint."""
    x, q = _corpus()
    model = models.get(family)
    base = _small_config(family)
    named = Config.make(family, dict(base.params, index=HNSW))
    a = model.build(x, base, seed=3)
    b = model.build(x, named, seed=3)
    assert np.array_equal(model.search(a, q, 5, base).ids,
                          model.search(b, q, 5, named).ids), family
    assert model.footprint(a).as_dict() == model.footprint(b).as_dict(), family


# ------------------------------------------------------------ determinism
@pytest.mark.parametrize("algorithm", INDEX_ALGORITHMS)
def test_two_builds_of_one_algorithm_are_byte_identical_synthetic(algorithm):
    """One machine, `deterministic=True`. The cross-environment half is a
    measurement on two machines and lives in the task report, not here."""
    import faiss
    x, _ = _corpus()
    cfg = Config.make("single_node_hnsw", dict(SMALL_KNOBS[algorithm],
                                               index=algorithm))
    a = indexes.build(x, cfg, seed=11, deterministic=True)
    b = indexes.build(x, cfg, seed=11, deterministic=True)
    assert (faiss.serialize_index(a).tobytes()
            == faiss.serialize_index(b).tobytes()), algorithm


@pytest.mark.parametrize("algorithm", (IVF, IVF_PQ))
def test_the_trained_algorithms_take_the_run_seed_synthetic(algorithm):
    """A k-means seeded from faiss's global default would reproduce itself and
    ignore the run -- two seeds must be two indexes."""
    import faiss
    x, _ = _corpus()
    cfg = Config.make("single_node_hnsw", dict(SMALL_KNOBS[algorithm],
                                               index=algorithm))
    a = indexes.build(x, cfg, seed=11, deterministic=True)
    b = indexes.build(x, cfg, seed=12, deterministic=True)
    assert (faiss.serialize_index(a).tobytes()
            != faiss.serialize_index(b).tobytes()), algorithm


# -------------------------------------------------- the decomposition holds
@pytest.mark.parametrize("family", FAMILIES)
def test_routing_loss_is_identical_across_index_choices(family):
    """Step 4 of the brief, as a property rather than a report line.

    The ceiling is exact search over the vectors a query can reach, and what
    it can reach is the partition's business. Four algorithms over one
    partition must return the same ceiling ids; if they do not, the
    decomposition is attributing index loss to routing or the reverse.
    """
    x, q = _corpus()
    model = models.get(family)
    want = None
    for algorithm in INDEX_ALGORITHMS:
        cfg = _config_for(family, algorithm)
        built = model.build(x, cfg, seed=5)
        got = model.ceiling(built, q, 10)
        if want is None:
            want = got
        else:
            assert np.array_equal(got, want), (family, algorithm)


# ---------------------------------------------------- memory, measured
def test_quantisation_is_measured_rather_than_estimated_synthetic():
    """`vectors x dim x 4` is the answer for a flat index and is wrong for a
    quantised one, which is why `footprint` reports faiss's own number."""
    x, _ = _corpus(n=1024, dim=64)
    flat = Config.make("single_node_hnsw", {"index": FLAT})
    pq = Config.make("single_node_hnsw", {"index": IVF_PQ, "nlist": 16,
                                          "nprobe": 4, "m": 8, "nbits": 8})
    flat_bytes = indexes.measured_bytes(
        indexes.build(x, flat, seed=1, deterministic=True))
    pq_bytes = indexes.measured_bytes(
        indexes.build(x, pq, seed=1, deterministic=True))
    payload = x.size * 4
    assert flat_bytes >= payload
    assert pq_bytes < payload, (pq_bytes, payload)


@pytest.mark.parametrize("family", FAMILIES)
def test_the_footprint_carries_measured_bytes_and_their_difference(family):
    x, _ = _corpus()
    model = models.get(family)
    cfg = _config_for(family, IVF_PQ)
    d = model.footprint(model.build(x, cfg, seed=5)).as_dict()
    for key in ("index_bytes", "vector_bytes", "overhead_bytes"):
        assert key in d, (family, key)
    assert d["overhead_bytes"] == d["index_bytes"] - d["vector_bytes"]
    # and the estimate is still there, still named an estimate
    assert "est_memory_bytes" in d, sorted(d)


# --------------------------------------------------------------- the sweep
@pytest.mark.parametrize("family", FAMILIES)
def test_a_grid_that_never_names_index_sweeps_what_it_always_did(family):
    """The other half of "does not re-label": the *set* of configurations a
    requirements file written before 034 produces is unchanged."""
    space = ConfigSpace(seed=1, node_counts=(1, 3, 5))
    labels = [c.label for c in models.get(family).configs(space)]
    assert labels == sorted(set(labels), key=labels.index)   # no duplicates
    assert not any("index" in lb for lb in labels), labels


@pytest.mark.parametrize("family", FAMILIES)
def test_the_index_axis_is_swept_and_stays_coherent(family):
    """Four algorithms from one grid, each carrying only its own knobs."""
    space = ConfigSpace(seed=1, node_counts=(3,), grid={family: {
        "index": list(INDEX_ALGORITHMS), "nlist": [16], "nprobe": [2, 4],
        "m": [4], "nbits": [4]}})
    labels = [c.label for c in models.get(family).configs(space)]
    assert any(f"index={FLAT}" in lb for lb in labels), labels
    assert any(f"index={IVF}," in lb for lb in labels), labels
    assert any(f"index={IVF_PQ}," in lb for lb in labels), labels
    # the HNSW rows are the ones with no `index` in the label at all
    assert any("index=" not in lb for lb in labels), labels
    # no configuration mixes an algorithm with another's knob
    for lb in labels:
        if "index=ivf" in lb:
            assert "M=" not in lb and "efSearch" not in lb, lb
        if f"index={FLAT}" in lb:
            # flat has no knobs at all; what remains is the partition's
            assert "M=" not in lb and "nlist" not in lb, lb


@pytest.mark.parametrize("family", FAMILIES)
def test_a_knob_no_swept_algorithm_reads_is_refused_in_a_grid(family):
    """`nprobe: [4, 8]` with no IVF in the grid sweeps nothing -- the
    accept-and-ignore defect 026 exists to stop, one key further out."""
    with pytest.raises(ParameterError) as e:
        models.get(family).configs(ConfigSpace(
            seed=1, grid={family: {"nprobe": [4, 8]}}))
    assert "would be ignored" in str(e.value), str(e.value)
    with pytest.raises(ParameterError) as e:
        models.get(family).configs(ConfigSpace(
            seed=1, grid={family: {"index": [IVF], "nlist": [16],
                                   "nprobe": [2], "M": [32]}}))
    assert f"{family}.M is a hnsw setting" in str(e.value), str(e.value)


def test_knobs_in_use_reports_only_what_the_algorithm_reads_synthetic():
    cfg = Config.make("single_node_hnsw", {"index": IVF, "nlist": 8,
                                           "nprobe": 2})
    assert indexes.knobs_in_use(cfg) == {"index": IVF, "nlist": 8,
                                         "nprobe": 2}
    plain = Config.make("single_node_hnsw", {"M": 32, "efConstruction": 200,
                                             "efSearch": 128})
    assert indexes.knobs_in_use(plain) == {"index": HNSW, "M": 32,
                                           "efConstruction": 200,
                                           "efSearch": 128}
