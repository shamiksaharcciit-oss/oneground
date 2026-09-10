#!/usr/bin/env python3
"""
Re-derive the teaser's numbers from base.bin alone.

The acceptance test for task T1: read the exported binary the way the browser
reads it, apply the same closure rule at the same epsilon, and check the
counters against the fixture's published values. Nothing here imports the
export script or the package, and nothing reads the 460 MB of vectors -- if
base.bin does not carry enough to reproduce the published numbers, this fails,
which is exactly the claim the page makes about itself.

    python site/teaser/verify_teaser_data.py
    python site/teaser/verify_teaser_data.py --dir site/teaser/data

Checks, in order:

  1. every file in data/MANIFEST.sha256 has the digest the manifest gives
  2. base.bin is the size and shape values.json declares
  3. copies(eps = 0.20) recomputed from d1..d4 reproduces the published
     storage amplification (3.715x) and boundary crispness (0.036) within the
     spec's tolerances
  4. the sweep values.json recorded agree with a fresh recomputation here
  5. queries.json is internally consistent: recall@10 x 10 equals the count of
     true neighbours whose region equals the query's routed region
  6. data/inline.js carries the same four files, byte for byte

Exit status is 0 only when every check passes. It never adjusts a tolerance.
"""

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import struct
import sys

DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# The published values this script checks against, and where each one lives.
# They are read from values.json (which the export copied out of the spec) so
# that this file states no number of its own.
PUBLISHED = [
    ("boundary_crispness", ("published", "characterization", "boundary_crispness")),
    ("storage_amplification",
     ("published", "reference_results", "semantic_sharded")),
]


class Fail(Exception):
    pass


def dig(obj, path):
    for key in path:
        obj = obj[key]
    return obj


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def read_column(buf, col):
    """One column of base.bin, as a list of Python numbers.

    Deliberately written with `struct` rather than numpy: the point of this
    script is to read the bytes the way something that is not the export
    would, and numpy is what the export used.
    """
    n = col["count"]
    if col["dtype"] == "float32":
        return list(struct.unpack_from("<%df" % n, buf, col["offset"]))
    if col["dtype"] == "uint8":
        return list(struct.unpack_from("<%dB" % n, buf, col["offset"]))
    raise Fail(f"unknown dtype {col['dtype']} for column {col['name']}")


def copies_at(d, eps):
    """The closure rule, from the four distances, one vector at a time."""
    d1, d2, d3, d4 = d
    n = len(d1)
    out = [0] * n
    for i in range(n):
        lim = d1[i] * (1 + eps)
        c = 1
        if d2[i] <= lim:
            c += 1
        if d3[i] <= lim:
            c += 1
        if d4[i] <= lim:
            c += 1
        out[i] = c
    return out


def percentile_lower(counts, n, q):
    """numpy's percentile(..., method='lower') read off a small histogram."""
    k = int(q * (n - 1))
    acc = 0
    for value, c in enumerate(counts, start=1):
        acc += c
        if acc > k:
            return value
    return len(counts)


def check(label, ok, detail=""):
    print(f"  {'OK  ' if ok else 'FAIL'} {label}" + (f"   {detail}" if detail else ""))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEFAULT_DIR)
    args = ap.parse_args()
    d = args.dir
    ok = True

    # ---- 1. digests -------------------------------------------------------
    print("digests (data/MANIFEST.sha256)")
    manifest_path = os.path.join(d, "MANIFEST.sha256")
    if not os.path.exists(manifest_path):
        raise SystemExit(f"no MANIFEST.sha256 in {d}; run corpora/export_teaser_data.py")
    entries = []
    for line in open(manifest_path, encoding="utf-8"):
        line = line.strip()
        if line:
            digest, _, name = line.partition("  ")
            entries.append((name.strip(), digest))
    for name, digest in entries:
        path = os.path.join(d, name)
        got = sha256_file(path) if os.path.exists(path) else "(missing)"
        ok &= check(name, got == digest, got[:16] + "…")

    # ---- 2. shape ---------------------------------------------------------
    print("\nbase.bin against the layout values.json declares")
    values = json.load(open(os.path.join(d, "values.json"), encoding="utf-8"))
    spec = values["base_bin"]
    raw = open(os.path.join(d, "base.bin"), "rb").read()
    ok &= check("byte length", len(raw) == spec["bytes"],
                f"{len(raw):,} bytes, declared {spec['bytes']:,}")
    names = [c["name"] for c in spec["columns"]]
    ok &= check("columns", names == ["x", "y", "d1", "d2", "d3", "d4",
                                     "category", "region"], ", ".join(names))
    cols = {c["name"]: read_column(raw, c) for c in spec["columns"]}
    n = spec["rows"]

    sorted_ok = all(cols["d1"][i] <= cols["d2"][i] <= cols["d3"][i] <= cols["d4"][i]
                    for i in range(n))
    ok &= check("d1 <= d2 <= d3 <= d4 for every vector", sorted_ok)
    ok &= check("region ids inside 0..n_centroids-1",
                max(cols["region"]) < values["geometry"]["n_centroids"])

    # ---- 3. the published values, from base.bin alone ---------------------
    eps = values["geometry"]["reference_epsilon"]
    print(f"\nrecomputed from base.bin at eps = {eps:.2f}")
    c = copies_at([cols["d1"], cols["d2"], cols["d3"], cols["d4"]], eps)
    cap = values["geometry"]["max_assign"]
    hist = [c.count(k) for k in range(1, cap + 1)]
    amp = sum(c) / n
    copied = sum(1 for v in c if v > 1)
    p99 = percentile_lower(hist, n, 0.99)

    crisp_ratio = values["geometry"]["crisp_ratio"]
    crisp = sum(1 for i in range(n)
                if cols["d1"][i] > 0 and cols["d2"][i] > crisp_ratio * cols["d1"][i]) / n

    pub_amp = dig(values, PUBLISHED[1][1])
    pub_crisp = dig(values, PUBLISHED[0][1])
    ok &= check("storage amplification",
                abs(amp - pub_amp["storage_amplification"]) <= pub_amp["tolerance"],
                f"{amp:.4f} vs published {pub_amp['storage_amplification']} "
                f"(tol {pub_amp['tolerance']})")
    ok &= check("boundary crispness",
                abs(crisp - pub_crisp["value"]) <= pub_crisp["tolerance"],
                f"{crisp:.4f} vs published {pub_crisp['value']} "
                f"(tol {pub_crisp['tolerance']})")
    ok &= check("p99 copies per vector",
                p99 == pub_amp["p99_copies_per_vector"],
                f"{p99} vs published {pub_amp['p99_copies_per_vector']}")
    print(f"       copies histogram  " + "  ".join(
        f"{k}:{hist[k - 1]:,} ({hist[k - 1] / n:.3f})" for k in range(1, cap + 1)))
    print(f"       vectors copied    {copied:,}")

    # ---- 4. the sweep the export recorded ---------------------------------
    print("\nthe eps sweep in values.json, recomputed here")
    bad = []
    for key in ["0.00", f"{eps:.2f}", "0.40"]:
        want = values["measured"]["eps_sweep"][key]
        cc = copies_at([cols["d1"], cols["d2"], cols["d3"], cols["d4"]], float(key))
        got_hist = [cc.count(k) for k in range(1, cap + 1)]
        got_copied = sum(1 for v in cc if v > 1)
        if got_hist != want["hist"] or got_copied != want["copied"]:
            bad.append(f"eps {key}: {got_hist}/{got_copied} vs "
                       f"{want['hist']}/{want['copied']}")
        else:
            check(f"eps {key}", True, f"{got_hist} copied {got_copied:,}")
    for b in bad:
        ok &= check("sweep", False, b)

    # ---- 5. queries.json internal consistency ------------------------------
    print("\nqueries.json")
    queries = json.load(open(os.path.join(d, "queries.json"), encoding="utf-8"))
    region = cols["region"]
    mismatched = 0
    for q in queries["queries"]:
        inside = sum(1 for idx in q["nn"] if region[idx] == q["region"])
        if inside != round(q["recall10_one_region"] * values["geometry"]["k"]):
            mismatched += 1
        if 10 - inside != q["outside"]:
            mismatched += 1
    ok &= check("recall@10 x 10 == neighbours inside the routed region",
                mismatched == 0, f"{len(queries['queries']):,} queries, "
                                 f"{mismatched} disagreements")
    ok &= check("curated set is 12 distinct queries",
                len(set(queries["curated"])) == 12)
    ok &= check("no query title is an abstract",
                max(len(q["title"]) for q in queries["queries"]) < 400,
                f"longest title {max(len(q['title']) for q in queries['queries'])} chars")

    # ---- 5b. app.js is stamped with the digests actually on disk ----------
    print("\napp.js cache-bust stamp against the manifest")
    app = open(os.path.join(os.path.dirname(d), "app.js"),
               encoding="utf-8").read()
    m = re.search(r"const DATA_VERSION = (\{.*?\});", app, re.S)
    if not m:
        ok &= check("app.js carries a DATA_VERSION block", False)
    else:
        stamped = json.loads(m.group(1))
        want = {name: digest[:8] for name, digest in entries}
        ok &= check("stamp matches every manifest line", stamped == want,
                    f"{len(stamped)} entries")
        if stamped != want:
            for k in sorted(set(stamped) | set(want)):
                if stamped.get(k) != want.get(k):
                    print(f"       {k}: app.js {stamped.get(k)} "
                          f"manifest {want.get(k)}")

    # ---- 6. the file:// bundle is the same four files ----------------------
    print("\ndata/inline.js against the four files beside it")
    src = open(os.path.join(d, "inline.js"), encoding="utf-8").read()
    m = re.search(r"window\.__ONEGROUND_TEASER__ = (\{.*\});\s*$", src, re.S)
    if not m:
        ok &= check("inline.js parses", False)
    else:
        bundle = json.loads(m.group(1))
        for name, entry in bundle["files"].items():
            raw_here = open(os.path.join(d, name), "rb").read()
            unpacked = gzip.decompress(base64.b64decode(entry["gzip_b64"]))
            ok &= check(name, unpacked == raw_here and
                        entry["sha256"] == hashlib.sha256(raw_here).hexdigest(),
                        f"{len(unpacked):,} bytes")

    # ---- sizes -------------------------------------------------------------
    http = sum(os.path.getsize(os.path.join(d, n_))
               for n_, _ in entries if n_ != "inline.js")
    inline = os.path.getsize(os.path.join(d, "inline.js"))
    page = sum(os.path.getsize(os.path.join(os.path.dirname(d), f))
               for f in ("index.html", "app.js", "style.css"))
    print(f"\nload size")
    print(f"       over http    {(http + page) / 1e6:.2f} MB   "
          f"(data {http:,} + page {page:,})")
    print(f"       from file:// {(inline + page) / 1e6:.2f} MB   "
          f"(inline.js {inline:,} + page {page:,})")
    ok &= check("under 5 MB either way", max(http, inline) + page < 5_000_000)

    print("\nALL CHECKS PASSED" if ok else "\nCHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as e:
        print(f"FAILED: {e}", file=sys.stderr)
        sys.exit(2)
