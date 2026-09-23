"""Running `characterize` once per embedding model, and comparing the results.

A COMPARISON IS N RUNS, NOT ONE RUN WITH N COLUMNS
--------------------------------------------------
Changing the embedding model changes the vectors, which changes the exact
k-NN ground truth, which invalidates every number computed against it. So this
module does not thread a model parameter through the measurement code; it runs
the whole measurement once per model, into its own workdir, and then builds a
comparison from the results.

That shape is deliberate and it is also the safe one. **`characterize.run` is
not modified.** A run naming one model takes exactly the path it took before
this module existed, produces exactly the same labels, and cannot be affected
by anything here -- which is what task 036 step 7 requires, because every
published fixture value was measured under one model on that path.

The orchestration is: resolve every model first, price the whole thing, print
the price, then run them one at a time.
"""

import copy
import json
import os
import time

from . import compare as C
from . import registry as R

#: How many records the cost probe embeds per model before the run starts.
PROBE_RECORDS = R.PROBE_RECORDS


def workdir_for(base, model_name):
    """`runs/<name>/models/<slug>` -- one model's whole run.

    Slugged rather than nested by org, so a workdir is one directory deep and
    a path never contains a character a filesystem will argue about.
    """
    slug = str(model_name).replace("/", "__").replace(" ", "_")
    return os.path.join(base, "models", slug)


def plan(req, texts, log_fn=print, device="cpu"):
    """Resolve every model and price the run, before any of them embeds.

    Returns `(resolved, projection)`. Raises `ModelUnresolved` on the first
    name that does not load -- eagerly, so a typo in the third name is caught
    before the first model spends an hour.
    """
    names = req.models
    log_fn("resolving %d model(s) before any of them runs" % len(names))
    resolved = R.resolve_all(names, device=device, log=log_fn)
    for rm in resolved:
        log_fn("  %-44s %4dd  max_seq %-5d weights %s"
               % (rm.name, rm.dimension, rm.max_seq_length,
                  (rm.weights_sha256 or "couldn't-check")[:16]))

    rates = []
    if texts:
        log_fn("pricing on %d real records per model" % min(PROBE_RECORDS,
                                                            len(texts)))
        for rm in resolved:
            rates.append(R.probe_rate(rm, texts))
    projection = R.project_cost(rates, len(texts) if texts else 0)
    return resolved, projection


def observation_from(run_output, resolved, truncation=None,
                     embed_seconds=None):
    """One model's `characterize` result, sorted into the three registers.

    The sorting is the whole point and it is done here rather than by each
    caller: a measure lands in `comparable` only if `compare.COMPARABLE` says
    it may, and anything unclassified is refused rather than quietly dropped.
    """
    char = dict(run_output.get("characterization") or run_output)
    comparable, per_model, unclassified = {}, {}, []
    for key, value in char.items():
        if isinstance(value, dict) and "value" in value:
            value = value["value"]
        register = C.register_of(key)
        if register == "comparable":
            comparable[key] = value
        elif register == "per_model":
            per_model[key] = value
        elif register is None:
            unclassified.append(key)
    return C.ModelObservation(
        model=resolved.name,
        dimension=resolved.dimension,
        max_seq_length=resolved.max_seq_length,
        weights_sha256=resolved.weights_sha256,
        ground_truth_sha256=run_output.get("ground_truth_sha256"),
        n_base=int(run_output.get("n_base") or 0),
        n_queries=int(run_output.get("n_queries") or 0),
        comparable=comparable,
        per_model=per_model,
        truncation=truncation,
        embed_seconds=embed_seconds,
        device=resolved.device,
    ), unclassified


def write_comparison(path, observations, corpus=None, anchor=None,
                     projection=None, unclassified=None):
    """`models.json`, plus the text rendering beside it."""
    payload = C.build_comparison(observations, corpus=corpus, anchor=anchor)
    if projection is not None:
        payload["cost"] = projection
    if unclassified:
        # Not silently dropped: a measure nobody has classified is a decision
        # somebody has to make, and it is recorded where they will see it.
        payload["unclassified_measures"] = {
            "measures": sorted(set(unclassified)),
            "note": ("these appeared in a characterization and are in none of "
                     "the three registers, so they are absent from every "
                     "table above. Classify them in embed/compare.py -- an "
                     "unclassified measure is never assumed comparable."),
        }
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
    text_path = os.path.splitext(path)[0] + ".txt"
    with open(text_path, "w", encoding="utf-8") as fh:
        fh.write(C.render(payload) + "\n")
    return payload


def run(req, requirements_path, workdir, characterize_run, log_fn=print,
        device="cpu", texts_for_pricing=None):
    """Characterize once per model and write the comparison.

    `characterize_run` is injected rather than imported so this module can be
    tested without loading a model or importing the measurement stack.
    """
    names = req.models
    if len(names) < 2:
        raise ValueError(
            "multimodel.run is for two or more models; one model takes "
            "characterize.run unchanged, which is what keeps published "
            "labels and values where they are")

    resolved, projection = plan(req, texts_for_pricing or [], log_fn=log_fn,
                                device=device)
    log_fn("")
    log_fn(R.render_cost(projection))

    observations, unclassified = [], []
    for rm in resolved:
        sub = copy.deepcopy(req)
        sub.text["model"] = rm.name
        sub.text.pop("models", None)
        sub.run["workdir"] = workdir_for(workdir, rm.name)
        log_fn("=" * 70)
        log_fn("model %d of %d: %s" % (len(observations) + 1, len(resolved),
                                       rm.name))
        log_fn("=" * 70)
        t0 = time.time()
        out = characterize_run(sub, rm)
        seconds = time.time() - t0
        obs, stray = observation_from(out, rm,
                                      truncation=out.get("truncation"),
                                      embed_seconds=out.get("embed_seconds",
                                                            seconds))
        observations.append(obs)
        unclassified.extend(stray)

    path = os.path.join(workdir, "models.json")
    payload = write_comparison(path, observations,
                               corpus=getattr(req, "name", None),
                               anchor=names[0], projection=projection,
                               unclassified=unclassified)
    log_fn("")
    log_fn(C.render(payload))
    log_fn("")
    log_fn("wrote %s and %s" % (path, os.path.splitext(path)[0] + ".txt"))
    return payload
