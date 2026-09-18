# Report: 023-ground-live-recount

## Repo state expected vs found

- **Branch:** as expected. `task-020` in the worktree, five commits on `383c7a1` (tasks 020, 021, 021b, 021c and the 023 brief at `c941150`), clean tree. `main`, the tag and `site/teaser/` untouched, and no rebase.
- **The brief:** `tasks/023-ground-live-recount.md`, committed on the branch.
- **Nothing unexpected.**

## What was done

**(1) The recount, as a contract-bound view.** `oneground/lab/views/ground.py` recounts what ε decides instead of reading back what one run emitted.
- **The closure**, in `recount(dist, near, epsilon, n_regions)`: `d <= d[:, [0]] * (1 + epsilon)` on the stored float32 distances with ε a Python float — the expression `semantic_sharded.build` uses, so the recount reproduces that run's bits rather than approximating them. It returns the closure mask, each vector's copy count, and the vectors each region holds.
- **What the view draws from it:** the copies histogram, vectors copied, storage amplification, p99 copies, per-shard sizes, boundary crispness (ε-independent), and the routing ceiling at k=10 — a true neighbour is reachable when some region the query probes holds a copy of it at this ε.
- **Columns:** the declared ones only — `assignment.centroid_dist`, `assignment.nearest_region`, `assignment.home_region`, `partition.region_ids`, `route.probed_region`, `candidates.true_ids`, and `assignment.copy_count` / `load.vectors_held` on the fallback path. No vector column.
- **The guard still passes**, and the run-time refusal is tested: `GroundView` subclasses that declare `partition.centroids`, or reach for it without declaring it, both raise `VectorColumn`.
- **Old states still render.** A state without `nearest_region` cannot be recounted, so at another ε the view reports a `couldnt_check` gap, keeps the figures the run emitted, and says so in its caption.

**(2) `EpsilonSet`: one source for both views.** `contract.EpsilonSet` carries where the control stands, which ε values were simulated, and the cost and action a panel offers between them. `plan()` in `render_from_state.py` builds it once from the declared set of state directories and hands the same object to the ground and to the query trace, which cannot then disagree about which ε values are simulated. The query trace was refactored onto it.

**(3) The honest caption.** `Drawing.caption` is part of the drawing. `contract.draw` refuses a recounting view whose drawing has no caption, and at an ε that was not simulated it refuses a caption that does not say `not simulated at this epsilon` and that the geometry was recounted from state. The ground's caption names the simulated ε values and states that no recall figure exists at this one.

**(4) What still waits for a simulated ε.** Unchanged from task 021b: recall, candidates and a query's missed neighbours are drawn only from a state simulated at the ε asked for; between them the recall panel carries the cost and the action. The ground adds no recall-shaped figure beyond the ceiling, which needs no index.

**(5) The composer.** `render_from_state.py` draws the ground from the base state at `--epsilon` (the closure at any ε follows from stored columns, so the ground never needs the state simulated at that ε), prints the caption and the ceiling, and writes both into its JSON.

**(6) Docs.** `docs/STATE.md`'s "When ε moves" section now describes what is built: the recount, the measured timings with the machine control, the ceiling, the one ε set, the caption rule, and the vector refusal. Its closing "designed, not yet a lab module" paragraph is gone.

## Measurements

**Correctness first: the recount equals the runs, exactly** (`tasks/scratch/023-check.py`). The ground is drawn from the base ε 0.2 state at each ε, and compared with the run that simulated that ε.

| fixture | ε | per-vector copy counts | vectors per shard | all ground figures | storage: recount = `simulate.json` | ceiling@10: recount = `simulate.json` |
|---|---|---|---|---|---|---|
| StackExchange 20k | 0.0 | exact | exact | exact | 1.000000 = 1.0 | 0.528150 = 0.52815 |
| StackExchange 20k | 0.1 | exact | exact | exact | 2.871900 = 2.8719 | 0.749900 = 0.7499 |
| StackExchange 20k | 0.2 | exact | exact | exact | 3.871750 = 3.87175 | 0.802100 = 0.8021 |
| StackExchange 20k | 0.3 | exact | exact | exact | 3.994900 = 3.9949 | 0.805150 = 0.80515 |
| arXiv 150k | 0.1 | exact | exact | exact | 2.667153 = 2.667153 | 0.895250 = 0.89525 |
| arXiv 150k | 0.2 | exact | exact | exact | 3.715160 = 3.71516 | 0.932300 = 0.9323 |
| arXiv 150k | 0.3 | exact | exact | exact | 3.970260 = 3.97026 | 0.935750 = 0.93575 |

- **"exact"** means array equality against that state's own `assignment.copy_count` and `load.vectors_held`, and equality of every ground figure with the same view drawn from that state at its own ε: histogram, percentages, vectors copied, storage, p99, crispness, vectors held, ceiling and reachable count.
- **Against `simulate.json`**, storage and the ceiling are compared at the six decimals `simulate` writes, which is the receipt's own precision.

**Then speed** (`tasks/scratch/023-bench.py`, 101 slider positions, each cost in its own warmed pass so one's allocations do not land in another's timings).

| median (p95) | 20,000 vectors | 150,000 vectors |
|---|---|---|
| `recount` | 2.0 ms (2.6) | 22.9 ms (31.5) |
| routing ceiling@10, every query | 10.0 ms (18.6) | 10.1 ms (59.8) |
| redraw: figures, marks, caption | 13.7 ms (137.8) | 12.5 ms (67.4) |
| whole ground draw | 27.5 ms (148.6) | 44.7 ms (103.7) |
| task 021 reported, when 021 ran | 1.5 / 9.6 ms recount + ceiling; 0.6 / 4.4 ms draw | |

**This moved materially from task 021's figures, and the cause is the machine, not the code.** The brief asks why before optimising, so I measured rather than guessed:

- **Control.** Task 021's own benchmark, its unchanged code, re-run on the same machine in the same session: its `full_recount.ground` reports **3.97 ms at 20k and 33.0 ms at 150k**, against the **0.82 ms and 8.64 ms** task 021 recorded. The machine is about 3.8× slower today than when task 021 measured — a laptop under different thermal and background conditions, a week later.
- **Against that control, task 023's recount is not a regression.** In one process on today's machine: task 021's shaped recount 21.5 ms, task 023's `recount` 22.9 ms at 150k, for slightly different work (021's includes histogram and p99; 023's includes per-region membership). Task 021's own bench measured 33.0 ms for its version in a separate process on the same day.
- **Nothing was optimised.** The design decision stands on the gap to a rebuild — 45 ms against 194–398 s at 150k — which no plausible machine state closes.

**Where a draw's time goes** (`tasks/scratch/023-profile.py`, 20 draws under cProfile):
- **The recount and numpy reductions dominate** at both sizes.
- **The only size-independent cost** is `StateColumns.__init__`'s defensive `copy.deepcopy` of the state header: 292 Python-level deepcopy calls per draw, about 1–2 ms. That copy is what keeps a view from editing the header it was handed. It is a candidate if the lab ever needs the last millisecond; I left it alone.
- **The incremental index was not built**, per the brief and task 021's measurement.

## Verification

- **`oneground/lab/test_lab.py`: 27 of 27.** New in this task:
  - the recount at the state's own ε reproduces its emitted copy counts and shard sizes exactly, at ε 0.0, 0.1, 0.2 and 0.5;
  - drawn from the 0.2 state at 0.1, the ground shows what the 0.1 run emitted, and the closure differs between those ε values, so the test is not vacuous;
  - the ground is refused `partition.centroids` at run time, declared or reached for;
  - captions: plain at a simulated ε, and carrying `not simulated at this epsilon` plus the recount wording between them;
  - the contract refuses a recounting drawing with no caption, or one that hides either fact;
  - one `EpsilonSet` answers for both views, which agree on the simulated set;
  - through the composer: the ground recounts at 0.2, 0.15, 0.1 and 0.05, captions the unsimulated ones, and both views report the same set.
- **Full suite** (`pytest oneground corpora`, from the worktree root): **823 passed, 3 skipped, 0 failed**, in 445.3 s. That is 7 more than task 021c's 816: the new lab tests. The 3 skips are the same environment gates as before: no local `runs/arxiv-150k-via-characterize` verify or report workdir, at `oneground/report/test_claims.py:443`, `oneground/report/test_end_to_end.py:348` and `oneground/verify/test_matched.py:1182`.
- **Step 4 unchanged at the default ε:** the rewritten ground gives all 24 compared fields equal to task 020's rendering, and task 020's unchanged acceptance script passes 20 of 20 on the arXiv state.
- **The correctness table above** is the acceptance criterion, exact at all 7 simulated ε values across both fixtures.
- **Identifier scan:** every changed file scanned before commit, and the committed tree scanned after.

## Observed, not done

- **Two of my own test expectations were wrong**, and the code was right: per-shard holdings (each region homes 3 of 12 vectors, and the six even ones copy into regions 1 and 3, giving 3/6/3/6), and the closure at ε 0.15 in a synthetic state built with a 1.15 ratio, where `1.15 <= 1.15` copies. Both are fixed, and the second now checks ε 0.05 as well, where the closure really is empty.
- **The first benchmark I wrote measured its own noise.** It timed the recount, the ceiling and a whole draw inside one loop, so the drawing's allocation and GC time landed in the recount's numbers (a 4.3 s maximum at 150k). It now times each cost in a separate warmed pass. The first numbers are not in this report.
- **The ceiling costs about as much at 20k as at 150k** (10.0 vs 10.1 ms): it scales with queries × k × `max_assign` × probes, not with the corpus.
- **The header deepcopy per draw** is named above and not changed.
- **The ground is drawn from the base state at every ε.** A different base state of the same configuration would give the same figures — that is what the correctness table shows — so the choice does not affect what is drawn, only which file is read.
- **`corpora/render_ground.py`** still draws the teaser's ground from the old export path. It is not a lab view and was outside this task.

## Repo now contains

On `task-020`, not pushed, one new commit after `c941150`:
- `oneground/lab/contract.py`: `EpsilonSet`, `Drawing.caption`, `View.recounts`, the caption refusals, and the recount stamp.
- `oneground/lab/views/ground.py`: the recount and the recounting view.
- `oneground/lab/views/query_trace.py`: refactored onto `EpsilonSet`.
- `corpora/render_from_state.py`: one ε set for both views; the ground drawn at `--epsilon`; the caption and ceiling printed and stored.
- `oneground/lab/test_lab.py`: 27 tests.
- `docs/STATE.md`: "When ε moves" as built.
- This report.

No measured value, tolerance, seed, gate, fixture file or published figure was changed.

## Blocked on developer

Nothing. Standing by, and the hold on `main` and the rebase is unchanged: `task-020` is rebased onto `main` the day the release lands, before anything else.
