"""End-to-end tests for `oneground characterize`, on synthetic .npy inputs.

**Synthetic data throughout** — these check the command's contract, not any
published number: that it writes the four receipts and a manifest, that the
manifest verifies, that couldn't-check is reported rather than filled in, and
that the intake refuses a bad requirements file by naming the field.

    python oneground/test_characterize.py
    pytest oneground/test_characterize.py
"""

import io
import json
import os
import sys
import tempfile

import numpy as np
import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground import characterize, intake  # noqa: E402
from oneground.fixture import verify as fv  # noqa: E402

SEED = 20260910


def _quiet(msg):
    pass


def _write_corpus(tmp, n=2000, dim=64, n_queries=100, seed=SEED):
    """A 2k synthetic corpus with three blobs, plus queries drawn from it."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(3, dim))
    x = np.vstack([c + rng.normal(0, 0.15, size=(n // 3 + 1, dim))
                   for c in centres])[:n].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    q = x[rng.choice(n, size=n_queries, replace=False)].copy()

    vec_p = os.path.join(tmp, "vectors.npy")
    q_p = os.path.join(tmp, "queries.npy")
    np.save(vec_p, x.astype(np.float32))
    np.save(q_p, q.astype(np.float32))
    return vec_p, q_p


def _write_req(tmp, vec_p, q_p, **over):
    req = {
        "oneground": 1,
        "run": {"name": "synthetic", "seed": SEED,
                "workdir": os.path.join(tmp, "out")},
        "corpus": {"sample": {
            "kind": "receipt",
            "vectors": {"path": vec_p, "normalized": True},
            "queries": {"path": q_p, "count_min": 50},
            "target_sample_size": 2000,
        }},
    }
    for k, v in over.items():
        if v is None:
            req["corpus"]["sample"].pop(k, None)
        else:
            req["corpus"]["sample"][k] = v
    p = os.path.join(tmp, "requirements.yaml")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(req, f, sort_keys=False)
    return p


def _run(req_path):
    buf, orig = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        wd = characterize.run(req_path, log_fn=_quiet)
    finally:
        sys.stdout = orig
    return wd, buf.getvalue()


# ------------------------------------------------------------ end to end
def test_characterize_writes_the_receipts_and_a_manifest_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _write_req(tmp, *_write_corpus(tmp))
        wd, out = _run(req)
        for name in ("characterization.json", "build_info.json",
                     "sample_ids.json", "queries_ids.json", "MANIFEST.sha256"):
            assert os.path.exists(os.path.join(wd, name)), name


def test_the_manifest_it_writes_actually_verifies_synthetic():
    """The product path's receipts must pass the same verifier the fixture
    path's do -- that is the point of them being the same shape."""
    with tempfile.TemporaryDirectory() as tmp:
        req = _write_req(tmp, *_write_corpus(tmp))
        wd, _ = _run(req)
        entries = fv.read_manifest(os.path.join(wd, "MANIFEST.sha256"))
        assert len(entries) == 4, entries
        for digest, name in entries:
            got = fv.sha256_file(os.path.join(wd, name))
            assert got == digest, f"{name}: manifest {digest}, file {got}"


def test_values_are_in_range_and_the_definitions_are_recorded_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _write_req(tmp, *_write_corpus(tmp))
        wd, _ = _run(req)
        with open(os.path.join(wd, "characterization.json"),
                  encoding="utf-8") as f:
            d = json.load(f)
        ch = d["characterization"]
        assert 0.0 <= ch["boundary_crispness"] <= 1.0
        assert 0.0 <= ch["skew_top10_share"] <= 1.0
        assert ch["intrinsic_dimensionality"] > 0
        # NOT "three separated blobs so crispness is high": the definition
        # fixes 256 centroids, so 2,000 points in 3 blobs are cut into ~85
        # sub-regions per blob and most points land near a sub-region
        # boundary. Measured 0.23 here. The property worth asserting is that
        # over-partitioning *lowers* crispness relative to a partition that
        # matches the structure -- which is the same effect that makes
        # arxiv-150k's 0.036 mean what it does.
        from oneground.measures import boundary_crispness, centroid_dists, kmeans
        x = np.load(os.path.join(tmp, "vectors.npy"))
        d3, _ = centroid_dists(x, kmeans(x, 3, SEED), 2)
        matched = boundary_crispness(d3)
        assert matched > ch["boundary_crispness"], (
            f"3 centroids over 3 blobs gave {matched}, 256 gave "
            f"{ch['boundary_crispness']}; over-partitioning should lower it")
        assert matched > 0.9, f"3 centroids over 3 tight blobs: {matched}"
        assert d["definitions"] == {"centroids": 256, "crispness_ratio": 1.2,
                                    "ambiguity_ratio": 1.1, "seed": SEED}
        assert d["n_base"] == 2000 and d["dimension"] == 64


def test_sample_ids_record_which_rows_were_measured_synthetic():
    """A characterization of a subsample is only a receipt if it says which
    rows it drew."""
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p = _write_corpus(tmp)
        req = _write_req(tmp, vec_p, q_p, target_sample_size=500)
        wd, _ = _run(req)
        with open(os.path.join(wd, "sample_ids.json"), encoding="utf-8") as f:
            ids = json.load(f)
        assert len(ids) == 500
        assert len(set(ids)) == 500, "the draw repeated a row"
        assert ids == sorted(ids), "sample_ids should be a stable sorted slice"


def test_the_same_seed_twice_gives_the_same_sample_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p = _write_corpus(tmp)
        first = json.load(open(os.path.join(
            _run(_write_req(tmp, vec_p, q_p, target_sample_size=400))[0],
            "sample_ids.json"), encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp2:
        vec_p, q_p = _write_corpus(tmp2)
        second = json.load(open(os.path.join(
            _run(_write_req(tmp2, vec_p, q_p, target_sample_size=400))[0],
            "sample_ids.json"), encoding="utf-8"))
    assert first == second


# --------------------------------------------------------- couldnt-check
def test_drift_is_couldnt_check_without_a_timestamp_field_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        req = _write_req(tmp, *_write_corpus(tmp))
        wd, _ = _run(req)
        with open(os.path.join(wd, "characterization.json"),
                  encoding="utf-8") as f:
            ch = json.load(f)["characterization"]
        assert isinstance(ch["drift"], str)
        assert ch["drift"].startswith("couldnt_check")
        assert "timestamp_field" in ch["drift"]


def test_ambiguity_is_couldnt_check_below_count_min_and_names_the_count_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        vec_p, q_p = _write_corpus(tmp, n_queries=12)
        req = _write_req(tmp, vec_p, q_p)
        wd, _ = _run(req)
        with open(os.path.join(wd, "characterization.json"),
                  encoding="utf-8") as f:
            ch = json.load(f)["characterization"]
        a = ch["ambiguous_query_rate"]
        assert isinstance(a, str) and a.startswith("couldnt_check")
        assert "12" in a and "50" in a, a


def test_summary_never_says_reproduced_synthetic():
    """Nothing is being reproduced by `characterize` -- there is no published
    value to compare a first measurement against."""
    with tempfile.TemporaryDirectory() as tmp:
        req = _write_req(tmp, *_write_corpus(tmp))
        _, out = _run(req)
        assert "reproduc" not in out.lower(), out


# ---------------------------------------------------------------- intake
def _expect_refusal(tmp, mutate, must_name):
    vec_p, q_p = _write_corpus(tmp, n=200, n_queries=60)
    p = _write_req(tmp, vec_p, q_p)
    with open(p, encoding="utf-8") as f:
        d = yaml.safe_load(f)
    mutate(d)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(d, f, sort_keys=False)
    try:
        intake.load(p)
    except intake.RequirementsError as e:
        assert must_name in str(e), f"{must_name!r} not named in: {e}"
        return
    raise AssertionError(f"a file missing {must_name} was accepted")


def test_intake_refuses_text_without_a_model_and_names_the_field_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        def mutate(d):
            s = d["corpus"]["sample"]
            s.pop("vectors")
            s["text"] = {"path": "x.jsonl", "text_field": "text"}
        _expect_refusal(tmp, mutate, "corpus.sample.text.model")


def test_intake_refuses_a_missing_sample_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _expect_refusal(tmp, lambda d: d["corpus"].pop("sample"),
                        "corpus.sample")


def test_intake_refuses_missing_queries_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _expect_refusal(tmp,
                        lambda d: d["corpus"]["sample"].pop("queries"),
                        "corpus.sample.queries.path")


def test_intake_refuses_a_missing_seed_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _expect_refusal(tmp, lambda d: d["run"].pop("seed"), "run.seed")


def test_intake_accepts_tier_2_and_marks_it_synthetic():
    """Tier 2 was refused as "not implemented" until task 013. It is now
    validated and carried, and it still never produces a verdict -- that
    property is tested in oneground/intake/test_tier2.py, which owns it."""
    with tempfile.TemporaryDirectory() as tmp:
        import yaml as _yaml
        p = os.path.join(tmp, "r.yaml")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            _yaml.safe_dump({"oneground": 1,
                             "run": {"name": "t", "seed": 1,
                                     "workdir": "./runs/t"},
                             "corpus": {"declared": {"size_now": 100,
                                                     "dimension": 8}}}, f)
        req = intake.load(p)
        assert req.tier == 2
        assert req.declared["size_now"] == 100


def test_intake_refuses_both_vectors_and_text_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        def mutate(d):
            d["corpus"]["sample"]["text"] = {"path": "x.jsonl",
                                             "model": "some/model"}
        _expect_refusal(tmp, mutate, "both set")


def _main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
