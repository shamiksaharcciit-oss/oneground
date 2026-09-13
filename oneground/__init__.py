"""oneground — characterize, simulate, verify, report.

The "Choose" door of the oneproof suite: measure a retrieval architecture
decision on your own vectors, against exact k-NN ground truth, and keep the
receipt.

What exists today is the four commands above -- `characterize` (the five
measures on your own sample), `simulate` (architectures against exact ground
truth), `verify` (finalists against a real Qdrant or pgvector), `report` (the
decision, its log and its receipt) -- plus `fixture verify` (does this
installation reproduce the published values), `pod` (run a session on rented
hardware) and `calibrate`. Two engines have adapters and two public fixtures
are published. Everything else in the charter is planned, and this package
says so rather than implying otherwise.
"""

# PEP 440 for the resolver, the display name for humans. They are separate
# strings because neither is derived from the other, so neither can drift into
# a shape the other cannot read -- `0.1.0rc1` / "0.1.0-preview" was the pair
# the preview shipped. For a final release the two coincide; the fields stay
# because the next pre-release will separate them again, and a field that
# appears only when it differs is a field nobody remembers to set.
__version__ = "0.1.0"
__display_version__ = "0.1.0"
