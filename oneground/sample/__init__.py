"""Getting vectors in: the user's own, or the fixture's source corpus.

Two entry points that do not resemble each other, because the jobs differ:

`arxiv` holds the fixture builder's two-pass stratified sampling over the
arXiv metadata snapshot -- source-specific, and moved from
`corpora/build_fixture.py` unchanged so the smoke and canonical fixtures
rebuild byte-identically.

`loaders` holds the product path: load whatever the user points at (.npy,
.parquet, .jsonl), downsample it to `target_sample_size` with a seeded draw,
and record exactly which rows were used. That last part matters more than it
looks -- a characterization of 20,000 rows out of 2.1 million is only a
receipt if the file says which 20,000.
"""

from .arxiv import (eligible, primary_category, sample_records, split_queries,
                    year_of)
from .loaders import (LoadError, load_ids, load_metadata, load_queries,
                      load_vectors, normalize_rows, subsample)

__all__ = [
    "LoadError", "eligible", "load_ids", "load_metadata", "load_queries",
    "load_vectors", "normalize_rows", "primary_category", "sample_records",
    "split_queries", "subsample", "year_of",
]
