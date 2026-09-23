"""Which exceptions are the tool declining, and which are it breaking.

A refusal is the tool saying *no, and here is why, and here is what to do*.
A failure is something coming apart. They look identical from outside a
process -- both are a non-zero exit -- and until task 046 the command line
made them identical from inside one too: `intake.RequirementsError`, the
project's own refusal type with twenty-five messages that each name a field,
escaped `cli.main` as an unhandled Python traceback.

So the most common refusal in the product -- a requirements file that is
missing, or malformed, or names two corpora at once -- was met by every
command-line user as a crash, with the carefully written sentence on the last
line. The form looked fine only because `lab/compose.py` catches
`RequirementsError` from `intake.load()` directly and never goes through the
CLI. It was shielded by accident, not fixed.

> **A refusal is produced where it is raised, once.**

That is the rule, and it is also the direction *not* taken. The tempting fix
was to teach the supervisor to recognise a refusal by parsing the traceback:
match the exception name off the last line and classify from that. It would
have worked, and it would have been a second implementation of the CLI's own
error formatting in the one place the design says not to have one -- and it
would have left the command line's own users exactly where they were, reading
stack traces. The refusal is produced at the raise, printed once by `main`,
and read by everyone.

WHY THIS IS A DECLARATION AND NOT A BASE CLASS
----------------------------------------------
Fifty-five exception types live in this package. Giving the refusals a common
base would mean editing eight modules to answer a question about one, and the
answer would then be invisible at the place it is used. A mapping from dotted
name to the reason it is a refusal is checkable by reading, and an entry that
cannot be justified in a sentence has nowhere to go -- `docs/PRACTICE.md`
§7.1.

It matches on `module.qualname` and **imports nothing**. Building a tuple of
classes would mean importing eight subpackages to handle an error from one.
"""


#: Dotted name -> why this is the tool declining rather than breaking. Each
#: reason is drawn from the type's own docstring, because a type that does
#: not describe itself as a refusal is not one for this purpose.
REFUSALS = {
    "oneground.intake.RequirementsError":
        "the requirements file is missing something or says something "
        "impossible, and the message names the field; this is the one that "
        "was arriving as a traceback",
    "oneground.simulate.SimulateError":
        "the run cannot proceed and the message says what to do about it",
    "oneground.verify.VerifyError":
        "the run cannot proceed and the message says what to do about it",
    "oneground.report.ReportError":
        "the report cannot be produced and the message says what to run "
        "first",
    "oneground.chunk.stage.StageError":
        "the chunking stage cannot run on what it was given",
    "oneground.chunk.report.DeclarationError":
        "the extraction declaration is missing or incomplete",
    "oneground.chunk.strategies.ChunkingError":
        "the chunking stage refuses to proceed, naming what it was given",
    "oneground.chunk.strategies.UnknownStrategy":
        "a strategy outside the declared set, quoted back with the set",
    "oneground.models.UnknownFamily":
        "a requirements file named a family that is not registered",
    "oneground.models.base.ParameterError":
        "a configuration names or sets a key its family does not accept, "
        "which task 026 made a refusal rather than a silent ignore",
    "oneground.adapters.base.UnknownEngine":
        "a requirements file named an engine with no adapter",
    "oneground.cost.CostError":
        "the price table is missing or unusable and the message names the "
        "file",
    "oneground.calibrate.CalibrateError":
        "the check cannot be run and the message says what to do about it",
    "oneground.proposals.propose.ProposeError":
        "every problem at once, and `_cmd_propose` already treated it this "
        "way in its own words: a refusal is not a crash",
    "oneground.environment.UnpinnedEnvironment":
        "the interpreter is not running the pinned versions; already a "
        "refusal via `guard_or_exit`, listed so the set is complete",
    "oneground.environment.ForeignPackage":
        "the imported package is not the working tree's own; same path as "
        "the above",
}

#: Deliberately **not** refusals, with the reason, because the next reader
#: will wonder. An exception wrongly listed above would hide a defect as a
#: refusal -- the inverse of the finding this module exists for, and worse,
#: because a crash presented as a refusal tells the user the tool meant it.
NOT_REFUSALS = {
    "oneground.adapters.base.AdapterError":
        "an engine operation failed: the engine broke, or the network did",
    "oneground.embed.EmbedError":
        "its own docstring is 'text was supplied with no model to embed it "
        "with, OR the model failed' -- one type carrying a refusal and a "
        "failure, which is this module's own finding one level down. "
        "Splitting it is a change to `embed`, not to this list, and until "
        "then the safe reading is failure",
    "oneground.verify.ProbeUnavailable":
        "the readiness probe could not be performed, which is a "
        "couldn't-check about the engine rather than a refusal of the "
        "user's input",
    "oneground.models.indexes.IndexTooSmall":
        "arguably a configuration refusal, and it is raised mid-build after "
        "work has happened; it is left out until someone decides which, "
        "rather than guessed at here",
}

#: What `main` returns for a refusal. The code `guard_or_exit` and
#: `_cmd_propose` already used, so a refusal exits the same way whichever
#: part of the tool produced it.
REFUSED_EXIT = 2


def name_of(exc):
    """`module.qualname` for an exception or an exception class."""
    cls = exc if isinstance(exc, type) else type(exc)
    return f"{cls.__module__}.{cls.__qualname__}"


def is_refusal(exc):
    """Whether this is the tool declining rather than breaking.

    Exact on the type, not on a base class: a subclass of a refusal is not
    automatically one, because the reason in the table is about *that* type's
    contract. When a subclass arrives, it gets its own row and its own
    sentence.
    """
    return name_of(exc) in REFUSALS


def reason(exc):
    """Why it counts as a refusal, or None."""
    return REFUSALS.get(name_of(exc))
