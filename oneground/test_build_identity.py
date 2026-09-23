"""A server that cannot say which build it serves is a URL nobody should be
handed.

Task 046. The rule and what it cost are in `docs/PRACTICE.md`; this is the
mechanism. Every test here can fail -- the refusal is watched firing on a
constructed clash, not merely observed not firing on a clean tree, which is
`docs/PRACTICE.md` section 2 warning 3.
"""

import os
import tempfile

import pytest

from oneground import provenance
from oneground.lab import server

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_identity_names_the_package_directory_first():
    """The field that would have answered the question the incident asked.

    Two checkouts were in play with the same version and, for all anyone
    knew, the same commit. Only the path differed, so the path is the
    identifier that discriminates and it is not optional.
    """
    it = provenance.identity()
    assert it["package"] == os.path.join(REPO, "oneground")
    assert it["version"]
    assert it["source"] in ("checkout", "wheel", "unknown")
    # a commit may honestly be unknown, and then it says why
    assert it["commit"] is not None or it["note"]


def test_no_clash_when_the_working_directory_is_this_checkout():
    assert provenance.conflicting_checkout(REPO) is None
    assert provenance.conflicting_checkout(
        os.path.join(REPO, "oneground", "lab")) is None


def test_a_working_directory_holding_another_oneground_is_a_clash():
    """The incident, constructed: a checkout whose `oneground` package is not
    the one that got imported."""
    with tempfile.TemporaryDirectory() as tmp:
        os.mkdir(os.path.join(tmp, ".git"))
        pkg = os.path.join(tmp, "oneground")
        os.mkdir(pkg)
        with open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8") as f:
            f.write("__version__ = '0.0.0'\n")

        clash = provenance.conflicting_checkout(tmp)
        assert clash is not None, "the clash that produced this module"
        assert clash["imported"] == provenance.PACKAGE_DIR
        assert clash["working_directory"] == pkg


def test_an_unrelated_directory_is_not_a_clash():
    """Deliberately narrow. Running an installed oneground from somewhere
    else is fine and common; the refusal is for the case where the working
    directory *is* a checkout of this project and disagrees."""
    with tempfile.TemporaryDirectory() as tmp:
        assert provenance.conflicting_checkout(tmp) is None
        os.mkdir(os.path.join(tmp, ".git"))
        assert provenance.conflicting_checkout(tmp) is None, \
            "a checkout with no oneground package is not this project"


def test_the_server_refuses_to_bind_on_a_clash():
    """Watched firing. Without this the refusal is a branch nobody has run,
    and a guard that has never been seen to stop anything is not evidence
    that it would."""
    real = provenance.conflicting_checkout
    provenance.conflicting_checkout = lambda cwd=None: {
        "imported": "/a/oneground", "working_directory": "/b/oneground",
        "checkout": "/b"}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(server.LabRefused) as caught:
                server.LabServer(runs_dir=tmp, port=0)
            said = str(caught.value)
            # both paths, because naming one is what made the incident
            # invisible: the build that answered looked entirely normal
            assert "/a/oneground" in said and "/b/oneground" in said
            assert "install location" in said
    finally:
        provenance.conflicting_checkout = real


def test_the_server_serves_its_build_and_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        lab = server.LabServer(runs_dir=tmp, port=0)
        try:
            build = lab.check({})["build"]
            assert build["package"] == os.path.join(REPO, "oneground")
            assert build["version"]
            line = lab.build_line()
            assert build["package"] in line
            assert lab.ui_startup_line(0.1, tmp).count(build["package"]) == 1
        finally:
            lab.httpd.server_close()
