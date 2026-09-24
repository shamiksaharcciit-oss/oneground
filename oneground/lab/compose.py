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
import tempfile

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

    def __init__(self, message, refusal=None, lost=None, field=None):
        super().__init__(message)
        self.refusal = refusal
        self.lost = lost
        #: Which declared field the refusal is about, where one can be
        #: named. Both doors set it, because the same refusal arriving by
        #: upload and by save should point at the same box.
        self.field = field


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


def open_text(text):
    """**Door two.** An uploaded file, as form state, validated on arrival.

    Three things happen here and the order is the point. The bytes are
    parsed; the document is validated by `intake` itself; and only then is it
    flattened to state. What comes back is state, so the upload path rejoins
    `document()` rather than becoming a second way to build a file.

    **Validation does not need to know where the file will live.** `load()`
    reads the document and never touches the filesystem -- only
    `input_paths()` does, and `load()` does not call it -- so a temp file
    anywhere validates exactly what a file in the runs directory would. That
    is worth stating because the obvious worry is that a relative path would
    resolve differently, and it would, if anything resolved it.

    A refusal is named against **the field it belongs to** rather than
    reported as a parse position, which is the whole difference between
    arriving in a form and arriving at a traceback.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise WriteRefused(
            "this file is not readable as YAML",
            refusal=_yaml_refusal(e)) from None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise WriteRefused(
            "a requirements file is a mapping of fields",
            refusal="the document is a "
                    f"{type(data).__name__}, not a mapping of fields")

    handle, tmp = tempfile.mkstemp(suffix=".yaml", prefix="oneground-open-")
    os.close(handle)
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        try:
            intake.load(tmp)
            refusal, field = None, None
        except intake.RequirementsError as e:
            refusal = str(e).replace(tmp + ": ", "")
            field = _field_named_in(refusal)
    finally:
        try:
            os.remove(tmp)
        except OSError:                                # pragma: no cover
            pass

    state = state_from_mapping(data)
    return {
        "state": state,
        "refusal": refusal,
        "field": field,
        # Keys the table does not declare. Carried in the answer rather than
        # dropped in silence: the form cannot show them, and a user whose
        # file loses a block deserves to be told which one before they save
        # rather than after.
        "not_offered": sorted(set(_flatten(data)) - set(_flatten(
            document(state)))),
    }


def _yaml_refusal(error):
    """A YAML error, as a sentence rather than a stack.

    The `problem` and the line are the two parts a person can act on; the
    rest of a `yaml.YAMLError` is about the parser.
    """
    mark = getattr(error, "problem_mark", None)
    problem = getattr(error, "problem", None) or str(error)
    if mark is None:
        return problem
    return f"line {mark.line + 1}, column {mark.column + 1}: {problem}"


def _without_path_prefix(message, path):
    """`intake` names the file it was reading before every refusal.

    Useful at a terminal, noise in a form, and an absolute path in a form is
    a slice-1 finding in its own right. The prefix is removed by the path
    that produced it rather than by a general rule, so a message that happens
    to contain a colon keeps it.
    """
    prefix = path + ": "
    return message[len(prefix):] if message.startswith(prefix) else message


def _field_named_in(refusal):
    """Which declared field a refusal is about, or None.

    `intake` names the field in every message it raises -- that is its own
    first rule -- so this looks for a declared name in the sentence rather
    than parsing the sentence. The longest match wins, because
    `corpus.sample.text.model` contains `corpus.sample.text`, and the more
    specific field is the one the form should point at.

    None is a real answer and not a failure: eleven of the twenty-five
    refusals are not about a declared field at all, and saying so is more
    useful than attaching one of them to a field it does not belong to.
    """
    named = [p.name for p in fields.FIELDS if p.name in refusal]
    return max(named, key=len) if named else None


# ------------------------------------------------------------- the render
#: Written once at the top of every file this produces. The front-door
#: ruling says comments are never read back as data, and a file that leaves
#: the tool should say so in itself rather than relying on a reader knowing.
PREAMBLE = (
    "# Written by oneground. Every explanation below is generated from the\n"
    "# same declaration the form shows, so the two cannot drift.\n"
    "#\n"
    "# The comments are not read back. Editing one changes nothing about the\n"
    "# run, and saving through the form rewrites them from the current text.\n"
)


def _comment(text, indent):
    """One explanation, wrapped, as YAML comment lines at `indent`.

    Wrapped here rather than left to the writer of the declaration: a note
    is one sentence in a table and a paragraph in a file, and asking every
    author to hard-wrap for an indentation they cannot see is asking them to
    maintain a layout.
    """
    import textwrap
    pad = " " * indent
    return "".join(
        pad + "# " + line + "\n"
        for line in textwrap.wrap(" ".join(text.split()),
                                  width=max(30, 74 - indent)))


def render(doc, explain=None):
    """`D` to bytes, with each field's explanation above it.

    **The comments come from the same strings the form shows**, because both
    read `fields.BY_NAME[...].note`. That is what makes the one-string test
    a property rather than an agreement between two places: there is one
    place.

    `explain` overrides the source of those strings and exists for the test
    that proves the writer uses what it is given rather than reaching for a
    second copy. It takes a dotted path and returns the text, or None.

    Comments cannot change what this round-trips to, which is why the guard's
    identity is over the parsed document. That was settled before this
    function had comments in it; adding them changed nothing about the guard,
    which is the strongest evidence the rule was drawn in the right place.
    """
    if explain is None:
        def explain(name):
            param = fields.BY_NAME.get(name)
            return param.note if param else None

    lines = [PREAMBLE]
    lines.extend(_emit(doc, explain, prefix="", indent=0))
    return "".join(lines)


def _emit(node, explain, prefix, indent):
    """The document, in the declaration's order, each leaf explained.

    Ordered by `fields.FIELDS` rather than by the mapping, so two files with
    the same content are the same bytes -- a file whose keys wander is a file
    nobody can diff. Anything the table does not declare is written after, in
    its own order, rather than dropped: the guard would catch a loss, and a
    file the form cannot fully explain is still a file it must write whole.
    """
    out = []
    pad = " " * indent
    declared = [p.name for p in fields.FIELDS]

    def rank(key):
        full = prefix + key
        for i, name in enumerate(declared):
            if name == full or name.startswith(full + "."):
                return i
        return len(declared)

    for key in sorted(node, key=rank):
        value = node[key]
        full = prefix + key
        if isinstance(value, dict):
            out.append("%s%s:\n" % (pad, key))
            out.extend(_emit(value, explain, full + ".", indent + 2))
            continue
        note = explain(full)
        if note:
            out.append(_comment(note, indent))
        scalar = yaml.safe_dump(value, default_flow_style=True,
                                allow_unicode=True).strip()
        if scalar.endswith("\n..."):                    # pragma: no cover
            scalar = scalar[:-4].strip()
        out.append("%s%s: %s\n" % (pad, key, scalar))
    return out


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
            # `intake` prefixes every message with the file it was reading,
            # which here is a temp file nobody asked about. Printing the
            # target instead just swaps one absolute path for another --
            # slice 1's own finding, arriving again -- so the prefix comes
            # off entirely. The form knows which file it is writing; the
            # sentence is about a field.
            raise WriteRefused(
                "the document this form built is one the tool refuses",
                refusal=_without_path_prefix(str(e), tmp),
                field=_field_named_in(str(e))) from None
        if loaded.data != doc:
            raise WriteRefused(
                "the file did not read back as the document that was built",
                lost=_difference(doc, loaded.data))
        # INSIDE the guard, not after it. This was the one step the cleanup
        # did not cover: `os.replace` can fail -- a sharing violation on
        # Windows is the ordinary way -- and when it did, the exception
        # propagated and the temp file stayed in the runs directory.
        #
        # A guard that cleans up after every failure except its last step
        # leaves its debris in exactly the case it was written for, and the
        # case is rare enough to go unnoticed: it showed up as a stray
        # `.oneground-write` beside a refused write, which is the one place
        # nobody looks for a leftover.
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
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
