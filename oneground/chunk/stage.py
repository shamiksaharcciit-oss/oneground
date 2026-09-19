"""`oneground chunk` — the stage, run alone (task 031).

A stage **before** the vector-database simulation, **optional**, and runnable
**in isolation**. This module is what `oneground chunk` calls, and what
`characterize` calls when the corpus is given as text rather than as vectors.

**Given vectors, it reports couldn't-check.** That is not an error path and
not a degraded mode: if the input is `.npy`, the cut has already happened and
is out of the instrument's reach. `docs/CHUNKING.md` §5 requires the report to
say so in those words rather than omitting the section, because a missing
section reads as "no problem found".
"""

import os

import yaml

from .report import DeclarationError, Extraction

VECTORS_COULDNT_CHECK = (
    "chunking: couldn't-check — vectors were supplied, not text. The cut has "
    "already happened and is out of this instrument's reach: a vector carries "
    "no record of where its chunk began or ended, so neither the structural "
    "measures nor self-retrieval by containment can be computed. Supply the "
    "extracted text, one record per document, to measure chunking."
)


class StageError(RuntimeError):
    """The chunking stage cannot run on what it was given."""


def corpus_is_vectors(req):
    """Does this requirements file supply vectors rather than text?"""
    corpus = req.get("corpus") or {}
    if corpus.get("documents") or corpus.get("text"):
        return False
    sample = corpus.get("sample") or {}
    # PRESENCE of the key is the declaration, not its truthiness. An empty
    # `vectors:` block is a malformed vector corpus, not a text one, and
    # reading it as text would send the stage looking for documents that were
    # never promised.
    return "vectors" in sample or "vectors" in corpus


def declared_extraction(req):
    """The extraction declaration, required, carried onto every result."""
    d = req.get("extraction")
    if not d:
        raise DeclarationError(
            "this requirements file declares no `extraction:`. oneground "
            "takes extracted text and does not run extractors, so what "
            "produced the text cannot be inferred and must be stated -- name "
            "the tool and its version, or `unknown` with a reason.")
    return Extraction(d.get("tool"), d.get("version"), d.get("reason"))


def run(requirements, documents=None, anchors=None, device=None):
    """Run the stage from a requirements file. Returns a process exit code."""
    with open(requirements, encoding="utf-8") as f:
        req = yaml.safe_load(f)

    if corpus_is_vectors(req):
        print(VECTORS_COULDNT_CHECK)
        # Not a failure: the command did what it could and said what it could
        # not. A non-zero exit would read as "the run broke".
        return 0

    declared_extraction(req)          # refuses here, before any work

    # The comparison itself lives in corpora/run_chunking.py, which is also
    # what the pod session runs. One implementation, two entry points: a
    # second copy of the loop would be a second thing to keep correct.
    import subprocess
    import sys
    script = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "corpora",
        "run_chunking.py")
    cmd = [sys.executable, script, requirements]
    if documents:
        cmd += ["--documents", str(documents)]
    if anchors:
        cmd += ["--anchors", str(anchors)]
    if device:
        cmd += ["--device", device]
    return subprocess.call(cmd)
