"""Offsets for chunks that were cut somewhere else.

**This is the fallback, never the normal path.** Every strategy in
`strategies.py` emits `start` and `end` as it cuts, because those positions
are what the strategy computed in order to cut at all. This module exists only
for a user who brings chunks produced by their own tool, where the positions
were computed and thrown away.

It matters on this corpus more than it looks. Filings repeat themselves so
heavily that `sec-filings-10k` publishes a pre-chunking duplicate baseline of
56.28% of documents at Jaccard 0.50, and a chunk's text can occur many times
in one document. A naive `text.find(chunk)` would return the first occurrence,
which is the wrong one for every chunk after the first repeat, and it would be
wrong *silently* -- the offsets would look fine and every positional measure
downstream would be quietly computed against the wrong span.

So the search is **ordered and monotonic**: chunks are located in emission
order and the *n*th is found at or after where the (*n*−1)th ended. That is
the only assumption a chunker's output supports, and it is stated rather than
assumed.

**A chunk that is not a verbatim substring is `couldnt_check`, with the
reason, and is never repaired.** A tool that collapses whitespace or
normalises quotes has produced text that is not in the document, so there is
no true span to find; fuzzy matching would invent one, and every positional
measure computed from it would be a number with no referent. Two measures
depend on position -- self-retrieval by containment and span survival -- and
those two report couldn't-check for that chunk. The measures that do not need
position (length distribution, near-duplicate rate, unresolved-reference rate)
are unaffected and still reported.
"""

from dataclasses import dataclass
from typing import List

from .strategies import Chunk, ChunkingError

#: The two measures that cannot be computed for a chunk whose position in the
#: document is unknown. Named here so the report can say exactly what was lost
#: rather than degrading the whole result.
POSITIONAL_MEASURES = ("self_retrieval", "span_survival")

NOT_VERBATIM = (
    "not a verbatim substring of the document at or after the previous "
    "chunk's end; the tool that produced it altered the text (collapsed "
    "whitespace, normalised quotes, or similar), so there is no true span to "
    "locate. Repairing this by fuzzy matching would invent a position and "
    "every positional measure computed from it would be a number with no "
    "referent."
)

OUT_OF_ORDER = (
    "found only before the previous chunk's end, so the chunks were not "
    "supplied in emission order; the monotonic cursor is the only assumption "
    "a chunker's output supports and it does not hold here."
)


@dataclass(frozen=True)
class Derivation:
    """What the ordered search could and could not establish."""

    chunks: List[Chunk]
    unlocated: List[dict]

    @property
    def located(self):
        return len(self.chunks)

    @property
    def examined(self):
        return len(self.chunks) + len(self.unlocated)

    def summary(self):
        return {
            "offsets_origin": "derived",
            "examined": self.examined,
            "located": self.located,
            "couldnt_check": len(self.unlocated),
            "couldnt_check_rate": (len(self.unlocated) / self.examined
                                   if self.examined else 0.0),
            "measures_affected": list(POSITIONAL_MEASURES),
            "reasons": sorted({u["reason_code"] for u in self.unlocated}),
        }


def derive_offsets(text, chunk_texts, doc_id="doc", strategy="external"):
    """Locate externally-produced chunks in `text`, in order.

    Returns a `Derivation`. Chunks that could be located carry exact offsets
    and `offsets_origin="derived"`; chunks that could not are listed in
    `unlocated` with a reason, and are couldn't-check on
    `POSITIONAL_MEASURES`.

    The cursor only moves forward. A chunk found nowhere at or after the
    cursor is not searched for earlier in the document: that would silently
    reorder the user's chunks, and a chunker's output is ordered.
    """
    if not isinstance(text, str):
        raise ChunkingError("derive_offsets needs the document text")
    chunks, unlocated, cursor = [], [], 0
    for i, ct in enumerate(chunk_texts):
        if not ct:
            unlocated.append(dict(index=i, reason_code="empty",
                                  reason="the chunk is empty", preview=""))
            continue
        at = text.find(ct, cursor)
        if at == -1:
            earlier = text.find(ct)
            code, why = (("out_of_order", OUT_OF_ORDER) if earlier != -1
                         else ("not_verbatim", NOT_VERBATIM))
            unlocated.append(dict(index=i, reason_code=code, reason=why,
                                  preview=ct[:60]))
            continue
        chunks.append(Chunk(doc_id=doc_id, index=i, start=at, end=at + len(ct),
                            text=ct, strategy=strategy,
                            offsets_origin="derived"))
        cursor = at + len(ct)
    return Derivation(chunks=chunks, unlocated=unlocated)
