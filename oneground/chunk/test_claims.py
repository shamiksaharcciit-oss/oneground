"""What the chunking report may not say (task 031, step 5).

Tested the way the 019 claim invariant is tested: by making the forbidden
sentence **impossible to construct**, not by checking that today's output
happens not to contain it. 019 exists because two shipped defects passed every
test in the repository -- the tests asserted presence and the defect was in
correspondence.

Three things this report may never say:

  1. that one chunking produces better ANSWERS. Nothing here measures answer
     quality. Path B is retrievability and says so in its own caveat.
  2. that a structural improvement implies a retrieval improvement. A and B
     are shown side by side precisely so a reader sees when they disagree,
     so they may never be combined, ranked, or emitted apart.
  3. anything about a corpus other than the one measured.

The guards below are structural where they can be and lexical where they
cannot. The lexical one allows a forbidden word only inside a named constant
that is a refusal -- which is how the caveats can say "not an estimate of
answer quality" without the guard firing on the word "answer".
"""

import ast
import os
import pathlib

import pytest

from oneground.chunk import measures as m
from oneground.chunk import report as rp
from oneground.chunk import selfretrieval as sr
from oneground.chunk.strategies import Chunk

PKG = pathlib.Path(__file__).parent
SOURCES = sorted(p for p in PKG.glob("*.py") if not p.name.startswith("test_"))

#: Words that assert answer quality, a recommendation, or a comparison. They
#: may appear in the package ONLY inside one of ALLOWED_CAVEATS.
FORBIDDEN_WORDS = ("answer quality", "more accurate", "better answers",
                   "recommended", "we recommend", "best strategy",
                   "outperforms", "superior", "proves", "guarantees")

#: Constants whose whole job is to deny one of the above. A forbidden word
#: inside one of these is the refusal doing its work.
ALLOWED_CAVEATS = {
    "UPPER_BOUND_CAVEAT", "BIAS_CAPTION", "TRANSFER_CAVEAT",
    "FRAGMENTED_CAPTION", "BASIS", "NOUN_PHRASE_CAVEAT",
    "UNRESOLVED_CAVEAT", "UNRESOLVED_RULE", "SENTENCE_RULE",
    "NOT_VERBATIM", "OUT_OF_ORDER",
}


def _string_constants(path):
    """(name, value) for every module-level string assignment, plus the
    docstrings, so a claim cannot hide in prose either."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.append((t.id, node.value.value))
        elif isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node)
            if doc:
                name = getattr(node, "name", "<module>")
                out.append((f"docstring:{name}", doc))
    return out


# ------------------------------------------------- 1. the vocabulary guard

def test_no_forbidden_claim_outside_a_named_refusal():
    """A forbidden word may appear only inside a constant whose job is to
    deny it. Anywhere else it is an assertion the report is not allowed to
    make."""
    offences = []
    for path in SOURCES:
        for name, value in _string_constants(path):
            if name in ALLOWED_CAVEATS or name.startswith("docstring:"):
                continue
            low = value.lower()
            for word in FORBIDDEN_WORDS:
                if word in low:
                    offences.append(f"{path.name}:{name} contains {word!r}")
    assert not offences, "\n".join(offences)


def test_the_allowed_caveats_all_exist():
    """An allowlist that names something gone is an allowlist that has
    stopped guarding."""
    live = set()
    for path in SOURCES:
        for name, _ in _string_constants(path):
            live.add(name)
    missing = sorted(ALLOWED_CAVEATS - live)
    assert not missing, f"named in ALLOWED_CAVEATS but not defined: {missing}"


def test_a_forbidden_word_in_a_new_constant_is_caught():
    """The guard has to guard: prove it fires."""
    import tempfile
    src = 'SUMMARY = "the fixed strategy produces better answers"\n'
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "sneaky.py"
        p.write_text(src, encoding="utf-8")
        found = [(n, v) for n, v in _string_constants(p)
                 if any(w in v.lower() for w in FORBIDDEN_WORDS)]
    assert found, "the vocabulary guard would not have caught it"


# ----------------------------------------------- 2. A and B are inseparable

def _result(strategy="fixed", recall=0.9, p50=100):
    ld = {"p50": p50, "p5": 10, "p95": 300, "chunks": 3, "orphans": 0,
          "tokenizer": "whitespace"}
    flag = rp.fragmented_flag(ld, recall, floor=50, high_self_recall=0.95)
    return rp.StrategyResult(
        strategy=strategy, params={"size": 512}, chunks=3,
        path_a={"length_distribution": ld, "boundary_alignment": {}},
        path_b={"self_recall_at_k": recall, "bias_caption": sr.BIAS_CAPTION,
                "upper_bound_caveat": sr.UPPER_BOUND_CAVEAT},
        flag=flag)


def test_every_strategy_row_carries_both_paths():
    """A structural improvement may not imply a retrieval improvement, so the
    two are never emitted apart -- a reader always has both or neither."""
    rep = rp.chunking_report([_result()], rp.Extraction("unstructured", "0.16"))
    for row in rep["strategies"]:
        assert row["path_a"], "path A missing: B would stand alone"
        assert row["path_b"], "path B missing: A would stand alone"


def test_the_report_names_no_winner():
    """No ranking, no best, no recommendation -- combining A and B into one
    verdict is exactly the inference the paper forbids."""
    rep = rp.chunking_report([_result("fixed", 0.9), _result("sentence", 0.7)],
                             rp.Extraction("unstructured", "0.16"))
    blob = repr(rep).lower()
    for key in ("'best'", "'winner'", "'recommended'", "'rank'", "'score'"):
        assert key not in blob, key


def test_the_bias_caption_sits_beside_every_b_column():
    rep = rp.chunking_report([_result(), _result("sentence")],
                             rp.Extraction("unstructured", "0.16"))
    for row in rep["strategies"]:
        assert "maximised by chunks too small" in row["captions"][
            "over_fragmentation_bias"]
        assert "UPPER BOUND" in row["captions"][
            "self_retrieval_is_an_upper_bound"]


def test_the_transfer_caveat_sits_beside_the_numbers():
    """Beside them, not in a footnote a renderer may drop."""
    rep = rp.chunking_report([_result()], rp.Extraction("unstructured", "0.16"))
    assert "never a comparison" in rep["captions"]["extraction_transfer"]


# ------------------------------------------------ 3. the extraction is declared

def test_a_report_without_an_extraction_declaration_is_refused():
    with pytest.raises(rp.DeclarationError):
        rp.chunking_report([_result()], extraction=None)


def test_unknown_extraction_needs_a_reason():
    """Unknown with no reason is indistinguishable from nobody having asked."""
    with pytest.raises(rp.DeclarationError) as e:
        rp.Extraction("unknown")
    assert "nobody having asked" in str(e.value)
    ok = rp.Extraction("unknown", reason="the corpus was handed over as text")
    assert ok.as_dict()["reason"]


def test_a_named_extractor_needs_its_version():
    with pytest.raises(rp.DeclarationError) as e:
        rp.Extraction("unstructured")
    assert "version" in str(e.value)


def test_the_declaration_says_oneground_neither_ran_nor_verified_it():
    d = rp.Extraction("unstructured", "0.16").as_dict()
    assert d["run_by_oneground"] is False
    assert d["verified_by_oneground"] is False


def test_the_extraction_is_carried_onto_the_result():
    rep = rp.chunking_report([_result()], rp.Extraction("unstructured", "0.16"))
    assert rep["extraction"]["tool"] == "unstructured"
    assert rep["extraction"]["version"] == "0.16"


# --------------------------------------------- 4. the one judgement it makes

def test_the_flag_cannot_exist_without_its_length_distribution():
    """`evidence` is a required positional field, so a flag with no numbers
    beside it is not constructible."""
    with pytest.raises(TypeError):
        rp.FragmentedFlag(outcome="flagged")


def test_the_flag_carries_both_thresholds_and_its_basis():
    ld = {"p50": 20, "p5": 5, "p95": 40}
    f = rp.fragmented_flag(ld, 0.99, floor=50, high_self_recall=0.95)
    d = f.as_dict()
    assert d["outcome"] == "flagged"
    assert d["thresholds"] == {"length_p50_floor": 50, "high_self_recall": 0.95}
    assert d["measured"] == {"length_p50": 20, "self_recall_at_k": 0.99}
    assert d["length_distribution"] is ld
    assert "either alone is not the fault" in d["basis"].lower()
    assert "Not recommended" in d["caption"]


def test_short_chunks_with_a_poor_score_are_not_flagged():
    """Simply a poor chunking, not the measure being gamed."""
    f = rp.fragmented_flag({"p50": 20}, 0.40, floor=50, high_self_recall=0.95)
    assert f.outcome == "not_flagged" and f.caption == ""


def test_a_high_score_with_sound_lengths_is_not_flagged():
    """That is the result the measure exists to find."""
    f = rp.fragmented_flag({"p50": 400}, 0.99, floor=50, high_self_recall=0.95)
    assert f.outcome == "not_flagged"


def test_a_missing_threshold_is_couldnt_check_never_not_flagged():
    """'Not flagged' would read as an assurance nobody gave."""
    for kwargs in ({"floor": None, "high_self_recall": 0.95},
                   {"floor": 50, "high_self_recall": None},
                   {}):
        f = rp.fragmented_flag({"p50": 20}, 0.99, **kwargs)
        assert f.outcome == "couldnt_check", kwargs
        assert "not flagged" in f.reason
        assert f.evidence, "the evidence travels even when the judgement does not"


def test_the_flag_is_the_only_judgement_in_the_report():
    """If a second one appears, it needs the same care as this one and this
    test is where that gets noticed."""
    rep = rp.chunking_report([_result()], rp.Extraction("unstructured", "0.16"))
    row = rep["strategies"][0]
    judgements = [k for k in row if k in ("fragmented", "verdict", "rating",
                                          "recommendation", "grade")]
    assert judgements == ["fragmented"], judgements


# ------------------------------------------------- 5. no model in path B

def test_no_perturbation_calls_a_model():
    """An import guard: path B may not reach for a tagger, a generator or a
    sentence-transformer, and the file that would need one is this one."""
    src = (PKG / "selfretrieval.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for banned in ("spacy", "nltk", "transformers", "sentence_transformers",
                   "torch", "openai", "anthropic"):
        assert banned not in imported, f"path B imports {banned}"
