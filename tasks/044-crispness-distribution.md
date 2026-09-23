# Task 044 — Crispness becomes a distribution, and the count becomes a reading

**Not to be built until approved.** This changes a published measure. The
migration is specified below so it can be approved with the numbers in front
of you.

## Setup
Branch `task-044` from `main`. Commit `task 044:` and push after every commit.
No pod. Nothing here re-measures a fixture at full size; the point of the
design below is that it does not have to.

## Why

`boundary_crispness` counts the fraction of vectors whose second-nearest
centroid is more than **1.20×** the first. That constant is `CRISP_RATIO =
1.20` in `oneground/measures/crispness.py`, under the comment
`# Definitions, not parameters.`

Measured in task 036, on identical records, seed and centroid count:

| model | crispness | median ratio | **p95 ratio** |
|---|---|---|---|
| bge-base-en-v1.5 | **0.1487** | 1.1035 | **1.2631** |
| e5-base-v2, raw | 0.0063 | 1.0565 | **1.1475** |
| e5-base-v2, `passage: ` | 0.0063 | 1.0584 | **1.1505** |
| e5-base-v2, `query: ` | 0.0125 | 1.0644 | **1.1643** |

**Under e5 the 95th percentile of the ratio is 1.15 and the threshold is
1.20.** It sits above almost the entire distribution, so the measure returns a
near-zero for every corpus regardless of what is in it. Truncation was ruled
out (bge and e5 truncate identically) and protocol was ruled out (both
prefixes tested). The ratio is scale-invariant, so this is not a units
artifact: e5 genuinely places these vectors more equidistantly between
centroids, and the fixed threshold converts that real difference into
`0.0000`.

**The defect is what the user reads.** Someone bringing such an embedding gets
crispness ≈ 0 on every corpus they own. The tool's output supports only one
reading of that — *"my corpus has no boundary structure"* — and the true
statement is *"this threshold does not fit my embedding's scale"*. That is the
product stating a confident falsehood about the user's own data, which is the
one thing it exists to refuse. Same class as an alignment rate without its
ceiling and a gap without its scale: the number is true, the sentence it
licenses is not, and nothing in the artifact says which.

Full evidence: `tasks/036-embedding-models.report.md`, leading section.

## The ruling, which is made

**Crispness becomes the ratio distribution with its quantiles. The 1.20 count
is retained as a named reading, with its threshold stated beside it. Every
published value keeps its meaning, because the count remains computable from
the distribution.**

**Corpus-derived quantiles were considered and are refused.** A threshold
derived from the corpus makes the measure self-referential: each corpus would
be scored against its own distribution, so two corpora measured that way
**cannot be compared** — which is exactly the property crispness exists to
provide. It would fix the e5 symptom by destroying the measure's purpose.

The reasoning to carry into the code: **the distribution is the honest object;
a thresholded count is a reading of it; and a reading can be labelled with
what it assumes.** A distribution assumes nothing beyond the k-means and the
metric. A count assumes a threshold, and the remedy is to say so rather than
to hide it in a constant called a definition.

## Do

### 1. The distribution is the measured object

`boundary_crispness` gains a sibling that reports the **ratio distribution**
`d2/d1` over the base vectors: at minimum the quantiles, enough of them to
reconstruct the shape and to compute any threshold's count.

- Quantiles at a **declared, fixed** set — they are a definition and must not
  vary by corpus or by run, for the same reason the threshold must not.
- The distribution is **scale-invariant already** (a quotient of distances),
  so it is comparable across embeddings in the way the count is not.
- Include whatever makes a count recomputable to the precision the published
  tolerances require. State in the report what precision that is and how it
  was determined; do not guess a quantile count.

### 2. The count survives, named and labelled

`boundary_crispness` **keeps its name, its value, its tolerance and its
definition prose.** It becomes explicitly *a reading at threshold 1.20*:

- the threshold is recorded **beside the value**, in the artifact, not only in
  the spec prose;
- the artifact says the count is a reading of the distribution, and that a
  different threshold gives a different count of the same geometry;
- **`CRISP_RATIO` is not changed.** Rule 3. Changing it to make e5 read better
  is precisely the move that rule forbids.

### 3. Say when the reading does not read

The e5 case must be detectable from the artifact rather than by someone
noticing a zero. When the threshold sits outside the distribution — the p95
below it is the case measured, but state the rule in terms of the
distribution, not of e5 — the artifact says so:

> the count is 0.0063 at threshold 1.20; the 95th percentile of the ratio is
> 1.1475, so the threshold is above almost every vector in this corpus and the
> count is not discriminating here. The distribution is the number to read.

This is a **couldn't-check on the reading, not on the measure** — the
distribution was measured fine. Keep those apart; they are different outcomes
and the project does not round one into the other.

### 4. What the interfaces do with it

- `characterize` reports the distribution and the labelled count.
- `fixture verify` continues to check the published count against its
  published tolerance, unchanged. It gains the distribution as something it
  reports, and the report says whether it also gains it as something it
  *checks* — which requires a published value, which requires this task's
  migration to have landed.
- The lab and the report render the distribution where they render the count
  today, or say why not. Both are named in step 6's impact list.

## The migration, which is what needs approving

### The three published fixture values are **unchanged**

| fixture | published `boundary_crispness` | tolerance | after 044 |
|---|---|---|---|
| `arxiv-150k` | 0.036 | ±0.02 | **0.036, unchanged** |
| `stackexchange-150k` | 0.0115 | ±0.02 | **unchanged** |
| `sec-filings-10k` | 0.1073 | ±0.02 | **unchanged** |

The count is computed the same way from the same vectors with the same seed,
centroids and threshold. Nothing about it moves. The spec's definition prose —
*"Fraction of base vectors whose second-nearest centroid distance exceeds 1.20
× their nearest centroid distance, under k-means with 256 centroids (seed
20260908, 20 iterations)"* — **stays true word for word**, and is in fact the
best evidence that the ruling is the right shape: the published definition
already states its threshold.

### The teaser is **unchanged**, and already labels its threshold

`site/teaser/` is byte-checked against the live page, and crispness appears
there twice:

1. **The `receipt-values` table** (`app.js:929`) verifies `boundary_crispness`
   published-vs-recomputed against the spec tolerance. Unchanged: the value
   and tolerance do not move.
2. **The ε-caption** (`app.js:433-438`) renders
   `fmtPct(1 - crisp)` as *"The boundaries are still there: **96.4%** of
   vectors have a second centroid inside 1.20× of the first."*

The caption **already names the threshold in its own sentence**. It is
therefore already a labelled reading, and needs no change. Under this design
**not one of the nine teaser files moves**, and `check_hosted.py` should still
read 9 verified, 0 contradicted after the task.

If anything in the implementation would move a teaser byte, that is a signal
the design has drifted from this ruling — stop and report rather than editing
the teaser.

### Where the distribution is stored — **ruled: derived on demand**

Three options were put; all three leave the values and the teaser alone and
they differ only in migration cost.

| | what changes | cost |
|---|---|---|
| A. a field in `characterization.json` | that file's bytes and digest, so `MANIFEST.sha256` too, for all three fixtures | the three release assets regenerated and republished |
| B. a sibling artifact | `characterization.json` untouched; MANIFEST gains a line | release assets still regenerated |
| **C. derived on demand, not stored** | **nothing published changes at all** | **none** |

**C is the ruling.** The argument is the project's own definition of a
receipt: *re-derivable from seeds and rules*. The distribution derives from
`vectors.npy`, the recorded seed and the declared centroid count — all already
published receipts — so it is a **view of existing receipts**, exactly as the
count is. Storing it would declare bytes for something that needs none.

Nothing in `fixtures/` changes, no release asset is regenerated, no MANIFEST
moves, and the distribution is available for every corpus a user brings
without re-downloading anything.

**The loss, recorded rather than waved past:** a consumer holding only the
artifacts, without `vectors.npy`, cannot see the distribution. It is real,
small, and the artifacts that do carry it are the ones already published.

### This makes the implementation match the documentation

Worth stating plainly, because it decides how carefully to tread. The fixture
spec's published definition already says *"exceeds 1.20 ×"*, and the teaser's
caption already says *"a second centroid inside 1.20× of the first"*. **Both
were labelled readings before anyone noticed the code was not.** The
documentation has been describing a thresholded reading all along; only
`crispness.py` called the threshold a definition.

So this task is not changing a meaning. It is making the implementation say
what the published documents already say, and adding the object those readings
are readings *of*. Any change that would move a published value or a teaser
byte has therefore gone beyond the task, not deeper into it.

### What this does NOT migrate

- `N_CENTROIDS = 256` sits under the same comment and **is not examined here**.
  Whether the same class of defect applies to it is unknown, and this task does
  not find out. Say so; do not imply it was checked.
- The other four characterization measures are not audited for model-dependent
  constants by this task. `ambiguous_query_rate` uses a ratio rule of the same
  family and is the obvious next candidate — name it, do not fix it.

## Acceptance

- The ratio distribution is reported with declared fixed quantiles, and the
  1.20 count is recomputable from it to the precision the published tolerances
  require, demonstrated against all three fixtures.
- `boundary_crispness` keeps its name, value, tolerance and definition; the
  three published values reproduce exactly; `oneground fixture verify` passes
  on all three unchanged.
- The threshold is recorded beside the count in the artifact.
- An artifact whose threshold sits outside its own distribution says so, as a
  couldn't-check on the reading and not on the measure, with a test that
  constructs such a distribution synthetically.
- `site/teaser/` is byte-identical; `check_hosted.py` reads 9 verified, 0
  contradicted.
- The storage decision is recorded with its reason and its cost.
- Full suite green.

## Do not

- Change `CRISP_RATIO`, or any published value, or any tolerance.
- Derive a threshold from the corpus. It is refused above and the reason is
  that it destroys comparability, which is the property the measure exists for.
- Edit `site/teaser/`. If the design requires it, the design is wrong.
- Imply that the other four measures were audited.
- Report the distribution and quietly drop the count. Every published number
  keeps its meaning; that is the constraint that made this shape the right one.
