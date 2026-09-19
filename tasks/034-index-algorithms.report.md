# Report: 034-index-algorithms

## Repo state expected vs found

The brief (as merged with its engine-coverage addition into one document,
`tasks/034-index-algorithms.md`) assumes:

| expected | found |
|---|---|
| three families, all building HNSW underneath, with `M`, `efConstruction`, `efSearch` the only index knobs | yes |
| 026's parameter tables, so a new key is declared rather than accepted | yes |
| 032's label canonicalisation, so a default and its omission are one label | yes |
| 029's determinism apparatus, so step 2 is a measurement | yes — `deterministic_faiss` = `single_threaded_faiss` + `deterministic_blas` |
| `ceiling()` mandatory on every family | yes |
| two published fixtures with reference results | yes — arxiv-150k (verified), stackexchange-150k (built) |
| two adapters behind one protocol | yes — qdrant, pgvector, plus the in-process stub |

Two things the brief did not say, found on arrival:

- **The branch.** The brief's Setup says "branch `task-034` from `main`"; the
  instruction that sent me said `origin/task-032` at `d5efd78`, which is what
  I branched from. Three further commits arrived from the developer while the
  work was in progress (`d9f4e7a`, `45d9a90`, `6e2f601`); none was acted on
  except the addition, which was merged into the brief as instructed.
- **The 150k vectors are on this machine**, at `~/oneground-assets/`. The
  brief allowed for a pod for the 150k measurements; it was not needed. What
  did need a pod was 032b, and what cannot be done here at all is the engine
  coverage — there is no Docker on this machine.

## What was done

**1. The index is a declared parameter of every family.** `flat`, `hnsw`,
`ivf`, `ivf_pq` in 026's parameter-table form, with knobs declared per
algorithm, and one builder — `oneground/models/indexes.py` — used by all
three families. `Param` gained three fields: `in_label_at_default`,
`belongs_to`, `choices`.

The label tension and how it was resolved: every published label is composed
*entirely* of parameters at their declared defaults, so 032's rule of filling
a missing default would have appended `index=hnsw` to a public interface,
while eliding every default would have collapsed those labels to `family[]`.
So the direction is declared per key, the invariant holds either way, and a
key added after a label was published elides at its default.

Refusals: an unknown algorithm (`choices`), a knob the chosen algorithm does
not read (`belongs_to`), a swept grid key no named algorithm reads, `nlist`
greater than the shard size, and `2**nbits` greater than it — the PQ's own
clustering is a second and much higher size floor, and faiss's message for it
names neither the configuration nor the shard.

**2. The index axis is swept.** `nlist` and `nprobe` were declared
`swept=True` in the first commit and no `configs()` read a grid for them,
which is exactly 026's accept-and-ignore defect. `index_combinations` crosses
the algorithms a grid names with the knobs that algorithm reads, and
`coherent` drops a family's HNSW knobs from a configuration whose algorithm
does not read them.

**3. `footprint()` stopped being arithmetic.** `index_bytes` is what faiss
reports for the built index summed over shards, `vector_bytes` is the vector
data it holds, `overhead_bytes` is the difference. `simulate`'s table splits
`est MB` from `idx MB`.

**6–9. The engine half.** `index_families()` is a protocol method enforced by
the conformance suite; three states (`builds` / `cannot_build` /
`unresolved`); `verify` refuses at plan time before anything is created; the
report separates *not verified* from *not verifiable here*; the decision log
prints a remedy that is a different engine rather than a command.

**10.** The quantisation caveat beside the sample caveat, and three new
forbidden claim classes with negative controls.

**A sweep no longer dies on one bad row.** An `IndexTooSmall` from one shard
used to end the whole run and take every row already measured with it — eight
were lost that way while this task was being written. A configuration the
corpus cannot build is now recorded as `couldnt_check: not buildable on this
corpus` with faiss's own reason, the sweep continues, and the command exits
**non-zero** naming how many were not measured. The rows that were measured
are written and valid; couldn't-check is not rounded up, including to an exit
code. Two tests: that the eleven good rows survive and the twelfth is named
with `nlist=4096` and its reason, and that the exit code is 1 with a drop and
0 without one.

**12. Docs.** `docs/MODELS.md` gains the four algorithms with their knobs,
determinism status and measured cost; `docs/CHARTER.md` gains Phase 3d and
Phase 3b stops being the only named index work; `docs/ADAPTERS.md` gains the
coverage table; both `ADAPTER.md` files gain an index-families section.

## Measurements

### Step 2 — determinism per algorithm, one machine

`tasks/scratch/034-determinism.py` on arxiv-smoke (2,000 × 768), two builds
each, compared as `faiss.serialize_index` bytes:

| index | deterministic=True | deterministic=False | bytes |
|---|---|---|---|
| flat | identical | identical | 6,144,045 |
| hnsw | identical | **NOT identical** | 6,687,522 |
| ivf | identical | identical | 6,357,259 |
| ivf_pq | identical | identical | 1,031,732 |

HNSW reproduces 012b exactly: the switch is what makes it reproducible.
`ivf` and `ivf_pq` reproduce themselves on this machine either way, which is
**not** a claim about two machines — 029's finding is that the divergence is
*between* machines, and each machine reproduces itself.

Cross-environment for the index algorithms: **couldn't-check.** The 029
apparatus proves it for `semantic_sharded`'s k-means (and 032b re-confirmed
it), but no session has built `ivf` or `ivf_pq` on a second machine. The
remedy is a session, and it is a developer's `y`.

### Step 3 — memory, measured

On the smoke fixture, against faiss's own serialised size:

```
flat     6,144,045 = 6,144,000 payload + 45 header
hnsw     6,687,522 = 6,144,000 + 543,522 graph
ivf      6,357,259 = 6,144,000 + 213,259 (coarse quantiser 64x768x4 = 196,608)
ivf_pq   1,031,732 =    32,000 codes  + 999,732 (quantiser 196,608 +
                                        PQ codebook 16x256x48x4 = 786,432)
```

### Step 4 — routing loss identical across index choices

`tasks/scratch/034-routing-loss.py`, grouping rows by partition:

| corpus | partition | routing loss, all four algorithms |
|---|---|---|
| arxiv-smoke | single_node | 0.000000 |
| arxiv-smoke | semantic, 16 centroids | 0.003500 |
| arxiv-smoke | hash, 3 shards | 0.000000 |
| arxiv-150k | single_node | 0.000000 |
| arxiv-150k | semantic, 256 centroids | 0.067200 |
| arxiv-150k | hash, 3 shards | 0.000000 |
| stackexchange-150k | single_node | 0.000000 |
| stackexchange-150k | semantic, 256 centroids | 0.130800 |
| stackexchange-150k | hash, 3 shards | 0.000000 |

**Identical, on both fixtures, for every partition.** The decomposition
survives: index loss carries the whole difference between algorithms.

### Step 5 — the sweep

The full tables are in `docs/MODELS.md`. Twelve configurations per corpus:
arxiv-150k in 50.0 min, stackexchange-150k in 79.4 min, both on the laptop.

### Step 11 — published values did not move

Re-running the reference configurations:

| fixture | value | published | measured | delta | tolerance |
|---|---|---|---|---|---|
| arxiv-150k | single_node recall@10 | 0.997 | 0.99680 | 0.00020 | 0.01 |
| arxiv-150k | semantic recall@10 | 0.932 | 0.93235 | 0.00035 | 0.01 |
| arxiv-150k | semantic routing_ceiling | 0.932 | 0.93280 | 0.00080 | 0.01 |
| arxiv-150k | semantic storage_amplification | 3.715 | 3.71487 | 0.00013 | 0.01 |
| arxiv-150k | semantic p50/p95 copies | 4 | 4 | 0 | — |
| stackexchange-150k | single_node recall@10 | 0.994 | 0.99380 | 0.00020 | 0.01 |
| stackexchange-150k | semantic recall@10 | 0.869 | 0.86875 | 0.00025 | 0.01 |
| stackexchange-150k | semantic routing_ceiling | 0.870 | 0.86920 | 0.00080 | 0.01 |
| stackexchange-150k | semantic storage_amplification | 3.897 | 3.89735 | 0.00035 | 0.01 |

And the stronger form the brief asks for — the same requirements file run at
034's parent `d5efd78` and at 034, so the only difference is the commit:
**both rows identical field for field**, with only `index_bytes`,
`vector_bytes` and `overhead_bytes` appearing, which did not exist before.

`runs/arxiv-150k-via-characterize` was **refused** as the baseline: its
sharded rows predate the deterministic build, its semantic row was measured
at the family's default per-shard depth (recall@100 0.421 against 0.887), and
its timings are still inside the rows because it predates 020b. Diffing
against it would measure four tasks at once — 028c's lesson.

## Findings from the numbers

**The two corpora agree about quantisation, and disagree about IVF.** That is
the finding, and it was not predictable from either.

| family | arxiv: hnsw → ivf_pq | stackexchange: hnsw → ivf_pq | difference |
|---|---|---|---|
| single_node | 0.9968 → 0.2872 (−0.7096) | 0.9938 → 0.2772 (−0.7166) | 0.0070 |
| hash | 0.9984 → 0.2461 (−0.7523) | 0.9966 → 0.2473 (−0.7493) | 0.0030 |
| semantic | 0.9324 → 0.4324 (−0.5000) | 0.8688 → 0.3880 (−0.4808) | 0.0192 |

Two corpora that disagreed about drift, and agreed about architecture, also
agree about what quantisation costs — to within 0.007 on two families and
0.019 on the third, at `m=16, nbits=8`.

They do **not** agree about IVF without quantisation:

| family | arxiv index loss | stackexchange index loss |
|---|---|---|
| single_node ivf | 0.1431 | 0.2414 |
| hash ivf | 0.0603 | 0.1552 |
| semantic ivf | 0.1882 | 0.2138 |

At `nprobe=8` of `nlist=1024`, stackexchange loses roughly twice what arxiv
loses on the two unsharded partitions. **That the corpora diverge here is
the measurement. Why they diverge is a hypothesis**, and it is stated as one:
that the coarse quantiser's cell structure is corpus-dependent in a way the
product quantiser's additional loss is not, because the PQ error is large
enough on both corpora to swamp the difference between them.

Nothing in this run tests that. Two facts are consistent with it and do not
establish it — the IVF gap is 0.098 on single_node while the IVF-PQ gap is
0.007, and stackexchange's semantic partition has twice arxiv's routing loss
(0.1308 against 0.0672), so it is the less crisply clustered corpus of the
two.

**What would test it: sweep `nprobe` across both corpora.** If the hypothesis
holds, the two corpora's IVF curves converge as `nprobe` rises — more cells
probed, less of the cell structure mattering — and their IVF-PQ curves stay
apart by the same small amount at every `nprobe`, because the PQ error does
not depend on how many cells were read. If instead the gap is flat in
`nprobe`, the cell structure is not what is doing it. The machinery exists:
`index` and `nprobe` are both swept keys, so
`grid: {index: [ivf, ivf_pq], nprobe: [1, 2, 4, 8, 16, 32, 64]}` is the whole
change. **Not run** — it is 7× the configurations on each corpus, about
six hours on this laptop, and it is a new measurement rather than part of
this brief.

### Quantisation does not survive sharding

The most useful thing in the table, and it has its own section in
`docs/MODELS.md` because a team walks into it.

A single IVF-PQ index over arxiv-150k measures **7.5 MB** where the vectors
would cost 460.8 MB — **61× compression**, the number anyone would quote. The
same corpus, same algorithm, cut into the 256 regions the semantic partition
uses, measures **265.2 MB** — **6.5×**.

The codes did not change: 557,231 stored vectors at 16 bytes is 8.9 MB. What
changed is that there are 256 codebooks instead of one.

```
        coarse quantiser    nlist × dim × 4   =  64 × 768 × 4      =  197 KB
        PQ codebook         m × 2^nbits × (dim/m) × 4
                                              =  16 × 256 × 48 × 4 =  786 KB
                                                                  ----------
        per shard                                                    983 KB
        × 256 shards                                              ≈  252 MB

        measured overhead                          256.3 MB
        codes being compressed                       8.9 MB
```

**The codebooks cost 29× more than the codes they compress.** stackexchange
agrees to within 0.2 MB — 256.5 MB against 9.4 MB of codes — as expected,
since this is arithmetic over the knobs and not over the data.

Per-shard overhead is `nlist × dim × 4 + m × 2^nbits × (dim/m) × 4`, which
does not shrink as shards get smaller, while the codes in each shard do. So
there is a shard size below which quantisation costs memory rather than
saving it, and a team that read "60× smaller" from a single-index benchmark
and then sharded 256 ways will walk into it. This is not an argument against
sharding or against 256 regions; it is that the two interact, the interaction
is measurable on your own corpus, and the number from one index is not the
number from many.

**Flat is not free, and where it costs is the query.** `hash_sharded[flat]`
queries in 48.6 s (arxiv) and 68.3 s (stackexchange) against 4.3 s and 18.1 s
for HNSW — fan-out 3 with exhaustive scans. Its build is ~0 s and its recall
is 1.0 by construction, which makes it the honest reference point the brief
asked for rather than an option.

**What the report may not say**, and does not: that one of these is better.
They trade differently — 61× less memory for 0.71 of recall, or exactness for
50× the query time — and the trade is the finding.

## Verification

**Passed.** Suite 1102 passed, 1 skipped, 1 deselected. Routing-loss identity
on both fixtures and the smoke fixture. Every published value within
tolerance on both fixtures. The before/after row diff at 034's parent.
`index: hnsw` written out and omitted produce one label, one params dict, one
set of ids and one footprint, for all three families. A grid that never names
`index` produces the label set it produced before 034, with no duplicates.
Foreign knobs, unknown algorithms and under-sized shards refused, each with
its own message and a negative control.

**Failed, then fixed.** My first `vector_bytes` was `n × dim × 4` — what the
vectors would cost stored raw — which made `overhead_bytes` **−453 MB** for
IVF-PQ. A negative overhead is a definition that does not fit the algorithm,
not a small error. `stored_vector_bytes` now answers what the index holds;
a test requires `overhead_bytes >= 0` and `vector_bytes <= index_bytes` for
every family at every algorithm. The arxiv sweep that produced the negative
number was discarded and re-run; the stackexchange sweep was stopped at 3 of
12 rather than allowed to write eleven more.

**Couldn't-check.**

- *Cross-environment determinism for `ivf` and `ivf_pq`.* No session has
  built them on a second machine. Remedy: a pod session.
- *Engine index coverage.* Both adapters ship `not_resolved`, because this
  machine has no Docker and no reachable Qdrant or Postgres, so the question
  has never been put to a running engine. Every cell of the coverage table in
  `docs/ADAPTERS.md` says so. Remedy: `oneground adapters coverage` against a
  pinned engine. The resolvers for both adapters are implemented and have
  **never been executed against a live engine** — only the stub's, which runs
  in-process and is covered by the conformance suite.
- *Whether the two corpora agree about quantisation at another operating
  point.* One `nprobe`, one `m`, one `nbits` per algorithm. Remedy: a sweep
  over the knobs, which the index axis now supports.

## Observed, not done

- **`capacity.py`'s memory estimate is HNSW-only.** `_default_config` returns
  HNSW parameters for every family and `estimate_memory_bytes` takes an `M`.
  A Tier-2 sizing for a quantised index would be wrong by the 61× this task
  measured.
- **`simulate`'s table truncates long labels.** The configuration column is
  52 wide and `semantic_sharded[centroids=256,epsilon=0.2,index=ivf_pq,...]`
  is 96. Pre-existing — the published semantic label was already 68 — but 034
  makes it routine.
- **`index` is swept but `efConstruction` is not.** A user comparing build
  cost across algorithms can vary `nlist` and `m` from a grid but must pin
  `efConstruction` with an `include` entry.

## Repo now contains

New:
- `oneground/models/indexes.py`, `oneground/models/test_indexes.py`
- `oneground/adapters/index_families.py`, `oneground/adapters/coverage_cli.py`
- `requirements.arxiv-smoke.index.yaml`, `requirements.arxiv-150k.index.yaml`,
  `requirements.stackexchange-150k.index.yaml`,
  `requirements.arxiv-150k.reference.yaml`
- `requirements.arxiv-150k.determinism.032b.pod.yaml`

Changed:
- `oneground/models/base.py`, and all three families' `model.py`
- `oneground/models/test_parameters.py`, `test_conformance.py`
- `oneground/simulate/__init__.py`, `oneground/verify/__init__.py`,
  `oneground/report/{__init__,claims,verdict}.py`,
  `oneground/proposals/{card,policy}.py`, `oneground/cli.py`
- `oneground/adapters/{conformance,stub}.py`, both adapters and both
  `ADAPTER.md`
- `oneground/pod/{session,cli}.py`, `oneground/pod/test_pod.py`
- `corpora/compare_state.py`, `corpora/run_032b_state_proof.sh`,
  `sessions/032b-state-proof.yaml`
- `docs/{MODELS,CHARTER,ADAPTERS,STATE}.md`
- `tasks/034-index-algorithms.md` (the addition merged in)

Run outputs (gitignored): `runs/034-index-smoke`,
`runs/034-index-arxiv-150k`, `runs/034-index-stackexchange-150k`,
`runs/034-reference`, `runs/032b-state-local`, `runs/032b-state-pod`,
`runs/032b-state-local.before-fix`.

## Task 032b, closed out here

**The residual, and what it decomposed into.** Session 20260919-152147 at
`b0bfb11` found 5 of 24 state columns differing across an Intel i3-1115G4 and
an AMD EPYC 7352. Separating arithmetic from traversal — by comparing every
`(query, shard, vector)` triple both sides returned — gave the answer:
319,351 shared candidates scored identically, 80,648 moved, and exactly one
candidate per side was unshared. The graphs agree; the floating point does
not.

Two causes, and only one was ours. `route.scored_dist` moved because
`state()` computed the query-side routing outside the determinism context the
base side was computed inside. `a974b1a` puts the context in
`semantic_sharded._probed`, so `search`, `ceiling` and `state` share one
path. Session 20260919-160731 at that commit confirmed it: **`route.scored_dist`
is now byte-identical, and `candidates.cand_score` is unchanged to the
element** — 80,648 of 400,000, 75,811 by one ulp and 4,837 by two.

**The fix moved no measured row.** arxiv-smoke, 12 configurations across all
four algorithms: 0 of 12 rows moved. arxiv-150k reference configurations,
same machine, `b0bfb11` → `a974b1a`: no measured quantity moved, and that
range contains all of 034's index work as well as the state fix.

**The contract.** Written into `docs/STATE.md` as two claims — byte-identical
within an environment, identical decisions and scored floats within a couple
of ulps across environments — with the false-alarm warning, and shipped as
`compare_state.py --cross-environment` so the honest comparison is a command.
Three ways to force byte-identity (reduced precision, decisions only,
rounding) are named and refused: each trades a receipt's exactness for a
simpler claim.

**An ad-hoc harness that nearly became the answer.** Before the laptop half
finished I recomputed `route.scored_dist` on the deterministic path and
compared it to the pod's column, getting 424 of 4,000 differences — which I
was about to report as "the prediction half-failed". The run-to-run
comparison says the column is byte-identical. My harness differed from the
product path in some way I did not chase, and I do not know which. The lesson
is not that the harness was wrong; it is that **a reimplementation of a
measurement is not that measurement**, and when the two disagree the run is
the evidence and the harness is a hypothesis. It nearly inverted a reported
result, and it would have been a finding about my script presented as a
finding about two CPUs.

**On the number in the contract.** I reported the residual as "max |delta|
1.1920929e-07, which is float32 epsilon — one unit in the last place at
magnitude ~1", and the ruling took "within one ulp" from it. That was
imprecise: eps is the ulp *at 1.0*, and these inner products lie in
[0.546, 0.905], where the same absolute delta is two ulps. The measured
distribution is 75,811 pairs at one ulp and 4,837 at two, so the tool's
default is 2 — documented as an observation, not a derivation, with the
distribution printed every time.

**On the pin check I deleted.** Preparing the second session I copied
`corpora/run_032b_state_proof.sh` from the launching worktree, detached at
`b0bfb11`, over this branch's newer copy, silently removing the pin check,
and committed it in `a974b1a`. `24bc2a3` restores it. The consequence for the
record: **the runner did not verify the pin on either of the first two
sessions**, because the commit they were launched from has no such check. The
equality held — I ran `git diff --quiet b0bfb11 HEAD -- oneground/` before
each launch — but I described it in a report as "the runner's own check",
and it was mine. From `a974b1a` onward it is the runner's again.

**Bytes lost.** The third session's fetch extracted into
`runs/032b-state-pod/` in the launching worktree, overwriting the second
session's output. The **pre-fix pod state no longer exists**; only its counts
survive, in this report and the one before it (5 columns differing:
`cand_score` 80,648 of 400,000 at max 1.1920929e-07, `survived_dedupe` 5,244,
`cand_id` 27, `true_rank` 14, `scored_dist` 3,191 of 4,000 at max
7.1525574e-07). The pre-fix laptop half is preserved at
`runs/032b-state-local.before-fix`, and the post-fix pod state has been moved
out of the throwaway worktree to `runs/032b-state-pod/`.

**Three sessions, $0.37 total.** 20260919-144616 failed on the workdir
mismatch (~$0.18, no output); 20260919-152147 measured the residual (~$0.09);
20260919-160731 proved the fix (~$0.10).

## Blocked on developer

- **Engine index coverage.** Needs a reachable Qdrant and Postgres.
  `oneground adapters coverage --engine <name> --endpoint <url>` fills the
  table in `docs/ADAPTERS.md`; until then every engine cell is a
  couldn't-check and both adapters' resolvers are untested against a live
  engine.
- **Cross-environment determinism for `ivf` and `ivf_pq`.** A session.
- **The throwaway worktrees.** `git worktree list` shows two beside the main
  checkout, `oneground-032b` (the 032b launcher, detached at `24bc2a3`) and
  `oneground-pre034` (the step-11 baseline at `d5efd78`); `git worktree
  remove <path>` for each when you are done with them. The first is on branch
  `task-032b-session`, which has one commit (`682d820`) superseded by
  `24bc2a3` on this branch.
- **Whether `simulate` should drop an unbuildable configuration rather than
  abort.** See "Observed, not done".
