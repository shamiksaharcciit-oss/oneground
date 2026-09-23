"""Resolving an embedding model, and saying what it will cost before it runs.

A model is **declared by name and resolved against the library**, not chosen
from a list this project maintains. Any `sentence-transformers` model that
resolves is usable; one that does not is refused naming what was tried, so a
typo does not become a download attempt that fails forty minutes in.

What the user declares is the **name**. What the model declares is its
`dimension` and `max_seq_length`, and those are read from it rather than
accepted from the requirements file -- a declared dimension that disagreed
with the model's would be a number nobody could act on, and the vectors would
be whatever the model actually produces either way.

WHY COST IS REPORTED BEFORE THE FIRST MODEL RUNS
------------------------------------------------
Comparing N models costs N of everything: N embedding passes, N exact k-NN
ground truths, N characterizations, N sweeps. Nothing is shared but the
documents. That is not obvious from `models: [a, b, c]` -- it reads like one
run with three columns -- and a user who learns it after starting has already
spent the time.

Embedding is **token-bound, not record-bound**, which is the part that makes
estimates from record counts wrong. Measured on the developer's laptop
(4 logical cores, torch defaulting to 2 threads), `bge-base-en-v1.5` runs at
roughly 270 tokens/second: 42-token records at 6.5/s and 552-token records at
0.5/s, a 13x spread from a 13x difference in length. So the projection takes a
sample of the real text, tokenizes it with the model's own tokenizer, and
scales -- rather than multiplying a record count by a rate somebody once saw.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import count_truncated, embed as _embed, load_model

#: What a cost projection is allowed to extrapolate from. Small enough to be
#: cheap, large enough that a mean token count means something.
PROBE_RECORDS = 64


class ModelUnresolved(ValueError):
    """Base: a model name that could not be resolved.

    Kept as the base so `except ModelUnresolved` still catches every case,
    and **raised directly only where a typo and an unreachable hub genuinely
    cannot be told apart** -- which is one of the three sites below.

    It used to be the only class here, and its own docstring carried the
    defect: *the two common causes -- a typo and no network -- need
    different actions from the reader, and the underlying exception
    distinguishes them badly*. That put the distinction in the message,
    where a person can act on it and no caller can. The two subclasses are
    the same distinction moved into the type, for the sites that know.
    """


class ModelUnknown(ModelUnresolved):
    """The name is wrong on its face. **A refusal.**

    Decided from the request alone, without asking anything outside this
    process, so no environment can make it wrong.
    """


class ModelUnusable(ModelUnresolved):
    """The model loaded and cannot be used. **A failure.**

    The name resolved, so nothing the user wrote is wrong.
    """


@dataclass
class ResolvedModel:
    """One embedding model, resolved, with what it says about itself."""

    name: str
    dimension: int
    max_seq_length: int
    weights_sha256: Optional[str]
    device: str = "cpu"
    model: Any = None

    def as_dict(self):
        return {"model": self.name, "dimension": int(self.dimension),
                "max_seq_length": int(self.max_seq_length),
                "weights_sha256": self.weights_sha256, "device": self.device}


def resolve(name, device="cpu", max_seq_length=None, log=None):
    """Load a model and read its own dimension and sequence limit.

    `max_seq_length` overrides the model's declared limit when given. It is an
    override rather than a declaration: the default is whatever the model says,
    and a run that sets it records that it did.
    """
    try:
        model, weights = load_model(
            name, device=device,
            max_seq_length=(max_seq_length if max_seq_length is not None
                            else _declared_limit(name)), log=log)
    except Exception as e:                                     # noqa: BLE001
        # THE BASE, DELIBERATELY. This is the one site where a typo and an
        # unreachable hub cannot be told apart: sentence-transformers raises
        # much the same thing for both, which is what the base's docstring
        # has always said. Guessing here is the failure the split exists to
        # prevent -- calling it a refusal would tell a user with a broken
        # network that the tool meant it and send them to fix a name that
        # was never wrong. The message already carries both readings, in
        # order, for the person who can tell.
        raise ModelUnresolved(
            "could not resolve embedding model %r on device %r: %s: %s. "
            "The name is passed to sentence-transformers unchanged, so it must "
            "be one it can load -- a HuggingFace repo id such as "
            "'BAAI/bge-base-en-v1.5', or a local path. If the name is right, "
            "the next thing to check is whether this machine can reach the "
            "model hub."
            % (name, device, type(e).__name__, e)) from None

    model._oneground_name = name
    dim = _dimension_of(model)
    limit = int(getattr(model, "max_seq_length", 0) or 0)
    if not dim:
        # It loaded, so the name was right and nothing the user wrote is
        # wrong. A failure.
        raise ModelUnusable(
            "%r loaded but reports no embedding dimension, so nothing "
            "downstream can size an index for it" % name)
    return ResolvedModel(name=name, dimension=int(dim), max_seq_length=limit,
                         weights_sha256=weights, device=device, model=model)


def _declared_limit(name):
    """The model's own limit, before it is loaded. None means 'ask the model'.

    `load_model` takes a limit and sets it, so passing the project's old
    hard-coded 512 would silently impose it on a model declaring something
    else. Returning None here means `load_model` is handed the model's own
    value in `resolve`, which reads it back afterwards.
    """
    return None


def _dimension_of(model):
    for attr in ("get_sentence_embedding_dimension", "get_embedding_dimension"):
        fn = getattr(model, attr, None)
        if callable(fn):
            try:
                return int(fn())
            except Exception:                                  # noqa: BLE001
                continue
    return 0


def resolve_all(names, device="cpu", log=None):
    """Resolve every model before any of them runs.

    Deliberately eager: a typo in the third name should be refused before the
    first model spends an hour embedding, not after.
    """
    seen, out = set(), []
    for name in names:
        if name in seen:
            # Decided from the list itself. No network, no filesystem, no
            # way for an environment to make this wrong: a refusal.
            raise ModelUnknown(
                "model %r is listed twice. Each model is its own run of "
                "everything; listing one twice would measure it twice under "
                "one label." % name)
        seen.add(name)
        out.append(resolve(name, device=device, log=log))
    return out


# --------------------------------------------------------------------------
# cost, projected from the model's own tokenizer on the real text
# --------------------------------------------------------------------------

def probe_rate(resolved, texts, records=PROBE_RECORDS):
    """Measured tokens/second and records/second for this model on this text.

    Returns the measurement, not an estimate: it embeds a real slice of the
    real corpus. `tokens_per_second` is the portable number -- records/second
    is only meaningful for text of this length.
    """
    sample = [str(t) for t in texts[:records]]
    if not sample:
        return None
    tok = getattr(resolved.model, "tokenizer", None)
    n_tokens = None
    if tok is not None:
        try:
            ids = tok(sample, add_special_tokens=True, truncation=True,
                      max_length=resolved.max_seq_length or 512,
                      padding=False)["input_ids"]
            n_tokens = sum(len(i) for i in ids)
        except Exception:                                      # noqa: BLE001
            n_tokens = None
    t0 = time.time()
    _embed(resolved.model, sample, batch=min(32, len(sample)),
           show_progress_bar=False)
    seconds = max(time.time() - t0, 1e-9)
    return {
        "model": resolved.name,
        "probe_records": len(sample),
        "probe_seconds": seconds,
        "records_per_second": len(sample) / seconds,
        "tokens_per_second": (n_tokens / seconds) if n_tokens else None,
        "mean_tokens_per_record": (n_tokens / len(sample)) if n_tokens else None,
        "measured_on": "this machine, this text, at the model's own limit",
    }


def project_cost(rates, n_records, models=None):
    """What the whole comparison will cost, from measured rates.

    `rates` is `[probe_rate(...)]`. Returns per-model seconds and the total,
    with the multiplication spelled out -- the point is that a reader sees
    "three models is three of everything" before the first one starts.
    """
    per_model, total = [], 0.0
    for r in rates:
        if not r:
            continue
        seconds = n_records / max(r["records_per_second"], 1e-9)
        total += seconds
        per_model.append({
            "model": r["model"],
            "records": int(n_records),
            "records_per_second": r["records_per_second"],
            "tokens_per_second": r.get("tokens_per_second"),
            "embed_seconds": seconds,
            "embed_hours": seconds / 3600.0,
        })
    return {
        "n_records": int(n_records),
        "n_models": len(per_model),
        "per_model": per_model,
        "embed_seconds_total": total,
        "embed_hours_total": total / 3600.0,
        "what_else_scales": (
            "Embedding only. Each model also needs its own exact k-NN ground "
            "truth, its own characterization and its own simulate, because "
            "none of those can be shared across models: different vectors, "
            "different neighbours, different answer key. %d model(s) is %d of "
            "everything." % (len(per_model), len(per_model))),
        "measured_not_estimated": (
            "Rates were measured by embedding a sample of this corpus's real "
            "text with each model's own tokenizer and weights. Embedding is "
            "token-bound rather than record-bound, so a rate taken from "
            "another corpus would be wrong in proportion to how much the "
            "record lengths differ."),
    }


def render_cost(projection, width=78):
    """The cost block, for printing before the first model runs."""
    out = ["=" * width,
           "COST, measured on this corpus before anything is embedded",
           "=" * width, ""]
    out.append("  %-42s %10s %10s %8s"
               % ("model", "rec/s", "tok/s", "hours"))
    out.append("  " + "-" * 72)
    for p in projection["per_model"]:
        out.append("  %-42s %10.1f %10s %8.1f"
                   % (p["model"], p["records_per_second"],
                      ("%.0f" % p["tokens_per_second"])
                      if p.get("tokens_per_second") else "-",
                      p["embed_hours"]))
    out.append("  " + "-" * 72)
    out.append("  %-42s %10s %10s %8.1f"
               % ("TOTAL over %d records" % projection["n_records"], "", "",
                  projection["embed_hours_total"]))
    out.append("")
    for key in ("what_else_scales", "measured_not_estimated"):
        out.append(_wrap(projection[key], width))
        out.append("")
    return "\n".join(out)


def _wrap(text, width, indent="  "):
    words, lines, line = str(text).split(), [], indent
    for w in words:
        if len(line) + len(w) + 1 > width:
            lines.append(line)
            line = indent + w
        else:
            line = (line + " " + w) if line.strip() else indent + w
    if line.strip():
        lines.append(line)
    return "\n".join(lines)


__all__ = ["ModelUnresolved", "ResolvedModel", "resolve", "resolve_all",
           "probe_rate", "project_cost", "render_cost", "count_truncated"]
