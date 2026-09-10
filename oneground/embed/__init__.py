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

__all__ = ["load_model", "embed", "EmbedError"]


class EmbedError(RuntimeError):
    """Text was supplied with no model to embed it with, or the model failed."""


def load_model(model_name, device="cpu", max_seq_length=512, log=None):
    """Load a SentenceTransformer and hash its weights for the receipt.

    The weight hash is best-effort: it needs the HuggingFace cache layout, and
    a miss must not sink a run that is otherwise fine. It is recorded as null
    and reported as couldn't-check rather than silently omitted.
    """
    def _say(msg):
        if log:
            log(msg)

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name, device=device)
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
