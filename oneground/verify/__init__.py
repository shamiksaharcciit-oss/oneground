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
import time

import numpy as np

from .. import intake
from ..adapters import (AdapterError, get as get_engine, managed_namespace,
                        namespace_for)
from ..receipts import (library_versions, round_floats, sha256_file,
                        write_json_stable, write_manifest)
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

# The pod image for a matched-environment run. A CPU-capable image with
# python3.12 and curl is all this needs: the engine runs from its own release
# binary rather than from a container, because RunPod cannot grant the
# privileges docker-in-docker requires (measured, task 011). Resolved live
# from Docker Hub and pinned; see the report.
POD_IMAGE = "runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404"

# The baseline share above which latency is not attributable to the engine.
NOISE_FRACTION = 0.20
RTT_PINGS = 50


class VerifyError(RuntimeError):
    """The run cannot proceed. The message says what to do about it."""


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# the local target
# --------------------------------------------------------------------------

def compose_image():
    """The pinned tag from the compose file, for the receipt."""
    try:
        with open(COMPOSE_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("image:"):
                    return line.split("image:", 1)[1].strip()
    except OSError:
        pass
    return None


def compose_up(log_fn=log, timeout=120):
    log_fn(f"docker compose up ({compose_image()})")
    subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, "up", "-d"],
                   check=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    deadline = time.time() + timeout
    while time.time() < deadline:
        p = subprocess.run(["docker", "inspect", "--format",
                            "{{.State.Health.Status}}",
                            "oneground-verify-qdrant"],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if "healthy" in (p.stdout or ""):
            log_fn("  container healthy")
            return True
        time.sleep(2)
    raise VerifyError("the qdrant container did not become healthy in "
                      f"{timeout}s")


def compose_down(log_fn=log):
    log_fn("docker compose down -v")
    subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"],
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


def run(requirements_path, up=False, down=False, on_pod=False,
        target_override=None, endpoint_override=None, log_fn=log):
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
    engine_name = str(cfg.get("engine", "qdrant"))
    engine_params = dict(cfg.get("engine_params") or
                         {"m": 32, "ef_construct": 200, "hnsw_ef": 128,
                          "indexing_threshold": 1})
    metric = str(cfg.get("metric", "inner_product"))
    ks = tuple(int(k) for k in (cfg.get("ks") or (10, 100)))

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
        endpoint = str(endpoint_override or cfg.get("endpoint")
                       or LOCAL_ENDPOINT)
        if up:
            compose_up(log_fn)
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
    log_fn(f"verify '{req.name}'  target={target}  engine={engine_name}  "
           f"endpoint={endpoint}")

    try:
        if target in ("existing", "existing_collection"):
            result = _verify_existing(req, cfg, workdir, engine_name, endpoint,
                                      session_id, ks, engine_params, log_fn)
        else:
            result = _verify_local(req, cfg, workdir, engine_name, endpoint,
                                   session_id, ks, engine_params, metric,
                                   log_fn)
    finally:
        if down:
            compose_down(log_fn)

    result["elapsed_seconds"] = time.time() - t0
    _write(req, workdir, result, requirements_path, engine_name, endpoint,
           target, engine_params, log_fn)
    _summary(req, result, workdir)
    return workdir


def _prepare_runpod(req, cfg, workdir, requirements_path, log_fn):
    """Generate the session spec for a matched-environment run. Creates
    nothing; prints what the developer has to run."""
    engines = list(cfg.get("engines") or [cfg.get("engine", "qdrant")])
    for name in engines:
        if name != "qdrant":
            raise VerifyError(
                f"{requirements_path}: verify.engines names {name!r}, and "
                "the only adapter in this build is qdrant. The code path "
                "handles a list so a second engine needs no change here, but "
                "the adapter has to exist first.")
    image = str(cfg.get("image") or POD_IMAGE)
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
            _apply_noise_guard(row, shape, out["rtt_baseline_ms"], k)
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
            res = loadgen.run_load(
                engine, ns, queries, k=10, concurrency=conc,
                target_qps=tqps, duration_minutes=mins, warmup_seconds=warm,
                params=engine_params,
                container=cfg.get("engine_container"), log_fn=log_fn)
            out["load"] = res.as_dict()
            # The p95 under load is a different quantity from the sequential
            # shape, and the verdict rule reads whichever the row carries.
            p = res.percentiles()
            if p:
                shape = dict(p)
                shape.update({"n_queries": res.completed,
                              "concurrency": conc,
                              "note": ("measured UNDER LOAD at concurrency "
                                       f"{conc}; not a single-client shape")})
                row = {"recall_at_10": out["searches"]["k=10"]["recall_at_10"]}
                _apply_noise_guard(row, shape, out["rtt_baseline_ms"], 10)
                out["searches"]["k=10_under_load"] = row

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


def _apply_noise_guard(row, shape, baseline, k):
    """Set `latency_shape_single_client`: the shape, or why it is unusable.

    Sets the key either way rather than replacing one the caller pre-set. A
    guard that only writes on failure is a guard that silently does nothing
    when called on the wrong dict, which is how it was first written here.
    """
    row["latency_shape_single_client"] = shape
    base_p95 = baseline["p95_ms"]
    if shape["p95_ms"] <= 0:
        return
    share = base_p95 / shape["p95_ms"]
    row["rtt_share_of_p95"] = share
    if share > NOISE_FRACTION:
        row["latency_shape_single_client"] = (
            f"{COULDNT_CHECK}: environment noise -- the baseline RTT "
            f"p95 ({base_p95:.2f} ms) is {share * 100:.0f}% of the query p95 "
            f"({shape['p95_ms']:.2f} ms), over the {NOISE_FRACTION * 100:.0f}% "
            "limit, so this measures the path to the engine more than the "
            "engine. Recall is unaffected and is reported.")
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
        _apply_noise_guard(row, shape, out["rtt_baseline_ms"], k)
        out["searches"][f"k={k}"] = row
        log_fn(f"  recall@{k} {row[f'recall_at_{k}']:.4f} (over the sample)")

    out["calibration_error_recall"] = (
        f"{COULDNT_CHECK}: existing_collection mode measures recall over a "
        "sampled ground truth, which is not the quantity simulate scored")
    return out


def _write(req, workdir, result, requirements_path, engine_name, endpoint,
           target, engine_params, log_fn):
    measurement = {k: v for k, v in result.items() if k != "engine_facts"}
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
        "engine": engine_name,
        "endpoint": endpoint,
        "engine_params": engine_params,
        "engine_facts": result.get("engine_facts"),
        "compose_image": compose_image() if target == "local" else None,
        "library_versions": versions,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "requirements_file": {"path": os.path.abspath(requirements_path),
                              "sha256": sha256_file(requirements_path)},
        "note": ("engine_facts is what the engine reported about itself. "
                 "Nothing in this file was measured by oneground."),
    }
    write_json_stable(os.path.join(workdir, "verify_info.json"), info)

    present = [f for f in CHARACTERIZE_FILES + SIMULATE_FILES + VERIFY_FILES
               if os.path.exists(os.path.join(workdir, f))]
    write_manifest(workdir, present)


def _summary(req, result, workdir):
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
    print(f"  measured in {result['elapsed_seconds'] / 60:.1f} min. Every "
          "number here is a measurement of")
    print("  this engine on this sample. Nothing is scored against your "
          "constraints.")
    print()
    print(f"  verify.json + verify_info.json in {workdir}")
    print()
