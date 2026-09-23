"""`oneground lab <workdir>`: the lab, served on this machine (task 024).

WHY A SERVER RATHER THAN A FILE
-------------------------------
A generated file would have to carry the corpus inside it; a server reads the
run directory as it is. Any corpus size works, the recall panel's "simulate
this epsilon" has a command to print, and task 023b's render-on-release mode
has somewhere to live. The cost is a process and a port, and this module keeps
both boring.

A TRANSPORT, NEVER A SECOND RENDERER
------------------------------------
Every drawing the server returns is `contract.draw(view, ...)` of a view in
`oneground/lab/views/`, serialised and sent unchanged. The server computes
nothing a view draws: it parses a query string, picks the loaded state a view
is drawn from (`runs.LoadedRun`), and writes the view's own `as_dict()` to the
socket. It does not import numpy. Before it binds a port it runs the view
guard and `guard.check_transport` over its own source, and refuses to start if
either finds anything.

WHAT IT NEVER DOES
------------------
- write a file **itself**: exactly one served module opens one for writing
  (`compose.py`, requirements files, through the write guard), and
  `guard.check_write_path` refuses the session at startup if any other can.
  This list said "no write path, and no method but GET" until task 046 gave
  the page a form -- both halves false the hour it landed, in the served
  module's own header, which is where a reader checks. Corrected rather than
  deleted: what it guarantees is narrower now and still worth stating.
- send a file from the run directory: states are drawn, never served raw, and
  the only files served are the interface's own, from a fixed table -- no part
  of a request path is ever joined to a directory
- run a simulation, or anything else: a job is run by the supervisor, a
  second process, because a server that may not import the measuring packages
  cannot run them
- answer a request without this session's token, or for a Host it did not bind
- send a CORS header, list a directory, or log a request line (it carries the
  token)
- **make a request of its own.** Still true, and the one on this list most
  under pressure: the write half needs a job enqueued and the supervisor owns
  the job list. Forwarding would be the easy way and would turn this server
  into something that makes requests, which is a property worth more than the
  convenience. See `tasks/046-interface-write.report.md`; the ruling is not
  this module's to make.

What the token does and does not protect against is in docs/LAB.md.
"""

import hashlib
import hmac
import http.server
import ipaddress
import json
import math
import os
import secrets
import socket
import threading
import time
import urllib.parse

from oneground import jobs as jobsmod
from oneground import provenance
from oneground import supervisor as supmod
from oneground.intake import fields

from . import compose, contract, guard
from . import citations as citationsmod
from . import runs as runsmod
from .receipt import draw_receipt
from .runs import LabRunError, LoadedRun                      # noqa: F401
from .views.compare import ComparisonView
from .views.evidence import EvidenceDrawerView
from .views.headline import RunHeadlineView, RunProgressView
from .views.run_list import RunListView
from .views import GroundView, QueryIndexView, QueryTraceView

K_TRUE = 10
MODE_READINGS = 5
MODE_DRAWS = 20             # per reading
MODE_WARMUP = 3
EPSILON_CEILING = 1.0

TOKEN_PARAM = "token"
TOKEN_HEADER = "X-Oneground-Token"
TOKEN_PLACEHOLDER = "__ONEGROUND_LAB_TOKEN__"

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "static")
# The only files a request can reach: the interface's own, by exact path.
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/lab.css": ("lab.css", "text/css; charset=utf-8"),
    "/static/lab.js": ("lab.js", "text/javascript; charset=utf-8"),
    "/static/boot.js": ("boot.js", "text/javascript; charset=utf-8"),
    "/static/ui.js": ("ui.js", "text/javascript; charset=utf-8"),
    "/static/compose.js": ("compose.js", "text/javascript; charset=utf-8"),
    "/static/jobs.js": ("jobs.js", "text/javascript; charset=utf-8"),
    "/static/ui.css": ("ui.css", "text/css; charset=utf-8"),
}
ENDPOINTS = {
    "/api/check": "check",
    "/api/runs": "run_list",
    "/api/headline": "headline",
    "/api/evidence": "evidence",
    "/api/compare": "compare",
    "/api/run": "describe_run",
    "/api/ground": "ground",
    "/api/trace": "trace",
    "/api/query-index": "query_index",
    "/api/ids": "ids",
    # The write half's two reads. They are GETs because they change nothing:
    # the field table is the declaration the form renders itself from, and
    # the template is that declaration written out as a file.
    "/api/compose/fields": "compose_fields",
    "/api/compose/template": "compose_template",
    # The jobs half, all reads. The server never enqueues and never
    # cancels: it has no write path and makes no request of its own, so the
    # page is told where the supervisor is and speaks to it directly.
    "/api/jobs": "job_list",
    "/api/jobs/targets": "job_targets",
    "/api/jobs/log": "job_log",
    "/api/supervisor": "supervisor_address",
}

#: The write half. POST only, and only in a `ui` session -- see
#: `answer_write`. Kept in their own map rather than mixed into `ENDPOINTS`
#: so that a read route can never be reached by POST and a write route can
#: never be reached by GET: the split is in the table, not in a conditional
#: somebody has to remember to write.
WRITE_ENDPOINTS = {
    "/api/compose/open": "compose_open",
    "/api/compose/preview": "compose_preview",
    "/api/compose/write": "compose_write",
}

#: A requirements file is prose-sized. This is two orders of magnitude more
#: than the largest example in the tree and it is here so that an unbounded
#: body cannot be posted to a loopback server.
MAX_BODY = 1 << 20

#: How much of an over-sized body is drained so that the refusal can be read.
#: Above this the connection is closed instead: a caller sending eight
#: megabytes to a loopback form is not owed a readable answer.
DRAIN_CEILING = 8 << 20
SECURITY_HEADERS = (
    ("Content-Security-Policy",
     "default-src 'none'; script-src 'self'; style-src 'self'; "
     "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
     "form-action 'none'; frame-ancestors 'none'"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Cache-Control", "no-store"),
)


class LabRefused(RuntimeError):
    """The lab will not start as asked. The message says why and what to do."""


# ------------------------------------------------------------------ host
def is_loopback(host):
    host = host.strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_host(host, i_know=False):
    """None on a loopback address. Anything else serves the run to every
    machine that can reach this one: refused without `i_know`, and with it,
    the warning that must be printed, naming what is exposed."""
    if is_loopback(host):
        return None
    if not i_know:
        raise LabRefused(
            f"--host {host} is not a loopback address. It would serve this "
            "run -- its drawings, its figures, the workdir's path and its "
            "digests -- to every machine that can reach this one, guarded "
            "only by the token in the URL. Pass --i-know to do that anyway, "
            "or leave --host at 127.0.0.1.")
    return (f"WARNING: --host {host} --i-know: this lab is reachable from "
            "the network. Anyone who can reach this machine and holds the "
            "URL, token included, can read every drawing of this run -- the "
            "ground, every query's trace, the figures -- and the workdir's "
            "path and digests. It still writes nothing and runs nothing.")


# ---------------------------------------------------------- measurements
def p95(values):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def measure_render_mode(run, draws=MODE_DRAWS, override=None,
                        readings=MODE_READINGS):
    """Time whole ground draws on this host, for this corpus, and choose the
    mode (tasks 023b, 024b).

    Up to `readings` readings of `draws` draws each, across the epsilon range.
    Redraw on move only if every reading's p95 is within the margined
    threshold (`choose_mode`). The first reading above it settles the
    decision, so measuring stops there: a slow host does not pay for readings
    that cannot change the answer.

    `override` (from `--mode`) wins, and the measurement is still taken and
    kept, so the caption can say what measurement alone would have chosen.
    """
    if not run.has_epsilon:
        return contract.RenderMode(mode=contract.STATIC, p95_ms=None,
                                   chosen_by="this family has no epsilon")
    draws = max(2, int(draws))
    readings = max(1, int(readings))
    top = run.epsilon_max()
    positions = [top * i / (draws - 1) for i in range(draws)]
    for e in positions[:MODE_WARMUP]:
        contract.draw(GroundView(run.epsilon_set(e)), *run.base)
    per_reading, everything = [], []
    for _ in range(readings):
        timings = []
        for e in positions:
            eps = run.epsilon_set(e)
            start = time.perf_counter()
            contract.draw(GroundView(eps), *run.base)
            timings.append((time.perf_counter() - start) * 1000.0)
        per_reading.append(round(p95(timings), 1))
        everything.extend(timings)
        if per_reading[-1] > contract.THRESHOLD_MS:
            break
    return choose_mode(per_reading, draws, override,
                       pooled=round(p95(everything), 1), planned=readings)


def choose_mode(readings_ms, draws, override=None, pooled=None, planned=0):
    """The rule, and nothing else: redraw on move only when every reading's
    p95 is within `contract.THRESHOLD_MS`; render on release when the
    readings straddle it or sit above it. An override wins and keeps the
    measured choice beside it."""
    readings = tuple(float(x) for x in readings_ms)
    if not readings:
        raise ValueError("a render mode needs at least one reading")
    within = [x <= contract.THRESHOLD_MS for x in readings]
    if all(within):
        verdict = contract.WITHIN
    elif any(within):
        verdict = contract.STRADDLED
    else:
        verdict = contract.ABOVE
    measured = contract.MOVE if verdict == contract.WITHIN \
        else contract.RELEASE
    return contract.RenderMode(
        mode=override or measured, p95_ms=max(readings), draws=draws,
        chosen_by="--mode" if override else "measurement", measured=measured,
        readings_ms=readings, pooled_p95_ms=pooled, verdict=verdict,
        planned=int(planned or len(readings)))


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_manifests(directories):
    """Each directory's MANIFEST.sha256, every entry checked against the file.

    A manifest entry naming anything outside its own directory is reported as
    unverified rather than followed.
    """
    report = []
    for directory in directories:
        manifest = os.path.join(directory, "MANIFEST.sha256")
        entry = {"directory": directory, "files": []}
        if not os.path.isfile(manifest):
            entry["manifest"] = None
            entry["note"] = (f"{contract.COULDNT_CHECK}: no MANIFEST.sha256 "
                             "in this directory")
            report.append(entry)
            continue
        entry["manifest"] = "MANIFEST.sha256"
        with open(manifest, encoding="utf-8") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]
        for line in lines:
            digest, _, name = line.partition("  ")
            name = name.lstrip("*")
            path = os.path.normpath(os.path.join(directory, name))
            inside = os.path.dirname(path) == os.path.normpath(directory)
            actual = (_sha256(path) if inside and os.path.isfile(path)
                      else None)
            entry["files"].append({"name": name, "sha256": digest,
                                   "verified": actual == digest})
        entry["all_verified"] = all(f["verified"] for f in entry["files"])
        report.append(entry)
    return report


# ---------------------------------------------------------------- server
class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "oneground-lab"
    sys_version = ""

    def log_message(self, format, *args):              # noqa: A002
        """Nothing is logged: a request line carries the session token."""

    def do_GET(self):                                   # noqa: N802
        self.server.lab.answer(self)

    def do_POST(self):                                  # noqa: N802
        self.server.lab.answer_write(self)

    def _no_write_path(self):
        self.server.lab.send(self, 405, {
            "error": "the lab has no write path; only GET is answered"},
            extra=(("Allow", "GET"),))

    do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _no_write_path


class _HTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True


class _HTTPServer6(_HTTPServer):
    address_family = socket.AF_INET6


class LabServer:
    """One lab session over one loaded run.

    Holds the loaded run, the token, the measured render mode, the verified
    digests and the interface's own files -- all fixed at startup -- and no
    state of its own beyond them.
    """

    def __init__(self, run=None, host="127.0.0.1", port=0, mode=None,
                 i_know=False, draws=MODE_DRAWS, token=None, runs_dir=None,
                 demo=False):
        """One session, over one run (`oneground lab`) or over a directory of
        them (`oneground ui`).

        The same server, the same token, the same guard: task 041 points it at
        a directory rather than replacing it, because a second server would be
        a second implementation of everything the first one refuses.

        Over a directory the render mode is not measured at startup. It is a
        measurement of drawing one run's ground, and until a run is opened
        there is nothing to draw -- measuring it against an arbitrary run
        would report a number about a run the reader did not ask for.
        """
        if demo and run is None and runs_dir is None:
            runs_dir = runsmod.demo_root()
        if (run is None) == (runs_dir is None):
            raise LabRefused("a lab session serves one run or one runs "
                             "directory, not both and not neither")
        # Which build is this? Asked before anything binds, because a
        # server that cannot answer it is a URL nobody should be handed.
        #
        # A session was started from this project and handed over to be
        # looked at. It answered 200, listed nine runs and served a page with
        # no write half -- the console script resolves the package by install
        # location, and that install pointed at a third checkout weeks out of
        # date. The suite had passed against a different directory minutes
        # before. Nothing was broken; the build being served was simply not
        # the one anyone had in mind, and no part of the system had ever been
        # asked to say which build it was.
        self.build = provenance.identity()
        clash = provenance.conflicting_checkout()
        if clash is not None:
            raise LabRefused(
                "this would serve a different build than the one you are "
                "working on.\n"
                f"  imported:          {clash['imported']}\n"
                f"  working directory: {clash['working_directory']}\n"
                "The console script resolves the package by install "
                "location, not by working directory. Run the checkout you "
                "mean -- `python -c \"from oneground.cli import main; "
                "main()\"` from it, or reinstall it -- rather than reading "
                "a page whose subject you cannot name.")
        self.warning = check_host(host, i_know)
        broken = {**guard.check_views(), **guard.check_transport(),
                  **guard.check_contract()}
        # Task 046: a served module that writes is refused at startup, like
        # a view that measures. The write path is one module by declaration
        # (`guard.WRITE_MODULES`) and this is where that stops being a
        # convention -- a session does not start if anything else can write.
        writes = guard.check_write_path()
        if writes:
            raise LabRefused(
                "these modules are served and open a file for writing, and "
                "only " + ", ".join(guard.WRITE_MODULES) + " may: " +
                "; ".join(f"{m}:{line} {detail}"
                          for m, found in sorted(writes.items())
                          for line, _, detail in found))
        unclassified = guard.unclassified_modules()
        if unclassified:
            raise LabRefused(
                "these modules are in the lab package and no rule set holds "
                f"them: {', '.join(unclassified)}. Classify each as a view, "
                "as transport or as contract machinery before serving.")
        if broken:
            raise LabRefused(
                "the lab's own modules break the rendering contract: " +
                "; ".join(f"{m}:{line} {rule} {detail}"
                          for m, found in sorted(broken.items())
                          for line, rule, detail in found))
        self.run = run
        self.runs_dir = os.path.abspath(runs_dir) if runs_dir else None
        self.token = token or secrets.token_urlsafe(32)
        self.render = (measure_render_mode(run, draws, mode)
                       if run is not None else None)
        self.digests = (verify_manifests(run.digest_directories())
                        if run is not None else [])
        self.demo = bool(demo)
        if demo:
            self.index = runsmod.demo_index()
            self.runs_dir = self.index["directory"]
        else:
            self.index = (runsmod.index_runs(self.runs_dir, verify_manifests)
                          if self.runs_dir else None)
        self.static = self._load_static()

        bind = host.strip("[]")
        server_class = _HTTPServer6 if ":" in bind else _HTTPServer
        self.httpd = server_class((bind, int(port)), _Handler)
        self.httpd.lab = self
        self.port = self.httpd.server_address[1]
        shown = f"[{bind}]" if ":" in bind else bind
        self.url = f"http://{shown}:{self.port}/?{TOKEN_PARAM}={self.token}"
        self._hosts = {h.lower() for h in (
            f"{shown}:{self.port}", f"127.0.0.1:{self.port}",
            f"localhost:{self.port}", f"[::1]:{self.port}")}
        self._thread = None

    def _load_static(self):
        out = {}
        for name, _ in STATIC.values():
            with open(os.path.join(STATIC_DIR, name), "rb") as f:
                out[name] = f.read()
        out["index.html"] = out["index.html"].replace(
            TOKEN_PLACEHOLDER.encode("ascii"), self.token.encode("ascii"))
        return out

    # ------------------------------------------------------------ requests
    def answer(self, req):
        if not self._addressed(req):
            return
        split = urllib.parse.urlsplit(req.path)
        params = urllib.parse.parse_qs(split.query, keep_blank_values=True)
        if split.path in WRITE_ENDPOINTS:
            return self.send(req, 405, {
                "error": f"{split.path} writes; it answers POST"},
                extra=(("Allow", "POST"),))
        if split.path in STATIC:
            name, content_type = STATIC[split.path]
            return self.send_bytes(req, 200, self.static[name], content_type)
        endpoint = ENDPOINTS.get(split.path)
        if endpoint is None:
            return self.send(req, 404, {"error": "not found"})
        try:
            body = getattr(self, endpoint)(params)
        except (ValueError, KeyError) as e:
            return self.send(req, 400, {"error": str(e)})
        except contract.ContractError as e:
            return self.send(req, 500, {"error": f"contract: {e}"})
        return self.send(req, 200, body)

    def answer_write(self, req):
        """POST, for the write half only.

        Host and token are checked exactly as `answer` checks them, by
        calling nothing twice: the two share `_refuse_unless_addressed`, so a
        change to the session's security model cannot reach one and miss the
        other.

        **A `lab` session refuses every write.** `oneground lab` opens one
        run for reading and that has not changed; the write half belongs to
        `oneground ui`, which is pointed at a directory of runs. Reading a
        run can never trigger a write, and this is where that is enforced
        rather than intended.
        """
        # The body is read before any refusal -- including the token one,
        # which is why this runs first. See the note below.
        # The body is read before any refusal, and that ordering is not
        # cosmetic. Answering a POST without draining what the client is
        # still sending resets the connection -- on Windows the client sees
        # `RemoteDisconnected` and never reads the refusal, so a 405 written
        # carefully in the CLI's words arrives as a transport error. Two
        # tests caught it and both were about refusals, which is where it
        # would always show up first.
        try:
            length = int(req.headers.get("Content-Length") or 0)
        except ValueError:
            req.close_connection = True
            return self.send(req, 400, {"error": "unreadable Content-Length"})
        if length > MAX_BODY:
            # Refusing without reading resets the connection, and the client
            # then sees a transport error instead of the refusal -- the same
            # defect as below, in the one place it is tempting to accept,
            # because reading the body is the thing being refused.
            #
            # So it is drained and discarded in chunks up to a hard ceiling.
            # Under the ceiling the client gets a clean 413 it can read; over
            # it, nothing is owed to a caller sending eight megabytes to a
            # loopback form, and the connection is closed.
            remaining = min(length, DRAIN_CEILING)
            while remaining > 0:
                chunk = req.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            if length > DRAIN_CEILING:
                req.close_connection = True
            return self.send(req, 413, {
                "error": f"a requirements document over {MAX_BODY} bytes is "
                         "not one this form wrote"})
        raw = req.rfile.read(length) if length else b""

        # Only now. The body is bounded above, so draining it costs a known
        # amount and buys a refusal the client can actually read.
        if not self._addressed(req):
            return

        split = urllib.parse.urlsplit(req.path)
        endpoint = WRITE_ENDPOINTS.get(split.path)
        if endpoint is None:
            if split.path in ENDPOINTS or split.path in STATIC:
                return self.send(req, 405, {
                    "error": f"{split.path} is read-only; it answers GET"},
                    extra=(("Allow", "GET"),))
            return self.send(req, 404, {"error": "not found"})
        if self.runs_dir is None:
            return self.send(req, 405, {
                "error": "this is a `oneground lab` session over one run, "
                         "which reads and never writes. The write half is "
                         "`oneground ui`, over a directory of runs."},
                extra=(("Allow", "GET"),))
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError) as e:
            return self.send(req, 400, {"error": f"unreadable body: {e}"})
        if not isinstance(body, dict):
            return self.send(req, 400, {"error": "expected a JSON object"})
        try:
            out = getattr(self, endpoint)(body)
        except compose.WriteRefused as e:
            return self.send(req, 400, self._refused(e))
        except (ValueError, KeyError) as e:
            return self.send(req, 400, {"error": str(e)})
        except Exception as e:                        # noqa: BLE001
            # The CLI's validator raised something that is not a refusal.
            # That is a defect in the validator rather than in the document,
            # and the honest answer says so: a refusal names a field and
            # tells the user what to change, and this cannot, because
            # nothing decided the document was wrong -- something fell over
            # reading it.
            #
            # It is answered rather than allowed to escape, because an
            # unanswered POST drops the connection and the user sees a
            # transport error for a defect in the tool. Task 046 found one
            # this way: a `corpus:` holding a list crashes `intake.load()`
            # with AttributeError instead of refusing.
            return self.send(req, 500, {
                "error": "the validator did not refuse this document, it "
                         "failed while reading it, which is a defect in the "
                         "tool rather than in the file",
                "raised": f"{type(e).__name__}: {e}"})
        return self.send(req, 200, out)

    def _addressed(self, req):
        """Whether this request is for this session. **Answers a bool.**

        It used to be `_refuse_unless_addressed`, returning `self.send(...)`,
        and callers wrote `if refusal is not None: return refusal`. `send`
        has no return statement, so it returns `None`, so that condition was
        never true -- **the 403 went out and the handler carried straight on
        and did the work.** An unauthenticated caller got a refusal and the
        action.

        It was introduced here in task 046 by extracting this helper out of
        `answer`, where the same line had been `return self.send(...)` and
        returned from the function that mattered. A refactor that removed a
        second implementation added a token bypass.

        A bool, and the callers say `if not self._addressed(req): return`,
        because the previous shape was only wrong in a way no type and no
        reviewer catches: `None is not None` reads exactly like a guard.
        """
        if (req.headers.get("Host") or "").lower() not in self._hosts:
            self.send(req, 403, {"error": "refused: unexpected Host"})
            return False
        params = urllib.parse.parse_qs(
            urllib.parse.urlsplit(req.path).query, keep_blank_values=True)
        offered = req.headers.get(TOKEN_HEADER) or \
            (params.get(TOKEN_PARAM) or [""])[0]
        if not hmac.compare_digest(offered.encode("utf-8"),
                                   self.token.encode("utf-8")):
            self.send(req, 403, {
                "error": "refused: this lab session's token is required"})
            return False
        return True

    @staticmethod
    def _refused(e):
        """A refusal, verbatim, never rephrased and never summarised.

        `refusal` is the CLI's own words where the document reached `load()`
        and was turned away. `lost` is the guard catching the form instead --
        the document parsed and came back different -- and it names the
        fields, because a guard that says only *they differ* hands back the
        obstacle rather than anything to do with it.
        """
        out = {"error": str(e), "refusal": e.refusal,
               "field": getattr(e, "field", None)}
        if e.lost:
            out["lost"] = [{"field": name, "written": a, "read_back": b}
                           for name, a, b in e.lost]
        return out

    # ------------------------------------------------- the three front doors
    # ------------------------------------------------------------- jobs
    def job_list(self, params):
        """Every job the supervisor has recorded. Read from the directory.

        A corrupt list is a refusal rather than an empty one, because
        `jobs.read` already decided that and the page would otherwise draw
        "no jobs" over a list that exists -- the same rounding the three
        outcomes exist to prevent.
        """
        del params
        if self.runs_dir is None:
            raise ValueError("a lab session over one run has no job list")
        try:
            found = jobsmod.read(self.runs_dir)
        except jobsmod.JobError as e:
            raise ValueError(str(e)) from None
        return {"jobs": [j.to_dict() for j in found],
                "stages": list(jobsmod.STAGES),
                "not_a_job": [{"stage": k, "why": v}
                              for k, v in jobsmod.NOT_A_JOB.items()]}

    #: What kind of thing each stage is run against. Read off the CLI's own
    #: parsers rather than restated: five stages take a requirements file and
    #: `propose` takes a workdir.
    STAGE_TARGET = {
        "characterize": "requirements", "simulate": "requirements",
        "verify": "requirements", "report": "requirements",
        "chunk": "requirements", "propose": "workdir",
    }

    def job_targets(self, params):
        """What a stage could be run against, in this directory, named.

        **The page asks; it never defaults.** A job's record says exactly
        what ran, so a target nobody chose would make that record accurate
        and meaningless -- which is the whole value of the record gone at the
        first click. The previous version sent `.` and produced a traceback
        from a directory nobody had named.

        A stage whose target this cannot name is **not offered**, and the
        reason is returned with it. The pod stages are that case today: their
        arguments are a session's, not this directory's, and offering a
        button that cannot be completed is the defect one step later.
        """
        del params
        if self.runs_dir is None:
            raise ValueError("a lab session over one run has no targets")

        requirements = []
        for name in sorted(os.listdir(self.runs_dir)):
            if not name.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(self.runs_dir, name)
            if os.path.isfile(path):
                requirements.append({"name": name, "arg": name})

        # A workdir is whatever the run index already calls one. Calling the
        # function the tool uses rather than re-deciding what a workdir is.
        workdirs = []
        index = self.index or runsmod.index_runs(self.runs_dir,
                                                 verify_manifests)
        for row in index.get("runs", []):
            workdirs.append({"name": row["name"], "arg": row["name"]})

        offered, withheld = {}, []
        for stage in jobsmod.STAGES:
            kind = self.STAGE_TARGET.get(stage)
            if kind is None:
                withheld.append({
                    "stage": stage,
                    # The reason, once. The clause about what this page
                    # does with an unnameable target is a rule about the
                    # page, not a fact about `pod watch`, and repeating it
                    # per stage is one fact stated four times (task 045).
                    "why": "their target is a pod session's rather than "
                           "this directory's, so this page cannot name one"})
                continue
            choices = requirements if kind == "requirements" else workdirs
            if not choices:
                withheld.append({
                    "stage": stage,
                    "why": "no %s in this directory to run it against"
                           % ("requirements file" if kind == "requirements"
                              else "run")})
                continue
            offered[stage] = {"kind": kind, "choices": choices}
        return {"offered": offered, "withheld": withheld,
                "kinds": {"requirements": "a requirements file in this "
                                          "directory",
                          "workdir": "a run in this directory"}}

    def job_log(self, params):
        """One job's log: the CLI's own output, unchanged.

        The path comes from the job record rather than from the request, so
        no part of a request ever reaches a filesystem path -- the rule this
        server has held since it was written.
        """
        if self.runs_dir is None:
            raise ValueError("a lab session over one run has no job list")
        wanted = (params.get("id") or [""])[0]
        for job in jobsmod.read(self.runs_dir):
            if job.id != wanted:
                continue
            if not job.log:
                return {"id": job.id, "text": None,
                        "absent": "this job has no log"}
            path = os.path.join(self.runs_dir, job.log)
            if not os.path.isfile(path):
                return {"id": job.id, "text": None, "offset": 0,
                        "live": job.state in ("queued", "running"),
                        "absent": "the log has not been written yet"}
            # Streamed by offset rather than re-read whole. A `simulate`
            # writes for minutes, and re-sending the file every two seconds
            # would make a long run cost more to watch than to do -- and
            # would flicker, because the page would replace text a reader
            # was in the middle of.
            #
            # Bytes, not characters: the offset has to survive a multi-byte
            # character split across two reads, and a character offset does
            # not. `errors="replace"` then makes a half-character visible
            # rather than an exception.
            try:
                since = max(0, int((params.get("since") or ["0"])[0]))
            except ValueError:
                since = 0
            size = os.path.getsize(path)
            if since > size:
                # The log was replaced -- a job restarted, or a stale offset
                # from a previous one. Saying so beats returning nothing,
                # which the page would draw as "no output".
                return {"id": job.id, "text": None, "offset": 0,
                        "live": job.state in ("queued", "running"),
                        "absent": "this log is shorter than it was; it has "
                                  "been replaced since you last read it"}
            with open(path, "rb") as f:
                f.seek(since)
                chunk = f.read()
            return {"id": job.id,
                    "text": chunk.decode("utf-8", errors="replace"),
                    "offset": since + len(chunk),
                    # Whether there is more coming, from the record rather
                    # than guessed from the bytes: a log that stops growing
                    # has either finished or stalled, and only the state
                    # knows which.
                    "live": job.state in ("queued", "running"),
                    "absent": None}
        raise ValueError(f"no job {wanted!r} in this directory")

    def supervisor_address(self, params):
        """Where the supervisor is, so the page can speak to it directly.

        The server does not forward. Its own header has promised since it was
        written that it makes no request of its own, and that is the last
        promise on that list still standing -- so the page gets the address
        and does the asking.

        `running: false` is a real answer the page shows as *no supervisor is
        running, so nothing can be started from here*. Inventing one would
        put a button on the page that fails when pressed, which reads as a
        defect in the tool rather than as a process nobody started.
        """
        del params
        if self.runs_dir is None:
            return {"running": False,
                    "why": "a lab session over one run runs nothing"}
        found = supmod.address(self.runs_dir)
        if not found:
            return {"running": False,
                    "why": "no supervisor has announced itself in this "
                           "directory, so nothing can be started from here"}
        same = found.get("build") == provenance.PACKAGE_DIR
        return {"running": True, "url": found["url"],
                "token": found["token"], "build": found.get("build"),
                # A server and a supervisor on different checkouts would each
                # be correct about themselves and wrong together.
                "same_build": same,
                "why": None if same else
                       "the supervisor is running a different build from "
                       "this server: %s against %s"
                       % (found.get("build"), provenance.PACKAGE_DIR)}

    def compose_fields(self, params):
        """The declaration the form renders itself from.

        The form does not carry its own labels. It asks for the table and
        draws what it is given, which is what makes "the explanation in the
        file is the string the form showed" a property of one declaration
        rather than an agreement between two.
        """
        del params
        return {"fields": [{
            "name": p.name,
            "type": getattr(p.type, "__name__", str(p.type)),
            "note": p.note,
            "choices": list(p.choices) if p.choices else None,
            "minimum": p.minimum,
            "maximum": p.maximum,
            # From `REQUIRED`, never from `default`: see that table's note.
            "required": p.name in fields.REQUIRED,
            "required_when": list(fields.REQUIRED[p.name])
                             if fields.REQUIRED.get(p.name) else None,
            # What is written when the box is left alone, so the empty
            # option can say so instead of being blank. `NO_DEFAULT` means
            # the key is simply absent, which is a different statement.
            "default": (None if p.default is fields.NO_DEFAULT
                        else p.default),
            "belongs_to": ([p.belongs_to[0], p.belongs_to[1]]
                           if p.belongs_to else None),
        } for p in fields.FIELDS],
            "outside_the_table": [
                {"rule": name, "kind": kind, "why": why}
                for name, kind, why in fields.OUTSIDE_THE_TABLE]}

    def compose_template(self, params):
        """Door three: a file to keep, not a blank form.

        Built through `document()` like the other two, from whatever the
        request carries, so a template is a document and not a special case.
        """
        del params
        return {"text": compose.render(compose.document({}))}

    def compose_open(self, body):
        """Door two: a file that arrived, turned into form state.

        Validated on arrival, and an error is named against the field it
        belongs to rather than reported as a parse position. The document is
        **not** edited in place: what comes back is state, and state goes
        through `document()` like anything typed.
        """
        text = body.get("text")
        if not isinstance(text, str):
            raise ValueError("expected `text`, the file that was uploaded")
        return compose.open_text(text)

    def compose_preview(self, body):
        """Door one, before saving: the file as it stands, shown live.

        Changes nothing. It is a POST because it carries the form state, not
        because it writes.
        """
        state = body.get("state")
        if not isinstance(state, dict):
            raise ValueError("expected `state`, the form's fields")
        doc = compose.document(state)
        return {"text": compose.render(doc), "document": doc}

    def compose_write(self, body):
        """Saving. Through the guard, like every other write."""
        state = body.get("state")
        name = body.get("path")
        if not isinstance(state, dict):
            raise ValueError("expected `state`, the form's fields")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("expected `path`, where to write the file")
        target = self._inside_runs_dir(name)
        written = compose.write(compose.document(state), target)
        return {"path": os.path.relpath(written, self.runs_dir)
                .replace("\\", "/")}

    def _inside_runs_dir(self, name):
        """Where a write may land: under the directory this session serves.

        The session was pointed at a directory and everything it writes stays
        in it. A path that climbs out is refused by comparing the resolved
        path to the resolved root, rather than by inspecting the string for
        `..` -- a string check is a second implementation of what the
        filesystem already answers, and it is the one that gets a symlink
        wrong.
        """
        target = os.path.abspath(os.path.join(self.runs_dir, name))
        root = os.path.abspath(self.runs_dir)
        if os.path.commonpath([root, target]) != root:
            raise ValueError(
                f"{name} is outside the directory this session serves")
        if os.path.isdir(target):
            raise ValueError(f"{name} is a directory")
        return target

    @staticmethod
    def _epsilon(params):
        raw = (params.get("epsilon") or [""])[0]
        if raw == "":
            return None
        value = float(raw)
        if not math.isfinite(value) or not 0.0 <= value <= EPSILON_CEILING:
            raise ValueError(f"epsilon {raw} is not in [0, {EPSILON_CEILING}]")
        return value

    def check(self, params):
        """What this session is, in both modes.

        `mode` is "run" for `oneground lab` and "runs" for `oneground ui`.
        The page reads it to decide what it is looking at; without it the
        page would have to infer the mode from a missing field, which is the
        kind of inference that renders an empty table as a result.
        """
        common = {
            "mode": "runs" if self.index is not None else "run",
            # These two were flat strings saying this server writes nothing
            # and runs nothing. The first became false for a `ui` session the
            # hour the form landed, and it is the FOURTH place that one claim
            # lived: the page's eyebrow, the CLI's startup line, this field,
            # and the module docstring below. Three were corrected one at a
            # time, each by someone looking at that one.
            #
            # So this is not the staleness defect, it is the two-homes
            # defect -- `docs/PRACTICE.md` section 4. A claim with four
            # copies has no owner, and correcting a sentence is not
            # correcting a claim.
            #
            # They now answer per mode, which is the repair that makes the
            # next change impossible to miss: a `lab` session still writes
            # nothing and the sentence says so, and a `ui` session says what
            # it writes. When jobs land, `runs` is the field that has to
            # change, and it is the field a reader asks.
            "writes": ("requirements files, through one guarded path"
                       if self.index is not None
                       else "nothing: this session has no write path"),
            "runs": ("nothing: no job, no session is created from this "
                     "page" if self.index is not None else
                     "nothing: no job, no written file, no session is "
                     "created from this page"),
            "token": ("required on every request; see docs/UI.md for what "
                      "it protects against and what it does not"),
            # Which build answered this request. The page shows it and a
            # reader can check it, because the incident that produced this
            # field was two checkouts with the same version and the same
            # commit where only the path differed.
            "build": self.build,
        }
        package = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if self.index is not None:
            # Shortened, like every other path this page receives: the header
            # renders it, and a header is in every screenshot.
            return {**common,
                    "package": runsmod.shown_dir(package),
                    "demo": self.index.get("demo"),
                    "runs_dir": runsmod.shown_dir(self.runs_dir),
                    "n_runs": len(self.index["runs"]),
                    "unverified": [r["name"] for r in self.index["runs"]
                                   if r["manifest"]["all_verified"]
                                   is not True]}
        return {**common,
                "package": package,
                "workdir": self.run.workdir,
                "also": self.run.also,
                "files": self.run.present,
                "digests": self.digests,
                "render": self.render.as_dict()}

    def describe_run(self, params):
        return {**self.run.describe(), "render": self.render.as_dict()}

    def ground(self, params):
        eps = self.run.epsilon_set(self._epsilon(params))
        return contract.draw(GroundView(eps, k=K_TRUE, render=self.render),
                             *self.run.base).as_dict()

    def trace(self, params):
        query_index = int((params.get("query") or ["0"])[0])
        epsilon = self._epsilon(params)
        eps = self.run.epsilon_set(epsilon)
        return contract.draw(QueryTraceView(query_index, K_TRUE, eps=eps,
                                            ambiguity=self.run.ambiguity),
                             *self.run.trace_state(epsilon)).as_dict()

    def query_index(self, params):
        epsilon = self._epsilon(params)
        eps = self.run.epsilon_set(epsilon)
        return contract.draw(QueryIndexView(K_TRUE, eps=eps,
                                            ambiguity=self.run.ambiguity),
                             *self.run.trace_state(epsilon)).as_dict()

    def ids(self, params):
        raw = (params.get("rows") or [""])[0]
        rows = [v for v in raw.split(",") if v != ""]
        if not rows:
            raise ValueError("name base rows as ?rows=1,2,3")
        return self.run.ids_of(rows)

    # ------------------------------------------------------------ responses
    def send(self, req, status, obj, extra=()):
        try:
            body = json.dumps(obj, allow_nan=False,
                              separators=(",", ":")).encode("utf-8")
        except ValueError as e:
            status = 500
            body = json.dumps({"error": f"not serialisable: {e}"}).encode()
        self.send_bytes(req, status, body, "application/json", extra)

    @staticmethod
    def send_bytes(req, status, body, content_type, extra=()):
        req.send_response(status)
        for name, value in SECURITY_HEADERS + tuple(extra):
            req.send_header(name, value)
        req.send_header("Content-Type", content_type)
        req.send_header("Content-Length", str(len(body)))
        req.end_headers()
        req.wfile.write(body)

    # ------------------------------------------------------------ lifecycle
    def start(self):
        self._thread = threading.Thread(target=self.httpd.serve_forever,
                                        name="oneground-lab", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def run_list(self, params):
        """Every run under the runs directory, drawn.

        Refused, rather than emptied, when this session serves one run: an
        empty list would say the directory holds nothing, and a lab session
        has no directory to hold anything.
        """
        if self.index is None:
            raise ValueError("this session serves one run, not a directory; "
                             "start `oneground ui <runs-dir>` for a list")
        return draw_receipt(RunListView(), self.index).as_dict()

    def _named_run(self, params):
        """The workdir one request is about, refused if it is not listed.

        Refused by NAME against the index rather than by joining a path: a
        parameter that reached the filesystem would be a way to read a
        directory this session was never pointed at.
        """
        if self.index is None:
            raise ValueError("this session serves one run, not a directory")
        want = (params.get("run") or [""])[0]
        if not want:
            raise ValueError("name a run: ?run=<name>")
        for row in self.index["runs"]:
            if row["name"] == want:
                return row
        raise ValueError(f"no run named {want!r} under "
                         f"{self.index['directory_shown']}")

    def _report_of(self, row):
        path = os.path.join(row["path"], "report.json")
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def headline(self, params):
        """What one run concluded -- or, with no report, how far it got."""
        row = self._named_run(params)
        report = self._report_of(row)
        if report is None:
            return draw_receipt(RunProgressView(run=row["name"]),
                                self.index).as_dict()
        return draw_receipt(RunHeadlineView(), report).as_dict()

    def evidence(self, params):
        """Every claim of one run's report, with what each one cites."""
        row = self._named_run(params)
        report = self._report_of(row)
        if report is None:
            raise ValueError(f"{row['name']} has not reported, so it has no "
                             "claims to show evidence for")
        doc = citationsmod.resolve_citations(row["path"], report)
        return draw_receipt(EvidenceDrawerView(), doc).as_dict()

    def compare(self, params):
        """Two runs, and whether they may be read against each other.

        Both named by `?run=` twice, resolved against the index by name. The
        verdict is `oneground.comparability`, which docs/LIBRARY.md 2.2
        specifies; this endpoint draws it and does not re-derive it.
        """
        if self.index is None:
            raise ValueError("this session serves one run, not a directory")
        want = params.get("run") or []
        if len(want) != 2:
            raise ValueError("name two runs: ?run=<a>&run=<b>")
        rows = []
        for name in want:
            match = [r for r in self.index["runs"] if r["name"] == name]
            if not match:
                raise ValueError(f"no run named {name!r} under "
                                 f"{self.index['directory_shown']}")
            rows.append(match[0])
        doc = runsmod.comparison_document(rows[0]["path"], rows[1]["path"])
        return draw_receipt(ComparisonView(), doc).as_dict()

    def ui_startup_line(self, seconds, shown_dir):
        """The one line `oneground ui` prints.

        It names how many runs were found and how many of them failed their
        digests, because a reader who is told "4 runs" and not told that one
        of them does not verify has been told the less useful half.
        """
        rows = self.index["runs"]
        bad = [r["name"] for r in rows if r["manifest"]["all_verified"]
               is not True]
        note = f", {len(bad)} unverified ({', '.join(bad)})" if bad else ""
        # It said "(read-only; nothing runs from this page)" until this
        # slice gave the page a write half, and the page's own eyebrow was
        # corrected in the same commit while this line was not -- the claim
        # lived in two places and only one was in front of me. Corrected the
        # same way and for the same reason: say what is true and stop, since
        # "nothing runs" is step 3 of this brief and a sentence that has to
        # be edited again shortly is stale before it is written
        # (`docs/PRACTICE.md` 1.2).
        return (f"oneground ui: {len(rows)} run(s) under {shown_dir}{note} -- "
                f"{self.url}  (served from this machine; "
                f"reads runs, writes requirements files)\n"
                f"  build: {self.build_line()} "
                f"[{seconds:.1f}s]")

    def build_line(self):
        """Which build this is, in one line, for the terminal.

        The package directory leads, because that is the field that would
        have answered the question the incident asked: the version and the
        commit were identical between the two checkouts involved and only
        the path differed.
        """
        b = self.build
        commit = (b.get("commit") or "no commit")[:12]
        dirty = "" if b.get("dirty") is None else (
            " dirty" if b["dirty"] else " clean")
        return f"{b['package']} @ {commit}{dirty} ({b['source']})"

    def startup_line(self, seconds, shown_workdir):
        """The one line `oneground lab` prints: the URL, the render mode and
        why, the configuration, and how long startup took."""
        r = self.render
        if r.p95_ms is None:
            why = r.mode
        else:
            # The same words the page and the ground's caption show:
            # `RenderMode.evidence` writes them once. This line used to
            # compose its own, which is how a log and a screenshot of one
            # measurement come to read differently.
            why = f"{r.mode}: {r.evidence()}"
            if r.chosen_by == "--mode":
                why += f" (chosen by --mode; measured: {r.measured})"
        return (f"oneground lab: {self.url}  |  {why}  |  "
                f"{self.run.head['config_label']} in {shown_workdir}  |  "
                f"ready in {seconds:.1f} s")
