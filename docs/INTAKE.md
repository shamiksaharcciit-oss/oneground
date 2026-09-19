# Intake — the two tiers

`requirements.yaml` is how you tell oneground what you have and what you need.
There are two ways to fill it in, and the difference between them is the
difference between a measurement and a description.

| | Tier 1 | Tier 2 |
| --- | --- | --- |
| you provide | `corpus.sample` — vectors, or text plus a pinned model | `corpus.declared` — a description |
| oneground measures | your corpus | nothing |
| you get | verdicts against exact k-NN ground truth | a fixture analogy and capacity arithmetic |
| a recommendation? | yes, when an option meets every constraint | **never** |

A file may contain both blocks. A sample always wins: a measurement beats a
description, every time.

---

## Tier 1 — the receipt path

You have exported a sample of your own vectors. `characterize` measures five
properties of them, `simulate` runs architectures against exact ground truth,
`verify` measures a real engine, and `report` judges the result against your
constraints.

```yaml
corpus:
  sample:
    kind: receipt
    vectors:
      path: ./data/sample_vectors.npy     # (n, dim) float32
      normalized: false
    queries:
      path: ./data/queries.jsonl
      count_min: 50
    metadata:
      path: ./data/sample_meta.parquet
      timestamp_field: created_at
    target_sample_size: 20000
```

Everything the report says is traceable to a file and a field in your workdir.
That is what "receipt" means here: re-derivable from the seeds and rules
recorded beside it.

### If you bring text: chunking runs first, and it is measured

Since task 031, `oneground characterize` accepts **extracted text** as well as
vectors — one record per document, however you produced it, with no extractor
protocol, adapter, plugin or catalogue. Given text, the chunking stage runs
first, writes its own receipt, and the rest of the path continues from the
chunks it produced. `oneground chunk <requirements>` runs that stage alone, so
you can ask "is my chunking cutting through answers" without committing to a
full run. See [CHUNKING.md](CHUNKING.md).

**Given vectors, chunking reports couldn't-check** in those words: the cut has
already happened and is out of the instrument's reach. A vector carries no
record of where its chunk began, so neither the structural measures nor
self-retrieval can be computed. That is a stated outcome, not an omitted
section.

#### The `extraction:` declaration is required

oneground **does not run extractors**, and this is deliberate rather than
unfinished. In a real pipeline the chunker sits behind an extractor and the
text has already been through one; feeding the chunker raw HTML would measure
it in a position it never occupies, and shipping pre-cleaned text would bake
an extractor's choices in invisibly. Running them ourselves would mean
dependencies dwarfing the wheel, or a hosted service that sends your documents
off your machine, and partial responsibility for someone else's parser — the
position the adapter protocol deliberately avoids for engines.

So you declare what produced the text, and it is carried onto every result:

```yaml
extraction:
  tool: unstructured
  version: "0.16"
```

`unknown` is accepted — you often will not know — **but only with a reason**:

```yaml
extraction:
  tool: unknown
  reason: the corpus was handed over as text by another team
```

Unknown with no reason is indistinguishable from nobody having asked, and a
reader cannot tell which they are looking at. A named tool needs its version,
because an extractor's output changes between releases.

Nothing about this declaration is checked. It says what the result is
conditional on; it does not claim to be true, and the result records that
oneground neither ran nor verified it.

**A chunking measured under one extraction may not hold under another.** Two
results from differently-extracted text are two observations, never a
comparison — and comparing two extractions needs no new machinery: run both
extractors yourself, bring two corpora, get two results, each declaring its
extraction.

### One record is one vector, so bring chunks

oneground embeds each record you give it into exactly one vector, and the
model takes a fixed number of tokens — `max_seq_length`, 512 by default. A
record longer than that is **truncated, silently**: the transformer keeps the
first `max_seq_length` tokens, discards the rest, and returns a perfectly
well-formed vector of the part it kept. Nothing downstream can tell. Ground
truth is computed from those same truncated vectors, so recall against it is
high and self-consistent, and every number in the report describes a corpus
that is not the one on your disk. If your records are whole documents, chunk
them before intake and bring one row per chunk — that is a retrieval design
decision, and oneground will not make it for you by quietly cutting at 512.

So it is counted and said out loud. `characterize` tokenizes with the model's
own tokenizer before embedding anything, prints

```
WARNING: 15 of 55 records (27.3%) are longer than max_seq_length 128 tokens
and will be TRUNCATED; the longest is 402 tokens. if these are documents
rather than chunks, chunk them first
```

and writes `truncated_count`, `max_seq_length` and the full `truncation` block
to `build_info.json` as **declared** facts. `truncated_count: 0` means it was
counted and none were cut; `null` means it could not be counted — the two are
deliberately different values, because the reassuring one must never be what
you get when nothing looked.

## Tier 2 — the declared path

You have not exported anything yet. You know roughly what your corpus is and
how big it is, and you want to see the shape of the decision before doing the
work.

```yaml
corpus:
  # no `sample:` block — that is what makes this Tier 2
  declared:
    kind: declared
    size_now: 2100000
    dimension: 768
    embedding_model: BAAI/bge-base-en-v1.5
    corpus_type: support_tickets
    text_length: short              # short | medium | long
    topics_trend: true
    time_ordered: true
    languages: [en, nl]
    nearest_fixture: auto           # auto | <fixture id> | none
```

`size_now` and `dimension` are required — the capacity arithmetic is
arithmetic over exactly those two, and there is nothing to compute without
them. Everything else is optional and sharpens the analogy.

Run it the same way:

```
oneground characterize requirements.declared.example.yaml
oneground report        requirements.declared.example.yaml
```

---

## What unlocks each measurement

This is the table Tier 2's report prints as its final decision-log entry. It
is the honest answer to "what do I have to do to get a real answer?"

| measurement | what it needs |
| --- | --- |
| `recall_at_k` | 10,000–20,000 vectors drawn **stratified** from the corpus. Exact k-NN over the sample is the ground truth everything else is compared against. |
| `storage_amplification` | the same sample. Replication depends on how *your* corpus clusters, which is exactly what a sample shows and a description cannot. |
| `memory_budget` | the same sample, plus `dimension`. |
| `ambiguous_query_rate` | **50 or more real queries** — logged, not invented. Below 50 it stays couldn't-check; a rate over 12 queries is a number you can compute and should not report. |
| `drift` | a timestamp column on the corpus **and** on the queries. Corpus timestamps alone say when the partition was trained but not which queries are the future ones. |
| `latency_p95`, `qps` | more than a sample: a real engine in an environment where the round trip is small relative to the query. That is `oneground verify` with `verify.target: runpod`. See [VERIFY.md](VERIFY.md). |
| `span_survival`, `self_retrieval` | **text and chunk offsets.** The chunker emits them as it cuts; chunks brought from elsewhere have them derived by an ordered search, and a chunk that is not a verbatim substring is couldn't-check on these two with the reason. Vectors alone: couldn't-check. |
| `length_distribution`, chunk `near_duplicate_rate`, `unresolved_references` | the chunks' text. **No offsets needed** — these three are unaffected by a chunk whose position is unknown. |
| `monthly_budget` | stays declared either way. The price table is list prices with an error band, and the budget verdict uses the **upper** bound. |

---

## The analogy, and its honesty rules

With no sample, the most oneground can offer is: *here is a published corpus
whose declared character matches yours, and here is what we measured on it.*

Four rules govern that, and they are enforced in code rather than by
convention:

1. **An analogy is never a verdict.** Nothing about your corpus is returned.
   The report shows the fixture's own published values under the label
   `analogy — measured on <fixture>, not on your corpus`, and every one of
   them sits under a `fixture_*` key in `report.json` so it can never appear
   beside your own numbers unlabelled.

2. **Matching uses declared fields only** — `corpus_type`, `text_length`,
   `topics_trend`, `time_ordered`, `dimension`, and the embedding model's
   family. Those are the fields you can answer without exporting anything,
   which is what makes Tier 2 zero-friction. A fixture's *measured* values
   play no part in choosing it; using them would be fitting the analogy to the
   answer.

3. **A weak match is no match.** `corpus_type` is weighted above the sum of
   everything else, so "same kind of corpus, everything else different"
   outranks "different kind of corpus, everything else identical". Below the
   floor, the report says there is no analogy and names the near miss and its
   score. A fixture chosen because it was the only one available is a default,
   not an analogy.

4. **You can override.** `nearest_fixture: arxiv-150k` names one directly and
   the report says it was *not* chosen by matching. `none` disables the
   analogy entirely.

**Only a fixture that has actually been built is matchable.** A spec's
`status` has to be `built` or `verified`; a `planned` spec — one written in
full before its build runs, which is how this project commits to a fixture's
rules before it knows the answer — declares an `analogy:` block and is
deliberately skipped until the numbers behind it exist. Matching a corpus to
a fixture whose values are all `TO_BE_FILLED` would offer an analogy to
nothing.

Two fixtures qualify today: `arxiv-150k` (`corpus_type: papers`,
`text_length: medium`) and `stackexchange-150k` (`corpus_type: qa`,
`text_length: short`). Both are time-ordered with trending topics. A
support-ticket corpus still matches neither on `corpus_type`, and so still
correctly gets **no** analogy — that is the honest outcome, not a gap to be
papered over, and adding fixtures until everything matches something would be
the wrong fix.

---

## The capacity arithmetic, and what it refuses

From `size_now` and `dimension`: stored vectors, estimated memory, nodes at
your declared memory budget, and cost from the price table. Every value
carries `kind: derived_from_declared`.

Structure comes from building each family on a **synthetic** isotropic sample
at your declared dimension and asking it for its footprint; memory then scales
linearly. That is exact for:

- `single_node_hnsw` — amplification is 1.0 by construction
- `hash_sharded` — a hash spreads vectors evenly regardless of what they mean

It is **not** exact for `semantic_sharded`, which replicates a vector into
every region whose centroid is within `(1+epsilon)` of its nearest. How many
regions that is depends on how your corpus clusters — the geometry Tier 1
measures and Tier 2 does not have. On isotropic random vectors the answer is
near-uniform and bears no relation to real text embeddings, so that family is
not built at all and its amplification is refused.

Where an analogy fixture published a **measured** amplification, it is offered
as a multiplier and labelled as the fixture's own, so the arithmetic has a
number to stand on and you can see whose number it is. Without one, the
storage arithmetic is not attempted rather than done on a guess. The same rule
governs the epsilon sweep.

`nodes_needed` leaves 30% headroom: a node filled to 100% cannot compact.

---

## What Tier 2 will never do

It will never emit a verdict, and it will never recommend anything. Every
constraint you name comes back `couldnt_check` with the same reason —
*nothing was measured on your corpus: this run declared it rather than
sampling it* — and the report says plainly:

> Nothing is recommended. Tier 2 has measured nothing on your corpus, and a
> recommendation from a description is a guess wearing a verdict's clothes.

If you want a decision, the last entry of the decision log tells you exactly
what to add. It is usually about a day's work and 20,000 vectors.
