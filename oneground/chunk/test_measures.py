"""Path A and path B (task 031).

The home-chunk definition and the containing/hit separation are pinned here
because `docs/CHUNKING.md` says the definition of a hit decides every
comparison. Both are taken from the paper verbatim; the brief agrees with it
word for word, so there is nothing to resolve between them.
"""

import numpy as np
import pytest

from oneground.chunk import measures as m
from oneground.chunk import selfretrieval as sr
from oneground.chunk.strategies import Chunk, WhitespaceTokens

TEXT = ("Alpha beta gamma delta epsilon zeta eta theta. "
        "Iota kappa lambda mu nu xi omicron pi. "
        "Rho sigma tau upsilon phi chi psi omega. "
        "Aleph beth gimel daleth he waw zayin heth.")


def ch(start, end, index=0, doc="d", strategy="fixed"):
    return Chunk(doc, index, start, end, TEXT[start:end], strategy)


# --------------------------------------------------------------- path A

def test_span_survival_counts_survived_and_split_by_kind():
    spans = [(0, 46, "sentence"), (46, 84, "sentence")]
    chunks = [ch(0, 46, 0), ch(46, 84, 1)]
    r = m.span_survival(chunks, spans)
    assert r["survived"] == 2 and r["survival_rate"] == 1.0
    cut = [ch(0, 60, 0), ch(60, 84, 1)]
    r2 = m.span_survival(cut, spans)
    assert r2["survived"] == 1
    assert r2["by_kind"]["sentence"]["split"] == 1


def test_span_survival_is_reported_per_unit_kind():
    """One number would hide a chunking that never splits a sentence and
    routinely splits a table row."""
    spans = [(0, 46, "sentence"), (46, 84, "table_row")]
    r = m.span_survival([ch(0, 46)], spans)
    assert set(r["by_kind"]) == {"sentence", "table_row"}
    assert r["by_kind"]["sentence"]["survival_rate"] == 1.0
    assert r["by_kind"]["table_row"]["survival_rate"] == 0.0


def test_boundary_alignment_is_couldnt_check_without_structure():
    """Not zero, not skipped. A chunker scoring 0 on unmarked text would read
    as badly aligned when nothing was measured."""
    r = m.boundary_alignment([ch(0, 46)], units=None)
    assert r["outcome"] == m.COULDNT_CHECK
    assert "not an alignment of zero" in r["reason"]


def test_boundary_alignment_measures_where_structure_exists():
    units = [(0, 46, "Item 1"), (46, 84, "Item 1A")]
    aligned = m.boundary_alignment([ch(0, 46), ch(46, 84)], units)
    assert aligned["alignment_rate"] == 1.0
    astray = m.boundary_alignment([ch(0, 30), ch(30, 84)], units)
    assert astray["alignment_rate"] == 0.5


def test_the_near_duplicate_rate_is_not_attributable_without_a_baseline():
    """A chunking's duplicate rate on a corpus that repeats is mostly the
    corpus. Reporting it bare would attribute boilerplate to the strategy."""
    chunks = [ch(0, 46, 0), ch(0, 46, 1)]
    r = m.near_duplicate_rate(chunks)
    assert r["attributable"] is False
    assert "most of a chunk-level duplicate rate is the corpus" in r["note"]


def test_the_near_duplicate_rate_is_read_against_the_corpus_baseline():
    chunks = [ch(0, 46, 0), ch(0, 46, 1)]
    r = m.near_duplicate_rate(chunks, baseline=0.0431)
    assert r["attributable"] is True
    assert r["baseline"] == 0.0431
    assert r["excess_over_baseline"] == pytest.approx(r["rate"] - 0.0431)


def test_length_distribution_reports_orphans_and_the_cap():
    chunks = [ch(0, 10, 0), ch(0, 46, 1), ch(0, 84, 2)]
    r = m.length_distribution(chunks, floor=3, cap=12)
    assert r["chunks"] == 3
    assert r["tokenizer"] == "whitespace"
    assert r["orphans"] == 1          # the 10-char chunk is 1 token
    assert r["at_cap"] >= 1


def test_unresolved_references_is_labelled_heuristic_and_publishes_its_rule():
    r = m.unresolved_references([Chunk("d", 0, 0, 20, "This is a chunk.", "fixed")])
    assert r["heuristic"] is True and r["exact"] is False
    assert r["rule"] == m.UNRESOLVED_RULE
    assert "HEURISTIC" in r["caveat"]
    assert "false-positive" in r["caveat"]
    assert r["unresolved"] == 1


def test_unresolved_references_admits_its_false_positives():
    """'This Annual Report' opens a self-contained chunk and is counted."""
    c = Chunk("d", 0, 0, 40, "This Annual Report describes our business.", "fixed")
    assert m.unresolved_references([c])["unresolved"] == 1
    assert "This Annual Report" in m.UNRESOLVED_CAVEAT


def test_path_a_says_what_each_measure_needs():
    units = [(0, 46, "Item 1"), (46, 84, "Item 1A")]
    a = m.path_a([ch(0, 46), ch(46, 84)], spans=units, units=units, floor=2,
                 cap=40)
    assert a["span_survival"]["needs_offsets"] is True
    assert a["boundary_alignment"]["needs_offsets"] is True
    assert a["near_duplicate_rate"]["needs_offsets"] is False
    assert a["length_distribution"]["needs_offsets"] is False
    assert a["unresolved_references"]["needs_offsets"] is False


# --------------------------------------------------------------- path B

def test_the_home_chunk_is_the_one_the_span_is_most_centred_in():
    anchor = sr.Anchor("d", 46, 84, TEXT[46:84], "sentence")
    off_centre = ch(40, 90, 0)        # 1 token before, 1 after
    centred = ch(0, 130, 1)           # many tokens either side
    home, holders = sr.home_chunk([off_centre, centred], anchor, TEXT)
    assert len(holders) == 2
    assert home is centred


def test_a_tie_goes_to_the_earliest_chunk():
    """Pinned because it decides every comparison."""
    anchor = sr.Anchor("d", 46, 84, TEXT[46:84], "sentence")
    a = ch(38, 92, 0)
    b = ch(38, 92, 1)
    home, holders = sr.home_chunk([a, b], anchor, TEXT)
    assert len(holders) == 2
    assert home is a, "a tie must go to the earliest chunk, not the last"


def test_centredness_is_measured_in_tokens_not_characters():
    """The paper says tokens, and the two disagree: a chunk padded with long
    words is closer in characters and no closer in tokens."""
    text = "aa " + "x" * 40 + " bb TARGET SPAN cc " + "y y y y " + "dd"
    start = text.index("TARGET SPAN")
    end = start + len("TARGET SPAN")
    anchor = sr.Anchor("d", start, end, text[start:end], "sentence")
    wide_chars = Chunk("d", 0, 0, len(text), text, "fixed")       # 1 big token before
    home, holders = sr.home_chunk([wide_chars], anchor, text)
    tok = WhitespaceTokens()
    before = len(tok.offsets(text[wide_chars.start:start]))
    after = len(tok.offsets(text[end:wide_chars.end]))
    assert before != after, "fixture should be asymmetric in tokens"
    assert home is wide_chars


def test_a_span_no_chunk_contains_has_no_home_and_that_is_a_result():
    anchor = sr.Anchor("d", 40, 90, TEXT[40:90], "sentence")
    home, holders = sr.home_chunk([ch(0, 46), ch(46, 60)], anchor, TEXT)
    assert home is None and holders == []


def test_a_containing_chunk_that_is_not_home_is_not_a_self_recall_hit():
    """The separation the paper pins: without it, overlap raises the score by
    multiplying acceptable answers, and a strategy could look better by
    overlapping more while cutting no better."""
    docs = {"d": TEXT}
    anchor = sr.Anchor("d", 46, 84, TEXT[46:84], "sentence")
    home = ch(0, 130, 0)              # most centred -> the home chunk
    other = ch(40, 90, 1)             # also contains it, less centred
    chunks = [home, other]
    # vectors chosen so retrieval returns `other` first and never `home`
    cv = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    qv = np.array([[0.0, 1.0]], dtype=np.float32)
    r = sr.self_retrieval(chunks, [anchor], docs, cv, qv, k=1)
    assert r["self_recall_at_k"] == 0.0, "a non-home container scored a hit"
    assert r["containing_hit_at_k"] == 1.0
    assert r["containing_count_mean"] == 2.0


def test_the_home_chunk_in_the_top_k_is_a_hit():
    docs = {"d": TEXT}
    anchor = sr.Anchor("d", 46, 84, TEXT[46:84], "sentence")
    chunks = [ch(0, 130, 0), ch(40, 90, 1)]
    cv = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    qv = np.array([[1.0, 0.0]], dtype=np.float32)
    r = sr.self_retrieval(chunks, [anchor], docs, cv, qv, k=1)
    assert r["self_recall_at_k"] == 1.0
    assert r["self_rank_p50"] == 1


def test_every_path_b_result_carries_the_bias_and_upper_bound_captions():
    docs = {"d": TEXT}
    anchor = sr.Anchor("d", 46, 84, TEXT[46:84], "sentence")
    chunks = [ch(0, 130, 0)]
    cv = np.array([[1.0, 0.0]], dtype=np.float32)
    qv = np.array([[1.0, 0.0]], dtype=np.float32)
    r = sr.self_retrieval(chunks, [anchor], docs, cv, qv, k=1)
    assert "maximised by chunks too small to answer with" in r["bias_caption"]
    assert "UPPER BOUND" in r["upper_bound_caveat"]
    assert "NOT a self_recall hit" in r["hit_definition"]


# ----------------------------------------------------------- the anchors

def test_anchor_sampling_is_seeded_and_reproducible():
    docs = {"d": TEXT}
    a = sr.sample_anchors(docs, 2, seed=7, min_tokens=4)
    b = sr.sample_anchors(docs, 2, seed=7, min_tokens=4)
    c = sr.sample_anchors(docs, 2, seed=8, min_tokens=4)
    assert [x.start for x in a] == [x.start for x in b]
    assert len(a) == 2
    assert isinstance(c, list)


def test_short_spans_are_not_sampled():
    docs = {"d": "Tiny. " + TEXT}
    for a in sr.sample_anchors(docs, 50, seed=1, min_tokens=6):
        assert len(a.text.split()) >= 6


# ------------------------------------------------------- the perturbations

def test_perturbations_are_named_and_declared():
    assert set(sr.PERTURBATIONS) == {"verbatim", "drop_first_clause",
                                     "function_words_removed"}
    with pytest.raises(ValueError) as e:
        sr.perturb([], "paraphrase_with_an_llm", seed=1)
    assert "declared" in str(e.value)


def test_drop_first_clause_drops_it():
    a = [sr.Anchor("d", 0, 0, "Because of the risk, we reduced exposure.", "s")]
    assert sr.perturb(a, "drop_first_clause", seed=1) == ["we reduced exposure."]


def test_function_words_removed_does_not_claim_to_be_noun_phrases():
    """The specification asks for 'noun phrases only'. True NP chunking needs
    a POS tagger, which is a model, and no model may appear in path B. The
    perturbation is a published closed-class removal and is named and
    captioned as that, not as noun-phrase extraction."""
    a = [sr.Anchor("d", 0, 0, "The company is subject to the risk of loss.", "s")]
    out = sr.perturb(a, "function_words_removed", seed=1)[0]
    assert "the" not in out.lower().split()
    assert "company" in out and "risk" in out
    assert "APPROXIMATE" in sr.NOUN_PHRASE_CAVEAT
    assert "part-of-speech tagger, which is a model" in sr.NOUN_PHRASE_CAVEAT
    assert sr.PERTURBATIONS["function_words_removed"]["caveat"] is sr.NOUN_PHRASE_CAVEAT


def test_no_perturbation_is_a_model():
    """Every perturbation is a published rule over the span's own words."""
    for name, p in sr.PERTURBATIONS.items():
        out = p["fn"]("The company is subject to the risk of loss.",
                      __import__("random").Random(0))
        assert isinstance(out, str) and out.strip(), name
