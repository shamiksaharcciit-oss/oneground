"""One path grammar, and the walker over it. Task 045, finding 1.

**Why this module exists rather than a second copy of the grammar.**

Task 019's claim invariant makes every sentence in a report a `Claim` carrying
the rows it cites. `claims.check()` verified that the sentence follows from
what it cites, and **never that the citation is true** -- a `Cite` carries a
`source` path and a `value`, and nothing compared the two until a UI was asked
to render them side by side. Two defects had survived the invariant, two other
real-report tests, a published fixture and the teaser:

    verdict.py:606   cited 119.1     load.completed actually held 35731
    verdict.py:670   cited a budget  costs["config"] was never a key

Both were one-line repairs in task 041. The gap that let them through was not.

**The dependency that shapes this.** The resolver already existed, in
`oneground/lab/citations.py`, because 041 was forbidden to import
`oneground.report`: the lab's guard lists it in `MEASURING` and `citations.py`
is a transport module held to that rule. So the check cannot simply live in
`claims.py` and be called by the lab -- the lab could never call it.

Two options were on the table (045 finding 1) and this is **(a)**: the grammar
and the walker move to a module both import, and `lab/citations.py` stays the
lab's transport over it. Option (b) -- implement in `claims.py` and have the
lab cite that -- required the shared part to sit outside `oneground.report`
anyway, which is this module; (b) collapses into (a) as soon as the guard is
read.

**Why `oneground.receipts` is the home.** It is not in `MEASURING`, so a
transport module may import it; `oneground.report` already depends on it; and
resolving a citation *is* reading a receipt, which is what this package is
for. A new neutral package would have been a third place to look.

**There must be one grammar.** 041 chose the grammar `report.json` already
cites with, so a view's declared `reads` and a claim's `source` never need
translating. A second grammar would reintroduce precisely the place two things
can disagree -- which is the defect this module was written to close.
"""

import json
import os

#: Fields a list member may be identified by.
MEMBER_KEYS = ("config", "engine", "label", "name", "key")

#: A source that is not a `file:field` reference, and what it is instead.
#: Each is a legitimate shape in a real report, not a defect: a check that
#: failed them would be wrong three times to catch one.
NON_FIELD = {
    "(rule)": ("rule",
               "this follows from a rule, not from a row: no measurement was "
               "read to reach it"),
    "(not run)": ("not_run",
                  "the stage that would have produced this was not run"),
    "cost": ("cost_model",
             "the cost model, which is declared prices rather than a "
             "measurement"),
}

#: Sources naming something the user wrote rather than a receipt of this run.
REQUIREMENTS_PREFIX = "requirements:"

#: The outcomes a resolution can have. `field` and `within` point at something
#: a reader can open; the rest say why there is nothing to open, and are
#: answers rather than failures.
RESOLVED = "field"
WITHIN = "within"
RULE = "rule"
REQUIREMENTS = "requirements"
EVERY_OPTION = "every_option"
NOT_RUN = "not_run"
COST_MODEL = "cost_model"
UNRESOLVED = "unresolved"

#: Kinds that mean the citation named no single field **and that is correct**.
#: Distinguished from `UNRESOLVED`, which means it named one and it was not
#: there -- the distinction finding 1 turns on.
NOT_A_FIELD = (RULE, REQUIREMENTS, EVERY_OPTION, NOT_RUN, COST_MODEL)


class PathError(ValueError):
    """A citation path that is not well formed."""


def split_path(path):
    """`a.b[LABEL].c` -> `["a", "b[LABEL]", "c"]`, honouring nested brackets.

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
                raise PathError("unbalanced ] in path %r" % path)
        elif ch == "." and depth == 0:
            if buf:
                out.append(buf)
            buf = ""
            continue
        buf += ch
    if depth:
        raise PathError("unbalanced [ in path %r" % path)
    if buf:
        out.append(buf)
    return out


def split_source(source):
    """`file.json:a.b` -> `("file.json", "a.b")`. Either part may be empty."""
    head, sep, rest = str(source).partition(":")
    return (head, rest) if sep else (head, "")


def segment(seg):
    """`b[LABEL]` -> `("b", "LABEL")`; `b` -> `("b", None)`."""
    if seg.endswith("]") and "[" in seg:
        head, _, rest = seg.partition("[")
        return head, rest[:-1]
    return seg, None


def member_of(node, want):
    for it in node:
        if isinstance(it, dict) and any(it.get(k) == want
                                        for k in MEMBER_KEYS):
            return it
    return None


def walk(node, path, member=None):
    """`(found, value, reason)`. Never raises: unresolvable is an answer.

    Returning a reason rather than throwing is what lets a caller tell a
    citation that names nothing from one that names something absent, and
    those are different findings.
    """
    for seg in split_path(path):
        head, want = segment(seg)
        if isinstance(node, dict):
            if head not in node:
                return False, None, (
                    "no field %r here (this receipt has %s)"
                    % (head, sorted(node)[:5]))
            node = node[head]
        elif isinstance(node, list) and member is not None:
            got = member_of(node, member)
            if got is None:
                return False, None, "no member %r in this list" % member
            if head not in got:
                return False, None, ("no field %r on member %r"
                                     % (head, member))
            node = got[head]
        else:
            return False, None, ("cannot read %r from a %s"
                                 % (head, type(node).__name__))
        if want is None:
            continue
        if want == "*":
            return False, None, "names every option, not one field"
        if isinstance(node, list):
            got = member_of(node, want)
            if got is None:
                return False, None, ("no member %r in a list of %d"
                                     % (want, len(node)))
            node = got
        elif isinstance(node, dict):
            if want not in node:
                return False, None, "no key %r" % want
            node = node[want]
        else:
            return False, None, "cannot index a %s" % type(node).__name__
    return True, node, None


def contains(container, value):
    """Where `value` sits inside `container`, or None.

    Some sources name a container and cite a leaf inside it --
    `latency_shape_single_client.p95_across_runs` holds min/median/max and the
    claim cites the min; `qps_max` holds a block and the claim cites its
    `qps_max`. **That is an under-specified source rather than a wrong one**,
    and saying so is more useful than calling it a mismatch.
    """
    if isinstance(container, dict):
        for k, v in container.items():
            if v == value:
                return k
    return None


def scoped(data, path, member):
    """Enter `engines[member]` when a source starts below that level.

    `verify.json:load.achieved_qps` names no engine; the citation's `member`
    does. Descending by the member rather than guessing is what makes a
    two-engine run's citations unambiguous.
    """
    if not (isinstance(data, dict) and "engines" in data and member):
        return data
    first = split_path(path)[0] if path else ""
    head, _ = segment(first)
    if head in data:
        return data
    engines = data["engines"]
    if isinstance(engines, list):
        got = member_of(engines, member)
        if got is not None:
            return got
    elif isinstance(engines, dict) and member in engines:
        return engines[member]
    return data


def classify(source):
    """What kind of thing this source names, before any file is opened.

    Returns `(kind, note)` for a source that is legitimately not a field, or
    `(None, None)` for one that should resolve to one.
    """
    s = str(source or "")
    if not s:
        return UNRESOLVED, "no source given"
    if s in NON_FIELD:
        kind, note = NON_FIELD[s]
        return kind, note
    if s.startswith(REQUIREMENTS_PREFIX):
        return REQUIREMENTS, ("an input the user wrote, not a measurement "
                              "this run made")
    _file, path = split_source(s)
    if "[*]" in path or path.endswith("[*]"):
        return EVERY_OPTION, "names every option rather than one field"
    return None, None


def _load(workdir, filename, cache):
    if cache is not None and filename in cache:
        return cache[filename]
    p = os.path.join(workdir, filename)
    data = None
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:                                    # noqa: BLE001
            data = None
    if cache is not None:
        cache[filename] = data
    return data


def resolve(workdir, source, member=None, cache=None):
    """Read what a citation names. `(kind, value, note)`.

    `kind` is one of the constants above. `value` is meaningful only for
    `field` and `within`; for everything else it is None and `note` says why.

    This is deliberately **not** a comparison: it answers *what is at that
    path*, and the caller decides what a disagreement means. The lab renders
    it; `report.claims.check` fails on it. One resolver, two consequences.
    """
    kind, note = classify(source)
    if kind is not None:
        return kind, None, note

    filename, path = split_source(source)
    data = _load(workdir, filename, cache)
    if data is None:
        return UNRESOLVED, None, "%s is not in this run" % filename
    if not path:
        return UNRESOLVED, None, "%s names no field" % filename

    found, value, reason = walk(scoped(data, path, member), path, member)
    if not found:
        return UNRESOLVED, None, reason
    return RESOLVED, value, None
