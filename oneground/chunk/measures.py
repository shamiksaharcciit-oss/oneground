"""Path A — the structural measures (task 031).

Five measures of the cut itself. Ground truth is by construction: no labels,
no model, and four of the five are exact. The fifth is a heuristic and says so
in its own name, in its output and in the report, and never carries a verdict
alone.

`docs/CHUNKING.md` §4 is the specification for this module.

  span_survival           exact, needs offsets
  boundary_alignment      exact where structure exists, else couldnt_check
  near_duplicate_rate     exact, no offsets needed, read against the corpus's
                          own PRE-CHUNKING baseline
  length_distribution     exact, no offsets needed
  unresolved_references   HEURISTIC, no offsets needed, labelled everywhere

The near-duplicate rate is the one most easily misread, so it is not reported
as a bare number. A chunking's duplicate rate on a corpus that duplicates
heavily is mostly the corpus, and `sec-filings-10k` publishes exactly the
baseline needed to tell the two apart. Reporting the chunking's rate without
it would attribute the corpus's boilerplate to the strategy.
"""

import re
from collections import Counter

from ..measures import duplicates as dup

COULDNT_CHECK = "couldnt_check"


# ------------------------------------------------------------ span survival

def _by_doc(chunks):
    out = {}
    for c in chunks:
        out.setdefault(c.doc_id, []).append(c)
    return out


def span_survival(chunks, spans):
    """Did the cut fall inside a unit?

    `spans` maps doc_id -> [(start, end, kind)] -- the document's own units:
    sentences, list items, heading-scoped paragraphs. A span SURVIVES if some
    chunk OF THAT DOCUMENT contains it entirely; it is SPLIT if every chunk
    that touches it cuts through it.

    **Scoped per document, and that is not a detail.** Offsets are character
    positions into one document, so pooling every document's spans into one
    list and asking whether any chunk contains them compares a chunk of
    filing A against a span of filing B. It does not raise -- integers
    compare fine -- it just inflates the result. That is exactly what the
    first run of this measure did, across 1,000 filings, and it took a
    number that looked wrong to find it.

    Reported per unit kind, because a chunking that never splits a sentence
    and routinely splits a table row is a different thing from one that does
    the reverse, and one number would hide it.

    Exact, and needs offsets: this is one of the two measures that a chunk of
    unknown position cannot contribute to.
    """
    if isinstance(spans, (list, tuple)):
        raise TypeError(
            "span_survival takes spans as {doc_id: [(start, end, kind)]}. A "
            "flat list has no document to belong to, and comparing offsets "
            "across documents silently inflates survival.")
    per_doc = _by_doc(chunks)
    by_kind = {}
    for doc_id, doc_spans in spans.items():
        mine = per_doc.get(doc_id, [])
        for (s, e, kind) in doc_spans:
            rec = by_kind.setdefault(kind, {"total": 0, "survived": 0,
                                            "split": 0})
            rec["total"] += 1
            if any(c.contains(s, e) for c in mine):
                rec["survived"] += 1
            else:
                rec["split"] += 1
    for rec in by_kind.values():
        rec["survival_rate"] = (rec["survived"] / rec["total"]
                                if rec["total"] else 0.0)
    total = sum(r["total"] for r in by_kind.values())
    survived = sum(r["survived"] for r in by_kind.values())
    return {
        "exact": True,
        "needs_offsets": True,
        "by_kind": dict(sorted(by_kind.items())),
        "total": total,
        "survived": survived,
        "survival_rate": survived / total if total else 0.0,
    }


# ------------------------------------------------------- boundary alignment

def boundary_alignment(chunks, units):
    """Do chunk boundaries fall on the document's own boundaries?

    Measured where structure exists and **couldnt_check on plain text**, as
    the position paper requires -- not zero, not silently skipped. A chunker
    that scores 0 on unmarked text would read as badly aligned when in truth
    nothing was measured.
    """
    if not units:
        return {
            "exact": False,
            "outcome": COULDNT_CHECK,
            "reason": "the document declares no structural units, so there "
                      "are no boundaries to align to. This is couldnt_check, "
                      "not an alignment of zero: nothing was measured.",
            "needs_offsets": True,
        }
    if isinstance(units, (list, tuple)):
        raise TypeError(
            "boundary_alignment takes units as {doc_id: [(start, end, kind)]}. "
            "Pooling every document's edges into one set of integers lets a "
            "chunk of filing A align with an edge of filing B.")
    per_doc = _by_doc(chunks)
    starts = aligned = edge_count = 0
    ceiling_units = 0
    for doc_id, doc_units in units.items():
        edges = set()
        for (s, e, _kind) in doc_units:
            edges.add(s)
            edges.add(e)
        edge_count += len(edges)
        ceiling_units += len(doc_units)
        for c in per_doc.get(doc_id, []):
            starts += 1
            if c.start in edges:
                aligned += 1
    return {
        "exact": True,
        "needs_offsets": True,
        "outcome": "measured",
        "chunk_starts": starts,
        "aligned_starts": aligned,
        "alignment_rate": aligned / starts if starts else 0.0,
        "unit_edges": edge_count,
        # A chunking cannot align more starts than it has units to align to:
        # a unit longer than max_size is split, and only the first of its
        # pieces can begin on the unit's edge. Published beside the rate
        # because 0.11 against a ceiling of 0.12 and 0.11 against a ceiling
        # of 1.00 are different results.
        "alignment_ceiling": (ceiling_units / starts) if starts else 0.0,
    }


# ------------------------------------------------------- near-duplicate rate

def near_duplicate_rate(chunks, threshold=0.80, seed=20260919, baseline=None):
    """Duplicate rate over the CHUNKS, reported against the corpus's baseline.

    The measure itself is the one `oneground.measures.duplicates` computes for
    a corpus, applied to chunk texts. What matters is that it is never
    reported alone: `baseline` is the corpus's own pre-chunking rate at the
    same threshold, which `sec-filings-10k` publishes, and the difference is
    what a strategy is answerable for.

    Without a baseline the rate is still reported, and is labelled as not
    attributable -- a chunking's duplicate rate on a corpus that duplicates
    heavily is mostly the corpus.
    """
    texts = [c.text for c in chunks]
    res = dup.near_duplicate_rate(texts, seed=seed, thresholds=(threshold,))
    row = res["by_threshold"][f"{threshold:.2f}"]
    out = {
        "exact": row["kind"] == "exact",
        "needs_offsets": False,
        "threshold": threshold,
        "rate": row["rate"],
        "chunks": len(texts),
        "pairs": row["pairs"],
        "kind": row["kind"],
        "lsh_recall": row["lsh_recall"],
    }
    if baseline is None:
        out["baseline"] = None
        out["attributable"] = False
        out["note"] = (
            "no pre-chunking baseline was supplied, so this rate is NOT "
            "attributable to the chunking. On a corpus that repeats itself, "
            "most of a chunk-level duplicate rate is the corpus.")
    else:
        out["baseline"] = baseline
        out["excess_over_baseline"] = round(row["rate"] - baseline, 6)
        out["attributable"] = True
        out["note"] = (
            f"the corpus's own pre-chunking rate at this threshold is "
            f"{baseline:.4f}; the chunking is answerable for the difference, "
            f"not for the total.")
    return out


# ----------------------------------------------------- length distribution

def length_distribution(chunks, tokenizer=None, floor=None, cap=None):
    """p5 / p50 / p95, the orphan count under `floor`, the count at `cap`.

    Lengths are in tokens of the declared tokenizer, because that is what a
    `size` parameter is in. The floor and the cap are the caller's: they are
    what rules out the over-fragmentation that self-retrieval rewards, so they
    are stated rather than defaulted.
    """
    import numpy as np
    if tokenizer is None:
        from .strategies import WhitespaceTokens
        tokenizer = WhitespaceTokens()
    lens = np.array([len(tokenizer.offsets(c.text)) for c in chunks]) \
        if chunks else np.zeros(0, dtype=int)

    def q(p):
        return int(np.percentile(lens, p)) if lens.size else 0

    out = {
        "exact": True,
        "needs_offsets": False,
        "tokenizer": getattr(tokenizer, "name", "unknown"),
        "chunks": int(lens.size),
        "p5": q(5), "p50": q(50), "p95": q(95),
        "min": int(lens.min()) if lens.size else 0,
        "max": int(lens.max()) if lens.size else 0,
        "mean": round(float(lens.mean()), 2) if lens.size else 0.0,
    }
    out["floor"] = floor
    out["orphans"] = int((lens < floor).sum()) if (floor and lens.size) else 0
    out["orphan_rate"] = (out["orphans"] / lens.size) if lens.size else 0.0
    out["cap"] = cap
    out["at_cap"] = int((lens >= cap).sum()) if (cap and lens.size) else 0
    out["at_cap_rate"] = (out["at_cap"] / lens.size) if lens.size else 0.0
    return out


# --------------------------------------------------- unresolved references

#: Chunk-initial anaphora. Published, because a heuristic whose rule is not
#: published is not a measurement anyone can argue with.
UNRESOLVED_RULE = r"^\W*(this|that|these|those|it|its|they|them|their|such|the\s+above|the\s+foregoing|the\s+former|the\s+latter|he|she|his|her)\b"

_UNRESOLVED = re.compile(UNRESOLVED_RULE, re.I)

UNRESOLVED_CAVEAT = (
    "HEURISTIC. This is a rule-based detector of chunk-initial anaphora with "
    "a false-positive rate it does not know: 'This Annual Report' opens a "
    "perfectly self-contained chunk and is counted, and a reference carried "
    "by a bare noun phrase ('the Facility') is missed. It is reported "
    "labelled, with its rule published, and it never carries a verdict alone."
)


def unresolved_references(chunks):
    """Rule-based, labelled heuristic, never a verdict on its own."""
    hits = [c for c in chunks if _UNRESOLVED.match(c.text or "")]
    n = len(chunks)
    return {
        "exact": False,
        "heuristic": True,
        "needs_offsets": False,
        "rule": UNRESOLVED_RULE,
        "caveat": UNRESOLVED_CAVEAT,
        "chunks": n,
        "unresolved": len(hits),
        "rate": len(hits) / n if n else 0.0,
        "opening_words": dict(Counter(
            (c.text.split() or [""])[0].lower().strip(".,;:") for c in hits
        ).most_common(8)),
    }


# ------------------------------------------------------------- all together

def path_a(chunks, spans=None, units=None, tokenizer=None, floor=None,
           cap=None, duplicate_threshold=0.80, duplicate_seed=20260919,
           duplicate_baseline=None):
    """The five measures, each carrying whether it is exact and what it needs.

    `spans` and `units` are {doc_id: [(start, end, kind)]}, not flat lists.
    See `span_survival` for why that distinction is load-bearing.
    """
    return {
        "span_survival": (span_survival(chunks, spans) if spans else {
            "exact": False, "outcome": COULDNT_CHECK, "needs_offsets": True,
            "reason": "no structural units were supplied, so there is nothing "
                      "a cut could have fallen inside."}),
        "boundary_alignment": boundary_alignment(chunks, units),
        "near_duplicate_rate": near_duplicate_rate(
            chunks, threshold=duplicate_threshold, seed=duplicate_seed,
            baseline=duplicate_baseline),
        "length_distribution": length_distribution(
            chunks, tokenizer=tokenizer, floor=floor, cap=cap),
        "unresolved_references": unresolved_references(chunks),
    }
