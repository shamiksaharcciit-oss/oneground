"""Reading and validating a requirements file.

`requirements.example.yaml` at the repo root is the schema by example. This
module reads the parts task 007 implements -- Tier 1, the receipt path -- and
refuses clearly when something it needs is missing.

Two rules shape every error message here:

1.  **Name the field.** "no model" is useless; "corpus.sample.text is set but
    corpus.sample.text.model is not" tells the user what to type.
2.  **Refuse rather than guess.** A missing model is not a reason to pick a
    default one. A default embedding model would silently decide the most
    load-bearing thing about a user's vectors.

Tier 2 (`corpus.declared`) describes a corpus that has not been sampled yet.
It is validated here and carried through, and it never produces a verdict:
claiming one from a description is exactly what this project exists not to do.
What it produces instead is a fixture analogy, labelled as measured on the
fixture and not on the user's corpus, and capacity arithmetic labelled
derived-from-declared.
"""

import os

import yaml

SCHEMA_VERSION = 1

# What Tier 2 cannot do without. Everything else in `corpus.declared` sharpens
# the fixture analogy or the capacity arithmetic; these two are what the
# arithmetic is arithmetic *over*, and guessing either would be inventing the
# user's corpus.
DECLARED_REQUIRED = ("size_now", "dimension")

# Values `corpus_type` is matched on. Not a closed set for the user -- an
# unrecognised type is carried through and simply matches no fixture, which is
# an honest "no analogy" rather than a wrong one.
DECLARED_TEXT_LENGTHS = ("short", "medium", "long")


class RequirementsError(ValueError):
    """The requirements file is missing something, or says something
    impossible. The message always names the field."""


class Requirements:
    """A validated Tier-1 requirements file."""

    def __init__(self, data, path):
        self.path = path
        self.data = data
        self.run = data.get("run") or {}
        self.corpus = data.get("corpus") or {}
        self.sample = self.corpus.get("sample") or {}
        self.declared = self.corpus.get("declared") or {}
        # 1 when there is a sample to measure, 2 when there is only a
        # description. A file may carry both; a sample always wins, because a
        # measurement always beats a declaration.
        self.tier = 1 if self.sample else (2 if self.declared else None)

        self.name = str(self.run.get("name") or
                        os.path.splitext(os.path.basename(path))[0])
        self.seed = int(self.run.get("seed", 0))
        self.workdir = str(self.run.get("workdir") or
                           os.path.join("runs", self.name))

        self.vectors = self.sample.get("vectors") or {}
        self.text = self.sample.get("text") or {}
        self.metadata = self.sample.get("metadata") or {}
        self.queries = self.sample.get("queries") or {}
        # A declared 2-D placement for drawing (task 027). Never an input
        # to a measurement: nothing reads it but the lab, and the state
        # records it as declared with its digest.
        self.projection = self.sample.get("projection") or {}
        self.target_sample_size = self.sample.get("target_sample_size")

    # -- convenience accessors ---------------------------------------------
    @property
    def timestamp_field(self):
        return self.metadata.get("timestamp_field")

    @property
    def category_field(self):
        return self.metadata.get("category_field")

    @property
    def count_min(self):
        """Below this many queries the ambiguity rate is couldn't-check.

        50 is the example file's value and the default. It is a floor on
        meaning, not on arithmetic: a rate over 12 queries is a number you can
        compute and should not report.
        """
        return int(self.queries.get("count_min", 50))

    @property
    def model(self):
        return self.text.get("model")

    def resolve(self, path):
        """Paths in a requirements file are relative to the file itself, so a
        file and its data can be moved together.

        `~` is expanded first: a published requirements file names
        `~/oneground-assets/...` rather than someone's home directory spelled
        out, and without this that would be joined onto the file's own
        directory and produce a path with a literal tilde in it.
        """
        if not path:
            return None
        path = os.path.expanduser(str(path))
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(os.path.dirname(
            os.path.abspath(self.path)), path))

    def input_paths(self):
        """Every input file, for the build_info digest block."""
        out = {}
        for key, p in (("vectors", self.vectors.get("path")),
                       ("vectors_ids", self.vectors.get("ids_path")),
                       ("text", self.text.get("path")),
                       ("metadata", self.metadata.get("path")),
                       ("queries", self.queries.get("path")),
                       ("queries_metadata",
                        (self.queries.get("metadata") or {}).get("path")),
                       ("projection", self.projection.get("path"))):
            rp = self.resolve(p)
            if rp and os.path.exists(rp):
                out[key] = rp
        return out


def _validate_text_corpus(req, path):
    """A corpus given as extracted text needs its extraction declared.

    oneground does not run extractors, so what produced the text cannot be
    inferred. The declaration is carried onto every result so a reader knows
    what the result is conditional on; `unknown` is accepted with a reason,
    because unknown with no reason is indistinguishable from nobody having
    asked. See docs/INTAKE.md and docs/CHUNKING.md.
    """
    d = req.data.get("extraction")
    if not d:
        raise RequirementsError(
            f"{path}: corpus.documents is set but `extraction:` is missing. "
            "oneground takes extracted text and does not run extractors, so "
            "name the tool and its version -- or `unknown` with a reason.")
    if not d.get("tool"):
        raise RequirementsError(f"{path}: extraction.tool is required")
    if d["tool"] == "unknown" and not d.get("reason"):
        raise RequirementsError(
            f"{path}: extraction.tool is 'unknown' with no reason. Unknown "
            "with no reason is indistinguishable from nobody having asked.")
    if d["tool"] != "unknown" and not d.get("version"):
        raise RequirementsError(
            f"{path}: extraction.tool {d['tool']!r} needs its version; an "
            "extractor's output changes between releases.")


def _validate_declared(req, path):
    """Tier 2's own validation. Names the field, refuses rather than guesses.

    Deliberately narrow: `size_now` and `dimension` are required because the
    capacity arithmetic is arithmetic over them, and everything else is
    optional. A missing `corpus_type` does not fail the file -- it produces no
    fixture analogy, which is the honest outcome and is reported as one.
    """
    d = req.declared
    missing = [k for k in DECLARED_REQUIRED if d.get(k) is None]
    if missing:
        raise RequirementsError(
            f"{path}: corpus.declared is missing "
            f"{', '.join('corpus.declared.' + m for m in missing)}. Tier 2's "
            "capacity arithmetic is arithmetic over exactly these two; there "
            "is nothing to compute without them.")

    for key in ("size_now", "dimension"):
        try:
            value = int(d[key])
        except (TypeError, ValueError):
            raise RequirementsError(
                f"{path}: corpus.declared.{key} must be a whole number; got "
                f"{d[key]!r}") from None
        if value <= 0:
            raise RequirementsError(
                f"{path}: corpus.declared.{key} must be greater than 0; got "
                f"{value}")

    length = d.get("text_length")
    if length is not None and str(length) not in DECLARED_TEXT_LENGTHS:
        raise RequirementsError(
            f"{path}: corpus.declared.text_length is {length!r}; it must be "
            f"one of {', '.join(DECLARED_TEXT_LENGTHS)}. It is matched "
            "against the fixtures' own declared lengths, and a value outside "
            "that set can only match by accident.")

    for key in ("topics_trend", "time_ordered"):
        if d.get(key) is not None and not isinstance(d[key], bool):
            raise RequirementsError(
                f"{path}: corpus.declared.{key} must be true or false; got "
                f"{d[key]!r}")

    languages = d.get("languages")
    if languages is not None and not isinstance(languages, (list, tuple)):
        raise RequirementsError(
            f"{path}: corpus.declared.languages must be a list; got "
            f"{languages!r}")

    # `corpus.sample` absent but a Tier-1 field set anyway is a file caught
    # halfway between the two tiers, and silently ignoring it would run the
    # wrong tier without saying so.
    for stray in ("vectors", "text", "queries", "metadata"):
        if req.corpus.get(stray):
            raise RequirementsError(
                f"{path}: corpus.{stray} is set but corpus.sample is not. "
                f"Tier 1 fields belong under corpus.sample; as written this "
                "file would run as Tier 2 and ignore them.")


def load(path):
    """Read, validate, return. Raises RequirementsError with a named field."""
    if not os.path.exists(path):
        raise RequirementsError(f"requirements file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise RequirementsError(f"{path}: expected a YAML mapping")

    version = data.get("oneground")
    if version is not None and int(version) != SCHEMA_VERSION:
        raise RequirementsError(
            f"{path}: oneground: {version} is not schema version "
            f"{SCHEMA_VERSION}, which is the only one this build understands")

    req = Requirements(data, path)

    if not req.sample:
        if req.declared:
            _validate_declared(req, path)
            return req                      # Tier 2: nothing below applies
        if (req.data.get("corpus") or {}).get("documents"):
            # A TEXT corpus (task 031). `characterize` accepts extracted text
            # as well as vectors: the chunking stage runs first, writes its
            # own receipt, and the rest of the path continues from the chunks
            # it produced. The corpus is documents, so there is no
            # `corpus.sample.vectors` to point at and nothing below applies.
            _validate_text_corpus(req, path)
            return req
        raise RequirementsError(
            f"{path}: corpus.sample is missing, corpus.declared is empty and "
            "corpus.documents names no extracted text. `characterize` "
            "measures a sample of your own vectors (Tier 1); with "
            "corpus.declared it produces a fixture analogy and capacity "
            "arithmetic instead (Tier 2); with corpus.documents it chunks "
            "extracted text first (docs/CHUNKING.md). One of the three has "
            "to be there.")

    has_vectors = bool(req.vectors.get("path"))
    has_text = bool(req.text.get("path"))
    if not has_vectors and not has_text:
        raise RequirementsError(
            f"{path}: set corpus.sample.vectors.path or "
            "corpus.sample.text.path -- one of them has to say where the "
            "corpus is.")
    if has_vectors and has_text:
        raise RequirementsError(
            f"{path}: corpus.sample.vectors.path and corpus.sample.text.path "
            "are both set. Provide one; which of the two produced the vectors "
            "would otherwise be unrecorded.")
    if has_text and not req.text.get("model"):
        raise RequirementsError(
            f"{path}: corpus.sample.text is set but "
            "corpus.sample.text.model is not. Text has to be embedded by a "
            "named, pinned model -- oneground will not choose one for you, "
            "because the model decides what the measurements mean.")

    if not req.queries.get("path"):
        raise RequirementsError(
            f"{path}: corpus.sample.queries.path is missing. The ambiguity "
            "rate and the ground truth are measured against real queries; "
            "there is no useful substitute for them.")

    if req.run.get("seed") is None:
        raise RequirementsError(
            f"{path}: run.seed is missing. Every draw in a run is seeded, so "
            "that the same file twice gives the same receipt.")

    if req.target_sample_size is not None:
        try:
            n = int(req.target_sample_size)
        except (TypeError, ValueError):
            raise RequirementsError(
                f"{path}: corpus.sample.target_sample_size must be a whole "
                f"number, got {req.target_sample_size!r}") from None
        if n <= 0:
            raise RequirementsError(
                f"{path}: corpus.sample.target_sample_size must be > 0")

    return req
