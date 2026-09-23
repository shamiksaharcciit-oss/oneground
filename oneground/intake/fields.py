"""The intake field table: one declaration per requirements field.

**It lives in `intake` rather than in the lab**, for two reasons that
agree. The lab's guard refuses `oneground.models` to every served module, so a
table in the lab could not import `Param` without an exemption -- and an
exemption would have been the wrong repair, because this is the better home
on the merits: a field's explanation and its refusal must not diverge, and the
refusals are in this package. The declaration sits beside the thing it must
agree with. The lab imports it.

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
Eleven of intake's twenty-five refusals are outside it, and `OUTSIDE_THE
_TABLE` below names every one with the reason. They are not a backlog: the
write guard refuses each of them at write time, because a document that
violates one does not survive `load()`. What an absent declaration costs is
*when* the user finds out -- at save rather than while typing -- which is a
timing defect and not a correctness one.
"""

from oneground.models.base import NO_DEFAULT, Param

#: Re-exported deliberately. The lab's guard refuses `oneground.models` to
#: every served module, so the write path cannot ask `models.base` whether a
#: field has a default -- it asks this table, which is the only thing it
#: should be asking anyway. The re-export is the layering made explicit: the
#: interface talks to the declaration, and the declaration talks to `Param`.
__all__ = ["NO_DEFAULT", "Param", "PRESENT", "ABSENT", "SENTINELS",
           "FIELDS", "BY_NAME", "OUTSIDE_THE_TABLE"]

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

    _p("corpus.sample.queries.path", str,
       "Real queries. The ambiguity rate and the ground truth are measured "
       "against these, and there is no useful substitute for them.",
       belongs_to=("corpus.sample", PRESENT)),
    _p("corpus.sample.queries.count_min", int,
       "Below this many queries the ambiguity rate is reported "
       "couldn't-check rather than computed. A rate over twelve queries is a "
       "number you can compute and should not report.",
       default=50, minimum=1),

    _p("corpus.sample.target_sample_size", int,
       "How many vectors to draw from the file, if you want fewer than it "
       "holds. Omit to use all of them.",
       minimum=1),

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

    _p("extraction.tool", str,
       "What produced the extracted text. oneground takes extracted text and "
       "does not run extractors, so what produced it cannot be inferred -- "
       "name the tool, or `unknown` with a reason below.",
       belongs_to=("corpus.documents", PRESENT)),
    _p("extraction.version", str,
       "The extractor's version. An extractor's output changes between "
       "releases, so a result is conditional on which one ran."),
    _p("extraction.reason", str,
       "Why the tool is unknown. Unknown with no reason is "
       "indistinguishable from nobody having asked.",
       belongs_to=("extraction.tool", ("unknown",))),
)

#: name -> Param.
BY_NAME = {p.name: p for p in FIELDS}

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
