"""What an engine can actually build (task 034).

034 makes the index algorithm a choice in `simulate`: `flat`, `hnsw`, `ivf`
and `ivf_pq`, all four measured against exact ground truth. Those are faiss's
four. Engines offer something else. Qdrant builds HNSW and nothing else -- its
quantisation is a modifier on that graph, not a separate index family.
pgvector offers HNSW and IVFFlat, and its IVFFlat is not faiss's IVF:
different construction, different parameter names, different behaviour.

Without this module a user simulates `ivf_pq`, learns what it costs on their
corpus, takes it to `verify`, and finds out afterwards that neither engine
they are considering can build it. The refusal should be early, named, and
distinguishable from an absence.

THREE STATES, NOT TWO
---------------------
An engine either builds a family, cannot build it, or has not been asked.
The third is not the second, and collapsing them is the defect this module
exists to prevent: `cannot_build` means *choose a different engine*, and
`unresolved` means *nobody has run the resolution yet*. Only `cannot_build`
refuses a run; `unresolved` is a couldn't-check with its own remedy.

RESOLVED, NOT DOCUMENTED
------------------------
A declaration is `RESOLVED` only when it came from a running engine of a
pinned version, and it records which version answered. A table typed in from
an engine's documentation is a guess about a version nobody ran, and it is
exactly what this project calls declared-and-unchecked. An adapter that has
never been resolved says so, in every row, and `verify` reports it as
couldn't-check rather than as a capability.

APPROXIMATE IS A STATE, NOT A FOOTNOTE
--------------------------------------
pgvector's IVFFlat and faiss's IVF are both "an inverted file over k-means
cells", and they are not the same index. A mapping that is not exact is
recorded `approximate=True` with `differs` saying what, and `differs` is
required: an approximate mapping with nothing said about it is refused by the
conformance suite, because it would read as a correspondence.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# The families are the simulator's, not this module's: an adapter answers
# about the same four `simulate` measures, or the two halves of the tool are
# talking about different things. Re-exported so an adapter names them from
# here rather than reaching into the models package.
from ..models.base import (FLAT, HNSW, INDEX_ALGORITHMS,  # noqa: F401
                           IVF, IVF_PQ)

# What an engine's answer about one family can be.
BUILDS = "builds"
CANNOT_BUILD = "cannot_build"
UNRESOLVED = "unresolved"
STATUSES = (BUILDS, CANNOT_BUILD, UNRESOLVED)

# Where a coverage declaration came from.
RESOLVED = "resolved"          # a running engine of a recorded version said so
NOT_RESOLVED = "not_resolved"  # nobody has asked an engine yet


class CoverageError(ValueError):
    """A coverage declaration that cannot be believed."""


@dataclass
class FamilySupport:
    """One engine's answer about one index family.

    `engine_name` is what the engine calls it -- `hnsw`, `ivfflat` -- and
    `params` maps the family's declared keys to the engine's own parameter
    names, so a reader can see that `M` is `m` here and `ef_construction`
    there without reading two adapters.
    """

    family: str
    status: str = UNRESOLVED
    engine_name: Optional[str] = None
    params: Dict[str, str] = field(default_factory=dict)
    approximate: bool = False
    differs: str = ""
    note: str = ""

    def as_dict(self):
        return {
            "family": self.family,
            "status": self.status,
            "engine_name": self.engine_name,
            "params": dict(self.params),
            "approximate": bool(self.approximate),
            "differs": self.differs,
            "note": self.note,
        }


@dataclass
class IndexCoverage:
    """One engine's answer about all four families.

    `kind` is `resolved` only when `engine_version` names the version that
    answered. Everything else is a declaration nobody has checked, and it
    says so rather than being absent.
    """

    engine: str
    families: Dict[str, FamilySupport] = field(default_factory=dict)
    kind: str = NOT_RESOLVED
    engine_version: Optional[str] = None
    resolved_at: Optional[str] = None
    how: str = ""                # what was asked of the engine, in one line
    raw: Dict[str, Any] = field(default_factory=dict)

    def status(self, family):
        support = self.families.get(family)
        return support.status if support else UNRESOLVED

    def builds(self, family):
        return self.status(family) == BUILDS

    def buildable(self):
        return sorted(n for n, s in self.families.items()
                      if s.status == BUILDS)

    def as_dict(self):
        return {
            "engine": self.engine,
            "kind": self.kind,
            "engine_version": self.engine_version,
            "resolved_at": self.resolved_at,
            "how": self.how,
            "families": {n: s.as_dict() for n, s in sorted(
                self.families.items())},
            "raw": dict(self.raw),
            "note": ("resolved against a running engine of the version named "
                     "above" if self.kind == RESOLVED else
                     "not resolved: no engine has been asked, so every family "
                     "here is couldn't-check, not a capability"),
        }


def unresolved(engine, why=""):
    """A coverage for an adapter that has never been asked an engine.

    The honest default. An adapter that shipped a table typed in from
    documentation would look identical to a resolved one in a report, which
    is why the default is this and not a guess.
    """
    return IndexCoverage(
        engine=engine,
        families={f: FamilySupport(family=f, status=UNRESOLVED, note=why)
                  for f in INDEX_ALGORITHMS},
        kind=NOT_RESOLVED, how=why)


def resolved(engine, version, supported, how, raw=None):
    """A coverage from a live engine.

    `supported` maps a family to a `FamilySupport` for the families the
    engine builds or is known not to; every family not named is filled in as
    `cannot_build`, because a live resolution that enumerated the engine's
    index types has answered for all of them.
    """
    families = {}
    for name in INDEX_ALGORITHMS:
        got = supported.get(name)
        families[name] = got if got is not None else FamilySupport(
            family=name, status=CANNOT_BUILD,
            note=f"{engine} {version} lists no index type for {name}")
    cov = IndexCoverage(engine=engine, families=families, kind=RESOLVED,
                        engine_version=str(version),
                        resolved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime()),
                        how=how, raw=dict(raw or {}))
    problems(cov, raise_on_problem=True)
    return cov


def problems(coverage, raise_on_problem=False):
    """Every reason a coverage declaration cannot be believed, as sentences.

    Reported together rather than one at a time, as 022 requires of a
    precondition: someone fixing an adapter should learn the whole shape of
    the requirement from one refusal.
    """
    out = []
    missing = sorted(set(INDEX_ALGORITHMS) - set(coverage.families))
    if missing:
        out.append(
            f"{coverage.engine} declares nothing about {', '.join(missing)}: "
            "an adapter answers for every declared family, because a family "
            "left out is indistinguishable from one it cannot build")
    for name, support in sorted(coverage.families.items()):
        where = f"{coverage.engine}.{name}"
        if name not in INDEX_ALGORITHMS:
            out.append(f"{where} is not a declared index family; they are "
                       + ", ".join(INDEX_ALGORITHMS))
        if support.status not in STATUSES:
            out.append(f"{where} has status {support.status!r}; the states "
                       "are " + ", ".join(STATUSES))
        if support.approximate and not support.differs.strip():
            out.append(
                f"{where} is declared an approximate mapping and says nothing "
                "about what differs. An approximate mapping with no "
                "difference stated reads as a correspondence, which is what "
                "pgvector's IVFFlat is not to faiss's IVF")
        if support.status == BUILDS and not support.engine_name:
            out.append(f"{where} says the engine builds it but not what the "
                       "engine calls it")
    if coverage.kind == RESOLVED and not coverage.engine_version:
        out.append(f"{coverage.engine} claims a resolved coverage with no "
                   "engine version; a resolution names the version that "
                   "answered or it is a guess")
    if coverage.kind not in (RESOLVED, NOT_RESOLVED):
        out.append(f"{coverage.engine} coverage kind {coverage.kind!r} is "
                   f"neither {RESOLVED} nor {NOT_RESOLVED}")
    if out and raise_on_problem:
        raise CoverageError("index coverage refused:\n  - "
                            + "\n  - ".join(out))
    return out


# --------------------------------------------------------------------------
# what `verify` asks before it creates anything
# --------------------------------------------------------------------------
# Three answers, and the third is not the second.

VERIFIABLE = "verifiable"
NOT_VERIFIABLE_HERE = "not_verifiable_here"
COVERAGE_UNRESOLVED = "coverage_unresolved"


@dataclass
class Buildability:
    """Whether one family can be verified on one engine, and what to do.

    `remedy` is the sentence a decision log prints. For a not-verifiable-here
    row it is not a command: it is a different engine, or an adapter that does
    not exist, and saying "run it" would be false.
    """

    engine: str
    family: str
    state: str
    reason: str
    remedy: str

    def as_dict(self):
        return {"engine": self.engine, "index": self.family,
                "state": self.state, "reason": self.reason,
                "remedy": self.remedy}


def buildability(coverage, family):
    """Can this engine build this index family, and what follows if not."""
    support = coverage.families.get(family)
    status = support.status if support else UNRESOLVED
    if status == BUILDS:
        return Buildability(
            engine=coverage.engine, family=family, state=VERIFIABLE,
            reason=f"{coverage.engine} {coverage.engine_version or ''}".strip()
            + f" builds {family} as {support.engine_name}",
            remedy="")
    if status == CANNOT_BUILD:
        offers = coverage.buildable()
        return Buildability(
            engine=coverage.engine, family=family, state=NOT_VERIFIABLE_HERE,
            reason=(f"{coverage.engine} "
                    f"{coverage.engine_version or '(version unrecorded)'} "
                    f"cannot build index={family}; it offers "
                    + (", ".join(offers) if offers else "no index family this "
                       "project declares")),
            remedy=("a different engine, or an adapter for one that builds "
                    f"{family}. There is no command that settles this on "
                    f"{coverage.engine}"))
    return Buildability(
        engine=coverage.engine, family=family, state=COVERAGE_UNRESOLVED,
        reason=(f"{coverage.engine} has not been asked what index families it "
                "builds; the declaration is not resolved against a running "
                "engine"),
        remedy=(f"resolve the coverage against a pinned {coverage.engine}: "
                "`oneground adapters coverage` with the engine reachable"))


def coverage_table(coverages):
    """The four families against the adapters, as rows for docs/ADAPTERS.md.

    A fact about the ecosystem rather than about a corpus, which is why it
    belongs beside the adapters rather than in a run's report.
    """
    rows = []
    for family in INDEX_ALGORITHMS:
        row = {"index": family}
        for cov in coverages:
            support = cov.families.get(family)
            row[cov.engine] = (support.as_dict() if support
                               else FamilySupport(family=family).as_dict())
        rows.append(row)
    return rows


def write(path, coverages):
    """Record a resolution, so it is a receipt rather than a memory."""
    doc = {"kind": "declared",
           "note": ("what each engine answered about the index families it "
                    "builds. Resolved against a running engine of the version "
                    "recorded in each block; a block that says not_resolved "
                    "was never asked."),
           "coverages": [c.as_dict() for c in coverages]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def read(path):
    """A recorded resolution, back as `IndexCoverage` objects."""
    return read_blocks((json.load(open(path, encoding="utf-8"))
                        or {}).get("coverages") or [])


def read_blocks(blocks):
    """`as_dict()` output, back as `IndexCoverage` objects.

    Separate from `read` because a verify receipt carries the same blocks
    inline, and a report should not have to go back to a file to read what
    the run it is reporting on already recorded.
    """
    out = []
    for block in blocks:
        families = {n: FamilySupport(
            family=s.get("family", n), status=s.get("status", UNRESOLVED),
            engine_name=s.get("engine_name"), params=dict(s.get("params") or {}),
            approximate=bool(s.get("approximate")), differs=s.get("differs", ""),
            note=s.get("note", ""))
            for n, s in (block.get("families") or {}).items()}
        out.append(IndexCoverage(
            engine=block["engine"], families=families,
            kind=block.get("kind", NOT_RESOLVED),
            engine_version=block.get("engine_version"),
            resolved_at=block.get("resolved_at"), how=block.get("how", ""),
            raw=dict(block.get("raw") or {})))
    return out
