"""Every module that writes a receipt routes its paths through `public_path`.

WHY "TRACKED" IS THE WRONG WORD, AND THIS GUARD'S SUBJECT IS NOT THAT
----------------------------------------------------------------------
`test_no_tracked_file_carries_a_machine_identifier` scans **what git tracks**.
That predicate was chosen when the exposure was a committed decision log
(task 016), and it has been right about every instance it can see.

It cannot see the one that matters most. `runs/` is gitignored, so a receipt
written there is outside its subject forever -- and `runs/` is precisely what
`corpora/export_teaser_data.py` reads on its way to a published page. Measured
in task 044e: three `runs/*/report.json` in this checkout carry
`C:\\Users\\...\\prices.example.yaml`, dated ten days before task 043's
write-site fix, invisible to the tracked scan and readable by a publisher.

So the blind spot is **not a bug in that guard's implementation. It is its
subject.** It asks *what does git track*; the exposure is *what does a
publishing path read*, and those differ exactly where it matters. The
predicate should never have been "tracked":

    tracked        -> a file git happens to store
    receipt        -> a file this project writes as a record of a measurement

The second is the class the rule is about, and whether git stores it is an
unrelated fact about a `.gitignore`.

**Both checks stay.** Two checks that see different things are not redundant,
and this pair is the proof: one scans the tracked tree, one scans the write
site, and the gap between them held a ten-day-old machine identifier on a
publishing path. Deleting either restores a blind spot.

PROVENANCE, NOT LOCALITY
------------------------
The obvious implementation is "the sanitiser call appears in the same module
as the write". That is the locality predicate, and task 044d's finding is that
selecting on locality is how a check ends up unable to see its own subject:
**the write and the sanitiser do not have to share a module**, and in this
project they frequently do not -- `report/__init__.py` writes the field and
`receipts.public_path` sanitises it.

So a path-bearing field is accepted when its value **came from** a sanitiser,
by any of these routes, and not when a sanitiser merely appears nearby:

  - the value expression is a call to one of `SANITISERS`;
  - the value is a name bound, anywhere in the enclosing function, to such a
    call, or to a subscript of one;
  - the whole payload is wrapped in `public_paths_in(...)`;
  - the field is declared in `DECLARED_PUBLIC` with the reason it cannot
    carry a machine path.

The declaration is the escape hatch and it is deliberately the only one, for
the reason task 043 gave: a rule with an undeclared exception is a rule
nobody can check.

WHAT THIS CANNOT SEE
--------------------
It reads the roots it is given. A writer outside them -- a scratch script, a
notebook, a one-off -- is not covered, and task 044c's instance was exactly
that: a script under `tasks/scratch/` whose output was later committed. Pass
that directory in when it exists; `known_roots()` does. Where it does not
exist, this guard sees two of the three known instances and says so rather
than claiming three.
"""

import ast
import os
import re
import warnings

#: Calls that serialise a receipt to disk. A payload reaching one of these is
#: a receipt, wherever the file lands.
RECEIPT_WRITERS = ("write_json_stable", "dump", "dumps", "safe_dump",
                   "write_text")

#: Calls that make a value fit to record. `receipts.public_path` and its
#: table form; nothing else counts, because a private reimplementation is a
#: second place for the rule to be wrong (task 043).
SANITISERS = ("public_path", "public_paths_in")

#: Keys whose value is a filesystem path. Matched on the key name, because
#: that is what a reader of the receipt sees.
#:
#: **Key names are the weaker of this guard's two detectors** and are kept
#: only because they catch fields whose value is computed elsewhere. Matching
#: on a name misses a path under a name that does not say so -- in this
#: repository, `query_trace_state` held one three lines below a `state_file`
#: that this pattern did catch. That near-miss is why `PATH_PRODUCERS` exists.
PATH_KEY = re.compile(
    r"(^|_)(path|paths|dir|directory|file|filename|workdir|checkout|root)$")

#: Calls that turn something into a filesystem path. A receipt field whose
#: value comes from one of these holds a path **whatever the key is called**,
#: which is the provenance detector and the stronger of the two.
#:
#: `os.path.basename` is on this list although a basename cannot name a
#: directory. It is half of `public_path` written out by hand, and task 043's
#: finding is that a private reimplementation of a shared rule is a second
#: place for it to be wrong -- the half that is missing is the repo-relative
#: case, so a basename silently discards *which* file inside the checkout it
#: was. Safe today, and the wrong shape.
PATH_PRODUCERS = ("basename", "dirname", "abspath", "realpath", "relpath",
                  "expanduser", "normpath", "getcwd", "fspath")

#: Fields that hold a path-shaped key and cannot carry a machine path, with
#: the reason. The only exception route, and each entry is a claim someone can
#: check.
#: **This started with a second entry and it was false.** It declared
#: `requirements_file` public "because the file is inside the checkout, so the
#: path is repo-relative by construction". The path was
#: `os.path.abspath(requirements_path)` at four write sites, and every local
#: `build_info.json` carries a home directory because of it. The declaration
#: was written from what the field ought to hold rather than from what the
#: code put in it -- which is the exact move an exception list exists to make
#: visible, and it was visible for about an hour.
#:
#: So an entry here states what the *code* guarantees, not what the field is
#: for, and anything that cannot be said that way is a finding rather than an
#: exception.
DECLARED_PUBLIC = {
    ("*", "path_note"):
        "prose describing the transform; never holds a path itself",
}


def _is_sanitised_call(node):
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in SANITISERS) or (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in SANITISERS)


def _sanitised_names(fn):
    """Names bound to a sanitiser's result anywhere in this function.

    Provenance rather than locality: the binding may be many lines from the
    write, and the sanitiser may be imported from another module.
    """
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            src = node.value
            if isinstance(src, ast.Subscript):
                src = src.value
            if _is_sanitised_call(src):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        out.add(t.id)
        elif isinstance(node, (ast.For, ast.comprehension)):
            pass
    return out


def _value_is_public(value, safe_names):
    if _is_sanitised_call(value):
        return True
    if isinstance(value, ast.Name) and value.id in safe_names:
        return True
    if isinstance(value, ast.Subscript):
        return _value_is_public(value.value, safe_names)
    # A literal cannot name anybody's machine.
    if isinstance(value, ast.Constant):
        return True
    # An f-string or concatenation of literals only -- still no machine path.
    if isinstance(value, ast.JoinedStr):
        return all(isinstance(v, ast.Constant) for v in value.values)
    return False


def _produces_a_path(node):
    """Does this expression compute a filesystem path, whatever it is called?

    The provenance detector. A key called `state_file` and a key called
    `query_trace_state` are indistinguishable by name and identical in what
    they hold; this sees both, because it looks at where the value came from.
    """
    # A value that IS a dict is not itself a path; its own keys are checked
    # individually by the caller. Without this, `epsilon` was reported as
    # path-bearing because a sibling key inside it held a basename -- a
    # finding attributed to the wrong key, which sends the reader to a line
    # where nothing is wrong and is worse than no finding at all.
    if isinstance(node, ast.Dict):
        return False
    stack = [node]
    while stack:
        cur = stack.pop()
        if (isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute)
                and cur.func.attr in PATH_PRODUCERS):
            return True
        for child in ast.iter_child_nodes(cur):
            if isinstance(child, ast.Dict):
                continue          # visited on its own
            stack.append(child)
    return False


def _declared(module, key):
    return (("*", key) in DECLARED_PUBLIC
            or (module, key) in DECLARED_PUBLIC)


def _payload_dicts(fn):
    """Every dict literal that becomes a receipt written by this function.

    **The inline case is the rare one.** A receipt is usually built into a
    local and written by name -- `write_json_stable(path, report)` -- so a
    guard that only inspects dict literals sitting inside the writer's
    argument list sees almost nothing. That is how the first three versions of
    this function each missed `price_table`: requiring the dict and the write
    to be syntactically adjacent is a locality predicate, and this project's
    receipts are assembled a long way from where they are serialised.

    So: find the names handed to a receipt writer, then the dict literals
    assigned to them. One dataflow step, within one function, which is where
    receipts are assembled in this codebase.
    """
    written = set()
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, (ast.Name, ast.Attribute))):
            continue
        name = (node.func.id if isinstance(node.func, ast.Name)
                else node.func.attr)
        if name not in RECEIPT_WRITERS:
            continue
        for arg in node.args:
            for sub in _unsanitised_dicts(arg):
                yield sub
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Name):
                    written.add(sub.id)
    if not written:
        return
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id in written
                   for t in node.targets):
            continue
        for sub in _unsanitised_dicts(node.value):
            yield sub


def _unsanitised_dicts(node):
    """Dict literals under `node`, **not descending into a sanitiser call**.

    `public_paths_in({"path": raw, ...})` is the correct idiom and the whole
    dict is public. Walking into it and judging its keys one by one reported
    the *fixed* form of task 044c's own instance as a defect -- a guard
    failing the code written to satisfy it, which is how a guard gets
    switched off.
    """
    stack = [node]
    while stack:
        cur = stack.pop()
        if _is_sanitised_call(cur):
            continue
        if isinstance(cur, ast.Dict):
            yield cur
        stack.extend(ast.iter_child_nodes(cur))


def _enclosing_functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def findings_in_source(src, module):
    """Path-bearing receipt fields whose value did not come from a sanitiser.

    **Scope: every dict literal in the module, not only those at a call to a
    receipt writer.** The first version required the dict to sit inside a
    `json.dump`/`write_json_stable` call, and it missed the instance it was
    written for: `price_table.path` is a literal in `cost/__init__.py`'s
    `as_dict()` and is written by `report/__init__.py`, two modules away.

    That restriction was a locality predicate wearing a provenance predicate's
    clothes -- the same mistake as selecting on the sanitiser's module, one
    level deeper, because **the field and the write do not share a module
    either.** Whether a given dict reaches a receipt is not knowable
    statically, so the honest scope is every dict that could, and
    `DECLARED_PUBLIC` carries the ones that do not with the reason.
    """
    try:
        # A file in the scanned roots may carry an invalid escape sequence,
        # which `ast.parse` reports as a SyntaxWarning against `<unknown>`.
        # That is a real thing about that file and not this guard's subject,
        # so it is silenced here rather than printed into these findings.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for fn in _enclosing_functions(tree):
        safe = _sanitised_names(fn)
        for sub in _payload_dicts(fn):
                    for k, v in zip(sub.keys, sub.values):
                        if not (isinstance(k, ast.Constant)
                                and isinstance(k.value, str)):
                            continue
                        # A key whose value is a dict is a container, not a
                        # path, however path-like its name: `requirements_file`
                        # holds `{"path": ..., "sha256": ...}` and its `path`
                        # is judged on its own line. Without this the guard
                        # reported the container and the field, and the
                        # container's line is where nothing is wrong.
                        if isinstance(v, ast.Dict):
                            continue
                        if _declared(module, k.value):
                            continue
                        if _value_is_public(v, safe):
                            continue
                        by_name = bool(PATH_KEY.search(k.value))
                        by_origin = _produces_a_path(v)
                        if not (by_name or by_origin):
                            continue
                        out.append((
                            module, getattr(v, "lineno", fn.lineno), k.value,
                            fn.name, "origin" if by_origin else "name"))
    return out


def known_roots(repo_root):
    """Where receipts are written from. Scratch is included when present.

    `tasks/scratch/` is gitignored and often absent, and task 044c's instance
    was a scratch script whose output was committed. Including it when it
    exists is the difference between seeing two of the three known instances
    and seeing three.
    """
    roots = [os.path.join(repo_root, "oneground"),
             os.path.join(repo_root, "corpora")]
    scratch = os.path.join(repo_root, "tasks", "scratch")
    if os.path.isdir(scratch):
        roots.append(scratch)
    return [r for r in roots if os.path.isdir(r)]


def findings(roots, repo_root):
    out = []
    for root in roots:
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in sorted(files):
                if not fn.endswith(".py") or fn.startswith("test_"):
                    continue
                path = os.path.join(base, fn)
                rel = os.path.relpath(path, repo_root).replace(os.sep, "/")
                with open(path, encoding="utf-8-sig") as f:
                    out.extend(findings_in_source(f.read(), rel))
    return out
