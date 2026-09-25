"""The VectorDBBench bridge. `docs/BRIDGE.md` is the position; this package
is the exporter (§8's first slice) and the importer that follows it (§4).

    query_subset    the declared, seeded query subset §3.3 says the export
                    cannot honestly proceed without, and no receipt records
                    until this package
    export          writes train.parquet, test.parquet and neighbors.parquet,
                    with the id space, the explicit config and the naming
                    §3 rules on
    import_result   reads a result file VectorDBBench already wrote: raw
                    per-case numbers, a failure or timeout as couldnt_check,
                    and §4's table rule refused at construction

No CLI command -- §7 leaves "does the export belong in report or as its own
command" unsettled, and this package does not settle it either.
"""
