# oneground — chunking: the ground-truth position

*11 September 2026, v1.1. From the oneground team, in reply to core's note of the same
date; revised the same day with core's three precisions (the over-fragmentation bias
named beside the B column; the hit definition pinned; the formatter experiment split
into unchanged and changed spans). A position, not a plan: this is what the chunking
feature will be built against when it is built (v0.2 at the earliest), and what the
report will be allowed to say under it.*

---

## 1. Agreement, first

Core's framing is accepted in full: chunking is the highest-leverage unmeasured decision;
changing it changes the vector set, so nearest-neighbour ground truth does not carry
across; and the structural measures (span survival, boundary alignment, near-duplicate
rate, length tail, unresolved references) are the honest v1. Sequencing: not before
v0.2, and nothing on any page until it exists.

This document adds one thing to core's three paths — a fourth that is label-free *and*
about retrieval rather than structure — and then fixes the rules.

## 2. The four paths, and what each is allowed to claim

| path | what it measures | ground truth | model in the loop | may the report issue a verdict on it |
|---|---|---|---|---|
| A. structural | properties of the cut itself | by construction | no | yes, on the structural property — never on answers |
| B. self-retrieval (this note) | whether content stays retrievable after the cut | by construction | no | yes, on retrievability — never on answers |
| C. labelled questions | answer-bearing retrieval | human labels over the customer's corpus | no | yes, scoped to the label set, provenance stated |
| D. generated questions | answer-bearing retrieval | a model's questions | yes | never as a verdict; reported as a labelled, provenance-stated advisory row |

A and B ship together as v1. C is supported as intake if a team has labels (they rarely
do). D is permitted only as its own row, its own colour, and its own sentence: *"this
row was written by a model; it is not a measurement in the sense the rows above are."*
Nothing from D is ever blended into a column that also carries A, B or C.

## 3. Path B — self-retrieval: exact, label-free, about retrieval

**The construction.** Sample anchor spans from the *raw* corpus before any chunking —
sentences, or fixed windows, drawn by a seeded rule so the set is a receipt. For any
chunking strategy, every anchor span has a known home: the chunk (or chunks) that
contain it. That containment is ground truth by construction; no label, no model.

**The measurement.** Embed the anchor span as a query. Retrieve top-k over the
strategy's chunk vectors. Record whether a chunk containing the span is in the top-k
(`self_recall@k`) and at what rank (`self_rank`). Across the sample this is a
distribution, per strategy, comparable across strategies, exact.

**What it measures.** Whether the cut kept content findable: a span whose chunk is
split across a boundary, or drowned in a 2,000-token chunk, shows up here as a drop.
That is a retrieval outcome, not a structural property — and it is the outcome that
structural measures are proxies for.

**The hit definition, pinned.** A span may be contained by several chunks when
strategies overlap, and the definition of a hit decides every comparison, so it is
fixed here and printed in the report:

- Each span has exactly one **home chunk**: among the chunks that contain the span
  entirely, the one in which the span is most centred (largest minimum distance from
  the span to either chunk boundary, in tokens); ties go to the earliest chunk.
- A **hit** is the home chunk appearing in the top-k. A different containing chunk in
  the top-k is *not* a hit for `self_recall`; it is counted separately as
  `containing_hit@k` and reported beside it, with `containing_count` (how many chunks
  contain each span) so the effect of overlap is visible rather than rewarded.

Under this definition, overlap cannot raise `self_recall` by multiplying acceptable
answers; it can only help by giving the span a better-centred home, which is the
effect a reader would want measured.

**What it does not measure, stated in the report every time.** Anchor spans are
*drawn from the corpus*, so they overlap the text they retrieve — an easier query than a
user's question, which is phrased differently and may need content from two chunks.
Self-retrieval is therefore an **upper bound on retrievability**, not an estimate of
answer quality. A strategy that scores badly here is bad; a strategy that scores well
here has cleared a necessary condition, not a sufficient one.

**The known bias, named beside the column.** Self-retrieval is maximised by
over-fragmentation: chunk the corpus into single sentences and every span retrieves its
own chunk at rank one, for a chunking that carries no context and answers nothing. This
failure is predictable and directional, so the report does not wait for a reader to
notice it. Beside every B column it prints: *"Self-retrieval rises as chunks shrink and
is maximised by chunks too small to answer with; the length distribution, the orphan
count, and boundary alignment in the structural columns are what rule that out. Read
them together."* A strategy whose B score is high and whose A columns show a length
p50 under a stated floor is flagged as fragmented, not recommended.

The sentence the report carries for B: *"Under chunking X, 96% of sampled spans
retrieve their home chunk in the top 5 against 78% under chunking Y. This is
retrievability of the corpus's own text, not accuracy on your users' questions, which
this report does not measure."*

**Two refinements that keep it honest.**
- *Paraphrase distance, declared.* Optionally perturb the anchor to move the query away
  from verbatim overlap. Each perturbation rule is seeded, named, and reported as its
  own column; none is a model. Two are built: `drop_first_clause`, and
  `function_words_removed`, which removes a published closed-class word list and keeps
  whatever is left.

  *Corrected in task 031, and the correction matters more than the perturbation.* This
  paragraph previously asked for "use only the sentence's noun phrases". Noun-phrase
  extraction needs a part-of-speech tagger, which is a model, and this path admits no
  model — so the specification was asking for something its own rules forbid, which is
  how a future implementer admits a tagger while believing they are following the
  document. The refusal outranks the optional feature. What replaces it is named for
  what it does rather than for what was wanted: a closed-class removal is not
  noun-phrase extraction, what survives it includes verbs and adverbs, and the rule has
  no idea which is which.
- *Document-level agreement.* For real queries the team already has (logs, no labels),
  measure whether the top-k *documents* agree across chunkings. This is a stability
  measure — it says whether the chunking decision changes what a user would see — and
  it is exact. It is not correctness, and is labelled as agreement.

## 4. Path A — the structural set, with one precision each

- **Answer-span survival** needs a definition of "span" that is not a label. v1 uses
  sentences and structural units (list items, table rows, heading-scoped paragraphs)
  from the document's own markup; "the span that answers a question" is path C and
  needs labels. Survival is reported per unit type.
- **Boundary alignment** needs the document's structure to be recoverable. For plain
  text it is couldn't-check; for markdown/HTML/PDF-with-structure it is measured. The
  report says which.
- **Near-duplicate rate** at a stated similarity threshold on the chunk vectors (exact
  k-NN, same machinery as today), reported with the threshold.
- **Length distribution** — p5/p50/p95, the orphan count under a stated floor, the
  count at the cap.
- **Unresolved-reference rate** is the one measure in the set that is *not* exact: a
  rule-based detector of chunk-initial anaphora ("this", "it", "the above") is a
  heuristic with a false-positive rate. It ships labelled heuristic, with its rule
  published, and never carries a verdict alone.

## 5. What the report must refuse to say

- That one chunking produces better *answers* than another. Not from A, not from B.
- That a generated-question score (D) is a measurement of the customer's corpus. It is
  a model's opinion of a model's questions; the report says so in the row.
- That a structural improvement implies a retrieval improvement. A and B are reported
  side by side precisely so a reader sees when they disagree.
- Anything about chunking on a corpus supplied as vectors. If the input is `.npy`, the
  cut has already happened and is out of the instrument's reach; the report says
  "chunking: couldn't-check — vectors were supplied, not text".

## 6. The Semantic Formatter experiment, as an instance of the above

Same raw corpus, formatted and unformatted; same chunker; same anchor-span sample.
The spans are split into two sets by a diff between the two corpora — not by the
formatter's own alignment record, which would put the component under test inside the
instrument's ground truth:

- **Unchanged spans** — text the formatter left byte-identical. Present in both corpora,
  no mapping needed. On these, the comparison isolates one question: *does better
  surrounding structure alone change span survival and self-retrieval?* This is the
  controlled result.
- **Changed spans** — text the formatter rewrote (a resolved reference, a repaired
  heading, a de-duplicated paragraph). These cannot be compared span-for-span, so they
  are reported as a separate, labelled observation: the unresolved-reference rate and
  duplicate rate before and after, and self-retrieval of the *rewritten* spans against
  the formatted corpus only. This is where the formatter's intended effect should show
  up, and it is presented as its own row, never merged with the controlled one.

Two numbers, two questions, no instrument depending on its subject. Every number exact
or labelled heuristic; the only model in the loop is the formatter under test. If the
formatter helps, the receipt shows where; if it does not, the same receipt says so.
That is the experiment core asked for, and it costs a fixture and a weekend.

## 7. Built (task 031) — this document is now the specification

What was a position is what the code does. Three strategies, both paths, on
`sec-filings-10k`. Paths C and D remain **unbuilt** and are not scheduled.

### The rule the run added: an alignment rate is unreadable without its ceiling

**`boundary_alignment` must always be published with `alignment_ceiling`
beside it.** A chunking cannot align more starts than it has units to align
to: a unit longer than `max_size` is split, and only the first of its pieces
can begin on the unit's edge. So the achievable maximum is
`units / chunks`, not 1.0, and it is usually around 0.12 on this corpus.

0.0723 against a ceiling of 0.1178 is 61% of what was achievable. 0.0723
against an assumed ceiling of 1.0 reads as a failure. Same number, opposite
conclusions — so the bare rate is not a publishable figure.

### What the three strategies measured

1,000 filings (a declared 10% subsample, seed 20260921; the fixture's own five
measures are on all 10,000 — not the same population), 2,000 anchors, k=5.

| | fixed | sentence | structure |
|---|---|---|---|
| chunks | 158,341 | 185,771 | 182,361 |
| boundary alignment | 0.0003 | 0.0017 | **0.0723** |
| ceiling | 0.1357 | 0.1157 | 0.1178 |
| % of ceiling | 0.2% | 1.5% | **61.4%** |
| span survival | 0.5551 | 0.5607 | **0.6386** |
| `self_recall@5` | **0.2260** | 0.2070 | 0.2195 |
| `containing_hit@5` | 0.2485 | 0.2600 | **0.2725** |

### The finding, and it is the argument for the side-by-side rule

**The structure-aware strategy wins the structural measures by 241× and loses
retrieval.** `structure` aligns 0.0723 against `fixed`'s 0.0003, splits 1,794
fewer Items — and retrieves *worse*: `self_recall@5` 0.2195 against 0.2260.

Neither number is the answer. A reader with only path A would have concluded
that structure-aware chunking is the clear improvement; a reader with only
path B would have concluded it is not worth the trouble. **Both would have
been confident and wrong**, and this happened on the corpus with the best
structure available to disagree on — real Item boundaries, published offsets,
a strategy cutting precisely on them.

This is why A and B are shown side by side, and the reason is now measured
rather than reasoned. §5's refusal — that a structural improvement may not be
reported as implying a retrieval improvement — is not a hypothetical caution.

Note `structure` also has the widest gap between `self_recall` and
`containing_hit` (0.053 against `fixed`'s 0.023): more of its containing
chunks are not the home chunk. Under a hit definition that counted any
container, `structure` would have looked best. It does not under the pinned
one, which is what the pinning is for.

### What each measure needs

- **Need offsets:** self-retrieval by containment (a span's home chunk is
  positional) and span survival (did the cut fall inside a unit).
- **Do not:** length distribution, near-duplicate rate,
  unresolved-reference rate.
- **Never:** anything downstream of embedding. The vector-database path works
  on vectors and ids and has no idea where a chunk came from.

"Offsets required" is therefore not a precondition for using oneground: it is
a precondition for two of the seven columns.

### The cost, measured

Every strategy needs its own embedding pass — different chunks, different
vectors, no reuse. **Comparing N strategies costs N embeds.** Measured on an
RTX PRO 4500: 810 s, 927 s and 897 s for the three, 196–203 chunks/s, 43.9
minutes in total for ~526,000 chunks.

Tokenisation is the one cost that is *not* N-fold: all strategies read the
same offsets, so the document is tokenised once and the offsets shared. At
corpus scale that is the difference between one CPU cost and three.

At full corpus — all 10,000 filings — the three produce 5,294,400 chunks,
about 7.5 hours of embedding alone, 9 to 10 hours and roughly $7. That is the
reason the published comparison is on 10%.

## 8. What is written down now, and nothing else

This document; a `chunking:` section in `docs/CHARTER.md` under v0.2 with the four
paths and the refusal list; and an entry in the roadmap. No code before v0.1 ships, no
page copy until the measurement exists, and the first fixture for it is the arXiv
corpus we already have — abstracts are short, so it is a weak test of chunking and a
good test of the tooling; the real test needs long documents, which the StackExchange
posts partly are and a documentation corpus fully is.

*Sent as position. The self-retrieval construction is the answer to core's closing
question as far as we can see one: label-free, exact, about retrieval — and an upper
bound, which the report will say every time it prints it.*
