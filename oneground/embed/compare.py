"""Comparing embedding models: three registers, and the refusal that keeps
them apart.

WHY THIS MODULE EXISTS
----------------------
Every sweep in this tool holds the vectors fixed and varies what is built over
them. Changing the embedding model changes the vectors, which changes the
ground truth, which invalidates every number computed against it. So a
comparison across models is not a sweep, and most of what a report normally
says cannot be said across one.

There are exactly three registers, and **the difference between them is
enforced here rather than explained in a caption**:

  COMPARABLE        the geometry a model produces over a corpus. Each is
                    measured against that model's own exact ground truth, and
                    comparing them is the point of the exercise.

  PER MODEL         recall@k and everything derived from it. Under model A it
                    is measured against A's true neighbours, under model B
                    against B's. **Both are correct and they answer different
                    questions.** Shown as observations, each naming its ground
                    truth. Never as a comparison.

  NOT MEASURABLE    whether model A's true neighbours are BETTER ANSWERS than
                    model B's. That needs relevance labels this tool does not
                    have. It is stated in the artifact, not left for a reader
                    to infer from the fact that nobody mentioned it.

A report that puts 0.932 and 0.941 side by side under one "recall" heading is
asserting something false. `ComparisonRefused` is what makes that a crash
rather than a caption nobody reads -- the same move as task 026's
accept-and-ignore refusal and task 034's knob-belongs-to-an-algorithm rule.

TWO CONFOUNDS THAT ARE NOT FINDINGS
-----------------------------------
**Dimension.** A 384-dimension model uses half the memory of a 768-dimension
one and searches faster, for reasons that have nothing to do with how well it
separates anything. Memory and latency belong to the dimension; geometry
belongs to the model. `dimension_attributable` keeps them apart so that
"smaller and faster" cannot be read as "better".

**Truncation.** Models have different `max_seq_length`, so the same corpus
truncates differently under each. A model that silently drops half of every
document will look distinctive -- and the distinctiveness is an artifact of
what it never read. `truncation_confound` flags a model whose rate differs
materially from the others, as a confound rather than a finding.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# the three registers
# --------------------------------------------------------------------------

#: Geometry. Properties of the embedding over the corpus, each measured
#: against that model's own ground truth. Comparing these is the point.
COMPARABLE = (
    "boundary_crispness",
    "intrinsic_dimensionality",
    "ambiguous_query_rate",
    "skew_top10_share",
    "drift",
    "routing_ceiling",
    "storage_amplification",
    "copies_p50",
    "copies_p95",
    "copies_p99",
    "copies_histogram",
)

#: Measured against ground truth that differs per model. Two values here are
#: two observations, never a comparison.
PER_MODEL = (
    "recall_at_1",
    "recall_at_10",
    "recall_at_100",
    "index_loss",
    "inv_ratio_at_10",
    "ceiling_at_10",
)

#: Not measurable by this tool at all, with or without more compute.
NOT_MEASURABLE = (
    "answer_quality",
    "relevance",
    "which_model_is_better",
)

NOT_MEASURABLE_STATEMENT = (
    "Whether one model's true neighbours are BETTER ANSWERS than another's is "
    "not measured here and cannot be, because it needs relevance labels this "
    "tool does not have. A crisper ground is not a better model: it is a "
    "corpus that this embedding separates more sharply, which is a fact about "
    "the geometry and not about whether the neighbours it returns answer "
    "anyone's question. Nothing in this artifact ranks the models."
)

PER_MODEL_STATEMENT = (
    "Each of these was measured against its own model's exact k-NN ground "
    "truth. Under one model recall is computed against that model's true "
    "neighbours; under another, against a different set. Both numbers are "
    "correct and they answer different questions, so they are listed per "
    "model with the ground truth named and are never subtracted, ranked or "
    "placed under one heading."
)

COMPARABLE_STATEMENT = (
    "These describe the geometry each model produces over the same documents. "
    "Each is measured against that model's own ground truth, which is what "
    "makes them comparable rather than in spite of it: they are properties of "
    "the arrangement, not scores against a shared answer key."
)

#: A truncation rate this far above the lowest is reported as a confound.
TRUNCATION_CONFOUND_DELTA = 0.05


class ComparisonRefused(ValueError):
    """A measure was asked to be compared across models that cannot be.

    Its own error rather than a logged warning, for the reason task 026
    refuses an unread key: the alternative is a number in a table that reads
    exactly like a number that means something.
    """


def register_of(measure):
    """Which of the three registers a measure belongs to, or None."""
    name = str(measure)
    if name in COMPARABLE:
        return "comparable"
    if name in PER_MODEL:
        return "per_model"
    if name in NOT_MEASURABLE:
        return "not_measurable"
    return None


def refuse_if_not_comparable(measures, where=""):
    """Raise unless every measure may be compared across models.

    Called by anything that builds a cross-model table. An unknown measure is
    refused too: a measure nobody has classified is not one this module can
    promise is comparable, and defaulting to "yes" is how the false table gets
    built.
    """
    bad, unknown = [], []
    for m in measures:
        register = register_of(m)
        if register == "comparable":
            continue
        if register is None:
            unknown.append(str(m))
        else:
            bad.append((str(m), register))
    if not bad and not unknown:
        return
    lines = []
    for name, register in bad:
        if register == "per_model":
            lines.append(
                "%s is measured against each model's own ground truth, so two "
                "values of it are two observations and not a comparison" % name)
        else:
            lines.append(
                "%s is not measurable by this tool at all: %s"
                % (name, NOT_MEASURABLE_STATEMENT))
    for name in unknown:
        lines.append(
            "%s is not classified. Add it to COMPARABLE, PER_MODEL or "
            "NOT_MEASURABLE in embed/compare.py, deliberately -- an "
            "unclassified measure is refused rather than assumed comparable"
            % name)
    raise ComparisonRefused(
        "refused to compare across embedding models%s:\n  - %s"
        % ((" in " + where) if where else "", "\n  - ".join(lines)))


# --------------------------------------------------------------------------
# what one model produced
# --------------------------------------------------------------------------

@dataclass
class ModelObservation:
    """One model's run over one corpus. Everything it produced, labelled.

    `ground_truth` is the digest of the exact k-NN this model's vectors were
    measured against. It is carried on every per-model number so that a value
    can never be printed without the answer key it was scored on.
    """

    model: str
    dimension: int
    max_seq_length: int
    weights_sha256: Optional[str] = None
    ground_truth_sha256: Optional[str] = None
    n_base: int = 0
    n_queries: int = 0
    comparable: Dict[str, Any] = field(default_factory=dict)
    per_model: Dict[str, Any] = field(default_factory=dict)
    truncation: Optional[Dict[str, Any]] = None
    embed_seconds: Optional[float] = None
    device: str = "cpu"

    def as_dict(self):
        return {
            "model": self.model,
            "dimension": int(self.dimension),
            "max_seq_length": int(self.max_seq_length),
            "weights_sha256": self.weights_sha256,
            "ground_truth_sha256": self.ground_truth_sha256,
            "n_base": int(self.n_base),
            "n_queries": int(self.n_queries),
            "comparable": dict(self.comparable),
            "per_model": dict(self.per_model),
            "truncation": self.truncation,
            "embed_seconds": self.embed_seconds,
            "device": self.device,
        }


def truncation_confound(observations):
    """Models whose truncation rate differs materially from the lowest.

    A model that read less of every document will look distinctive, and the
    distinctiveness is an artifact of what it never saw. Reported beside the
    measures as a confound -- never as a finding, and never silently.
    """
    rates = {}
    for o in observations:
        t = o.truncation or {}
        rate = t.get("truncated_fraction")
        if rate is not None:
            rates[o.model] = float(rate)
    if len(rates) < 2:
        return {"checked": False,
                "reason": "fewer than two models reported a truncation rate; "
                          "couldn't-check, not zero",
                "rates": rates, "flagged": []}
    lowest = min(rates.values())
    flagged = [
        {"model": name, "truncated_fraction": rate,
         "above_lowest": rate - lowest,
         "why": ("this model truncated %.1f%% of records against a lowest of "
                 "%.1f%%. It read less of the corpus than the others, so any "
                 "way its geometry differs is confounded with what it never "
                 "saw. A confound, not a finding."
                 % (100 * rate, 100 * lowest))}
        for name, rate in sorted(rates.items())
        if rate - lowest > TRUNCATION_CONFOUND_DELTA]
    return {"checked": True, "rates": rates, "lowest": lowest,
            "threshold": TRUNCATION_CONFOUND_DELTA, "flagged": flagged}


def dimension_attributable(observations):
    """What differs because of dimension rather than because of the model.

    Memory and search cost scale with dimension. Separated so that a reader
    cannot read "smaller and faster" as "better": those two axes are not the
    same axis and this block is where the difference is written down.
    """
    dims = {o.model: int(o.dimension) for o in observations}
    if not dims:
        return {"dimensions": {}, "note": NOT_MEASURABLE_STATEMENT}
    smallest = min(dims.values())
    return {
        "dimensions": dims,
        "bytes_per_vector": {m: 4 * d for m, d in dims.items()},
        "relative_to_smallest": {m: d / smallest for m, d in dims.items()},
        "note": (
            "float32 storage and the cost of every distance computation scale "
            "with dimension. A %d-dimension model uses %.1fx the memory of a "
            "%d-dimension one and scores each candidate proportionally slower, "
            "for reasons unrelated to how well it separates anything. Read "
            "memory and latency against this block, and geometry against the "
            "comparable measures. They are different axes."
            % (max(dims.values()), max(dims.values()) / smallest, smallest)),
    }


def build_comparison(observations, corpus=None, anchor=None):
    """The `models.json` payload: three registers, visibly different.

    Refuses rather than renders if a per-model measure has been placed in the
    comparable block -- the one mistake this whole module exists to prevent.
    """
    observations = list(observations)
    if not observations:
        raise ComparisonRefused("no model observations to compare")

    for o in observations:
        refuse_if_not_comparable(
            o.comparable, where="the comparable block for %s" % o.model)
        stray = [m for m in o.per_model if register_of(m) == "comparable"]
        if stray:
            raise ComparisonRefused(
                "%s reports %s under per_model, but %s comparable across "
                "models. Put it in `comparable`."
                % (o.model, ", ".join(sorted(stray)),
                   "it is" if len(stray) == 1 else "they are"))

    measures = []
    for name in COMPARABLE:
        present = {o.model: o.comparable.get(name) for o in observations
                   if name in o.comparable}
        if present:
            measures.append({"measure": name, "by_model": present})

    return {
        "schema": 1,
        "corpus": corpus,
        "anchor": anchor,
        "models": [o.as_dict() for o in observations],
        "comparable": {
            "statement": COMPARABLE_STATEMENT,
            "measures": measures,
        },
        "per_model": {
            "statement": PER_MODEL_STATEMENT,
            "by_model": {
                o.model: {
                    "ground_truth_sha256": o.ground_truth_sha256,
                    "values": dict(o.per_model),
                } for o in observations},
        },
        "not_measurable": {
            "statement": NOT_MEASURABLE_STATEMENT,
            "measures": list(NOT_MEASURABLE),
        },
        "confounds": {
            "dimension": dimension_attributable(observations),
            "truncation": truncation_confound(observations),
        },
    }


# --------------------------------------------------------------------------
# rendering -- one table, three registers, visibly different
# --------------------------------------------------------------------------

def render(comparison, width=78):
    """The comparison as text. The registers are separated by construction."""
    out = []
    models = [m["model"] for m in comparison["models"]]
    corpus = comparison.get("corpus") or "(unnamed corpus)"
    out.append("=" * width)
    out.append("embedding models on %s" % corpus)
    out.append("=" * width)
    out.append("")
    for m in comparison["models"]:
        trunc = m.get("truncation") or {}
        rate = trunc.get("truncated_fraction")
        out.append("  %-38s %4dd  max_seq %-5s %s"
                   % (m["model"], m["dimension"], m["max_seq_length"],
                      ("truncated %.1f%%" % (100 * rate))
                      if rate is not None else "truncation couldn't-check"))
        out.append("      weights %s   ground truth %s"
                   % ((m.get("weights_sha256") or "couldn't-check")[:16],
                      (m.get("ground_truth_sha256") or "couldn't-check")[:16]))
    out.append("")

    out.append("-" * width)
    out.append("COMPARABLE -- the geometry each model produces")
    out.append("-" * width)
    out.append(_wrap(comparison["comparable"]["statement"], width))
    out.append("")
    head = "  %-26s" % "measure" + "".join("%18s" % _short(m) for m in models)
    out.append(head)
    out.append("  " + "-" * (len(head) - 2))
    for row in comparison["comparable"]["measures"]:
        cells = "".join("%18s" % _fmt(row["by_model"].get(m)) for m in models)
        out.append("  %-26s%s" % (row["measure"], cells))
    out.append("")

    out.append("-" * width)
    out.append("PER MODEL -- NOT a comparison")
    out.append("-" * width)
    out.append(_wrap(comparison["per_model"]["statement"], width))
    out.append("")
    for model, block in comparison["per_model"]["by_model"].items():
        out.append("  %s" % model)
        out.append("      measured against ground truth %s"
                   % (block.get("ground_truth_sha256") or "couldn't-check")[:16])
        for name, value in sorted((block.get("values") or {}).items()):
            out.append("      %-24s %s" % (name, _fmt(value)))
    out.append("")

    out.append("-" * width)
    out.append("NOT MEASURABLE HERE")
    out.append("-" * width)
    out.append(_wrap(comparison["not_measurable"]["statement"], width))
    out.append("")

    out.append("-" * width)
    out.append("CONFOUNDS")
    out.append("-" * width)
    out.append(_wrap(comparison["confounds"]["dimension"]["note"], width))
    trunc = comparison["confounds"]["truncation"]
    out.append("")
    if not trunc.get("checked"):
        out.append(_wrap("  truncation: " + trunc.get("reason", ""), width))
    elif trunc["flagged"]:
        for f in trunc["flagged"]:
            out.append(_wrap("  CONFOUND  " + f["why"], width))
    else:
        out.append(_wrap(
            "  truncation: no model's rate exceeds the lowest by more than "
            "%.0f%%, so none is flagged. The rates are in the artifact."
            % (100 * trunc["threshold"]), width))
    return "\n".join(out)


def _short(model):
    return model.split("/")[-1][:17]


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return "%.4f" % v
    if isinstance(v, (list, tuple)):
        return "[%d]" % len(v)
    if isinstance(v, dict):
        return "{%d}" % len(v)
    return str(v)


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
