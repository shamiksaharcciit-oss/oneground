#!/usr/bin/env python3
"""Fetch the stackexchange-150k source shards and verify every digest.

The source is 59 parquet shards, ~34 GB, at one pinned revision of
`mikex86/stackoverflow-posts`. This downloads them to a flat directory and
checks each one's sha256 against `sessions/stackexchange-shards.sha256`, which
holds the Hub's LFS oids recorded when the fixture spec was written.

A shard whose bytes do not match the pin is an error, not a warning: the whole
point of pinning a revision is that the corpus a published value was measured
on can be fetched again. Nothing is deleted on a mismatch -- the bad file is
left where a human can look at it -- and the script exits non-zero.

Already-present shards with a matching digest are skipped, so a re-run after an
interrupted download resumes rather than starting over.

    python corpora/fetch_stackexchange.py \
        --spec fixtures/stackexchange-150k.fixture.yaml \
        --dest /workspace/stackexchange-posts

Only files named in the digest manifest are fetched, and only from the
revision the spec pins.
"""

import argparse
import hashlib
import os
import shutil
import sys

import yaml

CHUNK = 1 << 20


def read_manifest(path):
    """`<sha256>  <filename>` lines, comments ignored."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                sha, name = line.split(None, 1)
            except ValueError:
                raise SystemExit(f"{path}:{n}: not a `<sha256>  <name>` line")
            if len(sha) != 64:
                raise SystemExit(f"{path}:{n}: {sha!r} is not a sha256")
            out[name.strip()] = sha
    if not out:
        raise SystemExit(f"{path}: no digests")
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def remote_sizes(repo_id, revision, names):
    """{filename: size} at the pinned revision, from the Hub's LFS metadata.

    One API call, and it doubles as a check that the revision still resolves
    before 34 GB of transfer is started.
    """
    from huggingface_hub import HfApi
    info = HfApi().repo_info(repo_id, repo_type="dataset", revision=revision,
                             files_metadata=True)
    out = {}
    for s in info.siblings or []:
        if s.rfilename in names:
            lfs = getattr(s, "lfs", None)
            size = (getattr(lfs, "size", None) if lfs else None) or s.size or 0
            out[s.rfilename] = int(size)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", default="fixtures/stackexchange-150k.fixture.yaml")
    ap.add_argument("--dest", required=True)
    ap.add_argument("--headroom-gb", type=float, default=2.0,
                    help="space the build still needs after the download: the "
                         "model cache, the artifacts and the two tarballs")
    args = ap.parse_args(argv)

    spec = yaml.safe_load(open(args.spec, encoding="utf-8"))
    src = spec["source"]
    repo_id = src["repo_id"]
    revision = src["revision"]
    manifest_path = src["shard_digests"]

    want = read_manifest(manifest_path)
    os.makedirs(args.dest, exist_ok=True)

    print(f"repo     : {repo_id}")
    print(f"revision : {revision}")
    print(f"shards   : {len(want)}")
    print(f"dest     : {args.dest}")

    # Refuse before the first byte rather than fail at the thirtieth gigabyte.
    # The `vecbench` volume is 50 GB and these shards are 34, so how much of it
    # the arXiv snapshot and its fixture already hold decides whether this run
    # can work at all -- and finding that out by running out of space costs a
    # pod.
    todo = [n for n in sorted(want)
            if not (os.path.exists(os.path.join(args.dest, n))
                    and sha256_file(os.path.join(args.dest, n)) == want[n])]
    sizes = remote_sizes(repo_id, revision, set(todo))
    missing_size = [n for n in todo if n not in sizes]
    if missing_size:
        print(f"\nREFUSED: the pinned revision does not list {missing_size[:3]}"
              f" ({len(missing_size)} file(s)). Nothing was downloaded.",
              file=sys.stderr)
        return 1

    need = sum(sizes[n] for n in todo)
    free = shutil.disk_usage(args.dest).free
    want_free = need + int(args.headroom_gb * (1 << 30))
    print(f"to fetch : {len(todo)} shard(s), {need / (1 << 30):.2f} GiB")
    print(f"free     : {free / (1 << 30):.2f} GiB "
          f"(need {want_free / (1 << 30):.2f} GiB incl. "
          f"{args.headroom_gb} GiB headroom)")
    if free < want_free:
        print(f"\nREFUSED: {args.dest} has {free / (1 << 30):.2f} GiB free and "
              f"this needs {want_free / (1 << 30):.2f} GiB. Nothing was "
              f"downloaded. Free space on the volume, or fetch fewer shards "
              f"than the spec pins -- which changes the sampling frame and so "
              f"needs the spec changed too, not just this command.",
              file=sys.stderr)
        return 1
    print(flush=True)

    from huggingface_hub import hf_hub_download

    skipped = len(want) - len(todo)
    if skipped:
        print(f"{skipped} shard(s) already present with a matching digest")
    bad, fetched = [], 0
    for i, name in enumerate(todo, 1):
        print(f"[{i:>2}/{len(todo)}] {name}  downloading ...", flush=True)
        got_path = hf_hub_download(repo_id=repo_id, filename=name,
                                   repo_type="dataset", revision=revision,
                                   local_dir=args.dest)
        got = sha256_file(got_path)
        if got != want[name]:
            bad.append((name, want[name], got))
            print(f"          DIGEST MISMATCH\n"
                  f"            expected {want[name]}\n"
                  f"            got      {got}", flush=True)
        else:
            fetched += 1
            print("          digest ok", flush=True)

    print()
    print(f"fetched {fetched}, already present {skipped}, mismatched {len(bad)}")
    if bad:
        print("\nThe pinned revision did not produce the pinned bytes. The "
              "files are left in place; do not build on them.", file=sys.stderr)
        for name, w, g in bad:
            print(f"  {name}: expected {w}, got {g}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
