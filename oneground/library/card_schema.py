"""What a publishable library card must carry, and the refusals that keep
one that cannot from being published. `docs/LIBRARY.md` §2, §5.

**A library card is a different artifact from the private card `propose`
writes** (`docs/LIBRARY.md` §2.0: "That is the right shape for a private
receipt and the wrong shape for a public one."). This module does not read
`oneground/proposals/card.py`'s `card.json` and does not build one; it
validates whatever dict a caller submits against the shape §2 requires. How
that dict gets built -- from a private card, by hand, or by a later tool --
is outside this module's scope, per §7's own sequencing: the schema and its
refusals come before the capability that produces cards to feed it.

Every required path below is a dotted key into the submitted dict, walked
generically by `_get`. A path is **missing** when the key is absent at any
level; a handful of paths may be **present and `None`** (the embedding
model, `docs/LIBRARY.md` §2.1's "declared, not measured" case) and are
listed in `MAY_BE_NULL` rather than silently exempted from the walk.
"""

MISSING = object()


def _get(d, dotted_path):
    """Walk a dotted path through nested dicts. `MISSING` if any level
    is absent; the real value (possibly `None`) if every level exists."""
    cur = d
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return MISSING
        cur = cur[part]
    return cur


class LibraryCardRefused(ValueError):
    """A card could not be published as submitted. The message names every
    reason at once, `fixture verify`'s own refusal shape
    (`docs/LIBRARY.md` §5: "refuses with every missing field named at
    once")."""


# --------------------------------------------------------------------------
# §2.1 -- the corpus, so a reader can locate it relative to their own
# --------------------------------------------------------------------------

CORPUS_REQUIRED = (
    "corpus.vectors_sha256",
    "corpus.characterization.intrinsic_dimensionality",
    "corpus.characterization.boundary_crispness",
    "corpus.characterization.skew_top10_share",
    "corpus.characterization.ambiguous_query_rate",
    "corpus.characterization.drift_before",
    "corpus.characterization.drift_after",
    "corpus.characterization.drift_cutoff",
    "corpus.characterization.definitions.crispness_ratio",
    "corpus.characterization.definitions.ambiguity_ratio",
    "corpus.characterization.definitions.centroids",
    "corpus.characterization.definitions.seed",
    "corpus.dimension",
    "corpus.n_base",
    "corpus.n_queries",
    "corpus.documents.domain",
    "corpus.documents.language",
    "corpus.documents.typical_length",
    "corpus.full_size",
    "corpus.sample_size",
    "corpus.sampling_seed",
    "corpus.resolvability",
)

# §2.1: "The embedding model is a publisher assertion... For a corpus
# supplied as vectors... build_info.embedding_model is null... A
# requirement that refuses most cards is a defect in the requirement." The
# KEY is required; the VALUE may honestly be null.
MAY_BE_NULL = ("corpus.embedding_model",)


# --------------------------------------------------------------------------
# §2.2 -- the instrument, so two cards can be compared at all
# --------------------------------------------------------------------------

INSTRUMENT_REQUIRED = (
    "instrument.oneground.baseline",
    "instrument.oneground.changed",
    "instrument.deterministic",
    "instrument.repeats",
    "instrument.hardware.cpu",
    "instrument.hardware.cores",
    "instrument.hardware.ram",
    "instrument.hardware.threads",
    "instrument.calibration_line",
    "instrument.comparability.verdict",
    "instrument.comparability.reason",
)

COMPARABLE = "comparable"
NOT_COMPARABLE = "not_comparable"
COULDNT_CHECK = "couldnt_check"
COMPARABILITY_VALUES = (COMPARABLE, NOT_COMPARABLE, COULDNT_CHECK)


# --------------------------------------------------------------------------
# §2.3 -- the finding, so it can be read rather than decoded
# --------------------------------------------------------------------------

FINDING_REQUIRED = (
    "finding.baseline_metrics",
    "finding.changed_metrics",
    "finding.threshold_basis",
    "finding.verified",
    "finding.cost",
    "card_id",
    "publisher",
    "licence",
)

# §2.3: "the routing/index decomposition... read by a sentence" -- required
# as a KEY (so a card cannot omit the question), the value may be null with
# a reason when the family has no such decomposition.
MAY_BE_NULL = MAY_BE_NULL + ("finding.decomposition",)


# --------------------------------------------------------------------------
# §2.4 -- the denominator
# --------------------------------------------------------------------------

DENOMINATOR_WITHHELD = "withheld"


def _denominator_problem(card):
    d = _get(card, "denominator")
    if d is MISSING:
        return ("denominator is missing. §2.4: 'A library that cannot show "
                "its denominator cannot be read as evidence, only as "
                "advertising.' Carry proposals_run_on_this_corpus and "
                "proposals_published, or denominator: "
                f"{DENOMINATOR_WITHHELD!r} if the publisher will not "
                "disclose them.")
    if d == DENOMINATOR_WITHHELD:
        return None
    if isinstance(d, dict):
        keys = ("proposals_run_on_this_corpus", "proposals_published")
        missing = [k for k in keys if not isinstance(d.get(k), int)]
        if not missing:
            return None
        return ("denominator is present but missing or non-integer "
                f"{', '.join(missing)}. A partial denominator is a soft "
                "number beside hard ones, which §2.4 says is worse than "
                f"none; carry both counts or denominator: "
                f"{DENOMINATOR_WITHHELD!r}.")
    return (f"denominator is {d!r}, neither a counts dict nor "
           f"{DENOMINATOR_WITHHELD!r}.")


# --------------------------------------------------------------------------
# §5 -- submission, and the two refusals worth naming
# --------------------------------------------------------------------------

def _prediction_problem(card):
    cited = _get(card, "prediction.cited_by_run")
    digest = _get(card, "prediction.digest")
    if digest is MISSING or not digest:
        return ("prediction.digest is missing. §5: 'The pre-registration "
                "is the whole claim; a card that cannot show the "
                "prediction preceded the measurement is not a card.'")
    if cited is not True:
        return ("prediction.cited_by_run is not true (digest "
                f"{digest!r}). §5: a card whose prediction digest is not "
                "cited by the run that produced it is not a card -- this "
                "is refused outright, not published couldnt_check.")
    return None


def _comparability_problem(card):
    verdict = _get(card, "instrument.comparability.verdict")
    if verdict is MISSING:
        return None            # already named by INSTRUMENT_REQUIRED
    if verdict not in COMPARABILITY_VALUES:
        return (f"instrument.comparability.verdict is {verdict!r}, not one "
                f"of {COMPARABILITY_VALUES}.")
    if verdict == NOT_COMPARABLE:
        return ("instrument.comparability.verdict is not_comparable. §5: "
                "'If the baseline and the change are known to have been "
                "measured by different code or in different environments, "
                "the card says so and is not published as a result.' It "
                "may be published as a separate, clearly labelled "
                "observation -- this module does not build that path.")
    return None                # comparable and couldnt_check both publish


# --------------------------------------------------------------------------
# the validator
# --------------------------------------------------------------------------

def submit_card(card):
    """§5: validate a library card against the whole required set at once.

    Raises `LibraryCardRefused` naming every problem found -- every missing
    field, together, not the first one hit -- if the card cannot be
    published as submitted. Returns nothing on success; a card that passes
    is publishable, not published (this module has no submission surface).
    """
    problems = []

    for group_name, required in (("§2.1 corpus", CORPUS_REQUIRED),
                                 ("§2.2 instrument", INSTRUMENT_REQUIRED),
                                 ("§2.3 finding", FINDING_REQUIRED)):
        missing = [p for p in required
                  if _get(card, p) is MISSING
                  or (_get(card, p) is None and p not in MAY_BE_NULL)]
        if missing:
            problems.append(
                f"{group_name} is missing: {', '.join(missing)}")

    for path in MAY_BE_NULL:
        if _get(card, path) is MISSING:
            problems.append(f"{path} must be present (may be null, may "
                            "not be absent)")

    verdict = _get(card, "instrument.comparability.verdict")
    if verdict not in (MISSING, *COMPARABILITY_VALUES):
        problems.append(f"instrument.comparability.verdict is {verdict!r}, "
                        f"not one of {COMPARABILITY_VALUES}")

    denom_problem = _denominator_problem(card)
    if denom_problem:
        problems.append(denom_problem)

    pred_problem = _prediction_problem(card)
    if pred_problem:
        problems.append(pred_problem)

    comp_problem = _comparability_problem(card)
    if comp_problem:
        problems.append(comp_problem)

    if problems:
        raise LibraryCardRefused(
            "card refused, every reason at once:\n  " +
            "\n  ".join(problems))
