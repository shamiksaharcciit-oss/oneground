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
