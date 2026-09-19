# Task 035 — The rerank stage

## Setup
Branch `task-035` from `main` after 034 has merged — it needs `flat` as a
declared index, because the exact scoring pass is that index applied to a
candidate set. Commit `task 035:` and push after every commit.

## Why
oneground models single-stage retrieval: a query goes to an index and
comes back with `k` results. Production pipelines frequently do something
else — retrieve `k × n` approximately, score those candidates exactly,
keep the best `k`. It is one of the two standard uses of exact search,
and the tool is silent on it.

The question a team actually has is not "is reranking good" but **"does
the recall it recovers justify the latency it costs, on my corpus?"** —
and that is a measurement, corpus-dependent, which is what this tool is
for. It is the same shape as chunking: a stage the pipeline has that the
simulator does not model. It is far smaller to build, because it needs no
new corpus and no new ground truth — only a second scoring pass over a
candidate set the first pass already produced.

## Do

1. **The stage, declared.** `rerank` becomes a declared parameter of the
   search path, in 026's parameter-table form: `rerank: none` (the
   default, and it must not re-label an existing configuration, per 032)
   or `rerank: exact` with `candidates` — the multiplier or absolute
   count retrieved before scoring. An unknown rerank mode or a knob
   belonging to another is refused with the declared list.

2. **What it does.** Retrieve `candidates` results from the configured
   index, score them exactly against the query with the corpus's own
   metric — the `flat` index from 034, applied to a candidate set rather
   than to the corpus — and return the top `k`. Exact scoring of a
   candidate set is exact by construction, so nothing here is
   approximate except what the first pass returned.

3. **The decomposition gains a third term, and it is the point.** Today
   recall splits into routing loss and index loss. With reranking it
   splits into three:
   - **routing loss** — what the partition made unreachable. Unchanged by
     reranking, by definition; verify it.
   - **candidate loss** — true neighbours not in the candidate set. This
     is the ceiling reranking cannot exceed, and it is what `candidates`
     buys.
   - **ordering loss** — true neighbours in the candidate set but ranked
     out of the top `k`. **This is what reranking recovers, and only
     this.**
   The report must show all three. A user whose loss is mostly candidate
   loss learns that reranking will not help them, which is a more useful
   answer than a recall number.

4. **Cost, measured on both sides.** Per configuration: query time with
   and without reranking, the exact-scoring time alone, and the candidate
   multiplier's effect on each. Reranking is bought with latency and the
   report must price it in the same row as the recall it recovers — never
   the gain without the cost.

5. **The crossover, which is the question behind the question.** Sweep
   `candidates` and report where the recovered recall flattens. Then
   report, beside it, the recall and latency of `flat` over the whole
   corpus at the same sample size — because for a small enough corpus the
   honest answer is *do not approximate at all*, and the tool should be
   able to say so rather than assuming approximation is required.

6. **Run it on both fixtures** with the four index algorithms from 034,
   and paste the table. Then write the findings from the numbers, in
   particular: how much of each corpus's index loss is ordering rather
   than candidate loss — which decides whether reranking is worth
   anything there — and whether the two corpora agree. They disagreed
   about drift, agreed about architecture, and 034 will say whether they
   agree about quantisation.

7. **What the report may not say**, tested as the claim invariant is
   tested: that reranking is recommended; that a candidate multiplier
   that worked on one corpus works on another; that recall recovered at
   this sample size holds at full scale. And it must never report the
   recall gain without the latency beside it — a gain shown alone is the
   kind of number this product exists to refuse.

8. **Docs.** `docs/MODELS.md` gains the stage, the three-way
   decomposition and what each term means for a decision. `docs/INTAKE.md`
   gains `rerank` in the constraint set, since a latency budget now has a
   second thing competing for it.

## Acceptance
- `rerank: none` is the default and does not re-label; `rerank: exact`
  works across all four index algorithms and all three families.
- Routing loss unchanged by reranking, verified.
- The three-way decomposition reported, with ordering loss identified as
  the only term reranking recovers.
- Latency with and without, in the same row as the recall.
- The sweep on both fixtures pasted, findings written from the numbers.
- Published fixture values unchanged.

## Do not
- Recommend reranking. Report a recall gain without its latency. Let
  `rerank: none` re-label. Rerank with anything but exact scoring — a
  model-based reranker is a different feature, a different position paper
  and not this task.
