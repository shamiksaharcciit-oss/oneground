"""`oneground.bridge.import_result`. docs/BRIDGE.md §4, §8.

Fixtures below are shaped like real `vectordb-bench==2.0.0` output --
checked against `TestResult`/`CaseResult`/`Metric` in the package's own
source and against real files under its `results/*/result_*.json`, not
guessed. A `composite_score` key is injected into one fixture's `metrics`
deliberately: nothing in a real VectorDBBench file ever carries one (the
importer's own docstring explains why), so this is a synthetic mutant
proving the importer would exclude it if some future format ever did.

    python oneground/bridge/test_import_result.py
    pytest oneground/bridge/test_import_result.py
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.bridge import import_result as bi          # noqa: E402
from oneground.comparability import Provenance             # noqa: E402


def _case(label=bi.RESULT_LABEL_NORMAL, db="Milvus", version="2.6.14",
         qps=3917.2035, recall=0.9203, concurrency_timeout=3600,
         extra_metrics=None):
    metrics = {
        "max_load_count": 0, "insert_duration": 1444.847,
        "optimize_duration": 7859.1353, "load_duration": 9303.9823,
        "qps": qps, "serial_latency_p99": 0.0024, "serial_latency_p95": 0.0023,
        "serial_latency_p50": 0.0021, "recall": recall, "ndcg": 0.9238,
    }
    if extra_metrics:
        metrics.update(extra_metrics)
    return {
        "metrics": metrics,
        "task_config": {
            "db": db,
            "db_config": {"version": version},
            "case_config": {
                "case_id": 4,
                "concurrency_search_config": {
                    "num_concurrency": [1, 5, 10],
                    "concurrency_timeout": concurrency_timeout,
                },
            },
            "stages": ["drop_old", "load", "search_serial",
                      "search_concurrent"],
        },
        "label": label,
    }


def _result_file(path, cases, run_id="run-1"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "task_label": "standard",
                  "results": cases}, f)


# ---------------------------------------------- raw numbers, never composite
def test_a_normal_case_imports_its_raw_numbers():
    row = bi.import_case(_case())
    assert row["outcome"] == bi.MEASURED
    assert row["metrics"]["qps"] == 3917.2035
    assert row["metrics"]["recall"] == 0.9203
    assert row["engine"] == "Milvus"
    assert row["engine_version"] == "2.6.14"


def test_a_composite_score_field_is_never_imported():
    """The mutant: VectorDBBench never writes this key in a real file, so
    this proves the importer names its fields rather than copying the
    whole `metrics` dict -- which is what would let a composite score
    through if one were ever added beside the raw numbers."""
    row = bi.import_case(_case(extra_metrics={
        "composite_score": 0.87, "QP$ (Quries per Dollar)": 12.4}))
    assert "composite_score" not in row["metrics"]
    assert "QP$ (Quries per Dollar)" not in row["metrics"]
    assert row["metrics"]["qps"] == 3917.2035


def test_vectordbbench_version_and_host_are_null_with_a_reason():
    row = bi.import_case(_case())
    assert row["vectordbbench_version"] is None
    assert "not recorded" in row["vectordbbench_version_reason"]
    assert row["host"] is None
    assert "not recorded" in row["host_reason"]


# ----------------------------------------------------- failure and timeout
def test_a_failed_case_imports_as_couldnt_check_not_a_number():
    row = bi.import_case(_case(label=bi.RESULT_LABEL_FAILED))
    assert row["outcome"] == bi.COULDNT_CHECK
    assert "not classify as a timeout" in row["reason"]
    assert "metrics" not in row


def test_a_timed_out_case_names_the_configured_timeout():
    row = bi.import_case(_case(label=bi.RESULT_LABEL_OUTOFRANGE,
                               concurrency_timeout=1800))
    assert row["outcome"] == bi.COULDNT_CHECK
    assert "timeout" in row["reason"]
    assert row["configured_concurrency_timeout"] == 1800


def test_a_timeout_with_no_recorded_concurrency_config_is_null_not_guessed():
    case = _case(label=bi.RESULT_LABEL_OUTOFRANGE)
    del case["task_config"]["case_config"]["concurrency_search_config"]
    row = bi.import_case(case)
    assert row["configured_concurrency_timeout"] is None


# --------------------------------------------------------------- the file
def test_reading_a_result_file_imports_every_case():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "result_20260924_standard_milvus.json")
        _result_file(path, [_case(), _case(label=bi.RESULT_LABEL_FAILED)])
        result = bi.read_result_file(path)
        assert result["run_id"] == "run-1"
        assert len(result["cases"]) == 2
        assert result["cases"][0]["outcome"] == bi.MEASURED
        assert result["cases"][1]["outcome"] == bi.COULDNT_CHECK


def test_a_missing_file_is_refused_named():
    with pytest.raises(bi.BridgeImportError, match="no such file"):
        bi.read_result_file("/does/not/exist.json")


def test_a_file_not_shaped_like_a_test_result_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "not-a-result.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"some": "other", "shape": True}, f)
        with pytest.raises(bi.BridgeImportError, match="not shaped like"):
            bi.read_result_file(path)


def test_invalid_json_is_refused_named():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "broken.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        with pytest.raises(bi.BridgeImportError, match="not valid JSON"):
            bi.read_result_file(path)


# ------------------------------------------------------------ the card
def _card(gt_sha="gtsha", qs_sha="qssha", req_sha="reqsha"):
    return {
        "gt_file": "neighbors.parquet",
        "files": {"neighbors.parquet": gt_sha, "test.parquet": "tsha",
                 "train.parquet": "trsha"},
        "query_subset": {"sha256": qs_sha, "seed": 1, "size": 20},
        "requirements_file": {"sha256": req_sha},
    }


def test_provenance_from_card_reads_the_ground_truth_and_query_subset_digests():
    prov = bi.provenance_from_card(_card())
    assert prov.measured["ground_truth"] == "gtsha"
    assert prov.measured["query_subset"] == "qssha"
    assert prov.measured["sample"] == "reqsha"


def test_provenance_from_card_refuses_a_card_missing_the_ground_truth_digest():
    card = _card()
    del card["files"]["neighbors.parquet"]
    with pytest.raises(bi.BridgeImportError, match="does not carry a digest"):
        bi.provenance_from_card(card)


# --------------------------------------------- the table rule, at construction
def test_two_rows_with_matching_provenance_assemble():
    prov = bi.provenance_from_card(_card())
    rows = [({"a": 1}, prov), ({"a": 2}, prov)]
    assert bi.assemble_table(rows) == [{"a": 1}, {"a": 2}]


def test_a_single_row_needs_no_comparison():
    prov = bi.provenance_from_card(_card())
    assert bi.assemble_table([({"a": 1}, prov)]) == [{"a": 1}]


def test_matching_bridge_rows_assemble_despite_carrying_no_measuring_facts():
    """The mutant for why this module does not reuse
    `oneground.comparability.rows_may_share_a_table` directly: that
    function also requires the `measuring` axis (oneground's own code,
    libraries, platform) to agree, and a bridge row has none of that --
    it was measured by VectorDBBench, not by oneground. Two bridge rows
    that agree on all three of §4's own keys must still assemble; if this
    ever regresses to using the broader function, every bridge table
    would refuse and this test would catch it."""
    from oneground.comparability import rows_may_share_a_table
    prov = bi.provenance_from_card(_card())
    assert rows_may_share_a_table(prov, prov)["verdict"] != "comparable", (
        "if this starts passing, the broader function no longer penalises "
        "an empty `measuring` half and assemble_table's own rule may be "
        "safe to simplify -- until then it must stay independent")
    assert bi.assemble_table([({"a": 1}, prov), ({"a": 2}, prov)]) == \
        [{"a": 1}, {"a": 2}]


def test_rows_with_a_different_ground_truth_refuse_construction():
    """The mutant: two rows, one field of provenance disagreeing (the
    ground truth digest), proves the refusal fires rather than silently
    building a table anyway."""
    left = bi.provenance_from_card(_card())
    right = bi.provenance_from_card(_card(gt_sha="a-different-gtsha"))
    with pytest.raises(bi.TableConstructionError,
                       match="ground_truth"):
        bi.assemble_table([({"a": 1}, left), ({"a": 2}, right)])


def test_rows_with_a_different_query_subset_refuse_construction():
    left = bi.provenance_from_card(_card())
    right = bi.provenance_from_card(_card(qs_sha="a-different-qssha"))
    with pytest.raises(bi.TableConstructionError):
        bi.assemble_table([({"a": 1}, left), ({"a": 2}, right)])


def test_a_row_with_unknown_query_subset_provenance_also_refuses():
    """`couldnt_check` is not a green light either -- a table this
    function cannot vouch for is not one it builds."""
    left = bi.provenance_from_card(_card())
    right = Provenance(measured={"sample": "reqsha", "ground_truth": "gtsha",
                                 "query_subset": None},
                       measuring={})
    with pytest.raises(bi.TableConstructionError):
        bi.assemble_table([({"a": 1}, left), ({"a": 2}, right)])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
