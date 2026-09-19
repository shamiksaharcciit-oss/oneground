# oneground — hybrid retrieval: the position, before the code

*19 September 2026. Written before implementation, in the order the
chunking, proposals and library positions were written: the exam before
the code. It settles what oneground can say about combining a dense and a
sparse retriever, and — more importantly — what it must refuse to say.*

---

## 1. The question, and why it is different from every other one

A hybrid system retrieves twice: a dense vector search and a sparse
lexical one (BM25, SPLADE, an engine's keyword index), then combines them
— by weighted score, or by reciprocal rank fusion. The knob everyone
asks about is the weighting:

> *"`dense_weight` and `sparse_weight` should be tuned against your actual
> retrieval evaluation set."*

That advice is correct and it is also the whole problem. **It presumes
relevance labels.** Most teams do not have them — which is the premise
oneground was built on, and why every measure it ships is label-free.

Every other question this tool answers has a label-free ground truth.
Recall is measured against exact k-NN. Routing loss is measured against
what the partition made reachable. Chunking's self-retrieval is measured
against containment, which is arithmetic on offsets. **Hybrid weighting
has no such anchor**, and this paper exists to say so before someone
builds something that appears to have one.

---

## 2. What oneground must refuse

**A recommended weighting.** There is no label-free way to know whether
moving weight from dense to sparse improved the answers. The tool cannot
recommend a value, cannot rank two weightings, and cannot report a
"best" fusion.

**Recall against dense ground truth as a judgement of a hybrid system.**
This is the trap, and it is subtle enough to be built by accident. Exact
k-NN over embeddings is *the dense retriever's own answer key*. Scoring a
hybrid configuration against it measures how closely the hybrid
reproduces pure dense retrieval — so the weighting that "wins" is always
`sparse_weight: 0`, by construction, and the number looks like a finding.
A report that did this would be confidently, plausibly wrong, which is
the failure mode this product exists to prevent.

**Any figure that implies fusion helped.** Without labels, "helped" is
unmeasurable here. The word does not appear in a hybrid result.

---

## 3. What oneground can measure, exactly and without labels

The useful question is not *what weighting is best* but **whether fusion
can matter on this corpus at all** — and that is answerable.

### 3.1 Retriever disagreement

For each query, the dense top-k and the sparse top-k, and their overlap.
Reported as a distribution, not a mean.

This is the headline measure, and its interpretation is the paper's main
claim:

- **High overlap** — the two retrievers return largely the same
  documents. Fusion has little to fuse; any weighting produces nearly the
  same result, and the tuning advice is nearly moot on this corpus.
- **Low overlap** — they disagree substantially, so the weighting
  materially changes what the user sees. Fusion *can* matter here, and
  the weight is a real decision — **which oneground still cannot make for
  you, because deciding it needs labels.**

A team learning that their two retrievers agree on 90% of queries has
learnt something actionable and cheap: do not spend a week tuning a knob
that cannot move much.

### 3.2 Where each retriever is alone

Per query: documents only dense found, only sparse found, both found. And
the corpus-level distribution of those three counts. A corpus where
sparse alone surfaces a large, consistent set is one where lexical signal
carries something the embedding does not — exact identifiers, rare
tokens, quoted phrases. That is a *property of the corpus*, measurable,
and stated as such rather than as a recommendation.

### 3.3 Sensitivity of the output to the weight

Sweep the weight and measure **how much the top-k changes**, not whether
it got better. Rank correlation between adjacent weightings, and the
weight range over which the top-k is stable. A corpus whose top-k is
unchanged from 0.3 to 0.7 tells you the knob is flat there; one that
flips at every step tells you the opposite. Both are facts about the
corpus and neither is a verdict.

### 3.4 Cost

A hybrid system runs two retrievals and a fusion. Latency of each side,
of the fusion, and of the whole, measured the way every other latency in
this tool is measured — under load, at the declared concurrency, with the
attribution rules intact.

---

## 4. What the corpus must carry

Sparse retrieval scores tokens, so a fixture of vectors alone cannot
support any of this. `arxiv-150k` as published cannot be used;
`sec-filings-10k` keeps its documents and can. Any user bringing vectors
without text gets `couldn't check` on the whole hybrid section, with the
reason — the same shape as drift without a timestamp column.

The sparse retriever itself is **declared, not run**, on the same
reasoning as extraction in the chunking position: oneground does not
become responsible for someone else's BM25 implementation, its
tokenisation or its stopword list. The user supplies sparse results, or
names an engine whose adapter exposes lexical search, and the tool
records which and what version.

---

## 5. If labels exist

A team that *does* have relevance labels can answer the real question,
and the tool should let them — clearly separated from everything above.

Labelled evaluation is a distinct mode: the labels are a declared input,
their provenance and coverage recorded, and every figure derived from
them is marked as depending on them. A weighting comparison under labels
is a legitimate result *for that label set*, and the report says so: it
does not generalise to another corpus, another label set, or the same
corpus labelled by someone else.

This is the same register separation the library position draws between
comparable, not-comparable and not-measurable — and it is the only route
by which "tune against your evaluation set" becomes something oneground
can help with rather than repeat.

---

## 6. The honest summary, for the docs

> oneground cannot tell you what to set `dense_weight` to. Nothing can,
> without relevance labels for your corpus. What it can tell you is
> whether the knob matters on your data: how often your two retrievers
> disagree, what each finds that the other misses, how far the weight can
> move before your results change, and what running both costs. If your
> retrievers agree on nine queries in ten, the tuning advice everyone
> repeats is nearly moot for you — and that is worth knowing before you
> spend a week on it.

---

## 7. What this position does not settle

- Whether to ship a reference sparse retriever for corpora that bring
  none. Declaring rather than running is the default; a reference BM25
  for the fixtures alone may be justifiable and is not decided here.
- Reciprocal rank fusion versus weighted score: both are declared
  strategies and neither is endorsed, but which are implemented first is
  open.
- Whether disagreement predicts anything about fusion's *value*. It
  predicts that fusion can change the output. Whether a changed output is
  a better one is exactly the thing needing labels, and the paper claims
  nothing beyond the distinction.
- The interaction with reranking: a hybrid candidate set reranked exactly
  is a real pipeline shape, and the three-way decomposition would need a
  fourth term. Not settled here.

---

## 8. Sequencing

Not before the label question is settled with a real user, because the
measures in §3 are worth building only if teams without labels are the
common case — which this project believes and has not verified. The first
implementation is §3.1 alone: retriever disagreement on a corpus that has
text, with the refusals of §2 in place before any of the capability.

*The exam, before the code.*
