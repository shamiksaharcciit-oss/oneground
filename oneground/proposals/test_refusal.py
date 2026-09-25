"""`oneground.proposals.refusal`. `docs/TRIAGE.md` §7's first item.

Synthetic throughout, the same shape `test_propose.py` uses: a small
corpus is characterized and simulated once, and every refusal here is
produced by the real `propose.run`, not constructed by hand.
"""

import json
import os
import sys

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from oneground import characterize, simulate                    # noqa: E402
from oneground.proposals import propose                         # noqa: E402
from oneground.proposals import refusal as R                    # noqa: E402
from oneground.simulate import test_simulate as ts              # noqa: E402

BASE = {"centroids": 8, "epsilon": 0.1, "probe": 1, "M": 16, "efSearch": 64}

PREDICTION = {"expects": [{"metric": "recall_at_10", "direction": "rises",
                           "by_at_least": 0.02}],
              "side_effects": [{"metric": "storage_amplification",
                                "stays_at_or_below": 4.0}]}


def _write(path, doc):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(doc, f, sort_keys=False)
    return path


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("refusal"))
    vp, qp = ts._corpus(tmp)
    block = {"kind": "declared", "families": ["semantic_sharded"],
             "ground_truth_k": 20,
             "include": [dict(BASE, family="semantic_sharded")],
             "grid": {"semantic_sharded": {
                 "centroids": [8], "epsilon": [0.1], "probe": [1],
                 "M": [16], "efSearch": [64]}}}
    req = ts._req(tmp, vp, qp, block)
    ts._capture(characterize.run, req, log_fn=ts._quiet)
    ts._capture(simulate.run, req, log_fn=ts._quiet)
    return {"tmp": tmp, "wd": os.path.join(tmp, "out"),
            "prediction": _write(os.path.join(tmp, "prediction.yaml"),
                                 PREDICTION)}


def _refusals_dir(run_dir):
    return os.path.join(run_dir["wd"], "proposals", "refusals")


def _run_refused(run_dir, policy_doc, name="refused", dry_run=False):
    policy_path = _write(
        os.path.join(run_dir["tmp"], f"{name}.yaml"), policy_doc)
    with pytest.raises(propose.ProposeError) as e:
        ts._capture(propose.run, run_dir["wd"], policy_path,
                    run_dir["prediction"], name=name, log_fn=ts._quiet,
                    dry_run=dry_run)
    return e.value.problems, policy_path


# ---------------------------------------------------------- the receipt itself
def test_a_family_refusal_writes_a_receipt_carrying_what_the_paper_asks_for(
        run_dir):
    problems, policy_path = _run_refused(run_dir, {"policy": {
        "family": "disk_tiered", "configuration": {"probe": 1},
        "changes": [{"param": "probe", "from": 1, "to": 2}],
        "rationale": "test"}})

    files = sorted(os.listdir(_refusals_dir(run_dir)))
    assert len(files) == 1, files
    with open(os.path.join(_refusals_dir(run_dir), files[0]),
             encoding="utf-8") as f:
        receipt = json.load(f)

    assert receipt["authored_by"] == "user"
    assert receipt["sentence"] is None
    assert "disk_tiered" in receipt["policy_declared"]
    assert receipt["named_as_missing"] == [
        {"kind": "family", "name": "disk_tiered"}]
    assert any("no model family named" in p for p in receipt["problems"])
    assert receipt["corpus_characterization"] is not None
    assert receipt["corpus_characterization_reason"] is None
    assert "measured" in receipt["provenance"]
    assert "measuring" in receipt["provenance"]
    assert receipt["oneground"] and receipt["invocation"]


def test_a_parameter_refusal_names_the_family_and_the_parameter(run_dir):
    _, _ = _run_refused(run_dir, {"policy": {
        "family": "semantic_sharded",
        "configuration": dict(BASE, not_a_real_param=1),
        "changes": [{"param": "not_a_real_param", "from": 1, "to": 2}],
        "rationale": "test"}}, name="bad-param")

    files = [f for f in os.listdir(_refusals_dir(run_dir))]
    receipts = []
    for name in files:
        with open(os.path.join(_refusals_dir(run_dir), name),
                 encoding="utf-8") as f:
            receipts.append(json.load(f))
    match = [r for r in receipts
            if any(m.get("name") == "not_a_real_param"
                  for m in r["named_as_missing"])]
    assert len(match) == 1, receipts
    named = match[0]["named_as_missing"]
    assert {"kind": "parameter", "name": "not_a_real_param",
           "family": "semantic_sharded"} in named


def test_a_scope_refusal_is_named_as_scope(run_dir):
    _run_refused(run_dir, {"policy": {
        "family": "semantic_sharded", "configuration": dict(BASE),
        "changes": [{"param": "probe", "from": 1, "to": 2}],
        "scope": "recent_documents", "rationale": "test"}}, name="bad-scope")

    receipts = []
    for name in os.listdir(_refusals_dir(run_dir)):
        with open(os.path.join(_refusals_dir(run_dir), name),
                 encoding="utf-8") as f:
            receipts.append(json.load(f))
    match = [r for r in receipts
            if any(m["kind"] == "scope" for m in r["named_as_missing"])]
    assert len(match) == 1, receipts


# -------------------------------------------------------------- authored_by
def test_a_policy_beside_a_translation_card_is_authored_by_model(run_dir):
    tmp = run_dir["tmp"]
    sub = os.path.join(tmp, "translated")
    os.makedirs(sub, exist_ok=True)
    policy_path = _write(os.path.join(sub, "policy.yaml"), {"policy": {
        "family": "disk_tiered", "configuration": {}, "changes": [],
        "rationale": "model said so"}})
    with open(os.path.join(sub, R.TRANSLATION_CARD_NAME), "w",
             encoding="utf-8") as f:
        json.dump({"authored_by": "model", "sentence": "make it faster"}, f)

    with pytest.raises(propose.ProposeError):
        ts._capture(propose.run, run_dir["wd"], policy_path,
                    run_dir["prediction"], name="model-authored",
                    log_fn=ts._quiet)

    receipts = []
    for name in os.listdir(_refusals_dir(run_dir)):
        with open(os.path.join(_refusals_dir(run_dir), name),
                 encoding="utf-8") as f:
            receipts.append(json.load(f))
    # policy_path is sanitised (docs/PRACTICE.md/task 043): a temp
    # directory outside the repo reduces to a basename, never the
    # absolute path a machine-local receipt must not carry.
    match = [r for r in receipts
            if r["policy_path"] == os.path.basename(policy_path)]
    assert len(match) == 1, receipts
    assert match[0]["authored_by"] == "model"
    assert match[0]["sentence"] == "make it faster"
    assert match[0]["translation_card"] == R.TRANSLATION_CARD_NAME


# ------------------------------------------------------------------- dry-run
def test_dry_run_writes_no_receipt():
    """docs/PROPOSALS.md §2.1: --dry-run's own contract is 'write nothing.'
    A receipt is a write, so it is skipped under --dry-run -- the sharpest
    mutant this test could have: prove the directory a normal refusal
    would have created does not exist at all."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        vp, qp = ts._corpus(tmp)
        block = {"kind": "declared", "families": ["semantic_sharded"],
                 "ground_truth_k": 20,
                 "include": [dict(BASE, family="semantic_sharded")],
                 "grid": {"semantic_sharded": {
                     "centroids": [8], "epsilon": [0.1], "probe": [1],
                     "M": [16], "efSearch": [64]}}}
        req = ts._req(tmp, vp, qp, block)
        ts._capture(characterize.run, req, log_fn=ts._quiet)
        ts._capture(simulate.run, req, log_fn=ts._quiet)
        wd = os.path.join(tmp, "out")
        pred = _write(os.path.join(tmp, "prediction.yaml"), PREDICTION)
        policy_path = _write(os.path.join(tmp, "bad.yaml"), {"policy": {
            "family": "disk_tiered", "configuration": {}, "changes": [],
            "rationale": "test"}})

        with pytest.raises(propose.ProposeError):
            ts._capture(propose.run, wd, policy_path, pred, name="dry",
                        log_fn=ts._quiet, dry_run=True)

        assert not os.path.isdir(os.path.join(wd, "proposals", "refusals"))


# --------------------------------------------------- a receipt that fails to write
def test_a_failing_receipt_write_never_turns_a_refusal_into_a_crash(
        run_dir, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("disk exploded")
    monkeypatch.setattr(R, "write_refusal_receipt", boom)

    problems, _ = _run_refused(run_dir, {"policy": {
        "family": "still_not_real", "configuration": {}, "changes": [],
        "rationale": "test"}}, name="receipt-fails")
    assert any("no model family named" in p for p in problems)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
