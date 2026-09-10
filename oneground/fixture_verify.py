#!/usr/bin/env python3
"""Deprecated entry point. The verifier moved in task 007.

    old:  python oneground/fixture_verify.py fixture verify arxiv-smoke
    new:  oneground fixture verify arxiv-smoke

The module now lives at `oneground/fixture/verify.py`. This shim keeps the old
file path working for one release, because three task reports, the pod run
script and POD_SETUP.md all invoke it by path, and a pod session already in
flight should not fail on a rename.

Remove after the next release.
"""

import os
import sys

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground.fixture.verify import main  # noqa: E402

if __name__ == "__main__":
    print("DEPRECATED: oneground/fixture_verify.py has moved to "
          "`oneground fixture verify <id>`; this shim is removed after the "
          "next release.", file=sys.stderr)
    sys.exit(main())
