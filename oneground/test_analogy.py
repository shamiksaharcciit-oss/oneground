"""The fixture analogy, and the honesty rules that shape it.

**Synthetic fixtures throughout**, except the two tests named `_real_specs`,
which read the shipped `fixtures/*.fixture.yaml`. The property under test is
that an analogy is never a verdict and a weak match is never presented as a
strong one.

    python oneground/test_analogy.py
    pytest oneground/test_analogy.py
"""

import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground import analogy as A                # noqa: E402

PAPERS = {"corpus_type": "papers", "text_length": "medium",
          "topics_trend": True, "time_ordered": True, "dimension": 768,
          "model_family": "bge"}
TICKETS = {"corpus_type": "support_tickets", "text_length": "short",
           "topics_trend": True, "time_ordered": True, "dimension": 768,
           "embedding_model": "BAAI/bge-base-en-v1.5"}


def _fixtures(tmp, specs):
    """Write `{id: analogy}` as fixture spec files and return the directory."""
    d = os.path.join(tmp, "fixtures")
    os.makedirs(d, exist_ok=True)
    for fid, analogy in specs.items():
        with open(os.path.join(d, f"{fid}.fixture.yaml"), "w",
                  encoding="utf-8", newline="\n") as f:
            yaml.safe_dump({"fixture": {"id": fid, "status": "built"},
                            "analogy": analogy,
                            "characterization": {
                                "intrinsic_dimensionality":
                                    {"value": 32.55, "tolerance": 0.5},
                                "drift": {"value_before": 0.52,
                                          "value_after": 0.55,
                                          "tolerance": 0.02},
                                "kind": "receipt"}}, f)
    return d


# ------------------------------------------------------------- the weighting
def test_corpus_type_outranks_everything_else_together_synthetic():
    """A papers fixture is a poor analogy for a ticket queue however well the
    other five fields agree. An earlier draft's weighting said otherwise."""
    others = sum(v for k, v in A.WEIGHTS.items() if k != "corpus_type")
    assert A.WEIGHTS["corpus_type"] > others, A.WEIGHTS
    total = sum(A.WEIGHTS.values())
    right_type_rest_wrong = A.WEIGHTS["corpus_type"] / total
    wrong_type_rest_right = others / total
    assert right_type_rest_wrong > wrong_type_rest_right


def test_a_wrong_corpus_type_can_never_reach_the_floor_synthetic():
    others = sum(v for k, v in A.WEIGHTS.items() if k != "corpus_type")
    assert others / sum(A.WEIGHTS.values()) < A.MIN_SCORE


def test_silence_is_not_agreement_synthetic():
    """A field neither side states cannot count for or against; counting it as
    agreement would let an empty declaration match everything."""
    sc, matched, differed, unknown = A.score({}, {})
    assert sc == 0.0 and matched == [] and differed == []
    assert set(unknown) == set(A.WEIGHTS)


def test_an_exact_declaration_scores_one_synthetic():
    # The two sides carry the model differently on purpose: a user declares
    # `embedding_model` (what they can answer), a fixture declares
    # `model_family` (what it can be matched on). `score` derives the family
    # from the user's side.
    declared = dict(PAPERS, embedding_model="BAAI/bge-base-en-v1.5")
    declared.pop("model_family")
    sc, matched, differed, unknown = A.score(declared, dict(PAPERS))
    assert sc == 1.0, (sc, differed)
    assert not differed and not unknown, (differed, unknown)
    assert "model_family" in matched, matched


# ------------------------------------------------------------- choosing
def test_the_nearest_fixture_is_chosen_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixtures(tmp, {"papers-fx": PAPERS,
                            "tickets-fx": dict(PAPERS,
                                               corpus_type="support_tickets",
                                               text_length="short")})
        a, why = A.choose(TICKETS, fixtures_dir=d)
        assert a is not None, why
        assert a.fixture == "tickets-fx", (a.fixture, why)
        assert "corpus_type" in a.matched


def test_no_fixture_close_enough_is_no_analogy_synthetic():
    """A default is not an analogy, and the reason says so."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixtures(tmp, {"papers-fx": PAPERS})
        a, why = A.choose(TICKETS, fixtures_dir=d)
        assert a is None
        assert "not close enough" in why or "close enough" in why, why
        assert "papers-fx" in why and "0." in why, why
        assert "default, not an analogy" in why, why


def test_none_disables_the_analogy_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixtures(tmp, {"papers-fx": PAPERS})
        a, why = A.choose(dict(PAPERS, nearest_fixture="none"), fixtures_dir=d)
        assert a is None and "none" in why


def test_a_named_fixture_is_used_and_says_it_was_not_matched_synthetic():
    """An override is honoured, and the reason must not imply it was chosen on
    merit -- a user who names a poor analogy should see that they named it."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixtures(tmp, {"papers-fx": PAPERS})
        a, why = A.choose(dict(TICKETS, nearest_fixture="papers-fx"),
                          fixtures_dir=d)
        assert a is not None and a.fixture == "papers-fx"
        assert "not chosen by matching" in why, why
        assert a.score < A.MIN_SCORE, a.score


def test_a_named_fixture_that_does_not_exist_says_what_does_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixtures(tmp, {"papers-fx": PAPERS})
        a, why = A.choose(dict(TICKETS, nearest_fixture="nope"),
                          fixtures_dir=d)
        assert a is None
        assert "nope" in why and "papers-fx" in why, why


def test_a_fixture_without_an_analogy_block_is_skipped_synthetic():
    """A spec that has not said what it is like cannot be matched against, and
    inferring its character from its measured values would be fitting the
    analogy to the answer."""
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "fixtures")
        os.makedirs(d)
        with open(os.path.join(d, "bare.fixture.yaml"), "w",
                  encoding="utf-8") as f:
            yaml.safe_dump({"fixture": {"id": "bare"},
                            "characterization": {"x": {"value": 1}}}, f)
        assert A.load_fixture_analogies(d) == []
        a, why = A.choose(PAPERS, fixtures_dir=d)
        assert a is None and "analogy" in why


def test_the_label_names_the_fixture_and_denies_the_corpus_synthetic():
    """The words that must appear wherever the fixture's numbers appear."""
    a = A.Analogy("arxiv-150k", 1.0, ["corpus_type"], [], [], "spec.yaml")
    label = a.label()
    assert "arxiv-150k" in label
    assert "not on your corpus" in label
    d = a.as_dict()
    assert d["kind"] == "declared"
    assert "not on your corpus" in d["note"]


def test_the_reason_is_always_a_sentence_synthetic():
    """"No analogy" with no explanation is indistinguishable from a bug."""
    with tempfile.TemporaryDirectory() as tmp:
        for declared in (TICKETS, {}, dict(PAPERS, nearest_fixture="none")):
            _a, why = A.choose(declared, fixtures_dir=_fixtures(
                tmp, {"papers-fx": PAPERS}))
            assert isinstance(why, str) and len(why) > 20, why


def test_no_analogy_ever_returns_a_number_about_your_corpus_synthetic():
    """The whole point. An Analogy carries a fixture id, a score and a reason,
    and nothing that could be mistaken for a measurement of the user's data."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixtures(tmp, {"papers-fx": PAPERS})
        a, _why = A.choose(PAPERS, fixtures_dir=d)
        assert a is not None
        for key in a.as_dict():
            assert key in ("fixture", "score", "matched", "differed",
                           "unknown", "spec", "kind", "note"), key


def test_the_model_family_is_derived_crudely_and_only_helps_synthetic():
    assert A._model_family("BAAI/bge-base-en-v1.5") == "bge"
    assert A._model_family("sentence-transformers/all-MiniLM-L6-v2") == "all"
    assert A._model_family(None) is None
    # And it can never decide on its own: smallest share available.
    assert A.WEIGHTS["model_family"] == min(A.WEIGHTS.values())


# ------------------------------------------------------- the shipped specs
def test_arxiv_150k_declares_an_analogy_real_specs():
    found = dict((fid, an) for fid, an, _p, _s in A.load_fixture_analogies())
    assert "arxiv-150k" in found, sorted(found)
    an = found["arxiv-150k"]
    assert an["corpus_type"] == "papers", an
    assert an["kind"] == "declared", an
    for field in ("text_length", "topics_trend", "time_ordered", "dimension"):
        assert field in an, field


def test_a_papers_declaration_matches_arxiv_150k_real_specs():
    a, why = A.choose({"corpus_type": "papers", "text_length": "medium",
                       "topics_trend": True, "time_ordered": True,
                       "dimension": 768,
                       "embedding_model": "BAAI/bge-base-en-v1.5"})
    assert a is not None, why
    assert a.fixture == "arxiv-150k"
    assert a.score == 1.0, a.score


def test_a_ticket_queue_gets_no_analogy_from_the_shipped_fixtures_real_specs():
    """The honest answer: no shipped fixture is a support-ticket corpus, so
    there is no analogy for one.

    *Which* fixture comes nearest is deliberately not asserted -- it moves as
    fixtures are added, and task 016 moved it from arxiv-150k to
    stackexchange-150k because a Q&A corpus is genuinely nearer to a ticket
    queue than paper abstracts are. What must not move is the verdict: below
    the floor `choose` returns nothing, names the nearest and its score, and
    refuses to dress a default up as an analogy.
    """
    a, why = A.choose({"corpus_type": "support_tickets", "text_length": "short",
                       "topics_trend": True, "time_ordered": True,
                       "dimension": 768,
                       "embedding_model": "BAAI/bge-base-en-v1.5"})
    assert a is None, a.fixture if a else None
    assert "default, not an analogy" in why, why
    assert f"floor of {A.MIN_SCORE:.2f}" in why, why
    assert "differs on corpus_type" in why, why
    # The nearest is named, and it is one of the shipped fixtures.
    shipped = {fid for fid, _an, _p, _s in A.load_fixture_analogies()}
    assert any(fid in why for fid in shipped), (why, sorted(shipped))


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
    print(f"\n{len(tests) - failed} passed, {failed} failed "
          f"(of {len(tests)} collected)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
