"""The static half of the lab contract: a view module may not measure.

Reads the source of every module in `oneground/lab/views/`. It reads all of
them, registered or not, because a module sitting there is a view module. It
names every line that does one of these:

  vector-arithmetic  `@`; dot, vdot, inner, outer, matmul, einsum, tensordot,
                     kron, cross; anything under `linalg`; norms and distances
                     (norm, cdist, pdist, cosine, euclidean, ...); clustering,
                     projection and neighbour indexes (kmeans, PCA, UMAP, svd,
                     eig, faiss index types)
  import             anything outside a short allow-list: numpy, math,
                     dataclasses, typing, collections, functools, itertools,
                     and `oneground.lab` itself. That keeps out faiss,
                     scikit-learn, scipy, torch, umap, the model families and
                     every oneground module that measures, reads corpora or
                     talks to an engine.
  vector-data        a vector column by name (`partition.centroids`), or a
                     value named centroids, vectors, queries or embeddings
  file-io            open, load, fromfile, memmap, read_state, urlopen and
                     the like: a view is handed its state and reads nothing
                     else
  dynamic-code       __import__, importlib, eval, exec, compile: the ways
                     around everything above

It checks names and syntax. It does not infer types, so `a * b` over two
vectors would pass it. That is why it is the second half of the contract. The
first half, in `contract.StateColumns`, is that a view is never handed a vector
to multiply.

`oneground/lab/test_lab.py` runs it over every view module, so a view that
measures fails the build.
"""

import ast
import importlib.util
import os

from .contract import PROJECTION_COLUMNS, VECTOR_COLUMNS

VIEWS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "views")
VIEWS_PACKAGE = "oneground.lab.views"

ALLOWED_IMPORTS = ("numpy", "math", "dataclasses", "typing", "collections",
                   "functools", "itertools", "oneground.lab")

VECTOR_ARITHMETIC = frozenset({
    "dot", "vdot", "inner", "outer", "matmul", "einsum", "tensordot", "kron",
    "cross", "linalg", "norm", "cdist", "pdist", "cosine", "euclidean",
    "sqeuclidean", "pairwise_distances", "cosine_similarity", "kmeans",
    "Kmeans", "KMeans", "NearestNeighbors", "PCA", "pca", "UMAP", "svd",
    "eig", "eigh", "cholesky", "IndexFlatIP", "IndexFlatL2",
    "IndexHNSWFlat",
})
VECTOR_DATA = frozenset({"centroids", "vectors", "queries", "embeddings"})
FILE_IO = frozenset({
    "open", "load", "loadtxt", "genfromtxt", "fromfile", "memmap",
    "read_state", "load_state", "urlopen", "read_bytes", "read_text",
    "socket", "requests", "urllib", "http",
})
DYNAMIC_CODE = frozenset({"__import__", "importlib", "import_module", "eval",
                          "exec", "compile"})

_NAME_RULES = ((VECTOR_ARITHMETIC, "vector-arithmetic"),
               (VECTOR_DATA, "vector-data"),
               (FILE_IO, "file-io"),
               (DYNAMIC_CODE, "dynamic-code"))

# Arithmetic and statistics over a declared placement (task 027). A view is
# handed the projection -- drawing the picture is passing these numbers to a
# mark -- so the rule cannot be "you may not have it", as it is for vectors.
# It is "you may not compute with it".
#
# Naming the columns here would be useless: a view that draws the projection
# mentions them, legitimately, in `reads` and in the subscript that reads
# them. So the guard tracks the NAMES a module binds from a projection column
# and flags those names in a numeric context. `contract.Positions` refuses the
# same operations at run time and is the primary guarantee; this catches it at
# the line where it was written, and catches it in a view module nobody ran.
PROJECTION_MATH = frozenset({
    "mean", "average", "median", "std", "var", "sum", "prod", "sqrt",
    "square", "hypot", "diff", "subtract", "add", "multiply", "divide",
    "true_divide", "power", "percentile", "quantile", "cumsum", "histogram",
    "histogram2d", "argmin", "argmax", "amin", "amax", "ptp", "corrcoef",
    "cov", "interp", "gradient",
})


def _docstrings(tree):
    """ids of the string constants that are docstrings, which may say
    'centroids' as often as they like."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                out.add(id(first.value))
    return out


def _allowed_import(module):
    return any(module == a or module.startswith(a + ".")
               for a in ALLOWED_IMPORTS)


def violations(source, filename="<view>", package=VIEWS_PACKAGE):
    """[(line, rule, detail)] for one view module's source. Empty is clean."""
    tree = ast.parse(source, filename)
    docs = _docstrings(tree)
    out = []

    def add(node, rule, detail):
        out.append((getattr(node, "lineno", 0), rule, detail))

    def check_name(node, name):
        for names, rule in _NAME_RULES:
            if name in names:
                add(node, rule, name)

    def check_module(node, module):
        if not _allowed_import(module):
            add(node, "import", module)
        for part in module.split("."):
            check_name(node, part)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                check_module(node, alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + base, package)
                except ImportError:
                    add(node, "import", "." * node.level + base)
                    continue
            check_module(node, base)
            for alias in node.names:
                check_name(node, alias.name)
                if not _allowed_import(f"{base}.{alias.name}"):
                    add(node, "import", f"{base}.{alias.name}")
        elif isinstance(node, (ast.BinOp, ast.AugAssign)) \
                and isinstance(node.op, ast.MatMult):
            add(node, "vector-arithmetic", "@")
        elif isinstance(node, ast.Attribute):
            check_name(node, node.attr)
        elif isinstance(node, ast.Name):
            check_name(node, node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs and node.value in VECTOR_COLUMNS:
            add(node, "vector-data", node.value)

    out.extend(_projection_violations(tree))
    return sorted(set(out))


def _reads_a_projection(node):
    """Whether an expression is, or indexes, a read of a projection column."""
    while isinstance(node, ast.Subscript):
        index = node.slice
        if isinstance(index, ast.Constant) \
                and index.value in PROJECTION_COLUMNS:
            return True
        node = node.value
    return False


def _projection_violations(tree):
    """Names bound from a projection column, used in a numeric context.

    Two passes: bind, then check. A view may hold the positions, index them
    and hand them to a mark; it may not take a difference, a distance, a mean
    or a percentile of them, because a projection is declared and illustrative
    and a figure measured from it would be a new measurement in a space
    nothing else in the run uses.
    """
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _reads_a_projection(node.value):
            for target in node.targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        bound.add(name.id)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) \
                and node.value is not None \
                and _reads_a_projection(node.value):
            if isinstance(node.target, ast.Name):
                bound.add(node.target.id)

    if not bound:
        return []

    def mentions(node):
        return any(isinstance(n, ast.Name) and n.id in bound
                   for n in ast.walk(node))

    out = []
    for node in ast.walk(tree):
        detail = None
        if isinstance(node, (ast.BinOp, ast.AugAssign)) and mentions(node):
            detail = type(node.op).__name__
        elif isinstance(node, ast.UnaryOp) and mentions(node) \
                and not isinstance(node.op, ast.Not):
            detail = type(node.op).__name__
        elif isinstance(node, ast.Compare) and mentions(node):
            detail = "comparison"
        elif isinstance(node, ast.Call):
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", ""))
            if name in PROJECTION_MATH and any(mentions(a) for a in node.args):
                detail = name
        if detail:
            out.append((getattr(node, "lineno", 0), "projection-arithmetic",
                        f"{detail} over a declared projection"))
    return out


def view_modules():
    """Every Python file in the views package."""
    return sorted(os.path.join(VIEWS_DIR, f) for f in os.listdir(VIEWS_DIR)
                  if f.endswith(".py"))


def check_views():
    """{module file name: [(line, rule, detail)]} for every view module that
    breaks the contract. Empty means every view module is clean."""
    found = {}
    for path in view_modules():
        with open(path, encoding="utf-8") as f:
            v = violations(f.read(), path)
        if v:
            found[os.path.basename(path)] = v
    return found


# ------------------------------------------------------------- transport
# Task 024: the lab's server is a transport, never a second renderer. It sends
# drawings views produced and must not compute them. Its own modules have to
# read files and speak HTTP, which a view may do neither of, so they are held
# to the rules that forbid computing rather than to the view profile:
#
#   import             nothing that measures -- and, for the server's own
#                      modules, not numpy at all: a module that cannot hold an
#                      array cannot compute one
#   vector-arithmetic  as for views
#   vector-data        as for views
#   dynamic-code       eval, exec, __import__
#
# `check_transport` reads the server's own modules. The test suite also
# imports the server in a clean process and holds every oneground module it
# pulled in to the same rules, numpy allowed.

LAB_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSPORT_MODULES = ("server.py", "runs.py", "citations.py")
MEASURING = (
    "faiss", "sklearn", "scipy", "torch", "umap", "sentence_transformers",
    "pynndescent", "numba", "hnswlib", "annoy",
    "oneground.models", "oneground.measures", "oneground.truth",
    "oneground.simulate", "oneground.characterize", "oneground.embed",
    "oneground.sample", "oneground.calibrate", "oneground.fixture",
    "oneground.verify", "oneground.adapters", "oneground.pod",
    "oneground.report",
)
EVAL_CODE = frozenset({"eval", "exec", "__import__"})
# Modules the server imports that may break exactly one named rule, each
# with its reason. Per rule, not per file: the exemption covers naming a
# vector column, never arithmetic or a measuring import.
TRANSPORT_ALLOWLIST = {
    "oneground/models/state.py": (
        {"vector-data"},
        "the state format itself: it defines the vector columns that every "
        "other module is refused, so it has to name them"),
    "oneground/lab/contract.py": (
        {"vector-data"},
        "the contract names partition.centroids in order to refuse it to "
        "every view"),
}


def transport_violations(source, filename="<transport>",
                         package="oneground.lab", allow_numpy=False):
    """[(line, rule, detail)] for one transport module's source."""
    tree = ast.parse(source, filename)
    docs = _docstrings(tree)
    forbidden = MEASURING if allow_numpy else MEASURING + ("numpy",)
    out = []

    def add(node, rule, detail):
        out.append((getattr(node, "lineno", 0), rule, detail))

    def check_module(node, module):
        if any(module == f or module.startswith(f + ".") for f in forbidden):
            add(node, "import", module)
        for part in module.split("."):
            if part in VECTOR_ARITHMETIC:
                add(node, "vector-arithmetic", part)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                check_module(node, alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + base, package)
                except ImportError:
                    add(node, "import", "." * node.level + base)
                    continue
            check_module(node, base)
            for alias in node.names:
                check_module(node, f"{base}.{alias.name}")
        elif isinstance(node, (ast.BinOp, ast.AugAssign)) \
                and isinstance(node.op, ast.MatMult):
            add(node, "vector-arithmetic", "@")
        elif isinstance(node, (ast.Attribute, ast.Name)):
            name = node.attr if isinstance(node, ast.Attribute) else node.id
            if name in VECTOR_ARITHMETIC:
                add(node, "vector-arithmetic", name)
            if name in VECTOR_DATA:
                add(node, "vector-data", name)
            if name in EVAL_CODE:
                add(node, "dynamic-code", name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs and node.value in VECTOR_COLUMNS:
            add(node, "vector-data", node.value)
    return sorted(set(out))


def check_transport():
    """{module file name: [(line, rule, detail)]} for every server module
    that breaks the transport rules. Empty means the server computes
    nothing a view draws."""
    found = {}
    # The write path is held to these rules too. It is a separate kind
    # because of what it may *do* -- open a file for writing -- not because
    # of what it may import, and a writer that could measure would be a
    # second implementation with a file handle.
    for name in TRANSPORT_MODULES + WRITE_MODULES:
        path = os.path.join(LAB_DIR, name)
        with open(path, encoding="utf-8") as f:
            v = transport_violations(f.read(), path)
        if v:
            found[name] = v
    return found


# --------------------------------------------------- every module, classified
# Task 041. The brief asked for a test that every module is "either a view
# under the contract or transport under the transport rules -- no third
# kind". The tree already had a third kind when that was written: `contract.py`
# and `guard.py` are neither. They are not an oversight -- they are the
# machinery that defines the other two -- so the honest repair is to name the
# kind rather than to pretend there are two.
#
# The point of the test is not the number of kinds. It is that a module cannot
# appear in this package without someone deciding which rules hold it, which
# is how a view would otherwise arrive unguarded.

#: The contract itself: it defines what a view and a transport may do, and
#: draws nothing. Held to the measuring rules like transport, except that
#: numpy is permitted -- `contract.py` types the state's own arrays in order
#: to refuse them to views.
CONTRACT_MODULES = ("contract.py", "guard.py", "receipt.py")

#: The write half (task 046). Exactly one module in this package may open a
#: file for writing, and this names it. The read half proves the inverse --
#: `test_the_server_has_no_write_path` scans every other served module -- so
#: the two together say *exactly one module writes, and it is this one*,
#: which is a stronger statement than either makes alone.
#:
#: This is a classification, not an exemption. `check_transport` holds these
#: modules to the measuring rules exactly as it holds transport, because the
#: thing that makes a writer special is what it may do, not what it may
#: import.
WRITE_MODULES = ("compose.py",)

#: Writes that land by moving a file into place rather than by opening one.
#: A scan that only looked for `open` would pass a module that renamed its
#: way past it. **Qualified**, because the unqualified form of this set was
#: wrong: `replace` and `move` are also string and list methods, and the
#: first version of this scan reported `server.py`, `runs.py` and `guard.py`
#: as writing when all four hits were `str.replace("\\", "/")` in a path.
#: That is warning 1 of `docs/PRACTICE.md` -- a check reporting its own
#: coverage gap as the subject's defect -- committed by a scan written to
#: enforce the rule beneath it.
QUALIFIED_WRITERS = frozenset({
    ("os", "replace"), ("os", "rename"), ("os", "remove"), ("os", "unlink"),
    ("os", "mkdir"), ("os", "makedirs"), ("os", "rmdir"),
    ("os", "truncate"), ("os", "writev"),
    ("shutil", "move"), ("shutil", "copy"), ("shutil", "copy2"),
    ("shutil", "copyfile"), ("shutil", "copytree"), ("shutil", "rmtree"),
})

#: Methods that write whatever they are called on. These need no qualifier
#: because no builtin type carries them: `str` has no `write_text`.
UNQUALIFIED_WRITERS = frozenset({
    "write_text", "write_bytes", "writelines", "touch",
})

#: Modes that make `open()` a write.
WRITING_MODES = ("w", "a", "x", "+")

#: Not part of the running server, so none of the three sets of rules apply:
#: the package docstring, the browser client the tests drive, and the tests.
NOT_SERVED = ("__init__.py", "cdp.py")


def package_modules(directory=None):
    """Every Python file in the lab package, tests excluded."""
    d = directory or LAB_DIR
    return sorted(f for f in os.listdir(d)
                  if f.endswith(".py") and not f.startswith("test_"))


def unclassified_modules(directory=None):
    """Modules in the package that no rule set holds. Empty is the only
    acceptable answer: a module nobody classified is a module nobody guards."""
    known = (set(TRANSPORT_MODULES) | set(CONTRACT_MODULES)
             | set(WRITE_MODULES) | set(NOT_SERVED))
    return sorted(set(package_modules(directory)) - known)


def check_contract():
    """{module: [(line, rule, detail)]} for contract machinery that imports
    something that measures. Numpy is allowed here and nowhere else.

    `TRANSPORT_ALLOWLIST` is applied exactly as the server's own import test
    applies it -- per rule, by repository-relative path -- rather than
    widened: `contract.py` already carries the one exemption it needs, for
    naming `partition.centroids` in order to refuse it to every view.
    """
    root = os.path.dirname(os.path.dirname(LAB_DIR))
    found = {}
    for name in CONTRACT_MODULES:
        path = os.path.join(LAB_DIR, name)
        rel = os.path.relpath(path, root).replace("\\", "/")
        allowed, _ = TRANSPORT_ALLOWLIST.get(rel, (set(), ""))
        with open(path, encoding="utf-8") as f:
            v = [x for x in transport_violations(f.read(), path,
                                                 allow_numpy=True)
                 if x[1] not in allowed]
        if v:
            found[name] = v
    return found

# ------------------------------------------------- the write path, scanned
def write_violations(source, filename="<module>"):
    """[(line, rule, detail)] for anything in one module that writes.

    Parsed rather than matched on text. The read half's scan looks for the
    string `open("w"` and its spellings, which was enough when the answer was
    *nothing writes anywhere*; it would miss `open(path, mode)` where mode is
    a variable, and it would miss a rename. This slice makes writing a thing
    one module is allowed to do, so the scan that finds it has to be able to
    find it however it is spelled.

    **What it cannot see, stated rather than implied.** A write through an
    alias (`from os import replace`), or through a file handle opened
    somewhere else and passed in. An `open()` whose mode this scan cannot
    read is *reported* rather than skipped: a scan that cannot tell answers
    couldn't-check, and a served module has no reason to open a file with a
    computed mode.

    The aliases are the honest gap, and they are why this is one of two
    halves. The read half asserts the served tree's digests are unchanged
    after a session, which catches a write however it was spelled; this half
    says which module is allowed to spell one at all.
    """
    out = []
    for node in ast.walk(ast.parse(source, filename)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
            owner = func.value.id if isinstance(func.value, ast.Name) else None
        elif isinstance(func, ast.Name):
            name, owner = func.id, None
        else:
            continue
        # The order matters and two mutants found it. A method that writes
        # whatever it is called on is checked before the qualified set,
        # because `p.write_text(...)` has an owner (`p`) that no qualified
        # pair will ever match -- the first version checked the pair first,
        # hit `continue`, and never reached the method it was looking for.
        if name in UNQUALIFIED_WRITERS:
            out.append((node.lineno, "write", name + "()"))
            continue
        if owner is not None:
            if (owner, name) in QUALIFIED_WRITERS:
                out.append((node.lineno, "write", f"{owner}.{name}()"))
            continue                          # someone else's method
        if name != "open":
            continue

        # `open(p)` names no mode and is a read. `open(p, mode)` names one
        # this scan cannot read, which is reported rather than skipped: a
        # scan that cannot tell answers couldn't-check, and a served module
        # has no reason to compute a mode. The first version conflated the
        # two under `mode is None` and silently passed the second.
        mode_node = node.args[1] if len(node.args) > 1 else None
        for kw in node.keywords:
            if kw.arg == "mode":
                mode_node = kw.value
        if mode_node is None:
            continue                          # a read
        if isinstance(mode_node, ast.Constant) and isinstance(
                mode_node.value, str):
            if any(m in mode_node.value for m in WRITING_MODES):
                out.append((node.lineno, "write",
                            f"open(..., {mode_node.value!r})"))
        else:
            out.append((node.lineno, "write",
                        "open() with a mode this scan cannot read"))
    return out


def check_write_path():
    """{module: [(line, rule, detail)]} for served modules that write and are
    not the one module permitted to.

    Empty is the only acceptable answer. The permitted module is not scanned
    for writes -- it is the write path -- but it is scanned for everything
    else, by `check_transport`.
    """
    found = {}
    for name in TRANSPORT_MODULES + CONTRACT_MODULES:
        path = os.path.join(LAB_DIR, name)
        with open(path, encoding="utf-8") as f:
            v = write_violations(f.read(), path)
        if v:
            found[name] = v
    return found
