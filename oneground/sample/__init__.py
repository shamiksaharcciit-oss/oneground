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

from . import arxiv as _arxiv
from . import stackexchange as _stackexchange
from .arxiv import (eligible, primary_category, sample_records, split_queries,
                    year_of)
from .fields import (CANONICAL, DEFAULTS, FieldMapError, drift_cutoff,
                     field_map)
from .loaders import (LoadError, load_ids, load_metadata, load_queries,
                      load_vectors, normalize_rows, subsample)

# One reader per source shape, chosen by `source.format` in the spec. A spec
# with no `format` is an arXiv snapshot, which is what every spec written
# before task 016 is.
READERS = {
    "arxiv_jsonl": _arxiv.sample_records,
    "stackexchange_parquet": _stackexchange.sample_records,
}


def sample_for_spec(source, spec, n_total, seed, log=None):
    """Sample `n_total` records from `source` the way `spec` says to."""
    fmt = ((spec.get("source") or {}).get("format")) or "arxiv_jsonl"
    try:
        reader = READERS[fmt]
    except KeyError:
        raise ValueError(
            f"source.format {fmt!r} has no reader; known formats: "
            f"{sorted(READERS)}") from None
    return reader(source, spec, n_total, seed, log=log)


__all__ = [
    "CANONICAL", "DEFAULTS", "FieldMapError", "LoadError", "READERS",
    "drift_cutoff", "eligible", "field_map", "load_ids", "load_metadata",
    "load_queries", "load_vectors", "normalize_rows", "primary_category",
    "sample_for_spec", "sample_records", "split_queries", "subsample",
    "year_of",
]
