"""`oneground verify <requirements.yaml>` -- measure a real engine.

Simulation predicts. This measures. On the same sample `characterize` drew and
against the same exact ground truth `simulate` scored against, it ingests into
a real engine and asks it real queries, so the two numbers can be compared and
the difference recorded.

What this command measures
--------------------------
    ingest_vectors_per_second      wall clock, durable writes (wait=True)
    recall_at_10 / recall_at_100   against the workdir's exact ground truth
    latency_shape_single_client    p50/p95/p99 of per-query wall clock,
                                   **sequential, one client**
    rtt_baseline_ms                50 pings against an empty collection first
    calibration_error_recall       simulated recall - measured recall

What it deliberately does not measure
-------------------------------------
**Throughput.** Not at all, not approximately, not "roughly". Latency measured
one query at a time by one client says what a request costs when nothing is
contending; it says nothing about what a server sustains under load, and the
two get conflated constantly. The field is called
`latency_shape_single_client` so that a reader who wants throughput has to go
and get it properly -- task 011, on a pod, with concurrency.

And no verdicts. Whether 12 ms p95 meets someone's budget is the report's job.

The RTT baseline
----------------
50 pings against an empty collection, before the run. If the baseline's p95 is
more than 20% of the query p95, the query latency is dominated by the path to
the engine rather than by the engine, and latency is reported as
`couldnt_check: environment noise` -- while recall, which noise cannot move, is
still reported. Measuring latency to a container through a Windows Docker NAT
and calling it "Qdrant's latency" is exactly the error this guards.
"""

import json
import os
import platform
import subprocess
import sys
import time

import numpy as np

from .. import intake
from ..adapters import (AdapterError, engines as registered_engines,
                        get as get_engine, managed_namespace, namespace_for)
from ..receipts import (library_versions, producing_version, round_floats,
                        sha256_file,
                        write_json_stable, write_manifest)
from ..provenance import invocation
from ..sample import loaders
from . import load as loadgen
from . import runpod as runpod_target

COULDNT_CHECK = "couldnt_check"

VERIFY_FILES = ["verify.json", "verify_info.json"]
CHARACTERIZE_FILES = ["characterization.json", "sample_ids.json",
                      "queries_ids.json", "build_info.json"]
SIMULATE_FILES = ["simulate.json", "simulate_info.json"]

COMPOSE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "compose", "qdrant.yml")
LOCAL_ENDPOINT = "http://localhost:6333"

# One compose file and one default endpoint per engine. Adding an engine is
# two lines here and an adapter; nothing else in this module names an engine.
_COMPOSE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "compose")
COMPOSE_FILES = {
    "qdrant": os.path.join(_COMPOSE_DIR, "qdrant.yml"),
    "pgvector": os.path.join(_COMPOSE_DIR, "pgvector.yml"),
}
CONTAINERS = {
    "qdrant": "oneground-verify-qdrant",
    "pgvector": "oneground-verify-pgvector",
}
DEFAULT_ENDPOINTS = {
    "qdrant": LOCAL_ENDPOINT,
    "pgvector": "postgresql://oneground:oneground@localhost:55432/oneground",
}


def compose_file_for(engine):
    try:
        return COMPOSE_FILES[str(engine)]
    except KeyError:
        raise VerifyError(
            f"no compose file for engine {engine!r}; this build has "
            f"{', '.join(sorted(COMPOSE_FILES))}") from None


def endpoint_for(cfg, engine, override=None):
    """Where this engine listens.

    `verify.endpoints` maps engine -> endpoint for a multi-engine run;
    `verify.endpoint` remains the single-engine form. A default per engine
    exists so a two-engine local run needs no endpoint block at all.
    """
    if override:
        return str(override)
    per = (cfg.get("endpoints") or {})
    if engine in per:
        return str(per[engine])
    if cfg.get("endpoint") and len(
            list(cfg.get("engines") or [cfg.get("engine", "qdrant")])) == 1:
        return str(cfg["endpoint"])
    return DEFAULT_ENDPOINTS.get(str(engine), "")

# The pod image for a matched-environment run. A CPU-capable image with
# python3.12 and curl is all this needs: the engine runs from its own release
# binary rather than from a container, because RunPod cannot grant the
# privileges docker-in-docker requires (measured, task 011). Resolved live
# from Docker Hub and pinned; see the report.
POD_IMAGE = "runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404"

# The baseline share above which latency is not attributable to the engine.
NOISE_FRACTION = 0.20
RTT_PINGS = 50


# Where a recorded index-family resolution is looked for, in order. The first
# that exists wins: a resolution run against a live engine beats the
# declaration an adapter shipped, which is `not_resolved` on purpose.
COVERAGE_FILES = (os.path.join("adapters", "index-coverage.json"),)


class VerifyError(RuntimeError):
    """The run cannot proceed. The message says what to do about it."""


class ProbeUnavailable(VerifyError):
    """The readiness probe could not be PERFORMED. Task 017c follow-up.

    Distinct from "the engine did not answer", and the distinction carries its
    weight: an engine that has not finished starting may answer a second
    later, so that failure is worth retrying. A driver that is not installed
    in this interpreter will not install itself, so retrying it spends the
    whole restart timeout to arrive at the same place with a vaguer message.

    A `VerifyError` subclass because the outcome is the same either way -- the
    run stops, and an unprobeable engine is never reported as reachable. What
    differs is how fast, and what it says while doing it.
    """


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# the local target
# --------------------------------------------------------------------------

def compose_image(engine="qdrant"):
    """The pinned tag from an engine's compose file, for the receipt."""
    try:
        with open(compose_file_for(engine), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("image:"):
                    return line.split("image:", 1)[1].strip()
    except (OSError, VerifyError):
        pass
    return None


def _probe_qdrant(endpoint, timeout):
    """GET a readiness endpoint; it must answer 200. Task 017c.

    `connect()` is not a probe: the Qdrant client is lazy and constructing it
    touches no socket, so the old reconnect loop returned "reachable" the
    instant the object existed -- which it would also have done against a
    server that was still replaying its WAL, or gone.

    `/readyz` is the right question and is not in every version, so a
    `/collections` call is the fallback: it is the cheapest request that cannot
    be answered without the server being up and serving.
    """
    import urllib.error
    import urllib.request

    base = str(endpoint).rstrip("/")
    last = None
    for path in ("/readyz", "/collections"):
        url = base + path
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                code = r.getcode()
                r.read(256)
            if code == 200:
                return f"GET {path} -> 200"
            last = f"GET {path} -> {code}"
        except urllib.error.HTTPError as e:
            last = f"GET {path} -> {e.code}"
        except Exception as e:                        # socket/DNS/timeout
            last = f"GET {path} -> {type(e).__name__}: {e}"
    raise VerifyError(last or "no probe attempted")


def _probe_pgvector(endpoint, timeout):
    """Open a connection and execute `SELECT 1`. Task 017c.

    A NEW connection on purpose, not the adapter's: the point is to prove the
    server accepts a connection and executes a statement right now. A pooled
    or already-open handle can look healthy against a server that has
    restarted underneath it.

    `pg_isready` is deliberately not what this uses. It reports that the
    postmaster is accepting connections, which is true some seconds before the
    database will actually run a query -- and "accepting connections" was
    exactly the state the failed sessions needed to distinguish from "serving".
    """
    # A missing driver is not a readiness verdict, and it must not escape as
    # `ModuleNotFoundError: No module named 'psycopg'` -- which says nothing
    # about the engine, names neither the engine nor the interpreter, and is
    # the same shape of under-informative failure this whole probe exists to
    # remove. The engine may be perfectly healthy; THIS PROCESS cannot ask it.
    #
    # `sys.executable` is in the message because that is the actual variable:
    # requirements.txt pins psycopg and psycopg-binary, so a driver missing
    # here means the command is running outside the pinned environment, and
    # the interpreter path is what tells the reader which one they are on.
    # This is the same failure task 013 traced to bare `python` on this
    # machine being the system interpreter.
    try:
        import psycopg
    except ImportError as e:
        raise ProbeUnavailable(
            "pgvector: cannot probe readiness -- the psycopg driver is not "
            f"installed in this interpreter ({sys.executable}). "
            "requirements.txt pins psycopg==3.3.5 and psycopg-binary, so this "
            "process is running outside the pinned environment; use the venv "
            "interpreter, or `pip install -r requirements.txt`. This is not a "
            "statement about the engine: it may be serving, and this process "
            "has no way to find out, so the run stops rather than measuring "
            "an engine it never checked."
        ) from e

    # Wrapped, so every probe fails the same way whoever calls it. Letting
    # psycopg.ConnectionTimeout out would make the probe contract "raises
    # something", and a caller deciding whether to keep measuring needs one
    # answer, not a union of every driver's exception hierarchy.
    try:
        with psycopg.connect(str(endpoint),
                             connect_timeout=max(1, int(timeout))) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row = cur.fetchone()
    except VerifyError:
        raise
    except Exception as e:                            # driver-specific
        raise VerifyError(
            f"SELECT 1 could not be executed: {type(e).__name__}: {e}") from e
    if not row or row[0] != 1:
        raise VerifyError(f"SELECT 1 returned {row!r}")
    return "SELECT 1 -> 1"


# Keyed by engine, like COMPOSE_FILES, CONTAINERS and DEFAULT_ENDPOINTS above.
PROBES = {
    "qdrant": _probe_qdrant,
    "pgvector": _probe_pgvector,
}


def probe_ready(engine_name, endpoint, timeout=10.0):
    """What the engine answered, or raise. Task 017c.

    Returns the request that succeeded, so the log line says what was actually
    checked instead of asserting reachability on no evidence.

    An engine with no registered probe returns a couldnt_check sentence rather
    than a success: nothing was asked, and saying "reachable" would be the
    overstatement this function exists to remove.
    """
    probe = PROBES.get(str(engine_name))
    if probe is None:
        return (f"couldnt_check: no readiness probe for {engine_name}; "
                "nothing was asked of it")
    return probe(endpoint, timeout)


# How long the restart COMMAND may take to RUN, as distinct from how long the
# engine may take to answer afterwards. Task 018c.
#
# These are two different quantities and sharing one number for them was a
# defect. "Wait up to three minutes for pgvector to come back" is a statement
# about an engine reloading a corpus; "allow sixty seconds for `pg_ctl
# restart` to return" is a statement about starting a process. A caller who
# shortens the first never meant to shorten the second, and when the two were
# one parameter a two-second readiness budget also gave the shell two seconds
# to start -- so on a loaded machine the command timed out, `restart_engine`
# returned "not restarted" instead of reaching the readiness loop, and the
# test asserting the readiness path failed for a reason that had nothing to do
# with readiness.
#
# The floor is applied as a MAXIMUM against the readiness budget, never a
# replacement: `max(60, timeout)`. Every existing caller uses the 180 s
# default and therefore gets exactly what it got before. Only a caller with a
# readiness budget under a minute is affected, and what it gains is budget for
# a different thing.
RESTART_COMMAND_TIMEOUT = 60.0


def restart_command_timeout(ready_timeout, command_timeout=None):
    """The spawn budget for a given readiness budget. Never smaller than now.

    Split out so the rule is one expression with one test, rather than an
    inline `max()` a reader has to find before they can believe the docstring.
    """
    if command_timeout is not None:
        return float(command_timeout)
    return max(RESTART_COMMAND_TIMEOUT, float(ready_timeout))


def restart_engine(engine, cfg, engine_name, endpoint, log_fn=log,
                   timeout=180.0, command_timeout=None):
    """Restart the engine between load runs. Returns what actually happened.

    `timeout` is the READINESS budget: how long the engine may take to answer
    a probe after the restart command has returned. The command's own budget
    is separate -- see `restart_command_timeout` -- because a slow process
    spawn is not the engine being slow to come back, and charging one to the
    other made a small readiness budget unusable.

    Task 017 item 2. Repeating a load run is only worth doing if the runs are
    comparable samples, and run 2 against a process that has been serving run
    1 for five minutes is not the same measurement: the page cache is warm,
    the allocator has settled, and any graph the engine builds lazily is
    built. Restarting is what makes run 2 a second sample rather than a
    continuation of the first.

    The return value is a sentence, never a bool, and it says "not restarted"
    when nothing was done. A spread measured across runs that silently shared
    a warm process is a different quantity from the one the report will call
    it, and the run record has to carry which of the two it is.
    """
    import subprocess

    # Three sources, most specific first. The environment variable is how a
    # SESSION sets this (task 017b): on a pod the engines are native processes
    # rather than containers, so there is nothing for `docker restart` to act
    # on, and the session spec is where the pod-side command belongs.
    #
    # `{engine}` is substituted, because one session measures both engines in
    # turn and they are not restarted the same way -- pkill and setsid for
    # qdrant, pg_ctl for postgres. A single command that ignored which engine
    # it was restarting would restart the wrong one, or neither, and report
    # success either way.
    cmd = (cfg.get("engine_restart_command")
           or os.environ.get("ONEGROUND_ENGINE_RESTART_COMMAND") or "")
    if cmd:
        cmd = cmd.replace("{engine}", str(engine_name))
    container = cfg.get("engine_container") or CONTAINERS.get(engine_name)
    if cmd:
        how = f"`{cmd}`"
        argv, shell = cmd, True
    elif container:
        how = f"docker restart {container}"
        argv, shell = ["docker", "restart", container], False
    else:
        return ("not restarted: no engine_restart_command and no known "
                "container for this engine, so this run continues against the "
                "process the previous run warmed")
    spawn_budget = restart_command_timeout(timeout, command_timeout)
    try:
        r = subprocess.run(argv, shell=shell, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=spawn_budget)
    except (OSError, subprocess.SubprocessError) as e:
        # Naming the budget matters: "could not be run" against a 2 s limit
        # reads as a broken command, and against a 60 s limit as a genuinely
        # stuck one. They call for different next steps.
        # `:g`, not `:.0f`: a 0.5 s budget printed as "0 s" reads as a bug in
        # the message rather than a deliberately tight limit.
        return (f"not restarted: {how} could not be run within its "
                f"{spawn_budget:g} s command budget ({e})")
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()
        return (f"not restarted: {how} exited {r.returncode}"
                + (f" -- {tail[-1][:200]}" if tail else ""))

    # Up is not the same as ready, and the whole point of the restart is lost
    # Up is not the same as ready, and "connected" is not the same as either.
    #
    # This loop used to call `engine.connect()` and report "reachable again
    # after 0.1 s" the moment it returned. For Qdrant that is a lie by
    # construction: the client is lazy, so constructing it touches no socket
    # and succeeds against a server that is gone. The only thing standing
    # between a restart and a measurement run against a dead engine was
    # restart_engine.sh's own curl poll -- one check, in a shell script, which
    # is not where a measurement should put its whole trust.
    #
    # So: reconnect the adapter (the run needs a live client either way), and
    # then PROBE with a request that cannot be answered without a serving
    # engine. The word "reachable" is printed only when a probe succeeded, and
    # it names what the probe sent.
    started = time.time()
    deadline = started + timeout
    last = None
    while time.time() < deadline:
        try:
            engine.connect(endpoint, cfg.get("credentials_env"))
            # The probe gets a slice of the caller's budget, not a
            # fixed 10 s: a 2 s restart timeout must not spend 20 s
            # inside one probe attempt.
            answered = probe_ready(engine_name, endpoint,
                                   timeout=max(1.0, min(10.0, timeout / 4.0)))
            waited = time.time() - started
            if str(answered).startswith(COULDNT_CHECK):
                # No probe exists for this engine. Do not claim reachability.
                return (f"restarted via {how}; client reconnected after "
                        f"{waited:.1f} s, but {answered}")
            return (f"restarted via {how}; reachable again after {waited:.1f} s "
                    f"({answered})")
        except ProbeUnavailable:
            # Not retryable and not survivable: the probe cannot be performed
            # at all, so every remaining second of the timeout would produce
            # the same answer, and the message it ends on would be the vague
            # one about the engine rather than the exact one about the driver.
            raise
        except Exception as e:                        # adapter- or probe-level
            last = e
            time.sleep(1.0)

    # Never fall through into a measurement. A load run against an engine that
    # did not come back produces numbers, and they would be numbers about
    # nothing -- with `load_restarts` carrying a sentence nobody reads until
    # after the report has been believed.
    waited = time.time() - started
    raise VerifyError(
        f"{engine_name}: restarted via {how}, but it did not answer a "
        f"readiness probe within {waited:.1f} s"
        + (f" (last: {type(last).__name__}: {last})" if last else "")
        + ". Refusing to measure an engine that is not serving: a load run "
        "against a dead engine still produces a p95.")


def p95_spread(per_run):
    """`{min, median, max, spread, n_runs, p95_ms_per_run}` for a p95 list.

    The spread is what task 015 could not report: the same configuration
    measured 38.22 ms on one pod and 42.82 ms on another, 12% apart, with a
    40 ms constraint between them. One run cannot tell you which side of a
    threshold a configuration sits on when the threshold is inside the
    run-to-run variation, and a single number hides that it is a sample of
    one.
    """
    vals = sorted(float(v) for v in per_run if v is not None)
    if not vals:
        return None
    n = len(vals)
    median = (vals[n // 2] if n % 2
              else (vals[n // 2 - 1] + vals[n // 2]) / 2.0)
    return {"min": vals[0], "median": median, "max": vals[-1],
            "spread": vals[-1] - vals[0], "n_runs": n,
            "p95_ms_per_run": [float(v) for v in per_run]}


def compose_up(log_fn=log, timeout=120, engine="qdrant"):
    path = compose_file_for(engine)
    log_fn(f"docker compose up {engine} ({compose_image(engine)})")
    subprocess.run(["docker", "compose", "-f", path, "up", "-d"],
                   check=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    deadline = time.time() + timeout
    while time.time() < deadline:
        p = subprocess.run(["docker", "inspect", "--format",
                            "{{.State.Health.Status}}",
                            CONTAINERS.get(engine, "")],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if "healthy" in (p.stdout or ""):
            log_fn(f"  {engine} container healthy")
            return True
        time.sleep(2)
    raise VerifyError(f"the {engine} container did not become healthy in "
                      f"{timeout}s")


def compose_down(log_fn=log, engine="qdrant"):
    log_fn(f"docker compose down -v {engine}")
    subprocess.run(["docker", "compose", "-f", compose_file_for(engine),
                    "down", "-v"],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace")


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------

def recall_at(pred_ids, gt_ids, k):
    gt, pred = gt_ids[:, :k], pred_ids[:, :k]
    hits = sum(len(set(p[p >= 0].tolist()) & set(g.tolist()))
               for p, g in zip(pred, gt))
    return hits / (gt.shape[0] * gt.shape[1])


def latency_shape(ms):
    """p50/p95/p99 of per-query wall clock. A shape, never a rate."""
    a = np.asarray(ms, dtype=np.float64)
    return {
        "p50_ms": float(np.percentile(a, 50)),
        "p95_ms": float(np.percentile(a, 95)),
        "p99_ms": float(np.percentile(a, 99)),
        "mean_ms": float(a.mean()),
        "n_queries": int(len(a)),
        "concurrency": 1,
        "note": ("sequential, single client, client-side wall clock. This is "
                 "a latency shape and is not throughput; nothing here was "
                 "measured under load."),
    }


def rtt_baseline_readonly(engine, ns, log_fn=log, pings=RTT_PINGS):
    """RTT for `existing_collection` mode, which must not write anything.

    The local-target baseline creates an empty collection and searches it, so
    the number is the path with no index work in it. That is a write, and
    existing_collection mode is read-only against a collection someone else
    owns -- so here the round trip is timed with `describe()`, the cheapest
    read the protocol has.

    It is a *different* measurement and is labelled as one: a collection-info
    call is not a search, so it bounds the path from below rather than
    matching the query path exactly.
    """
    lat = []
    for _ in range(pings):
        t0 = time.perf_counter()
        engine.describe(ns)
        lat.append((time.perf_counter() - t0) * 1000.0)
    shape = latency_shape(lat)
    shape["method"] = ("collection-info round trip, not an empty-collection "
                       "search: existing_collection mode creates nothing")
    log_fn(f"rtt baseline (read-only) over {pings} calls: "
           f"p50 {shape['p50_ms']:.2f} ms, p95 {shape['p95_ms']:.2f} ms")
    return shape


def rtt_baseline(engine, session_id, dim, log_fn=log, pings=RTT_PINGS):
    """Round trip to an *empty* collection, so the number is the path, not
    the index. Measured before the real run, on the same connection."""
    ns = namespace_for(session_id, "rtt")
    q = np.zeros((1, dim), dtype=np.float32)
    q[0, 0] = 1.0
    lat = []
    with managed_namespace(engine, ns, dim, "inner_product"):
        for _ in range(pings):
            t0 = time.perf_counter()
            engine.search(ns, q, 1, None)
            lat.append((time.perf_counter() - t0) * 1000.0)
    log_fn(f"rtt baseline over {pings} pings: "
           f"p50 {np.percentile(lat, 50):.2f} ms, "
           f"p95 {np.percentile(lat, 95):.2f} ms")
    return latency_shape(lat)


def _ground_truth(workdir, base, queries, k, log_fn):
    """The same cache `simulate` writes, so both score against one truth."""
    ids_p = os.path.join(workdir, "ground_truth.npy")
    if os.path.exists(ids_p):
        ids = np.load(ids_p)
        if ids.shape[0] == len(queries) and ids.shape[1] >= k:
            log_fn(f"ground truth: reusing {ids_p}")
            return ids
    log_fn(f"ground truth: exact k-NN, k={k}")
    import faiss
    index = faiss.IndexFlatIP(base.shape[1])
    index.add(base)
    _, ids = index.search(queries, k)
    np.save(ids_p, ids.astype(np.int64))
    return ids.astype(np.int64)


def _simulated_recall(workdir, engine_params):
    """The `single_node_hnsw` row this verify run corresponds to.

    Matched on M and efSearch, because those are the two the engine params map
    onto. Returns (recall, config_label) or (None, reason).
    """
    p = os.path.join(workdir, "simulate.json")
    if not os.path.exists(p):
        return None, f"{COULDNT_CHECK}: no simulate.json in the workdir"
    with open(p, encoding="utf-8") as f:
        rows = json.load(f).get("rows", [])
    want_m = int(engine_params.get("m", 32))
    want_ef = int(engine_params.get("hnsw_ef", engine_params.get("ef", 128)))
    for r in rows:
        if r.get("family") != "single_node_hnsw":
            continue
        pr = r.get("params", {})
        if int(pr.get("M", -1)) == want_m and int(pr.get("efSearch", -1)) == want_ef:
            return r["recall_at_10"], r["config"]
    labels = [r["config"] for r in rows if r.get("family") == "single_node_hnsw"]
    return None, (f"{COULDNT_CHECK}: no single_node_hnsw row with M={want_m}, "
                  f"efSearch={want_ef}; rows present: {labels or 'none'}")


# --------------------------------------------------------------------------
# the command
# --------------------------------------------------------------------------

def environment_id():
    """A stable name for the machine a measurement was taken on.

    On a pod this is the pod id, injected by the session. Off a pod it is
    `local:<platform>`, which is deliberately not comparable to anything --
    two laptops both called "local" are two different machines, and the
    same-environment rule has to be able to tell them apart.
    """
    eid = os.environ.get("ONEGROUND_ENVIRONMENT_ID")
    if eid:
        return str(eid)
    # Never the hostname: see oneground/environment.local_environment_id.
    from ..environment import local_environment_id
    return local_environment_id()


def index_coverages(engine_names, workdir=None, repo_root=None):
    """What each engine says it can build, best source first (task 034).

    A resolution recorded against a live engine beats the declaration the
    adapter shipped, which is `not_resolved` on purpose -- nobody types an
    engine's capabilities in from its documentation. An engine with neither
    is `not_resolved` too, which is a couldn't-check and not a capability.
    """
    from ..adapters import get as get_adapter
    from ..adapters import index_families as IF

    recorded = {}
    roots = [d for d in (workdir, repo_root, os.getcwd()) if d]
    for root in roots:
        for rel in COVERAGE_FILES:
            path = os.path.join(root, rel)
            if os.path.exists(path):
                for cov in IF.read(path):
                    recorded.setdefault(cov.engine, cov)
    out = []
    for name in engine_names:
        if name in recorded:
            out.append(recorded[name])
            continue
        try:
            declared = getattr(get_adapter(name)(), "INDEX_COVERAGE", None)
        except Exception:                                 # noqa: BLE001
            declared = None
        out.append(declared if declared is not None else IF.unresolved(
            name, "no adapter declaration and no recorded resolution"))
    return out


def plan_index_families(cfg, engine_names, coverages):
    """Whether every named engine can build the declared index family.

    Called before anything is created -- before a container is started and
    before a pod session is prepared -- because a refusal that arrives after
    a run has been paid for is not a refusal. 022's precondition rule
    applies: every engine that cannot build it is named at once.

    Returns the per-engine decisions. Raises `VerifyError` when any named
    engine cannot build the family. An engine whose coverage was never
    resolved does **not** refuse: "nobody asked" is not "it cannot be done",
    and collapsing the two is the defect this exists to prevent.
    """
    from ..adapters import index_families as IF
    from ..models.base import HNSW, INDEX_ALGORITHMS

    family = str(cfg.get("index", HNSW) or HNSW)
    if family not in INDEX_ALGORITHMS:
        raise VerifyError(
            f"verify.index {family!r} is not a declared index family; they "
            f"are {', '.join(INDEX_ALGORITHMS)}")
    decisions = [IF.buildability(cov, family) for cov in coverages]
    refusing = [d for d in decisions if d.state == IF.NOT_VERIFIABLE_HERE]
    if refusing:
        raise VerifyError(
            "this run cannot be verified as configured:\n  - "
            + "\n  - ".join(f"{d.reason}. {d.remedy}" for d in refusing)
            + "\n\nNothing has been created. Change verify.index, or run "
              "against an engine that builds it. A simulate row for "
              f"index={family} stays a true statement about that algorithm "
              "on this corpus; it is simply not a deployable option on these "
              "engines.")
    return decisions


def run(requirements_path, up=False, down=False, on_pod=False,
        target_override=None, endpoint_override=None, engines_override=None,
        log_fn=log):
    """`target_override` and `endpoint_override` exist for
    `oneground calibrate engine`, which has to run locally against a
    Docker or already-running Qdrant whatever the requirements file says
    about pods. They are keyword-only in practice and nothing else passes
    them; the requirements file stays the authority for every real run."""
    t0 = time.time()
    req = intake.load(requirements_path)
    workdir = req.resolve(req.workdir)
    if not os.path.exists(os.path.join(workdir, "characterization.json")):
        raise VerifyError(
            f"no characterization in {workdir}. `verify` measures an engine "
            "on a sample that has already been characterized; run this "
            f"first:\n\n    oneground characterize {requirements_path}\n")

    cfg = req.data.get("verify") or {}
    target = str(target_override or cfg.get("target", "local")).lower()
    # `engines` is the list form and `engine` the single form; a run measures
    # them SEQUENTIALLY, never concurrently, so the engines never contend for
    # the machine they are being compared on. See docs/VERIFY.md.
    engine_names = [str(e) for e in (engines_override or cfg.get("engines")
                                     or [cfg.get("engine", "qdrant")])]
    engine_name = engine_names[0]
    engine_params = dict(cfg.get("engine_params") or
                         {"m": 32, "ef_construct": 200, "hnsw_ef": 128,
                          "indexing_threshold": 1})
    metric = str(cfg.get("metric", "inner_product"))
    ks = tuple(int(k) for k in (cfg.get("ks") or (10, 100)))

    # Task 034, before anything exists: an engine that cannot build the
    # declared index family refuses here, not after a pod has been paid for.
    # `_prepare_runpod` is the next thing that would happen on the runpod
    # path and `compose_up` on the local one; both are below this line.
    coverages = index_coverages(engine_names, workdir, req.resolve("."))
    coverage_decisions = plan_index_families(cfg, engine_names, coverages)

    if target == "runpod" and not on_pod:
        # Off the pod: prepare the session and stop. This never creates
        # anything -- `oneground pod up` is the only thing that can, and it
        # still needs a typed 'y' at a terminal.
        return _prepare_runpod(req, cfg, workdir, requirements_path, log_fn)

    if target == "runpod" or on_pod:
        # On the pod: the engine is on this host, reached over loopback.
        endpoint = str(cfg.get("pod_endpoint") or LOCAL_ENDPOINT)
        target = "runpod"
    elif target == "local":
        endpoint = endpoint_for(cfg, engine_name, endpoint_override)
    if target in ("existing", "existing_collection"):
        endpoint = str(cfg.get("endpoint") or "")
        if not endpoint:
            raise VerifyError(
                f"{requirements_path}: verify.target is {target!r} but "
                "verify.endpoint is not set")
    elif target not in ("local", "runpod"):
        raise VerifyError(
            f"{requirements_path}: verify.target {target!r} is not "
            "supported. This build has 'local', 'runpod' and 'existing'.")

    session_id = time.strftime("%Y%m%d-%H%M%S")
    env_id = environment_id()
    log_fn(f"verify '{req.name}'  target={target}  "
           f"engines={', '.join(engine_names)}  environment={env_id}")

    blocks = []
    for name in engine_names:
        ep = endpoint_for(cfg, name, endpoint_override
                          if name == engine_name else None)
        if target == "runpod" or on_pod:
            ep = str((cfg.get("pod_endpoints") or {}).get(name)
                     or cfg.get("pod_endpoint") or ep)
        log_fn("")
        log_fn(f"--- {name} at {ep} "
               f"({len(blocks) + 1} of {len(engine_names)}) ---")
        t_engine = time.time()
        started = False
        try:
            if up and target == "local":
                compose_up(log_fn, engine=name)
                started = True
            if target in ("existing", "existing_collection"):
                block = _verify_existing(req, cfg, workdir, name, ep,
                                         session_id, ks, engine_params, log_fn)
            else:
                block = _verify_local(req, cfg, workdir, name, ep,
                                      session_id, ks, engine_params, metric,
                                      log_fn)
        finally:
            # Each engine is torn down before the next one starts, so two
            # engines are never resident at once on the machine that is
            # measuring them.
            if down and started:
                compose_down(log_fn, engine=name)
        block["endpoint"] = ep
        block["compose_image"] = (compose_image(name) if target == "local"
                                  else None)
        block["environment_id"] = env_id
        block["elapsed_seconds"] = time.time() - t_engine
        blocks.append(block)

    result = _combine(blocks, env_id, target, time.time() - t0)
    # What each engine answered about the index family this run measured
    # (task 034). Carried into the receipt so the report can tell "nobody ran
    # it" from "it cannot be run here" without asking an engine again.
    result["index"] = {
        "family": str(cfg.get("index", "hnsw") or "hnsw"),
        "kind": "declared",
        "engines": [d.as_dict() for d in coverage_decisions],
        # The whole coverage, not only the decision for the family this run
        # measured: the report judges every simulated option, and an option
        # at a different algorithm needs the same question answered without
        # asking an engine again.
        "coverages": [c.as_dict() for c in coverages],
        "note": ("what each adapter says it can build. `coverage_unresolved` "
                 "means no engine was asked, which is a couldn't-check and "
                 "not a capability."),
    }
    _write(req, workdir, result, requirements_path, engine_names, target,
           engine_params, log_fn)
    _summary(req, result, workdir)
    return workdir


def _combine(blocks, env_id, target, elapsed):
    """One verify.json for one or many engines.

    The per-engine results live in `engines`, a list, and no engine is
    promoted to the top level -- a shape with a primary engine and an
    also-ran would be picking a favourite in the file format. `environment_id`
    is at the top because it is the one thing every block shares, and it is
    what the same-environment rule turns on: these engines were measured on
    the same machine, one after the other.
    """
    return {
        "schema_engines": 1,
        "environment_id": env_id,
        "target": target,
        "engines": blocks,
        "engines_measured": [b.get("engine") for b in blocks],
        "sequential": True,
        "sequential_note": (
            "engines were measured one after the other on the same host, "
            "never concurrently. They therefore never contend with each "
            "other -- and equally, this says nothing about how either "
            "behaves while the other is running."),
        "elapsed_seconds": elapsed,
    }


def _prepare_runpod(req, cfg, workdir, requirements_path, log_fn):
    """Generate the session spec for a matched-environment run. Creates
    nothing; prints what the developer has to run."""
    engines = list(cfg.get("engines") or [cfg.get("engine", "qdrant")])
    # Refuse an engine with no adapter, by asking the registry rather than by
    # naming the engines this build happens to have. The previous form
    # hard-coded "the only adapter in this build is qdrant" and would have
    # gone on refusing pgvector after the adapter existed -- a guard that
    # knows a list of names is a guard that is wrong the day the list changes.
    known = set(registered_engines())
    unknown = [n for n in engines if n not in known]
    if unknown:
        raise VerifyError(
            f"{requirements_path}: verify.engines names "
            f"{', '.join(repr(n) for n in unknown)}, and this build has no "
            f"adapter for {'them' if len(unknown) > 1 else 'it'}. Registered: "
            f"{', '.join(sorted(known))}. See docs/ADAPTERS.md.")
    # A pod session must also know where each engine will listen, or the run
    # reaches the pod and fails there, having already been paid for.
    missing_endpoints = [
        n for n in engines
        if not ((cfg.get("pod_endpoints") or {}).get(n)
                or cfg.get("pod_endpoint")
                or DEFAULT_ENDPOINTS.get(n))]
    if missing_endpoints:
        raise VerifyError(
            f"{requirements_path}: no pod endpoint for "
            f"{', '.join(missing_endpoints)}. Set verify.pod_endpoints so the "
            "pod-side run knows where to reach each engine.")
    # Task 017: prefer the pre-baked image, by digest, when the lock has one.
    # An explicit `verify.image` still wins -- someone naming an image means it.
    #
    # Task 017d: when the lock has NO digest this refuses rather than falling
    # back to POD_IMAGE on its own. `oneground/pod/image.py` already says the
    # rule -- "a missing digest is never a reason to fall back to a tag...
    # reference() raises instead, and the caller decides whether to use the
    # documented fallback base image explicitly" -- and this was its one
    # caller, deciding implicitly. A session on the base tag has no Postgres,
    # no pgvector, no Qdrant and no venv; it presents as an environment fault
    # a few minutes in, which is the failure mode that cost two pods in task
    # 015. A log line in a pod session's output is easy to miss; a refusal
    # before anything is created is not.
    #
    # The fallback is not removed, only made explicit: naming it in
    # `verify.image` is one line, and it then appears in the receipt as
    # something a person chose.
    from ..pod import image as podimage
    if cfg.get("image"):
        image = str(cfg["image"])
        log_fn(f"pod image: {image} (named in verify.image)")
    elif podimage.is_baked():
        image = podimage.reference()
        log_fn(f"pod image: {image} (pre-baked, pinned by digest)")
    else:
        raise VerifyError(
            "docker/pod/IMAGE.lock names no digest, so there is no pre-baked "
            "pod image to run.\n"
            "  The digest in that lock is the single source of truth for what "
            "a pod session pulls.\n"
            "\n"
            "  Either build and lock one:\n"
            "      bash docker/pod/rebuild.sh\n"
            "\n"
            "  or say explicitly that this run should use the base image and "
            "install\n"
            "  Postgres, pgvector, Qdrant and the venv at run time, as every "
            "session\n"
            "  through task 016 did:\n"
            f"      verify:\n        image: {POD_IMAGE}\n"
            "\n"
            "  This does not choose the base image for you. A session that "
            "quietly ran\n"
            "  without the baked engines would look like an environment "
            "fault, and that\n"
            "  is the failure mode the pre-baked image exists to remove.")
    path = runpod_target.write_session(req, workdir, cfg, engines, image,
                                       path=cfg.get("session_path"),
                                       log_fn=log_fn)
    caps = runpod_target.session_spec(req, workdir, cfg, engines,
                                      image)["caps"]
    inputs = runpod_target.bundle_inputs(workdir)
    spec_inputs = runpod_target.session_spec(req, workdir, cfg, engines,
                                             image)["inputs"]
    pod_req = runpod_target.pod_requirements(req, cfg) or req
    _, external = runpod_target.corpus_inputs(pod_req)
    if pod_req is not req:
        print()
        print("  the pod runs %s (verify.requirements_on_pod), so the paths "
              "below are" % cfg.get("requirements_on_pod"))
        print("  the ones it will read -- not the ones on this machine.")
    log_fn(f"session written to {path}")
    print(runpod_target.instructions(path, workdir, engines, image, caps))
    print("  workdir inputs the pod will use:")
    for name, digest in sorted(inputs.items()):
        print(f"    {name:<28} {digest[:16]}")

    uploaded = sum(os.path.getsize(i["local"])
                   for i in spec_inputs if os.path.exists(i["local"]))
    print()
    print("  %d file(s) will be uploaded, %s bytes: git does not carry them."
          % (len([i for i in spec_inputs if os.path.exists(i["local"])]),
             "{:,}".format(uploaded)))
    if external:
        # Not a warning to be skimmed past: the session as written cannot run
        # unless these are already on the pod. The arxiv-150k vectors are
        # 460 MB at an absolute path outside the repo, and uploading them is
        # what the volume-first ruling rejected.
        print()
        print("  MUST ALREADY BE ON THE POD -- outside the repository, so "
              "neither the")
        print("  bundle nor the input upload can carry them:")
        for label, p, _why in external:
            size = os.path.getsize(p) if os.path.exists(p) else None
            print("    %-10s %s%s"
                  % (label, p,
                     "  (%s bytes)" % "{:,}".format(size) if size else ""))
        print()
        tarball = cfg.get("pod_corpus_tarball")
        manifest = cfg.get("pod_corpus_manifest")
        if tarball:
            print("  The pod's preflight extracts them from")
            print("    %s" % tarball)
            print("  before it downloads an engine, and checks both against")
            print("    %s" % (manifest or "(no manifest declared)"))
            if manifest:
                print("  so a corpus that is not the one this ground truth "
                      "was built from")
                print("  stops the run rather than producing a recall number "
                      "that means")
                print("  nothing. If neither the files nor the tarball are "
                      "there, the run")
                print("  exits in seconds having listed what is.")
            else:
                print("  DIGESTS UNCHECKED: declare verify.pod_corpus_manifest "
                      "to confirm the")
                print("  volume holds the corpus this ground truth was built "
                      "from.")
        else:
            print("  Put them on the network volume and point a pod-side "
                  "requirements file")
            print("  at that path (verify.requirements_on_pod), or this "
                  "session will fail")
            print("  on the pod exactly where session 20260909-205151 did.")
    print()
    return workdir


def _verify_local(req, cfg, workdir, engine_name, endpoint, session_id, ks,
                  engine_params, metric, log_fn):
    """Ingest the characterized sample, search it, measure."""
    vec_path = req.resolve(req.vectors.get("path"))
    base = loaders.load_vectors(vec_path)
    if not req.vectors.get("normalized", False):
        base = loaders.normalize_rows(base)
    qcfg = dict(req.queries)
    qcfg["path"] = req.resolve(qcfg["path"])
    queries, _ = loaders.load_queries(qcfg)
    queries = loaders.normalize_rows(np.ascontiguousarray(queries))
    log_fn(f"{len(base):,} vectors, {len(queries):,} queries, "
           f"dim {base.shape[1]}")

    gt = _ground_truth(workdir, base, queries, max(ks), log_fn)

    engine = get_engine(engine_name)()
    try:
        engine.connect(endpoint, cfg.get("credentials_env"))
    except AdapterError as e:
        raise VerifyError(
            f"{e}\n\nFor target 'local', start the pinned engine first:\n"
            f"    docker compose -f {COMPOSE_FILE} up -d\n"
            "or pass --up to have verify do it.") from None

    out = {"mode": "local", "engine": engine_name,
           "environment_id": environment_id(),
           "engine_version": engine.version,
           "n_base": int(len(base)), "n_queries": int(len(queries)),
           "dimension": int(base.shape[1])}

    out["rtt_baseline_ms"] = rtt_baseline(engine, session_id, base.shape[1],
                                          log_fn)

    ns = namespace_for(session_id, "verify")
    with managed_namespace(engine, ns, base.shape[1], metric, engine_params):
        log_fn(f"ingesting {len(base):,} vectors")
        stats = engine.upsert(ns, range(len(base)), base)
        out["ingest"] = stats.as_dict()
        log_fn(f"  {stats.vectors_per_second:,.0f} vectors/s "
               f"({stats.seconds:.1f} s, durable writes)")

        waiter = getattr(engine, "wait_for_index", None)
        if callable(waiter):
            indexed, points, secs = waiter(ns)
            out["index"] = {"indexed_vectors": indexed, "points": points,
                            "seconds": secs,
                            "fully_indexed": bool(points and indexed >= points)}
            log_fn(f"  indexed {indexed}/{points} in {secs:.1f} s")
            if not out["index"]["fully_indexed"]:
                out["index"]["warning"] = (
                    "the engine had not finished indexing; the searches below "
                    "may have been answered by an exact scan rather than the "
                    "index")

        out["searches"] = {}
        for k in ks:
            log_fn(f"searching k={k}")
            cand = engine.search(ns, queries, k, engine_params)
            shape = latency_shape(cand.latencies_ms)
            row = {f"recall_at_{k}": recall_at(cand.ids, gt, k)}
            _apply_noise_guard(row, shape, out["rtt_baseline_ms"], k,
                               engine=engine_name,
                               transport=_transport_of(engine))
            out["searches"][f"k={k}"] = row
            log_fn(f"  recall@{k} {row[f'recall_at_{k}']:.4f}   "
                   f"p50 {shape['p50_ms']:.2f} ms  p95 {shape['p95_ms']:.2f} ms")

        # ---- load phase: throughput at the requested concurrency ----
        # Runs AFTER the sequential recall pass, so a query dropped or slowed
        # under load can never be counted as a recall miss. The two passes
        # share the corpus and nothing else.
        lat_cfg = ((req.data.get("constraints") or {}).get("latency") or {})
        want_load = bool(cfg.get("load", lat_cfg.get("concurrency")))
        if want_load:
            conc = int(lat_cfg.get("concurrency",
                                   cfg.get("concurrency", 8)))
            tqps = float(lat_cfg.get("at_qps", cfg.get("target_qps", 0)))
            mins = float(cfg.get("duration_minutes", 1.0))
            warm = float(cfg.get("warmup_seconds", 10.0))
            # Task 017 item 2: `runs: N` repeats the load phase so the report
            # can say what the run-to-run spread is instead of implying there
            # is none. Default 1, which is the shape every earlier run had.
            n_runs = max(1, int(cfg.get("runs", 1) or 1))
            results, restarts = [], []
            for i in range(n_runs):
                if i:
                    note = restart_engine(engine, cfg, engine_name, endpoint,
                                          log_fn=log_fn)
                    restarts.append(note)
                    log_fn(f"  run {i + 1}/{n_runs}: {note}")
                results.append(loadgen.run_load(
                    engine, ns, queries, k=10, concurrency=conc,
                    target_qps=tqps, duration_minutes=mins,
                    warmup_seconds=warm, params=engine_params,
                    container=cfg.get("engine_container"), log_fn=log_fn))
            res = results[0]
            out["load"] = res.as_dict()
            if n_runs > 1:
                # Every run is kept. The aggregate is derived from these and
                # not the other way round, so a reader can recompute it.
                out["load_runs"] = [r.as_dict() for r in results]
                out["load_restarts"] = restarts
            # The p95 under load is a different quantity from the sequential
            # shape, and the verdict rule reads whichever the row carries.
            p = res.percentiles()
            if p:
                shape = dict(p)
                shape.update({"n_queries": res.completed,
                              "concurrency": conc,
                              "note": ("measured UNDER LOAD at concurrency "
                                       f"{conc}; not a single-client shape")})
                spread = p95_spread([(r.percentiles() or {}).get("p95_ms")
                                     for r in results]) if n_runs > 1 else None
                if spread:
                    # `p95_ms` stays a float so every existing reader keeps
                    # working; it becomes the median rather than run 1, which
                    # is the honest single number when there are several.
                    shape["p95_ms"] = spread["median"]
                    shape["p95_across_runs"] = spread
                    shape["note"] += (
                        f"; p95_ms is the MEDIAN of {spread['n_runs']} runs "
                        f"(min {spread['min']:.2f}, max {spread['max']:.2f}, "
                        f"spread {spread['spread']:.2f} ms) -- see "
                        "p95_across_runs, and the verdict rule, which does "
                        "not decide from one run")
                row = {"recall_at_10": out["searches"]["k=10"]["recall_at_10"]}
                _apply_noise_guard(row, shape, out["rtt_baseline_ms"], 10,
                                   engine=engine_name,
                                   transport=_transport_of(engine))
                out["searches"]["k=10_under_load"] = row

            # Task 017 item 5: the ceiling, opt-in and kept well away from the
            # sustain verdict. Off by default because it deliberately drives
            # the engine into degradation, which is not something to do to a
            # run that was asked for a recall number.
            if cfg.get("measure_ceiling") or lat_cfg.get("measure_ceiling"):
                log_fn("measuring qps_max (open-loop ramp)")
                out["qps_max"] = loadgen.ramp_to_ceiling(
                    engine, ns, queries, k=10, params=engine_params,
                    container=cfg.get("engine_container"), log_fn=log_fn)
                log_fn(f"  qps_max {out['qps_max']['qps_max']} at "
                       f"concurrency {out['qps_max']['at_concurrency']}; "
                       f"{out['qps_max']['stopped_because']}")

        out["engine_facts"] = engine.describe(ns).as_dict()

    # calibration
    sim, why = _simulated_recall(workdir, engine_params)
    measured = out["searches"].get("k=10", {}).get("recall_at_10")
    if sim is None or measured is None:
        out["calibration_error_recall"] = why or f"{COULDNT_CHECK}: no k=10 run"
    else:
        out["calibration_error_recall"] = sim - measured
        out["calibration"] = {"simulated_recall_at_10": sim,
                              "measured_recall_at_10": measured,
                              "simulated_config": why,
                              "definition": "simulated - measured"}
    return out


# The transport each adapter uses when it has nothing faster to offer. When a
# run is already on this one and the round trip still dominates, no client
# choice closes the gap -- the question is unanswerable here, which is a
# different statement from "this run was noisy".
FASTEST_TRANSPORT = {"qdrant": "grpc", "pgvector": "libpq"}


def _transport_of(engine):
    """What the adapter says it connected over, or None.

    Read off the adapter rather than assumed from the engine name: the whole
    point is that qdrant can be either, and which one it got decides whether
    a refused latency row is "noisy" or "unanswerable".
    """
    return getattr(engine, "_transport", None)


def _apply_noise_guard(row, shape, baseline, k, engine=None, transport=None):
    """Set `latency_shape_single_client`: the shape, or why it is unusable.

    Sets the key either way rather than replacing one the caller pre-set. A
    guard that only writes on failure is a guard that silently does nothing
    when called on the wrong dict, which is how it was first written here.

    Task 017f splits the refusal in two. "Environment noise" reads as a bad
    day -- run it again, run it somewhere quieter. On session 20260913-161921
    it was nothing of the sort: the pod was fast enough that Qdrant's round
    trip was 60% of its p95, and no rerun on that class of host would have
    changed it. That is not a noisy measurement, it is a question this
    environment cannot answer, and saying so has to name what would.
    """
    row["latency_shape_single_client"] = shape
    base_p95 = baseline["p95_ms"]
    if shape["p95_ms"] <= 0:
        return
    share = base_p95 / shape["p95_ms"]
    row["rtt_share_of_p95"] = share
    if transport:
        row["transport"] = transport
    if share <= NOISE_FRACTION:
        return

    head = (f"the baseline RTT p95 ({base_p95:.2f} ms) is "
            f"{share * 100:.0f}% of the query p95 ({shape['p95_ms']:.2f} ms), "
            f"over the {NOISE_FRACTION * 100:.0f}% limit")
    best = FASTEST_TRANSPORT.get(str(engine))
    if transport and best and str(transport) == best:
        row["latency_shape_single_client"] = (
            f"{COULDNT_CHECK}: unanswerable in this environment -- {head}, "
            f"and this run already used the fastest transport this adapter "
            f"has ({transport}). No client choice closes that gap: the engine "
            "answers faster than the path to it can be measured. It becomes "
            "answerable with more engine work per request (a larger corpus, a "
            "higher k), an in-process measurement, or a host where the engine "
            "rather than the path is the bottleneck -- not by re-running this "
            "one. Recall is unaffected and is reported.")
        row["latency_unanswerable_here"] = True
    else:
        faster = (f" This run used {transport}; {best} would lower the round "
                  f"trip and may bring it under the limit." if transport
                  and best and transport != best else "")
        row["latency_shape_single_client"] = (
            f"{COULDNT_CHECK}: environment noise -- {head}, so this measures "
            f"the path to the engine more than the engine.{faster} Recall is "
            "unaffected and is reported.")
    row["latency_measured_but_not_attributable"] = shape


def _verify_existing(req, cfg, workdir, engine_name, endpoint, session_id, ks,
                     engine_params, log_fn):
    """Read-only against a collection someone else owns.

    Scroll a sample out, compute exact ground truth **over that sample**, then
    query the live collection and score against it. The receipt has to say what
    that means, and it does: recall here is measured over sampled neighbours,
    not over the whole collection, so a neighbour that exists in the collection
    but not in the sample counts as neither hit nor miss.
    """
    ns = str(cfg.get("collection") or "")
    if not ns:
        raise VerifyError("verify.collection is required for target "
                          "'existing'")
    sample_size = int(cfg.get("sample_size", 5000))
    n_queries = int(cfg.get("n_queries", 200))

    engine = get_engine(engine_name)()
    engine.connect(endpoint, cfg.get("credentials_env"))
    facts = engine.describe(ns)
    log_fn(f"existing collection {ns}: {facts.point_count} points, "
           f"dim {facts.dim}")

    log_fn(f"scrolling {sample_size:,} vectors (read-only)")
    ids, vecs = engine.scroll(ns, sample_size)
    if len(ids) == 0:
        raise VerifyError(f"{ns} returned no points to scroll")
    vecs = loaders.normalize_rows(np.ascontiguousarray(vecs))

    rng = np.random.default_rng(req.seed)
    qi = rng.choice(len(ids), size=min(n_queries, len(ids)), replace=False)
    queries = np.ascontiguousarray(vecs[qi])

    import faiss
    ix = faiss.IndexFlatIP(vecs.shape[1])
    ix.add(vecs)
    _, gt_local = ix.search(queries, max(ks))
    gt_ids = ids[gt_local]                     # engine ids, not row indices

    out = {"mode": "existing_collection", "engine": engine_name,
           "environment_id": environment_id(),
           "engine_version": engine.version, "collection": ns,
           "n_sampled": int(len(ids)), "n_queries": int(len(queries)),
           "dimension": int(vecs.shape[1]),
           "engine_facts": facts.as_dict(),
           "read_only": ("this mode created, wrote and deleted nothing on "
                         "the engine: it scrolls, describes and searches"),
           "recall_scope": (
               "LOWER BOUND. Ground truth is computed over the "
               f"{len(ids):,} scrolled vectors, but the engine searches all "
               f"{facts.point_count} points in the collection. A neighbour "
               "the engine returns that is genuinely nearer but was not in "
               "the scrolled sample is scored as a MISS, because it is not in "
               "the sampled ground truth. So the true recall of this "
               "collection is at least this number and probably higher, and "
               "the gap grows as the sample shrinks relative to the "
               "collection. Compare two runs of this mode only at the same "
               "sample fraction."),
           "sample_fraction": (len(ids) / facts.point_count
                               if facts.point_count else None)}

    out["rtt_baseline_ms"] = rtt_baseline_readonly(engine, ns, log_fn)
    out["searches"] = {}
    for k in ks:
        cand = engine.search(ns, queries, k, engine_params)
        shape = latency_shape(cand.latencies_ms)
        row = {f"recall_at_{k}": recall_at(cand.ids, gt_ids, k)}
        _apply_noise_guard(row, shape, out["rtt_baseline_ms"], k,
                           engine=engine_name,
                           transport=_transport_of(engine))
        out["searches"][f"k={k}"] = row
        log_fn(f"  recall@{k} {row[f'recall_at_{k}']:.4f} (over the sample)")

    out["calibration_error_recall"] = (
        f"{COULDNT_CHECK}: existing_collection mode measures recall over a "
        "sampled ground truth, which is not the quantity simulate scored")
    return out


def _write(req, workdir, result, requirements_path, engine_names,
           target, engine_params, log_fn):
    """verify.json holds the measurements; verify_info.json the declarations.

    Both are per-engine now. `engine_facts` is stripped out of every block in
    verify.json and lives only in verify_info.json, because it is the engine's
    claim about itself rather than anything oneground measured -- the same
    split the single-engine form had, applied blockwise.
    """
    measurement = dict(result)
    measurement["engines"] = [
        {k: v for k, v in b.items() if k != "engine_facts"}
        for b in result.get("engines", [])]
    measurement["run"] = req.name
    measurement["schema"] = intake.SCHEMA_VERSION
    write_json_stable(os.path.join(workdir, "verify.json"),
                      round_floats(measurement))

    versions, torch_info = library_versions(log=log_fn)
    info = {
        "kind": {"verify.json": "receipt (measurements)",
                 "verify_info.json": "declared"},
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": target,
        "environment_id": result.get("environment_id"),
        "engines": [
            {"engine": b.get("engine"),
             "engine_version": b.get("engine_version"),
             "endpoint": b.get("endpoint"),
             "engine_params": engine_params,
             "engine_facts": b.get("engine_facts"),
             "compose_image": b.get("compose_image")}
            for b in result.get("engines", [])],
        "library_versions": versions,
        "oneground": producing_version(),
        # Which command wrote this, for the replay rule (task 046,
        # docs/INTERFACE.md section 2). Beside the version rather than
        # inside it: it is not a fact about the version.
        "invocation": invocation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "requirements_file": {"path": os.path.abspath(requirements_path),
                              "sha256": sha256_file(requirements_path)},
        "note": ("engine_facts is what each engine reported about itself. "
                 "Nothing in this file was measured by oneground."),
    }
    write_json_stable(os.path.join(workdir, "verify_info.json"), info)

    present = [f for f in CHARACTERIZE_FILES + SIMULATE_FILES + VERIFY_FILES
               if os.path.exists(os.path.join(workdir, f))]
    write_manifest(workdir, present)


def _summary(req, result, workdir):
    """One block per engine, then what the run as a whole established.

    A flat single-engine result -- the shape verify.json had before task 015,
    and the shape `_verify_local` still returns -- is read as a list of one,
    so a caller holding one block does not have to wrap it.
    """
    blocks = result.get("engines")
    if not isinstance(blocks, list):
        blocks = [result] if result.get("engine") else []
    for block in blocks:
        _summary_engine(req, block, workdir)

    if len(blocks) > 1:
        print()
        print("=" * 78)
        print(f"  {len(blocks)} engines, one environment: "
              f"{result.get('environment_id')}")
        print("=" * 78)
        hdr = (f"  {'engine':<12} {'recall@10':>10} {'rtt/query':>10} "
               f"{'p95 ms':>9} {'ingest/s':>10}")
        print(hdr)
        print("  " + "-" * (len(hdr) - 2))
        for b in blocks:
            row = (b.get("searches") or {}).get("k=10") or {}
            shape = row.get("latency_shape_single_client")
            p95 = (shape.get("p95_ms") if isinstance(shape, dict) else None)
            rtt = (b.get("rtt_baseline_ms") or {}).get("p95_ms")
            ratio = (f"{rtt / p95:.0%}" if (rtt and p95) else "-")
            ing = (b.get("ingest") or {}).get("vectors_per_second")
            print(f"  {str(b.get('engine')):<12} "
                  f"{row.get('recall_at_10', float('nan')):>10.4f} "
                  f"{ratio:>10} "
                  f"{(f'{p95:.2f}' if p95 else '-'):>9} "
                  f"{(f'{ing:,.0f}' if ing else '-'):>10}")
        print()
        print("  Measured SEQUENTIALLY on one host: the engines never ran at "
              "the same time,")
        print("  so neither number includes contention from the other -- and "
              "neither says")
        print("  anything about how either behaves while the other is "
              "running.")
        print("  rtt/query over 20% means latency is not attributable to the "
              "engine.")
    print()
    print(f"  verify.json + verify_info.json in {workdir}")
    print()


def _summary_engine(req, result, workdir):
    print()
    print("=" * 78)
    print(f"verify -- {req.name}   {result['engine']} "
          f"{result.get('engine_version', '?')}   mode {result['mode']}")
    print("=" * 78)
    if "ingest" in result:
        ing = result["ingest"]
        print(f"  ingest            {ing['vectors_per_second']:,.0f} vectors/s "
              f"({ing['n_vectors']:,} in {ing['seconds']:.1f} s, durable)")
    if "index" in result:
        ix = result["index"]
        print(f"  indexed           {ix['indexed_vectors']}/{ix['points']} "
              f"in {ix['seconds']:.1f} s")
    rtt = result["rtt_baseline_ms"]
    how = rtt.get("method", f"empty collection, {rtt['n_queries']} pings")
    print(f"  rtt baseline      p50 {rtt['p50_ms']:.2f} ms  "
          f"p95 {rtt['p95_ms']:.2f} ms   ({how})")
    print()
    for key, row in result["searches"].items():
        # "k=10_under_load" -> 10. Splitting on "=" alone left
        # "10_under_load", which then looked up `recall_at_10_under_load` and
        # raised KeyError -- after every number in this summary had already
        # been measured and written (session 20260909-213526).
        k = key.split("=", 1)[1].split("_", 1)[0]
        under_load = key.endswith("_under_load")
        print(f"  {key}")
        recall = row.get(f"recall_at_{k}")
        if recall is None:
            print(f"    recall@{k:<5}      -")
        elif under_load:
            # Carried over from the sequential run, not measured under load:
            # the load generator never measures recall. An unlabelled number
            # here would read as a second measurement of the same thing.
            print(f"    recall@{k:<5}      {recall:.4f}   "
                  "(from the sequential run -- load never measures recall)")
        else:
            print(f"    recall@{k:<5}      {recall:.4f}")
        shape = row["latency_shape_single_client"]
        if isinstance(shape, str):
            print(f"    latency          {shape}")
        elif under_load:
            # Measured at the session's concurrency. The stored field is
            # still named latency_shape_single_client -- a schema wart kept
            # because renaming it would change verify.json for every reader,
            # including the verdict rules -- but the caption must not repeat
            # the lie.
            conc = shape.get("concurrency", "?")
            print(f"    latency          p50 {shape['p50_ms']:.2f}  "
                  f"p95 {shape['p95_ms']:.2f}  p99 {shape['p99_ms']:.2f} ms "
                  f"(UNDER LOAD at concurrency {conc})")
        else:
            print(f"    latency shape    p50 {shape['p50_ms']:.2f}  "
                  f"p95 {shape['p95_ms']:.2f}  p99 {shape['p99_ms']:.2f} ms "
                  f"(sequential, 1 client -- not throughput)")
    print()
    if any(k.endswith("_under_load") for k in result["searches"]):
        print("  rows marked UNDER LOAD were measured at the stated "
              "concurrency and are")
        print("  throughput-relevant. The rest are sequential single-client "
              "latency shapes,")
        print("  which are not throughput.")
    else:
        print("  latency above is sequential, single client, client-side: a "
              "latency shape and")
        print("  not throughput. Nothing here was measured under load.")
    print()
    cal = result.get("calibration_error_recall")
    if isinstance(cal, str):
        print(f"  calibration      {cal}")
    else:
        c = result["calibration"]
        print(f"  calibration      simulated {c['simulated_recall_at_10']:.4f} "
              f"- measured {c['measured_recall_at_10']:.4f} = {cal:+.4f}")
        print(f"                   ({c['simulated_config']})")
    if "recall_scope" in result:
        print()
        print(f"  scope            {result['recall_scope']}")
    print()
    print(f"  measured in {result.get('elapsed_seconds', 0) / 60:.1f} min. "
          "Every number here is a measurement of")
    print("  this engine on this sample. Nothing is scored against your "
          "constraints.")
