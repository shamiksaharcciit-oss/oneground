#!/usr/bin/env python3
"""
oneground ground-view export
============================

Produces the small per-point table the hero image (the ground view) is drawn
from, so that rendering runs on a laptop against a few megabytes instead of
against the 460 MB of vectors that live on the pod's volume.

Everything here is *recomputed from the fixture's own artifacts* using the
spec's seeds and the estimator functions imported unmodified from
`build_fixture.py` — this file defines no geometry of its own. If a definition
changes there, it changes here.

    fixtures/<id>/
        ground_view_base.parquet       one row per base vector
        ground_view_queries.parquet    one row per held-out query
        ground_view_centroids.parquet  one row per k-means region

All three are **declared**: derived, illustrative, and recomputable from the
receipts beside them. Their digests are appended to MANIFEST.sha256 and
`fixture_verify.py` classifies them as declared.

2-D placement — read this before drawing conclusions from the picture
--------------------------------------------------------------------
The UMAP fit is NOT re-run, and nothing here is a new projection.

  * Base points use `projection.npy` exactly as built. Row i of the projection
    is base vector i.
  * Queries have no position of their own: a query is placed at the **mean
    2-D position of its 10 true nearest neighbours** taken from
    `ground_truth.npy`. This is an illustrative placement, not a projection of
    the query vector. A query whose true neighbours are spread across the map
    lands in the middle of nowhere, between them, which is an artifact of the
    placement rule and not a property of the query.
  * Centroids are placed at the **mean 2-D position of their members**, with
    the same caveat: a region that UMAP tore in half is drawn at the midpoint
    of the two halves, where none of its members are.

Regions, distances, copy counts and recall are all computed in the full 768-d
space. Only the x/y columns are illustrative.

Usage
-----
    python corpora/export_ground_view.py \\
        --spec fixtures/arxiv-150k.fixture.yaml \\
        --dir fixtures/arxiv-150k/

Requires: pyarrow, plus build_fixture.py's own dependencies.
"""

import argparse
import importlib.util
import io
import json
import os
import sys
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
import zstandard as zstd

# --------------------------------------------------------------------------
# build_fixture.py, imported unmodified. Every estimator below comes from it.
# --------------------------------------------------------------------------
_BF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_fixture.py")
_spec = importlib.util.spec_from_file_location("build_fixture", _BF)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)

# Fixed by the spec's reference configuration; named here so the numbers that
# drive the picture are visible rather than buried in a call.
N_CENTROIDS = 256
EPSILON = 0.20            # closure band, semantic_sharded
MAX_ASSIGN = 4            # copy cap, semantic_sharded
CRISP_RATIO = 1.20        # boundary_crispness definition
AMBIGUOUS_RATIO = 1.10    # ambiguous_query_rate definition
K_RECALL = 10

REQUIRED = ["vectors.npy", "queries.npy", "sample.jsonl.zst",
            "projection.npy", "ground_truth.npy"]

OUT_BASE = "ground_view_base.parquet"
OUT_QUERIES = "ground_view_queries.parquet"
OUT_CENTROIDS = "ground_view_centroids.parquet"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def read_base_records(path, n_expected):
    """The base half of sample.jsonl.zst, in the order vectors.npy was built.

    build_fixture writes every base record first, tagged role=base, then the
    queries; and embeds base_recs in that same order. So the i-th base line
    corresponds to row i of vectors.npy.
    """
    recs = []
    with open(path, "rb") as f:
        reader = zstd.ZstdDecompressor().stream_reader(f)
        for line in io.TextIOWrapper(reader, encoding="utf-8"):
            r = json.loads(line)
            if r.get("role") == "base":
                recs.append(r)
    if len(recs) != n_expected:
        raise SystemExit(f"sample.jsonl.zst holds {len(recs):,} base records, "
                         f"vectors.npy has {n_expected:,} rows")
    return recs


def rewrite_manifest_entries(d, names):
    """Add these digests to MANIFEST.sha256, replacing our own earlier lines.

    bf.append_manifest is append-only, which is right for the builder — it
    writes the projection line once, at the end of a build. This export can be
    re-run over a directory that already has its tables listed, so it drops its
    own lines first; otherwise a second run lists each table twice and the
    manifest stops being a description of the directory.

    Only the names passed in are touched. Every receipt line is left alone.
    """
    path = os.path.join(d, bf.MANIFEST_NAME)
    kept = [line for line in io.open(path, encoding="utf-8").read().splitlines(True)
            if line.strip() and line.partition("  ")[2].strip() not in names]
    io.open(path, "w", encoding="utf-8", newline="\n").writelines(kept)
    for name in names:
        bf.append_manifest(d, name)


def top_level(cat):
    """'cs.LG' -> 'cs', 'astro-ph.GA' -> 'astro-ph', 'hep-th' -> 'hep-th'."""
    return cat.split(".")[0] if cat else None


def published(spec, *path):
    """A published value from the spec, or None when it is still TO_BE_FILLED.

    The smoke fixture's spec is deliberately unfilled (its values are
    synthetic and were never published), so an assertion against it has
    nothing to compare with and is skipped rather than faked.
    """
    node = spec
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            return None
    return node if isinstance(node, (int, float)) else None


def check(label, measured, expected, tol, failures, asserted):
    """Compare a recomputed value against the spec, or record that we can't."""
    if expected is None:
        print(f"  {label:<24} {measured:.4f}   (spec value TO_BE_FILLED - not asserted)")
        return
    asserted.append(label)
    delta = abs(measured - expected)
    ok = delta <= tol
    print(f"  {label:<24} {measured:.4f}   spec {expected}  "
          f"delta {delta:.4f}  tol {tol}  {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append(f"{label}: recomputed {measured:.4f}, spec {expected}, "
                        f"delta {delta:.4f} exceeds tolerance {tol}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--dir", required=True, help="fixtures/<id>/")
    args = ap.parse_args()

    spec = yaml.safe_load(open(args.spec))
    d = args.dir
    missing = [f for f in REQUIRED if not os.path.exists(os.path.join(d, f))]
    if missing:
        raise SystemExit(f"missing required inputs in {d}: {', '.join(missing)}\n"
                         "The large artifacts ship as a release asset; this "
                         "export runs where they live (the pod), not on a clone.")

    t0 = time.time()
    seed = spec["sampling"]["seed"]

    log("loading artifacts")
    base = np.load(os.path.join(d, "vectors.npy"))
    queries = np.load(os.path.join(d, "queries.npy"))
    proj = np.load(os.path.join(d, "projection.npy"))
    gt = np.load(os.path.join(d, "ground_truth.npy"))
    gt10 = gt[:, :K_RECALL]
    if len(proj) != len(base):
        raise SystemExit(f"projection has {len(proj):,} rows, vectors has {len(base):,}")
    log(f"base {len(base):,} x {base.shape[1]}  queries {len(queries):,}  "
        f"projection {proj.shape}")

    recs = read_base_records(os.path.join(d, "sample.jsonl.zst"), len(base))

    # ---- regions, distances, closure copies (all in 768-d) ----
    log(f"k-means {N_CENTROIDS} (seed {seed})")
    cents = bf.kmeans(base, N_CENTROIDS, seed)

    log("assigning base vectors")
    d_base, near_base = bf.centroid_dists(base, cents, MAX_ASSIGN)
    region = near_base[:, 0].astype(np.int32)
    d1, d2 = d_base[:, 0], d_base[:, 1]
    ratio = np.divide(d2, d1, out=np.full_like(d2, np.inf), where=d1 > 0)

    within = d_base <= d_base[:, [0]] * (1 + EPSILON)
    within[:, 0] = True
    copies = within.sum(axis=1).astype(np.int8)

    log("assigning queries")
    d_q, near_q = bf.centroid_dists(queries, cents, 2)
    q_region = near_q[:, 0].astype(np.int32)
    q_d1, q_d2 = d_q[:, 0], d_q[:, 1]
    q_ratio = np.divide(q_d2, q_d1, out=np.full_like(q_d2, np.inf), where=q_d1 > 0)
    ambiguous = q_d2 <= AMBIGUOUS_RATIO * q_d1

    # ---- per-query recall at one-region exact routing ----
    # build_fixture.one_region_exact_recall gives the aggregate only, so the
    # per-query figure is computed here and then checked against it: if the two
    # disagree this export has drifted from the estimator it claims to mirror.
    log("per-query recall at one-region exact routing")
    per_query = one_region_recall_per_query(base, queries, region, q_region, gt10)
    aggregate = bf.one_region_exact_recall(base, queries, cents, gt10)
    if abs(per_query.mean() - aggregate) > 1e-9:
        raise SystemExit(
            f"per-query recall mean {per_query.mean():.9f} disagrees with "
            f"build_fixture.one_region_exact_recall {aggregate:.9f}")
    log(f"per-query mean matches build_fixture aggregate ({aggregate:.6f})")

    # ---- 2-D placement (illustrative; see the header) ----
    log("placing queries and centroids in 2-D")
    q_xy = proj[gt10].mean(axis=1)                       # mean of true 10-NN
    sizes = np.bincount(region, minlength=N_CENTROIDS)
    sums = np.zeros((N_CENTROIDS, 2), dtype=np.float64)
    np.add.at(sums, region, proj.astype(np.float64))
    with np.errstate(invalid="ignore"):
        c_xy = sums / sizes[:, None]                     # NaN for empty regions

    # ---- tables ----
    cats = [bf.primary_category(r["categories"]) for r in recs]
    base_tbl = pa.table({
        "x": pa.array(proj[:, 0], pa.float32()),
        "y": pa.array(proj[:, 1], pa.float32()),
        "region": pa.array(region, pa.int32()),
        "d1": pa.array(d1, pa.float32()),
        "d2": pa.array(d2, pa.float32()),
        "ratio": pa.array(ratio, pa.float32()),
        "copies": pa.array(copies, pa.int8()),
        "top_level_category": pa.array([top_level(c) for c in cats], pa.string()),
        "primary_category": pa.array(cats, pa.string()),
        "update_year": pa.array([bf.year_of(r["update_date"]) for r in recs], pa.int16()),
    })
    queries_tbl = pa.table({
        "x": pa.array(q_xy[:, 0], pa.float32()),
        "y": pa.array(q_xy[:, 1], pa.float32()),
        "region": pa.array(q_region, pa.int32()),
        "ratio": pa.array(q_ratio, pa.float32()),
        "ambiguous": pa.array(ambiguous, pa.bool_()),
        "recall10_one_region": pa.array(per_query, pa.float32()),
    })
    centroids_tbl = pa.table({
        "region": pa.array(np.arange(N_CENTROIDS), pa.int32()),
        "x": pa.array(c_xy[:, 0], pa.float32()),
        "y": pa.array(c_xy[:, 1], pa.float32()),
        "size": pa.array(sizes, pa.int32()),
    })

    for name, tbl in ((OUT_BASE, base_tbl), (OUT_QUERIES, queries_tbl),
                      (OUT_CENTROIDS, centroids_tbl)):
        pq.write_table(tbl, os.path.join(d, name), compression="zstd")
        log(f"wrote {name}  ({tbl.num_rows:,} rows, "
            f"{os.path.getsize(os.path.join(d, name)):,} bytes)")

    # ---- manifest: declared, appended ----
    rewrite_manifest_entries(d, (OUT_BASE, OUT_QUERIES, OUT_CENTROIDS))
    log("three digests in MANIFEST.sha256 (declared)")

    # ---- summary, and the assertions against published values ----
    hist = {n: int((copies == n).sum()) for n in range(1, MAX_ASSIGN + 1)}
    crispness = float((ratio > CRISP_RATIO).mean())
    ambiguity = float(ambiguous.mean())
    mean_recall = float(per_query.mean())
    top10_share = float(np.sort(sizes)[-10:].sum() / len(base))

    print("\n================ ground view summary ================")
    print(f"  base rows              {len(base):,}")
    print(f"  query rows             {len(queries):,}")
    print(f"  centroid rows          {N_CENTROIDS}  "
          f"({int((sizes == 0).sum())} empty)")
    print(f"  copies histogram       " +
          "  ".join(f"{n}:{hist[n]:,} ({hist[n] / len(base):.3f})"
                    for n in range(1, MAX_ASSIGN + 1)))
    print(f"  storage amplification  {copies.sum() / len(base):.3f}x")
    print()
    print("  recomputed vs the spec's published values")

    ch = spec.get("characterization", {})
    failures, asserted = [], []
    check("boundary_crispness", crispness,
          published(spec, "characterization", "boundary_crispness", "value"),
          ch.get("boundary_crispness", {}).get("tolerance", 0.02), failures, asserted)
    check("ambiguous_query_rate", ambiguity,
          published(spec, "characterization", "ambiguous_query_rate", "value"),
          ch.get("ambiguous_query_rate", {}).get("tolerance", 0.02), failures, asserted)
    check("skew_top10_share", top10_share,
          published(spec, "characterization", "skew_top10_share", "value"),
          ch.get("skew_top10_share", {}).get("tolerance", 0.02), failures, asserted)

    # One-region recall has no published field of its own. The spec's drift
    # pair is the same measurement taken against pre-2019 centroids, so it is
    # the only published anchor; the band is those two values widened by the
    # drift tolerance. Centroids fitted to the whole corpus should do at least
    # as well as centroids fitted to its first half, so a value above the band
    # is expected to be reported, not silently accepted.
    before = published(spec, "characterization", "drift", "value_before")
    after = published(spec, "characterization", "drift", "value_after")
    drift_tol = ch.get("drift", {}).get("tolerance", 0.02)
    if before is None or after is None:
        print(f"  {'one_region_recall@10':<24} {mean_recall:.4f}   "
              "(spec drift pair TO_BE_FILLED - not asserted)")
    else:
        asserted.append("one_region_recall@10")
        lo, hi = min(before, after) - drift_tol, max(before, after) + drift_tol
        ok = lo <= mean_recall <= hi
        print(f"  {'one_region_recall@10':<24} {mean_recall:.4f}   "
              f"drift band [{lo:.3f}, {hi:.3f}]  {'OK' if ok else 'FAIL'}")
        if not ok:
            failures.append(
                f"one_region_recall@10: {mean_recall:.4f} outside the band "
                f"[{lo:.3f}, {hi:.3f}] derived from the spec's drift pair "
                f"({before} / {after}) +/- {drift_tol}")

    print(f"\nartifacts written to {d}   ({time.time() - t0:.1f} s)")

    if failures:
        print("\nGROUND VIEW EXPORT FAILED - recomputed geometry disagrees "
              "with the published values:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        raise SystemExit(1)
    if asserted:
        print(f"all {len(asserted)} published values checked reproduced within "
              f"tolerance: {', '.join(asserted)}")
    else:
        print("NOTHING ASSERTED: this spec publishes no values yet (all "
              "TO_BE_FILLED), so the summary above was not checked against "
              "anything. Expected for arxiv-smoke; on arxiv-150k every line "
              "above is asserted.")


def one_region_recall_per_query(base, queries, region, q_region, gt10):
    """recall@10 for each query, searching only its own region, exactly.

    Mirrors build_fixture.one_region_exact_recall, which reports the aggregate
    of the same quantity; main() asserts the two agree.
    """
    import faiss
    from collections import defaultdict

    members = defaultdict(list)
    for i, r in enumerate(region):
        members[int(r)].append(i)

    out = np.zeros(len(queries), dtype=np.float64)
    for qi in range(len(queries)):
        ids = np.asarray(members[int(q_region[qi])], dtype=np.int64)
        if len(ids) == 0:
            continue
        sub = faiss.IndexFlatIP(base.shape[1])
        sub.add(base[ids])
        _, loc = sub.search(queries[qi:qi + 1], min(K_RECALL, len(ids)))
        pred = ids[loc[0]]
        out[qi] = len(set(pred) & set(gt10[qi])) / gt10.shape[1]
    return out


if __name__ == "__main__":
    main()
