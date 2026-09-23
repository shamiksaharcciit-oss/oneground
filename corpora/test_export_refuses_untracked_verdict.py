"""The verdict is built only from a committed report (task 044j).

**The published verdict used to cite `runs/arxiv-150k-via-characterize/
report.json`, and `runs/` is ignored.** The page named a report no commit
held; nobody could rebuild the decision from the tree that published it; and
when a newer committed report of the same fixture appeared, nothing noticed
the page was still citing the old one. A verdict stayed live for thirteen days
after its own receipts had been destroyed.

Core's sabotage is `test_the_sabotage_a_runs_report_is_refused`: point the
exporter at a `runs/` report and require it to refuse and name the path.
"""

import importlib.util
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, REPO)

_p = os.path.join(REPO, "corpora", "export_teaser_data.py")
_s = importlib.util.spec_from_file_location("etd_verdict_test", _p)
etd = importlib.util.module_from_spec(_s)
_s.loader.exec_module(etd)


# ----------------------------------------------------------- the sabotage
def test_the_sabotage_a_runs_report_is_refused(tmp_path):
    """A report under runs/ must be refused, and the path must be named."""
    d = os.path.join(REPO, "runs", "044j-sabotage")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "report.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"schema": 1}, f)
    try:
        with pytest.raises(SystemExit) as e:
            etd.committed_report(p)
        msg = str(e.value)
        assert "runs/044j-sabotage/report.json" in msg, msg
        assert "not committed" in msg or "working directory" in msg, msg
    finally:
        os.remove(p)
        os.rmdir(d)


def test_an_untracked_report_outside_runs_is_refused(tmp_path):
    """The second half: not under runs/, and still not in any commit.

    Without this, moving a working file anywhere but runs/ would satisfy the
    guard while leaving the page citing something no clone has.
    """
    d = os.path.join(REPO, "fixtures", "044j-not-committed")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "report.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"schema": 1}, f)
    try:
        with pytest.raises(SystemExit) as e:
            etd.committed_report(p)
        assert "does not track" in str(e.value), str(e.value)
    finally:
        os.remove(p)
        os.rmdir(d)


# ------------------------------------------------- what it must still allow
def test_the_committed_report_the_page_actually_uses_is_accepted():
    """NOT synthetic. The real source of the live verdict.

    A guard that refused this would be refusing the correct case, which is how
    a guard gets removed rather than fixed.
    """
    p = os.path.join(REPO, "fixtures", "arxiv-150k", "report", "report.json")
    assert etd.committed_report(p) == "fixtures/arxiv-150k/report/report.json"


def test_it_is_not_vacuous():
    """`git ls-files --error-unmatch` must actually be reachable here.

    If git were missing, every call would raise and the accept-case test above
    would be the only thing failing -- so this says plainly that the mechanism
    the guard depends on is present.
    """
    r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "true", r.stderr


# --------------------------------------------------------- source_sha256
def test_the_verdict_records_its_source_digest():
    """Core's addition: the verdict named a path and not the bytes at it.

    A path can be right while the file has changed, which is the whole reason
    `measured.k_sweep` carries a digest. The verdict is the block where it
    matters most, because it is the one a reader is asked to trust.
    """
    p = os.path.join(REPO, "fixtures", "arxiv-150k", "report", "report.json")
    with open(p, encoding="utf-8") as f:
        report = json.load(f)
    v = etd.build_verdict(report, p)
    assert v["source"] == "fixtures/arxiv-150k/report/report.json"
    assert v["source_sha256"] == etd.sha256_file(p)
    assert len(v["source_sha256"]) == 64


def test_the_published_page_carries_the_digest_of_the_report_it_cites():
    """End to end, against the file that is actually served."""
    vals = os.path.join(REPO, "site", "teaser", "data", "values.json")
    if not os.path.exists(vals):
        pytest.skip("no exported values.json here")
    with open(vals, encoding="utf-8") as f:
        verdict = json.load(f)["verdict"]
    src = os.path.join(REPO, verdict["source"])
    if not os.path.exists(src):
        pytest.skip("the cited report is not in this checkout")
    assert verdict.get("source_sha256") == etd.sha256_file(src), (
        "the page cites %s but not the bytes that are there now"
        % verdict["source"])
