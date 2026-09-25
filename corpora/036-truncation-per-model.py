"""Truncation per model, on the same records the ordering experiment used.

Step 5: models declare different `max_seq_length`, so the same corpus
truncates differently under each, and a model that read less of every record
will look distinctive for a reason that has nothing to do with its geometry.

Tokenizer only -- no embedding -- so this is minutes rather than hours. The
records are drawn with the same seed and the same subsample as
036-ordering-experiment, so these rates describe exactly the vectors that
experiment measured.
"""
import json
import os
import sys

import numpy as np

# See corpora/036-ordering-experiment.py's own comment: anchored to
# __file__, matching the majority convention in this directory
# (corpora/build_fixture.py, corpora/export_ground_view.py,
# corpora/run_chunking.py), not the caller's cwd. This file's own previous
# `os.path.abspath(".")` was the minority form that happened to work
# because `run_036_models.sh` always `cd`s to the repo root first -- which
# is exactly the kind of route-dependent correctness `tasks/finding-a-
# check-that-takes-a-different-route-than-production.md` is about.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..")))

from oneground.embed import count_truncated                     # noqa: E402
from oneground.embed.compare import (                            # noqa: E402
    truncation_confound, ModelObservation)
from oneground.embed.registry import resolve                    # noqa: E402

# Reuse the experiment's own corpus construction so the records are
# identical. Path built from __file__, not a bare relative string, for the
# same reason the sys.path insert above is.
import importlib.util                                            # noqa: E402
spec = importlib.util.spec_from_file_location(
    "ordering", os.path.join(_HERE, "036-ordering-experiment.py"))
ordering = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ordering)

# Overridable the same way `036-ordering-experiment.py`'s own `OUT` is
# (`ONEGROUND_036_OUT`). Task 073's own report: the hardcoded default sat
# outside `run_036_models.sh`'s packaged `$OUT_DIR`, so the fresh file
# never reached the fetch and a later local read of this path silently
# returned a stale copy from earlier, unrelated local work -- production
# wrote one file, the read found another, and both were real files at
# real paths.
OUT = os.environ.get("ONEGROUND_036_TRUNC_OUT",
                     "tasks/scratch/036-truncation-results.json")

results = {}
texts_by_corpus = {}
for corpus, fn in ordering.CORPORA.items():
    picked, total = ordering.subsample(fn(), ordering.N_BASE)
    texts_by_corpus[corpus] = picked
    print("%-22s %d records, mean %d chars"
          % (corpus, len(picked), int(np.mean([len(t) for t in picked]))))
print()

for name in ordering.MODELS:
    rm = resolve(name, device="cpu")
    print("=== %s  %dd  max_seq %d" % (rm.name, rm.dimension,
                                       rm.max_seq_length))
    for corpus, texts in texts_by_corpus.items():
        t = count_truncated(rm.model, texts,
                            max_seq_length=rm.max_seq_length)
        # What the model actually READ, which is the number the ordering has
        # to be read against: the truncated fraction says how often it cut,
        # and this says how much reached the encoder on average.
        ids = rm.model.tokenizer(
            [str(x) for x in texts], add_special_tokens=True, truncation=True,
            max_length=rm.max_seq_length, padding=False)["input_ids"]
        mean_tokens = float(np.mean([len(i) for i in ids]))
        results.setdefault(corpus, {})[name] = {
            **(t or {}), "max_seq_length": rm.max_seq_length,
            "dimension": rm.dimension, "mean_tokens": mean_tokens}
        if t:
            print("   %-22s %5d of %d truncated (%.1f%%), longest %d tokens"
                  % (corpus, t["truncated_count"], t["n_records"],
                     100 * t["truncated_fraction"], t["longest_tokens"]))
        else:
            print("   %-22s couldn't-check" % corpus)
    del rm
    print()

print("CONFOUND CHECK, per corpus")
for corpus, by_model in results.items():
    obs = [ModelObservation(model=m, dimension=v["dimension"],
                            max_seq_length=v["max_seq_length"],
                            truncation=v)
           for m, v in by_model.items()]
    got = truncation_confound(obs)
    flagged = [f["model"] for f in got["flagged"]]
    print("  %-22s rates %s  -> %s"
          % (corpus,
             {m.split("/")[-1]: round(r, 3) for m, r in got["rates"].items()},
             ("FLAGGED " + ", ".join(flagged)) if flagged else "none flagged"))

json.dump(results, open(OUT, "w", encoding="utf-8"), indent=1)
print()
print("wrote %s" % OUT)
