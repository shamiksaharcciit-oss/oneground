"""Extraction of 10-K filings from EDGAR (task 030).

Source-specific, the way `arxiv.py` and `stackexchange.py` are, and for a
different reason again: the source is not a dataset at all but 21,287
separately-filed HTML documents of wildly varying discipline, written by
thousands of filers and their agents over three years. There is no schema.
What structure exists is a convention -- "Item 1. Business", "Item 1A. Risk
Factors" -- that most filers follow and some do not.

That variance is the point, and it is also the trap. A rule loose enough to
accept everything would report structure that is not there; a rule tight
enough to be sure would quietly keep only the filings that happen to suit it.
Either way the fixture would be measuring this parser rather than the corpus.
So the rule below is written down in full, and **every document it turns away
is counted and attributed to a category** (`REJECTIONS`). The fixture
publishes examined-versus-accepted and the reasons. A rejection rate is a
measurement of the corpus and of this rule together, and it is reported as
such rather than hidden by a bigger numerator.

Access is one streamed request per filing. The complete submission at
`edgar/data/<cik>/<accession>.txt` is SGML-wrapped, each part a <DOCUMENT>
with a declared <TYPE>; the 10-K is the first part, about 1 kB in. The reader
stops at the end of that part and abandons the rest of the response, so a
16 MB submission costs the ~3 MB the filing itself occupies and no
primary-document lookup is needed. Nothing is written to disk but the
extracted text (the 016 rule).

EDGAR requires a declared user agent carrying a reachable contact. This is
not advisory: an undeclared agent is refused outright on this path, and --
measured, before the refusal -- SEC's edge first injects a bot-detection
<script> carrying a random nonce into otherwise-static documents, which makes
every byte digest irreproducible without any error being raised. See
`USER_AGENT` and the task 030 report.
"""

import html
import re
import unicodedata

# ---------------------------------------------------------------- the source

USER_AGENT = "oneground/0.1 (shamik.saha.rcciit@gmail.com)"
"""Declared to EDGAR on every request, as SEC's access policy requires.

Published deliberately: the policy asks for a contact that is reachable, and
a fixture whose source cannot be re-fetched is not reproducible. **A
rebuilder must substitute their own address.** Nobody should put load on
EDGAR under this one.

A URL may not appear here. Measured against the live service on 2026-09-19:
any user agent containing a domain is refused with 403, with or without a
scheme and with or without a leading `+`; the same string carrying only the
e-mail address is served. The repository URL is carried in the fixture spec
instead.
"""

ARCHIVES = "https://www.sec.gov/Archives/"
INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/form.idx"

# SEC asks for no more than 10 requests a second. The build stays under.
MAX_REQUESTS_PER_SECOND = 8

# ------------------------------------------------------------ the rejections

REJECTIONS = {
    "fetch_failed":      "the submission could not be retrieved after retries",
    "no_10k_document":   "no <DOCUMENT> in the submission declares <TYPE>10-K",
    "not_html":          "the 10-K part is not HTML (plain text or encoded binary)",
    "decode_failed":     "the bytes decode under neither utf-8 nor cp1252",
    "too_short":         "the extracted text is shorter than MIN_DOC_CHARS",
    "no_sections":       "no Item heading survived table-of-contents filtering",
    "too_few_sections":  "fewer than MIN_SECTIONS distinct Items were recovered",
    "no_core_section":   "none of Items 1, 1A, 7 or 8 was recovered",
    "sections_empty":    "the Items were recovered but carry no prose",
}
"""Every way a filing can fail to become a record, and what each means.

They are kept apart from each other, and from `too_short`, because they fail
for different reasons and a reader deciding whether to trust this corpus
needs to see which.

`sections_empty` is the one that is easy to miss and would do the most
damage. An asset-backed issuer files a structurally perfect 10-K under
General Instruction J: Items 1 to 15 are all present, in order, correctly
numbered, and every one of them reads "Omitted." A rule that counts headings
accepts it -- 22 Items recovered from 45,915 characters, which looks like the
best-structured filing in the sample -- and what lands in the corpus is a
cover page, a list of Item titles and nothing else. It is caught by asking
what the sections *contain* rather than whether they exist.
"""

MIN_DOC_CHARS = 20_000      # a real 10-K is 100k+; below this it incorporates by reference
MIN_SECTIONS = 6            # of the 23 canonical Items
CORE_ITEMS = ("1", "1A", "7", "8")

MIN_PROSE_CHARS = 1_000
MIN_PROSE_SECTIONS = 4
"""At least this many recovered Items must carry at least this much body.

The floor a filing has to clear to be a document rather than a table of
contents with the pages removed. Both numbers are deliberately low: the test
is meant to catch the empty filing, not to grade the full ones. The
asset-backed trusts in the development sample have every section between 29
and 44 characters, so they fail it by two orders of magnitude, and no filing
that clears it in that sample does so narrowly.
"""

# --------------------------------------------------------------- the HTML rule

_SGML_TEXT = re.compile(rb"<TEXT>", re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)
_IX_HEADER = re.compile(r"<ix:header\b.*?</ix:header\s*>", re.S | re.I)
_HIDDEN_DIV = re.compile(r'<div[^>]*style="[^"]*display:\s*none[^"]*"[^>]*>.*?</div>',
                         re.S | re.I)
_TABLE = re.compile(r"<table\b.*?</table\s*>", re.S | re.I)
_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", re.S | re.I)
_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr\s*>", re.S | re.I)
_BLOCK = re.compile(r"</?(p|div|br|tr|li|h[1-6]|table|section|article)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS_RUN = re.compile(r"[ \t ]+")
_NL_RUN = re.compile(r"\n{3,}")

# A cell counts as numeric if, stripped of currency, separators and the
# parenthesis convention for negatives, nothing but digits remains.
_NUMERICISH = re.compile(r"^[\s$()\-–—+%.,0-9]*$")

TABLE_NUMERIC_FRACTION = 0.60
"""Above this share of numeric-or-empty cells, a table is dropped, not read.

A 10-K is mostly financial tables, and a linearised balance sheet embeds as a
run of numbers with no sentence in it -- text that would dominate the corpus
and mean nothing to a retrieval measure. Below the threshold the table is
prose that a filer happened to lay out in a grid, which is common enough that
dropping every table would delete real narrative; those are linearised, cells
joined by " | ". The threshold is declared here rather than tuned: its effect
on accepted-document length is reported in the task 030 report.
"""


def _strip_sgml(part):
    """The bytes of one <DOCUMENT>, reduced to the bytes of its <TEXT>."""
    m = _SGML_TEXT.search(part)
    return part[m.end():] if m else part


def decode(raw):
    """Filings rarely declare a charset. utf-8, then cp1252, then give up."""
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def _clean_inline(fragment):
    return _WS_RUN.sub(" ", html.unescape(_TAG.sub(" ", fragment))).strip()


def _table_text(tbl):
    """One table, dropped or linearised by its numeric density."""
    rows = _ROW.findall(tbl)
    cells = [[_clean_inline(c) for c in _CELL.findall(r)] for r in rows]
    flat = [c for row in cells for c in row]
    if not flat:
        return "\n"
    numeric = sum(1 for c in flat if _NUMERICISH.match(c))
    if numeric / len(flat) >= TABLE_NUMERIC_FRACTION:
        return "\n"
    lines = [" | ".join(c for c in row if c) for row in cells]
    return "\n" + "\n".join(l for l in lines if l) + "\n"


def to_text(doc):
    """The declared extraction rule, in order.

    1. the SGML <TEXT> body only;
    2. comments, <script>, <style>, inline-XBRL <ix:header> and display:none
       containers removed -- these carry hidden XBRL facts that are not part
       of the filing a reader sees;
    3. each <table> dropped if at least TABLE_NUMERIC_FRACTION of its cells
       are numeric or empty, else linearised with " | " between cells;
    4. block tags become newlines, every other tag a space;
    5. HTML entities unescaped, NBSP and the Unicode dashes and quotes
       normalised under NFKC;
    6. runs of spaces collapsed to one, runs of blank lines to one.

    Nothing is lower-cased, nothing is stemmed, no boilerplate is removed.
    Boilerplate is a property of this corpus that the fixture exists to
    report, so stripping it here would delete the finding.
    """
    text = _COMMENT.sub(" ", doc)
    text = _SCRIPT.sub(" ", text)
    text = _IX_HEADER.sub(" ", text)
    text = _HIDDEN_DIV.sub(" ", text)
    text = _TABLE.sub(lambda m: _table_text(m.group(0)), text)
    text = _BLOCK.sub("\n", text)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text).replace(" ", " ")
    text = _WS_RUN.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _NL_RUN.sub("\n\n", text).strip()


# -------------------------------------------------------------- the sections

CANONICAL_ITEMS = ["1", "1A", "1B", "1C", "2", "3", "4",
                   "5", "6", "7", "7A", "8", "9", "9A", "9B", "9C",
                   "10", "11", "12", "13", "14", "15", "16"]
_ORDER = {k: i for i, k in enumerate(CANONICAL_ITEMS)}

HEADING_TITLE_CHARS = 200
"""How much of the heading line may follow the Item number.

Generous on purpose. The cap exists only to stop a sentence that happens to
begin "Item 7 of this report describes..." from matching a whole paragraph;
it is not a filter on real headings. Two of the canonical titles are long --
Item 5, "Market for Registrant's Common Equity, Related Stockholder Matters
and Issuer Purchases of Equity Securities", runs to 128 characters as filers
write it, and Item 12 to 116 -- so a tighter cap silently deletes those two
Items from almost every filing while their neighbours are recovered. That is
the exact failure this module exists to avoid, and it was found by Item 5
appearing in 5 of 35 accepted filings against Item 6's 33.
"""

_ITEM_WORD = r"I[ \t]?T[ \t]?E[ \t]?M"
"""The word, allowing a space to fall inside it.

Not a flourish. Filers lay headings out as separate inline elements and
letter-space them for typography, so after the tags come out the word arrives
as `It em 7.` (Rocket Lab), `I T EM 6.` (Ikena), and the number is often on
the next line again -- `ITEM\\n1A. RISK FACTORS` (Jewett Cameron, Oncotelic).
Four of the forty filings in the development sample were rejected on this
alone, three of them real 10-Ks of 150k to 630k characters. Requiring the
literal string measures the filer's HTML generator, not the filing.
"""

_HEADING = re.compile(
    r"^[ \t]*(?:PART\s+[IV]+[ \t.\-–—:]*)?"
    + _ITEM_WORD +
    r"[ \t\n]{1,3}(\d{1,2})[ \t]*([A-C])?[ \t]*([.\-–—:)])?[ \t]*"
    r"(.{0,%d})$" % HEADING_TITLE_CHARS,
    re.I | re.M)
"""Groups: item number, optional letter suffix, optional separator, title.

The separator is captured rather than discarded because it is the only thing
distinguishing `Item 15 for a list of our Financial Statements` -- a sentence
that begins a line -- from `ITEM 15 | EXHIBITS | 87`, which is a heading a
filer wrote without punctuation. See `_is_cross_reference`.
"""


def _is_cross_reference(sep, title):
    """A line that begins with an Item number but continues as prose.

    Measured over the development sample: of 1,403 candidates, 1,317 carry a
    separator, 84 carry none but a capitalised title (real headings -- filers
    do write `ITEM 1 | BUSINESS | 4`), and 2 carry none and continue in lower
    case. Both of those two are cross-references. The test is narrow on
    purpose; it is not a general defence against prose, which is what the
    increasing-subsequence rule is for.
    """
    return not sep and title[:1].islower()

TOC_MAX_GAP = 800
TOC_MIN_RUN = 6
TOC_MAX_POSITION = 0.20
"""A run of TOC_MIN_RUN or more candidates, each within TOC_MAX_GAP characters
of the next and beginning inside the first TOC_MAX_POSITION of the text, is
the contents page and is dropped whole.

The contents page lists every Item in order with page numbers, as consecutive
lines of one table: its entries are tens of characters apart. A real section
heading is followed by its section, so the next heading is pages away. The
gap between candidates separates the two, and unlike a symmetric density
window it does not also delete the first real heading when the body begins
immediately after the contents -- which it usually does. Canadian Pacific's
real `ITEM 1. BUSINESS` sits 1,448 characters after its own contents entry,
and a 3,000-character window swallowed it.

The position test is the second half of the rule and is not decoration. A
dense run is not by itself a contents page: Items 10 to 14 are commonly
answered "incorporated by reference to the Proxy Statement", six consecutive
headings with a line of body each, which has the same shape. Dropping those
cost four filings and pushed Items 10-16 down to 26 of 34 recovered while
Items 1-9 stayed at 33. A contents page is at the front of the document;
Part III is at the back.
"""


def _runs(cands):
    """Candidates grouped into runs of near-neighbours in increasing order.

    A run breaks on distance, and also where the Item order steps backwards.
    The second test is what protects the first real heading: a contents page
    runs 1, 1A, 1B ... 15, 16 and the body's own `Item 1` follows it, often
    within a few hundred characters, so on distance alone the body heading is
    swallowed by the contents run and Item 1 is lost while Item 1A survives.
    Measured at 31 of 38 accepted filings before this test, 38 of 38 after.
    A contents page never counts down.
    """
    runs, run = [], [cands[0]]
    for prev, c in zip(cands, cands[1:]):
        if (c["start"] - prev["start"] <= TOC_MAX_GAP
                and _ORDER[c["item"]] > _ORDER[prev["item"]]):
            run.append(c)
        else:
            runs.append(run)
            run = [c]
    runs.append(run)
    return runs


def _longest_increasing(cands):
    """Longest subsequence whose canonical Item order strictly increases.

    Cross-references that survive the density test are out of order with
    their neighbours and drop out here. O(n^2) is fine: a filing yields tens
    of candidates, not thousands.
    """
    n = len(cands)
    if not n:
        return []
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if (_ORDER[cands[j]["item"]] < _ORDER[cands[i]["item"]]
                    and best[j] + 1 > best[i]):
                best[i], prev[i] = best[j] + 1, j
    i = max(range(n), key=lambda k: best[k])
    out = []
    while i != -1:
        out.append(cands[i])
        i = prev[i]
    return list(reversed(out))


def find_sections(text):
    """Item headings with their character offsets into `text`.

    Returns a list of {item, title, start, end}, in document order, `start`
    at the heading and `end` at the next heading or the end of the text. The
    offsets are what a chunking strategy is scored against, so they index the
    extracted text exactly as the fixture publishes it.
    """
    cands = []
    for m in _HEADING.finditer(text):
        item = m.group(1) + (m.group(2) or "").upper()
        title = m.group(4).strip(" .:-–—|")
        if item not in _ORDER or _is_cross_reference(m.group(3), title):
            continue
        cands.append(dict(item=item, title=title, start=m.start()))
    if not cands:
        return []

    front = TOC_MAX_POSITION * len(text)
    kept = [c for run in _runs(cands)
            if not (len(run) >= TOC_MIN_RUN and run[0]["start"] <= front)
            for c in run]
    if not kept:
        return []

    best = _longest_increasing(kept)
    for a, b in zip(best, best[1:]):
        a["end"] = b["start"]
    if best:
        best[-1]["end"] = len(text)
    return best


# --------------------------------------------------------------- the decision

def extract(part):
    """One <DOCUMENT> part -> a record, or a rejection with its category.

    Returns (record, None) or (None, category). Never raises on bad input: a
    filing that defeats the rule is a measurement, not an error.
    """
    raw = _strip_sgml(part)
    doc = decode(raw)
    if doc is None:
        return None, "decode_failed"
    if not re.search(r"<(html|body|div|p|table)\b", doc[:20000], re.I):
        return None, "not_html"
    text = to_text(doc)
    if len(text) < MIN_DOC_CHARS:
        return None, "too_short"
    sections = find_sections(text)
    if not sections:
        return None, "no_sections"
    items = {s["item"] for s in sections}
    if len(items) < MIN_SECTIONS:
        return None, "too_few_sections"
    if not any(i in items for i in CORE_ITEMS):
        return None, "no_core_section"
    prose = sum(1 for s in sections if s["end"] - s["start"] >= MIN_PROSE_CHARS)
    if prose < MIN_PROSE_SECTIONS:
        return None, "sections_empty"
    return dict(text=text, sections=sections, chars=len(text),
                prose_sections=prose), None


# ------------------------------------------------------- the baseline chunking

CHUNK_TOKENS = 512
CHUNK_OVERLAP = 64
CHUNK_STRIDE = CHUNK_TOKENS - CHUNK_OVERLAP
CHUNK_MIN_TOKENS = 32

BASELINE_CHUNKING_IS_NOT_A_RECOMMENDATION = """\
Fixed-size, section-blind, 512 tokens with 64 of overlap.

This fixture ships one chunking because the five standard measures need a
vector set, and shipping one is not endorsing it. It is a **baseline for
comparison**: the thing a strategy has to beat, chosen to be the obvious
naive default rather than a good idea.

Section-blind on purpose. The fixture publishes every document's section
offsets precisely so a strategy can be scored on whether it cut through one;
a baseline that respected those boundaries would already be the treatment.
This one knows nothing about Item headings and will cut through them, and how
often it does is a number task 031 can report against.

512 tokens because that is `bge-base-en-v1.5`'s `max_seq_length`, so no chunk
is truncated at embedding time and chunk size is not confounded with
truncation. 64 tokens of overlap because some overlap is near-universal in
practice and zero would make the baseline a straw man. Neither number was
tuned against any measurement, and neither should be read as advice.

The rule is deterministic: the tokenizer is the embedding model's own, the
stride is fixed, and the cut points are a function of the text alone. No seed
enters here. The seed in the spec governs which chunks are *sampled* down to
the fixture's 150,000, which is a separate step.
"""


def chunk_document(text, offsets, n_tokens):
    """Fixed-size chunks over a tokenised document, as character spans.

    `offsets` is the tokenizer's offset mapping for `text` (fast tokenizers
    return it); `n_tokens` its length. Returns dicts with the token range and
    the character range, so a chunk can be tied back to the section offsets
    the fixture publishes.

    The last chunk is kept only if it carries CHUNK_MIN_TOKENS, so a document
    whose length lands just past a stride boundary does not contribute a
    two-token fragment to the corpus.
    """
    out = []
    for lo in range(0, max(n_tokens, 1), CHUNK_STRIDE):
        hi = min(lo + CHUNK_TOKENS, n_tokens)
        if hi - lo < CHUNK_MIN_TOKENS and out:
            break
        out.append(dict(token_start=lo, token_end=hi,
                        char_start=int(offsets[lo][0]),
                        char_end=int(offsets[hi - 1][1])))
        if hi >= n_tokens:
            break
    return out


def sections_spanned(chunk, sections):
    """Which Items a chunk overlaps, and whether it cuts through a boundary.

    A chunk that overlaps more than one section crossed a heading. This is
    the per-chunk fact the fixture publishes so that a chunking strategy can
    be scored on boundary alignment without re-deriving the sections.
    """
    hit = [s["item"] for s in sections
           if s["start"] < chunk["char_end"] and s["end"] > chunk["char_start"]]
    return dict(items=hit, crosses_boundary=len(hit) > 1)
