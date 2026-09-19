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
- **A projection of its own.** The simulator never fits one. Where a run
  *declares* a projection it is carried, labelled, as three columns — see
  "The declared projection" below — and nothing is ever computed from it.
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

## The declared projection (task 027)

The ground used to be a grid of region cells, captioned "a layout, not a map:
the state holds no positions", because the 2-D projection the teaser draws is
declared illustrative by the fixture spec and so was never emitted as state.
The contract was doing its job, and the consequence was that the instrument
refused to draw the picture the product is sold on. The developer's decision
on 18 September: **the projection becomes a declared column, labelled, and the
ground draws it.**

### Three columns, one read from a file

| column | shape | what it is |
|---|---|---|
| `assignment.projection` | (N, 2) float32 | where to draw each base vector |
| `route.projection` | (Q, 2) float32 | where to draw each query |
| `partition.projection` | (R, 2) float32 | where to draw each region |

Only the first comes from a file. The other two are **derived by the pipeline
at emit time**, and that is not an implementation convenience — both are
arithmetic over projected coordinates, which no view may do:

- **A query has no position.** The fixture's projection was fitted on base
  vectors; projecting a query into it would be a new computation in a space
  the run does not use. It is drawn at the mean of its own true neighbours'
  positions, which is what the teaser draws. Checked against
  `ground_view_queries.parquet`: identical, float32 for float32.
- **A centroid is not a base vector either.** A region is drawn at the mean
  position of the vectors whose home it is. A region with no home vectors gets
  NaN, not the origin — the origin is a real place.

All three are additive: `state_version` is unchanged, and a state written
before them simply lacks them.

### Declared, and recorded as such

`corpus.sample.projection.path` in the requirements, digested with the other
inputs. Read once before anything is measured, so a projection that does not
fit the corpus stops the run in a second rather than after an hour — a row
count that does not match is refused rather than padded, truncated or
reordered, because a placement that does not line up draws every point in
somebody else's place and looks fine.

`state_info.json` records the source path, its sha256 and size, the row count,
the method, seed and library where the requirements declare them, the query
placement rule and its `k`, and the fixture spec's own sentence verbatim: *2-D
placement is illustrative; regions, distances and copy counts are computed in
the full space.* Where the requirements do not declare a method or seed it
says `couldnt_check` and why.

Two formats, because the two corpora that have one differ: `.npy` (N, 2), and
`.parquet` with `x` and `y` columns — which is how `arxiv-150k` ships it,
inside `ground_view_base.parquet`. `pyarrow` is imported only for the second
and only when asked, since it is in the `[view]` extra.

**Never a precondition.** With no projection declared, `state_info.json`
records `kind: absent` with the reason, the states carry no positions, and the
lab falls back to the cell layout with its own caption.

### What a view may do with it, and what it may not

A vector column can simply be withheld — a view does not need one. A
projection cannot: drawing the picture *is* passing these numbers to a mark.
So the rule moves from "you cannot have it" to **"you cannot compute with
it"**, and it is enforced twice.

**At run time.** `contract.Positions` is the array a view is handed. Every
ufunc and array function raises `MeasuredFromProjection`, so a difference, a
scaling, a norm, a mean, a matmul, a comparison and a stack all fail at the
line where they are written. Indexing, slicing, iteration and `.tolist()`
work, because that is what drawing needs, and a slice stays a `Positions`, so
taking the x column does not launder the refusal.

**Statically.** `guard._projection_violations` binds the names a view module
takes from a projection column and flags those names in arithmetic, a
comparison, or a numpy statistic. Naming the columns alone would be useless: a
view that draws them mentions them legitimately, in `reads` and in the
subscript that reads them.

**The stated limit** is the vector rule's: `np.asarray(p)` returns a plain
array, and a view determined to measure could call it. This makes the mistake
impossible to make by accident and obvious to see in review.

**Why the rule is sharper here than anywhere else.** A projection is
illustrative and the fixture spec says so. A figure measured from it would be
a second measurement, in a space nothing else in the run uses, that can
disagree with the table — and it would arrive wearing a picture, which is the
most convincing form a wrong number can take.

### The caption is part of the drawing

`contract.draw` refuses a drawing that read a projection and does not say so.
The words are checked, not a flag, because the words are what a screenshot
carries:

> Positions are a declared projection, illustrative: nothing on this picture
> was measured from where the points are. Regions, distances and copy counts
> are computed in the full space.

The check is on the columns actually read, so a view that stops drawing
positions stops needing the sentence. The `positions` row in the ground's
gaps changes from `couldnt_check` to `declared`; without a projection it stays
`couldnt_check` and now says what happens instead.

### Epsilon does not move a point

All three columns are `UNCHANGED` in `ON_EPSILON`. Epsilon decides which
regions hold a copy of a vector, which is its colour; it has nothing to say
about where it is drawn. Both of the lab's layouts are therefore built once
and only chosen between afterwards.

### Checked against the teaser

At epsilon 0.20, over all 150,000 arXiv vectors, compared by id against
`site/teaser/data/base.bin`:

| | |
|---|---|
| maximum coordinate difference | **0** (bit-identical) |
| copy-count disagreements | **0** |
| home-region disagreements | **0** |

`base.bin` was written by `corpora/export_teaser_data.py` from the fixture
build's `projection.npy`; the state's positions come from
`ground_view_base.parquet`, written by `corpora/export_ground_view.py` from
that same file by a different code path into a different format. Copy counts
come from neither — the ground recounts them from the state's own stored
distances. Task 020's acceptance script still passes 20 of 20.

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

## What "the same state" means: two claims, not one

A `.state.npz` stores decisions **and** raw float32 inner products, and one
identity claim cannot be true of both. So the contract is two statements, and
which one applies depends on where the two files came from.

> **Within one environment: byte-identical.**
> The writer fixes every zip entry's timestamp and sorts the entries, so the
> same run on the same machine produces the same bytes. This is what
> `MANIFEST.sha256` is for.
>
> **Across environments: identical decisions, and scored floats equal to
> within a couple of units in the last place.**

**A reader who compares two machines' digests and expects a match will get a
false alarm.** The digests *will* differ, and nothing is wrong.

### Why, measured

Task 032b ran the arxiv-150k reference configuration at one commit on an
Intel i3-1115G4 and an AMD EPYC 7352, with the same corpus, the same
characterization and the same seed. Of 24 columns, **20 were byte-identical**:

- the partition — `partition.centroids`, `region_ids`, `region_sizes`
- the assignment — `home_region`, `centroid_dist`, `copy_count`, `copy_set`,
  `nearest_region`
- the routing — `probed_region`, `scored_region`, `scored_dist`, `probe_reason`
- the load — every column
- the candidate structure — `cand_shard`, `offsets`, `true_ids`
- `header.json`

Four differed, all downstream of one thing: `candidates.cand_score`, where
80,648 of 400,000 values differed — 75,811 by one ulp and 4,837 by two, a
maximum absolute difference of 1.1920929e-07 on values lying in
[0.546, 0.905]. `cand_id` moved in 27 places, `survived_dedupe` in 5,244 and
`true_rank` in 14, all as a consequence of two adjacent candidates swapping
when their scores moved. Exactly one candidate in 400,000 was returned by one
machine and not the other, so the graphs agree; what differs is the
arithmetic.

Those scores are inner products computed inside faiss's own search kernels,
below `distance_compute_blas_threshold`, where `deterministic_faiss` does not
reach: it pins the thread count and keeps k-means off the BLAS, and neither
touches a per-vector distance in an HNSW traversal. `FAISS_OPT_LEVEL` at
unset, `AVX2`, `AVX512` and `GENERIC` gives identical results on one machine,
so the dispatch level is **couldn't-check** as the mechanism — tested, not
demonstrated.

**None of it reaches a measurement.** `simulate.json`'s rows were equal across
the two machines, because recall is a count of matching ids and the merged
top-k did not move.

### What was a defect, and is not any more

`route.scored_dist` was in the differing set until 032b found the reason: the
query-side routing was computed outside the determinism context the base side
was computed inside, so the state recorded distances the run had not computed
on the path it computed everything else on. The context now lives in
`semantic_sharded._probed`, so `search`, `ceiling` and `state` share one path,
and the column is byte-identical across the two machines.

That distinction is the one to keep: **a float we own the arithmetic of must
be exact, and only a float we do not own may move.** A column joins the
tolerated set because faiss computes it where we cannot reach, never because
we have not reached it yet.

### The check

```
python corpora/compare_state.py <A>/state <B>/state                    # within
python corpora/compare_state.py --cross-environment <A>/state <B>/state
```

The second implements the second claim: every decision column exact, the
scored columns within `--max-ulps`, and the ordering columns allowed to move
only where a scored column actually did — a rank that changed with no score
behind it is a different traversal, not rounding. The ulp distribution is
printed every time.

`--max-ulps` defaults to **2 because that is what one pair of machines
showed**, not because anyone derived it. The worst case for a float32 dot
product over 768 terms summed in two orders is of order 768 × eps ≈ 9e-5,
four orders larger than anything observed, so no bound here follows from the
arithmetic. A third machine could exceed 2 with nothing being wrong, which is
why the distribution is printed rather than reduced to a verdict.

### What is deliberately not done about it

Three things would make byte-identity true across environments: store the
scores at reduced precision, store only the decisions, or round what is
stored. **All three are refused.** Each trades a receipt's exactness for a
simpler claim, and the receipt is worth more than the claim. The scores are
what they are, and the contract describes them accurately rather than the
file being reshaped to fit.

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

**Measured** (task 023b) on one laptop, `semantic_sharded` at the reference
configuration, 2,000 queries. Six rounds of 40 slider positions, ε order
shuffled per round, with task 021's unchanged recount timed back to back with
the view's at every position, so any drift lands on both. Figures are the
median over 240 positions, with [p05–p95].

| | 20,000 vectors | 150,000 vectors |
|---|---|---|
| task 021's recount, unchanged: the control | 1.4 ms [0.8–2.6] | 12.4 ms [7.9–20.6] |
| `views.ground.recount` | 1.1 ms [0.7–2.4] | 11.4 ms [7.2–17.9] |
| **a whole ground draw**: recount, ceiling@10, figures, marks, caption | **6.7 ms [4.3–11.2]**, max 25.6 | **21.3 ms [14.3–34.6]**, max 58.4 |
| rebuild one ε: `simulate` build + query | 3–21 s | 194–398 s |
| state file, semantic / columns the recount reads | 11.1 MB / 2.3 MB | 18.0 MB / 6.4 MB |

- **The view's recount is not slower than the path task 021 measured.** Paired
  at each position, `recount / control` is 0.85 at 20k and 0.92 at 150k: it
  does slightly less work.
- **The host drifts while it measures.** Within one quiet session the per-round
  median at 150,000 vectors moved from 8.9 to 14.4 ms for the control and from
  15.3 to 24.2 ms for a draw, and a fixed 4M-element numpy sum timed once per
  round varied 2.0–3.6 ms — 77%. No single timing figure here is a property of
  the code.
- **Task 021's "14 ms, inside a frame" was one pass on a machine whose state
  nobody recorded**, and task 023 measured 44.7 ms for the same path on a
  worse day. Both are draws from the distribution above. The honest statement
  is the distribution.
- **A ground draw's only size-independent cost** is the contract's defensive
  copy of the state header, about 1–2 ms. Everything else scales with the
  corpus or the query count.
- **An incremental index was measured in task 021 and rejected:** it wins only
  on small slider steps, loses to a full recount on jumps (29 ms against
  9.6 ms at 150,000 vectors), and costs 14.2 MB. Task 023 did not build one.

**A full recount per move, and it is built.** `views/ground.py` recounts the
closure at whatever ε the control is at, from the stored distances and nearest
regions, written exactly as `semantic_sharded.build` writes it. Every
geometric readout moves continuously with the slider: each vector's copy count
and colour, the copies histogram, vectors copied, storage amplification, p99
copies, the vectors each shard holds, and the routing ceiling at k=10.

- **The ceiling is recountable** because it asks where copies are, not what an
  index returned: a true neighbour is reachable when some region the query
  probes holds a copy of it at this ε.
- **The recount reproduces the runs.** At every ε a state was simulated at —
  StackExchange 0.0, 0.1, 0.2, 0.3 and arXiv 0.1, 0.2, 0.3 — recounting from
  the ε 0.2 state gives that run's own copy counts, shard sizes and figures
  exactly, and storage and ceiling@10 equal its `simulate.json` row. Exact
  equality, not tolerance: see `tasks/023-ground-live-recount.report.md`.

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

### The interaction budget, and what a host that cannot meet it must do

A design that assumes a frame budget has to name the budget and its fallback,
rather than assume the machine.

- **The budget.** A slider that redraws on every move must finish a draw before
  the next move arrives. Moves arrive at the display's refresh rate: 16.7 ms at
  60 Hz, 8.3 ms at 120 Hz. So the requirement is **p95 of a whole ground draw
  within one frame**, not the median. A median inside the frame with a p95
  outside it stutters; worse, a draw slower than the event rate builds a
  backlog, and what is on screen then belongs to an ε the control has already
  left. That is an honesty failure, not a smoothness one — someone can
  screenshot figures under the wrong ε.
- **Measured against it on this laptop:** 20,000 vectors passed (p95 11.2 ms);
  150,000 vectors does not (median 21.3 ms, p95 34.6 ms). 11.2 ms fits the
  frame and also the margined threshold below, by 1.3 ms — which is why this
  laptop's choice at 20k depends on the state it is in when the lab starts.
- **The fallback: render on release, and say so.** Where p95 exceeds the frame,
  the lab must not redraw on move. While the control is dragged, the ε readout
  follows it and the ground stays as last drawn, captioned with both numbers —
  "showing ε 0.20; release to redraw at 0.35". On release it recounts and
  redraws once.
- **In either mode, the same rules hold.** No figure is shown without the ε it
  belongs to; nothing between simulated ε values is interpolated; the recall
  panel keeps its rule above.
- **The host decides, not the publisher.** A lab times its own first draws, on
  the machine and corpus in front of it, and picks the mode from them. The
  numbers above are one laptop on one day, and the same code measured twice as
  slow on the same laptop a day earlier. The chosen mode belongs in the
  ground's caption, so a screenshot carries it.
- **The decision needs a margin, not only the measurement.** Deciding from one
  p95 near the frame repeats, in the decision, the defect this section found
  in the measurement: at 20,000 vectors four back-to-back readings on one
  laptop were 16.3, 17.8, 36.3 and 26.2 ms — one inside the frame, three not.
  So the rule is: **take several readings** (up to five, each a p95 of 20
  whole ground draws), and **redraw on move only if every reading is within a
  threshold 25% inside the frame** — 12.5 ms at 60 Hz. When the readings
  straddle the threshold, or sit above it, **render on release.** A slider that
  stutters is worse than one that says it redraws on release. The first reading
  above the threshold settles the decision, so a slow host is not made to take
  the rest. `contract.MARGIN`, `contract.THRESHOLD_MS`, and the readings and
  verdict travel with the `RenderMode` into the caption.
- **Where it is built.** `oneground lab` (task 024, `docs/LAB.md`) measures at
  startup, prints the mode and its readings, and puts both in the ground's
  caption; `render_from_state.py` still draws once per invocation and has no
  mode.

**One ε set, and an honest caption.**

- **One source.** `EpsilonSet` — where the control stands, which ε values were
  simulated, and the cost and action a panel offers between them — is built
  once by whoever holds the runs and handed to every view. The ground and the
  query trace cannot disagree about which ε values are simulated.
- **The caption is part of the drawing.** A view that recounts must caption
  what it is showing, and at an ε nobody simulated the caption must say
  `not simulated at this epsilon` and that the geometry was recounted from
  state. `contract.draw` refuses a recounting drawing whose caption omits
  either. Someone who screenshots the ground between simulated ε values must
  not be able to mistake it for a measured configuration.
- **The ground still refuses vectors.** It recounts what the centroids decide
  and is handed no centroid: `partition.centroids` is refused at run time,
  declared or not.

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
