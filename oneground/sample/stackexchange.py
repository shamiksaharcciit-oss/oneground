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
proportional-across-years both hold, and the file is read once.

The one way this can go wrong is a reservoir smaller than the quota drawn from
it, which would silently bias that year towards whatever the reservoir happened
to keep. That is checked and raises.

Determinism: the result is fixed by (seed, pinned dataset revision, shard
order, row order). Shards are read in sorted filename order and rows in file
order, both of which the revision pins.
"""

import os
import re
from collections import Counter, defaultdict

import numpy as np

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


def eligible(title, body, min_body_len):
    if not title or not str(title).strip():
        return False
    return len(body) >= min_body_len


def sample_records(source, spec, n_total, seed, log=None):
    """One pass, per-year reservoirs, then proportional quotas."""
    def _say(msg):
        if log:
            log(msg)

    import pyarrow.parquet as pq

    samp = spec["sampling"]
    lo, hi = samp.get("year_range", [2008, 2023])
    min_body = samp.get("min_body_chars", 200)
    body_chars = samp.get("body_chars", 500)
    reservoir = samp.get("reservoir_per_year", 60000)

    rng = np.random.default_rng(seed)
    kept = defaultdict(list)          # year -> reservoir of records
    n_seen = Counter()                # year -> eligible posts seen

    paths = shard_paths(source)
    _say(f"one pass over {len(paths)} shard(s), reservoir {reservoir:,}/year")

    for si, path in enumerate(paths, 1):
        pf = pq.ParquetFile(path)
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
                    # were written, and the attribution notice has to be able
                    # to say which. The distribution over the built sample is
                    # published in the fixture's findings.
                    "content_license": d["ContentLicense"][i] or "",
                }
                if k < reservoir:
                    kept[y].append(rec)
                else:
                    # Standard reservoir replacement, drawn from the same rng
                    # so the whole pass is one seeded stream.
                    j = int(rng.integers(0, k + 1))
                    if j < reservoir:
                        kept[y][j] = rec
        _say(f"  shard {si}/{len(paths)}: {sum(n_seen.values()):,} eligible so far")

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
