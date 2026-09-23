"""The second process: it owns the job list and runs the commands.

Task 046 step 4. `docs/INTERFACE.md`: *the supervisor is a second process
holding no state beyond the job list; the truth is the workdir.*

WHY IT IS A SECOND PROCESS, WHICH IS A GUARD'S DECISION AND NOT A PREFERENCE
----------------------------------------------------------------------------
The lab's guard refuses `oneground.models`, `oneground.simulate` and the rest
to every served module. A server that may not import the measuring packages
cannot run them, and this is the same ruling one step on: a server that may
not write cannot own the record of what ran. So the server reads
`jobs.read()` and this process writes.

It also buys the property the brief asks for directly: **this crashing must
not kill a running `simulate`.** The child is spawned and not held — no job
object, no process group, no cleanup on exit — so a supervisor that dies
leaves the work running and the workdir is still the truth when something
comes back to look.

WHAT A RECORD MEANS IS IN THE RECORD
------------------------------------
A reader of one artifact does not have the state. So everything a record
means travels in it: the invocation that produced it, the exit code, the
classification **and the reason for the classification**, the refusal
verbatim, and whether the outputs are partial. Nothing here is inferable
only by someone holding the whole list.

That is why `classify` returns a reason and why this stores it. A `failed`
job whose record cannot say whether it was the exit code or a missing receipt
that decided has told the reader the conclusion and kept the evidence.

THE REFUSAL IS CAPTURED, NOT PARSED
-----------------------------------
When a job is refused the record carries the process's error output
**whole and verbatim**. Not the message extracted from it: extracting would
mean recognising `cli.main`'s own format here, which is the second
implementation `oneground/refusals.py` exists to have avoided. The CLI
prints one line for a refusal now, so whole and one-line are the same thing,
and if that ever stops being true the record is still honest.
"""

import json
import os
import subprocess
import sys
import time
import uuid

from . import jobs, provenance

#: Where a job's streamed output lands, under the runs directory.
LOGS_DIR = "logs"

#: How long `cancel` waits for a child to stop before it stops being polite.
#: A `simulate` writing a receipt deserves the chance to finish the file it
#: is in the middle of; a run that ignores the request is not left running.
CANCEL_GRACE_SECONDS = 10.0


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_id(stage):
    """Sortable, readable in a directory listing, and carrying nothing a path
    would have to escape -- `jobs.valid_id` is the fence."""
    slug = stage.replace(" ", "-")
    return "%s-%s-%s" % (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
                         slug, uuid.uuid4().hex[:8])


class Supervisor:
    """Owns the job list for one runs directory.

    One instance per directory, one process. It does not hold jobs in memory
    between calls beyond the list it just wrote: the file is the state, so a
    restart reads it back and nothing is lost with the process.
    """

    def __init__(self, runs_dir):
        self.runs_dir = os.path.abspath(runs_dir)
        self.path = os.path.join(self.runs_dir, jobs.JOBS_NAME)
        self.logs = os.path.join(self.runs_dir, LOGS_DIR)

    # -- the list ----------------------------------------------------------
    def read(self):
        return jobs.read(self.runs_dir)

    def _write(self, records):
        """Atomic, because the server reads this file while we write it.

        A half-written list is not a slow read, it is a parse error in the
        page -- and `jobs.read` correctly refuses a corrupt file rather than
        returning nothing, so a torn write would take the run list down with
        it. Temp beside the target, then replace.
        """
        os.makedirs(self.runs_dir, exist_ok=True)
        tmp = self.path + ".writing"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump([r.to_dict() for r in records], f, indent=1,
                      sort_keys=True)
        os.replace(tmp, self.path)

    def _replace(self, job):
        records = [j for j in self.read() if j.id != job.id]
        records.append(job)
        records.sort(key=lambda j: j.id)
        self._write(records)
        return job

    # -- creating ----------------------------------------------------------
    def enqueue(self, stage, invocation, workdir=None):
        """Record a job as queued. Runs nothing."""
        if stage in jobs.NOT_A_JOB:
            raise jobs.JobError(
                f"{stage} is never a job: {jobs.NOT_A_JOB[stage]}")
        job = jobs.Job(id=new_id(stage), stage=stage, invocation=invocation,
                       workdir=workdir or self.runs_dir, state=jobs.QUEUED,
                       log=os.path.join(LOGS_DIR, new_id(stage) + ".log"))
        if not jobs.valid_id(job.id):                    # pragma: no cover
            raise jobs.JobError(f"generated an unusable job id: {job.id!r}")
        job.log = os.path.join(LOGS_DIR, job.id + ".log")
        return self._replace(job)

    # -- running -----------------------------------------------------------
    def start(self, job, python=None):
        """Spawn the CLI and return the process, with the log open.

        **The child is not held.** No process group, no job object, no
        `atexit` that reaps it: if this process dies the run continues, which
        is the property the brief asks for in as many words.
        """
        os.makedirs(self.logs, exist_ok=True)
        log_path = os.path.join(self.runs_dir, job.log)
        handle = open(log_path, "w", encoding="utf-8", newline="\n")
        argv = [python or sys.executable, "-c",
                "from oneground.cli import main; import sys; "
                "sys.exit(main())"] + list(job.invocation)

        # THE CHILD RUNS THIS BUILD, and that is not a convenience. A
        # subprocess resolves `oneground` by install location, and on the
        # machine this was written the install pointed at a different
        # checkout -- so the first run of this code produced a traceback
        # from a build weeks out of date, in a test asserting the refusal
        # that build did not have.
        #
        # It is the third appearance of one defect: a server serving a build
        # nobody named, and now a supervisor spawning one. The rule from the
        # first is the rule here -- anything you hand someone to look at
        # states what it is -- and the supervisor's version of stating it is
        # to make it true: the package directory this process imported is
        # put ahead of whatever the child would otherwise find.
        env = dict(os.environ)
        here = os.path.dirname(provenance.PACKAGE_DIR)
        env["PYTHONPATH"] = (here + os.pathsep + env["PYTHONPATH"]
                             if env.get("PYTHONPATH") else here)
        proc = subprocess.Popen(
            argv, stdout=handle, stderr=subprocess.STDOUT,
            cwd=self.runs_dir, close_fds=True, env=env)
        job.started = _now()
        # Which build produced what this job leaves behind. The receipts get
        # the commit from `producing_version`; this is the package directory,
        # which is the field that discriminated when two checkouts shared a
        # commit.
        job.build = provenance.PACKAGE_DIR
        job.become(jobs.RUNNING)
        self._replace(job)
        return proc, handle

    def finish(self, job, exit_code, handle=None):
        """Record how a job ended, from its exit code and the workdir.

        Everything the classification rests on goes into the record: the
        code, the state, **and the reason** -- because a reader of this one
        record does not have the workdir in front of them and cannot re-run
        the decision.
        """
        if handle is not None and not handle.closed:
            handle.close()
        state, why = jobs.classify(job.stage, exit_code, job.workdir)
        job.ended = _now()
        job.exit_code = exit_code
        refusal = None
        if state == jobs.REFUSED:
            # Whole and verbatim. Extracting the sentence would mean
            # recognising `cli.main`'s format here, which is the second
            # implementation this project keeps refusing to write.
            refusal = self._log_text(job) or (
                "the command exited %s, which this tool uses only for a "
                "refusal, and wrote nothing to its log" % exit_code)
        job.become(state, refusal=refusal, exit_code=exit_code)
        job.why = why
        return self._replace(job)

    def _log_text(self, job):
        try:
            with open(os.path.join(self.runs_dir, job.log),
                      encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return None

    # -- stopping ----------------------------------------------------------
    def cancel(self, job, proc=None, grace=CANCEL_GRACE_SECONDS):
        """A real stop, with a record saying so and the partial outputs kept.

        Two things this does not do. It does not delete what the run
        produced: a half-written characterization is evidence about a
        cancelled run and throwing it away answers a question nobody asked.
        And it does not present those outputs as complete -- `partial` rides
        in the record, because a reader of one artifact does not have the
        state.
        """
        if proc is not None and proc.poll() is None:
            proc.terminate()
            deadline = time.time() + grace
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.05)
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        job.ended = _now()
        job.become(jobs.CANCELLED, partial=True,
                   exit_code=None if proc is None else proc.returncode)
        job.why = ("cancelled; whatever it had written is kept and marked "
                   "partial rather than presented as complete")
        return self._replace(job)

# ======================================================== the channel
# The server may not write, so it cannot enqueue a job itself. It asks this
# process to, over loopback, with a token -- the same shape as the lab's own
# door and for the same reason.
#
# WHY NOT A FILE THE SERVER DROPS IN A DIRECTORY. Because that is a write,
# and the whole point of the split is that the served package has exactly one
# module that opens a file for writing and it writes requirements files. A
# queue directory would be a second write path wearing a different hat, and
# `guard.check_write_path` would have to be taught to ignore it -- an
# exemption that describes convenience rather than the world (section 5).
#
# The server finds this process the way a reader finds anything here: a file
# in the runs directory, written by the process that owns it.

import hmac                                                   # noqa: E402
import http.server                                            # noqa: E402
import secrets                                                # noqa: E402
import threading                                              # noqa: E402
import urllib.parse                                           # noqa: E402

#: Where the supervisor says how to reach it.
ADDRESS_NAME = "supervisor.json"

SUPERVISOR_TOKEN_HEADER = "X-Oneground-Supervisor-Token"


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "oneground-supervisor"
    sys_version = ""

    def log_message(self, fmt, *args):                 # noqa: A002
        """Nothing is logged: a request line carries the token."""

    def do_POST(self):                                 # noqa: N802
        self.server.channel._answer(self)

    def _only_post(self):
        _send(self, 405, {"error": "the supervisor answers POST; the job "
                                   "list is read from the runs directory"})

    do_GET = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _only_post


def _send(req, status, obj):
    body = json.dumps(obj).encode("utf-8")
    req.send_response(status)
    req.send_header("Content-Type", "application/json")
    req.send_header("Content-Length", str(len(body)))
    req.send_header("X-Content-Type-Options", "nosniff")
    req.end_headers()
    req.wfile.write(body)


class _HTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True


class Channel:
    """A loopback door onto one supervisor.

    Bound to 127.0.0.1, with a token the caller must present. The address
    file is how the server finds both.
    """

    #: A body larger than this is not a job request.
    MAX_BODY = 1 << 16

    def __init__(self, sup, host="127.0.0.1", port=0, token=None):
        self.sup = sup
        self.token = token or secrets.token_urlsafe(32)
        self.httpd = _HTTPServer((host, port), _Handler)
        self.httpd.channel = self
        self.port = self.httpd.server_address[1]
        self.url = "http://%s:%d" % (host, self.port)
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self.httpd.serve_forever,
                                        daemon=True)
        self._thread.start()
        self.announce()
        return self

    def announce(self):
        """Write where this supervisor is, for the server to read.

        It carries the build for the same reason `/api/check` does: a server
        and a supervisor running different checkouts would each be correct
        about themselves and wrong together, which is the defect that has
        now appeared three times.
        """
        os.makedirs(self.sup.runs_dir, exist_ok=True)
        target = os.path.join(self.sup.runs_dir, ADDRESS_NAME)
        tmp = target + ".writing"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"url": self.url, "token": self.token,
                       "pid": os.getpid(),
                       "build": provenance.PACKAGE_DIR}, f, indent=1)
        os.replace(tmp, target)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        try:
            os.remove(os.path.join(self.sup.runs_dir, ADDRESS_NAME))
        except OSError:                                  # pragma: no cover
            pass

    # -- answering ---------------------------------------------------------
    def _answer(self, req):
        try:
            length = int(req.headers.get("Content-Length") or 0)
        except ValueError:
            req.close_connection = True
            return _send(req, 400, {"error": "unreadable Content-Length"})
        if length > self.MAX_BODY:
            req.close_connection = True
            return _send(req, 413, {"error": "a job request is not that big"})
        # Read before any refusal: answering a POST without draining resets
        # the connection and the caller sees a transport error instead of
        # the refusal. Learned twice already in this slice.
        raw = req.rfile.read(length) if length else b""

        offered = req.headers.get(SUPERVISOR_TOKEN_HEADER) or ""
        if not hmac.compare_digest(offered.encode("utf-8"),
                                   self.token.encode("utf-8")):
            return _send(req, 403, {
                "error": "refused: this supervisor's token is required"})

        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError) as e:
            return _send(req, 400, {"error": "unreadable body: %s" % e})
        if not isinstance(body, dict):
            return _send(req, 400, {"error": "expected a JSON object"})

        path = urllib.parse.urlsplit(req.path).path
        if path == "/enqueue":
            return self._enqueue(req, body)
        if path == "/cancel":
            return self._cancel(req, body)
        return _send(req, 404, {"error": "not found"})

    def _enqueue(self, req, body):
        invocation = body.get("invocation")
        if not isinstance(invocation, list) or not invocation:
            return _send(req, 400, {
                "error": "a job is a CLI invocation and this names none"})
        try:
            job = self.sup.enqueue(body.get("stage"), invocation,
                                   workdir=body.get("workdir"))
        except jobs.JobError as e:
            # The supervisor's own refusal, verbatim. It already names what
            # is wrong and what the set is; rephrasing here would be the
            # second implementation one hop further out.
            return _send(req, 400, {"error": str(e), "refusal": str(e)})
        return _send(req, 200, {"job": job.to_dict()})

    def _cancel(self, req, body):
        wanted = body.get("id")
        for job in self.sup.read():
            if job.id != wanted:
                continue
            if not job.live:
                return _send(req, 409, {
                    "error": "this job is already %s; a terminal state is "
                             "terminal, and a late cancellation must not "
                             "rewrite what happened" % job.state})
            return _send(req, 200, {"job": self.sup.cancel(job).to_dict()})
        return _send(req, 404, {"error": "no job %r in this list" % wanted})


def address(runs_dir):
    """How to reach the supervisor for this directory, or None.

    None is a real answer and the page says so: *no supervisor is running,
    so nothing can be started from here*. Pretending otherwise would put a
    button on the page that fails when pressed, which is worse than an
    absent one because it looks like a defect in the tool rather than a
    process nobody started.
    """
    try:
        with open(os.path.join(runs_dir, ADDRESS_NAME), encoding="utf-8") as f:
            found = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(found, dict) or not found.get("url"):
        return None
    return found
