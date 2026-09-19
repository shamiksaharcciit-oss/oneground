"""Task 032b: do two runs' emitted state columns agree, and in which sense?

    python corpora/compare_state.py <state-dir-A> <state-dir-B>
    python corpora/compare_state.py --cross-environment <dir-A> <dir-B>

TWO CLAIMS, NOT ONE. The state's contract (docs/STATE.md) is deliberately
two statements, because one cannot be true of a file that stores raw float32
inner products:

    within one environment    byte-identical. This is what the MANIFEST's
                              sha256 is for, and the default mode checks it.
    across environments       identical decisions, and scored floats equal to
                              within a couple of units in the last place.
                              This is what `--cross-environment` checks.

A reader who compares two machines' digests and expects a match **will get a
false alarm**. Task 032b measured why, on the arxiv-150k reference
configuration across an Intel i3-1115G4 and an AMD EPYC 7352 at one commit:
every decision column byte-identical -- region assignment, the closure, copy
counts, shard membership, load, offsets -- and 80,648 of 400,000 candidate
scores differing in their last one or two bits, because they are inner
products computed inside faiss's own search kernels, below the BLAS
threshold, where no determinism context this project controls reaches.

The default mode is in three steps, and it reports rather than judges:

  1. the files each side wrote, by name;
  2. the sha256 of each `*.state.npz` they share;
  3. for any file whose bytes differ, a column-by-column comparison, so the
     residual is a named column and a count rather than "the files differ".

`--cross-environment` replaces step 2's verdict with the contract's second
claim: every column must match exactly except the scored float columns, which
must match to within `--max-ulps`. A decision column that moves at all fails,
because that would be a different partition or a different traversal and not
rounding.

ON THE NUMBER. `--max-ulps` defaults to 2 because that is what the one pair
of machines measured so far showed, over 400,000 candidate scores:

    0 ulps apart   319,352
    1 ulp          75,811
    2 ulps          4,837

It is an **observation, not a derivation**. The worst case for a float32 dot
product over 768 terms summed in two different orders is of order 768 x eps,
which is about 9e-5 -- four orders larger than anything seen. So 2 is not a
bound anyone can prove from the arithmetic; it is what two CPUs did on one
corpus, and a third machine could exceed it without anything being wrong.
The distribution is therefore printed every time, so a reader judges the
shape rather than a pass/fail on a number fitted to one run.

(An earlier report of mine called the residual "max |delta| 1.1920929e-07,
which is float32 epsilon -- one unit in the last place at magnitude ~1", and
"one ulp" was taken from it. That was imprecise: eps is the ulp AT 1.0, and
these inner products lie in [0.546, 0.905], where the same absolute delta is
two ulps. The measurement above is what the contract states.)

`state_info.json` is compared with its environment-dependent fields set
aside -- library versions, timings and byte counts -- because it is declared
and describes the run, not the state.

Exit code 0 when the chosen claim holds, 1 otherwise. A difference is a
finding to report, not a reason to widen anything.
"""

import hashlib
import json
import os
import sys

import numpy as np

# Fields of state_info.json that describe the run rather than the state.
ENVIRONMENTAL = ("library_versions", "state_seconds_total", "state_bytes_total",
                 "state_seconds", "bytes", "run")

# The columns whose values are computed by faiss's own distance kernels, and
# which therefore may differ across microarchitectures in their last bits.
# Everything else in the state is a decision -- an argmin, a comparison, a
# count, an id -- and a decision that moves is not rounding.
#
# `route.scored_dist` is NOT here. It was, in the sense that it moved, until
# task 032b found the reason: `state()` computed it outside the determinism
# context the base side was inside. Once the context reached it, it came back
# byte-identical across the two machines. A column belongs on this list only
# when we do not own its arithmetic -- not when we have not yet reached it.
SCORED_COLUMNS = ("candidates.cand_score",)

# Columns derived from the scored ones by ordering. A last-bit difference can
# flip two neighbouring candidates, which moves an id and a rank without any
# decision having been made differently. Allowed only when a scored column
# actually moved -- otherwise a rank that changed has no rounding behind it
# and is a different traversal.
ORDERING_COLUMNS = ("candidates.cand_id", "candidates.true_rank",
                    "candidates.survived_dedupe")


def ulps_apart(x, y):
    """How many representable float32 values lie between each pair.

    Computed on the integer representation, which is what "one unit in the
    last place" means: consecutive float32 values differ by 1 when their bits
    are read as int32. Sign-magnitude is folded so that values straddling
    zero are not reported as billions of ulps apart.
    """
    a = x.astype(np.float32).view(np.int32).astype(np.int64)
    b = y.astype(np.float32).view(np.int32).astype(np.int64)
    a = np.where(a < 0, np.int64(1) << 31 | -a, a)
    b = np.where(b < 0, np.int64(1) << 31 | -b, b)
    return np.abs(a - b)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def state_files(d):
    return sorted(n for n in os.listdir(d) if n.endswith(".state.npz"))


def strip_environmental(obj):
    if isinstance(obj, dict):
        return {k: strip_environmental(v) for k, v in obj.items()
                if k not in ENVIRONMENTAL}
    if isinstance(obj, list):
        return [strip_environmental(v) for v in obj]
    return obj


def _json_diff(a_bytes, b_bytes):
    """Which keys of two `header.json` entries differ, as dotted paths.

    The header is not a column and `np.load` hands it back as raw bytes, not
    an array -- which this function's absence turned into an AttributeError
    the first time two headers actually differed. A header difference is a
    real finding, and often a more interesting one than a column difference:
    it means the two runs described the same arrays differently.
    """
    try:
        a = json.loads(bytes(a_bytes).decode("utf-8"))
        b = json.loads(bytes(b_bytes).decode("utf-8"))
    except Exception as e:                                # noqa: BLE001
        return ["(could not be parsed as JSON: %s)" % e]

    def walk(x, y, path):
        if isinstance(x, dict) and isinstance(y, dict):
            out = []
            for key in sorted(set(x) | set(y)):
                out.extend(walk(x.get(key), y.get(key),
                                path + ("." if path else "") + str(key)))
            return out
        if x == y:
            return []
        return ["%s: A=%r B=%r" % (path, x, y)]

    return walk(a, b, "")


def compare_columns(a_path, b_path):
    """[(column, verdict, detail)] for two .state.npz files."""
    a, b = np.load(a_path, allow_pickle=False), np.load(b_path,
                                                        allow_pickle=False)
    out = []
    for name in sorted(set(a.files) | set(b.files)):
        if name not in a.files or name not in b.files:
            out.append((name, "only in one side",
                        "A" if name in a.files else "B"))
            continue
        x, y = a[name], b[name]
        # `header.json` is a stored entry, not an array. Compare it as JSON
        # so the residual is a named field rather than "the bytes differ".
        if not hasattr(x, "shape") or not hasattr(y, "shape"):
            differences = _json_diff(x, y)
            if not differences:
                out.append((name, "identical", "json, same fields"))
            else:
                out.append((name, "DIFFERS", "; ".join(differences)))
            continue
        if x.shape != y.shape or x.dtype != y.dtype:
            out.append((name, "shape or dtype differs",
                        "%s %s vs %s %s" % (x.shape, x.dtype, y.shape,
                                            y.dtype)))
            continue
        if np.array_equal(x, y):
            out.append((name, "identical", "%s %s" % (x.dtype, x.shape)))
            continue
        differing = int(np.count_nonzero(x != y))
        detail = "%d of %d elements" % (differing, x.size)
        if np.issubdtype(x.dtype, np.floating):
            delta = float(np.max(np.abs(x.astype(np.float64)
                                        - y.astype(np.float64))))
            detail += ", max |delta| %.8g" % delta
        out.append((name, "DIFFERS", detail))
    return out


DEFAULT_MAX_ULPS = 2


def check_cross_environment(a_path, b_path, max_ulps=DEFAULT_MAX_ULPS):
    """[(column, verdict, detail)] under the contract's second claim.

    Exactness everywhere except the scored float columns, which may differ by
    at most `max_ulps`. The ordering columns are allowed to move only where a
    scored value did: a rank that changed with no score behind it is a
    different traversal, and that is not rounding.

    The scored columns are judged FIRST, whatever the alphabet says. They were
    not, and `candidates.cand_id` sorts before `candidates.cand_score`, so the
    first run of this check reported "NO scored column moved, so this is a
    different traversal" about a file whose scores had moved 80,648 times. A
    check whose verdict depends on the order it happens to visit columns in is
    not a check.
    """
    a, b = np.load(a_path, allow_pickle=False), np.load(b_path,
                                                        allow_pickle=False)
    names = sorted(set(a.files) | set(b.files))
    scores_moved = any(
        name in SCORED_COLUMNS and name in a.files and name in b.files
        and getattr(a[name], "shape", None) == getattr(b[name], "shape", None)
        and not np.array_equal(a[name], b[name])
        for name in names)
    out = []
    for name in names:
        if name not in a.files or name not in b.files:
            out.append((name, "FAILS", "present on only one side"))
            continue
        x, y = a[name], b[name]
        if not hasattr(x, "shape") or not hasattr(y, "shape"):
            differences = _json_diff(x, y)
            out.append((name, "holds" if not differences else "FAILS",
                        "json, same fields" if not differences
                        else "; ".join(differences)))
            continue
        if x.shape != y.shape or x.dtype != y.dtype:
            out.append((name, "FAILS", "shape or dtype differs: %s %s vs %s %s"
                        % (x.shape, x.dtype, y.shape, y.dtype)))
            continue
        if np.array_equal(x, y):
            out.append((name, "holds", "exact, %s %s" % (x.dtype, x.shape)))
            continue

        moved = int(np.count_nonzero(x != y))
        if name in SCORED_COLUMNS and np.issubdtype(x.dtype, np.floating):
            ulps = ulps_apart(x, y)
            worst = int(ulps.max())
            delta = float(np.max(np.abs(x.astype(np.float64)
                                        - y.astype(np.float64))))
            spread = ", ".join(
                "%d ulp: %d" % (k, int(np.count_nonzero(ulps == k)))
                for k in range(1, worst + 1)
                if np.count_nonzero(ulps == k))
            out.append((name, "holds" if worst <= max_ulps else "FAILS",
                        "%d of %d values differ (%s), max |delta| %.8g; "
                        "allowed %d ulp"
                        % (moved, x.size, spread, delta, max_ulps)))
            continue
        if name in ORDERING_COLUMNS:
            # Allowed only as a consequence of a scored value having moved.
            out.append((name, "holds" if scores_moved else "FAILS",
                        "%d of %d values differ; %s"
                        % (moved, x.size,
                           "a scored column moved, so an order can"
                           if scores_moved else
                           "NO scored column moved, so this is a different "
                           "traversal rather than rounding")))
            continue
        detail = "%d of %d values differ" % (moved, x.size)
        if np.issubdtype(x.dtype, np.floating):
            detail += ", max |delta| %.8g" % float(
                np.max(np.abs(x.astype(np.float64) - y.astype(np.float64))))
        out.append((name, "FAILS", detail + " -- this is a decision, and a "
                                            "decision that moves is not "
                                            "rounding"))
    return out


def cross_environment(a_dir, b_dir, shared, max_ulps=DEFAULT_MAX_ULPS):
    """The contract's second claim, file by file. Returns the failures."""
    print()
    print("  cross-environment: identical decisions, and scored floats "
          "within %d ulp" % max_ulps)
    print("  (docs/STATE.md. Byte-identity is the WITHIN-environment claim; "
          "comparing")
    print("   two machines' digests and expecting a match gives a false "
          "alarm.)")
    failed = []
    for name in shared:
        pa, pb = os.path.join(a_dir, name), os.path.join(b_dir, name)
        rows = check_cross_environment(pa, pb, max_ulps)
        bad = [r for r in rows if r[1] != "holds"]
        inexact = [r for r in rows if r[1] == "holds"
                   and not r[2].startswith("exact")
                   and not r[2].startswith("json")]
        print()
        print("  %-46s %s" % (name, "HOLDS" if not bad else "FAILS"))
        for column, verdict, detail in bad:
            print("      %-26s %-8s %s" % (column, verdict, detail))
        for column, verdict, detail in inexact:
            print("      %-26s %-8s %s" % (column, "within", detail))
        exact = [r[0] for r in rows if r[1] == "holds"
                 and (r[2].startswith("exact") or r[2].startswith("json"))]
        print("      (%d column(s) exact: %s)" % (len(exact),
                                                  ", ".join(exact)))
        if bad:
            failed.append(name)
    return failed


def main():
    argv = sys.argv[1:]
    cross = "--cross-environment" in argv
    max_ulps = DEFAULT_MAX_ULPS
    rest = []
    it = iter(argv)
    for arg in it:
        if arg == "--cross-environment":
            continue
        if arg == "--max-ulps":
            try:
                max_ulps = int(next(it))
            except (StopIteration, ValueError):
                print("--max-ulps takes an integer")
                return 2
            continue
        rest.append(arg)
    if len(rest) != 2:
        print(__doc__)
        return 2
    a_dir, b_dir = rest[0], rest[1]
    for d in (a_dir, b_dir):
        if not os.path.isdir(d):
            print("no such state directory: %s" % d)
            return 2

    a_files, b_files = state_files(a_dir), state_files(b_dir)
    print("A %s" % a_dir)
    print("B %s" % b_dir)
    print()
    only_a, only_b = sorted(set(a_files) - set(b_files)), sorted(
        set(b_files) - set(a_files))
    for name in only_a:
        print("  only in A   %s" % name)
    for name in only_b:
        print("  only in B   %s" % name)

    shared = [n for n in a_files if n in set(b_files)]
    if not shared:
        print("  no .state.npz file is present on both sides; nothing to "
              "compare")
        return 1

    bad = []
    if cross:
        bad = cross_environment(a_dir, b_dir, shared, max_ulps)
    else:
        for name in shared:
            pa, pb = os.path.join(a_dir, name), os.path.join(b_dir, name)
            da, db = digest(pa), digest(pb)
            if da == db:
                print("  identical   %-46s %s" % (name, da[:16]))
                continue
            bad.append(name)
            print("  DIFFERS     %-46s" % name)
            print("      A %s  (%d bytes)" % (da[:16], os.path.getsize(pa)))
            print("      B %s  (%d bytes)" % (db[:16], os.path.getsize(pb)))
            for column, verdict, detail in compare_columns(pa, pb):
                if verdict != "identical":
                    print("      %-26s %-22s %s" % (column, verdict, detail))
            same = [c for c, v, _ in compare_columns(pa, pb)
                    if v == "identical"]
            print("      (%d column(s) identical: %s)"
                  % (len(same), ", ".join(same)))

    info_a = os.path.join(a_dir, "state_info.json")
    info_b = os.path.join(b_dir, "state_info.json")
    if os.path.exists(info_a) and os.path.exists(info_b):
        with open(info_a, encoding="utf-8") as f:
            ia = strip_environmental(json.load(f))
        with open(info_b, encoding="utf-8") as f:
            ib = strip_environmental(json.load(f))
        print()
        print("  state_info.json, environment-dependent fields set aside: %s"
              % ("same" if ia == ib else "DIFFERS"))
        if ia != ib:
            for key in sorted(set(ia) | set(ib)):
                if ia.get(key) != ib.get(key):
                    print("      %-22s A=%s" % (key, str(ia.get(key))[:60]))
                    print("      %-22s B=%s" % ("", str(ib.get(key))[:60]))

    print()
    if cross:
        if bad:
            print("RESIDUAL: the cross-environment claim FAILS for %d of %d "
                  "state file(s): %s" % (len(bad), len(shared), ", ".join(bad)))
            return 1
        print("The cross-environment claim holds for all %d state file(s): "
              "identical decisions," % len(shared))
        print("and every scored float within %d ulp. This is NOT "
              "byte-identity, and the" % max_ulps)
        print("digests will differ; see docs/STATE.md for why that is the "
              "right contract here.")
        return 0
    if bad:
        print("RESIDUAL: %d of %d shared state file(s) differ: %s"
              % (len(bad), len(shared), ", ".join(bad)))
        print("Two machines? This is the WITHIN-environment claim. Re-run "
              "with --cross-environment")
        print("for the one that applies (docs/STATE.md).")
        return 1
    print("Every shared state file is byte-identical (%d of %d)."
          % (len(shared), len(shared)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
