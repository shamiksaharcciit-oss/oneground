"""Intrinsic dimensionality, by the TwoNN estimator.

How many dimensions the data actually occupies, as opposed to how many the
embedding declares. bge-base declares 768; arXiv abstracts occupy ~32.5 of
them. That gap is why a 768-dimensional index is not the right size of
problem, and it is the first number a user should see about their corpus.
"""

import numpy as np


def two_nn_lid(x, seed, n_sample=20000, discard=0.10):
    """TwoNN intrinsic-dimension estimator (Facco et al. 2017).

    Moved from corpora/build_fixture.py unchanged. The estimator works on the
    ratio of second- to first-nearest-neighbour distances; the top `discard`
    fraction is dropped because the tail is where the estimator is least
    stable.
    """
    import faiss
    rng = np.random.default_rng(seed)
    s = x[rng.choice(len(x), size=min(n_sample, len(x)), replace=False)]
    idx = faiss.IndexFlatL2(s.shape[1])
    idx.add(s)
    d, _ = idx.search(s, 3)               # self, nn1, nn2 (squared)
    r1 = np.sqrt(np.maximum(d[:, 1], 1e-12))
    r2 = np.sqrt(np.maximum(d[:, 2], 1e-12))
    mu = r2 / r1
    mu = np.sort(mu[np.isfinite(mu) & (mu > 1)])
    mu = mu[: int(len(mu) * (1 - discard))]
    return float(len(mu) / np.sum(np.log(mu)))
