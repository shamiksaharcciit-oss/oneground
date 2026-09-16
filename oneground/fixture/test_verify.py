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
    # Task 022: a fixture is its spec and its directory together. This spec
    # publishes no values, so these tests stay about the digest half: nothing
    # is recomputed and no release asset is needed.
    with open(os.path.join(tmp, "fx.fixture.yaml"), "w", encoding="utf-8",
              newline="\n") as s:
        s.write("fixture:\n  id: fx\n  status: built\n")
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




# ---------------------------------------------------------------- task 016g
def _runner_text():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "..", "corpora", "run_fixture_build.sh")
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_the_runner_packages_before_the_projection_real_script():
    """Receipts first. Session 20260911-220320 lost a finished build because
    the only tarball was written at the very end; the first `pack` must come
    before anything optional runs."""
    t = _runner_text()
    first_pack = t.index('\npack "the manifest')
    projection = t.index("fixture project")
    assert first_pack < projection, "the projection runs before the receipts are packaged"
    build = t.index("python corpora/build_fixture.py")
    assert build < first_pack, "packaging happens before the builder runs"


def test_the_builder_is_always_told_to_skip_the_projection_real_script():
    """Otherwise the receipts pack would still wait on UMAP."""
    t = _runner_text()
    line = [ln for ln in t.splitlines() if ln.startswith("BUILD_ARGS=(")][0]
    assert "--skip-projection" in line, line


def test_every_later_stage_repacks_real_script():
    """Each stage that can add a file must leave the tarball current."""
    t = _runner_text()
    for stage in ("the projection", "verify", "the ground view"):
        assert 'pack "%s"' % stage in t, stage


def test_packing_is_atomic_real_script():
    """A fetch that races a repack must get the previous whole tarball, not a
    half-written one."""
    t = _runner_text()
    assert 'tar -czf "$TARBALL.tmp"' in t
    assert 'mv -f "$TARBALL.tmp" "$TARBALL"' in t
    assert 'tar -czf "$TARBALL_LARGE.tmp"' in t
    assert 'mv -f "$TARBALL_LARGE.tmp" "$TARBALL_LARGE"' in t


def test_the_receipts_are_all_mandatory_members_real_script():
    t = _runner_text()
    block = t[t.index("    local members=("):t.index("    # Optional members")]
    for want in ("MANIFEST.sha256", "characterization.json",
                 "build_info.json", "query_ids.json", "ground_truth.npy"):
        assert want in block, want
    # The projection is optional: it must not be a mandatory member, or an
    # early pack would fail outright on a file that does not exist yet.
    assert "projection.npy" not in block



def test_skip_projection_still_skips_the_separate_step_real_script():
    """SKIP_PROJECTION=1 must skip the projection, not merely announce it.

    The builder is now always given --skip-projection, so honouring the
    variable moved to the runner's own projection step. Without this the
    variable would have become a no-op that printed a NOTE and then projected
    anyway.
    """
    t = _runner_text()
    i = t.index('echo "projecting ..."')
    guard = t.rindex('if [ -n "$SKIP_PROJECTION" ]; then', 0, i)
    # The guard must be the thing immediately wrapping the projection call,
    # not the earlier NOTE-printing one near BUILD_ARGS.
    between = t[guard:i]
    assert "projection skipped (SKIP_PROJECTION set)" in between, between
    assert "BUILD_ARGS" not in between, between

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


# ---------------------------------------------------------------- task 016h
# A first canonical build has nothing to verify against: the spec carries
# TO_BE_FILLED throughout, and the build's own output is what fills it. The
# recomputation is exact k-NN, a fresh k-means over the whole base and both
# HNSW reference configurations -- 6-8 minutes of pod time on
# stackexchange-150k, producing rows that were knowable from the spec before
# a vector was read. Session 20260911-220320 was killed at its cap 21 minutes
# from the finish with that recomputation in its tail.

def _placeholder_spec(tmp, fid="tiny"):
    """A tiny fixture whose published values are all TO_BE_FILLED."""
    fdir, spec, fixtures = _tiny_fixture(tmp, fid=fid)
    for f in fv.REPRODUCIBLE:
        if f in spec["characterization"]:
            spec["characterization"][f] = {"value": "TO_BE_FILLED",
                                           "tolerance": 0.02}
    spec["characterization"]["drift"] = {"value_before": "TO_BE_FILLED",
                                         "value_after": "TO_BE_FILLED",
                                         "tolerance": 0.02}
    spec["reference_results"] = {
        "single_node_hnsw": {"params": {"M": 32, "efSearch": 128},
                             "recall_at_10": "TO_BE_FILLED",
                             "tolerance": 0.01},
        "semantic_sharded": {"params": {"centroids": 8, "epsilon": 0.2,
                                        "probe": 2, "M": 32, "efSearch": 96},
                             "recall_at_10": "TO_BE_FILLED",
                             "storage_amplification": "TO_BE_FILLED",
                             "tolerance": 0.01},
        "kind": "receipt"}
    spec["fixture"]["status"] = "planned"
    return fdir, spec, fixtures


def test_a_spec_with_nothing_published_skips_the_recomputation():
    """Every row is still couldnt_check -- it just costs nothing to say so."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, _f = _placeholder_spec(tmp)
        lines = []
        rows = fv.verify_values("tiny", fdir, spec, assets_dir=tmp,
                                requirements_path=os.path.join(tmp, "n.txt"),
                                log_fn=lines.append)
        assert rows, "no rows at all"
        for name, outcome, detail in rows:
            assert outcome == fv.COULDNT_CHECK, (name, outcome, detail)
            assert "nothing to reproduce" in detail, (name, detail)
        text = "\n".join(lines)
        assert "every published value is a placeholder" in text, text
        # The two expensive recomputations must not have been announced.
        assert "recomputing single_node_hnsw" not in text, text
        assert "recomputing semantic_sharded" not in text, text


def test_the_skip_covers_the_reference_rows_too():
    """The reference configs are the expensive half; they must be in the
    skipped set, not merely absent from it."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, _f = _placeholder_spec(tmp)
        rows = fv.verify_values("tiny", fdir, spec, assets_dir=tmp,
                                requirements_path=os.path.join(tmp, "n.txt"),
                                log_fn=lambda *_a: None)
        names = {n for n, _o, _d in rows}
        for want in ("single_node_hnsw.recall_at_10",
                     "semantic_sharded.recall_at_10",
                     "semantic_sharded.storage_amplification", "drift"):
            assert want in names, (want, sorted(names))


def test_one_filled_value_is_enough_to_make_it_recompute():
    """Deliberately generous: a single real number can still be contradicted,
    so the recomputation is worth doing for it."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, _f = _placeholder_spec(tmp)
        # Fill exactly one field. Its value does not matter -- verified or
        # contradicted are both proof that the recomputation ran.
        spec["characterization"]["boundary_crispness"] = {
            "value": 0.5, "tolerance": 0.02}
        lines = []
        rows = fv.verify_values("tiny", fdir, spec, assets_dir=tmp,
                                requirements_path=os.path.join(tmp, "n.txt"),
                                log_fn=lines.append)
        text = "\n".join(lines)
        assert "every published value is a placeholder" not in text, text
        by = {n: o for n, o, _d in rows}
        # It recomputed, so this one got a real verdict rather than the skip.
        assert by["boundary_crispness"] in (fv.VERIFIED, fv.CONTRADICTED), by


def test_anything_published_agrees_with_what_compare_treats_as_a_number():
    """The guard and `_compare` must not disagree about what is published."""
    wanted = ["boundary_crispness"]
    ref_rows = [("single_node_hnsw.recall_at_10", "single_node_hnsw")]
    empty = {"boundary_crispness": {"value": "TO_BE_FILLED"}}
    assert not fv._anything_published(empty, {}, wanted, ref_rows)
    assert not fv._anything_published({}, {}, [], [])
    filled = {"boundary_crispness": {"value": 0.036}}
    assert fv._anything_published(filled, {}, wanted, ref_rows)
    # A value only in the reference block still counts.
    assert fv._anything_published(
        empty, {"single_node_hnsw": {"recall_at_10": 0.99}}, wanted, ref_rows)
    # And a drift pair on its own counts.
    assert fv._anything_published(
        {"drift": {"value_before": 0.52}}, {}, [], [])


def _shipped(name):
    import yaml as _yaml
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "..", "fixtures", name)
    with open(path, encoding="utf-8") as f:
        return _yaml.safe_load(f)


def _publish_args(spec):
    published = spec.get("characterization") or {}
    refs = spec.get("reference_results") or {}
    wanted = [f for f in fv.REPRODUCIBLE if f in published]
    ref_rows = [("single_node_hnsw.recall_at_10", "single_node_hnsw"),
                ("semantic_sharded.recall_at_10", "semantic_sharded"),
                ("semantic_sharded.storage_amplification", "semantic_sharded")]
    return published, refs, wanted, ref_rows


def test_a_shipped_unbuilt_spec_is_in_the_skip_case():
    """Not synthetic: arxiv-smoke is `status: planned` and TO_BE_FILLED
    throughout, which is the state every fixture is in before its first
    canonical build -- the state stackexchange-150k was in when this skip was
    written, and the one that cost 6-8 minutes of pod time per run."""
    spec = _shipped("arxiv-smoke.fixture.yaml")
    assert spec["fixture"]["status"] == "planned", spec["fixture"]["status"]
    assert not fv._anything_published(*_publish_args(spec))


def test_a_built_fixture_leaves_the_skip_case():
    """stackexchange-150k was the motivating skip case and is no longer in it:
    its canonical build (session 20260912-100920) filled every value, so the
    recomputation now has something to contradict and must run."""
    spec = _shipped("stackexchange-150k.fixture.yaml")
    assert spec["fixture"]["status"] == "built", spec["fixture"]["status"]
    assert fv._anything_published(*_publish_args(spec))


def test_the_shipped_arxiv_spec_is_not_in_the_skip_case():
    """arxiv-150k publishes real values and must still be recomputed."""
    import yaml as _yaml
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "..", "fixtures",
                        "arxiv-150k.fixture.yaml")
    with open(path, encoding="utf-8") as f:
        spec = _yaml.safe_load(f)
    published = spec.get("characterization") or {}
    refs = spec.get("reference_results") or {}
    wanted = [f for f in fv.REPRODUCIBLE if f in published]
    ref_rows = [("single_node_hnsw.recall_at_10", "single_node_hnsw"),
                ("semantic_sharded.recall_at_10", "semantic_sharded"),
                ("semantic_sharded.storage_amplification", "semantic_sharded")]
    assert fv._anything_published(published, refs, wanted, ref_rows)


# ---------------------------------------------------------------- task 022
# `oneground fixture verify arxiv-150k`, from a bare `pip install` outside any
# checkout, printed `error: no such fixture directory` and nothing else. These
# pin the four things task 022 changed: where a fixture is found, that every
# missing precondition is named in one run, that a value the host cannot
# recompute is couldnt_check for that value alone, and that the summary says
# no more than its rows.
import contextlib                                              # noqa: E402
import io                                                      # noqa: E402


@contextlib.contextmanager
def _cwd(path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


@contextlib.contextmanager
def _patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


def _run(**kw):
    """cmd_verify with these attributes, returning (exit code, stdout)."""
    class Args:
        pass
    for k, v in kw.items():
        setattr(Args, k, v)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fv.cmd_verify(Args)
    return code, buf.getvalue()


def _pinned_requirements(tmp, **override):
    """A requirements file pinning exactly what this process runs, so a test
    is decided by the fixture and not by the developer's venv."""
    path = os.path.join(tmp, "requirements.txt")
    running = fv.running_versions()
    with open(path, "w", encoding="utf-8") as f:
        for name in ("numpy", "faiss-cpu", "scikit-learn"):
            version = override.get(name.replace("-", "_"), running.get(name))
            if version:
                f.write(f"{name}=={version}\n")
    return path


def _manifest(fdir):
    lines = []
    for name in sorted(os.listdir(fdir)):
        p = os.path.join(fdir, name)
        if os.path.isfile(p) and name != fv.MANIFEST_NAME:
            with open(p, "rb") as f:
                lines.append(f"{hashlib.sha256(f.read()).hexdigest()}  {name}")
    with open(os.path.join(fdir, fv.MANIFEST_NAME), "w", encoding="utf-8",
              newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def _spec_dir(root, fid="fx"):
    os.makedirs(os.path.join(root, fid), exist_ok=True)
    with open(os.path.join(root, fid, fv.MANIFEST_NAME), "w",
              encoding="utf-8") as f:
        f.write("")
    with open(os.path.join(root, fid + ".fixture.yaml"), "w",
              encoding="utf-8") as f:
        f.write(f"fixture:\n  id: {fid}\n")


def test_outside_a_checkout_the_installed_packages_copy_is_found():
    with tempfile.TemporaryDirectory() as tmp:
        pkg, elsewhere = os.path.join(tmp, "pkg"), os.path.join(tmp, "else")
        _spec_dir(pkg)
        os.makedirs(elsewhere)
        with _patched(fv, "PACKAGE_FIXTURES", pkg), _cwd(elsewhere):
            found, looked = fv.find_fixture("fx")
        assert found and found["label"] == "the installed package", found
        assert found["dir"] == os.path.join(pkg, "fx")
        # and it says where it looked first
        assert [label for label, _r, _m in looked] == ["the current directory"]


def test_the_current_directory_wins_over_the_package():
    with tempfile.TemporaryDirectory() as tmp:
        pkg, work = os.path.join(tmp, "pkg"), os.path.join(tmp, "work")
        _spec_dir(pkg)
        _spec_dir(os.path.join(work, "fixtures"))
        with _patched(fv, "PACKAGE_FIXTURES", pkg), _cwd(work):
            found, _looked = fv.find_fixture("fx")
        assert found["label"] == "the current directory", found


def test_an_explicit_fixtures_directory_is_the_only_place_looked():
    """Pointing at a directory and being given the package's copy instead
    would be a result about bytes the reader did not choose."""
    with tempfile.TemporaryDirectory() as tmp:
        pkg, mine = os.path.join(tmp, "pkg"), os.path.join(tmp, "mine")
        _spec_dir(pkg)
        os.makedirs(mine)
        with _patched(fv, "PACKAGE_FIXTURES", pkg):
            found, looked = fv.find_fixture("fx", fixtures=mine)
        assert found is None
        assert [label for label, _r, _m in looked] == ["--fixtures"]


def test_a_directory_without_its_spec_is_not_a_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "fixtures")
        _spec_dir(root)
        os.remove(os.path.join(root, "fx.fixture.yaml"))
        found, looked = fv.find_fixture("fx", fixtures=root)
        assert found is None
        assert looked[0][2] == [os.path.join(root, "fx.fixture.yaml")]


def test_a_missing_fixture_names_all_three_preconditions_not_a_bare_error():
    with tempfile.TemporaryDirectory() as tmp:
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        code, out = _run(id="arxiv-150k", fixtures_dir=empty,
                         requirements=_pinned_requirements(tmp),
                         assets_dir=os.path.join(tmp, "assets"))
        assert code == 2, (code, out)
        assert "no such fixture directory" not in out, out
        for key in ("fixture ", "environment ", "asset "):
            assert "\n  " + key in out, (key, out)
        # a known release asset is described even without the spec
        assert "arxiv-150k-v1.tgz, 483,468,013 bytes" in out, out
        assert "--asset" in out, out
        assert "nothing was checked" in out, out


def _fixture_with_manifest(tmp, with_asset=True, extra_spec=None):
    fdir, spec, fixtures = _tiny_fixture(tmp, with_asset=with_asset)
    if extra_spec:
        import yaml as _yaml
        spec.update(extra_spec)
        with open(os.path.join(fixtures, "tiny.fixture.yaml"), "w",
                  encoding="utf-8", newline="\n") as f:
            _yaml.safe_dump(spec, f)
    _manifest(fdir)
    return fdir, spec, fixtures


def test_a_missing_asset_still_checks_the_digests_and_exits_2():
    with tempfile.TemporaryDirectory() as tmp:
        _fdir, _spec, fixtures = _fixture_with_manifest(tmp, with_asset=False)
        code, out = _run(id="tiny", fixtures_dir=fixtures,
                         requirements=_pinned_requirements(tmp),
                         assets_dir=os.path.join(tmp, "assets"))
        assert code == 2, (code, out)
        assert "verified      receipt  ground_truth.npy" in out, out
        assert "asset        MISSING" in out, out
        flat = " ".join(out.split())             # the summary is wrapped
        assert ("No value was recomputed, because the release asset is not "
                "present.") in flat, out
        # the one universal it may say about the digests, because it holds
        assert "listed files are present and match the manifest" in flat, out


def test_every_missing_precondition_is_named_in_the_same_run():
    """The environment and the asset, both, from one run -- not the first."""
    with tempfile.TemporaryDirectory() as tmp:
        _fdir, _spec, fixtures = _fixture_with_manifest(tmp, with_asset=False)
        code, out = _run(id="tiny", fixtures_dir=fixtures,
                         requirements=_pinned_requirements(tmp,
                                                           numpy="0.0.1"),
                         assets_dir=os.path.join(tmp, "assets"))
        assert code == 2, (code, out)
        assert "environment  UNPINNED" in out, out
        assert "pinned 0.0.1" in out, out
        assert "pip install oneground==" in out, out
        assert "asset        MISSING" in out, out
        assert ("No value was recomputed, because this environment is not "
                "running the pinned versions and the release asset is not "
                "present.") in " ".join(out.split()), out


def test_no_pin_source_is_never_read_as_pinned():
    """Before 022 a missing requirements.txt was an empty pin set, and an
    empty set has no mismatches."""
    with tempfile.TemporaryDirectory() as tmp:
        _fdir, _spec, fixtures = _fixture_with_manifest(tmp)
        nowhere = os.path.join(tmp, "nowhere")
        os.makedirs(nowhere)
        with _patched(fv, "distribution_pins", lambda: {}), _cwd(nowhere):
            pins, source, looked = fv.resolve_pins()
            assert (pins, source) == ({}, None), (pins, source)
            code, out = _run(id="tiny", fixtures_dir=fixtures,
                             assets_dir=os.path.join(tmp, "assets"))
        assert code == 2, (code, out)
        assert "environment  MISSING" in out, out
        assert "verified      intrinsic" not in out, out


def test_outside_a_checkout_the_distributions_own_pins_are_the_set():
    with tempfile.TemporaryDirectory() as tmp:
        numpy_now = fv.running_versions()["numpy"]
        with _patched(fv, "distribution_pins",
                      lambda: {"numpy": numpy_now}), _cwd(tmp):
            pins, source, _looked = fv.resolve_pins()
        assert pins == {"numpy": numpy_now}
        assert source.startswith("the installed oneground"), source


def test_an_injected_memory_error_on_one_value_leaves_the_rest_and_exits_0():
    """The 018e intent. 018d's fresh-machine check died on one allocation and
    reported no value at all."""
    from oneground.fixture import reference
    with tempfile.TemporaryDirectory() as tmp:
        refs = {"reference_results": {"single_node_hnsw": {
            "params": {"M": 8, "efConstruction": 40, "efSearch": 32},
            "recall_at_10": 0.9, "tolerance": 0.01}}}
        _fdir, spec, fixtures = _fixture_with_manifest(tmp, extra_spec=refs)

        def out_of_memory(*_a, **_k):
            raise MemoryError("Unable to allocate 211. MiB for an array")

        with _patched(reference, "ref_single_node", out_of_memory):
            code, out = _run(id="tiny", fixtures_dir=fixtures,
                             requirements=_pinned_requirements(tmp),
                             assets_dir=os.path.join(tmp, "assets"))
        assert code == 0, (code, out)
        assert ("couldnt_check single_node_hnsw.recall_at_10" in out
                and "out of memory" in out), out
        for field in fv.REPRODUCIBLE:
            if field in spec["characterization"]:
                assert f"verified      {field}" in out, (field, out)
        flat = " ".join(out.split())             # the summary is wrapped
        assert ("1 value could not be recomputed on this host; the rows above "
                "give the reason: single_node_hnsw.recall_at_10.") in flat, out
        assert ("The digests were checked before any value, so the 4 files "
                "that verified are the published bytes") in flat, out
        assert "Every" not in out, out


def test_a_host_failure_never_softens_a_contradiction_beside_it():
    from oneground.fixture import reference
    with tempfile.TemporaryDirectory() as tmp:
        refs = {"reference_results": {"single_node_hnsw": {
            "params": {"M": 8, "efConstruction": 40, "efSearch": 32},
            "recall_at_10": 0.9, "tolerance": 0.01}}}
        _fdir, spec, fixtures = _fixture_with_manifest(tmp, extra_spec=refs)
        import yaml as _yaml
        spec["characterization"]["boundary_crispness"]["value"] += 0.5
        with open(os.path.join(fixtures, "tiny.fixture.yaml"), "w",
                  encoding="utf-8", newline="\n") as f:
            _yaml.safe_dump(spec, f)

        def out_of_memory(*_a, **_k):
            raise MemoryError("no room")

        with _patched(reference, "ref_single_node", out_of_memory):
            code, out = _run(id="tiny", fixtures_dir=fixtures,
                             requirements=_pinned_requirements(tmp),
                             assets_dir=os.path.join(tmp, "assets"))
        assert code == 1, (code, out)
        assert "contradicted  boundary_crispness" in out, out


def test_recompute_failed_names_the_environmental_causes():
    assert fv.recompute_failed(MemoryError("x")).cause == fv.HOST
    assert fv.recompute_failed(ImportError("x")).cause == fv.HOST
    assert fv.recompute_failed(OSError("x")).cause == fv.HOST
    # anything else is the recomputation failing, not the machine
    assert fv.recompute_failed(TypeError("x")).cause == fv.RECOMPUTE


def test_a_spec_with_nothing_published_needs_no_asset_and_exits_0():
    """arxiv-smoke's shape: TO_BE_FILLED throughout."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, fixtures = _placeholder_spec(tmp)
        import yaml as _yaml
        with open(os.path.join(fixtures, "tiny.fixture.yaml"), "w",
                  encoding="utf-8", newline="\n") as f:
            _yaml.safe_dump(spec, f)
        for name in ("vectors.npy", "queries.npy"):
            os.remove(os.path.join(fdir, name))
        _manifest(fdir)
        code, out = _run(id="tiny", fixtures_dir=fixtures,
                         requirements=_pinned_requirements(tmp),
                         assets_dir=os.path.join(tmp, "assets"))
        assert code == 0, (code, out)
        assert "asset        not needed" in out, out
        assert ("No value is published in the spec yet"
                in " ".join(out.split())), out


def test_the_release_assets_agree_with_the_release_notes():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "..", "RELEASE_NOTES.md"),
              encoding="utf-8") as f:
        notes = f.read()
    for fid, (name, size) in fv.RELEASE_ASSETS.items():
        assert f"{name}\n  {size:,} bytes" in notes, (fid, name, size)


# --- the summary, by the 019 rule --------------------------------------------

def _row(name, outcome, cause=None):
    return fv.ValueRow(name, outcome, "detail", cause)


def _digest(name, outcome):
    return (name, fv.RECEIPT, outcome, "detail")


_MISSING_ASSET = [{"key": "asset", "met": False, "blocks_values": True,
                   "because": "the release asset is not present"}]


def test_every_published_value_is_said_only_when_the_published_set_is_covered():
    rows = [_row("val_one", fv.VERIFIED), _row("val_two", fv.VERIFIED)]
    said = fv.summary_sentences([], rows, ["val_one", "val_two"], [])
    assert any(s.startswith("Every published value reproduced (2 of 2)")
               for s in said), said
    said = fv.summary_sentences([], rows,
                                ["val_one", "val_two", "val_ceiling"], [])
    assert not any("Every published value" in s for s in said), said
    assert "Every value this command recomputes reproduced (2 of 2)." in said
    assert ("1 published value is not recomputed by this command: "
            "val_ceiling.") in said, said
    assert not any("may be set to `verified`" in s for s in said), said


def test_the_shipped_150k_specs_publish_values_this_command_does_not_recompute():
    """Not synthetic. Found by task 022: `semantic_sharded` publishes its
    routing ceiling and copy percentiles, which no row recomputes, so "every
    published value reproduced" was never true of these specs."""
    for name in ("arxiv-150k.fixture.yaml", "stackexchange-150k.fixture.yaml"):
        spec = _shipped(name)
        uncovered = (set(fv.published_value_names(spec))
                     - set(fv.value_names(spec)))
        assert "semantic_sharded.routing_ceiling" in uncovered, (name,
                                                                 uncovered)


def test_the_three_different_sentences_stay_different():
    both = [_row("val_one", fv.COULDNT_CHECK, fv.NOT_ATTEMPTED),
            _row("val_two", fv.COULDNT_CHECK, fv.NOT_ATTEMPTED)]
    said = fv.summary_sentences([], both, [], _MISSING_ASSET)
    assert ("No value was recomputed, because the release asset is not "
            "present.") in said, said

    host = [_row("val_one", fv.VERIFIED),
            _row("val_two", fv.COULDNT_CHECK, fv.HOST)]
    said = fv.summary_sentences([], host, [], [])
    assert any(s.startswith("1 value could not be recomputed on this host")
               for s in said), said
    assert not any(s.startswith(("No value", "Every")) for s in said), said

    placeholders = [_row("val_one", fv.COULDNT_CHECK, fv.UNPUBLISHED)]
    said = fv.summary_sentences([], placeholders, [], [])
    assert any(s.startswith("No value is published") for s in said), said


def test_no_summary_sentence_asserts_more_than_its_rows():
    """Task 019's rule, by hand, over every mix of three values and two
    digests: a universal is written only when it holds for every row it
    quantifies over, and a value is named only in the sentence for its own
    outcome and cause."""
    import itertools
    from oneground.report import claims

    kinds = [(fv.VERIFIED, None), (fv.CONTRADICTED, None),
             (fv.COULDNT_CHECK, fv.NOT_ATTEMPTED),
             (fv.COULDNT_CHECK, fv.HOST), (fv.COULDNT_CHECK, fv.UNPINNED),
             (fv.COULDNT_CHECK, fv.UNPUBLISHED)]
    marker = {fv.VERIFIED: "reproduced", fv.CONTRADICTED: "contradicted",
              fv.NOT_ATTEMPTED: "not recomputed, because",
              fv.HOST: "on this host", fv.UNPINNED: "outside the pinned",
              fv.UNPUBLISHED: "not published"}
    names = ("val_one", "val_two", "val_three")
    douts = (fv.VERIFIED, fv.CONTRADICTED, fv.COULDNT_CHECK)
    checked = 0
    for combo in itertools.product(kinds, repeat=3):
        rows = [_row(n, o, c) for n, (o, c) in zip(names, combo)]
        for d in itertools.product(douts, repeat=2):
            digests = [_digest("file_a", d[0]), _digest("file_b", d[1])]
            said = fv.summary_sentences(digests, rows, list(names),
                                        _MISSING_ASSET)
            checked += 1
            for s in said:
                universal = (claims.universal_words_in(s)
                             or s.startswith("No value"))
                if s.startswith("All "):
                    assert all(x[2] == fv.VERIFIED for x in digests), s
                elif s.startswith("Every"):
                    assert all(r[1] == fv.VERIFIED for r in rows), (s, rows)
                elif s.startswith("No value was recomputed"):
                    assert all(r.cause == fv.NOT_ATTEMPTED for r in rows), s
                elif s.startswith("No value is published"):
                    assert all(r.cause == fv.UNPUBLISHED for r in rows), s
                else:
                    assert not universal, (s, universal)
                for r in rows:
                    if r[0] not in s or s.startswith(("Every", "No value")):
                        continue
                    key = r.cause if r[1] == fv.COULDNT_CHECK else r[1]
                    assert marker[key] in s, (r[0], key, s)
    assert checked == 6 ** 3 * 3 ** 2


# ----------------------------------------------------- task 022, additions
# From runs on the published 0.1.0rc1: `--asset ./arxiv-150k` (the README's
# path, one level short of what the tarball creates) reported every value
# couldn't-check and exited 0 -- the tool saying it checked when it did not.
# And extracting the tarball where the fixture is looked for produced
# `error: no MANIFEST.sha256 in fixtures\arxiv-150k`, naming nothing useful.

def _fixture_and_separate_asset(tmp):
    """A tiny fixture whose asset lives in its own folder, as a tarball's does."""
    import shutil as _shutil
    fdir, spec, fixtures = _tiny_fixture(tmp, with_asset=True)
    asset = os.path.join(tmp, "extracted", "fixtures", "tiny")
    os.makedirs(asset)
    for name in ("vectors.npy", "queries.npy"):
        _shutil.move(os.path.join(fdir, name), os.path.join(asset, name))
    _manifest(fdir)
    return fdir, spec, fixtures, asset


def test_a_correct_asset_folder_verifies():
    with tempfile.TemporaryDirectory() as tmp:
        _fdir, spec, fixtures, asset = _fixture_and_separate_asset(tmp)
        code, out = _run(id="tiny", fixtures_dir=fixtures, asset=asset,
                         requirements=_pinned_requirements(tmp),
                         assets_dir=os.path.join(tmp, "assets"))
        assert code == 0, (code, out)
        assert "asset        present" in out, out
        for field in fv.REPRODUCIBLE:
            if field in spec["characterization"]:
                assert f"verified      {field}" in out, (field, out)


def test_a_wrong_asset_folder_exits_2_naming_what_it_looked_for_and_found():
    with tempfile.TemporaryDirectory() as tmp:
        _fdir, _spec, fixtures, _asset = _fixture_and_separate_asset(tmp)
        wrong = os.path.join(tmp, "somewhere")
        os.makedirs(wrong)
        with open(os.path.join(wrong, "notes.txt"), "w") as f:
            f.write("not an asset")
        code, out = _run(id="tiny", fixtures_dir=fixtures, asset=wrong,
                         requirements=_pinned_requirements(tmp),
                         assets_dir=os.path.join(tmp, "assets"))
        assert code == 2, (code, out)
        flat = " ".join(out.split())
        assert ("holds none of vectors.npy, queries.npy and sample.jsonl.zst; "
                "it holds notes.txt") in flat, out
        assert "verified      intrinsic" not in out, out


def test_an_asset_folder_that_does_not_exist_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        _fdir, _spec, fixtures, _asset = _fixture_and_separate_asset(tmp)
        code, out = _run(id="tiny", fixtures_dir=fixtures,
                         asset=os.path.join(tmp, "tiny"),
                         requirements=_pinned_requirements(tmp),
                         assets_dir=os.path.join(tmp, "assets"))
        assert code == 2, (code, out)
        assert "it does not exist" in out, out


def test_an_asset_path_one_level_short_names_the_folder_that_holds_it():
    """The tarball extracts to fixtures/<id>/; pointing at the extraction
    directory is the commonest wrong path."""
    with tempfile.TemporaryDirectory() as tmp:
        _fdir, _spec, fixtures, asset = _fixture_and_separate_asset(tmp)
        up = os.path.join(tmp, "extracted")
        code, out = _run(id="tiny", fixtures_dir=fixtures, asset=up,
                         requirements=_pinned_requirements(tmp),
                         assets_dir=os.path.join(tmp, "assets"))
        assert code == 2, (code, out)
        assert "it holds fixtures/" in out, out
        assert f"pass --asset {os.path.normpath(asset)}" in out, out


def test_a_wrong_asset_on_a_spec_with_nothing_published_still_exits_2():
    """Passing --asset asserts the asset is there, whether or not it is
    needed -- but the rows still say the values are unpublished, not that the
    flag stopped them."""
    with tempfile.TemporaryDirectory() as tmp:
        fdir, spec, fixtures = _placeholder_spec(tmp)
        import yaml as _yaml
        with open(os.path.join(fixtures, "tiny.fixture.yaml"), "w",
                  encoding="utf-8", newline="\n") as f:
            _yaml.safe_dump(spec, f)
        _manifest(fdir)
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        code, out = _run(id="tiny", fixtures_dir=fixtures, asset=empty,
                         requirements=_pinned_requirements(tmp),
                         assets_dir=os.path.join(tmp, "assets"))
        flat = " ".join(out.split())
        assert code == 2, (code, out)
        assert "it is empty" in out, out
        assert "No value is published in the spec yet" in flat, out
        assert "No value was recomputed" not in flat, out
        # and the same spec with an asset folder that does hold it: exit 0
        code, out = _run(id="tiny", fixtures_dir=fixtures, asset=fdir,
                         requirements=_pinned_requirements(tmp),
                         assets_dir=os.path.join(tmp, "assets"))
        assert code == 0, (code, out)


def _extracted_in_cwd(tmp):
    """The package holds the fixture; the tarball was extracted in the cwd."""
    import shutil as _shutil
    fdir, _spec, fixtures = _tiny_fixture(tmp, with_asset=True)
    work = os.path.join(tmp, "work")
    extracted = os.path.join(work, "fixtures", "tiny")
    os.makedirs(extracted)
    for name in ("vectors.npy", "queries.npy"):
        _shutil.move(os.path.join(fdir, name), os.path.join(extracted, name))
    _manifest(fdir)
    return fixtures, work, extracted


def test_an_asset_extracted_where_the_fixture_is_looked_for_is_named():
    with tempfile.TemporaryDirectory() as tmp:
        pkg, work, extracted = _extracted_in_cwd(tmp)
        reqs = _pinned_requirements(tmp)
        with _patched(fv, "PACKAGE_FIXTURES", pkg), _cwd(work):
            code, out = _run(id="tiny", requirements=reqs,
                             assets_dir=os.path.join(tmp, "assets"))
        flat = " ".join(out.split())
        assert code == 2, (code, out)
        assert "(the installed package)" in out, out
        assert ("that is the release asset extracted there, not the "
                "fixture") in flat, out
        assert f"an extracted asset is at {os.path.normpath(extracted)}" \
            in flat, out


def test_without_a_package_copy_the_extracted_asset_is_still_named():
    """0.1.0rc1's `error: no MANIFEST.sha256 in fixtures\\arxiv-150k`."""
    with tempfile.TemporaryDirectory() as tmp:
        _pkg, work, _extracted = _extracted_in_cwd(tmp)
        nothing = os.path.join(tmp, "no-package-copy")
        os.makedirs(nothing)
        reqs = _pinned_requirements(tmp)
        with _patched(fv, "PACKAGE_FIXTURES", nothing), _cwd(work):
            code, out = _run(id="tiny", requirements=reqs,
                             assets_dir=os.path.join(tmp, "assets"))
        flat = " ".join(out.split())
        assert code == 2, (code, out)
        assert "fixture      MISSING" in out, out
        assert ("that is the release asset extracted there, not the "
                "fixture") in flat, out
        assert "error:" not in out, out


def test_the_environment_line_states_the_virtual_environment_requirement():
    """It says so; it does not refuse. Whether a system interpreter should be
    refused outright is an open question for after the release."""
    kw = dict(fixture_id="fx", found=None, looked=[], spec={},
              pins={"numpy": "1"}, pin_source="x", pin_looked=[],
              unpinned=[], allow_unpinned=False, assets_dir="nowhere",
              versions={"numpy": "1"})
    env = {p["key"]: p for p in
           fv.check_preconditions(in_venv=False, **kw)}["environment"]
    text = " ".join(env["lines"])
    assert "SYSTEM INTERPRETER: a virtual environment is required." in text
    assert "replaces the versions" in text
    assert env["met"] is True and env["state"] == "pinned", env
    env = {p["key"]: p for p in
           fv.check_preconditions(in_venv=True, **kw)}["environment"]
    assert "in a virtual environment" in env["lines"], env
