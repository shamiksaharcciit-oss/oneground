# 044c — decision and migration: `skew_top10_share` carries its k

**APPLIED, unmerged, on branch `task-044c`.** Ruled by the developer: *"skew
is a property of the corpus at k=256, so k travels with it wherever it is
published or it is not one of the five."* The four fixture YAMLs are named in
§1 below, which is the naming CLAUDE.md requires, and the diff is on the
branch for review.

**No published number moved.** Verified after applying: the three `value:`
fields and all four `tolerance:` fields are byte-unchanged, and the four specs
still parse.

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

### 3. `oneground/measures/skew.py` and `oneground/characterize.py`

**Changed from the proposal as written.** The draft inlined a dict in
`characterize`. Applied instead as `skew.reading()`, a module function beside
`skew_top10_share` — which is the shape 044 and 044b already gave the other
two, and the only shape that is testable on its own. Inlining it in the caller
would have put the third member of a family somewhere the first two are not.

`skew.reading(region_ids, n_base, n_centroids=N_CENTROIDS)` returns `value`,
`n_centroids`, `of`, `uniform_baseline`, `excess_over_uniform`,
`empty_regions`, `largest_region`, `comparable_with` and `note`.

It **omits** the `resolvable` key its two siblings carry, deliberately: there
is no threshold here to empty out, so a resolvability test would be a question
about nothing. A skew reading is never couldn't-check — it is either
comparable with another at the same count or not comparable at all — and this
project does not report an outcome it cannot mean.

`characterize_arrays` gains one line, `out["skew_reading"] = …`.
`out["skew_top10_share"]` is untouched, so every existing consumer, test and
published comparison is unaffected — the containment 044 used for
`boundary_crispness`.

### 4. The printed summary, `characterize.py:633`

Already half right — it prints `(even would be 0.039)`. It should name the
count that 0.039 comes from:

```python
-       f"   (even would be {10 / N_CENTROIDS:.3f})")
+       f"   (10 largest of {N_CENTROIDS} regions; even would be "
+       f"{10 / N_CENTROIDS:.3f})")
```

### 5. A test

`oneground/measures/test_skew_carries_its_count.py`, eight tests, named for
what they check rather than for the function. Two guard that the published
function is unchanged; the rest are about the count being present and the
comparison being refused across counts.

The one worth reading is
`test_the_uniform_baseline_does_not_make_the_two_comparable`. It asserts that
two *synthetic* even partitions at k=64 and k=256 both give
`excess_over_uniform == 1.0` — that is, the rescaling **does** work on
synthetic data — and then asserts that the reading still refuses the
comparison. That is the point: the rescaling's failure is a measured fact
about real corpora (1.19 → 3.10 on arxiv-150k), not something a synthetic
fixture can show, so the test records why it cannot be the evidence rather
than quietly passing and implying it is.

`test_the_module_records_the_range_it_was_measured_over` asserts the sweep's
range and three of its numbers are in the module docstring — because "load-
bearing" without a range is not a measurement any more than "stable" is.

## What this migration does not do

- It does not change `N_CENTROIDS`, and §"Recommendation on the fixtures' k"
  in the report argues against ever doing so.
- It does not touch `fixtures/<id>/characterization.json` or any MANIFEST.
- It does not add the k to `boundary_crispness`'s or
  `ambiguous_query_rate`'s definitions, which already carry it. The U-shape
  finding asks for something different of those two and is in the report.
