"""Reading back a path a receipt recorded (task 044g).

`public_path` makes a receipt say **what** a file is rather than where one
machine kept it. That is only half a design: something has to find the file
again. These are the other half.

THE MEASUREMENT THAT CHOSE THIS SHAPE
-------------------------------------
Of 32 recorded paths in this checkout's `runs/`, **seven did not open as
absolute paths** -- two of them `/workspace/...` from pod sessions, two from a
checkout that no longer exists, two from a sibling checkout. A pod session
always produces a path the laptop cannot open, and pod sessions are how this
project runs heavy jobs, so the absolute form was already failing on the
normal case while appearing to be the safe one.

**The digest is what makes searching safe.** Every receipt records `sha256`
beside the path, so a candidate is confirmed rather than guessed at.
"""

import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import receipts as R                             # noqa: E402


def _write(path, text="pins\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return hashlib.sha256(text.encode()).hexdigest()


def test_a_pod_path_resolves_against_the_checkout_it_was_fetched_into(tmp_path):
    """The case the measurement turned on.

    A run produced on a pod records `/workspace/...`, is fetched here, and
    must still find its requirements file. The recorded form is
    repo-relative, so it resolves against the checkout the workdir sits in --
    not against the pod's filesystem, which is not here.
    """
    checkout = tmp_path / "oneground"
    (checkout / "oneground").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    digest = _write(str(checkout / "requirements.pod.yaml"))
    workdir = checkout / "runs" / "fetched-from-pod"
    workdir.mkdir(parents=True)

    got, how = R.resolve_recorded_path(
        "requirements.pod.yaml", workdir=str(workdir), sha256=digest)
    assert got is not None, how
    assert os.path.samefile(got, str(checkout / "requirements.pod.yaml"))
    assert how == "the workdir's checkout"


def test_a_candidate_whose_digest_differs_is_not_accepted(tmp_path):
    """The property that makes searching several bases safe at all.

    A same-named file in an earlier base must not be returned when the digest
    says it is a different file -- otherwise widening the search would quietly
    make wrong answers more likely instead of less.
    """
    checkout = tmp_path / "co"
    (checkout / "oneground").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    workdir = checkout / "runs" / "r"
    workdir.mkdir(parents=True)

    _write(str(workdir / "requirements.yaml"), "the wrong file\n")
    right = _write(str(checkout / "requirements.yaml"), "the right one\n")

    got, how = R.resolve_recorded_path(
        "requirements.yaml", workdir=str(workdir), sha256=right)
    assert os.path.samefile(got, str(checkout / "requirements.yaml")), how


def test_without_a_digest_the_base_that_found_it_is_reported(tmp_path):
    """A resolved path whose provenance is unstated is how the wrong file gets
    read quietly. The caller is always told which base answered."""
    checkout = tmp_path / "co"
    (checkout / "oneground").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    workdir = checkout / "runs" / "r"
    workdir.mkdir(parents=True)
    _write(str(checkout / "requirements.yaml"))

    got, how = R.resolve_recorded_path(
        "requirements.yaml", workdir=str(workdir))
    assert got is not None
    assert how in R.RESOLUTION_BASES


def test_nothing_found_returns_every_base_it_tried(tmp_path):
    """The refusal has to be able to say where it looked, or the remedy is an
    inference rather than a sentence."""
    workdir = tmp_path / "runs" / "r"
    workdir.mkdir(parents=True)
    got, tried = R.resolve_recorded_path(
        "requirements.yaml", workdir=str(workdir), sha256="0" * 64)
    assert got is None
    assert len(tried) >= 2
    assert all(len(t) == 2 for t in tried), tried


def test_an_absolute_path_still_works(tmp_path):
    """Back-compatibility, asserted. Pre-044g receipts hold absolute paths and
    must keep resolving on the machine that wrote them."""
    p = tmp_path / "requirements.yaml"
    digest = _write(str(p))
    got, how = R.resolve_recorded_path(str(p), sha256=digest)
    assert os.path.samefile(got, str(p))
    assert how == "as recorded"


def test_an_empty_recorded_path_is_not_a_resolution(tmp_path):
    assert R.resolve_recorded_path(None, workdir=str(tmp_path)) == (None, [])
    assert R.resolve_recorded_path("", workdir=str(tmp_path)) == (None, [])


def test_checkout_of_finds_the_checkout_and_not_a_workdir():
    """`runs/x` is not a checkout; the repository containing it is."""
    here = os.path.dirname(os.path.abspath(__file__))
    assert R.checkout_of(here) == R.REPO_ROOT


def test_checkout_of_returns_none_outside_any_checkout(tmp_path):
    assert R.checkout_of(str(tmp_path)) is None
