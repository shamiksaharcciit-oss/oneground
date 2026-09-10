#!/usr/bin/env python3
"""A small synthetic corpus for the engine calibration, made in CI.

WHY CI NEEDS ONE
----------------
`oneground calibrate engine` compares our simulator's predicted recall against
a real engine's measured recall **on the same sample**. The workflow pointed
it at `requirements.smoke.yaml`, whose corpus is
`fixtures/arxiv-smoke/vectors.npy` -- and `.gitignore` excludes
`fixtures/*/vectors.npy`, so a fresh checkout has that fixture's queries and
ground truth but not its vectors. The step could never have passed on CI, on
any run; calibration run #1 is simply the first time anyone read the error.

Regenerating the arxiv-smoke vectors is not an option: they are embeddings of
real arXiv abstracts, and the embedding model is 400 MB.

WHY SYNTHETIC IS THE RIGHT SUBSTRATE HERE
-----------------------------------------
This check does not compare against a published number. It asks whether *our
simulator* and *a real engine* agree with each other on one sample, and any
sample both can see will answer that. Clustered synthetic vectors give the
index something to get wrong -- a uniform cloud would make every architecture
look identical and the check vacuous -- while staying small enough that CI
runs it in seconds rather than the twenty minutes the glove corpus would cost.

What it deliberately does NOT do is stand in for a corpus in any check that
compares against someone else's published values. `calibrate curve` uses
glove, from the ANN-Benchmarks HDF5, and nothing here touches it.
"""

import argparse
import os
import sys

import numpy as np
import yaml

# Enough vectors that HNSW builds a real graph and recall is not trivially 1.0,
# small enough that ingest into Qdrant and the sweep both finish in seconds.
N_VECTORS = 4000
DIM = 64
N_QUERIES = 200
N_CLUSTERS = 8
SEED = 20260911


def build(out_dir, seed=SEED):
    rng = np.random.default_rng(seed)
    centres = rng.normal(0, 1, size=(N_CLUSTERS, DIM))
    per = N_VECTORS // N_CLUSTERS + 1
    x = np.vstack([c + rng.normal(0, 0.35, size=(per, DIM))
                   for c in centres])[:N_VECTORS].astype(np.float32)
    x /= np.linalg.norm(x, axis=1, keepdims=True)

    # Queries drawn from the corpus, then perturbed: an exact copy would make
    # every architecture score 1.0 at k=1 and hide any disagreement.
    idx = rng.choice(N_VECTORS, size=N_QUERIES, replace=False)
    q = x[idx] + rng.normal(0, 0.05, size=(N_QUERIES, DIM)).astype(np.float32)
    q /= np.linalg.norm(q, axis=1, keepdims=True)

    os.makedirs(out_dir, exist_ok=True)
    vec_p = os.path.join(out_dir, "vectors.npy")
    q_p = os.path.join(out_dir, "queries.npy")
    np.save(vec_p, x)
    np.save(q_p, q.astype(np.float32))
    return vec_p, q_p


def requirements(path, vec_p, q_p, workdir):
    doc = {
        "oneground": 1,
        "run": {"name": "ci-engine-calibration", "mode": "measure",
                "seed": SEED, "workdir": workdir},
        "corpus": {"sample": {
            "kind": "receipt",
            "vectors": {"path": vec_p, "normalized": True},
            "queries": {"path": q_p, "count_min": 50, "source": "synthetic"},
            "target_sample_size": N_VECTORS,
        }},
        "simulate": {
            "kind": "declared",
            "families": ["single_node_hnsw"],
            "node_counts": [1],
            "ground_truth_k": 100,
            "include": [{"family": "single_node_hnsw", "M": 32,
                         "efConstruction": 200, "efSearch": 128}],
            "grid": {"single_node_hnsw": {"M": [32], "efSearch": [128]}},
        },
        # `calibrate engine` overrides the target to local and points the
        # adapter at ONEGROUND_QDRANT_URL, so the engine here is the service
        # container the workflow already started.
        "verify": {
            "kind": "declared",
            "target": "local",
            "engine": "qdrant",
            "engines": ["qdrant"],
            "endpoint": "http://localhost:6333",
            "metric": "inner_product",
            "ks": [10, 100],
            "engine_params": {"m": 32, "ef_construct": 200, "hnsw_ef": 128,
                              # Without this Qdrant leaves a collection under
                              # its 20 MB default unindexed and answers every
                              # search with an exact scan (task 009).
                              "indexing_threshold": 1},
        },
        "constraints": {
            "kind": "declared",
            "recall_at_k": {"k": 10, "min": 0.5},
            "storage_amplification_max": 2.0,
        },
    }
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(doc, f, sort_keys=False)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=".ci/corpus")
    ap.add_argument("--requirements", default=".ci/requirements.ci.yaml")
    ap.add_argument("--workdir", default="./runs/ci-engine-calibration")
    args = ap.parse_args(argv)

    vec_p, q_p = build(args.out)
    os.makedirs(os.path.dirname(args.requirements) or ".", exist_ok=True)
    requirements(args.requirements, os.path.abspath(vec_p),
                 os.path.abspath(q_p), args.workdir)
    print(f"{N_VECTORS:,} vectors, dim {DIM}, {N_QUERIES} queries "
          f"in {N_CLUSTERS} clusters (seed {SEED})")
    print(f"  {vec_p}")
    print(f"  {q_p}")
    print(f"  {args.requirements}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
