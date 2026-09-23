# The embedding model — and what changes when it does

> **Naming.** On this page a *model* is an **embedding model**: the thing that
> turns text into vectors. The simulator also has "models", which are
> **architecture families** — how vectors are arranged across shards. They are
> independent and both keep their names, because the collision is in the
> field's vocabulary rather than in this repository. See
> [MODELS.md](MODELS.md) and [FAMILIES.md](FAMILIES.md).

---

## 1. Why this is not a sweep

Every sweep in this tool holds the vectors fixed and varies what is built over
them. Changing the embedding model **changes the vectors**, which changes the
exact k-NN ground truth, which invalidates every number computed against it.

So comparing two embedding models is not a sweep with an extra column. It is
**N complete runs**: N embedding passes, N ground truths, N characterizations,
N sweeps. Nothing is shared but the documents. That is the same structural
fact as chunking — see [CHUNKING.md](CHUNKING.md) — and the two use the same
machinery for the same reason.

It is arguably the larger lever. The embedding decides what *similar* means
for a corpus before any index or partition sees it, and **the five
characterization measures are properties of the embedding, not of the
documents**.

---

## 2. Three registers, and the difference is enforced in code

This is the part that must not be left to a caption. It lives in
[`oneground/embed/compare.py`](../oneground/embed/compare.py), and putting a
measure in the wrong one raises `ComparisonRefused` rather than rendering.

### Comparable — the geometry

`boundary_crispness`, `intrinsic_dimensionality`, `ambiguous_query_rate`,
`skew_top10_share`, drift, the routing ceiling, storage amplification, copies
per vector and the shape of the copies histogram.

These describe the geometry each model produces over the same documents. Each
is measured against that model's own ground truth, and **that is what makes
them comparable rather than a problem with comparing them**: they are
properties of the arrangement, not scores against a shared answer key.

### Per model — not a comparison

`recall@k` and everything derived from it.

Under model A, recall is measured against A's true neighbours. Under model B,
against B's. **Both are correct and they answer different questions.** A
report that puts 0.932 and 0.941 side by side under one "recall" heading is
asserting something false.

They are shown as observations, each naming the ground truth digest it was
scored against, and they are never subtracted, ranked, or placed under one
heading.

### Not measurable here at all

Whether model A's true neighbours are **better answers** than model B's.

That needs relevance labels this tool does not have. It is the same wall the
chunking position hit: structural and self-referential measures are exact and
label-free, and answer quality is not among them.

**A crisper ground is not a better model.** It is a corpus this embedding
separates more sharply — a fact about the geometry, and not about whether the
neighbours it returns answer anyone's question. The statement is written into
the artifact itself, not only into this page, so that a reader who never opens
the docs still meets it.

---

## 3. Two confounds that are not findings

### Dimension is not quality

A 384-dimension model uses half the memory of a 768-dimension one and scores
every candidate proportionally faster, **for reasons unrelated to how well it
separates anything**. The artifact separates the two axes: memory and latency
against the dimension block, geometry against the comparable measures. A
reader must not read "smaller and faster" as "better".

### Truncation is per model

Models declare different `max_seq_length`, so the same corpus truncates
differently under each — and a model that silently drops half of every
document will look distinctive for the wrong reason. Truncation is counted per
model with that model's own tokenizer and reported beside its measures. A rate
materially above the lowest is flagged as a **confound, not a finding**.

This one bites hardest where chunks are long. A chunking strategy that counts
whitespace tokens and a model that counts subword tokens do not agree, so a
chunk cut to 512 whitespace tokens can exceed a 512-subword-token limit.

---

## 4. Declaring models

```yaml
corpus:
  sample:
    text:
      path: corpus.jsonl.zst
      text_field: text
      models:
        - BAAI/bge-base-en-v1.5
        - sentence-transformers/all-MiniLM-L6-v2
```

The name is passed to `sentence-transformers` unchanged, so any model it can
load is usable: a HuggingFace repo id or a local path. There is no list this
project maintains, and **a name that does not resolve is refused naming what
was tried**, before any model embeds anything — a typo in the third name
should not surface after the first has run for an hour.

`dimension` and `max_seq_length` are **read from the model**, not declared by
the user. A declared dimension that disagreed with the model's would be a
number nobody could act on; the vectors are whatever the model produces
either way.

`model` (singular) keeps working and does not re-label: a run naming one model
produces exactly the labels it produced before this existed.

---

## 5. Cost, before the first model runs

`characterize` prints the projected cost before embedding anything, because
"three models" reads like one run with three columns and is three of
everything.

The projection is **measured, not estimated**: it embeds a small sample of the
corpus's real text with each model's own weights and tokenizer, then scales.
That matters because **embedding is token-bound, not record-bound**. Measured
on the developer's laptop with `bge-base-en-v1.5`: 42-token records at 6.5/s
and 552-token records at 0.5/s — a 13× spread from a 13× difference in length.
A rate borrowed from another corpus is wrong in proportion to how much the
record lengths differ.

---

## 6. The same model in two places is not the same vectors

Re-embedding the same text with the same named model in a different
environment does **not** reproduce the original vectors. Measured (task 036):
the published `arxiv-150k` and `stackexchange-150k` vectors were built on CUDA
on Linux; re-embedded on Windows CPU with the same model name and the same
text they come back at **cosine 0.9969 and 0.9985**, with a maximum element
difference of 0.02. That is roughly a thousand times larger than float32
noise.

Two consequences, and the second is the one that bites:

- The model **name** is not the receipt. The weights digest is, and it is
  recorded — but even identical weights do not give identical vectors across
  platforms.
- **Every model in a comparison must be embedded in one environment.** Mixing
  a stored anchor with locally embedded challengers puts a platform difference
  inside the comparison, where it is indistinguishable from a model
  difference. It is cheaper to reuse the stored vectors and it is not sound.

This is the embedding-layer version of what [STATE.md](STATE.md) settles for
simulator state, and the divergence here is far larger.

---

## 7. What the published values depend on

Every published fixture value was measured under `BAAI/bge-base-en-v1.5`, and
every finding this project has published about the three public corpora is
**conditional on that model** until measured otherwise.

*The findings from measuring otherwise are in
`tasks/036-embedding-models.report.md`.*
