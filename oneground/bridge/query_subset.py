"""The declared query subset the export needs, and no receipt held before
this module. `docs/BRIDGE.md` §3.3.

VectorDBBench copies its whole test set into every concurrent process, so a
recommended run uses far fewer queries than a oneground fixture draws for
the ambiguity rate -- 2,000 against VectorDBBench's own advice of around
1,000. The export therefore takes a **seeded subset**, and the subset has
to be declared, not assumed: "the first N", "however many happened to load"
and "the seed used for the corpus sample" are three different subsets that
would each produce a plausible-looking, silently wrong export.

Written in the same shape `sample_ids.json` and `queries_ids.json` already
use: a seeded, sorted draw over positions (`loaders.subsample`'s own
method, `np.random.default_rng(seed).choice(...).sort()`), so "same seed,
same file" holds here the way it holds for the corpus sample. Written once
per seed, the way `oneground/proposals/prediction.py:write_prediction`
writes once before a run -- a second call with the same seed either agrees
byte for byte or should not have been made.
"""

import json
import os

import numpy as np

from ..provenance import invocation
from ..receipts import producing_version, sha256_file, write_json_stable

#: The file this module writes, sibling to `queries_ids.json` in the same
#: workdir -- the "recorded the way sampling is recorded for the corpus,
#: and the selected ids written as a receipt the way queries_ids.json
#: writes the full set" §3.3 asks for, both in one file rather than two.
NAME = "query_subset.json"


class QuerySubsetError(ValueError):
    """The subset could not be selected, or the receipt could not be
    written without silently replacing one that already exists."""


def select(n_available, size, seed):
    """Positions into the full query array -- seeded, sorted, re-derivable.

    Sorted for the same reason `loaders.subsample` sorts the corpus draw:
    the file this produces should depend on the seed alone, not on
    `np.random`'s internal draw order, so two exports with the same seed
    agree byte for byte rather than merely set-for-set.
    """
    n_available = int(n_available)
    size = int(size)
    if size <= 0:
        raise QuerySubsetError(f"query subset size must be > 0, got {size}")
    if size > n_available:
        raise QuerySubsetError(
            f"query subset size {size} exceeds the {n_available} queries "
            "available -- VectorDBBench needs fewer test vectors than a "
            "oneground fixture draws, not more")
    idx = np.random.default_rng(seed).choice(n_available, size, replace=False)
    idx.sort()
    return idx


def write(workdir, query_ids, seed, size, out_dir=None):
    """Write `query_subset.json` once. Returns `(path, sha256)`.

    `query_ids` is `queries_ids.json`'s own list, read by the caller --
    this module does not read the workdir's files itself, so a caller
    testing against a synthetic query set never has to write one to disk
    first. `out_dir` follows `write_prediction`'s split: `workdir` is the
    run whose queries these are a subset of; `out_dir` is where the
    receipt lands, when the two differ.
    """
    positions = select(len(query_ids), size, seed)
    path = os.path.join(out_dir or workdir, NAME)
    if os.path.exists(path):
        raise QuerySubsetError(
            f"{path} already exists. A query subset is written once for a "
            "given seed and size -- choose a different seed, or read the "
            "file that is already there rather than overwrite it.")
    doc = {
        "kind": "receipt",
        "oneground": producing_version(),
        "invocation": invocation(),
        "seed": int(seed),
        "size": int(size),
        "n_available": len(query_ids),
        # Positions into the full query array, in the same units
        # ground_truth.npy and neighbors.parquet use -- and the ids at
        # those positions, so a reader does not have to hold
        # queries_ids.json open to know which queries these are.
        "positions": [int(i) for i in positions],
        "ids": [query_ids[i] for i in positions],
    }
    write_json_stable(path, doc)
    return path, sha256_file(path)


def read(path):
    """The receipt `write` produced, as a dict."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)
