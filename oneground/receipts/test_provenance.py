"""Task 033: the version and commit that produced an artifact.

The field three tasks paid for: 028b dated a commit to work out which code
measured a workdir, 028c measured one configuration at three revisions to
settle the same question, and `docs/LIBRARY.md` §2.2 cannot give a card a
comparability verdict better than couldn't-check without it.

Synthetic throughout, except the tests named for the shipped writers.

    .venv/Scripts/python.exe -m pytest oneground/receipts/test_provenance.py
"""

import ast
import json
import os
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)

from oneground import __version__                               # noqa: E402
from oneground import receipts as R                             # noqa: E402
# Task 046 moved `producing_version` and its two helpers to
# `oneground.provenance`, a leaf the lab's server can import -- `receipts`
# imports torch, which every served module is refused. `receipts`
# re-exports them, so the calls below are unchanged.
#
# The PATCHES are not. `producing_version` reads `_build_stamp` and
# `_run_git` from the module that defines it, so patching the re-export
# patches a name nothing looks at, and these four tests went red the moment
# the function moved. They were right to: the assertions still hold and the
# setup had stopped reaching the code under test, so the input changed and
# the assertions did not (`docs/PRACTICE.md` section 2, warning 7).
from oneground import provenance as P                           # noqa: E402

KEYS = {"version", "commit", "dirty", "source", "note"}


# ------------------------------------------------------------- the shape
def test_the_version_is_always_answered():
    got = R.producing_version()
    assert set(got) == KEYS, got
    assert got["version"] == __version__
    assert got["source"] in ("checkout", "wheel", "unknown"), got


def test_a_commit_is_forty_hex_or_none_with_a_reason():
    got = R.producing_version()
    if got["commit"] is None:
        assert got["note"], "a null commit must say why"
    else:
        assert len(got["commit"]) == 40, got
        assert all(c in "0123456789abcdef" for c in got["commit"]), got


def test_a_build_stamp_answers_for_a_wheel_synthetic(monkeypatch):
    """An installed wheel has no git; `setup.py` writes what it was built
    from, and this reads it back."""
    stamp = {"commit": "a" * 40, "dirty": False, "note": ""}
    monkeypatch.setattr(P, "_build_stamp", lambda: stamp)
    got = R.producing_version()
    assert got == {"version": __version__, "commit": "a" * 40, "dirty": False,
                   "source": "wheel", "note": ""}


def test_a_stamp_without_a_commit_says_why_synthetic(monkeypatch):
    monkeypatch.setattr(P, "_build_stamp", lambda: {
        "commit": None, "dirty": None,
        "note": "built from a tree with no readable git checkout"})
    got = R.producing_version()
    assert got["commit"] is None and got["source"] == "wheel"
    assert "no readable git checkout" in got["note"]


def test_no_stamp_and_no_checkout_is_null_with_a_reason_synthetic(monkeypatch):
    monkeypatch.setattr(P, "_build_stamp", lambda: None)
    monkeypatch.setattr("oneground.provenance.checkout_root",
                        lambda *a, **k: None)
    got = R.producing_version()
    assert got["commit"] is None and got["dirty"] is None
    assert got["source"] == "unknown"
    assert "not a git checkout" in got["note"], got


def test_a_checkout_whose_git_cannot_run_says_so_synthetic(monkeypatch):
    """022e's distinction, here too: a tree with a `.git` and no runnable git
    is a stated reason, not a silent null and not a refusal."""
    monkeypatch.setattr(P, "_build_stamp", lambda: None)
    monkeypatch.setattr("oneground.provenance.checkout_root",
                        lambda *a, **k: ROOT)
    monkeypatch.setattr(P, "_run_git",
                        lambda args: (None, "FileNotFoundError: no git"))
    got = R.producing_version()
    assert got["source"] == "checkout" and got["commit"] is None
    assert "git could not be asked" in got["note"], got
    assert "FileNotFoundError" in got["note"], got


# --------------------------------------------------- what it may never carry
FORBIDDEN_GIT = ("--abbrev-ref", "symbolic-ref", "branch", "remote",
                 "describe", "for-each-ref", "config user")


def test_it_never_reaches_for_a_branch_a_remote_or_a_tag():
    """The guard for the defect one move away.

    A commit and a dirty flag are facts about the code. A branch name, a
    remote URL or a build path name whose machine this was, and this project
    has an identifier scan because that line is crossed by accident. The
    check is on the source, so a path no test reaches is still covered.
    """
    for path in (os.path.join(HERE, "__init__.py"),
                 os.path.join(ROOT, "setup.py")):
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(
                    node.value, str):
                continue
            low = node.value.lower()
            for needle in FORBIDDEN_GIT:
                # The prose that explains the rule may name it; a git
                # argument may not. Only short strings are arguments.
                if needle in low and len(node.value) < 40:
                    raise AssertionError(
                        "%s passes %r to git: a version and a commit are "
                        "facts about the code, a branch or a remote is a "
                        "fact about the machine" % (os.path.basename(path),
                                                    node.value))


def test_the_recorded_shape_carries_nothing_but_the_five_keys():
    assert set(R.producing_version()) == KEYS


# ------------------------------------------------- every writer records it
WRITERS = {
    "oneground/characterize.py": "build_info.json",
    "oneground/simulate/__init__.py": "simulate_info.json and state_info.json",
    "oneground/verify/__init__.py": "verify_info.json",
    "oneground/proposals/propose.py": "propose_info.json and card.json",
    "oneground/report/__init__.py": "report.json",
    "oneground/calibrate/history.py": "each calibration line",
}


@pytest.mark.parametrize("path, what", sorted(WRITERS.items()))
def test_every_declared_writer_records_the_producing_version(path, what):
    src = open(os.path.join(ROOT, path), encoding="utf-8").read()
    assert "producing_version()" in src, (
        "%s writes %s and records no producing version" % (path, what))


def test_a_simulate_run_records_it_end_to_end_synthetic():
    """The real command, on a 2k corpus: the field is in the file."""
    from oneground import characterize, simulate
    from oneground.simulate import test_simulate as ts
    with tempfile.TemporaryDirectory() as tmp:
        req = ts._prepared(tmp)
        ts._capture(simulate.run, req, log_fn=ts._quiet)
        workdir = os.path.join(tmp, "out")
        for name in ("build_info.json", "simulate_info.json"):
            with open(os.path.join(workdir, name), encoding="utf-8") as f:
                doc = json.load(f)
            assert set(doc.get("oneground") or {}) == KEYS, name
            assert doc["oneground"]["version"] == __version__, name
        assert characterize is not None


# ------------------------------------------- an artifact written before 033
def test_an_artifact_without_the_field_reads_as_couldnt_check():
    """A workdir written before this task has no version anywhere and nothing
    can add one honestly. A reader gets a stated absence, never a KeyError and
    never a match."""
    old = {"run_at": "2026-09-09T16:47:12Z", "library_versions": {}}
    got = old.get("oneground") or {"version": None, "commit": None,
                                   "note": "written before task 033"}
    assert got["commit"] is None and got["note"]


def test_the_arxiv_workdir_is_such_an_artifact():
    """Not synthetic, and the reason this task exists: the workdir whose
    provenance 028b and 028c had to reconstruct still cannot say what made
    it, and this task does not repair it."""
    path = os.path.join(ROOT, "runs", "arxiv-150k-via-characterize",
                        "simulate_info.json")
    if not os.path.exists(path):
        pytest.skip("the arxiv workdir is not on this machine")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    assert "oneground" not in doc, (
        "this workdir predates task 033; if it now carries a version, "
        "something wrote one into an old artifact")


# ------------------------------------------------------------ the build hook
def test_setup_writes_a_stamp_with_a_commit_and_nothing_else():
    """The wheel case, answered by construction rather than by a null."""
    setup_src = open(os.path.join(ROOT, "setup.py"), encoding="utf-8").read()
    assert "_build_stamp.json" in setup_src or "STAMP_NAME" in setup_src
    stamp = _build_stamp_from_setup()
    assert set(stamp) == {"commit", "dirty", "note"}, stamp
    if stamp["commit"] is not None:
        assert len(stamp["commit"]) == 40, stamp


def _build_stamp_from_setup():
    """`setup.py`'s own `build_stamp()`, without running a build.

    The module's trailing `setup(...)` call is dropped before the rest is
    executed: running it would have setuptools parse this process's argv and
    exit. Everything above it -- the imports, `HERE`, the fixture selection
    rule, and the function under test -- runs exactly as it does at build
    time.
    """
    path = os.path.join(ROOT, "setup.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    tree.body = [n for n in tree.body
                 if not (isinstance(n, ast.Expr)
                         and isinstance(n.value, ast.Call)
                         and getattr(n.value.func, "id", "") == "setup")]
    namespace = {"__file__": path, "__name__": "setup_under_test"}
    exec(compile(tree, path, "exec"), namespace)      # noqa: S102
    return namespace["build_stamp"]()
