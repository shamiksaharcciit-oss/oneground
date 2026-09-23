"""Embedding text with a pinned model, and hashing the weights that did it.

A vector is only a receipt if you can say which weights produced it. The
model is pinned by name in the spec or requirements file, and the weight file
is hashed into the receipt -- so "the same model" means the same bytes, not
the same string on HuggingFace.

Moved from corpora/build_fixture.py unchanged.
"""

import os

import numpy as np

from ..receipts import sha256_file

__all__ = ["load_model", "embed", "EmbedError", "NoModelNamed",
           "EmbedFailed"]


class EmbedError(RuntimeError):
    """Base: something went wrong embedding. **Raise one of the two below.**

    This used to read *"text was supplied with no model to embed it with, or
    the model failed"* -- one class for a refusal and a failure, and a
    caller handed it could not tell which it got. It was never raised, which
    is why it was split before anything depended on it: the cheapest moment
    to separate a type that promises two things is before the first raise.

    The base is kept so `except EmbedError` catches both, and so that a
    caller who genuinely does not care does not have to name two.
    """


class NoModelNamed(EmbedError):
    """No model was named to embed the text with. **A refusal.**

    The user's file did not say, the tool will not choose -- the model
    decides what every measurement means -- and the remedy is to name one.
    """


class EmbedFailed(EmbedError):
    """A named model was there and embedding it came apart. **A failure.**

    Nothing the user wrote is wrong; something broke.
    """


def load_model(model_name, device="cpu", max_seq_length=512, log=None):
    """Load a SentenceTransformer and hash its weights for the receipt.

    The weight hash is best-effort: it needs the HuggingFace cache layout, and
    a miss must not sink a run that is otherwise fine. It is recorded as null
    and reported as couldn't-check rather than silently omitted.

    `max_seq_length=None` means **leave the model's own limit alone**. Task
    036: models declare different limits, and the old unconditional assignment
    had no way to say "whatever this model says" -- passing None set the limit
    to None, which reads back as 0 and truncates everything to nothing. The
    default stays 512 so every existing caller is unchanged.
    """
    def _say(msg):
        if log:
            log(msg)

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name, device=device)
    if max_seq_length is not None:
        model.max_seq_length = max_seq_length

    weights_sha = None
    try:
        from huggingface_hub import snapshot_download
        p = snapshot_download(model_name)
        for cand in ("model.safetensors", "pytorch_model.bin"):
            fp = os.path.join(p, cand)
            if os.path.exists(fp):
                weights_sha = sha256_file(fp)
                break
    except Exception as e:
        _say(f"could not hash weights: {e}")
    return model, weights_sha


def embed(model, texts, batch, show_progress_bar=True):
    v = model.encode(texts, batch_size=batch, show_progress_bar=show_progress_bar,
                     convert_to_numpy=True, normalize_embeddings=True)
    return v.astype(np.float32)


TRUNCATION_ADVICE = (
    "if these are documents rather than chunks, chunk them first -- "
    "everything past the limit was discarded before a single number was "
    "computed, and no measurement downstream can tell you it happened")


def count_truncated(model, texts, max_seq_length=None, batch=1000):
    """How many records the model will silently cut. Task 017 item 3.

    A transformer takes a fixed number of tokens and drops the rest. It does
    not fail, it does not warn, and the vector it returns is a perfectly good
    vector -- of the first `max_seq_length` tokens. Every measurement built on
    it then describes a corpus the user does not have: recall against ground
    truth computed from the same truncated vectors is self-consistent and
    says nothing about whether the tail mattered.

    Counted with the model's own tokenizer, the one `encode` is about to use,
    so this is what will actually happen rather than an estimate from
    characters or whitespace.

    Returns None when the count cannot be taken -- couldn't-check, which the
    caller records as such rather than reporting zero truncated.
    """
    tok = getattr(model, "tokenizer", None)
    if tok is None:
        return None
    limit = int(max_seq_length if max_seq_length is not None
                else getattr(model, "max_seq_length", 0) or 0)
    if limit <= 0:
        return None

    n, truncated, longest = 0, 0, 0
    try:
        for i in range(0, len(texts), batch):
            chunk = [str(t) for t in texts[i:i + batch]]
            encoded = tok(chunk, add_special_tokens=True, truncation=False,
                          padding=False)["input_ids"]
            for ids in encoded:
                n += 1
                ln = len(ids)
                if ln > longest:
                    longest = ln
                if ln > limit:
                    truncated += 1
    except Exception:                                 # tokenizer-specific
        return None

    return {
        "model": getattr(model, "_oneground_name", None),
        "max_seq_length": limit,
        "n_records": n,
        "truncated_count": truncated,
        "truncated_fraction": (truncated / n) if n else 0.0,
        "longest_tokens": longest,
        "counted_with": "the model's own tokenizer, add_special_tokens=True",
        "note": ("records whose tokenized length exceeds max_seq_length. The "
                 "model truncates them to the limit and returns a vector "
                 "without reporting it; this is the count of how often that "
                 "happened. " + TRUNCATION_ADVICE),
    }
