"""Build hook: the wheel carries the fixture specs, and what built it.

Everything about the distribution is declared in pyproject.toml. This file
exists for two steps pyproject cannot express.

**The fixtures.** Copying files from `fixtures/`, which is outside the package
directory, into `oneground/_fixtures/` in the built package. Task 022 --
`oneground fixture verify <id>` must work from a bare `pip install`, outside
any checkout.

**The build stamp.** Writing `oneground/_build_stamp.json` with the commit the
wheel was built from. Task 033: every artifact records the version and commit
that produced it, and an installed wheel has no git to ask. Without this a
wheel's artifacts would carry `commit: null` forever, which is honest and
useless; with it they answer as confidently as a checkout's. A build from a
tree that is not a checkout still writes a stamp, with `commit: null` and the
reason -- the couldn't-check habit, at build time.

The selection rule lives in `oneground/fixture/shipped.py` and is read here by
path, because the build environment has none of the package's dependencies.
"""

import json
import os
import runpy
import subprocess

from setuptools import setup
from setuptools.command.build_py import build_py

HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = runpy.run_path(os.path.join(HERE, "oneground", "fixture",
                                      "shipped.py"))

# What the stamp may contain. A commit and whether the tree was dirty are
# facts about the code; a branch, a remote or a build path name whose machine
# built it, and this project's identifier scan exists because that line gets
# crossed by accident.
STAMP_NAME = "_build_stamp.json"


def _git(args):
    try:
        r = subprocess.run(["git"] + list(args), cwd=HERE,
                           capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 \
        else None


def build_stamp():
    """`{commit, dirty, note}` for the tree this wheel is being built from."""
    commit = _git(["rev-parse", "HEAD"])
    if commit is None:
        return {"commit": None, "dirty": None,
                "note": "built from a tree with no readable git checkout"}
    status = _git(["status", "--porcelain"])
    return {"commit": commit,
            "dirty": None if status is None else bool(status.strip()),
            "note": "" if status is not None else
                    "the working tree's cleanliness could not be read"}


class build_py_with_fixtures(build_py):
    """`build_py`, then the fixture files into the package's build tree."""

    def run(self):
        super().run()
        root = os.path.join(HERE, "fixtures")
        if not os.path.isdir(root):
            # Refuse rather than ship a package whose `fixture verify` cannot
            # find a fixture. An sdist without them is a broken sdist.
            raise SystemExit(f"{root} is missing; the wheel would ship no "
                             "fixtures. See MANIFEST.in.")
        files = SHIPPED["shipped_files"](root)
        if not files:
            raise SystemExit(f"no fixture specs in {root}")
        dest_root = os.path.join(self.build_lib, "oneground",
                                 SHIPPED["PACKAGE_DIRNAME"])
        for src, rel in files:
            dest = os.path.join(dest_root, *rel.split("/"))
            self.mkpath(os.path.dirname(dest))
            self.copy_file(src, dest)

        stamp_path = os.path.join(self.build_lib, "oneground", STAMP_NAME)
        self.mkpath(os.path.dirname(stamp_path))
        with open(stamp_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(build_stamp(), f, indent=2, sort_keys=True)
            f.write("\n")


setup(cmdclass={"build_py": build_py_with_fixtures})
