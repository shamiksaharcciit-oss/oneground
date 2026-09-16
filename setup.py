"""Build hook: the wheel carries the fixture specs and their small receipts.

Everything about the distribution is declared in pyproject.toml. This file
exists for one step pyproject cannot express: copying files from `fixtures/`,
which is outside the package directory, into `oneground/_fixtures/` in the
built package. Task 022 -- `oneground fixture verify <id>` must work from a
bare `pip install`, outside any checkout.

The selection rule lives in `oneground/fixture/shipped.py` and is read here by
path, because the build environment has none of the package's dependencies.
"""

import os
import runpy

from setuptools import setup
from setuptools.command.build_py import build_py

HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = runpy.run_path(os.path.join(HERE, "oneground", "fixture",
                                      "shipped.py"))


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


setup(cmdclass={"build_py": build_py_with_fixtures})
