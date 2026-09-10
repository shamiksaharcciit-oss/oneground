"""Contract tests for oneground/fixture_verify.py.

These run entirely on synthetic directories built in a temp dir — they never
touch a real fixture, and passing here says nothing about any corpus. What
they pin down is the verifier's contract: the three outcomes stay distinct,
couldnt_check is never rounded up to verified or down to contradicted, the
receipt/declared split is applied to the right files, and the exit code means
what the docstring says it means.

No test-runner dependency: run it directly.

    python oneground/fixture/test_verify.py
"""

import hashlib
import json
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.fixture import verify as fv  # noqa: E402


def _write(path, data):
    with open(path, "wb") as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()


def _fixture(tmp, entries, extra_files=()):
    """entries: [(name, bytes_or_None, digest_override_or_None)]"""
    d = os.path.join(tmp, "fx")
    os.makedirs(d, exist_ok=True)
    lines = []
    for name, data, override in entries:
        digest = override
        if data is not None:
            real = _write(os.path.join(d, name), data)
            digest = override or real
        lines.append(f"{digest}  {name}")
    for name, data in extra_files:
        _write(os.path.join(d, name), data)
    with open(os.path.join(d, fv.MANIFEST_NAME), "w", encoding="utf-8", newline="\n") as m:
        m.write("\n".join(lines) + "\n")
    return d


def test_kind_split_synthetic():
    # declared: recorded, not re-derivable. build_info.json varies by build;
    # projection.npy is a seeded UMAP, not guaranteed bit-identical across
    # BLAS builds, and the spec marks it illustrative.
    assert fv.kind_of("build_info.json") == fv.DECLARED
    assert fv.kind_of("projection.npy") == fv.DECLARED
    for name in ("characterization.json", "vectors.npy", "ground_truth.npy",
                 "queries.npy", "query_ids.json", "sample.jsonl.zst"):
        assert fv.kind_of(name) == fv.RECEIPT, name


def test_ground_view_parquets_are_declared_synthetic():
    """ground_view_*.parquet are derived for drawing, so declared — and, like
    every declared file, still digest-checked."""
    for name in ("ground_view_base.parquet", "ground_view_queries.parquet",
                 "ground_view_centroids.parquet"):
        assert fv.kind_of(name) == fv.DECLARED, name

    # the glob must not swallow neighbours that are not the exported tables
    for name in ("ground_view.txt", "ground_view_base.npy", "vectors.parquet"):
        assert fv.kind_of(name) == fv.RECEIPT, name

    with tempfile.TemporaryDirectory() as tmp:
        d = _fixture(tmp, [
            ("ground_view_base.parquet", b"parquet bytes", None),
            ("ground_view_queries.parquet", b"tampered", "00" * 32),
        ])
        results, _ = fv.verify_digests(d)
        by = {n: (k, o) for n, k, o, _ in results}
        assert by["ground_view_base.parquet"] == (fv.DECLARED, fv.VERIFIED)
        assert by["ground_view_queries.parquet"] == (fv.DECLARED, fv.CONTRADICTED)


def test_projection_is_declared_but_still_digest_checked_synthetic():
    """declared exempts projection.npy from reproduction, never from its digest."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixture(tmp, [("projection.npy", b"not the bytes the manifest names", "00" * 32)])
        results, _ = fv.verify_digests(d)
        name, kind, outcome, _ = results[0]
        assert (name, kind, outcome) == ("projection.npy", fv.DECLARED, fv.CONTRADICTED)


def test_three_outcomes_stay_distinct_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixture(tmp, [
            ("characterization.json", b'{"a":1}\n', None),          # matches
            ("build_info.json", b'{"built_at":"x"}\n', None),       # matches, declared
            ("vectors.npy", b"tampered", "00" * 32),                # present, wrong digest
            ("ground_truth.npy", None, "11" * 32),                  # listed, absent
        ])
        results, unlisted = fv.verify_digests(d)
        by = {name: (kind, outcome) for name, kind, outcome, _ in results}

        assert by["characterization.json"] == (fv.RECEIPT, fv.VERIFIED)
        assert by["build_info.json"] == (fv.DECLARED, fv.VERIFIED)
        assert by["vectors.npy"] == (fv.RECEIPT, fv.CONTRADICTED)
        # absent is couldnt_check: not verified, and not contradicted either
        assert by["ground_truth.npy"] == (fv.RECEIPT, fv.COULDNT_CHECK)
        assert unlisted == []


def test_declared_file_is_still_digest_checked_synthetic():
    """declared exempts a file from value reproduction, never from its digest."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixture(tmp, [("build_info.json", b"changed after the manifest", "00" * 32)])
        results, _ = fv.verify_digests(d)
        name, kind, outcome, _ = results[0]
        assert (kind, outcome) == (fv.DECLARED, fv.CONTRADICTED)


def test_verifies_with_and_without_projection_synthetic():
    """The verifier checks what the MANIFEST lists, so a fixture whose
    projection failed verifies exactly as well as one where it succeeded."""
    class Args:
        fixtures_dir = None
        id = "fx"

    receipts = [("characterization.json", b"{}\n", None),
                ("build_info.json", b'{"projection":"failed"}\n', None)]

    # listed and present (projection succeeded)
    with tempfile.TemporaryDirectory() as tmp:
        _fixture(tmp, receipts + [("projection.npy", b"umap bytes", None)])
        Args.fixtures_dir = tmp
        assert fv.cmd_verify(Args) == 0

    # not listed at all (projection failed; the manifest never mentioned it)
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixture(tmp, receipts)
        results, unlisted = fv.verify_digests(d)
        assert [r[2] for r in results] == [fv.VERIFIED, fv.VERIFIED]
        assert unlisted == []
        Args.fixtures_dir = tmp
        assert fv.cmd_verify(Args) == 0

    # a stale projection.npy on disk that the manifest does not list is
    # reported as unlisted, and does not fail verification
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixture(tmp, receipts, extra_files=[("projection.npy", b"stale")])
        _, unlisted = fv.verify_digests(d)
        assert unlisted == ["projection.npy"]
        Args.fixtures_dir = tmp
        assert fv.cmd_verify(Args) == 0


def test_unlisted_files_are_reported_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixture(tmp, [("characterization.json", b"{}\n", None)],
                     extra_files=[("stray.npy", b"x")])
        _, unlisted = fv.verify_digests(d)
        assert unlisted == ["stray.npy"]


def test_malformed_manifest_raises_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "fx")
        os.makedirs(d)
        with open(os.path.join(d, fv.MANIFEST_NAME), "w", encoding="utf-8") as m:
            m.write("not-a-digest  file.npy\n")
        try:
            fv.read_manifest(os.path.join(d, fv.MANIFEST_NAME))
        except ValueError:
            return
        raise AssertionError("malformed manifest line should raise ValueError")


def test_exit_codes_synthetic():
    """0 unless something is contradicted; absence alone is not a failure."""
    class Args:
        fixtures_dir = None
        id = "fx"

    with tempfile.TemporaryDirectory() as tmp:
        _fixture(tmp, [("characterization.json", b"{}\n", None)])
        Args.fixtures_dir = tmp
        assert fv.cmd_verify(Args) == 0

    with tempfile.TemporaryDirectory() as tmp:
        _fixture(tmp, [("characterization.json", b"{}\n", None),
                       ("ground_truth.npy", None, "11" * 32)])
        Args.fixtures_dir = tmp
        assert fv.cmd_verify(Args) == 0          # listed but absent -> still 0

    with tempfile.TemporaryDirectory() as tmp:
        _fixture(tmp, [("vectors.npy", b"tampered", "00" * 32),
                       ("ground_truth.npy", None, "11" * 32)])
        Args.fixtures_dir = tmp
        # a contradiction outranks a couldnt_check
        assert fv.cmd_verify(Args) == 1


def test_strict_flag_synthetic():
    """--strict turns absence into exit 2; it must not change the report.

    Default is the clone-friendly reading (absence is not a failure); --strict
    is for a caller that has the whole fixture and wants it accounted for.
    A contradiction still outranks both.
    """
    class Args:
        fixtures_dir = None
        id = "fx"
        strict = False

    complete = [("characterization.json", b"{}\n", None),
                ("build_info.json", b"{}\n", None)]
    with_absent = complete + [("vectors.npy", None, "11" * 32)]

    # nothing absent: --strict changes nothing
    with tempfile.TemporaryDirectory() as tmp:
        _fixture(tmp, complete)
        Args.fixtures_dir = tmp
        Args.strict = False
        assert fv.cmd_verify(Args) == 0
        Args.strict = True
        assert fv.cmd_verify(Args) == 0

    # one listed file absent: 0 by default, 2 under --strict
    with tempfile.TemporaryDirectory() as tmp:
        d = _fixture(tmp, with_absent)
        Args.fixtures_dir = tmp
        Args.strict = False
        assert fv.cmd_verify(Args) == 0
        Args.strict = True
        assert fv.cmd_verify(Args) == 2
        # the report is identical either way: absence is still couldnt_check,
        # still not contradicted, and the present files still verify
        results, _ = fv.verify_digests(d)
        outcome = {name: o for name, _, o, _ in results}
        assert outcome["vectors.npy"] == fv.COULDNT_CHECK
        assert outcome["characterization.json"] == fv.VERIFIED

    # a contradiction outranks --strict
    with tempfile.TemporaryDirectory() as tmp:
        _fixture(tmp, [("vectors.npy", b"tampered", "00" * 32),
                       ("queries.npy", None, "11" * 32)])
        Args.fixtures_dir = tmp
        Args.strict = True
        assert fv.cmd_verify(Args) == 1


def test_absent_large_artifacts_are_couldnt_check_not_contradicted_synthetic():
    """The view from a fresh clone: the release-asset artifacts are missing.

    This is what a contributor sees who has the repo but not vectors.npy,
    queries.npy or sample.jsonl.zst. Their fixture is incomplete, not broken:
    the absent files must be couldnt_check (never contradicted, never rounded
    up to verified), the present ones verified, and the exit code 0.
    """
    class Args:
        fixtures_dir = None
        id = "fx"

    absent = ["sample.jsonl.zst", "vectors.npy", "queries.npy"]
    present = ["query_ids.json", "ground_truth.npy", "characterization.json",
               "build_info.json", "projection.npy"]

    with tempfile.TemporaryDirectory() as tmp:
        entries = [(n, None, f"{i:02x}" * 32) for i, n in enumerate(absent)]
        entries += [(n, f"contents of {n}".encode(), None) for n in present]
        d = _fixture(tmp, entries)

        results, unlisted = fv.verify_digests(d)
        outcome = {name: o for name, _, o, _ in results}

        for n in absent:
            assert outcome[n] == fv.COULDNT_CHECK, n
            assert outcome[n] != fv.CONTRADICTED, n
        for n in present:
            assert outcome[n] == fv.VERIFIED, n
        assert unlisted == []

        Args.fixtures_dir = tmp
        assert fv.cmd_verify(Args) == 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\n{len(tests)} passed")


# ------------------------------- value reproduction (task 013)
def _tiny_fixture(tmp, fid="tiny", published=None, tolerance=0.02,
                  with_asset=True):
    """A fixture whose published values are whatever this build computes.

    The point of these tests is the comparison machinery -- which values are
    checked, against whose tolerance, and what makes an outcome
    couldnt_check -- not the numbers themselves. So the spec is written from a
    real recomputation and then perturbed on purpose.
    """
    import numpy as np
    import yaml as _yaml
    from oneground.characterize import characterize_arrays

    fdir = os.path.join(tmp, "fixtures", fid)
    os.makedirs(fdir, exist_ok=True)
    rng = np.random.default_rng(7)
    base = rng.normal(size=(600, 16)).astype(np.float32)
    base /= np.linalg.norm(base, axis=1, keepdims=True)
    queries = base[:60].copy()
    if with_asset:
        np.save(os.path.join(fdir, "vectors.npy"), base)
        np.save(os.path.join(fdir, "queries.npy"), queries)

    from oneground.truth import exact_knn
    gt = exact_knn(base, queries, 10)
    np.save(os.path.join(fdir, "ground_truth.npy"), gt)

    got = characterize_arrays(base, queries, 1, log_fn=lambda *_a: None)
    values = published or {
        f: {"value": float(got[f]), "tolerance": tolerance}
        for f in fv.REPRODUCIBLE if not isinstance(got.get(f), str)
    }
    spec = {"fixture": {"id": fid, "status": "built"},
            "sampling": {"seed": 1},
            "characterization": dict(values, kind="receipt")}
    spec_path = os.path.join(tmp, "fixtures", f"{fid}.fixture.yaml")
    with open(spec_path, "w", encoding="utf-8", newline="\n") as f:
        _yaml.safe_dump(spec, f)

    with open(os.path.join(fdir, "build_info.json"), "w",
              encoding="utf-8") as f:
        json.dump({"library_versions": {}}, f)
    return fdir, spec, os.path.join(tmp, "fixtures")


def test_values_reproduce_against_their_own_published_tolerance():
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, fixtures = _tiny_fixture(tmp)
        rows = fv.verify_values("tiny", fdir, spec, assets_dir=tmp,
                                requirements_path=os.path.join(tmp, "none.txt"),
                                log_fn=lambda *_a: None)
        by = {n: (o, d) for n, o, d in rows}
        for field in fv.REPRODUCIBLE:
            if field in spec["characterization"]:
                assert by[field][0] == fv.VERIFIED, (field, by[field])


def test_a_value_outside_its_tolerance_is_contradicted_not_widened():
    """Never widen a tolerance to make something pass."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, _f = _tiny_fixture(tmp)
        field = "boundary_crispness"
        spec["characterization"][field] = {
            "value": spec["characterization"][field]["value"] + 0.5,
            "tolerance": 0.01}
        rows = fv.verify_values("tiny", fdir, spec, assets_dir=tmp,
                                requirements_path=os.path.join(tmp, "none.txt"),
                                log_fn=lambda *_a: None)
        by = {n: (o, d) for n, o, d in rows}
        assert by[field][0] == fv.CONTRADICTED, by[field]
        assert "delta" in by[field][1] and "tolerance" in by[field][1]


def test_a_value_with_no_published_tolerance_is_couldnt_check():
    """"Reproduces" has no defined meaning without one."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, _f = _tiny_fixture(tmp)
        spec["characterization"]["boundary_crispness"].pop("tolerance")
        rows = fv.verify_values("tiny", fdir, spec, assets_dir=tmp,
                                requirements_path=os.path.join(tmp, "none.txt"),
                                log_fn=lambda *_a: None)
        by = {n: (o, d) for n, o, d in rows}
        assert by["boundary_crispness"][0] == fv.COULDNT_CHECK
        # The message names why it is unusable, not just that it is.
        assert "no usable tolerance" in by["boundary_crispness"][1]
        assert "publishes no value" in by["boundary_crispness"][1]


def test_an_absent_release_asset_is_couldnt_check_never_contradicted():
    """A fresh clone is incomplete, not broken."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, _f = _tiny_fixture(tmp, with_asset=False)
        rows = fv.verify_values("tiny", fdir, spec, assets_dir=tmp,
                                requirements_path=os.path.join(tmp, "none.txt"),
                                log_fn=lambda *_a: None)
        assert rows, "no rows at all"
        for _n, outcome, detail in rows:
            assert outcome == fv.COULDNT_CHECK, (_n, outcome)
        assert any("ships separately" in d for _n, _o, d in rows)


def test_a_differing_pin_makes_every_value_couldnt_check():
    """A value reproduced under different pins has not been reproduced."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, _f = _tiny_fixture(tmp)
        with open(os.path.join(fdir, "build_info.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"library_versions": {"numpy": "1.0.0"}}, f)
        reqs = os.path.join(tmp, "requirements.txt")
        with open(reqs, "w", encoding="utf-8") as f:
            f.write("numpy==2.3.4\n")
        rows = fv.verify_values("tiny", fdir, spec, assets_dir=tmp,
                                requirements_path=reqs,
                                log_fn=lambda *_a: None)
        for _n, outcome, detail in rows:
            assert outcome == fv.COULDNT_CHECK, (_n, outcome)
        assert any("built with 1.0.0, pinned 2.3.4" in d for _n, _o, d in rows)


def test_drift_is_couldnt_check_with_the_reason_it_cannot_be_recomputed():
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, _f = _tiny_fixture(tmp)
        spec["characterization"]["drift"] = {"value_before": 0.5,
                                             "value_after": 0.5,
                                             "tolerance": 0.02}
        rows = fv.verify_values("tiny", fdir, spec, assets_dir=tmp,
                                requirements_path=os.path.join(tmp, "none.txt"),
                                log_fn=lambda *_a: None)
        by = {n: (o, d) for n, o, d in rows}
        assert by["drift"][0] == fv.COULDNT_CHECK
        assert "sample.jsonl.zst" in by["drift"][1]


def test_requirements_pins_are_read_from_a_pinned_file():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "requirements.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# a comment\nnumpy==2.3.4\n"
                    "pywin32==312; sys_platform == \"win32\"\n"
                    "unpinned-package\n\n")
        pins = fv.read_requirements_pins(p)
        assert pins["numpy"] == "2.3.4"
        assert pins["pywin32"] == "312", "an environment marker broke the pin"
        assert "unpinned-package" not in pins


def test_the_asset_may_live_beside_the_receipts():
    """arxiv-smoke keeps its 6 MB of vectors in the fixture directory;
    arxiv-150k's are a 460 MB separate download. Both are the asset."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, _spec, _f = _tiny_fixture(tmp)
        vec, q, where = fv._asset_paths("tiny", os.path.join(tmp, "nowhere"),
                                        fdir)
        assert where == fdir, where
        assert os.path.exists(vec) and os.path.exists(q)


# ------------------------------------------- drift reproduction (task 013)
def _sample_zst(path, base_dates, query_dates):
    """A sample.jsonl.zst in the layout `build` writes: base rows first."""
    import zstandard as zstd
    with open(path, "wb") as f, zstd.ZstdCompressor(level=1).stream_writer(f) as w:
        for i, d in enumerate(base_dates):
            w.write((json.dumps({"id": f"b{i}", "update_date": d,
                                 "role": "base"}) + "\n").encode())
        for i, d in enumerate(query_dates):
            w.write((json.dumps({"id": f"q{i}", "update_date": d,
                                 "role": "query"}) + "\n").encode())
    return path


def test_the_reader_splits_base_from_query_in_written_order():
    with tempfile.TemporaryDirectory() as tmp:
        p = _sample_zst(os.path.join(tmp, "s.jsonl.zst"),
                        ["2018-01-01", "2020-01-01", "2017-06-01"],
                        ["2016-01-01", "2021-01-01"])
        base, q = fv.read_sample_records(p)
        assert [r["id"] for r in base] == ["b0", "b1", "b2"], base
        assert [r["id"] for r in q] == ["q0", "q1"], q
        assert base[2]["update_date"] == "2017-06-01"


def test_the_cutoff_is_read_from_the_spec_not_guessed():
    assert fv._published_cutoff({"cutoff": "2020-06-01"}) == "2020-06-01"
    assert fv._published_cutoff(
        {"definition": "trained on records with update_date before "
                       "2019-01-01; recall measured..."}) == "2019-01-01"
    # Falling back is safe: a wrong cutoff shows up as a contradiction.
    assert fv._published_cutoff({}) == fv.DRIFT_CUTOFF


def test_a_sample_file_that_is_not_this_corpus_is_refused():
    """Zipping two different corpora together would give a number that looks
    like a reproduction and is not one."""
    import numpy as np
    with tempfile.TemporaryDirectory() as tmp:
        p = _sample_zst(os.path.join(tmp, "s.jsonl.zst"),
                        ["2018-01-01"] * 3, ["2016-01-01"] * 2)
        base = np.zeros((5, 4), dtype=np.float32)       # 5, not 3
        queries = np.zeros((2, 4), dtype=np.float32)
        got, why = fv.recompute_drift(p, base, queries, None, 1)
        assert got is None
        assert "not the same corpus" in why, why

        base = np.zeros((3, 4), dtype=np.float32)
        queries = np.zeros((7, 4), dtype=np.float32)    # 7, not 2
        got, why = fv.recompute_drift(p, base, queries, None, 1)
        assert got is None and "not the same query set" in why, why


def test_a_cutoff_that_empties_one_side_is_refused():
    import numpy as np
    with tempfile.TemporaryDirectory() as tmp:
        p = _sample_zst(os.path.join(tmp, "s.jsonl.zst"),
                        ["2020-01-01"] * 3, ["2020-01-01"] * 2)
        base = np.zeros((3, 4), dtype=np.float32)
        queries = np.zeros((2, 4), dtype=np.float32)
        got, why = fv.recompute_drift(p, base, queries, None, 1,
                                      cutoff="2019-01-01")
        assert got is None and "one side of the corpus empty" in why, why


def test_records_without_update_date_are_refused():
    import numpy as np
    import zstandard as zstd
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "s.jsonl.zst")
        with open(p, "wb") as f, \
                zstd.ZstdCompressor(level=1).stream_writer(f) as w:
            for i in range(3):
                w.write((json.dumps({"id": i, "role": "base"}) + "\n").encode())
            for i in range(2):
                w.write((json.dumps({"id": i, "role": "query"}) + "\n").encode())
        got, why = fv.recompute_drift(p, np.zeros((3, 4), dtype=np.float32),
                                      np.zeros((2, 4), dtype=np.float32),
                                      None, 1)
        assert got is None and "no update_date" in why, why


def test_the_drift_pair_is_compared_against_both_published_sides():
    published = {"value_before": 0.522, "value_after": 0.549,
                 "tolerance": 0.02}
    ok = fv._compare_drift(published, {"drift_before": 0.5225,
                                       "drift_after": 0.5488})
    assert ok[1] == fv.VERIFIED, ok
    assert "before recomputed" in ok[2] and "after recomputed" in ok[2]

    # One side outside tolerance fails the pair; a pair is a pair.
    bad = fv._compare_drift(published, {"drift_before": 0.522,
                                        "drift_after": 0.60})
    assert bad[1] == fv.CONTRADICTED, bad


def test_drift_without_a_published_tolerance_is_couldnt_check():
    out = fv._compare_drift({"value_before": 0.5, "value_after": 0.5},
                            {"drift_before": 0.5, "drift_after": 0.5})
    assert out[1] == fv.COULDNT_CHECK, out
    assert "no usable tolerance for drift" in out[2], out


# ----------------------------- the verifier's own pins (task 013)
def test_the_running_environment_is_what_decides_a_reproduction():
    """`pin_mismatches` confirms the historical build was pinned. It says
    nothing about the process recomputing the values now, and that is the
    comparison `verified` depends on."""
    with tempfile.TemporaryDirectory() as tmp:
        reqs = os.path.join(tmp, "requirements.txt")
        with open(reqs, "w", encoding="utf-8") as f:
            f.write("numpy==2.5.3\nfaiss-cpu==1.15.0\n")
        # The build matched the pins ...
        assert fv.pin_mismatches(
            {"library_versions": {"numpy": "2.5.3", "faiss-cpu": "1.15.0"}},
            reqs) == []
        # ... and this process does not.
        bad = fv.running_pin_mismatches(
            reqs, versions={"numpy": "2.2.6", "faiss-cpu": "1.14.3"})
        assert ("numpy", "2.2.6", "2.5.3") in bad, bad
        assert ("faiss-cpu", "1.14.3", "1.15.0") in bad, bad


def test_a_within_tolerance_value_outside_the_pins_is_couldnt_check():
    """Never rounded up -- and the number stays visible."""
    row = ("boundary_crispness", fv.VERIFIED,
           "recomputed 0.0362, published 0.036, delta 0.0002, tolerance 0.02")
    out = fv._downgrade(row, [("numpy", "2.2.6", "2.5.3")])
    assert out[1] == fv.COULDNT_CHECK, out
    assert "WITHIN TOLERANCE" in out[2]
    assert "not under the pinned environment" in out[2]
    assert "running 2.2.6, pinned 2.5.3" in out[2]
    # The measurement itself is still readable.
    assert "delta 0.0002" in out[2]


def test_a_contradiction_is_never_downgraded_by_an_unpinned_environment():
    """Disagreement is disagreement; unpinned libraries explain it at most."""
    row = ("boundary_crispness", fv.CONTRADICTED,
           "recomputed 0.9, published 0.036, delta 0.86, tolerance 0.02")
    out = fv._downgrade(row, [("numpy", "2.2.6", "2.5.3")])
    assert out == row, out


def test_nothing_is_downgraded_in_a_pinned_environment():
    row = ("x", fv.VERIFIED, "detail")
    assert fv._downgrade(row, []) == row


def test_running_versions_reports_what_was_actually_imported():
    got = fv.running_versions()
    import numpy
    assert got.get("numpy") == numpy.__version__


# --------------------------------------- --asset, an explicit folder (014)
def test_an_explicit_asset_folder_wins_over_the_documented_location():
    """An external runner must never have to adopt this project's layout.

    `--asset` names the extracted folder outright; without it the release
    asset is looked for under the assets directory, then beside the receipts.
    """
    with tempfile.TemporaryDirectory() as tmp:
        elsewhere = os.path.join(tmp, "somewhere-else")
        os.makedirs(elsewhere)
        for name in ("vectors.npy", "queries.npy"):
            with open(os.path.join(elsewhere, name), "wb") as f:
                f.write(b"x")
        vec, q, where = fv._asset_paths(
            "any-fixture", os.path.join(tmp, "assets"),
            fixture_dir=os.path.join(tmp, "fixture"), asset=elsewhere)
        assert where == elsewhere, where
        assert vec == os.path.join(elsewhere, "vectors.npy")
        assert q == os.path.join(elsewhere, "queries.npy")


def test_the_asset_folder_expands_a_tilde():
    """A published instruction says ~/oneground-assets/..., so the flag has to
    accept what the instruction tells people to type."""
    vec, _q, where = fv._asset_paths("x", "assets", asset="~/nowhere-at-all")
    assert "~" not in where, where
    assert where == os.path.expanduser("~/nowhere-at-all")


def test_without_asset_the_documented_location_is_still_used():
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "assets", "fx")
        os.makedirs(d)
        for name in ("vectors.npy", "queries.npy"):
            with open(os.path.join(d, name), "wb") as f:
                f.write(b"x")
        _v, _q, where = fv._asset_paths("fx", os.path.join(tmp, "assets"))
        assert where == d, where


def test_the_verify_parser_offers_asset_on_both_entry_points():
    from oneground import cli

    def flags(parser):
        return {o for a in parser._actions
                for o in getattr(a, "option_strings", ())}

    assert "--asset" in flags(
        cli._fixture_parser()._actions[-1].choices["verify"])
    assert "--asset" in flags(
        fv.build_parser()._actions[-1].choices["fixture"]
        ._actions[-1].choices["verify"])
