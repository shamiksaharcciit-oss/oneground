#!/usr/bin/env python3
"""
oneground fixture builder — thin wrapper (task 007)
====================================================

The builder moved into the package at `oneground.fixture.build`. This file
stays because `corpora/run_arxiv_150k.sh`, `corpora/POD_SETUP.md` and three
task reports invoke it by path, and a pod session mid-flight should not
discover that its entry point was renamed.

It re-exports the names `corpora/export_ground_view.py` loads from it
(`kmeans`, `centroid_dists`, `one_region_exact_recall`, `sha256_file`,
`round_floats`, `write_json_stable`), so that module keeps working unchanged.

    python corpora/build_fixture.py --spec fixtures/arxiv-150k.fixture.yaml \
        --source /workspace/arxiv-metadata-oai-snapshot.json \
        --out fixtures/

Prefer `oneground fixture build` in new work.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground.fixture.build import (  # noqa: E402,F401
    RECEIPT_ARTIFACTS, build, characterize, fmt_dur, log, project)
from oneground.measures import (  # noqa: E402,F401
    centroid_dists, kmeans, one_region_exact_recall, two_nn_lid)
from oneground.measures.drift import recall  # noqa: E402,F401
from oneground.receipts import (  # noqa: E402,F401
    MANIFEST_NAME, append_manifest, round_floats, sha256_array, sha256_file,
    torch_receipt, write_json_stable, write_manifest)
from oneground.sample.arxiv import (  # noqa: E402,F401
    eligible, primary_category, sample_records, split_queries, year_of)
from oneground.truth import exact_knn  # noqa: E402,F401


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--source", required=True,
                    help="arxiv-metadata-oai-snapshot.json")
    ap.add_argument("--out", default="fixtures")
    ap.add_argument("--skip-projection", action="store_true")
    args = ap.parse_args()
    build(args.spec, args.source, out=args.out,
          skip_projection=args.skip_projection)


if __name__ == "__main__":
    main()
