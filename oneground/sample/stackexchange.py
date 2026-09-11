"""Stratified sampling over a sharded Stack Exchange posts dump (task 016).

Source-specific, the way `arxiv.py` is. The shape of the problem is different
enough that sharing code with the arXiv reader would obscure both:

* the source is ~34 GB of parquet in 59 shards, not one 4 GB JSONL, so there
  are no byte offsets to seek back to and a second pass would re-read the
  `Body` column in full -- the chosen rows are spread across every row group,
  so nothing can be skipped.
* eligibility depends on the body, so the per-year totals a proportional quota
  needs cannot be counted without reading the expensive column anyway.

So this is **one pass** with a seeded reservoir per year. A reservoir of size R
over a year's stream is a uniform sample of that year without replacement; the
pass also counts eligible posts per year exactly, so afterwards the quotas are
computed proportionally, exactly as `arxiv.py` does, and each year's reservoir
is subsampled down to its quota. Uniform-within-year and
proportional-across-years both hold, and the source is read once. A second
counting pass is not needed and is not done: the reservoir counts as it goes.

**Nothing is stored.** The shards are never written to disk. Each is opened as
a remote file at the pinned revision and its row groups are pulled through the
reservoir over HTTP range requests, so the build's disk requirement is the
sample it writes -- roughly 150 MB -- rather than the 34 GB the dump occupies.
`sampling.reservoir_per_year` bounds the memory this holds: measured at 0.78
GiB for the shipped spec.

This works because parquet is a random-access format: the footer at the end of
the file names the row groups and the column chunks, so a reader can fetch just
the columns it wants, in the order it wants, without the bytes in between. It
is also why the shards cannot simply be piped through a hash as they arrive --
see `verify_source` for what is checked instead, and the task 016b report for
why that is a weaker receipt than arXiv's and what it still catches.

A local directory of shards is still accepted, for tests and for an offline
rebuild. Determinism does not depend on which is used: the result is fixed by
(seed, pinned revision, shard order, row order), shards are read in sorted
name order and rows in file order, and the revision pins both.

The one way the sampling can go wrong is a reservoir smaller than the quota
drawn from it, which would silently bias that year towards whatever the
reservoir happened to keep. That is checked and raises.
"""

import os
import re
from collections import Counter, defaultdict

import numpy as np

from ..receipts import manifest_digest, sha256_file

# Columns the builder needs. Body dominates the bytes read; the rest are noise
# beside it, which is why a cheap metadata-only pre-pass would not help.
COLUMNS = ["Id", "PostTypeId", "Title", "Body", "Tags", "CreationDate",
           "ContentLicense"]

QUESTION = 1          # PostTypeId: 1 = question, 2 = answer, 3+ = wiki/meta

_FENCED = re.compile(r"```.*?```", re.S)
_INDENTED = re.compile(r"(?m)^(?: {4}|\t).*$")
_HTML = re.compile(r"<[^>]+>")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WS = re.compile(r"\s+")


def clean_body(md):
    """Markdown body -> one line of prose.

    The dump is Markdown, not HTML (mikex86/stackoverflow-posts renders the
    dump's HTML to Markdown), so the rule is stated in those terms:

      1. drop fenced code blocks (``` ... ```) entirely,
      2. drop indented code blocks (four spaces or a tab at line start),
      3. keep the text of a [label](url) link and drop the url,
      4. strip any residual HTML tags,
      5. drop remaining backticks, and collapse all whitespace to single
         spaces.

    Code is removed rather than kept because it is the part of a Stack Overflow
    post least like the natural-language question the title asks, and a corpus
    whose bodies are half stack traces would be measuring the embedding
    model's behaviour on code, not on Q&A text. This is a stated rule, not a
    tuning knob: it is fixed before the build and does not change on what the
    numbers come out as.
    """
    if not md:
        return ""
    s = _FENCED.sub(" ", md)
    s = _INDENTED.sub(" ", s)
    s = _LINK.sub(r"\1", s)
    s = _HTML.sub(" ", s)
    s = s.replace("`", "")
    return _WS.sub(" ", s).strip()


def year_of(created):
    try:
        return int(str(created)[:4])
    except Exception:
        return None


def shard_paths(source):
    """Every .parquet under `source`, in sorted filename order."""
    if os.path.isfile(source):
        return [source]
    out = []
    for root, _dirs, files in os.walk(source):
        for fn in files:
            if fn.endswith(".parquet"):
                out.append(os.path.join(root, fn))
    if not out:
        raise FileNotFoundError(f"no .parquet shards under {source}")
    return sorted(out)


# --------------------------------------------------------------- the source
class SourceError(RuntimeError):
    """The pinned source does not resolve, or does not match its pins."""


def read_pinned_digests(path):
    """`{name: sha256}` from a `sha256sum -c` file, comments ignored."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                sha, name = line.split(None, 1)
            except ValueError:
                raise SourceError(
                    f"{path}:{n}: not a `<sha256>  <name>` line") from None
            if len(sha) != 64:
                raise SourceError(f"{path}:{n}: {sha!r} is not a sha256")
            out[name.strip()] = sha.lower()
    if not out:
        raise SourceError(f"{path}: no digests")
    return out


def hub_digests(repo_id, revision, names):
    """`{name: sha256}` for `names` at `revision`, from the Hub's LFS metadata.

    One API call and no file content: an LFS pointer's oid *is* the sha256 of
    the file it stands for, which is how the pinned manifest was written in the
    first place.
    """
    from huggingface_hub import HfApi
    info = HfApi().repo_info(repo_id, repo_type="dataset", revision=revision,
                             files_metadata=True)
    out = {}
    for s in info.siblings or []:
        if s.rfilename not in names:
            continue
        lfs = getattr(s, "lfs", None)
        oid = getattr(lfs, "sha256", None) or getattr(lfs, "oid", None)
        if oid:
            out[s.rfilename] = str(oid).lower()
    return out


def verify_source(spec, log=None):
    """Check the pinned revision still serves the pinned bytes.

    Returns `source.snapshot_sha256` -- the manifest digest over the pinned
    per-shard values. **Transfers no file content**, so it is safe to run
    before committing a pod to 34 GB of reading.

    What this catches: a revision that has been moved or deleted, a shard that
    has been added, removed or renamed, and a shard whose recorded sha256 no
    longer matches the one the Hub reports. What it does not catch is a
    corrupted transfer of a shard's bytes, because those bytes are never all
    read in one order -- the reader fetches only the column chunks it needs.
    arXiv's snapshot, a single file read end to end, is hashed directly and has
    no such gap. This difference is a property of the source, not a choice, and
    it is stated in the fixture spec rather than papered over.
    """
    def _say(msg):
        if log:
            log(msg)

    src = spec["source"]
    repo_id, revision = src["repo_id"], src["revision"]
    pinned = read_pinned_digests(src["shard_digests"])

    _say(f"verifying {len(pinned)} pinned shard(s) at {repo_id}@{revision[:12]}"
         " (metadata only, no file bytes)")
    try:
        actual = hub_digests(repo_id, revision, set(pinned))
    except Exception as e:                       # network, auth, gone revision
        raise SourceError(
            f"could not resolve {repo_id}@{revision}: {type(e).__name__}: {e}"
        ) from e

    missing = sorted(set(pinned) - set(actual))
    if missing:
        raise SourceError(
            f"the pinned revision no longer lists {len(missing)} shard(s), "
            f"e.g. {missing[:3]}. Nothing was read.")
    bad = {n: (pinned[n], actual[n]) for n in pinned if pinned[n] != actual[n]}
    if bad:
        first = sorted(bad)[:3]
        raise SourceError(
            f"{len(bad)} shard(s) do not match their pinned sha256, e.g. "
            + "; ".join(f"{n}: pinned {bad[n][0][:12]}, hub {bad[n][1][:12]}"
                        for n in first)
            + ". Nothing was read.")

    digest = manifest_digest(pinned)
    _say(f"source verified · snapshot_sha256 {digest}")
    return digest


def open_shards(source, spec, log=None):
    """Yield `(name, opener)` for every shard, in sorted name order.

    `opener` is a zero-argument callable returning a binary file object, so a
    remote shard is opened only when it is about to be read and closed as soon
    as it has been.
    """
    def _say(msg):
        if log:
            log(msg)

    if source:
        for p in shard_paths(source):
            yield os.path.basename(p), (lambda p=p: open(p, "rb"))
        return

    from huggingface_hub import HfFileSystem
    src = spec["source"]
    repo_id, revision = src["repo_id"], src["revision"]
    names = sorted(read_pinned_digests(src["shard_digests"]))
    fs = HfFileSystem()
    _say(f"streaming {len(names)} shard(s) from {repo_id}@{revision[:12]} "
         "-- nothing is written to disk")
    for name in names:
        path = f"datasets/{repo_id}@{revision}/{name}"
        yield name, (lambda path=path: fs.open(path, "rb"))


def local_source_digest(source):
    """Manifest digest of a local shard directory, or the file's own sha256."""
    if os.path.isfile(source):
        return sha256_file(source)
    digests = {}
    for root, _dirs, files in os.walk(source):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, source).replace(os.sep, "/")
            digests[rel] = sha256_file(full)
    if not digests:
        raise FileNotFoundError(f"source directory holds no files: {source}")
    return manifest_digest(digests)


def eligible(title, body, min_body_len):
    if not title or not str(title).strip():
        return False
    return len(body) >= min_body_len


def sample_records(source, spec, n_total, seed, log=None, receipt=None):
    """One pass, per-year reservoirs, then proportional quotas.

    `source` may be a local directory of shards, or `None` to stream them from
    the pinned revision without storing any. When streaming, the source is
    verified before a byte of content is read, and `receipt` (if given) is
    filled with `snapshot_sha256` -- the builder's source receipt, which
    otherwise has no file to hash.
    """
    def _say(msg):
        if log:
            log(msg)

    import pyarrow.parquet as pq

    # The builder hashes a local source itself and passes it down, so only
    # compute a digest that is not already in hand.
    if receipt is None or "snapshot_sha256" not in receipt:
        digest = (local_source_digest(source) if source
                  else verify_source(spec, log=log))
        if receipt is not None:
            receipt["snapshot_sha256"] = digest

    samp = spec["sampling"]
    lo, hi = samp.get("year_range", [2008, 2023])
    min_body = samp.get("min_body_chars", 200)
    body_chars = samp.get("body_chars", 500)
    reservoir = samp.get("reservoir_per_year", 60000)

    rng = np.random.default_rng(seed)
    kept = defaultdict(list)          # year -> reservoir of records
    n_seen = Counter()                # year -> eligible posts seen

    shards = list(open_shards(source, spec, log=log))
    _say(f"one pass over {len(shards)} shard(s), reservoir {reservoir:,}/year")

    for si, (name, opener) in enumerate(shards, 1):
        # Opened here and closed at the end of the block: exactly one shard is
        # ever in flight, whether it is a local file or a remote one.
        with opener() as fh:
            pf = pq.ParquetFile(fh)
            for batch in pf.iter_batches(batch_size=65536, columns=COLUMNS):
                d = batch.to_pydict()
                for i in range(batch.num_rows):
                    if d["PostTypeId"][i] != QUESTION:
                        continue
                    y = year_of(d["CreationDate"][i])
                    if y is None or not (lo <= y <= hi):
                        continue
                    title = d["Title"][i]
                    body = clean_body(d["Body"][i])[:body_chars]
                    if not eligible(title, body, min_body):
                        continue

                    n_seen[y] += 1
                    k = n_seen[y] - 1
                    rec = {
                        "id": str(d["Id"][i]),
                        "title": " ".join(str(title).split()),
                        "body": body,
                        "categories": " ".join(d["Tags"][i] or []),
                        "creation_date": str(d["CreationDate"][i])[:10],
                        # Carried per record, not assumed: Stack Exchange posts
                        # are CC BY-SA 2.5, 3.0 or 4.0 depending on when they
                        # were written, and the attribution notice has to be
                        # able to say which. The distribution over the built
                        # sample is published in the fixture's findings.
                        "content_license": d["ContentLicense"][i] or "",
                    }
                    if k < reservoir:
                        kept[y].append(rec)
                    else:
                        # Standard reservoir replacement, drawn from the same
                        # rng so the whole pass is one seeded stream.
                        j = int(rng.integers(0, k + 1))
                        if j < reservoir:
                            kept[y][j] = rec
        _say(f"  shard {si}/{len(shards)} {name}: "
             f"{sum(n_seen.values()):,} eligible so far")

    total = sum(n_seen.values())
    if total == 0:
        raise ValueError(f"no eligible posts found under {source}")
    _say(f"eligible: {total:,} questions across {len(n_seen)} years")

    # Proportional quota per year, largest-remainder rounding -- the same rule
    # and the same rounding as arxiv.py, so the two fixtures are comparable.
    raw = {y: n_total * n / total for y, n in n_seen.items()}
    quotas = {y: int(v) for y, v in raw.items()}
    rem = n_total - sum(quotas.values())
    for y in sorted(raw, key=lambda y: raw[y] - int(raw[y]), reverse=True)[:rem]:
        quotas[y] += 1

    short = {y: (quotas[y], len(kept[y]))
             for y in quotas if quotas[y] > len(kept[y])}
    if short:
        raise ValueError(
            "reservoir_per_year is too small to fill the quota for "
            f"{sorted(short)}: (quota, reservoir) = {short}. Raise "
            "sampling.reservoir_per_year; do not lower the quota, which would "
            "bias those years towards whatever the reservoir happened to keep.")

    chosen = []
    for y in sorted(kept):
        pool = kept[y]
        idx = rng.choice(len(pool), size=quotas[y], replace=False)
        idx.sort()
        chosen.extend(pool[i] for i in idx)

    rng.shuffle(chosen)
    return chosen
