# oneground — project charter

*As of 10 September 2026. Part of the oneproof suite: Prevent (onedoor),
Detect (onewatch), Prove (onetrace), Choose (oneground).*

---

## Goal

Make the choice of a retrieval architecture — which vector store, which
index, sharded how, tuned to what — a decision made from evidence measured
on the user's own data, recorded in a form a stranger can re-derive and
check, instead of a decision made from vendor leaderboards, blog posts, and
whatever the last team did.

The long-term aim is for that decision to be machine-consumable: a future
automated pipeline builder should be able to call oneground, receive a
measured recommendation with its receipt, and deploy from the manifest.
oneground is the ground truth that automation stands on.

## Objective

Ship an open-source, local-first tool that:

1. **Characterizes** a sample of the user's embeddings — intrinsic
   dimensionality, boundary crispness between semantic regions, skew,
   ambiguity rate, drift — and reports those numbers as first-class output.
2. **Simulates** each retrieval architecture family on that sample against
   exact ground truth, producing a trade-off surface (recall, fan-out,
   storage, memory) with loss decomposed into partitioning vs. index.
3. **Verifies** the finalists against real engines in a short timed run for
   the numbers simulation cannot produce (latency, throughput, ingest).
4. **Decides**: three honest outcomes per option — meets / fails /
   couldn't-check — a decision log, and a deployable manifest with the
   receipt attached.

And that serves three audiences with one instrument: the implementer who
wants the decision, the learner who wants to see the algorithms work on
their data, and the tinkerer who has an idea and wants it tested.

## Principles (non-negotiable)

- Your data or nothing. No recommendation from a canned corpus.
- No engine of our own, no favourite. Every engine behind one adapter.
- Receipts (re-derivable) and declarations (bytes frozen), never blurred.
- couldn't-check is never rounded up to a verdict.
- Runs on your machine. Your vectors never leave it. No telemetry.
- Nothing labelled as capability that is only planned.

## What we are doing now

**Building the first checkable artifact: the arXiv-150k fixture.**

A public corpus (150k arXiv abstracts, CC0), embedded with pinned weights,
with exact ground truth, the five characterization values, two reference
architecture results, and a MANIFEST of digests — so anyone can install
oneground, rebuild the fixture, and confirm it reproduces the published
numbers within tolerance. It is the proof that "true baseline" is a
verifiable claim, not a slogan. It also yields the hero image (the ground
view) and the drift headline (recall before vs. after a field trends).

Status of the build:

| task | what | state |
|---|---|---|
| 001 | repo skeleton, fixture pipeline dry run on synthetic data | done |
| 001b | reproducible `characterization.json` (timestamp split out) | done |
| 002 A | newline pinning, projection declared, pod run script | done |
| 002b | projection step non-fatal, manifest written first | done |
| 002 B | canonical build on RunPod (developer runs) | done |
| 003 | publish values, `status: built`, verify | done |
| 003b | republish build 2, reconcile docs | done |
| 003c | torch in receipts, loose ends | done |
| 004 | ground-view export, both tarballs | done |
| 005 | publish build 3, the ground (hero image) | done |
| 006 | `oneground pod`, the money boundary | done |
| 007 | the package, `oneground characterize` | done |
| 008 | models as plugins, `oneground simulate` | done |
| 009 | `VectorEngine`, Qdrant adapter, `oneground verify` | done |
| 010 | `oneground report`, the first verdicts | done |
| 011 | cloud verify: matched environment, concurrency, cost | done |
| 012 | calibration harness, GloVe fixture, the three layers | done |
| 013 | Tier 2 intake, `status: verified`, value reproduction | done |
| 013b | the pinned-environment guard | done |
| 014 | `0.1.0-preview`: public branch, wheel, release asset | in progress |

Findings so far that changed the design: the pipeline is byte-deterministic
(five of six artifacts identical across rebuilds, the sixth fixed in 001b);
Windows text-mode writes produced CRLF that would have broken cross-platform
digests (fixed in 002 A); UMAP was placed before the manifest and could have
sunk a three-hour build (fixed in 002b). From the canonical build itself:
crispness 0.036 / ambiguity 0.891 on arXiv with bge-base; semantic-sharded
loses on this fixture (0.932 at 3.7x vs 0.997 at 1x); closure at epsilon 0.20
replicates 84% of the corpus to the four-region cap, which is where the 3.7x
comes from; and three builds in three environments agree on values, not bytes,
with build 3's ground-view export reproducing four published values live to
within 0.0005.

**How the work runs.** An orchestrator (this chat) writes bounded task
briefs with acceptance criteria and a required report format; a Claude agent
in VS Code builds and reports; the developer commits, runs anything needing
credentials or money, and carries reports back. Gates are never moved to
pass. The git log is the project's own receipt trail.

## Roadmap

### Phase 1 — Foundation (September 2026)
- arXiv-150k fixture built, verified, published as a release asset.
- Build 3 — same pinned environment, records torch; third reproducibility
  data point. **Done** (2026-09-09, RTX PRO 4500 Blackwell).
- Hero image.
- Fourth door on oneproof.dev as *planned*, with the product definition.
- `VectorEngine` adapter protocol + Qdrant adapter + conformance test.

### Phase 2 — The simulator (October)
- `models/semantic_sharded/` moved in from the parked benchmark, with a
  sensitivity sweep as its documentation.
- `models/single_node_hnsw/` and `models/hash_sharded/` baselines.
- Characterization module as a reusable library (`oneground characterize`).
- `requirements.yaml` intake: Tier 1 (sample → receipts) and Tier 2
  (description → fixture analogy + capacity arithmetic, no verdict).
- Fixture value-reproduction in `fixture verify` (tolerances, not digests).

### Phase 3 — The advisor (November)
- Report generator: trade-off surface, three outcomes, decision log,
  manifest export, HTML + JSON.
- Verification runner: timed runs against pinned engines, local or RunPod.
- Cost model with error bands.
- pgvector adapter. Second fixture (StackExchange, fuzzier boundaries) so
  the tool can show a corpus where semantic sharding loses.
- **v0.1 release**: characterize + simulate three families + verify two
  engines + report. The point at which oneground beats folklore for the
  majority of RAG projects.

### Phase 4 — The lab (Q1 2027)
- The ground view and the query trace as interactive renderers over
  simulator state — visuals drawn from the same model the numbers come from.
- Cluster heat view (overflow vs. read replicas under a skewed stream).
- Second embedding model on the same corpus (pre-computed arXiv embeddings
  exist on Kaggle) to show how model-dependent the recommendation is.

### Phase 5 — Proposals (Q2 2027)
- Tier-1 (parametric) proposal loop: plain-language idea → translated
  policy (visible, editable) → adversarial review → pre-registered
  prediction → run → card, pass or fail.
- Public library of settled proposals, failures kept.
- Tier-2 (structural) triage queue, maintainer-reviewed.

### Later
- Disk-tiered family; filtered-search measurement; hybrid search.
- Hosted demo on public fixtures (local stays the product).
- Machine-readable decision output consumed by an automated pipeline builder.

## What would make us stop or change course

- The characterization values prove unstable on stratified 10–20k samples
  (the "never asks for your whole corpus" claim depends on this).
- Verification latency numbers cannot be made reproducible enough to carry
  a verdict — then verify becomes declared-only and the report says so.
- A family's simulator cannot be validated against its real-engine
  counterpart within tolerance — that family ships as couldn't-check until
  it can.

Each of these is a finding worth publishing, not a failure to hide.
