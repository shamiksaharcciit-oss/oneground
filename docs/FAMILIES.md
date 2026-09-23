# Writing an architecture family

*For someone who has not seen this codebase. If you can write Python and you
have an idea about how to lay vectors out across shards, this document is
everything you need to get that idea measured.*

---

## 1. What a family is

A **family** is a way of arranging a corpus of vectors and deciding which part
of that arrangement a query looks at. Three ship:

| family | the arrangement | what a query searches |
|---|---|---|
| `single_node_hnsw` | one index over everything | all of it |
| `hash_sharded` | N shards by a seeded hash of the id | every shard |
| `semantic_sharded` | k-means regions, with vectors copied into near ones | the nearest `probe` regions |

A family is **not** an index algorithm. `flat`, `hnsw`, `ivf` and `ivf_pq` are
faiss's, they are a declared parameter every family accepts, and one builder
(`oneground/models/indexes.py`) serves all of them. You are not writing an
index. You are writing the thing that decides *where vectors live and which
of them a query can reach.*

### The one-line test

Ask: **does my idea change what a query can reach?**

- **Yes** → it is a family. Routing differs, so `ceiling()` differs, so the
  routing/index decomposition differs. Write a family.
- **No, it changes how well the reachable ones are found** → it is a
  **parameter** of an existing family, or an index algorithm. Add a `Param`
  to that family's table; do not write a new family.
- **It depends on something per-query that the corpus does not determine** —
  a filter supplied at query time, a user's permissions, a freshness window —
  → the simulator **cannot represent it today**, and saying so is the honest
  answer. Nothing here takes per-query predicates.

Worked examples of the test:

| idea | verdict |
|---|---|
| "shard by document date" | **family** — a query reaching only recent shards reaches different vectors |
| "raise `efSearch` to 200" | **parameter** of an existing family |
| "use IVF-PQ instead of HNSW inside each shard" | **parameter** (`index`), already supported |
| "keep hot vectors in RAM and cold ones on disk" | **family** — it changes what is reachable at a given latency |
| "only search documents this user may see" | **not representable** — per-query filtering is not in the simulator |

---

## 2. The protocol

Six methods. Put them in `oneground/models/<your_name>/model.py`, export
`NAME` and `MODEL`, and add your family to `REGISTRY` in
`oneground/models/__init__.py`. The full type signatures are in
`oneground/models/base.py` under `class Model`.

### `configs(space) -> [Config]`

Every configuration your family offers for a given sweep. Two rules:

- Build each one with **`Config.make`**, never `Config(...)` directly. `make`
  canonicalises defaults, so a parameter written at its default and the same
  parameter omitted produce **one label and therefore one row**. Without it a
  sweep measures identical work twice and reports it as two architectures.
- Cross the **index axis through `index_combinations(NAME, grid)`**, which
  pairs each algorithm with only the knobs that algorithm reads. Crossing
  every knob with every algorithm produces configurations that are refused on
  sight, from a grid nobody wrote.

### `build(vectors, config, seed, context=None) -> BuiltIndex`

Deterministic given `(vectors, config, seed)`. Put whatever your family needs
in `BuiltIndex.state`.

Two things that are not optional:

- **Refuse what you cannot build**, with a `ParameterError` that names the
  problem and the fix. A sweep that meets a `ParameterError` **drops one row
  and reports the drop**; a sweep that meets any other exception **stops**.
  This is the difference between a run that loses one configuration and a run
  that loses six hours.
- **Seed every random choice from `seed`.** Not `np.random`, which is global
  state another library can move: `np.random.default_rng(seed)`. A partition
  that changes between runs makes every comparison meaningless.

`context` is an escape hatch for work the caller already did — the fixture
builder passes centroids it computed during characterization rather than
making you recompute a 256-way clustering. **Your result must be identical
with or without it.** It is a speed concession, not a behaviour switch.

### `search(built, queries, k, config) -> Candidates`

The top `k` your architecture actually returns. Call
`rerank.depth_for(k, config)` for how deep the first pass goes and hand the
result to `rerank.apply(...)`: the rerank stage is one shared implementation
and you do not write your own.

### `ceiling(built, queries, k) -> ids`

**Exact k-NN over everything your routing can reach. This is the method the
whole project turns on, and it is not optional.**

It answers: *if the index inside every region a query probes were perfect,
what is the best this architecture could return?* With it, the gap from
perfect recall splits in two:

```
routing_loss = 1 - ceiling@k      the neighbours are in regions never probed.
                                  No index tuning recovers these. Re-architect.

index_loss = ceiling@k - recall@k reachable, and not returned.
                                  A bigger efSearch or nprobe might. Tune.
```

That distinction — **tune it** versus **re-architect** — is the question the
tool exists to answer, and a family that cannot state what it reaches cannot
appear in the table.

If your family reaches everything, return exact k-NN over the whole corpus and
say in your `MODEL.md` that routing loss is zero **by definition, not by
measurement**. If it does not, `ceiling()` must restrict to what each query
actually reaches. Returning the whole corpus when you do not reach it all
reports your routing loss as zero and blames your index for everything. The
conformance suite catches the opposite error (`ceiling >= recall`); **nothing
catches this one but care.**

### `footprint(built) -> Footprint`

What the architecture costs, independent of how well it recalls:
`stored_vectors`, `amplification`, `fanout`, `shards`, copy percentiles, and
the measured bytes.

**`index_bytes` must come from the artifact, not from a formula.** Compute it
with `indexes.measured_bytes(index)` summed over your shards, and
`vector_bytes` with `indexes.stored_vector_bytes(...)`. A formula over vector
count and dimension cannot see quantisation: measured against the estimate, a
single IVF-PQ index came out **61× smaller** than `n × dim × 4` claimed. The
estimate (`memory_bytes`) stays, keeps its name and stays labelled an
estimate.

`fanout` is how many regions a query searches — the cost a recall number never
shows. A fan-out of 8 at equal recall is eight times the query work.

### `state(built, queries, k, config, gt_ids, seed) -> ModelState`

Where every vector went, how every query was routed, and every candidate each
region returned — what the lab draws. It must:

- **measure nothing new.** Every array is a record of a decision `build` and
  `search` already made. A `state()` that recomputes a routing decision can
  disagree with the row printed beside it.
- satisfy `state.contract_violations(state, footprint)`, which checks that
  candidates merge back to exactly what `search` returned, that every probed
  region was scored, and that copy counts agree with your own footprint.
- carry every column the lab's views read. The suite lists them; a family
  missing one is usable and invisible.

---

## 3. The parameter table

Every key your family reads is declared, once, with
`declare_parameters(NAME, (Param(...), ...))`:

```python
PARAMETERS = declare_parameters(NAME, (
    Param("shards", int, minimum=1, swept=True, default=8,
          note="how many regions the corpus is split into"),
    Param("efConstruction", int, role=CONSTANT, fixed=200,
          note="every shard is built at this"),
    Param("deterministic", bool, role=BUILD),
) + index_params() + rerank_params())
```

**Why this exists:** a key accepted and silently ignored is a run that reports
numbers as if the setting had been applied. `Config.get` refuses any key the
table does not list, so it cannot happen by accident.

The fields that matter:

- **`role`** — `PARAMETER` is the architecture and the only role a proposal
  may change. `RUN` is set per run by the simulator. `BUILD` is how the index
  was built, not what it is. `CONSTANT` is fixed inside the family and
  **refused** in any configuration, so nobody thinks they can turn it.
- **`minimum` / `maximum`** — validity bounds: what you can build **at all**.
  Not recommendations.
- **`default`** — the one place the value is written. Read it with
  `PARAMETERS[key].default`, never by repeating the literal at each
  `config.get` call, or the value in the label and the value in the build
  will drift apart.
- **`belongs_to`** — which value of another key this one requires, e.g.
  `("index", ("ivf", "ivf_pq"))`. A knob the chosen algorithm would ignore is
  **refused**, not accepted.
- **`in_label_at_default`** — whether the key appears in a label when it is at
  its default. Leave it `True` for a new family. It exists because adding
  `index` to families whose labels were already published had to not rewrite
  them; you have no published labels yet.

Add `index_params()` and `rerank_params()` to your table. They are shared
declarations because the index algorithm and the rerank stage are properties
of the search path rather than of a partition.

---

## 4. The conformance suite

```
oneground models conformance                                   # all shipped
oneground models conformance --family hash_sharded
oneground models conformance --module examples/random_sharded/model.py
```

`--module` takes a path, so **you can run it before your family is
registered** — which is the point. It runs on a small synthetic corpus in a
few seconds and checks the protocol's contract, not any published number.

Outcomes are **passes**, **fails**, and **couldn't-check**, and the third is
never rounded up to either of the others.

Nine checks, and what a failure means:

| check | a failure means |
|---|---|
| **parameter table** | a key is declared and never read (a knob that does nothing — a sweep over it produces distinct labels for identical work), or read and not declared |
| **defaults and omissions** | a parameter at its default and the same parameter omitted produce two labels, so a sweep can measure the same architecture twice |
| **ceiling** | `ceiling()` came back **below** your own measured recall — you returned neighbours your routing says are unreachable, and every routing-loss figure that cites you is wrong |
| **routing loss is index-invariant** | changing the index algorithm changed what your routing reaches. It cannot: the partition decides reachability. One of the two is misreporting |
| **determinism (this machine)** | two builds from identical inputs, with `deterministic=True`, produced different state. Nothing you produce can be compared to anything |
| **footprint is measured** | your reported size does not change with the index algorithm, which is what a formula over vector count and dimension produces. It did not come from the artifact |
| **state is emitted and renders** | your state contradicts what you measured, or omits a column the lab reads — your runs fail at draw time rather than at build time |
| **determinism (across environments)** | always couldn't-check: one machine cannot answer it. See `docs/STATE.md` |
| **refusals, not crashes** | an impossible configuration raised something other than `ParameterError`, so it aborts a sweep instead of being dropped from one |

**A check that fails is a finding about the family, never a reason to weaken
the check.** One of the three shipped families fails one of these today, and
it is recorded in `tasks/042-family-conformance.report.md` rather than
smoothed away.

A `couldn't-check` result always says what would settle it. The
cross-environment half of the determinism contract is the standing example:
one machine cannot answer it, and `docs/STATE.md` says what does.

### 4.1 If you extend the suite, read this first

**The suite was wrong three times before it was right, and twice more when it
was extended.** Not about the families — about itself. The first three each
produced a confident, specific, false result on a shipped family; the last two
were found while adding the tenth check, by an author who had read the first
three. They are recorded here because the next person to add a check will make
the same kind of mistake in a new place, and because knowing the list is not
the same as not making them.

**1. It reported a knob that does nothing, and the knob works.** It said
`candidates` was declared and never read, in all three families. `candidates`
is read only when `rerank` is `exact`, and the suite's grid never set that. A
check that asks *"was this key read?"* without first asking *"could it have
been?"* reports its own coverage gap as the family's defect.

> The rule: before asserting a key is unread, satisfy its `belongs_to`. If you
> cannot, the outcome is **couldn't-check**, not **fails**.

**2. It reported `M` and `efSearch` unreachable in every family, because it
reimplemented a rule that already existed.** It tested belonging with
`config.params.get("index") in ("hnsw",)`. But `index` **elides at its
default** — that is deliberate, so that adding the key rewrote no published
label — so `params` has no `index` key at all in an HNSW configuration and the
test was false everywhere. The validator's own `_belonging_problem` resolves
the default and gets it right.

> The rule: **call the function the tool already uses.** A second
> implementation of a rule is a second place for it to be wrong, and this one
> disagreed with the first in the most common case there is.

**3. A check passed for the wrong reason, which is worse than one that
fails.** *Refusals, not crashes* fed `nlist=1501` to `single_node_hnsw` and
saw a `ParameterError`, so it passed. The refusal was about **belonging** —
`nlist` is an IVF setting and the configuration was HNSW — and said nothing
whatever about size. The family had not been tested and the suite reported
green.

> The rule: **a passing check must be able to fail.** Before trusting one,
> break the thing it tests and watch it go red. That is what the mutants in
> `oneground/models/test_family_conformance.py` are: seven families that each
> violate one requirement, asserting the suite names *that* check and not
> another. Add a mutant with every check.

The shape all three share: **the suite was measuring itself and reporting the
family.** A green result and a red result are both claims, and a check you
have not watched fail is not evidence of either.

Two more were found while adding the tenth check, in task 042c. Both are
things the author reached for *because* the first three had been read.

**4. A held measurement was downgraded to couldn't-check because a stronger
claim was unproven.** `fanout matches the build` asserts that a family's
fan-out is within its shard count. It held on every configuration of every
family. The first version reported **couldn't-check** anyway, reasoning that a
family reporting the requested count and one reporting the built count would
look identical wherever the two agree — so the result did not prove the
family reads the build.

That reasoning is true and it is about a different claim. The check asserts a
bound; the bound was measured and it held. Reporting couldn't-check said no
measurement was available when one was.

> The rule: **couldn't-check is for what was not measured, not for what was
> measured weakly.** This is the hedge form of the error the three outcomes
> exist to prevent, and it is the exact inverse of rounding an unknown up to a
> verdict — equally wrong, and more tempting, because it feels careful. If a
> check's evidence is weaker than a reader might assume, **say how strong it
> is** in `meaning`, and let the outcome report what was actually found. A
> check that answers couldn't-check on a healthy tree teaches its readers to
> ignore it.

**5. A mutant that does not run the rule's own code proves only that the
defect is reproducible.** Warning 3 already says to add a mutant with every
check. The first mutant here restated the rule — it asserted `fanout >
shards` for a deliberately broken family — and passed. It would have gone on
passing if the check itself had been deleted, because it never called it.

> The rule: **a mutant runs the check, not a copy of it.** Break the family,
> hand it to `run_conformance`, and assert the suite names *that* check with
> `FAILS`. Assert too that the unbroken family passes the same check on the
> same corpus, so a failure is the mutation and not the fixture. A rule and a
> mutant that share no code drift apart, and the day they do, the mutant is
> still green and proving nothing.

---

## 5. The worked example

[`examples/random_sharded/model.py`](../examples/random_sharded/model.py) is a
complete family, written to be read. It implements all six methods in the
order this document introduces them, with the reasoning beside each, and it
passes all eight decidable checks (the ninth is the cross-environment one no
single machine can answer).

It partitions **at random** and routes **at random**, which makes it a bad
architecture on purpose. That is what makes it useful: because its partition
carries no information, probing `probe` of `shards` regions reaches a random
`probe/shards` of the corpus, so its routing loss is large, visible, and
predictable. Measured on the suite's own corpus:

| shards | probe | ceiling@10 | `probe/shards` | recall@10 |
|---|---|---|---|---|
| 4 | 1 | 0.2750 | 0.25 | 0.2750 |
| 4 | 2 | 0.5175 | 0.50 | 0.5175 |
| 8 | 1 | 0.1525 | 0.125 | 0.1525 |
| 8 | 2 | 0.2900 | 0.25 | 0.2900 |

Recall equals the ceiling in every row: the index found everything it could
reach, and **every point of loss is routing**. `hash_sharded` over the same
corpus scores 1.0000 at every shard count, because it fans out to all of them.
That contrast in one table is what `ceiling()` buys.

It is deliberately **not registered** and lives outside `oneground/models/`,
so no requirements file can name it and nobody can deploy it by accident.
Copy it, do not import it.

---

## 6. What a family may never do

- **Compute its own ground truth.** Ground truth is exact k-NN computed once,
  outside the family, and handed to it. A family that scores itself is not
  being measured.
- **Read the projection.** The 2-D layout is for drawing. A family that routed
  by it would be routing by a picture of the data instead of the data.
- **Report a figure it did not measure.** If you cannot measure something, the
  answer is couldn't-check with the reason, not a plausible estimate.
- **Rank itself against another family.** You measure your architecture. The
  report compares. A family that claims to be better than another is a
  benchmark with a favourite, which is the thing this project exists not to
  be.
- **Send anything anywhere.** No network calls, no telemetry. A user's vectors
  never leave their machine.

---

## 7. From a fork into the tool

1. Write `oneground/models/<name>/model.py` with the six methods and the
   parameter table.
2. Write `MODEL.md` beside it: what the arrangement is, what it costs, and a
   **known limits** section. Write the limits honestly and specifically —
   `semantic_sharded` records that its four-copy cap *understates* storage on
   very fuzzy corpora, and `hash_sharded` records that its recall can drift
   slightly above the single-node baseline at equal `efSearch`. Both are real,
   both would otherwise be read as bugs. **A limits section that is empty has
   not been thought about.**
3. `oneground models conformance --module <path>` until it is green. Do not
   change a check to get there.
4. Register it in `oneground/models/__init__.py` and add tests of your own for
   anything specific to your arrangement. The shared conformance tests
   parameterise over the registry, so your family is held to them the moment
   it is registered, without editing them.
5. Open a pull request. **The acceptance criterion is a test run, not a
   maintainer's opinion** — the same rule adapters get.

**Your first published result carries the same caveats as everyone else's.** A
number measured on one corpus is a fact about that corpus; a fixture is for
learning and for checking an installation, never a leaderboard; and a
comparison between your family and a shipped one says what was measured, on
what, with what left unchecked. A pull request that ranks families on a
fixture will be closed — including one that ranks yours first.

---

*The protocol is `oneground/models/base.py`. The decomposition it exists to
produce is [MODELS.md](MODELS.md#the-ceiling-rule). The state contract is
[STATE.md](STATE.md).*

