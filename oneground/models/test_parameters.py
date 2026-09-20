"""Every family's parameter table, against what the family actually reads.

Task 026. Until then a configuration key no family read was accepted, folded
into the label and silently ignored: `probez: 3` produced a config called
`semantic_sharded[...,probez=3]`, measured exactly like one without it. A
proposal loop built on that would publish a result for a change never applied.

The property, in both directions:
  - every key a family reads is declared (a strict `Config.get` raises
    otherwise, and a static scan catches paths no synthetic run reaches);
  - every declared key that is not a constant is read (a declared key nobody
    reads is the same accept-and-ignore defect, one step removed);
  - constants are refused in any configuration and never read.

Synthetic corpora throughout, except the tests named for shipped files.
"""

import ast
import glob
import re
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from oneground import models  # noqa: E402
from oneground.models import Config, ConfigSpace  # noqa: E402
from oneground.models.base import (CONSTANT, FLAT, HNSW,  # noqa: E402
                                   INDEX_ALGORITHMS, IVF, IVF_PQ, NO_DEFAULT,
                                   PARAMETER, PARAMETER_TABLES,
                                   RERANK_EXACT, ParameterError,
                                   parameter_table)

FAMILIES = sorted(models.REGISTRY)

# Knob values small enough for the 240-vector synthetic corpus below, and for
# one shard of it. The declared defaults (nlist=1024, nbits=8) cannot be
# trained on 240 points -- faiss cannot learn more cells than it has points,
# and a PQ with 8 bits wants 256 training points per sub-quantiser. The
# defaults are exercised by the fixture sweeps, not here.
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
    q = x[:n_q].copy()
    return x, q


def _small_config(family):
    """The family's first default config, shrunk to fit a tiny corpus."""
    space = ConfigSpace(seed=1, node_counts=(2,),
                        grid={"semantic_sharded": {"centroids": [4],
                                                   "probe": [2]}})
    return list(models.get(family).configs(space))[0]


def _config_for(family, algorithm, rerank=None):
    """The family's small config, re-pointed at `algorithm` (task 034).

    A knob belongs to an algorithm, so this is not "the same config plus
    `index`": the keys the chosen algorithm does not read are dropped, because
    `Config.make` refuses them -- that refusal being the point of `belongs_to`.
    """
    table = parameter_table(family)
    params = {}
    for name, value in _small_config(family).params.items():
        owned = table[name].belongs_to
        if owned and algorithm not in tuple(owned[1]):
            continue
        params[name] = value
    params["index"] = algorithm
    params.update(SMALL_KNOBS[algorithm])
    if rerank:
        # Task 035: `candidates` belongs to `rerank: exact` exactly as `nlist`
        # belongs to `ivf`, so it is only read under that mode. Same reason
        # this function loops over algorithms at all.
        params["rerank"] = rerank
        params["candidates"] = 2
    return Config.make(family, params)


def test_every_registered_family_has_a_table():
    assert set(FAMILIES) <= set(PARAMETER_TABLES), (
        sorted(set(FAMILIES) - set(PARAMETER_TABLES)))


@pytest.mark.parametrize("family", FAMILIES)
def test_the_keys_a_family_reads_are_exactly_its_declared_settings_synthetic(
        family, monkeypatch):
    """Run build, search, ceiling and footprint, recording every key read.

    Once per declared index algorithm since task 034: `nlist` is read only
    when `index` is `ivf` or `ivf_pq`, so a single run at the default
    algorithm would report four declared-and-never-read keys that are in fact
    read -- under a configuration this loop now reaches.

    And once more with `rerank: exact` since task 035, for the same reason:
    `candidates` is read only under that mode, so a run at the default would
    report it declared-and-never-read.
    """
    read = set()
    real_get = Config.get

    def recording_get(self, key, default=None):
        read.add(key)
        return real_get(self, key, default)

    monkeypatch.setattr(Config, "get", recording_get)
    x, q = _corpus()
    model = models.get(family)
    for algorithm in INDEX_ALGORITHMS:
        for rerank in (None, RERANK_EXACT):
            cfg = _config_for(family, algorithm, rerank=rerank)
            built = model.build(x, cfg, 1)
            model.search(built, q, 10, cfg)
            model.ceiling(built, q, 10)
            model.footprint(built)

    table = parameter_table(family)
    settable = {n for n, p in table.items() if p.role != CONSTANT}
    constants = {n for n, p in table.items() if p.role == CONSTANT}
    assert read <= set(table), f"{family} read undeclared {read - set(table)}"
    assert not (read & constants), f"{family} read constants {read & constants}"
    assert settable <= read, (
        f"{family} declares {sorted(settable - read)} but never reads them: "
        "a value set there would be accepted and ignored")


def _static_keys(path):
    """String keys in `<something config>.get("key"...)` calls in a module."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    keys = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            receiver = ast.unparse(node.func.value)
            if receiver.split(".")[-1] in ("config", "cfg"):
                keys.add(node.args[0].value)
    return keys


@pytest.mark.parametrize("family", FAMILIES)
def test_no_family_source_reads_an_undeclared_key(family):
    """The static half: a read on a path the synthetic run never reaches."""
    path = os.path.join(HERE, family, "model.py")
    keys = _static_keys(path)
    table = parameter_table(family)
    assert keys, f"the scan found no config reads in {path}"
    assert keys <= set(table), f"{family} source reads {keys - set(table)}"
    # and the shared helper every family calls
    base_keys = _static_keys(os.path.join(HERE, "base.py"))
    assert base_keys <= set(table), (family, base_keys - set(table))


def test_no_family_reaches_past_get_into_params():
    for family in FAMILIES:
        src = open(os.path.join(HERE, family, "model.py"),
                   encoding="utf-8").read()
        assert ".params" not in src, (
            f"{family} reads config.params directly, around the table")


# ------------------------------------------------------------- refusals
def test_an_undeclared_key_is_refused_naming_what_exists_synthetic():
    with pytest.raises(ParameterError) as e:
        list(models.get("semantic_sharded").configs(ConfigSpace(
            seed=1, include=[{"family": "semantic_sharded", "probez": 3}])))
    msg = str(e.value)
    assert "no parameter 'probez'" in msg and "probe" in msg, msg


def test_a_direct_config_is_validated_too_synthetic():
    with pytest.raises(ParameterError):
        Config(family="single_node_hnsw", params={"M": 32, "centroids": 4},
               label="x")


def test_get_refuses_an_undeclared_key_synthetic():
    c = Config.make("single_node_hnsw", {"M": 32, "efConstruction": 200,
                                         "efSearch": 128})
    with pytest.raises(ParameterError) as e:
        c.get("centroids")
    assert ("declares: M, candidates, deterministic, efConstruction, "
            "efSearch, index, m, nbits, nlist, nprobe, rerank") in str(e.value)


def test_a_constant_is_refused_with_its_fixed_value_synthetic():
    with pytest.raises(ParameterError) as e:
        Config.make("semantic_sharded", {"centroids": 4, "epsilon": 0.2,
                                         "probe": 2, "M": 16, "efSearch": 32,
                                         "efConstruction": 200})
    assert "constant fixed at 200" in str(e.value)
    with pytest.raises(ParameterError) as e:
        Config.make("hash_sharded", {"shards": 2, "M": 16, "efSearch": 32,
                                     "shard_depth": 100})
    assert "constant fixed at max(30, k)" in str(e.value)


def test_a_grid_key_that_would_be_ignored_is_refused_synthetic():
    model = models.get("single_node_hnsw")
    with pytest.raises(ParameterError) as e:
        model.configs(ConfigSpace(seed=1, grid={
            "single_node_hnsw": {"efConstruction": [400]}}))
    assert "not swept" in str(e.value)
    with pytest.raises(ParameterError):
        model.configs(ConfigSpace(seed=1, grid={
            "single_node_hnsw": {"efSerach": [64]}}))


@pytest.mark.parametrize("family, params, needle", [
    ("semantic_sharded", {"probe": 2.5}, "must be int"),
    ("semantic_sharded", {"probe": 0}, "at least 1"),
    ("semantic_sharded", {"epsilon": -0.1}, "at least 0.0"),
    ("semantic_sharded", {"epsilon": "0.2"}, "must be float"),
    ("single_node_hnsw", {"deterministic": 1}, "must be bool"),
    ("hash_sharded", {"shards": True}, "must be int"),
])
def test_types_and_ranges_are_checked_synthetic(family, params, needle):
    with pytest.raises(ParameterError) as e:
        Config.make(family, params)
    assert needle in str(e.value), str(e.value)


def test_simulate_turns_a_bad_key_into_its_own_error_synthetic():
    from oneground import simulate

    class Req:
        data = {"simulate": {"families": ["semantic_sharded"],
                             "include": [{"family": "semantic_sharded",
                                          "probez": 3}]}}
    with pytest.raises(simulate.SimulateError) as e:
        simulate.plan_sweep(Req, 1)
    assert "probez" in str(e.value)


def test_shard_depth_is_added_only_where_it_is_read():
    """The simulator used to add it to every family, where two ignored it."""
    from oneground.simulate import _with_shard_depth
    for family in FAMILIES:
        cfg = _small_config(family)
        out = _with_shard_depth(cfg, 100)
        assert ("shard_depth" in out.params) == (family == "semantic_sharded"), (
            family, out.params)
        assert out.label == cfg.label


# ------------------------------------------------------------- shipped files
def test_every_shipped_requirements_file_plans_valid_configs():
    """Not synthetic: every requirements*.yaml in the repository."""
    from oneground import intake
    from oneground.simulate import _space_from
    paths = sorted(glob.glob(os.path.join(ROOT, "requirements*.yaml")))
    assert paths
    for path in paths:
        req = intake.load(path)
        sim = req.data.get("simulate") or {}
        space = _space_from(req, 1)
        for family in sim.get("families") or []:
            if family not in models.REGISTRY:
                continue            # an unknown family is simulate's refusal
            models.get(family).configs(space)       # raises on a bad key


def test_every_fixture_reference_configuration_is_valid():
    """Not synthetic: the published reference parameters build as Configs."""
    import yaml
    for path in sorted(glob.glob(os.path.join(ROOT, "fixtures",
                                              "*.fixture.yaml"))):
        spec = yaml.safe_load(open(path, encoding="utf-8")) or {}
        for family, entry in (spec.get("reference_results") or {}).items():
            if not isinstance(entry, dict) or family not in models.REGISTRY:
                continue
            Config.make(family, dict(entry.get("params") or {}))


# ------------------------------------------------- one label per configuration
# Task 032. A parameter written at its default and the same parameter left out
# are the same architecture measured the same way, and used to be two labels:
# `semantic_sharded[...,probe=2]` and `semantic_sharded[...]` are two rows in
# `simulate.json`, so a sweep could measure identical work twice and present it
# as two configurations. `Config.make` fills the declared defaults.

def _full_params(family):
    """The default configuration of `family`, every parameter written out.

    Task 034 made "every parameter with a default" stop being a
    configuration: a knob belongs to an index algorithm, and `nlist` and `M`
    cannot both appear in one. This is the *default algorithm's* set, which
    is what every published label is made of, and `index` itself is left out
    because it elides at its default.
    """
    table = parameter_table(family)
    out = {}
    for name, param in table.items():
        if param.role != PARAMETER or param.default is NO_DEFAULT:
            continue
        if not param.in_label_at_default:
            continue
        if param.belongs_to:
            owner, wanted = param.belongs_to
            if table[owner].default not in tuple(wanted):
                continue
        out[name] = param.default
    return out


@pytest.mark.parametrize("family", FAMILIES)
def test_a_default_written_and_a_default_omitted_are_one_config(family):
    """The wrinkle itself: both spellings, one label and one params dict."""
    full = _full_params(family)
    assert full, f"{family} declares no parameter with a default"
    whole = Config.make(family, dict(full))
    for key in sorted(full):
        without = {k: v for k, v in full.items() if k != key}
        c = Config.make(family, without)
        assert c.label == whole.label, (family, key, c.label, whole.label)
        assert c.params == whole.params, (family, key)


@pytest.mark.parametrize("family", FAMILIES)
def test_the_two_spellings_are_indistinguishable_when_measured(family):
    """Not only the label: the same index, the same ids, the same footprint.

    A label that collapsed two spellings the family measures differently
    would be worse than the wrinkle -- it would present two results as one.
    """
    x, q = _corpus()
    full = _full_params(family)
    # Small enough for a 240-vector corpus, and still every parameter named.
    for key, value in (("centroids", 4), ("shards", 2)):
        if key in full:
            full[key] = value
    model = models.get(family)
    written = Config.make(family, dict(full))

    # The key to leave out has to be one still *at* its declared default:
    # omitting a key whose value was changed is a different configuration,
    # and asserting the two agree would be asserting something false.
    key = "efSearch"
    assert full[key] == parameter_table(family)[key].default, family
    omitted = Config.make(family, {k: v for k, v in full.items() if k != key})

    a = model.build(x, written, seed=3)
    b = model.build(x, omitted, seed=3)
    ia = model.search(a, q, 5, written).ids
    ib = model.search(b, q, 5, omitted).ids
    assert np.array_equal(ia, ib), (family, key)
    assert model.footprint(a).as_dict() == model.footprint(b).as_dict()


def test_the_label_test_would_catch_the_wrinkle_coming_back_synthetic():
    """The negative control for the guard itself.

    `canonical_params` is what closes the wrinkle; without it the two
    spellings are two labels again. A test nobody has seen fail proves
    nothing, so this is the same comparison against the un-canonicalised
    form, asserting it *does* differ.
    """
    full = _full_params("semantic_sharded")
    without = {k: v for k, v in full.items() if k != "probe"}
    raw = "semantic_sharded[%s]" % ",".join(
        "%s=%s" % (k, without[k]) for k in sorted(without))
    assert raw != Config.make("semantic_sharded", without).label
    assert "probe" not in raw
    # and the canonical form is the one with every parameter in it
    assert "probe=2" in Config.make("semantic_sharded", without).label


@pytest.mark.parametrize("family", FAMILIES)
def test_a_non_default_value_is_still_its_own_configuration(family):
    """The negative control. Canonicalising defaults must not collapse two
    configurations that differ: a label that did would hide a real change."""
    full = _full_params(family)
    whole = Config.make(family, dict(full))
    moved = 0
    for key, value in sorted(full.items()):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        other = Config.make(family, dict(full, **{key: value + 1}))
        assert other.label != whole.label, (family, key)
        assert other.params[key] != whole.params[key]
        moved += 1
    assert moved, f"nothing numeric to move in {family}"


@pytest.mark.parametrize("family", FAMILIES)
def test_a_build_setting_at_its_default_is_not_collapsed(family):
    """Only `parameter` keys are filled.

    `deterministic=True` is a run someone asked for explicitly and
    `deterministic=False` is a different build; task 029 compared the two by
    label. Filling or eliding a build setting would make one of those
    comparisons impossible.
    """
    full = _full_params(family)
    plain = Config.make(family, dict(full))
    on = Config.make(family, dict(full, deterministic=True))
    off = Config.make(family, dict(full, deterministic=False))
    assert on.label != plain.label, family
    assert off.label != on.label, family
    assert "deterministic" not in plain.params, family


@pytest.mark.parametrize("family", FAMILIES)
def test_a_run_setting_does_not_change_a_label(family):
    """`simulate` adds `shard_depth` to a config without re-labelling it, so
    two sweeps of the same grid stay comparable row for row."""
    from oneground.simulate import _with_shard_depth
    cfg = Config.make(family, _full_params(family))
    assert _with_shard_depth(cfg, 100).label == cfg.label, family


def test_the_published_labels_are_the_ones_canonicalisation_produces():
    """Not synthetic: the labels published values are keyed by do not move.

    Canonicalisation would be worth nothing if it renamed the rows the
    fixtures publish, so this pins the three of them.
    """
    assert Config.make("single_node_hnsw", {
        "M": 32, "efConstruction": 200, "efSearch": 128}).label == (
        "single_node_hnsw[M=32,efConstruction=200,efSearch=128]")
    assert Config.make("semantic_sharded", {
        "centroids": 256, "epsilon": 0.2, "probe": 2, "M": 32,
        "efSearch": 96}).label == (
        "semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2]")
    assert Config.make("hash_sharded", {
        "shards": 3, "M": 32, "efSearch": 96}).label == (
        "hash_sharded[M=32,efSearch=96,shards=3]")


@pytest.mark.parametrize("family", FAMILIES)
def test_the_declared_default_is_the_one_the_family_builds_with(family):
    """One source of truth, asserted: the source reads the table rather than
    repeating the literal, so the label and the build cannot disagree."""
    src = open(os.path.join(HERE, family, "model.py"), encoding="utf-8").read()
    table = parameter_table(family)
    for name, param in table.items():
        if param.default is NO_DEFAULT:
            continue
        # Every read of this key falls back to the table, never to a literal.
        for hit in re.finditer(r'config\.get\("%s",\s*([^,\n]+)' % name, src):
            assert hit.group(1).strip().startswith('_d("%s"' % name), (
                family, name, hit.group(1))
