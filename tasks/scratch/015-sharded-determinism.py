"""015 step 1: what determinism costs the two sharded families, and that it holds.

Task 012b made `single_node_hnsw` build single-threaded after measuring that a
parallel faiss add is not reproducible. `hash_sharded` and `semantic_sharded`
build `IndexHNSWFlat` per shard through the same code and were left
unconverted; 015 converts them.

Two questions, kept apart, the same way 012b kept them:

    correctness  two builds -> byte-identical returned ids
    cost         parallel build seconds vs deterministic build seconds

Measured at two sizes: arxiv-smoke's 2,000 real vectors (768-dim, the fixture
the product path is exercised against) and a 20,000-vector synthetic sample,
which is the size a user's sweep actually runs at -- `characterize` samples
10-20k, so that is the regime the cost lands in for a real user rather than a
fixture.

`semantic_sharded` is the interesting one: it is not only HNSW. Its k-means is
seeded but its centroid update is a floating-point sum whose order OpenMP does
not fix, so a last-bit difference in a centroid can move a point across a
region boundary and change shard membership. Whether that actually happens is
measured here rather than argued.
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, ".")

from oneground.models import REGISTRY                      # noqa: E402
from oneground.models.base import ConfigSpace              # noqa: E402

SMOKE = "fixtures/arxiv-smoke/vectors.npy"
N_SYNTHETIC = 20_000
DIM_SYNTHETIC = 256
SEED = 20260911
K = 10
N_QUERIES = 200

# The published reference configurations, so the cost measured is the cost of
# the configurations that actually get built.
CONFIGS = {
    "semantic_sharded": {"centroids": 256, "epsilon": 0.2, "probe": 2,
                         "M": 32, "efSearch": 96},
    "hash_sharded": {"shards": 3, "M": 32, "efSearch": 96},
    "single_node_hnsw": {"M": 32, "efConstruction": 200, "efSearch": 128},
}


def synthetic(n, dim, seed=SEED):
    """Clustered, normalized -- k-means has something to find."""
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(48, dim))
    x = np.vstack([c + rng.normal(0, 0.28, size=(n // 48 + 1, dim))
                   for c in centres])[:n].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    return np.ascontiguousarray(x)


def timed(model, v, cfg, deterministic):
    t0 = time.time()
    built = model.build(v, cfg, seed=SEED, deterministic=deterministic)
    return time.time() - t0, built


def measure(family, v, q, corpus_name):
    model = REGISTRY[family]
    space = ConfigSpace(seed=SEED, include=[{"family": family,
                                             **CONFIGS[family]}])
    cfg = model.configs(space)[0]
    print(f"\n===== {family} on {corpus_name}: {v.shape} =====", flush=True)
    print(f"  config {cfg.label}", flush=True)

    # Discarded warm-up. The first build in a process pays for faiss's
    # one-time setup and for paging the corpus in; 012b already saw that
    # inflate a first measurement several-fold. Without it, whichever build
    # ran first looks slower -- which is how "deterministic is 6x faster"
    # gets into a report.
    timed(model, v, cfg, False)

    t_par, b_par = timed(model, v, cfg, False)
    print(f"  parallel        {t_par:8.2f}s", flush=True)
    t_det, b_det = timed(model, v, cfg, True)
    print(f"  deterministic   {t_det:8.2f}s   ratio {t_det / t_par:.2f}x",
          flush=True)
    t_det2, b_det2 = timed(model, v, cfg, True)

    a = model.search(b_det, q, K, cfg).ids
    c = model.search(b_det2, q, K, cfg).ids
    same = bool(np.array_equal(a, c))
    print(f"  two deterministic builds -> byte-identical ids: {same}",
          flush=True)

    row = {"family": family, "corpus": corpus_name, "n": int(v.shape[0]),
           "dim": int(v.shape[1]), "config": cfg.label,
           "parallel_s": t_par, "deterministic_s": t_det,
           "deterministic_s_2": t_det2, "ratio": t_det / t_par,
           "byte_identical_ids": same}
    if not same:
        row["fraction_differing"] = float(np.mean(a != c))
        print(f"    ids differing: {row['fraction_differing']:.6f}")

    # For semantic_sharded, shard membership is upstream of every graph, so
    # report whether it is stable too -- a family can return identical ids and
    # still have been lucky.
    if "ids_of" in b_det.state:
        def signature(b):
            return tuple((r, len(b.state["ids_of"][r]),
                          int(b.state["ids_of"][r].sum()))
                         for r in sorted(b.state["ids_of"]))
        row["shard_membership_identical"] = bool(
            signature(b_det) == signature(b_det2))
        row["n_shards"] = len(b_det.state["ids_of"])
        print(f"  shard membership identical: "
              f"{row['shard_membership_identical']} "
              f"({row['n_shards']} shards)", flush=True)

    # ...and the two PARALLEL builds, for the contrast that motivated all this
    _, p1 = timed(model, v, cfg, False)
    _, p2 = timed(model, v, cfg, False)
    pa = model.search(p1, q, K, cfg).ids
    pc = model.search(p2, q, K, cfg).ids
    row["parallel_byte_identical_ids"] = bool(np.array_equal(pa, pc))
    row["parallel_fraction_differing"] = float(np.mean(pa != pc))
    print(f"  two PARALLEL builds -> byte-identical ids: "
          f"{row['parallel_byte_identical_ids']} "
          f"(differing {row['parallel_fraction_differing']:.6f})", flush=True)
    return row


if __name__ == "__main__":
    families = ["hash_sharded", "semantic_sharded"]
    rows = []

    sv = np.load(SMOKE)
    sq = np.ascontiguousarray(np.load("fixtures/arxiv-smoke/queries.npy")
                              [:N_QUERIES])
    for fam in families:
        rows.append(measure(fam, sv, sq, "arxiv-smoke"))

    yv = synthetic(N_SYNTHETIC, DIM_SYNTHETIC)
    yq = np.ascontiguousarray(yv[:N_QUERIES])
    for fam in families:
        rows.append(measure(fam, yv, yq, f"synthetic-{N_SYNTHETIC // 1000}k"))

    # The regime where the defect actually shows. Task 012 measured
    # single_node_hnsw diverging between two parallel builds at 200,000
    # glove vectors (37% of returned ids differing at efSearch=10) while
    # agreeing at 2,000. If the sharded families never diverge here either,
    # the conversion closed a hole rather than fixed an observed failure, and
    # the report has to say which.
    big = "fixtures/glove-100-angular/vectors.npy"
    if os.path.exists(big):
        gv = np.ascontiguousarray(np.load(big, mmap_mode="r")[:200_000])
        gq = np.ascontiguousarray(
            np.load("fixtures/glove-100-angular/queries.npy")[:N_QUERIES])
        for fam in families:
            rows.append(measure(fam, gv, gq, "glove-200k"))
    else:
        print(f"\n  {big} absent: the 200k divergence check did not run")

    print("\n===== summary =====")
    print(f"  {'family':<18} {'corpus':<16} {'n':>7} {'parallel':>10} "
          f"{'determ.':>10} {'ratio':>7}  det-identical  par-identical")
    for r in rows:
        print(f"  {r['family']:<18} {r['corpus']:<16} {r['n']:>7} "
              f"{r['parallel_s']:>9.2f}s {r['deterministic_s']:>9.2f}s "
              f"{r['ratio']:>6.2f}x  {str(r['byte_identical_ids']):<13}  "
              f"{r['parallel_byte_identical_ids']}")
    with open("tasks/scratch/015-sharded-determinism.json", "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, indent=2, sort_keys=True)
        f.write("\n")
    print("\n  wrote tasks/scratch/015-sharded-determinism.json")
