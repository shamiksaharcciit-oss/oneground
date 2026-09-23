"""Build the GloVe calibration fixture from the ANN-Benchmarks HDF5.

Why this fixture is built differently from arxiv-150k
-----------------------------------------------------
Every other fixture in this repo is a *receipt*: we sample, we embed, we
compute exact k-NN ourselves, and a rebuild from the same seeds must produce
the same bytes. This one is deliberately not that. Its whole purpose is to
carry someone else's published numbers, so its ground truth is **declared**:
the bytes come from ANN-Benchmarks and we do not recompute them. Recomputing
would silently replace the thing we are trying to check ourselves against.

The corpus is the FULL train split
----------------------------------
The published `neighbors` array indexes into the full 1,183,514-vector train
split. Task 012 measured what happens if only a prefix is indexed:

    fraction of published GT neighbours with index < 100,000   0.084673
    queries whose entire published top-10 lies below 100,000   0.000000
    mean count of a query's top-10 below 100,000               0.8617 / 10

So a 100k prefix caps recall@10 at about 0.086 against this ground truth, and
every point of a reference curve would read ~0.086 regardless of the index.
That is not a corpus, it is a truncation artifact. The fixture therefore holds
the whole train split, and `subset` exists only so the arithmetic above can be
re-run by anyone who doubts it.

Metric
------
ANN-Benchmarks calls this dataset `angular`; the raw vectors are not
normalized (norms run 2.17 to 11.40). Ranking by cosine similarity is the same
ordering as ranking by inner product on unit vectors, so the fixture stores
L2-normalized vectors and every consumer uses `METRIC_INNER_PRODUCT`. The
published `neighbors` ordering is preserved by that change of representation,
which `verify_metric_convention()` checks on a query sample rather than
assuming.
"""

import os
import platform
import time

import numpy as np

from ..receipts import (MANIFEST_NAME, library_versions, producing_version,
                        sha256_file,
                        write_json_stable, write_manifest)

from ..provenance import invocation
CHUNK = 50_000

ARTIFACTS = ["vectors.npy", "queries.npy", "ground_truth.npy",
             "ground_truth_distances.npy",
             "characterization.json", "build_info.json"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _normalize_inplace(a):
    n = np.linalg.norm(a, axis=1, keepdims=True)
    zero = (n[:, 0] == 0)
    if zero.any():
        raise ValueError(f"{int(zero.sum())} zero-norm vectors: cosine "
                         f"ordering is undefined for them, so this source "
                         f"cannot be used as an angular fixture")
    a /= n
    return a


def build(spec_path, source_path, out="fixtures", subset=None, log_fn=log):
    """Write the fixture artifacts from the downloaded HDF5.

    `subset` truncates the train split. It is not the supported configuration
    (see the module docstring), and build_info.json records it so a fixture
    built with one can never be mistaken for the real thing.
    """
    import h5py
    import yaml

    with open(spec_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    fid = spec["fixture"]["id"]
    outdir = os.path.join(out, fid)
    os.makedirs(outdir, exist_ok=True)

    log_fn(f"source: {source_path}")
    src_digest = sha256_file(source_path)
    log_fn(f"  sha256 {src_digest}")
    declared = spec["source"].get("source_sha256")
    if declared and declared != "TO_BE_FILLED" and declared != src_digest:
        raise ValueError(
            f"source digest does not match the spec: spec says {declared}, "
            f"the file on disk is {src_digest}. The published values in this "
            f"fixture were measured against the spec's bytes; refusing to "
            f"build a fixture that quietly swaps the corpus underneath them.")

    with h5py.File(source_path, "r") as f:
        n_train_full = f["train"].shape[0]
        dim = f["train"].shape[1]
        n = n_train_full if subset is None else min(int(subset), n_train_full)
        log_fn(f"train: {n_train_full} x {dim}"
               + ("" if subset is None else f"  -> subset {n}"))

        # Chunked through a memmap so a 473 MB array is never held twice.
        vp = os.path.join(outdir, "vectors.npy")
        vec = np.lib.format.open_memmap(vp, mode="w+", dtype=np.float32,
                                        shape=(n, dim))
        for i in range(0, n, CHUNK):
            j = min(i + CHUNK, n)
            vec[i:j] = _normalize_inplace(
                np.asarray(f["train"][i:j], dtype=np.float32))
            if (i // CHUNK) % 5 == 0:
                log_fn(f"  normalized {j}/{n}")
        vec.flush()
        del vec

        q = _normalize_inplace(np.asarray(f["test"][:], dtype=np.float32))
        np.save(os.path.join(outdir, "queries.npy"), q)
        gt = np.asarray(f["neighbors"][:], dtype=np.int64)
        np.save(os.path.join(outdir, "ground_truth.npy"), gt)
        # The published distances too, kept because the recall-rule check
        # needs them: ANN-Benchmarks' `knn` metric is distance-based, and
        # bounding how far it can diverge from an id-based intersection means
        # knowing where the k-th and (k+1)-th true distances coincide.
        gtd = np.asarray(f["distances"][:], dtype=np.float32)
        np.save(os.path.join(outdir, "ground_truth_distances.npy"), gtd)
        log_fn(f"queries: {q.shape}   ground truth: {gt.shape} (declared)"
               f"   distances: {gtd.shape} (declared)")

    # The truncation arithmetic, recomputed every build rather than quoted.
    inside = float((gt[:, :10] < n).all(axis=1).mean())
    reach = float((gt[:, :10] < n).sum(axis=1).mean() / 10.0)
    log_fn(f"published top-10 fully inside the indexed corpus: {inside:.6f}")
    log_fn(f"mean reachable share of a query's top-10:          {reach:.6f}")
    if reach < 0.999:
        log_fn("  WARNING: this corpus cannot reach its own published ground "
               "truth; recall is capped at the share above.")

    from ..environment import environment_id as _environment_id
    versions, torch_info = library_versions(log=log_fn)
    write_json_stable(os.path.join(outdir, "build_info.json"), {
        "fixture": fid,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Not platform.node(): a hostname identifies a machine and a person.
        "environment": _environment_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "libraries": versions,
        "oneground": producing_version(),     # task 033
        # Which command wrote this, for the replay rule (task 046,
        # docs/INTERFACE.md section 2). Beside the version rather than
        # inside it: it is not a fact about the version.
        "invocation": invocation(),
        "torch": torch_info,
        "source_sha256": src_digest,
        "n_base": int(n),
        "n_train_full": int(n_train_full),
        "subset": None if subset is None else int(subset),
        "dim": int(dim),
        "ground_truth_kind": "declared",
        "published_top10_fully_reachable": inside,
        "mean_reachable_share_of_top10": reach,
    })
    return outdir


def characterize(outdir, seed, log_fn=log):
    """The one characterization value task 012 asks for: TwoNN LID.

    Written as its own artifact rather than folded into the build so the
    (sampled) estimate can be re-run without rebuilding 473 MB.
    """
    from ..measures.lid import two_nn_lid

    vec = np.load(os.path.join(outdir, "vectors.npy"), mmap_mode="r")
    log_fn(f"TwoNN on {vec.shape} (sampled, seed {seed})")
    x = np.ascontiguousarray(vec[:])          # faiss needs it contiguous
    lid = two_nn_lid(x, seed=seed)
    del x
    log_fn(f"  intrinsic dimensionality {lid:.4f}")
    write_json_stable(os.path.join(outdir, "characterization.json"), {
        "intrinsic_dimensionality": {
            "estimator": "TwoNN",
            "value": lid,
            "seed": int(seed),
            "n_sample": 20000,
            "discard": 0.10,
        },
        "n_base": int(vec.shape[0]),
        "dim": int(vec.shape[1]),
    })
    return lid


def write_fixture_manifest(outdir, log_fn=log):
    written = write_manifest(outdir, ARTIFACTS)
    log_fn(f"{MANIFEST_NAME}: {len(written)} files")
    return written


def verify_metric_convention(outdir, n_queries=200, k=10, log_fn=log):
    """Check that normalized inner product reproduces the published ordering.

    NOT a recomputation of the fixture's ground truth: the result is thrown
    away and the fixture keeps the published array either way. This answers
    only "does our metric convention agree with theirs", which is the one
    assumption the whole calibration rests on and the one thing that would
    make every downstream recall silently wrong.
    """
    import faiss

    vec = np.load(os.path.join(outdir, "vectors.npy"), mmap_mode="r")
    q = np.load(os.path.join(outdir, "queries.npy"))[:n_queries]
    gt = np.load(os.path.join(outdir, "ground_truth.npy"))[:n_queries, :k]
    log_fn(f"metric check: exact IP top-{k} for {len(q)} queries over "
           f"{vec.shape[0]} vectors")
    index = faiss.IndexFlatIP(vec.shape[1])
    for i in range(0, vec.shape[0], CHUNK):
        index.add(np.ascontiguousarray(vec[i:i + CHUNK]))
    _, ids = index.search(np.ascontiguousarray(q), k)
    agree = float(np.mean([len(set(a.tolist()) & set(b.tolist())) / k
                           for a, b in zip(ids, gt)]))
    log_fn(f"  agreement with the published neighbours: {agree:.6f}")
    return agree
