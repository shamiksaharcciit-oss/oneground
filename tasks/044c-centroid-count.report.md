# Report: 044c-centroid-count

## The third constant is the worst of the three

**Leading, because it is the answer and it is not the one the brief expected
either way.**

`N_CENTROIDS = 256` is neither load-bearing-everywhere nor incidental. It is
all three at once, and which it is depends on which measure you ask:

| reading | stays inside its ±0.02 tolerance over | factor |
|---|---|---|
| `boundary_crispness` | k ∈ [32, 2048] | **64×** |
| `ambiguous_query_rate` | k ∈ [256, 1024], k isolated | **4×** |
| `skew_top10_share` | k = 256 | **1×** |

**`skew_top10_share` holds no tolerance in either direction.** One step down
to k=128 and it is 0.1246 against a published 0.0754; one step up to k=512 and
it is 0.0357. Over the swept range it spans 0.0076 to 0.7465 on arXiv — a
factor of 98 — and the result is unanimous: both fixtures, both arms, every
step.

That is the third constant under *"Definitions, not parameters"* and it is the
worst case of the three. The first two carried thresholds calibrated to one
embedding; **this one has no meaning at all away from one arbitrary k.**
1.20 and 1.10 at least denote something fixed — a ratio of two distances —
that a different corpus can be asked about. "The ten largest regions" denotes
nothing until you say ten of how many, and 10 of 4096 is not a weaker version
of 10 of 256, it is a different question.

So, plainly: **`skew_top10_share` as published is not a property of the
corpus. It is a property of the corpus at k=256.** Either k is reported beside
it as part of the measure, or it should not be reported as one of the five.
The decision and the migration are in
[`tasks/044c-skew-migration.md`](044c-skew-migration.md) — recommended:
report k beside it; no published number moves; nothing under `fixtures/`
is touched.

**The obvious rescaling is refuted rather than untried.** Dividing by the
uniform baseline 10/k does not make it k-invariant — `skew/(10/k)` on arXiv
climbs 1.19, 1.36, 1.55, 1.59, 1.93, 1.83, 2.27, 2.77, 3.10 across k = 16 to
4096. There is no normalisation that rescues the number.

And the definition is the only one of the three that omits its own k. All four
specs: crispness says *"under k-means with 256 centroids"*, ambiguity says
*"against the same centroids"*, skew says *"share of base vectors in the 10
largest centroid regions"* and stops. **The measure that is 98× sensitive to
the count is the one whose published definition never names it.**

## Repo state expected vs found

| expected | found |
|---|---|
| `tasks/044c-centroid-count.md` on `main` | yes; branched `task-044c` from `8c07b4b` |
| 042d landed (the brief's precondition) | yes — `tasks/042d-shards-refusal.report.md`, merged |
| `crispness.py` declares the three constants as described | yes, with one difference below |
| `arxiv-150k` and `stackexchange-150k` vectors local | yes, `C:\Users\polo2\oneground-assets\` |
| `sec-filings-10k` vectors local | **no**, as the brief predicted — only `documents.jsonl.zst` |

One difference from the brief's quotation. The brief quotes

```python
# Definitions, not parameters. See the module docstring in measures/__init__.
N_CENTROIDS = 256
CRISP_RATIO = 1.20
```

Task 044 moved `CRISP_RATIO` out from under that comment and gave it its own,
so what is in the file today is a **plural comment standing over a single
constant**, with the plural claim now living one module up in
`measures/__init__.py`. That matters for the position on the comment and is
taken up there.

## What was done

A sweep of `N_CENTROIDS` over k ∈ {16, 32, 64, 128, 256, 512, 1024, 2048,
4096} — 256 bracketed 16× each way — on both fixtures whose vectors are on
this machine, in **two arms**, measuring `boundary_crispness`,
`ambiguous_query_rate`, their threshold percentiles and resolvability, the
base and query ratio distributions, and `skew_top10_share`.

Scripts: `tasks/scratch/044c_centroid_sweep.py` (the sweep),
`044c_table.py`, `044c_skew.py`, `044c_compare.py`, `044c_pure_k.py`,
`044c_band_edge.py`. All import project code unmodified.

Outputs: `runs/044c/*.json`. `runs/` is gitignored by project rule, so the
four sweep JSONs are also copied to `tasks/044c-centroid-count.sweep/` and
verified there by sha256 — rule 9, because every number below is cited from
them. The copies are byte-identical to the run outputs.

**Two digests per file, because one of them would have been misleading.** git
normalises CRLF to LF on `add`, so the sha256 of the copy I verified is not
the sha256 a fresh clone produces:

| file | as written (CRLF) | as committed (LF) |
|---|---|---|
| `arxiv-150k.default.json` | `5d723d7dcd5eb5d2…` | `b91eaeff675564cb…` |
| `arxiv-150k.allpts.json` | `663e09cb772347c8…` | `e0a165d721d34cc4…` |
| `stackexchange-150k.default.json` | `3f6552dbf61ac3ce…` | `3298ad9a7efc9e37…` |
| `stackexchange-150k.allpts.json` | `f1b081b424bf1be6…` | `bb90f059cad1f6e0…` |

The first column proves the copy matches the run that produced it; the second
is what a reader can check. Recording only the first would have been a digest
nobody else could reproduce — the failure mode rule 9 exists to prevent,
arriving by a route rule 9 does not mention.

### The second arm, which nobody briefed, and without which none of this reads

**`kmeans` never held the training set fixed, and nothing in the project
recorded that.** faiss's `Kmeans` defaults to `max_points_per_centroid = 256`,
so `kmeans(base, k, seed)` trains on `min(n, 256k)` vectors, not on `n`.

At the published k=256 on a 150,000-vector fixture that is **65,536 of
150,000 — 44% of the corpus.** Every published `boundary_crispness`,
`ambiguous_query_rate`, `skew_top10_share` and drift pair in this project was
computed against centroids trained on a subsample, and the crossover above
which all vectors train is k = 586.

So a sweep of k below 586 varies two things at once, and the region of the
sweep where the readings move most is exactly the region where the training
set is smallest. The sweep as briefed would have been **uninterpretable**: I
could not have told a k effect from a sample effect anywhere below 586, which
includes the published point.

The second arm raises `max_points_per_centroid` so every vector trains. It is
a copy of `cr.kmeans` in the scratch script, not a change to the module.

**The control's answer is that it moves nothing at the published settings**,
which is the right answer:

| at k=256 | shipped (65,536 train) | control (150,000 train) | move |
|---|---|---|---|
| arxiv crispness | 0.0362 | 0.0365 | +0.0003 |
| arxiv ambiguity | 0.8915 | 0.8935 | +0.0020 |
| arxiv skew | 0.0754 | 0.0710 | −0.0044 |
| stackexchange crispness | 0.0114 | 0.0113 | −0.0001 |
| stackexchange ambiguity | 0.9085 | 0.9020 | −0.0065 |
| stackexchange skew | 0.0694 | 0.0730 | +0.0036 |

All six inside tolerance; the largest is skew's 0.0065, and skew is the most
subsample-sensitive of the three as well as the most k-sensitive.

**The not-knowing is the finding.** The published values do not rest on the
subsample — but nobody knew they were computed on one, and it took an arm the
brief did not ask for to establish it. A sweep of a constant cannot be read
unless you know what else that constant is silently setting, and here the
constant was setting the training-set size through a library default three
layers down.

It also changed a number. **Isolating k narrows arXiv's ambiguity band from
8× to 4×**: at k=128 the shipped arm reads −0.0050 from its anchor and the
controlled arm reads −0.0205, outside. The shipped arm's wider band is partly
the shrinking training set compensating for the falling k. Both figures are
reported, together, neither alone — 039's rule — because they answer different
questions: 8× is what the shipped code does as k varies, 4× is what k does.

## Measurements

Every number below is from `tasks/044c-centroid-count.sweep/*.json`, computed
by `oneground.measures` unmodified, on vectors whose **array sha256 was
checked against the fixture spec before use**: `cb973a94…` = arxiv
`vectors_sha256`, `16e0f488…` = arxiv `queries_sha256`, and the stackexchange
pair likewise. These are the published arrays, not a re-derivation.

### The anchor reproduces, which is what makes the rest comparable

| at k=256 | published | swept | Δ |
|---|---|---|---|
| arxiv `boundary_crispness` | 0.036273 | 0.0362 | 0.00007 |
| arxiv `ambiguous_query_rate` | 0.8915 | 0.8915 | 0.0000 |
| arxiv `skew_top10_share` | 0.0754 | 0.0754 | 0.0000 |
| arxiv crisp threshold percentile | 96.37 | 96.3726 | 0.0026 |
| stackexchange `boundary_crispness` | 0.0115 | 0.0114 | 0.0001 |
| stackexchange `ambiguous_query_rate` | 0.908 | 0.9085 | 0.0005 |
| stackexchange `skew_top10_share` | 0.069373 | 0.0694 | 0.00003 |
| stackexchange crisp threshold percentile | 98.83 | 98.8296 | 0.0004 |

### arxiv-150k, shipped code

| k | n_train | crisp | Δ256 | pct | σ | ambig | Δ256 | pct | σ | med | p95 | skew | 10/k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | 4,096 | 0.1430 | **+0.1068** | 85.69 | 158 | 0.6835 | **−0.2080** | 68.44 | 30 | 1.0895 | 1.2507 | 0.7465 | 0.6250 |
| 32 | 8,192 | 0.0461 | +0.0099 | 95.38 | 85 | 0.8315 | **−0.0600** | 83.19 | 20 | 1.0642 | 1.1967 | 0.4262 | 0.3125 |
| 64 | 16,384 | 0.0369 | +0.0006 | 96.31 | 76 | 0.8640 | **−0.0275** | 86.35 | 18 | 1.0595 | 1.1876 | 0.2421 | 0.1562 |
| 128 | 32,768 | 0.0394 | +0.0032 | 96.06 | 79 | 0.8865 | −0.0050 | 88.76 | 16 | 1.0554 | 1.1892 | 0.1246 | 0.0781 |
| **256** | 65,536 | **0.0362** | — | 96.37 | 75 | **0.8915** | — | 89.27 | 16 | 1.0539 | 1.1858 | **0.0754** | 0.0391 |
| 512 | 131,072 | 0.0347 | −0.0016 | 96.53 | 73 | 0.9035 | +0.0120 | 90.43 | 15 | 1.0535 | 1.1830 | 0.0357 | 0.0195 |
| 1024 | 150,000 | 0.0407 | +0.0044 | 95.93 | 80 | 0.8985 | +0.0070 | 89.97 | 15 | 1.0558 | 1.1897 | 0.0222 | 0.0098 |
| 2048 | 150,000 | 0.0529 | +0.0167 | 94.71 | 92 | 0.9145 | **+0.0230** | 91.49 | 14 | 1.0624 | 1.2032 | 0.0135 | 0.0049 |
| 4096 | 150,000 | 0.0810 | **+0.0447** | 91.91 | 115 | 0.9165 | **+0.0250** | 91.79 | 14 | 1.0747 | 1.2306 | 0.0076 | 0.0024 |

### stackexchange-150k, shipped code

| k | n_train | crisp | Δ256 | pct | σ | ambig | Δ256 | pct | σ | med | p95 | skew |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | 4,096 | 0.0009 | −0.0105 | 99.65 | 12 | 0.9500 | **+0.0415** | 95.02 | 10 | 1.0364 | 1.1264 | 0.7004 |
| 32 | 8,192 | 0.0035 | −0.0079 | 99.53 | 23 | 0.9330 | **+0.0245** | 93.36 | 12 | 1.0396 | 1.1357 | 0.4305 |
| 64 | 16,384 | 0.0117 | +0.0002 | 98.80 | 42 | 0.9080 | −0.0005 | 90.87 | 14 | 1.0415 | 1.1504 | 0.2373 |
| 128 | 32,768 | 0.0099 | −0.0015 | 99.01 | 39 | 0.9025 | −0.0060 | 90.29 | 15 | 1.0416 | 1.1454 | 0.1214 |
| **256** | 65,536 | **0.0114** | — | 98.83 | 42 | **0.9085** | — | 90.87 | 14 | 1.0425 | 1.1501 | **0.0694** |
| 512 | 131,072 | 0.0135 | +0.0021 | 98.62 | 45 | 0.9130 | +0.0045 | 91.39 | 14 | 1.0453 | 1.1548 | 0.0421 |
| 1024 | 150,000 | 0.0160 | +0.0045 | 98.39 | 49 | 0.9190 | +0.0105 | 91.92 | 13 | 1.0476 | 1.1573 | 0.0216 |
| 2048 | 150,000 | 0.0236 | +0.0121 | 97.63 | 60 | 0.9245 | +0.0160 | 92.41 | 13 | 1.0548 | 1.1690 | 0.0125 |
| 4096 | 150,000 | 0.0455 | **+0.0340** | 95.45 | 85 | 0.9360 | **+0.0275** | 93.63 | 12 | 1.0669 | 1.1951 | 0.0083 |

Control arm (k ≤ 512, all 150,000 training; above 586 the arms coincide):
`tasks/044c-centroid-count.sweep/*.allpts.json`.

### Question 1 — does either reading change materially with the count?

Material as the brief defines it: more than the ±0.02 published tolerance.

**Yes, all three, and by very different margins.** Bands, contiguous and
centred on 256:

| | arxiv shipped | arxiv k-isolated | stackexchange shipped | stackexchange k-isolated |
|---|---|---|---|---|
| crispness | [32, 2048] 64× | [32, 2048] 64× | [16, 2048] 128× | [16, 2048] 128× |
| ambiguity | [128, 1024] 8× | **[256, 1024] 4×** | [64, 2048] 32× | [32, 1024] 32× |
| skew | **[256] 1×** | **[256] 1×** | **[256] 1×** | **[256] 1×** |

The binding case is the tighter corpus: crispness 64×, ambiguity 4×, skew 1×.

**One caveat on the criterion, which the brief fixed and I am reporting by
rather than around.** The ±0.02 tolerance is uniform across all five measures
and all fixtures, and stackexchange's published crispness is **0.0115 — less
than the tolerance itself.** A stackexchange crispness of exactly 0.0000 would
pass `fixture verify`. That is why its band reads 128×: at k=16 the measured
value is 0.0009, a 13-fold collapse, and it passes. So stackexchange's wide
crispness band is evidence that the criterion is weak there, **not** evidence
that the measure is stable. arXiv's 0.036 is 1.8× its tolerance and
sec-filings' 0.107 is 5.4×; stackexchange's is 0.58×. The 64× figure from
arXiv is the one with teeth.

### Question 2 — is there a count at which either degenerates?

**No.** `crispness.distinguishable` — the 044b standard-error test, used as
the brief requires rather than a fourth criterion — returns resolvable at
every k, on both sides, on both fixtures, in both arms. **60 of 60 readings**
(30 rows × 2).

The minimum margin over the whole sweep is **σ = 10.3**, stackexchange
ambiguity at k=16, against the 3.0 floor. Crispness's minimum is σ = 11.1,
stackexchange at k=16 in the control arm, where the value is 0.0008 — about
120 vectors of 150,000, still 11σ from zero because n is large. There are **no empty regions
at any k** on either corpus, and the largest region falls monotonically from
16,488 to 120.

Degeneracy would be reachable — crispness → 1 as k → n, since every vector
approaches its own centroid — but not inside a range this corpus supports.
faiss's own floor (`min_points_per_centroid = 39`) puts the ceiling at
k = 3,846 for a 150,000-vector corpus, and it warned at k=4096 on both
fixtures. **So the k=4096 row is the one row in this report taken past a
limit the library names**, and it is marked wherever it is used. k=2048 is
not: 73 points per centroid, comfortably above the floor.

### The U-shape, and what it means for the teaser

**arXiv's crispness is not monotone in k. It is U-shaped, with its minimum at
k = 512.**

    k        16      32      64     128     256     512    1024    2048    4096
    crisp  0.1430  0.0461  0.0369  0.0394  0.0362  0.0347  0.0407  0.0529  0.0810
                                            ^published        minimum at 512 ^

The published 0.036 sits one step to the left of the least-crisp
configuration in the whole range. At k=2048 — inside faiss's floor, no
caveat — crispness is **0.0529, 46% higher than published**, and at k=4096 it
is 0.0810, more than double.

The base ratio distribution does the same thing, which is the mechanism: its
median runs 1.0895 → 1.0535 (k=512) → 1.0747. At small k the centroids are
far apart relative to the data's own spacing, so a vector near one sits
clearly inside it; at intermediate k the centroid spacing matches the scale at
which these vectors concentrate, and the ratios squeeze toward 1; at large k
the centroids begin to resolve individual vectors and the ratios open out
again. 256 sits at the bottom of that valley.

**So the teaser's headline figure is not arXiv's crispness. It is arXiv's
crispness at one k, chosen before anyone measured that the choice mattered,
and it happens to be near the minimum of the curve.** The fixture's own
finding `no_crisp_boundaries` — *"under k-means with 256 centroids this
embedding space has almost no crisp region boundaries"* — is correctly
qualified in its own text; what is not qualified is the 0.036 as it travels.

This needs the same treatment as skew: **k beside the number wherever it is
published.** Crispness's definition already carries it in the four specs, so
the gap is downstream — the teaser caption, the report renderer, and any
prose that quotes 0.036 without the clause. Unlike skew this is not a
migration, because nothing about the value's meaning is missing from its
definition; it is a propagation.

Stackexchange has no U: its crispness rises monotonically, 0.0009 → 0.0455.
**The two corpora respond to k in different shapes**, which is itself the
reason no single k can be argued as correct from the data.

### Recommendation on the fixtures' k: do not change it

Asked for as an argument rather than an assumption. I agree with not changing
it, and the reason is not that changing it would be disruptive.

**1. There is no k to move to.** For skew, no k is better than any other — the
measure is k-relative wherever you stand. For crispness and ambiguity, 256 is
already inside both stable bands (64× and 4×), so it is not a poor choice on
the axis the sweep measures. A move would buy nothing measurable.

**2. Choosing k to improve a reading is rule 3 inverted.** The only k the
sweep suggests is k=512, the crispness minimum — and "pick the k where the
number is smallest" is selecting a parameter to make a finding come out. The
same objection kills k=2048, where crispness is 46% higher and the corpus
looks better partitioned.

**3. A per-corpus k is the self-reference 044 already refused.** 044 turned
down a corpus-derived crispness threshold because it makes the measure
self-referential and two corpora measured that way cannot be compared. A
corpus-derived centroid count has exactly that defect one level up, and the
sweep shows it would be worse: the two corpora's crispness curves have
different shapes, so a rule that picked k per corpus would pick different
points of different curves.

**4. 256 has one non-arbitrary property nothing else has: everything is
already measured at it.** Every published value, every ground view's `ratio`
column, the teaser, `PUBLISHED_CRISP_PERCENTILES`,
`PUBLISHED_AMBIGUITY_PERCENTILES`, and the `centroids=256` semantic-sharded
reference configuration. `docs/FIXTURES.md` argues that a frozen value's worth
is that it is an unmoving thing to be checked against; k is upstream of every
one of those frozen values, so moving it un-freezes all of them at once.

**5. The defect is invisibility, not wrongness, and relabelling fixes exactly
that.** Re-measurement fixes none of it — a fixture at k=512 with the count
still absent from skew's definition has the identical defect.

**The one thing that would change this answer** is a purpose 256 was never
chosen for: if the project ever wanted the k that best *discriminates between*
corpora, that is a different question, and the sweep says it is answerable
only with more corpora than three. `docs/FIXTURES.md` already records the
thin-reference limit; this is a second use for the same fourth and fifth
fixture.

### The comparison survives; its effect size does not

Crispness exists to say one corpus has more boundary structure than another,
so the sweep's real test is whether the comparison survives k.

**It does. The ordering never flips at any k**: arXiv is crisper than
stackexchange at all nine counts, and stackexchange is more ambiguous than
arXiv at all nine. That is the most reassuring result in this report and it is
worth stating as loudly as the failures.

But the effect size is not stable. arxiv/stackexchange crispness runs **156.6×
at k=16, 3.17× at k=256, 1.78× at k=4096** — monotonically collapsing. The
sentence "arXiv is crisper than stackexchange" survives any k; the sentence
"arXiv is three times crisper than stackexchange" is true only near 256.

### The brief's hypothesis, measured: k is one level down

The brief asked whether 256 being a parameter would make 044 and 044b symptoms
of something one level down. It is, and here is the size of it.

044's remedy was to report the ratio **distribution** rather than a count,
because the count depends on the embedding. But the distribution is computed
against the k-means, so k is upstream of the remedy:

| what moves the arXiv base ratio median | by |
|---|---|
| bge-base → e5-base-v2 (task 036, the move that motivated 044) | 1.1035 → 1.0565 = **0.047** |
| k = 512 → k = 16 (this sweep, same embedding) | 1.0535 → 1.0895 = **0.036** |

and on p95, 0.116 for the embedding against 0.068 for k. **Changing the
centroid count moves the distribution about three-quarters as far as changing
the embedding did.**

*The comparison is of magnitudes, not of a shared baseline:* 036's pair was
measured on its own subsample — its bge count is 0.1487 against this corpus's
published 0.036 — so the two rows are not two readings of one quantity. What
is comparable is how far each intervention moves the median of the same kind
of distribution, and those are the same order.

So 044's fix is itself a reading taken at one k — the
same relationship the fix established between the count and the distribution,
one level up. Same order of magnitude, not the same size, and it is measured
rather than argued.

## The position on the comment: three for three

**Required either way, and the answer here is not benign, which makes the
comment's cost easier to see rather than harder.**

Three constants sat under one line reading *"Definitions, not parameters"*.
All three are parameters. Two were established as such by tasks that went
looking for that class of defect; the third went unexamined **through both of
those tasks**, and it is the one whose reading collapses fastest.

The comment is the finding, and it is a finding whichever way the sweep
landed. **A comment that stopped a question being asked is a defect even when
the answer is benign** — the cost was the two tasks that did not ask. Here it
is worse than that: the unasked question was upstream of both asked ones, so
044 and 044b each built a remedy on a foundation neither checked.

### What the comment actually did

It did not assert something false that a reader could check. It asserted
something **unfalsifiable as written** — a classification, with no statement
of what would refute it. "Definition, not parameter" reads as a fact about the
constant's nature. It is not one. Whether a constant is a parameter is a
question about whether the published reading is a function of it, and that is
a **measurement** — one no one had taken for any of the three.

That is why review never caught it and never could. There is nothing in the
line to disagree with. You can only disagree with it by running a sweep, and
the line is precisely what tells a reader that running one would be
pointless. **A classification with no falsifier attached does not merely fail
to invite the question; it forecloses it**, which is what happened twice.

### The state it is in now is worse than the state the brief quotes

Task 044 gave `CRISP_RATIO` its own docstring and left the plural comment
standing over `N_CENTROIDS` alone:

```python
# Definitions, not parameters. See the module docstring in measures/__init__.
N_CENTROIDS = 256
```

and the module docstring it points at still reads, unchanged since before 044:

> The ratios 1.20 and 1.10, and the centroid count 256, are the definitions
> themselves rather than parameters to tune: change one and the published
> fixture values stop meaning what they say.

**Two tasks reclassified two of those three, and neither touched the sentence
that classifies all three.** The pointer now leads from the one constant still
under the claim to a statement that is false about the other two. A reader
following `crispness.py:52` today arrives at worse information than a reader
who followed it before 044.

### And the project already treats this number as a parameter, one directory away

`oneground/models/semantic_sharded/model.py:82`:

```python
Param("centroids", int, minimum=1, swept=True, default=256, ...)
```

Swept, with a minimum and a default, in a declared parameter table — over the
same `cr.kmeans` on the same vectors that `measures` calls a definition. The
`reference_results` in every fixture spec publish it as
`params: {centroids: 256, ...}`. **The same number is a parameter in
`models/` and a definition in `measures/`, and the two are the same k-means.**
Nothing in either place says why.

### What replaces it

Not a different number, and not a different adjective. The replacement has to
be the thing the comment was standing in for:

> **A constant that a published reading is a function of carries its measured
> stability range, or it carries nothing.**
>
> "Definition, not parameter" is not a claim anyone can make by inspection. It
> is a measurement, and the measurement is: over what range of this constant
> does the published value stay inside its published tolerance? Until that
> range exists, the honest comment is *"unmeasured"*.

Concretely, at each such declaration:

1. **The measured band**, with the corpus and tolerance it was measured
   against — `N_CENTROIDS`: crispness 64×, ambiguity 4×, skew 1×.
2. **What is downstream of it.** `N_CENTROIDS` feeds four of the five
   measures; that is why one unexamined constant cost two tasks.
3. **What the constant silently co-varies**, which is how
   `max_points_per_centroid` would have been on the record.
4. **Where the band is narrower than a user could plausibly stray**, the
   constant appears in the reported value and not only in the definition
   prose. Skew fails this today; crispness and ambiguity pass it in the specs
   and fail it downstream in the teaser.

Applying this shape is not in 044c's scope and I have not applied any of it.
The skew half is brought as a decision in
[`tasks/044c-skew-migration.md`](044c-skew-migration.md); the docstring
correction is named under *Observed, not done* because the brief does not name
the file.

## Verification

| check | result |
|---|---|
| Vectors are the published arrays | **PASS** — array sha256 matched `vectors_sha256`/`queries_sha256` in both specs before any measurement |
| k=256 reproduces every published value | **PASS** — 8 of 8, largest Δ 0.0005 |
| k=256 reproduces both published percentile constants | **PASS** — 96.3726 vs 96.37, 98.8296 vs 98.83 |
| Both questions answered with numbers | **PASS** — bands above; 72/72 readings resolvable |
| Degeneracy judged by `crispness.distinguishable` | **PASS** — no fourth criterion invented |
| Sweep brackets 256 by ≥ 1 order of magnitude each way | **PASS** — 16× down, 16× up |
| No published value moved | **PASS** — `git status fixtures/ site/ docs/ oneground/` empty; nothing outside `tasks/` and `runs/` was written |
| No constant changed | **PASS** — `N_CENTROIDS`, `CRISP_RATIO`, `AMBIGUOUS_RATIO` untouched; the control arm is a copy in scratch, not an edit |
| Cited artifacts in the main checkout, verified by digest | **PASS** — `tasks/044c-centroid-count.sweep/`, four files, sha256 compared against `runs/044c/`; both CRLF and committed-LF digests recorded |
| Full suite | see below |
| `sec-filings-10k` swept | **COULDN'T-CHECK** — see below |

**`sec-filings-10k` is couldn't-check and is not rounded up.** Its vectors are
not on this machine — `oneground-assets/sec-filings-10k/` holds only
`documents.jsonl.zst` — and its published `ground_view_*.parquet` carry
`ratio` at k=256 only, which is one point of a sweep. Re-deriving them means
re-embedding 10k chunked filings, and `docs/CHUNKING.md`'s open item is that
this corpus needs re-chunking in subword tokens first. So two of the three
full fixtures were swept and one was not, and **the unanimity of the skew
result is across two corpora, not three.**

`arxiv-smoke` and `glove-100-angular` were not swept and were not intended to
be: the former is a 2,000-vector smoke fixture excluded from the percentile
references for the reason recorded beside them, and the latter publishes no
characterization values.

## Observed, not done

**1. A fixture reads outside its own published band. Live, and not from this
sweep's subject.**

`PUBLISHED_AMBIGUITY_PERCENTILES` stores stackexchange at `90.87`, and that
value is the **maximum of the table**, so it is the top edge of the band
`against_published` compares against. The stored literal is rounded to two
decimals; what `reading()` computes is not:

    stackexchange-150k   measured 90.871567   band 65.44 - 90.87   outside = True

So `oneground characterize` on the stackexchange fixture, at the published
settings, on the published vectors, tells the user *"This reading is being
taken somewhere the measure has never been calibrated"* — about the corpus
that calibrated it. Measured by `tasks/scratch/044c_band_edge.py`; the other
three of the four cases land inside only because their rounding happened to go
the other way (`98.829571` stored as `98.83`).

This is the false-alarm class 044b introduced `MIN_N_FOR_TRANSFER` to prevent,
arriving through rounding instead of through sample size — and a false alarm
degrades a warning faster than silence does, which is 044b's own argument.

**Why the existing test cannot catch it**, which is the more useful half:
`test_the_published_percentile_constants_still_match_the_fixtures` asserts
`got == approx(recorded, abs=0.05)`. It checks that the constant *agrees* with
the fixture. The defect is about *direction at an edge*, and a 0.05 agreement
band is 10× wider than the 0.005 rounding error that causes it. The test is
right about the fact it checks and structurally blind to this one — the same
shape as 043's finding that an exhaustive absence test cannot see a wrong
value.

Not fixed: outside 044c's subject. The remedy is small — store the percentiles
at the precision they were measured, or compare with an explicit rounding
allowance — and it should be a brief so the test is written to fail first.

**2. `PUBLISHED_PERCENTILE_BASIS` attributes an answered question to this
task.** It says the threshold's drift with sample size *"has not been
measured. That is task 044c's question"* — but 044b measured exactly that and
set `MIN_N_FOR_TRANSFER` from it, with the table, **three lines below in the
same file**. Two comments in one module disagreeing about whether a thing is
measured, which is the `docs/PRACTICE.md` mechanism in a smaller key. 044c's
question was the centroid count, and the sentence should say so.

**3. The `measures/__init__.py` docstring is false about two of three
constants** and is the target `crispness.py:52` points at. Not edited: the
brief does not name the file. Proposed replacement text is in *What replaces
it* above.

**4. `intrinsic_dimensionality` is immune to `N_CENTROIDS` by construction,
and that is stronger than "probably".** `two_nn_lid` (`measures/lid.py`) never
receives the centroids and never calls `kmeans` — there is no data path from
one to the other, so no measurement is needed and none was taken. Stated as a
data-path argument, not as a measured result.

But **it carries two constants of exactly the class this task is about**, and
neither has been examined: `n_sample = 20000` — a 13% subsample of a 150k
corpus, the same kind of silent sampling as `max_points_per_centroid` — and
`discard = 0.10`. The published `intrinsic_dimensionality` of 32.55 is a
reading at both. Unexamined, and out of scope here.

**5. `drift` also reads the k-means and was not swept.**
`measures/drift.py:62` takes `n_centroids=256` as a default argument, so it is
a fourth measure downstream of this constant. The brief scoped the sweep to
crispness, ambiguity and skew; drift's k-sensitivity is unmeasured and the
published drift pairs are readings at k=256 like the rest.

**6. `skew_top10_share`'s signature already admits it.** It takes
`n_centroids=N_CENTROIDS` as a parameter — the function has always known the
count is an input; only the published definition and the reported value do
not say so.

## Repo now contains

| path | what |
|---|---|
| `tasks/044c-centroid-count.report.md` | this report |
| `tasks/044c-skew-migration.md` | the skew decision and its migration, for ruling; **not applied** |
| `tasks/044c-centroid-count.sweep/*.json` | the four sweep outputs, copied from `runs/044c/` and verified by sha256 |
| `runs/044c/` | the same four JSONs and their logs (gitignored, as `runs/` is) |
| `tasks/scratch/044c_*.py` | six scratch scripts (gitignored, as `tasks/scratch/` is) |

**No file under `oneground/`, `fixtures/`, `docs/`, `site/`, `models/`,
`policies/` or `corpora/` was created, edited or deleted.**

## Blocked on developer

1. **The skew decision.** `tasks/044c-skew-migration.md` — recommended:
   report k beside the value; no number moves; four fixture YAML definition
   strings need naming per CLAUDE.md before they can be edited.
2. **The teaser/propagation half of the U-shape finding.** Whether 0.036
   travels with its k wherever it is published. I have not touched
   `site/teaser/`, which is standing instruction.
3. **Whether the band-edge defect (Observed 1) becomes a brief.** It is live
   today on a published fixture.
