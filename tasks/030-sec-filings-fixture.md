# Task 030 — The SEC filings fixture

## Setup
Branch `task-030` from `main` after the 23rd merge. `main` is
release-frozen until then. Commit `task 030:` and push after every commit.
The build runs on a pod and needs the developer's `y` once.

## Why
Chunking cannot be measured on vectors or on short text. Neither existing
fixture works: arXiv abstracts are one chunk each, StackOverflow posts
mostly so. A chunking fixture needs documents long enough that where you
cut them matters, and structure real enough that boundary alignment is
measurable rather than couldn't-check.

SEC filings are public domain (US government works), genuinely long
(a 10-K runs 50–150 pages), structurally marked (Item 1, Item 1A, Item 7,
MD&A), and the retrieval use case is real. They also have two properties
this fixture must report rather than hide: extraction quality varies
wildly across filers, and boilerplate repetition is intrinsic — near
duplicates will be high for reasons that are the corpus's, not a chunking
strategy's.

EUR-Lex is named in the spec as the contrast fixture we have not built:
far better structured, weaker as a retrieval story, and the instrument we
would reach for if the point were structure alone. Same pattern as arXiv
and StackOverflow, where two corpora disagreeing was the finding.

## Do

1. **Pin the source.** Resolve a public EDGAR access path live — the
   full-text search API or the quarterly index files — and pin: the URL
   pattern, the filing types (10-K, and state whether 10-Q is included),
   the date range, the accession numbers or the rule that selects them,
   and a digest over the selected set. Record that the material is public
   domain and why. If rate limits or a user-agent requirement apply, put
   them in the spec; EDGAR requires a declared user agent and refusing to
   declare one is not an option.

2. **The extraction rule, declared and measured.** Filings are HTML of
   highly variable discipline. Write the rule down: what is treated as a
   section heading, what is treated as a table and how tables are handled,
   what is stripped, what is preserved. Then **count what it rejects** — a
   document whose structure cannot be recovered is a rejection, and the
   fixture reports the rejection rate and the reasons by category. A
   fixture that silently drops a third of its corpus is measuring its own
   parser. Target 10,000 documents accepted; report how many were
   examined to get them.

3. **The spec**, `fixtures/sec-filings-10k.fixture.yaml`, mirroring the
   others: source and digests, licence, extraction rule, sampling rule and
   seed, embedding model (`bge-base-en-v1.5`, same as the others, for
   comparability), the five standard measures with tolerances, and a
   chunking block declaring what this fixture exists for. `status:
   planned` with every value `TO_BE_FILLED` until the build fills them.
   Add an `analogy:` block for Tier 2 (`corpus_type: filings`,
   `text_length: long`, `structure: marked`, `time_ordered: true`).

4. **What this fixture publishes that the others do not.** Per document:
   its sections with their character offsets, so a chunking strategy can
   be scored on whether it cut through one. Per corpus: the near-duplicate
   rate at a stated threshold **before any chunking**, which is the
   baseline the chunking measures must be read against. Both are receipts.

5. **Build it on a pod.** Stream the source rather than storing it (the
   016 rule), one session, caps `{max_hours: 2.0, max_usd: 2.50}`,
   receipts packaged the moment the MANIFEST is written (the 016f rule).
   Report the streamed throughput, the rejection rate, and the time for
   each stage.

6. **Publish values from the files**, not from a log: the five measures,
   the reference results, the section statistics, the pre-chunking
   duplicate rate. `status: built`. Findings written from the numbers,
   including the two this fixture was expected to show — extraction
   variance and boilerplate — whichever way they fall.

7. **Docs.** `docs/FIXTURES.md` gains a third column; note plainly that
   this corpus is for chunking and that its near-duplicate baseline is
   intrinsic. Name EUR-Lex in the spec's own `contrast:` field as the
   unbuilt comparison and say what it would settle.

## Acceptance
- Source pinned with licence, user agent and digests; extraction rule
  written down.
- Rejection rate and reasons reported by category; documents examined
  versus accepted.
- Section offsets and the pre-chunking duplicate rate published as
  receipts.
- One pod session, zero pods left, cost reported.
- `status: built` with values from the files; findings written from the
  numbers.

## Do not
- Choose or tune the corpus to produce a particular result. Silently drop
  unparseable filings. Store the source. Touch `main` before the merge.
