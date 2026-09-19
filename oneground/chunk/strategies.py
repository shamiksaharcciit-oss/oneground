"""The chunking strategies: a declared, closed set.

Three of them, each with its parameters in the task 026 parameter-table form.
A strategy is **selected, never invented**: an unknown name is refused with
the declared list, the same way a configuration naming a key its family does
not accept is refused.

The parameter tables live in their own registry rather than in
`models.base.PARAMETER_TABLES`. That is not tidiness. `proposals/policy.py`
validates a policy's `family` against that global, so registering `fixed`
there would let a proposal name a chunking strategy as a model family and be
accepted. Same `Param` dataclass, same `check_value`, separate namespace.

**Every strategy emits offsets as it cuts.** `Chunk.start` and `Chunk.end`
are character offsets into the document text the strategy was handed, and
they are what the strategy computed in order to cut. No strategy searches for
its own output.
"""

import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Sequence, Tuple

from ..models.base import CONSTANT, PARAMETER, Param, check_value


class ChunkingError(ValueError):
    """The chunking stage refuses to proceed, with what was named."""


class UnknownStrategy(ChunkingError):
    """A strategy outside the declared set."""


@dataclass(frozen=True)
class Chunk:
    """One chunk, with the offsets the strategy emitted as it cut.

    `start` and `end` are character offsets into the document text, half-open
    (`text[start:end]` is the chunk). They are exact by construction and are
    never derived by searching for `text` -- see `oneground.chunk`.
    """

    doc_id: str
    index: int
    start: int
    end: int
    text: str
    strategy: str
    unit: Optional[str] = None          # the structural unit it came from, if any

    def as_record(self):
        return asdict(self)

    def contains(self, start, end):
        """Does this chunk wholly contain the span [start, end)?"""
        return self.start <= start and end <= self.end


# --------------------------------------------------------------- the tables

STRATEGY_TABLES = {}


def _declare(name, params):
    table = {}
    for p in params:
        if p.name in table:
            raise ValueError(f"{name}.{p.name} declared twice")
        table[p.name] = p
    STRATEGY_TABLES[name] = table
    return table


_declare("fixed", [
    Param("size", int, PARAMETER, minimum=16, maximum=8192, swept=True,
          note="chunk length in tokens of the declared tokenizer"),
    Param("overlap", int, PARAMETER, minimum=0, maximum=4096, swept=True,
          note="tokens of the previous chunk repeated at the start of the next"),
    Param("min_final", int, PARAMETER, minimum=0, maximum=4096,
          note="a trailing window shorter than this is dropped, not shipped "
               "as a fragment"),
])

_declare("sentence", [
    Param("max_size", int, PARAMETER, minimum=16, maximum=8192, swept=True,
          note="a chunk is filled with whole sentences up to this many tokens"),
    Param("overlap", int, PARAMETER, minimum=0, maximum=4096, swept=True,
          note="whole sentences, not tokens: the last sentences of a chunk "
               "are repeated at the start of the next until the overlap "
               "budget in tokens is met"),
    Param("min_final", int, PARAMETER, minimum=0, maximum=4096,
          note="a trailing chunk shorter than this is merged into the previous"),
    Param("sentence_rule", str, CONSTANT, fixed="declared_regex_v1",
          note="the sentence rule is fixed and published, not configurable; "
               "see SENTENCE_RULE"),
])

_declare("structure", [
    Param("max_size", int, PARAMETER, minimum=16, maximum=16384, swept=True,
          note="a structural unit longer than this is split, on sentence "
               "boundaries, rather than shipped whole"),
    Param("overlap", int, PARAMETER, minimum=0, maximum=4096, swept=True,
          note="tokens repeated when a long unit has to be split; units are "
               "never overlapped with each other"),
    Param("min_size", int, PARAMETER, minimum=0, maximum=4096,
          note="consecutive units shorter than this are merged, so a one-line "
               "section does not become a one-line chunk"),
])

STRATEGIES = tuple(sorted(STRATEGY_TABLES))


def declared_strategies():
    return STRATEGIES


def strategy_table(name):
    try:
        return STRATEGY_TABLES[name]
    except KeyError:
        raise UnknownStrategy(
            f"no chunking strategy named {name!r}; oneground declares: "
            f"{', '.join(STRATEGIES)}. A strategy is selected, never "
            f"invented -- a new one is a change to oneground, not to a "
            f"requirements file.") from None


def describe(name):
    """The strategy's declared parameters, for the report and the refusals."""
    table = strategy_table(name)
    return {n: {"type": p.type.__name__, "role": p.role,
                "minimum": p.minimum, "maximum": p.maximum, "note": p.note}
            for n, p in sorted(table.items())}


def check_params(name, params):
    """Validate a parameter set against the strategy's table. Raises."""
    table = strategy_table(name)
    unknown = sorted(set(params) - set(table))
    if unknown:
        raise ChunkingError(
            f"chunking strategy {name!r} does not accept {unknown}; it "
            f"declares: {', '.join(sorted(table))}")
    problems = [check_value(name, table[k], v) for k, v in params.items()]
    problems = [p for p in problems if p]
    if problems:
        raise ChunkingError("; ".join(problems))
    missing = sorted(n for n, p in table.items()
                     if p.role == PARAMETER and n not in params)
    if missing:
        raise ChunkingError(
            f"chunking strategy {name!r} needs {missing}; a chunking whose "
            f"parameters are implied rather than stated is not a receipt")
    return {n: params[n] for n in sorted(params)}


# ------------------------------------------------------------ the tokenizer

class WhitespaceTokens:
    """The fallback tokenizer: offsets of whitespace-delimited runs.

    Declared rather than assumed. Token counts under this rule are not the
    embedding model's token counts, and a report that used it says so, because
    a `size: 512` measured in whitespace tokens is a different chunking from
    `size: 512` measured in WordPiece. It exists so the stage runs, and is
    tested against, without pulling a model in.
    """

    name = "whitespace"

    def offsets(self, text):
        return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


class ModelTokens:
    """The embedding model's own tokenizer, which is what a size means.

    Wraps a HuggingFace fast tokenizer's offset mapping. The fast tokenizer is
    required, not preferred: a slow one has no offsets, and a chunker that
    cannot say where it cut is not one this stage will use.
    """

    def __init__(self, tokenizer, name=None):
        self._tok = tokenizer
        self.name = name or getattr(tokenizer, "name_or_path", "model")
        if not getattr(tokenizer, "is_fast", False):
            raise ChunkingError(
                "the chunking stage needs a fast tokenizer: offsets are "
                "emitted as the strategy cuts, and a slow tokenizer cannot "
                "report them. Nothing here falls back to searching for the "
                "text it just produced.")

    def offsets(self, text):
        enc = self._tok(text, add_special_tokens=False,
                        return_offsets_mapping=True, truncation=False)
        return [tuple(o) for o in enc["offset_mapping"]]


# --------------------------------------------------------- the sentence rule

SENTENCE_RULE = r"""Declared, published, and fixed (`sentence_rule:
declared_regex_v1`).

A sentence ends at `.`, `!` or `?`, optionally followed by a closing quote or
bracket, when the next non-space character is an opening quote, bracket or an
upper-case letter -- or at a blank line, which ends a sentence whatever
punctuation precedes it.

Its limits, stated rather than discovered: it splits after an abbreviation
followed by a capitalised word ("Inc. The company"), and it does not split
where a filer omits the space after a full stop. It is a rule, not a model,
and no model may be substituted for it -- a learned sentence splitter would
put a model inside a measurement this stage reports as exact.
"""

_SENT_END = re.compile(r'(?<=[.!?])["\')\]]?\s+(?=["\'(\[A-Z])|\n[ \t]*\n')


def sentence_spans(text):
    """(start, end) of each sentence. Contiguous and covering: every
    character of `text` belongs to exactly one sentence, so a chunk built from
    whole sentences has offsets that are exact against the original."""
    spans, prev = [], 0
    for m in _SENT_END.finditer(text):
        end = m.end()
        if end > prev:
            spans.append((prev, end))
            prev = end
    if prev < len(text):
        spans.append((prev, len(text)))
    return spans


# ------------------------------------------------------------- the strategies

def _windows(n, size, stride, min_final):
    """Token index windows [lo, hi) over n tokens."""
    out = []
    for lo in range(0, max(n, 1), stride):
        hi = min(lo + size, n)
        if hi - lo < min_final and out:
            break
        out.append((lo, hi))
        if hi >= n:
            break
    return out


def _fixed(text, offs, params, doc_id):
    size, overlap = params["size"], params["overlap"]
    if overlap >= size:
        raise ChunkingError(
            f"fixed: overlap {overlap} must be less than size {size}; an "
            f"overlap at or above the size never advances")
    stride = size - overlap
    out = []
    for i, (lo, hi) in enumerate(_windows(len(offs), size, stride,
                                          params["min_final"])):
        if hi <= lo:
            continue
        start, end = offs[lo][0], offs[hi - 1][1]
        out.append(Chunk(doc_id, i, start, end, text[start:end], "fixed"))
    return out


def _token_index(offs, char_pos):
    """The first token starting at or after `char_pos`."""
    lo, hi = 0, len(offs)
    while lo < hi:
        mid = (lo + hi) // 2
        if offs[mid][0] < char_pos:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _sentence(text, offs, params, doc_id):
    max_size, overlap = params["max_size"], params["overlap"]
    if overlap >= max_size:
        raise ChunkingError(
            f"sentence: overlap {overlap} must be less than max_size "
            f"{max_size}")
    sents = sentence_spans(text)
    if not sents:
        return []
    # token count per sentence, from the offsets already computed
    bounds = [(_token_index(offs, s), _token_index(offs, e)) for s, e in sents]
    out, i, idx = [], 0, 0
    while i < len(sents):
        tok_lo = bounds[i][0]
        j, tok_hi = i, bounds[i][1]
        while j + 1 < len(sents) and bounds[j + 1][1] - tok_lo <= max_size:
            j += 1
            tok_hi = bounds[j][1]
        start, end = sents[i][0], sents[j][1]
        out.append(Chunk(doc_id, idx, start, end, text[start:end], "sentence"))
        idx += 1
        if j + 1 >= len(sents):
            break
        # Step back over whole sentences until the overlap budget is met.
        #
        # The overlap the NEXT chunk gets is the tokens from sentence k
        # through sentence j, so it is measured from `bounds[k][0]`, not from
        # `bounds[k - 1][0]`. Measuring it one sentence early made the
        # condition true on the first test every time and produced contiguous
        # chunks with `overlap` silently ignored -- a parameter the report
        # would have printed and the chunker would not have applied.
        k = j + 1
        while k > i + 1 and (bounds[j][1] - bounds[k][0] if k <= j else 0) < overlap:
            k -= 1
        i = k
    if len(out) > 1 and out[-1].end - out[-1].start < params["min_final"]:
        last = out.pop()
        prev = out[-1]
        out[-1] = Chunk(prev.doc_id, prev.index, prev.start, last.end,
                        text[prev.start:last.end], "sentence")
    return out


def _structure(text, offs, params, doc_id, units):
    """Cuts on the document's own markup. couldn't-check without it."""
    if not units:
        raise ChunkingError(
            "structure: this document has no declared structural units, so "
            "there is no markup to cut on. On unmarked text this strategy is "
            "couldnt_check, not a silent fall back to fixed windows.")
    max_size, min_size = params["max_size"], params["min_size"]

    def tokens_in(s, e):
        return _token_index(offs, e) - _token_index(offs, s)

    # `min_size` is declared in TOKENS, like `max_size`. Comparing it against
    # `e - s` -- characters -- is how this first went wrong, and it fails
    # quietly: whether a unit merges then depends on the corpus's average word
    # length rather than on the parameter, so the same `min_size` means
    # different things on different text and nothing raises.
    merged = []
    for (s, e, label) in units:
        if merged and tokens_in(s, e) < min_size and merged[-1][1] == s:
            ps, pe, plabel = merged[-1]
            merged[-1] = (ps, e, f"{plabel}+{label}")
        else:
            merged.append((s, e, label))
    out, idx = [], 0
    for (s, e, label) in merged:
        lo, hi = _token_index(offs, s), _token_index(offs, e)
        if hi - lo <= max_size:
            out.append(Chunk(doc_id, idx, s, e, text[s:e], "structure", label))
            idx += 1
            continue
        # too long for one chunk: split it on sentence boundaries, never
        # across unit boundaries -- the unit is the thing being respected.
        sub = _sentence(text[s:e], [(a - s, b - s) for a, b in offs[lo:hi]],
                        {"max_size": max_size, "overlap": params["overlap"],
                         "min_final": 0}, doc_id)
        for c in sub:
            out.append(Chunk(doc_id, idx, s + c.start, s + c.end,
                             text[s + c.start:s + c.end], "structure", label))
            idx += 1
    return out


_DISPATCH = {"fixed": _fixed, "sentence": _sentence}


def chunk_document(text, strategy, params, doc_id="doc", tokenizer=None,
                   units=None):
    """Cut one document. Returns a list of `Chunk`, offsets emitted as cut.

    `units` is the document's own structural markup as (start, end, label)
    spans -- required by `structure`, ignored by the others. Nothing here
    infers structure from plain text: that would be an extractor, and this
    stage does not run extractors.
    """
    params = check_params(strategy, params)
    tok = tokenizer or WhitespaceTokens()
    offs = tok.offsets(text)
    if strategy == "structure":
        chunks = _structure(text, offs, params, doc_id, units)
    else:
        chunks = _DISPATCH[strategy](text, offs, params, doc_id)
    for c in chunks:
        # The offsets are the contract. If a strategy ever emits one that does
        # not index its own text, that is a defect here and not the caller's
        # problem to discover three measures downstream.
        assert text[c.start:c.end] == c.text, (
            f"{strategy}: chunk {c.index} offsets do not index its text")
    return chunks
