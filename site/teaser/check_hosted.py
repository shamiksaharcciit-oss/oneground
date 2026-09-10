#!/usr/bin/env python3
"""
Is the hosted copy of this page the repository's copy?

    python site/teaser/check_hosted.py https://oneground.oneproof.dev
    python site/teaser/check_hosted.py https://shamiksaharcciit-oss.github.io/oneground

Fetches `data/MANIFEST.sha256` from the host, then every file it lists
(including `inline.js`), then `index.html`, `app.js` and `style.css`, which no
manifest covers, and compares each digest to the file in this repository. One
outcome per file, in the project's vocabulary:

    verified        the hosted bytes are the repository's bytes
    contradicted    the host served something else
    couldnt_check   the host has no such file, or could not be reached

Exit status is 0 unless something was **contradicted**. An absent file is not
a contradiction -- it is a gap, and couldn't-check is never rounded up to a
verdict. Read the summary line: it says how many of each.

Against a Pages *branch* build -- which is what this repository served before
`.github/workflows/pages.yml` existed -- the honest reading is a mixture:
`data/*`, `app.js` and `style.css` are absent, and `index.html` is present but
**contradicted**, because the host really is serving a different page (the
README, rendered by Jekyll). The closing message names that case.

Stdlib only, so it runs anywhere Python does, including on a machine that has
never installed oneground.
"""

import argparse
import hashlib
import io
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = "data/MANIFEST.sha256"

# Files no manifest covers: the page itself. They are compared to the
# repository copy directly, because there is nothing else to compare them to.
PAGE_FILES = ["index.html", "app.js", "style.css"]

# Present in the repository, and expected on the host, but not compared:
# CNAME is consumed by Pages rather than served, and .nojekyll is a marker.
NOT_SERVED = ["CNAME", ".nojekyll"]

VERIFIED, CONTRADICTED, COULDNT = "verified", "contradicted", "couldnt_check"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url, timeout):
    """Bytes at `url`, or (None, reason). Asks caches not to answer for us."""
    req = urllib.request.Request(url, headers={
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "oneground-check-hosted",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:                       # DNS, TLS, timeout, refused
        return None, f"{type(e).__name__}: {e}"


def read_manifest(text):
    out = []
    for line in io.StringIO(text):
        line = line.strip()
        if line:
            digest, _, name = line.partition("  ")
            out.append((name.strip(), digest))
    return out


def local_bytes(rel):
    path = os.path.join(HERE, rel.replace("/", os.sep))
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def check(rows, name, url, expect_sha, timeout):
    """One file: fetch it, digest it, say which of the three it is."""
    body, why = fetch(url, timeout)
    if body is None:
        rows.append((COULDNT, name, why))
        return
    got = sha256(body)
    if expect_sha is None:
        rows.append((COULDNT, name, "not in the repository, nothing to compare"))
    elif got == expect_sha:
        rows.append((VERIFIED, name, f"{len(body):,} bytes  {got[:16]}…"))
    else:
        rows.append((CONTRADICTED, name,
                     f"host {got[:16]}… repo {expect_sha[:16]}…  "
                     f"{len(body):,} bytes"))


def main():
    ap = argparse.ArgumentParser(
        description="Compare a hosted copy of the teaser to this repository.")
    ap.add_argument("base_url", help="e.g. https://oneground.oneproof.dev")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    print(f"host   {base}")
    print(f"repo   {HERE}\n")

    rows = []

    # ---- the manifest itself, then everything it lists ------------------
    local_manifest = local_bytes(MANIFEST)
    if local_manifest is None:
        raise SystemExit(f"{MANIFEST} is missing from this checkout; there is "
                         "nothing to compare the host against.")

    body, why = fetch(f"{base}/{MANIFEST}", args.timeout)
    no_manifest = body is None
    if no_manifest:
        rows.append((COULDNT, MANIFEST, why))
        listed = []
    else:
        got = sha256(body)
        want = sha256(local_manifest)
        if got == want:
            rows.append((VERIFIED, MANIFEST, f"{got[:16]}…"))
        else:
            rows.append((CONTRADICTED, MANIFEST,
                         f"host {got[:16]}… repo {want[:16]}…"))
        # Read the file list from the *repository's* manifest, not the host's.
        # If the host served a manifest of its own choosing, checking the files
        # it names would let it choose what gets checked.
        listed = read_manifest(local_manifest.decode("utf-8"))
        for name, digest in listed:
            check(rows, name, f"{base}/data/{name}", digest, args.timeout)

    # ---- the page files, which no manifest covers ------------------------
    for name in PAGE_FILES:
        data = local_bytes(name)
        check(rows, name, f"{base}/{name}",
              sha256(data) if data is not None else None, args.timeout)

    # ---- report ----------------------------------------------------------
    for outcome, name, detail in rows:
        print(f"  {outcome:<13} {name:<20} {detail}")
    if no_manifest:
        print("\n  The manifest could not be fetched, so the files it lists "
              "were not checked.")

    counts = {VERIFIED: 0, CONTRADICTED: 0, COULDNT: 0}
    for outcome, _, _ in rows:
        counts[outcome] += 1

    print(f"\n  {counts[VERIFIED]} verified · {counts[CONTRADICTED]} "
          f"contradicted · {counts[COULDNT]} couldn't-check")

    if counts[CONTRADICTED]:
        print("\nCONTRADICTED: the host is serving bytes this repository did "
              "not produce.")
        if no_manifest:
            # Everything absent but index.html present is the shape of a Pages
            # branch build: a different site altogether, not a bad deploy of
            # this one. Say so, because the fix is a settings change.
            print("There is no data/MANIFEST.sha256 on the host and "
                  "index.html disagrees, which is\nwhat a Pages *branch* "
                  "build looks like — the README rendered by Jekyll, not this\n"
                  "site. Set Settings -> Pages -> Source to GitHub Actions and "
                  "let the workflow run.")
        else:
            print("A stale CDN cache looks exactly like this; so does a bad "
                  "deploy. Re-run after\nthe next deployment before "
                  "concluding anything worse.")
        return 1
    if counts[COULDNT] and not counts[VERIFIED]:
        print("\nNothing was contradicted and nothing was verified: the host "
              "has none of these\nfiles. If the Pages workflow has not run "
              "yet, that is expected.")
        return 0
    if counts[COULDNT]:
        print("\nNothing contradicted. The couldn't-check rows above are "
              "files the host did not\nserve; they are not disagreements and "
              "are not counted as failures.")
        return 0
    print("\nThe hosted copy is this repository's copy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
