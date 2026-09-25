"""Step 6: is the ordering of the three corpora by crispness stable across
embedding models?

THE DESIGN, AND WHY IT IS THIS SHAPE

Full size is not affordable here. Embedding is token-bound at ~273 tokens/s on
this machine, so one 150k corpus under one model is ~41 hours and the full
3x3 is ~200 hours. Measured, not estimated: see 036-cost-and-protocol-probe.

So the ordering is measured on a seeded subsample of N records per corpus, at
a fixed centroid count, identical across every corpus and every model. The
subsample was validated as an instrument first (036-instrument-check): on the
stored anchor vectors it reproduces the published ordering arxiv >
stackexchange at every size from N=1000 to N=20000, with the gap converging on
the published 0.0248 as N grows. A subsample that reversed the published
ordering under the published model would have been measuring noise.

EVERY MODEL IS EMBEDDED HERE, INCLUDING THE ANCHOR, and that is deliberate
even though the anchor's vectors are already on disk. Re-embedding the stored
text with the same named model on this machine reproduces the published
vectors only to cosine 0.9969 (036-anchor-reproduces), because the published
vectors were built on CUDA on Linux and this is CPU on Windows. Mixing a
stored anchor with locally embedded challengers would put a platform
difference inside the comparison, where it would be indistinguishable from a
model difference.

Crispness is a property of the base vectors alone, so only base records are
embedded. Ambiguity and drift need queries and timestamps and are not measured
here; they are not the question.
"""
import io
import json
import os
import sys
import time

import numpy as np
import zstandard as zstd

# Task 065-071's third failure class: `python corpora/036-ordering-
# experiment.py`, run as a file the way `run_036_models.sh` actually runs
# it, puts THIS FILE'S OWN DIRECTORY on `sys.path[0]` -- not the caller's
# cwd, which is what every local check of this script exercised instead
# (an explicit `sys.path.insert(0, '.')` in an ad hoc snippet, or
# `importlib.util.spec_from_file_location`, neither of which touches
# `sys.path[0]` the way a real `python <path>` invocation does).
# `oneground` is never pip-installed (`pip install -r requirements.txt`
# only), so nothing else makes it importable. Anchored to `__file__`, not
# cwd, matching `corpora/build_fixture.py`, `corpora/export_ground_view.py`
# and `corpora/run_chunking.py` -- the majority convention already in this
# directory -- rather than `corpora/036-truncation-per-model.py`'s
# `os.path.abspath(".")`, which depends on the caller's cwd and was the
# minority, weaker form. See `tasks/finding-a-check-that-takes-a-different-
# route-than-production.md`.
sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground.chunk.strategies import chunk_document          # noqa: E402
from oneground.embed import embed                               # noqa: E402
from oneground.embed.registry import resolve                    # noqa: E402
from oneground.measures.crispness import (                      # noqa: E402
    boundary_crispness, centroid_dists, kmeans,
    reading as crispness_reading)
from oneground.measures.lid import two_nn_lid                   # noqa: E402
from oneground.measures.skew import skew_top10_share             # noqa: E402

HOME = os.environ.get("ONEGROUND_ASSETS") or os.path.expanduser(
    "~/oneground-assets")
OUT = os.environ.get("ONEGROUND_036_OUT",
                     "tasks/scratch/036-ordering-results.json")
SEED = 20260920
# N_BASE=0 means "every record": the full-size run on a pod. The subsample
# size and the centroid count are the instrument, and both are recorded in the
# results so a full-size run and a subsample are never read as one series.
N_BASE = int(os.environ.get("ONEGROUND_036_N", "3000"))
CENTROIDS = int(os.environ.get("ONEGROUND_036_CENTROIDS", "32"))
DEVICE = os.environ.get("ONEGROUND_036_DEVICE", "cpu")
BATCH = int(os.environ.get("ONEGROUND_036_BATCH", "16"))
MODELS = ("BAAI/bge-base-en-v1.5",
          "sentence-transformers/all-MiniLM-L6-v2",
          "intfloat/e5-base-v2")
STRUCTURE_PARAMS = {"max_size": 512, "overlap": 0, "min_size": 64}


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def read_jsonl_zst(path, limit=None, role=None):
    out = []
    with open(path, "rb") as fh:
        with zstd.ZstdDecompressor().stream_reader(fh) as reader:
            for line in io.TextIOWrapper(reader, encoding="utf-8"):
                r = json.loads(line)
                if role and r.get("role") != role:
                    continue
                out.append(r)
                if limit and len(out) >= limit:
                    break
    return out


def texts_arxiv():
    recs = read_jsonl_zst(os.path.join(HOME, "arxiv-150k", "sample.jsonl.zst"),
                          role="base")
    return ["%s\n\n%s" % (r["title"], r["abstract"]) for r in recs]


def texts_stackexchange():
    recs = read_jsonl_zst(
        os.path.join(HOME, "stackexchange-150k", "sample.jsonl.zst"),
        role="base")
    return ["%s\n\n%s" % (r["title"], r["body"]) for r in recs]


def texts_filings(target):
    """Chunks, cut on the filings' own section markup.

    `structure` is used because these documents carry declared sections and it
    is what the published fixture's chunking run measured. Enough documents are
    read to reach `target` chunks and no more.
    """
    path = os.path.join(HOME, "sec-filings-10k", "documents.jsonl.zst")
    chunks, docs_read = [], 0
    with open(path, "rb") as fh:
        with zstd.ZstdDecompressor().stream_reader(fh) as reader:
            for line in io.TextIOWrapper(reader, encoding="utf-8"):
                r = json.loads(line)
                docs_read += 1
                units = [(s["start"], s["end"], s.get("title", ""))
                         for s in (r.get("sections") or [])]
                if not units:
                    continue
                try:
                    got = chunk_document(r["text"], "structure",
                                         dict(STRUCTURE_PARAMS),
                                         doc_id=str(r.get("accession")),
                                         units=units)
                except Exception:                              # noqa: BLE001
                    continue
                chunks.extend(c.text for c in got)
                if len(chunks) >= target * 3:
                    break
    log("filings: %d chunks from %d documents" % (len(chunks), docs_read))
    return chunks


_ALL_CORPORA = {
    "arxiv-150k": texts_arxiv,
    "stackexchange-150k": texts_stackexchange,
    # N_BASE=0 is the full-size run, and "all of it" for the filings means
    # every chunk the strategy produces rather than a cap.
    "sec-filings-10k": lambda: texts_filings(N_BASE or 200000),
}

# Task 065: `texts_filings` chunks with no `tokenizer=` argument, so
# `chunk_document` falls back to `WhitespaceTokens` (oneground/chunk/
# strategies.py) -- `max_size: 512` there means 512 whitespace-delimited
# tokens, not the 512 (bge/e5) or 256 (MiniLM) SUBWORD tokens the models'
# own `max_seq_length` is stated in. That mismatch, not corpus content
# alone, is a candidate explanation for the heavy truncation filings
# already showed at subsample scale (86-94%, all three models) -- and
# fixing it by chunking per model's own tokenizer would make the chunk
# boundaries, and so the chunk COUNT and geometry, differ by model, which
# breaks this experiment's own stated invariant that every model measures
# the identical records. That is a design decision (a shared reference
# tokenizer? per-model chunking with the confound now structural instead
# of incidental? chunk in characters instead of tokens?) this task does not
# invent a guess for. `sec-filings-10k` is excluded from this session by
# this allowlist; re-chunking it in subword tokens is left as a separate
# task. `ONEGROUND_036_CORPORA` overrides the list, comma-separated, for
# anyone re-running this script once that follow-up exists.
CORPORA = {name: fn for name, fn in _ALL_CORPORA.items()
          if name in (os.environ.get("ONEGROUND_036_CORPORA")
                      or "arxiv-150k,stackexchange-150k").split(",")}

PUBLISHED = {"sec-filings-10k": 0.107347, "arxiv-150k": 0.036273,
             "stackexchange-150k": 0.0115}


def subsample(items, n, seed=SEED):
    rng = np.random.default_rng(seed)
    if n <= 0 or len(items) <= n:
        return list(items), len(items)
    idx = np.sort(rng.choice(len(items), size=n, replace=False))
    return [items[int(i)] for i in idx], len(items)


def measure(vectors, seed=SEED):
    x = np.ascontiguousarray(vectors.astype(np.float32))
    cents = kmeans(x, CENTROIDS, seed)
    d, r = centroid_dists(x, cents, 2)
    # Task 044: `boundary_crispness` is unchanged -- kept so this experiment's
    # ordering is still the published reading -- but it is a count at a fixed
    # threshold, and this is the ordering question the threshold was found to
    # mislead on (e5's count collapses toward zero on every corpus at
    # subsample scale, this module's own docstring). `crispness_reading`
    # is what `oneground.characterize` itself now carries beside the bare
    # count, precisely so a near-zero number comes with why: where 1.20 sits
    # in THIS corpus's own distribution, whether that count is even
    # distinguishable from zero, and -- at full size only, n >=
    # MIN_N_FOR_TRANSFER -- whether this embedding is reading the threshold
    # somewhere the measure has never been calibrated. Omitting this call
    # would report exactly the collapsed number the subsample already showed
    # was insufficient to read, and calling it is the entire difference this
    # full-size session is meant to make.
    crisp = crispness_reading(d, with_distribution=True)
    return {
        "boundary_crispness": boundary_crispness(d),
        "crispness_reading": crisp,
        "intrinsic_dimensionality": float(two_nn_lid(x, seed)),
        # `skew_top10_share` defaults its centroid count to the project's 256;
        # this experiment runs 32, and passing it is the difference between a
        # share of the regions that exist and a share of regions that do not.
        "skew_top10_share": float(
            skew_top10_share(r[:, 0], len(x), n_centroids=CENTROIDS)),
    }


def main():
    results = {}
    if os.path.exists(OUT):
        results = json.load(open(OUT, encoding="utf-8"))
        log("resuming with %d cells already done"
            % sum(len(v) for v in results.get("cells", {}).values()))
    results.setdefault("design", {
        "n_base": N_BASE, "centroids": CENTROIDS, "seed": SEED,
        "device": DEVICE, "full_size": N_BASE <= 0,
        "models": list(MODELS), "corpora": list(CORPORA),
        "published_full_size": PUBLISHED,
        "structure_params": STRUCTURE_PARAMS,
        "note": "subsample validated in 036-instrument-check; every model "
                "embedded in this environment including the anchor, because "
                "the stored anchor vectors were built on CUDA/Linux and "
                "reproduce here only to cosine 0.9969",
    })
    results.setdefault("cells", {})

    texts_by_corpus = {}
    for corpus, fn in CORPORA.items():
        log("loading %s" % corpus)
        all_texts = fn()
        picked, total = subsample(all_texts, N_BASE)
        texts_by_corpus[corpus] = picked
        log("  %s: %d of %d records, mean %d chars"
            % (corpus, len(picked), total,
               int(np.mean([len(t) for t in picked]))))

    for model_name in MODELS:
        pending = [c for c in CORPORA
                   if model_name not in results["cells"].get(c, {})]
        if not pending:
            log("%s: already done" % model_name)
            continue
        log("resolving %s" % model_name)
        rm = resolve(model_name, device=DEVICE)
        log("  %dd, max_seq %d" % (rm.dimension, rm.max_seq_length))
        for corpus in pending:
            texts = texts_by_corpus[corpus]
            log("  embedding %s x %s (%d records)"
                % (model_name, corpus, len(texts)))
            t0 = time.time()
            v = embed(rm.model, texts, batch=BATCH, show_progress_bar=False)
            dt = time.time() - t0
            m = measure(v)
            m.update({"embed_seconds": dt,
                      "records_per_second": len(texts) / dt,
                      "dimension": rm.dimension,
                      "max_seq_length": rm.max_seq_length,
                      "weights_sha256": rm.weights_sha256,
                      "n_records": len(texts)})
            results["cells"].setdefault(corpus, {})[model_name] = m
            log("    crispness %.4f  lid %.1f  skew %.4f  (%.0f s, %.1f rec/s)"
                % (m["boundary_crispness"], m["intrinsic_dimensionality"],
                   m["skew_top10_share"], dt, m["records_per_second"]))
            cr = m["crispness_reading"]
            log("      reading: threshold 1.20 sits at the %.2fth percentile "
                "of this corpus's ratio distribution (%d of %d above it)%s"
                % (cr["threshold_percentile"], cr["n_above"], cr["n"],
                   "" if cr["resolvable"]
                   else "  COULDN'T-CHECK: " + cr["why"]))
            tr = cr["transfer"]
            if tr.get("outcome") == "couldnt_check":
                log("      transfer: " + tr["note"])
            else:
                log("      transfer: %s"
                    % ("OUTSIDE the published band" if tr["outside_published_range"]
                       else "inside the published band"))
            json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
        del rm

    json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
    log("done -> %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
