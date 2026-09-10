"""Fixture builder: spec in, artifacts out.

Consumes a fixture spec and produces every artifact it describes,
deterministically from the seeds in the spec:

    fixtures/<id>/
        sample.jsonl.zst        sampled records (base + held-out queries, tagged)
        vectors.npy             base vectors, float32, L2-normalized
        queries.npy             query vectors (title-only), float32, normalized
        query_ids.json          source ids of the held-out queries
        ground_truth.npy        exact k-NN ids, (n_queries, k)
        characterization.json   published values only (receipt: stable bytes)
        build_info.json         timestamp, versions, host, device (declared)
        projection.npy          2-D UMAP of the base vectors (illustrative)
        MANIFEST.sha256         digest of every file above

At the end it prints every TO_BE_FILLED value from the spec so they can be
pasted into the YAML. It never edits the YAML itself.

Task 007 moved this out of `corpora/build_fixture.py` into the package, with
the orchestration **unchanged**: same call order, same seeds, same writes, in
the same sequence. The measures, receipts, sampling and embedding it calls now
live in `oneground.measures`, `oneground.receipts`, `oneground.sample` and
`oneground.embed`, but each function moved with its logic intact. The proof is
that the smoke fixture's six receipt artifacts rebuild byte-identically across
the move; if any byte had moved, the refactor changed something.

Source data
-----------
The canonical source is the arXiv metadata snapshot
(arxiv-metadata-oai-snapshot.json, one JSON object per line), CC0, from
https://www.kaggle.com/datasets/Cornell-University/arxiv . The file's sha256 is
recorded as the `source.snapshot_sha256` declared value.
"""

import json
import os
import platform
import time
import traceback

import numpy as np
import yaml

from ..embed import embed, load_model
from ..measures import (centroid_dists, drift_pair, kmeans, two_nn_lid)
from ..measures.ambiguity import ambiguous_query_rate
from ..measures.crispness import boundary_crispness
from ..measures.skew import skew_top10_share
from ..receipts import (append_manifest, library_versions, round_floats,
                        sha256_array, sha256_file, write_json_stable,
                        write_manifest)
from ..sample.arxiv import sample_records, split_queries
from ..truth import exact_knn
from .reference import ref_semantic_sharded, ref_single_node

# Everything re-derivable from the spec's seeds. The projection is deliberately
# absent: it is declared, illustrative, and produced after this list is written,
# so that a projection failure cannot leave the receipts unmanifested.
RECEIPT_ARTIFACTS = ["sample.jsonl.zst", "vectors.npy", "queries.npy",
                     "query_ids.json", "ground_truth.npy",
                     "characterization.json", "build_info.json"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def fmt_dur(sec):
    if sec < 90:
        return f"{sec:.1f} s"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def characterize(base, queries, base_recs, q_recs, gt, spec):
    """The five measures, in the order and with the seeds the spec fixes.

    Order is load-bearing: faiss k-means consumes the seed, so moving the
    drift block above the main k-means would change the centroids and every
    value derived from them.
    """
    out = {}
    log("characterize: TwoNN LID")
    out["intrinsic_dimensionality"] = two_nn_lid(base, spec["sampling"]["seed"])

    log("characterize: k-means 256")
    cents = kmeans(base, 256, spec["sampling"]["seed"])
    d_b, r_b = centroid_dists(base, cents, 2)
    d_q, _ = centroid_dists(queries, cents, 2)
    out["boundary_crispness"] = boundary_crispness(d_b)
    out["ambiguous_query_rate"] = ambiguous_query_rate(d_q)
    out["skew_top10_share"] = skew_top10_share(r_b[:, 0], len(base))

    log("characterize: drift pair (centroids trained pre-2019)")
    cutoff = "2019-01-01"
    pre_mask = np.array([r["update_date"] < cutoff for r in base_recs])
    gt10 = gt[:, :10]
    q_pre = np.array([r["update_date"] < cutoff for r in q_recs])
    out.update(drift_pair(base, queries, pre_mask, q_pre, gt10,
                          spec["sampling"]["seed"]))
    return out, cents


def project(base, p):
    try:
        import umap
    except ImportError:
        log("umap-learn not installed; skipping projection")
        return None
    red = umap.UMAP(n_neighbors=p["n_neighbors"], min_dist=p["min_dist"],
                    metric=p["metric"], random_state=p["seed"], n_components=2)
    return red.fit_transform(base).astype(np.float32)


def build(spec_path, source, out="fixtures", skip_projection=False):
    """Build one fixture. Returns the output directory."""
    spec = yaml.safe_load(open(spec_path))
    fx = spec["fixture"]
    outdir = os.path.join(out, fx["id"])
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()

    n_base = spec["sampling"]["target_size"]
    n_q = spec["queries"]["count"]

    # ---- source receipt ----
    log("hashing source snapshot")
    src_sha = sha256_file(source)

    # ---- sample + split ----
    records = sample_records(source, spec, n_base + n_q,
                             spec["sampling"]["seed"], log=log)
    base_recs, q_recs, hot_cats = split_queries(records, n_q,
                                                spec["queries"]["seed"])
    log(f"base {len(base_recs):,} · queries {len(q_recs):,} · "
        f"hot categories {len(hot_cats)}")

    import zstandard as zstd
    sample_path = os.path.join(outdir, "sample.jsonl.zst")
    with open(sample_path, "wb") as f, \
            zstd.ZstdCompressor(level=10).stream_writer(f) as w:
        for r in base_recs:
            w.write((json.dumps({**r, "role": "base"}) + "\n").encode())
        for r in q_recs:
            w.write((json.dumps({**r, "role": "query"}) + "\n").encode())
    json.dump([r["id"] for r in q_recs],
              open(os.path.join(outdir, "query_ids.json"), "w"))

    # ---- embed ----
    emb = spec["embedding"]
    model, weights_sha = load_model(emb["model"], device=emb.get("device", "cpu"),
                                    max_seq_length=emb.get("max_seq_length", 512),
                                    log=log)
    tmpl = spec["sampling"]["text_template"]
    t_emb = time.time()
    log("embedding base (title + abstract)")
    base = embed(model, [tmpl.format(**r) for r in base_recs], emb["batch_size"])
    log("embedding queries (title only)")
    queries = embed(model, [r["title"] for r in q_recs], emb["batch_size"])
    log(f"embedding done in {fmt_dur(time.time() - t_emb)} "
        f"({len(base_recs) + len(q_recs):,} texts)")
    np.save(os.path.join(outdir, "vectors.npy"), base)
    np.save(os.path.join(outdir, "queries.npy"), queries)

    # ---- ground truth ----
    log("exact ground truth")
    gt = exact_knn(base, queries, spec["ground_truth"]["k"])
    np.save(os.path.join(outdir, "ground_truth.npy"), gt)
    gt10 = gt[:, :10]

    # ---- characterization ----
    ch, cents = characterize(base, queries, base_recs, q_recs, gt, spec)

    # ---- reference results ----
    log("reference: single-node HNSW")
    rs = spec["reference_results"]
    ref_single = ref_single_node(base, queries, gt10,
                                 rs["single_node_hnsw"]["params"])
    log("reference: semantic-sharded")
    ref_sem = ref_semantic_sharded(base, queries, gt10, cents,
                                   rs["semantic_sharded"]["params"])

    # ---- characterization.json (receipt) ----
    # Measurement only. Nothing here may vary between two builds from the same
    # seeds: no timestamp, no library versions, no host information. Those live
    # in build_info.json, which is declared and exempt from reproduction.
    versions, torch_info = library_versions(log=log)
    charj = {
        "fixture": fx["id"], "version": fx["version"],
        "characterization": ch,
        "reference_results": {"single_node_hnsw": {"recall_at_10": ref_single},
                              "semantic_sharded": ref_sem},
        "hot_categories": hot_cats,
    }
    write_json_stable(os.path.join(outdir, "characterization.json"),
                      round_floats(charj))

    # ---- build_info.json (declared) ----
    build_info = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "library_versions": versions,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "device": emb.get("device", "cpu"),
        # Kept as explicit nulls on a CPU build rather than omitted, so the
        # shape of build_info.json does not change between a CPU and a GPU
        # build and the two stay diffable.
        "torch_cuda": torch_info["torch_cuda"],
        "cuda_device_name": torch_info["cuda_device_name"],
        "source_snapshot_sha256": src_sha,
    }
    write_json_stable(os.path.join(outdir, "build_info.json"), build_info)

    # ---- manifest, covering every artifact that exists at this point ----
    # Written BEFORE the projection on purpose. Everything above is a receipt;
    # from here the fixture is complete and verifiable, and nothing the
    # projection does can take that away.
    listed = write_manifest(outdir, RECEIPT_ARTIFACTS)
    log(f"manifest written, {len(listed)} artifacts - "
        f"fixture is verifiable from here")

    # ---- print the values to paste into the YAML ----
    # Printed here, before the projection, so that a kill during UMAP (an OOM
    # is a SIGKILL and cannot be caught) cannot take these values with it.
    # Every one of them is derived from artifacts already written above.
    print("\n================ TO_BE_FILLED values ================")
    print(f"source.snapshot_sha256:               {src_sha}")
    print(f"sampling.sample_sha256:               {sha256_file(sample_path)}")
    print(f"embedding.weights_sha256:             {weights_sha}")
    print(f"embedding.library_version:            "
          f"{versions.get('sentence-transformers')}")
    print(f"embedding.vectors_sha256:             {sha256_array(base)}")
    print(f"queries.queries_sha256:               {sha256_array(queries)}")
    print(f"ground_truth.ground_truth_sha256:     {sha256_array(gt)}")
    print(f"characterization.intrinsic_dimensionality.value: "
          f"{ch['intrinsic_dimensionality']:.2f}")
    print(f"characterization.boundary_crispness.value:       "
          f"{ch['boundary_crispness']:.3f}")
    print(f"characterization.ambiguous_query_rate.value:     "
          f"{ch['ambiguous_query_rate']:.3f}")
    print(f"characterization.skew_top10_share.value:         "
          f"{ch['skew_top10_share']:.3f}")
    print(f"characterization.drift.value_before:             "
          f"{ch['drift_before']:.3f}  (n={ch['drift_n_before']})")
    print(f"characterization.drift.value_after:              "
          f"{ch['drift_after']:.3f}  (n={ch['drift_n_after']})")
    print(f"reference_results.single_node_hnsw.recall_at_10: {ref_single:.3f}")
    for k, v in ref_sem.items():
        print(f"reference_results.semantic_sharded.{k}: "
              f"{v if isinstance(v, int) else round(v, 3)}")
    print(flush=True)

    # ---- projection (declared, illustrative, must not sink the build) ----
    # UMAP over the full corpus has the least predictable runtime and memory of
    # any step here, and it runs last for that reason. On success its digest is
    # appended to the manifest; on failure the fixture stands without it.
    if skip_projection:
        log("projection skipped (--skip-projection)")
    else:
        log("UMAP projection")
        t_proj = time.time()
        try:
            proj = project(base, spec["projection"]["params"])
            if proj is None:
                # project() returns None when umap-learn is not installed; it
                # has already said so. Record it rather than leaving the
                # artifact's absence unexplained.
                log(f"projection unavailable after {fmt_dur(time.time() - t_proj)}")
                build_info["projection"] = "unavailable"
                write_json_stable(os.path.join(outdir, "build_info.json"),
                                  build_info)
                write_manifest(outdir, RECEIPT_ARTIFACTS)  # build_info changed
            else:
                np.save(os.path.join(outdir, "projection.npy"), proj)
                append_manifest(outdir, "projection.npy")
                log(f"projection done in {fmt_dur(time.time() - t_proj)}")
        except Exception:
            traceback.print_exc()
            print(f"PROJECTION FAILED - fixture is complete without it "
                  f"(after {fmt_dur(time.time() - t_proj)})", flush=True)
            build_info["projection"] = "failed"
            write_json_stable(os.path.join(outdir, "build_info.json"), build_info)
            # build_info.json changed, so its manifest line must be reissued.
            write_manifest(outdir, RECEIPT_ARTIFACTS)

    print(f"\nartifacts written to {outdir}   ({(time.time() - t0) / 60:.1f} min)")
    return outdir
