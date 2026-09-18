"""The declared 2-D projection a run may carry, for the lab to draw. Task 027.

A projection is **declared, not measured**. The fixture spec calls 2-D
placement illustrative, and nothing in a run is computed from it: regions,
distances, copy counts and every published figure are computed in the full
space. It is carried in the state so the lab can draw the picture the teaser
draws, labelled as what it is.

This module only *reads* one. It never fits a projection: fitting is the
fixture builder's job, off the product path, and a lab that computed its own
would be inventing positions a published artifact does not have.

Two shapes are accepted, because the two corpora that have one store it
differently:

  * `.npy`     an (N, 2) float array -- how `stackexchange-150k` ships it
  * `.parquet` a table with `x` and `y` columns -- how `arxiv-150k` ships it,
               inside `ground_view_base.parquet`, which is the artifact the
               teaser's own picture was exported from

`pyarrow` is only imported for the second, and only when asked: it is in the
`[view]` extra, not the core dependency set, so a core install that names a
parquet projection is told what to install rather than failing on an import.
"""

import hashlib
import os

import numpy as np

COULDNT_CHECK = "couldnt_check"

# The sentence the fixture spec uses, carried verbatim into every state that
# holds a projection so the caption and the receipt say the same thing.
ILLUSTRATIVE = ("2-D placement is illustrative; regions, distances and copy "
                "counts are computed in the full space.")


class ProjectionError(RuntimeError):
    """A declared projection could not be read, or does not fit the corpus."""


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _from_parquet(path):
    try:
        import pyarrow.parquet as pq
    except ImportError as e:                       # pragma: no cover
        raise ProjectionError(
            f"{path} is a parquet projection and pyarrow is not installed. "
            "Install the view extra (`pip install oneground[view]`), or "
            "declare an .npy projection instead.") from e
    table = pq.read_table(path)
    missing = [c for c in ("x", "y") if c not in table.column_names]
    if missing:
        raise ProjectionError(
            f"{path} has no {', '.join(missing)} column; it holds "
            f"{table.column_names}")
    return np.stack([table.column("x").to_numpy(),
                     table.column("y").to_numpy()], axis=1)


def read(path, n_base):
    """The projection at `path` as (n_base, 2) float32, or raise.

    Refuses a row count that does not match the corpus rather than padding,
    truncating or reordering: a placement that does not line up with the
    vectors would draw every point in somebody else's place, and look fine.
    """
    if not os.path.isfile(path):
        raise ProjectionError(f"{path} does not exist")
    if path.lower().endswith(".parquet"):
        xy = _from_parquet(path)
    elif path.lower().endswith(".npy"):
        xy = np.load(path, mmap_mode="r")
    else:
        raise ProjectionError(
            f"{path}: a projection is .npy (N x 2) or .parquet (x, y columns)")

    xy = np.asarray(xy)
    if xy.ndim != 2 or xy.shape[1] != 2:
        raise ProjectionError(
            f"{path} has shape {xy.shape}; a projection is (N, 2)")
    if xy.shape[0] != n_base:
        raise ProjectionError(
            f"{path} holds {xy.shape[0]:,} positions and this corpus has "
            f"{n_base:,} vectors. A projection is matched to its corpus row "
            "by row; a different length is a different corpus.")
    out = np.ascontiguousarray(xy, dtype=np.float32)
    if not np.isfinite(out).all():
        raise ProjectionError(
            f"{path} holds {int((~np.isfinite(out)).sum()):,} non-finite "
            "coordinates; a point with no position cannot be drawn.")
    return out


def provenance(path, declared, n_base, query_k):
    """What `state_info.json` records about a projection: where it came from,
    how it was made, and its digest. Every field is declared by the
    requirements or read off the file -- none of it is measured here."""
    info = {
        "kind": "declared",
        "illustrative": ILLUSTRATIVE,
        "path": os.path.basename(path),
        "sha256": digest(path),
        "bytes": os.path.getsize(path),
        "rows": int(n_base),
        "query_placement": (
            f"the mean of each query's {query_k} true neighbours' positions; "
            "not a projection of the query vector, which was never fitted"),
        "query_placement_k": int(query_k),
    }
    for key in ("method", "params", "seed", "library", "library_version",
                "fitted_on", "note"):
        if declared.get(key) is not None:
            info[key] = declared[key]
    for key in ("method", "seed"):
        if key not in info:
            info[key] = (f"{COULDNT_CHECK}: corpus.sample.projection.{key} "
                         "is not declared in the requirements, so how this "
                         "placement was made is not recorded here")
    return info
