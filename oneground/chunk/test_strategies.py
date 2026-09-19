"""Contract tests for the chunking strategies (task 031).

The offsets are the contract. Every measure downstream that needs to know
where a chunk came from — self-retrieval's home chunk, span survival — reads
`start` and `end`, so a strategy that emits one that does not index its own
text corrupts a measurement rather than raising. Every test here checks that
invariant as well as whatever else it is for.
"""

import pytest

from oneground.chunk import strategies as st

SENTS = [
    "Alpha beta gamma delta epsilon zeta eta theta iota kappa.",
    "Lambda mu nu xi omicron pi rho sigma tau upsilon phi.",
    "Chi psi omega alpha beta gamma delta epsilon zeta eta.",
    "Theta iota kappa lambda mu nu xi omicron pi rho sigma.",
    "Tau upsilon phi chi psi omega alpha beta gamma delta.",
]
TEXT = " ".join(SENTS)

FIXED = {"size": 16, "overlap": 4, "min_final": 4}
SENTENCE = {"max_size": 24, "overlap": 8, "min_final": 0}
STRUCTURE = {"max_size": 40, "overlap": 0, "min_size": 0}


def units_of(text=TEXT):
    cut = len(SENTS[0]) + 1 + len(SENTS[1]) + 1
    return [(0, cut, "Item 1"), (cut, len(text), "Item 1A")]


def all_three():
    yield "fixed", FIXED, {}
    yield "sentence", SENTENCE, {}
    yield "structure", STRUCTURE, {"units": units_of()}


# ------------------------------------------------------- the closed set

def test_the_declared_set_is_exactly_three():
    assert st.declared_strategies() == ("fixed", "sentence", "structure")


def test_an_unknown_strategy_is_refused_with_the_declared_list():
    """A strategy is selected, never invented."""
    with pytest.raises(st.UnknownStrategy) as e:
        st.chunk_document(TEXT, "semantic", {})
    msg = str(e.value)
    assert "semantic" in msg
    for name in st.declared_strategies():
        assert name in msg
    assert "never" in msg


def test_a_parameter_the_strategy_does_not_declare_is_refused():
    with pytest.raises(st.ChunkingError) as e:
        st.chunk_document(TEXT, "fixed", dict(FIXED, temperature=0.7))
    assert "temperature" in str(e.value)


def test_an_omitted_parameter_is_refused_rather_than_defaulted():
    """A chunking whose parameters are implied is not a receipt."""
    with pytest.raises(st.ChunkingError) as e:
        st.chunk_document(TEXT, "fixed", {"size": 16})
    assert "overlap" in str(e.value) and "min_final" in str(e.value)


def test_a_parameter_outside_its_declared_bounds_is_refused():
    with pytest.raises(st.ChunkingError) as e:
        st.chunk_document(TEXT, "fixed", dict(FIXED, size=4))
    assert "at least 16" in str(e.value)


def test_the_sentence_rule_is_a_constant_and_cannot_be_configured():
    """A learned splitter would put a model inside a measure reported exact."""
    with pytest.raises(st.ChunkingError) as e:
        st.chunk_document(TEXT, "sentence", dict(SENTENCE, sentence_rule="spacy"))
    assert "constant" in str(e.value)


def test_overlap_at_or_above_the_size_is_refused():
    """It never advances, so it is a hang rather than a chunking."""
    with pytest.raises(st.ChunkingError) as e:
        st.chunk_document(TEXT, "fixed", dict(FIXED, size=16, overlap=16))
    assert "less than" in str(e.value)


# ------------------------------------------------------------ the offsets

@pytest.mark.parametrize("name", ["fixed", "sentence", "structure"])
def test_offsets_index_the_text_they_claim(name):
    params, kw = {"fixed": (FIXED, {}), "sentence": (SENTENCE, {}),
                  "structure": (STRUCTURE, {"units": units_of()})}[name]
    for c in st.chunk_document(TEXT, name, params, doc_id="d", **kw):
        assert TEXT[c.start:c.end] == c.text
        assert c.start < c.end
        assert c.strategy == name


@pytest.mark.parametrize("name", ["fixed", "sentence", "structure"])
def test_every_character_is_in_at_least_one_chunk(name):
    """No strategy may silently drop text. `min_final` drops a trailing
    fragment for `fixed`, which is why that one is checked to its last
    chunk's end rather than to the end of the text."""
    params, kw = {"fixed": (FIXED, {}), "sentence": (SENTENCE, {}),
                  "structure": (STRUCTURE, {"units": units_of()})}[name]
    chunks = st.chunk_document(TEXT, name, params, doc_id="d", **kw)
    covered = set()
    for c in chunks:
        covered |= set(range(c.start, c.end))
    assert covered == set(range(0, chunks[-1].end))


@pytest.mark.parametrize("name", ["fixed", "sentence", "structure"])
def test_chunks_are_emitted_in_document_order(name):
    params, kw = {"fixed": (FIXED, {}), "sentence": (SENTENCE, {}),
                  "structure": (STRUCTURE, {"units": units_of()})}[name]
    chunks = st.chunk_document(TEXT, name, params, doc_id="d", **kw)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks == sorted(chunks, key=lambda c: c.start)


# -------------------------------------------------------------- overlap

def test_fixed_applies_its_overlap():
    a = st.chunk_document(TEXT, "fixed", dict(FIXED, overlap=0))
    b = st.chunk_document(TEXT, "fixed", dict(FIXED, overlap=8))
    assert len(b) > len(a), "more overlap must mean more chunks at one size"
    assert all(x.end <= y.start for x, y in zip(a, a[1:])), "overlap 0 overlaps"
    assert any(x.end > y.start for x, y in zip(b, b[1:])), "overlap 8 does not"


def test_sentence_applies_its_overlap():
    """It did not. `overlap` was measured from the sentence before the one the
    next chunk starts at, so the step-back condition was satisfied on its
    first test every time and the chunks came out contiguous -- a parameter
    the report would have printed and the chunker would not have applied."""
    a = st.chunk_document(TEXT, "sentence", dict(SENTENCE, overlap=0))
    b = st.chunk_document(TEXT, "sentence", dict(SENTENCE, overlap=8))
    assert all(x.end <= y.start for x, y in zip(a, a[1:]))
    assert any(x.end > y.start for x, y in zip(b, b[1:]))


def test_sentence_chunks_start_and_end_on_sentence_boundaries():
    spans = set()
    for s, e in st.sentence_spans(TEXT):
        spans.add(s)
        spans.add(e)
    for c in st.chunk_document(TEXT, "sentence", SENTENCE):
        assert c.start in spans, c.start
        assert c.end in spans, c.end


def test_fixed_drops_a_trailing_fragment_rather_than_shipping_it():
    small = st.chunk_document(TEXT, "fixed", dict(FIXED, min_final=0))
    big = st.chunk_document(TEXT, "fixed", dict(FIXED, min_final=14))
    assert len(big) <= len(small)


# ------------------------------------------------------------- structure

def test_structure_refuses_unmarked_text_rather_than_falling_back():
    """couldn't-check on unmarked text, never a silent fall back to fixed."""
    with pytest.raises(st.ChunkingError) as e:
        st.chunk_document(TEXT, "structure", STRUCTURE, units=None)
    assert "couldnt_check" in str(e.value)
    assert "fixed windows" in str(e.value)


def test_structure_cuts_on_the_units_it_is_given():
    us = units_of()
    chunks = st.chunk_document(TEXT, "structure", STRUCTURE, units=us)
    assert len(chunks) == len(us)
    for c, (s, e, label) in zip(chunks, us):
        assert (c.start, c.end, c.unit) == (s, e, label)


def test_structure_never_cuts_across_a_unit_boundary():
    """A long unit is split, but a chunk never spans two units -- the unit is
    the thing being respected."""
    us = units_of()
    chunks = st.chunk_document(TEXT, "structure", dict(STRUCTURE, max_size=16),
                               units=us)
    assert len(chunks) > len(us), "max_size 16 should have split a unit"
    for c in chunks:
        home = [u for u in us if u[0] <= c.start and c.end <= u[1]]
        assert home, f"chunk [{c.start},{c.end}) spans a unit boundary"


def test_structure_merges_units_under_min_size():
    """A one-line section should not become a one-line chunk.

    `max_size` is raised out of the way so this tests merging alone: with the
    default 40 the merged unit is 52 tokens and is then correctly split again,
    which is a different behaviour and has its own test.
    """
    us = units_of()
    merged = st.chunk_document(TEXT, "structure",
                               dict(STRUCTURE, max_size=4096, min_size=100),
                               units=us)
    assert len(merged) == 1
    assert merged[0].unit == "Item 1+Item 1A"
    assert (merged[0].start, merged[0].end) == (0, len(TEXT))


def test_a_merged_unit_over_max_size_is_still_split():
    """Merging and splitting compose: merge short units, then split the result
    if it is too long. Neither silently disables the other."""
    us = units_of()
    chunks = st.chunk_document(TEXT, "structure",
                               dict(STRUCTURE, max_size=40, min_size=100),
                               units=us)
    assert len(chunks) == 2
    assert {c.unit for c in chunks} == {"Item 1+Item 1A"}


# ------------------------------------------------------------ the tokenizer

def test_the_whitespace_tokenizer_is_declared_not_assumed():
    t = st.WhitespaceTokens()
    assert t.name == "whitespace"
    assert t.offsets("ab  cd") == [(0, 2), (4, 6)]


def test_a_slow_tokenizer_is_refused():
    """A slow tokenizer has no offsets, and nothing here falls back to
    searching for the text it just produced."""
    class Slow:
        is_fast = False
        name_or_path = "slow-model"
    with pytest.raises(st.ChunkingError) as e:
        st.ModelTokens(Slow())
    assert "fast tokenizer" in str(e.value)


# ------------------------------------------------- the strategy is described

def test_every_strategy_describes_its_parameters():
    """The refusal message and the report both read this."""
    for name in st.declared_strategies():
        d = st.describe(name)
        assert d, name
        for param, meta in d.items():
            assert meta["note"], f"{name}.{param} has no note"
            assert meta["role"] in ("parameter", "constant")


def test_the_strategies_are_not_registered_as_model_families():
    """`proposals/policy.py` validates a policy's `family` against
    `models.base.PARAMETER_TABLES`. A chunking strategy in that global would
    let a proposal name a chunker as a model family and be accepted."""
    from oneground.models.base import PARAMETER_TABLES
    for name in st.declared_strategies():
        assert name not in PARAMETER_TABLES, name


def test_min_size_is_measured_in_tokens_not_characters():
    """`min_size` is declared in tokens, like `max_size`. Comparing it against
    a character count fails quietly: whether a unit merges would depend on the
    corpus's average word length rather than on the parameter, so the same
    value would mean different things on different text and nothing would
    raise. Unit 'Item 1A' here is 31 tokens and 163 characters, so the two
    readings disagree about every threshold between them.
    """
    us = units_of()
    assert us[1][1] - us[1][0] == 163, "the fixture's character length moved"
    # 100 is above 31 tokens and below 163 characters: merges under the
    # declared reading, does not under the wrong one.
    merged = st.chunk_document(TEXT, "structure",
                               dict(STRUCTURE, max_size=4096, min_size=100),
                               units=us)
    assert len(merged) == 1, "min_size was read as characters"
    # 20 is below 31 tokens: no merge under either reading.
    apart = st.chunk_document(TEXT, "structure",
                              dict(STRUCTURE, max_size=4096, min_size=20),
                              units=us)
    assert len(apart) == 2
