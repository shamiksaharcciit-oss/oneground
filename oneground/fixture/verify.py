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

**The scope is the release asset, not "vectors and queries".** `drift` needs
`update_date` per record, which lives in `sample.jsonl.zst` -- part of the same
published asset -- so it is recomputed from there rather than reported
unreachable. A value that is checkable from the published artifacts is a value
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

Exit codes (they describe both halves)
    0   nothing contradicted. Every file that is present verified; any the
        manifest lists but that are absent were reported couldnt_check, which
        does not change the exit code. A contributor who cloned the repo
        without the large release artifacts should not see a failure — their
        fixture is not broken, it is incomplete, and the report says which.
    1   at least one file contradicted
    2   --strict only: nothing contradicted, but at least one file could not
        be checked. For a caller that needs the whole fixture present — a
        release gate, say — rather than the default clone-friendly reading.

couldnt_check never becomes verified in the report; it is only the default
exit code that treats absence as non-fatal, and the summary line always states
how many files could not be checked. --strict changes what the exit code
means, never what the report says.

--strict counts both halves, so a caller that has the release asset and wants
the whole fixture accounted for gets exit 2 when anything could not be checked.
A fresh clone without the asset should not use it.

Usage
-----
    oneground fixture verify arxiv-smoke
    oneground fixture verify arxiv-smoke --fixtures-dir fixtures

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

# Where the release assets are extracted. Declared, and overridable: the large
# artifacts ship separately from the repository, so a fresh clone has none of
# them and reports couldnt_check rather than failing.
DEFAULT_ASSETS = os.path.join(os.path.expanduser("~"), "oneground-assets")

VERIFIED = "verified"
CONTRADICTED = "contradicted"
COULDNT_CHECK = "couldnt_check"

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
DECLARED_GLOBS = ("ground_view_*.parquet",)


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
            results.append((name, k, COULDNT_CHECK,
                            "artifact not present (release asset, or not "
                            "built)" + hint))
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

def pin_mismatches(build_info, requirements_path="requirements.txt"):
    """[(package, built_with, pinned)] for pins that decide the numbers."""
    pinned = read_requirements_pins(requirements_path)
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
                    cutoff=DRIFT_CUTOFF, log_fn=None):
    """The build's own drift call, with its inputs read back from the asset.

    Returns (result_dict, None) or (None, reason).
    """
    import numpy as np

    from ..measures import drift_pair

    if log_fn:
        log_fn(f"  reading update_date from {sample_path}")
    try:
        base_recs, q_recs = read_sample_records(sample_path)
    except ImportError:
        return None, ("zstandard is not installed, so sample.jsonl.zst cannot "
                      "be read")
    except (OSError, ValueError) as e:
        return None, f"could not read {sample_path}: {type(e).__name__}: {e}"

    # Asserted, not trusted. A file whose base rows do not match vectors.npy
    # is not the file that produced those vectors, and zipping two different
    # corpora together would give a number that looks like a reproduction.
    if len(base_recs) != len(base):
        return None, (f"{sample_path} holds {len(base_recs):,} base records "
                      f"but vectors.npy holds {len(base):,}; these are not "
                      "the same corpus")
    if len(q_recs) != len(queries):
        return None, (f"{sample_path} holds {len(q_recs):,} query records but "
                      f"queries.npy holds {len(queries):,}; these are not the "
                      "same query set")
    missing = [r for r in (base_recs[:1] + q_recs[:1])
               if "update_date" not in r]
    if missing:
        return None, ("the sample records carry no update_date field, so "
                      "there is no timeline to cut at")

    if log_fn:
        log_fn(f"  recomputing the drift pair (cutoff {cutoff}, seed {seed})")
    pre = np.array([r["update_date"] < cutoff for r in base_recs])
    q_pre = np.array([r["update_date"] < cutoff for r in q_recs])
    if pre.all() or (~pre).all():
        return None, (f"the cutoff {cutoff} leaves one side of the corpus "
                      "empty")
    if q_pre.all() or (~q_pre).all():
        return None, f"every query falls on one side of the cutoff {cutoff}"
    return drift_pair(base, queries, pre, q_pre, gt10, seed), None


def _compare_drift(published, got):
    """The pair, against its published pair and single tolerance."""
    tol_n, tol_why = _as_number(published.get("tolerance"))
    if tol_n is None:
        return ("drift", COULDNT_CHECK,
                f"no usable tolerance for drift ({tol_why})")
    rows, unusable = [], None
    for side in ("before", "after"):
        want_n, why = _as_number(published.get(f"value_{side}"))
        have = got.get(f"drift_{side}")
        if want_n is None:
            unusable = f"value_{side}: {why}"
            break
        if have is None:
            unusable = f"drift_{side} was not produced by the recomputation"
            break
        rows.append((side, float(have), want_n, abs(float(have) - want_n)))
    if unusable:
        return ("drift", COULDNT_CHECK, unusable)
    detail = "; ".join(
        f"{s} recomputed {h:.6g}, published {w:.6g}, delta {d:.6g}"
        for s, h, w, d in rows) + f"; tolerance {tol_n:.6g}"
    if all(d <= tol_n for _s, _h, _w, d in rows):
        return ("drift", VERIFIED, detail)
    return ("drift", CONTRADICTED, detail)


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


def verify_values(fixture_id, fixture_dir, spec, assets_dir,
                  requirements_path="requirements.txt", log_fn=print,
                  asset=None):
    """[(name, outcome, detail)] -- one row per published value.

    Recomputes with the same functions the product path uses, so a fixture
    number and a user's number are the same computation by construction rather
    than by two implementations agreeing.
    """
    rows = []
    published = spec.get("characterization") or {}
    refs = spec.get("reference_results") or {}
    wanted = [f for f in REPRODUCIBLE if f in published]
    ref_rows = [("single_node_hnsw.recall_at_10", "single_node_hnsw"),
                ("semantic_sharded.recall_at_10", "semantic_sharded"),
                ("semantic_sharded.storage_amplification", "semantic_sharded")]

    def all_couldnt_check(reason):
        for f in wanted:
            rows.append((f, COULDNT_CHECK, reason))
        for name, fam in ref_rows:
            if fam in refs:
                rows.append((name, COULDNT_CHECK, reason))
        if "drift" in published:
            rows.append(("drift", COULDNT_CHECK, reason))
        return rows

    build_info = {}
    bi_path = os.path.join(fixture_dir, "build_info.json")
    if os.path.exists(bi_path):
        with open(bi_path, encoding="utf-8") as f:
            build_info = json.load(f)

    bad_pins = pin_mismatches(build_info, requirements_path)
    if bad_pins:
        detail = "; ".join(f"{n}: built with {g}, pinned {w}"
                           for n, g, w in bad_pins)
        return all_couldnt_check(
            f"the recorded build used a pin that differs from "
            f"requirements.txt ({detail}), so the published values are not "
            "the pinned environment's values.")

    # The comparison `verified` actually depends on: is *this* process running
    # the pins? Not a short circuit -- the values are still computed and
    # compared below, because the agreement is worth seeing even when it
    # cannot count. `unpinned` downgrades each outcome and says why.
    unpinned = running_pin_mismatches(requirements_path)

    vec_p, q_p, asset_dir = _asset_paths(fixture_id, assets_dir, fixture_dir,
                                        asset=asset)
    missing = [p for p in (vec_p, q_p) if not os.path.exists(p)]
    if missing:
        return all_couldnt_check(
            f"the release asset is not present: {', '.join(missing)}. It "
            "ships separately from the repository, so a fresh clone cannot "
            "check values.")

    gt_p = os.path.join(fixture_dir, "ground_truth.npy")
    if not os.path.exists(gt_p):
        return all_couldnt_check(f"no ground_truth.npy in {fixture_dir}")

    import numpy as np

    from ..characterize import characterize_arrays
    from . import reference

    seed = int(((spec.get("sampling") or {}).get("seed"))
               or ((spec.get("ground_truth") or {}).get("seed")) or 20260908)
    log_fn(f"  loading {vec_p}")
    base = np.load(vec_p, mmap_mode=None).astype(np.float32)
    queries = np.load(q_p).astype(np.float32)
    gt10 = np.load(gt_p)[:, :10]

    log_fn(f"  recomputing the characterization over {len(base):,} vectors "
           f"(seed {seed})")
    got = characterize_arrays(base, queries, seed, log_fn=lambda *_a: None)

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
            rows.append(("drift", COULDNT_CHECK,
                         f"sample.jsonl.zst is not present ({sample_path}); "
                         "it carries the update_date column drift is cut on"))
        else:
            cutoff = _published_cutoff(published["drift"])
            drift, why = recompute_drift(sample_path, base, queries, gt10,
                                         seed, cutoff, log_fn=log_fn)
            if drift is None:
                rows.append(("drift", COULDNT_CHECK, why))
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
            rows.append(("single_node_hnsw.recall_at_10", COULDNT_CHECK,
                         f"recompute failed: {type(e).__name__}: {e}"))

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
        except Exception as e:                        # reported, not raised
            for name in ("semantic_sharded.recall_at_10",
                         "semantic_sharded.storage_amplification"):
                rows.append((name, COULDNT_CHECK,
                             f"recompute failed: {type(e).__name__}: {e}"))
    return rows


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
    return (name, COULDNT_CHECK,
            f"{detail} -- WITHIN TOLERANCE, but not under the pinned "
            f"environment ({versions}), so it is not a reproduction")


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
        return (name, COULDNT_CHECK, why)
    if have is None:
        return (name, COULDNT_CHECK, "not produced by the recomputation")
    if isinstance(have, str):
        return (name, COULDNT_CHECK, have)
    tol_n, tol_why = _as_number(tol)
    if tol_n is None:
        return (name, COULDNT_CHECK,
                "the spec publishes no usable tolerance for this value, so "
                f"'reproduces' has no defined meaning ({tol_why})")
    delta = abs(float(have) - want_n)
    detail = (f"recomputed {float(have):.6g}, published {want_n:.6g}, "
              f"delta {delta:.6g}, tolerance {tol_n:.6g}")
    if delta <= tol_n:
        return (name, VERIFIED, detail)
    return (name, CONTRADICTED, detail)


def cmd_verify(args):
    # `fixture verify` decides whether a fixture may be called verified, so it
    # is guarded like anything else that writes a canonical claim -- and it
    # already knew how to say couldnt_check per value. The guard stops it
    # before it spends ten minutes recomputing under the wrong libraries.
    from .. import environment as envmod
    envmod.GUARDED_COMMANDS.add("oneground fixture verify")
    _stamp, code = envmod.guard_or_exit(
        "oneground fixture verify",
        getattr(args, "requirements", "requirements.txt"),
        allow_unpinned=getattr(args, "allow_unpinned", False))
    if code:
        return code

    fixture_dir = os.path.join(args.fixtures_dir, args.id)
    if not os.path.isdir(fixture_dir):
        print(f"error: no such fixture directory: {fixture_dir}", file=sys.stderr)
        return 1
    if not os.path.exists(os.path.join(fixture_dir, MANIFEST_NAME)):
        print(f"error: no {MANIFEST_NAME} in {fixture_dir}", file=sys.stderr)
        return 1

    assets_dir = getattr(args, "assets_dir", DEFAULT_ASSETS)
    asset = getattr(args, "asset", None)
    # `--asset` names the extracted folder outright; without it, the
    # documented location under the assets directory.
    digest_dir = (os.path.expanduser(str(asset)) if asset
                  else os.path.join(assets_dir, args.id))
    results, unlisted = verify_digests(fixture_dir, digest_dir)

    print(f"fixture: {args.id}")
    print(f"directory: {fixture_dir}")
    print(f"manifest: {MANIFEST_NAME} ({len(results)} files listed)")
    print()
    print("digests")
    width = max(len(n) for n, _, _, _ in results) if results else 0
    for name, k, outcome, detail in results:
        print(f"  {outcome:<13} {k:<8} {name:<{width}}  {detail}")

    counts = {o: sum(1 for _, _, r, _ in results if r == o)
              for o in (VERIFIED, CONTRADICTED, COULDNT_CHECK)}
    print()
    if unlisted:
        print(f"present but not listed in the manifest: {', '.join(unlisted)}")
        print()
    print("values")
    spec_path = os.path.join(args.fixtures_dir, f"{args.id}.fixture.yaml")
    value_rows = []
    if not os.path.exists(spec_path):
        print(f"  {COULDNT_CHECK:<13} no spec at {spec_path}")
    else:
        with open(spec_path, encoding="utf-8") as f:
            spec = yaml.safe_load(f) or {}
        value_rows = verify_values(
            args.id, fixture_dir, spec, assets_dir,
            getattr(args, "requirements", "requirements.txt"),
            log_fn=(print if getattr(args, "verbose", False)
                    else lambda *_a: None),
            asset=asset)
        vw = max((len(n) for n, _, _ in value_rows), default=0)
        for name, outcome, detail in value_rows:
            print(f"  {outcome:<13} {name:<{vw}}  {detail}")
        if not value_rows:
            print(f"  {COULDNT_CHECK:<13} the spec publishes no values")
    print()

    unpinned = running_pin_mismatches(
        getattr(args, "requirements", "requirements.txt"))
    if unpinned and value_rows:
        print("  NOTE: this environment does not match requirements.txt:")
        for n, g, w in unpinned:
            print(f"    {n}: running {g}, pinned {w}")
        print("  Values are reported couldnt_check for that reason alone; "
              "each row's")
        print("  detail says whether the number itself landed within "
              "tolerance.")
        print()

    vcounts = {o: sum(1 for _, r, _ in value_rows if r == o)
               for o in (VERIFIED, CONTRADICTED, COULDNT_CHECK)}
    n_declared = sum(1 for _, k, _, _ in results if k == DECLARED)
    print(f"summary: digests {counts[VERIFIED]} verified, "
          f"{counts[CONTRADICTED]} contradicted, {counts[COULDNT_CHECK]} "
          f"couldnt_check ({len(results) - n_declared} receipt, "
          f"{n_declared} declared)")
    print(f"         values  {vcounts[VERIFIED]} verified, "
          f"{vcounts[CONTRADICTED]} contradicted, "
          f"{vcounts[COULDNT_CHECK]} couldnt_check")
    if value_rows and not vcounts[CONTRADICTED] and not vcounts[COULDNT_CHECK]:
        print()
        print(f"         every published value reproduced. This fixture's "
              f"status may be set to `verified`.")
    counts[CONTRADICTED] += vcounts[CONTRADICTED]
    counts[COULDNT_CHECK] += vcounts[COULDNT_CHECK]

    # By default only a contradiction is a failure. An absent artifact is
    # reported, not punished: the large artifacts ship as a separate release
    # asset, so a fresh clone legitimately cannot check them. --strict is for
    # the caller that does have them and wants the whole fixture accounted for.
    # getattr keeps cmd_verify callable with a bare namespace.
    if counts[CONTRADICTED]:
        return 1
    if getattr(args, "strict", False) and counts[COULDNT_CHECK]:
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
    v.add_argument("--fixtures-dir", default="fixtures")
    v.add_argument("--assets-dir", default=DEFAULT_ASSETS,
                   help="where release assets are extracted, one folder per "
                        "fixture id (default: ~/oneground-assets)")
    v.add_argument("--asset", default=None, metavar="FOLDER",
                   help="the extracted asset folder for THIS fixture, "
                        "overriding --assets-dir. Use this rather than "
                        "adopting a directory layout: "
                        "--asset ./arxiv-150k")
    v.add_argument("--requirements", default="requirements.txt",
                   help="the pinned requirements the fixture claims")
    v.add_argument("--verbose", action="store_true",
                   help="print each recomputation as it runs")
    envmod.add_argument(v)
    v.add_argument("--strict", action="store_true",
                   help="exit 2 if any listed file is absent (couldnt_check) "
                        "instead of the default 0; the report is unchanged")
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
