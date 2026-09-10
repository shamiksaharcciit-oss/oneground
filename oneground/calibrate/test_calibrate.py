"""Tests for the calibration harness.

The contracts worth holding, in the order they matter:

    1. an outcome is derived, never asserted, and a tolerance changed later
       cannot re-judge a line already written
    2. couldnt_check is never rounded up, and never fails a workflow
    3. a reference point that was not published is not invented
    4. a truncated corpus is refused, not measured
    5. the history is append-only

Tests whose fixture is generated rather than measured carry `_synthetic` in
the name, per CLAUDE.md. The two that read real committed artifacts do not.
"""

import json
import os
import subprocess
import sys

import numpy as np
import pytest

from . import CalibrateError, parse_config, recall_at, run_curve
from . import history as H
from . import reference as R

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


# --------------------------------------------------------------------------
# history: outcomes are derived
# --------------------------------------------------------------------------

def _line(**kw):
    base = dict(check="glove_curve", dataset="d", engine="e",
                engine_version="1", config="c", measured=0.5, reference=0.5,
                tolerance=0.02, definition="measured - reference")
    base.update(kw)
    return H.make_line(**base)


def test_outcome_is_derived_from_deviation_and_tolerance_synthetic():
    assert _line(measured=0.50, reference=0.50)["outcome"] == H.VERIFIED
    assert _line(measured=0.51, reference=0.50)["outcome"] == H.VERIFIED
    assert _line(measured=0.53, reference=0.50)["outcome"] == H.CONTRADICTED
    assert _line(measured=0.47, reference=0.50)["outcome"] == H.CONTRADICTED


def test_tolerance_boundary_is_inclusive_synthetic():
    ln = _line(measured=0.52, reference=0.50, tolerance=0.02)
    assert ln["deviation"] == pytest.approx(0.02)
    assert ln["outcome"] == H.VERIFIED


def test_a_missing_reference_is_couldnt_check_not_a_pass_synthetic():
    ln = _line(measured=0.9, reference=None)
    assert ln["reference"] is None
    assert ln["deviation"] is None
    assert ln["outcome"] == H.COULDNT_CHECK


def test_validate_refuses_a_hand_edited_outcome_synthetic():
    """The point of deriving outcomes: a line cannot claim its own verdict."""
    ln = _line(measured=0.60, reference=0.50)       # really contradicted
    assert ln["outcome"] == H.CONTRADICTED
    ln["outcome"] = H.VERIFIED
    with pytest.raises(ValueError, match="does not follow"):
        H.validate(ln)


def test_validate_refuses_a_line_missing_required_fields_synthetic():
    ln = _line()
    del ln["pins_sha256"]
    with pytest.raises(ValueError, match="missing required fields"):
        H.validate(ln)


def test_history_is_append_only_synthetic(tmp_path):
    p = str(tmp_path / "history.jsonl")
    H.append(_line(measured=0.50), p)
    H.append(_line(measured=0.60), p)
    lines = H.read(p)
    assert len(lines) == 2
    assert [ln["measured"] for ln in lines] == [0.50, 0.60]
    # A correction is a later line, and the earlier one survives verbatim.
    assert lines[0]["outcome"] == H.VERIFIED
    assert lines[1]["outcome"] == H.CONTRADICTED


def test_append_writes_lf_newlines_synthetic(tmp_path):
    """Task 002 found CRLF in artifacts that had to hash the same on two
    platforms. The history is a receipt and gets the same treatment."""
    p = str(tmp_path / "history.jsonl")
    H.append(_line(), p)
    with open(p, "rb") as f:
        raw = f.read()
    assert raw.endswith(b"\n")
    assert b"\r\n" not in raw


def test_comparable_requires_engine_version_and_config_synthetic():
    a = _line()
    b = _line()
    assert H.comparable(a, b)
    assert not H.comparable(a, _line(engine_version="2"))
    assert not H.comparable(a, _line(config="other"))
    assert not H.comparable(a, _line(dataset="other"))


def test_an_advisory_reading_can_be_seen_but_never_gates_synthetic():
    """The monthly qdrant:latest job must not become the answer.

    012b moved where that is enforced. `latest_by_check` now shows the most
    recent line whatever its scope -- otherwise a check could never be
    re-scoped, which is exactly what happened to the hnswlib curve. The
    safety property lives in the two places that matter: the exit code and
    the report footer both ignore advisory lines.
    """
    from . import _exit_code
    blocking = _line(measured=0.50, reference=0.50)
    advisory = _line(measured=0.90, reference=0.50,
                     outcome_scope=H.ADVISORY)
    assert advisory["outcome"] == H.CONTRADICTED

    (shown,) = H.latest_by_check([blocking, advisory]).values()
    assert shown["outcome_scope"] == H.ADVISORY, "the later line is displayed"
    # ...but it cannot fail anything, and it is not what a report cites.
    assert _exit_code([shown]) == 0
    assert H.latest_for_engine("e", [blocking, advisory])["outcome_scope"]         == H.BLOCKING


def test_re_scoping_a_check_to_advisory_clears_the_gate_synthetic(tmp_path):
    """The concrete case: seven blocking contradictions from task 012,
    superseded by advisory lines once the curve was re-scoped."""
    from . import _exit_code
    p = str(tmp_path / "history.jsonl")
    for _ in range(7):
        H.append(_line(check="glove_curve", config="c1", measured=0.9,
                       reference=0.5), p)
    assert _exit_code(H.latest_by_check(H.read(p)).values()) == 1

    H.append(_line(check="glove_curve", config="c1", measured=0.9,
                   reference=0.5, outcome_scope=H.ADVISORY), p)
    assert _exit_code(H.latest_by_check(H.read(p)).values()) == 0
    # the contradiction is still on the record, not deleted
    assert sum(1 for ln in H.read(p)
               if ln["outcome"] == H.CONTRADICTED) == 8


def test_a_later_blocking_line_does_displace_an_earlier_one_synthetic():
    first = _line(measured=0.50, reference=0.50)
    second = _line(measured=0.60, reference=0.50)
    (only,) = H.latest_by_check([first, second]).values()
    assert only["outcome"] == H.CONTRADICTED


def test_latest_for_engine_ignores_advisory_lines_synthetic(tmp_path):
    p = str(tmp_path / "history.jsonl")
    H.append(_line(engine="qdrant", measured=0.50), p)
    H.append(_line(engine="qdrant", measured=0.99, outcome_scope=H.ADVISORY), p)
    got = H.latest_for_engine("qdrant", path=p)
    assert got["outcome_scope"] == H.BLOCKING
    assert H.latest_for_engine("pgvector", path=p) is None


def test_render_marks_advisory_and_counts_outcomes_synthetic():
    text = H.render([_line(measured=0.50, reference=0.50),
                     _line(measured=0.90, reference=0.50),
                     _line(measured=0.50, reference=None),
                     _line(measured=0.90, reference=0.50,
                           outcome_scope=H.ADVISORY)])
    assert "1 verified" in text
    assert "2 contradicted" in text
    assert "1 couldn't-check" in text
    assert "advisory" in text


def test_render_of_an_empty_history_says_what_to_run_synthetic():
    assert "calibrate curve" in H.render([])


# --------------------------------------------------------------------------
# reference: a point that was not published is not invented
# --------------------------------------------------------------------------

def _page(points_by_config, x_label="Recall", algorithm="hnswlib"):
    """Minimal stand-in for an ANN-Benchmarks chart section."""
    charts = []
    for cfg, recalls in points_by_config.items():
        m, efc = cfg
        pts = ",\n".join(
            '{ x: %s , y: 100.0, label: "%s ({\'M\': %d, \'efConstruction\': '
            '%d})" }' % (r, algorithm, m, efc) for r in recalls)
        charts.append(
            "new Chart(ctx, {\n"
            '  data: { datasets: [ {\n'
            '                            label: "%s",\n'
            "                            fill: false,\n"
            "                            data: [\n%s\n            ]\n"
            "  } ] },\n"
            "  options: { scales: { xAxes: [{ scaleLabel: { labelString: "
            "' %s   ' } }] } }\n});" % (algorithm, pts, x_label))
    return "\n".join(charts)


def test_a_complete_sweep_maps_to_the_ef_grid_synthetic():
    grid = R.ANN_BENCHMARKS_EF_GRID
    recalls = [0.10 + 0.05 * i for i in range(len(grid))]
    html = _page({(12, 500): recalls})
    sweeps = R.complete_sweeps(html)
    assert (12, 500) in sweeps
    assert sweeps[(12, 500)][10] == pytest.approx(0.10)
    assert sweeps[(12, 500)][800] == pytest.approx(recalls[-1])


def test_an_incomplete_sweep_yields_no_reference_points_synthetic():
    """Eight recovered points against a nine-value grid is ambiguous, and a
    plausible alignment would be fiction."""
    grid = R.ANN_BENCHMARKS_EF_GRID
    recalls = [0.10 + 0.05 * i for i in range(len(grid) - 1)]
    html = _page({(96, 500): recalls})
    assert R.complete_sweeps(html) == {}
    got = R.reference_for(html, M=96, ef_construction=500, ef_values=[10, 20])
    assert got == {10: None, 20: None}


def test_a_non_monotone_series_is_rejected_synthetic():
    """Equal counts alone are not enough: a tie means the order is not a
    bijection onto the ef grid."""
    grid = R.ANN_BENCHMARKS_EF_GRID
    recalls = [0.10 + 0.05 * i for i in range(len(grid))]
    recalls[3] = recalls[2]                       # a tie
    html = _page({(12, 500): recalls})
    assert R.complete_sweeps(html) == {}


def test_non_recall_axes_are_excluded_synthetic():
    """The Relative Error and Epsilon-Recall charts have a different x."""
    grid = R.ANN_BENCHMARKS_EF_GRID
    recalls = [0.10 + 0.05 * i for i in range(len(grid))]
    html = _page({(12, 500): recalls}, x_label="Relative Error")
    assert R.recall_points(html) == {}


def test_reference_for_an_unpublished_efconstruction_is_all_none_synthetic():
    grid = R.ANN_BENCHMARKS_EF_GRID
    html = _page({(12, 500): [0.10 + 0.05 * i for i in range(len(grid))]})
    got = R.reference_for(html, M=16, ef_construction=200,
                          ef_values=[10, 20, 40])
    assert got == {10: None, 20: None, 40: None}


# --------------------------------------------------------------------------
# the real page, as committed in the fixture spec
# --------------------------------------------------------------------------

def test_the_fixture_declares_only_the_sweep_the_page_actually_completes():
    """Not synthetic: reads the committed spec.

    The spec may declare reference points only for M=12/efC=500, the one
    configuration whose sweep the page fully determines. If a future edit adds
    points for another configuration, this fails.
    """
    import yaml
    p = os.path.join(ROOT, "fixtures", "glove-100-angular.fixture.yaml")
    with open(p, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    withpoints = [(c["M"], c["efConstruction"])
                  for c in spec["reference_curve"]["configurations"]
                  if c.get("points")]
    assert withpoints == [(12, 500)]
    pts = spec["reference_curve"]["configurations"][0]["points"]
    assert sorted(pts) == sorted(R.ANN_BENCHMARKS_EF_GRID)
    vals = [pts[ef] for ef in sorted(pts)]
    assert all(b > a for a, b in zip(vals, vals[1:])), "must be monotone in ef"


def test_the_brief_configuration_is_kept_and_has_no_reference():
    """Not synthetic. M=16/efC=200 is the configuration task 012's brief
    asked for; ANN-Benchmarks never ran it, so it carries no points and every
    one of its curve points must be couldnt_check."""
    import yaml
    p = os.path.join(ROOT, "fixtures", "glove-100-angular.fixture.yaml")
    with open(p, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    cfgs = {(c["M"], c["efConstruction"]): c
            for c in spec["reference_curve"]["configurations"]}
    assert (16, 200) in cfgs
    assert not cfgs[(16, 200)]["points"]
    assert cfgs[(16, 200)]["recovered"] == "none"


# --------------------------------------------------------------------------
# recall and config parsing
# --------------------------------------------------------------------------

def test_recall_at_matches_the_verify_definition_synthetic():
    from ..verify import recall_at as verify_recall
    pred = np.array([[1, 2, 3], [4, 5, 6]])
    gt = np.array([[1, 2, 9], [7, 8, 9]])
    assert recall_at(pred, gt, 3) == verify_recall(pred, gt, 3)
    assert recall_at(pred, gt, 3) == pytest.approx(2 / 6)


def test_recall_at_ignores_padding_synthetic():
    pred = np.array([[1, -1, -1]])
    gt = np.array([[1, 2, 3]])
    assert recall_at(pred, gt, 3) == pytest.approx(1 / 3)


def test_parse_config_synthetic():
    assert parse_config("M=12,efConstruction=500") == {"M": 12,
                                                       "efConstruction": 500}
    with pytest.raises(CalibrateError):
        parse_config("M")


# --------------------------------------------------------------------------
# a truncated corpus is refused, not measured
# --------------------------------------------------------------------------

def test_curve_refuses_a_corpus_that_cannot_reach_its_ground_truth_synthetic(
        tmp_path):
    """The failure mode task 012 measured on the real data: with a 100k prefix
    of glove, 0 of 10,000 queries have their whole top-10 in the corpus and
    recall@10 is capped near 0.086. Every point of a curve would report the
    truncation as an index result, so the curve refuses to run."""
    fx = tmp_path / "fixtures"
    d = fx / "tiny"
    d.mkdir(parents=True)
    rng = np.random.default_rng(0)
    v = rng.normal(size=(50, 8)).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    np.save(d / "vectors.npy", v)
    np.save(d / "queries.npy", v[:5])
    # Ground truth pointing at ids 900+, which this corpus does not hold.
    np.save(d / "ground_truth.npy",
            np.full((5, 10), 900, dtype=np.int64))
    (fx / "tiny.fixture.yaml").write_text(
        "fixture: {id: tiny}\n"
        "reference_curve: {k: 10, tolerance: 0.02, ef_values: [10],\n"
        "                  configurations: []}\n", encoding="utf-8")
    with pytest.raises(CalibrateError, match="does not hold"):
        run_curve(fixture_id="tiny", config="M=4,efConstruction=8",
                  fixtures_dir=str(fx), append=False, log_fn=lambda m: None)


def test_missing_fixture_arrays_say_how_to_build_them_synthetic(tmp_path):
    fx = tmp_path / "fixtures"
    (fx / "gone").mkdir(parents=True)
    (fx / "gone.fixture.yaml").write_text(
        "fixture: {id: gone}\nreference_curve: {}\n", encoding="utf-8")
    with pytest.raises(CalibrateError, match="calibrate fixture"):
        run_curve(fixture_id="gone", fixtures_dir=str(fx), append=False,
                  log_fn=lambda m: None)


# --------------------------------------------------------------------------
# exit codes: couldnt_check never fails
# --------------------------------------------------------------------------

def test_exit_code_rules_synthetic():
    from . import _exit_code
    ok = _line(measured=0.5, reference=0.5)
    bad = _line(measured=0.9, reference=0.5)
    gap = _line(measured=0.5, reference=None)
    advisory_bad = _line(measured=0.9, reference=0.5,
                         outcome_scope=H.ADVISORY)
    assert _exit_code([ok]) == 0
    assert _exit_code([ok, gap]) == 0, "couldnt_check never fails by default"
    assert _exit_code([ok, gap], strict=True) == 2
    assert _exit_code([ok, bad]) == 1
    assert _exit_code([ok, advisory_bad]) == 0, "advisory never blocks"


# --------------------------------------------------------------------------
# the command line
# --------------------------------------------------------------------------

def test_calibrate_show_runs_on_the_committed_history():
    """Not synthetic: renders calibration/history.jsonl as committed.

    The exit code is deliberately not pinned to 0 here. `show` reports whether
    this installation is *currently* contradicted, so its code tracks the
    committed data; pinning it would make the test fail the day a standing
    contradiction is resolved. The semantics are pinned on controlled data in
    `test_show_exit_code_tracks_the_standing_outcome_synthetic`.
    """
    r = subprocess.run(
        [sys.executable, "-m", "oneground.cli", "calibrate", "show"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": ROOT})
    assert r.returncode in (0, 1), r.stderr
    assert "latest outcome per check" in r.stdout
    assert "glove_curve" in r.stdout
    assert "simulator_vs_engine" in r.stdout


def test_show_exit_code_tracks_the_standing_outcome_synthetic(tmp_path):
    p = str(tmp_path / "history.jsonl")
    H.append(_line(measured=0.50, reference=0.50), p)
    r = subprocess.run(
        [sys.executable, "-m", "oneground.cli", "calibrate", "show",
         "--history", p],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": ROOT})
    assert r.returncode == 0, r.stdout + r.stderr

    # A later line supersedes the earlier one, so the standing state is what
    # decides -- not whether a contradiction ever happened.
    H.append(_line(measured=0.90, reference=0.50), p)
    r = subprocess.run(
        [sys.executable, "-m", "oneground.cli", "calibrate", "show",
         "--history", p],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": ROOT})
    assert r.returncode == 1, r.stdout + r.stderr


def test_every_committed_history_line_reads_as_schema_2():
    """Not synthetic: the committed file, whatever era each line came from.

    Schema-2 lines must satisfy the schema they document. Schema-1 lines are
    translated on read and must land in the same shape -- but they are NOT
    rewritten on disk, which the next test checks.
    """
    p = os.path.join(ROOT, "calibration", "history.jsonl")
    lines = H.read(p)
    assert lines, "the history should not be empty"
    for ln in lines:
        assert set(H.FIELDS) <= set(ln), f"missing: {set(H.FIELDS) - set(ln)}"
        if ln.get("schema") == H.SCHEMA:
            H.validate(ln)


def test_the_seeded_task_011_line_is_translated_not_migrated():
    """Not synthetic: calibration/README.md says lines are never edited, only
    appended. That has to hold across a schema change too, so the schema-1
    line must still be on disk in its original shape."""
    p = os.path.join(ROOT, "calibration", "history.jsonl")
    raw = H.read(p, raw=True)
    legacy = [ln for ln in raw if H.is_legacy(ln)]
    assert legacy, "task 011's seeded line should still be here"
    first = legacy[0]
    assert "check" not in first, "the bytes on disk must not have been rewritten"
    assert first["calibration_error_recall"] == pytest.approx(-0.0018)

    view = H.normalize(first)
    assert view["check"] == "simulator_vs_engine"
    assert view["dataset"] == "arxiv-150k"
    assert view["deviation"] == pytest.approx(-0.0018)
    # It declared no tolerance, so it reaches no verdict.
    assert view["tolerance"] is None
    assert view["outcome"] == H.COULDNT_CHECK


def test_the_engine_line_reads_the_config_key_verify_actually_writes():
    """Not synthetic where it matters: the key name comes from the real
    verify.json schema.

    `verify` writes the matched configuration under `simulated_config`.
    Reading `config` instead produced a line with `config: "None"` -- and
    `config` is one of the five fields `comparable()` turns on, so such a line
    silently compares equal to every other broken line and to nothing real.
    Caught by running the command, not by a test, which is why one exists now.
    """
    from ..verify import _simulated_recall  # noqa: F401  (schema is verify's)

    cal = {"definition": "simulated - measured",
           "measured_recall_at_10": 1.0,
           "simulated_config": "single_node_hnsw[M=32,efConstruction=200,"
                               "efSearch=128]",
           "simulated_recall_at_10": 1.0}
    line = H.make_line(
        check="simulator_vs_engine", dataset="arxiv-smoke", engine="qdrant",
        engine_version="1.19.1", config=str(cal["simulated_config"]),
        measured=cal["simulated_recall_at_10"],
        reference=cal["measured_recall_at_10"], tolerance=0.05,
        definition="simulated recall@10 - measured recall@10")
    assert line["config"].startswith("single_node_hnsw[")
    assert "None" not in line["config"]

    # and a line whose config is missing must not compare equal to a real one
    broken = H.make_line(
        check="simulator_vs_engine", dataset="arxiv-smoke", engine="qdrant",
        engine_version="1.19.1", config="None", measured=1.0, reference=1.0,
        tolerance=0.05, definition="d")
    assert not H.comparable(line, broken)


def test_every_committed_engine_line_carries_efsearch():
    """Not synthetic: guards the committed file.

    Task 012 measured that efSearch does not mean the same thing across HNSW
    implementations -- faiss reaches at e what hnswlib reached at ~1.4e-1.9e --
    so a calibration point that does not say which efSearch it was taken at is
    not comparable to one from another engine. It has to be its own field:
    parsing it out of a config label works until a label changes shape.
    """
    lines = H.read(os.path.join(ROOT, "calibration", "history.jsonl"))
    engine_lines = [ln for ln in lines
                    if ln.get("check") == "simulator_vs_engine"
                    and int(ln.get("schema") or 0)
                    >= H.EFSEARCH_REQUIRED_FROM_SCHEMA]
    assert engine_lines, "expected at least one schema-3 engine line"
    for ln in engine_lines:
        assert ln.get("efSearch") is not None, (
            f"engine line on {ln.get('date')} does not say which efSearch it "
            f"was measured at")
        assert isinstance(ln["efSearch"], int)


def test_every_committed_engine_line_names_a_configuration():
    """Not synthetic: guards the committed file against the defect above."""
    lines = H.read(os.path.join(ROOT, "calibration", "history.jsonl"))
    for ln in lines:
        if ln.get("check") != "simulator_vs_engine":
            continue
        cfg = str(ln.get("config") or "")
        assert cfg and cfg not in ("None", "unknown"), (
            f"engine line on {ln.get('date')} names no configuration: {cfg!r}. "
            f"A calibration point whose config is unknown is not comparable "
            f"to anything.")


def test_show_check_filters_what_it_renders_and_what_it_judges_synthetic(
        tmp_path):
    """`--check` has to filter the table too, not just the exit code: a
    command that prints everything and exits on a subset is lying twice."""
    p = str(tmp_path / "history.jsonl")
    H.append(_line(check="glove_curve", measured=0.9, reference=0.5), p)
    H.append(_line(check="simulator_vs_engine", measured=0.5, reference=0.5,
                   extra={"efSearch": 128}), p)

    r = subprocess.run(
        [sys.executable, "-m", "oneground.cli", "calibrate", "show",
         "--history", p, "--check", "simulator_vs_engine"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": ROOT})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "glove_curve" not in r.stdout
    assert "simulator_vs_engine" in r.stdout

    r = subprocess.run(
        [sys.executable, "-m", "oneground.cli", "calibrate", "show",
         "--history", p, "--check", "nothing_like_this"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": ROOT})
    assert r.returncode == 0
    assert "no lines for check" in r.stdout


# --------------------------------------------------------------------------
# 012b: the three blocking layer checks
# --------------------------------------------------------------------------

def _tiny_fixture(tmp_path, n=200, dim=8, nq=20, k=5, truncate=False):
    """A fixture whose ground truth is exact, so the checks have a known
    answer to hit."""
    import faiss
    fx = tmp_path / "fixtures"
    d = fx / "tiny"
    d.mkdir(parents=True)
    rng = np.random.default_rng(7)
    v = rng.normal(size=(n, dim)).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    q = v[:nq].copy()
    idx = faiss.IndexFlatIP(dim)
    idx.add(v)
    sim, ids = idx.search(q, k + 1)
    # angular distance for unit vectors, the convention upstream uses
    dist = np.sqrt(np.maximum(2.0 - 2.0 * np.clip(sim, -1, 1), 0.0))
    if truncate:
        ids = ids + n           # point the truth outside the corpus
    np.save(d / "vectors.npy", v)
    np.save(d / "queries.npy", q)
    np.save(d / "ground_truth.npy", ids.astype(np.int64))
    np.save(d / "ground_truth_distances.npy", dist.astype(np.float32))
    (fx / "tiny.fixture.yaml").write_text(
        "fixture: {id: tiny}\nreference_curve: {k: 5, tolerance: 0.02}\n",
        encoding="utf-8")
    return str(fx), k


def test_layers_pass_on_a_fixture_whose_truth_is_exact_synthetic(tmp_path):
    from . import layers as L
    fx, k = _tiny_fixture(tmp_path)
    res = L.run_layers(fixture_id="tiny", k=k, n_queries=20, fixtures_dir=fx,
                       append=False, log_fn=lambda m: None)
    got = {ln["check"]: ln for ln in res["lines"]}
    assert set(got) == set(L.CHECKS)
    assert got["corpus_reachability"]["measured"] == pytest.approx(1.0)
    assert got["metric_agreement"]["measured"] == pytest.approx(1.0)
    for ln in res["lines"]:
        assert ln["outcome"] == H.VERIFIED, (ln["check"], ln["measured"])
        assert ln["outcome_scope"] == H.BLOCKING


def test_corpus_reachability_catches_a_truncated_corpus_synthetic(tmp_path):
    """The defect task 012 caught by hand, now a gate."""
    from . import layers as L
    fx, k = _tiny_fixture(tmp_path, truncate=True)
    res = L.run_layers(fixture_id="tiny", k=k, n_queries=20, fixtures_dir=fx,
                       append=False, log_fn=lambda m: None)
    got = {ln["check"]: ln for ln in res["lines"]}
    assert got["corpus_reachability"]["measured"] == pytest.approx(0.0)
    assert got["corpus_reachability"]["outcome"] == H.CONTRADICTED


def test_metric_agreement_collapses_on_the_wrong_convention_synthetic(
        tmp_path):
    """A metric-convention error is not a small effect.

    Ground truth built under L2 on unnormalized vectors, searched under inner
    product on normalized ones: agreement should fall far below the 0.001
    band, not drift just outside it.
    """
    import faiss
    from . import layers as L
    fx = tmp_path / "fixtures"
    d = fx / "wrong"
    d.mkdir(parents=True)
    rng = np.random.default_rng(3)
    raw = (rng.normal(size=(300, 8)) * rng.uniform(1, 9, (300, 1))
           ).astype(np.float32)
    l2 = faiss.IndexFlatL2(8)
    l2.add(raw)
    _, ids = l2.search(raw[:40], 6)
    unit = raw / np.linalg.norm(raw, axis=1, keepdims=True)
    np.save(d / "vectors.npy", unit)
    np.save(d / "queries.npy", unit[:40])
    np.save(d / "ground_truth.npy", ids.astype(np.int64))
    np.save(d / "ground_truth_distances.npy",
            np.zeros((40, 6), dtype=np.float32))
    (fx / "wrong.fixture.yaml").write_text("fixture: {id: wrong}\n",
                                           encoding="utf-8")
    agree = L.metric_agreement(unit, unit[:40], ids.astype(np.int64), 5, 40)
    assert agree < 0.9, f"a convention error should collapse, got {agree}"


def test_recall_rule_tie_bound_is_zero_without_ties_synthetic():
    from . import layers as L
    d = np.tile(np.arange(1, 13, dtype=np.float32), (50, 1))
    assert L.recall_rule_divergence_bound(d, 10) == pytest.approx(0.0)


def test_recall_rule_tie_bound_counts_boundary_ties_synthetic():
    from . import layers as L
    d = np.tile(np.arange(1, 13, dtype=np.float32), (100, 1))
    d[:25, 10] = d[:25, 9]                    # 10th and 11th coincide
    assert L.recall_rule_divergence_bound(d, 10) == pytest.approx(0.25)


def test_the_distance_based_metric_is_never_below_the_id_based_one_synthetic():
    """The one-signedness that made layer 3 an elimination rather than a
    guess: ANN-Benchmarks' tie-generous metric can only score a candidate set
    at or above an id-based intersection."""
    from . import layers as L
    rng = np.random.default_rng(11)
    k, nq = 10, 200
    gt = np.arange(nq * k).reshape(nq, k)
    gtd = np.sort(rng.uniform(0.2, 0.9, size=(nq, k + 1)).astype(np.float32),
                  axis=1)
    # Returned ids: some correct, some not; scores consistent with distances
    # at or inside the k-th true distance.
    pred = gt.copy()
    pred[:, 5:] = -1
    sim = 1.0 - (gtd[:, :k] ** 2) / 2.0
    id_based = recall_at(pred, gt, k)
    dist_based = L.recall_distance_based(pred, sim.astype(np.float32), gtd, k)
    assert dist_based >= id_based - 1e-12


def test_layer_tolerances_are_declared_not_chosen_per_run_synthetic():
    """The bands live in the module, so a run cannot pick its own gate."""
    from . import layers as L
    assert set(L.TOLERANCES) == set(L.CHECKS)
    assert L.TOLERANCES["corpus_reachability"] == 0.0
    assert L.TOLERANCES["metric_agreement"] <= 0.001
    assert L.TOLERANCES["recall_rule_accounting"] <= 0.01


# --------------------------------------------------------------------------
# 012b: the curve is advisory because the fixture says so
# --------------------------------------------------------------------------

def test_the_glove_fixture_declares_the_curve_advisory():
    """Not synthetic: the committed spec.

    The scope belongs to the fixture, not to whoever runs the command --
    whether a comparison may block is a property of what is being compared.
    """
    import yaml
    p = os.path.join(ROOT, "fixtures", "glove-100-angular.fixture.yaml")
    with open(p, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    assert spec["reference_curve"]["outcome_scope"] == H.ADVISORY
    # and the tolerance was NOT widened to make the points pass
    assert spec["reference_curve"]["tolerance"] == 0.02


def test_advisory_curve_lines_cannot_fail_the_run_synthetic():
    from . import _exit_code
    lines = [_line(check="glove_curve", measured=0.9, reference=0.5,
                   outcome_scope=H.ADVISORY) for _ in range(7)]
    assert all(ln["outcome"] == H.CONTRADICTED for ln in lines)
    assert _exit_code(lines) == 0


def test_blocking_layer_lines_do_fail_the_run_synthetic():
    from . import _exit_code
    ok = _line(check="corpus_reachability", measured=1.0, reference=1.0,
               tolerance=0.0)
    bad = _line(check="corpus_reachability", measured=0.086, reference=1.0,
                tolerance=0.0)
    assert _exit_code([ok]) == 0
    assert _exit_code([ok, bad]) == 1


def test_a_legacy_line_is_not_counted_as_a_pass_synthetic():
    legacy = {"date": "2026-09-10", "corpus": "c", "engine": "qdrant",
              "engine_version": "1.19.1", "config": "x",
              "simulated_recall_at_10": 0.99, "measured_recall_at_10": 0.99,
              "calibration_error_recall": 0.0, "environment_id": "pod"}
    assert H.counts([legacy])[H.COULDNT_CHECK] == 1
    assert H.counts([legacy])[H.VERIFIED] == 0
