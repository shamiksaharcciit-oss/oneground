"""Matching a declared corpus to a published fixture.

Tier 2 has no sample, so there is nothing to measure. What it can do is find
the published corpus whose *declared* character is closest to the user's
declared character, and show that fixture's measured surface — labelled, every
time, as measured on the fixture and not on the user's corpus.

The honesty rules, which are the whole of this module's design:

1.  **An analogy is never a verdict.** Nothing here returns a number about the
    user's corpus. It returns a fixture id and a reason, and the caller
    presents the fixture's own published values under a label that names the
    fixture.

2.  **Matching is on declared fields only** — `corpus_type`, `text_length`,
    `topics_trend`, `time_ordered`, `dimension` and the model family. Those
    are the fields a user can answer without exporting anything, which is what
    makes Tier 2 zero-friction. A fixture's measured values play no part in
    choosing it; using them would be fitting the analogy to the answer.

3.  **A weak match is reported as weak, and no match as none.** A fixture
    chosen because it was the only one available is not an analogy, it is a
    default. `MIN_SCORE` is the floor below which this returns nothing at all.

4.  **The user can override.** `nearest_fixture: arxiv-150k` names one
    directly; `none` disables the analogy. `auto` is the only value that
    searches.
"""

import os

import yaml

FIXTURES_DIR = "fixtures"

# What each declared field is worth when it matches. `corpus_type` dominates
# because it is the field that decides whether two corpora are the same kind
# of thing at all -- a papers fixture is a poor analogy for a ticket queue
# however well the other five agree.
WEIGHTS = {
    # Strictly greater than the sum of the rest (7.0), so that "same kind of
    # corpus, everything else different" outranks "different kind of corpus,
    # everything else identical" -- 8/15 against 7/15. An earlier draft used
    # 4.0 and claimed the same property in a comment; the arithmetic said the
    # opposite, and a weighting whose stated rationale is false is worse than
    # one with no rationale at all.
    "corpus_type": 8.0,
    "text_length": 2.0,
    "topics_trend": 1.5,
    "time_ordered": 1.5,
    "dimension": 1.0,
    "model_family": 1.0,
}

# Below this share of the available weight, there is no analogy at all.
#
# 0.70 of 15.0 is 10.5, so a match needs the right corpus_type (8.0) plus at
# least 2.5 of the remaining 7.0. A right corpus_type on its own scores 0.53
# and is not enough; a wrong one caps at 0.47 and can never be enough however
# well the rest agree. A fixture chosen because it was the only one available
# is a default, not an analogy.
MIN_SCORE = 0.70


class Analogy:
    """One fixture proposed as an analogy, with why and how well."""

    __slots__ = ("fixture", "score", "matched", "differed", "unknown",
                 "spec_path")

    def __init__(self, fixture, score, matched, differed, unknown, spec_path):
        self.fixture = fixture
        self.score = score
        self.matched = matched
        self.differed = differed
        self.unknown = unknown
        self.spec_path = spec_path

    def as_dict(self):
        return {"fixture": self.fixture, "score": round(self.score, 4),
                "matched": list(self.matched), "differed": list(self.differed),
                "unknown": list(self.unknown), "spec": self.spec_path,
                "kind": "declared",
                "note": ("matched on declared fields only. Every measured "
                         "value shown alongside this analogy was measured on "
                         f"{self.fixture}, not on your corpus.")}

    def label(self):
        """The words that must appear wherever the fixture's numbers appear."""
        return (f"analogy — measured on {self.fixture}, not on your corpus")

    def reason(self):
        bits = [f"matched on {', '.join(self.matched)}"] if self.matched else []
        if self.differed:
            bits.append(f"differs on {', '.join(self.differed)}")
        if self.unknown:
            bits.append(f"not stated: {', '.join(self.unknown)}")
        return "; ".join(bits) or "no fields in common"


def _model_family(name):
    """`BAAI/bge-base-en-v1.5` -> `bge`. Declared, and deliberately crude.

    Two corpora embedded by the same family are more alike than two embedded
    by different ones, and that is all this is used for. It never decides
    anything on its own -- `WEIGHTS` gives it the smallest share available.
    """
    if not name:
        return None
    tail = str(name).split("/")[-1].lower()
    for sep in ("-", "_"):
        if sep in tail:
            return tail.split(sep)[0]
    return tail


def load_fixture_analogies(fixtures_dir=FIXTURES_DIR):
    """Every fixture spec that declares an `analogy:` block.

    A fixture without one is skipped rather than guessed at: a spec that has
    not said what it is like cannot be matched against, and inferring its
    character from its measured values would be exactly the fitting this
    module refuses to do.
    """
    out = []
    if not os.path.isdir(fixtures_dir):
        return out
    for name in sorted(os.listdir(fixtures_dir)):
        if not name.endswith(".fixture.yaml"):
            continue
        path = os.path.join(fixtures_dir, name)
        try:
            with open(path, encoding="utf-8") as f:
                spec = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            continue
        analogy = spec.get("analogy")
        if not analogy:
            continue
        out.append((spec.get("fixture", {}).get("id") or
                    name[:-len(".fixture.yaml")], analogy, path, spec))
    return out


def score(declared, analogy):
    """(score, matched, differed, unknown) for one fixture.

    `score` is the share of the weight available on fields *both* sides
    state. A field neither side states cannot count for or against -- counting
    silence as agreement would let an empty declaration match everything.
    """
    matched, differed, unknown = [], [], []
    got = available = 0.0

    pairs = [
        ("corpus_type", declared.get("corpus_type"), analogy.get("corpus_type")),
        ("text_length", declared.get("text_length"), analogy.get("text_length")),
        ("topics_trend", declared.get("topics_trend"), analogy.get("topics_trend")),
        ("time_ordered", declared.get("time_ordered"), analogy.get("time_ordered")),
        ("dimension", declared.get("dimension"), analogy.get("dimension")),
        ("model_family",
         _model_family(declared.get("embedding_model")),
         analogy.get("model_family") or _model_family(
             analogy.get("embedding_model"))),
    ]
    for field, mine, theirs in pairs:
        if mine is None or theirs is None:
            unknown.append(field)
            continue
        available += WEIGHTS[field]
        if _same(mine, theirs):
            got += WEIGHTS[field]
            matched.append(field)
        else:
            differed.append(field)
    if available == 0:
        return 0.0, matched, differed, unknown
    return got / available, matched, differed, unknown


def _same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) is bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return str(a).strip().lower() == str(b).strip().lower()


def choose(declared, fixtures_dir=FIXTURES_DIR):
    """(Analogy or None, reason).

    The reason is always a sentence, including when the answer is None -- "no
    analogy" with no explanation is indistinguishable from a bug.
    """
    want = declared.get("nearest_fixture", "auto")
    candidates = load_fixture_analogies(fixtures_dir)
    if not candidates:
        return None, ("no fixture spec declares an `analogy:` block, so there "
                      "is nothing to match against")

    if want in (None, "none", False):
        return None, "corpus.declared.nearest_fixture is 'none'"

    if want and str(want) != "auto":
        for fid, analogy, path, _spec in candidates:
            if fid == str(want):
                sc, matched, differed, unknown = score(declared, analogy)
                return (Analogy(fid, sc, matched, differed, unknown, path),
                        f"corpus.declared.nearest_fixture names {fid} "
                        f"directly; it was not chosen by matching")
        return None, (f"corpus.declared.nearest_fixture is {want!r}, and no "
                      f"fixture with that id declares an analogy block. "
                      f"Available: {', '.join(c[0] for c in candidates)}")

    scored = []
    for fid, analogy, path, _spec in candidates:
        sc, matched, differed, unknown = score(declared, analogy)
        scored.append(Analogy(fid, sc, matched, differed, unknown, path))
    scored.sort(key=lambda a: (-a.score, a.fixture))
    best = scored[0]
    if best.score < MIN_SCORE:
        return None, (
            f"no fixture is close enough to be an analogy. The nearest, "
            f"{best.fixture}, scores {best.score:.2f} against a floor of "
            f"{MIN_SCORE:.2f} ({best.reason()}). A fixture chosen because it "
            "was the only one available is a default, not an analogy.")
    return best, (f"nearest of {len(scored)} fixture(s) by declared "
                  f"character, scoring {best.score:.2f} ({best.reason()})")


def fixture_surface(spec):
    """The fixture's own published values, as a labelled block.

    Copied, never recomputed, and every entry carries the fixture's own
    tolerance so a reader can see what "reproduces" would mean.
    """
    ch = spec.get("characterization") or {}
    out = {}
    for field, entry in ch.items():
        if field == "kind" or not isinstance(entry, dict):
            continue
        if "value" in entry:
            out[field] = {"value": entry["value"],
                          "tolerance": entry.get("tolerance")}
        elif "value_before" in entry:
            out[field] = {"value_before": entry["value_before"],
                          "value_after": entry.get("value_after"),
                          "tolerance": entry.get("tolerance")}
    return out
