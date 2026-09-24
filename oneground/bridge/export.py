"""The VectorDBBench exporter. `docs/BRIDGE.md` §3, §8.

Writes the three files `CustomDataset` reads -- `train.parquet` (or its
zero-padded shards), `test.parquet`, `neighbors.parquet` -- plus a card
recording what the position paper rules cannot be left to a default:
`metric_type`, `with_gt`, `use_shuffled`, `with_scalar_labels`,
`file_count`, and the query subset's own seed and size.

**§3.3 is a prerequisite, not a companion.** `comparability.
rows_may_share_a_table` cannot admit a row from this export to a table
with anything else until the query subset it used is itself a receipt
(`oneground.bridge.query_subset`) -- so `export()` always writes one; there
is no path through this module that skips it.

Nothing here vendors, runs or imports VectorDBBench. The three files and
the card are declared, the way an extracted-text corpus is declared
(`docs/CHUNKING.md`'s rule, restated in `docs/BRIDGE.md` §5): oneground
writes what a tool needs, and the user runs the tool.
"""

import json
import os

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .. import intake
from ..provenance import invocation
from ..receipts import (producing_version, public_paths_in, sha256_file,
                        write_json_stable)
from ..sample import loaders
from ..simulate import _sample_indices
from ..truth import exact_knn
from . import query_subset as qs

#: `docs/BRIDGE.md` §3.1 -- every name `CustomDataset`/`CustomDatasetConfig`
#: default to, adopted rather than renamed. Kept as one place to read them
#: from, not because any of them is expected to change.
TRAIN_ID_COL = "id"
TRAIN_VEC_COL = "emb"
TEST_ID_COL = "id"
TEST_VEC_COL = "emb"
GT_ID_COL = "id"
GT_NEIGHBORS_COL = "neighbors_id"

CARD_NAME = "vdbbench_card.json"


class ExportError(ValueError):
    """The export could not be produced, or would have produced files
    VectorDBBench cannot honestly be pointed at."""


def _shard_names(file_count):
    """§3.2's naming ruling: a single file is named plainly; more than one
    is zero-padded two digits, `train-00-of-N.parquet` -- `str(i).rjust(2,
    "0")` in VectorDBBench's own source, not `train-[i]-of-[n]` as an
    earlier draft of the position paper had it."""
    if file_count == 1:
        return ["train.parquet"]
    return [f"train-{str(i).rjust(2, '0')}-of-{file_count}.parquet"
           for i in range(file_count)]


def _list_column(matrix, arrow_type):
    """A pyarrow list column built from a 2-D array's own bytes.

    `pa.array([row.tolist() for row in matrix])` round-trips every value
    through a Python `float` first -- float64 -- and pyarrow then narrows
    it back to `arrow_type`, which is not always the identity: a float32
    value can print differently after that detour than the bits it left
    with. Building the list array from the flattened array directly keeps
    the original bits, which is what "the round trip preserves the
    vectors... exactly" (`docs/BRIDGE.md` §8) means literally.
    """
    n, width = matrix.shape
    flat = pa.array(np.ascontiguousarray(matrix).reshape(-1), type=arrow_type)
    offsets = pa.array(np.arange(0, (n + 1) * width, width, dtype=np.int64),
                       type=pa.int32())
    return pa.ListArray.from_arrays(offsets, flat)


def _write_vector_table(path, ids, vectors, id_col, vec_col):
    tbl = pa.table({
        id_col: pa.array(np.asarray(ids), type=pa.int64()),
        vec_col: _list_column(np.asarray(vectors, dtype=np.float32),
                              pa.float32()),
    })
    pq.write_table(tbl, path)


def _write_neighbors_table(path, ids, neighbor_ids):
    tbl = pa.table({
        GT_ID_COL: pa.array(np.asarray(ids), type=pa.int64()),
        GT_NEIGHBORS_COL: _list_column(
            np.asarray(neighbor_ids, dtype=np.int64()), pa.int64()),
    })
    pq.write_table(tbl, path)


def export(requirements_path, out_dir, query_subset_seed, query_subset_size,
          k=100, file_count=1, workdir=None, log_fn=print):
    """Write `train*.parquet`, `test.parquet`, `neighbors.parquet` and the
    card. Returns a dict of everything written, with each file's sha256.

    `workdir` is the `characterize` run whose `sample_ids.json` and
    `queries_ids.json` this reads -- defaults to `req.workdir`. `out_dir`
    is where the export's own files land; it may be `workdir` itself or
    somewhere else, the same split `write_prediction` makes, because an
    export is not the only thing a workdir might hold.

    Neither the corpus vectors file nor the queries file is copied wholesale
    -- both are re-read from the paths the requirements file names, and the
    sample is reconstructed from `sample_ids.json` exactly as `simulate`
    reconstructs it (`oneground.simulate._sample_indices`), because
    `characterize` itself never writes the vectors it measured back to disk.
    """
    req = intake.load(requirements_path)
    wd = workdir or req.resolve(req.workdir)
    if not os.path.isdir(wd):
        raise ExportError(f"{wd}: not a run directory -- run characterize "
                          "on this requirements file first")
    sample_ids_path = os.path.join(wd, "sample_ids.json")
    queries_ids_path = os.path.join(wd, "queries_ids.json")
    for p in (sample_ids_path, queries_ids_path):
        if not os.path.exists(p):
            raise ExportError(
                f"{p} is missing. The export reads what characterize "
                "measured, not what it might measure -- run characterize "
                "on this requirements file first.")

    if file_count < 1:
        raise ExportError(f"file_count must be >= 1, got {file_count}")

    log_fn(f"export: reading the corpus sample from {req.vectors['path']!r}")
    full_vectors = loaders.load_vectors(req.resolve(req.vectors["path"]))
    idx = _sample_indices(wd, len(full_vectors))
    base = full_vectors[idx]
    if not req.vectors.get("normalized", False):
        base = loaders.normalize_rows(base)

    log_fn(f"export: reading the query set from {req.queries['path']!r}")
    full_queries = loaders.load_vectors(req.resolve(req.queries["path"]))
    full_queries = loaders.normalize_rows(full_queries)
    with open(queries_ids_path, encoding="utf-8") as f:
        query_ids = json.load(f)
    if len(query_ids) != len(full_queries):
        raise ExportError(
            f"{queries_ids_path} names {len(query_ids)} queries but "
            f"{req.queries['path']} holds {len(full_queries)} -- the "
            "receipt and the file it describes have drifted apart")

    log_fn(f"export: query subset -- seed {query_subset_seed}, "
          f"size {query_subset_size}")
    subset_path, subset_sha = qs.write(
        wd, query_ids, query_subset_seed, query_subset_size, out_dir=out_dir)
    subset = qs.read(subset_path)
    subset_positions = np.asarray(subset["positions"], dtype=np.int64)
    test_vectors = full_queries[subset_positions]

    # docs/BRIDGE.md §3.1's one conversion: queries_ids.json holds strings
    # (characterize writes str(q) unconditionally, task 007); test.parquet.id
    # is declared int. They agree on meaning -- each entry still names the
    # same query -- not on type, so the cast is made explicitly rather than
    # assumed. Where a query's id is not numeric (an arbitrary string id
    # from a .jsonl source), there is nothing honest to cast it to, and the
    # export refuses naming the id rather than inventing a position that
    # would silently stop meaning what queries_ids.json says it means.
    try:
        test_ids = np.asarray([int(subset["ids"][i]) for i in
                               range(len(subset["ids"]))], dtype=np.int64)
    except ValueError as e:
        raise ExportError(
            f"{queries_ids_path} names at least one query id that is not "
            f"a plain integer ({e}); test.parquet.id must be int and this "
            "exporter does not invent one for an id it cannot cast -- "
            "re-run characterize with queries drawn from a source whose "
            "ids are positions (.npy/.parquet), or extend this exporter's "
            "conversion rule rather than guess here.") from None

    log_fn(f"export: exact k-NN, k={k}, {len(base):,} base x "
          f"{len(test_vectors):,} queries")
    neighbors = exact_knn(base, test_vectors, k)

    out = out_dir or wd
    os.makedirs(out, exist_ok=True)

    train_names = _shard_names(file_count)
    boundaries = np.linspace(0, len(base), file_count + 1, dtype=np.int64)
    written = {}
    for i, name in enumerate(train_names):
        lo, hi = int(boundaries[i]), int(boundaries[i + 1])
        path = os.path.join(out, name)
        _write_vector_table(path, np.arange(lo, hi), base[lo:hi],
                            TRAIN_ID_COL, TRAIN_VEC_COL)
        written[name] = sha256_file(path)
    log_fn(f"export: wrote {len(train_names)} train file(s), "
          f"{len(base):,} vectors total")

    test_path = os.path.join(out, "test.parquet")
    _write_vector_table(test_path, test_ids, test_vectors,
                        TEST_ID_COL, TEST_VEC_COL)
    written["test.parquet"] = sha256_file(test_path)

    neighbors_path = os.path.join(out, "neighbors.parquet")
    _write_neighbors_table(neighbors_path, test_ids, neighbors)
    written["neighbors.parquet"] = sha256_file(neighbors_path)
    log_fn(f"export: wrote test.parquet ({len(test_vectors):,} queries) "
          f"and neighbors.parquet (k={k})")

    card = {
        "kind": "declared",
        "oneground": producing_version(),
        "invocation": invocation(),
        "requirements_file": public_paths_in(
            {"path": requirements_path,
             "sha256": sha256_file(requirements_path)}),
        # docs/BRIDGE.md §3.2 -- five parameters a default would get wrong,
        # set explicitly rather than left for CustomDatasetConfig's own
        # defaults (which disagree with each other: L2 in the config
        # object, COSINE on the CLI) or VectorDBBench's --skip flags to
        # decide silently.
        "metric_type": "IP",
        "with_gt": True,
        "use_shuffled": False,
        "with_scalar_labels": False,
        "file_count": file_count,
        "train_files": train_names,
        "test_file": "test.parquet",
        "gt_file": "neighbors.parquet",
        "columns": {"train_id_name": TRAIN_ID_COL,
                    "train_col_name": TRAIN_VEC_COL,
                    "test_col_name": TEST_VEC_COL,
                    "gt_col_name": GT_NEIGHBORS_COL},
        "ground_truth_k": k,
        "n_base": len(base),
        "n_test": len(test_vectors),
        "dimension": int(base.shape[1]),
        "query_subset": public_paths_in(
            {"path": qs.NAME, "sha256": subset_sha,
             "seed": query_subset_seed, "size": query_subset_size}),
        "files": written,
    }
    card_path = os.path.join(out, CARD_NAME)
    write_json_stable(card_path, card)
    written[CARD_NAME] = sha256_file(card_path)
    log_fn(f"export: wrote {CARD_NAME}")

    return {"out_dir": out, "train_files": train_names,
           "test_file": "test.parquet", "gt_file": "neighbors.parquet",
           "card": card_path, "files": written}
