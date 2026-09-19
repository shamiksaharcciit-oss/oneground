# Task 036 — The embedding model becomes a variable

## Setup
Branch `task-036` from `main` after 031 has merged — it shares 031's
machinery and its hardest constraint, and building them twice would be
waste. Commit `task 036:` and push after every commit. The 150k
measurements need a pod and that is a developer's `y`.

## Why
A user names a model in `requirements.yaml`, the weights digest is
recorded, and everything downstream measures that embedding. Using a
chosen model is solved. **Comparing two is not, and cannot be, under the
machinery that exists** — because every sweep in the tool holds the
vectors fixed and varies what is built over them. Changing the model
changes the vectors, which changes the ground truth, which invalidates
every number computed against it.

That is the same structural fact as chunking: a dimension that forces a
full re-measure per variant. The two are mechanically the same feature
and should share the machinery.

It is arguably the larger lever. The embedding decides what *similar*
means for a corpus before any index or partition sees it — and the five
characterization measures are properties of the embedding, not of the
documents. arXiv's crispness of 0.036, StackOverflow's 0.011 and the
filings' 0.107 are all measured under `bge-base-en-v1.5`. Whether a
corpus that looks unpartitionable under one model looks different under
another is checkable and nobody here has checked it.

## What is comparable across models, and what is not

This is the hardest part of the task and it must be settled in the code,
not left to a reader.

**Comparable.** The five characterization measures; the routing ceiling;
storage amplification; copies per vector; the shape of the copies
histogram. These describe the geometry a model produces over a corpus,
each measured against that model's own exact ground truth, and comparing
them is the point of the task.

**Not comparable, and must be refused as a comparison.** Recall@k. Under
model A it is measured against A's true neighbours; under model B against
B's. Both are correct and they answer different questions. A report that
puts 0.932 and 0.941 side by side under a single "recall" heading is
asserting something false. They may be shown as two observations, each
naming its ground truth, never as a comparison.

**Not measurable here at all, and stated as the limit.** Whether model A's
true neighbours are *better answers* than model B's. That needs relevance
labels the tool does not have, and it is the same wall the chunking
position hit: structural and self-referential measures are exact and
label-free, and answer quality is not among them. Say so in the docs
rather than letting a reader infer that a crisper ground is a better
model.

## Do

1. **Models as a declared, closed-ish set with an escape.** In 026's
   parameter-table form: any `sentence-transformers` model resolvable by
   name, with its weights digest recorded as today, plus `dimension` and
   `max_seq_length` read from the model rather than declared by the user.
   A model that cannot be resolved is refused naming what was tried.

2. **One run per model, and say so loudly.** `characterize` gains
   `models: [a, b, c]`, and for each: its own embedding pass, its own
   exact k-NN ground truth, its own characterization, its own
   `simulate`. Nothing is shared between them except the sample of
   documents. Report the wall clock and the cost per model before the
   first one runs, so a user choosing three models knows they have chosen
   three of everything.

3. **The comparison artifact.** A `models.json` and its rendering: the
   comparable measures side by side, the non-comparable ones shown per
   model with their ground truth named, and the not-measurable limit
   stated in the artifact rather than the documentation. One table, three
   registers, visibly different.

4. **Dimensionality is not quality.** A 384-dimension model will use half
   the memory and search faster than a 768-dimension one for reasons
   unrelated to how well it separates anything. The report separates the
   two: memory and latency attributable to dimension, and geometry
   attributable to the model. A reader must not read "smaller and faster"
   as "better" when the two are not the same axis.

5. **Truncation is per model and matters here.** 017's truncation
   accounting counts records exceeding `max_seq_length`. Different models
   have different limits, so the same corpus truncates differently under
   each — and a model that silently drops half of every document will
   look distinctive for the wrong reason. Report truncation per model
   beside its measures, and flag a model whose truncation rate differs
   materially from the others as a confound rather than a finding.

6. **Run it on the three fixtures**, with `bge-base-en-v1.5` as the
   anchor (every published value was measured under it) and at least two
   others of different dimension and family. Paste the table. Then write
   the findings from the numbers, in particular: whether the ordering of
   the three corpora by crispness is stable across models, or whether a
   corpus's ground depends more on the model than on the corpus. Either
   answer is a finding and the second would be the more consequential.

7. **Published values do not move.** Every fixture's published values
   were measured under `bge-base-en-v1.5`. Adding the variable must not
   change one — `model` at its default must not re-label, per 032, and
   the reference configurations must diff clean.

8. **Docs.** `docs/MODELS.md` — note the name collision with the
   architecture families and resolve it; embedding models may want their
   own page. State the three registers of comparability, the
   dimensionality confound, and the label limit.

## Acceptance
- Multiple models measured on one corpus, each with its own ground truth.
- The comparison artifact shows comparable, non-comparable and
  not-measurable in visibly different registers.
- Truncation reported per model; a material difference flagged as a
  confound.
- Cost stated before the first run.
- The three fixtures swept; findings written from the numbers including
  whether crispness ordering is stable across models.
- Published values and reference labels unchanged.

## Do not
- Compare recall across models. Call a crisper ground a better model.
  Reuse one model's ground truth for another. Let `model` at its default
  re-label. Claim anything about answer quality.
