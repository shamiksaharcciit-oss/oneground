"""oneground — characterize, simulate, verify, report.

The "Choose" door of the oneproof suite: measure a retrieval architecture
decision on your own vectors, against exact k-NN ground truth, and keep the
receipt.

What exists today is `characterize` (the five measures on your own sample),
`fixture verify` (does this installation reproduce the published values), and
`pod` (run a session on rented hardware). Everything else in the charter is
planned, and this package says so rather than implying otherwise.
"""

# PEP 440 for the resolver, the display name for humans. `0.1.0rc1` is what
# pip compares and what the wheel is named; "0.1.0-preview" is what the
# release page, the teaser and `oneground --version` say. Neither is derived
# from the other, so neither can drift into a shape the other cannot read.
__version__ = "0.1.0rc1"
__display_version__ = "0.1.0-preview"
