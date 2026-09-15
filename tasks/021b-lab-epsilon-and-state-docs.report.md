# Report: 021b-lab-epsilon-and-state-docs

## Repo state expected vs found

- **Branch:** as expected. The worktree `oneground-v2` is on `task-020` at `57ae41f` (task 021, accepted), with a clean tree. The main checkout and `main` were not touched.
- **The brief:** there is no file. It is the developer's message: two items, a note for the report, commit on `task-020`.
- **Nothing unexpected was found.**

## What was done

**(1) `docs/STATE.md`, updated as named.**
- **New sections:**
  - "The field task 021 found missing: `assignment.nearest_region`": why a recount could lower ε but not raise it, that the column is additive, the size change, and the validation against runs at five other ε values.
  - "The rendering contract": views, declared reads, no vector columns, read-only state, tally versus measure, the drawing, and the guard. It also states the guard's limit: names and syntax, not types, so `a * b` over two vectors would pass, and it cannot tell a tally over stored numbers from a new measurement assembled out of them. The runtime refusal of vector columns is the primary guarantee.
  - "When ε moves": the three classes of column, the measured table at 20,000 and 150,000 vectors, the conclusion that **a full recount per move is the design** (no incremental index), and the declared-set rule for recall (item 2).
- **Existing sections updated:**
  - The rule now records that the state has been insufficient twice, with both fields named.
  - The `AssignmentState` row and the state contract list `nearest_region`.
  - The browser note carries the current sizes, including the 2.2 MB ground drawing.
- **Removed from "Not settled":**
  - the "incremental recomputation as ε moves" note, which the new ε section replaces;
  - the "interactivity" note, which now reads that ε is settled and other controls (probe, centroid count, index parameters) are not yet classified or measured.

**(2) Recall at other ε: a declared set, rendered on request, as a contract.**
- **`oneground/lab/contract.py`.**
  - A `Drawing` now carries `panels`. Each has one of two states: `SIMULATED`, with its figures, or `NOT_SIMULATED` ("not simulated at this epsilon").
  - `draw` refuses, for every view:
    - a simulated panel with figures for an ε its state was not simulated at, which would be interpolation;
    - a simulated panel with no figures;
    - a not-simulated panel that carries figures;
    - a not-simulated panel that lacks the ε asked for, the simulated ε values, the cost in minutes or the action;
    - a not-simulated panel at the ε the state *was* simulated at;
    - any not-simulated drawing that read a column `ON_EPSILON` says ε rebuilds.
  - `same_epsilon` compares at six decimals, the precision `simulate` writes.
- **`oneground/lab/views/query_trace.py`** is split by `ON_EPSILON`.
  - **Geometric half:** routed and probed regions, true neighbours, home regions, outside count. It reads only columns ε leaves unchanged, and is drawn at any ε.
  - **The `recall` panel:** recall@k (the merged top k: first occurrences, best score first), the returned candidates, the neighbours the route missed, and the answerable-from-candidates diagnostic. It is drawn only at the ε its state was simulated at.
  - **Between simulated ε values,** the panel is `NOT_SIMULATED`, with the simulated ε values, the declared cost and the action. With none declared it still carries a `couldnt_check` cost and a runnable default action, so it is never blank.
  - **A simulated ε over the wrong state** (the one simulated at a different ε) is refused (`ValueError`). That recall lives in the other state.
- **`corpora/render_from_state.py`.**
  - `--epsilon` is where the control stands.
  - `--simulated DIR` (repeatable) adds state directories. With the base directory, they form the declared set: every state of the same configuration differing only in ε.
  - `plan()` draws the trace from the state simulated at the asked ε when it exists, and from the base state otherwise.
  - **The cost** is the build + query minutes of that configuration at the simulated ε values, from their runs' declared `simulate_info.json` timings. Its basis is stated in the panel.
  - **The action** carries the configuration at the new ε, its grid, the requirements file name and `oneground simulate … --emit-state`.
  - At the default ε, the output keeps task 020's shape. It adds `recall_at_k_mean` over every query and the panel.
- **Tests in `oneground/lab/test_lab.py`** (19 now; 5 new, and the trace test updated):
  - between simulated ε values, no recall, candidates or missed neighbours appear anywhere in the drawing, no rebuild column is read, and every geometric readout equals the simulated one;
  - the panel is never blank;
  - a simulated ε is drawn from its own state;
  - the contract refuses each interpolated and blank form above;
  - `render_from_state.py` switches states across a declared set of two synthetic runs, draws the not-simulated panel with the measured cost (2.0–5.0 min) and the exact command at 0.15, and keeps every query's routed region and outside count.

## The pattern: the renderer is the state's acceptance test

The state has now been insufficient twice. Both times, a consumer that needed a column found the gap. Reading the model did not.

- **Task 020: `candidates.true_ids`.**
  - **How it was found.** `render_from_state.py` could not answer "how many true neighbours lie outside the routed region" for 2 of 60 synthetic queries. On arXiv that became 609 of 2,000.
  - **Why nothing earlier caught it.** The state carried true neighbours only as candidates a shard had returned. The dataclasses looked complete, every field was a measurement, and the state contract and conformance suite passed. Those suites check that a state is internally consistent. None of them asks whether it is sufficient.
- **Task 021: `assignment.nearest_region`.**
  - **How it was found.** Working out what a render at a moved ε would have to recount from state. Copy sets above the emitted ε need region ids the state did not keep.
  - **Why nothing earlier caught it.** The state was again consistent, again passed every check, and again could not serve the view.

**The argument this makes.** Sufficiency is not a property of the state on its own. It is a property relative to what has to be drawn from it, and only something that draws from it can test that.

- **Every future change to the state lands with its consumer.** It comes with the rendering that needs it, and that rendering passes: the published figures through `render_from_state.py` and task 020's unchanged acceptance comparison, plus a check like this task's recall panel against `simulate.json`.
- **A state change that no renderer exercises is untested,** however consistent it is.
- **The acceptance test grows with the views.** A view that does not exist yet has not tested anything.

## Measurements

**The recall panel on real runs** (`tasks/scratch/021b-check.py`, through `render_from_state.py`'s own `plan` and `draw_every_query`).

| fixture | ε | panel | drawn from | recall@10 over every query | `simulate.json` recall_at_10 | routed region and outside count, every query |
|---|---|---|---|---|---|---|
| StackExchange 20k | 0.0 | simulated | ε 0.0 run | 0.528150 | 0.52815 | identical to base |
| StackExchange 20k | 0.1 | simulated | ε 0.1 run | 0.749900 | 0.7499 | identical |
| StackExchange 20k | 0.2 | simulated | reference run | 0.802100 | 0.8021 | identical |
| StackExchange 20k | 0.3 | simulated | ε 0.3 run | 0.805100 | 0.8051 | identical |
| StackExchange 20k | 0.05, 0.15, 0.25 | not simulated; cost 0.1–0.6 min; action at that ε | base state | not drawn | — | identical |
| arXiv 150k | 0.1 | simulated | ε 0.1 run | 0.895100 | 0.8951 | identical |
| arXiv 150k | 0.2 | simulated | reference run | 0.931800 | 0.9318 | identical |
| arXiv 150k | 0.3 | simulated | ε 0.3 run | 0.935300 | 0.9353 | identical |
| arXiv 150k | 0.15, 0.25 | not simulated; cost 3.2–6.6 min; action at that ε | base state | not drawn | — | identical |

- **Recall from state matches.** The view's recall, averaged over all 2,000 queries, equals `simulate.json` at every one of the 7 simulated ε values.
- **Geometry doesn't move.** The geometric readouts are identical at all 12 ε values checked, simulated or not.
- **Cost basis.** Build + query of one configuration, from single runs on this laptop. Loading, ground truth and k-means are not included, and the panel says so.

**From the command line, arXiv at ε 0.15:**

```
epsilon 0.15   simulated at [0.1, 0.2, 0.3]   query trace drawn from runs\020-ref-arxiv\state\semantic_sharded__c95327ef.state.npz
  routed region 131   probed [131, 215]
  true neighbours 10 of 10; outside routed region 10
  recall panel      not simulated at this epsilon 0.15 (simulated: [0.1, 0.2, 0.3]); cost 3.2-6.6 min
                    run: oneground simulate 020-ref-arxiv.yaml --emit-state  with epsilon 0.15
  recall            not simulated at this epsilon
```

At the default ε 0.2, the same query's panel reads: simulated, recall@10 0.60, missed by the route 4.

## Verification

- **`oneground/lab/test_lab.py`: 19 of 19.**
- **Full suite** (`pytest oneground corpora`, from the worktree root): **815 passed, 3 skipped, 0 failed**, in 311.9 s. That is 5 more than task 021's 810, the new lab tests. The 3 skips are the same environment gates as before: no local `runs/arxiv-150k-via-characterize` verify or report workdir, at `oneground/report/test_claims.py:443`, `oneground/report/test_end_to_end.py:348` and `oneground/verify/test_matched.py:1182`.
- **Step 4 at the default ε, after the composer change.**
  - The views' output equals task 020's `render.json` in all 24 compared fields, across 2,000 queries (`tasks/scratch/021-render-equivalence.py`).
  - Task 020's acceptance script, unchanged (sha256 `9fc0a0d9…`), passes 20 of 20 on the re-emitted arXiv state.
- **The recall panel on real runs:** all 12 cases hold, on both fixtures (table above).
- **Identifier scan:** `docs/STATE.md` and every changed code file scanned clean before commit. It was re-run against the committed tree.

## Observed, not done

- **The ground's live recount is designed, not built.** `docs/STATE.md` specifies it: a full recount per move, as a declared state transform outside `views/`. `render_from_state.py` still draws the ground at the base state's ε. The query trace's geometric readouts are correct at any ε because none of them depends on ε. The ground's copy counts do depend on it, and are not yet recounted to `--epsilon`.
- **Recall could in principle differ on exact score ties.** The view's recall orders surviving candidates with a stable sort. `base.merge_candidates` uses an unstable one, so exact score ties at rank k could order differently. On these fixtures the two agreed at all 7 simulated ε values, and I didn't change `merge_candidates`.
- **The declared set is formed from state directories on the command line.** Nothing yet records which runs belong to a lab session, which the lab would need.
- **The action names the requirements file its runs used** (here a scratch copy). A lab running it would still have to write a requirements file at the new ε. The action carries the exact configuration and grid for that.
- **The check scripts are in scratch.** `tasks/scratch/021b-check.py` and task 020's acceptance comparison are gitignored, as before. The synthetic tests in `test_lab.py` are tracked.

## Repo now contains

On `task-020`, not pushed, one new commit after `57ae41f`:
- `docs/STATE.md`: item (1).
- `oneground/lab/contract.py`, `oneground/lab/__init__.py`: panels, `SIMULATED` / `NOT_SIMULATED`, `same_epsilon`, and the refusals in `draw`.
- `oneground/lab/views/query_trace.py`: the geometric half and the recall panel.
- `corpora/render_from_state.py`: the declared set, `--epsilon`, `--simulated`, the cost and the action.
- `oneground/lab/test_lab.py`: 19 tests.
- This report.

No measured value, tolerance, seed, gate, fixture file or published figure was changed.

## Blocked on developer

Nothing. The natural next step is the ground's recount as a declared state transform, so the ground's copy counts, histogram, storage and ceiling move with `--epsilon` as `docs/STATE.md` now specifies. That needs a brief.
