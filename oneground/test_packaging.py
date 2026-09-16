"""`pyproject.toml` against `requirements.txt` and against the package.

WHY THIS FILE EXISTS
--------------------
`docs/RELEASE.md` records what the 0.1.0-preview release procedure caught,
and one of the three was:

    step 2 | `[qdrant]` and `[calibrate]` extras pinned versions that were
             invented rather than read from `requirements.txt`

That was fixed by hand and nothing stopped it happening again -- until task
018 went looking, no test in this repository read `pyproject.toml` at all. A
wrong pin in an extra is invisible in development, where the venv already has
the right version installed, and shows up only on a stranger's machine, which
is the one place nobody is watching.

The rule the pins exist to hold: **a bare `pip install oneground` must yield
an environment the canonical-artifact commands accept.** `environment.PINNED`
lists the packages whose version can move a measured number; every one of them
has to be pinned by the core dependencies, not by an extra, or the install
succeeds and then every fixture verification reports `couldnt_check` on a pin
the wheel never fixed.

Task 018 also found `[pgvector]` missing outright -- the adapter shipped in
015, `verify`'s readiness probe has imported psycopg since 017c, and
`pip install oneground[pgvector]` failed on a release claiming two engines.
The last test here is the one that catches that class: every engine with an
adapter must have an extra that installs its driver.
"""

import os
import re
import sys
import tomllib

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground import environment                            # noqa: E402
from oneground import __version__                            # noqa: E402

ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PYPROJECT = os.path.join(ROOT, "pyproject.toml")
REQUIREMENTS = os.path.join(ROOT, "requirements.txt")


def _project():
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)["project"]


def _pins(specs):
    """{normalised name: version} for every `name==version` in a dep list."""
    out = {}
    for spec in specs:
        head = spec.split(";")[0].strip()
        if "==" not in head:
            continue
        name, _, version = head.partition("==")
        out[environment._normalise(name.strip())] = version.strip()
    return out


def _all_declared():
    p = _project()
    specs = list(p.get("dependencies") or [])
    for extra in (p.get("optional-dependencies") or {}).values():
        specs.extend(extra)
    return specs


def test_the_version_is_the_packages_own():
    assert _project()["version"] == __version__, (
        "pyproject says %s and oneground/__init__.py says %s; pip would build "
        "a wheel named one and print the other"
        % (_project()["version"], __version__))


def test_every_pin_is_the_one_requirements_txt_names():
    """The 0.1.0-preview defect, checked rather than remembered.

    Not "a version is present" but "the same version": an extra that pins
    1.18.0 against a requirements.txt at 1.19.0 installs cleanly and measures
    against different bytes than every published number was produced with.
    """
    req = environment.read_requirements_pins(REQUIREMENTS)
    assert req, "requirements.txt produced no pins at all"
    wrong, unknown = [], []
    for name, version in _pins(_all_declared()).items():
        if name not in req:
            unknown.append(name)
        elif req[name] != version:
            wrong.append("%s: pyproject %s, requirements.txt %s"
                         % (name, version, req[name]))
    assert not wrong, wrong
    assert not unknown, (
        "pinned in pyproject.toml but absent from requirements.txt, so the "
        "pin was written rather than read: %s" % unknown)


def test_nothing_is_declared_without_a_pin():
    """Exact pins, not ranges, everywhere -- extras included.

    A range in an extra is how a resolver picks a version nobody measured
    anything on.
    """
    loose = [s for s in _all_declared() if "==" not in s.split(";")[0]]
    assert not loose, loose


def test_a_bare_install_pins_everything_the_guard_checks():
    """`pip install oneground` must produce an environment the commands accept.

    Every package in `environment.PINNED` pinned by the CORE dependencies --
    not by an extra, which a stranger has no reason to ask for.
    """
    core = _pins(_project().get("dependencies") or [])
    missing = []
    for name in environment.PINNED:
        if environment._normalise(name) not in core:
            # faiss and faiss-cpu are the same distribution under two names
            # the guard accepts; one of them being pinned is enough.
            alts = {"faiss": "faiss-cpu", "faiss-cpu": "faiss"}
            alt = alts.get(name)
            if alt and environment._normalise(alt) in core:
                continue
            missing.append(name)
    assert not missing, (
        "environment.PINNED names %s, which a bare `pip install oneground` "
        "would not fix; every canonical-artifact command would then refuse, "
        "or worse, run unpinned" % missing)


def test_scikit_learn_is_a_core_dependency_even_though_nothing_imports_it():
    """Not an oversight, and a comment is not enough to keep it.

    `umap-learn` (the [view] extra) requires scikit-learn without pinning it,
    and scikit-learn is in PINNED. Dropping it from the core because no module
    imports it would let `pip install oneground[view]` resolve a version that
    makes every canonical-artifact command refuse.
    """
    core = _pins(_project().get("dependencies") or [])
    assert "scikit-learn" in core, sorted(core)


# ------------------------------------------------------------------ extras

def _adapter_dirs():
    d = os.path.join(ROOT, "oneground", "adapters")
    return sorted(n for n in os.listdir(d)
                  if os.path.isdir(os.path.join(d, n))
                  and not n.startswith("_")
                  and os.path.exists(os.path.join(d, n, "adapter.py")))


def test_every_engine_with_an_adapter_has_an_extra_that_installs_its_driver():
    """The `[pgvector]` defect, as a rule rather than as one more entry.

    An adapter in the tree is a claim that `oneground verify` runs against
    that engine. If no extra installs the driver it imports, the claim is
    true only on a machine that already had it -- which is every machine
    except a new user's.
    """
    extras = _project().get("optional-dependencies") or {}
    adapters = _adapter_dirs()
    assert adapters, "no adapters found; the walk looked at nothing"
    missing = [a for a in adapters if a not in extras]
    assert not missing, (
        "adapters with no install extra: %s. `pip install oneground[%s]` "
        "fails on a release that claims the engine works."
        % (missing, (missing or [""])[0]))

    # And the extra installs something the adapter actually imports.
    for name in adapters:
        src = open(os.path.join(ROOT, "oneground", "adapters", name,
                                "adapter.py"), encoding="utf-8").read()
        imported = set(re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)",
                                  src, re.M))
        declared = {environment._normalise(n)
                    for n in _pins(extras[name])}
        # Distribution names and module names differ: qdrant-client provides
        # qdrant_client, psycopg provides psycopg. Compare on the squashed
        # form rather than requiring a mapping table nobody maintains.
        squashed = {d.replace("-", "") for d in declared}
        hit = any(m.replace("_", "") in squashed
                  or any(m.replace("_", "").startswith(d) for d in squashed)
                  for m in imported)
        assert hit, (
            "the [%s] extra installs %s, none of which is what "
            "adapters/%s/adapter.py imports (%s)"
            % (name, sorted(declared), name, sorted(imported)))


def test_the_pod_extra_is_empty_on_purpose():
    """An empty extra names a capability; it must not quietly gain a dep.

    `oneground pod` calls the RunPod API through stdlib urllib -- see
    oneground/pod/api.py -- so this extra exists to be nameable, not to
    install anything. If it ever does install something, that is a new runtime
    network dependency and a decision, not a detail.
    """
    extras = _project().get("optional-dependencies") or {}
    assert extras.get("pod") == [], extras.get("pod")


def test_every_extra_the_docs_offer_exists():
    """A README that offers `pip install oneground[x]` must be installable."""
    extras = set((_project().get("optional-dependencies") or {}))
    offered = set()
    for name in ("README.md", os.path.join("docs", "VERIFY.md"),
                 os.path.join("docs", "INTAKE.md"),
                 os.path.join("docs", "ADAPTERS.md")):
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            offered |= set(re.findall(r"oneground\[([a-z0-9,\-]+)\]", f.read()))
    wanted = set()
    for group in offered:
        wanted |= {g.strip() for g in group.split(",") if g.strip()}
    assert wanted, "no extras are offered anywhere in the docs"
    missing = sorted(wanted - extras)
    assert not missing, (
        "the docs tell a reader to install %s, and pyproject.toml has no such "
        "extra" % missing)


# --------------------------------------------------------------------------
# what an extra installs, and what it must not
# --------------------------------------------------------------------------
# Task 018b. Task 018 established that every *adapter* has an extra and that
# every pin matches `requirements.txt`. It did not check the other direction:
# that what an extra installs is what its capability needs. `[pgvector]` was
# absent for three tasks; the same blind spot lets an extra keep a dependency
# nothing imports, or acquire one that belongs to a different capability, and
# a user pays the download either way.

# Distributions an extra legitimately installs although no oneground module
# imports them. Each needs a reason; a list without reasons is a list that
# grows.
NOT_IMPORTED_BY_US = {
    "pywin32":
        "a Windows-only transitive of qdrant-client via portalocker. Pinned "
        "here so the version is fixed, with the marker that keeps a Linux "
        "install resolving; nothing in this project imports it",
    "psycopg-binary":
        "the compiled backend psycopg loads. `import psycopg` is ours; "
        "`psycopg_binary` is psycopg's, and installing it is what removes the "
        "libpq build dependency",
}


def _distribution_modules():
    """{normalised distribution: {top-level module}} for what is installed.

    Read from the interpreter rather than from a table in this file.
    `top_level.txt` is absent from most modern wheels -- torch, pyarrow,
    matplotlib and qdrant-client all omit it here -- so this inverts
    `packages_distributions()`, which is built from the installed files.
    """
    import importlib.metadata as md

    out = {}
    try:
        mapping = md.packages_distributions()
    except Exception:                                     # pragma: no cover
        return out
    for module, dists in mapping.items():
        for dist in dists:
            out.setdefault(environment._normalise(dist), set()).add(module)
    return out


def _imported_modules():
    """Every top-level module name imported anywhere in the shipped tree."""
    import ast
    import warnings

    roots = [os.path.join(ROOT, d) for d in
             ("oneground", "adapters", "models", "policies", "corpora")]
    names, scanned = set(), 0
    for base in roots:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                try:
                    with open(os.path.join(dirpath, fname),
                              encoding="utf-8") as f:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            tree = ast.parse(f.read())
                except (OSError, SyntaxError, UnicodeDecodeError):
                    continue
                scanned += 1
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            names.add(alias.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.level == 0 and node.module:
                            names.add(node.module.split(".")[0])
    return names, scanned


def test_every_extra_installs_only_what_that_capability_needs():
    """Each distribution in an extra is imported by this project, or says why.

    The direction 018 did not check. An extra that installs something nothing
    imports is a download a user pays for and never uses, and -- worse for a
    project whose whole claim is that nothing is included by default -- it is
    a dependency nobody can account for.
    """
    extras = _project().get("optional-dependencies") or {}
    dist_modules = _distribution_modules()
    imported, scanned = _imported_modules()
    assert scanned > 50, "the import walk parsed only %d files" % scanned
    assert dist_modules, "no installed distributions could be resolved"

    unaccounted, unresolved = [], []
    for extra, specs in sorted(extras.items()):
        for dist in sorted(_pins(specs)):
            if dist in NOT_IMPORTED_BY_US:
                assert len(NOT_IMPORTED_BY_US[dist]) > 20, dist
                continue
            modules = dist_modules.get(dist)
            if not modules:
                # Not installed in THIS interpreter: unresolvable rather than
                # wrong. Recorded, and the floor below keeps an empty result
                # from passing as a clean one.
                unresolved.append("%s[%s]" % (extra, dist))
                continue
            if not (modules & imported):
                unaccounted.append(
                    "%s: [%s] installs it and nothing in the tree imports "
                    "%s" % (extra, dist, sorted(modules)[:4]))

    assert not unaccounted, (
        "extras installing what this project does not use: %s. Either drop "
        "it, or add it to NOT_IMPORTED_BY_US with the reason."
        % unaccounted)
    # The floor: an all-clear only means something if most were checkable.
    total = sum(len(_pins(s)) for s in extras.values())
    assert len(unresolved) <= total // 2, (
        "%d of %d extra dependencies could not be resolved in this "
        "interpreter, so this check saw too little to mean anything: %s"
        % (len(unresolved), total, unresolved))


def test_no_extra_installs_another_extras_dependency():
    """Capabilities do not overlap, so neither should their extras.

    `pip install oneground[qdrant]` must not drag in matplotlib. A shared
    dependency belongs in the core list where it is stated once, not
    duplicated into two extras where the two copies can drift apart.
    """
    extras = _project().get("optional-dependencies") or {}
    seen, clashes = {}, []
    for extra, specs in sorted(extras.items()):
        for dist in sorted(_pins(specs)):
            if dist in seen:
                clashes.append("%s is in both [%s] and [%s]"
                               % (dist, seen[dist], extra))
            seen[dist] = extra
    assert not clashes, clashes


def test_no_extra_repeats_a_core_dependency():
    """An extra that re-pins a core dependency has two pins to keep in step."""
    core = set(_pins(_project().get("dependencies") or []))
    extras = _project().get("optional-dependencies") or {}
    dupes = []
    for extra, specs in sorted(extras.items()):
        for dist in sorted(set(_pins(specs)) & core):
            dupes.append("%s is pinned in the core list and again in [%s]"
                         % (dist, extra))
    assert not dupes, dupes


def test_every_guarded_pin_is_exact_and_matches_requirements():
    """`environment.PINNED`, spelled out rather than inferred.

    Two other tests together imply this -- one says nothing is declared
    without `==`, another says every guarded package is in the core list --
    but the packages whose version can move a published number deserve an
    assertion that says so in one place and fails with their names in it.
    """
    req = environment.read_requirements_pins(REQUIREMENTS)
    core_specs = _project().get("dependencies") or []
    by_name = {}
    for spec in core_specs:
        head = spec.split(";")[0].strip()
        name = re.split(r"[=<>!~ \[]", head, 1)[0].strip()
        by_name[environment._normalise(name)] = head

    problems = []
    for guarded in environment.PINNED:
        key = environment._normalise(guarded)
        head = by_name.get(key)
        if head is None:
            if key == "faiss" and "faiss-cpu" in by_name:
                head = by_name["faiss-cpu"]
                key = "faiss-cpu"
            else:
                problems.append("%s: not in the core dependency list" % guarded)
                continue
        if "==" not in head:
            problems.append("%s: declared as %r, which is not an exact pin"
                            % (guarded, head))
            continue
        version = head.split("==", 1)[1].strip()
        if key in req and req[key] != version:
            problems.append("%s: pyproject pins %s, requirements.txt pins %s"
                            % (guarded, version, req[key]))
    assert not problems, (
        "the packages whose version can move a measured number are not "
        "exactly pinned: %s" % problems)


def test_the_extras_the_readme_lists_are_exactly_the_extras_that_exist():
    """Both directions, because both fail quietly.

    An extra in the README that pyproject lacks fails at `pip install`. An
    extra pyproject has that the README omits is undiscoverable -- which is
    how `[pgvector]` could be missing for three tasks without anyone noticing:
    nobody was reading a list that named it.
    """
    extras = set(_project().get("optional-dependencies") or {})
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        readme = f.read()
    # The extras table: rows that begin `| \`[name]\` |`.
    listed = set(re.findall(r"^\|\s*`\[([a-z0-9\-]+)\]`\s*\|", readme, re.M))
    assert listed, "the README has no extras table any more"
    assert listed == extras, (
        "README extras table and pyproject disagree: only in the README %s; "
        "only in pyproject %s"
        % (sorted(listed - extras), sorted(extras - listed)))


# ---------------------------------------------------------------- task 022
# The wheel carries the fixture specs and their small receipts, so
# `oneground fixture verify <id>` works from a bare install. It never carries
# the release asset.

def _shipped_module():
    import runpy
    return runpy.run_path(os.path.join(ROOT, "oneground", "fixture",
                                       "shipped.py"))


def test_the_wheel_ships_every_fixture_spec_and_its_small_receipts():
    sh = _shipped_module()
    rel = {r for _src, r in sh["shipped_files"](os.path.join(ROOT,
                                                             "fixtures"))}
    for fid in ("arxiv-150k", "stackexchange-150k", "arxiv-smoke"):
        assert f"{fid}.fixture.yaml" in rel, fid
        for name in ("MANIFEST.sha256", "characterization.json",
                     "build_info.json", "query_ids.json", "ground_truth.npy"):
            assert f"{fid}/{name}" in rel, (fid, name)


def test_the_wheel_never_ships_the_release_asset():
    sh = _shipped_module()
    rel = [r for _src, r in sh["shipped_files"](os.path.join(ROOT,
                                                            "fixtures"))]
    for r in rel:
        base = r.rsplit("/", 1)[-1]
        assert base not in sh["NEVER_SHIPPED"], r
        assert "/report/" not in r and "ground_view" not in r, r
    assert not set(sh["SHIPPED_FILES"]) & set(sh["NEVER_SHIPPED"])


def test_a_stray_asset_on_the_build_machine_does_not_reach_the_wheel_synthetic():
    import tempfile
    sh = _shipped_module()
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "fx"))
        for name in ("vectors.npy", "queries.npy", "sample.jsonl.zst",
                     "projection.npy", "ground_truth.npy", "notes.txt"):
            with open(os.path.join(tmp, "fx", name), "wb") as f:
                f.write(b"x")
        with open(os.path.join(tmp, "fx.fixture.yaml"), "w") as f:
            f.write("fixture: {id: fx}\n")
        rel = sorted(r for _s, r in sh["shipped_files"](tmp))
    assert rel == ["fx.fixture.yaml", "fx/ground_truth.npy"], rel


def test_the_sdist_carries_what_the_wheel_ships():
    """A wheel built from the sdist must not silently ship no fixtures."""
    import fnmatch
    sh = _shipped_module()
    with open(os.path.join(ROOT, "MANIFEST.in"), encoding="utf-8") as f:
        patterns = [line.split(None, 1)[1].strip() for line in f
                    if line.startswith("include ")]
    for _src, r in sh["shipped_files"](os.path.join(ROOT, "fixtures")):
        path = "fixtures/" + r
        assert any(fnmatch.fnmatch(path, p) for p in patterns), path


def test_the_build_hook_reads_the_rule_it_ships_by():
    with open(os.path.join(ROOT, "setup.py"), encoding="utf-8") as f:
        text = f.read()
    assert "shipped.py" in text and "build_py" in text
    import ast
    with open(os.path.join(ROOT, "oneground", "fixture", "shipped.py"),
              encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    # read at build time, where none of the package's dependencies exist
    assert imported <= set(sys.stdlib_module_names), imported


def _main():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print("ok   %s" % name)
        except AssertionError as e:                       # noqa: PERF203
            failed += 1
            print("FAIL %s\n     %s" % (name, e))
    print("\n%d/%d passed" % (len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
