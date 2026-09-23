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
                 "started", "ended", "refusal", "exit_code", "partial", "why", "build")

    def __init__(self, id, stage, invocation, workdir, state=QUEUED,
                 log=None, started=None, ended=None, refusal=None,
                 exit_code=None, partial=False, why=None,
                 build=None):
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
        #: Why this job is in the state it is in -- the sentence `classify`
        #: returned, or the reason it was cancelled. In the record because a
        #: reader of one job does not have the workdir in front of them and
        #: cannot re-run the decision: a `failed` that cannot say whether the
        #: exit code or a missing receipt decided has handed over the
        #: conclusion and kept the evidence.
        self.why = why
        #: The package directory that ran it. Task 046 found two checkouts
        #: sharing a version and a commit where only the path differed.
        self.build = build

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
                "partial": self.partial, "why": self.why,
                "build": self.build}

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
                   partial=d.get("partial", False), why=d.get("why"),
                   build=d.get("build"))

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

# ============================================ THE EXIT-CODE CONTRACT
#
# > **A stage's exit code says whether the command ran. It never says what
# > the command found.**
# >
# >   0  it ran. What it found is in the artifact.
# >   2  it declined, with a reason, and printed it.
# >   1  it did not finish. Whether anything survives is the workdir's to
# >      say, not the code's.
#
# Written down in task 046 after measuring what was already true rather than
# deciding something new. Exit 2 already meant *refused* in fifteen
# assertions across three test files, and no document anywhere stated an exit
# code -- a contract by every practical measure and not one by the only
# measure a user has. So this is a promotion from undocumented to written,
# not an invention.
#
# WHY THE RULE IS ABOUT *RAN* RATHER THAN ABOUT *REFUSED*
# -------------------------------------------------------
# "Exit 2 means refused" would be true of every stage and false of
# `fixture verify`, which exits 2 when a fixture does not verify -- the tool
# ran and the answer was no. That is a NEGATIVE RESULT: not a refusal, not a
# failure, and the third of the three outcomes this project keeps apart
# everywhere else.
#
# `fixture verify` is the named exception rather than a counter-example,
# because it is **a checker whose whole output is the verdict**. It has
# nothing else to say, so its exit code carries the answer. A stage has an
# artifact to say it in.
#
# AND WHY NOTHING IS BROKEN TODAY, WHICH IS NOT LUCK
# --------------------------------------------------
# The stage that could most obviously have violated this does not:
# `_cmd_verify` returns **0** when a real engine contradicts the simulation,
# because the contradiction is written into `verify.json`.
#
# That is this project's own rule -- **the three outcomes live in the
# artifact, not in the process** -- holding at the process boundary without
# anyone having stated it there. A rule that has been silently obeyed is the
# cheapest kind to write down, and the tell that it was real is that breaking
# it would have broken fifteen tests nobody thought of as guarding it.
#
# The day a stage exits non-zero for a result, `classify` calls it `refused`
# or `failed` and the page says *the tool declined* about an answer the tool
# gave. `test_exit_contract.py` is what would report that.

#: Non-zero returns a stage handler is permitted, and why. Anything not here
#: is a stage reporting a finding through its exit code, which the rule above
#: forbids. A reason per entry, so an addition costs a sentence (section 7.1).
EXIT_CONTRACT = {
    # `_cmd_simulate`, when configurations were planned and not measured.
    #
    # **This is the one entry that is a finding rather than a fate**, and it
    # is listed rather than quietly permitted because the rule above says it
    # should not exist. The run happened; `simulate.json` holds the rows that
    # were measured and `simulate_info.json:dropped` names each one that was
    # not, with its reason. Under the rule that is exit 0 with the finding in
    # the artifact, exactly where the artifact already carries it.
    #
    # Its own comment gives the argument for the non-zero: "couldn't-check is
    # never rounded up to success". That is right about the outcome and it is
    # being asserted in the wrong channel -- the artifact already refuses to
    # round it up, and the exit code is being asked to repeat a claim the
    # receipt makes better.
    #
    # Left as it is, declared, and raised as the fifth contract change in
    # `tasks/046-contract-changes-pending.md`: it is `simulate`'s contract,
    # scripts may depend on it, and it is not a UI slice's to change unasked.
    # Its cost is visible here: it is the sole reason `EXIT_MEANING[1]` has
    # two meanings and `classify` has to consult the workdir at all.
    ("simulate", 1): "configurations were planned and not measured; the rows "
                     "that were are in simulate.json and each drop is named "
                     "in simulate_info.json:dropped",
}


# ------------------------------------------ reading an exit code honestly
# Task 046. A supervisor is given an exit code, a stream of output, and
# whatever landed in the workdir. `tasks/finding-refusals-arrive-as-
# tracebacks.md` measured what those codes mean, and the mapping is declared
# here rather than written into the supervisor, so every row is checkable by
# reading one table.
#
# The `1` row is the only one where a single code means two things, and it is
# the row to test hardest.
EXIT_MEANING = {
    0: ("done",
        "the command completed"),
    2: ("refused",
        "the tool declined, with a reason and a remedy. Every stage uses "
        "this code for a refusal and for nothing else; `cli.main` now routes "
        "the declared refusal types here too, which is what made `refused` "
        "reachable at all"),
    1: (None,
        "TWO THINGS, and the workdir separates them. `simulate` exits 1 when "
        "it ran and dropped some configurations -- the measured rows are in "
        "`simulate.json` and each drop is named with its reason in "
        "`simulate_info.json:dropped` -- and the interpreter exits 1 when "
        "something raised. The first is closer to done than to failed; the "
        "second produced nothing"),
}

#: The receipt whose presence says the stage actually ran. This is what
#: resolves the `1` row, and it is the whole of *the truth is the workdir*
#: made concrete: the exit code is a claim about the process, the receipt is
#: evidence about the work.
STAGE_RECEIPT = {
    "characterize": "characterization.json",
    "simulate": "simulate.json",
    "verify": "verify.json",
    "report": "report.json",
    "chunk": "chunk_info.json",
    "propose": "proposals",
    "pod plan": "pod_plan.json",
    "pod status": None,
    "pod watch": None,
    "pod fetch": None,
}


def classify(stage, exit_code, workdir):
    """`(state, why)` for a finished job. Never guesses.

    `why` is returned beside the state because a reader of a `failed` job
    deserves to know whether it was the code or the missing receipt that
    decided -- `docs/PRACTICE.md` §7.2, an exemption or an inference that is
    not reported has only moved the silence.
    """
    if stage not in STAGES:
        raise JobError(f"{stage!r} is not a stage")
    state, why = EXIT_MEANING.get(exit_code, (None, None))
    if state is not None:
        return state, why
    if why is None:
        return FAILED, (f"exit {exit_code}, which is not a code this tool "
                        f"returns deliberately")

    receipt = STAGE_RECEIPT.get(stage)
    if receipt is None:
        # A stage that writes no receipt of its own cannot be separated this
        # way, and saying so beats guessing. `failed` is the safe reading:
        # calling a crash `done` would put a run in the list as complete.
        return FAILED, ("exit 1, and this stage writes no receipt of its "
                        "own, so nothing here can tell a drop from a crash")
    where = os.path.join(workdir or "", receipt)
    if os.path.exists(where):
        return DONE, ("exit 1 with %s written: the run happened and dropped "
                      "something, which the receipt records" % receipt)
    return FAILED, ("exit 1 with no %s: nothing was produced, so the run "
                    "did not happen" % receipt)
