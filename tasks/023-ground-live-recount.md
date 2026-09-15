# Task 023 — The ground's live recount

## Setup
Branch `task-020` in the worktree, currently four commits on `383c7a1`.
`main` is frozen for the 23 September release; do not touch it, do not
rebase until the release lands. Commit `task 023:` on `task-020`.

## Why
021 measured the answer and 021b applied half of it. A full recount at
150k is 9.6 ms and a redraw 4.4 ms — 14 ms, inside a frame — while
anything needing an index rebuild is minutes. So the ground moves
continuously with ε and the recall panel does not.

`render_from_state.py`'s ground view still draws the copy counts at the
base state's ε. This task makes it recount. It is the last piece of the
lab's interaction model that is designed and not built.

## Do

1. **The recount, as a contract-bound view.** The ground view takes an ε
   and recomputes, from `AssignmentState` alone: each vector's copy count,
   the copies histogram, storage amplification, p99 copies, per-shard
   sizes, and the routing ceiling at k=10. It reads only the declared
   columns (`nearest_region`, the `MAX_ASSIGN` distances) and no vector
   column — the 021 guard must still pass, and a test must prove the view
   is refused a vector column at run time.

2. **Correctness before speed.** For every ε where a simulated state
   exists (StackExchange 0.0/0.1/0.2/0.3, arXiv 0.1/0.2/0.3), the
   recounted figures must equal that state's own — and equal the
   corresponding `simulate.json` row for storage amplification and the
   ceiling. Exact equality, not tolerance: the recount reads the same
   numbers by a different path. Report the comparison table.

3. **Then speed, measured on this machine.** Time the recount and the
   redraw separately at 20k and 150k, median and p95 over at least 50
   slider steps, and report them beside 021's figures. If either has
   moved materially from 021's measurement, say why before optimising.
   Do not build the incremental index — 021 measured it as not worth
   having, and that decision stands unless your numbers contradict it.

4. **What the ground may and may not show as ε moves.** Geometry
   recounts continuously. Anything requiring a rebuilt index — recall,
   candidates, a query's missed neighbours — follows 021b's rule: shown
   only at simulated ε, otherwise the *not simulated at this epsilon*
   panel with the cost and the action. The ground and the query trace
   must agree about which ε values are simulated; one source, not two.

5. **The honest caption.** When the displayed ε is not a simulated one,
   the ground states in its own caption that the geometry is recounted
   from state and no recall figure is available at this ε — not as fine
   print, as part of the view. A reader who screenshots the ground at an
   unsimulated ε must not be able to mistake it for a measured
   configuration.

6. **Docs.** `docs/STATE.md`'s "When ε moves" section becomes a
   description of what is built rather than what is designed, with the
   new timings.

## Acceptance
- Recounted figures equal the simulated states' own at every simulated ε,
  exactly; table in the report.
- Recount + redraw timings reported at both sizes, beside 021's.
- The 021 contract guard passes; a run-time refusal of a vector column is
  tested.
- The simulated-ε set has one source shared by both views.
- Caption behaviour tested at a simulated and an unsimulated ε.
- `docs/STATE.md` updated; suite green; identifier scan clean.

## Do not
- Touch `main`, the tag, or `site/teaser/`. Rebase before the release.
  Build the incremental index. Change any published value.
