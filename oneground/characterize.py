"""`oneground characterize <requirements.yaml>` — the product path.

The same five measures the fixture publishes, run against a user's own
vectors, producing the same receipt-shaped output:

    <workdir>/
        characterization.json   measurement only  (receipt)
        build_info.json         versions, device, input digests  (declared)
        sample_ids.json         which input rows were measured  (receipt)
        queries_ids.json        which queries were used  (receipt)
        MANIFEST.sha256         digest of every file above

Nothing is reproduced here. The fixture reproduces published values; this
command measures a corpus for the first time, and says so -- the word
"reproduced" never appears in its output, because there is nothing to compare
against.

Three things are reported as couldn't-check rather than filled in:

    drift              needs metadata.timestamp_field; without a time column
                       there is no before and after
    ambiguous_query_rate  needs at least `queries.count_min` queries (50 by
                       default); a rate over a dozen queries is arithmetic,
                       not a measurement
    weights_sha256     best-effort, and null when the model cache cannot be
                       located

Vectors never leave the machine. Every path in this module is a local file.
"""

import json
import os
import platform
import time

import numpy as np

from . import environment
from . import intake
from .measures import centroid_dists, kmeans, two_nn_lid
from .measures.ambiguity import (AMBIGUOUS_RATIO, ambiguous_query_rate,
                                 reading as ambiguity_reading)
from .measures.crispness import (CRISP_RATIO, N_CENTROIDS, boundary_crispness,
                                 reading as crispness_reading)
from .measures.drift import drift_pair
from .measures.skew import reading as skew_reading, skew_top10_share
from .receipts import (MANIFEST_NAME, library_versions, producing_version,
                      round_floats,
                       sha256_file, write_json_stable, write_manifest)
from .provenance import invocation
from .sample import loaders

COULDNT_CHECK = "couldnt_check"

RECEIPT_FILES = ["characterization.json", "sample_ids.json",
                 "queries_ids.json", "build_info.json"]

# Tier 2 produces the same two files and no sample: there are no ids to write
# because nothing was sampled.
DECLARED_FILES = ["characterization.json", "build_info.json"]

# Every field `characterize_arrays` produces. Tier 2 writes all of them,
# carrying the same sentence, rather than omitting them: an absent field reads
# as an oversight, a field that says why it is empty reads as a boundary, and
# every consumer that already renders a couldnt_check string renders it with
# no change.
MEASURED_FIELDS = ("intrinsic_dimensionality", "boundary_crispness",
                   "crispness_reading",
                   "skew_top10_share", "ambiguous_query_rate",
                   "ambiguity_reading", "drift")

DECLARED_NOT_MEASURED = f"{COULDNT_CHECK}: declared, not measured"

# UMAP settings for --project. Taken from the fixture specs' `projection`
# block so a user's ground view is drawn the same way the published one was.
# The projection is illustrative and declared, never a measurement: UMAP is
# seeded but not bit-stable across BLAS builds, and nothing is decided from it.
PROJECTION_PARAMS = {"n_neighbors": 30, "min_dist": 0.08, "metric": "cosine"}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _fmt(v, nd=3):
    if isinstance(v, str):
        return v
    if v is None:
        return "-"
    return f"{v:.{nd}f}"


def _warn_truncation(truncation, log_fn=log):
    """Say it at run time, not only in a file nobody opens. Task 017 item 3.

    Truncation is the one intake fault that leaves no trace in any number
    downstream: the vectors are well-formed, the recall is self-consistent,
    and the corpus they describe is not the corpus on disk. So it is said
    loudly, once, with the count in it.
    """
    from .embed import TRUNCATION_ADVICE
    if truncation is None:
        log_fn("truncation: couldnt_check -- the model exposed no tokenizer "
               "to count with, so it is not known how many records were cut")
        return
    n = truncation["truncated_count"]
    if not n:
        log_fn(f"truncation: none -- the longest of "
               f"{truncation['n_records']:,} records is "
               f"{truncation['longest_tokens']} tokens, within "
               f"{truncation['max_seq_length']}")
        return
    log_fn(f"WARNING: {n:,} of {truncation['n_records']:,} records "
           f"({truncation['truncated_fraction']:.1%}) are longer than "
           f"max_seq_length {truncation['max_seq_length']} tokens and will be "
           f"TRUNCATED; the longest is {truncation['longest_tokens']} tokens. "
           + TRUNCATION_ADVICE)


def _embedder(req, log_fn=log):
    """`(embed, weights_sha256, count_truncated)`, each None without a model.

    Built lazily so that a vectors-only run never imports torch.
    """
    model_name = req.model
    if not model_name:
        return None, None, None

    from .embed import (count_truncated, embed as _embed, load_model)
    device = req.text.get("device", "cpu")
    log_fn(f"loading model {model_name} on {device}")
    model, weights_sha = load_model(
        model_name, device=device,
        max_seq_length=int(req.text.get("max_seq_length", 512)), log=log_fn)
    batch = int(req.text.get("batch_size", 64))
    # So the truncation record can name the model without the caller having
    # to carry it separately.
    model._oneground_name = model_name

    def run(texts):
        return _embed(model, texts, batch)

    def count(texts):
        return count_truncated(model, texts)

    return run, weights_sha, count


def _say_reading(got, log_fn=log):
    """Where the crispness threshold fell, and whether it could be read.

    Printed rather than written, and always -- not only when it fails. A user
    who never sees a warning learns nothing about where 1.20 sits in their own
    corpus's distribution, and that position is what decides whether the count
    means anything for their embedding (task 036).
    """
    log_fn("characterize: crispness %.4f at threshold %.2f, which is the "
           "%.2fth percentile of this corpus's ratio distribution (%d of %d "
           "vectors above it)"
           % (got["value"], got["threshold"], got["threshold_percentile"],
              got["n_above"], got["n"]))
    if got.get("outcome") == COULDNT_CHECK:
        log_fn("characterize: COULDN'T-CHECK on the crispness reading -- "
               + got["why"])


def _say_ambiguity(got, log_fn=log):
    """Where the ambiguity threshold fell, and whether the rate can be read.

    Printed always, like the crispness one, and for a sharper reason: this
    measure fails by SATURATING, and a rate near 1.0 reads as a strong finding
    rather than as an instrument that has stopped discriminating. A user who
    sees only `0.98` has no way to tell those apart; a user who also sees that
    1.10 sits at the 97th percentile of their own distribution does.
    """
    log_fn("characterize: ambiguity %.4f at threshold %.2f, which is the "
           "%.2fth percentile of this corpus's query ratio distribution "
           "(%d of %d queries outside it)"
           % (got["value"], got["threshold"], got["threshold_percentile"],
              got["n_outside"], got["n"]))
    if got.get("outcome") == COULDNT_CHECK:
        log_fn("characterize: COULDN'T-CHECK on the ambiguity reading -- "
               + got["why"])


def characterize_arrays(base, queries, seed, timestamps=None,
                        query_timestamps=None, cutoff=None,
                        count_min=50, log_fn=log):
    """The five measures over already-loaded arrays.

    Split out from the file handling so the measures can be tested directly
    and so the fixture path and the product path are visibly the same
    computation. The call order matches `oneground.fixture.build.characterize`
    exactly -- faiss k-means consumes the seed, so reordering would change the
    centroids and everything derived from them.
    """
    out = {}

    log_fn("characterize: TwoNN LID")
    out["intrinsic_dimensionality"] = two_nn_lid(base, seed)

    log_fn(f"characterize: k-means {N_CENTROIDS}")
    cents = kmeans(base, N_CENTROIDS, seed)
    d_b, r_b = centroid_dists(base, cents, 2)
    out["boundary_crispness"] = boundary_crispness(d_b)
    out["skew_top10_share"] = skew_top10_share(r_b[:, 0], len(base))

    # Task 044c. The centroid count is part of what this number means, not a
    # setting behind it: swept from 16 to 4096 it spans two orders of
    # magnitude and leaves the published tolerance at the first step either
    # way -- the only one of the five with no tolerance band in the count.
    # So the reading carries `n_centroids`, and `skew_top10_share` above is
    # left exactly as it was, the same containment 044 gave crispness.
    out["skew_reading"] = skew_reading(r_b[:, 0], len(base))

    # Task 044. The ratio distribution is the measurement and `boundary_
    # crispness` above is a reading of it at 1.20, which is why the reading
    # carries its threshold and where that threshold falls in this corpus's
    # own distribution.
    #
    # Stored here, in a user's own workdir, and NOT added to the published
    # fixtures. The storage ruling protects published bytes; a fresh workdir
    # has none to protect, and a user whose corpus ships no `ratio` column is
    # exactly the person who cannot recover the distribution afterwards. The
    # published fixtures keep deriving it on demand: their ground views
    # already carry the ratio for every base vector, and their digests are
    # the thing the ruling exists to hold still.
    out["crispness_reading"] = crispness_reading(d_b, with_distribution=True)
    _say_reading(out["crispness_reading"], log_fn)

    if len(queries) >= count_min:
        d_q, _ = centroid_dists(queries, cents, 2)
        out["ambiguous_query_rate"] = ambiguous_query_rate(d_q)
        # Task 044b, the mirror of 044. The same ratio, thresholded from the
        # other side: crispness counts the tail above 1.20, ambiguity counts
        # everything below 1.10. A compressed distribution empties the first
        # and SATURATES the second, and a saturated rate reads as "my queries
        # are all ambiguous" -- a claim about the corpus -- where a zero
        # crispness at least invites the question of whether it is right.
        out["ambiguity_reading"] = ambiguity_reading(d_q,
                                                     with_distribution=True)
        _say_ambiguity(out["ambiguity_reading"], log_fn)
    else:
        out["ambiguous_query_rate"] = (
            f"{COULDNT_CHECK}: {len(queries)} queries, fewer than the "
            f"{count_min} needed (corpus.sample.queries.count_min)")
        out["ambiguity_reading"] = (
            f"{COULDNT_CHECK}: {len(queries)} queries, fewer than the "
            f"{count_min} needed (corpus.sample.queries.count_min)")

    # Drift needs a time column for the corpus *and* one for the queries: the
    # centroids are trained on the corpus before the cutoff, and recall is
    # then compared between queries from before it and queries from after.
    # Both halves are real requirements -- corpus timestamps alone say when
    # the partition was trained but not which queries are the future ones.
    if timestamps is None:
        out["drift"] = f"{COULDNT_CHECK}: no timestamp_field"
    elif query_timestamps is None:
        out["drift"] = (f"{COULDNT_CHECK}: no timestamps for the queries "
                        "(set corpus.sample.queries.metadata.path and "
                        ".timestamp_field); corpus timestamps alone cannot "
                        "say which queries are from after the cutoff")
    else:
        ts = np.asarray([str(t) for t in timestamps])
        q_ts = np.asarray([str(t) for t in query_timestamps])
        if len(q_ts) != len(queries):
            out["drift"] = (f"{COULDNT_CHECK}: {len(q_ts)} query timestamps "
                            f"for {len(queries)} queries")
            return out
        cut = str(cutoff) if cutoff else str(np.sort(ts)[len(ts) // 2])
        base_pre = ts < cut
        q_pre = q_ts < cut
        if base_pre.all() or (~base_pre).all():
            out["drift"] = (f"{COULDNT_CHECK}: the cutoff {cut} leaves one "
                            "side of the corpus empty")
        elif q_pre.all() or (~q_pre).all():
            out["drift"] = (f"{COULDNT_CHECK}: every query falls on one side "
                            f"of the cutoff {cut}")
        else:
            from .truth import exact_knn
            log_fn("characterize: exact ground truth for the drift pair")
            gt10 = exact_knn(base, queries, 10)
            log_fn(f"characterize: drift pair (centroids trained before {cut})")
            out["drift"] = drift_pair(base, queries, base_pre, q_pre, gt10,
                                      seed)
            out["drift"]["cutoff"] = cut
    return out


def project(vectors, seed, params=None, log_fn=log):
    """2-D UMAP of the sample. Illustrative, declared, and optional.

    Returns None when umap-learn is not installed rather than failing the run:
    the projection is a picture, and a missing picture must never cost a user
    their measurements. Task 002b established that ordering for the fixture
    builder and it holds here for the same reason.
    """
    p = {**PROJECTION_PARAMS, **(params or {})}
    try:
        import umap
    except ImportError:
        log_fn("umap-learn not installed; skipping projection "
               "(pip install 'oneground[view]')")
        return None
    log_fn(f"projecting {len(vectors):,} vectors to 2-D (UMAP, seed {seed})")
    red = umap.UMAP(n_neighbors=p["n_neighbors"], min_dist=p["min_dist"],
                    metric=p["metric"], random_state=seed, n_components=2)
    return red.fit_transform(vectors).astype(np.float32)


def run(requirements_path, with_projection=False, log_fn=log,
        env_stamp=None):
    """Load, measure, write receipts, print a summary. Returns the workdir."""
    t0 = time.time()
    req = intake.load(requirements_path)
    workdir = req.resolve(req.workdir)
    os.makedirs(workdir, exist_ok=True)
    log_fn(f"run '{req.name}'  seed {req.seed}  ->  {workdir}")

    if req.tier == 2:
        return run_declared(req, requirements_path, workdir, t0,
                            log_fn, env_stamp=env_stamp)

    embed_fn, weights_sha, count_truncated_fn = _embedder(req, log_fn)
    truncation = None

    # ---- corpus ----
    if req.vectors.get("path"):
        vec_path = req.resolve(req.vectors["path"])
        log_fn(f"loading vectors {vec_path}")
        full = loaders.load_vectors(vec_path)
        ids = loaders.load_ids(req.resolve(req.vectors.get("ids_path")),
                               len(full))
        source_kind = "vectors"
    else:
        text_path = req.resolve(req.text["path"])
        log_fn(f"loading text {text_path}")
        texts, ids = loaders.load_text(
            text_path, text_field=req.text.get("text_field", "text"))
        # Counted BEFORE embedding, so a run that dies in the encoder has
        # already told the user what it was about to throw away. Task 017.
        truncation = count_truncated_fn(texts) if count_truncated_fn else None
        _warn_truncation(truncation, log_fn)
        log_fn(f"embedding {len(texts):,} texts")
        full = embed_fn(texts)
        source_kind = "text"

    n_full, dim = full.shape
    log_fn(f"{n_full:,} vectors, dim {dim}")

    # ---- metadata, before subsampling so the columns stay aligned ----
    meta = loaders.load_metadata(req.resolve(req.metadata.get("path")), n_full)

    # ---- subsample ----
    idx = loaders.subsample(n_full, req.target_sample_size, req.seed)
    if len(idx) < n_full:
        log_fn(f"subsampling {len(idx):,} of {n_full:,} "
               f"(target_sample_size, seed {req.seed})")
    base = np.ascontiguousarray(full[idx])
    if not req.vectors.get("normalized", False) or source_kind == "text":
        base = loaders.normalize_rows(base)
    sample_ids = ([ids[i] for i in idx] if ids
                  else [int(i) for i in idx])

    timestamps = None
    if req.timestamp_field:
        if not meta:
            raise intake.RequirementsError(
                f"{requirements_path}: metadata.timestamp_field is "
                f"{req.timestamp_field!r} but corpus.sample.metadata.path is "
                "not set, so there is no column to read it from")
        if req.timestamp_field not in meta:
            raise intake.RequirementsError(
                f"{requirements_path}: metadata.timestamp_field "
                f"{req.timestamp_field!r} is not a column in the metadata "
                f"file; columns are {sorted(meta)[:10]}")
        timestamps = np.asarray([meta[req.timestamp_field][i] for i in idx])

    # ---- queries ----
    log_fn(f"loading queries {req.resolve(req.queries['path'])}")
    qcfg = dict(req.queries)
    qcfg["path"] = req.resolve(qcfg["path"])
    queries, query_ids = loaders.load_queries(qcfg, embed_fn=embed_fn)
    queries = loaders.normalize_rows(np.ascontiguousarray(queries))
    if queries.shape[1] != dim:
        raise loaders.LoadError(
            f"queries have dim {queries.shape[1]} but the corpus has {dim}; "
            "they must come from the same embedding model")
    if query_ids is None:
        query_ids = list(range(len(queries)))
    log_fn(f"{len(queries):,} queries")

    # ---- query timestamps, for the drift pair ----
    query_timestamps = None
    qmeta_cfg = req.queries.get("metadata") or {}
    qmeta_path = req.resolve(qmeta_cfg.get("path"))
    qts_field = qmeta_cfg.get("timestamp_field") or req.timestamp_field
    if qmeta_path and qts_field:
        qmeta = loaders.load_metadata(qmeta_path, len(queries),
                                      what="queries.metadata")
        if qts_field not in qmeta:
            raise intake.RequirementsError(
                f"{requirements_path}: corpus.sample.queries.metadata."
                f"timestamp_field {qts_field!r} is not a column in "
                f"{qmeta_path}; columns are {sorted(qmeta)[:10]}")
        query_timestamps = np.asarray(qmeta[qts_field])

    # ---- measure ----
    ch = characterize_arrays(
        base, queries, req.seed, timestamps=timestamps,
        query_timestamps=query_timestamps,
        cutoff=req.metadata.get("timestamp_cutoff"),
        count_min=req.count_min, log_fn=log_fn)

    # ---- projection (optional, declared, must not sink the run) ----
    projection_written = False
    if with_projection:
        try:
            proj = project(base, req.seed, log_fn=log_fn)
            if proj is not None:
                np.save(os.path.join(workdir, "projection.npy"), proj)
                projection_written = True
        except Exception as e:                        # noqa: BLE001
            log_fn(f"projection failed, continuing without it: {e}")

    # ---- receipts ----
    charj = {
        "run": req.name,
        "schema": intake.SCHEMA_VERSION,
        "n_base": int(len(base)),
        "n_queries": int(len(queries)),
        "dimension": int(dim),
        "definitions": {
            "centroids": N_CENTROIDS,
            "crispness_ratio": CRISP_RATIO,
            "ambiguity_ratio": AMBIGUOUS_RATIO,
            "seed": req.seed,
        },
        "characterization": ch,
    }
    write_json_stable(os.path.join(workdir, "characterization.json"),
                      round_floats(charj))
    write_json_stable(os.path.join(workdir, "sample_ids.json"), sample_ids)
    write_json_stable(os.path.join(workdir, "queries_ids.json"),
                      [str(q) for q in query_ids])

    versions, torch_info = library_versions(log=log_fn)
    inputs = {k: {"path": p, "sha256": sha256_file(p)}
              for k, p in req.input_paths().items()}
    build_info = {
        "kind": {
            "characterization.json": "receipt",
            "sample_ids.json": "receipt",
            "queries_ids.json": "receipt",
            "build_info.json": "declared",
        },
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "library_versions": versions,
        "oneground": producing_version(),
        # Which command wrote this, for the replay rule (task 046,
        # docs/INTERFACE.md section 2). Beside the version rather than
        # inside it: it is not a fact about the version.
        "invocation": invocation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "device": req.text.get("device", "cpu") if source_kind == "text" else None,
        "torch_cuda": torch_info["torch_cuda"],
        "cuda_device_name": torch_info["cuda_device_name"],
        "projection": ("projection.npy" if projection_written
                       else "not requested (--project)"),
        "source_kind": source_kind,
        "embedding_model": req.model,
        "weights_sha256": weights_sha,
        # Task 017 item 3. Declared, like everything else in this file: the
        # model reports what it cut, and nothing downstream can re-derive it
        # from the vectors -- a truncated vector looks exactly like a short
        # document's. `null` is couldn't-check (no tokenizer, or no text
        # path), and is deliberately not the same as 0.
        "max_seq_length": (truncation or {}).get("max_seq_length"),
        "truncated_count": (truncation or {}).get("truncated_count"),
        "truncation": truncation,
        "requirements_file": {"path": os.path.abspath(requirements_path),
                              "sha256": sha256_file(requirements_path)},
        # Which interpreter produced this, and whether it was running the
        # pins. `pinned: false` means the numbers above were computed outside
        # requirements.txt, and the artifact says so in its own bytes.
        "environment": env_stamp or environment.stamp(),
        "inputs": inputs,
    }
    write_json_stable(os.path.join(workdir, "build_info.json"), build_info)
    files = list(RECEIPT_FILES)
    if projection_written:
        # Declared, not a receipt: UMAP is seeded but not bit-stable across
        # BLAS builds. Its digest is still recorded.
        files.append("projection.npy")
        build_info["kind"]["projection.npy"] = "declared"
        write_json_stable(os.path.join(workdir, "build_info.json"), build_info)
    listed = write_manifest(workdir, files)

    _summary(req, charj, workdir, listed, time.time() - t0)
    return workdir


def run_declared(req, requirements_path, workdir, t0, log_fn=log,
                 env_stamp=None):
    """Tier 2: echo what was declared, measure nothing, claim nothing.

    There is no sample, so there is nothing to sample from and no ids to
    write. What this produces is a `characterization.json` shaped exactly like
    Tier 1's, with every measured field carrying
    `couldnt_check: declared, not measured`, and a `declared` block holding
    the inputs verbatim.

    Nothing here is a receipt. A receipt is re-derivable from seeds and rules;
    these are bytes the user typed, and `build_info.json` says so.
    """
    d = dict(req.declared)
    log_fn(f"declared corpus: {int(d['size_now']):,} vectors, dim "
           f"{int(d['dimension'])} -- Tier 2, nothing is measured")

    charj = {
        "run": req.name,
        "schema": intake.SCHEMA_VERSION,
        "tier": 2,
        "kind": "declared",
        # Shaped like Tier 1's so every reader works unchanged. `n_base` is
        # the size of the *sample*, and there is no sample -- `size_now` in
        # the declared block is the corpus the user says they have, which is
        # a different number and lives somewhere a reader cannot confuse it.
        "n_base": DECLARED_NOT_MEASURED,
        "n_queries": DECLARED_NOT_MEASURED,
        "dimension": DECLARED_NOT_MEASURED,
        "definitions": {
            "centroids": N_CENTROIDS,
            "crispness_ratio": CRISP_RATIO,
            "ambiguity_ratio": AMBIGUOUS_RATIO,
            "seed": req.seed,
            "note": ("the definitions a Tier-1 run would measure against. "
                     "Nothing in this file was measured."),
        },
        "characterization": {f: DECLARED_NOT_MEASURED
                             for f in MEASURED_FIELDS},
        "declared": d,
        "note": ("Tier 2. Every measured field is couldnt_check because there "
                 "is no sample to measure. The `declared` block is what the "
                 "user stated, echoed verbatim and taken as given. No verdict "
                 "can be issued from this file."),
    }
    write_json_stable(os.path.join(workdir, "characterization.json"), charj)

    versions, torch_info = library_versions(log=log_fn)
    build_info = {
        "kind": {
            # Declared, both of them. Nothing here is re-derivable from a seed
            # and a rule, which is what would make it a receipt.
            "characterization.json": "declared",
            "build_info.json": "declared",
        },
        "tier": 2,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "library_versions": versions,
        "oneground": producing_version(),
        # Which command wrote this, for the replay rule (task 046,
        # docs/INTERFACE.md section 2). Beside the version rather than
        # inside it: it is not a fact about the version.
        "invocation": invocation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "device": None,
        "torch_cuda": torch_info["torch_cuda"],
        "cuda_device_name": torch_info["cuda_device_name"],
        "projection": "not applicable (Tier 2 has no sample to project)",
        "source_kind": "declared",
        "embedding_model": d.get("embedding_model"),
        "weights_sha256": None,
        # Written as nulls rather than omitted, for the reason the field list
        # above is exhaustive: an absent field reads as "not measured" and a
        # null reads as "could not be". Tier 2 embeds nothing -- the corpus
        # was declared, not sampled -- so there is no text to truncate and no
        # tokenizer that saw it.
        "max_seq_length": None,
        "truncated_count": None,
        "truncation": None,
        "requirements_file": {"path": os.path.abspath(requirements_path),
                              "sha256": sha256_file(requirements_path)},
        # Which interpreter produced this, and whether it was running the
        # pins. `pinned: false` means the numbers above were computed outside
        # requirements.txt, and the artifact says so in its own bytes.
        "environment": env_stamp or environment.stamp(),
        "inputs": {},
    }
    write_json_stable(os.path.join(workdir, "build_info.json"), build_info)
    listed = write_manifest(workdir, DECLARED_FILES)
    _summary_declared(req, charj, workdir, listed, time.time() - t0)
    return workdir


def _summary_declared(req, charj, workdir, listed, elapsed):
    """The Tier-2 summary. Says what is missing and what would fix it."""
    d = charj["declared"]
    print()
    print("=" * 62)
    print(f"characterization — {req.name}   (Tier 2: declared)")
    print("=" * 62)
    print(f"  declared corpus   {int(d['size_now']):,} vectors, dim "
          f"{int(d['dimension'])}")
    if d.get("embedding_model"):
        print(f"  embedding model   {d['embedding_model']}")
    for key in ("corpus_type", "text_length", "topics_trend", "time_ordered"):
        if d.get(key) is not None:
            print(f"  {key:<17} {d[key]}")
    if d.get("languages"):
        print(f"  languages         {', '.join(str(x) for x in d['languages'])}")
    print()
    print("  measured          nothing. There is no sample in this file, so")
    print("                    every field below is couldn't-check:")
    for f in MEASURED_FIELDS:
        print(f"    {f:<26} {DECLARED_NOT_MEASURED}")
    print()
    print("  What would turn these into measurements: 10,000-20,000 vectors")
    print("  drawn stratified from the corpus, 50 or more real queries, and")
    print("  a timestamp column if drift matters. Put them under")
    print("  corpus.sample and this becomes a Tier-1 run.")
    print()
    print(f"  {len(listed)} file(s) + {MANIFEST_NAME} in {workdir}")
    print(f"  ({elapsed:.1f} s)")
    print()


def _summary(req, charj, workdir, listed, elapsed):
    """The plain-text summary. Never the word 'reproduced'."""
    ch = charj["characterization"]
    drift = ch.get("drift")
    print()
    print("=" * 62)
    print(f"characterization — {req.name}")
    print("=" * 62)
    print(f"  corpus            {charj['n_base']:,} vectors, dim "
          f"{charj['dimension']}")
    print(f"  queries           {charj['n_queries']:,}")
    print(f"  seed              {req.seed}")
    print()
    print(f"  intrinsic_dimensionality   {_fmt(ch['intrinsic_dimensionality'], 2)}"
          f"   of {charj['dimension']} declared")
    print(f"  boundary_crispness         "
          f"{_fmt(ch['boundary_crispness'])}   (d2 > {CRISP_RATIO} x d1, "
          f"{N_CENTROIDS} regions)")
    print(f"  ambiguous_query_rate       {_fmt(ch['ambiguous_query_rate'])}"
          f"   (d2 <= {AMBIGUOUS_RATIO} x d1)")
    print(f"  skew_top10_share           {_fmt(ch['skew_top10_share'])}"
          f"   (10 largest of {N_CENTROIDS} regions; even would be "
          f"{10 / N_CENTROIDS:.3f})")
    if isinstance(drift, dict):
        print(f"  drift  before / after      {_fmt(drift['drift_before'])} / "
              f"{_fmt(drift['drift_after'])}   (cutoff {drift['cutoff']}, "
              f"n={drift['drift_n_before']}/{drift['drift_n_after']})")
    else:
        print(f"  drift                      {drift}")
    print()
    print(f"  measured in {elapsed / 60:.1f} min. These are measurements of "
          "this corpus,")
    print("  not a comparison against anything.")
    print()
    print(f"  {len(listed)} artifacts + {MANIFEST_NAME} in {workdir}")
    print()
