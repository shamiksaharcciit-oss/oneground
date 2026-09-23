"""The shape of a declared key, and nothing else.

`Param` lives here rather than in `models/base.py` because more than one
package declares keys with it, and `oneground.models` cannot be imported just
to reach a dataclass: its `__init__` registers all three families, so reading
the shape loads every family, every index type and numpy.

That is not a tidiness argument. The lab's interface declares intake's fields
with this same shape (`oneground/intake/fields.py`), and the lab's guard
refuses `oneground.models` to every served module -- correctly, because a
front end has no business loading a simulator. There is also a runtime test,
`test_everything_the_server_imports_passes_the_guard`, which asserts on the
loaded modules rather than on the source, and it is the one that found this:
the static scan passed, because nothing in the lab named a measuring module,
and the process had loaded three families anyway through a dataclass import
two packages away.

So the shape is a leaf. It imports nothing but the standard library, which is
what makes it safe to depend on from anywhere. `models/base.py` imports it and
re-exports it, so every existing importer of `base.Param` is unaffected.

**One shape, one module.** The alternative was a second declaration format for
intake's fields, which is the thing a shared shape exists to prevent: two
formats for one idea drift the first time either is extended, and the
explanation a user reads would then come from one while the refusal came from
the other.
"""

from dataclasses import dataclass
from typing import Any, Optional

# What a key is to a family.
PARAMETER = "parameter"    # the architecture; the only role a policy changes
RUN = "run"                # set per run by the simulator, uniform across it
BUILD = "build"            # how the index is built, not what it is
CONSTANT = "constant"      # fixed inside the family; refused in any config

ROLES = (PARAMETER, RUN, BUILD, CONSTANT)


class _NoDefault:
    """A declared key the family has no default for: it must be named."""

    def __repr__(self):                               # pragma: no cover
        return "<no default>"


NO_DEFAULT = _NoDefault()


@dataclass(frozen=True)
class Param:
    """One declared key.

    `minimum`/`maximum` are validity bounds -- what the family can build at
    all -- not recommendations. `swept` says whether the family's `configs()`
    reads a requirements grid for it; a declared key that is not swept can
    still be pinned by an `include` entry. `fixed` is a constant's value, for
    the message that refuses it.
    """

    name: str
    type: type
    role: str = PARAMETER
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    swept: bool = False
    fixed: Any = None
    # What the family uses when a config does not name this key. Declared
    # here so there is one of it: before task 032 the same number appeared in
    # the family's `config.get(key, X)` calls, again in the dict `configs()`
    # seeds an `include` entry from, and nowhere a reader could look it up.
    # `NO_DEFAULT` means the key must be named.
    default: Any = NO_DEFAULT
    # Whether this key appears in a label when it is at its default.
    #
    # Task 032 canonicalised a label by *filling* the defaults, so that a
    # parameter written at its default and the same parameter omitted are one
    # label and one row. Task 034 then added `index`, whose default is the
    # behaviour every published label was measured under -- and filling it
    # would append `index=hnsw` to labels that are a public interface, while
    # eliding every default would collapse those same labels to `family[]`,
    # since each is composed entirely of parameters at their defaults.
    #
    # So the table says which, per key, and the invariant holds either way:
    # `always` fills a missing default, `when_set` elides one, and both make
    # the two spellings of a default one label. The direction that does not
    # move a label already published is the one a new key takes.
    in_label_at_default: bool = True
    # Which value of another key this one belongs to: ("index", ("ivf",
    # "ivf_pq")) means the key is accepted only when `index` is one of those.
    # A knob an algorithm would ignore is refused rather than accepted (034),
    # for the reason 026 refuses a key no family reads.
    belongs_to: Optional[Any] = None
    # The closed set of values this key may take, for a key whose type does
    # not bound it. `minimum`/`maximum` bound a number; nothing bounded a
    # string until 034 declared `index`, and an unknown algorithm accepted
    # and then quietly built as HNSW is the accept-and-ignore defect 026
    # exists to stop.
    choices: Optional[Any] = None
    note: str = ""
