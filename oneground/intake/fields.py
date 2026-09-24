"""The intake field table: one declaration per requirements field.

**It lives in `intake` rather than in the lab because a field's explanation
and its refusal must not end up in different packages.** They are two strings
about one field; the whole reason this table exists is that they cannot be
allowed to diverge; and the refusals are here -- `count_refusals()` below
says how many, by parsing `__init__.py` rather than by a digit written down
to go stale the next time one is added. This sentence used to say
"twenty-five." Task 047 added a twenty-sixth (`load()` refusing a
directory) and touched none of the four places, including this one, that
said so -- the instance task 049 exists to stop repeating. So the
declaration sits beside the thing it has to agree with, and the lab imports
it.

The guard is how that became visible rather than why it is right, and the
order matters. A table in the lab could not import `Param` at all -- the lab's
guard refuses `oneground.models` to every served module -- and an exemption
was available and easy. Taking it would have put a field's explanation in one
package and the refusal it must match in another, and would have done it by
talking a guard out of a refusal that was correct.

**A guard refusing something reasonable earns one question before it earns an
exemption: what is it saying about where this belongs?** Here the answer was
the whole design decision, and it was free.

A new registry over an existing shape. `models/base.py:Param` already carries
`type`, `minimum`, `maximum`, `choices`, `belongs_to` and `note`, and this
module declares intake's fields with it rather than inventing a second format
(task 046, step 2). What does not carry over is `declare_parameters`, which is
keyed by family: intake fields are not a family's parameters, so the registry
is new and the shape is not.

`Param.name` here is a **dotted path** into the requirements mapping --
`corpus.sample.vectors.path` -- because that is what a form field maps to and
what a comment in the written file sits above. Family parameters are flat, so
this is the one thing the shape is asked to carry that it was not built for,
and it carries it without change: the name is a string either way.

Presence is a different question from membership
------------------------------------------------
`belongs_to` in a family table is `(owner, wanted)`, tested as `chosen in
tuple(wanted)` -- a positive membership test over one key's value. Three of
intake's four conditional refusals do not ask that question. They ask whether
another key was written at all.

So the owner position here accepts two sentinels, `PRESENT` and `ABSENT`,
alongside a value set. **This is not a widening of `belongs_to` and the
distinction is load-bearing**: the brief excludes intake's six relational
refusals from this table on the grounds that `belongs_to` is one key and one
value set, and a premise loosened where it is inconvenient is not a premise.
Presence and membership are two questions, and a declaration that says which
one it is asking is more honest than one that blurs them. The test of that
claim is simple and it is the line not to cross: **each sentinel answers a
question with no value in it.** A sentinel that needed to know a value would
be a predicate wearing a sentinel's clothes.

`Param.type` and `belongs_to` keep their family meanings exactly. Nothing is
added to `Param`.

What this table cannot carry, named rather than missing
-------------------------------------------------------
`len(OUTSIDE_THE_TABLE)` of intake's `count_refusals()` refusals are outside
it, and `OUTSIDE_THE_TABLE` below names every one with the reason. They are
not a backlog: the write guard refuses each of them at write time, because a
document that violates one does not survive `load()`. What an absent
declaration costs is *when* the user finds out -- at save rather than while
typing -- which is a timing defect and not a correctness one.

What intake validates, and why
-------------------------------
Everything above says how a field intake validates is declared. It does not
say which fields those are, and until task 049 nothing did -- `FIELDS` was a
list a reader could inspect but not a rule they could apply to a field not
already on it, and the list had no stated boundary, only its own membership.

**A field is validated iff, applied in order:**

1.  **Scope.** It belongs to what `characterize` -- the stage intake feeds --
    needs to run and to route correctly: `run.*`, `corpus.sample.*`,
    `corpus.declared.*`, `extraction.*`, the file and its schema version. A
    field under `constraints`, `simulate`, `verify` or `report` is never in
    scope -- those are later stages' own configuration, validated (if at
    all) by the stage that consumes it. `OUT_OF_SCOPE_BLOCKS` names the four
    blocks; this line alone places 44 of the 74 fields
    `requirements.example.yaml` currently documents.
2.  **Presence.** Within scope, required when absence would force something
    load-bearing to be guessed rather than refused -- this module's own rule
    2. `run.seed`, one of `vectors.path`/`text.path`, `queries.path`,
    `size_now` and `dimension` are required this way (`REQUIRED`, and the
    `xor`/`one-of` entries in `OUTSIDE_THE_TABLE`); nothing else in scope is,
    because nothing else is load-bearing on a measurement happening at all.
3.  **Value.** Within scope, a field's value (beyond presence) is validated
    against a type, range or closed set only when the field's own domain is
    closed **by definition** -- everything outside it is necessarily a
    mistake, not a legitimate answer the field's concept has not been asked
    about yet. `text_length` (short/medium/long, with defined character
    boundaries -- there is no fourth length) is closed this way;
    `corpus_type` is not, on its own comment above `DECLARED_TEXT_LENGTHS`,
    even though both feed the identical mechanism in `analogy.py`'s scoring.
    `OPEN_DOMAIN` names the fields this leaves deliberately unchecked for
    that reason. A second, separate reason a value is left unchecked: its
    correctness can only be judged by opening a file the requirements file
    merely *names* -- not from the YAML text alone. `DEFERRED` names those;
    each is checked later, by the stage that actually opens the file.
4.  **Descriptive annotation.** Carved out regardless of 1-3: a field that
    documents why a block is what it is, for a human reader, and that no
    code path consults -- not because nothing has read it yet, but because
    there is nothing for it to decide. `ANNOTATIONS` names each with its own
    reason, because an exception with no stated reason is a field the rule
    quietly gave up on. One entry, `run.mode`, is declared there on
    *behaviour* rather than on a comment in the file the way its two
    neighbours are -- the worked example of what this component asks for
    when a field fits by conduct rather than by its own documentation.

**Its own exceptions.** A field every one of 1-4 places, with a stated
reason, is decided -- `checked_reason()` returns it. A field none of them
places is not a fifth rule invented to cover it: it is evidence this rule is
incomplete, exactly as much as a field the rule predicts wrong. Task 049's
proposal found two of the latter (`nearest_fixture`, `corpus.sample.
queries.source` -- closed domains the rule said should be checked and were
not) and fixed them rather than explained them away, which is the argument
for a rule over a list: a rule can be wrong in a way a test can catch before
anyone reads the report. `test_checked_set.py` is that test, over all 74 of
the example file's current leaves in both directions -- checked matches
checked, and everything else resolves to one of 1/3/4's named reasons or the
test fails.
"""

import ast
import os

from oneground.param import NO_DEFAULT, Param

#: Re-exported deliberately. The lab's guard refuses `oneground.models` to
#: every served module, so the write path cannot ask `models.base` whether a
#: field has a default -- it asks this table, which is the only thing it
#: should be asking anyway. The re-export is the layering made explicit: the
#: interface talks to the declaration, and the declaration talks to `Param`.
__all__ = ["NO_DEFAULT", "Param", "PRESENT", "ABSENT", "SENTINELS",
           "FIELDS", "BY_NAME", "OUTSIDE_THE_TABLE",
           "OUT_OF_SCOPE_BLOCKS", "ANNOTATIONS", "DEFERRED", "OPEN_DOMAIN",
           "checked_reason"]

#: Sentinels for the owner position of `belongs_to`. See the module docstring:
#: each answers a question with no value in it, which is what keeps them from
#: being the thin end of a predicate.
PRESENT = "<present>"
ABSENT = "<absent>"

#: Conditional kinds this table can express, for the test that asserts the
#: split the brief measured. A `belongs_to` whose `wanted` is one of the
#: sentinels is a presence question; anything else is a membership question.
SENTINELS = (PRESENT, ABSENT)


def _p(name, type_, note, **kw):
    """One field. `role` is not a family role here, so it is left at its
    default and never read: this registry has no sweeps and no labels."""
    return Param(name=name, type=type_, note=note, **kw)


#: fact -> Param, keyed by dotted path. Ordered as the written file is
#: ordered, because the writer walks this table to emit the document and a
#: file whose keys wander is a file a reader cannot diff.
FIELDS = (
    _p("oneground", int,
       "Schema version. This build understands version 1; a file naming "
       "any other version is refused rather than read on a guess.",
       default=1, choices=(1,)),

    _p("run.name", str,
       "Free text, and it appears in the report and names the working "
       "directory. Use something you will recognise in six months.",
       default=NO_DEFAULT),
    _p("run.seed", int,
       "Every draw in a run is seeded -- the sample, the queries, the "
       "simulation -- so that the same file twice gives the same receipt. "
       "There is no default: an unseeded run cannot be reproduced.",
       default=NO_DEFAULT, minimum=0),
    _p("run.workdir", str,
       "Where the receipts are written. Defaults to ./runs/<name>."),

    _p("corpus.sample.target_sample_size", int,
       "How many vectors to draw from the file, if you want fewer than it "
       "holds. Omit to use all of them.",
       minimum=1),

    _p("corpus.sample.vectors.path", str,
       "An (n, dim) float32 array of your own vectors -- ten to twenty "
       "thousand, not your whole corpus. The exact answer key is computed by "
       "brute force over this sample, which is what makes it cheap; at full "
       "scale it would not be."),
    _p("corpus.sample.vectors.ids_path", str,
       "Optional. n identifiers, in the same order as the vectors, so that "
       "results can be traced back to your own records."),
    _p("corpus.sample.vectors.normalized", bool,
       "Whether the vectors are already unit length. If false the tool "
       "normalizes them, and says so in the receipt.",
       default=False),

    _p("corpus.sample.text.path", str,
       "Extracted text instead of vectors. The tool embeds it with the model "
       "you name below; it never chooses a model for you."),
    _p("corpus.sample.text.model", str,
       "The embedding model, pinned. The model decides what every "
       "measurement means, so there is no default and no guess.",
       belongs_to=("corpus.sample.text.path", PRESENT)),

    # No `belongs_to`. It was conditional on `corpus.sample` being present,
    # which hid the one REQUIRED field in the block while the two optional
    # ones beside it stayed visible -- a browser pass found it, because the
    # form was internally consistent and simply wrong about which fields a
    # person starting from empty needs to see. `queries.path` is part of the
    # sample block exactly as `vectors.path` is; that it is required is the
    # separate question `REQUIRED` answers.
    _p("corpus.sample.queries.path", str,
       "Real queries. The ambiguity rate and the ground truth are measured "
       "against these, and there is no useful substitute for them."),
    # The knob, once there is something for it to be a floor on.
    _p("corpus.sample.queries.count_min", int,
       "Below this many queries the ambiguity rate is reported "
       "couldn't-check rather than computed. A rate over twelve queries is a "
       "number you can compute and should not report.",
       default=50, minimum=1,
       belongs_to=("corpus.sample.queries.path", PRESENT)),
    # Task 049: closed by definition, the same reasoning as text_length --
    # three named provenances, nothing a fourth word could mean that one of
    # them does not already say. Previously documented and read by nothing.
    _p("corpus.sample.queries.source", str,
       "logs | written | synthetic -- where these queries came from.",
       choices=("logs", "written", "synthetic")),

    _p("corpus.declared.size_now", int,
       "Your real corpus size today. The capacity arithmetic is arithmetic "
       "over this, and over the dimension below; guessing either would be "
       "inventing your corpus.",
       minimum=1),
    _p("corpus.declared.dimension", int,
       "The embedding dimension. Required with size_now for the same reason: "
       "it is what the arithmetic is arithmetic over.",
       minimum=1),
    _p("corpus.declared.text_length", str,
       "short | medium | long. Matched against the fixtures' own declared "
       "lengths, so a value outside that set can only match by accident.",
       choices=("short", "medium", "long")),
    _p("corpus.declared.topics_trend", bool,
       "Whether hot topics appear and fade. Sharpens which fixture your "
       "corpus is compared against."),
    _p("corpus.declared.time_ordered", bool,
       "Whether the corpus has a meaningful time order."),
    _p("corpus.declared.languages", list,
       "The languages present, as a list. Sharpens the fixture analogy."),
    # Task 049: closed by definition too, but not by a static set -- 'auto'
    # and 'none' are the two fixed sentinels analogy.choose() matches on,
    # and anything else must name a fixture the account actually has built.
    # No `choices=`: the third option is not a fixed list, it is whatever
    # `analogy.load_fixture_analogies()` finds, and a static tuple here
    # would go stale the first time a fixture is added -- the defect this
    # task exists to stop reproducing.
    _p("corpus.declared.nearest_fixture", str,
       "auto | none | a built fixture's id. 'auto' matches; 'none' "
       "disables the analogy; a named fixture is used directly rather than "
       "chosen by matching. The set of valid ids is read from the "
       "fixtures directory, not fixed here."),

    _p("extraction.tool", str,
       "What produced the extracted text. oneground takes extracted text and "
       "does not run extractors, so what produced it cannot be inferred -- "
       "name the tool, or `unknown` with a reason below.",
       belongs_to=("corpus.documents", PRESENT)),
    # Shown only once a tool is named. *Required* when the tool is anything
    # but `unknown` is the negation this table cannot carry -- that one stays
    # in `OUTSIDE_THE_TABLE` -- but *belonging* is a presence question and is
    # declarable, so the form no longer offers an extractor version on a file
    # that declares no extraction at all.
    _p("extraction.version", str,
       "The extractor's version. An extractor's output changes between "
       "releases, so a result is conditional on which one ran.",
       belongs_to=("extraction.tool", PRESENT)),
    _p("extraction.reason", str,
       "Why the tool is unknown. Unknown with no reason is "
       "indistinguishable from nobody having asked.",
       belongs_to=("extraction.tool", ("unknown",))),
)

#: name -> Param.
BY_NAME = {p.name: p for p in FIELDS}

#: Which fields `intake` refuses when they are absent, and under what
#: condition. A separate declaration, and the reason is a defect this table
#: shipped with for one afternoon.
#:
#: `Param.default is NO_DEFAULT` means *the family has no default for this
#: key, so a configuration must name it*. The form read that as **required**,
#: which is the same words and a different fact: most intake fields have no
#: default and are entirely optional. Every field declared here without an
#: explicit default was marked `required` in the form, so `ids_path` — whose
#: own explanation begins "Optional." — was labelled required directly above
#: the sentence saying it is not.
#:
#: That is `docs/PRACTICE.md` §4 exactly: a key whose meaning differs by file.
#: `default` means one thing in a family table and would have to mean another
#: here, so requiredness gets its own declaration rather than borrowing one
#: that nearly fits. The tell was the one §4 names: **the field was present,
#: well-formed and plausible**, and it took a browser to see it, because it
#: reads as a wrong value rather than as an error.
#:
#: The condition uses the same vocabulary as `belongs_to`: a value set, or
#: `PRESENT`/`ABSENT` for the presence question. `None` means unconditionally.
REQUIRED = {
    "run.seed": ("corpus.sample", PRESENT),
    "corpus.sample.queries.path": ("corpus.sample", PRESENT),
    "corpus.declared.size_now": ("corpus.declared", PRESENT),
    "corpus.declared.dimension": ("corpus.declared", PRESENT),
    "extraction.tool": ("corpus.documents", PRESENT),
    "extraction.reason": ("extraction.tool", ("unknown",)),
}

#: The eleven refusals this table cannot express, each named with the reason
#: and the line that raises it. Named rather than missing: an implementer who
#: does not know they are excluded will believe the table is finishable, stop
#: at eleven, and leave the form re-expressing eleven refusals it was ruled
#: must execute. The write guard refuses all eleven at write time.
OUTSIDE_THE_TABLE = (
    # -- relational: no single owner key decides them ----------------------
    ("corpus.sample.vectors.path xor corpus.sample.text.path", "xor",
     "both set leaves it unrecorded which produced the vectors"),
    ("corpus.sample.vectors.path or corpus.sample.text.path", "one-of",
     "one of them has to say where the corpus is"),
    ("corpus.sample.text.model xor corpus.sample.text.models", "xor",
     "naming both leaves it unsaid which model produced the vectors"),
    ("corpus.sample.text implies model or models", "implies",
     "text has to be embedded by a named, pinned model"),
    ("corpus.sample or corpus.declared or corpus.documents", "one-of",
     "one of the three tiers has to be there"),
    ("corpus.sample.text.models is a set", "uniqueness",
     "a model listed twice is measured twice and reported under one name"),
    # -- not about a declared field at all ---------------------------------
    ("the file itself", "not-a-field", "the requirements file does not exist"),
    ("the document root", "not-a-field", "the file is not a YAML mapping"),
    ("oneground:", "not-a-field",
     "a schema version this build does not understand"),
    ("corpus.<stray>", "not-a-field",
     "a Tier-1 key set with no corpus.sample, which would run as Tier 2 and "
     "ignore it"),
    # -- the negation ------------------------------------------------------
    ("extraction.version when tool != 'unknown'", "negated-set",
     "a negated value set over an open string domain; expressing it needs a "
     "predicate, and a predicate cannot be rendered into a comment"),
)


# ============================================================================
# THE CHECKED SET -- task 049
#
# Everything above says how a field intake validates is declared. This says
# which fields those are, as a rule rather than as this table's membership --
# see the module docstring's new section, "What intake validates, and why."
# ============================================================================

#: Rule 1. A field under one of these top-level blocks is never intake's
#: subject: `constraints`, `simulate`, `verify` and `report` are later
#: stages' own configuration, validated (if at all) by the stage that
#: consumes it, not by intake. This single line accounts for 44 of the 74
#: leaves `requirements.example.yaml` currently documents.
OUT_OF_SCOPE_BLOCKS = ("constraints", "simulate", "verify", "report")

#: Rule 4. In scope by rule 1, carved out anyway: a field that documents
#: *why* a block is what it is, for a human reader, and that no code path
#: consults -- not because nothing has read it yet, but because there is
#: nothing for it to decide. Each entry names why, because an exception
#: with no stated reason is a field the rule quietly gave up on rather than
#: placed.
ANNOTATIONS = {
    "corpus.sample.kind": "restates corpus.sample's own presence: a file "
        "has this block or it does not, structurally",
    "corpus.declared.kind": "restates corpus.declared's own presence, the "
        "same way",
    "corpus.sample.sampling.method": "the example file's own comment: "
        "\"how the sample was drawn from the full corpus -- recorded, not "
        "enforced\"",
    "corpus.sample.sampling.stratify_by": "same block, same comment",
    "corpus.sample.sampling.full_corpus_size": "same block, same comment",
    # The worked example: a field that fits by behaviour rather than by a
    # comment in the file, declared here with the reason rather than left a
    # disagreement between the rule and the tree. `Requirements` never reads
    # it; `self.tier` is computed from which blocks are present
    # (`1 if self.sample else (2 if self.declared else None)`), never from
    # this field. It looks like a decision the user makes; the code decides
    # it structurally instead, and this field is what that decision would
    # have read if anything did.
    "run.mode": "nothing reads it; tier is computed from which blocks are "
        "present, never from this field -- it fits rule 4 by behaviour, "
        "unlike its two neighbours above which the file says so about "
        "directly",
}

#: Rule 3, the file-opening clause. In scope, and not validated because
#: correctness can only be judged by opening a file the requirements file
#: merely names -- not judgeable from the YAML text alone. Each is checked
#: later, by the stage that actually opens that file, which is `intake`'s
#: own module docstring rule 2 ("refuse rather than guess") applied one
#: level down: a check that cannot yet tell truth from guess is not ready
#: to refuse.
DEFERRED = {
    "corpus.sample.metadata.path": "optional; if `characterize` cannot "
        "open it, that failure names the path, not a schema violation",
    "corpus.sample.metadata.timestamp_field": "characterize.py checks the "
        "column exists once the metadata file is actually open",
    "corpus.sample.metadata.filter_fields": "same shape as "
        "timestamp_field: column names, checkable only once the file is "
        "open",
    "corpus.sample.metadata.category_field": "same shape again -- and "
        "task 048 found the property that would carry it "
        "(`Requirements.category_field`) is never called by anything "
        "either, a second, separate absence this rule does not speak to",
}

#: Rule 3, the closed-domain clause, negative case. In scope, presence
#: optional, and not validated because the field's domain is open BY
#: CONCEPT rather than closed by definition -- see `DECLARED_TEXT_LENGTHS`'s
#: own comment for the reasoning, which this generalises rather than
#: repeats. An unmatched value degrades to an honest "no match", not a
#: wrong answer, so there is nothing for a refusal to catch.
OPEN_DOMAIN = {
    "corpus.declared.corpus_type": "an unrecognised type simply matches no "
        "fixture in analogy.py's scoring -- an honest 'no analogy', not a "
        "wrong one",
    "corpus.declared.embedding_model": "the same mechanism, the same "
        "reasoning, previously unstated: an unmatched model scores low "
        "rather than refusing",
}


def count_refusals():
    """How many refusals `intake.load()` (and everything it calls) raises,
    today -- parsed, not grepped, and never written down as a digit.

    Task 049: `fields.py`'s own docstring said "twenty-five" through task
    046 and stayed twenty-five through task 047, which added a twenty-sixth
    (`load()` refusing a directory) without anyone noticing the sentence had
    gone stale, because nothing connected the sentence to the source. This
    is that connection: every `raise RequirementsError(...)` in
    `intake/__init__.py`, walked by `ast` rather than assumed.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "__init__.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    return sum(
        1 for node in ast.walk(tree)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "RequirementsError")


def checked_reason(field):
    """`(checked, reason)` for a dotted field path -- the rule, applied.

    `checked` is `field in BY_NAME`. `reason` explains either side: which
    `Param` declares it, or which of rules 1/3/4 places it outside the
    checked set and why. Returns `(None, None)` for a field none of the
    above accounts for -- the rule not yet having an answer, which is
    evidence the rule is incomplete rather than something to be guessed at
    here. `test_checked_set.py` treats that pair as a failure, not a case.
    """
    if field in BY_NAME:
        return True, f"declared in FIELDS: {BY_NAME[field].note[:60]}..."
    top = field.split(".")[0]
    if top in OUT_OF_SCOPE_BLOCKS:
        return False, f"rule 1: {top} is a later stage's configuration"
    for table, rule in ((ANNOTATIONS, "rule 4"), (DEFERRED, "rule 3"),
                        (OPEN_DOMAIN, "rule 3")):
        if field in table:
            return False, f"{rule}: {table[field]}"
    return None, None
