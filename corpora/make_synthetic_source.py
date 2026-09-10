#!/usr/bin/env python3
"""
Synthetic arXiv-format source generator
=======================================

FOR PIPELINE TESTING ONLY. This emits fake records in the same JSONL shape as
the real arXiv metadata snapshot (arxiv-metadata-oai-snapshot.json) so that
corpora/build_fixture.py can be exercised end to end without downloading the
real 4 GB snapshot. Nothing produced here is a corpus, a measurement, or a
fixture value: the text is assembled from a small word list, so any
characterization computed on it describes the generator, not arXiv. Never use
it for a published artifact.

Each record carries the fields build_fixture.py reads:

    id           arXiv-style identifier, YYMM.NNNNN, consistent with update_date
    title        short noun phrase built from the record's primary category
    abstract     >= 200 characters (the builder's eligibility floor)
    categories   space-separated, primary category first, as in the snapshot
    update_date  YYYY-MM-DD, spanning 2007-2025

Category mix is skewed toward cs.LG / cs.CL, mirroring the real corpus. Text is
drawn from per-category vocabularies so the embedding space has some cluster
structure to characterize rather than being uniform noise.

Usage
-----
    python corpora/make_synthetic_source.py --out <path.json> [--n 6000]
"""

import argparse
import json

import numpy as np

# Twelve real arXiv category strings, with the weight each gets in the mix.
# Skewed toward cs.LG / cs.CL, as the real corpus is.
CATEGORIES = [
    ("cs.LG", 0.22), ("cs.CL", 0.17), ("cs.CV", 0.11), ("cs.AI", 0.09),
    ("stat.ML", 0.08), ("cs.IR", 0.07), ("eess.SP", 0.06), ("math.OC", 0.05),
    ("cond-mat.stat-mech", 0.04), ("astro-ph.GA", 0.04), ("hep-th", 0.04),
    ("q-bio.NC", 0.03),
]

# Per-category vocabulary. Gives each region of the embedding space its own
# lexis so k-means has something to find.
VOCAB = {
    "cs.LG": "gradient descent regularization overfitting ensemble kernel batch"
             " normalization convergence generalization optimizer sparsity",
    "cs.CL": "tokenization parsing morphology corpus translation semantics"
             " discourse coreference lexicon utterance grammar transliteration",
    "cs.CV": "segmentation occlusion convolution saliency stereo pixel texture"
             " calibration keypoint photometric silhouette registration",
    "cs.AI": "planner heuristic ontology constraint satisfaction agent belief"
             " revision abduction scheduling nonmonotonic reasoning",
    "stat.ML": "posterior likelihood variational estimator covariance prior"
               " marginal consistency asymptotic bootstrap identifiability",
    "cs.IR": "ranking relevance retrieval index query expansion recall"
             " precision collection judgement snippet click",
    "eess.SP": "waveform spectrum filter quantization sampling modulation"
               " antenna interference beamforming estimation channel",
    "math.OC": "convex duality subgradient feasible polytope relaxation"
               " stationarity Lagrangian constraint minimax proximal",
    "cond-mat.stat-mech": "entropy lattice thermodynamic equilibrium phase"
                          " transition Ising correlation fluctuation ensemble critical",
    "astro-ph.GA": "galaxy halo metallicity photometry redshift stellar"
                   " kinematics luminosity spectroscopy nebula accretion",
    "hep-th": "gauge supersymmetry anomaly holography soliton renormalization"
              " brane manifold curvature amplitude duality",
    "q-bio.NC": "neuron synapse cortical spiking plasticity dendrite receptive"
                " field oscillation connectome excitability firing",
}

FRAME = [
    "We study {a} {b} in the setting of {c}.",
    "This paper introduces a method for {a} based on {b}.",
    "We show that {a} and {b} are related through {c}.",
    "An analysis of {a} under {b} is presented.",
    "We report experiments on {a}, {b}, and {c}.",
    "The role of {a} in {b} has not been characterized.",
    "Our approach improves {a} relative to {b} baselines.",
    "We derive bounds on {a} in terms of {b} and {c}.",
]

# Year weights: volume grows over time, as arXiv's does, but enough mass stays
# before 2019 for the drift split in the spec to have a usable pre-2019 half.
YEARS = list(range(2007, 2026))


def year_weights():
    w = np.array([1.35 ** (y - 2007) for y in YEARS], dtype=np.float64)
    w = w / w.sum()
    # flatten toward uniform so the pre-2019 side keeps roughly a third of mass
    w = 0.45 * w + 0.55 * np.full(len(YEARS), 1.0 / len(YEARS))
    return w / w.sum()


def make_abstract(rng, primary, secondary):
    words = VOCAB[primary].split() + VOCAB[secondary].split()
    out = []
    while sum(len(s) for s in out) < 260:          # comfortably over the 200 floor
        frame = FRAME[rng.integers(len(FRAME))]
        a, b, c = rng.choice(words, size=3, replace=False)
        out.append(frame.format(a=a, b=b, c=c))
    return " ".join(out)


def make_title(rng, primary):
    words = VOCAB[primary].split()
    a, b, c = rng.choice(words, size=3, replace=False)
    shape = rng.integers(3)
    if shape == 0:
        return f"On the {a} of {b} in {c}"
    if shape == 1:
        return f"{a.capitalize()} and {b}: a study of {c}"
    return f"Learning {a} from {b} with {c}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=20260908)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    names = [c for c, _ in CATEGORIES]
    probs = np.array([w for _, w in CATEGORIES], dtype=np.float64)
    probs = probs / probs.sum()
    yw = year_weights()

    used = set()
    n_written = 0
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        for _ in range(args.n):
            primary = names[rng.choice(len(names), p=probs)]
            secondary = names[rng.choice(len(names), p=probs)]
            cats = primary if secondary == primary else f"{primary} {secondary}"

            year = YEARS[rng.choice(len(YEARS), p=yw)]
            month = int(rng.integers(1, 13))
            day = int(rng.integers(1, 29))

            while True:                                    # ids are unique
                ident = f"{year % 100:02d}{month:02d}.{int(rng.integers(1, 99999)):05d}"
                if ident not in used:
                    used.add(ident)
                    break

            f.write(json.dumps({
                "id": ident,
                "title": make_title(rng, primary),
                "abstract": make_abstract(rng, primary, secondary),
                "categories": cats,
                "update_date": f"{year:04d}-{month:02d}-{day:02d}",
            }) + "\n")
            n_written += 1

    print(f"wrote {n_written:,} synthetic records to {args.out}")


if __name__ == "__main__":
    main()
