"""The job record and its state machine (task 046, step 3)."""

import json
import os

import pytest

from oneground import jobs


def _job(**kw):
    kw.setdefault("id", "20260923T120000Z-simulate-0a1b2c3d")
    kw.setdefault("stage", "simulate")
    kw.setdefault("invocation", ["simulate", "runs/x"])
    kw.setdefault("workdir", "runs/x")
    return jobs.Job(**kw)


# ------------------------------------------------------------ the stages
def test_every_pod_operation_but_the_create_is_a_job():
    """The brief's step 3 was corrected to this after `docs/INTERFACE.md`
    §4.2 and §4.3 disagreed with it: plan, status, watch and the fetch are
    jobs; only `up` is a terminal."""
    for stage in ("pod plan", "pod status", "pod watch", "pod fetch"):
        assert stage in jobs.STAGES
    assert "pod up" not in jobs.STAGES


def test_the_create_is_named_as_never_a_job_with_the_reason():
    """Named rather than merely absent. An implementer who finds `pod up`
    missing and assumes an omission will add it; one who finds it listed
    with the ruling will not."""
    assert "pod up" in jobs.NOT_A_JOB
    assert "cannot be automated by accident" in jobs.NOT_A_JOB["pod up"]


def test_an_unknown_stage_is_refused_and_the_refusal_names_the_set():
    with pytest.raises(jobs.JobError) as caught:
        _job(stage="deploy")
    said = str(caught.value)
    assert "characterize" in said and "pod fetch" in said
    assert "pod up is never a job" in said


def test_a_job_with_no_invocation_is_refused():
    """The field everything hangs off: without it nothing this job produced
    could be replayed, so the record would be a claim with no evidence."""
    with pytest.raises(jobs.JobError) as caught:
        _job(invocation=[])
    assert "replayed" in str(caught.value)


# ----------------------------------------------------- the state machine
def test_the_states_are_closed_and_refused_is_not_a_kind_of_failed():
    """A refusal is the tool declining, with a reason and a remedy; a failure
    is something breaking. Collapsing them would turn the most useful message
    the tool produces into an error string."""
    assert set(jobs.STATES) == {"queued", "running", "done", "failed",
                                "refused", "cancelled"}
    assert jobs.REFUSED != jobs.FAILED
    assert set(jobs.TERMINAL) == {"done", "failed", "refused", "cancelled"}


@pytest.mark.parametrize("start,to", [
    ("queued", "running"), ("queued", "refused"), ("queued", "cancelled"),
    ("running", "done"), ("running", "failed"), ("running", "refused"),
    ("running", "cancelled"),
])
def test_the_legal_transitions_are_allowed(start, to):
    j = _job(state=start)
    j.become(to, refusal="the CLI said so" if to == "refused" else None)
    assert j.state == to


@pytest.mark.parametrize("start,to", [
    ("done", "running"), ("done", "queued"), ("failed", "done"),
    ("refused", "running"), ("cancelled", "done"), ("running", "queued"),
])
def test_an_illegal_transition_is_refused_and_says_what_is_allowed(start, to):
    """Watched failing. The states are what the page draws from: a job that
    went from done back to running would render a finished run as in
    progress and nothing downstream would notice."""
    j = _job(state=start, refusal="x" if start == "refused" else None)
    with pytest.raises(jobs.JobError) as caught:
        j.become(to)
    said = str(caught.value)
    assert f"a {start} job cannot become {to}" in said
    if start in jobs.TERMINAL:
        assert "terminal state" in said
    assert j.state == start, "a refused transition changed the state anyway"


def test_becoming_refused_without_a_refusal_is_itself_refused():
    """§4.4: the refusal is shown verbatim. A refused job with nothing to
    show has lost the thing the state exists to carry."""
    j = _job()
    with pytest.raises(jobs.JobError) as caught:
        j.become("refused")
    assert "verbatim" in str(caught.value)
    assert j.state == "queued"


def test_a_cancelled_job_can_be_marked_partial():
    """Partial outputs are kept and marked, never presented as complete. The
    mark travels with the record because a reader of one artifact does not
    have the state."""
    j = _job(state="running")
    j.become("cancelled", partial=True)
    assert j.partial is True and j.live is False


def test_live_is_the_two_non_terminal_states():
    assert _job(state="queued").live and _job(state="running").live
    for s in jobs.TERMINAL:
        assert not _job(state=s, refusal="x" if s == "refused" else None).live


# ------------------------------------------------------------ the record
def test_a_record_round_trips():
    j = _job(state="running", log="logs/x.log", started="2026-09-23T12:00:00Z")
    again = jobs.Job.from_dict(j.to_dict())
    assert again.to_dict() == j.to_dict()


def test_a_record_missing_a_required_field_is_refused():
    d = _job().to_dict()
    del d["invocation"]
    with pytest.raises(jobs.JobError) as caught:
        jobs.Job.from_dict(d)
    assert "invocation" in str(caught.value)


@pytest.mark.parametrize("value,ok", [
    ("20260923T120000Z-simulate-0a1b2c3d", True),
    ("20260923T120000Z-pod-fetch-0a1b2c3d", True),
    ("../../etc/passwd", False),
    ("20260923T120000Z-simulate-0a1b2c3d/../x", False),
    ("simulate", False),
    ("", False),
    (None, False),
])
def test_a_job_id_carries_nothing_a_path_would_have_to_escape(value, ok):
    """Checked because an id reaches the filesystem as a log file's name."""
    assert jobs.valid_id(value) is ok


# ------------------------------------------------------------- the list
def test_a_runs_directory_with_no_jobs_reads_as_empty(tmp_path):
    """The ordinary first visit. Refusing it would make the page's first
    load a failure."""
    assert jobs.read(str(tmp_path)) == []


def test_the_list_is_read_back(tmp_path):
    a = _job(id="20260923T120000Z-simulate-0a1b2c3d")
    b = _job(id="20260923T130000Z-report-1b2c3d4e", stage="report",
             invocation=["report", "runs/x"], state="done")
    with open(os.path.join(str(tmp_path), jobs.JOBS_NAME), "w",
              encoding="utf-8") as f:
        json.dump([a.to_dict(), b.to_dict()], f)
    got = jobs.read(str(tmp_path))
    assert [j.id for j in got] == [a.id, b.id]
    assert got[1].state == "done"


@pytest.mark.parametrize("content", ["{}", "not json at all", '[{"id": 1}]'])
def test_an_unreadable_job_list_refuses_rather_than_returning_nothing(
        tmp_path, content):
    """Empty and unreadable are different answers. Returning [] for a
    corrupt file would render "no jobs" over a list that exists."""
    with open(os.path.join(str(tmp_path), jobs.JOBS_NAME), "w",
              encoding="utf-8") as f:
        f.write(content)
    with pytest.raises(jobs.JobError):
        jobs.read(str(tmp_path))


def test_this_module_does_not_write():
    """The split that keeps the served package's single write path single:
    the server reads jobs, the supervisor writes them. Asserted on the source
    with the guard's own scan rather than a second one."""
    from oneground.lab import guard
    path = os.path.join(os.path.dirname(os.path.abspath(jobs.__file__)),
                        "jobs.py")
    with open(path, encoding="utf-8") as f:
        assert guard.write_violations(f.read(), path) == []
