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
        #: Processes this supervisor started, by job id. Not state about the
        #: work -- the work's state is the record and the workdir -- but a
        #: handle on children of THIS process, which no file can hold.
        self._live = {}
        self._handles = {}

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
        """Record how a job ended, from its exit code.

        Everything the classification rests on goes into the record: the
        code, the state, **and the reason** -- because a reader of this one
        record does not have the exit code's table in front of them and
        cannot re-run the decision.
        """
        if handle is not None and not handle.closed:
            handle.close()
        state, why = jobs.classify(job.stage, exit_code)
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

    # -- advancing ---------------------------------------------------------
    def tick(self):
        """Advance the list by one step: reap what finished, start what is
        next. Returns what it did, so a caller can log it and a test can
        assert on it rather than inferring from the file.

        **One job at a time.** A `simulate` uses the machine, and two of them
        fight for it -- the second would measure a loaded machine and record
        timings nobody can compare. This is a decision rather than a
        limitation, and it is the reason `started` and `ended` in a record
        mean what they look like.

        Idempotent and cheap, so it can be called on a timer without the
        caller tracking anything.
        """
        did = []
        records = self.read()

        for job in records:
            if job.state != jobs.RUNNING:
                continue
            proc = self._live.get(job.id)
            if proc is None:
                # Running in the record and not a child of this process: a
                # previous supervisor started it and did not survive. Left
                # alone rather than guessed at -- the record says running,
                # and this process cannot tell whether it still is. Saying
                # so is `couldnt_check` in the one place the three outcomes
                # have no field for it, so it is named here instead.
                did.append(("orphaned", job.id))
                continue
            code = proc.poll()
            if code is None:
                continue
            self.finish(job, code, self._handles.pop(job.id, None))
            self._live.pop(job.id, None)
            did.append(("finished", job.id))

        records = self.read()
        if any(j.state == jobs.RUNNING for j in records):
            return did
        queued = [j for j in records if j.state == jobs.QUEUED]
        if queued:
            job = sorted(queued, key=lambda j: j.id)[0]
            proc, handle = self.start(job)
            self._live[job.id] = proc
            self._handles[job.id] = handle
            did.append(("started", job.id))
        return did

    def run_forever(self, interval=1.0, stop=None):
        """Tick until told to stop. The whole scheduler.

        There is no queue object and no worker pool: the job list on disk is
        the queue, so a supervisor that dies and is restarted picks up
        exactly where the file says, and nothing is held anywhere else.
        """
        while stop is None or not stop.is_set():
            try:
                self.tick()
            except jobs.JobError:                        # pragma: no cover
                # A malformed list is not a reason to stop advancing the
                # ones that are fine -- but it is not this loop's to repair
                # either, so it is left for a reader to see.
                pass
            time.sleep(interval)

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

    def do_OPTIONS(self):                              # noqa: N802
        """The preflight, for the one permitted origin and no other."""
        self.server.channel._preflight(self)

    def _only_post(self):
        _send(self, 405, {"error": "the supervisor answers POST; the job "
                                   "list is read from the runs directory"})

    do_GET = do_PUT = do_PATCH = do_DELETE = _only_post


def _send(req, status, obj, extra=()):
    body = b"" if obj is None else json.dumps(obj).encode("utf-8")
    req.send_response(status)
    if obj is not None:
        req.send_header("Content-Type", "application/json")
    req.send_header("Content-Length", str(len(body)))
    req.send_header("X-Content-Type-Options", "nosniff")
    for name, value in extra:
        req.send_header(name, value)
    req.end_headers()
    if body:
        req.wfile.write(body)


class _HTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True


class OriginRefused(ValueError):
    """An allowance that is not exactly one origin."""


def _one_origin(value):
    """Exactly one origin, or None. Refused at construction.

    A wildcard is refused because it is the whole loosening with none of the
    narrowness. A list is refused because the first list is always two
    entries and the second is always longer, and a value nobody can read at
    a glance is a value nobody audits.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise OriginRefused("an origin allowance is one origin as a string")
    value = value.strip()
    if value == "*":
        raise OriginRefused(
            "a wildcard is not an allowance, it is the absence of one; name "
            "the single origin the page is served from")
    if "," in value or " " in value:
        raise OriginRefused(
            "exactly one origin, never a list: %r. Two callers mean two "
            "supervisors or one decision nobody has made" % value)
    if not value.startswith(("http://", "https://")):
        raise OriginRefused(
            "an origin is scheme://host:port, not %r" % value)
    if value.rstrip("/") != value:
        raise OriginRefused("an origin carries no path, not even %r" % value)
    return value


class Channel:
    """A loopback door onto one supervisor.

    Bound to 127.0.0.1, with a token the caller must present. The address
    file is how the server finds both.
    """

    #: A body larger than this is not a job request.
    MAX_BODY = 1 << 16

    def __init__(self, sup, host="127.0.0.1", port=0, token=None,
                 allow_origin=None):
        """`allow_origin` is **exactly one origin, or none at all.**

        The lab's server may not make a request of its own -- its own header
        has said so since it was written, and that is the last promise on
        that list still standing. So the page talks to this process directly,
        and this process has to permit one origin to do it.

        Which is a loosening, and it is spent here rather than there on a
        distinction worth stating: **the lab's no-CORS rule protects a server
        that serves evidence; this serves an action already gated by a
        token.** Those are different properties, so spending one is not
        spending the other.

        Three things hold it narrow.

        **One origin, never a wildcard and never a list.** `*` and any value
        carrying a comma or a space are refused at construction, not at
        request time, because a configuration mistake should not wait for a
        request to become visible.

        **It is not a substitute for the token.** An allowed origin with no
        token is refused exactly as any other request is. CORS says which
        page the browser will let read a reply; it says nothing about who
        may ask.

        **`None` means no cross-origin access at all**, which is the default,
        so a supervisor started without being told an origin is not quietly
        open to one.
        """
        self.sup = sup
        self.token = token or secrets.token_urlsafe(32)
        self.allow_origin = _one_origin(allow_origin)
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

    # -- the one origin ----------------------------------------------------
    def _permitted(self, req):
        """The request's Origin, if it is the one permitted. Exact string
        comparison: a prefix match would let `http://127.0.0.1:1234.evil`
        through, which is the classic way this check is got wrong."""
        offered = req.headers.get("Origin")
        if not self.allow_origin or not offered:
            return None
        return self.allow_origin if offered == self.allow_origin else None

    def _cors_headers(self, req):
        origin = self._permitted(req)
        if origin is None:
            return ()
        return (("Access-Control-Allow-Origin", origin),
                ("Vary", "Origin"),
                ("Access-Control-Allow-Headers", SUPERVISOR_TOKEN_HEADER
                 + ", Content-Type"),
                ("Access-Control-Allow-Methods", "POST"),
                ("Access-Control-Max-Age", "600"))

    def _preflight(self, req):
        if self._permitted(req) is None:
            # No allowance echoed, so the browser refuses the real request.
            # Answered rather than dropped, so the page sees a refusal it can
            # show instead of a network error it cannot explain.
            return _send(req, 403, {
                "error": "this supervisor permits one origin and it is not "
                         "this one"})
        _send(req, 204, None, extra=self._cors_headers(req))

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

        # The allowance decides what a browser may READ; the token decides
        # who may ASK. An allowed origin with no token is refused exactly as
        # anything else is, and the refusal still carries the allowance so
        # the page can read it and say so.
        cors = self._cors_headers(req)
        offered = req.headers.get(SUPERVISOR_TOKEN_HEADER) or ""
        if not hmac.compare_digest(offered.encode("utf-8"),
                                   self.token.encode("utf-8")):
            return _send(req, 403, {
                "error": "refused: this supervisor's token is required"},
                extra=cors)

        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError) as e:
            return _send(req, 400, {"error": "unreadable body: %s" % e})
        if not isinstance(body, dict):
            return _send(req, 400, {"error": "expected a JSON object"})

        path = urllib.parse.urlsplit(req.path).path
        if path == "/enqueue":
            return self._enqueue(req, body, cors)
        if path == "/cancel":
            return self._cancel(req, body, cors)
        return _send(req, 404, {"error": "not found"}, extra=cors)

    def _enqueue(self, req, body, cors=()):
        invocation = body.get("invocation")
        if not isinstance(invocation, list) or not invocation:
            return _send(req, 400, {
                "error": "a job is a CLI invocation and this names none"},
                extra=cors)
        try:
            job = self.sup.enqueue(body.get("stage"), invocation,
                                   workdir=body.get("workdir"))
        except jobs.JobError as e:
            # The supervisor's own refusal, verbatim. It already names what
            # is wrong and what the set is; rephrasing here would be the
            # second implementation one hop further out.
            return _send(req, 400, {"error": str(e), "refusal": str(e)},
                         extra=cors)
        return _send(req, 200, {"job": job.to_dict()}, extra=cors)

    def _cancel(self, req, body, cors=()):
        wanted = body.get("id")
        for job in self.sup.read():
            if job.id != wanted:
                continue
            if not job.live:
                return _send(req, 409, {
                    "error": "this job is already %s; a terminal state is "
                             "terminal, and a late cancellation must not "
                             "rewrite what happened" % job.state}, extra=cors)
            return _send(req, 200, {"job": self.sup.cancel(job).to_dict()},
                         extra=cors)
        return _send(req, 404, {"error": "no job %r in this list" % wanted},
                     extra=cors)


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
