# State — what the simulator did, as a receipt

`simulate.json` says *how well* each architecture did: recall, ceiling, storage,
fan-out. It does not say what the architecture *did*: where each vector went,
how a query was routed, what each shard sent back. The lab draws exactly those
things. **State** is that second half, written as an artifact beside the table
and held to the same standard as the table.

The format lives in [`oneground/models/state.py`](../oneground/models/state.py).
The lab's rendering contract lives in [`oneground/lab/`](../oneground/lab/).
The reference renderer, which is also the state's acceptance test, is
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
fill it, and extend the contract if it can be checked. Then render it. This has
happened twice, both times below: task 020 added `candidates.true_ids` and task
021 added `assignment.nearest_region`. Both times a consumer of the state that
needed a column found the gap. Inspecting the model found neither.

> **The only test of whether the state is sufficient is a renderer that needs
> the column.**

The state contract and the conformance suite check that a state is internally
consistent. Neither can say it holds enough, and both passed the two states
that did not. So a change to the state lands with the rendering that needs it,
and that rendering passing is its acceptance test: the published figures
reproduced through `render_from_state.py`, and task 020's acceptance
comparison. A column no renderer reads has not been tested for anything.

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
| `AssignmentState` | base vector | home region, copy set (nearest first, `-1` unused), copy count, distance to its nearest `max_assign` centroids (`NaN` where the family has none), and which regions those are, copied into or not (`nearest_region`) |
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

## The field task 021 found missing: `assignment.nearest_region`

Task 021 asked what recomputes when ε moves.
- **Copy counts** at any ε follow from `centroid_dist` alone.
- **Copy sets** do not. They decide which regions a vector lands in, and so
  shard membership, load, and which true neighbours a route can reach. For
  those, a recount needs the ids of the regions the distances were taken to.
- **What `copy_set` holds.** A region id only inside the closure at the
  emitted ε. A recount could lower ε, but it could not raise it: it had the
  distance to a region a vector would now be copied into, and no idea which
  region that was.

`AssignmentState.nearest_region` (N × `max_assign`, int32) holds those regions,
nearest first, whether or not the vector was copied into them. The state
contract checks every copy against it.

**Additive.** It does not change `state_version`, because readers work from the
header's column map. A state written before it simply lacks it, and a consumer
that needs it reports `couldnt_check`. Adding it left `simulate.json`
byte-identical and every other column unchanged on both published fixtures.
The semantic state grew from 15.6 to 18.0 MB at 150,000 vectors.

**Validated against runs, not assumed.** Copy counts, copy sets, vectors per
shard, storage and routing ceiling@10 were recounted from the ε 0.2 state.
They matched exactly what `simulate` emitted at ε 0.0, 0.1 and 0.3
(StackExchange 20k) and at 0.1 and 0.3 (arXiv 150k), including every ε above
0.2.

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
monotone from 0, copy-set slot 0 is the home region, every copy is in the
region `nearest_region` names for its slot, and load totals equal the parts
they are counted from.

The suite also checks the state against the architecture itself: merging a
state's candidates with `base.merge_candidates` must reproduce `search()`'s ids
and scores exactly. A state that satisfies the contract but describes a
different search is still wrong.

A family implements `state(built, queries, k, config, gt_ids, seed)` and must
not change what it measures to do so. `state()` is called after the row is
measured and before the index is released.

---

## The rendering contract

The rule above, made enforceable (task 021, `oneground/lab/`):

> **A view takes state and returns a drawing.**

- **Pure.** A view is a `View` with a `name`, the columns it `reads`, and
  `render(state) -> Drawing`. It reads no files, no network and no clock.
- **Only what it declared, never a vector.** The state a view is handed
  (`StateColumns`) exposes only the declared columns. It refuses a vector
  column (`partition.centroids`) even when declared, and returns read-only
  arrays.
- **Tally, never measure.**
  - A view may select, gather by stored id, compare, count, sum, and take
    fractions and percentiles of stored columns.
  - It may not compute anything that needs a vector: no distance, similarity,
    norm, projection, clustering or neighbour search.
  - Crispness is a tally in this sense: the share of stored second centroid
    distances above 1.20 × the first.
- **A drawing is declarative:**
  - `marks`: point, region, link and bar layers of equal-length columns;
  - `figures`: the numbers it states;
  - `gaps`: each a `couldnt_check` reason;
  - `panels`: see below.

  `draw` validates it and stamps on the columns actually read, the state's
  identity, and what moving ε does to it.
- **The guard.** `oneground/lab/guard.py` reads every module in `views/`,
  registered or not. It fails the test suite on vector arithmetic (`@`,
  dot/inner/einsum, `linalg`, norms, distances, clustering), on any import
  outside a short allow-list (so no faiss, scikit-learn, scipy, torch, model
  family or measuring module), on file I/O, and on dynamic code.
  `render_from_state.py` refuses to draw while any view module breaks it.

**The stated limit.** The guard checks names and syntax. It does not infer
types, so `a * b` over two vectors would pass it. The runtime refusal of vector
columns is the primary guarantee: a view is never handed a vector to multiply.
Nor can the guard tell a legitimate tally over stored numbers from a new
measurement assembled out of them. That line is drawn in
`oneground/lab/__init__.py`, and review holds it.

`corpora/render_from_state.py` is two views, `ground` and `query_trace`, over
this contract. Task 020's acceptance comparison passes unchanged on its output.

---

## When ε moves

ε is the closure rule's one parameter. It decides which regions a vector is
copied into, and nothing upstream of that. `contract.ON_EPSILON` classifies
every column. The recount rows were checked against states emitted at five
other ε values, and the rebuild rows really do change.

| what moving ε asks | columns |
|---|---|
| nothing | centroids, region ids and home populations, home region, centroid distances, nearest regions, every route column, true neighbours, shard ids, queries served |
| a recount from state | copy count, copy set, vectors each shard holds; and from them the histogram, storage, p99 and routing ceiling@10 |
| a rebuild: a new `simulate` run | every candidate column, `true_rank`, candidates contributed; and from them recall, index loss and the neighbours a route missed |

**Measured** (task 021, `semantic_sharded` at the reference configuration, one
laptop). Figures are median (p95). Every incremental move was checked against a
full recount at the same ε.

| | 20,000 vectors | 150,000 vectors |
|---|---|---|
| full recount from state: ground figures + ceiling@10 over 2,000 queries | 1.5 ms (2.0) | **9.6 ms (11.8)** |
| draw the ground view | 0.6 ms | 4.4 ms |
| incremental update, slider step of 0.005 | 0.12 ms (0.54) | 0.70 ms (5.8) |
| incremental update, random jump | 1.4 ms (10.2) | 29 ms (161) |
| incremental index: memory / build | 2.2 MB / 13 ms | 14.2 MB / 93 ms |
| rebuild one ε: `simulate` build + query | 3–21 s | 194–398 s |
| state file, semantic / columns the recount reads | 11.1 MB / 2.3 MB | 18.0 MB / 6.4 MB |

**The design: a full recount per move.** A recount plus a ground redraw is
about 14 ms at 150,000 vectors, inside a 16 ms frame. So every geometric
readout moves continuously with the slider: copy counts and colours, the
histogram, storage, p99, shard sizes and the routing ceiling. An incremental
index is not used. It wins only on small steps, loses to a full recount on
jumps, and costs 14 MB.

**Recall is a declared set, rendered on request.** Recall, candidates and the
neighbours a route missed need a rebuild, which takes seconds at 20,000 vectors
and minutes at 150,000. They exist only at the ε values that were simulated,
and the lab marks which those are.

- **At a simulated ε,** the query trace is drawn from the state emitted at that
  ε. Its recall panel is `simulated` and carries recall@k, the returned
  candidates and the missed neighbours.
- **Between simulated ε values,** the geometric readouts are still drawn, and
  the recall panel reads **`not simulated at this epsilon`**. It carries:
  - the ε values that were simulated;
  - the cost of simulating one, in minutes, measured from those runs' declared
    timings;
  - the explicit action that would run it: the configuration at that ε and its
    `oneground simulate … --emit-state` command.
- **Never interpolated, never blank.** `contract.draw` refuses, for every view:
  - a simulated panel with figures for an ε its state was not simulated at;
  - a not-simulated panel that carries figures, or lacks its ε values, cost or
    action;
  - a not-simulated drawing that read any column ε rebuilds.

  The query-trace view also refuses to draw recall for a simulated ε over a
  state simulated at a different one: that recall lives in the other state.
- **The renderer.** `render_from_state.py --epsilon E --simulated DIR …` draws
  a declared set from the state directories it is given. ε values are compared
  at six decimals, the precision `simulate` writes.

The ground's live recount is designed and measured, not yet a lab module. When
it is built, it is a declared state transform outside `views/`, because a view
may not do it.

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

- **Controls other than ε.** The interaction model for ε is settled, above. What
  else the lab lets a person change is not. Probe, centroid count and index
  parameters have not been classified or measured the way ε has.
- **The browser.** How state reaches a page is open: `.npz` directly, a
  converted columnar form, or a sampled one. So is whether 150,000 points can be
  drawn at all without sampling, and if they are sampled, how the sample is
  declared. What is known:
  - **State files, uncompressed, at 150,000 × 768:** 18.0 MB for
    `semantic_sharded` and 8.0 MB for `single_node_hnsw`, including
    `nearest_region`.
  - **Candidate columns** grow with queries × probes × depth, not with the
    corpus.
  - **The ground drawing,** one point per vector, is 2.2 MB of JSON at 150,000
    vectors.
  - **At 20,000 vectors,** a three-shard `hash_sharded` state is 13.3 MB.
- **The ambiguity reason.** Code 3 is reserved for a family that probes by the
  ambiguity rule (d2 ≤ 1.10 · d1). No family does yet.
