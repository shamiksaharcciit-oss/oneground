# oneground/

The package. It measures a retrieval architecture decision on a corpus of
embeddings against exact k-NN ground truth, and keeps the receipt: every
number is either re-derivable from seeds and rules, or recorded and labelled
as declared. Its three outcomes are always kept apart — verified /
contradicted / couldn't-check — and couldn't-check is never rounded up. It is
local-first: no telemetry, no runtime network calls, and nothing that sends a
user's vectors anywhere.

## What exists today

- **`characterize`** — the five measures (intrinsic dimensionality, boundary
  crispness, ambiguous query rate, region skew, drift) on a sample of your own
  vectors, with receipts.
- **`simulate`** — a configuration sweep over three architecture families
  (`single_node_hnsw`, `semantic_sharded`, `hash_sharded`) against exact
  ground truth, emitting a trade-off table in which every row carries its
  routing ceiling so loss is decomposed into routing vs. index. It measures;
  it does not decide.
- **`fixture verify` / `fixture build`** — check that an installation
  reproduces a public fixture's published values, or rebuild one from its
  spec and seeds.
- **`pod`** — run a build on rented hardware, with the money boundary
  documented in [../docs/POD.md](../docs/POD.md).

## What is planned

Nothing here is implemented, and this package does not imply otherwise.

- **Tier 2 intake** — describe a corpus you have not embedded yet and get a
  fixture analogy plus capacity arithmetic. No verdicts from a description.
- **`verify`** — timed runs against real engines behind one adapter protocol,
  for the numbers simulation cannot produce.
- **`report`** — the trade-off surface turned into a decision: three honest
  outcomes per option, a decision log, and a deployable manifest.

The plan, including what would make the project change course, is in
[../docs/CHARTER.md](../docs/CHARTER.md).

## Layout

    intake/      requirements.yaml loading and validation
    sample/      loading vectors, text, ids, metadata; seeded subsampling
    embed/       pinned-model embedding, weight hashing
    truth/       exact k-NN ground truth
    measures/    the five measures, one module each
    models/      architecture families behind one Model interface
    simulate/    the sweep and the trade-off table
    receipts/    stable JSON, MANIFEST, build_info, the receipt/declared split
    fixture/     building and verifying public fixtures
    pod/         RunPod sessions
