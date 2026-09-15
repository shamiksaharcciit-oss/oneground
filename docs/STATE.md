# State — what the simulator did, as a receipt

`simulate.json` says *how well* each architecture did: recall, ceiling, storage,
fan-out. It does not say what the architecture *did*: where each vector went,
how a query was routed, what each shard sent back. The lab draws exactly those
things. **State** is that second half, written as an artifact beside the table
and held to the same standard as the table.

The format lives in [`oneground/models/state.py`](../oneground/models/state.py).
The reference renderer is
[`corpora/render_from_state.py`](../corpora/render_from_state.py).

---

## The rule

> **Every lab view is a rendering of state. No view recomputes.**

A view that needs a number the state does not hold must not go back to the
vectors, re-run k-means, or re-derive a route. That would produce a second
measurement that can disagree with the first, and nothing on screen would say
which one the table was built from.

When a view finds that the state is missing something, that is a defect in the
state. Add the field in `state.py`, document it in `_MEANINGS`, have each family
fill it, and extend the contract if it can be checked. Then render it. Task 020
had to do this once, below.

The same rule makes the renderer honest about gaps. `render_from_state.py`
reports `couldnt_check` and names the missing field rather than filling it in,
and it exits non-zero when anything it was asked to draw is unanswerable.

---

## What is in it

One `ModelState` per configuration, in five parts. Every field is a
measurement or a declared parameter.

| part | per | holds |
|---|---|---|
| `PartitionState` | region | region ids, home populations, centroids (k-means only), `kind` (`kmeans` / `hash` / `single`), seed, parameters |
| `AssignmentState` | base vector | home region, copy set (nearest first, `-1` unused), copy count, distance to its nearest `max_assign` centroids (`NaN` where the family has none) |
| `RouteState` | query | regions scored with their distances, regions probed in probe order, and why each was probed |
| `CandidateState` | query | its exact top-`true_k` neighbour ids; every candidate a shard returned before the merge, with its shard, its score, whether it survived dedupe, and its rank in the true top-k |
| `LoadState` | shard | vectors held (counting copies), queries that probed it, candidates it contributed |

Probe reasons are one byte per probed slot:

| code | meaning |
|---|---|
| 0 | default: the nearest region |
| 1 | probe: an additional region, because `probe > 1` |
| 2 | fan-out: every shard, because the family does not route |
| 3 | ambiguity rule; reserved, and no current family writes it |
| 255 | padding |

Distances are **non-squared Euclidean**, as
`measures.crispness.centroid_dists` returns them. faiss returns squared
distances, but crispness (1.20) and the ε closure (1 + ε) are ratios of real
distances. The header states the convention so a renderer never has to assume
it.

### What is deliberately not in it

- **The vectors.** A state file holds ids, regions, distances and scores, not
  embeddings.
- **2-D positions.** The teaser places points with a UMAP projection that the
  fixture spec declares illustrative. It is not a measurement and the simulator
  does not produce one, so the ground renders copy counts per point without
  positions.
- **Text and metadata.** Titles and categories belong to the corpus, not to
  what the architecture did.

State is still derived from a user's corpus. Centroids are means of their
vectors, and neighbour ids index into their sample. Like every other receipt it
stays where it was written. Nothing in oneground sends it anywhere.

---

## The field step 4 found missing: `candidates.true_ids`

The state was first specified with candidates carrying "whether it is in the
true top-k". That names a true neighbour only if some probed shard *returned*
it. A neighbour the route never reached is by definition not a candidate, so it
had no id in the state. Neither "how many true neighbours lie outside the routed
region" nor "which ones the route missed" could be answered for any query that
lost one. Those are exactly the queries a routing view exists to show.

It was found by rendering, not by review. On a synthetic harness (1,200 × 32,
60 queries), the first renderer could answer 58 of 60 queries' outside counts.
All 58 matched an independent count from the raw vectors, and the other 2 were
unanswerable. `CandidateState.true_ids` holds each query's exact top-`true_k`
ids whether or not the route reached them, and closes the gap.
`render_from_state.py` still reports how many queries the candidates alone
could have answered, so the size of that gap is measured on every run.

At scale it was not an edge case. Measured on `semantic_sharded` at ε 0.2,
probe 2, with 2,000 queries on each corpus:

| corpus | answerable from candidates alone | with `true_ids` |
|---|---|---|
| arXiv 150k | 1,391 of 2,000 | 2,000 of 2,000 |
| StackExchange 20k sample | 628 of 2,000 | 2,000 of 2,000 |

With the field in place, every arXiv figure rendered from state matched what
the teaser published: crispness, storage, the copies histogram, and the routed
region and outside count for all 2,000 queries. The comparison is in
`tasks/020-simulator-state.report.md`.

---

## The contract

`contract_violations(state, footprint)` returns every way a state breaks the
contract; an empty list means it holds. The conformance suite runs it for every
registered family (`oneground/models/test_conformance.py`):

- every candidate's shard exists in the partition
- every probed region was scored, except under fan-out, which scores nothing
  because it chooses nothing
- copy counts agree with the family's own `footprint().amplification`
- candidate ids are a subset of the base ids, and so are `true_ids`

It also checks the shapes that make those four well-defined: offsets are
monotone from 0, copy-set slot 0 is the home region, and load totals equal the
parts they are counted from.

The suite also checks the state against the architecture itself: merging a
state's candidates with `base.merge_candidates` must reproduce `search()`'s ids
and scores exactly. A state that satisfies the contract but describes a
different search is still wrong.

A family implements `state(built, queries, k, config, gt_ids, seed)` and must
not change what it measures to do so. `state()` is called after the row is
measured and before the index is released.

---

## Emitting it

```
oneground simulate requirements.yaml --emit-state
```

Off by default. When it is on, `simulate` writes a `state/` directory beside
`simulate.json`:

```
state/
  <family>__<id8>.state.npz    one per configuration
  state_info.json              declared: versions, seeds, sizes, timings
  MANIFEST.sha256              digests of everything above
```

`<id8>` is the first eight hex digits of the sha256 of the config label. Labels
carry `[`, `]`, `=` and `,`, which no filename should have to survive. The label
itself is in the header.

`simulate.json` is unchanged by the flag. Every value in it is measured before
`state()` is called.

### `simulate.json`'s format changes in v0.2

This change moves no measured value. Task 020b took `build_seconds` and
`query_seconds` out of `simulate.json`'s rows and put them in
`simulate_info.json` under `timings`, keyed by config label and declared.

- **Why.** They are wall clock: a fact about one machine on one run, not about
  the architecture. While they sat in the rows, no two runs of the same code
  wrote the same bytes, so "simulate.json is unchanged" could only be checked
  with those two fields masked. Now the file depends only on what was measured,
  and two runs compare byte for byte.
- **What did not change.** Every other field of every row is byte for byte what
  v0.1 wrote. Task 020b checked this against runs of the unmodified tree on
  both published fixtures.
- **What a reader must change.** Anything that read timings from the rows must
  read `simulate_info.json` instead. `oneground report` never based a verdict
  on them. It also stops listing them among an option's measurements, which
  they never were.

---

## The encoding

Each `.state.npz` is an uncompressed zip holding `header.json` and one `.npy`
per column, named `part.field` (for example `assignment.copy_count.npy`). Any
language with a zip reader and the documented `.npy` format can read it.

It is columnar because the base side is a row per vector (150,000 on arXiv) and
the candidate side is hundreds of thousands of rows. A JSON list of that many
objects is an order of magnitude larger than the columns it describes.

It is written deterministically: entries sorted, every timestamp fixed at
1980-01-01, no compression. The same state gives the same bytes, so its line in
`MANIFEST.sha256` identifies it.

`header.json` carries:

- `state_version`
- the configuration's identity: family, label, parameters, seed, `n_base`,
  `n_queries`, `dim`
- each part's scalars
- the route-reason table and the distance convention
- `columns`: for every array, its dtype, its shape and what it means

A reader never has to guess a layout. `read_state()` refuses any
`state_version` it does not understand rather than misreading one.

---

## Not settled

- **Interactivity.** What the lab lets a person change, and which views update
  when they do, is undecided. The state supports drawing; it makes no claim
  about editing.
- **Incremental recomputation as ε moves.** A state is one configuration at one
  ε. Moving ε changes copy sets, shard membership, every graph and every
  candidate, so today moving it means a new `simulate` run.
  `assignment.centroid_dist` holds enough to redraw copy counts at any
  ε ≤ what `max_assign` allows without recomputing. It does not hold the
  resulting recall, and a view that showed recall at an ε nobody simulated
  would break the rule above.
- **The browser.** How state reaches a page is open: `.npz` directly, a
  converted columnar form, or a sampled one. So is whether 150,000 points can be
  drawn at all without sampling, and if they are sampled, how the sample is
  declared. What is known, measured in task 020: at 150,000 × 768, uncompressed,
  a `semantic_sharded` state is 15.6 MB and a `single_node_hnsw` state is
  7.4 MB. The candidate columns grow with queries × probes × depth, not with
  the corpus. On 20,000 vectors a three-shard `hash_sharded` state is 13.3 MB.
- **The ambiguity reason.** Code 3 is reserved for a family that probes by the
  ambiguity rule (d2 ≤ 1.10 · d1). No family does yet.
