"""Running one characterization per model, and what is refused before it runs.

**Synthetic throughout, and no model is loaded.** The parts that need weights
are `resolve`/`probe_rate`, which are exercised in the task's own measurements
rather than in a test that would download half a gigabyte to assert a shape.
What is tested here is the orchestration and every refusal, because those are
the parts that decide whether a false comparison can be built.
"""

import json
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import intake                                    # noqa: E402
from oneground.embed import compare as C                        # noqa: E402
from oneground.embed import multimodel as M                     # noqa: E402
from oneground.embed.registry import ResolvedModel              # noqa: E402


def _resolved(name="BAAI/bge-base-en-v1.5", dim=768, limit=512):
    return ResolvedModel(name=name, dimension=dim, max_seq_length=limit,
                         weights_sha256="b" * 64, device="cpu", model=None)


# ------------------------------------------------------------------ workdirs
def test_each_model_gets_its_own_workdir_and_the_slug_is_path_safe():
    got = M.workdir_for("runs/x", "BAAI/bge-base-en-v1.5")
    assert got == os.path.join("runs/x", "models", "BAAI__bge-base-en-v1.5")
    assert "/" not in os.path.basename(got)


# -------------------------------------------------------------- the registers
def test_a_characterization_is_sorted_into_the_registers():
    out = {"characterization": {"boundary_crispness": 0.03,
                                "intrinsic_dimensionality": 32.5,
                                "recall_at_10": 0.93},
           "ground_truth_sha256": "c" * 64, "n_base": 100, "n_queries": 10}
    obs, stray = M.observation_from(out, _resolved())
    assert obs.comparable == {"boundary_crispness": 0.03,
                              "intrinsic_dimensionality": 32.5}
    assert obs.per_model == {"recall_at_10": 0.93}
    assert not stray
    assert obs.ground_truth_sha256 == "c" * 64


def test_an_unclassified_measure_is_reported_not_silently_dropped():
    out = {"characterization": {"boundary_crispness": 0.03,
                                "some_new_measure": 1.0}}
    obs, stray = M.observation_from(out, _resolved())
    assert stray == ["some_new_measure"]
    assert "some_new_measure" not in obs.comparable
    assert "some_new_measure" not in obs.per_model


def test_the_artifact_records_unclassified_measures_where_someone_sees_them(
        tmp_path):
    obs, _ = M.observation_from(
        {"characterization": {"boundary_crispness": 0.03}}, _resolved("a"))
    obs2, _ = M.observation_from(
        {"characterization": {"boundary_crispness": 0.05}}, _resolved("b", 384))
    path = str(tmp_path / "models.json")
    payload = M.write_comparison(path, [obs, obs2], corpus="x",
                                 unclassified=["mystery"])
    assert payload["unclassified_measures"]["measures"] == ["mystery"]
    assert "never assumed comparable" in \
        payload["unclassified_measures"]["note"]
    assert os.path.exists(os.path.splitext(path)[0] + ".txt")
    written = json.load(open(path, encoding="utf-8"))
    assert written["comparable"]["measures"][0]["measure"] == \
        "boundary_crispness"


def test_a_false_comparison_cannot_be_written(tmp_path):
    """The refusal reaches the artifact writer, not only the checker."""
    bad = C.ModelObservation(model="a", dimension=768, max_seq_length=512,
                             comparable={"recall_at_10": 0.9})
    with pytest.raises(C.ComparisonRefused):
        M.write_comparison(str(tmp_path / "models.json"), [bad])


def test_one_model_is_refused_here_and_belongs_on_the_unchanged_path():
    """Published values depend on the single-model path staying untouched."""
    req = type("R", (), {"models": ["only-one"]})()
    with pytest.raises(ValueError) as e:
        M.run(req, "r.yaml", "runs/x", characterize_run=lambda *a: {})
    assert "keeps published labels" in str(e.value)


# ------------------------------------------------------- intake's refusals
def _write(tmp_path, text_block):
    doc = {
        "name": "t", "run": {"seed": 1, "workdir": str(tmp_path / "w")},
        "corpus": {"sample": {
            "kind": "receipt",
            "text": {"path": "c.jsonl", "text_field": "text", **text_block},
            "queries": {"path": "q.jsonl"},
        }},
    }
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    (tmp_path / "c.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "q.jsonl").write_text("{}\n", encoding="utf-8")
    return str(p)


def _refusal(tmp_path, text_block):
    with pytest.raises(intake.RequirementsError) as e:
        intake.load(_write(tmp_path, text_block))
    return str(e.value)


def test_naming_both_model_and_models_is_refused(tmp_path):
    msg = _refusal(tmp_path, {"model": "a", "models": ["a", "b"]})
    assert "are both set" in msg
    assert "which of them produced the vectors" in msg


def test_an_empty_models_list_is_not_a_default(tmp_path):
    msg = _refusal(tmp_path, {"models": []})
    assert "there is no default" in msg


def test_a_model_listed_twice_is_refused(tmp_path):
    msg = _refusal(tmp_path, {"models": ["a", "b", "a"]})
    assert "more than once" in msg
    assert "its own embedding pass" in msg


def test_text_with_no_model_at_all_is_still_refused(tmp_path):
    msg = _refusal(tmp_path, {})
    assert "neither" in msg and "models" in msg


def test_one_model_and_a_list_of_one_are_the_same_run(tmp_path):
    """Task 036 step 7: `model` at its default must not re-label."""
    os.makedirs(tmp_path / "a", exist_ok=True)
    os.makedirs(tmp_path / "b", exist_ok=True)
    a = intake.load(_write(tmp_path / "a", {"model": "m"}))
    b = intake.load(_write(tmp_path / "b", {"models": ["m"]}))
    assert a.models == b.models == ["m"]
    assert a.model == "m"
