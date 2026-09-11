"""`oneground calibrate` — the tool measures its own error, in public.

Three layers of validation, and this package is where two of them run:

    layers   the three assumptions every recall here rests on: corpus
             reachability, metric agreement, recall-rule accounting. BLOCKING
    curve    our simulator against someone else's published numbers, on a
             corpus and a ground truth we did not produce. ADVISORY on the
             glove fixture, because it compares two HNSW implementations that
             genuinely differ and the difference is published as an offset
    engine   our simulator against a real engine, on the user's own corpus
    show     the history they all append to

What makes this different from a test suite is that it can *fail in public and
keep the failure*. A contradicted line is appended, not fixed; the history is
append-only, and a tolerance is never widened to turn a contradiction into a
pass. `docs/VALIDATION.md` says which measures are validated by reference and
which are only predictions.

Exit codes
----------
    0   nothing contradicted
    1   at least one check contradicted
    2   --strict only: nothing contradicted, but something could not be
        checked

`couldnt_check` never fails by default. A published reference point that does
not exist is a gap in the reference, not a defect in this installation, and
the CI workflow is wired to the same rule.
"""

import argparse
import os
import sys
import time

import numpy as np

from ..models.base import resolve_deterministic
from . import history as H
from . import layers as L
from . import reference as R

VERIFIED = H.VERIFIED
CONTRADICTED = H.CONTRADICTED
COULDNT_CHECK = H.COULDNT_CHECK

DEFAULT_FIXTURE = "glove-100-angular"
DEFAULT_K = 10

# faiss reads a memmap through this many rows at a time so a 473 MB corpus is
# added to the index without ever being resident twice.
ADD_CHUNK = 100_000

# Queries per search call. All 10,000 at once is what faiss expects and what
# a well-provisioned machine should do; on the development laptop it is how a
# run gets killed after an hour of building.
BATCH_QUERIES = 1_000

# Built indexes are parked here. A deterministic build over a million vectors
# is a 69-minute measurement (task 012b); throwing it away because the search
# after it failed is the kind of waste that stops people re-running checks.
INDEX_CACHE_DIR = os.path.join(".cache", "indexes")


class CalibrateError(RuntimeError):
    """The check cannot be run. The message says what to do about it."""


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# fixture access
# --------------------------------------------------------------------------

def load_spec(fixture_id, fixtures_dir="fixtures"):
    import yaml
    p = os.path.join(fixtures_dir, f"{fixture_id}.fixture.yaml")
    if not os.path.exists(p):
        raise CalibrateError(f"no fixture spec at {p}")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f), p


def fixture_arrays(fixture_id, fixtures_dir="fixtures"):
    """vectors (memmap), queries, published ground truth."""
    d = os.path.join(fixtures_dir, fixture_id)
    need = ["vectors.npy", "queries.npy", "ground_truth.npy"]
    missing = [n for n in need if not os.path.exists(os.path.join(d, n))]
    if missing:
        raise CalibrateError(
            f"{d} is missing {', '.join(missing)}. These are large, "
            f"re-derivable from the upstream HDF5, and deliberately not "
            f"committed. Build them with:\n\n"
            f"    oneground calibrate fixture --fixture {fixture_id} "
            f"--source <glove-100-angular.hdf5>\n")
    return (np.load(os.path.join(d, "vectors.npy"), mmap_mode="r"),
            np.load(os.path.join(d, "queries.npy")),
            np.load(os.path.join(d, "ground_truth.npy")))


def parse_config(text):
    """`M=12,efConstruction=500` -> {'M': 12, 'efConstruction': 500}."""
    out = {}
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise CalibrateError(f"bad --config item {part!r}; want key=value")
        k, v = part.split("=", 1)
        out[k.strip()] = int(v.strip())
    return out


def select_reference(spec, params):
    """The declared reference block for one (M, efConstruction), or None."""
    block = spec.get("reference_curve") or {}
    for cfg in block.get("configurations") or []:
        if all(int(cfg.get(k, -1)) == int(v) for k, v in params.items()
               if k in ("M", "efConstruction")):
            return block, cfg
    return block, None


# --------------------------------------------------------------------------
# recall
# --------------------------------------------------------------------------

def recall_at(pred_ids, gt_ids, k):
    """Mean over queries of |returned top-k INTERSECT true top-k| / k.

    The same definition `verify.recall_at` uses, and the same one
    ANN-Benchmarks' `knn` metric uses, so a number here is comparable to a
    number there without a conversion nobody would remember to apply.
    """
    gt, pred = gt_ids[:, :k], pred_ids[:, :k]
    hits = sum(len(set(p[p >= 0].tolist()) & set(g.tolist()))
               for p, g in zip(pred, gt))
    return hits / (gt.shape[0] * gt.shape[1])


# --------------------------------------------------------------------------
# curve
# --------------------------------------------------------------------------

def run_curve(fixture_id=DEFAULT_FIXTURE, config="M=12,efConstruction=500",
              ef_values=None, k=DEFAULT_K, tolerance=None, fixtures_dir="fixtures",
              append=True, history_path=H.DEFAULT_PATH, outcome_scope=None,
              log_fn=log, deterministic=None, index_cache=True):
    """Sweep efSearch on the simulator and compare to published hnswlib.

    What is being calibrated is `oneground.models.single_node_hnsw` itself --
    the module the simulator actually uses -- not a bespoke faiss call written
    for this check. A calibration that exercised different code from the
    product would calibrate the wrong thing.
    """
    from ..models.single_node_hnsw.model import MODEL
    from ..models.base import Config

    spec, spec_path = load_spec(fixture_id, fixtures_dir)
    params = parse_config(config)

    # Arrays first: a missing corpus is the more fundamental blocker, and its
    # message tells the reader how to produce one.
    vectors, queries, gt = fixture_arrays(fixture_id, fixtures_dir)

    block, ref_cfg = select_reference(spec, params)
    k = int(block.get("k") or k)
    if tolerance is None:
        tolerance = block.get("tolerance")
    if tolerance is None:
        raise CalibrateError(
            f"{spec_path} declares no reference_curve.tolerance, and none was "
            f"passed. A curve without a declared band cannot reach a verdict, "
            f"and picking one here would be choosing the gate after seeing "
            f"the measurement.")
    tolerance = float(tolerance)
    ef_values = [int(e) for e in (ef_values or block.get("ef_values")
                                  or R.ANN_BENCHMARKS_EF_GRID[:7])]

    # The fixture decides whether this comparison may block, because that is a
    # property of what is being compared, not of who is running it. Task 012b
    # set it to advisory here: the curve compares two HNSW implementations
    # that genuinely differ, and gating a release on someone else's
    # implementation is not a gate on this one.
    if outcome_scope is None:
        outcome_scope = str(block.get("outcome_scope") or H.BLOCKING)

    points = {}
    if ref_cfg:
        points = {int(a): (None if b is None else float(b))
                  for a, b in (ref_cfg.get("points") or {}).items()}
    ref_note = (ref_cfg or {}).get("note")

    # The known, one-signed implementation difference, if this fixture has
    # published one. Not a gate: a published observation, like the reference
    # values themselves. Where it exists, each point also reports how far
    # today's offset sits from it.
    known = {}
    if ref_cfg:
        known = {int(a): (None if b is None else float(b))
                 for a, b in (ref_cfg.get("implementation_offset") or {}).items()}

    log_fn(f"fixture {fixture_id}: {vectors.shape[0]} x {vectors.shape[1]}, "
           f"{queries.shape[0]} queries, published ground truth k={gt.shape[1]}")
    if gt[:, :k].max() >= vectors.shape[0]:
        reach = float((gt[:, :k] < vectors.shape[0]).sum(axis=1).mean() / k)
        raise CalibrateError(
            f"the published ground truth indexes vectors this fixture does "
            f"not hold: only {reach:.4f} of a query's true top-{k} is in the "
            f"corpus, so recall@{k} is capped at about that and every point "
            f"of this curve would measure the truncation, not the index. "
            f"Build the fixture without --subset.")

    cfg = Config.make(MODEL.name, {"M": params.get("M", 12),
                                   "efConstruction": params.get(
                                       "efConstruction", 500),
                                   "efSearch": ef_values[0]})
    # A deterministic build over a million vectors takes over an hour on a
    # laptop (measured: 4127 s). Losing it to a failure in the two-minute
    # search that follows -- which is exactly what happened once -- is not
    # acceptable, so the index is cached on disk and reused. The cache key
    # carries everything the graph depends on; anything else changing means a
    # rebuild, which is the safe direction to be wrong in.
    cache = _index_cache_path(fixture_id, params, vectors.shape[0],
                              deterministic)
    built, build_seconds, det = _build_or_load(
        MODEL, vectors, cfg, cache, log_fn, deterministic=deterministic,
        use_cache=index_cache)

    rows, lines = [], []
    engine_version = _faiss_version()
    for ef in ef_values:
        c = Config.make(MODEL.name, {"M": params.get("M", 12),
                                     "efConstruction": params.get(
                                         "efConstruction", 500),
                                     "efSearch": ef})
        t1 = time.time()
        cand = _search_batched(MODEL, built, queries, k, c)
        measured = recall_at(cand.ids, gt, k)
        ref = points.get(ef)
        dev = None if ref is None else measured - ref
        outcome = H.decide(dev, tolerance)
        known_off = known.get(ef)
        residual = (None if (dev is None or known_off is None)
                    else round(dev - known_off, 6))
        rows.append({"efSearch": ef, "measured": measured, "reference": ref,
                     "deviation": dev, "tolerance": tolerance,
                     "outcome": outcome, "known_offset": known_off,
                     "offset_residual": residual,
                     "search_seconds": time.time() - t1})
        log_fn(f"  efSearch {ef:>4}  recall@{k} {measured:.5f}  "
               f"reference {'-' if ref is None else f'{ref:.5f}'}  "
               f"{'-' if dev is None else f'{dev:+.5f}'}  {outcome}"
               + ("" if residual is None
                  else f"  offset residual {residual:+.5f}"))
        lines.append(H.make_line(
            check="glove_curve",
            dataset=fixture_id,
            engine="oneground/single_node_hnsw",
            engine_version=f"faiss-cpu {engine_version}",
            config=c.label,
            measured=measured,
            reference=ref,
            tolerance=tolerance,
            definition="measured - reference; reference is the published "
                       "ANN-Benchmarks hnswlib recall@10 at the same "
                       "(M, efConstruction, efSearch)",
            outcome_scope=outcome_scope,
            source=spec_path,
            note=(None if ref is not None else
                  (ref_note or "no published reference point at this "
                               "configuration")),
            extra={"k": k, "efSearch": int(ef),
                   "reference_algorithm": (block.get("algorithm") or "hnswlib"),
                   "reference_sha256": ((block.get("source") or {})
                                        .get("sha256")),
                   "known_implementation_offset": known_off,
                   "offset_residual": residual,
                   "deterministic_build": det,
                   "build_seconds": (None if build_seconds is None
                                     else round(build_seconds, 3))}))

    if append:
        H.append_all(lines, history_path)
        log_fn(f"appended {len(lines)} line(s) to {history_path}")
    return {"fixture": fixture_id, "config": config, "k": k,
            "tolerance": tolerance, "rows": rows, "lines": lines,
            "deterministic": det, "build_seconds": build_seconds,
            "outcome_scope": outcome_scope}


def _index_cache_path(fixture_id, params, n_base, deterministic):
    """Where a built index is parked, keyed by what the graph depends on."""
    det = "det" if resolve_deterministic(None, deterministic) else "par"
    bits = "-".join(f"{k}{params[k]}" for k in sorted(params))
    return os.path.join(INDEX_CACHE_DIR,
                        f"{fixture_id}-{bits}-n{n_base}-{det}.faiss")


def _build_or_load(model, vectors, cfg, cache_path, log_fn,
                   deterministic=None, use_cache=True):
    """Build the index, or load one an earlier run already paid for.

    Returns (built, build_seconds, deterministic). `build_seconds` is None on
    a cache hit -- a loaded index has no build time of its own, and reporting
    the original run's would be quoting a measurement this run did not make.
    """
    import faiss

    from ..models.base import BuiltIndex

    det = resolve_deterministic(None, deterministic)
    if use_cache and cache_path and os.path.exists(cache_path):
        log_fn(f"index cache hit: {cache_path}")
        idx = faiss.read_index(cache_path)
        built = BuiltIndex(family=model.name, config=cfg,
                           n_base=vectors.shape[0], dim=vectors.shape[1],
                           state={"index": idx, "vectors": vectors,
                                  "deterministic": det},
                           build_seconds=0.0)
        return built, None, det

    log_fn(f"building {cfg.label} over {vectors.shape[0]} vectors "
           f"(this is the slow part)")
    t0 = time.time()
    built = _build_chunked(model, vectors, cfg, log_fn,
                           deterministic=deterministic)
    seconds = time.time() - t0
    det = bool(built.state.get("deterministic"))
    log_fn(f"  built in {seconds:.1f}s  (deterministic={det})")
    if use_cache and cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        faiss.write_index(built.state["index"], cache_path)
        log_fn(f"  index cached at {cache_path}")
    return built, seconds, det


def _search_batched(model, built, queries, k, cfg, batch=BATCH_QUERIES):
    """Search in slices and concatenate.

    faiss will happily take all 10,000 queries at once, and on a laptop whose
    free memory is measured in hundreds of megabytes that is how a run gets
    killed after an hour of building. Batching changes no result: each query
    is independent.
    """
    from ..models.base import Candidates

    ids, scores = [], []
    for i in range(0, len(queries), batch):
        chunk = np.ascontiguousarray(queries[i:i + batch])
        c = model.search(built, chunk, k, cfg)
        ids.append(c.ids)
        scores.append(c.scores)
    return Candidates(ids=np.concatenate(ids),
                      scores=np.concatenate(scores))


def _build_chunked(model, vectors, cfg, log_fn, deterministic=None):
    """The model's own `build`, with the corpus fed in slices.

    Task 012 had a local faiss copy here. It was replaced in 012b: a
    calibration that exercises different code from the product calibrates the
    wrong thing, and the determinism fix lives in the model. `add_chunk` keeps
    a 473 MB memmap from being materialised whole; adds stay sequential, so
    the graph is unchanged by chunking.
    """
    t0 = time.time()
    built = model.build(
        vectors, cfg, seed=0, deterministic=deterministic,
        add_chunk=ADD_CHUNK,
        progress=lambda done, total, secs: log_fn(
            f"    added {done}/{total}  ({secs:.0f}s)"))
    log_fn(f"    built {vectors.shape[0]} vectors in "
           f"{time.time() - t0:.0f}s  "
           f"(deterministic={built.state.get('deterministic')})")
    return built


def _faiss_version():
    try:
        import importlib.metadata as md
        return md.version("faiss-cpu")
    except Exception:                            # pragma: no cover - env
        return "unknown"


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------

def _engine_block(doc, engine):
    """One engine's block out of verify.json or verify_info.json.

    Task 015 made both files hold `engines`, a list, with no engine promoted
    to the top level. Files written before that are a single flat block and
    are read as themselves, so an older workdir still calibrates.
    """
    blocks = doc.get("engines")
    if not isinstance(blocks, list):
        return doc
    for b in blocks:
        if isinstance(b, dict) and b.get("engine") == engine:
            merged = dict(b)
            merged.setdefault("environment_id", doc.get("environment_id"))
            return merged
    raise CalibrateError(
        f"the run measured {[b.get('engine') for b in blocks]}, not "
        f"{engine!r}; there is no block to calibrate against")


def run_engine(requirements, engine="qdrant", workdir=None, append=True,
               history_path=H.DEFAULT_PATH, outcome_scope=H.BLOCKING,
               tolerance=0.05, log_fn=log):
    """Simulator recall@10 minus a real engine's, on the same sample.

    The measurement already exists: `verify` computes
    `calibration_error_recall` and writes it to `verify.json`. This command's
    job is to make it *repeatable and recorded* rather than transcribed by
    hand into the history, which is how the first line got there.

    `ONEGROUND_<ENGINE>_URL` points the run at an engine that is already up,
    so a workdir can be calibrated against an engine nobody has to compose:
    `ONEGROUND_QDRANT_URL`, `ONEGROUND_PGVECTOR_URL`. The variable is chosen
    from the engine being calibrated -- reading the Qdrant variable while
    calibrating pgvector would point one engine's run at another's endpoint,
    and the resulting line would name the wrong engine for the number.
    """
    import json

    from .. import verify as V

    url_var = f"ONEGROUND_{str(engine).upper().replace('-', '_')}_URL"
    url = os.environ.get(url_var)
    manage = url is None
    log_fn(f"engine calibration: {engine}"
           + (f" at {url} (from {url_var})" if url
              else " via the pinned compose file"))

    # Only the engine being calibrated. A requirements file may list several
    # for a comparison run; calibrating one engine must not silently measure
    # and overwrite the others.
    wd = V.run(requirements, up=manage, down=manage, target_override="local",
               endpoint_override=url, engines_override=[engine], log_fn=log_fn)
    workdir = workdir or wd

    with open(os.path.join(workdir, "verify.json"), encoding="utf-8") as f:
        vj = _engine_block(json.load(f), engine)
    with open(os.path.join(workdir, "verify_info.json"), encoding="utf-8") as f:
        vi = _engine_block(json.load(f), engine)

    cal = vj.get("calibration")
    err = vj.get("calibration_error_recall")

    # efSearch on its own field, not only buried in the config label. Task 012
    # measured that efSearch does not mean the same thing across HNSW
    # implementations -- faiss reaches at e what hnswlib reached at ~1.4e-1.9e
    # -- so a calibration point that does not say which efSearch it was taken
    # at cannot be compared to one from another engine. See docs/MODELS.md.
    ep = (vi.get("engine_params") or {})
    ef_search = ep.get("hnsw_ef", ep.get("ef"))
    facts_params = ((vi.get("engine_facts") or {}).get("index_params") or {})
    engine_ef = {"efSearch": (None if ef_search is None else int(ef_search)),
                 "efSearch_source": ("verify_info.engine_params.hnsw_ef"
                                     if ef_search is not None else None),
                 "M": facts_params.get("m", ep.get("m")),
                 "efConstruction": facts_params.get("ef_construct",
                                                    ep.get("ef_construct"))}
    if not isinstance(err, (int, float)) or not cal:
        reason = err if isinstance(err, str) else "verify produced no calibration"
        log_fn(f"  {reason}")
        line = H.make_line(
            check="simulator_vs_engine", dataset=os.path.basename(workdir),
            engine=engine,
            engine_version=str((vi.get("engine_facts") or {}).get("version")
                               or vi.get("engine_version") or "unknown"),
            config=str((cal or {}).get("simulated_config") or "unknown"),
            measured=None, reference=None, tolerance=tolerance,
            definition="simulated recall@10 - measured recall@10",
            outcome_scope=outcome_scope,
            source=os.path.join(workdir, "verify.json"), note=reason,
            extra=engine_ef)
    else:
        # `measured` is this installation's simulator; `reference` is the real
        # engine it is being checked against. deviation = simulated - measured
        # engine recall, which is the pre-012 `calibration_error_recall`
        # unchanged in sign.
        line = H.make_line(
            check="simulator_vs_engine", dataset=os.path.basename(workdir),
            engine=engine,
            engine_version=str((vi.get("engine_facts") or {}).get("version")
                               or vi.get("engine_version") or "unknown"),
            config=str(cal["simulated_config"]),
            measured=float(cal["simulated_recall_at_10"]),
            reference=float(cal["measured_recall_at_10"]),
            tolerance=tolerance,
            definition="simulated recall@10 - measured recall@10 "
                       "(measured=simulator, reference=engine)",
            outcome_scope=outcome_scope,
            source=os.path.join(workdir, "verify.json"),
            extra={**engine_ef, "k": 10})
        log_fn(f"  simulated {line['measured']:.5f} - engine "
               f"{line['reference']:.5f} = {line['deviation']:+.5f}  "
               f"{line['outcome']}  (efSearch {line.get('efSearch')})")

    if append:
        H.append(line, history_path)
        log_fn(f"appended 1 line to {history_path}")
    return {"workdir": workdir, "lines": [line]}


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def _exit_code(lines, strict=False):
    c = H.counts(lines)
    blocking = [ln for ln in lines
                if ln.get("outcome_scope", H.BLOCKING) == H.BLOCKING]
    if any(ln["outcome"] == CONTRADICTED for ln in blocking):
        return 1
    if strict and c[COULDNT_CHECK]:
        return 2
    return 0


def _cmd_fixture(args):
    from . import fixture as F
    spec_path = os.path.join(args.fixtures_dir, f"{args.fixture}.fixture.yaml")
    outdir = F.build(spec_path, args.source, out=args.fixtures_dir,
                     subset=args.subset)
    if not args.skip_characterize:
        F.characterize(outdir, seed=args.seed)
    F.write_fixture_manifest(outdir)
    if args.check_metric:
        agree = F.verify_metric_convention(outdir)
        if agree < 0.99:
            raise CalibrateError(
                f"normalized inner product reproduces only {agree:.4f} of the "
                f"published neighbours. The metric convention does not match "
                f"upstream, so every recall measured on this fixture would be "
                f"wrong in a way no tolerance would catch.")
    return 0


def _cmd_layers(args):
    res = L.run_layers(fixture_id=args.fixture, k=args.k,
                       n_queries=args.queries, fixtures_dir=args.fixtures_dir,
                       append=not args.no_append, history_path=args.history,
                       outcome_scope=(H.ADVISORY if args.advisory
                                      else H.BLOCKING),
                       log_fn=log)
    print()
    print(H.render(res["lines"]))
    return _exit_code(res["lines"], args.strict)


def _cmd_curve(args):
    scope = None
    if args.advisory:
        scope = H.ADVISORY
    elif args.blocking:
        scope = H.BLOCKING
    res = run_curve(fixture_id=args.fixture, config=args.config,
                    ef_values=([int(x) for x in args.ef.split(",")]
                               if args.ef else None),
                    k=args.k, tolerance=args.tolerance,
                    fixtures_dir=args.fixtures_dir,
                    append=not args.no_append,
                    history_path=args.history,
                    outcome_scope=scope,
                    deterministic=(False if args.no_deterministic else None))
    print()
    print(H.render(res["lines"]))
    return _exit_code(res["lines"], args.strict)


def _cmd_engine(args):
    res = run_engine(args.requirements, engine=args.engine,
                     append=not args.no_append, history_path=args.history,
                     tolerance=args.tolerance,
                     outcome_scope=(H.ADVISORY if args.advisory
                                    else H.BLOCKING))
    print()
    print(H.render(res["lines"]))
    return _exit_code(res["lines"], args.strict)


def _cmd_show(args):
    lines = H.read(args.history)
    if args.check:
        lines = [ln for ln in lines if ln.get("check") == args.check]
        if not lines:
            print(f"no lines for check {args.check!r} in {args.history}")
            return 0
    print(H.render(lines))
    # The standing state decides the exit code, not whether a contradiction
    # ever happened: a later line supersedes an earlier one for the same
    # (check, dataset, engine, config).
    return _exit_code(H.latest_by_check(lines).values(), args.strict)


def _cmd_reference(args):
    import json
    with open(args.page, encoding="utf-8", errors="replace") as f:
        html = f.read()
    print(json.dumps(R.describe(html, args.algorithm), indent=2,
                     sort_keys=True))
    return 0


# Subcommands that write something a later report cites: the fixture itself,
# and the three that append to calibration/history.jsonl. `show` and
# `reference` only render, and guarding a renderer would teach people to pass
# --allow-unpinned to read a file.
WRITES_ARTIFACTS = ("fixture", "layers", "curve", "engine")


def build_parser():
    """The `oneground calibrate` parser.

    Split out of `main` so the command surface can enumerate the subcommands
    -- oneground/cli.py's guard-coverage check walks every parser rather than
    a hand-maintained list.
    """
    ap = argparse.ArgumentParser(
        prog="oneground calibrate",
        description="Measure this installation's error against published "
                    "numbers and against real engines, and keep the history.")
    sub = ap.add_subparsers(dest="action", required=True)

    f = sub.add_parser("fixture", help="build the calibration fixture from "
                                       "the ANN-Benchmarks HDF5")
    f.add_argument("--fixture", default=DEFAULT_FIXTURE)
    f.add_argument("--source", required=True, help="path to the .hdf5")
    f.add_argument("--fixtures-dir", default="fixtures")
    f.add_argument("--seed", type=int, default=20260910)
    f.add_argument("--subset", type=int, default=None,
                   help="truncate the train split. NOT the supported "
                        "configuration: the published ground truth indexes "
                        "the full split, so a prefix caps recall at the share "
                        "of it that survives. Kept so that can be re-measured.")
    f.add_argument("--skip-characterize", action="store_true")
    f.add_argument("--check-metric", action="store_true",
                   help="confirm normalized inner product reproduces the "
                        "published neighbour ordering on a query sample")

    la = sub.add_parser("layers", help="the three blocking checks: corpus "
                                       "reachability, metric agreement, "
                                       "recall-rule accounting")
    la.add_argument("--fixture", default=DEFAULT_FIXTURE)
    la.add_argument("--k", type=int, default=DEFAULT_K)
    la.add_argument("--queries", type=int, default=1000,
                    help="how many queries the exact-search pass uses")
    la.add_argument("--fixtures-dir", default="fixtures")
    la.add_argument("--history", default=H.DEFAULT_PATH)
    la.add_argument("--no-append", action="store_true")
    la.add_argument("--advisory", action="store_true",
                    help="record as advisory. These checks are the gate; use "
                         "this only to try something out.")
    la.add_argument("--strict", action="store_true")

    c = sub.add_parser("curve", help="sweep efSearch against the published "
                                     "hnswlib curve (advisory on the glove "
                                     "fixture: see its spec)")
    c.add_argument("--fixture", default=DEFAULT_FIXTURE)
    c.add_argument("--config", default="M=12,efConstruction=500")
    c.add_argument("--ef", default=None, help="comma-separated efSearch values")
    c.add_argument("--k", type=int, default=DEFAULT_K)
    c.add_argument("--tolerance", type=float, default=None)
    c.add_argument("--fixtures-dir", default="fixtures")
    c.add_argument("--history", default=H.DEFAULT_PATH)
    c.add_argument("--no-append", action="store_true")
    c.add_argument("--advisory", action="store_true",
                   help="record the lines as advisory; they are never allowed "
                        "to block. Default for a fixture whose spec says "
                        "outcome_scope: advisory.")
    c.add_argument("--blocking", action="store_true",
                   help="override the fixture's scope and let this comparison "
                        "block. On the glove fixture that means gating a "
                        "release on another project's HNSW implementation.")
    c.add_argument("--no-deterministic", action="store_true",
                   help="build with a parallel faiss add. Faster and NOT "
                        "reproducible; the recall it reports cannot be "
                        "rebuilt. See docs/MODELS.md.")
    c.add_argument("--strict", action="store_true",
                   help="exit 2 when something could not be checked")

    e = sub.add_parser("engine", help="simulator against a real engine")
    e.add_argument("requirements")
    e.add_argument("--engine", default="qdrant")
    e.add_argument("--tolerance", type=float, default=0.05)
    e.add_argument("--history", default=H.DEFAULT_PATH)
    e.add_argument("--no-append", action="store_true")
    e.add_argument("--advisory", action="store_true")
    e.add_argument("--strict", action="store_true")

    s = sub.add_parser("show", help="render calibration/history.jsonl")
    s.add_argument("--history", default=H.DEFAULT_PATH)
    s.add_argument("--check", default=None, help="only this check")
    s.add_argument("--strict", action="store_true")

    r = sub.add_parser("reference", help="what the downloaded ANN-Benchmarks "
                                         "page actually publishes")
    r.add_argument("--page", required=True)
    r.add_argument("--algorithm", default="hnswlib")

    from .. import environment as envmod
    for name, sp in _subparsers(ap):
        if name in WRITES_ARTIFACTS:
            envmod.add_argument(sp)
    return ap


def _subparsers(parser):
    """[(name, parser)] for a parser's subcommands."""
    for action in parser._actions:                     # argparse exposes no
        choices = getattr(action, "choices", None)     # public accessor
        if isinstance(choices, dict):
            return list(choices.items())
    return []


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = build_parser()
    args = ap.parse_args(argv)

    # The four that write are guarded; the two that render are not.
    if args.action in WRITES_ARTIFACTS:
        from .. import environment as envmod
        command = f"oneground calibrate {args.action}"
        envmod.GUARDED_COMMANDS.add(command)
        _stamp, code = envmod.guard_or_exit(
            command, allow_unpinned=getattr(args, "allow_unpinned", False))
        if code:
            return code

    try:
        if args.action == "layers":
            return _cmd_layers(args)
        if args.action == "fixture":
            return _cmd_fixture(args)
        if args.action == "curve":
            return _cmd_curve(args)
        if args.action == "engine":
            return _cmd_engine(args)
        if args.action == "show":
            return _cmd_show(args)
        if args.action == "reference":
            return _cmd_reference(args)
    except CalibrateError as ex:
        print(f"oneground calibrate: {ex}", file=sys.stderr)
        return 3
    return 1
