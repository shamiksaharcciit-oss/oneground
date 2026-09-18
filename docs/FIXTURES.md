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
| status | `verified` | `built` | `planned` |
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
| intrinsic dimensionality (TwoNN) | 0.5 | 32.55 | **37.46** | not built |
| boundary crispness | 0.02 | 0.036 | **0.011** | not built |
| ambiguous query rate | 0.02 | 0.891 | **0.908** | not built |
| skew, top-10 share | 0.02 | 0.075 | 0.069 | not built |
| drift (before → after) | 0.02 | 0.522 → 0.549 | **0.485 → 0.450** | not built |

`sec-filings-10k` is `planned`: its rules, seeds, thresholds and cutoffs are
fixed in writing and every value in its spec is `TO_BE_FILLED`. Nothing is
reported for it here until the canonical build fills them, and "not built" is
not a placeholder for a number someone expects — it is the whole of what is
known.

Definitions are in each spec and are identical across the two: crispness is the
fraction of base vectors whose second-nearest centroid distance exceeds 1.20×
the nearest under k-means with 256 centroids; ambiguity is the fraction of
queries with `d2 <= 1.10 × d1` against the same centroids; skew is the share of
base vectors in the 10 largest regions; drift trains centroids on records
before the cutoff and measures recall@10 at one-region routing separately on
queries either side.

### The two reference results

Both fixtures publish the same two configurations at the same parameters, so
the rows are comparable line for line.

| | arxiv-150k | stackexchange-150k |
|---|---|---|
| **single-node HNSW** `M=32, efConstruction=200, efSearch=128` | | |
| recall@10 (tol 0.01) | 0.997 | 0.994 |
| **semantic sharded** `centroids=256, ε=0.2, probe=2, M=32, efSearch=96` | | |
| recall@10 (tol 0.01) | 0.932 | **0.869** |
| routing ceiling | 0.932 | 0.870 |
| storage amplification | 3.715× | **3.897×** |
| copies p50 / p95 / p99 | 4 / 4 / 4 | 4 / 4 / 4 |

The **routing ceiling** is what an exact search over everything the routing can
reach would return. On both fixtures it sits at the measured recall, which says
the loss is the routing rather than the index — no amount of `efSearch`
recovers it.

### The drift pair

| | arxiv-150k | stackexchange-150k |
|---|---|---|
| cutoff | 2019-01-01 | 2017-01-01 |
| before | 0.522 | 0.485 |
| after | 0.549 | **0.450** |
| direction | improves | **degrades** |
| queries before / after | — | 1,063 / 937 |
| realised corpus split | — | 78,969 / 150,000 = 52.6% before |

This is the one measure where the two corpora disagree in **sign**, and it is
the finding v0.1 leads with. arXiv's regions describe newer papers slightly
better than older ones; Stack Overflow's describe newer questions *worse*. A
topic mix that turns over — jQuery out, React and Kubernetes in — is not
described by centroids trained before it turned.

---

## The one-line comparison

From `stackexchange-150k`'s own `findings` block, verbatim:

> Against arxiv-150k: blurrier (crispness 0.011 vs 0.036), slightly more
> ambiguous (0.908 vs 0.891), more expensive to shard (3.897x vs 3.715x),
> worse under semantic sharding (0.869 vs 0.932 recall@10), and drifting the
> opposite way (0.485->0.450 vs 0.522->0.549). Two corpora that look unalike
> to a reader turn out to agree on the architecture question and disagree
> about time.

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
silently drops a third of its corpus is measuring its own parser. On a seeded
development sample of 40 filings the rule accepted 38, and both rejections were
asset-backed trusts that file Items 1 to 15 under General Instruction J and
answer "Omitted." to every one — structurally perfect, and empty.

**Boilerplate repetition is intrinsic, so the near-duplicate rate is published
for the corpus before any chunking.** This is the baseline a chunking
comparison must be read against: without it, a strategy's duplicate rate cannot
be told apart from the corpus's own. It is measured lexically — Jaccard over
word shingles — precisely because a chunk vector exists only once a chunking has
been chosen, so a cosine rate on chunk vectors already contains the strategy
under test. Measured before the build on three filers' consecutive filings, the
same company's adjacent-year 10-Ks score Jaccard 0.49 to 0.62. The repetition is
large and it belongs to the corpus.

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
