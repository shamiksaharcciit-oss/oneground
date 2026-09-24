"""The VectorDBBench bridge. `docs/BRIDGE.md` is the position; this is the
first slice of it -- the exporter and its round-trip verification, per §8.

    query_subset   the declared, seeded query subset §3.3 says the export
                    cannot honestly proceed without, and no receipt records
                    until this package
    export         writes train.parquet, test.parquet and neighbors.parquet,
                    with the id space, the explicit config and the naming
                    §3 rules on

Not here: the importer (§8, "the first implementation is the exporter and
its verification. The importer follows"), and no CLI command -- §7 leaves
"does the export belong in report or as its own command" unsettled, and
this package does not settle it either.
"""
