"""The one write path: form state in, a requirements file out.

This is the first thing in the interface that is not a drawing. The rendering
contract has nothing to say about bytes leaving the page -- its clauses
describe what a view is handed, what it may read and what it must return, and
none of them describes a write -- so the write half is held by a guard of its
own (task 046, `docs/UI.md`, *Settled before slice 2*).

    The bytes must round-trip to the same document the form validated:
    parse(write(D)) == D, checked on every write, not in tests.

Four things about that rule, each of which was settled before this module
existed and none of which is this module's to reopen.

**It is on the parsed document, not the bytes.** `write(D) == bytes` is not a
stronger version of this rule, it is a different and incompatible one: it
would forbid the comments the front door requires the form to write. The
identity is over the parsed document *precisely because* comments are not
data, which is the same ruling's own statement that they are never read back
as such.

**It runs on every write.** Temp file beside the target, read back, compare,
then `os.replace`. A guard that runs in tests is not a guard, and the reason
it can run on every write is that it is mechanical: no judgement, no
threshold, one comparison.

**It is load-bearing rather than a sanity check.** `D` is built from form
state rather than by editing a loaded document, so that upload-and-edit and
fill-from-empty produce the same file for the same inputs. That makes `D` a
*second construction of the schema*, and this identity is the only thing
standing between that construction and drift from the one `load()` performs.

**And it does a second job.** If `D` round-trips through `load()`, then `D` is
in the set `load()` accepts -- so the form cannot construct a document the CLI
would refuse without the guard saying so at write time. That is the executable
form of *the form's refusal is the CLI's refusal executed, not re-expressed*,
and it is why the eleven refusals outside the field table are a timing defect
rather than a correctness one: the guard refuses every one of them here, at
save, rather than the form refusing them while the user types.

Why `D` is a plain YAML-native mapping
--------------------------------------
The guard compares `D` against what `yaml.safe_load` returns, so any value
that does not survive that round trip fails the guard rather than differing
quietly. That is the intended behaviour and not a limitation to work around:
a tuple in `D` comes back a list and the write is refused, loudly, at the
point the tuple was introduced.

The one module that writes
--------------------------
`guard.WRITE_MODULES` names this file and `check_write_path()` refuses a file
opened for writing anywhere else in the served package. That is the inverse of
the read half's `test_the_server_has_no_write_path`, which is why the read
half's scan now excludes this module rather than being weakened: the two scans
together say *exactly one module writes, and it is this one*.
"""

import os

import yaml

from oneground import intake
from oneground.intake import fields

#: Everything this module writes goes through one suffix, so a crash leaves a
#: file nobody will mistake for a requirements file.
TEMP_SUFFIX = ".oneground-write"


class WriteRefused(Exception):
    """A write did not survive its own guard.

    Carries the refusal verbatim where one came from `intake`, because the
    form shows the CLI's words rather than its own. `lost` is set instead when
    the document parsed but came back different, which is the guard catching
    the form rather than the user.
    """

    def __init__(self, message, refusal=None, lost=None):
        super().__init__(message)
        self.refusal = refusal
        self.lost = lost


# --------------------------------------------------------------- the fold
def _coerce(param, value):
    """A form hands back strings. The declaration says what they are."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        if param.type is bool:
            low = text.lower()
            if low in ("true", "yes", "on", "1"):
                return True
            if low in ("false", "no", "off", "0"):
                return False
            raise WriteRefused(
                f"{param.name}: {value!r} is not true or false")
        if param.type is int:
            try:
                return int(text.replace("_", ""))
            except ValueError:
                raise WriteRefused(
                    f"{param.name} must be a whole number; got "
                    f"{value!r}") from None
        if param.type is float:
            try:
                return float(text)
            except ValueError:
                raise WriteRefused(
                    f"{param.name} must be a number; got {value!r}") from None
        if param.type is list:
            return [part.strip() for part in text.split(",") if part.strip()]
        return text
    return value


def _put(mapping, dotted, value):
    """Set a dotted path in a nested mapping, creating what it walks."""
    parts = dotted.split(".")
    node = mapping
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _get(mapping, dotted):
    """Read a dotted path, or None. Absent and null are the same here: a form
    field left empty and a key not written are the same statement."""
    node = mapping
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def document(state):
    """**The one construction path.** Form state in, `D` out.

    All three front doors end here -- fill-in-the-form, upload-and-edit and
    download-a-template -- which is what makes "three paths produce the same
    file for the same inputs" a property rather than a hope. Upload does not
    edit the mapping it loaded; it turns it into state and comes back through
    this function, so a file that arrives and a form that is typed converge on
    the same construction.

    Keys whose value is empty are left out entirely rather than written null.
    A form field nobody filled in and a key nobody wrote are the same
    statement, and writing `null` would make the file say something the user
    did not.
    """
    doc = {}
    for param in fields.FIELDS:
        value = _coerce(param, state.get(param.name))
        if value is None or value == [] or value == {}:
            # `oneground:` is the one exception, and it is not a setting: it
            # is the file saying which schema it is written against. A file
            # that leaves the tool without it is a file whose reader has to
            # guess, so it is written from the declared default when the form
            # did not carry one. Every other default stays out: writing
            # `normalized: false` and `count_min: 50` into every file would
            # fill it with values nobody chose.
            if param.name == "oneground" and param.default is not fields.NO_DEFAULT:
                _put(doc, param.name, param.default)
            continue
        _put(doc, param.name, value)
    return doc


def state_from_mapping(data):
    """A loaded requirements mapping, flattened back to form state.

    The inverse of the fold, and the reason upload-and-edit is not a second
    code path: what arrives becomes state, and state goes through
    `document()` like anything else.

    Keys the table does not declare are **not** carried. That is deliberate
    and it is visible rather than silent: the write guard compares the
    document this produces against what `load()` reads back, so a file
    carrying a key the table has never heard of does not round-trip, and the
    user is told at save rather than having the key quietly dropped.
    """
    return {p.name: _get(data, p.name) for p in fields.FIELDS
            if _get(data, p.name) is not None}


# ------------------------------------------------------------- the render
def render(doc, explain=None):
    """`D` to bytes.

    `explain` is the hook step 2 fills: a callable taking a dotted path and
    returning the explanation to write above it, which is the same string the
    form showed. It is separate from this function because the guard's
    identity is over the parsed document, so comments cannot change what this
    round-trips to -- and a renderer that could not have comments added to it
    later would have to be rewritten to gain them.
    """
    if explain is not None:                        # pragma: no cover - step 2
        raise NotImplementedError(
            "comment rendering is task 046 step 2; the hook is here so that "
            "adding it does not rewrite the writer")
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False,
                          allow_unicode=True)


# -------------------------------------------------------------- the guard
def write(doc, path):
    """Write `D` to `path`, or refuse. **The guard, on every write.**

    Temp file beside the target -- beside, because `intake` resolves relative
    paths against the file's own directory, so a temp file written anywhere
    else would validate a document with different paths than the one that
    lands.

    Returns the path written. Raises `WriteRefused`, never a partial file.
    """
    text = render(doc)
    tmp = path + TEMP_SUFFIX
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    try:
        try:
            loaded = intake.load(tmp)
        except intake.RequirementsError as e:
            raise WriteRefused(
                "the document this form built is one the tool refuses",
                refusal=str(e).replace(tmp, path)) from None
        if loaded.data != doc:
            raise WriteRefused(
                "the file did not read back as the document that was built",
                lost=_difference(doc, loaded.data))
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:                            # pragma: no cover
            pass
        raise
    os.replace(tmp, path)
    return path


def _difference(built, read_back):
    """Which dotted paths differ, for a guard failure a reader can act on.

    A guard that says only *they differ* hands back the obstacle rather than
    anything to do with it.
    """
    out = []
    for name in sorted(set(_flatten(built)) | set(_flatten(read_back))):
        a, b = _get(built, name), _get(read_back, name)
        if a != b:
            out.append((name, a, b))
    return out


def _flatten(mapping, prefix=""):
    """Every leaf path in a nested mapping."""
    out = []
    for key, value in (mapping or {}).items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.extend(_flatten(value, name + "."))
        else:
            out.append(name)
    return out
