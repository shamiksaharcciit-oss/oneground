"""Truncation accounting. Task 017 item 3.

**Synthetic throughout.** The tokenizer here is a stub that splits on
whitespace, so nothing in this file measures a real model. What it measures is
the counting rule, against a corpus with a known number of over-length
records -- which is the only part that can be wrong in a way a real model
would hide.

WHY THIS MATTERS MORE THAN IT LOOKS
-----------------------------------
Every other intake fault leaves a trace. A wrong dimension raises, a missing
file raises, a bad metric shows up as terrible recall. Truncation leaves
none: the transformer takes its `max_seq_length` tokens, drops the rest, and
returns a well-formed vector. Ground truth computed from those same truncated
vectors agrees with them perfectly, so recall is high and self-consistent, and
the corpus every number describes is not the corpus on disk.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from oneground.embed import count_truncated, TRUNCATION_ADVICE  # noqa: E402


class _Tokenizer:
    """Splits on whitespace and adds two special tokens, like a real one."""

    def __init__(self, special=2):
        self.special = special

    def __call__(self, texts, add_special_tokens=True, truncation=False,
                 padding=False):
        extra = self.special if add_special_tokens else 0
        return {"input_ids": [[0] * (len(t.split()) + extra) for t in texts]}


class _Model:
    def __init__(self, max_seq_length=10, tokenizer=None, name="stub/model"):
        self.max_seq_length = max_seq_length
        self.tokenizer = _Tokenizer() if tokenizer is None else tokenizer
        self._oneground_name = name


def _corpus(n_short, n_long, limit=10):
    """`n_long` records over the limit, `n_short` comfortably under it."""
    short = ["word " * (limit - 5) for _ in range(n_short)]
    long_ = ["word " * (limit * 4) for _ in range(n_long)]
    return short + long_


def test_a_known_number_of_over_length_records_is_counted():
    t = count_truncated(_Model(max_seq_length=10), _corpus(70, 30))
    assert t["n_records"] == 100
    assert t["truncated_count"] == 30, t
    assert abs(t["truncated_fraction"] - 0.30) < 1e-9
    assert t["max_seq_length"] == 10
    assert t["model"] == "stub/model"


def test_a_corpus_that_fits_reports_zero_not_nothing():
    t = count_truncated(_Model(max_seq_length=10), _corpus(50, 0))
    assert t["truncated_count"] == 0
    assert t["n_records"] == 50
    # Zero is a measurement. None is the absence of one, and they must not be
    # the same value -- `build_info` distinguishes them.
    assert t["truncated_count"] is not None


def test_the_special_tokens_count_toward_the_limit():
    """A record of exactly `max_seq_length` words is over the limit once the
    tokenizer's two special tokens are added, and the real one adds them."""
    model = _Model(max_seq_length=10)
    exactly_ten_words = ["w " * 10]
    t = count_truncated(model, exactly_ten_words)
    assert t["longest_tokens"] == 12, t          # 10 + [CLS] + [SEP]
    assert t["truncated_count"] == 1, (
        "counting without special tokens would call this a fit")


def test_the_boundary_is_strictly_greater_than():
    """Exactly at the limit is not truncated; one over is."""
    model = _Model(max_seq_length=12, tokenizer=_Tokenizer(special=0))
    assert count_truncated(model, ["w " * 12])["truncated_count"] == 0
    assert count_truncated(model, ["w " * 13])["truncated_count"] == 1


def test_the_longest_record_is_reported():
    t = count_truncated(_Model(max_seq_length=10),
                        ["w " * 5, "w " * 200, "w " * 7])
    assert t["longest_tokens"] == 202, t
    assert t["truncated_count"] == 1


def test_batching_does_not_change_the_count():
    """The walk is batched; a boundary must not drop or double-count."""
    corpus = _corpus(37, 23)
    full = count_truncated(_Model(max_seq_length=10), corpus, batch=1000)
    for b in (1, 2, 7, 60, 61):
        got = count_truncated(_Model(max_seq_length=10), corpus, batch=b)
        assert got["truncated_count"] == full["truncated_count"] == 23, b
        assert got["n_records"] == full["n_records"] == 60, b


def test_no_tokenizer_is_couldnt_check_not_zero():
    """Reporting 0 truncated when nothing was counted would be the worst
    possible answer: it is the one that looks like good news."""
    model = _Model()
    model.tokenizer = None
    assert count_truncated(model, ["anything"]) is None


def test_a_tokenizer_that_raises_is_couldnt_check():
    class _Angry:
        def __call__(self, *a, **k):
            raise RuntimeError("no")

    assert count_truncated(_Model(tokenizer=_Angry()), ["x"]) is None


def test_no_limit_is_couldnt_check():
    assert count_truncated(_Model(max_seq_length=0), ["x"]) is None


def test_the_advice_names_chunking():
    """The brief's wording: the warning has to say what to do about it."""
    t = count_truncated(_Model(max_seq_length=10), _corpus(1, 1))
    assert "chunk them first" in TRUNCATION_ADVICE
    assert "chunk them first" in t["note"]


def test_an_empty_corpus_does_not_divide_by_zero():
    t = count_truncated(_Model(max_seq_length=10), [])
    assert t["n_records"] == 0 and t["truncated_count"] == 0
    assert t["truncated_fraction"] == 0.0
