"""Task 032b: are two runs' emitted state columns the same bytes?

    python corpora/compare_state.py <state-dir-A> <state-dir-B>

Each argument is a run's `state/` directory -- the laptop's and the pod's.
The comparison is in three steps, and it reports rather than judges:

  1. the files each side wrote, by name;
  2. the sha256 of each `*.state.npz` they share, which is the claim: the
     writer fixes every zip entry's timestamp and sorts the entries
     (`oneground/models/state.py`), so identical state is identical bytes;
  3. for any file whose bytes differ, a column-by-column comparison, so the
     residual is a named column and a count rather than "the files differ".

`state_info.json` is compared with its environment-dependent fields set
aside -- library versions, timings and byte counts -- because it is declared
and describes the run, not the state.

Exit code 0 when every shared `.state.npz` matches, 1 otherwise. A difference
is a finding to report, not a reason to widen anything.
"""

import hashlib
import json
import os
import sys

import numpy as np

# Fields of state_info.json that describe the run rather than the state.
ENVIRONMENTAL = ("library_versions", "state_seconds_total", "state_bytes_total",
                 "state_seconds", "bytes", "run")


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


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a_dir, b_dir = sys.argv[1], sys.argv[2]
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
        same = [c for c, v, _ in compare_columns(pa, pb) if v == "identical"]
        print("      (%d column(s) identical: %s)" % (len(same),
                                                      ", ".join(same)))

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
    if bad:
        print("RESIDUAL: %d of %d shared state file(s) differ: %s"
              % (len(bad), len(shared), ", ".join(bad)))
        return 1
    print("Every shared state file is byte-identical (%d of %d)."
          % (len(shared), len(shared)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
