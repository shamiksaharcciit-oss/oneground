# The public fixtures

Three corpora, built the same way, published with their receipts. They exist so
that anyone can install oneground, rebuild a fixture, and confirm it reproduces
the published numbers within tolerance — and so that a user with their own
vectors has something measured to compare against.

**They are not a leaderboard.** Every recommendation oneground makes is
measured on the user's own corpus. A fixture is a reference point and a proof
that the pipeline is honest, never a ranking of corpora or of architectures in
general.

Every number below is read from the fixture's own spec
(`fixtures/<id>.fixture.yaml`), which is filled from the build's artifacts.
Each carries its own tolerance, and `oneground fixture verify <id>` recomputes
it locally and reports **verified / contradicted / couldn't-check** — never
rounding couldn't-check up to verified.

---

## Side by side

|  | **arxiv-150k** | **stackexchange-150k** | **sec-filings-10k** |
|---|---|---|---|
| status | `verified` | `built` | `built` |
| built for | reference | reference | **chunking** |
| source | arXiv metadata snapshot | Stack Overflow posts (Internet Archive Stack Exchange dump) | EDGAR 10-K annual reports |
| provider | arxiv.org via Kaggle `Cornell-University/arxiv` | Hugging Face `mikex86/stackoverflow-posts`, revision `9e791fe8` | U.S. Securities and Exchange Commission, twelve quarterly indexes |
| licence | **CC0 1.0** | **CC BY-SA** 2.5 / 3.0 / 4.0, *per post*, from each record's `ContentLicense` | **no licence terms**: a public record the SEC publishes for free reuse. *Not* claimed under 17 U.S.C. §105 — see below |
| what a record is | title + abstract | title + first 500 chars of the cleaned body | a **chunk** of a filing, 512 tokens |
| queries are | the paper's title | the question's title | a **held-out chunk** — a 10-K has no title field |
| model | `BAAI/bge-base-en-v1.5`, 768-d, normalized | same | same |
| size | 150,000 base + 2,000 held-out queries | same | same, from 10,000 documents |
| sampling | stratified by year, hot categories by volume | same rule, tags in place of categories | seeded shuffle, examine until 10,000 accepted |
| source scale | ~2.1M papers | 20,388,803 eligible questions of 58,329,355 posts | 21,287 distinct 10-K filings, 2022–2024 |
| drift cutoff | `2019-01-01` | `2017-01-01` | `2024-01-01` |
| ships | — | — | section offsets per document; pre-chunking duplicate rate |

### The five measures

| measure | tolerance | arxiv-150k | stackexchange-150k | sec-filings-10k |
|---|---|---|---|---|
| intrinsic dimensionality (TwoNN) | 0.5 | 32.55 | **37.46** | 33.43 |
| boundary crispness | 0.02 | 0.036 | 0.011 | **0.107** |
| ambiguous query rate | 0.02 | 0.891 | 0.908 | **0.654** |
| skew, top-10 share | 0.02 | 0.075 | 0.069 | 0.089 |
| drift (before → after) | 0.02 | 0.522 → 0.549 | **0.485 → 0.450** | 0.632 → 0.616 |

The third column is the one that does not follow. `sec-filings-10k` is **three
times crisper than arXiv and ten times crisper than Stack Overflow**, and much
less ambiguous. Part of that is the corpus and part of it is the construction:
its records are 512-token chunks of long documents, and the other chunks of a
document are a chunk's nearest neighbours, so regions inherit the document
boundary as structure that abstracts and question titles do not have. That is
the property the fixture exists to make measurable, and it is stated here
rather than read as a fact about filings alone.

Definitions are in each spec and are identical across the three: crispness is the
fraction of base vectors whose second-nearest centroid distance exceeds 1.20×
the nearest under k-means with 256 centroids; ambiguity is the fraction of
queries with `d2 <= 1.10 × d1` against the same centroids; skew is the share of
base vectors in the 10 largest regions; drift trains centroids on records
before the cutoff and measures recall@10 at one-region routing separately on
queries either side.

### The two reference results

All three fixtures publish the same two configurations at the same parameters,
so the rows are comparable line for line.

| | arxiv-150k | stackexchange-150k |
|---|---|---|
| **single-node HNSW** `M=32, efConstruction=200, efSearch=128` | | |
| recall@10 (tol 0.01) | 0.997 | 0.994 |
| **semantic sharded** `centroids=256, ε=0.2, probe=2, M=32, efSearch=96` | | |
| recall@10 (tol 0.01) | 0.932 | **0.869** |
| routing ceiling | 0.932 | 0.870 |
| storage amplification | 3.715× | **3.897×** |
| copies p50 / p95 / p99 | 4 / 4 / 4 | 4 / 4 / 4 |

`sec-filings-10k` adds a third column to both: single-node HNSW **0.988** —
the *lowest* of the three — and semantic sharding **0.929** at **3.432×**,
routing ceiling 0.930. It is the cheapest of the three to shard and among the
best served by it, and the hardest of the three to search exactly. The two
results move in opposite directions, which is worth more than either alone.

The **routing ceiling** is what an exact search over everything the routing can
reach would return. On all three fixtures it sits at the measured recall, which
says the loss is the routing rather than the index — no amount of `efSearch`
recovers it. What differs is how high the ceiling sits.

### The drift pair

| | arxiv-150k | stackexchange-150k | sec-filings-10k |
|---|---|---|---|
| cutoff | 2019-01-01 | 2017-01-01 | 2024-01-01 |
| before | 0.522 | 0.485 | 0.632 |
| after | 0.549 | **0.450** | 0.616 |
| direction | improves | **degrades** | degrades mildly |
| queries before / after | — | 1,063 / 937 | 1,370 / 630 |
| realised corpus split | — | 78,969 / 150,000 = 52.6% before | — |

arXiv is the only one that **improves**: its regions describe newer papers
slightly better than older ones. Stack Overflow's describe newer questions
*worse*, by 7.2% relative — a topic mix that turns over, jQuery out, React and
Kubernetes in, is not described by centroids trained before it turned. Filings
drift the same way and by a third as much, 2.5% relative, which is what a
corpus of mandated annual disclosures on a two-year window should do.

---

## The one-line comparison

From `stackexchange-150k`'s own `findings` block, verbatim:

> Against arxiv-150k: blurrier (crispness 0.011 vs 0.036), slightly more
> ambiguous (0.908 vs 0.891), more expensive to shard (3.897x vs 3.715x),
> worse under semantic sharding (0.869 vs 0.932 recall@10), and drifting the
> opposite way (0.485->0.450 vs 0.522->0.549). Two corpora that look unalike
> to a reader turn out to agree on the architecture question and disagree
> about time.

And from `sec-filings-10k`'s, which breaks that agreement:

> Against the other two fixtures: far crisper (0.107 vs 0.036 and 0.011), much
> less ambiguous (0.654 vs 0.891 and 0.908), cheaper to shard (3.432x vs
> 3.715x and 3.897x), better under semantic sharding (0.929 vs 0.932 and
> 0.869), harder to search exactly (0.988 vs 0.997 and 0.994), and drifting
> mildly in Stack Overflow's direction (0.632 to 0.616).
>
> Three corpora now, and the architecture question has three answers rather
> than a trend. What separates this one is not its subject matter but that its
> records are chunks of long documents instead of short whole ones — which is
> the property the fixture was built to make measurable.

---

## The third fixture is for chunking, and two of its numbers are the corpus's own

`sec-filings-10k` exists because **the other two cannot measure chunking at
all**. An arXiv abstract is one chunk; a Stack Overflow question is usually one
chunk. Where you cut them does not arise. A 10-K runs 50 to 150 pages and is
marked by convention — Item 1, Item 1A, Item 7 — so where you cut it matters
and whether the cut landed on a boundary is measurable rather than
couldn't-check. It ships every document's section offsets so a strategy can be
scored on whether it cut through one.

It ships **one** chunking — fixed size, 512 tokens, 64 of overlap,
section-blind — and that is a **baseline, not a recommendation**. It is the
thing a strategy has to beat, chosen to be the obvious naive default. Nothing
in this fixture should be read as advice about how to chunk; comparing
strategies against the baseline is what `docs/CHUNKING.md` describes and is not
this fixture's job.

Two properties of this corpus are reported rather than cleaned away, because
hiding either would make the fixture misleading:

**Extraction quality varies wildly across filers, so the rejection rate is
published by category.** Filer HTML is of no fixed discipline: some letter-space
headings across inline elements so the word arrives as `It em 7.`, some put the
Item number on its own line. Every filing the rule turns away is counted and
attributed, and the fixture publishes examined-versus-accepted. A fixture that
silently drops a third of its corpus is measuring its own parser.

Measured on the canonical build: **11,445 filings examined to accept 10,000,
12.63% rejected**. `sections_empty` is 766 of the 1,445 — the largest single
reason, 53% — and those are asset-backed trusts that file Items 1 to 15 under
General Instruction J and answer "Omitted." to every one. Structurally
perfect, and empty; a rule that counted headings would have taken all 766 as
among the best-structured documents in the corpus. `too_short` is 492,
`no_sections` 137, `too_few_sections` 43 — the last two are the honest count
of what this parser cannot read, 1.6% of what it examined. `not_html` 4,
`no_core_section` 2, `no_10k_document` 1, `fetch_failed` 0.

**Boilerplate repetition is intrinsic, so the near-duplicate rate is published
for the corpus before any chunking.** This is the baseline a chunking
comparison must be read against: without it, a strategy's duplicate rate cannot
be told apart from the corpus's own. It is measured lexically — Jaccard over
word shingles — precisely because a chunk vector exists only once a chunking has
been chosen, so a cosine rate on chunk vectors already contains the strategy
under test.

Measured on the canonical build, and the reason the thresholds were fixed from
a three-filer pilot *before* it:

| threshold | rate | kind |
|---|---|---|
| J ≥ 0.50 | **56.28%** | lower bound (LSH recall 0.873) |
| J ≥ 0.60 | 36.73% | lower bound (LSH recall 0.988) |
| J ≥ 0.70 | 14.31% | exact |
| J ≥ 0.80 | 4.31% | exact |
| J ≥ 0.90 | 0.43% | exact |

At the primary 0.80 cutoff alone this corpus looks barely duplicated, 4.31%.
At 0.50, **more than half of all 10,000 documents** have another sharing at
least half their five-word shingles. The repetition is enormous and lives in a
band a single high cutoff cannot see — which is exactly what a chunking
comparison must know before attributing any of it to a strategy.

**On the licence.** The SEC says of EDGAR that "anyone can access and download
this information for free", asserts no copyright, and attaches no reuse terms —
only access conditions, which are a declared user agent carrying a reachable
contact and a rate limit of 10 requests a second. The spec deliberately does
*not* claim 17 U.S.C. §105: that covers works the government authored, and a
10-K is authored by the registrant and filed with the government. Any residual
interest of a registrant in its own filed text is recorded as untested rather
than dismissed. **A rebuilder must put their own contact in
`source.user_agent`** — the address published there is the maintainer's, present
because a source that cannot be re-fetched is not reproducible, and it is not an
invitation to load a public service under someone else's name.

**The comparison it is not.** The spec names `eur-lex` in its own `contrast`
field as the fixture that has *not* been built, and says what it would settle:
whether these results are about long documents or about *badly marked* long
documents. Here a section boundary is recovered by a rule that some filings
defeat; in EU legislation the structure is given by law. If a section-aware
strategy beats the baseline on both, the finding is about length. If only on
EUR-Lex, the finding is that structure-aware chunking needs structure it can
trust — and the honest advice for a corpus of filings is a different one.

---

## Reading these responsibly

**The second fixture was not chosen to make anything win.** Its brief said so
explicitly, and its spec committed every rule — corpus, text rule, cutoff,
seeds — in writing with every value `TO_BE_FILLED` *before* the build ran. The
answer came out against semantic sharding, harder than on arXiv. It is
published as it fell.

**Two fixtures are two corpora, not a trend.** That they agree about
architecture and disagree about time is worth knowing and is not a law. The
right use of it is to ask the same questions of your own corpus, which is what
`oneground characterize` is for.

**`verified` and `built` mean different things.** `arxiv-150k` is `verified`:
its values have been reproduced under the pinned environment.
`stackexchange-150k` is `built`: its values are measured and its digests check,
and at the time of writing two rows — `semantic_sharded.recall_at_10` and
`.storage_amplification` — are **couldn't-check** on the developer's machine,
which runs out of memory recomputing the 256-shard reference over 150,000
vectors. That is recorded as couldn't-check with its reason, and closes on a
CPU-pod session. It is not rounded up.

## Getting the artifacts

The small artifacts are in the repository. The large ones — `vectors.npy`,
`queries.npy`, `sample.jsonl.zst` — ship as release assets, so a fresh clone
reports couldnt_check for the values that need them. An asset extracts to
`fixtures/<id>/` wherever you extract it; point verify at that folder:

    tar -xzf stackexchange-150k-v1.tgz
    oneground fixture verify stackexchange-150k --asset <where you extracted it>/fixtures/stackexchange-150k

Rebuilding a fixture from source is `corpora/run_fixture_build.sh`, which the
pod sessions in `sessions/` drive. `stackexchange-150k` streams its 34 GB
source at a pinned revision and stores none of it; `arxiv-150k` reads a local
snapshot. See `docs/POD.md`.

`fixtures/arxiv-150k/report/` publishes a developer's own run of the product
path — `oneground report` over the arXiv workdir from the two-engine matched
session `20260913-161921` — so a reader can see a real report rather than a
description of one: `report.json`, `report.html`, and the `simulate`, `verify`
and `characterize` outputs it was judged from. It is **declared**, not a
receipt: one machine, one day, one pod, and its digests in the fixture's
`MANIFEST.sha256` confirm only that these are the bytes that run produced. It
is not a fixture value and nothing is verified against it.
