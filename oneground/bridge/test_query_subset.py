"""`oneground.bridge.query_subset`. docs/BRIDGE.md §3.3.

    python oneground/bridge/test_query_subset.py
    pytest oneground/bridge/test_query_subset.py
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.bridge import query_subset as qs  # noqa: E402


def test_the_same_seed_gives_the_same_positions():
    a = qs.select(2000, 30, seed=42)
    b = qs.select(2000, 30, seed=42)
    assert list(a) == list(b)


def test_a_different_seed_gives_a_different_subset():
    a = qs.select(2000, 30, seed=1)
    b = qs.select(2000, 30, seed=2)
    assert list(a) != list(b)


def test_positions_are_sorted():
    """The same reason loaders.subsample sorts the corpus draw: the file
    depends on the seed alone, not on numpy's internal draw order."""
    p = qs.select(2000, 200, seed=7)
    assert list(p) == sorted(p)


def test_a_size_larger_than_available_is_refused():
    with pytest.raises(qs.QuerySubsetError, match="exceeds"):
        qs.select(50, 51, seed=1)


def test_a_size_of_zero_is_refused():
    with pytest.raises(qs.QuerySubsetError, match="> 0"):
        qs.select(50, 0, seed=1)


def test_write_reads_back_what_it_wrote():
    ids = [str(i) for i in range(500)]
    with tempfile.TemporaryDirectory() as tmp:
        path, digest = qs.write(tmp, ids, seed=42, size=30)
        assert os.path.exists(path)
        doc = qs.read(path)
        assert doc["seed"] == 42
        assert doc["size"] == 30
        assert doc["n_available"] == 500
        assert len(doc["positions"]) == 30
        assert doc["positions"] == sorted(doc["positions"])
        assert doc["ids"] == [ids[i] for i in doc["positions"]]
        assert doc["kind"] == "receipt"
        assert "oneground" in doc


def test_writing_twice_with_the_same_seed_refuses_rather_than_overwrites():
    """The same discipline write_prediction holds: a subset is chosen once
    for a given seed and size."""
    ids = [str(i) for i in range(500)]
    with tempfile.TemporaryDirectory() as tmp:
        qs.write(tmp, ids, seed=42, size=30)
        with pytest.raises(qs.QuerySubsetError, match="already exists"):
            qs.write(tmp, ids, seed=42, size=30)


def test_out_dir_separates_the_receipt_from_the_workdir():
    ids = [str(i) for i in range(500)]
    with tempfile.TemporaryDirectory() as tmp:
        workdir = os.path.join(tmp, "run")
        out = os.path.join(tmp, "export")
        os.makedirs(workdir)
        os.makedirs(out)
        path, _digest = qs.write(workdir, ids, seed=1, size=10, out_dir=out)
        assert path == os.path.join(out, qs.NAME)
        assert not os.path.exists(os.path.join(workdir, qs.NAME))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
