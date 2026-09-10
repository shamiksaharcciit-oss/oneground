"""015 step 5: does the copied arxiv-150k workdir match its own manifest?

The pod session spec is built from this workdir, and the session carries its
digests to the pod, which re-checks them before measuring. A workdir copied
between checkouts is exactly the kind of input that can be subtly wrong -- a
partial copy, a file from a different run, a line-ending mangling on Windows
-- and every one of those failures would show up as a measurement rather than
as an error.

So this recomputes every digest MANIFEST.sha256 lists, and reports the three
outcomes this project keeps apart. It is deliberately not `fixture verify`:
that command is about a published fixture, this is about a run directory.
"""
import os
import sys

sys.path.insert(0, ".")

from oneground.receipts import MANIFEST_NAME, sha256_file    # noqa: E402

VERIFIED = "verified"
CONTRADICTED = "contradicted"
COULDNT_CHECK = "couldnt_check"

WORKDIR = sys.argv[1] if len(sys.argv) > 1 else \
    "runs/arxiv-150k-via-characterize"

# What the session spec actually reads. A manifest that verifies but is
# missing one of these is still not a workdir a pod run can be built from.
REQUIRED = ("characterization.json", "simulate.json", "simulate_info.json",
            "sample_ids.json", "queries_ids.json", "build_info.json")


def read_manifest(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            digest, _, name = line.partition("  ")
            if len(digest) != 64 or not name:
                raise ValueError(f"{path}:{lineno}: malformed: {line!r}")
            entries.append((digest.lower(), name))
    return entries


if __name__ == "__main__":
    mpath = os.path.join(WORKDIR, MANIFEST_NAME)
    if not os.path.exists(mpath):
        print(f"no {MANIFEST_NAME} in {WORKDIR}")
        raise SystemExit(2)

    rows, counts = [], {VERIFIED: 0, CONTRADICTED: 0, COULDNT_CHECK: 0}
    for want, name in read_manifest(mpath):
        p = os.path.join(WORKDIR, name)
        if not os.path.exists(p):
            outcome, detail = COULDNT_CHECK, "listed but not present"
        else:
            got = sha256_file(p)
            if got == want:
                outcome, detail = VERIFIED, got
            else:
                outcome, detail = CONTRADICTED, f"want {want}, got {got}"
        counts[outcome] += 1
        rows.append((outcome, name, detail))

    width = max(len(n) for _, n, _ in rows)
    for outcome, name, detail in rows:
        print(f"  {outcome:<14} {name:<{width}}  {detail}")

    listed = {n for _, n in read_manifest(mpath)}
    missing_required = [n for n in REQUIRED
                        if not os.path.exists(os.path.join(WORKDIR, n))]
    unlisted_required = [n for n in REQUIRED if n not in listed]

    print()
    print(f"  {counts[VERIFIED]} verified, {counts[CONTRADICTED]} "
          f"contradicted, {counts[COULDNT_CHECK]} couldn't-check")
    if unlisted_required:
        print(f"  NOTE: present but not covered by the manifest: "
              f"{', '.join(unlisted_required)}")
    if missing_required:
        print(f"  MISSING and required by the session spec: "
              f"{', '.join(missing_required)}")

    if counts[CONTRADICTED] or missing_required:
        print("\n  REFUSING: this workdir is not what its manifest says it is")
        raise SystemExit(1)
    print("\n  every digest in the manifest matches, and every file the "
          "session spec reads is present")
