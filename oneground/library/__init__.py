"""The public library. `docs/LIBRARY.md` is the position; this is its
first slice, per §7: "The first implementation is the card schema and its
validator... The refusals before the capability."

    card_schema    what a publishable library card must carry, and the
                    refusals that keep a card that cannot carry it from
                    being published

Not here: the ledger that counts proposals for §2.4's denominator ("written
by `propose` on every run"), the private-card-to-library-card
transformation, the transport (§6, unsettled), and any submission surface.
A library card is, for now, a dict a caller constructs and hands to
`submit_card` -- how it gets constructed is a later task's job.
"""
