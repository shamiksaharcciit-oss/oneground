"""Loading a user's own vectors, text, ids and metadata.

The product path. Everything here answers one question: what exactly was
measured? A characterization over a subsample is only a receipt if the run
records which rows it drew, so `subsample` returns indices and the caller
writes them out.

Nothing in this module sends anything anywhere. Files are read from local
paths named in the requirements file, and that is the whole of its I/O.
"""

import json
import os

import numpy as np


class LoadError(RuntimeError):
    """An input file is missing, unreadable, or not the shape it claims."""


def _require(path, what):
    if not path:
        raise LoadError(f"{what}: no path given")
    if not os.path.exists(path):
        raise LoadError(f"{what}: file not found: {path}")
    return path


def load_vectors(path, what="vectors"):
    """Load an (n, dim) float32 array from .npy or .parquet.

    Returns the array as float32 and C-contiguous, because faiss requires both
    and a silent copy later is a memory surprise on a large corpus.
    """
    _require(path, what)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".npy":
        a = np.load(path)
    elif ext in (".parquet", ".pq"):
        try:
            import pyarrow.parquet as pq
        except ImportError:                       # pragma: no cover
            raise LoadError(
                f"{what}: reading .parquet needs pyarrow "
                "(pip install 'oneground[view]')") from None
        tbl = pq.read_table(path)
        cols = [c for c in tbl.column_names]
        if len(cols) == 1:
            a = np.stack(tbl.column(cols[0]).to_numpy(zero_copy_only=False))
        else:
            a = np.column_stack([tbl.column(c).to_numpy(zero_copy_only=False)
                                 for c in cols])
    else:
        raise LoadError(
            f"{what}: unsupported extension {ext!r}; expected .npy or .parquet")

    a = np.ascontiguousarray(np.asarray(a, dtype=np.float32))
    if a.ndim != 2:
        raise LoadError(f"{what}: expected a 2-D (n, dim) array, got shape "
                        f"{a.shape} from {path}")
    if a.shape[0] == 0:
        raise LoadError(f"{what}: {path} holds no rows")
    return a


def normalize_rows(a):
    """L2-normalize in place-ish. Zero rows are left as zeros rather than
    producing NaN, and the caller is expected to notice them."""
    n = np.linalg.norm(a, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (a / n).astype(np.float32)


def load_ids(path, n_expected, what="ids"):
    """Optional id list, one per vector row. JSON list or newline text."""
    if not path:
        return None
    _require(path, what)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, encoding="utf-8") as f:
            ids = json.load(f)
    else:
        with open(path, encoding="utf-8") as f:
            ids = [ln.rstrip("\n") for ln in f if ln.strip()]
    if len(ids) != n_expected:
        raise LoadError(f"{what}: {path} has {len(ids)} ids for "
                        f"{n_expected} vectors")
    return [str(i) for i in ids]


def load_text(path, text_field="text", id_field="id", what="text"):
    """One JSON object per line. Returns (texts, ids)."""
    _require(path, what)
    texts, ids = [], []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError as e:
                raise LoadError(f"{what}: {path}:{lineno} is not JSON: {e}") from None
            if text_field not in rec:
                raise LoadError(
                    f"{what}: {path}:{lineno} has no field {text_field!r}; "
                    f"set corpus.sample.text.text_field to one of "
                    f"{sorted(rec)[:8]}")
            texts.append(rec[text_field])
            ids.append(str(rec.get(id_field, lineno - 1)))
    if not texts:
        raise LoadError(f"{what}: {path} holds no records")
    return texts, ids


def load_metadata(path, n_expected, what="metadata"):
    """Optional parquet sidecar, same order as the vectors.

    Returned as a dict of column name -> list, which is all the measures need
    and avoids making pandas a dependency.
    """
    if not path:
        return None
    _require(path, what)
    try:
        import pyarrow.parquet as pq
    except ImportError:                           # pragma: no cover
        raise LoadError(f"{what}: reading .parquet needs pyarrow "
                        "(pip install 'oneground[view]')") from None
    tbl = pq.read_table(path)
    if tbl.num_rows != n_expected:
        raise LoadError(f"{what}: {path} has {tbl.num_rows} rows for "
                        f"{n_expected} vectors; they must line up row for row")
    return {name: tbl.column(name).to_pylist() for name in tbl.column_names}


def load_queries(cfg, embed_fn=None, what="queries"):
    """Queries as vectors, or as text to be embedded.

    `cfg` is the requirements file's `corpus.sample.queries` block. Text
    queries need `embed_fn`; the caller supplies it so this module never
    imports torch.
    """
    path = cfg.get("path")
    _require(path, what)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".npy", ".parquet", ".pq"):
        return load_vectors(path, what), None

    # .jsonl: either {id, vector} or {id, text}
    rows, ids = [], []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rows.append(rec)
            ids.append(str(rec.get("id", lineno - 1)))
    if not rows:
        raise LoadError(f"{what}: {path} holds no records")

    if "vector" in rows[0]:
        a = np.ascontiguousarray(
            np.asarray([r["vector"] for r in rows], dtype=np.float32))
        return a, ids

    field = cfg.get("text_field", "text")
    if field not in rows[0]:
        raise LoadError(
            f"{what}: {path} records have neither 'vector' nor {field!r}; "
            f"fields present: {sorted(rows[0])[:8]}")
    if embed_fn is None:
        raise LoadError(
            f"{what}: {path} holds text, which needs a model. Set "
            "corpus.sample.text.model (the queries are embedded with the same "
            "model as the corpus).")
    return embed_fn([r[field] for r in rows]), ids


def subsample(n, target, seed):
    """Indices of a seeded draw of `target` rows out of `n`, sorted.

    Sorted so the drawn subset is a stable, readable slice, and so two runs
    with the same seed produce the same file rather than the same set in a
    different order.
    """
    if not target or target >= n:
        return np.arange(n)
    rng = np.random.default_rng(seed)
    idx = rng.choice(n, size=int(target), replace=False)
    idx.sort()
    return idx
