"""The three registers, and the refusal that keeps them apart.

**Synthetic throughout.** Nothing here loads a model: what is under test is
the classification of measures and the refusal, which is the part the brief
says must be settled in the code rather than left to a reader.

Most of this file is attempts to build the false table, because that is the
only thing that shows the refusal works. A module that merely documents the
distinction would pass a test that asserts the documentation exists.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.embed import compare as C                        # noqa: E402


def _obs(model="m", dim=768, **kw):
    kw.setdefault("comparable", {"boundary_crispness": 0.03})
    kw.setdefault("per_model", {"recall_at_10": 0.93})
    kw.setdefault("ground_truth_sha256", "a" * 64)
    return C.ModelObservation(model=model, dimension=dim,
                              max_seq_length=512, **kw)


# ------------------------------------------------------------ the registers
def test_every_measure_belongs_to_exactly_one_register():
    seen = {}
    for register, names in (("comparable", C.COMPARABLE),
                            ("per_model", C.PER_MODEL),
                            ("not_measurable", C.NOT_MEASURABLE)):
        for n in names:
            assert n not in seen, (
                "%s is in both %s and %s; a measure in two registers is a "
                "measure nobody has decided about" % (n, seen.get(n), register))
            seen[n] = register
            assert C.register_of(n) == register


def test_recall_is_never_comparable_across_models():
    """The brief's central constraint, as an assertion.

    Under model A recall is measured against A's neighbours, under B against
    B's. Both correct, different questions.
    """
    for name in ("recall_at_1", "recall_at_10", "recall_at_100"):
        assert C.register_of(name) == "per_model"
        with pytest.raises(C.ComparisonRefused) as e:
            C.refuse_if_not_comparable([name])
        assert "own ground truth" in str(e.value)


def test_the_geometry_measures_are_comparable():
    C.refuse_if_not_comparable(
        ["boundary_crispness", "intrinsic_dimensionality",
         "ambiguous_query_rate", "skew_top10_share", "routing_ceiling",
         "storage_amplification"])


def test_answer_quality_is_refused_as_not_measurable_at_all():
    with pytest.raises(C.ComparisonRefused) as e:
        C.refuse_if_not_comparable(["answer_quality"])
    assert "relevance labels" in str(e.value)


def test_an_unclassified_measure_is_refused_rather_than_assumed():
    """The default must be refusal.

    A measure nobody has classified is not one this module can promise is
    comparable, and defaulting to yes is exactly how the false table gets
    built by someone adding a column in a hurry.
    """
    with pytest.raises(C.ComparisonRefused) as e:
        C.refuse_if_not_comparable(["some_new_measure"])
    assert "not classified" in str(e.value)
    assert "deliberately" in str(e.value)


# -------------------------------------------------------------- the artifact
def test_building_a_comparison_refuses_recall_in_the_comparable_block():
    bad = _obs(comparable={"recall_at_10": 0.93})
    with pytest.raises(C.ComparisonRefused):
        C.build_comparison([bad])


def test_building_a_comparison_refuses_geometry_hidden_under_per_model():
    """The mirror of the defect, and it is a defect too.

    Putting a comparable measure under `per_model` does not assert anything
    false, but it hides a comparison the task exists to make, and it would
    leave the geometry unstated while the recall got all the attention.
    """
    bad = _obs(comparable={}, per_model={"boundary_crispness": 0.03})
    with pytest.raises(C.ComparisonRefused) as e:
        C.build_comparison([bad])
    assert "boundary_crispness" in str(e.value)


def test_a_comparison_carries_all_three_registers_and_names_ground_truth():
    got = C.build_comparison([_obs("a"), _obs("b", dim=384)],
                             corpus="arxiv-150k", anchor="a")
    assert set(got) >= {"comparable", "per_model", "not_measurable",
                        "confounds"}
    # every per-model value is printed with the answer key it was scored on
    for model, block in got["per_model"]["by_model"].items():
        assert block["ground_truth_sha256"], model
    # and the limit is in the artifact, not only the documentation
    assert "relevance labels" in got["not_measurable"]["statement"]


def test_the_rendering_keeps_recall_out_of_the_comparable_table():
    text = C.render(C.build_comparison([_obs("a"), _obs("b", dim=384)],
                                       corpus="arxiv-150k"))
    comparable_block = text.split("PER MODEL")[0]
    assert "recall_at_10" not in comparable_block
    assert "boundary_crispness" in comparable_block
    assert "NOT a comparison" in text


# --------------------------------------------------------------- the confounds
def test_dimension_is_separated_from_geometry():
    got = C.dimension_attributable([_obs("big", dim=768),
                                    _obs("small", dim=384)])
    assert got["bytes_per_vector"]["big"] == 768 * 4
    assert got["relative_to_smallest"]["big"] == 2.0
    assert "unrelated to how well it separates" in got["note"]


def test_a_model_that_truncates_much_more_is_flagged_as_a_confound():
    a = _obs("reads-it-all", truncation={"truncated_fraction": 0.01})
    b = _obs("reads-half", truncation={"truncated_fraction": 0.50})
    got = C.truncation_confound([a, b])
    assert [f["model"] for f in got["flagged"]] == ["reads-half"]
    assert "confound, not a finding" in got["flagged"][0]["why"]


def test_similar_truncation_rates_are_not_flagged():
    a = _obs("a", truncation={"truncated_fraction": 0.010})
    b = _obs("b", truncation={"truncated_fraction": 0.015})
    assert C.truncation_confound([a, b])["flagged"] == []


def test_truncation_with_nothing_to_compare_is_couldnt_check_not_zero():
    got = C.truncation_confound([_obs("only-one",
                                      truncation={"truncated_fraction": 0.2})])
    assert got["checked"] is False
    assert "couldn't-check" in got["reason"]
