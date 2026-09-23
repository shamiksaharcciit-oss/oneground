"""The family conformance suite, checked against families that break it.

**Synthetic throughout.** A suite that reports `passes` is worth exactly what
its failures are worth, so most of this file is mutants: families that break
one requirement each, asserting the suite names *that* check and not another.
A green suite that cannot fail is the defect these tests exist to prevent.

The shipped families are run too, and their current results are asserted --
including the two that fail `refusals, not crashes`. Those assertions are
written as findings with their task number, not as an accepted baseline: when
a family is fixed the assertion changes with it, and that is the intended way
to notice.
"""

import os
import sys
from dataclasses import dataclass

import numpy as np
import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import models                                    # noqa: E402
from oneground.models import conformance as C                   # noqa: E402
from oneground.models.base import Config, ParameterError        # noqa: E402

EXAMPLE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "examples", "random_sharded", "model.py"))


@pytest.fixture(scope="module")
def small():
    """A corpus small enough to run eight checks per mutant quickly."""
    return C.synthetic_corpus(n=400, dim=16, n_q=20, blobs=4)


def _by_check(results):
    return {r.check: r for r in results}


def _outcome(results, check):
    got = _by_check(results).get(check)
    assert got is not None, "no check named %r in %s" % (
        check, sorted(_by_check(results)))
    return got.outcome


# --------------------------------------------------------------- the shape
def test_every_shipped_family_gets_every_check_synthetic():
    for family in models.families():
        results = C.run_conformance(family, verbose=False)
        assert len(results) == len(C.CHECKS), (family, len(results))
        for r in results:
            assert r.outcome in (C.PASSES, C.FAILS, C.COULDNT_CHECK), r
            assert r.requirement, "%s: %s states no requirement" % (
                family, r.check)
            # A result a reader cannot act on is not a check.
            assert r.measured or r.detail, "%s: %s measured nothing" % (
                family, r.check)


def test_a_failure_names_the_requirement_not_an_assertion_synthetic():
    results = C.run_conformance("hash_sharded", verbose=False)
    for r in results:
        if r.outcome == C.FAILS:
            assert "must" in r.requirement or "cannot" in r.requirement, r
            assert "assert" not in r.detail.lower(), r


# ------------------------------------------------------- the worked example
def test_the_worked_example_loads_unregistered_and_passes_everything():
    """`examples/random_sharded` is the contribution gate's own demonstration.

    It is NOT registered -- that is deliberate, so nobody can select it -- so
    this also covers `--module`, the path a contributor's family takes before
    it is in the registry.
    """
    name, model = C.load_module_family(EXAMPLE)
    assert name == "random_sharded"
    assert name not in models.REGISTRY, (
        "the worked example must not be registered: it is a teaching "
        "artifact and a bad architecture")
    results = C.run_conformance(name, model=model, verbose=False)
    failed = [r.check for r in results if r.outcome == C.FAILS]
    assert not failed, "the worked example must fail no check: %s" % failed
    # Exactly one couldn't-check, and it is the one no single machine can
    # answer. If another appears, the example has stopped exercising
    # something it is supposed to demonstrate.
    unchecked = [r.check for r in results if r.outcome == C.COULDNT_CHECK]
    assert unchecked == ["determinism (across environments)"], unchecked


def test_the_worked_example_has_the_routing_loss_it_claims(small):
    """Its docstring says routing loss is about 1 - probe/shards. Measured."""
    from oneground.truth import exact_knn
    name, model = C.load_module_family(EXAMPLE)
    x, q = small
    gt = exact_knn(x, q, C.K)
    for shards, probe in ((4, 1), (4, 2), (8, 2)):
        cfg = Config.make(name, {"shards": shards, "probe": probe,
                                 "M": 16, "efSearch": 64})
        built = model.build(x, cfg, seed=1)
        ceiling = C._recall(model.ceiling(built, q, C.K), gt)
        expected = probe / shards
        assert abs(ceiling - expected) < 0.15, (
            "shards=%d probe=%d: ceiling %.4f, expected about %.4f"
            % (shards, probe, ceiling, expected))


# --------------------------------------------------------------- the mutants
def _mutant(**overrides):
    """The worked example with one method replaced."""
    name, model = C.load_module_family(EXAMPLE)

    class Mutant:
        pass

    m = Mutant()
    m.name = name
    for attr in ("configs", "build", "search", "ceiling", "footprint",
                 "state"):
        setattr(m, attr, overrides.get(attr) or getattr(model, attr))
    return name, m, model


def test_a_ceiling_below_recall_is_caught_synthetic(small):
    """The invariant every routing-loss figure in every report depends on."""
    name, mutant, real = _mutant()

    def broken_ceiling(built, queries, k):
        # Reach nothing: guaranteed below whatever search returned.
        return np.full((len(queries), k), -1, dtype=np.int64)

    mutant.ceiling = broken_ceiling
    results = C.run_conformance(name, model=mutant, corpus=small,
                                verbose=False)
    assert _outcome(results, "ceiling") == C.FAILS


def test_a_computed_footprint_is_caught_synthetic(small):
    """A size that does not change with the algorithm did not come from one."""
    name, mutant, real = _mutant()

    def formula_footprint(built):
        fp = real.footprint(built)
        # n x dim x 4: the estimate that was 61x wrong on a quantised index.
        fp.index_bytes = built.n_base * built.dim * 4
        fp.vector_bytes = built.n_base * built.dim * 4
        return fp

    mutant.footprint = formula_footprint
    results = C.run_conformance(name, model=mutant, corpus=small,
                                verbose=False)
    assert _outcome(results, "footprint is measured") == C.FAILS


def test_a_crash_instead_of_a_refusal_is_caught_synthetic(small):
    """A sweep that aborts instead of dropping one row."""
    name, mutant, real = _mutant()

    def crashing_build(vectors, config, seed, context=None,
                       deterministic=None):
        if int(config.get("shards", 8)) > len(vectors):
            raise RuntimeError("not a ParameterError")
        return real.build(vectors, config, seed, context, deterministic)

    mutant.build = crashing_build
    results = C.run_conformance(name, model=mutant, corpus=small,
                                verbose=False)
    assert _outcome(results, "refusals, not crashes") == C.FAILS


def test_a_missing_state_column_is_caught_synthetic(small):
    """A family that is usable and invisible."""
    name, mutant, real = _mutant()

    def stripped_state(built, queries, k, config, gt_ids, seed):
        st = real.state(built, queries, k, config, gt_ids, seed)
        st.load.vectors_held = None         # a column the ground view reads
        return st

    mutant.state = stripped_state
    results = C.run_conformance(name, model=mutant, corpus=small,
                                verbose=False)
    assert _outcome(results, "state is emitted and renders") == C.FAILS


def test_an_index_dependent_ceiling_is_caught_synthetic(small):
    """Routing loss is the partition's, and the index may not move it."""
    name, mutant, real = _mutant()

    def leaky_ceiling(built, queries, k):
        ids = real.ceiling(built, queries, k)
        from oneground.models import indexes
        if indexes.algorithm_of(built.config) == "ivf":
            ids = ids.copy()
            ids[:, -1] = -1                 # the index changed what is reachable
        return ids

    mutant.ceiling = leaky_ceiling
    results = C.run_conformance(name, model=mutant, corpus=small,
                                verbose=False)
    assert _outcome(results, "routing loss is index-invariant") == C.FAILS


def test_a_nondeterministic_build_is_caught_synthetic(small):
    """Two builds that disagree make every artifact incomparable."""
    name, mutant, real = _mutant()
    counter = {"n": 0}

    def drifting_state(built, queries, k, config, gt_ids, seed):
        st = real.state(built, queries, k, config, gt_ids, seed)
        counter["n"] += 1
        st.notes = list(st.notes) + ["build %d" % counter["n"]]
        return st

    mutant.state = drifting_state
    results = C.run_conformance(name, model=mutant, corpus=small,
                                verbose=False)
    assert _outcome(results, "determinism (this machine)") == C.FAILS


def test_a_knob_that_does_nothing_is_caught_synthetic(small):
    """A declared key nothing reads: distinct labels for identical work."""
    name, mutant, real = _mutant()
    table = C.parameter_table(name)
    from oneground.models.base import PARAMETER, Param
    added = "unread_knob"
    table[added] = Param(added, int, role=PARAMETER, minimum=1, default=1,
                         swept=False, note="declared here and read nowhere")
    try:
        results = C.run_conformance(name, model=mutant, corpus=small,
                                    verbose=False)
        result = _by_check(results)["parameter table"]
        assert result.outcome == C.FAILS, result
        assert added in result.detail, result.detail
    finally:
        del table[added]


# ------------------------------------------------------ the shipped findings
def test_hash_sharded_still_accepts_more_shards_than_vectors_task_042():
    """A FINDING, still open — and now only half of the one 042 recorded.

    042 found two things in one build: the configuration was accepted at all,
    and `fanout` then reported the shards that were *asked for* while
    `shards` reported the ones that were *built*, so one footprint carried
    two mutually inconsistent numbers.

    **The fan-out half closed in 042c** and is asserted below as fixed. The
    refusal half is open: `hash_sharded` still accepts a configuration asking
    for more shards than there are vectors, so its label still names a
    partition larger than the artifact. That is one `ParameterError` in
    `build`, and it was not authorised by 042c's brief.

    When the refusal lands, this test fails and is deleted.
    """
    x = np.ascontiguousarray(
        C.synthetic_corpus(n=200, dim=16, n_q=5)[0])
    cfg = Config.make("hash_sharded",
                      {"shards": 201, "M": 16, "efSearch": 64})
    built = models.get("hash_sharded").build(x, cfg, seed=1)
    fp = models.get("hash_sharded").footprint(built)

    # the half still open: accepted, and the label names 201
    assert fp.shards < 201, "the artifact holds fewer shards than requested"
    assert "201" in cfg.label, cfg.label

    # the half 042c closed: the fan-out follows the artifact
    assert fp.fanout == float(fp.shards), (
        "042c: fan-out must report the shards that were built, not the ones "
        "requested (fan-out %.0f, shards %d)" % (fp.fanout, fp.shards))
    assert fp.fanout < 201.0, "fanout still reports the requested count"


def test_semantic_sharded_refuses_too_many_centroids_task_042b():
    """The 042 finding, fixed in 042b. Was: faiss raised and the sweep stopped.

    A `ParameterError` is what `simulate` catches to drop one row and report
    it. Anything else ends the run -- on arxiv-150k that is up to five hours
    of measured rows lost to one unbuildable configuration.
    """
    x = np.ascontiguousarray(C.synthetic_corpus(n=200, dim=16, n_q=5)[0])
    cfg = Config.make("semantic_sharded",
                      {"centroids": 201, "epsilon": 0.2, "probe": 2,
                       "M": 16, "efSearch": 64})
    with pytest.raises(ParameterError) as caught:
        models.get("semantic_sharded").build(x, cfg, seed=1)
    message = str(caught.value)
    # The refusal names what the user wrote and what to do, not the C++ frame.
    assert "centroids=201" in message, message
    assert "200 vector(s)" in message, message
    assert "Lower centroids" in message, message


def test_the_centroid_refusal_is_raised_before_supplied_centroids_task_042b():
    """`context` is a speed concession and may not route around a refusal.

    The fixture builder passes centroids `characterize()` already computed. If
    the refusal sat after that shortcut, the same incoherent configuration
    would be refused from one caller and accepted from another.
    """
    x = np.ascontiguousarray(C.synthetic_corpus(n=200, dim=16, n_q=5)[0])
    cfg = Config.make("semantic_sharded",
                      {"centroids": 201, "epsilon": 0.2, "probe": 2,
                       "M": 16, "efSearch": 64})
    supplied = np.ascontiguousarray(
        C.synthetic_corpus(n=201, dim=16, n_q=5)[0])
    with pytest.raises(ParameterError):
        models.get("semantic_sharded").build(
            x, cfg, seed=1, context={"centroids": supplied})


def test_semantic_sharded_now_passes_every_check_synthetic():
    """042b closes the only check this family failed."""
    results = C.run_conformance("semantic_sharded", verbose=False)
    failed = [r.check for r in results if r.outcome == C.FAILS]
    assert not failed, failed


def test_single_node_hnsw_passes_every_check_synthetic():
    """The one shipped family with nothing outstanding, as of task 042."""
    results = C.run_conformance("single_node_hnsw", verbose=False)
    failed = [r.check for r in results if r.outcome == C.FAILS]
    assert not failed, failed



def test_a_fanout_that_reports_the_request_is_caught_synthetic(small):
    """The mutant for 042c's check, against the check's own code.

    A family that reports its requested shard count -- exactly what
    `hash_sharded` did before 042c -- must make `fanout matches the build`
    fail. Without this the check would still report `passes` on a tree where
    the defect had been reintroduced, which is task 042's own finding one
    level up: a check that passes for the wrong reason is worse than one that
    fails.
    """
    from oneground.models.base import Footprint
    name, mutant, real = _mutant()

    def inflated_footprint(built):
        f = real.footprint(built)
        return Footprint(**{**f.__dict__, "fanout": float(f.shards) + 1.0})

    mutant.footprint = inflated_footprint
    results = C.run_conformance(name, model=mutant, corpus=small,
                                verbose=False)
    result = _by_check(results)["fanout matches the build"]
    assert result.outcome == C.FAILS, result
    assert "shard" in result.measured, result.measured

    # and the real family passes the same check on the same corpus, so the
    # failure above is the mutation and not the corpus
    clean = _by_check(C.run_conformance(name, model=real, corpus=small,
                                        verbose=False))
    assert clean["fanout matches the build"].outcome == C.PASSES, \
        clean["fanout matches the build"]


def test_a_fanout_below_one_is_caught_synthetic(small):
    """The other end: a query touches at least one shard."""
    from oneground.models.base import Footprint
    name, mutant, real = _mutant()

    def zero_footprint(built):
        f = real.footprint(built)
        return Footprint(**{**f.__dict__, "fanout": 0.0})

    mutant.footprint = zero_footprint
    results = C.run_conformance(name, model=mutant, corpus=small,
                                verbose=False)
    assert _outcome(results, "fanout matches the build") == C.FAILS
