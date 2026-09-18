# Task 020 — The simulator state model

## Setup
Worktree `C:\Users\<developer>\projects\oneground-v2`, branch `task-020` from
`main` at `383c7a1`. Work only there; the main checkout is frozen for the
23 September release and another stream is active in it. Commit on
`task-020`; never touch `main`. The developer merges after the release.

## Why
v0.2 is the lab: the ground and the query trace, live, on the user's own
vectors. The teaser proved those views are worth having — but it renders
from a parquet baked by a one-off export script, with the geometry
recomputed in the browser from four pre-computed distances. That is a demo,
not a product.

The lab needs the simulator to *expose its state* as a first-class,
receipted artifact: what the partition is, where each vector went, how a
query was routed, what came back and from where. Everything the lab draws
must be a rendering of that state, never a second computation — the same
rule that makes the report's claims checkable, applied to pictures.

This task defines and emits that state. The lab itself is a later brief.

## Do

1. **Define the state.** `oneground/models/state.py` — dataclasses, with a
   documented JSON encoding and a version field:
   - `PartitionState`: centroids (ids, vectors, sizes), the seed and
     parameters that produced them, and the family that owns them.
   - `AssignmentState`: per base vector — its home region, its copy set
     and count, its distances to the nearest `MAX_ASSIGN` centroids.
     Must scale: 150k × a handful of fields, stored columnar.
   - `RouteState`: per query — the regions scored, the regions probed and
     why (default, ambiguity rule, fan-out), and the ordering.
   - `CandidateState`: per query — every candidate returned, with the
     shard it came from, its score, whether it survived dedupe, and
     whether it is in the true top-k.
   - `LoadState`: per shard — vectors held, queries served, candidates
     contributed, under a given query stream.
   Every field is a measurement or a declared parameter; nothing derived
   that a renderer could compute itself.

2. **Emit it.** `simulate` gains `--emit-state` (off by default): writes
   `state/` beside `simulate.json` — one file per configuration, plus a
   `MANIFEST.sha256` and a `state_info.json` (declared: versions, seeds,
   timings). Receipt/declared kinds as everywhere else. Sizes: report what
   150k × 768 produces for each family at the reference configuration, and
   if any artifact exceeds ~50 MB, say so and propose the columnar or
   sampled form rather than shipping it silently.

3. **Make the models produce it without changing what they measure.**
   Every family implements `state()` returning the above; the conformance
   test gains a state contract (every candidate's shard exists in the
   partition; every probed region was scored; copy counts agree with the
   footprint's storage amplification; candidate ids are a subset of the
   base ids). The published values of both fixtures must not move — prove
   it by re-running the reference configurations and diffing
   `simulate.json` byte for byte.

4. **Prove the state is sufficient — this is the acceptance test, not a
   demo.** Write `corpora/render_from_state.py` that reproduces the
   teaser's two views *from the emitted state alone*, with no access to
   `base.bin`, the export script, or the fixture's parquet:
   - the ground: points coloured by copy count at a given ε, the counters
     (vectors copied, storage amplification, p99 copies);
   - one query's trace: routed region, the regions probed, the true
     neighbours, and which of them the route missed.
   Run it on the arXiv fixture and compare against the teaser's published
   values: crispness 0.036, storage 3.715×, the copies histogram
   (3.6/5.6/6.5/84.3%), and for a named query the count of true neighbours
   outside the routed region. Every one must match within the spec's
   tolerances. A mismatch means the state is missing something — find what,
   add it, say what it was.

5. **Live, on a user's own sample.** Run the whole path — characterize →
   simulate --emit-state → render_from_state — on a 20k synthetic corpus
   and on the StackExchange fixture's sample, and report the wall-clock
   and artifact sizes for each. This is the path the lab will run; if it
   takes minutes rather than seconds, say so now.

6. **Docs.** `docs/STATE.md`: what the state is, the contract, the
   encoding, the rule that every lab view must be a rendering of state and
   never a second computation, and what this task did *not* settle
   (interactivity, incremental recomputation as ε moves, anything about
   the browser).

## Acceptance
- The state contract is in the conformance suite; all three families pass.
- Both fixtures' `simulate.json` byte-identical after the change.
- `render_from_state.py` reproduces the teaser's published figures from
  state alone, within tolerance; report each number beside its published
  value.
- Sizes and wall-clock reported for 150k and 20k.
- `docs/STATE.md` exists.

## Do not
- Touch the main checkout, `main`, the tag, or anything under
  `site/teaser/`. Change a measured value or tolerance. Build any part of
  the lab's interface — that is a later brief.
