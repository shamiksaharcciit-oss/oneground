# calibration/history.jsonl

One line per check per run: what this installation measured, what it was
compared against, and whether that cleared a band declared in advance.

This is the file that answers "is the tool still telling the truth about what
it measures?", and it can only answer it by accumulating points. **One line is
a measurement; a trend needs many.**

Written by the harness, never by hand:

    oneground calibrate layers     # the three BLOCKING checks
    oneground calibrate curve      # against published ANN-Benchmarks values
                                   #   (ADVISORY on the glove fixture)
    oneground calibrate engine     # against a real engine
    oneground calibrate show       # render this file as a table

## What blocks and what does not

`outcome_scope` decides. A `contradicted` line whose scope is `blocking` fails
CI and opens an issue; one whose scope is `advisory` is recorded and nothing
else, and never displaces a blocking line as the latest outcome for its check.

The three checks written by `calibrate layers` are blocking. They are the
assumptions every recall in this project rests on, and each has a correct
answer known before the run: corpus reachability 1.0, metric agreement 1.0,
recall-rule tie bound ~0.

The hnswlib curve is advisory, permanently, and the fixture spec says so
rather than the command deciding. It compares two HNSW implementations that
genuinely differ -- faiss at efSearch=e reaches the recall hnswlib reached at
roughly 1.4e to 1.9e -- and gating this project's release on another
project's implementation would be gating on the wrong thing. Its tolerance was
**not** widened: the points still read `contradicted`, which is the honest
reading, and the offset is published beside them.

See [docs/VALIDATION.md](../docs/VALIDATION.md) for what each check actually
compares, and [`.github/workflows/calibration.yml`](../.github/workflows/calibration.yml)
for the cadence.

## The schema

    date              UTC date of the run, YYYY-MM-DD
    check             corpus_reachability | metric_agreement |
                      recall_rule_accounting | glove_curve |
                      simulator_vs_engine
    dataset           the corpus the check ran on
    engine            what produced `measured`; `oneground/single_node_hnsw`
                      when the measurement is the simulator's own
    engine_version    version of that engine
    config            the architecture configuration, in the label form
                      simulate.json uses
    measured          what this installation measured
    reference         what it was compared against, or null when none exists
    deviation         measured - reference, or null
    tolerance         the band deviation had to fall inside
    outcome           verified | contradicted | couldnt_check
    environment       local:<host>, or a pod id
    pins_sha256       digest of requirements.txt
    oneground_version the package version

and, alongside them: `definition` (the sign convention in words, on every
line, so no reader has to know which era a line came from), `outcome_scope`
(`blocking` or `advisory`), `schema`, `source`, and an optional `note`.

`simulator_vs_engine` lines also carry `efSearch` (required from schema 3),
`efSearch_source`, `M` and `efConstruction`. `glove_curve` lines carry
`efSearch`, `deterministic_build`, `build_seconds`, and -- once the fixture
publishes one -- `known_implementation_offset` and `offset_residual`.

## Four rules

**Outcomes are derived, never asserted.** `outcome` is computed at write time
from `deviation` and `tolerance`, and `validate()` refuses any line whose
stated outcome does not follow from its own numbers. A tolerance changed next
year cannot silently re-judge a line written today. `deviation` is rounded to
six decimals first — the same precision every other float in this project is
pinned to — so a point sitting exactly on the band is not contradicted by
floating-point representation.

**couldnt_check is not a pass.** When `reference` is null there was nothing to
compare against. That is a gap in the reference, not evidence of correctness,
and it never fails a workflow either.

**Advisory lines never displace blocking ones.** The monthly job runs against
a moving engine tag so upstream breakage is visible early. A moving tag is not
the contract; the pinned run is.

**Lines are never edited, only appended.** A calibration point that turned out
to be measured wrongly gets a later line saying so, not a correction in place.

## Comparability

A line is comparable to another only when `check`, `dataset`, `engine`,
`engine_version` and `config` all agree — `history.comparable()`. Simulated
recall depends on the parameters the simulator was given and measured recall
on the parameters the engine was built with; a point where those disagree is
not a calibration point at all.

## Schema versions

Task 012 defined the schema above. The first line in this file predates it: it
was written by hand in task 011 from a completed verify run, and uses field
names (`corpus`, `simulated_recall_at_10`, `calibration_error_recall`,
`environment_id`) that no longer appear.

Because the file is append-only, that line was **not migrated**. It is still
on disk exactly as written, and `history.normalize()` translates it on read so
every consumer sees one shape. The translation is faithful with one honest
loss: the seeded line declared no tolerance, so it reaches no verdict and
reads as `couldnt_check` — a measurement that was never gated. Task 011's
report never claimed otherwise.

Task 012b added one more requirement and bumped the version to **3**: a
`simulator_vs_engine` line must carry `efSearch` as its own field, and
`validate()` refuses one that does not. efSearch is not portable across HNSW
implementations (see [docs/MODELS.md](../docs/MODELS.md)), so a calibration
point that does not say which efSearch it was taken at is not comparable to
one from another engine -- and parsing it back out of a config label works
only until a label changes shape.

    schema 1   pre-012, hand-written, no declared tolerance -> no verdict
    schema 2   task 012: derived outcomes, append-only, the field list above
    schema 3   task 012b: efSearch required on simulator_vs_engine lines

Older lines are not rewritten. `normalize()` presents every era in the
schema-3 shape on read, and the required-field rule applies only from the
version that introduced it.

## A correction, 2026-09-10

26 of the 27 lines in `history.jsonl` recorded `environment` as
`local:<hostname>`. They now read `local:<os>-<arch>` —
`local:windows-amd64` for all of them. The one line carrying a pod id,
`tf8sd2usxbblsm`, is unchanged: a pod id names a rented machine that no
longer exists, while a hostname names a person's laptop that does.

**Corrected in place rather than by appending, and that is a deliberate
exception.** This file is append-only for *outcomes*: a contradicted line is
kept, not fixed, and a tolerance is never widened after the fact. An
environment label is not an outcome. No measured value moved — deviation,
tolerance, outcome, every number is byte-identical to what it was, which was
asserted field by field before the file was rewritten. Appending a correction
line would have implied a second measurement was taken, and none was.

The writer was fixed at the same time, so no future line can carry a
hostname: `oneground/environment.py` owns the one function allowed to look at
the platform, and a test walks the package's AST for any other
`platform.node()` call.
