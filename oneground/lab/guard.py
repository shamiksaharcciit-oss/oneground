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

from .contract import VECTOR_COLUMNS

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
    return sorted(set(out))


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
