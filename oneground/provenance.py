"""Which build is this, and is it the one you meant?

A leaf: standard library only, so anything may depend on it. That is the
point rather than a convenience. The server has to be able to say which build
it is serving, and until this module existed the answer lived behind
`oneground.receipts` (which imports torch) and `oneground.environment` (faiss,
sklearn) -- two packages the lab's guard refuses every served module, for
good reason. The choice was a second implementation of *what commit is this*
or one more leaf. This is the second time that choice has come up in this
slice and the answer is the same both times; the first was `oneground/param.py`.

`producing_version` and `checkout_root` **moved here** from those two modules
and are re-exported from their old homes, so every existing importer is
unaffected and there is still exactly one of each.

WHAT THIS EXISTS TO PREVENT
---------------------------
A server was started from this project and handed to a developer to look at.
It answered 200, listed nine runs, and served a page with no write half --
because the console script `oneground.exe` resolves the package by *install
location*, and on that machine the install pointed at a third checkout that
predated the work by weeks. The suite had passed against a different
directory minutes earlier.

Nothing was wrong with the code, the tests, the server or the browser. The
build being served was simply not the build anyone had in mind, and no part
of the system was able to notice, because no part of it had ever been asked
to say which build it was.

> **A server that cannot say which build it serves is a URL nobody should be
> handed.**

So: `identity()` is printed at startup and answered on `/api/check`, and
`conflicting_checkout()` refuses the bind in the one case that produced this
-- a working directory holding an `oneground` package that is not the one
that got imported.
"""

import json
import os

#: What `setup.py` records at build time so a wheel can answer the same
#: question a checkout can.
BUILD_STAMP_NAME = "_build_stamp.json"

#: This package's directory, which is the thing the whole module is about.
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def checkout_root(start=None):
    """The nearest directory at or above `start` holding a `.git`, else None.

    A `.git` is a directory in a checkout and a file in a worktree or a
    submodule; either answers "there is a tree here that git could describe".
    Walks upward because a command may run from a subdirectory.
    """
    d = os.path.abspath(start or ".")
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _run_git(args):
    """`git <args>` in the package's own tree, or None if it cannot be run."""
    import subprocess
    try:
        r = subprocess.run(["git"] + list(args), cwd=PACKAGE_DIR,
                           capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return None, "%s: %s" % (type(e).__name__, e)
    if r.returncode != 0:
        return None, "git %s: exit %s: %s" % (
            " ".join(args), r.returncode,
            r.stderr.decode("utf-8", "replace").strip() or "(no stderr)")
    return r.stdout.decode("utf-8", "replace").strip(), None


def _build_stamp():
    """What `setup.py` recorded at build time, or None."""
    path = os.path.join(os.path.dirname(PACKAGE_DIR), BUILD_STAMP_NAME)
    for candidate in (path, os.path.join(PACKAGE_DIR, BUILD_STAMP_NAME)):
        try:
            with open(candidate, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return None


def producing_version():
    """What produced this artifact: the version, and the commit if knowable.

    Task 033. Every other input to a measurement is recorded -- the seed, the
    pins, the corpus digests, the run-level settings -- and until this the one
    that decides what those inputs *mean* was not.

        {"version": "0.1.0",
         "commit": "<40 hex>" | None,
         "dirty": True | False | None,
         "source": "checkout" | "wheel" | "unknown",
         "note": "<why commit is None, when it is>"}

    `commit` is None with a stated reason rather than a guess or a refusal:
    an installed wheel has no git, which task 022 made a first-class case. A
    wheel built by this project's `setup.py` carries a build stamp and
    answers as confidently as a checkout.

    **Only the version and the commit.** Never a branch, a remote, a tag or a
    build path: those name a person's working arrangements rather than the
    code, and the identifier scan exists because that distinction gets lost.
    """
    from . import __version__

    out = {"version": __version__, "commit": None, "dirty": None,
           "source": "unknown", "note": ""}

    stamp = _build_stamp()
    if stamp:
        out["source"] = "wheel"
        out["commit"] = stamp.get("commit")
        out["dirty"] = stamp.get("dirty")
        if not out["commit"]:
            out["note"] = str(stamp.get("note") or
                              "built without a commit recorded")
        return out

    if checkout_root(PACKAGE_DIR) is None:
        out["note"] = ("installed without a build stamp and not a git "
                       "checkout, so no commit can be recorded")
        return out

    commit, problem = _run_git(["rev-parse", "HEAD"])
    if commit is None:
        out["source"] = "checkout"
        out["note"] = "this is a checkout and git could not be asked: %s" % (
            problem,)
        return out
    status, problem = _run_git(["status", "--porcelain"])
    out.update(source="checkout", commit=commit,
               dirty=None if status is None else bool(status.strip()))
    if status is None:
        out["note"] = "the working tree's cleanliness could not be read: %s" % (
            problem,)
    return out


def identity():
    """Which build this is, in the terms a reader can check.

    The package directory first, because that is the field that would have
    answered the question the incident asked -- the version and the commit
    were identical between the two checkouts involved, and only the path
    differed.
    """
    out = {"package": PACKAGE_DIR, "checkout": checkout_root(PACKAGE_DIR)}
    out.update(producing_version())
    return out


def conflicting_checkout(cwd=None):
    """The ambiguity that produced this module, or None.

    If the working directory holds an `oneground` package and it is **not**
    the one that was imported, both are named. That is the exact shape of the
    incident: a developer working in one checkout, a console script resolving
    to another, and a server that came up looking correct.

    It is deliberately narrow. Running an installed oneground from inside
    some unrelated directory is fine and common, and returns None here; the
    refusal fires only when the working directory *is* a checkout of this
    project, which is when "which build is this" stops being obvious and
    starts mattering.
    """
    here = os.path.abspath(cwd or os.getcwd())
    root = checkout_root(here)
    if root is None:
        return None
    candidate = os.path.join(root, "oneground")
    if not os.path.isfile(os.path.join(candidate, "__init__.py")):
        return None
    if os.path.normcase(os.path.abspath(candidate)) == \
            os.path.normcase(PACKAGE_DIR):
        return None
    return {"imported": PACKAGE_DIR, "working_directory": candidate,
            "checkout": root}
