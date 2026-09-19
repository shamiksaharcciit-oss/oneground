"""The chunking stage (task 031).

A stage **before** the vector-database simulation, **optional**, and runnable
**in isolation**. Given extracted text it cuts the text into chunks, writes
its own receipt, and the rest of the path continues from the chunks it
produced. Given vectors it reports couldn't-check, because the cut has
already happened and is out of the instrument's reach.

`docs/CHUNKING.md` is the specification. It was written and reviewed before
any code, and where this package and that document disagree the document
wins; any such place is named in the task 031 report.

Two things this package does not do, both deliberate.

**It does not run extractors.** In a real pipeline the chunker sits behind an
extractor and the text has already been through one. Feeding the chunker raw
HTML would measure it in a position it never occupies; shipping pre-cleaned
text would bake an extractor's choices in invisibly; running extractors
ourselves would mean dependencies dwarfing the wheel, or a hosted service
that sends the user's documents off their machine, and partial responsibility
for someone else's parser -- the position the adapter protocol deliberately
avoids for engines. So the requirements file *declares* what produced the
text and its version, and that declaration is carried onto every result.

**It does not search for its own offsets.** Every strategy emits each chunk's
`start` and `end` as it cuts, because those positions are what the strategy
computed in order to cut at all. Recovering them afterwards by searching for
the emitted text reconstructs something we threw away. On this corpus that is
not a nicety: filings repeat themselves so heavily that sec-filings-10k
publishes a pre-chunking duplicate baseline of 56.28% at Jaccard 0.50, and a
chunk's text can occur many times in one document, so a search would be
ambiguous exactly where the fixture is most interesting. Derivation by search
exists only for chunks cut elsewhere, and says so.
"""

from .strategies import (STRATEGIES, Chunk, ChunkingError, UnknownStrategy,
                         chunk_document, declared_strategies, describe,
                         strategy_table)

__all__ = [
    "STRATEGIES", "Chunk", "ChunkingError", "UnknownStrategy",
    "chunk_document", "declared_strategies", "describe", "strategy_table",
]
