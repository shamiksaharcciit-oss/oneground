"""Tier 2: a corpus described rather than sampled.

The property under test throughout: **a declaration never becomes a
measurement.** Every measured field comes back couldnt_check, `build_info`
says declared, and nothing in the workdir claims to be a receipt.

    python oneground/intake/test_tier2.py
    pytest oneground/intake/test_tier2.py
"""

import json
import os
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import characterize as ch          # noqa: E402
from oneground import intake                      # noqa: E402


def _declared(**over):
    d = {"kind": "declared", "size_now": 2100000, "dimension": 768,
         "embedding_model": "BAAI/bge-base-en-v1.5",
         "corpus_type": "support_tickets", "text_length": "short",
         "topics_trend": True, "time_ordered": True,
         "languages": ["en"], "nearest_fixture": "auto"}
    d.update(over)
    return {k: v for k, v in d.items() if v is not _ABSENT}


class _Absent:
    pass


_ABSENT = _Absent()


def _write(tmp, corpus, name="r.yaml"):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump({"oneground": 1,
                        "run": {"name": "t", "seed": 1,
                                "workdir": "./runs/t"},
                        "corpus": corpus}, f)
    return p


# ------------------------------------------------------------------ intake
def test_a_declared_only_file_loads_as_tier_2():
    with tempfile.TemporaryDirectory() as tmp:
        req = intake.load(_write(tmp, {"declared": _declared()}))
        assert req.tier == 2
        assert req.declared["size_now"] == 2100000
        assert not req.sample


def test_a_sample_wins_over_a_declaration():
    """A measurement always beats a description, so a file with both is
    Tier 1."""
    with tempfile.TemporaryDirectory() as tmp:
        vec = os.path.join(tmp, "v.npy")
        import numpy as np
        np.save(vec, np.zeros((4, 3), dtype=np.float32))
        p = _write(tmp, {
            "declared": _declared(),
            "sample": {"kind": "receipt", "vectors": {"path": vec},
                       "queries": {"path": vec, "count_min": 1}}})
        assert intake.load(p).tier == 1


def test_size_now_and_dimension_are_required():
    for missing in ("size_now", "dimension"):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, {"declared": _declared(**{missing: _ABSENT})})
            try:
                intake.load(p)
            except intake.RequirementsError as e:
                assert f"corpus.declared.{missing}" in str(e), e
            else:
                raise AssertionError(f"{missing} was not required")


def test_a_nonsense_size_is_refused_rather_than_coerced():
    for value in (0, -1, "lots"):
        with tempfile.TemporaryDirectory() as tmp:
            p = _write(tmp, {"declared": _declared(size_now=value)})
            try:
                intake.load(p)
            except intake.RequirementsError as e:
                assert "size_now" in str(e), e
            else:
                raise AssertionError(f"size_now {value!r} was accepted")


def test_an_unknown_text_length_is_refused():
    """It is matched against the fixtures' own declared lengths, so a value
    outside that set can only match by accident."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, {"declared": _declared(text_length="smallish")})
        try:
            intake.load(p)
        except intake.RequirementsError as e:
            assert "text_length" in str(e) and "short" in str(e), e
        else:
            raise AssertionError("an unknown text_length was accepted")


def test_a_file_caught_between_the_tiers_is_refused():
    """Tier-1 fields outside corpus.sample would be silently ignored."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, {"declared": _declared(),
                         "vectors": {"path": "./v.npy"}})
        try:
            intake.load(p)
        except intake.RequirementsError as e:
            assert "corpus.vectors" in str(e), e
            assert "corpus.sample" in str(e), e
        else:
            raise AssertionError("a half-Tier-1 file was accepted")


def test_neither_sample_nor_declared_names_both():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, {})
        try:
            intake.load(p)
        except intake.RequirementsError as e:
            assert "corpus.sample" in str(e) and "corpus.declared" in str(e), e
        else:
            raise AssertionError("an empty corpus was accepted")


# ------------------------------------------------------------ characterize
def _run(tmp, **over):
    p = _write(tmp, {"declared": _declared(**over)})
    wd = ch.run(p, log_fn=lambda *a, **k: None)
    with open(os.path.join(wd, "characterization.json"), encoding="utf-8") as f:
        charj = json.load(f)
    with open(os.path.join(wd, "build_info.json"), encoding="utf-8") as f:
        bi = json.load(f)
    return wd, charj, bi


def test_every_measured_field_is_couldnt_check():
    """The property this tier exists to hold."""
    with tempfile.TemporaryDirectory() as tmp:
        _wd, charj, _bi = _run(tmp)
        assert charj["tier"] == 2
        assert charj["kind"] == "declared"
        for field in ch.MEASURED_FIELDS:
            value = charj["characterization"][field]
            assert isinstance(value, str), (field, value)
            assert value.startswith("couldnt_check"), (field, value)
            assert "declared, not measured" in value, (field, value)


def test_no_measured_field_is_simply_absent():
    """An absent field reads as an oversight; one that says why it is empty
    reads as a boundary."""
    with tempfile.TemporaryDirectory() as tmp:
        _wd, charj, _bi = _run(tmp)
        assert set(charj["characterization"]) == set(ch.MEASURED_FIELDS)


def test_the_declared_block_echoes_the_inputs_verbatim():
    with tempfile.TemporaryDirectory() as tmp:
        _wd, charj, _bi = _run(tmp)
        assert charj["declared"]["size_now"] == 2100000
        assert charj["declared"]["dimension"] == 768
        assert charj["declared"]["corpus_type"] == "support_tickets"
        assert charj["declared"]["languages"] == ["en"]


def test_the_sample_size_is_not_the_declared_size():
    """`n_base` is the size of a sample, and there is no sample. Filling it
    from `size_now` would turn a declaration into a measurement in the one
    field a reader is most likely to trust."""
    with tempfile.TemporaryDirectory() as tmp:
        _wd, charj, _bi = _run(tmp)
        for field in ("n_base", "n_queries", "dimension"):
            assert charj[field].startswith("couldnt_check"), field
        assert charj["declared"]["dimension"] == 768


def test_build_info_says_declared_for_everything():
    """Nothing here is re-derivable from a seed and a rule, which is what
    would make it a receipt."""
    with tempfile.TemporaryDirectory() as tmp:
        _wd, _charj, bi = _run(tmp)
        assert bi["tier"] == 2
        assert set(bi["kind"].values()) == {"declared"}, bi["kind"]
        assert bi["source_kind"] == "declared"
        assert bi["weights_sha256"] is None
        assert bi["inputs"] == {}


def test_no_sample_ids_are_written_because_nothing_was_sampled():
    with tempfile.TemporaryDirectory() as tmp:
        wd, _charj, _bi = _run(tmp)
        for name in ("sample_ids.json", "queries_ids.json", "projection.npy"):
            assert not os.path.exists(os.path.join(wd, name)), name


def test_the_manifest_lists_what_was_written():
    with tempfile.TemporaryDirectory() as tmp:
        wd, _charj, _bi = _run(tmp)
        with open(os.path.join(wd, "MANIFEST.sha256"), encoding="utf-8") as f:
            listed = {ln.split()[-1] for ln in f if ln.strip()}
        assert listed == {"characterization.json", "build_info.json"}, listed


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
    print(f"\n{len(tests) - failed} passed, {failed} failed "
          f"(of {len(tests)} collected)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())


# ------------------------------------------------------------------ report
def _report(tmp, **over):
    from oneground import report as rep
    p = _write(tmp, {"declared": _declared(**over)})
    # A Tier-2 report needs constraints to name; they all come back
    # couldn't-check, which is the property under test.
    data = yaml.safe_load(open(p, encoding="utf-8"))
    data["constraints"] = {"kind": "declared",
                           "recall_at_k": {"k": 10, "min": 0.9},
                           "storage_amplification_max": 2.0,
                           "memory_budget_gb": 64,
                           "latency": {"p95_ms": 40, "at_qps": 200,
                                       "concurrency": 32}}
    data["simulate"] = {"kind": "declared",
                        "families": ["single_node_hnsw", "semantic_sharded"]}
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(data, f)
    ch.run(p, log_fn=lambda *a, **k: None)
    wd = rep.run(p, log_fn=lambda *a, **k: None)
    with open(os.path.join(wd, "report.json"), encoding="utf-8") as f:
        return json.load(f)


def test_a_tier_2_report_issues_no_verdict_at_all():
    """The tier's whole reason for existing."""
    with tempfile.TemporaryDirectory() as tmp:
        r = _report(tmp)
        assert r["tier"] == 2
        assert r["recommended"] is None
        assert r["options"] == []
        assert r["constraints"], "no constraints were named at all"
        for c in r["constraints"]:
            assert c["outcome"] == "couldnt_check", c
            assert "declared it rather than sampling it" in c["reason"], c


def test_a_tier_2_report_never_says_meets_or_fails():
    with tempfile.TemporaryDirectory() as tmp:
        blob = json.dumps(_report(tmp))
        for word in ('"meets"', '"fails"'):
            assert word not in blob, word


def test_the_analogy_is_labelled_wherever_the_fixtures_numbers_appear():
    with tempfile.TemporaryDirectory() as tmp:
        r = _report(tmp, corpus_type="papers", text_length="medium")
        a = r["analogy"]
        assert a["chosen"] is not None, a["why"]
        assert a["chosen"]["fixture"] == "arxiv-150k"
        assert "not on your corpus" in a["label"]
        # The block-level note says the same thing at more length; assert what
        # it must convey rather than the exact words of one phrasing.
        assert "measured on the fixture" in a["note"]
        assert "None of it was measured on your corpus" in a["note"]
        assert a["fixture_characterization"], a
        # Every fixture value sits under a fixture_* key, never beside the
        # user's own declared numbers.
        for key in a["fixture_characterization"]:
            assert key not in r["declared"], key


def test_no_analogy_is_reported_with_its_reason():
    with tempfile.TemporaryDirectory() as tmp:
        r = _report(tmp)                     # support_tickets: no match
        assert r["analogy"]["chosen"] is None
        assert "default, not an analogy" in r["analogy"]["why"]


def test_the_last_log_entry_says_what_would_make_this_measurable():
    with tempfile.TemporaryDirectory() as tmp:
        r = _report(tmp)
        last = r["decision_log"][-1]
        assert last["kind"] == "to_resolve", last
        text = last["text"]
        assert "corpus.sample" in text
        assert "10,000-20,000 vectors" in text
        assert "50 or more real queries" in text
        assert "timestamp" in text
        # latency and qps need more than a sample, and the entry says so.
        assert "verify.target: runpod" in text, text


def test_the_capacity_block_is_labelled_derived_from_declared():
    with tempfile.TemporaryDirectory() as tmp:
        r = _report(tmp)
        cap = r["capacity"]
        assert cap["kind"] == "derived_from_declared"
        assert "No verdict" in cap["note"]
        for family, e in cap["families"].items():
            assert e["kind"] == "derived_from_declared", family


def test_a_tier_1_workdir_under_a_tier_2_file_is_refused():
    """The workdir and the requirements must describe the same run."""
    from oneground import report as rep
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, {"declared": _declared()})
        wd = os.path.join(tmp, "runs", "t")
        os.makedirs(wd, exist_ok=True)
        with open(os.path.join(wd, "characterization.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"run": "t", "characterization": {}}, f)   # no tier
        try:
            rep.run(p, log_fn=lambda *a, **k: None)
        except rep.ReportError as e:
            assert "Tier-1 characterization" in str(e), e
        else:
            raise AssertionError("a mismatched workdir was accepted")
