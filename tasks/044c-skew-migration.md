# 044c — decision and migration: `skew_top10_share` carries its k

**For the developer to rule.** Nothing in this file has been applied. It
touches a published value's *meaning*, which is why it is brought rather than
done.

## The decision

> **`skew_top10_share` as published is not a property of the corpus. It is a
> property of the corpus at k=256.** Either k is reported beside it as part of
> the measure, or it should not be reported as one of the five.

**Recommended: report k beside it.** The alternative — dropping it — would
remove the only capacity-side measure of the five, and the measurement is not
wrong. It is unlabelled.

## Why this one and not the other two

The sweep's stability bands, measured over k ∈ [16, 4096] on both fixtures
whose vectors are local, using the ±0.02 tolerance each published value
carries:

| reading | band, shipped code | band, k isolated | factor |
|---|---|---|---|
| `boundary_crispness` | k ∈ [32, 2048] | k ∈ [32, 2048] | 64× |
| `ambiguous_query_rate` | k ∈ [128, 1024] | k ∈ [256, 1024] | 8× / **4×** |
| `skew_top10_share` | **k = 256 only** | **k = 256 only** | **1×** |

Unanimous across both fixtures and both arms: skew leaves tolerance at the
first step in either direction. Over the full sweep it spans 0.0076 to 0.7465
on arXiv — a factor of 98 — against a published value of 0.075.

**The obvious rescaling is refuted, not untried.** Dividing by the uniform
baseline 10/k does not make it k-invariant: on arXiv `skew/(10/k)` climbs
1.19 → 1.36 → 1.55 → 1.59 → 1.93 → 1.83 → 2.27 → 2.77 → 3.10 across the
sweep, a 2.6× climb of its own. There is no normalisation that rescues the
number; the k has to be visible.

**And the definition is the only one of the three that omits it.** All four
fixture specs, identically:

    boundary_crispness   "...exceeds 1.20 x their nearest centroid distance,
                          under k-means with 256 centroids"     names k
    ambiguous_query_rate "...against the same centroids"        inherits k
    skew_top10_share     "share of base vectors in the 10
                          largest centroid regions"             SILENT

The measure that is 98× sensitive to k is the one whose published definition
never mentions it. That is the defect, and it is a labelling defect.

## The migration

**No published number moves.** 0.075 (arxiv-150k), 0.069 (stackexchange-150k)
and 0.089 (sec-filings-10k) all stand, unchanged, at the same tolerance. The
sweep reproduces each of them at k=256 to the last published digit. What
changes is what the number says it is.

**Nothing under `fixtures/<id>/` is touched.** Adding a field to
`characterization.json` would change its sha256, which would change
`MANIFEST.sha256`, which would make `oneground fixture verify` contradict on
every installed copy and every release asset. The migration is confined to the
spec prose, the docs, and the reporting layer.

### 1. Four fixture specs — the definition string

`fixtures/arxiv-150k.fixture.yaml:132`,
`fixtures/stackexchange-150k.fixture.yaml:236`,
`fixtures/sec-filings-10k.fixture.yaml:593`,
`fixtures/arxiv-smoke.fixture.yaml:112`. Identical text in all four:

```yaml
  skew_top10_share:
-   definition: share of base vectors in the 10 largest centroid regions
+   definition: >
+     Share of base vectors in the 10 largest centroid regions, under k-means
+     with 256 centroids — the same centroids crispness and ambiguity use.
+     The count is part of the definition and not a detail of it: measured
+     over k from 16 to 4096 (task 044c) this value spans 0.008 to 0.747 on
+     arxiv-150k, and it leaves the +/-0.02 tolerance at the first step in
+     either direction from 256. An even partition would put 10/256 = 0.039
+     here.
    value: 0.075
    tolerance: 0.02
```

Per CLAUDE.md, a fixture YAML is edited only when a brief names the file and
the change. This section is that naming, for the developer to authorise.

### 2. `docs/FIXTURES.md:69`

```
- skew is the share of
- base vectors in the 10 largest regions;
+ skew is the share of base vectors in the 10 largest of the 256 regions —
+ the centroid count is part of this definition, and task 044c measured that
+ this is the one of the five that holds no tolerance away from it;
```

### 3. `oneground/characterize.py` — the reported dict

`skew_top10_share` becomes a reading with its parameter beside it, the same
shape 044 gave crispness. A user's own workdir, not a published fixture:

```python
out["skew_top10_share"] = skew_top10_share(r_b[:, 0], len(base))
out["skew_reading"] = {
    "value": out["skew_top10_share"],
    "n_centroids": N_CENTROIDS,
    "uniform_baseline": 10.0 / N_CENTROIDS,
    "excess_over_uniform": out["skew_top10_share"] / (10.0 / N_CENTROIDS),
    "note": ("the share of vectors in the 10 largest of %d regions. The "
             "region count is part of this reading, not a setting behind "
             "it: 10 regions of 4096 is a different question from 10 of "
             "256, and the value is not comparable across counts. Measured "
             "in task 044c: this is the only one of the five measures with "
             "no tolerance band in the centroid count."
             % N_CENTROIDS),
}
```

`out["skew_top10_share"]` is left exactly as it is, so every existing
consumer, test and published comparison is unaffected — the same containment
044 used for `boundary_crispness`.

### 4. The printed summary, `characterize.py:633`

Already half right — it prints `(even would be 0.039)`. It should name the
count that 0.039 comes from:

```python
-       f"   (even would be {10 / N_CENTROIDS:.3f})")
+       f"   (10 largest of {N_CENTROIDS} regions; even would be "
+       f"{10 / N_CENTROIDS:.3f})")
```

### 5. A test

`skew_top10_share` at two different k on the same region assignment must not
be compared — a test that asserts the reading carries `n_centroids` and that
the value at k=256 is the published one, named for what it checks rather than
for the function.

## What this migration does not do

- It does not change `N_CENTROIDS`, and §"Recommendation on the fixtures' k"
  in the report argues against ever doing so.
- It does not touch `fixtures/<id>/characterization.json` or any MANIFEST.
- It does not add the k to `boundary_crispness`'s or
  `ambiguous_query_rate`'s definitions, which already carry it. The U-shape
  finding asks for something different of those two and is in the report.
