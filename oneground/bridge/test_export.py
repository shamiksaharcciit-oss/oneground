"""`oneground.bridge.export`. docs/BRIDGE.md §3, §8.

**Synthetic throughout.** The property under test is the round trip: write
the three files, load them back, and the vectors and the ground truth
survive exactly -- plus the two rulings a silent exporter could get wrong
without any error appearing: the id space is positions, not source ids,
and the zero-padded shard naming.

    python oneground/bridge/test_export.py
    pytest oneground/bridge/test_export.py
"""

import json
import os
import sys
import tempfile

import numpy as np
import pyarrow.parquet as pq
import pytest
import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import characterize                         # noqa: E402
from oneground.bridge import export as bexport             # noqa: E402
from oneground.bridge import query_subset as qs            # noqa: E402
from oneground.sample.loaders import normalize_rows        # noqa: E402
from oneground.truth import exact_knn                       # noqa: E402

SEED = 20260910


def _corpus(tmp, n=500, dim=16, n_queries=80, seed=SEED):
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(3, dim))
    x = np.vstack([c + rng.normal(0, 0.15, size=(n // 3 + 1, dim))
                  for c in centres])[:n].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = rng.normal(0, 1, size=(n_queries, dim)).astype(np.float32)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    vec_p = os.path.join(tmp, "vectors.npy")
    q_p = os.path.join(tmp, "queries.npy")
    np.save(vec_p, x)
    np.save(q_p, q)
    return vec_p, q_p, x, q


def _write_req(tmp, vec_p, q_p, workdir, target_sample_size=None, seed=SEED):
    sample = {"kind": "receipt", "vectors": {"path": vec_p, "normalized": True},
             "queries": {"path": q_p, "count_min": 10}}
    if target_sample_size:
        sample["target_sample_size"] = target_sample_size
    req_path = os.path.join(tmp, "r.yaml")
    with open(req_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump({"oneground": 1,
                        "run": {"name": "synthetic", "seed": seed,
                                "workdir": workdir},
                        "corpus": {"sample": sample}}, f)
    return req_path


def _read_train(out_dir, train_files):
    """Concatenated (ids, vectors) across every shard, in file order --
    the same order a caller reassembling the dataset would read them in."""
    ids, vecs = [], []
    for name in train_files:
        t = pq.read_table(os.path.join(out_dir, name))
        ids.extend(t.column("id").to_pylist())
        vecs.extend(t.column("emb").to_pylist())
    return np.asarray(ids), np.asarray(vecs, dtype=np.float32)


# --------------------------------------------------------- the round trip
def test_the_three_files_round_trip_the_vectors_and_the_ground_truth():
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p, x, q = _corpus(tmp)
        workdir = os.path.join(tmp, "out")
        req_path = _write_req(tmp, vec_p, q_p, workdir)
        characterize.run(req_path, log_fn=lambda m: None)

        result = bexport.export(req_path, out_dir=None,
                                query_subset_seed=1, query_subset_size=20,
                                k=10)
        out = result["out_dir"]

        train_ids, train_vecs = _read_train(out, result["train_files"])
        assert list(train_ids) == list(range(len(x)))
        assert np.array_equal(train_vecs, x), "train vectors are not bit-exact"

        test_t = pq.read_table(os.path.join(out, "test.parquet"))
        test_ids = np.asarray(test_t.column("id").to_pylist())
        test_vecs = np.asarray(test_t.column("emb").to_pylist(),
                               dtype=np.float32)
        assert len(test_ids) == 20
        # export() re-normalizes queries unconditionally, the same
        # convention characterize.py itself uses -- so the comparison
        # basis is normalized once here too, not the fixture's own
        # already-normalized copy compared bit-for-bit against a second
        # normalization of the same vectors.
        assert np.array_equal(test_vecs, normalize_rows(q)[test_ids]), (
            "test vectors do not match the queries at their own declared "
            "ids -- the id space and the vectors have come apart")

        gt_t = pq.read_table(os.path.join(out, "neighbors.parquet"))
        assert gt_t.column("id").to_pylist() == test_ids.tolist(), (
            "neighbors.parquet.id must match test.parquet.id row for row")
        got_neighbors = np.asarray(gt_t.column("neighbors_id").to_pylist())

        expected = exact_knn(x, test_vecs, 10)
        assert np.array_equal(got_neighbors, expected), (
            "the exported ground truth does not match an independent "
            "recomputation over the same base and query vectors")


def test_neighbors_id_is_a_valid_position_into_every_train_shard():
    """Every neighbours_id is checkable against the file it names -- not
    just numerically in range, but pointing at the actual nearest vector."""
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p, x, q = _corpus(tmp, n=260)
        workdir = os.path.join(tmp, "out")
        req_path = _write_req(tmp, vec_p, q_p, workdir)
        characterize.run(req_path, log_fn=lambda m: None)
        result = bexport.export(req_path, out_dir=None, query_subset_seed=3,
                                query_subset_size=15, k=5, file_count=4)
        out = result["out_dir"]
        train_ids, train_vecs = _read_train(out, result["train_files"])
        assert list(train_ids) == list(range(260))

        gt_t = pq.read_table(os.path.join(out, "neighbors.parquet"))
        test_t = pq.read_table(os.path.join(out, "test.parquet"))
        test_vecs = np.asarray(test_t.column("emb").to_pylist(),
                               dtype=np.float32)
        neighbor_rows = gt_t.column("neighbors_id").to_pylist()
        for qi, row in enumerate(neighbor_rows):
            for nid in row:
                assert 0 <= nid < len(train_vecs)
            # The first-ranked neighbour really is the closest vector by
            # inner product -- not merely an in-range integer.
            sims = train_vecs @ test_vecs[qi]
            assert row[0] == int(np.argmax(sims)), (
                "the top neighbour is not the actual nearest vector in "
                "the exported train file")


# ------------------------------------------------- the id-space ruling
def test_ids_are_positions_in_the_sample_not_source_ids():
    """docs/BRIDGE.md's own trap: on a subsampled run, sample_ids.json
    diverges from positions completely. An exporter that used sample_ids
    as train.parquet.id would pass on a full-corpus run and be silently
    wrong here -- this is the run that catches it."""
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p, x, q = _corpus(tmp, n=2000, dim=8, n_queries=200)
        workdir = os.path.join(tmp, "out")
        req_path = _write_req(tmp, vec_p, q_p, workdir,
                              target_sample_size=300)
        characterize.run(req_path, log_fn=lambda m: None)

        with open(os.path.join(workdir, "sample_ids.json"),
                 encoding="utf-8") as f:
            sample_ids = json.load(f)
        assert len(sample_ids) == 300
        # The trap only bites if the source ids actually differ from
        # positions -- assert the fixture exercises it rather than hoping.
        assert sample_ids != list(range(300)), (
            "the subsample happened to equal positions; this test proves "
            "nothing until the fixture draws a genuinely different subset")

        result = bexport.export(req_path, out_dir=None, query_subset_seed=5,
                                query_subset_size=20, k=8)
        out = result["out_dir"]
        train_ids, train_vecs = _read_train(out, result["train_files"])

        # The written ids are 0..299 -- positions in the 300-row sample --
        # not sample_ids's source-file row numbers.
        assert list(train_ids) == list(range(300))
        assert train_ids.tolist() != sample_ids

        # And they are the RIGHT positions: train row i is x's row
        # sample_ids[i], the vector characterize actually measured at
        # sample position i.
        expected_sample = x[np.asarray(sample_ids)]
        assert np.array_equal(train_vecs, expected_sample)

        gt_t = pq.read_table(os.path.join(out, "neighbors.parquet"))
        for row in gt_t.column("neighbors_id").to_pylist():
            for nid in row:
                assert 0 <= nid < 300, (
                    f"neighbours_id {nid} is not a position in the "
                    "300-row sample -- it looks like a source id leaked "
                    "through instead")


# --------------------------------------------------------- shard naming
def test_a_single_file_is_named_plainly():
    assert bexport._shard_names(1) == ["train.parquet"]


def test_shards_are_zero_padded_two_digits():
    names = bexport._shard_names(12)
    assert names[0] == "train-00-of-12.parquet"
    assert names[9] == "train-09-of-12.parquet"
    assert names[11] == "train-11-of-12.parquet"
    # Not the earlier draft's train-[i]-of-[n] -- docs/BRIDGE.md §3.2.
    assert "[" not in "".join(names)


def test_shard_boundaries_cover_every_row_exactly_once():
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p, x, q = _corpus(tmp, n=263)
        workdir = os.path.join(tmp, "out")
        req_path = _write_req(tmp, vec_p, q_p, workdir)
        characterize.run(req_path, log_fn=lambda m: None)
        result = bexport.export(req_path, out_dir=None, query_subset_seed=2,
                                query_subset_size=10, k=3, file_count=5)
        train_ids, _ = _read_train(result["out_dir"], result["train_files"])
        assert sorted(train_ids.tolist()) == list(range(263))


# ---------------------------------------------------------------- the card
def test_the_card_states_the_five_parameters_explicitly():
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p, x, q = _corpus(tmp)
        workdir = os.path.join(tmp, "out")
        req_path = _write_req(tmp, vec_p, q_p, workdir)
        characterize.run(req_path, log_fn=lambda m: None)
        result = bexport.export(req_path, out_dir=None, query_subset_seed=9,
                                query_subset_size=10, k=4, file_count=2)
        with open(result["card"], encoding="utf-8") as f:
            card = json.load(f)
        assert card["metric_type"] == "IP"
        assert card["with_gt"] is True
        assert card["use_shuffled"] is False
        assert card["with_scalar_labels"] is False
        assert card["file_count"] == 2
        assert card["query_subset"]["seed"] == 9
        assert card["query_subset"]["size"] == 10


# ----------------------------------------------- the query-subset seam
def test_the_export_writes_the_query_subset_receipt():
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p, x, q = _corpus(tmp)
        workdir = os.path.join(tmp, "out")
        req_path = _write_req(tmp, vec_p, q_p, workdir)
        characterize.run(req_path, log_fn=lambda m: None)
        result = bexport.export(req_path, out_dir=None, query_subset_seed=4,
                                query_subset_size=12, k=3)
        subset_path = os.path.join(result["out_dir"], qs.NAME)
        assert os.path.exists(subset_path)
        doc = qs.read(subset_path)
        assert doc["seed"] == 4 and doc["size"] == 12


def test_exporting_twice_with_the_same_seed_refuses_the_second_time():
    """The subset receipt's own discipline, visible through export()."""
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p, x, q = _corpus(tmp)
        workdir = os.path.join(tmp, "out")
        req_path = _write_req(tmp, vec_p, q_p, workdir)
        characterize.run(req_path, log_fn=lambda m: None)
        bexport.export(req_path, out_dir=None, query_subset_seed=1,
                       query_subset_size=10, k=3)
        with pytest.raises(qs.QuerySubsetError, match="already exists"):
            bexport.export(req_path, out_dir=None, query_subset_seed=1,
                           query_subset_size=10, k=3)


# --------------------------------------------------------------- refusals
def test_exporting_without_characterize_having_run_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p, x, q = _corpus(tmp)
        workdir = os.path.join(tmp, "out")
        req_path = _write_req(tmp, vec_p, q_p, workdir)
        with pytest.raises(bexport.ExportError, match="characterize"):
            bexport.export(req_path, out_dir=None, query_subset_seed=1,
                           query_subset_size=5, k=3)


def test_a_query_subset_larger_than_available_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p, x, q = _corpus(tmp, n_queries=20)
        workdir = os.path.join(tmp, "out")
        req_path = _write_req(tmp, vec_p, q_p, workdir)
        characterize.run(req_path, log_fn=lambda m: None)
        with pytest.raises(qs.QuerySubsetError, match="exceeds"):
            bexport.export(req_path, out_dir=None, query_subset_seed=1,
                           query_subset_size=21, k=3)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
