# Task 031 — The chunking stage

## Setup
Branch `task-031` from `main`, after 030's fixture is built. Commit
`task 031:` and push after every commit. Read `docs/CHUNKING.md` first —
it is the position paper, written and reviewed before any code, and it is
the specification for this task. Where this brief and that document
disagree, the document wins and you say so.

**One consequence for 030, which this task depends on.** 030's extraction
rule — the one that turns filings into text — is a **published artifact of
that fixture**: the rule, its parameters, its seed, its digest, and the
rejection count by category, declared in the spec and named as *a reference
for comparison, not a recommendation*. If 030 has already run when this
starts, the spec gains the declaration and nothing is rebuilt — the rule it
used is the rule it publishes.

## Why
Chunking is the decision oneground has said it does not measure, and the
one most likely to be the largest lever. The ground-truth position is
settled: structural measures and self-retrieval by containment are exact
and label-free; generated-question scoring is advisory and never a
verdict. This task builds the first two.

**And two decisions about what the stage is given, and what it keeps.**

*oneground takes extracted text and does not run extractors.* In a real
pipeline the chunker sits behind an extractor and the text has already been
through it. Feeding the chunker raw HTML measures it in a position it never
occupies; shipping a fixture pre-cleaned bakes the extractor's choices in
invisibly; running extractors ourselves means dependencies that dwarf the
wheel, a hosted service that would send the user's documents off their
machine, another version to pin on every card, and partial responsibility
for someone else's parser — the position the adapter protocol deliberately
avoids for engines. So the requirements file names what produced the text
and its version, and it is carried as declared onto every result.

*The chunker records each chunk's offsets as it cuts.* The start and end
positions are what the strategy computed **in order to cut at all**;
recovering them afterwards by searching for the emitted text is
reconstructing something we threw away — the same mistake as recomputing a
timing that was known at the point of production. It matters more than it
looks on this corpus: filings repeat themselves so heavily that 030
publishes a pre-chunking duplicate baseline, and a chunk's text can appear
many times in one document, so search-based location would be ambiguous
exactly where the fixture is most interesting. Derivation by search is a
fallback for text chunked elsewhere, never the normal path.

*Not onetrace.* onetrace proves an answer rests on the evidence it cites, at
runtime, over a live retrieval system; it has no view of a text file being
split in a batch process. The suite shares a discipline, not machinery, and
depending on a sibling product to recover something our own code already
holds would be the wrong coupling.

## Where it sits
A stage **before** the vector-database simulation, **optional**, and
runnable **in isolation**:

- `oneground characterize` accepts **extracted text** as well as vectors —
  one record per document, however the user produced it, with no extractor
  protocol, adapter, plugin or catalogue. Given text, the chunking stage
  runs first, writes its own receipt, and the rest of the path continues
  from the chunks it produced.
- **The extraction is declared, never run and never verified**:
  `extraction: {tool: unstructured, version: "0.x"}` in the requirements, or
  `unknown` with a stated reason, carried as declared onto every result so a
  reader knows what the result is conditional on.
- `oneground chunk <requirements>` runs the stage alone and reports,
  answering "is my chunking cutting through answers" without committing
  to a full run.
- Given vectors, chunking reports `couldn't check — vectors were
  supplied, not text`, as the position paper requires.
- **Comparing two extractions needs no new machinery.** A user who wants it
  runs both extractors themselves and brings two corpora; they get two
  results, each declaring its extraction.

## Do

1. **The chunker.** Strategies as a declared, closed set, each with its
   parameters in the 026 parameter-table form: `fixed` (size, overlap),
   `sentence` (max size, overlap, sentence rule declared), `structure`
   (uses the document's own markup; couldn't-check on unmarked text).
   A strategy is selected, never invented; an unknown one is refused with
   the declared list. The chunker writes `chunks.jsonl` plus a receipt:
   per chunk, its document, its strategy, its text, and its `start` and
   `end` character offsets — **emitted by the strategy as it cuts, exact by
   construction**. No string search, no ambiguity under repetition, and
   nothing for the user to supply.

   **The fallback, for chunks produced elsewhere.** If a user brings chunks
   cut with their own tool, offsets are derived by locating each chunk in
   the text, in emission order with a monotonic cursor, so the *n*th chunk
   is found at or after where the (*n*−1)th ended. A chunk that is not a
   verbatim substring — a tool that collapses whitespace or normalises
   quotes — is `couldnt_check` on the two containment measures with the
   reason, **never repaired by fuzzy matching**.

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

4. **The captions that sit beside the numbers, every time.**

   *The bias.* Self-retrieval is maximised by over-fragmentation. Beside
   every B column the report prints that it rises as chunks shrink and is
   maximised by chunks too small to answer with, and that the length
   distribution, orphan count and boundary alignment are what rule that out.
   A strategy with a high B score and a length p50 under the stated floor is
   flagged **fragmented** and never recommended.

   *The transfer caveat.* Beside the numbers, not in a footnote: a chunking
   measured under one extraction may not hold under another. Two results
   from differently-extracted text are two observations, never a comparison.

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
   `docs/INTAKE.md` gains the extracted-text path and the `extraction`
   declaration.

   **And which measures need offsets, stated plainly**, because "offsets
   required" would otherwise read as a precondition for using oneground at
   all:

   - **Need them:** self-retrieval by containment (a span's home chunk is
     positional) and span survival (did the cut fall inside a unit).
   - **Do not:** length distribution, near-duplicate rate,
     unresolved-reference rate.
   - **Never:** anything downstream of embedding. The vector-database path
     works on vectors and ids and has no idea where a chunk came from.

## Acceptance
- `oneground chunk` runs alone and as a stage; vectors give
  couldn't-check.
- `chunks.jsonl` carries every chunk's `start` and `end`, emitted by the
  strategy; a chunk set brought from elsewhere derives them with the
  monotonic cursor, and a non-verbatim chunk is couldn't-check on the two
  containment measures with the reason.
- The `extraction` declaration is required, carried onto every result, and
  `unknown` is accepted only with a stated reason.
- All five A measures and both B columns on 030's fixture, three
  strategies, pasted.
- The bias caption beside every B column; a fragmented strategy flagged;
  the transfer caveat beside the numbers.
- Forbidden claims tested; A and B shown side by side.
- Embedding cost per strategy reported.

## Do not
- Put a model in path B. Recommend a chunking on B alone. Let a
  heuristic measure carry a verdict. Invent a strategy outside the
  declared set.
- Run, bundle, verify or take responsibility for an extractor.
- Derive offsets by search on the normal path, or repair a non-verbatim
  chunk by fuzzy matching.

## What this addition did not change
The chunking strategies, the five structural measures, self-retrieval with
its home-chunk definition, the over-fragmentation caption, the forbidden
claims, and the rule that no model appears in path B.
