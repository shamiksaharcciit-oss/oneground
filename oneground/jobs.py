"""What a job is: one CLI invocation, its state, and what it left behind.

Task 046 step 3. `docs/INTERFACE.md` §4.2 makes each stage a job, and §2 makes
every job exactly a CLI invocation that a test can replay.

WHY THIS IS NOT IN `oneground/lab/`
-----------------------------------
The lab's guard permits exactly one served module to open a file for writing,
and that module writes requirements files. A job list that the server could
write would put a second write path inside the served package, so the split
is: **the server reads jobs, the supervisor writes them** (§4, a second
process). This module holds the record, the state machine and the reading;
the writing belongs to the process that runs things.

That is the same ruling as *the UI does not launch pod sessions*, one level
down: a server that may not import the measuring packages cannot run them,
and a server that may not write cannot own the record of what ran.

THE STATES, AND WHY THE TRANSITIONS ARE CHECKED
-----------------------------------------------
Six states, and the set is closed. `refused` is not a kind of `failed`: a
refusal is the tool declining to run something, with a reason and a remedy,
and a failure is something breaking. `docs/INTERFACE.md` §4.4 requires the
refusal be shown verbatim, and collapsing the two would make the most useful
message the tool produces into an error string.

The transitions are checked because the states are what the page draws from.
A job that went from `done` back to `running` would render a finished run as
in progress, and nothing downstream would notice -- the same shape as a
receipt that says something it should not.
"""

import json
import os
import re

#: Queued and running are live; the rest are terminal.
QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
REFUSED = "refused"
CANCELLED = "cancelled"

STATES = (QUEUED, RUNNING, DONE, FAILED, REFUSED, CANCELLED)
TERMINAL = (DONE, FAILED, REFUSED, CANCELLED)

#: What may follow what. A refusal can happen before the work starts -- an
#: unpinned environment is refused at parse time -- so `queued -> refused` is
#: legal and is not a failure.
TRANSITIONS = {
    QUEUED: (RUNNING, REFUSED, CANCELLED),
    RUNNING: (DONE, FAILED, REFUSED, CANCELLED),
    DONE: (), FAILED: (), REFUSED: (), CANCELLED: (),
}

#: The stages a job may be. Every pod operation except the create: `up` is a
#: terminal, because a scriptable page is `--yes` with a nicer surface
#: (`docs/INTERFACE.md` §4.3).
STAGES = ("characterize", "simulate", "verify", "report", "chunk", "propose",
          "pod plan", "pod status", "pod watch", "pod fetch")

#: Never a job, and named rather than merely absent, because the reason is a
#: ruling rather than an omission.
NOT_A_JOB = {
    "pod up": "the one operation that spends money keeps the one boundary "
              "that cannot be automated by accident; the UI shows the card "
              "and hands over the command",
}

_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[a-z0-9-]{1,40}-[0-9a-f]{8}$")


class JobError(ValueError):
    """A job record is malformed, or a transition is not one the states
    allow."""


class Job:
    """One invocation, its state, and what it left behind.

    `invocation` is the field everything else hangs off: it is what
    `provenance.record_invocation` wrote into the receipts this job produced,
    and what `oneground.replay` re-runs to check them.
    """

    __slots__ = ("id", "stage", "invocation", "state", "workdir", "log",
                 "started", "ended", "refusal", "exit_code", "partial")

    def __init__(self, id, stage, invocation, workdir, state=QUEUED,
                 log=None, started=None, ended=None, refusal=None,
                 exit_code=None, partial=False):
        if stage not in STAGES:
            raise JobError(
                f"{stage!r} is not a stage a job may be. Stages: "
                + ", ".join(STAGES)
                + "".join(f"; {k} is never a job because {v}"
                          for k, v in NOT_A_JOB.items()))
        if state not in STATES:
            raise JobError(f"{state!r} is not a state; states: "
                           + ", ".join(STATES))
        if not invocation:
            raise JobError(
                "a job is a CLI invocation and this one names none, so "
                "nothing it produced could be replayed")
        self.id = id
        self.stage = stage
        self.invocation = list(invocation)
        self.state = state
        self.workdir = workdir
        self.log = log
        self.started = started
        self.ended = ended
        #: The CLI's own words, verbatim. Never rephrased and never
        #: summarised -- `docs/INTERFACE.md` §4.4.
        self.refusal = refusal
        self.exit_code = exit_code
        #: A cancelled job's outputs are kept and marked, never presented as
        #: complete. The mark travels with the record rather than being
        #: inferred from the state, because a reader of one artifact does not
        #: have the state.
        self.partial = bool(partial)

    # -- the state machine --------------------------------------------------
    def may_become(self, state):
        return state in TRANSITIONS.get(self.state, ())

    def become(self, state, *, refusal=None, exit_code=None, ended=None,
               partial=None):
        """Move to `state`, or refuse to.

        Refusing an illegal transition is the point. The states are what the
        page draws from, so a job that went from `done` back to `running`
        would render a finished run as in progress and nothing downstream
        would notice.
        """
        if not self.may_become(state):
            allowed = TRANSITIONS.get(self.state, ())
            raise JobError(
                f"a {self.state} job cannot become {state}; from "
                f"{self.state} a job may become "
                + (", ".join(allowed) if allowed else
                   "nothing: it is a terminal state"))
        if state == REFUSED and not refusal:
            raise JobError(
                "a refused job carries the CLI's refusal verbatim; refusing "
                "without one would lose the most useful thing the tool "
                "produces")
        self.state = state
        if refusal is not None:
            self.refusal = refusal
        if exit_code is not None:
            self.exit_code = exit_code
        if ended is not None:
            self.ended = ended
        if partial is not None:
            self.partial = bool(partial)
        return self

    @property
    def live(self):
        return self.state not in TERMINAL

    # -- the record ---------------------------------------------------------
    def to_dict(self):
        return {"id": self.id, "stage": self.stage,
                "invocation": list(self.invocation), "state": self.state,
                "workdir": self.workdir, "log": self.log,
                "started": self.started, "ended": self.ended,
                "refusal": self.refusal, "exit_code": self.exit_code,
                "partial": self.partial}

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            raise JobError(f"a job record is a mapping, not a "
                           f"{type(d).__name__}")
        missing = [k for k in ("id", "stage", "invocation", "state")
                   if d.get(k) in (None, "")]
        if missing:
            raise JobError("a job record is missing " + ", ".join(missing))
        return cls(id=d["id"], stage=d["stage"], invocation=d["invocation"],
                   workdir=d.get("workdir"), state=d["state"],
                   log=d.get("log"), started=d.get("started"),
                   ended=d.get("ended"), refusal=d.get("refusal"),
                   exit_code=d.get("exit_code"),
                   partial=d.get("partial", False))

    def __repr__(self):                                # pragma: no cover
        return f"<Job {self.id} {self.stage} {self.state}>"


def valid_id(value):
    """Whether a job id has the shape this project writes.

    Checked because an id reaches the filesystem as a log file's name. It is
    a timestamp, the stage, and eight hex -- sortable, readable in a
    directory listing, and containing nothing a path would have to escape.
    """
    return bool(isinstance(value, str) and _ID.match(value))


#: The job list's file name, inside the runs directory the session serves.
JOBS_NAME = "jobs.json"


def read(runs_dir):
    """Every job the supervisor has recorded, oldest first.

    Reading only. The server calls this; nothing here writes, which is what
    keeps the served package's single write path single.

    An absent file is an empty list rather than an error: a runs directory
    that has never had a job is the ordinary case, and refusing it would
    make the page's first visit a failure.
    """
    path = os.path.join(runs_dir, JOBS_NAME)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise JobError(f"{JOBS_NAME} could not be read: {e}") from None
    if not isinstance(raw, list):
        raise JobError(f"{JOBS_NAME} holds a {type(raw).__name__}, not a "
                       "list of jobs")
    return [Job.from_dict(d) for d in raw]
