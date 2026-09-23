#!/usr/bin/env python3
"""
oneground teaser export (task T1)
=================================

Writes the four files the teaser page reads. Everything here is recomputed
from the fixture's own artifacts using the spec's seeds and the geometry
functions imported unmodified from `corpora/export_ground_view.py` (which in
turn imports them from the package). This file defines no geometry of its own.

    site/teaser/data/
        base.bin            150,000 x (x, y, d1..d4, category, region)
        centroids.json      256 x (x, y, size)
        queries.json        2,000 x (placement, routing, true 10-NN, title)
        values.json         published values, digests, the verdict, receipts
        MANIFEST.sha256     sha256 of each of the four above

Inputs
------
Two directories, because the fixture's large artifacts ship as a release asset
and are not in the clone:

    --assets   vectors.npy, queries.npy, sample.jsonl.zst   (release asset)
    --dir      projection.npy, ground_truth.npy, query_ids.json,
               characterization.json, build_info.json, MANIFEST.sha256,
               ground_view_*.parquet                        (fixtures/arxiv-150k/)
    --spec     fixtures/arxiv-150k.fixture.yaml
    --report   runs/<run>/report.json                       (the verdict)

Every input digest is checked against the fixture MANIFEST before anything is
read, so the page's receipt panel is describing bytes this export actually saw.

base.bin layout
---------------
The brief lists, per base vector: float32 x, y, d1, d2, d3, d4, then uint8
category and uint8 region. The columns are written **in that order but grouped
by column** (struct-of-arrays), not interleaved per record:

    [ x     ] 150000 * float32     offset        0
    [ y     ] 150000 * float32     offset   600000
    [ d1    ] 150000 * float32     offset  1200000
    [ d2    ] 150000 * float32     offset  1800000
    [ d3    ] 150000 * float32     offset  2400000
    [ d4    ] 150000 * float32     offset  3000000
    [ cat   ] 150000 * uint8       offset  3600000
    [ region] 150000 * uint8       offset  3750000
                                   total    3900000 bytes

A 26-byte interleaved record puts every float32 on an odd byte boundary, so a
browser could not take a `Float32Array` view over it and would have to copy
150,000 records out through a `DataView` before the first frame. Grouped by
column, each column is one zero-copy typed-array view. The content and the
column order are exactly as the brief specifies; only the grouping differs.
`values.json:base_bin` carries the layout, so the page reads the offsets from
data rather than hard-coding them.

Distances are **non-squared** Euclidean: `centroid_dists` takes the sqrt of
what faiss returns, because the 1.20 and 1.10 ratio definitions in the spec
mean ratios of actual distances. The closure rule the browser replays is the
one `export_ground_view.py` uses:

    copies(eps) = #{ j in 1..4 : d_j <= d_1 * (1 + eps) }

capped at four because the spec's semantic_sharded reference configuration
caps at four. Four is a property of that configuration, not of the corpus.

Usage
-----
    python corpora/export_teaser_data.py \\
        --spec fixtures/arxiv-150k.fixture.yaml \\
        --dir fixtures/arxiv-150k/ \\
        --assets ~/oneground-assets/arxiv-150k/ \\
        --report runs/arxiv-150k-via-characterize/report.json \\
        --out site/teaser/data/

Requires: pyarrow, faiss, zstandard, pyyaml, numpy (the fixture's own deps).
"""

import argparse
import hashlib
import importlib.util
import io
import json
import os
import platform
import re
import sys
import time

import numpy as np
import yaml

# --------------------------------------------------------------------------
# export_ground_view.py, imported unmodified. It carries the geometry
# constants and the per-query recall function; it in turn imports the
# estimators from the package via build_fixture.py.
# --------------------------------------------------------------------------
_EGV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "export_ground_view.py")
_spec = importlib.util.spec_from_file_location("export_ground_view", _EGV)
egv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(egv)
bf = egv.bf                      # build_fixture, re-exporting oneground.measures

# Task 044e: the shared path transform, not a sixth private copy of it. This
# file already carries one (`public_price_table`, below) written before
# `receipts.public_path` existed; adding a second would be the defect task
# 044h is about. Reached the way `egv` is, because this script runs as a file
# rather than as part of the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from oneground.receipts import public_path                        # noqa: E402

N_CENTROIDS = egv.N_CENTROIDS    # 256
EPSILON = egv.EPSILON            # 0.20, the spec's reference closure band
MAX_ASSIGN = egv.MAX_ASSIGN      # 4, the closure cap
CRISP_RATIO = egv.CRISP_RATIO    # 1.20
AMBIGUOUS_RATIO = egv.AMBIGUOUS_RATIO   # 1.10
K_RECALL = egv.K_RECALL          # 10

N_BASE = 150000
N_QUERIES = 2000
CURATED_N = 12
CURATED_WELL_ROUTED = 3          # of the 12; the rest are worst-recall ambiguous

# Which decision-log entries the verdict panel quotes verbatim. Chosen by
# kind, not by index, so a re-run of the report that reorders the log still
# quotes the same claims (and this export fails loudly if one is gone).
QUOTED_LOG_KINDS = ["scope", "indistinguishable", "recommendation"]

# The fourth quoted entry, first match wins. Before the verify landed the only
# thing to say about latency was that it was unresolved; now that it has been
# measured in a named environment, the sentence carrying the pod id is the one
# worth quoting, and `to_resolve` survives as the fallback for a run that has
# not been verified. Each entry is (kind, substring the text must contain).
FOURTH_LOG_ENTRY = [
    ("meets_environment", "latency_p95"),
    ("to_resolve", None),
]

# The three canonical builds. Digests are read out of the spec's own git
# history (the value `embedding.vectors_sha256` held after each build) and out
# of the finding `digests_are_environment_specific`, which is where the
# "values agree, bytes don't" claim is published. Build 3's row is asserted
# against the live spec below, so this table cannot drift from it silently.
BUILDS = [
    {
        "build": 1,
        "date": "2026-09-08",
        "environment": "RunPod pod template, numpy 2.1.2",
        "device": "NVIDIA GeForce RTX 4090",
        "vectors_sha256": "90ffb2567aba9b8e8ab057391687f61cc3c0958f57b17b617809186d2fe1f573",
        "queries_sha256": "f1b7b0151db515bee5ba1ce7ae54d949b3f1d1b81912848f037285c5327ccfed",
        "drift_before": 0.523,
        "drift_after": 0.549,
        "source": "fixtures/arxiv-150k.fixture.yaml @ 595ce9f",
    },
    {
        "build": 2,
        "date": "2026-09-08",
        "environment": "isolated venv honouring requirements.txt, numpy 2.5.3",
        "device": "NVIDIA GeForce RTX 4090",
        "vectors_sha256": "414e1484d94964df6d5d60e64899347096bf0388f241250cac84184236eb5b4e",
        "queries_sha256": "87718975fe2cc2513abcc28de138a072c8f2d223e09744862b431305626c1b0b",
        "drift_before": 0.524,
        "drift_after": 0.551,
        "source": "fixtures/arxiv-150k.fixture.yaml @ 0ab7567",
    },
    {
        "build": 3,
        "date": "2026-09-09",
        "environment": "same pinned venv, numpy 2.5.3",
        "device": "NVIDIA RTX PRO 4500 Blackwell",
        "vectors_sha256": "cb973a94ba305a9afe81c98bdc05e51ee3b91023281c33997bc5212fe6db5f5f",
        "queries_sha256": "16e0f4882b317bfad531f844230f76ad1ef90e62ac365fbe4b986ab2fdde5ebe",
        "drift_before": 0.522,
        "drift_after": 0.549,
        "source": "fixtures/arxiv-150k.fixture.yaml @ b81b3a1 (current)",
    },
]

# Files whose digests must match the fixture MANIFEST before this export runs.
# vectors.npy / queries.npy / sample.jsonl.zst live in --assets, the rest in
# --dir; the MANIFEST covers all of them.
CHECK_IN_ASSETS = ["sample.jsonl.zst", "vectors.npy", "queries.npy"]
CHECK_IN_DIR = ["projection.npy", "ground_truth.npy", "query_ids.json",
                "characterization.json", "build_info.json",
                "ground_view_base.parquet", "ground_view_queries.parquet",
                "ground_view_centroids.parquet"]

OUT_FILES = ["base.bin", "centroids.json", "queries.json", "values.json"]

MANIFEST_OUT = "MANIFEST.sha256"

# The generated region in site/teaser/app.js that carries the cache-bust
# digests. app.js is source, not an output, so the export edits exactly the
# lines between these two markers and refuses if they are not there.
MARK_START = "// --- generated by corpora/export_teaser_data.py --- do not edit by hand ---"
MARK_END = "// --- end generated ---"

# A fifth output, derived from exactly those four. Chrome and Edge refuse
# fetch() and XMLHttpRequest against file:// URLs, so a page opened by
# double-clicking index.html cannot read its own data directory -- but it can
# still load a <script src="">. INLINE_FILE is the four outputs gzipped,
# base64-encoded and assigned to one global, which app.js pulls in only when
# location.protocol is 'file:'. A hosted visitor never downloads it.
#
# gzip, and not plain base64, because base64 alone would take base.bin from
# 3.9 MB to 5.2 MB and put the file:// load over the brief's 5 MB budget on
# its own. Gzipped first it lands at 4.4 MB.
INLINE_FILE = "inline.js"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(path):
    out = {}
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            digest, _, name = line.partition("  ")
            out[name.strip()] = digest
    return out


def check_inputs(manifest, d, assets):
    """Every input this export reads, digested against the fixture MANIFEST.

    The teaser's receipt panel claims the page was drawn from the published
    canonical bytes. That claim is only worth printing if it was checked here,
    so a mismatch stops the export rather than being reported on the page.
    """
    rows, bad = [], []
    for name, where in ([(n, assets) for n in CHECK_IN_ASSETS] +
                        [(n, d) for n in CHECK_IN_DIR]):
        path = os.path.join(where, name)
        if not os.path.exists(path):
            bad.append(f"{name}: not found at {path}")
            continue
        got = sha256_file(path)
        want = manifest.get(name)
        ok = (want is not None and got == want)
        rows.append({"file": name, "sha256": got, "bytes": os.path.getsize(path),
                     "matches_fixture_manifest": ok})
        mark = "OK " if ok else "MISMATCH"
        print(f"  {mark} {name:<32} {got[:16]}...")
        if not ok:
            bad.append(f"{name}: manifest {want}, file {got}")
    if bad:
        raise SystemExit("input digests do not match the fixture MANIFEST:\n  " +
                         "\n  ".join(bad))
    return rows


def read_records(path):
    """sample.jsonl.zst split into (base_recs, query_recs), in row order.

    `oneground.fixture.build` writes every base record first tagged
    role=base, then every held-out query tagged role=query, and embeds
    base_recs and q_recs in exactly those orders. So the i-th role=base line
    is row i of vectors.npy and the i-th role=query line is row i of
    queries.npy. `main` re-checks the query half against query_ids.json.
    """
    import zstandard as zstd
    base, queries = [], []
    with open(path, "rb") as f:
        reader = zstd.ZstdDecompressor().stream_reader(f)
        for line in io.TextIOWrapper(reader, encoding="utf-8"):
            r = json.loads(line)
            (base if r.get("role") == "base" else queries).append(r)
    return base, queries


def copies_at(d_base, eps):
    """The closure rule of export_ground_view.py, at an arbitrary epsilon.

    within[:, 0] is forced True for the same reason it is there: a vector is
    always stored in its own nearest region, even if d1 is 0 and the ratio is
    undefined.
    """
    within = d_base <= d_base[:, [0]] * (1 + eps)
    within[:, 0] = True
    return within.sum(axis=1)


def round_to(x, n):
    return float(f"{float(x):.{n}g}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", help="fixtures/<id>.fixture.yaml (full export only)")
    ap.add_argument("--dir", help="fixtures/arxiv-150k/ (full export only)")
    ap.add_argument("--assets", help="the release asset directory (full export only)")
    ap.add_argument("--report", help="runs/<run>/report.json; required for a "
                                     "full export and for --report-only, and "
                                     "deliberately NOT used by --cite-only")
    ap.add_argument("--verify", help="runs/<run>/verify.json; defaults to the "
                                     "file beside --report")
    ap.add_argument("--out", required=True, help="site/teaser/data/")
    ap.add_argument("--page-dir", help="the directory holding app.js; "
                                       "defaults to the parent of --out")
    ap.add_argument("--report-only", action="store_true",
                    help="rebuild values.json from --report and --verify and "
                         "leave the geometry alone. The 460 MB of vectors are "
                         "never opened and base.bin, queries.json and "
                         "centroids.json are asserted unchanged.")
    ap.add_argument("--cite-only", action="store_true",
                    help="refresh measured.k_sweep and NOTHING else. Carries "
                         "every other block over and proves it: each is "
                         "digested before and after and the run refuses if "
                         "any moved. Needs no --report, because a citation "
                         "needs no derivation.")
    args = ap.parse_args()

    if args.cite_only:
        return cite_only(args)

    if args.report_only:
        if not args.report:
            raise SystemExit("--report-only rebuilds verdict and verify from "
                             "a report; pass --report. To add a citation "
                             "without rebuilding anything, use --cite-only.")
        return report_only(args)

    if not args.report:
        raise SystemExit("a full export needs --report")
    missing = [f for f in ("spec", "dir", "assets") if not getattr(args, f)]
    if missing:
        raise SystemExit("a full export needs " +
                         ", ".join("--" + m for m in missing) +
                         "; for values.json alone use --report-only")

    t0 = time.time()
    spec = yaml.safe_load(open(args.spec, encoding="utf-8"))
    d, assets, out = args.dir, args.assets, args.out
    os.makedirs(out, exist_ok=True)

    seed = spec["sampling"]["seed"]
    log(f"fixture {spec['fixture']['id']} v{spec['fixture']['version']}  "
        f"seed {seed}  centroids {N_CENTROIDS}  eps {EPSILON}  cap {MAX_ASSIGN}")

    log("checking every input against the fixture MANIFEST")
    manifest = read_manifest(os.path.join(d, "MANIFEST.sha256"))
    input_digests = check_inputs(manifest, d, assets)

    # ---- build 3's published digests must be the ones in the spec ----
    b3 = BUILDS[-1]
    for section, field in (("embedding", "vectors_sha256"),
                           ("queries", "queries_sha256")):
        if spec[section].get(field) != b3[field]:
            raise SystemExit(
                f"BUILDS[build 3].{field} is {b3[field]}, but the spec now "
                f"publishes {spec[section].get(field)}. The receipt table "
                "in this file has drifted from the fixture; fix the table.")
    log("build 3 row agrees with the spec's published digests")

    # ---- load ----
    log("loading artifacts")
    base = np.load(os.path.join(assets, "vectors.npy"))
    queries = np.load(os.path.join(assets, "queries.npy"))
    proj = np.load(os.path.join(d, "projection.npy"))
    gt10 = np.load(os.path.join(d, "ground_truth.npy"))[:, :K_RECALL]
    if base.shape[0] != N_BASE or queries.shape[0] != N_QUERIES:
        raise SystemExit(f"expected {N_BASE} base / {N_QUERIES} query rows, "
                         f"got {base.shape[0]} / {queries.shape[0]}")
    if len(proj) != len(base):
        raise SystemExit(f"projection has {len(proj):,} rows, vectors has "
                         f"{len(base):,}")
    log(f"base {base.shape}  queries {queries.shape}  projection {proj.shape}")

    base_recs, query_recs = read_records(os.path.join(assets, "sample.jsonl.zst"))
    if len(base_recs) != N_BASE or len(query_recs) != N_QUERIES:
        raise SystemExit(f"sample.jsonl.zst holds {len(base_recs):,} base and "
                         f"{len(query_recs):,} query records")
    q_ids = json.load(open(os.path.join(d, "query_ids.json"), encoding="utf-8"))
    if [r["id"] for r in query_recs] != list(q_ids):
        raise SystemExit("the role=query records in sample.jsonl.zst are not in "
                         "query_ids.json order; query titles would be attached "
                         "to the wrong query vectors")
    log("query record order matches query_ids.json")

    # ---- geometry, all in 768-d ----
    log(f"k-means {N_CENTROIDS} (seed {seed})")
    cents = bf.kmeans(base, N_CENTROIDS, seed)

    log(f"assigning base vectors to their {MAX_ASSIGN} nearest centroids")
    d_base, near_base = bf.centroid_dists(base, cents, MAX_ASSIGN)
    region = near_base[:, 0].astype(np.int32)
    d1, d2 = d_base[:, 0], d_base[:, 1]
    ratio = np.divide(d2, d1, out=np.full_like(d2, np.inf), where=d1 > 0)

    log("assigning queries")
    d_q, near_q = bf.centroid_dists(queries, cents, 2)
    q_region, q_region2 = near_q[:, 0].astype(np.int32), near_q[:, 1].astype(np.int32)
    q_ratio = np.divide(d_q[:, 1], d_q[:, 0],
                        out=np.full_like(d_q[:, 1], np.inf), where=d_q[:, 0] > 0)
    ambiguous = d_q[:, 1] <= AMBIGUOUS_RATIO * d_q[:, 0]

    log("per-query recall at one-region exact routing")
    per_query = egv.one_region_recall_per_query(base, queries, region, q_region, gt10)

    # ---- 2-D placement (illustrative; see export_ground_view.py's header) ----
    log("placing queries and centroids in 2-D")
    q_xy = proj[gt10].mean(axis=1)
    sizes = np.bincount(region, minlength=N_CENTROIDS)
    sums = np.zeros((N_CENTROIDS, 2), dtype=np.float64)
    np.add.at(sums, region, proj.astype(np.float64))
    with np.errstate(invalid="ignore"):
        c_xy = sums / sizes[:, None]

    # ---- cross-check against the pod's ground-view tables -----------------
    # Those three parquets were computed by export_ground_view.py on the pod
    # in build 3's environment. This export recomputes the same geometry on
    # the developer's laptop. Comparing them is the fixture's own claim about
    # itself -- values reproduce across environments, bytes do not -- checked
    # rather than asserted.
    log("cross-checking the recomputed geometry against build 3's tables")
    cross = cross_check(d, region, ratio, q_region, q_ratio, ambiguous,
                        per_query, q_xy, c_xy, sizes, d_base)

    # ---- categories ----
    cats = [egv.top_level(bf.primary_category(r["categories"])) for r in base_recs]
    cat_names = sorted({c for c in cats if c})
    if len(cat_names) > 255:
        raise SystemExit(f"{len(cat_names)} top-level categories will not fit "
                         "in the uint8 category column")
    cat_index = {c: i for i, c in enumerate(cat_names)}
    cat_col = np.array([cat_index.get(c, 255) for c in cats], dtype=np.uint8)
    log(f"{len(cat_names)} top-level categories")

    # ---- base.bin --------------------------------------------------------
    log("writing base.bin")
    columns = [("x", proj[:, 0], "float32"), ("y", proj[:, 1], "float32")]
    for j in range(MAX_ASSIGN):
        columns.append((f"d{j + 1}", d_base[:, j], "float32"))
    columns.append(("category", cat_col, "uint8"))
    columns.append(("region", region.astype(np.uint8), "uint8"))

    layout, offset = [], 0
    with open(os.path.join(out, "base.bin"), "wb") as f:
        for name, col, dtype in columns:
            buf = np.ascontiguousarray(col, dtype=dtype)
            if buf.shape != (N_BASE,):
                raise SystemExit(f"column {name} has shape {buf.shape}")
            f.write(buf.tobytes())
            layout.append({"name": name, "dtype": dtype,
                           "offset": offset, "count": N_BASE})
            offset += buf.nbytes
    log(f"base.bin  {offset:,} bytes  ({len(columns)} columns)")

    # region is uint8 and the browser compares it to a routed region id, so
    # the round trip has to be lossless for all 256 regions.
    if region.max() > 255 or region.min() < 0:
        raise SystemExit(f"region ids run {region.min()}..{region.max()}, "
                         "which does not fit the uint8 column")

    # ---- centroids.json ----
    log("writing centroids.json")
    centroids = [{"x": None if not np.isfinite(c_xy[i, 0]) else round_to(c_xy[i, 0], 6),
                  "y": None if not np.isfinite(c_xy[i, 1]) else round_to(c_xy[i, 1], 6),
                  "size": int(sizes[i])} for i in range(N_CENTROIDS)]
    write_json(os.path.join(out, "centroids.json"), centroids)

    # ---- queries.json ----
    log("writing queries.json")
    # A true neighbour that sits inside the routed region is necessarily in
    # that region's exact top 10, because its score already beats every other
    # vector in the corpus. So recall x 10 must equal the count of true
    # neighbours inside the region -- which is the number the page states.
    inside = (region[gt10] == q_region[:, None]).sum(axis=1)
    disagree = int((np.rint(per_query * K_RECALL).astype(int) != inside).sum())
    if disagree:
        raise SystemExit(
            f"{disagree} queries where recall@10 x 10 disagrees with the count "
            "of true neighbours inside the routed region. The page's sentence "
            "'N of 10 true neighbours are outside the region this query routes "
            "to' would not be the same measurement as the recall beside it.")
    log("recall@10 x 10 == true neighbours inside the routed region, all 2,000")

    q_rows = []
    for i in range(N_QUERIES):
        q_rows.append({
            "title": query_recs[i]["title"].replace("\n", " ").strip(),
            "x": round_to(q_xy[i, 0], 6),
            "y": round_to(q_xy[i, 1], 6),
            "region": int(q_region[i]),
            "region2": int(q_region2[i]),
            # d1 == 0 makes the ratio infinite; JSON has no Infinity, and a
            # null here reads as "no second region to be ambiguous about".
            "ratio": (round_to(q_ratio[i], 5) if np.isfinite(q_ratio[i]) else None),
            "ambiguous": bool(ambiguous[i]),
            "nn": [int(v) for v in gt10[i]],
            "recall10_one_region": round_to(per_query[i], 4),
            "outside": int(K_RECALL - inside[i]),
        })

    # The 12 curated queries: the worst-recall ambiguous ones, plus three that
    # route well. Ties broken by index so the picker is the same on every run.
    amb = [i for i in range(N_QUERIES) if ambiguous[i]]
    worst = sorted(amb, key=lambda i: (per_query[i], i))[:CURATED_N - CURATED_WELL_ROUTED]
    best = sorted(range(N_QUERIES), key=lambda i: (-per_query[i], i))[:CURATED_WELL_ROUTED]
    curated = worst + best
    if len(set(curated)) != CURATED_N:
        raise SystemExit("the curated set overlaps; a query is both worst and best")
    write_json(os.path.join(out, "queries.json"),
               {"curated": curated, "queries": q_rows})

    # ---- measured now, on this machine ----
    log("measuring the epsilon sweep")
    hist_at = {}
    for eps in [round(e / 100, 2) for e in range(0, 41)]:
        c = copies_at(d_base, eps)
        hist_at[f"{eps:.2f}"] = {
            "hist": [int((c == n).sum()) for n in range(1, MAX_ASSIGN + 1)],
            "storage_amplification": round_to(c.sum() / N_BASE, 6),
            "copied": int((c > 1).sum()),
            "p99": int(np.percentile(c, 99, method="lower")),
        }
    at20 = hist_at[f"{EPSILON:.2f}"]
    measured = {
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "faiss": __import__("faiss").__version__,
            "note": "the fourth environment: the developer laptop this export ran on",
        },
        "boundary_crispness": round_to(float((ratio > CRISP_RATIO).mean()), 6),
        "ambiguous_query_rate": round_to(float(ambiguous.mean()), 6),
        "skew_top10_share": round_to(float(np.sort(sizes)[-10:].sum() / N_BASE), 6),
        "one_region_recall_at_10": round_to(float(per_query.mean()), 6),
        "storage_amplification_at_eps_0_20": at20["storage_amplification"],
        "copies_histogram_at_eps_0_20": at20["hist"],
        "empty_regions": int((sizes == 0).sum()),
        "eps_sweep": hist_at,
        "cross_check_vs_build3_tables": cross,
        # Task 044e. Cited, not measured here -- see `k_sweep_block`.
        "k_sweep": k_sweep_block(),
    }

    # ---- the published values, asserted ----
    failures = assert_published(spec, measured)

    # ---- the verdict, and the verify run behind it ----
    report = json.load(open(args.report, encoding="utf-8"))
    verdict = build_verdict(report, args.report)
    verify = build_verify(args.report, args.verify)

    # ---- values.json ----
    log("writing values.json")
    characterization = json.load(open(os.path.join(d, "characterization.json"),
                                      encoding="utf-8"))
    build_info = json.load(open(os.path.join(d, "build_info.json"), encoding="utf-8"))
    values = {
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "generated_by": "corpora/export_teaser_data.py",
        "fixture": {
            "id": spec["fixture"]["id"],
            "version": spec["fixture"]["version"],
            "status": spec["fixture"]["status"],
            "spec_path": os.path.relpath(args.spec).replace("\\", "/"),
            "license_notice": " ".join(spec["fixture"]["license_notice"].split()),
            "source": {k: spec["source"][k] for k in
                       ("name", "provider", "snapshot_date", "snapshot_sha256")},
            "embedding": {k: spec["embedding"][k] for k in
                          ("model", "dimension", "normalize", "device",
                           "library", "library_version")},
            "counts": {"base": N_BASE, "queries": N_QUERIES,
                       "centroids": N_CENTROIDS, "k_ground_truth":
                       spec["ground_truth"]["k"]},
        },
        "geometry": {
            "seed": seed,
            "n_centroids": N_CENTROIDS,
            "reference_epsilon": EPSILON,
            "max_assign": MAX_ASSIGN,
            "crisp_ratio": CRISP_RATIO,
            "ambiguous_ratio": AMBIGUOUS_RATIO,
            "k": K_RECALL,
            "distance": "non-squared Euclidean to the centroid",
            "closure_rule": "a vector is copied into region j when d_j <= d_1 * (1 + eps), for the four nearest regions",
            "cap_note": ("Four is the copy cap of the spec's semantic_sharded "
                         "reference configuration, not a property of the corpus. "
                         "base.bin carries four distances because the model "
                         "stores at most four copies."),
        },
        "base_bin": {
            "path": "base.bin",
            "rows": N_BASE,
            "bytes": offset,
            "layout": "struct-of-arrays; each column is contiguous",
            "columns": layout,
        },
        "published": {
            "characterization": spec["characterization"],
            "reference_results": spec["reference_results"],
            "characterization_json": characterization,
            "note": ("Published values are the cross-environment contract. A "
                     "local build reproduces them within tolerance; it does "
                     "not reproduce the bytes."),
        },
        "categories": cat_names,
        "measured": measured,
        "receipt": {
            "build_info": build_info,
            "fixture_manifest": [{"file": k, "sha256": v} for k, v in manifest.items()],
            "input_digests": input_digests,
            "builds": BUILDS,
            "identical_across_builds": [
                {"file": "sample.jsonl.zst", "sha256": spec["sampling"]["sample_sha256"],
                 "source": "fixtures/arxiv-150k.fixture.yaml:sampling.sample_sha256"},
                {"file": "query_ids.json", "sha256": manifest["query_ids.json"],
                 "source": "fixtures/arxiv-150k/MANIFEST.sha256"},
            ],
            "finding": " ".join(
                next(f["note"] for f in spec["findings"]
                     if f["id"] == "digests_are_environment_specific").split()),
            "verify_command": spec["verification"]["command"],
        },
        "findings": [{"id": f["id"], "note": " ".join(f["note"].split())}
                     for f in spec["findings"]],
        "verdict": verdict,
        "verify": verify,
    }
    write_json(os.path.join(out, "values.json"), values)

    # ---- the file:// bundle, derived from the four outputs ----
    log(f"writing {INLINE_FILE} (the file:// path)")
    write_inline(out)

    # ---- MANIFEST ----
    lines = []
    total = 0
    for name in OUT_FILES + [INLINE_FILE]:
        p = os.path.join(out, name)
        lines.append(f"{sha256_file(p)}  {name}\n")
        if name in OUT_FILES:
            total += os.path.getsize(p)
    io.open(os.path.join(out, "MANIFEST.sha256"), "w",
            encoding="utf-8", newline="\n").writelines(lines)

    stamp_page(out, args.page_dir)

    inline_bytes = os.path.getsize(os.path.join(out, INLINE_FILE))
    print("\n================ teaser export summary ================")
    for name in OUT_FILES:
        print(f"  {name:<18} {os.path.getsize(os.path.join(out, name)):>10,} bytes")
    print(f"  {'total (http)':<18} {total:>10,} bytes  ({total / 1e6:.2f} MB)")
    print(f"  {INLINE_FILE:<18} {inline_bytes:>10,} bytes  "
          f"({inline_bytes / 1e6:.2f} MB, the file:// path, not both)")
    print(f"\n  copies at eps {EPSILON}: " + "  ".join(
        f"{n}:{at20['hist'][n - 1]:,} ({at20['hist'][n - 1] / N_BASE:.3f})"
        for n in range(1, MAX_ASSIGN + 1)))
    print(f"  storage amplification  {at20['storage_amplification']:.3f}x")
    print(f"  vectors copied         {at20['copied']:,}")
    print(f"  p99 copies             {at20['p99']}")
    print(f"\nwritten to {out}   ({time.time() - t0:.1f} s)")

    if failures:
        print("\nTEASER EXPORT FAILED - recomputed geometry disagrees with the "
              "published values:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        raise SystemExit(1)


def cross_check(d, region, ratio, q_region, q_ratio, ambiguous, per_query,
                q_xy, c_xy, sizes, d_base):
    """This laptop's recomputation against build 3's ground-view parquets.

    Reported, never asserted to be byte-identical: k-means on a different
    platform and BLAS may land on a different local optimum, and the fixture's
    published claim is about values, not bytes. Any disagreement is measured
    and carried into values.json so the page can be honest about it.
    """
    import pyarrow.parquet as pq
    b = pq.read_table(os.path.join(d, "ground_view_base.parquet")).to_pydict()
    q = pq.read_table(os.path.join(d, "ground_view_queries.parquet")).to_pydict()
    c = pq.read_table(os.path.join(d, "ground_view_centroids.parquet")).to_pydict()

    pod_region = np.asarray(b["region"], dtype=np.int64)
    pod_copies = np.asarray(b["copies"], dtype=np.int64)
    pod_ratio = np.asarray(b["ratio"], dtype=np.float64)
    here_copies = copies_at(d_base, EPSILON)

    # Region ids are labels: the same partition can come out numbered
    # differently. Compare the partition, not the labels, by asking whether
    # two vectors that share a region here shared one there -- via the size
    # multiset and the best label matching.
    out = {
        "note": ("build 3's ground_view_*.parquet were computed on the pod; "
                 "the rows below recompute the same geometry on this laptop"),
        "base_rows": int(len(pod_region)),
        "copies_identical_frac": round_to(float((pod_copies == here_copies).mean()), 6),
        "storage_amplification_pod": round_to(float(pod_copies.mean()), 6),
        "storage_amplification_here": round_to(float(here_copies.mean()), 6),
        "crispness_pod": round_to(float((pod_ratio > CRISP_RATIO).mean()), 6),
        "crispness_here": round_to(float((np.asarray(ratio) > CRISP_RATIO).mean()), 6),
        "region_sizes_multiset_identical":
            bool(np.array_equal(np.sort(np.asarray(c["size"], dtype=np.int64)),
                                np.sort(sizes.astype(np.int64)))),
        "query_ambiguous_identical_frac": round_to(
            float((np.asarray(q["ambiguous"]) == ambiguous).mean()), 6),
        "query_recall_mean_pod": round_to(
            float(np.asarray(q["recall10_one_region"], dtype=np.float64).mean()), 6),
        "query_recall_mean_here": round_to(float(per_query.mean()), 6),
        "query_recall_identical_frac": round_to(float(
            (np.abs(np.asarray(q["recall10_one_region"], dtype=np.float64)
                    - per_query) < 1e-6).mean()), 6),
        "query_xy_max_abs_delta": round_to(float(np.abs(
            np.column_stack([q["x"], q["y"]]).astype(np.float64) - q_xy).max()), 6),
    }
    for k, v in out.items():
        if k != "note":
            print(f"  {k:<38} {v}")
    return out


def assert_published(spec, measured):
    """The recomputed values against the spec's published ones.

    Same shape as export_ground_view.py's check: never a parameter change, a
    reported failure. One-region recall has no published field of its own, so
    the spec's drift pair widened by the drift tolerance is the band, exactly
    as that script does it.
    """
    ch = spec["characterization"]
    ref = spec["reference_results"]["semantic_sharded"]
    checks = [
        ("boundary_crispness", measured["boundary_crispness"],
         ch["boundary_crispness"]["value"], ch["boundary_crispness"]["tolerance"]),
        ("ambiguous_query_rate", measured["ambiguous_query_rate"],
         ch["ambiguous_query_rate"]["value"], ch["ambiguous_query_rate"]["tolerance"]),
        ("skew_top10_share", measured["skew_top10_share"],
         ch["skew_top10_share"]["value"], ch["skew_top10_share"]["tolerance"]),
        ("storage_amplification", measured["storage_amplification_at_eps_0_20"],
         ref["storage_amplification"], ref["tolerance"]),
    ]
    print("\n  recomputed vs the spec's published values")
    failures = []
    for label, got, want, tol in checks:
        delta = abs(got - want)
        ok = delta <= tol
        print(f"  {label:<24} {got:.4f}   spec {want}  delta {delta:.4f}  "
              f"tol {tol}  {'OK' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"{label}: recomputed {got:.4f}, spec {want}, "
                            f"delta {delta:.4f} exceeds tolerance {tol}")

    before, after = ch["drift"]["value_before"], ch["drift"]["value_after"]
    tol = ch["drift"]["tolerance"]
    lo, hi = min(before, after) - tol, max(before, after) + tol
    got = measured["one_region_recall_at_10"]
    ok = lo <= got <= hi
    print(f"  {'one_region_recall@10':<24} {got:.4f}   drift band "
          f"[{lo:.3f}, {hi:.3f}]  {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append(f"one_region_recall@10: {got:.4f} outside the band "
                        f"[{lo:.3f}, {hi:.3f}] derived from the spec's drift "
                        f"pair ({before} / {after}) +/- {tol}")
    return failures


#: The one key `--cite-only` is allowed to change, plus the two stamps that
#: record that a run happened at all.
CITED_KEY = ("measured", "k_sweep")
CITE_ONLY_STAMPS = ("generated_at", "generated_by", "cited_from")


def _block_digests(values):
    """A digest per top-level block, and per `measured` key.

    Canonical JSON so key order cannot make an unchanged block look moved.
    `measured` is opened one level down because that is where the one
    permitted change lives; everything else is whole-block.
    """
    out = {}
    for k, v in values.items():
        if k == CITED_KEY[0] and isinstance(v, dict):
            for mk, mv in v.items():
                out["measured.%s" % mk] = hashlib.sha256(json.dumps(
                    mv, sort_keys=True, ensure_ascii=False,
                    default=str).encode()).hexdigest()
            continue
        out[k] = hashlib.sha256(json.dumps(
            v, sort_keys=True, ensure_ascii=False,
            default=str).encode()).hexdigest()
    return out


def cite_only(args):
    """Refresh `measured.k_sweep` and nothing else.

    **`--report-only` exists for a rebuild; this exists for a carry-over. Do
    not fold them.** They look similar and are opposites: `--report-only`
    takes a `--report` and *re-derives* `verdict` and `verify` from it, and
    this one takes no report and derives nothing at all.

    The distinction is not stylistic. Task 044e needed to add a cited sweep to
    a page whose `verdict` came from a pod run that is **not in this
    repository** -- `environment_id tf8sd2usxbblsm`, measured 2026-09-09 in a
    checkout called `oneground-012`. `--report-only` would have happily
    rebuilt that verdict from whatever report it was handed, replacing a
    pod-measured decision with a laptop-measured one in order to land a
    citation. That is the worst trade available here: a measurement destroyed
    to add a reference to a measurement.

    So a citation needs no derivation, and a mode that rebuilds a measurement
    to add one is the wrong tool.

    **The mode's own acceptance is the before/after digest.** Every block is
    digested before and after and the run refuses if any moved, which makes
    the claim *nothing else changed* checkable rather than asserted -- the
    same shape `--report-only` uses for the three geometry files, applied to
    every block because this mode claims more.

    TWO PERMITTED CHANGES, WITH DIFFERENT JUSTIFICATIONS
    ----------------------------------------------------
    1. **The citation** -- `measured.k_sweep`. The mode's purpose.
    2. **The sanitisation** -- `public_sources` over every block it carries.
       Not a purpose but a **precondition**: `write_json` refuses to publish a
       value shaped like a local path, and the carried `verdict` block holds
       one (`calibration.engine_line.source`, an absolute path through a
       checkout called `oneground-012`). Without this the mode cannot write at
       all.

       No measurement moves. The field becomes `verify.json`, and the block
       still carries `dataset`, `date` and `environment_id`, so the run
       remains fully identified -- **the path was never the identifier**,
       which is the whole basis of the rule that it should not have been
       recorded.

    Every block a sanitisation touched is **named in the output**, so the
    second permission cannot be used quietly. The acceptance still digests
    everything else: the claim is narrowed, not weakened.

    AND NOT A THIRD: carried-over content is not exempt
    ---------------------------------------------------
    The obvious alternative was to let the refusal skip anything this mode
    merely carries rather than creates. **Refused.** It would let a file stay
    publishable precisely because its defect is old, which is the
    repair-on-read loophole inverted -- and repair-on-read is what let a
    machine identifier sit unnoticed in three receipts for ten days. Do not
    reach for it later.
    """
    out = args.out
    t0 = time.time()
    values_path = os.path.join(out, "values.json")
    if not os.path.exists(values_path):
        raise SystemExit("%s does not exist; --cite-only refreshes a citation "
                         "in a file that is already there and has nothing to "
                         "start from. Run a full export first." % values_path)

    untouched_files = ["base.bin", "queries.json", "centroids.json"]
    before_files = {n: sha256_file(os.path.join(out, n))
                    for n in untouched_files}

    prior = json.load(open(values_path, encoding="utf-8"))
    before = _block_digests(prior)

    # Permitted change 2, the precondition: sanitise the blocks being carried,
    # or `write_json` refuses the whole file. Applied before the citation so
    # the citation is not itself exempted from it.
    values = public_sources(dict(prior))
    sanitised = sorted(k for k, d in _block_digests(values).items()
                       if _block_digests(prior).get(k) != d)

    measured = dict(values.get("measured") or {})
    measured[CITED_KEY[1]] = k_sweep_block()
    values["measured"] = measured
    values["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    values["generated_by"] = "corpora/export_teaser_data.py --cite-only"
    values["cited_from"] = {
        "generated_at": prior.get("generated_at"),
        "generated_by": prior.get("generated_by"),
        "note": ("every block but measured.k_sweep was carried over from the "
                 "export named here, byte for byte; nothing was re-derived "
                 "and no report was read"),
    }

    after = _block_digests(values)
    allowed = ({"measured.%s" % CITED_KEY[1]} | set(CITE_ONLY_STAMPS)
               | set(sanitised))
    moved = sorted(k for k in set(before) | set(after)
                   if k not in allowed and before.get(k) != after.get(k))
    if moved:
        raise SystemExit(
            "--cite-only changed a block it must carry over: "
            + ", ".join(moved))

    write_json(values_path, values)
    write_inline(out)
    lines = []
    for name in OUT_FILES + [INLINE_FILE]:
        lines.append("%s  %s\n" % (sha256_file(os.path.join(out, name)), name))
    io.open(os.path.join(out, "MANIFEST.sha256"), "w",
            encoding="utf-8", newline="\n").writelines(lines)
    stamp_page(out, args.page_dir)

    after_files = {n: sha256_file(os.path.join(out, n))
                   for n in untouched_files}
    moved_files = [n for n in untouched_files
                   if before_files[n] != after_files[n]]

    print("\n================ cite-only export ================")
    for k in sorted(before):
        if k in allowed:
            continue
        print("  carried over  %-34s %s..." % (k, before[k][:12]))
    print("  REFRESHED     %-34s %s...   (the citation)"
          % ("measured.k_sweep", after["measured.k_sweep"][:12]))
    for k in sanitised:
        print("  SANITISED     %-34s %s...   (a path made publishable; no "
              "measurement moved)" % (k, after.get(k, "")[:12]))
    for n in untouched_files:
        print("  unchanged     %-34s %s..." % (n, after_files[n][:12]))
    for n in ("values.json", INLINE_FILE, "MANIFEST.sha256"):
        print("  rewritten     %-34s %s...  %s bytes"
              % (n, sha256_file(os.path.join(out, n))[:12],
                 format(os.path.getsize(os.path.join(out, n)), ",")))
    print("  restamped     ../app.js  (cache-bust digests)")
    ks = values["measured"]["k_sweep"]
    print("\n  cited         %s" % ks["source"])
    print("  sha256        %s" % ks["source_sha256"])
    print("  rows          %d, k=%d..%d"
          % (len(ks["rows"]), ks["rows"][0]["k"], ks["rows"][-1]["k"]))
    print("\nwritten to %s   (%.1f s)" % (out, time.time() - t0))

    if moved_files:
        raise SystemExit("--cite-only changed a geometry output: "
                         + ", ".join(moved_files))
    return 0


def report_only(args):
    """Rebuild values.json from report.json and verify.json. Nothing else.

    The geometry costs a k-means over 460 MB of vectors and about a minute; a
    decision that has been re-judged does not need it re-derived. Every block
    of values.json that came from the fixture -- published, measured, receipt,
    geometry, base_bin, categories -- is carried over from the file already on
    disk, and only `verdict` and `verify` are rebuilt.

    `inline.js` is rewritten too. It is not a fifth source: it is the four
    outputs gzipped for the file:// path, and values.json is one of them. Left
    stale it would serve the pre-verify decision to anyone who opened the page
    by double-clicking, so the page would state two different verdicts
    depending on how it was loaded. `verify_teaser_data.py` checks the bundle
    against the four files beside it and fails if this is skipped.

    base.bin, queries.json and centroids.json are digested before and after and
    must be identical; the run stops if any of them moved.
    """
    out = args.out
    t0 = time.time()
    values_path = os.path.join(out, "values.json")
    if not os.path.exists(values_path):
        raise SystemExit(f"{values_path} does not exist; --report-only rebuilds "
                         "it in place and has nothing to start from. Run a full "
                         "export first.")

    untouched = ["base.bin", "queries.json", "centroids.json"]
    before = {n: sha256_file(os.path.join(out, n)) for n in untouched}
    log("digested the three geometry outputs; they must not move")

    prior = json.load(open(values_path, encoding="utf-8"))
    report = json.load(open(args.report, encoding="utf-8"))

    values = dict(prior)
    values["verdict"] = build_verdict(report, args.report)
    values["verify"] = build_verify(args.report, args.verify)

    # Task 044e. `k_sweep` is a CITATION, so it can be refreshed here without
    # re-deriving anything: report-only carries `measured` over untouched
    # because the geometry costs a k-means over 460 MB, and reading a file
    # and its digest costs neither. This is the difference a cited receipt
    # makes -- the page's newest number can land without the export having to
    # re-measure the corpus to justify it.
    measured = dict(values.get("measured") or {})
    measured["k_sweep"] = k_sweep_block()
    values["measured"] = measured
    values["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    values["generated_by"] = "corpora/export_teaser_data.py --report-only"
    # Carry the FULL export's stamp forward, do not take the previous run's.
    # This field names the export the geometry came from; setting it to
    # `prior.generated_at` made it chase -- after one report-only run it named
    # that run, and after two it named the one before, so the field stopped
    # naming a full export at all. Found in task 044i by exporting twice and
    # diffing: it was one of only two fields that moved with no data change.
    prior_geo = prior.get("geometry_from") or {}
    values["geometry_from"] = {
        "generated_at": prior_geo.get("generated_at")
                        or prior.get("generated_at"),
        "generated_by": prior_geo.get("generated_by")
                        or prior.get("generated_by"),
        "note": ("every block but verdict and verify was carried over from the "
                 "full export named here; the geometry was not re-derived"),
    }
    write_json(values_path, values)
    log(f"values.json rewritten  ({os.path.getsize(values_path):,} bytes)")

    log(f"writing {INLINE_FILE} (values.json is one of the four it carries)")
    write_inline(out)

    lines = []
    for name in OUT_FILES + [INLINE_FILE]:
        lines.append(f"{sha256_file(os.path.join(out, name))}  {name}\n")
    io.open(os.path.join(out, "MANIFEST.sha256"), "w",
            encoding="utf-8", newline="\n").writelines(lines)

    stamp_page(out, args.page_dir)

    after = {n: sha256_file(os.path.join(out, n)) for n in untouched}
    moved = [n for n in untouched if before[n] != after[n]]

    print("\n================ report-only export ================")
    for n in untouched:
        print(f"  unchanged  {n:<16}  {after[n][:16]}...")
    for n in ("values.json", INLINE_FILE, "MANIFEST.sha256"):
        print(f"  rewritten  {n:<16}  {sha256_file(os.path.join(out, n))[:16]}..."
              f"  {os.path.getsize(os.path.join(out, n)):>10,} bytes")
    print("  restamped  ../app.js       (cache-bust digests)")
    v = values["verdict"]
    print(f"\n  summary          {v['summary']}")
    print(f"  recommendation   {v['recommendation']}")
    print(f"  quoted log kinds {[e['kind'] for e in v['decision_log_quoted']]}")
    print(f"\nwritten to {out}   ({time.time() - t0:.1f} s)")

    if moved:
        raise SystemExit(
            "--report-only changed a geometry output, which it must never do: "
            + ", ".join(f"{n} {before[n][:12]}... -> {after[n][:12]}..."
                        for n in moved))
    return 0


def build_verify(report_path, verify_path):
    """The verify run behind the decision, for the page to show.

    Everything here is copied out of verify.json (a receipt: measurements) and
    verify_info.json (declared: what the engine reported about itself). Nothing
    is recomputed and nothing is rounded -- the page does its own formatting,
    so the numbers it prints and the numbers here are the same numbers.
    """
    run_dir = os.path.dirname(os.path.abspath(report_path))
    vp = verify_path or os.path.join(run_dir, "verify.json")
    ip = os.path.join(os.path.dirname(os.path.abspath(vp)), "verify_info.json")
    for path in (vp, ip):
        if not os.path.exists(path):
            raise SystemExit(
                f"{path} not found. The page states a verified decision, so the "
                "verify receipt has to sit beside the report it came from; pass "
                "--verify explicitly if it lives elsewhere.")
    v = json.load(open(vp, encoding="utf-8"))
    info = json.load(open(ip, encoding="utf-8"))
    report = json.load(open(report_path, encoding="utf-8"))

    # A latency number is only meaningful with the machine it was taken on.
    # If these two disagree the page would hang a measurement on the wrong pod.
    if v.get("environment_id") != report["environment"].get("environment_id"):
        raise SystemExit(
            f"verify.json names environment {v.get('environment_id')} and "
            f"report.json names {report['environment'].get('environment_id')}; "
            "the page would attribute a measurement to the wrong machine.")

    # TASK 015 MADE VERIFY MULTI-ENGINE AND THIS FUNCTION NEVER LEARNED
    # ------------------------------------------------------------------
    # A two-engine verify carries `engines`, a LIST, each entry holding the
    # single-engine shape this function was written for. Handed one, it died
    # on `v["searches"]` -- so **re-exporting the page has been impossible
    # since 015, and nothing noticed because nothing tried.** That is why a
    # stale verdict survived thirteen days: not an omission, an impossibility.
    #
    # Ruled (044i): the panel shows BOTH engines, named, each with its outcome
    # and its reason. Showing one is a true number that reads as something
    # else -- qdrant alone reads unmeasurable, pgvector alone reads far too
    # slow, and the truth is that two engines were measured sequentially on
    # one host and neither produced a verdict, for two different reasons. A
    # couldn't-check and a fail are different results and collapsing them
    # loses the only distinction worth having.
    if isinstance(v.get("engines"), list):
        return _verify_multi(v, info, report, vp, ip)

    seq = v["searches"]["k=10"]
    seq_lat = seq["latency_measured_but_not_attributable"]
    loaded = v["searches"]["k=10_under_load"]
    loaded_lat = loaded["latency_shape_single_client"]
    load = v["load"]
    facts = info.get("engine_facts", {})

    return {
        "source": os.path.relpath(vp).replace("\\", "/"),
        "info_source": os.path.relpath(ip).replace("\\", "/"),
        "kind": info.get("kind"),
        "run_at": info["run_at"],
        "date": info["run_at"][:10],
        "target": info["target"],
        "platform": info["platform"],
        "environment_id": v["environment_id"],
        "engine": v["engine"],
        "engine_version": v["engine_version"],
        "namespace": facts.get("namespace"),
        "index_type": facts.get("index_type"),
        "index_params": facts.get("index_params"),
        "metric": facts.get("metric"),
        "shards": facts.get("shards"),
        "replicas": facts.get("replicas"),
        "n_base": v["n_base"],
        "n_queries": v["n_queries"],
        "dimension": v["dimension"],
        "elapsed_seconds": v["elapsed_seconds"],
        "recall_at_10_measured": seq["recall_at_10"],
        # public_sources: this block is copied from verify.json and carries
        # `engine_line.source`, the field that reached the published page as
        # an absolute path and was redacted by hand. Task 044e.
        "calibration": public_sources(
            dict(v["calibration"],
                 error_recall=v["calibration_error_recall"])),
        "ingest": {k: v["ingest"][k] for k in
                   ("n_vectors", "batches", "seconds", "vectors_per_second")},
        "index": v["index"],
        "latency": {
            "rtt_baseline": v["rtt_baseline_ms"],
            "sequential": {
                "p50_ms": seq_lat["p50_ms"],
                "p95_ms": seq_lat["p95_ms"],
                "p99_ms": seq_lat["p99_ms"],
                "n_queries": seq_lat["n_queries"],
                "concurrency": seq_lat["concurrency"],
                "rtt_share_of_p95": seq["rtt_share_of_p95"],
                "outcome": seq["latency_shape_single_client"],
            },
            "under_load": {
                "p50_ms": loaded_lat["p50_ms"],
                "p95_ms": loaded_lat["p95_ms"],
                "p99_ms": loaded_lat["p99_ms"],
                "max_ms": loaded_lat["max_ms"],
                "mean_ms": loaded_lat["mean_ms"],
                "n_queries": loaded_lat["n_queries"],
                "concurrency": loaded_lat["concurrency"],
                "rtt_share_of_p95": loaded["rtt_share_of_p95"],
                "recall_at_10": loaded["recall_at_10"],
            },
            "note": load["note"],
        },
        "qps": {
            "target": load["target_qps"],
            "achieved": load["achieved_qps"],
            "completed": load["completed"],
            # target x duration: what the run was offered. Derived once here so
            # the page states the number rather than doing arithmetic of its own.
            "offered": int(round(load["target_qps"] * load["duration_seconds"])),
            "offered_basis": "target_qps x duration_seconds",
            "concurrency": load["concurrency"],
            "duration_seconds": load["duration_seconds"],
            "warmup_seconds_excluded": load["warmup_seconds_excluded"],
            "errors": load["errors"],
            "error_rate": load["error_rate"],
        },
    }


# The repository root, for turning absolute paths back into the repo-relative
# ones every other source field on the page uses.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


#: The measured sweep this page cites. **A file with a digest, not a
#: computation.** Task 044e's ruling: a sweep recomputed at export time would
#: be a second derivation of a published number, and the whole point of the
#: lab's rule -- *a number on the page has a receipt in the data the page
#: ships* -- is that the page's number is answerable to a receipt. So the
#: export cites this file and records its sha256; it does not re-derive it.
#:
#: Produced by task 044c on the published arXiv vectors, whose array digests
#: were checked against `fixtures/arxiv-150k.fixture.yaml` before the sweep
#: ran. Its k=256 row reproduces every published value to the last digit,
#: which is what makes the other rows comparable to the published one.
K_SWEEP_SOURCE = os.path.join(REPO_ROOT, "tasks",
                              "044c-centroid-count.sweep",
                              "arxiv-150k.default.json")

#: The three measures the caption and the panel read. Everything else in the
#: sweep file stays in the sweep file: the page ships what it uses.
K_SWEEP_MEASURES = ("boundary_crispness", "ambiguous_query_rate",
                    "skew_top10_share")


def k_sweep_block(path=K_SWEEP_SOURCE):
    """The centroid sweep, cited from its file, for `measured.k_sweep`.

    Task 044e. Core refused a typed `0.053` in the epsilon caption because it
    would have been the first number on the page the page could not check --
    the caption's own argument turned on the caption, since its whole purpose
    is to stop a figure travelling without what it depends on. This is what
    lets the caption **read** the number instead of stating it.

    Carries its source and that source's digest, so the page's number is
    traceable to a file in the repository rather than to this export run.
    """
    with io.open(path, encoding="utf-8") as f:
        doc = json.load(f)
    rows = [r for r in doc["rows"] if r.get("arm") == "default"]
    if not rows:
        raise SystemExit("%s has no default-arm rows" % path)
    return {
        # public_path: this is a receipt field and the export is a write site.
        "source": public_path(path),
        "source_sha256": sha256_file(path),
        "fixture": doc["fixture"],
        "seed": doc["seed"],
        "n_base": doc["n_base"],
        "n_queries": doc["n_queries"],
        "arm": "default",
        "measured_by": "task 044c",
        "constants": doc.get("constants", {}),
        "rows": [
            dict([("k", r["k"])]
                 + [(m, round_to(r[m], 6)) for m in K_SWEEP_MEASURES])
            for r in sorted(rows, key=lambda r: r["k"])],
        "note": (
            "boundary_crispness, ambiguous_query_rate and skew_top10_share "
            "measured at each centroid count on this fixture's own published "
            "vectors, seed and embedding -- everything held but k. The k=256 "
            "row is the published one and reproduces it to the last digit, "
            "which is what makes the others comparable to it. Cited from the "
            "file named in `source`, not recomputed by this export: a second "
            "derivation of a published number is not a receipt for it."),
    }


#: Keys whose value is a path, wherever they sit in a copied block.
PATH_KEYS = ("source", "path")


def public_sources(obj):
    """A block copied from a receipt, with its path fields made publishable.

    A **walker over** `receipts.public_path`, not another implementation of
    it: the transform is the shared one and this only decides where to apply
    it. `build_verdict` copies `verify.json`'s calibration block wholesale,
    and that block carries `engine_line.source` -- an absolute path through
    somebody's checkout, which reached the published `values.json` and was
    redacted by hand afterwards. Task 044e: redaction is the hand that does
    not scale, because it must be applied every time and only has to be
    forgotten once.
    """
    if isinstance(obj, dict):
        return {k: (public_path(v) if _needs_sanitising(k, v)
                    else public_sources(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [public_sources(v) for v in obj]
    return obj


def _needs_sanitising(key, value):
    """Only what the refusal would reject. **Keyed on the value, not the name.**

    The first version transformed every field called `source` or `path`, and
    `verdict.price_table.source` is a *sentence* -- "Public list prices, EU
    regions, ... no egress." `public_path` resolved it as a relative path
    inside the repo and `relpath` normalised away its trailing full stop,
    because `.` is a path component. **A sanitiser keyed on a field's name
    silently rewrote prose**, which is core's finding: the check was doing
    more than refusing paths.

    Tying it to `LOCAL_PATH` makes the two agree by construction -- exactly
    what would otherwise be refused is transformed, and nothing else can be.
    A value the refusal would accept is left alone whatever it is called.
    """
    return (key in PATH_KEYS and isinstance(value, str) and bool(value)
            and bool(LOCAL_PATH.search(value)))


def public_price_table(table):
    """The price table, with the machine it was read on taken out of it.

    `price_table.path` is where `prices.example.yaml` happened to sit on the
    machine that ran `oneground report` -- an absolute path through somebody's
    home directory. It reaches this page, and a published page has no business
    naming a developer's filesystem. The useful half of the field is *which*
    price table, so it becomes the repo-relative path, which is the shape every
    other source string on this page already has.

    A path outside the repository is reduced to its basename: still says which
    file, still says nothing about where it lives. `path_note` records that the
    field was rewritten, so the page never claims this is what report.json
    said.
    """
    if not table:
        return table
    out = dict(table)
    raw = out.get("path")
    if not raw:
        return out
    native = raw.replace("\\", os.sep).replace("/", os.sep)
    try:
        inside = os.path.commonpath([os.path.abspath(native), REPO_ROOT]) == REPO_ROOT
    except ValueError:          # different drives on Windows
        inside = False
    out["path"] = (os.path.relpath(native, REPO_ROOT).replace(os.sep, "/")
                   if inside else os.path.basename(native))
    out["path_note"] = ("rewritten by the teaser export: report.json records an "
                        "absolute path on the machine that produced it")
    return out


#: The run this page showed until task 044i, kept visible on it.
#:
#: **Why it is here at all.** Between 2026-09-09 and 2026-09-20 the lab page
#: and the oneproof.dev home page disagreed about the same fixture, one click
#: apart: the lab recommended a configuration and the home page recommended
#: nothing. Neither number was false. They were two runs, and **nothing on
#: either page said so** -- which is the failure this product exists to
#: prevent, occurring on our own page.
#:
#: Deleting the older run would have made the pages agree and taught a reader
#: nothing. Both are true measurements and the difference between them is the
#: finding: a single run at the margin is not a verdict.
SUPERSEDED_RUN = {
    "run": "tf8sd2usxbblsm",
    "date": "2026-09-09",
    "said": "single_node_hnsw[M=32,efConstruction=200,efSearch=128] meets",
    "latency_p95_ms": 38.216508,
    "threshold_ms": 40.0,
    "report": ("fixtures/arxiv-150k/report/"
               "superseded-2026-09-09-tf8sd2usxbblsm.report.json"),
    # THE DATES WERE WRONG HERE, ON THE NOTE WHOSE SUBJECT IS EXACTNESS.
    # The first version said the page "showed a different verdict until
    # 2026-09-20" -- it showed it until the copy landed, and 20 September is
    # when our report was BUILT. It said "re-measured on 2026-09-20" -- the
    # measurement was 2026-09-13 (verify_info.json, 17:09:13Z).
    #
    # Both are the same conflation as `geometry_from`'s chase, three
    # declarations above: **when something was measured against when a record
    # of it was made.** Made twice in one task, the second time in prose.
    #
    # Core's wording is kept because it cannot go stale: naming the re-export
    # rather than a date means the sentence is true whatever day the deploy
    # lands, so the note never has to know one.
    "measured_on": "2026-09-13",
    "report_built_on": "2026-09-20",
    "note": (
        "Until the page was re-exported from the report of 2026-09-20, it "
        "showed a different verdict. On 2026-09-09 a single verify run "
        "measured p95 latency at 38.22 ms against a 40.0 ms threshold and the "
        "configuration met it -- by 1.8 ms, on one run. Measured again on "
        "2026-09-13 on the same fixture and the same configuration (the "
        "report from that run was built on 2026-09-20), pgvector fails it in "
        "all three runs (316.87, 317.41 and 332.23 ms) and qdrant cannot be "
        "judged at all, because the baseline round-trip was 60% of the query "
        "p95 and the number would have measured the network more than the "
        "engine. "
        "**That earlier run is not the basis of this verdict and its verify "
        "receipt no longer exists** -- it was never committed, so only its "
        "report survives, and it is linked above. It is shown because a "
        "measurement that met a threshold by 1.8 ms on one run is not a "
        "result that later turned out to be wrong; it is a result that was "
        "never separable from its margin, and a page that quietly replaced it "
        "would be hiding the most useful thing on it."),
}


def _engine_outcomes(report, verified_config=None):
    """Per-engine latency outcomes, read from the report rather than derived.

    The report already judged each engine and wrote down why. Re-deriving it
    here would be a second judgement that could disagree with the one the rest
    of the page shows, so this copies.
    """
    # The configuration the verify run actually built, named by the run
    # itself. Without this the first option wins, and on this report that is
    # `hash_sharded`, whose every engine row says "this configuration was not
    # the one verified" -- true, and not what the verify panel is about.
    seen, out = set(), []
    options = report.get("options", [])
    if verified_config:
        options = ([o for o in options if o.get("config") == verified_config]
                   or options)
    for opt in options:
        for c in (opt.get("judgement") or {}).get("constraints", []):
            eng = c.get("engine")
            if not eng or eng in seen:
                continue
            if c.get("constraint") != "latency_p95":
                continue
            seen.add(eng)
            out.append({
                "engine": eng,
                "outcome": c.get("outcome"),
                "reason": c.get("reason"),
                "constraint": c.get("constraint"),
                "config": opt.get("config"),
                "source": "report.json:options[].judgement.constraints[]",
            })
    return sorted(out, key=lambda e: e["engine"])


def _latency_or_why(shape):
    """A latency block that always has the same type, never a union.

    `verify.json` writes numbers when latency could be attributed and a
    **string** saying why when it could not -- qdrant's under-load entry on
    this run is `"couldnt_check: environment noise -- the baseline RTT p95
    (4.62 ms) is 60% of the query p95 ..."`. That is the right thing to have
    recorded and the wrong thing to hand a renderer, which would have to test
    the type of a field to know whether it can read `p95_ms` from it.

    So both become an object and the page reads one key to know which it has.
    **This is the distinction the panel exists to show** -- one engine has
    numbers and one has a reason, and flattening them to "no data" would lose
    exactly what a couldn't-check is for.
    """
    if isinstance(shape, dict):
        return dict(shape, outcome="measured")
    if shape is None:
        return None
    return {"outcome": "couldnt_check", "why": str(shape)}


def _verify_multi(v, info, report, vp, ip):
    """A two-engine verify, with both engines named and neither chosen.

    **The page must render every entry of `engines`.** A renderer that shows
    `engines[0]` reproduces the defect this replaced: one true number standing
    where two belong. `outcomes` is the minimum a page has to show -- one line
    per engine with its verdict and the sentence explaining it -- and
    `engines` carries the detail for anything that wants more.
    """
    # `engine_facts` sits inside each entry of verify_info["engines"] in the
    # two-engine shape, not in a top-level map keyed by engine.
    facts_by_engine = {e.get("engine"): (e.get("engine_facts") or {})
                       for e in (info.get("engines") or [])}
    verified = ((v["engines"][0].get("calibration") or {})
                .get("simulated_config") if v.get("engines") else None)
    engines = []
    for e in v["engines"]:
        name = e.get("engine")
        facts = facts_by_engine.get(name) or {}
        searches = e.get("searches") or {}
        seq = searches.get("k=10") or {}
        loaded = searches.get("k=10_under_load") or {}
        engines.append({
            "engine": name,
            "engine_version": e.get("engine_version"),
            "environment_id": e.get("environment_id"),
            "endpoint_kind": e.get("mode"),
            "index_type": facts.get("index_type"),
            "index_params": facts.get("index_params"),
            "metric": facts.get("metric"),
            "n_base": e.get("n_base"),
            "n_queries": e.get("n_queries"),
            "elapsed_seconds": e.get("elapsed_seconds"),
            "recall_at_10_measured": seq.get("recall_at_10"),
            "calibration": public_sources(
                dict(e.get("calibration") or {},
                     error_recall=e.get("calibration_error_recall"))),
            "ingest": e.get("ingest"),
            "index": e.get("index"),
            "rtt_baseline": e.get("rtt_baseline_ms"),
            "sequential": _latency_or_why(
                seq.get("latency_shape_single_client")),
            "sequential_rtt_share_of_p95": seq.get("rtt_share_of_p95"),
            "under_load": _latency_or_why(
                loaded.get("latency_shape_single_client")),
            "under_load_rtt_share_of_p95": loaded.get("rtt_share_of_p95"),
            "load": e.get("load"),
            "qps_max": e.get("qps_max"),
        })

    return {
        "schema_engines": v.get("schema_engines"),
        "source": public_path(vp),
        "info_source": public_path(ip),
        "kind": info.get("kind"),
        "run_at": info["run_at"],
        "date": info["run_at"][:10],
        "target": info["target"],
        "platform": info["platform"],
        "environment_id": v["environment_id"],
        "elapsed_seconds": v.get("elapsed_seconds"),
        "sequential": v.get("sequential", True),
        "sequential_note": v.get("sequential_note"),
        "engines_measured": v.get("engines_measured"),
        # The minimum a page must show, one line per engine.
        "verified_config": verified,
        "outcomes": _engine_outcomes(report, verified),
        "engines": engines,
        "note": (
            "Two engines were measured sequentially on one host: neither ran "
            "while the other was running, so neither number carries the "
            "other's contention -- and neither says anything about how either "
            "behaves while the other runs. Every engine here is shown; none "
            "is the page's choice."),
    }


def build_verdict(report, report_path):
    """Task 010's decision, copied out of report.json without re-deriving it.

    Nothing is recomputed here and nothing is rounded: every option keeps its
    per-constraint outcome, value, threshold and source field, because the
    page shows the source beside every verdict cell.
    """
    log_entries = report["decision_log"]
    quoted = []
    for kind in QUOTED_LOG_KINDS:
        hits = [e for e in log_entries if e["kind"] == kind]
        if not hits:
            raise SystemExit(
                f"report.json has no decision_log entry of kind '{kind}'. The "
                "verdict panel quotes four entries by kind; the report has "
                "changed shape and the panel would quote something else.")
        quoted.append(hits[0])

    # The fourth, first match wins: the sentence naming the environment a
    # latency verdict was reached in, and `to_resolve` for a run with no
    # verify behind it. Still four or nothing.
    for kind, needle in FOURTH_LOG_ENTRY:
        hits = [e for e in log_entries if e["kind"] == kind
                and (needle is None or needle in e["text"])]
        if hits:
            quoted.append(hits[0])
            break
    else:
        raise SystemExit(
            "report.json has no decision_log entry matching any of " +
            ", ".join(f"{k}" + (f" containing '{n}'" if n else "")
                      for k, n in FOURTH_LOG_ENTRY) +
            ". The verdict panel quotes four entries and will not quote three.")

    families = {}
    for o in report["options"]:
        families.setdefault(o["family"], []).append({
            "config": o["config"],
            "params": o["params"],
            "outcome": o["judgement"]["outcome"],
            "indistinguishable_from": o["judgement"]["indistinguishable_from"],
            "constraints": o["judgement"]["constraints"],
            "measurement": {k: o["measurement"][k] for k in
                            ("recall_at_10", "storage_amplification",
                             "stored_vectors", "p99_copies_per_vector",
                             "est_memory_bytes") if k in o["measurement"]},
        })

    recommended, runner_up = None, None
    by_config = {o["config"]: o for o in report["options"]}
    rec = report.get("recommendation")
    if rec:
        if rec not in by_config:
            raise SystemExit(
                f"report.json recommends {rec}, which is not one of its own "
                "options; the page would name a configuration that was never "
                "judged.")
        o = by_config[rec]
        recommended = {
            "config": o["config"],
            "family": o["family"],
            "params": o["params"],
            "outcome": o["judgement"]["outcome"],
            "constraints": o["judgement"]["constraints"],
            "measurement": o["measurement"],
            # The budget verdict travels with its cost and its error band, and
            # with the fact that the verdict was taken on the upper bound. A
            # cost with no band is a guess wearing a number's clothes.
            "cost": dict(report.get("costs", {}).get(o["config"], {}),
                         budget=report["constraints"].get("monthly_budget"),
                         source=f"report.json:costs[{o['config']}]"),
        }
        # The option this one could not be separated from on recall. It is the
        # runner-up precisely because the separation happened elsewhere, so it
        # carries the constraints that could not be checked for it.
        others = o["judgement"].get("indistinguishable_from") or []
        if others and others[0] in by_config:
            r = by_config[others[0]]
            runner_up = {
                "config": r["config"],
                "family": r["family"],
                "outcome": r["judgement"]["outcome"],
                "couldnt_check": [
                    {"constraint": c["constraint"], "reason": c["reason"],
                     "source": c["source"]}
                    for c in r["judgement"]["constraints"]
                    if c["outcome"] == "couldnt_check"],
                "measurement": {k: r["measurement"][k] for k in
                                ("recall_at_10", "storage_amplification")
                                if k in r["measurement"]},
            }

    return {
        "run": report["run"],
        "generated_at": report["generated_at"],
        "source": public_path(report_path),
        "schema": report["schema"],
        # Task 044i. The run this page used to show, kept visible rather than
        # deleted: a page that silently replaces one decision with another
        # teaches a reader that decisions are opinions.
        "superseded": SUPERSEDED_RUN,
        "constraints": report["constraints"],
        "summary": report["summary"],
        "recommendation": report["recommendation"],
        "calibration": report["calibration"],
        "environment": report["environment"],
        "families": [{"family": f, "options": opts} for f, opts in families.items()],
        "recommended": recommended,
        "runner_up": runner_up,
        "price_table": public_price_table(report.get("price_table")),
        "decision_log_quoted": quoted,
        "decision_log_total": len(report["decision_log"]),
    }


def stamp_page(out, page_dir=None):
    """Write the data digests into app.js, so the URLs change when they do.

    app.js carries a generated one-line map of filename -> first 8 hex of that
    file's sha256, read straight out of the MANIFEST this export just wrote.
    The page appends it as ?v= to each data URL. Keeping the token in the code
    rather than in the data is what lets the four files still be fetched in
    parallel: there is no manifest to fetch first in order to learn it.

    Refuses if the markers are gone rather than silently leaving the page
    pinned to digests that no longer exist.
    """
    page_dir = page_dir or os.path.dirname(os.path.abspath(out.rstrip("/\\")))
    app = os.path.join(page_dir, "app.js")
    if not os.path.exists(app):
        raise SystemExit(f"{app} not found; --page-dir should point at the "
                         "directory holding app.js")

    manifest = read_manifest(os.path.join(out, MANIFEST_OUT))
    version = {name: digest[:8] for name, digest in manifest.items()}

    src = io.open(app, encoding="utf-8").read()
    start = src.find(MARK_START)
    end = src.find(MARK_END)
    if start < 0 or end < 0 or end < start:
        raise SystemExit(
            f"{app} has no generated cache-bust block. The markers\n"
            f"  {MARK_START}\n  {MARK_END}\n"
            "are what this export writes between; without them the page would "
            "keep serving whatever digests it was last stamped with.")

    body = (MARK_START + "\nconst DATA_VERSION = " +
            json.dumps(version, sort_keys=True) + ";\n")
    io.open(app, "w", encoding="utf-8", newline="\n").write(
        src[:start] + body + src[end:])
    log(f"stamped app.js with {len(version)} data digests")
    return version


def _stable_gzip(raw):
    """gzip bytes that depend on the input and nothing else.

    **`gzip.compress` writes the current time into the header**, so every
    export produced a different `inline.js` even when not one byte of data had
    changed. That is the precise situation in which a digest stops meaning
    what it is for: `data/MANIFEST.sha256` recorded a new digest, the page's
    `?v=` cache-bust changed, and `check_hosted.py` would have reported drift
    -- all of it saying *the data changed* when the data had not. A digest
    that moves on its own is worse than no digest, because it is believed.

    This has been true of every export this project has ever sent, which is
    why core saw `inline.js` move in changes that touched nothing near it.

    `mtime=0` removes the only non-deterministic input. Compression level and
    the OS byte are already fixed by the library.
    """
    import gzip
    import io as _io
    buf = _io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9,
                       mtime=0) as f:
        f.write(raw)
    return buf.getvalue()


def write_inline(out):
    """The four outputs, gzipped and base64-encoded into one script.

    Carries each source file's sha256 alongside its payload so the page can
    say which bytes it is showing, and so `verify_teaser_data.py` can check
    that the bundle really is the four files beside it and not a stale copy.
    """
    import base64
    import gzip

    payload = {}
    for name in OUT_FILES:
        raw = open(os.path.join(out, name), "rb").read()
        payload[name] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "gzip_b64": base64.b64encode(_stable_gzip(raw)).decode("ascii"),
        }
    body = ("/* Generated by corpora/export_teaser_data.py. Do not edit.\n"
            "   The four files in this directory, gzipped and base64'd, for the\n"
            "   file:// path only -- Chrome and Edge will not fetch() a file:// URL,\n"
            "   but they will load a script. app.js reads this only when\n"
            "   location.protocol === 'file:'. */\n"
            "window.__ONEGROUND_TEASER__ = " +
            json.dumps({"format": "gzip+base64", "files": payload},
                       separators=(",", ":")) + ";\n")
    io.open(os.path.join(out, INLINE_FILE), "w",
            encoding="utf-8", newline="\n").write(body)


#: A string shaped like somebody's filesystem. Task 044g's runtime refusal,
#: arriving at the publishing boundary where core asked for it -- and this is
#: the right place for it, because `write_json` below is the one writer in
#: this project that bypasses `receipts.write_json_stable`, and the file it
#: writes is the only one that is actually published.
#:
#: Wider than the receipt matcher in one way -- it catches `~/...`, which a
#: receipt never holds but a hand-edited page datum might -- and narrower in
#: none. Deliberately not matching a bare relative path (`runs/x/verify.json`
#: is the correct form) or a lone username, which is
#: `test_no_tracked_file_carries_a_machine_identifier`'s subject.
LOCAL_PATH = re.compile(
    r"(^|[\s\"'=(\[])("
    r"[A-Za-z]:\\"                      # C:\ -- a drive letter and backslash
    r"|[A-Za-z]:/"                      # C:/ -- the same thing, posix-slashed
    r"|\\\\[^\\/\s]+\\"                 # \\server\share
    r"|/(?:home|Users|root|workspace)/"  # unix homes, and the pod
    r"|~[/\\]"                          # ~/ or ~\
    r")")


def local_paths_in(obj, at=()):
    """Every string in a payload shaped like a local path, with its key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from local_paths_in(v, at + (str(k),))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from local_paths_in(v, at + ("[%d]" % i,))
    elif isinstance(obj, str):
        m = LOCAL_PATH.search(obj)
        if m:
            yield ".".join(at), obj, m.group(2)


def refuse_local_paths(path, obj):
    """Raise if this payload would publish somebody's filesystem.

    **Refuses; does not repair.** `public_price_table` in this same file
    repairs one such field on read, and task 044e measured what that bought:
    a machine identifier sat in three receipts for ten days *because it was
    being repaired*, so nothing ever surfaced. A silent repair on a
    publishing path removes the symptom and leaves the writer wrong.
    """
    found = list(local_paths_in(obj))
    if not found:
        return
    lines = "\n".join("    %s\n        %s" % (k, v[:160])
                      for k, v, _f in found[:5])
    more = "\n    ... and %d more" % (len(found) - 5) if len(found) > 5 else ""
    raise SystemExit(
        "refusing to write %s: %d value(s) are shaped like a local path, and "
        "this file is published.\n%s%s\n\n"
        "  Not repaired on purpose: a page datum quietly corrected on the way "
        "out leaves the exporter wrong and tells nobody.\n"
        "  Pass the value through oneground.receipts.public_path() where the "
        "field is built."
        % (path, len(found), lines, more))


def write_json(path, obj):
    # allow_nan=False on purpose: Python would happily write Infinity and NaN,
    # which JSON.parse rejects, and the page would fail at load rather than
    # here where the offending field can be named.
    #
    # The refusal goes here and not at the callers: this is the choke point
    # every published JSON passes through, and a check at a caller protects
    # that caller only. Same argument as receipts.write_json_stable, at the
    # boundary that actually publishes.
    refuse_local_paths(path, obj)
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"),
                   sort_keys=False, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
