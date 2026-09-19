"""The fallback for chunks cut elsewhere (task 031).

The repetition case is the one that matters. A naive `text.find(chunk)` is
right on text that does not repeat and silently wrong on text that does, and
this corpus repeats: sec-filings-10k publishes 56.28% of documents having a
near-duplicate at Jaccard 0.50. So the first test here is the one where a
chunk's text occurs three times.
"""

import pytest

from oneground.chunk import external as ex
from oneground.chunk.strategies import ChunkingError

REPEATED = ("The Company is subject to risks. "
            "Alpha section follows here. "
            "The Company is subject to risks. "
            "Beta section follows here. "
            "The Company is subject to risks. "
            "Gamma section follows here.")


def test_a_repeated_chunk_is_located_at_its_own_occurrence():
    """The whole reason the cursor is monotonic. Under `text.find` every one
    of these three chunks would be located at the FIRST occurrence, and every
    positional measure after that would be computed against the wrong span
    without anything raising."""
    piece = "The Company is subject to risks. "
    d = ex.derive_offsets(REPEATED, [piece, piece, piece], doc_id="d")
    assert d.located == 3 and not d.unlocated
    starts = [c.start for c in d.chunks]
    assert starts == sorted(starts) and len(set(starts)) == 3, starts
    for c in d.chunks:
        assert REPEATED[c.start:c.end] == c.text


def test_located_chunks_say_their_offsets_were_derived():
    """A reader must be able to tell a derived offset from an emitted one."""
    d = ex.derive_offsets(REPEATED, ["The Company is subject to risks. "])
    assert d.chunks[0].offsets_origin == "derived"


def test_a_non_verbatim_chunk_is_couldnt_check_and_is_not_repaired():
    """A tool that collapsed whitespace produced text that is not in the
    document. There is no true span, so fuzzy matching would invent one."""
    d = ex.derive_offsets(REPEATED, ["The Company is subject to risks."
                                     .replace(" ", "  ")])
    assert d.located == 0
    (u,) = d.unlocated
    assert u["reason_code"] == "not_verbatim"
    assert "fuzzy" in u["reason"]
    assert d.summary()["measures_affected"] == list(ex.POSITIONAL_MEASURES)


def test_only_the_two_positional_measures_are_affected():
    """Length, near-duplicate rate and unresolved references need no offsets
    and are not degraded by a chunk that could not be located."""
    assert set(ex.POSITIONAL_MEASURES) == {"self_retrieval", "span_survival"}


def test_chunks_out_of_order_are_reported_as_such_not_as_missing():
    """Found, but only before the cursor: the supplied order is wrong, which
    is a different fault from text that was altered, and says so."""
    a = "Alpha section follows here. "
    b = "Beta section follows here. "
    d = ex.derive_offsets(REPEATED, [b, a])
    assert d.located == 1 and len(d.unlocated) == 1
    assert d.unlocated[0]["reason_code"] == "out_of_order"
    assert "emission order" in d.unlocated[0]["reason"]


def test_the_cursor_never_searches_backwards():
    """Searching earlier would silently reorder the user's chunks."""
    piece = "The Company is subject to risks. "
    d = ex.derive_offsets(REPEATED, [piece, piece, piece, piece])
    assert d.located == 3
    assert d.unlocated[0]["index"] == 3
    assert d.unlocated[0]["reason_code"] == "out_of_order"


def test_one_unlocated_chunk_does_not_cost_the_others():
    piece = "The Company is subject to risks. "
    d = ex.derive_offsets(REPEATED, ["not in the document at all", piece])
    assert d.located == 1
    assert d.unlocated[0]["reason_code"] == "not_verbatim"
    assert d.examined == 2


def test_an_empty_chunk_is_reported_rather_than_matched_everywhere():
    """`"".find` succeeds at the cursor, which would give a zero-width span
    that contains nothing and is contained by everything."""
    d = ex.derive_offsets(REPEATED, [""])
    assert d.located == 0
    assert d.unlocated[0]["reason_code"] == "empty"


def test_the_summary_reports_the_rate_and_the_reasons():
    piece = "The Company is subject to risks. "
    d = ex.derive_offsets(REPEATED, [piece, "altered  text", piece])
    s = d.summary()
    assert s["examined"] == 3 and s["located"] == 2 and s["couldnt_check"] == 1
    assert s["couldnt_check_rate"] == pytest.approx(1 / 3)
    assert s["offsets_origin"] == "derived"
    assert s["reasons"] == ["not_verbatim"]


def test_text_is_required():
    with pytest.raises(ChunkingError):
        ex.derive_offsets(None, ["x"])
