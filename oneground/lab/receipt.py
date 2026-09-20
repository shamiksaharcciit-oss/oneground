"""The rendering contract, extended from state columns to receipt fields.

Task 021 gave the lab one rule -- *a view takes state and returns a drawing* --
and enforced it on simulator state: numpy columns, a state header, and an
epsilon that decides what a change would cost. Task 041 needs the same rule
over the four receipts a run holds (`characterization.json`, `simulate.json`,
`verify.json`, `report.json`), which have none of those things. This module is
that extension, and the rule it lands on is inherited by every page added
later, so it is written out rather than assumed.

    a view reads the declared fields of ONE receipt and returns a drawing

Four decisions, each with the reason it went that way.

**One receipt per view.** A view names `receipt` and may read nothing else.
A page that wants two receipts is two views composed by the server, not one
view reaching into a second file. The reason is provenance: a drawing says
what it was drawn from, and "drawn from simulate.json" is a claim a reader can
check. "Drawn from four files" is not.

**Declared fields are paths, in the same grammar the report cites with.**
A view declares `rows[].recall_at_10`, and `report.json` cites
`simulate.json:rows[LABEL].recall_at_10`. That is deliberate: the language a
drawing states its provenance in is the language a claim states its citation
in, so the two are comparable rather than merely adjacent. A drawer entry and
a view's `reads` can be checked against each other because they are written
the same way. Any other grammar would have made the evidence drawer translate
between two notations, and a translation is a place two things can disagree.

**A receipt reader refuses no vectors, and says why not.** `StateColumns`
refuses vector columns at run time because state carries vectors and a view
with one in reach could do arithmetic on it. The receipts carry none -- the
measures are already scalars and short lists, which was checked rather than
assumed before this was written. So the run-time refusal has nothing to
refuse, and the enforcement that remains is the one that was always doing the
work: `guard.py` reads every view module's source and fails the suite on a
measuring import or on vector arithmetic. This asymmetry is recorded here
because the absence of a check is exactly the kind of thing a later reader
assumes was an oversight.

**An absent field is a gap, not a crash.** A receipt written before a field
existed simply lacks it, and older runs are the normal case rather than the
exception. `has` asks; reading an absent field raises, so a view cannot
silently render `None` as though it were a measurement.
"""

from .contract import COULDNT_CHECK, ContractError, Drawing, check_drawing

#: A receipt drawing does not move when epsilon moves: it is a rendering of
#: what a command already wrote, and epsilon is a question about re-running.
#: Named rather than left blank so `on_epsilon` is never asked of one.
NOT_EPSILON = "not_epsilon"

#: The receipts a run holds. A view's `receipt` must be one of them: a view
#: reading some other file would be a view reading a file nobody verified.
RECEIPTS = ("characterization.json", "simulate.json", "verify.json",
            "report.json")

# Documents a view may read that are not files on disk. They are named rather
# than smuggled in, because "drawn from a file whose digest was checked" is the
# property the four receipts have and these do not. What they have instead is
# narrower, and it is the condition of being on this list:
#
#   every value in a transport document is copied from a named receipt,
#   without being recomputed, and carries where it came from
#
# A view drawing one of these is therefore still drawing recorded values with
# stated provenance -- the provenance is simply per-value rather than per-file.
# Only the named builder may construct each one.

#: Transport's index over many runs (`runs.index_runs`). Each row carries its
#: own run's digest verification, so a row built from files that failed their
#: manifest says so on the row itself.
RUN_INDEX = "run_index"

#: One report's citations, each resolved against the receipt it names
#: (`runs.resolve_citations`). Carries both the value the claim cites and the
#: value at the field it names, so the drawer can show them side by side
#: without computing either.
CITATIONS = "citations"

TRANSPORT_DOCS = (RUN_INDEX, CITATIONS)

#: What `draw_receipt` will accept as a view's `receipt`.
DRAWABLE = RECEIPTS + TRANSPORT_DOCS

#: Fields by which a member of a list is named, in order. `rows[LABEL]` finds
#: the row whose `config` is LABEL; `engines[qdrant]` finds the engine.
MEMBER_KEYS = ("config", "engine", "label", "name", "key")


class UndeclaredField(ContractError):
    """A view read a field it did not declare."""


class AbsentField(ContractError):
    """A view read a field this receipt does not carry. Ask `has` first."""


class UnknownReceipt(ContractError):
    """A view named a file that is not one of a run's receipts."""


def split_path(path):
    """"a.b[LABEL].c" -> ["a", "b[LABEL]", "c"], honouring nested brackets.

    A config label carries its own brackets and dots
    (`semantic_sharded[M=32,epsilon=0.2]`), so neither a naive split on "."
    nor a non-greedy bracket match is correct here.
    """
    out, buf, depth = [], "", 0
    for ch in path:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth < 0:
                raise ContractError(f"unbalanced ] in path {path!r}")
        elif ch == "." and depth == 0:
            if buf:
                out.append(buf)
            buf = ""
            continue
        buf += ch
    if depth:
        raise ContractError(f"unbalanced [ in path {path!r}")
    if buf:
        out.append(buf)
    return out


def _segment(seg):
    """"rows[LABEL]" -> ("rows", "LABEL"); "rows[]" -> ("rows", ""); "a" ->
    ("a", None)."""
    if seg.endswith("]") and "[" in seg:
        head, _, rest = seg.partition("[")
        return head, rest[:-1]
    return seg, None


def _member(node, want):
    for it in node:
        if isinstance(it, dict) and any(it.get(k) == want
                                        for k in MEMBER_KEYS):
            return it
    return None


class ReceiptFields:
    """One receipt as a view sees it.

    * only the paths the view declared in `reads`: anything else raises
      `UndeclaredField`, so a drawing's provenance is what it says it is
    * an absent path raises `AbsentField`; `has` asks without raising
    * `read` records the paths actually read, which `draw_receipt` puts on
      the drawing

    `each` walks a list of members -- rows, engines, options -- handing out a
    reader per member whose declared leaves are the ones declared under
    `name[]`. A view therefore declares `rows[].recall_at_10` once and reads
    it once per row, and the provenance stays one line rather than eight
    hundred.
    """

    def __init__(self, receipt, data, reads, _prefix="", _read=None):
        self.receipt = receipt
        self._data = data
        self._reads = frozenset(reads)
        self._prefix = _prefix
        self.read = set() if _read is None else _read

    # ---------------------------------------------------------------- asking
    def _declared(self, path):
        # `_reads` is always local to this reader's scope -- the leaves under
        # `rows[]` for a row reader -- while `_prefix` exists only so the
        # provenance reads `rows[].config` rather than `config`. Matching the
        # prefixed form against the local set was the first bug this file had.
        if path not in self._reads:
            raise UndeclaredField(
                f"{self.receipt}:{self._prefix}{path} is not in this view's "
                f"`reads` ({sorted(self._reads)[:6]}...)")
        return self._prefix + path

    def _walk(self, path):
        """(found, value). Never raises for absence."""
        node = self._data
        for seg in split_path(path):
            head, want = _segment(seg)
            if isinstance(node, dict):
                if head not in node:
                    return False, None
                node = node[head]
            else:
                return False, None
            if want is None:
                continue
            if want == "":
                return isinstance(node, list), node
            if isinstance(node, list):
                got = _member(node, want)
                if got is None:
                    return False, None
                node = got
            elif isinstance(node, dict):
                if want not in node:
                    return False, None
                node = node[want]
            else:
                return False, None
        return True, node

    def has(self, path):
        """Whether this receipt carries a declared field."""
        self._declared(path)
        found, _ = self._walk(path)
        return found

    def __getitem__(self, path):
        full = self._declared(path)
        found, value = self._walk(path)
        if not found:
            raise AbsentField(
                f"{self.receipt}:{full} is not in this receipt; check `has` "
                "first. A receipt written before a field existed simply "
                "lacks it, and rendering that as a value would state a "
                "measurement nobody made.")
        self.read.add(full)
        return value

    def get(self, path, default=None):
        return self[path] if self.has(path) else default

    # ---------------------------------------------------------------- walking
    def each(self, name):
        """Yield a reader per member of the list at `name`.

        Each reader's declared leaves are those declared under `name[]`, and
        reading one records `name[].leaf` once however many members there are.
        """
        # Match on the LOCAL prefix, because `_reads` is local to this
        # reader; record with the global one, because provenance is absolute.
        # Conflating the two broke `each` at the top level, and would have
        # broken a nested `each` -- claims[].entries[] -- in the same way.
        local = f"{name}[]."
        prefix = f"{self._prefix}{local}"
        leaves = {r[len(local):] for r in self._reads if r.startswith(local)}
        if not leaves:
            raise UndeclaredField(
                f"{self.receipt}: this view declares no fields under "
                f"{name}[]; declare {name}[].<field> to walk it")
        found, node = self._walk(f"{name}[]")
        if not found:
            return
        for item in node:
            yield ReceiptFields(self.receipt, item, leaves,
                                _prefix=prefix, _read=self.read)

    def count(self, name):
        """How many members the list at `name` has, without reading one."""
        found, node = self._walk(f"{name}[]")
        return len(node) if found else 0


class ReceiptView:
    """Subclass, set `name`, `receipt` and `reads`, implement `render`.

    `render(fields) -> Drawing`, and nothing else: no files, no network, no
    clock, exactly as a state view. What it is handed is a `ReceiptFields`
    over one receipt rather than a `StateColumns` over one state.
    """

    name = ""
    receipt = ""
    reads = ()

    def params(self):
        return {}

    def render(self, fields):                         # pragma: no cover
        raise NotImplementedError


def draw_receipt(view, data, receipt=None):
    """Draw `view` over one parsed receipt. The only way a receipt drawing is
    made.

    `data` is already-parsed JSON: the contract does not read files, so that a
    view cannot be handed a path and reach for something else.
    """
    name = receipt or view.receipt
    if name not in DRAWABLE:
        raise UnknownReceipt(
            f"{view.name}: {name!r} is not one of a run's receipts "
            f"{RECEIPTS} nor {RUN_INDEX!r}")
    fields = ReceiptFields(name, data, view.reads)
    d = check_drawing(view, view.render(fields))
    d.params = dict(view.params())
    d.reads = sorted(fields.read)
    d.source = {"receipt": name,
                "run": data.get("run") if isinstance(data, dict) else None,
                "schema": data.get("schema") if isinstance(data, dict)
                else None}
    d.epsilon = NOT_EPSILON
    return d


def gap(reason):
    """A `couldnt_check` reason in the form `Drawing.gaps` requires."""
    return f"{COULDNT_CHECK}: {reason}"


__all__ = ["AbsentField", "DRAWABLE", "Drawing", "MEMBER_KEYS", "NOT_EPSILON",
           "RECEIPTS", "RUN_INDEX", "ReceiptFields", "ReceiptView",
           "UnknownReceipt", "UndeclaredField", "draw_receipt", "gap",
           "split_path"]
