# Task 025 — The lab interface, finished

## Setup
Branch `task-020` in the worktree, twelve commits on `383c7a1`. `main` has
moved (022–022c, the licence). Do not rebase — that is the first thing on
the 23rd. Commit `task 025:` on `task-020`.

## Why
The foundation is built and measured: the state, the contract, the ε rule,
the continuous recount, the server with its security model, the render
mode chosen by measurement. What does not exist is an interface a person
would want to use. One browser pass has been made; that is not the same as
finished.

**This task is judged on the 20th by the developer opening it and using
it.** Not by tests passing. The acceptance criterion is a person's
judgement, and the work is to make that judgement easy to give.

## Do

1. **The ground, finished.**
   - The plot fills its space and redraws correctly on window resize.
   - The ε control: current value, the simulated values marked on the
     track, and a keyboard path (arrow keys, Home/End) as well as drag.
   - The readouts — copies histogram, storage amplification, p99 copies,
     vectors copied — update per 023's recount and are legible at a
     glance rather than requiring study.
   - The mode caption per 023b: which mode, why, and the measured p95.
   - At an unsimulated ε the caption says the geometry is recounted and
     no recall figure is available here, in the view rather than as fine
     print.
   - Copies 3 and 4 are currently hard to distinguish. Fix it *without*
     forking the teaser's palette: shape, size, or a legend with counts —
     your choice, but a reader must be able to tell them apart.

2. **The query trace, finished.**
   - A query picker that is usable with 2,000 queries: search or filter
     by text, and a way to reach the interesting ones (most neighbours
     missed, fewest, ambiguous, unambiguous).
   - The trace itself with a key saying what each mark means.
   - The four hops as 021b renders them, and the recall panel obeying the
     ε rule exactly — at an unsimulated ε it shows the *not simulated*
     panel with the simulated values, the cost in minutes, and the exact
     command, never a blank and never an interpolation.

3. **Getting in and around.** A landing state that says what run is
   loaded, from which workdir, with its digests, and offers the two
   views. Moving between them keeps the ε. Nothing requires reading the
   docs first.

4. **Both sizes, really tested.** 1200 px and 500 px, both views, every
   state: simulated ε, unsimulated ε, a query with all ten neighbours
   found, a query with none. Report what you saw, not that the requests
   returned 200 — that distinction cost a day last week.

5. **The contract still holds.** Every view remains a view; the guard
   passes; the server computes nothing; the workdir is unchanged after a
   session. Re-run those proofs and report them.

6. **`docs/LAB.md`** gains a short "using it" section with the two views,
   the ε rule as a user meets it, and the mode caption explained.

## Acceptance
- The developer opens it on the 20th against a real workdir and can use
  both views without asking a question.
- Both sizes, every state, reported as observations.
- Contract, no-write and guard proofs re-run and reported.
- No external requests. Suite green. Identifier scan clean.

## Do not
- Rebase. Touch `main` or `site/teaser/`. Fork the teaser's palette.
  Add a view that computes. Ship a state that renders blank.
