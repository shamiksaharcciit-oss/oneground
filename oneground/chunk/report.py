"""The chunking report: the captions, the declaration, and the one judgement.

Three things live here, and they are here together because each exists to stop
a number being read as more than it is.

**The extraction declaration.** oneground takes extracted text and does not
run extractors, so what produced the text is declared and carried onto every
result. A chunking measured under one extraction may not hold under another,
and two results from differently-extracted text are two observations, never a
comparison. `unknown` is accepted -- a user often does not know -- but only
with a stated reason, because "unknown" with no reason is indistinguishable
from nobody having asked.

**The captions.** The over-fragmentation bias beside every path B column, and
the transfer caveat beside the numbers rather than in a footnote. They are
fields of the result object, not strings a renderer is trusted to remember.

**The fragmented flag**, which is the only place this report makes a
judgement about a strategy. It therefore gets what a verdict gets: both
thresholds stated, the basis stated, and -- enforced by construction -- the
length distribution that justifies it carried inside the flag, so the flag
cannot be rendered without the evidence beside it.

Neither threshold has a default. A floor of "whatever the code happened to
pick" is how a judgement becomes folklore, and the absence of a threshold
makes the flag `couldnt_check`, never `not_flagged`: not flagged would read
as "this strategy is fine", which is a claim nobody made.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .selfretrieval import BIAS_CAPTION, UPPER_BOUND_CAVEAT

TRANSFER_CAVEAT = (
    "A chunking measured under one extraction may not hold under another. "
    "These numbers are conditional on the extraction declared above: two "
    "results from differently-extracted text are two observations, never a "
    "comparison."
)

FRAGMENTED_CAPTION = (
    "FRAGMENTED. This strategy's self-retrieval is high and its median chunk "
    "is below the stated floor -- the combination the bias caption warns "
    "about. Self-retrieval is maximised by chunks too small to answer with, "
    "so a high score bought by short chunks is the measure being gamed rather "
    "than the corpus being served. Not recommended. The length distribution "
    "that this rests on is printed beside it."
)


class DeclarationError(ValueError):
    """The extraction declaration is missing or incomplete."""


@dataclass(frozen=True)
class Extraction:
    """What produced the text. Declared, never run and never verified.

    oneground does not run extractors and takes no responsibility for one, so
    this is a statement carried onto the result rather than something checked.
    A reader knows what the result is conditional on; nobody claims it is true.
    """

    tool: str
    version: Optional[str] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if not self.tool:
            raise DeclarationError(
                "an extraction declaration is required: name the tool that "
                "produced this text and its version, or 'unknown' with a "
                "reason. oneground does not run extractors, so what produced "
                "the text cannot be inferred and must be stated.")
        if self.tool == "unknown":
            if not self.reason:
                raise DeclarationError(
                    "extraction 'unknown' needs a reason. Unknown with no "
                    "reason is indistinguishable from nobody having asked, "
                    "and the reader cannot tell which they are looking at.")
        elif not self.version:
            raise DeclarationError(
                f"extraction tool {self.tool!r} needs its version: an "
                f"extractor's output changes between releases, so a result "
                f"conditional on it is conditional on which one.")

    def as_dict(self):
        return {"tool": self.tool, "version": self.version,
                "reason": self.reason, "run_by_oneground": False,
                "verified_by_oneground": False}


@dataclass(frozen=True)
class FragmentedFlag:
    """The report's only judgement about a strategy.

    `evidence` is the length distribution. It is a required field rather than
    something the renderer looks up, so the flag literally cannot exist
    without the numbers that justify it.
    """

    outcome: str                      # flagged | not_flagged | couldnt_check
    evidence: Dict[str, Any]
    floor: Optional[int] = None
    high_self_recall: Optional[float] = None
    length_p50: Optional[int] = None
    self_recall_at_k: Optional[float] = None
    basis: str = ""
    caption: str = ""
    reason: str = ""

    def as_dict(self):
        d = {
            "outcome": self.outcome,
            "basis": self.basis,
            "thresholds": {"length_p50_floor": self.floor,
                           "high_self_recall": self.high_self_recall},
            "measured": {"length_p50": self.length_p50,
                         "self_recall_at_k": self.self_recall_at_k},
            "length_distribution": self.evidence,
        }
        if self.caption:
            d["caption"] = self.caption
        if self.reason:
            d["reason"] = self.reason
        return d


BASIS = (
    "A strategy is flagged fragmented when its median chunk is below the "
    "stated floor AND its self-retrieval is at or above the stated high "
    "threshold. Either alone is not the fault: short chunks with a poor score "
    "are simply a poor chunking, and a high score with sound lengths is the "
    "result the measure exists to find. The two together are the measure "
    "being gamed -- self-retrieval rises as chunks shrink and is maximised by "
    "chunks too small to answer with. Both thresholds are the caller's and "
    "are printed; neither has a default, because a floor nobody chose is how "
    "a judgement becomes folklore."
)


def fragmented_flag(length_distribution, self_recall_at_k, floor=None,
                    high_self_recall=None):
    """The judgement, with its thresholds, its basis and its evidence.

    Returns `couldnt_check` -- never `not_flagged` -- when a threshold is
    missing. "Not flagged" would read as "this strategy is fine", which is a
    claim nobody made.
    """
    p50 = length_distribution.get("p50")
    if floor is None or high_self_recall is None:
        missing = [n for n, v in (("floor", floor),
                                  ("high_self_recall", high_self_recall))
                   if v is None]
        return FragmentedFlag(
            outcome="couldnt_check", evidence=length_distribution,
            floor=floor, high_self_recall=high_self_recall,
            length_p50=p50, self_recall_at_k=self_recall_at_k, basis=BASIS,
            reason=(f"no {' and no '.join(missing)} was stated, so the "
                    f"judgement was not made. This is couldnt_check and not "
                    f"'not flagged': not flagged would read as an assurance "
                    f"nobody gave."))
    flagged = (p50 is not None and p50 < floor
               and self_recall_at_k is not None
               and self_recall_at_k >= high_self_recall)
    return FragmentedFlag(
        outcome="flagged" if flagged else "not_flagged",
        evidence=length_distribution, floor=floor,
        high_self_recall=high_self_recall, length_p50=p50,
        self_recall_at_k=self_recall_at_k, basis=BASIS,
        caption=FRAGMENTED_CAPTION if flagged else "")


@dataclass(frozen=True)
class StrategyResult:
    """One strategy's A columns, B columns, and the captions that govern them."""

    strategy: str
    params: Dict[str, Any]
    chunks: int
    path_a: Dict[str, Any]
    path_b: Dict[str, Any]
    flag: FragmentedFlag
    embed_seconds: Optional[float] = None
    notes: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self):
        return {
            "strategy": self.strategy,
            "params": self.params,
            "chunks": self.chunks,
            "path_a": self.path_a,
            "path_b": self.path_b,
            "fragmented": self.flag.as_dict(),
            "embed_seconds": self.embed_seconds,
            "captions": {
                "over_fragmentation_bias": BIAS_CAPTION,
                "self_retrieval_is_an_upper_bound": UPPER_BOUND_CAVEAT,
            },
            "notes": self.notes,
        }


def chunking_report(results, extraction, corpus=None, embed_note=None):
    """Assemble the report. Refuses without an extraction declaration.

    `results` is a list of `StrategyResult`. A and B are returned side by side
    per strategy, which is the point: the paper shows them together precisely
    so a reader sees when they disagree.
    """
    if not isinstance(extraction, Extraction):
        raise DeclarationError(
            "chunking_report needs an Extraction declaration; results are "
            "conditional on what produced the text and the declaration is "
            "carried onto every one of them.")
    return {
        "stage": "chunking",
        "corpus": corpus,
        "extraction": extraction.as_dict(),
        "captions": {
            "over_fragmentation_bias": BIAS_CAPTION,
            "self_retrieval_is_an_upper_bound": UPPER_BOUND_CAVEAT,
            "extraction_transfer": TRANSFER_CAVEAT,
        },
        "embedding_cost": embed_note,
        "strategies": [r.as_dict() for r in results],
    }
