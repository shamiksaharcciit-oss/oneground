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
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from oneground import models  # noqa: E402
from oneground.models import Config, ConfigSpace  # noqa: E402
from oneground.models.base import (CONSTANT, PARAMETER_TABLES,  # noqa: E402
                                   ParameterError, parameter_table)

FAMILIES = sorted(models.REGISTRY)


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


def test_every_registered_family_has_a_table():
    assert set(FAMILIES) <= set(PARAMETER_TABLES), (
        sorted(set(FAMILIES) - set(PARAMETER_TABLES)))


@pytest.mark.parametrize("family", FAMILIES)
def test_the_keys_a_family_reads_are_exactly_its_declared_settings_synthetic(
        family, monkeypatch):
    """Run build, search, ceiling and footprint, recording every key read."""
    read = set()
    real_get = Config.get

    def recording_get(self, key, default=None):
        read.add(key)
        return real_get(self, key, default)

    monkeypatch.setattr(Config, "get", recording_get)
    x, q = _corpus()
    model = models.get(family)
    cfg = _small_config(family)
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
    assert "declares: M, deterministic, efConstruction, efSearch" in str(e.value)


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
