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

**The floor is one rule, not three.** Task 031 shipped `fixed` silently
dropping a trailing window shorter than its floor, `sentence` merging only
the last chunk of a document into its neighbour, and `structure` merging
short *units* before chunking even began -- three unrelated mechanisms
behind two differently-named parameters, none stating that the others
meant something else by the same idea. `60` orphan chunks for `fixed`
against `~7,400` each for the other two read as a quality difference
between strategies and were not one (task 052/054). `_merge_undersized`
is now the one rule: a resulting chunk shorter than the floor is merged
into the adjacent chunk of the same document -- the previous one where
one exists, the next one only when the short chunk is a document's first
-- and every strategy calls it as the last step of building its chunks,
whatever mechanism produced them. `structure`'s pre-chunking unit merge
stays, declared as an additional, structural reason to avoid an
undersized chunk before one is even built (task 054, `structure`'s own
`min_size` note) -- not a substitute for the shared floor guarantee,
which now also runs on `structure`'s output.
"""

import re
from dataclasses import dataclass, asdict, replace
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
    offsets_origin: str = "emitted"     # "emitted" by a strategy, or "derived"

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
          note="a chunk shorter than this is merged into the adjacent chunk "
               "of the same document -- the previous one, or the next when "
               "it is the document's first. Task 054: this used to drop a "
               "short trailing window instead of merging it, silently -- "
               "the same parameter's role in `sentence` and `structure` "
               "below, now shared rather than three behaviours"),
])

_declare("sentence", [
    Param("max_size", int, PARAMETER, minimum=16, maximum=8192, swept=True,
          note="a chunk is filled with whole sentences up to this many tokens"),
    Param("overlap", int, PARAMETER, minimum=0, maximum=4096, swept=True,
          note="whole sentences, not tokens: the last sentences of a chunk "
               "are repeated at the start of the next until the overlap "
               "budget in tokens is met"),
    Param("min_final", int, PARAMETER, minimum=0, maximum=4096,
          note="a chunk shorter than this is merged into the adjacent chunk "
               "of the same document -- the previous one, or the next when "
               "it is the document's first. Task 054: this used to protect "
               "only a document's trailing chunk; every undersized chunk "
               "gets the same treatment now, the shared rule `fixed` and "
               "`structure` also use under their own name for it"),
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
          note="two things, both against the same floor: consecutive "
               "structural units shorter than this are merged before "
               "chunking, so a one-line section does not become a one-line "
               "chunk -- a declared exception to how `fixed`/`sentence` "
               "enforce the floor, kept because it respects unit "
               "boundaries a post-hoc merge cannot see; and, after "
               "chunking, any chunk this pre-merge still left short is "
               "merged into its neighbour exactly as `fixed`'s and "
               "`sentence`'s `min_final` do (task 054) -- so a unit with "
               "no adjacent short unit to merge with (a document's first, "
               "or one separated by a gap) is not left as an orphan the "
               "pre-merge alone would have missed"),
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

def _merge_label(a, b):
    """`structure`'s own join convention (`_structure`'s pre-chunking unit
    merge), reused so a chunk merged here reads the same way."""
    if a == b:
        return a
    if a and b:
        return f"{a}+{b}"
    return a or b


def _merge_undersized(chunks, min_final, text, tokens_in, mergeable=None):
    """The one floor rule every strategy ends on (task 054).

    A chunk shorter than `min_final` **tokens** -- `tokens_in(start, end)`,
    never a character count -- is merged into the adjacent chunk of the
    same document: the previous one where there is one, the next one only
    when the short chunk is the document's first (nothing precedes it). A
    document whose every chunk is short merges down to one chunk and
    stops: there is nothing left to merge into. Iterates because one merge
    can leave the result still short, which a single pass would miss.

    Measured in tokens because `min_final`/`min_size` are declared in
    tokens, like `max_size` (`_structure`'s own `min_size` comment names
    the same mistake: comparing a token floor against a character count
    means the same parameter value merges differently depending on the
    corpus's average word length, and nothing raises to say so).

    `mergeable`, when given, is one bool per chunk: `False` marks a chunk
    that neither absorbs a neighbour nor is absorbed by one. `structure`
    uses this for the pieces of a unit `max_size` forced it to split --
    merging them back together would silently undo the split the size cap
    exists to enforce, the opposite failure from the one this function
    closes. A piece marked this way is left exactly as split, however
    short, rather than merged past a limit the split was there to respect.
    """
    if min_final <= 0 or len(chunks) <= 1:
        return list(chunks)
    out = list(chunks)
    elig = list(mergeable) if mergeable is not None else [True] * len(out)
    changed = True
    while changed and len(out) > 1:
        changed = False
        for i, c in enumerate(out):
            if not elig[i] or tokens_in(c.start, c.end) >= min_final:
                continue
            if i > 0 and elig[i - 1]:
                j = i - 1
            elif i + 1 < len(out) and elig[i + 1]:
                j = i + 1
            else:
                continue
            lo, hi = min(i, j), max(i, j)
            a, b = out[lo], out[hi]
            out[lo:hi + 1] = [replace(a, end=b.end, text=text[a.start:b.end],
                                      unit=_merge_label(a.unit, b.unit))]
            elig[lo:hi + 1] = [True]
            changed = True
            break
    return [replace(c, index=k) for k, c in enumerate(out)]


def _windows(n, size, stride):
    """Token index windows [lo, hi) over n tokens.

    Every window is kept, including a short final one -- task 054.
    `_merge_undersized` is what enforces the floor now, uniformly across
    strategies, rather than this function refusing to create a window at
    all: a document's last few tokens are never simply absent from every
    chunk `oneground chunk` writes.
    """
    out = []
    for lo in range(0, max(n, 1), stride):
        hi = min(lo + size, n)
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
    for i, (lo, hi) in enumerate(_windows(len(offs), size, stride)):
        if hi <= lo:
            continue
        start, end = offs[lo][0], offs[hi - 1][1]
        out.append(Chunk(doc_id, i, start, end, text[start:end], "fixed"))
    tokens_in = lambda s, e: _token_index(offs, e) - _token_index(offs, s)
    return _merge_undersized(out, params["min_final"], text, tokens_in)


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
    tokens_in = lambda s, e: _token_index(offs, e) - _token_index(offs, s)
    return _merge_undersized(out, params["min_final"], text, tokens_in)


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
    out, mergeable, idx = [], [], 0
    for (s, e, label) in merged:
        lo, hi = _token_index(offs, s), _token_index(offs, e)
        if hi - lo <= max_size:
            out.append(Chunk(doc_id, idx, s, e, text[s:e], "structure", label))
            mergeable.append(True)
            idx += 1
            continue
        # too long for one chunk: split it on sentence boundaries, never
        # across unit boundaries -- the unit is the thing being respected.
        # The pieces are not eligible for the floor merge below: merging
        # them back together would silently undo the split max_size exists
        # to enforce, which is a different failure from the one that merge
        # closes.
        sub = _sentence(text[s:e], [(a - s, b - s) for a, b in offs[lo:hi]],
                        {"max_size": max_size, "overlap": params["overlap"],
                         "min_final": 0}, doc_id)
        for c in sub:
            out.append(Chunk(doc_id, idx, s + c.start, s + c.end,
                             text[s + c.start:s + c.end], "structure", label))
            mergeable.append(False)
            idx += 1
    # The pre-merge above is structural -- it keeps a one-line section from
    # becoming a one-line chunk by respecting unit boundaries, and stays for
    # that reason (task 054). It does not, by itself, guarantee no resulting
    # chunk is still under the floor: a short unit with no adjacent short
    # unit to merge with (the first unit of a document, or one separated by
    # a gap) reaches here unmerged. The same shared rule every strategy ends
    # on now closes that gap too, uniformly.
    return _merge_undersized(out, min_size, text, tokens_in, mergeable)


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
