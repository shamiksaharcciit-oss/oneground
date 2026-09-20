# Report: 039-nprobe-sweep

## Repo state expected vs found

Expected, and found:

- `runs/034-index-arxiv-150k/simulate.json` and
  `runs/034-index-stackexchange-150k/simulate.json`, 12 rows each, holding
  the `flat` and `hnsw` reference rows the brief says to cite rather than
  re-measure. Found, cited, not re-measured.
- Both 150k fixtures present locally, so no pod. Found.
- `index` as a declared choice with `nlist`, `m`, `nbits` as 034 left them.
  Found.

One thing the brief did not state and I had to establish before I could cite
the reference rows: **the `hnsw` rows carry no `index` key at all.** 034's
no-re-label rule elides the default from the label, so `params.get("index")`
is `None` for every `hnsw` row and `"flat"`, `"ivf"`, `"ivf_pq"` for the
others. A reader looking up the baselines by `index == "hnsw"` finds nothing.
That is the rule working as designed, not a defect, but it is a trap for
anything that reads these files by index name and it is worth knowing.

The brief was committed before the first row was measured: the predictions
are in `tasks/039-nprobe-sweep.md` at the commit the runs record
(`4faa428`, `dirty: false` in both `simulate_info.json`).

## What was done

Both published fixtures swept over `index: [ivf, ivf_pq]` ×
`nprobe: [1, 2, 4, 8, 16, 32, 64]` at each family's published partition,
with `nlist`, `m` and `nbits` at 034's values. 42 configurations per corpus,
84 in total. No pod; both ran in the background on the laptop.

Nothing else was changed. No gate, threshold, seed or fixture value was
touched.

## Measurements

### Run facts

| | arxiv-150k | stackexchange-150k |
|---|---|---|
| configurations planned | 42 | 42 |
| configurations measured | 42 | 42 |
| dropped | 0 | 0 |
| elapsed | 17,119.5 s = **285.3 min** | 9,413.3 s = **156.9 min** |
| budget | 300 min | 300 min |
| `stopped_after_config` | null | null |
| seed | 20260908 | 20260911 |
| `simulate.json` sha256 | `abee3eb1b9fb5c14e…6aadcd57` | `114ef62854bd28e3…13b872bf28` |

Both from `simulate_info.json`; elapsed is `elapsed_seconds`, the run's own
wall clock. Total 442.2 min against the brief's estimate of about six hours
— 23% over, entirely on arxiv.

**arxiv finished 14.7 minutes inside a 300-minute budget.** Nothing was
dropped and nothing needs re-running, but that is a 5% margin, and the same
sweep with one more `nprobe` value or a slower machine would have tripped
the budget and dropped rows. Reported because it was closer than the
estimate implied, not because it affected this result.

### recall@10 against `nprobe`, with the between-corpora gap

Gap = arxiv − stackexchange.

**single_node_hnsw** (`nlist=1024`)

| nprobe | arxiv ivf | arxiv ivf_pq | stack ivf | stack ivf_pq | gap ivf | gap ivf_pq |
|---|---|---|---|---|---|---|
| 1 | 0.4482 | 0.2415 | 0.3921 | 0.2258 | +0.0561 | +0.0157 |
| 2 | 0.6051 | 0.2700 | 0.5276 | 0.2572 | +0.0776 | +0.0128 |
| 4 | 0.7466 | 0.2839 | 0.6542 | 0.2722 | +0.0924 | +0.0118 |
| 8 | 0.8569 | 0.2872 | 0.7587 | 0.2772 | **+0.0982** | +0.0100 |
| 16 | 0.9296 | 0.2877 | 0.8417 | 0.2780 | +0.0879 | +0.0097 |
| 32 | 0.9728 | 0.2878 | 0.9028 | 0.2781 | +0.0700 | +0.0097 |
| 64 | 0.9910 | 0.2878 | 0.9475 | 0.2782 | +0.0435 | +0.0096 |

**hash_sharded** (`nlist=256`, `shards=3`)

| nprobe | arxiv ivf | arxiv ivf_pq | stack ivf | stack ivf_pq | gap ivf | gap ivf_pq |
|---|---|---|---|---|---|---|
| 1 | 0.5479 | 0.2225 | 0.4703 | 0.2187 | +0.0776 | +0.0038 |
| 2 | 0.7250 | 0.2402 | 0.6241 | 0.2394 | +0.1009 | +0.0008 |
| 4 | 0.8589 | 0.2452 | 0.7548 | 0.2462 | **+0.1041** | −0.0010 |
| 8 | 0.9397 | 0.2461 | 0.8448 | 0.2473 | +0.0949 | −0.0012 |
| 16 | 0.9792 | 0.2462 | 0.9129 | 0.2477 | +0.0664 | −0.0016 |
| 32 | 0.9944 | 0.2462 | 0.9577 | 0.2478 | +0.0367 | −0.0016 |
| 64 | 0.9987 | 0.2462 | 0.9843 | 0.2478 | +0.0144 | −0.0016 |

**semantic_sharded** (`nlist=64`, `centroids=256`, `probe=2`, `epsilon=0.2`)

| nprobe | arxiv ivf | arxiv ivf_pq | stack ivf | stack ivf_pq | gap ivf | gap ivf_pq |
|---|---|---|---|---|---|---|
| 1 | 0.4792 | 0.3534 | 0.4231 | 0.3162 | +0.0561 | +0.0372 |
| 2 | 0.6223 | 0.4038 | 0.5471 | 0.3619 | +0.0752 | +0.0418 |
| 4 | 0.7446 | 0.4324 | 0.6554 | 0.3880 | +0.0892 | +0.0444 |
| 8 | 0.8349 | 0.4459 | 0.7455 | 0.4011 | **+0.0894** | +0.0448 |
| 16 | 0.8947 | 0.4520 | 0.8142 | 0.4069 | +0.0806 | **+0.0451** |
| 32 | 0.9255 | 0.4531 | 0.8554 | 0.4094 | +0.0701 | +0.0438 |
| 64 | 0.9328 | 0.4533 | 0.8692 | 0.4097 | +0.0636 | +0.0436 |

### index loss against `nprobe`

| nprobe | s\_node arxiv ivf / pq | s\_node stack ivf / pq | hash arxiv | hash stack | sem arxiv | sem stack |
|---|---|---|---|---|---|---|
| 1 | 0.5517 / 0.7585 | 0.6079 / 0.7742 | 0.4521 / 0.7775 | 0.5297 / 0.7813 | 0.4536 / 0.5794 | 0.4461 / 0.5530 |
| 2 | 0.3948 / 0.7300 | 0.4724 / 0.7428 | 0.2750 / 0.7598 | 0.3759 / 0.7605 | 0.3105 / 0.5290 | 0.3221 / 0.5072 |
| 4 | 0.2534 / 0.7160 | 0.3458 / 0.7278 | 0.1411 / 0.7548 | 0.2452 / 0.7538 | 0.1882 / 0.5004 | 0.2138 / 0.4812 |
| 8 | 0.1431 / 0.7128 | 0.2414 / 0.7228 | 0.0603 / 0.7539 | 0.1552 / 0.7527 | 0.0979 / 0.4869 | 0.1237 / 0.4681 |
| 16 | 0.0703 / 0.7123 | 0.1583 / 0.7220 | 0.0208 / 0.7539 | 0.0872 / 0.7522 | 0.0381 / 0.4808 | 0.0551 / 0.4623 |
| 32 | 0.0272 / 0.7123 | 0.0972 / 0.7219 | 0.0056 / 0.7539 | 0.0423 / 0.7522 | 0.0073 / 0.4797 | 0.0138 / 0.4598 |
| 64 | 0.0090 / 0.7123 | 0.0525 / 0.7218 | 0.0013 / 0.7539 | 0.0157 / 0.7522 | 0.0000 / 0.4795 | 0.0000 / 0.4595 |

Reference rows, cited from 034 and not re-measured:

| family | arxiv flat / hnsw | stackexchange flat / hnsw |
|---|---|---|
| single_node_hnsw | 1.0000 / 0.9968 | 1.0000 / 0.9938 |
| hash_sharded | 1.0000 / 0.9984 | 1.0000 / 0.9966 |
| semantic_sharded | 0.9328 / 0.9324 | 0.8692 / 0.8688 |

The 034 index losses the brief's "Why" table quotes are reproduced exactly
at the matching `nprobe`: 0.1431, 0.0603, 0.1882 on arxiv and 0.2414,
0.1552, 0.2138 on stackexchange.

## The three predictions

### 1. Did not hold

> *the single_node IVF gap of 0.098 at `nprobe=8` should be **under 0.03 at
> `nprobe=64`***

**Measured: +0.0435.** The bound was 0.03. The gap missed it by 0.0135 —
**1.45× the predicted bound**.

The starting point reproduces: the gap at `nprobe=8` is +0.0982, which is
034's 0.098. The gap did fall from there, by 56% of its value, but it did
not fall below the line the prediction drew, and it was still falling at the
top of the range rather than having flattened.

### 2. Held

> *the two corpora's **IVF-PQ** gap **stays roughly flat in `nprobe`** —
> within about 0.02 across the whole range*

Spread of the IVF-PQ gap from `nprobe=1` to `nprobe=64`:

| family | min | max | spread | allowance |
|---|---|---|---|---|
| single_node_hnsw | +0.0096 | +0.0157 | **0.0061** | 0.02 |
| hash_sharded | −0.0016 | +0.0038 | **0.0054** | 0.02 |
| semantic_sharded | +0.0372 | +0.0451 | **0.0079** | 0.02 |

Held in all three families, the worst at 40% of the allowance.

One detail the prediction did not cover: **the hash_sharded IVF-PQ gap
changes sign.** arxiv leads by +0.0038 at `nprobe=1`; stackexchange leads by
0.0016 from `nprobe=4` on. The magnitudes are small enough to be near the
resolution of a 2,000-query recall, so this is reported as a sign change in
the numbers, not as a claim that one corpus overtakes the other.

### 3. Held on monotonicity; the convergence half is weaker than it looks

> *Both corpora's IVF recall rises monotonically with `nprobe` and approaches
> their flat/HNSW recall at the top of the range.*

**Monotonic: 6 of 6.** Every family on every corpus is strictly increasing
across all seven values.

**Approaches flat at the top of the range** — shortfall of IVF at
`nprobe=64` against that family's flat recall:

| family | arxiv short of flat | stackexchange short of flat |
|---|---|---|
| single_node_hnsw | 0.0090 | **0.0525** |
| hash_sharded | 0.0013 | 0.0157 |
| semantic_sharded | 0.0000 | 0.0000 |

Two qualifications, and both weaken the prediction rather than the result:

**The semantic zeros are degenerate.** semantic_sharded runs `nlist=64`, so
`nprobe=64` probes every list and the IVF is **exhaustive, not approximate**.
Its index loss at that point could not have been anything but 0.0000. That
row is not evidence of convergence; it is arithmetic. The sweep's top point
is a real approximation only for single_node (`nlist=1024`) and hash
(`nlist=256`).

**stackexchange single_node is still 0.0525 short of flat and 0.0463 short of
HNSW at the top of the range.** Whether that counts as "approaches" is a
matter of what the word was meant to bear; it is reported as the number.

The semantic zeros do buy one thing — **a cross-check of the decomposition**.
At `nprobe=64` semantic's index loss is exactly 0.0000 on both corpora, so
all remaining recall difference must be the partition. Measured difference
+0.0636; ceiling difference 0.9328 − 0.8692 = **0.0636**. The two agree
exactly, which is the decomposition proving itself at the one point where it
can be checked in closed form.

## The finding: the gap is non-monotonic, and the two scales disagree about its direction

Neither the hypothesis nor any of the three anticipated failure shapes
describes what the curves did.

**The IVF gap rises before it falls.** It is not monotonically narrowing
(the hypothesis), not flat, and not widening. It peaks in mid-range:

| family | peak gap | at nprobe | 034's reference nprobe | gap there | share of peak |
|---|---|---|---|---|---|
| single_node_hnsw | +0.0982 | 8 | 8 | +0.0982 | **100%** |
| hash_sharded | +0.1041 | 4 | 8 | +0.0949 | 91% |
| semantic_sharded | +0.0894 | 8 | 4 | +0.0892 | **100%** |

**034's published operating point sits at or within 9% of the maximum of
this curve in all three families.** The 0.098 single_node gap that prediction
1 was built on is not a point on a falling curve — it is the top of the
curve. That is the part neither of us anticipated, and it has a consequence
worth more than the prediction: a between-corpora gap quoted at 034's
reference `nprobe` is the largest value that gap takes anywhere in this
range, not a typical one.

**And the difference and the ratio disagree about the direction.** The
prediction was written in differences of recall. Written instead as a ratio
of index losses — stackexchange's loss over arxiv's, which is scale-free and
does not compress as both curves approach the ceiling — the gap **widens
monotonically across the whole range, in every family**:

| nprobe | single_node ratio | hash ratio | semantic ratio |
|---|---|---|---|
| 1 | 1.102 | 1.172 | 0.983 |
| 2 | 1.196 | 1.367 | 1.038 |
| 4 | 1.364 | 1.738 | 1.136 |
| 8 | 1.686 | 2.575 | 1.264 |
| 16 | 2.250 | 4.200 | 1.445 |
| 32 | 3.574 | 7.562 | 1.897 |
| 64 | **5.833** | **12.038** | undefined (both losses 0) |

So the same 84 rows support "the corpora converge as `nprobe` rises"
(differences, past the peak) and "the corpora diverge as `nprobe` rises"
(ratios, throughout). Both statements are true of the measurements and they
point opposite ways. **Which one a report makes depends on a choice of scale
that nobody in 034 or in this brief made explicitly** — including me, when I
wrote the prediction.

I am not claiming which scale is the right one for this question. That is
a decision, and it is not mine.

One more sign disagreement, at the bottom of the range: for semantic at
`nprobe=1`, arxiv has the higher recall (+0.0561) but the **higher** index
loss (0.4536 against stackexchange's 0.4461). Recall difference and
index-loss difference do not agree in sign there, because recall carries the
partition ceiling and index loss does not. It is the only cell in the sweep
where they disagree.

**Also measured, and not predicted either: IVF-PQ saturates early.** It stops
moving at `nprobe=8` (hash, both corpora), `nprobe=16` (single_node, both) and
`nprobe=32` (semantic, both), and plateaus far below flat — 0.2462/0.2478 for
hash against a flat 1.0000. Past its saturation point `nprobe` buys nothing
at all for IVF-PQ while still costing query time.

### What this does to 034's hypothesis

034's explanation was:

> the coarse quantiser's cell structure is corpus-dependent in a way the
> product quantiser's additional loss is not, because the PQ error is large
> enough on both corpora to swamp the difference between them.

**Not settled by this sweep, and not withdrawn.**

- Its PQ half (prediction 2) held cleanly, in all three families.
- Its IVF half made one falsifiable quantitative claim (prediction 1) and
  that claim failed.
- None of the three shapes the brief said would withdraw it occurred.

So it stays a hypothesis, now carrying a known-false consequence and a
measured shape it does not account for. Per the brief, no replacement
explanation is offered here. The rise-then-fall and the difference/ratio
disagreement are reported as measured; I have candidate stories for both and
this run tested neither, so they are not in this report.

## Verification

| check | result |
|---|---|
| Brief step 4 — routing loss identical across every row of a family on a corpus | **PASS** |
| Free reproduction — rows shared with 034 identical field for field | **PASS** |
| All seven `nprobe` values × both algorithms × three families × two corpora | **PASS**, 84/84 |
| Nothing dropped | **PASS**, `dropped: []` and `stopped_after_config: null` on both |
| `requirements_file` sha256 recorded by the run matches the file on disk | **PASS**, both |

**Routing loss** — 14 rows per family per corpus, one distinct value each:

| corpus | single_node_hnsw | hash_sharded | semantic_sharded |
|---|---|---|---|
| arxiv | 0.0 | 0.0 | 0.0672 |
| stackexchange | 0.0 | 0.0 | 0.1308 |

The partition does not move with `nprobe`, as 034 had it.

**Free reproduction** — six labels per corpus appear in both the sweep and
034's reference run (the `nprobe=8` single_node and hash rows, the
`nprobe=4` semantic rows). All twelve are **identical across all 21 fields**,
including `index_bytes`, `overhead_bytes` and every recall. Two independent
runs, different days, same bytes.

**Couldn't check:** whether any of this holds at other `nlist`, `m` or
`nbits`. This sweeps one axis, as the brief says it does. The
difference/ratio disagreement in particular is a statement about these
`nlist` values and nothing more.

## Observed, not done

- **The semantic family's top-of-range point is degenerate.** `nprobe=64`
  with `nlist=64` is exhaustive search. Two of the 84 rows measure nothing
  approximate. A future sweep of this family either caps `nprobe` below
  `nlist` or raises `nlist`, and `simulate` could refuse or flag
  `nprobe >= nlist` the way `indexes.build` already refuses `nlist > n`.
  Not done — it is a change to a refusal and this brief did not ask for one.
- **The `hnsw` reference rows are not addressable by index name.** They carry
  no `index` key, by 034's design. Anything reading these files by algorithm
  needs to know that the absent key means `hnsw`. Worth a helper next to
  `canonical_params` rather than each reader re-deriving it.
- **`runs/` is gitignored**, so the 84 rows behind this report are local
  directories only. The report's numbers are re-derivable from the two
  requirements files and the recorded seeds, and the two `simulate.json`
  digests are above, but this is again evidence whose directory outlives
  nothing — the same pattern already scoped as 035b.
- The arxiv sweep's 5% budget margin, above.

## Repo now contains

New:

- `tasks/039-nprobe-sweep.report.md` — this file.

Already committed earlier on this branch and merged to `main` at `414c600`:

- `tasks/039-nprobe-sweep.md` — the brief, with the predictions, committed
  before the first row was measured.
- `requirements.arxiv-150k.nprobe.yaml`
  (sha256 `b1933956bf6ef6ea…d700d92db959392a`)
- `requirements.stackexchange-150k.nprobe.yaml`
  (sha256 `f1961fc1bb2a5084…c597f523ed4dccd88`)

Untracked, local, cited above:

- `runs/039-nprobe-arxiv-150k/`
- `runs/039-nprobe-stackexchange-150k/`

Scratch (`tasks/scratch/` is gitignored; local only):

- `039-curves.py` — baselines, index-loss tables, the prediction-3 shortfalls
- `039-gap-shape.py` — peak locations, PQ spread, saturation, degenerate points
- `039-scales.py` — the difference/ratio comparison
- `039-verify.py` — the routing-loss check and the free reproduction check
- `039-run-facts.py` — run headers and timings
- `039-list-rows.py` — row lister (how the elided `hnsw` label was found)
- `039-arxiv.log`, `039-stackexchange.log` — the two sweep logs

These six scripts modify nothing and import no project code: they read the
emitted `simulate.json` and `simulate_info.json` only, so every number in
this report comes from the artifacts as written rather than from a
recomputation of my own. That is deliberate — in 032b a recomputation of
mine disagreed with the run's own comparison and was the wrong answer.

No source file was changed by this task.

## Blocked on developer

Nothing for this task.

One decision is raised by it and is not mine: **whether a between-corpora
gap is reported as a difference of recalls or as a ratio of index losses.**
The two disagree about direction on this data, `docs/MODELS.md` quotes
differences, and 034's published gap sits at the maximum of the difference
curve. Whatever is decided, it should be decided once and written down
rather than chosen per report.
