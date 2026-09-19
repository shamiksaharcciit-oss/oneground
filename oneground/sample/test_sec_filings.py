"""Contract tests for the 10-K extraction rule (task 030).

Every case here is a shape that was found in real filings while the rule was
being written, reduced to the smallest HTML that exhibits it. The inputs are
synthetic -- named so -- but none of the behaviours are invented: each one
cost an accepted document or a wrong section offset in the development
sample of forty filings, and the comment on each says which.

The section offsets are published as a receipt, so a heading the rule invents
is as damaging as one it misses. Both directions are tested.
"""

from oneground.sample import sec_filings as sf


def doc(body):
    """A minimal <DOCUMENT> part of the shape EDGAR serves."""
    return (b"<TYPE>10-K\n<SEQUENCE>1\n<FILENAME>x.htm\n<TEXT>\n"
            + body.encode("utf-8"))


def item_line(n, title=""):
    return f"<p>Item {n}. {title}</p>"


def filler(n=2000, word="disclosure "):
    return "<p>" + word * (n // len(word) + 1) + "</p>"


# ------------------------------------------------------------------- tables

def test_synthetic_numeric_table_is_dropped():
    """A balance sheet linearises to a run of numbers with no sentence in it."""
    html = ("<table><tr><td>Revenue</td><td>1,234</td><td>(567)</td></tr>"
            "<tr><td>Cost</td><td>890</td><td>$12</td></tr></table>")
    assert "1,234" not in sf.to_text(html)


def test_synthetic_prose_table_is_linearised():
    """Filers lay narrative out in grids; dropping every table deletes it."""
    html = ("<table><tr><td>Segment</td><td>We sell industrial equipment"
            " across three continents</td></tr></table>")
    text = sf.to_text(html)
    assert "industrial equipment" in text
    assert "|" in text


# ----------------------------------------------------------------- headings

def test_synthetic_heading_survives_a_space_inside_the_word():
    """Rocket Lab's `It em 7.` and Ikena's `I T EM 6.` -- inline elements,
    letter-spaced for typography. Requiring the literal string rejected three
    real 10-Ks of 150k to 630k characters."""
    for spelling in ("It em 7. Management", "I T EM 7. Management", "ITEM 7. Management"):
        text = f"body\n{spelling}\n"
        assert [s["item"] for s in sf.find_sections(text)] == ["7"], spelling


def test_synthetic_heading_survives_a_newline_before_the_number():
    """Jewett Cameron and Oncotelic: `ITEM\\n1A. RISK FACTORS`."""
    assert [s["item"] for s in sf.find_sections("body\nITEM\n1A. RISK FACTORS\n")] == ["1A"]


def test_synthetic_long_title_is_still_a_heading():
    """Item 5's official title runs to 128 characters as filers write it. A
    90-character cap left Item 5 in 5 of 35 filings and Item 6 in 33."""
    title = ("Market for Registrant's Common Equity, Related Stockholder "
             "Matters and Issuer Purchases of Equity Securities")
    assert len(title) > 90
    assert [s["item"] for s in sf.find_sections(f"body\nItem 5. {title}\n")] == ["5"]


# ------------------------------------------------------- the contents page

def _with_contents(n_body_filler=3000):
    """A filing shaped like a real one: contents page, then the body."""
    items = ["1", "1A", "1B", "2", "3", "4", "5", "6", "7"]
    toc = "\n".join(f"Item {i}. Title {i} | {k + 3}" for k, i in enumerate(items))
    body = "\n\n".join(f"Item {i}. Title {i}\n\n" + "prose " * n_body_filler
                       for i in items)
    return toc + "\n\n" + body


def test_synthetic_contents_page_is_dropped_whole():
    text = _with_contents()
    secs = sf.find_sections(text)
    # nine sections, each from the body, not the nine contents lines
    assert [s["item"] for s in secs] == ["1", "1A", "1B", "2", "3", "4", "5", "6", "7"]
    assert secs[0]["start"] > text.index("prose") - 200


def test_synthetic_first_body_heading_survives_the_contents_run():
    """The body's `Item 1` follows the contents page closely, so a rule that
    breaks runs on distance alone swallows it: Item 1 was recovered in 31 of
    38 accepted filings while Item 1A was recovered in all 38. A contents
    page never counts down, so the order step is what ends it."""
    items = ["1", "1A", "1B", "2", "3", "4", "5", "6"]
    toc = "\n".join(f"Item {i}. Title {i} | {k + 3}" for k, i in enumerate(items))
    body = "\n".join(f"Item {i}. Title {i}\n" + "prose " * 3000 for i in items)
    secs = sf.find_sections(toc + "\n" + body)       # no blank gap between them
    assert "1" in {s["item"] for s in secs}


def test_synthetic_part_three_run_is_not_a_contents_page():
    """Items 10-14 are commonly answered 'incorporated by reference to the
    Proxy Statement' -- six consecutive one-line sections, the same shape as
    a contents page. Dropping them cost four filings."""
    head = "Item 1. Business\n" + "prose " * 5000
    tail = "\n".join(f"Item {i}. Title\n\nIncorporated by reference."
                     for i in ("10", "11", "12", "13", "14"))
    secs = sf.find_sections(head + "\n" + tail)
    assert {"10", "11", "12", "13", "14"} <= {s["item"] for s in secs}


def test_synthetic_cross_reference_is_not_a_section():
    """'as described in Item 7' inside running prose is out of order with its
    neighbours and drops out of the increasing subsequence."""
    text = ("Item 1. Business\n" + "prose " * 3000
            + "\nItem 7 of this report describes our results\n" + "prose " * 3000
            + "\nItem 1A. Risk Factors\n" + "prose " * 3000)
    got = [s["item"] for s in sf.find_sections(text)]
    assert got == ["1", "1A"]


# --------------------------------------------------------------- the offsets

def test_synthetic_sections_tile_the_text_without_gaps():
    """The offsets index the published text exactly; a chunking strategy is
    scored against them, so they must be monotone and contiguous."""
    secs = sf.find_sections(_with_contents())
    text_len = len(_with_contents())
    for a, b in zip(secs, secs[1:]):
        assert a["start"] < a["end"] == b["start"]
    assert secs[-1]["end"] == text_len


# ------------------------------------------------------------ the rejections

def test_synthetic_structurally_perfect_but_empty_filing_is_rejected():
    """An asset-backed issuer files Items 1 to 15 under General Instruction J
    and answers 'Omitted.' to every one. It looks like the best-structured
    filing in the sample -- 22 Items recovered -- and contains nothing."""
    items = sf.CANONICAL_ITEMS
    body = "".join(item_line(i, "Title. Omitted.") for i in items)
    part = doc("<html><body>" + "<p>cover page</p>" * 2000 + body + "</body></html>")
    rec, why = sf.extract(part)
    assert rec is None and why == "sections_empty"


def test_synthetic_short_filing_is_rejected_as_too_short():
    rec, why = sf.extract(doc("<html><body><p>Item 1. Business</p></body></html>"))
    assert rec is None and why == "too_short"


def test_synthetic_non_html_part_is_rejected():
    rec, why = sf.extract(doc("begin 644 file.pdf\nM0V]N=&5N=", ))
    assert rec is None and why == "not_html"


def test_every_rejection_category_has_a_description():
    """A count with no explanation is not a measurement."""
    for name, why in sf.REJECTIONS.items():
        assert why and not why.endswith(".")


def test_synthetic_full_filing_is_accepted_with_its_sections():
    items = ["1", "1A", "1B", "2", "3", "4", "5", "6", "7", "7A", "8"]
    body = "".join(item_line(i, f"Title {i}") + filler(3000) for i in items)
    rec, why = sf.extract(doc("<html><body>" + body + "</body></html>"))
    assert why is None, why
    assert [s["item"] for s in rec["sections"]] == items
    assert rec["prose_sections"] >= sf.MIN_PROSE_SECTIONS


# ------------------------------------------------------- transport failures

def test_a_truncated_transfer_is_retried_then_becomes_one_rejection(monkeypatch):
    """http.client.IncompleteRead killed a build at 3,500 documents.

    It derives from HTTPException and ValueError, so an enumerated except
    clause listing URLError, TimeoutError and ConnectionError let it through
    and out of the worker thread. A filing that cannot be fetched is a
    rejection the corpus reports, never the end of the run.
    """
    import http.client

    calls = []

    def boom(url, timeout=300):
        calls.append(url)
        raise http.client.IncompleteRead(b"partial")

    monkeypatch.setattr(sf, "_get", boom)
    monkeypatch.setattr(sf.time, "sleep", lambda _s: None)
    try:
        sf.fetch_10k("edgar/data/1/x.txt", tries=3)
    except sf.SourceError:
        pass
    else:
        raise AssertionError("a transfer that never succeeds must raise SourceError")
    assert len(calls) == 3, calls


def test_a_403_is_not_retried(monkeypatch):
    """403 means the user agent is not declared. Waiting does not fix it."""
    import urllib.error

    calls = []

    def forbidden(url, timeout=300):
        calls.append(url)
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(sf, "_get", forbidden)
    monkeypatch.setattr(sf.time, "sleep", lambda _s: None)
    try:
        sf.fetch_10k("edgar/data/1/x.txt", tries=4)
    except urllib.error.HTTPError as e:
        assert e.code == 403
    assert len(calls) == 1, calls


def test_the_rate_limiter_holds_the_aggregate_across_threads():
    """Concurrency must never become a way to exceed a published limit."""
    import threading
    import time as _t

    lim = sf._RateLimiter(50)          # 20 ms apart
    stamps = []
    lock = threading.Lock()

    def worker():
        lim.take()
        with lock:
            stamps.append(_t.monotonic())

    ts = [threading.Thread(target=worker) for _ in range(10)]
    t0 = _t.monotonic()
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    span = max(stamps) - t0
    assert span >= 0.9 * (len(ts) - 1) * 0.02, span


# ------------------------------------- the rule as a published artifact (031)

RULE_SHA256 = "4766215f12ec83f14586d9d82fea7a21cad2889cb4b31924ee910924c2f32b87"


def test_the_extraction_rule_digest_is_the_published_one():
    """Task 031 makes 030's extraction rule a published artifact, because a
    chunking result measured on this text is conditional on it.

    If this fails, a threshold or a pattern changed. That is allowed -- it is
    not allowed to happen quietly. Update `extraction.rule_sha256` in
    fixtures/sec-filings-10k.fixture.yaml and this constant together, and say
    in the changelog what moved and why.
    """
    assert sf.rule_digest() == RULE_SHA256, (
        "the extraction rule changed; the fixture's published rule_sha256 and "
        "this constant must be updated deliberately, together")


def test_the_rule_parameters_cover_everything_that_changes_the_output():
    """A parameter missing from `rule_parameters` is a silent change waiting
    to happen: the digest would not move when the behaviour did."""
    p = sf.rule_parameters()
    for name in ("min_doc_chars", "min_sections", "core_items",
                 "min_prose_chars", "min_prose_sections",
                 "table_numeric_fraction", "heading_title_chars",
                 "item_word_pattern", "heading_pattern", "toc_max_gap",
                 "toc_min_run", "toc_max_position", "canonical_items",
                 "rejection_categories"):
        assert name in p, name
    assert p["rejection_categories"] == sorted(sf.REJECTIONS)


def test_changing_a_threshold_moves_the_digest():
    """The guard has to actually guard."""
    before = sf.rule_digest()
    original = sf.MIN_DOC_CHARS
    try:
        sf.MIN_DOC_CHARS = original + 1
        assert sf.rule_digest() != before
    finally:
        sf.MIN_DOC_CHARS = original
    assert sf.rule_digest() == before


def test_the_rule_declares_that_it_takes_no_seed():
    """Task 031 asks for the rule's seed. There is not one, and the module
    says so rather than inventing one."""
    assert "takes no seed" in sf.TAKES_NO_SEED
    assert "20260919" in sf.TAKES_NO_SEED
