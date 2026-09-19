# Report: 030-sec-filings-fixture

## Repo state expected vs found

The brief assumes a branch from `main` after the merge, a repo with two built
fixtures to mirror, and the pod machinery from tasks 011/016. All found:
`main` at `6d3ca69`, `fixtures/arxiv-150k` and `fixtures/stackexchange-150k`
built, `corpora/run_fixture_build.sh` generalised, `oneground pod` with its
`plan`/`up`/`watch` split. Branched `task-030` from `origin/main`.

One thing not found: the brief itself was not on origin. Copied from the
developer's checkout as the first commit so the report sits beside it.

## What was done

All seven steps. The fixture is built, `status: built`, values published from
the artifacts, findings written from the numbers.

It took **three pod sessions and four launches**, and cost about **$3.00**
against a per-session cap of $2.50. The first session produced nothing. That
is the central fact of this task and the rest of this report is mostly about
why.

---

## Measurements

### 1. The fetch phase, against its projection

| | projected | measured |
|---|---|---|
| fetch to 10,000 accepted | 25–40 min | **25.7 min** |
| throughput | — | **22.4 MB/s, 7.4 filings/s** |
| streamed, stored | — | **34.51 GB, none** |

The projection was right and the first implementation was not. I assumed 8
requests/second, which is SEC's stated limit. A filing is ~2.8 MB and one
connection to EDGAR carries ~2.4 MB/s, so a *serial* fetcher completes **0.86
requests/second** whatever limit it is given: the request duration binds, not
the limiter. Measured on the pod, 562 filings in 657 s. At 10,000 documents
that is 3.7 hours against a 2-hour cap.

I never reconciled the rate limit with the per-request duration. Reaching 8
req/s needs about ten connections overlapping; I wrote a serial loop.

Measured against EDGAR before changing the pod, same 16 filings each way:

| workers | time | throughput | filings/s |
|---|---|---|---|
| 1 | 9.1 s | 5.12 MB/s | 1.75 |
| 8 | 2.2 s | 21.64 MB/s | 7.38 |

So bandwidth is per-connection, not shared. Eight workers, with
`_RateLimiter` holding the aggregate under SEC's 10/s so concurrency never
becomes a way to exceed a published limit. On the pod the build now runs at
7.4 filings/s — limiter-bound, which is the correct place to be bound.

**The result did not change, and that was checked rather than argued.**
Filings are fetched ahead of the cursor but judged in the seeded order, and
the target stops the cursor. Across three separate runs the checkpoints are
identical: 500/562, 1,000/1,151, 1,500/1,723, 10,000/11,445.

### 2. `IncompleteRead`

**Yes — it now lands in `fetch_failed` rather than killing the run, and in
this build it did not even reach that far.**

The second attempt died at ~3,500 accepted documents on
`http.client.IncompleteRead`, a truncated chunked response. It derives from
`HTTPException` and `ValueError`, so my enumerated except clauses —
`URLError`, `TimeoutError`, `ConnectionError` in `fetch_10k`; `SourceError`,
`HTTPError`, `OSError` around the future — matched none of it. It came out of
the worker thread and killed the build. `fetch_failed`, the category that has
existed for exactly this since step 2, was unreachable for the single most
likely failure.

Serial fetching never saw one in 562 filings. Eight concurrent connections saw
one in four thousand: the concurrency did not create the fault, it made a rare
fault likely.

The list was the wrong shape. `fetch_10k` does nothing but network I/O, so a
transfer failing for **any** reason is now retried with bounded backoff, with
403 and 404 the two exceptions because neither clears by waiting. The consumer
counts any fetch exception as `fetch_failed`.

In the canonical build, **11,445 filings streamed and `fetch_failed` is 0** —
every transport fault that occurred was absorbed by the retry.

### 3. Rejections, by category

**11,445 filings examined to accept 10,000. 1,445 rejected, 12.63%.**

| category | count | share of rejections |
|---|---|---|
| `sections_empty` | 766 | 53.0% |
| `too_short` | 492 | 34.0% |
| `no_sections` | 137 | 9.5% |
| `too_few_sections` | 43 | 3.0% |
| `not_html` | 4 | 0.3% |
| `no_core_section` | 2 | 0.1% |
| `no_10k_document` | 1 | 0.1% |
| `fetch_failed` | **0** | — |

`sections_empty` is the largest single reason and it is the category that did
not exist until two filings in a 40-document development sample nearly got in.
An asset-backed issuer files Items 1 to 15 in order under General Instruction
J and answers "Omitted." to every one: 22 Items recovered from 45,915
characters, which reads as the best-structured filing in the sample. Without
that category this corpus would contain **766 cover pages with Item titles
attached**.

`no_sections` (137) plus `too_few_sections` (43) is the honest count of what
this parser cannot read: **1.6% of what it examined**.

### 4. Tokenising, against the revised figure

| | figure | measured |
|---|---|---|
| per-document, this laptop | 1.19 M chars/s → **~49 min** over the corpus | — |
| batched, this laptop (4 cores) | 1.48 M chars/s, 1.2× | — |
| batched, the pod (16 vCPU) | — | **5.8 min**, 1,559,834 chunks |

**8.4× on the pod, against 1.2× on four cores.** A fast tokenizer parallelises
across a batch in Rust and not across a single string, so one document per
call left fifteen of sixteen cores idle. Batching is throughput only and
cannot move a cut point, which was proved rather than argued: over the 38
cached filings the batched and per-document paths produce the same 5,808
chunks with identical spans.

I had also told the developer 30 minutes before measuring it, then corrected
that to 49. The measured 5.8 is better than both, on hardware neither figure
described.

### 5. The pre-chunking duplicate rate

10,000 documents, lexical Jaccard over 5-word shingles, 14,646 candidate pairs
scored exactly, 466 s.

| threshold | rate | documents | pairs | kind |
|---|---|---|---|---|
| J ≥ 0.50 | **0.5628** | 5,628 | 4,039 | lower bound (LSH recall 0.873) |
| J ≥ 0.60 | **0.3673** | 3,673 | 2,493 | lower bound (LSH recall 0.988) |
| J ≥ 0.70 | **0.1431** | 1,431 | 962 | exact |
| J ≥ 0.80 | **0.0431** | 431 | 290 | exact |
| J ≥ 0.90 | **0.0043** | 43 | 27 | exact |

**The threshold range earned itself here.** Reported at the primary 0.80
cutoff alone this corpus looks barely duplicated, 4.31%. At 0.50, more than
half of all 10,000 documents have another sharing at least half their
five-word shingles. The range was fixed before the build from a three-filer
pilot — Nicholas Financial, Medallion Financial, Henry Schein, scoring 0.49 to
0.62 between adjacent years — precisely so it could not be moved afterwards to
suit a result. The mass turned out to be exactly where the pilot said.

The two low rows are published as lower bounds with their LSH recall beside
them, never rounded up to rates.

### 6. The baseline chunking, as declared

Fixed size, **512 tokens, 64 overlap, stride 448, section-blind**, the
embedding model's own tokenizer, trailing window under 32 tokens dropped.
Deterministic: the cut points are a function of the text and the tokenizer
alone and no seed enters. The seed governs only which chunks are sampled to
150,000.

Section-blind on purpose. The fixture publishes every document's section
offsets so a strategy can be scored on whether it cut through one; a baseline
that respected those boundaries would already be the treatment. 512 because it
is `bge-base-en-v1.5`'s `max_seq_length`, so chunk size is not confounded with
truncation. 64 because zero would make the baseline a straw man.

It is a **baseline for comparison, not a recommendation**, and the spec says
so in its own field (`chunking.is_a_baseline_not_a_recommendation: true`).

- **1,559,834 chunks** from 10,000 documents, 155.98 per document
- **109,722 (7.03%) cross a section boundary** — the number a section-aware
  strategy has to beat. Recomputed independently from the shipped
  152,000-chunk sample: 10,730, **7.06%**.

### 7. The five measures and the two reference results

Read from `fixtures/sec-filings-10k/characterization.json`, not from the log.

| measure | tolerance | arxiv-150k | stackexchange-150k | **sec-filings-10k** |
|---|---|---|---|---|
| intrinsic dimensionality (TwoNN) | 0.5 | 32.55 | 37.46 | **33.43** |
| boundary crispness | 0.02 | 0.036 | 0.011 | **0.107** |
| ambiguous query rate | 0.02 | 0.891 | 0.908 | **0.654** |
| skew, top-10 share | 0.02 | 0.075 | 0.069 | **0.089** |
| drift before → after | 0.02 | 0.522 → 0.549 | 0.485 → 0.450 | **0.632 → 0.616** |

Drift n = 1,370 before / 630 after.

| reference | arxiv-150k | stackexchange-150k | **sec-filings-10k** |
|---|---|---|---|
| single-node HNSW recall@10 | 0.997 | 0.994 | **0.988** |
| semantic sharded recall@10 | 0.932 | 0.869 | **0.929** |
| routing ceiling | 0.932 | 0.870 | **0.930** |
| storage amplification | 3.715× | 3.897× | **3.432×** |
| copies p50 / p95 / p99 | 4 / 4 / 4 | 4 / 4 / 4 | **4 / 4 / 4** |

### 8. Session cost and stages

| session | outcome | elapsed | cost |
|---|---|---|---|
| 20260918-233949 | cap bound, **nothing survived** | 2h 00m | ~$1.44 |
| 20260919-101123 | **DONE** | 2h 09m | ~$1.56 |

Total ~**$3.00**; each session inside its own `max_usd` of $2.50. Zero pods
left on the account, confirmed by `pod ls`.

Canonical build stages, session 20260919-101123:

| stage | time |
|---|---|
| source resolve, 12 indexes streamed and digested | 0.3 min |
| fetch + extract, 11,445 filings | 25.7 min |
| write `documents.jsonl.zst` (691.6 MB) | 1.6 min |
| pre-chunking duplicate rate | 7.8 min |
| baseline chunking, 1,559,834 chunks | 5.8 min |
| embed 152,000 × 512 tokens | ~13 min |
| ground truth, characterization, 2 reference configs | ~14 min |
| **MANIFEST written, receipts packaged** | **58.0 min into the build** |
| projection, ground view | ~11 min |

---

## Verification

`oneground fixture verify sec-filings-10k`, on the developer's laptop against
a build produced on Linux/CUDA:

```
digests 14 verified, 0 contradicted, 0 couldnt_check
values   8 verified, 0 contradicted, 0 couldnt_check
4 published values are not recomputed by this command:
  semantic_sharded.routing_ceiling, .p50_copies, .p95_copies, .p99_copies_per_vector
```

Better than `stackexchange-150k` manages on this machine, which reports
couldn't-check for two semantic-sharded rows for memory.

**Cross-checks that passed:**

- The source digest reproduced on the pod: 21,287 distinct accessions,
  `selection_sha256` `59f847d7…`, identical to the laptop's.
- Every per-quarter 10-K row count identical between laptop and pod.
- Accepted/examined checkpoints identical across three independent runs.
- `documents.jsonl.zst` 691.6 MB in both completed fetch phases.
- Two file digests computed locally from the artifacts match `MANIFEST.sha256`
  exactly.
- Boundary-crossing rate recomputed from a shipped artifact, 7.06% against the
  log's 7.03%.

**Couldn't check:** nothing outstanding.

**Tests:** 30 new (18 extraction, 12 duplicates). Full suite **1014 passed, 5
skipped** at the last full run.

---

## The defects, and what each cost

Every one of these was mine, and each was found by a number that was wrong in
a way the corpus could not explain.

**Found before any pod time, on a 40-filing development sample:**

1. *Item 5 in 5 of 35 filings, Item 6 in 33.* A 90-character cap on the
   heading title. Item 5's official title runs to 128 characters and Item
   12's to 116 — the cap deleted exactly the two longest-named Items.
2. *Item 1 in 31 of 38, Item 1A in all 38.* A symmetric density window treated
   the first body heading as part of the contents page. Canadian Pacific's
   real `ITEM 1. BUSINESS` sits 1,448 characters after its contents entry.
   Runs now break where the Item order steps backwards; a contents page never
   counts down.
3. *Items 10–16 in 26 of 34, Items 1–9 in 33.* Part III is commonly five
   consecutive one-line "incorporated by reference" headings — a contents
   page's exact shape. A contents page is at the front, so position is the
   second half of the test.
4. *Four real 10-Ks of 150k–630k characters rejected outright.* Filers
   letter-space headings across inline elements: `It em 7.`, `I T EM 6.`,
   `ITEM\n1A.`. Matching the literal string measures the filer's HTML
   generator.
5. *Two asset-backed trusts **accepted**, reporting 22 Items from 45,915
   characters.* Caught by asking what the sections contain rather than whether
   they exist. This is the one that would have done real damage, and it
   became 766 rejections in the real build.

**Found on the pod, at cost:**

6. *The serial fetcher.* Would have needed 3.7 hours against a 2-hour cap and
   would have produced nothing rather than less. Cost: most of session 1.
7. *`IncompleteRead`.* Killed the build at 3,500 documents. Cost: the rest of
   session 1.
8. *`snapshot_sha256` as a gate.* Refused the build before a single filing was
   fetched. See below — the guard was right and the gate was in the wrong
   place.
9. *`embedding.device: TO_BE_FILLED`.* torch was handed the literal string as
   a device name, after the fetch, the duplicate rate and the chunking had all
   completed. `device` is recorded in `build_info.json`, which is what made it
   look like a receipt; the builder reads it. Afterwards I audited every one
   of the twenty spec values the builder reads rather than fixing only the one
   that fired.

### The gate that was in the wrong place

Session 20260919-101123 refused at the source check:

```
source.snapshot_sha256 does not match the live EDGAR indexes:
  spec pins  114f40559fb7354e…
  source now 0ba50ce465c4f8e4…
```

The guard fired correctly and the corpus had not changed. Re-streaming all
twelve indexes:

| | |
|---|---|
| 2022 QTR1–QTR4, 2023 QTR1–QTR2 | bytes **same** |
| 2023 QTR3 – 2024 QTR4 | bytes **moved** (six quarters) |
| 10-K rows per quarter | identical, all twelve |
| distinct accessions | 21,287 pinned, 21,287 now, **0 added, 0 removed** |
| `selection_sha256` | **unchanged** |

EDGAR regenerates its recent quarterly indexes. A `form.idx` names every
filing of every type made that quarter — 370,327 rows in 2024 QTR1, of which
4,980 are 10-K — so its digest answers to the whole of EDGAR, not to this
corpus.

`selection_sha256` is now the gate and `snapshot_sha256` is recorded and
reported. **This is not a gate loosened to make something pass**: the gate has
been moved onto the quantity it was always meant to protect, and the
measurement above is what says the corpus is identical. A changed selection
still refuses the build. Both observed snapshot values and their timestamps
are published in the spec, and the same note is in
`sessions/sec-filings-quarters.sha256` so a reader of the digest file is not
misled into treating it as a contract.

This is also the honest answer to a reproducibility question the fixture had
not been asked: a rebuild next year will not see these index bytes, and does
not need to.

### The session that produced nothing

Session 20260918-233949 hit its 2-hour cap mid-build. `watch` behaved
correctly — at 2h 00m it fetched what existed, reported couldn't-check for
both tarballs because neither was present, and terminated. Zero pods left,
about $1.44 spent, no artifact.

**The run log was not a declared output**, so it died with the pod. Which
phase that run had reached is unknowable; the watch log records only that the
file was 8,263 bytes and had been idle twelve minutes. The phase timings and
the rejection tally are the deliverable when the corpus is not, and they were
sitting in a file nobody had declared. The log is now the **first** declared
output, and on the successful run it came home at 100,779 bytes.

Confirmed from the code, not from that one log line: all four termination
paths — `done`, `cap`, `max_usd`, `stalled` — call `_finish`, which runs
`_fetch_outputs` **before** `terminate_pod` inside a `try/finally`.
`_fetch_outputs` walks outputs in declared order and continues past a missing
one, so the log being first means it is fetched before either tarball can
fail.

### One watcher per session

`oneground pod watch` is not read-only at its edges: every exit path fetches
and then terminates the pod. **Two watchers on one session is two cap clocks
and two things that will terminate**, and whichever fires first decides the
session while the other polls a pod that no longer exists.

Session 20260918-233949 was watched twice, because I started a second watcher
without stopping the first. It came to no harm only because the one that
reached the cap did the right thing. This is recorded as a rule, not an
anecdote, in `sessions/sec-filings-build.yaml` where the next person will
meet it: **stop a watcher before starting another.**

### A self-inflicted ssh error worth recording

Stopping the run on the pod with `pkill -f run_fixture_build.sh` killed the
ssh session's own shell — `pkill -f` matches full command lines, and the
remote shell's command line contains that string. ssh returned 255. The
bracket form `'[r]un_fixture_build.sh'` is in the swap script now with the
reason beside it.

### A test harness that reported two false failures

The first version of the `pack()` harness used `tar -tzf … | grep -q`. Under
`set -o pipefail`, `grep -q` exits early on a match, `tar` takes SIGPIPE, and
the pipeline reports failure **on success**. It reported two failures against
correct code. The harness now greps a saved listing.

---

## Findings, written from the numbers

Nine are in the spec's `findings` block. The three that matter most:

**The ground is far crisper than either other fixture, and part of that is the
construction.** Crispness 0.107 against arXiv's 0.036 and Stack Overflow's
0.011 — three and ten times respectively — with ambiguity down to 0.654 from
0.891 and 0.908. A chunk is 512 tokens of one document and the other chunks of
that document are its nearest neighbours, so regions inherit a document
boundary that abstracts and question titles do not have. The finding says so
rather than dressing it as a fact about filings.

**Semantic sharding does well here, and that is new.** 0.929 at 3.432×,
against 0.869 at 3.897× on stackexchange-150k and 0.932 at 3.715× on
arxiv-150k: the cheapest of the three to shard and among the best served by
it. The first fixture on which that architecture is not simply losing. The
routing ceiling still binds (0.930 against 0.929) as it does on all three —
what differs is how high it sits. Meanwhile single-node HNSW is the **lowest**
of the three at 0.988, so the corpus easiest to shard is the hardest to search
exactly, and the two results move in opposite directions.

**Both properties the corpus was expected to show, showed.** Extraction
variance: 12.63% rejected, with the reasons published by category and the
largest of them a category that did not exist a week ago. Intrinsic
boilerplate: 56.28% of documents have a near-duplicate at J ≥ 0.50, and 4.31%
at 0.80 — which is why the range was pre-registered.

### A prediction of mine that was wrong

The spec predicted in advance that the single hot query category would be
**Item 8, the financial statements**. It is **Item 1A, Risk Factors**, at
37,977 of 152,000 sampled chunks (25.0%), ahead of Item 8 at 17.7%. Item 8's
tables are dropped by the extraction rule while Item 1A is all prose. The
prediction is left on the record in both the spec and the findings rather than
quietly corrected.

---

## Observed, not done

- **`watch` does not fetch when a pod stops being `RUNNING`.** Every other
  exit path fetches before terminating; this one returns immediately. The one
  case where a pod dies unexpectedly — where evidence matters most — is the
  case with no fetch. `/workspace` is a network volume and outlives the pod,
  so it is recoverable by hand, which is what task 027 had to do. **The
  developer has scheduled this as task 030b.**
- **`drift_pair` raises `ZeroDivisionError` on an empty side** rather than
  reporting couldn't-check. Hit locally when an offline source stubbed every
  filing date to the same value. Shared code; not this brief's.
- **The builder does not persist the chunking counts.** `chunks_total`,
  `chunks_per_document` and `chunks_crossing_a_boundary` go into the `receipt`
  dict, which nothing writes out, so the full-corpus figures exist only in the
  build log. The rate is independently recomputable from the shipped sample
  (7.06% against 7.03%), and the spec says where each number came from, but
  they should be written into `section_statistics.json`.
- **The accession list is not shipped.** Given that EDGAR regenerates its
  indexes, publishing the 21,287 accessions as a declared artifact (~100 KB
  compressed) would make the fixture rebuildable even if the selection
  eventually moves. Today a moved selection correctly refuses the build, which
  is right but leaves a rebuilder stuck.
- **`fixture verify` does not recompute four published values** — the routing
  ceiling and the three copy percentiles. It says so, which is honest, but
  they are unverified by the tool that exists to verify them.
- **The GPU idles for roughly half the session.** Fetch, duplicates and
  chunking are CPU and network; only the 13-minute embed needs the card. A
  two-pod split would be cheaper and is a worse idea — one session is one
  receipt.

## Repo now contains

New:

- `oneground/sample/sec_filings.py` — extraction rule, rejection categories,
  baseline chunking, the EDGAR reader
- `oneground/sample/test_sec_filings.py` — 18 tests
- `oneground/measures/duplicates.py` — pre-chunking near-duplicate measure
- `oneground/measures/test_duplicates.py` — 12 tests
- `fixtures/sec-filings-10k.fixture.yaml` — `status: built`
- `fixtures/sec-filings-10k/` — MANIFEST, characterization, build_info,
  ground_truth, near_duplicates, section_statistics, query_ids, three
  ground-view parquets
- `sessions/sec-filings-build.yaml`, `sessions/sec-filings-quarters.sha256`
- `tasks/030-sec-filings-fixture.md`, this report

Changed:

- `oneground/sample/__init__.py` — `sec_filings_edgar` reader registered
- `oneground/fixture/build.py` — two additive lines: the reader is handed the
  output directory, and a spec may declare extra receipts. No-ops for every
  spec written before this one.
- `corpora/run_fixture_build.sh` — packages spec-declared extra receipts,
  split by size rather than by name
- `docs/FIXTURES.md` — third column, measured
- `.gitignore` — the corpus and query vectors, scoped to this fixture

Release asset (outside the repo): `../oneground-assets/sec-filings-10k-large.tgz`,
1.22 GB — `documents.jsonl.zst`, `vectors.npy`, `queries.npy`,
`sample.jsonl.zst`.

## Blocked on developer

Nothing. Three items for the record:

1. **The user agent is published**, `oneground/0.1 (shamik.saha.rcciit@gmail.com)`,
   on the developer's explicit instruction. A URL cannot appear in it —
   measured: any user agent containing a domain is refused with 403, with or
   without a scheme and with or without a leading `+`. The repository URL is
   carried in `source.project_url`. The spec's `rebuild` block says a
   rebuilder must substitute their own address.
2. **`max_hours` was raised from 2.0 to 3.0** on the developer's decision after
   the first session hit its cap. `max_usd` was unchanged at $2.50 and is
   still the real ceiling; the build finished at 2h 09m.
3. **Task 030b** is scheduled: make an unexpected pod stop fetch like every
   other exit path.
