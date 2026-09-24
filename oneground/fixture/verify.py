#!/usr/bin/env python3
"""
oneground fixture verify
========================

Minimal form of `oneground fixture verify <id>`: recompute the sha256 of every
file listed in a fixture's MANIFEST.sha256 and report, per file, one of the
three outcomes the project keeps apart:

    verified       the file is present and its digest matches the manifest
    contradicted   the file is present and its digest does not match
    couldnt_check  there were no bytes to compare, or no way to compare the
                   numbers — never rounded up to verified, and never rounded
                   down to contradicted either: absence is not evidence that
                   something differs. Large artifacts (vectors.npy,
                   projection.npy, sample.jsonl.zst) are deliberately not
                   committed, so this is the expected outcome for them, and
                   for every value, in a fresh clone.

Each file also carries a `kind`, which says what reproducing it would mean:

    receipt        re-derivable from the seeds and rules in the spec; two
                   builds from the same source must produce the same bytes
    declared       recorded or derived, not re-derivable as a receipt.
                   build_info.json holds the timestamp, library versions, host
                   and device of the build; projection.npy is a seeded UMAP,
                   not guaranteed bit-identical across BLAS builds and
                   illustrative rather than a measurement; ground_view_*.parquet
                   are derived from the receipts beside them for drawing.
                   Their digests are still checked, but a rebuild is not
                   expected to reproduce them, so the value-reproduction pass
                   skips them.

Scope
-----
Two halves, reported separately and summarised separately.

**Digests** say the bytes have not changed since the manifest was written.

**Values** say that *this* installation, on *this* machine, with *these*
library versions, computes the same numbers from those bytes. That is the
question a user verifying an install actually has, and it is what
`status: verified` in a fixture spec means. Each published value is recomputed
with the same functions the product path uses and compared against the spec's
own tolerance — never one invented here, and never one widened to make
something pass.

**The scope is the release asset, not "vectors and queries".** `drift` needs a
date per record, which lives in `sample.jsonl.zst` -- part of the same
published asset -- so it is recomputed from there rather than reported
unreachable. Which field carries that date comes from the spec's
`source.field_map`: arXiv writes `update_date`, Stack Exchange `creation_date`. A value that is checkable from the published artifacts is a value
this command checks.

Values are couldnt_check, never contradicted, when the release asset is absent
(a fresh clone legitimately has no vectors), when the recorded build used pins
that differ from `requirements.txt`, or — the one that decides most runs — when
**this process** is not running the pinned versions. A value recomputed under
different libraries has not been reproduced under the pins the fixture claims,
however closely it agrees, and the fixture specs say so themselves:

    couldnt_check is reported when a dependency version differs from the
    pinned one; it is never rounded up to verified.

The comparison is still made and the numbers still printed in that case: two
minor versions away, agreement to within a thousandth of tolerance is evidence
about the fixture worth seeing. It is just not the evidence `verified`
requires. A contradiction is never downgraded — disagreement is disagreement,
and an unpinned environment explains it at most.

Where the fixture comes from (task 022)
    `--fixtures <dir>` if given, and only there; otherwise `fixtures/` in the
    current directory; otherwise the copy the installed package carries (the
    specs and small receipts -- see `shipped.py`). The directory used is
    printed, and so is everywhere that was looked.

Preconditions (task 022)
    Three things decide whether the values can be checked: the fixture, the
    pinned environment, and the release asset. A run prints all three
    together, each with what it is and how to satisfy it -- a reader learns
    the whole shape of what they need from one run, not from three. The
    digests are checked whenever the fixture is found, whatever else is
    missing, because they depend on nothing but the bytes.

Exit codes (they describe both halves)
    0   nothing contradicted, and every precondition the values needed was
        met. A file the manifest lists but that is absent is couldnt_check and
        does not change the exit code, and neither is a value that could not
        be recomputed on this host (out of memory, say): each is reported with
        its reason, and the rest carry on.
    1   at least one digest or value contradicted. Always wins.
    2   nothing contradicted, but not everything could be checked: a
        precondition was missing (the preconditions block names which), or
        --strict was given and at least one digest or value is couldnt_check.

couldnt_check never becomes verified in the report, and a contradiction is
never downgraded to couldnt_check. --strict changes what the exit code means,
never what the report says.

Usage
-----
    oneground fixture verify arxiv-smoke
    oneground fixture verify arxiv-150k --asset ~/oneground-assets/arxiv-150k
    oneground fixture verify arxiv-smoke --fixtures fixtures

The old entry point still works for one release:

    python corpora/fixture_verify.py fixture verify arxiv-smoke   (deprecated)
"""

import argparse
import fnmatch
import json
import os
import sys

import yaml

from ..environment import (PINNED, read_requirements_pins,  # noqa: F401
                           running_pin_mismatches, running_versions)
from ..receipts import MANIFEST_NAME, sha256_file
from ..sample.fields import field_map
from .shipped import PACKAGE_DIRNAME, SHIPPED_FILES, SPEC_SUFFIX

# Where the release assets are extracted. Declared, and overridable: the large
# artifacts ship separately from the repository, so a fresh clone has none of
# them and reports couldnt_check rather than failing.
DEFAULT_ASSETS = os.path.join(os.path.expanduser("~"), "oneground-assets")

# The copy of the fixtures the installed package carries (task 022).
PACKAGE_FIXTURES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    PACKAGE_DIRNAME)

# The release assets, by fixture id: the tarball's name and its size in bytes,
# as published in RELEASE_NOTES.md (test_verify checks the two agree). The page
# is the release of the installed version, so a preview install points at the
# preview's release and 0.1.0 at 0.1.0's.
REPOSITORY = "https://github.com/shamiksaharcciit-oss/oneground"
RELEASE_ASSETS = {
    "arxiv-150k": ("arxiv-150k-v1.tgz", 483_467_899),
    "stackexchange-150k": ("stackexchange-150k-v1.tgz", 460_106_909),
}
# What the tarball extracts to, and what the values read from it.
ASSET_MEMBERS = ("vectors.npy", "queries.npy", "sample.jsonl.zst")

VERIFIED = "verified"
CONTRADICTED = "contradicted"
COULDNT_CHECK = "couldnt_check"

# Why a value is couldnt_check (task 022). The summary speaks per cause:
# "not published yet", "not attempted because a precondition is missing",
# "this host could not" and "agreed, but outside the pins" are four different
# sentences, and a summary that collapses them over-reads its rows.
UNPUBLISHED = "unpublished"        # the spec carries no number for it yet
NOT_ATTEMPTED = "not_attempted"    # a precondition is missing
HOST = "host"                      # out of memory, a missing library, an
                                   # unreadable file: this machine, not the
                                   # fixture
RECOMPUTE = "recompute"            # the recomputation failed another way,
                                   # or produced nothing for this value
UNPINNED = "unpinned"              # agreed, outside the pinned environment
BUILD_PINS = "build_pins"          # the recorded build was not pinned
SPEC = "spec"                      # the spec's entry cannot be compared
INPUT = "input"                    # the asset's files do not belong together


class Reason(str):
    """A couldnt_check reason that also carries its cause."""

    def __new__(cls, text, cause=None):
        self = str.__new__(cls, text)
        self.cause = cause
        return self


class ValueRow(tuple):
    """`(name, outcome, detail)` -- still a 3-tuple to anything that unpacks
    it -- plus `cause`, which is None unless the outcome is couldnt_check."""

    def __new__(cls, name, outcome, detail, cause=None):
        self = tuple.__new__(cls, (name, outcome, detail))
        if cause is None and outcome == COULDNT_CHECK:
            cause = getattr(detail, "cause", None)
        self.cause = cause
        return self

RECEIPT = "receipt"
DECLARED = "declared"

# Artifacts that are recorded rather than re-derived. Their digests are checked
# like any other file; what differs is that a rebuild is not expected to
# reproduce them, so value reproduction will skip them.
#
#   build_info.json  the timestamp, versions, host and device of the build
#   projection.npy   UMAP is seeded, but not guaranteed bit-identical across
#                    BLAS builds, and the spec marks the projection
#                    illustrative rather than a measurement
#   ground_view_*    derived from the receipts beside them, illustrative, and
#                    recomputable by corpora/export_ground_view.py
DECLARED_FILES = {"build_info.json", "projection.npy"}
# `report/*`: task 018f publishes the developer's own `oneground report` run of
# the arXiv workdir beside the fixture. It is the product path's output on one
# machine on one day -- timestamps, an environment id, a price table -- so it is
# declared, never a receipt: nothing about it is re-derivable from the seeds.
DECLARED_GLOBS = ("ground_view_*.parquet", "report/*")


def kind_of(name):
    if name in DECLARED_FILES:
        return DECLARED
    if any(fnmatch.fnmatch(name, g) for g in DECLARED_GLOBS):
        return DECLARED
    return RECEIPT


def read_manifest(path):
    """MANIFEST.sha256 lines are '<64-hex><two spaces><filename>'."""
    entries = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            digest, _, name = line.partition("  ")
            if len(digest) != 64 or not name:
                raise ValueError(f"{path}:{lineno}: malformed manifest line: {line!r}")
            entries.append((digest.lower(), name))
    return entries


def verify_digests(fixture_dir, asset_dir=None):
    """Return (results, unlisted), results being [(name, kind, outcome, detail)].

    `asset_dir` is where the release asset was extracted. A file listed in the
    manifest is looked for beside the receipts first and there second, because
    the large artifacts ship separately and calling one absent when it is
    sitting at the documented location is a wrong answer, not a cautious one.
    """
    manifest = os.path.join(fixture_dir, MANIFEST_NAME)
    entries = read_manifest(manifest)
    packaged = _is_packaged(fixture_dir)

    results = []
    for expected, name in entries:
        k = kind_of(name)
        fp = os.path.join(fixture_dir, name)
        where = ""
        if not os.path.exists(fp) and asset_dir:
            alt = os.path.join(asset_dir, name)
            if os.path.exists(alt):
                fp, where = alt, f"  (from {asset_dir})"
        if not os.path.exists(fp):
            hint = (f"; looked in {fixture_dir}"
                    + (f" and {asset_dir}" if asset_dir else ""))
            if name in ASSET_MEMBERS:
                fid = os.path.basename(os.path.normpath(fixture_dir))
                why = ("release asset member, not present"
                       if fid in RELEASE_ASSETS else
                       "not present, and no release asset is published for "
                       "this fixture; building it produces this file")
            elif packaged and name not in SHIPPED_FILES:
                # Task 022. The wheel carries the specs and small receipts.
                # Calling anything else a release asset would send a reader to
                # download a tarball that does not contain it. The ground-view
                # tables and the published report are tracked in the
                # repository; projection.npy is gitignored and is in no
                # published place, so it gets no such pointer.
                why = "not shipped with the installed package"
                if any(fnmatch.fnmatch(name, g) for g in DECLARED_GLOBS):
                    why += "; the repository carries it"
            else:
                why = "artifact not present (release asset, or not built)"
            results.append((name, k, COULDNT_CHECK, why + hint))
            continue
        actual = sha256_file(fp)
        if actual == expected:
            results.append((name, k, VERIFIED, actual + where))
        else:
            results.append((name, k, CONTRADICTED,
                            f"expected {expected}, got {actual}{where}"))

    listed = {name for _, name in entries}
    unlisted = sorted(
        f for f in os.listdir(fixture_dir)
        if f != MANIFEST_NAME
        and f not in listed
        and os.path.isfile(os.path.join(fixture_dir, f))
    )
    return results, unlisted


# Values recomputed from the release asset. `drift` is handled separately
# because it needs a third artifact -- sample.jsonl.zst, for update_date --
# rather than a different computation.
REPRODUCIBLE = ("intrinsic_dimensionality", "boundary_crispness",
                "skew_top10_share", "ambiguous_query_rate")

# The published cutoff. From the spec's own drift definition; never guessed
# and never taken from the data.
DRIFT_CUTOFF = "2019-01-01"

def _is_packaged(path):
    here = os.path.normcase(os.path.abspath(path))
    root = os.path.normcase(os.path.abspath(PACKAGE_FIXTURES))
    return here == root or here.startswith(root + os.sep)


def pin_mismatches(build_info, requirements_path="requirements.txt",
                   pins=None):
    """[(package, built_with, pinned)] for pins that decide the numbers.

    `pins` replaces reading `requirements_path` (task 022: outside a checkout
    the installed distribution's own pins are the set)."""
    pinned = (read_requirements_pins(requirements_path) if pins is None
              else {_norm(k): v for k, v in pins.items()})
    built = {k.lower(): v for k, v in
             (build_info.get("library_versions") or {}).items()}
    out = []
    for name in PINNED:
        want, got = pinned.get(name), built.get(name)
        if want is None or got is None:
            continue
        if str(want) != str(got):
            out.append((name, got, want))
    return out


def read_sample_records(path):
    """The records `build` wrote, in the order it wrote them.

    `sample.jsonl.zst` is base records tagged `role: "base"` followed by
    held-out query records tagged `role: "query"`, each in the order the
    builder embedded them. Returns (base_recs, query_recs).
    """
    import zstandard as zstd

    base_recs, q_recs = [], []
    with open(path, "rb") as f:
        with zstd.ZstdDecompressor().stream_reader(f) as r:
            buf = b""
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for line in lines:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    (q_recs if rec.get("role") == "query"
                     else base_recs).append(rec)
            if buf.strip():
                rec = json.loads(buf)
                (q_recs if rec.get("role") == "query"
                 else base_recs).append(rec)
    return base_recs, q_recs


def recompute_drift(sample_path, base, queries, gt10, seed,
                    cutoff=DRIFT_CUTOFF, log_fn=None, date_field=None):
    """The build's own drift call, with its inputs read back from the asset.

    `date_field` is the record key the timeline is cut on, which the spec's
    `source.field_map` names. It defaults to arXiv's `update_date`, so a spec
    that declares no field map behaves as it always has.

    Task 016 gave the builder a field map and left three readers behind. This
    was the third: stackexchange-150k's records carry `creation_date`, so its
    published drift pair reported `couldnt_check -- the sample records carry
    no update_date field` against a fixture that had just measured it.

    Returns (result_dict, None) or (None, reason).
    """
    import numpy as np

    from ..measures import drift_pair
    from ..sample.fields import DEFAULTS

    date_field = date_field or DEFAULTS["date"]

    if log_fn:
        log_fn(f"  reading {date_field} from {sample_path}")
    try:
        base_recs, q_recs = read_sample_records(sample_path)
    except ImportError:
        return None, Reason("zstandard is not installed, so "
                            "sample.jsonl.zst cannot be read", HOST)
    except (OSError, ValueError) as e:
        return None, Reason(f"could not read {sample_path}: "
                            f"{type(e).__name__}: {e}", HOST)

    # Asserted, not trusted. A file whose base rows do not match vectors.npy
    # is not the file that produced those vectors, and zipping two different
    # corpora together would give a number that looks like a reproduction.
    if len(base_recs) != len(base):
        return None, Reason(f"{sample_path} holds {len(base_recs):,} base "
                            f"records but vectors.npy holds {len(base):,}; "
                            "these are not the same corpus", INPUT)
    if len(q_recs) != len(queries):
        return None, Reason(f"{sample_path} holds {len(q_recs):,} query "
                            f"records but queries.npy holds "
                            f"{len(queries):,}; these are not the same query "
                            "set", INPUT)
    missing = [r for r in (base_recs[:1] + q_recs[:1])
               if date_field not in r]
    if missing:
        have = sorted((base_recs[:1] + q_recs[:1])[0]) if base_recs else []
        return None, Reason(f"the sample records carry no {date_field} "
                            f"field, so there is no timeline to cut at (they "
                            f"have: {', '.join(have)})", INPUT)

    if log_fn:
        log_fn(f"  recomputing the drift pair (cutoff {cutoff}, seed {seed})")
    pre = np.array([r[date_field] < cutoff for r in base_recs])
    q_pre = np.array([r[date_field] < cutoff for r in q_recs])
    if pre.all() or (~pre).all():
        return None, Reason(f"the cutoff {cutoff} leaves one side of the "
                            "corpus empty", INPUT)
    if q_pre.all() or (~q_pre).all():
        return None, Reason(f"every query falls on one side of the cutoff "
                            f"{cutoff}", INPUT)
    return drift_pair(base, queries, pre, q_pre, gt10, seed), None


def _compare_drift(published, got):
    """The pair, against its published pair and single tolerance."""
    tol_n, tol_why = _as_number(published.get("tolerance"))
    if tol_n is None:
        return ValueRow("drift", COULDNT_CHECK,
                        f"no usable tolerance for drift ({tol_why})", SPEC)
    rows, unusable = [], None
    for side in ("before", "after"):
        want_n, why = _as_number(published.get(f"value_{side}"))
        have = got.get(f"drift_{side}")
        if want_n is None:
            unusable = Reason(f"value_{side}: {why}", UNPUBLISHED)
            break
        if have is None:
            unusable = Reason(f"drift_{side} was not produced by the "
                              "recomputation", RECOMPUTE)
            break
        rows.append((side, float(have), want_n, abs(float(have) - want_n)))
    if unusable:
        return ValueRow("drift", COULDNT_CHECK, unusable)
    detail = "; ".join(
        f"{s} recomputed {h:.6g}, published {w:.6g}, delta {d:.6g}"
        for s, h, w, d in rows) + f"; tolerance {tol_n:.6g}"
    if all(d <= tol_n for _s, _h, _w, d in rows):
        return ValueRow("drift", VERIFIED, detail)
    return ValueRow("drift", CONTRADICTED, detail)


def _asset_paths(fixture_id, assets_dir, fixture_dir=None, asset=None):
    """Where the vectors and queries are, if they are anywhere.

    `asset` is an explicit folder from `--asset` and wins outright: an
    external runner should never have to adopt this project's directory
    layout to check a fixture. Otherwise the release asset directory first,
    then the fixture directory itself -- arxiv-smoke keeps its vectors beside
    its receipts (6 MB, gitignored rather than published separately), while
    arxiv-150k's are a 460 MB download. Both are legitimately "the asset".
    """
    if asset:
        d = os.path.expanduser(str(asset))
        return (os.path.join(d, "vectors.npy"),
                os.path.join(d, "queries.npy"), d)
    for d in ([os.path.join(assets_dir, fixture_id)]
              + ([fixture_dir] if fixture_dir else [])):
        vec = os.path.join(d, "vectors.npy")
        q = os.path.join(d, "queries.npy")
        if os.path.exists(vec) and os.path.exists(q):
            return vec, q, d
    d = os.path.join(assets_dir, fixture_id)
    return (os.path.join(d, "vectors.npy"), os.path.join(d, "queries.npy"), d)


def _anything_published(published, refs, wanted, ref_rows):
    """True when at least one value the run would compare is a real number.

    Deliberately generous: one filled value anywhere is enough to make the
    recomputation worth doing, because that one value can still be
    contradicted. It is only the all-placeholder case -- a spec whose first
    canonical build has not happened -- that has nothing to learn.
    """
    candidates = [(published.get(f) or {}).get("value") for f in wanted]
    drift = published.get("drift") or {}
    candidates += [drift.get("value_before"), drift.get("value_after")]
    for name, fam in ref_rows:
        entry = refs.get(fam) or {}
        candidates.append(entry.get(name.split(".", 1)[1]))
    return any(_as_number(c)[0] is not None for c in candidates)


REF_ROWS = (("single_node_hnsw.recall_at_10", "single_node_hnsw"),
            ("semantic_sharded.recall_at_10", "semantic_sharded"),
            ("semantic_sharded.storage_amplification", "semantic_sharded"),
            # Task 053. `ref_semantic_sharded` already returns these four
            # alongside the two above, in the one call `verify_values` was
            # already making -- they were published from arxiv-150k's first
            # commit and never covered by this table, so `uncovered` has
            # named them ever since without anyone adding four lines to say
            # why. There was no reason; only the omission.
            ("semantic_sharded.routing_ceiling", "semantic_sharded"),
            ("semantic_sharded.p50_copies", "semantic_sharded"),
            ("semantic_sharded.p95_copies", "semantic_sharded"),
            ("semantic_sharded.p99_copies_per_vector", "semantic_sharded"))


def value_names(spec):
    """The rows `verify_values` produces for this spec, in the order its
    all-couldnt_check path writes them."""
    published = spec.get("characterization") or {}
    refs = spec.get("reference_results") or {}
    names = [f for f in REPRODUCIBLE if f in published]
    names += [name for name, fam in REF_ROWS if fam in refs]
    if "drift" in published:
        names.append("drift")
    return names


def verify_values(fixture_id, fixture_dir, spec, assets_dir,
                  requirements_path="requirements.txt", log_fn=print,
                  asset=None, pins=None):
    """[(name, outcome, detail)] -- one row per value this command recomputes.

    Recomputes with the same functions the product path uses, so a fixture
    number and a user's number are the same computation by construction rather
    than by two implementations agreeing.

    Each row is a `ValueRow`: a 3-tuple, plus the `cause` of a couldnt_check.
    `pins` replaces reading `requirements_path` (task 022).
    """
    rows = []
    published = spec.get("characterization") or {}
    refs = spec.get("reference_results") or {}
    wanted = [f for f in REPRODUCIBLE if f in published]
    ref_rows = list(REF_ROWS)

    def all_couldnt_check(reason, cause):
        for name in value_names(spec):
            rows.append(ValueRow(name, COULDNT_CHECK, reason, cause))
        return rows

    # Nothing published yet -> nothing to verify, and the recomputation is
    # pure cost. A `status: planned` spec carries TO_BE_FILLED throughout, so
    # every row below would be couldnt_check whatever the recomputation found
    # -- and the recomputation is exact k-NN, a fresh k-means over the whole
    # base, and both HNSW reference configurations. On the first canonical
    # build of stackexchange-150k that was 6-8 minutes of pod time spent
    # producing rows that were knowable from the spec before a vector was
    # read, and the run was killed at its cap 21 minutes from the finish.
    #
    # `_as_number` decides what counts as published, so this test and
    # `_compare` cannot disagree about which values are real.
    if not _anything_published(published, refs, wanted, ref_rows):
        log_fn("  every published value is a placeholder - nothing to "
               "recompute against")
        return all_couldnt_check(
            "the spec publishes no value for this field yet, so there is "
            "nothing to reproduce. The recomputation was skipped rather "
            "than run against placeholders.", UNPUBLISHED)

    build_info = {}
    bi_path = os.path.join(fixture_dir, "build_info.json")
    if os.path.exists(bi_path):
        with open(bi_path, encoding="utf-8") as f:
            build_info = json.load(f)

    bad_pins = pin_mismatches(build_info, requirements_path, pins=pins)
    if bad_pins:
        detail = "; ".join(f"{n}: built with {g}, pinned {w}"
                           for n, g, w in bad_pins)
        return all_couldnt_check(
            f"the recorded build used a pin that differs from "
            f"requirements.txt ({detail}), so the published values are not "
            "the pinned environment's values.", BUILD_PINS)

    # The comparison `verified` actually depends on: is *this* process running
    # the pins? Not a short circuit -- the values are still computed and
    # compared below, because the agreement is worth seeing even when it
    # cannot count. `unpinned` downgrades each outcome and says why.
    unpinned = running_pin_mismatches(requirements_path, pinned=pins)

    vec_p, q_p, asset_dir = _asset_paths(fixture_id, assets_dir, fixture_dir,
                                        asset=asset)
    missing = [p for p in (vec_p, q_p) if not os.path.exists(p)]
    if missing:
        return all_couldnt_check(
            f"the release asset is not present: {', '.join(missing)}. It "
            "ships separately from the repository and the package, so no "
            "value was recomputed.", NOT_ATTEMPTED)

    gt_p = os.path.join(fixture_dir, "ground_truth.npy")
    if not os.path.exists(gt_p):
        return all_couldnt_check(f"no ground_truth.npy in {fixture_dir}",
                                 NOT_ATTEMPTED)

    import numpy as np

    from ..characterize import characterize_arrays
    from . import reference

    seed = int(((spec.get("sampling") or {}).get("seed"))
               or ((spec.get("ground_truth") or {}).get("seed")) or 20260908)
    log_fn(f"  loading {vec_p}")
    try:
        base = np.load(vec_p, mmap_mode=None).astype(np.float32)
        queries = np.load(q_p).astype(np.float32)
        gt10 = np.load(gt_p)[:, :10]
    except Exception as e:                            # reported, not raised
        # Nothing below can run without the arrays, so this is the one failure
        # that does take every value with it -- and it still reports them as
        # couldnt_check with the reason rather than raising.
        return all_couldnt_check(recompute_failed(e), None)

    log_fn(f"  recomputing the characterization over {len(base):,} vectors "
           f"(seed {seed})")
    try:
        got = characterize_arrays(base, queries, seed,
                                  log_fn=lambda *_a: None)
    except Exception as e:                            # reported, not raised
        # The five characterization values come from one call, so they fail
        # together -- but drift and the reference results are separate
        # computations over arrays that loaded fine, and they carry on below.
        got = None
        why = recompute_failed(e)
        for field in wanted:
            rows.append(ValueRow(field, COULDNT_CHECK, why))

    if got is not None:
        for field in wanted:
            entry = published[field]
            want, tol = entry.get("value"), entry.get("tolerance")
            have = got.get(field)
            rows.append(_downgrade(_compare(field, have, want, tol), unpinned))

    if "drift" in published:
        sample_path = os.path.join(asset_dir, "sample.jsonl.zst")
        if not os.path.exists(sample_path):
            alt = os.path.join(fixture_dir, "sample.jsonl.zst")
            sample_path = alt if os.path.exists(alt) else sample_path
        if not os.path.exists(sample_path):
            rows.append(ValueRow(
                "drift", COULDNT_CHECK,
                f"sample.jsonl.zst is not present ({sample_path}); it "
                "carries the date column drift is cut on", NOT_ATTEMPTED))
        else:
            cutoff = _published_cutoff(published["drift"])
            try:
                drift, why = recompute_drift(
                    sample_path, base, queries, gt10, seed, cutoff,
                    log_fn=log_fn, date_field=field_map(spec)["date"])
            except Exception as e:                    # reported, not raised
                # This is the one 018d hit: a k-means over the pre-cutoff
                # half, which on a 150k fixture is a 211 MiB allocation.
                drift, why = None, recompute_failed(e)
            if drift is None:
                rows.append(ValueRow("drift", COULDNT_CHECK, why))
            else:
                rows.append(_downgrade(
                    _compare_drift(published["drift"], drift), unpinned))

    # -- reference results, recomputed with the published parameters
    if "single_node_hnsw" in refs:
        p = dict(refs["single_node_hnsw"].get("params") or {})
        log_fn(f"  recomputing single_node_hnsw {p}")
        try:
            # `ref_single_node` returns the recall itself, not a dict --
            # unlike `ref_semantic_sharded`, which has several numbers to
            # return. Asking a float for `.get` would fail after the whole
            # recomputation had already run.
            r = reference.ref_single_node(base, queries, gt10, p)
            rows.append(_downgrade(_compare(
                "single_node_hnsw.recall_at_10", float(r),
                refs["single_node_hnsw"].get("recall_at_10"),
                refs["single_node_hnsw"].get("tolerance")), unpinned))
        except Exception as e:                        # reported, not raised
            rows.append(ValueRow("single_node_hnsw.recall_at_10",
                                 COULDNT_CHECK, recompute_failed(e)))

    if "semantic_sharded" in refs:
        p = dict(refs["semantic_sharded"].get("params") or {})
        log_fn(f"  recomputing semantic_sharded {p}")
        try:
            from ..measures import kmeans
            cents = kmeans(base, int(p.get("centroids", 256)), seed)
            r = reference.ref_semantic_sharded(base, queries, gt10, cents, p)
            ss = refs["semantic_sharded"]
            rows.append(_downgrade(_compare(
                "semantic_sharded.recall_at_10", r.get("recall_at_10"),
                ss.get("recall_at_10"), ss.get("tolerance")), unpinned))
            rows.append(_downgrade(_compare(
                "semantic_sharded.storage_amplification",
                r.get("storage_amplification"),
                ss.get("storage_amplification"),
                ss.get("tolerance")), unpinned))
            # Task 053: the same call above already returns these four: no
            # extra index build, no extra cost. `_compare` reports
            # couldnt_check/UNPUBLISHED on its own if a spec does not
            # publish one of them, so this is safe for a fixture whose
            # semantic_sharded block predates these fields too.
            for field in ("routing_ceiling", "p50_copies", "p95_copies",
                         "p99_copies_per_vector"):
                rows.append(_downgrade(_compare(
                    f"semantic_sharded.{field}", r.get(field),
                    ss.get(field), ss.get("tolerance")), unpinned))
        except Exception as e:                        # reported, not raised
            for name in ("semantic_sharded.recall_at_10",
                         "semantic_sharded.storage_amplification",
                         "semantic_sharded.routing_ceiling",
                         "semantic_sharded.p50_copies",
                         "semantic_sharded.p95_copies",
                         "semantic_sharded.p99_copies_per_vector"):
                rows.append(ValueRow(name, COULDNT_CHECK,
                                     recompute_failed(e)))
    return rows


def recompute_failed(e):
    """Why a value is couldnt_check rather than why the command stopped.

    Task 018e. `MemoryError` is named separately because it is the one failure
    here a reader can act on, and because it says nothing about the fixture:
    the bytes are already confirmed by the digests, which run first. Telling
    someone "recompute failed: MemoryError" invites them to doubt the fixture;
    telling them the machine ran out of room tells them what to do.

    numpy raises `_ArrayMemoryError`, which subclasses `MemoryError`, so the
    isinstance catches the shape 018d actually hit.
    """
    if isinstance(e, MemoryError):
        first = (str(e).strip().splitlines() or [""])[0][:120]
        return Reason(
            "out of memory recomputing this value on this machine (%s). The "
            "digests are checked before any value and are unaffected. Free "
            "memory and re-run to decide this row."
            % (first or "MemoryError"), HOST)
    # Task 022 names the environmental causes: a library this value needs is
    # not installed, or an input could not be read. Anything else is the
    # recomputation failing, and is not blamed on the host.
    cause = HOST if isinstance(e, (ImportError, OSError)) else RECOMPUTE
    return Reason("recompute failed: %s: %s" % (type(e).__name__, e), cause)


def _published_cutoff(drift_entry):
    """The cutoff the spec states, if it states one. Never inferred.

    The definition text carries it in prose ("before 2019-01-01"); a spec that
    names it in a field wins. Falling back to DRIFT_CUTOFF is safe because a
    wrong cutoff shows up as a contradiction, not as a quiet pass.
    """
    if drift_entry.get("cutoff"):
        return str(drift_entry["cutoff"])
    import re
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b",
                  str(drift_entry.get("definition", "")))
    return m.group(1) if m else DRIFT_CUTOFF


def _downgrade(row, unpinned):
    """A comparison made outside the pinned environment cannot say `verified`.

    The numbers stay in the detail: two minor versions away, agreement to
    within a thousandth of tolerance is evidence about the fixture worth
    seeing. It just is not the evidence `verified` is defined to require.

    A *contradiction* is left standing. If the values disagree, they disagree,
    and an unpinned environment is not an excuse for it -- it is at most an
    explanation, and the detail already carries the versions.
    """
    if not unpinned:
        return row
    name, outcome, detail = row
    if outcome != VERIFIED:
        return row
    versions = "; ".join(f"{n}: running {g}, pinned {w}"
                         for n, g, w in unpinned)
    return ValueRow(name, COULDNT_CHECK,
                    f"{detail} -- WITHIN TOLERANCE, but not under the pinned "
                    f"environment ({versions}), so it is not a reproduction",
                    UNPINNED)


def _as_number(value):
    """(number, None) or (None, reason). Never raises on a spec's own text.

    A spec may carry a placeholder where a value will go -- arxiv-smoke has
    `TO_BE_FILLED` throughout, and its header says the first canonical build
    sets them. That is a field nobody has published, not a disagreement.
    """
    if value is None:
        return None, "the spec publishes no value"
    if isinstance(value, bool):
        return None, f"the spec publishes {value!r}, which is not a number"
    if isinstance(value, (int, float)):
        return float(value), None
    text = str(value).strip()
    try:
        return float(text), None
    except ValueError:
        return None, (f"the spec publishes {text!r} rather than a number; "
                      "this value has not been filled in yet")


def _compare(name, have, want, tol):
    """One value against its own published tolerance. Never a wider one."""
    want_n, why = _as_number(want)
    if want_n is None:
        return ValueRow(name, COULDNT_CHECK, why, UNPUBLISHED)
    if have is None:
        return ValueRow(name, COULDNT_CHECK,
                        "not produced by the recomputation", RECOMPUTE)
    if isinstance(have, str):
        return ValueRow(name, COULDNT_CHECK, have, RECOMPUTE)
    tol_n, tol_why = _as_number(tol)
    if tol_n is None:
        return ValueRow(name, COULDNT_CHECK,
                        "the spec publishes no usable tolerance for this "
                        f"value, so 'reproduces' has no defined meaning "
                        f"({tol_why})", SPEC)
    delta = abs(float(have) - want_n)
    detail = (f"recomputed {float(have):.6g}, published {want_n:.6g}, "
              f"delta {delta:.6g}, tolerance {tol_n:.6g}")
    if delta <= tol_n:
        return ValueRow(name, VERIFIED, detail)
    return ValueRow(name, CONTRADICTED, detail)


# --------------------------------------------------------------------------
# task 022: from anywhere
# --------------------------------------------------------------------------
# `oneground fixture verify arxiv-150k`, from a bare `pip install` outside any
# checkout, answered `error: no such fixture directory: fixtures\arxiv-150k`.
# The command was built for someone standing inside the repository. It now
# finds the fixture wherever it is, names every precondition the run is
# missing in one place, and summarises only what its rows support.

def _norm(name):
    """pip's normalisation: `scikit_learn` and `scikit-learn` are one name."""
    return str(name).strip().lower().replace("_", "-")


def _and(items):
    items = [str(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _count(n, one, many):
    return f"{n} {one if n == 1 else many}"


def release_url():
    """The release page of the installed version, where its assets are."""
    from .. import __display_version__
    return f"{REPOSITORY}/releases/tag/v{__display_version__}"


def fixture_search_path(fixtures=None):
    """[(label, directory)] in the order a fixture is looked for.

    An explicit `--fixtures` is the only place looked. A reader who pointed
    at a directory and was quietly given the package's copy instead would be
    reading a result about bytes they did not choose.
    """
    if fixtures:
        return [("--fixtures",
                 os.path.abspath(os.path.expanduser(str(fixtures))))]
    return [("the current directory", os.path.abspath("fixtures")),
            ("the installed package", PACKAGE_FIXTURES)]


def find_fixture(fixture_id, fixtures=None):
    """(found, looked).

    `found` is `{"label", "root", "dir", "spec"}` for the first location that
    holds both `<id>.fixture.yaml` and `<id>/MANIFEST.sha256`, or None.
    `looked` is `[(label, root, [missing paths])]` for each location that did
    not.
    """
    looked = []
    for label, root in fixture_search_path(fixtures):
        d = os.path.join(root, fixture_id)
        spec = os.path.join(root, fixture_id + SPEC_SUFFIX)
        missing = [p for p in (spec, os.path.join(d, MANIFEST_NAME))
                   if not os.path.isfile(p)]
        if not missing:
            return ({"label": label, "root": root, "dir": d, "spec": spec},
                    looked)
        looked.append((label, root, missing))
    return None, looked


def known_fixtures(fixtures=None):
    """The fixture ids that would be found, from every location looked."""
    ids = set()
    for _label, root in fixture_search_path(fixtures):
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            fid = name[:-len(SPEC_SUFFIX)]
            if (name.endswith(SPEC_SUFFIX)
                    and os.path.isfile(os.path.join(root, fid,
                                                    MANIFEST_NAME))):
                ids.add(fid)
    return sorted(ids)


def distribution_pins():
    """{package: version} for the exact, unconditional pins the installed
    `oneground` distribution declares -- what `pip install oneground==<v>`
    installs. {} when there is no installed distribution to read."""
    try:
        from importlib import metadata
        reqs = metadata.requires("oneground") or []
    except Exception:                                     # not installed
        return {}
    out = {}
    for r in reqs:
        spec, _, marker = r.partition(";")
        if "extra" in marker or "==" not in spec:
            continue
        name, _, version = spec.partition("==")
        out[_norm(name)] = version.strip()
    return out


def resolve_pins(requirements=None):
    """(pins, source, looked).

    `--requirements <file>` if given, and only that; otherwise
    `requirements.txt` in the current directory; otherwise the pins the
    installed distribution declares.

    Before task 022 a missing requirements.txt read as an empty pin set, and
    an empty set has no mismatches: outside a checkout, an environment that
    nothing had been compared against was treated as pinned.
    """
    if requirements:
        path = os.path.abspath(os.path.expanduser(str(requirements)))
        if os.path.isfile(path):
            return read_requirements_pins(path), path, []
        return {}, None, [path]
    cwd = os.path.abspath("requirements.txt")
    if os.path.isfile(cwd):
        return read_requirements_pins(cwd), cwd, []
    pins = distribution_pins()
    if pins:
        from .. import __version__
        return pins, f"the installed oneground {__version__}", [cwd]
    return {}, None, [cwd, "the installed oneground distribution"]


_NOT_VALUES = {"params", "tolerance", "kind", "definition", "estimator",
               "note", "notes"}


def published_value_names(spec):
    """Every value the spec publishes as a number.

    `characterization.<field>` entries with a numeric value, the drift pair,
    and every numeric field of a reference result. A placeholder
    (`TO_BE_FILLED`) is not a published value. This is the set a sentence
    about "every published value" quantifies over -- which is not the set this
    command recomputes, and the summary says so when they differ.
    """
    names = []
    for field, entry in (spec.get("characterization") or {}).items():
        if not isinstance(entry, dict):
            continue
        if field == "drift":
            if any(_as_number(entry.get(k))[0] is not None
                   for k in ("value_before", "value_after")):
                names.append("drift")
        elif _as_number(entry.get("value"))[0] is not None:
            names.append(field)
    for fam, entry in (spec.get("reference_results") or {}).items():
        if not isinstance(entry, dict):
            continue
        for key, v in entry.items():
            if key in _NOT_VALUES or isinstance(v, (dict, list, bool)):
                continue
            if _as_number(v)[0] is not None:
                names.append(f"{fam}.{key}")
    return names


def _asset_members_in(d):
    """Which of the release asset's members are files directly in `d`."""
    return [m for m in ASSET_MEMBERS if os.path.isfile(os.path.join(d, m))]


def _describe_dir(d, limit=8):
    """What is actually at `d`, for a reader told their path is wrong."""
    if not os.path.exists(d):
        return "it does not exist"
    if not os.path.isdir(d):
        return "it is not a directory"
    names = sorted(os.listdir(d))
    if not names:
        return "it is empty"
    shown = [n + ("/" if os.path.isdir(os.path.join(d, n)) else "")
             for n in names[:limit]]
    more = f" and {len(names) - limit} more" if len(names) > limit else ""
    return "it holds " + ", ".join(shown) + more


def _nested_asset(d, fixture_id):
    """The folder under `d` that does hold the asset, one level down.

    Task 022, from runs on 0.1.0rc1: the tarball's members are
    `fixtures/<id>/...`, so the documented `--asset ./arxiv-150k` and a path to
    the extraction directory itself both point one level short.
    """
    for cand in (os.path.join(d, "fixtures", fixture_id),
                 os.path.join(d, fixture_id)):
        if _asset_members_in(cand):
            return cand
    return None


def _extracted_asset_at(fixture_id, looked):
    """Where a release tarball was extracted in place of a fixture.

    `tar -xzf arxiv-150k-v1.tgz` in the directory a fixture is looked for
    creates `fixtures/arxiv-150k/` holding the vectors and no manifest. 0.1.0rc1
    took that for the fixture and stopped with `error: no MANIFEST.sha256 in
    fixtures\\arxiv-150k`: what a reader who extracted in the wrong place hits.
    """
    out = []
    for _label, root, _missing in looked:
        d = os.path.join(root, fixture_id)
        if (os.path.isdir(d) and _asset_members_in(d)
                and not os.path.isfile(os.path.join(d, MANIFEST_NAME))):
            out.append(d)
    return out


def _needs_values(spec):
    published = spec.get("characterization") or {}
    refs = spec.get("reference_results") or {}
    wanted = [f for f in REPRODUCIBLE if f in published]
    return _anything_published(published, refs, wanted, list(REF_ROWS))


def check_preconditions(fixture_id, found, looked, spec, pins, pin_source,
                        pin_looked, unpinned, allow_unpinned, assets_dir,
                        asset=None, fixtures=None, versions=None,
                        in_venv=None):
    """The fixture, the pinned environment and the release asset, in order.

    Each is `{"key", "state", "met", "blocks_values", "because", "lines"}`.
    `met` is False when the run could not check everything because of it, and
    None when it cannot be known. `lines` say what it is and how to satisfy
    it. All three are always worked out, so a run that is missing more than
    one says so once.
    """
    needs = _needs_values(spec) if found else None
    pre = []
    extracted = _extracted_asset_at(fixture_id, looked)

    def extracted_lines():
        return [f"{os.path.normpath(d)} holds {_and(_asset_members_in(d))} "
                f"and no {MANIFEST_NAME}: that is the release asset extracted "
                f"there, not the fixture. Pass --asset {os.path.normpath(d)}"
                for d in extracted]

    # ---- the fixture
    if found:
        where = f"{found['dir']}  ({found['label']})"
        lines = [where]
        if looked:
            lines.append("not in " + _and(f"{root} ({label})"
                                          for label, root, _m in looked))
        lines += extracted_lines()
        gt = os.path.join(found["dir"], "ground_truth.npy")
        if needs and not os.path.isfile(gt):
            lines.append(f"but ground_truth.npy is not in it, and the values "
                         "are scored against it")
            pre.append({"key": "fixture", "state": "MISSING", "met": False,
                        "blocks_values": True, "lines": lines,
                        "because": "the fixture's ground_truth.npy is "
                                   "missing"})
        else:
            pre.append({"key": "fixture", "state": "found", "met": True,
                        "blocks_values": False, "lines": lines,
                        "because": ""})
    else:
        lines = [f"no {fixture_id}{SPEC_SUFFIX} with a {fixture_id}/"
                 f"{MANIFEST_NAME} beside it, looked in:"]
        lines += [f"  {root}  ({label})" for label, root, _m in looked]
        lines += extracted_lines()
        ids = known_fixtures(fixtures)
        lines.append("fixtures found there: " + _and(ids) if ids
                     else "no fixture was found in any of them")
        lines.append("pass one of those ids, or --fixtures <dir> for a "
                     f"directory holding {fixture_id}{SPEC_SUFFIX} and "
                     f"{fixture_id}/")
        pre.append({"key": "fixture", "state": "MISSING", "met": False,
                    "blocks_values": True, "lines": lines,
                    "because": "the fixture was not found"})

    # ---- the pinned environment
    from .. import __version__
    running = running_versions() if versions is None else versions
    names = [n for n in PINNED if _norm(n) in pins]
    install = (f"a fresh virtual environment with `pip install "
               f"oneground=={__version__}` installs the pinned set")
    not_needed = ("nothing is recomputed for this fixture, so this does not "
                  "stop the run")
    # Task 022: a virtual environment is a stated requirement. Installing the
    # pins into a system Python replaces the versions of whatever it already
    # has. This says so; it does not refuse -- whether it should is an open
    # question recorded for after the release.
    if in_venv is None:
        from .. import environment as envmod
        in_venv = envmod.in_venv()
    venv_lines = (["in a virtual environment"] if in_venv else
                  ["SYSTEM INTERPRETER: a virtual environment is required.",
                   "Installing the pins into the system Python replaces the "
                   "versions of any of these packages it already has;",
                   "create one with `python -m venv .venv` and install "
                   "oneground into it"])
    if not names:
        lines = ["no pinned set to compare this environment against: "
                 "looked in " + _and(pin_looked),
                 "pass --requirements <file>; or " + install]
        met = True if needs is False else bool(allow_unpinned)
        lines += venv_lines
        if allow_unpinned:
            lines.append("--allow-unpinned given: values are recomputed, and "
                         "one that agrees is reported couldn't-check, not "
                         "verified")
        elif needs is False:
            lines.append(not_needed)
        pre.append({"key": "environment", "state": "MISSING", "met": met,
                    "blocks_values": not met,
                    "because": "no pinned set was found to compare this "
                               "environment against",
                    "lines": lines})
    elif unpinned:
        lines = [f"{n:<14} running {g:<10} pinned {w}"
                 for n, g, w in unpinned]
        lines.append(f"(pins from {pin_source})")
        lines += venv_lines
        lines.append(install)
        if allow_unpinned:
            lines.append("--allow-unpinned given: values are recomputed, and "
                         "one that agrees is reported couldn't-check, not "
                         "verified")
            met = True
        else:
            lines.append("or pass --allow-unpinned to recompute anyway; a "
                         "value that agrees is then couldn't-check, not "
                         "verified")
            met = needs is False
            if needs is False:
                lines.append(not_needed)
        pre.append({"key": "environment", "state": "UNPINNED", "met": met,
                    "blocks_values": not met,
                    "because": "this environment is not running the pinned "
                               "versions",
                    "lines": lines})
    else:
        have = ", ".join(f"{_norm(n)} {running.get(n, 'not installed')}"
                         for n in names)
        pre.append({"key": "environment", "state": "pinned", "met": True,
                    "blocks_values": False, "because": "",
                    "lines": [have, f"(pins from {pin_source})"]
                    + venv_lines})

    # ---- the release asset
    def release_lines():
        if fixture_id in RELEASE_ASSETS:
            name, size = RELEASE_ASSETS[fixture_id]
            return [f"release asset {name}, {size:,} bytes, at",
                    release_url(),
                    f"it extracts to fixtures/{fixture_id}/ wherever you "
                    f"extract it: pass --asset <that folder>"]
        return [f"no release asset is published for {fixture_id}; pass "
                "--asset <a folder holding " + _and(ASSET_MEMBERS) + ">"]

    # Task 022: passing --asset asserts the asset is there. A folder holding
    # none of it used to report every value couldn't-check and exit 0 -- the
    # tool saying it checked when it did not. It is a missing precondition
    # whether or not this fixture has values to recompute.
    if asset:
        given = os.path.expanduser(str(asset))
        if not _asset_members_in(given):
            lines = [f"--asset {given} holds none of {_and(ASSET_MEMBERS)}; "
                     f"{_describe_dir(given)}"]
            nested = _nested_asset(given, fixture_id)
            if nested:
                nested = os.path.normpath(nested)
                lines.append(f"they are in {nested}: pass --asset {nested}")
            lines += release_lines()
            # Exit 2 either way; but a spec with nothing published had no
            # value to recompute, and its rows must still say so rather than
            # "not recomputed because of --asset".
            pre.append({"key": "asset", "state": "MISSING", "met": False,
                        "blocks_values": needs is not False,
                        "because": "--asset names a folder that holds none of "
                                   "the release asset",
                        "lines": lines})
            return pre

    if needs is False:
        pre.append({"key": "asset", "state": "not needed", "met": True,
                    "blocks_values": False, "because": "",
                    "lines": ["the spec publishes no values yet, so no asset "
                              "is read"]})
        return pre
    if found is None and fixture_id not in RELEASE_ASSETS:
        pre.append({"key": "asset", "state": "unknown", "met": None,
                    "blocks_values": False, "because": "",
                    "lines": ["without the fixture's spec it is not known "
                              "what its values need"]})
        return pre

    fdir = found["dir"] if found else None
    vec_p, q_p, asset_dir = _asset_paths(fixture_id, assets_dir, fdir,
                                        asset=asset)
    drift = (spec.get("characterization") or {}).get("drift") or {}
    wants_sample = (found is None) or any(
        _as_number(drift.get(k))[0] is not None
        for k in ("value_before", "value_after"))
    missing = [os.path.basename(p) for p in (vec_p, q_p)
               if not os.path.isfile(p)]
    if wants_sample and not any(
            os.path.isfile(os.path.join(d, "sample.jsonl.zst"))
            for d in [asset_dir] + ([fdir] if fdir else [])):
        missing.append("sample.jsonl.zst")
    if not missing:
        pre.append({"key": "asset", "state": "present", "met": True,
                    "blocks_values": False, "because": "",
                    "lines": [asset_dir]})
        return pre

    if asset:
        given = os.path.expanduser(str(asset))
        lines = [f"{_and(missing)} not found in {given}  (--asset); "
                 f"{_describe_dir(given)}"]
    else:
        places = [os.path.join(assets_dir, fixture_id)] + ([fdir] if fdir
                                                          else [])
        lines = [f"{_and(missing)} not found in " + " or ".join(places)]
        lines += [f"an extracted asset is at {os.path.normpath(d)}: pass "
                  f"--asset {os.path.normpath(d)}" for d in extracted]
    lines += release_lines()
    blocks = any(m in missing for m in ("vectors.npy", "queries.npy"))
    pre.append({"key": "asset", "state": "MISSING", "met": False,
                "blocks_values": blocks,
                "because": ("the release asset is not present" if blocks
                            else "sample.jsonl.zst is not present"),
                "lines": lines})
    return pre


def precondition_lines(pre):
    out = ["preconditions"]
    for p in pre:
        first, *rest = p["lines"] or [""]
        out.append(f"  {p['key']:<12} {p['state']:<10} {first}")
        out += [f"  {'':<12} {'':<10} {line}" for line in rest]
    return out


def _wrap(sentence, indent=9, width=79):
    import textwrap
    return textwrap.wrap(sentence, width=width,
                         initial_indent=" " * indent,
                         subsequent_indent=" " * indent)


# The order the summary speaks about couldnt_check values in.
CAUSE_ORDER = (NOT_ATTEMPTED, HOST, RECOMPUTE, INPUT, UNPINNED, BUILD_PINS,
               SPEC, UNPUBLISHED, None)


def summary_sentences(results, value_rows, published, pre):
    """The closing sentences, each reconstructible from the rows it names.

    Task 022, applying task 019's rule by hand: a sentence names the rows it
    is about, and a universal ("All", "Every", "No value") is written only
    when it holds for every row it quantifies over. "Every value reproduced",
    "n values could not be recomputed on this host" and "the asset is not
    present, so no value was recomputed" are different sentences, and are
    never collapsed into one.
    """
    out = []

    # ---- digests
    d_ver = [r for r in results if r[2] == VERIFIED]
    d_con = [r for r in results if r[2] == CONTRADICTED]
    d_cc = [r for r in results if r[2] == COULDNT_CHECK]
    if results and len(d_ver) == len(results):
        out.append(f"All {len(results)} listed files are present and match "
                   "the manifest.")
    if d_con:
        out.append(f"{_count(len(d_con), 'listed file', 'listed files')} "
                   f"contradicted the manifest: "
                   f"{_and(r[0] for r in d_con)}.")
    if d_cc:
        out.append(f"{_count(len(d_cc), 'listed file is', 'listed files are')}"
                   f" not present here, so "
                   f"{'its' if len(d_cc) == 1 else 'their'} bytes were not "
                   f"checked: {_and(r[0] for r in d_cc)}.")

    # ---- values
    n = len(value_rows)
    v_ver = [r for r in value_rows if r[1] == VERIFIED]
    v_con = [r for r in value_rows if r[1] == CONTRADICTED]
    recomputed = {r[0] for r in value_rows}
    uncovered = [p for p in published if p not in recomputed]
    if not value_rows:
        out.append("The spec lists no value this command recomputes.")
    if v_con:
        out.append(f"{_count(len(v_con), 'value', 'values')} contradicted "
                   f"{'its' if len(v_con) == 1 else 'their'} published "
                   f"value: {_and(r[0] for r in v_con)}.")
    if v_ver:
        if len(v_ver) == n and not uncovered:
            out.append(f"Every published value reproduced ({n} of {n}). "
                       "This fixture's status may be set to `verified`.")
        elif len(v_ver) == n:
            out.append(f"Every value this command recomputes reproduced "
                       f"({n} of {n}).")
        else:
            out.append(f"{_count(len(v_ver), 'value', 'values')} "
                       f"reproduced: {_and(r[0] for r in v_ver)}.")

    because = _and(p["because"] for p in pre if p["met"] is False
                   and p["because"])
    for cause in CAUSE_ORDER:
        group = [r for r in value_rows if r[1] == COULDNT_CHECK
                 and getattr(r, "cause", None) == cause]
        if not group:
            continue
        k = len(group)
        vals = _count(k, "value", "values")
        names = _and(r[0] for r in group)
        were = "was" if k == 1 else "were"
        if cause == NOT_ATTEMPTED:
            why = because or "a precondition is missing"
            if k == n:
                out.append(f"No value was recomputed, because {why}.")
            else:
                out.append(f"{vals} {were} not recomputed, because {why}: "
                           f"{names}.")
        elif cause == HOST:
            out.append(f"{vals} could not be recomputed on this host; the "
                       f"rows above give the reason: {names}.")
        elif cause == RECOMPUTE:
            out.append(f"{vals} {were} not produced by the recomputation; "
                       f"the rows above give the reason: {names}.")
        elif cause == INPUT:
            out.append(f"{vals} could not be recomputed, because the asset's "
                       f"files do not belong together: {names}.")
        elif cause == UNPINNED:
            out.append(f"{vals} landed within tolerance outside the pinned "
                       f"environment, so {'it is' if k == 1 else 'they are'}"
                       f" not counted as reproduced: {names}.")
        elif cause == BUILD_PINS:
            out.append(f"{vals} cannot be reproduced, because the recorded "
                       f"build used pins that differ from the pinned set: "
                       f"{names}.")
        elif cause == SPEC:
            out.append(f"{vals} {'has' if k == 1 else 'have'} no usable "
                       f"tolerance in the spec: {names}.")
        elif cause == UNPUBLISHED:
            if k == n:
                out.append("No value is published in the spec yet, so there "
                           f"was nothing to reproduce ({k} placeholders).")
            else:
                out.append(f"{vals} {'is' if k == 1 else 'are'} not "
                           f"published in the spec yet: {names}.")
        else:
            out.append(f"{vals} could not be checked: {names}.")

    if uncovered:
        out.append(f"{_count(len(uncovered), 'published value is', 'published values are')}"
                   f" not recomputed by this command: {_and(uncovered)}.")

    stopped = [r for r in value_rows if r[1] == COULDNT_CHECK
               and getattr(r, "cause", None) in (NOT_ATTEMPTED, HOST,
                                                 RECOMPUTE, INPUT)]
    if d_ver and stopped:
        out.append(f"The digests were checked before any value, so the "
                   f"{_count(len(d_ver), 'file', 'files')} that verified "
                   f"{'is' if len(d_ver) == 1 else 'are'} the published "
                   "bytes whatever happened to the values.")
    return out


def cmd_verify(args):
    # `fixture verify` decides whether a fixture may be called verified, so it
    # is guarded like anything else that writes a canonical claim. Task 022:
    # the guard no longer stops the command before it starts. The digests
    # depend on nothing but the bytes, so they are always checked; an unpinned
    # environment stops the values, and is named beside everything else that
    # is missing rather than instead of it.
    from .. import environment as envmod
    envmod.GUARDED_COMMANDS.add("oneground fixture verify")

    fid = args.id
    fixtures = getattr(args, "fixtures_dir", None)
    allow_unpinned = getattr(args, "allow_unpinned", False)
    assets_dir = getattr(args, "assets_dir", None) or DEFAULT_ASSETS
    asset = getattr(args, "asset", None)
    log_fn = (print if getattr(args, "verbose", False)
              else (lambda *_a: None))

    print(envmod.describe())
    found, looked = find_fixture(fid, fixtures)
    spec = {}
    if found:
        with open(found["spec"], encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
    pins, pin_source, pin_looked = resolve_pins(
        getattr(args, "requirements", None))
    pins_known = any(_norm(n) in pins for n in PINNED)
    unpinned = running_pin_mismatches(pinned=pins) if pins_known else []
    pre = check_preconditions(fid, found, looked, spec, pins, pin_source,
                              pin_looked, unpinned, allow_unpinned,
                              assets_dir, asset=asset, fixtures=fixtures)

    print(f"fixture: {fid}")
    results, unlisted = [], []
    if found:
        digest_dir = (os.path.expanduser(str(asset)) if asset
                      else os.path.join(assets_dir, fid))
        results, unlisted = verify_digests(found["dir"], digest_dir)
        print(f"directory: {found['dir']}")
        print(f"manifest: {MANIFEST_NAME} ({len(results)} files listed)")
    print()
    for line in precondition_lines(pre):
        print(line)
    print()

    if not found:
        print(f"summary: nothing was checked, because no fixture named {fid} "
              "was found (see preconditions above).")
        return 2

    print("digests")
    width = max(len(n) for n, _, _, _ in results) if results else 0
    for name, k, outcome, detail in results:
        print(f"  {outcome:<13} {k:<8} {name:<{width}}  {detail}")
    print()
    if unlisted:
        print(f"present but not listed in the manifest: {', '.join(unlisted)}")
        print()

    print("values")
    if any(p["blocks_values"] for p in pre):
        because = _and(p["because"] for p in pre if p["blocks_values"])
        value_rows = [ValueRow(name, COULDNT_CHECK,
                               f"not recomputed, because {because}",
                               NOT_ATTEMPTED)
                      for name in value_names(spec)]
    else:
        value_rows = verify_values(fid, found["dir"], spec, assets_dir,
                                   pin_source or "requirements.txt",
                                   log_fn=log_fn, asset=asset, pins=pins)
        if not pins_known:
            # --allow-unpinned with no pinned set at all: nothing was compared,
            # so nothing that agrees can be called a reproduction.
            value_rows = [_downgrade(r, [("the pinned set", "unknown",
                                          "not found")])
                          for r in value_rows]
    vw = max((len(r[0]) for r in value_rows), default=0)
    for name, outcome, detail in value_rows:
        print(f"  {outcome:<13} {name:<{vw}}  {detail}")
    print()

    counts = {o: sum(1 for r in results if r[2] == o)
              for o in (VERIFIED, CONTRADICTED, COULDNT_CHECK)}
    vcounts = {o: sum(1 for r in value_rows if r[1] == o)
               for o in (VERIFIED, CONTRADICTED, COULDNT_CHECK)}
    # The parenthetical breaks down the number it follows.
    #
    # It used to break down every listed file by kind, printed straight after
    # the couldn't-check count, so a reader saw `7 couldnt_check (6 receipt, 5
    # declared)` -- arithmetic that does not add up, on the one command an
    # outsider is told to run. It is the couldn't-checks' own split now, and
    # it is omitted when there are none rather than printed as two zeroes.
    cc_declared = sum(1 for _, k, o, _ in results
                      if o == COULDNT_CHECK and k == DECLARED)
    cc_receipt = counts[COULDNT_CHECK] - cc_declared
    split = (f" ({cc_receipt} receipt, {cc_declared} declared)"
             if counts[COULDNT_CHECK] else "")
    print(f"summary: digests {counts[VERIFIED]} verified, "
          f"{counts[CONTRADICTED]} contradicted, {counts[COULDNT_CHECK]} "
          f"couldnt_check{split}")
    print(f"         values  {vcounts[VERIFIED]} verified, "
          f"{vcounts[CONTRADICTED]} contradicted, "
          f"{vcounts[COULDNT_CHECK]} couldnt_check")
    sentences = summary_sentences(results, value_rows,
                                  published_value_names(spec), pre)
    if sentences:
        print()
        for s in sentences:
            for line in _wrap(s):
                print(line)

    if counts[CONTRADICTED] or vcounts[CONTRADICTED]:
        return 1
    if any(p["met"] is False for p in pre):
        return 2
    if getattr(args, "strict", False) and (counts[COULDNT_CHECK]
                                           or vcounts[COULDNT_CHECK]):
        return 2
    return 0


def add_verify_arguments(subparsers):
    """Define `verify` on a subparser group, and return it.

    The single definition of this command's flags. Both entry points call it
    -- `oneground fixture verify` through oneground/cli.py, and
    `python -m oneground.fixture.verify` through `build_parser` below -- so
    the two can no longer drift apart. They had: `--assets-dir` and
    `--verbose` existed on one and not the other.
    """
    from .. import environment as envmod

    v = subparsers.add_parser(
        "verify", help="check a built fixture against its MANIFEST.sha256")
    v.add_argument("id", help="fixture id, e.g. arxiv-smoke")
    v.add_argument("--fixtures", "--fixtures-dir", dest="fixtures_dir",
                   default=None, metavar="DIR",
                   help="the directory holding <id>.fixture.yaml and <id>/, "
                        "and the only place looked. Default: fixtures/ in "
                        "the current directory, then the copy the installed "
                        "package carries")
    v.add_argument("--assets-dir", default=DEFAULT_ASSETS,
                   help="where release assets are extracted, one folder per "
                        "fixture id (default: ~/oneground-assets)")
    v.add_argument("--asset", default=None, metavar="FOLDER",
                   help="the extracted asset folder for THIS fixture, "
                        "overriding --assets-dir. Use this rather than "
                        "adopting a directory layout: "
                        "--asset ./arxiv-150k")
    v.add_argument("--requirements", default=None,
                   help="the pinned requirements the values are judged "
                        "under. Default: requirements.txt in the current "
                        "directory, then the installed package's own pins")
    v.add_argument("--verbose", action="store_true",
                   help="print each recomputation as it runs")
    envmod.add_argument(v)
    v.add_argument("--strict", action="store_true",
                   help="exit 2 if any digest or value is couldnt_check, "
                        "instead of only when a precondition is missing; the "
                        "report is unchanged")
    v.set_defaults(func=cmd_verify)
    return v


def build_parser():
    ap = argparse.ArgumentParser(prog="oneground")
    sub = ap.add_subparsers(dest="group", required=True)
    fx = sub.add_parser("fixture", help="fixture operations")
    fxs = fx.add_subparsers(dest="action", required=True)
    add_verify_arguments(fxs)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
