"""What the installed package carries of each fixture.

Task 022. `oneground fixture verify arxiv-150k` from a bare `pip install`
answered `error: no such fixture directory`, because the command only looked
in the current working directory. The specs and the small receipts are what
the command reads, and they are a few megabytes, so the wheel carries them.

The vectors, the queries and the sample are a release asset and are never in
the wheel: 480 MB does not belong in a package any more than in git.

This module is read by `setup.py` with `runpy`, at build time, in an isolated
environment that has none of the package's dependencies. So it imports the
standard library and nothing else.
"""

import os

# Inside the installed package: oneground/_fixtures/<id>.fixture.yaml and
# oneground/_fixtures/<id>/<file>.
PACKAGE_DIRNAME = "_fixtures"

# Per fixture directory. Exactly the files `fixture verify` reads besides the
# release asset: the manifest it checks, the ground truth its values are
# scored against, and the three small receipts beside them.
SHIPPED_FILES = ("MANIFEST.sha256", "characterization.json",
                 "build_info.json", "query_ids.json", "ground_truth.npy")

# Never shipped, whatever a directory happens to hold on the machine that
# builds the wheel. `projection.npy` is gitignored and derived; the other three
# are the release asset.
NEVER_SHIPPED = ("vectors.npy", "queries.npy", "sample.jsonl.zst",
                 "projection.npy")

SPEC_SUFFIX = ".fixture.yaml"


def shipped_files(fixtures_root):
    """[(source path, path under _fixtures/)] for every fixture spec found.

    Every `<id>.fixture.yaml` in `fixtures_root` ships, with whichever of
    SHIPPED_FILES exist in `<id>/`. The allowlist is the rule: a file that is
    not named here does not ship, so a stray vectors.npy on the build machine
    cannot reach the wheel.
    """
    out = []
    for name in sorted(os.listdir(fixtures_root)):
        if not name.endswith(SPEC_SUFFIX):
            continue
        fid = name[:-len(SPEC_SUFFIX)]
        out.append((os.path.join(fixtures_root, name), name))
        d = os.path.join(fixtures_root, fid)
        for f in SHIPPED_FILES:
            p = os.path.join(d, f)
            if os.path.isfile(p):
                out.append((p, fid + "/" + f))
    return out
