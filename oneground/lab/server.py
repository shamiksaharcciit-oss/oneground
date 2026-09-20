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
- write a file, anywhere: there is no write path, and no method but GET
- send a file from the run directory: states are drawn, never served raw, and
  the only files served are the interface's own, from a fixed table -- no part
  of a request path is ever joined to a directory
- run a simulation: the recall panel's action is a command for the user
- answer a request without this session's token, or for a Host it did not bind
- send a CORS header, list a directory, log a request line (it carries the
  token), or make a request of its own

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

from . import contract, guard
from . import runs as runsmod
from .receipt import draw_receipt
from .runs import LabRunError, LoadedRun                      # noqa: F401
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
}
ENDPOINTS = {
    "/api/check": "check",
    "/api/runs": "run_list",
    "/api/run": "describe_run",
    "/api/ground": "ground",
    "/api/trace": "trace",
    "/api/query-index": "query_index",
    "/api/ids": "ids",
}
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

    def _no_write_path(self):
        self.server.lab.send(self, 405, {
            "error": "the lab has no write path; only GET is answered"},
            extra=(("Allow", "GET"),))

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _no_write_path


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
                 i_know=False, draws=MODE_DRAWS, token=None, runs_dir=None):
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
        if (run is None) == (runs_dir is None):
            raise LabRefused("a lab session serves one run or one runs "
                             "directory, not both and not neither")
        self.warning = check_host(host, i_know)
        broken = {**guard.check_views(), **guard.check_transport(),
                  **guard.check_contract()}
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
        split = urllib.parse.urlsplit(req.path)
        if (req.headers.get("Host") or "").lower() not in self._hosts:
            return self.send(req, 403, {"error": "refused: unexpected Host"})
        params = urllib.parse.parse_qs(split.query, keep_blank_values=True)
        offered = req.headers.get(TOKEN_HEADER) or \
            (params.get(TOKEN_PARAM) or [""])[0]
        if not hmac.compare_digest(offered.encode("utf-8"),
                                   self.token.encode("utf-8")):
            return self.send(req, 403, {
                "error": "refused: this lab session's token is required"})
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
        return {
            "workdir": self.run.workdir,
            "also": self.run.also,
            "files": self.run.present,
            "digests": self.digests,
            "render": self.render.as_dict(),
            "writes": "nothing: the lab has no write path",
            "token": ("required on every request; see docs/LAB.md for what "
                      "it protects against and what it does not"),
            "package": os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))),
        }

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
        return (f"oneground ui: {len(rows)} run(s) under {shown_dir}{note} -- "
                f"{self.url}  (read-only; nothing runs from this page) "
                f"[{seconds:.1f}s]")

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
