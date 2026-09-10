"""The counting rule that failed calibration run #1.

**Synthetic throughout.** Every case is a hand-built history; nothing here
reads the real one.

The first test is the regression: the exact shape of run #1 -- seven blocking
contradictions already in the file, seven advisory lines appended -- which the
old `bad[-appended:]` slice reported as seven blocking failures.

    .venv/Scripts/python.exe -m pytest .github/scripts/test_count_contradictions.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from count_contradictions import (blocking_contradictions,  # noqa: E402
                                  main, read_lines)


def line(outcome="verified", scope="blocking", check="glove_curve", **kw):
    d = {"check": check, "outcome": outcome, "date": "2026-09-10"}
    if scope is not None:
        d["outcome_scope"] = scope
    d.update(kw)
    return d


def _history(tmp, lines):
    p = os.path.join(tmp, "history.jsonl")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for d in lines:
            f.write(json.dumps(d, sort_keys=True) + "\n")
    return p


# ------------------------------------------------------------ the regression
def test_historical_blocking_lines_do_not_fail_a_run_that_appended_advisory():
    """Calibration run #1, exactly.

    Seven blocking contradictions already in the file from before the glove
    curve was ruled advisory, seven advisory lines appended by this run. The
    old slice took the last seven *blocking contradictions* -- all historical
    -- and failed the build on them.
    """
    history = ([line(outcome="contradicted", scope="blocking")] * 7
               + [line(outcome="contradicted", scope="advisory")] * 7)
    assert blocking_contradictions(history, appended=7) == []


def test_the_old_slice_would_have_failed_this_synthetic():
    """Pins the defect itself, so the fix cannot be quietly reverted."""
    history = ([line(outcome="contradicted", scope="blocking")] * 7
               + [line(outcome="contradicted", scope="advisory")] * 7)
    old_bad = [d for d in history
               if d.get("outcome") == "contradicted"
               and d.get("outcome_scope", "blocking") == "blocking"]
    old_result = old_bad[-7:] if old_bad else []
    assert len(old_result) == 7, "the old logic did not reproduce the failure"
    assert blocking_contradictions(history, appended=7) == []


# --------------------------------------------------------------- the rule
def test_a_blocking_contradiction_in_this_runs_lines_counts():
    history = [line(), line(outcome="contradicted", scope="blocking")]
    assert len(blocking_contradictions(history, appended=1)) == 1


def test_an_advisory_contradiction_never_counts():
    """The glove curve compares two HNSW implementations that genuinely
    differ. It stays in the history; it does not fail the build."""
    history = [line(outcome="contradicted", scope="advisory")] * 3
    assert blocking_contradictions(history, appended=3) == []


def test_couldnt_check_never_counts():
    """A gap in the reference is not a defect in this installation."""
    history = [line(outcome="couldnt_check", scope="blocking")] * 3
    assert blocking_contradictions(history, appended=3) == []


def test_a_line_with_no_scope_is_blocking():
    """Silence must not weaken a gate: no scope was the default before the
    field existed."""
    history = [line(outcome="contradicted", scope=None)]
    assert len(blocking_contradictions(history, appended=1)) == 1


def test_appending_nothing_contradicts_nothing():
    """A run that appended no lines cannot have contradicted anything --
    an empty result, not "look at the whole file"."""
    history = [line(outcome="contradicted", scope="blocking")] * 5
    assert blocking_contradictions(history, appended=0) == []
    assert blocking_contradictions(history, appended="") == []
    assert blocking_contradictions(history, appended=None) == []


def test_only_this_runs_window_is_examined():
    """Earlier contradictions are history and have their own issues."""
    history = ([line(outcome="contradicted", scope="blocking", note="old")] * 4
               + [line(outcome="verified", note="new")] * 2)
    assert blocking_contradictions(history, appended=2) == []


def test_a_mixed_window_reports_only_the_blocking_ones():
    history = [
        line(outcome="verified"),
        line(outcome="contradicted", scope="advisory", note="curve"),
        line(outcome="contradicted", scope="blocking", note="engine"),
        line(outcome="couldnt_check", scope="blocking"),
    ]
    bad = blocking_contradictions(history, appended=4)
    assert len(bad) == 1
    assert bad[0]["note"] == "engine"


# ------------------------------------------------------------------- the CLI
def test_the_cli_writes_a_count_and_a_body():
    with tempfile.TemporaryDirectory() as tmp:
        p = _history(tmp, [line(outcome="contradicted", scope="blocking",
                                note="engine")])
        out = os.path.join(tmp, "out.txt")
        assert main(["--history", p, "--appended", "1",
                     "--github-output", out]) == 0
        text = open(out, encoding="utf-8").read()
        assert "count=1" in text
        assert "ONEGROUND_EOF" in text
        assert '"note": "engine"' in text


def test_the_cli_writes_no_body_when_nothing_is_wrong():
    with tempfile.TemporaryDirectory() as tmp:
        p = _history(tmp, [line(outcome="contradicted", scope="advisory")])
        out = os.path.join(tmp, "out.txt")
        assert main(["--history", p, "--appended", "1",
                     "--github-output", out]) == 0
        text = open(out, encoding="utf-8").read()
        assert "count=0" in text
        assert "ONEGROUND_EOF" not in text


def test_counting_never_fails_the_process():
    """Counting is not judging. The workflow decides what to do with the
    count, and a step that both counts and fails cannot be reused by the
    advisory jobs."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _history(tmp, [line(outcome="contradicted", scope="blocking")] * 3)
        out = os.path.join(tmp, "out.txt")
        assert main(["--history", p, "--appended", "3",
                     "--github-output", out]) == 0


def test_blank_lines_in_the_history_are_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "h.jsonl")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n")
            f.write(json.dumps(line(outcome="verified")) + "\n")
            f.write("\n")
        assert len(read_lines(p)) == 1
