"""Stratified sampling over the arXiv metadata snapshot.

Source-specific, and the reason the arxiv-150k fixture is reproducible: two
passes over a 4 GB JSONL file, stratified by year in proportion to volume,
uniform within year, everything seeded.

Moved from corpora/build_fixture.py **unchanged in logic** in task 007. The
two-pass structure is deliberate and is not an optimisation to tidy away: pass
one records byte offsets only, so the 4 GB snapshot is never held in memory on
a 7.6 GB laptop, and pass two seeks to just the chosen records.
"""

import json
from collections import Counter, defaultdict

import numpy as np


def year_of(update_date):
    try:
        return int(update_date[:4])
    except Exception:
        return None


def primary_category(cats):
    return (cats or "").split()[0] if cats else None


def eligible(rec, min_abs_len):
    ab = rec.get("abstract") or ""
    if len(ab.strip()) < min_abs_len:
        return False
    if not rec.get("categories") or not rec.get("update_date"):
        return False
    if ab.strip().lower().startswith("this paper has been withdrawn"):
        return False
    return year_of(rec["update_date"]) is not None


def sample_records(source, spec, n_total, seed, log=None):
    """Stratified by year in proportion to volume, uniform within year."""
    def _say(msg):
        if log:
            log(msg)

    rng = np.random.default_rng(seed)
    years = spec["sampling"].get("year_range", [2007, 2025])
    lo, hi = years

    _say("pass 1: scanning source for eligible records")
    offsets_by_year = defaultdict(list)
    with open(source, "rb") as f:
        while True:
            off = f.tell()
            line = f.readline()
            if not line:
                break
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if not eligible(rec, 200):
                continue
            y = year_of(rec["update_date"])
            if lo <= y <= hi:
                offsets_by_year[y].append(off)

    total_elig = sum(len(v) for v in offsets_by_year.values())
    _say(f"eligible: {total_elig:,} records across {len(offsets_by_year)} years")

    # proportional quota per year, largest-remainder rounding
    quotas = {}
    raw = {y: n_total * len(v) / total_elig for y, v in offsets_by_year.items()}
    for y in raw:
        quotas[y] = int(raw[y])
    rem = n_total - sum(quotas.values())
    for y in sorted(raw, key=lambda y: raw[y] - int(raw[y]), reverse=True)[:rem]:
        quotas[y] += 1

    chosen = []
    for y in sorted(offsets_by_year):
        offs = np.asarray(offsets_by_year[y])
        pick = rng.choice(offs, size=min(quotas[y], len(offs)), replace=False)
        chosen.extend(pick.tolist())
    chosen.sort()

    _say("pass 2: reading selected records")
    records = []
    with open(source, "rb") as f:
        for off in chosen:
            f.seek(off)
            rec = json.loads(f.readline())
            records.append({
                "id": rec["id"],
                "title": " ".join(rec["title"].split()),
                "abstract": " ".join(rec["abstract"].split()),
                "categories": rec["categories"],
                "update_date": rec["update_date"],
            })
    rng.shuffle(records)
    return records


def split_queries(records, n_queries, seed, hot_share=0.05,
                  cat_field="categories"):
    """1/2 uniform, 1/2 from the top hot_share categories by volume.

    `cat_field` is the record key holding the category label -- `categories`
    for arXiv, and whatever the spec's `source.field_map` says for another
    source. The records are never renamed; see `oneground.sample.fields`.

    Half the queries come from the busiest categories on purpose: a query set
    drawn uniformly would under-represent exactly the traffic that stresses a
    partition, and the fixture would flatter semantic sharding.
    """
    rng = np.random.default_rng(seed)
    counts = Counter(primary_category(r[cat_field]) for r in records)
    n_hot_cats = max(1, int(len(counts) * hot_share))
    hot = {c for c, _ in counts.most_common(n_hot_cats)}
    idx = np.arange(len(records))
    hot_idx = np.array([i for i in idx
                        if primary_category(records[i][cat_field]) in hot])
    n_hot = n_queries // 2
    q_hot = rng.choice(hot_idx, size=n_hot, replace=False)
    rest = np.setdiff1d(idx, q_hot)
    q_uni = rng.choice(rest, size=n_queries - n_hot, replace=False)
    q = np.concatenate([q_hot, q_uni])
    rng.shuffle(q)
    qset = set(q.tolist())
    base = [r for i, r in enumerate(records) if i not in qset]
    queries = [records[i] for i in q]
    return base, queries, sorted(hot)
