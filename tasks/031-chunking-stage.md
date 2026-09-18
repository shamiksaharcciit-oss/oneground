# Task 031 — The chunking stage

## Setup
Branch `task-031` from `main`, after 030's fixture is built. Commit
`task 031:` and push after every commit. Read `docs/CHUNKING.md` first —
it is the position paper, written and reviewed before any code, and it is
the specification for this task. Where this brief and that document
disagree, the document wins and you say so.

## Why
Chunking is the decision oneground has said it does not measure, and the
one most likely to be the largest lever. The ground-truth position is
settled: structural measures and self-retrieval by containment are exact
and label-free; generated-question scoring is advisory and never a
verdict. This task builds the first two.

## Where it sits
A stage **before** the vector-database simulation, **optional**, and
runnable **in isolation**:

- `oneground characterize` accepts documents as well as vectors. Given
  documents, the chunking stage runs first, writes its own receipt, and
  the rest of the path continues from the chunks it produced.
- `oneground chunk <requirements>` runs the stage alone and reports,
  answering "is my chunking cutting through answers" without committing
  to a full run.
- Given vectors, chunking reports `couldn't check — vectors were
  supplied, not text`, as the position paper requires.

## Do

1. **The chunker.** Strategies as a declared, closed set, each with its
   parameters in the 026 parameter-table form: `fixed` (size, overlap),
   `sentence` (max size, overlap, sentence rule declared), `structure`
   (uses the document's own markup; couldn't-check on unmarked text).
   A strategy is selected, never invented; an unknown one is refused with
   the declared list. The chunker writes `chunks.jsonl` plus a receipt:
   per chunk, its document, its character span, and its strategy.

2. **Path A — the structural measures**, exact except where noted:
   span survival by unit type (sentences and structural units from the
   document's own markup; "the span that answers a question" is path C and
   is not built); boundary alignment (measured where structure exists,
   couldn't-check on plain text, and the report says which); near-duplicate
   rate at a stated threshold **reported against the corpus's own
   pre-chunking baseline**, which 030 publishes; length distribution with
   p5/p50/p95, the orphan count under a stated floor and the count at the
   cap; unresolved-reference rate, rule-based, **labelled heuristic**, its
   rule published, never carrying a verdict alone.

3. **Path B — self-retrieval by containment.** Sample anchor spans from
   the raw text by a seeded rule. Each span has exactly one **home chunk**:
   among the chunks containing it entirely, the one in which it is most
   centred (largest minimum distance to either boundary, in tokens); ties
   to the earliest. A **hit** is the home chunk in the top-k.
   `containing_hit@k` is reported separately, with `containing_count`, so
   overlap is visible rather than rewarded. Optional perturbations, each
   seeded, named and its own column: drop the first clause; noun phrases
   only. No model anywhere in this path.

4. **The bias, beside its own column, every time.** Self-retrieval is
   maximised by over-fragmentation. Beside every B column the report
   prints that it rises as chunks shrink and is maximised by chunks too
   small to answer with, and that the length distribution, orphan count and
   boundary alignment are what rule that out. A strategy with a high B
   score and a length p50 under the stated floor is flagged **fragmented**
   and never recommended.

5. **What the report may not say**, tested as the 019 claim invariant is
   tested: that one chunking produces better *answers*; that a structural
   improvement implies a retrieval improvement (A and B are shown side by
   side precisely so a reader sees when they disagree); anything about a
   corpus other than this one.

6. **The cost, measured and stated.** Every strategy needs its own
   embedding pass — different chunks, different vectors, no reuse. Report
   the embedding time per strategy at the fixture's size and say plainly
   in the docs that comparing N strategies costs N embeds.

7. **Run it on 030's fixture**, three strategies, and paste the report.
   Report what it found about extraction variance and boilerplate
   alongside — those are the corpus's properties and the measures should
   distinguish them from a strategy's.

8. **Docs.** `docs/CHUNKING.md` is promoted from position to
   specification: what is built, what each measure means, the refusals,
   the bias caption, and what remains unbuilt (paths C and D).
   `docs/INTAKE.md` gains the documents path.

## Acceptance
- `oneground chunk` runs alone and as a stage; vectors give
  couldn't-check.
- All five A measures and both B columns on 030's fixture, three
  strategies, pasted.
- The bias caption beside every B column; a fragmented strategy flagged.
- Forbidden claims tested; A and B shown side by side.
- Embedding cost per strategy reported.

## Do not
- Put a model in path B. Recommend a chunking on B alone. Let a
  heuristic measure carry a verdict. Invent a strategy outside the
  declared set.
