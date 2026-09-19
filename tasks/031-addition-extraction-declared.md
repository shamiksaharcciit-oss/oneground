# Task 031, addition — extraction is declared; offsets are recorded

*Replaces both earlier drafts of this addition. To be merged into
`tasks/031-chunking-stage.md` before it is executed.*

---

## Two decisions

**1. oneground takes extracted text and does not run extractors.**

**2. The chunker records each chunk's offsets as it cuts. Derivation by
search is a fallback for text chunked elsewhere, never the normal path.**

---

## Why extraction is declared, not run

The original brief had documents going straight into the chunker. In a
real pipeline they do not: the chunker sits behind an extractor, and the
text has already been through it. The answer is not for oneground to run
extractors — it is to take the text a pipeline already produces, which is
what every existing pipeline already has.

Feeding the chunker raw HTML measures it in a position it never occupies.
Shipping the fixture pre-cleaned bakes the extractor's choices in
invisibly. Running extractors ourselves means dependencies that dwarf the
wheel, a hosted service that would send the user's documents off their
machine, another version to pin on every card, and partial responsibility
for someone else's parser — the position the adapter protocol
deliberately avoids for engines.

So: the requirements file names what produced the text and its version —
`extraction: {tool: unstructured, version: "0.x"}`, or `unknown` with a
stated reason — and it is carried as declared onto every result. A reader
then knows the result is conditional on it. oneground does not verify it
and never executes it.

## Why offsets are recorded rather than derived

The chunker read the text and decided where to cut. The start and end
positions are what it computed *in order to cut at all*. Recovering them
afterwards by searching for the emitted text is reconstructing something
we threw away — the same mistake as recomputing a timing that was known
at the point of production.

So each shipped strategy emits, per chunk: its document, its `start` and
`end` character offsets, and its text. Exact by construction. No string
search, no ambiguity under repetition, and nothing for the user to supply.

This matters more than it looks on this corpus: filings repeat themselves
so heavily that 030 publishes a pre-chunking duplicate baseline, and a
chunk's text can appear many times in one document. Search-based location
would be ambiguous exactly where the fixture is most interesting.

**The fallback, for chunks produced elsewhere.** If a user brings chunks
they cut with their own tool, offsets are derived by locating each chunk
in the text, in emission order with a monotonic cursor, so the *n*th
chunk is found at or after where the (*n*−1)th ended. If a chunk is not
a verbatim substring — a tool that collapses whitespace or normalises
quotes — it is `couldnt_check` on the two containment measures with the
reason, never repaired by fuzzy matching.

**Not onetrace.** onetrace proves an answer rests on the evidence it
cites, at runtime, over a live retrieval system; it has no view of a text
file being split in a batch process. The suite shares a discipline, not
machinery, and depending on a sibling product to recover something our
own code already holds would be the wrong coupling.

## What changes in 031

1. **The input is extracted text** — one record per document, however the
   user produced it. No extractor protocol, adapter, plugin or catalogue.

2. **`chunks.jsonl` carries offsets**, emitted by the strategy, as part
   of the chunker's receipt.

3. **Extraction is declared** in the requirements and carried onto every
   result.

4. **The transfer caveat sits beside the numbers**, not in a footnote: a
   chunking measured under one extraction may not hold under another.
   Two results from differently-extracted text are two observations,
   never a comparison.

5. **Which measures need offsets, stated plainly in the docs**, because
   "offsets required" would otherwise read as a precondition for using
   oneground at all:

   - **Need them:** self-retrieval by containment (a span's home chunk is
     positional) and span survival (did the cut fall inside a unit).
   - **Do not:** length distribution, near-duplicate rate,
     unresolved-reference rate.
   - **Never:** anything downstream of embedding. The vector-database
     path works on vectors and ids and has no idea where a chunk came
     from.

6. **Comparing two extractions needs no new machinery.** A user who wants
   it runs both extractors themselves and brings two corpora; they get
   two results, each declaring its extraction.

## One consequence for 030

030's extraction rule — the one that turns filings into text — is now a
**published artifact of the fixture**: the rule, its parameters, its seed,
its digest, and the rejection count by category, declared in the spec,
named as *a reference for comparison, not a recommendation*. If 030 has
already run when this lands, the spec gains the declaration and nothing is
rebuilt — the rule it used is the rule it publishes.

## What does not change

The chunking strategies, the five structural measures, self-retrieval
with its home-chunk definition, the over-fragmentation caption, the
forbidden claims, and the rule that no model appears in path B.
