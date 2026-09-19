"""Path B — self-retrieval by containment (task 031).

Exact, label-free, and about retrieval rather than structure. Anchor spans are
drawn from the raw text by a seeded rule; each span's containment in a chunk
is ground truth by construction. Embed the span, retrieve top-k over the
strategy's chunk vectors, and ask whether the span's home chunk came back.

`docs/CHUNKING.md` §3 is the specification, and the two definitions most
likely to be got wrong are taken from it verbatim:

- **The home chunk.** Among the chunks that contain the span *entirely*, the
  one in which the span is most centred -- largest minimum distance from the
  span to either chunk boundary, **in tokens**; ties go to the earliest chunk.
- **A hit** is the home chunk appearing in the top-k. A *different* containing
  chunk in the top-k is **not** a hit for `self_recall`. It is counted
  separately as `containing_hit@k` and reported beside it, with
  `containing_count`, so the effect of overlap is visible rather than
  rewarded.

That separation is the whole reason the definition is pinned. Without it,
overlap raises the score by multiplying acceptable answers, and a strategy
could be made to look better by overlapping more while cutting no better.
Under it, overlap can only help by giving a span a better-centred home, which
is the effect a reader would want measured.

**No model appears in this path.** The embedding model turns text into
vectors, which is the measurement instrument, not a judge: nothing here asks a
model whether an answer is good, and the perturbations are published rules.
"""

import random
import re
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .strategies import WhitespaceTokens

UPPER_BOUND_CAVEAT = (
    "Anchor spans are drawn from the corpus, so they overlap the text they "
    "retrieve -- an easier query than a user's question, which is phrased "
    "differently and may need content from two chunks. Self-retrieval is "
    "therefore an UPPER BOUND on retrievability, not an estimate of answer "
    "quality. A strategy that scores badly here is bad; a strategy that "
    "scores well here has cleared a necessary condition, not a sufficient one."
)

BIAS_CAPTION = (
    "Self-retrieval rises as chunks shrink and is maximised by chunks too "
    "small to answer with; the length distribution, the orphan count, and "
    "boundary alignment in the structural columns are what rule that out. "
    "Read them together."
)


@dataclass(frozen=True)
class Anchor:
    """One sampled span of the raw document text."""

    doc_id: str
    start: int
    end: int
    text: str
    kind: str


# --------------------------------------------------------- sampling anchors

def sample_anchors(docs, n, seed, kind="sentence", min_tokens=8,
                   tokenizer=None):
    """A seeded draw of anchor spans, so the set is a receipt.

    `docs` maps doc_id -> text. Spans are whole sentences under the declared
    sentence rule (the same rule the `sentence` strategy uses, so the two
    cannot drift apart), filtered to those with at least `min_tokens` tokens:
    a three-word span retrieves nothing meaningfully and would measure the
    embedding model's behaviour on fragments.
    """
    from .strategies import sentence_spans
    tok = tokenizer or WhitespaceTokens()
    pool = []
    for doc_id in sorted(docs):
        text = docs[doc_id]
        for (s, e) in sentence_spans(text):
            if len(tok.offsets(text[s:e])) >= min_tokens:
                pool.append(Anchor(doc_id, s, e, text[s:e], kind))
    if not pool:
        return []
    rng = random.Random(seed)
    if n >= len(pool):
        return pool
    return [pool[i] for i in sorted(rng.sample(range(len(pool)), n))]


# ------------------------------------------------------------- the home chunk

def containing(chunks, anchor):
    """Every chunk that contains the anchor entirely, in document order."""
    return [c for c in chunks if c.contains(anchor.start, anchor.end)]


def home_chunk(chunks, anchor, text, tokenizer=None):
    """The chunk in which the anchor is most centred, ties to the earliest.

    Centredness is the minimum distance from the span to either chunk
    boundary, **in tokens** -- not characters. The paper says tokens, and the
    two disagree: a chunk padded with long words is closer in characters and
    no closer in tokens.

    Returns (chunk, containing_list) or (None, []) when nothing contains it,
    which is itself a result: a span no chunk contains was cut through by
    every chunk that touches it.
    """
    tok = tokenizer or WhitespaceTokens()
    holders = containing(chunks, anchor)
    if not holders:
        return None, []

    def centredness(c):
        before = len(tok.offsets(text[c.start:anchor.start]))
        after = len(tok.offsets(text[anchor.end:c.end]))
        return min(before, after)

    best, best_score = holders[0], centredness(holders[0])
    for c in holders[1:]:
        s = centredness(c)
        if s > best_score:          # strictly greater: ties go to the earliest
            best, best_score = c, s
    return best, holders


# ----------------------------------------------------------- perturbations

_FIRST_CLAUSE = re.compile(r"^[^,;:]{1,120}[,;:]\s*")

#: A published closed-class list. See `NOUN_PHRASE_CAVEAT`.
CLOSED_CLASS = frozenset("""
a an the this that these those and or but nor for yet so if then than as
because while when where which who whom whose what is are was were be been
being am do does did have has had having will would shall should may might
must can could of in on at to from by with without within into onto over
under about above below between among during before after since until not
no nor only also both either neither each every any some all such it its
they them their he she his her we us our you your i me my
""".split())

NOUN_PHRASE_CAVEAT = (
    "APPROXIMATE. The specification asks for 'noun phrases only'. True "
    "noun-phrase chunking needs a part-of-speech tagger, which is a model, "
    "and no model may appear in this path -- so this perturbation removes a "
    "PUBLISHED closed-class word list (see CLOSED_CLASS) and keeps the rest. "
    "It moves the query away from verbatim overlap, which is what the "
    "perturbation is for, but it is not noun-phrase extraction and is not "
    "reported as though it were."
)

PERTURBATIONS = {}


def _perturbation(name, caveat=None):
    def reg(f):
        PERTURBATIONS[name] = {"fn": f, "caveat": caveat, "name": name}
        return f
    return reg


@_perturbation("verbatim")
def _verbatim(text, rng):
    return text


@_perturbation("drop_first_clause")
def _drop_first_clause(text, rng):
    out = _FIRST_CLAUSE.sub("", text, count=1)
    return out if out.strip() else text


@_perturbation("function_words_removed", caveat=NOUN_PHRASE_CAVEAT)
def _function_words_removed(text, rng):
    """Removes a published list of function words and keeps what is left.

    Named for what it does. An earlier name, `content_words`, suggested it
    identifies content words, which a closed-class removal does not: what
    survives includes verbs and adverbs, and the rule has no idea which is
    which. The name claims nothing the rule cannot do.
    """
    kept = [w for w in text.split() if w.lower().strip(".,;:()\"'") not in CLOSED_CLASS]
    return " ".join(kept) if kept else text


def perturb(anchors, name, seed):
    """Apply a named, seeded perturbation. Each is its own reported column."""
    if name not in PERTURBATIONS:
        raise ValueError(
            f"no perturbation named {name!r}; declared: "
            f"{', '.join(sorted(PERTURBATIONS))}")
    fn = PERTURBATIONS[name]["fn"]
    rng = random.Random(seed)
    return [fn(a.text, rng) for a in anchors]


# ------------------------------------------------------------ the measurement

def self_retrieval(chunks, anchors, docs, chunk_vectors, query_vectors, k=5,
                   tokenizer=None):
    """`self_recall@k`, `self_rank`, `containing_hit@k`, `containing_count`.

    `chunk_vectors` are the strategy's chunk embeddings in `chunks` order;
    `query_vectors` the embedded anchors in `anchors` order. Retrieval is
    exact k-NN, the same machinery the rest of oneground uses.
    """
    from ..truth import exact_knn
    tok = tokenizer or WhitespaceTokens()
    by_doc = {}
    for i, c in enumerate(chunks):
        by_doc.setdefault(c.doc_id, []).append((i, c))

    top = exact_knn(np.ascontiguousarray(chunk_vectors, dtype=np.float32),
                    np.ascontiguousarray(query_vectors, dtype=np.float32), k)

    hits = cont_hits = 0
    ranks, counts, no_home = [], [], 0
    for qi, a in enumerate(anchors):
        pairs = by_doc.get(a.doc_id, [])
        idx_of = {id(c): i for i, c in pairs}
        home, holders = home_chunk([c for _i, c in pairs], a, docs[a.doc_id],
                                   tokenizer=tok)
        counts.append(len(holders))
        if home is None:
            no_home += 1
            ranks.append(None)
            continue
        retrieved = list(top[qi])
        hi = idx_of[id(home)]
        if hi in retrieved:
            hits += 1
            ranks.append(retrieved.index(hi) + 1)
        else:
            ranks.append(None)
        if any(idx_of[id(c)] in retrieved for c in holders):
            cont_hits += 1

    n = len(anchors)
    found = [r for r in ranks if r is not None]
    return {
        "k": k,
        "anchors": n,
        "self_recall_at_k": hits / n if n else 0.0,
        "containing_hit_at_k": cont_hits / n if n else 0.0,
        "containing_count_mean": round(float(np.mean(counts)), 3) if counts else 0.0,
        "containing_count_max": int(max(counts)) if counts else 0,
        "self_rank_p50": int(np.percentile(found, 50)) if found else None,
        "spans_with_no_containing_chunk": no_home,
        "bias_caption": BIAS_CAPTION,
        "upper_bound_caveat": UPPER_BOUND_CAVEAT,
        "hit_definition": (
            "the home chunk in the top-k. The home chunk is the containing "
            "chunk in which the span is most centred, by minimum distance to "
            "either boundary in tokens, ties to the earliest. A different "
            "containing chunk in the top-k is counted as containing_hit@k and "
            "is NOT a self_recall hit."),
    }
