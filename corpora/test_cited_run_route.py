"""A run a page cites is kept where a page may cite it (task 044j).

Core's second option, made a rule rather than a route walked by hand. `runs/`
is a working directory: ignored, overwritten in place, deleted with the
worktree that made it. `committed_report` refuses a page that cites one; this
is the other half, the place such a run goes instead.

It exists as code because the route has been walked twice by hand -- once for
`1ombs4scr257a5` and once for the superseded 9 September report -- and a path
spelled out twice by hand is a path that will be spelled a third way.
"""

import importlib.util
import json
import os
import sys

import pytest

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, REPO)

_p = os.path.join(REPO, "corpora", "export_teaser_data.py")
_s = importlib.util.spec_from_file_location("etd_cited_test", _p)
etd = importlib.util.module_from_spec(_s)
_s.loader.exec_module(etd)


def _src(tmp_path, body):
    p = tmp_path / "report.json"
    p.write_text(json.dumps(body), encoding="utf-8")
    return str(p)


def test_the_destination_is_one_decision_not_a_convention():
    got = etd.cited_run_destination("arxiv-150k")
    assert got.replace(os.sep, "/").endswith(
        "fixtures/arxiv-150k/report/report.json")


def test_the_two_runs_already_kept_by_hand_are_where_this_would_put_them():
    """NOT synthetic. The route was walked twice before it was a function, and
    if the function disagrees with either, one of them is in the wrong place.
    """
    live = etd.cited_run_destination("arxiv-150k")
    assert os.path.exists(live), live
    superseded = etd.cited_run_destination(
        "arxiv-150k", "superseded-2026-09-09-tf8sd2usxbblsm.report.json")
    assert os.path.exists(superseded), superseded


def test_a_copy_is_verified_by_digest(tmp_path, monkeypatch):
    src = _src(tmp_path, {"schema": 1, "run": "x"})
    monkeypatch.setattr(etd, "REPO_ROOT", str(tmp_path / "repo"))
    dest, digest = etd.copy_cited_run(src, "some-fixture",
                                      log_fn=lambda m: None)
    assert os.path.exists(dest)
    assert digest == etd.sha256_file(src) == etd.sha256_file(dest)


def test_copying_the_same_bytes_twice_is_not_an_error(tmp_path, monkeypatch):
    """Re-running a hand-over must not be a fight."""
    src = _src(tmp_path, {"schema": 1})
    monkeypatch.setattr(etd, "REPO_ROOT", str(tmp_path / "repo"))
    a = etd.copy_cited_run(src, "f", log_fn=lambda m: None)
    b = etd.copy_cited_run(src, "f", log_fn=lambda m: None)
    assert a == b


# ------------------------------------------------------------ the sabotage
def test_different_bytes_at_the_destination_are_refused(tmp_path, monkeypatch):
    """The durable copy is not silently replaced.

    This is the 9 September loss one directory over: a file that was the only
    record of a measurement, overwritten in place by a different run, with
    nothing refusing. Here it refuses and says what to do instead.
    """
    monkeypatch.setattr(etd, "REPO_ROOT", str(tmp_path / "repo"))
    first = _src(tmp_path, {"schema": 1, "run": "the nine september run"})
    etd.copy_cited_run(first, "f", log_fn=lambda m: None)
    dest = etd.cited_run_destination("f")
    before = etd.sha256_file(dest)

    second = tmp_path / "other.json"
    second.write_text(json.dumps({"schema": 1, "run": "a later run"}),
                      encoding="utf-8")

    with pytest.raises(SystemExit) as e:
        etd.copy_cited_run(str(second), "f", log_fn=lambda m: None)
    msg = str(e.value)
    assert "different bytes" in msg
    assert "name that says which run it is" in msg
    assert etd.sha256_file(dest) == before, (
        "the refusal fired but the durable copy had already been replaced")
