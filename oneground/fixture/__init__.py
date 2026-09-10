"""Public fixtures: building them, and verifying an installation reproduces
their published values.

    build    spec -> artifacts, deterministically from the spec's seeds
    verify   recompute every digest in a fixture's MANIFEST.sha256

A fixture is not a leaderboard. It exists so that a stranger can install
oneground, rebuild it, and confirm the numbers the project publishes.
"""

from . import verify as verify_mod
from .build import build, characterize, project, RECEIPT_ARTIFACTS
from .reference import ref_semantic_sharded, ref_single_node

__all__ = ["RECEIPT_ARTIFACTS", "build", "characterize", "project",
           "ref_semantic_sharded", "ref_single_node", "verify_mod"]
