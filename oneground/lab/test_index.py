"""Many runs: the index the run list draws (task 041, step 3).

The index is transport. The line it must not cross is computing something a
view draws, so these tests are mostly about what it does NOT do: it does not
tally outcomes, does not cast a declared corpus size to a number, does not
hide a run whose digests fail, and does not report an unreadable receipt as an
absent one.
"""
import json
import os
import shutil
import tempfile

import pytest

from oneground.lab import runs as R
from oneground.lab import server

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL = os.path.join(REPO, "runs", "041-ui")


def _index(d):
    return R.index_runs(d, verifier=server.verify_manifests)


def _by_name(ix):
    return {r["name"]: r for r in ix["runs"]}


# ------------------------------------------------------------------ synthetic
def _workdir(root, name, receipts, manifest=True):
    d = os.path.join(root, name)
    os.makedirs(d)
    for fname, body in receipts.items():
        with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
            if isinstance(body, str):
                f.write(body)
            else:
                json.dump(body, f)
    if manifest:
        import hashlib
        lines = []
        for fname in receipts:
            with open(os.path.join(d, fname), "rb") as f:
                lines.append(f"{hashlib.sha256(f.read()).hexdigest()}  {fname}")
        with open(os.path.join(d, "MANIFEST.sha256"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return d


def test_only_directories_holding_a_receipt_are_listed_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp, "a-run", {"characterization.json": {"run": "a"}})
        os.makedirs(os.path.join(tmp, "notes"))
        with open(os.path.join(tmp, "notes", "readme.txt"), "w") as f:
            f.write("not a run")
        with open(os.path.join(tmp, "loose.json"), "w") as f:
            f.write("{}")
        assert [r["name"] for r in _index(tmp)["runs"]] == ["a-run"]


def test_a_run_whose_digest_fails_is_listed_and_named_synthetic():
    """Never hidden and never shown as sound: a run the reader cannot trust
    is exactly the run they most need to see."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _workdir(tmp, "tampered",
                     {"characterization.json": {"run": "t", "n_base": 10},
                      "simulate.json": {"run": "t", "rows": []}})
        with open(os.path.join(d, "simulate.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"run": "t", "rows": [{"config": "x"}]}, f)
        row = _by_name(_index(tmp))["tampered"]
        assert row["manifest"]["all_verified"] is False
        assert row["manifest"]["failing"] == ["simulate.json"]
        assert row["stages"]["simulate"] is True, "still listed, not hidden"


def test_a_run_with_no_manifest_is_couldnt_check_not_false_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp, "bare", {"characterization.json": {"run": "b"}},
                 manifest=False)
        m = _by_name(_index(tmp))["bare"]["manifest"]
        assert m["present"] is False
        assert m["all_verified"] is None, "absent is not the same as failing"
        assert "couldnt_check" in (m["note"] or "")


def test_an_unreadable_receipt_is_not_reported_as_an_absent_one_synthetic():
    """A corrupt report.json must not make a run look like one that never
    reported: those are different facts and lead to different actions."""
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp, "corrupt",
                 {"characterization.json": {"run": "c"},
                  "report.json": "{not json at all"})
        row = _by_name(_index(tmp))["corrupt"]
        assert row["stages"]["report"] is False
        assert any("report.json unreadable" in p for p in row["problems"])


def test_the_index_does_not_tally_outcomes_synthetic():
    """Counting recorded outcomes is drawing a measurement, and a number on
    the page has to have come from a view."""
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp, "t2", {
            "characterization.json": {"run": "t2"},
            "report.json": {"oneground_report": 1, "tier": 2,
                            "kind": "declared", "recommended": None,
                            "recommendation_reason": "Tier 2 issues none.",
                            "constraints": [{"outcome": "couldnt_check"},
                                            {"outcome": "couldnt_check"}]}})
        rep = _by_name(_index(tmp))["t2"]["report"]
        assert rep["outcomes"] == ["couldnt_check", "couldnt_check"]
        assert rep["summary"] is None
        assert "count" not in rep and "n_couldnt_check" not in rep


def test_a_version_absent_is_a_reason_not_a_blank_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _workdir(tmp, "old", {"characterization.json": {"run": "o"}})
        v = _by_name(_index(tmp))["old"]["version"]
        assert v["version"] is None
        assert "task 033" in v["reason"] and v["reason"].startswith(
            "couldnt_check")


def test_a_directory_that_is_not_one_is_refused_synthetic():
    with pytest.raises(R.LabRunError):
        _index(os.path.join(tempfile.gettempdir(), "no-such-runs-dir-041"))


# ----------------------------------------------------------------- real runs
def _local():
    if not os.path.isdir(LOCAL):
        pytest.skip("no local runs/041-ui; see tasks/041-interface-read.md")
    return _index(LOCAL)


def test_the_four_local_runs_are_listed_with_their_stages():
    rows = _by_name(_local())
    assert {"acme-existing", "arxiv-150k-via-characterize", "arxiv-smoke",
            "support-tickets-2026q3"} <= set(rows)
    # a run that stopped before simulate is listed as such, not omitted
    assert rows["acme-existing"]["stages"] == {
        "characterize": True, "simulate": False, "verify": True,
        "report": False}
    assert all(s for s in
               rows["arxiv-150k-via-characterize"]["stages"].values())


def test_a_declared_corpus_size_is_carried_across_not_cast():
    """Tier 2 records `n_base` as a couldnt_check sentence rather than a
    number. Casting it would turn "not measured" into a measurement."""
    row = _by_name(_local())["support-tickets-2026q3"]
    assert isinstance(row["n_base"], str)
    assert row["n_base"].startswith("couldnt_check")


def test_both_report_tiers_arrive_in_one_shape():
    rows = _by_name(_local())
    t1 = rows["arxiv-150k-via-characterize"]["report"]
    t2 = rows["support-tickets-2026q3"]["report"]
    assert t1["tier"] == 1 and t2["tier"] == 2
    assert t1["summary"] and t1["n_claims"] > 0
    # Tier 2 has no claims and no summary, and says its own headline
    assert t2["summary"] is None and t2["n_claims"] == 0
    assert "guess wearing a verdict's clothes" in t2["headline"]
    assert set(t1) == set(t2), "the view draws one shape, not two"


def test_a_run_with_no_report_has_none_and_is_still_listed():
    row = _by_name(_local())["acme-existing"]
    assert row["report"] is None
    assert row["stages"]["characterize"] is True


def test_every_local_run_verifies_against_its_manifest():
    for row in _local()["runs"]:
        assert row["manifest"]["all_verified"] is True, (
            row["name"], row["manifest"]["failing"])
