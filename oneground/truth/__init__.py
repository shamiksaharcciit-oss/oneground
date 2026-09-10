"""Exact k-NN ground truth.

Every recall number in this project is measured against brute-force exact
search over the same vectors, not against another index's opinion. That is
what makes "recall 0.932" a fact rather than a comparison.

Moved from corpora/build_fixture.py unchanged.
"""

import numpy as np

from ..measures.drift import recall

__all__ = ["exact_knn", "recall"]


def exact_knn(base, queries, k):
    """Brute-force inner-product k-NN. Vectors are L2-normalized, so inner
    product ranks identically to cosine."""
    import faiss
    idx = faiss.IndexFlatIP(base.shape[1])
    idx.add(base)
    _, ids = idx.search(queries, k)
    return ids
