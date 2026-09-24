"""A per-engine verdict's remedy names its own engine (045, finding 2).

Two `to_resolve` claims in the arXiv report cited
`verify_info.json:engine_facts.index_params` with no member. `engine_facts`
lives under `engines[]`, one level below where the source points -- but the
missing member was the symptom, not the defect. **The claims' own text spanned
both engines** ("pgvector has not been asked ...; qdrant has not been asked
..."), so there was no single engine whose value the sentence rested on.

The verdicts were always one per engine. What spanned both was the remedy:
every engine's decision was joined onto each verdict. So the repair narrows
the sentence to the verdict carrying it, and the claim structure needs no
change.

**Why the obvious repair was refused**: rewriting the source as
`verify_info.json:engines[].engine_facts.index_params` would have made the
entry resolve while still not saying which engine's value it rests on -- a
link that looks right and answers nothing, which is worse than one that says
it cannot answer. 041's interface rendered it `unresolved`, which was correct.

THE MUTANT IS THE ACCEPTANCE, as for finding 1: restore the joined remedy and
the test must fail.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.adapters import index_families as IF              # noqa: E402
from oneground.report import verdict as V                        # noqa: E402


class _Cov:
    def __init__(self, engine):
        self.engine = engine
        self.families = {}
        self.asked = False


class _Verdict:
    def __init__(self, engine):
        self.constraint = "latency_p95"
        self.outcome = V.COULDNT_CHECK
        self.engine = engine
        self.remedy = ""
        self.couldnt_check_kind = None


class _Option:
    def __init__(self, verdicts):
        self.params = {}
        self.verdicts = verdicts


# --------------------------------------------------------- the acceptance
def test_each_engines_remedy_names_only_that_engine():
    """The mutant restored would join both names into each remedy."""
    fn = V.classify_couldnt_checks
    opt = _Option([_Verdict("qdrant"), _Verdict("pgvector")])
    fn(opt, [_Cov("qdrant"), _Cov("pgvector")])

    for v in opt.verdicts:
        assert v.remedy, "a coverage-unresolved verdict lost its remedy"
        other = "pgvector" if v.engine == "qdrant" else "qdrant"
        assert v.engine in v.remedy, (v.engine, v.remedy)
        assert other not in v.remedy, (
            "%s's remedy names %s: a per-engine verdict is carrying a "
            "sentence about both, which is the defect finding 2 is about.\n%s"
            % (v.engine, other, v.remedy))


def test_a_verdict_with_no_engine_keeps_every_decision():
    """The mirror, and it is not symmetry for its own sake.

    A constraint that is not per-engine has no one engine's coverage to cite.
    Giving it an empty remedy would turn a real obstacle into silence, which
    is the failure mode this project cares about most.
    """
    fn = V.classify_couldnt_checks
    v = _Verdict(None)
    opt = _Option([v])
    fn(opt, [_Cov("qdrant"), _Cov("pgvector")])
    if v.remedy:
        assert "qdrant" in v.remedy and "pgvector" in v.remedy, v.remedy
