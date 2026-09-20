# oneground — project charter

*As of 13 September 2026. Part of the oneproof suite: Prevent (onedoor),
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

**The product ships once, when it is ready and tested, with no date.** Four
commands that run end to end — characterize, simulate, verify, report — two
engine adapters behind the `VectorEngine` protocol, two public fixtures with
their receipts, and a calibration history every report cites. What is *not*
in it is named here and in the README's "What is planned", with no date
attached to anything, built or unbuilt.

`main` **is** the product. A task branch merges into it the moment its checks
are green — the suite, the environment guard, the tracked-tree identifier
scan confirmed to run rather than skip, and the hosted site byte-compared —
rather than waiting for a window. The only public tag is `0.1.0-preview`.

**Two checkable artifacts: the arXiv-150k and stackexchange-150k fixtures.**

A public corpus (150k arXiv abstracts, CC0), embedded with pinned weights,
with exact ground truth, the five characterization values, two reference
architecture results, and a MANIFEST of digests — so anyone can install
oneground, rebuild the fixture, and confirm it reproduces the published
numbers within tolerance. It is the proof that "true baseline" is a
verifiable claim, not a slogan. It also yields the hero image (the ground
view) and the drift headline (recall before vs. after a field trends).

Task 016 added the second: **stackexchange-150k**, 150k Stack Overflow
questions under CC BY-SA, built to the same rules so the two can be read line
for line. Its brief forbade steering it toward a corpus that makes semantic
sharding win, and it did not: the Q&A ground is *blurrier* than arXiv's
(crispness 0.011 against 0.036). The two are compared in `docs/FIXTURES.md`.

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
| 014 | `0.1.0-preview`: public branch, wheel, release asset | done |
| 014b | calibration in CI, the first two defects | done |
| 014c | the calibration push, tested against a stubbed remote | done |
| 014d | the push step deleted the script it was about to run | done |
| T1 | teaser: the ground, measured in the browser | done |
| T2 | the verdict, and `status: verified` | done |
| T3 | site and teaser hosted on Pages, by artifact | done |
| 015 | pgvector adapter, two-engine matched verify | done |
| 015b | two tests that were green for reasons that were not correctness | done |
| 016 | **stackexchange-150k: the second fixture** | done |
| 017 | hardening: baked pod image by digest, latency spread across runs, `qps_max`, truncation accounting, tracked-tree identifier scan | done |
| 017b | the image lock's bootstrap case; one shell-quoting function; sessions vs. their requirements | done |
| 017c | Postgres proved on the pulled image; readiness probes that actually probe | done |
| 017d | the lock check verifies pullability and co-change, and never rebuilds | done |
| 017e | the third matched session: spread, `qps_max`, and the comparison sentence that was lying | done |
| 017f | transport recording, runtime settings, the setup split, and the no-lent-outcome property | done |
| 017g | gRPC negotiated and proved against a live engine; the port stated everywhere | done |
| 018 | **the release procedure run end to end**: version, docs pass, release notes, fresh-machine check, tag | done; the dated release it was cut for was dropped, and its tag with it |
| 018b | the coverage walk widened to every rendering path; extras checked against what they install | done |
| 018c | a spawn budget and a readiness budget are not the same number | done |
| 019 | **the claim invariant**: every generated sentence checked against the rows it cites | done |
| 018d | the tag moved to include 018b, 018c and 019 | done |

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

From the second fixture (016), which was specified in full with every value
`TO_BE_FILLED` before it was built, so that the answer could not be steered:
the Stack Overflow ground is **blurrier** than arXiv's, not crisper (crispness
0.011 vs 0.036, ambiguity 0.908 vs 0.891), and semantic sharding loses by more
than it lost there (0.869 vs 0.932 recall@10, at 3.897x vs 3.715x storage).
The routing ceiling sits at the measured recall on both, so the loss is
routing, not the index, and no `efSearch` recovers it. 94.0% of vectors hit the
four-copy cap — a wall, not a tail — which is where the amplification comes
from. And the drift pair runs the *other way*: arXiv improves after its cutoff
(0.522 -> 0.549), Stack Overflow degrades (0.485 -> 0.450), as a topic mix that
turns over outruns centroids trained before it turned.

**Two corpora that look unalike agree on the architecture question and
disagree about time.** That is the v0.1 headline, and the one thing here a
reader should carry to their own time-ordered corpus rather than take on
trust — which is what `oneground characterize` is for.

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
- **The advisor**: characterize + simulate three families + verify two
  engines + report. The point at which oneground beats folklore for the
  majority of RAG projects. Built and run end to end.

  The release procedure was executed twice — once for `0.1.0-preview`, which
  is public, and once for a dated `0.1.0`, which was not published. The wheel
  and the sdist were built and checked and the findings from doing it are in
  `docs/RELEASE.md`; the `0.1.0` tag has since been **deleted**, because it
  named a commit that will never be published. **There is no dated release.**
  The product ships once, when it is ready and tested, and publishing — PyPI,
  the GitHub release, the assets — remains the one step this project does not
  automate.

### Phase 3b — More engines (v0.2 onward)

The unit of contribution, and deliberately the first thing after v0.1: the
project's credibility rests on having no favourite, and two adapters is the
smallest number that can demonstrate that. It is no longer the only index
work on this roadmap — see Phase 3d, which is about what the *simulator*
varies rather than about how many engines it can reach.

- **Milvus** and **Weaviate** are the named next two, behind the same
  `VectorEngine` protocol. Nothing about either is written.
- **The conformance suite is the gate.** `oneground/adapters/conformance.py`
  is what admits an adapter: an engine that passes it is an engine oneground
  can verify against, and an engine that does not is not, whoever wrote it.
  That is what makes this the natural community contribution — the acceptance
  criterion is a test run, not a maintainer's opinion. See
  [ADAPTERS.md](ADAPTERS.md) and [../CONTRIBUTING.md](../CONTRIBUTING.md).
- No adapter ships with a tuned configuration supplied by its vendor. Every
  engine is measured as deployed, and the report says how it was configured.

### Phase 3b2 — A family is a contribution unit, concretely (task 042)

The charter has always named an architecture family as one of the contribution
units. Until task 042 that claim rested on a protocol a contributor could
discover only by reading `models/base.py`, and on whatever acceptance criteria
each family's own task happened to carry. Both are now specific:

- **The protocol is six methods**, documented method by method with what each
  is for and what depends on it, in [FAMILIES.md](FAMILIES.md). `ceiling()` is
  the one that is not negotiable: it is what makes routing loss meaningful,
  and therefore what separates *tune it* from *re-architect*.
- **The gate is a command**, the same shape adapters have:
  `oneground models conformance --module path/to/model.py`, runnable **before**
  a family is registered. Eight checks, each stating what it measured and what
  it means, and naming the protocol requirement on failure.
- **A worked example**, `examples/random_sharded/`, deliberately a bad
  architecture: it partitions and routes at random, so its routing loss is
  large and predictable, and it demonstrates every method without teaching
  anyone to deploy it. It is not registered and cannot be selected.
- **The suite found two defects in the shipped families on its first run** —
  `hash_sharded` accepts more shards than there are vectors without refusing,
  and `semantic_sharded` lets faiss raise where a refusal belongs. Both are
  recorded as findings in `tasks/042-family-conformance.report.md`. A suite
  that had passed everything on the day it was written would not have been
  worth writing.

**No family has been contributed from outside this team.** Three ship, all
written here. The protocol, the document and the gate now exist; whether they
are enough for someone else is not something this project can assert on its
own behalf, and it stays couldn't-check until somebody does it.

### Phase 3c — Chunking measurement (v0.2 at the earliest)

A `characterize` feature, not a separate command: chunking is the
highest-leverage unmeasured decision in a RAG pipeline, and changing it
changes the vector set, so nearest-neighbour ground truth does not carry
across. The position is settled and written down in
[CHUNKING.md](CHUNKING.md); no code implements it, and nothing appears on any
page until it does.

**The four paths, and what each may claim:**

| path | ground truth | model in the loop | may carry a verdict |
|---|---|---|---|
| A. structural — properties of the cut itself | by construction | no | yes, on the structural property |
| B. self-retrieval — does content stay retrievable after the cut | by construction | no | yes, on retrievability |
| C. labelled questions | human labels over the user's corpus | no | yes, scoped to the label set |
| D. generated questions | a model's questions | yes | **never** — an advisory row, its own colour, its own sentence |

A and B ship together as v1. **Self-retrieval is an upper bound on
retrievability, not an estimate of answer quality**, and the report says so
every time it prints one: anchor spans are drawn from the corpus, so they
overlap the text they retrieve. Each span has exactly one **home chunk** — of
the chunks containing it entirely, the one in which it is most centred, ties
to the earliest — and a hit is the home chunk in the top-k; a different
containing chunk is counted separately, so overlap cannot raise the score by
multiplying acceptable answers. The **over-fragmentation bias** is printed
beside every B column rather than left for a reader to notice: self-retrieval
is maximised by chunks too small to answer with, and the structural columns
are what rule that out.

**What the report must refuse to say**, carried here from CHUNKING.md §5:

- that one chunking produces better *answers* than another — not from A, not
  from B;
- that a generated-question score is a measurement of the user's corpus;
- that a structural improvement implies a retrieval improvement — A and B are
  printed side by side precisely so a reader sees when they disagree;
- anything at all about chunking on a corpus supplied as vectors. If the input
  is `.npy` the cut has already happened and is out of the instrument's reach:
  `chunking: couldn't-check — vectors were supplied, not text`.

### Phase 3d — The index algorithm as a choice (v0.2)

Until task 034 the simulator varied the architecture — one index,
hash-partitioned, semantically partitioned — and HNSW's parameters within
each, but not the index algorithm. That was right for the question the
project started from, and it left out the trade a team argues about more
often than sharding: memory against recall.

- **Four families in `simulate`**: `flat`, `hnsw`, `ivf`, `ivf_pq`, all
  measured against exact ground truth, with their knobs declared per algorithm
  in task 026's parameter-table form. `hnsw` is the default and re-labels
  nothing, because every published fixture value was measured under it. See
  [MODELS.md](MODELS.md#the-index-algorithm).
- **Memory measured rather than estimated.** With quantisation, `vectors ×
  dimension × 4` is wrong by an order of magnitude; `footprint()` reports what
  faiss says about the index it built, and the old estimate keeps its name and
  its label.
- **What an engine can build is a separate question, and the tool says so
  before the run.** faiss has four families; Qdrant builds HNSW and nothing
  else, and pgvector's IVFFlat is not faiss's IVF. Each adapter declares its
  families, resolved against a running engine rather than from documentation,
  and a configuration no engine can build is refused at plan time — before a
  pod exists. See [ADAPTERS.md](ADAPTERS.md#index-families).
- **Three states, not two.** A report distinguishes *not verified* — remedy:
  run it — from *not verifiable here* — remedy: a different engine, or an
  adapter that does not exist. Collapsing them would let a reader think a
  missing run was the only thing in the way.
- **Not on this roadmap**: engine-specific index families in the simulator. An
  engine that builds something faiss cannot is a gap in what the simulator can
  predict, and it is named as one rather than papered over by simulating
  something adjacent.

### Phase 4 — The lab (Q1 2027)
- The ground view and the query trace as interactive renderers over
  simulator state — visuals drawn from the same model the numbers come from.
- Cluster heat view (overflow vs. read replicas under a skewed stream).
- Second embedding model on the same corpus (pre-computed arXiv embeddings
  exist on Kaggle) to show how model-dependent the recommendation is.

### Phase 5 — Proposals (Q2 2027)
- Planned, not shipped. [PROPOSALS.md](PROPOSALS.md) is the position written
  before the code, not a description of anything that runs: no command
  translates an idea, runs a proposal or publishes a card.
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
