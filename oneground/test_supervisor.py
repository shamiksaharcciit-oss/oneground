"""The second process: it owns the job list and runs the commands.

Task 046 step 4. Driven against real subprocesses, because every property
worth having here is about what happens to a process and a file.
"""

import json
import os
import subprocess
import sys
import time

import pytest

from oneground import jobs, supervisor

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def sup(tmp_path):
    return supervisor.Supervisor(str(tmp_path))


def _wait(proc, timeout=180):
    deadline = time.time() + timeout
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.05)
    assert proc.poll() is not None, "the child never finished"
    return proc.returncode


# ------------------------------------------------------------ the record
def test_an_enqueued_job_is_queued_and_named(sup):
    j = sup.enqueue("simulate", ["simulate", "runs/x"])
    assert j.state == "queued"
    assert jobs.valid_id(j.id), j.id
    assert j.log.endswith(".log") and j.id in j.log
    assert [r.id for r in sup.read()] == [j.id]


def test_the_create_cannot_be_enqueued(sup):
    """`pod up` is never a job, and the refusal quotes the ruling rather than
    saying the stage is unknown."""
    with pytest.raises(jobs.JobError) as caught:
        sup.enqueue("pod up", ["pod", "up"])
    assert "cannot be automated by accident" in str(caught.value)


def test_the_list_is_written_atomically(sup):
    """The server reads this file while the supervisor writes it, and
    `jobs.read` refuses a corrupt one rather than returning nothing -- so a
    torn write would take the run list down with it, not slow it down."""
    sup.enqueue("simulate", ["simulate", "runs/x"])
    leftovers = [n for n in os.listdir(sup.runs_dir) if n.endswith(".writing")]
    assert leftovers == []
    with open(sup.path, encoding="utf-8") as f:
        json.load(f)


def test_a_restart_loses_nothing(sup, tmp_path):
    """No state beyond the job list: a second Supervisor over the same
    directory is the same supervisor."""
    a = sup.enqueue("simulate", ["simulate", "runs/x"])
    again = supervisor.Supervisor(str(tmp_path))
    assert [r.id for r in again.read()] == [a.id]


# ------------------------------------------------------------- running
def test_a_refused_command_is_recorded_as_refused_with_its_words(sup):
    """End to end against the real CLI. A missing requirements file is the
    refusal that used to arrive as a traceback; it is now exit 2, and the
    record carries the CLI's own sentence."""
    j = sup.enqueue("characterize", ["characterize", "nope.yaml"])
    proc, handle = sup.start(j, python=sys.executable)
    code = _wait(proc)
    sup.finish(j, code, handle)

    stored = sup.read()[0]
    assert stored.state == "refused", stored.why
    assert stored.exit_code == 2
    assert "requirements file not found: nope.yaml" in stored.refusal
    assert "Traceback" not in stored.refusal
    assert stored.why and "refused" not in stored.why.split()[0:1]


def test_the_refusal_is_the_log_whole_and_unparsed(sup):
    """Verbatim, and not the sentence picked out of it: extracting would mean
    recognising `cli.main`'s format here, which is the second implementation
    `refusals.py` exists to have avoided."""
    j = sup.enqueue("characterize", ["characterize", "nope.yaml"])
    proc, handle = sup.start(j, python=sys.executable)
    sup.finish(j, _wait(proc), handle)
    stored = sup.read()[0]
    with open(os.path.join(sup.runs_dir, stored.log), encoding="utf-8") as f:
        assert stored.refusal == f.read().strip()


def test_the_log_is_the_cli_s_own_output(sup):
    j = sup.enqueue("characterize", ["characterize", "nope.yaml"])
    proc, handle = sup.start(j, python=sys.executable)
    sup.finish(j, _wait(proc), handle)
    path = os.path.join(sup.runs_dir, sup.read()[0].log)
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as f:
        assert "oneground characterize: refused." in f.read()


def test_start_records_running_and_a_start_time(sup):
    j = sup.enqueue("characterize", ["characterize", "nope.yaml"])
    proc, handle = sup.start(j, python=sys.executable)
    live = sup.read()[0]
    assert live.state == "running" and live.started
    sup.finish(j, _wait(proc), handle)


# ------------------------------- what a record means is in the record
def test_the_reason_for_the_classification_is_stored(sup):
    """A reader of one record does not have the workdir and cannot re-run
    the decision, so `failed` alone would hand over the conclusion and keep
    the evidence."""
    j = sup.enqueue("simulate", ["simulate", "runs/x"])
    sup.start(j, python=sys.executable)[1].close()
    sup.finish(j, 1)
    stored = sup.read()[0]
    assert stored.state == "failed"
    assert "no simulate.json" in stored.why


def test_exit_one_with_the_receipt_is_recorded_as_done_with_the_reason(sup):
    """The row where one code means two things, through the supervisor this
    time rather than through `classify` alone."""
    with open(os.path.join(sup.runs_dir, "simulate.json"), "w",
              encoding="utf-8") as f:
        f.write("{}")
    j = sup.enqueue("simulate", ["simulate", "runs/x"])
    sup.start(j, python=sys.executable)[1].close()
    sup.finish(j, 1)
    stored = sup.read()[0]
    assert stored.state == "done"
    assert "simulate.json written" in stored.why


def test_every_terminal_record_carries_its_reason(sup):
    """Not one path: all of them. A state without a reason is the defect,
    wherever it is reached from."""
    for code in (0, 1, 2, 137):
        j = sup.enqueue("simulate", ["simulate", "runs/x"])
        sup.start(j, python=sys.executable)[1].close()
        sup.finish(j, code)
    for stored in sup.read():
        assert stored.state in jobs.TERMINAL
        assert stored.why, stored.to_dict()


# ------------------------------------------------------------ stopping
def test_cancelling_keeps_the_outputs_and_marks_them_partial(sup):
    """Two things it does not do: delete what the run produced, and present
    it as complete."""
    with open(os.path.join(sup.runs_dir, "half.json"), "w",
              encoding="utf-8") as f:
        f.write("{")
    j = sup.enqueue("simulate", ["simulate", "runs/x"])
    sup.start(j, python=sys.executable)[1].close()
    sup.cancel(j)
    stored = sup.read()[0]
    assert stored.state == "cancelled"
    assert stored.partial is True
    assert "partial" in stored.why
    assert os.path.isfile(os.path.join(sup.runs_dir, "half.json"))


def test_cancelling_a_live_child_really_stops_it(sup):
    """A real stop, not a state change with a process still running."""
    j = sup.enqueue("simulate", ["simulate", "runs/x"])
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        j.become(jobs.RUNNING)
        sup._replace(j)
        sup.cancel(j, proc, grace=5.0)
        assert proc.poll() is not None, "the child outlived its cancellation"
        assert sup.read()[0].state == "cancelled"
    finally:
        if proc.poll() is None:                          # pragma: no cover
            proc.kill()


def test_the_supervisor_does_not_hold_the_child(sup):
    """Its crash must not kill a running simulate.

    `start` spawns and returns the process without registering it anywhere:
    no process group, no job object, no `atexit`. Asserted on the parsed
    source rather than by killing a supervisor mid-run, which would need a
    third process and would test the harness as much as the rule.

    **Parsed, not matched on text.** The first version of this searched the
    file for the word `atexit` and found it in the docstring explaining that
    there is no atexit -- a check reading its subject's own description as
    evidence against it, which is `docs/PRACTICE.md` §2 warning 1 in a test
    written the same hour as the code it checks.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(supervisor))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            used.add(node.arg)
    for held in ("atexit", "setsid", "CREATE_NEW_PROCESS_GROUP",
                 "AssignProcessToJobObject", "start_new_session",
                 "preexec_fn", "creationflags"):
        assert held not in used, (
            f"{held} appears in the code: the child is being held, and a "
            "supervisor that dies would take a running simulate with it")


def test_a_cancelled_job_cannot_then_be_finished(sup):
    """Terminal is terminal. A late exit code arriving after a cancellation
    must not rewrite the record into `done`."""
    j = sup.enqueue("simulate", ["simulate", "runs/x"])
    sup.start(j, python=sys.executable)[1].close()
    sup.cancel(j)
    with pytest.raises(jobs.JobError):
        sup.finish(j, 0)
    assert sup.read()[0].state == "cancelled"

# ----------------------------------------------------- advancing the list
def test_tick_starts_a_queued_job_and_reaps_it(sup):
    """The scheduler, which did not exist: enqueue recorded a job and
    nothing ever drove it to running. A channel that worked would still have
    produced a list of things that never ran."""
    j = sup.enqueue("characterize", ["characterize", "nope.yaml"])
    assert sup.read()[0].state == "queued"

    did = sup.tick()
    assert ("started", j.id) in did
    assert sup.read()[0].state == "running"

    for _ in range(600):
        did = sup.tick()
        if any(k == "finished" for k, _ in did):
            break
        time.sleep(0.05)
    stored = sup.read()[0]

    # What the RUNNER promises: it reaped the child, recorded a terminal
    # state, and recorded why. Which terminal state a real child reaches is
    # the environment's business -- under a loaded suite this one has been
    # seen killed with 0xC000013A, which `classify` correctly calls failed
    # and names as a code the tool does not return deliberately.
    #
    # Not weakened: that a refusal exit becomes `refused` with the CLI's
    # words is asserted deterministically in
    # `test_a_refused_command_is_recorded_as_refused_with_its_words`, which
    # drives the exit code rather than hoping for it. This test is about the
    # loop; that one is about the mapping. Splitting them is what lets both
    # be exact.
    assert stored.state in jobs.TERMINAL, stored.why
    assert stored.why, "a terminal state with no reason"
    assert stored.exit_code is not None
    assert stored.ended


def test_one_job_at_a_time(sup):
    """A simulate uses the machine and two of them fight for it -- the
    second would measure a loaded machine and record timings nobody can
    compare. A decision, not a limitation."""
    sup.enqueue("characterize", ["characterize", "nope.yaml"])
    sup.enqueue("characterize", ["characterize", "also-nope.yaml"])

    sup.tick()
    states = [j.state for j in sup.read()]
    # By count, not by identity: ids carry a random suffix and two enqueued
    # in the same second sort either way round, so naming which one runs
    # first would be asserting something this code does not promise. The
    # promise is that exactly one runs.
    assert states.count("running") == 1, states
    assert states.count("queued") == 1, states

    for _ in range(600):
        sup.tick()
        if not any(j.state == "queued" for j in sup.read()):
            break
        time.sleep(0.05)
    live = [j.state for j in sup.read()]
    assert "queued" not in live, live
    assert live.count("running") <= 1, "two jobs were running at once"


def test_tick_is_idempotent_on_an_empty_list(sup):
    assert sup.tick() == []
    assert sup.tick() == []


def test_a_job_running_under_a_dead_supervisor_is_named_not_guessed(sup):
    """Running in the record and not a child of this process. This one
    cannot tell whether it still is, so it says `orphaned` rather than
    deciding -- the couldnt_check the six states have no room for."""
    j = sup.enqueue("simulate", ["simulate", "runs/x"])
    j.become(jobs.RUNNING)
    sup._replace(j)                       # as a previous process left it
    did = sup.tick()
    assert ("orphaned", j.id) in did
    assert sup.read()[0].state == "running", "it was guessed at"
