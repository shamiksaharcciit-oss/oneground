"""`oneground.library.card_schema`. `docs/LIBRARY.md` §2, §5.

    python oneground/library/test_card_schema.py
    pytest oneground/library/test_card_schema.py
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.library import card_schema as sch  # noqa: E402


def _well_formed_card():
    """Every required field, once, satisfying every rule. Mutated per test
    rather than rebuilt, so a passing baseline is proven once."""
    return {
        "card_id": "card-2026-09-25-abcdef",
        "publisher": "oneground contributor",
        "licence": "CC-BY-4.0",
        "corpus": {
            "vectors_sha256": "a" * 64,
            "characterization": {
                "intrinsic_dimensionality": 12.4,
                "boundary_crispness": 0.021,
                "skew_top10_share": 0.31,
                "ambiguous_query_rate": 0.07,
                "drift_before": 0.02,
                "drift_after": 0.05,
                "drift_cutoff": "2026-08-01",
                "definitions": {"crispness_ratio": 1.2, "ambiguity_ratio": 0.9,
                                "centroids": 32, "seed": 20260101},
            },
            "dimension": 768,
            "n_base": 150000,
            "n_queries": 2000,
            "documents": {"domain": "support tickets", "language": "en",
                         "typical_length": "short"},
            "full_size": 500000,
            "sample_size": 150000,
            "sampling_seed": 20260101,
            "resolvability": "private corpus, digests only",
            "embedding_model": None,
        },
        "instrument": {
            "oneground": {"baseline": {"version": "0.4.0", "commit": "abc123"},
                         "changed": {"version": "0.4.0", "commit": "abc123"}},
            "deterministic": True,
            "repeats": {"count": 3, "spread": 0.0012},
            "hardware": {"cpu": "AMD EPYC 7B13", "cores": 16, "ram": "40GB",
                        "threads": 16},
            "calibration_line": "recall_at_10: tolerance 0.006",
            "comparability": {"verdict": "comparable",
                             "reason": "same commit, same libraries, same "
                                      "sample, same seed, same pod"},
        },
        "finding": {
            "baseline_metrics": {"recall_at_10": 0.874},
            "changed_metrics": {"recall_at_10": 0.912},
            "decomposition": None,
            "threshold_basis": "the fixture's own published tolerance",
            "verified": "simulator_only",
            "cost": {"estimate_eur": 0.0, "note": "no infra change"},
        },
        "prediction": {"digest": "b" * 64, "cited_by_run": True},
        "denominator": {"proposals_run_on_this_corpus": 17,
                        "proposals_published": 3},
    }


def test_a_well_formed_card_is_accepted():
    sch.submit_card(_well_formed_card())        # raises nothing


def test_a_card_with_denominator_withheld_is_accepted():
    card = _well_formed_card()
    card["denominator"] = "withheld"
    sch.submit_card(card)


# ----------------------------------------------- §2.1 missing characterization
def test_a_card_with_no_corpus_characterization_is_refused_naming_every_field():
    """The instance §3 names explicitly: 'A card without a characterization
    is not published; it is rejected at submission, with the missing
    fields named.'"""
    card = _well_formed_card()
    del card["corpus"]["characterization"]
    with pytest.raises(sch.LibraryCardRefused) as exc:
        sch.submit_card(card)
    msg = str(exc.value)
    for field in ("intrinsic_dimensionality", "boundary_crispness",
                 "skew_top10_share", "ambiguous_query_rate"):
        assert f"corpus.characterization.{field}" in msg, msg


def test_missing_fields_across_multiple_groups_are_all_named_at_once():
    """Not the first problem -- every problem, the same shape
    `fixture verify` refuses in."""
    card = _well_formed_card()
    del card["corpus"]["dimension"]
    del card["instrument"]["deterministic"]
    del card["finding"]["threshold_basis"]
    with pytest.raises(sch.LibraryCardRefused) as exc:
        sch.submit_card(card)
    msg = str(exc.value)
    assert "corpus.dimension" in msg
    assert "instrument.deterministic" in msg
    assert "finding.threshold_basis" in msg


# -------------------------------------------------------- embedding_model
def test_embedding_model_may_be_null_but_must_be_present():
    card = _well_formed_card()
    card["corpus"]["embedding_model"] = None
    sch.submit_card(card)                        # null is fine

    del card["corpus"]["embedding_model"]
    with pytest.raises(sch.LibraryCardRefused, match="embedding_model"):
        sch.submit_card(card)                    # absent is not


# --------------------------------------------------------- §5 prediction
def test_a_prediction_digest_not_cited_by_the_run_is_not_a_card():
    card = _well_formed_card()
    card["prediction"]["cited_by_run"] = False
    with pytest.raises(sch.LibraryCardRefused, match="not a card"):
        sch.submit_card(card)


def test_a_card_with_no_prediction_digest_is_refused():
    card = _well_formed_card()
    del card["prediction"]["digest"]
    with pytest.raises(sch.LibraryCardRefused,
                       match="prediction.digest is missing"):
        sch.submit_card(card)


# --------------------------------------------------- §5 comparability verdict
def test_not_comparable_is_refused_as_a_result():
    card = _well_formed_card()
    card["instrument"]["comparability"]["verdict"] = "not_comparable"
    with pytest.raises(sch.LibraryCardRefused, match="not_comparable"):
        sch.submit_card(card)


def test_couldnt_check_comparability_is_accepted():
    """§5: 'couldnt_check is not a refusal... a rule that refused it would
    refuse everything.'"""
    card = _well_formed_card()
    card["instrument"]["comparability"]["verdict"] = "couldnt_check"
    sch.submit_card(card)


def test_an_unrecognised_comparability_value_is_refused():
    card = _well_formed_card()
    card["instrument"]["comparability"]["verdict"] = "probably fine"
    with pytest.raises(sch.LibraryCardRefused, match="not one of"):
        sch.submit_card(card)


# ------------------------------------------------------------- §2.4 denominator
def test_a_missing_denominator_is_refused():
    card = _well_formed_card()
    del card["denominator"]
    with pytest.raises(sch.LibraryCardRefused, match="denominator is missing"):
        sch.submit_card(card)


def test_a_partial_denominator_is_refused_not_silently_accepted():
    """§2.4: 'a partial characterization is worse than none' -- the same
    rule applies to the denominator: a soft number beside hard ones."""
    card = _well_formed_card()
    card["denominator"] = {"proposals_run_on_this_corpus": 17}
    with pytest.raises(sch.LibraryCardRefused,
                       match="proposals_published"):
        sch.submit_card(card)


def test_a_denominator_of_the_wrong_shape_is_refused():
    card = _well_formed_card()
    card["denominator"] = 17
    with pytest.raises(sch.LibraryCardRefused,
                       match="neither a counts dict nor"):
        sch.submit_card(card)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
