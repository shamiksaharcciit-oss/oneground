# Task 027 — The projection, declared

## Setup
Branch `task-020` at `fc83608` or later, rebased on `main`. Commit
`task 027:` and push after every commit.

## Why
The lab's ground is a grid of region cells — "a layout, not a map: the
state holds no positions" — because the 2-D projection is declared
illustrative in the fixture spec and so was never emitted as state. The
contract is doing its job. The consequence is that the lab refuses to draw
the picture the teaser used to sell the product.

Decision, by the developer on 18 September: **the projection becomes a
declared column in the state**, illustrative and labelled, and the ground
draws it — the teaser's own approach, carried into the instrument.

## Do

1. **Emit it, as declared.** `simulate --emit-state` writes
   `assignment.projection` (two float32 columns per base vector, plus the
   same for queries) with `kind: declared`, and `state_info.json` records
   the method, its parameters and seed, the library version, and the
   sentence the fixture spec already uses: *2-D placement is illustrative;
   regions, distances and copy counts are computed in the full space.*
   When the fixture already carries a projection (`projection.npy`,
   declared), reuse it and record its digest rather than recomputing. When
   none exists and `[view]` is not installed, the column is absent and the
   ground falls back to the cell layout with its current caption — a
   projection is never a precondition for the lab.

2. **The contract stays literal.** The projection is a *declared position*,
   not a vector column: the view reads it like any other stored number and
   may not compute a distance from it, a cluster over it, or a neighbour by
   it. Add that to the contract's rules and to the guard's tests — a view
   that measured anything from projected coordinates would produce a
   number that disagrees with the table and looks like a map.

3. **The ground draws it.** With the column present, the ground renders
   points at their projected positions, coloured by copy count at the
   current ε, centroids marked, recount on ε unchanged. The cell layout
   remains as the fallback and as a toggle — it is the truer picture of
   *which region* a vector belongs to, and some readers will want it.

4. **The trace draws on it.** The query trace overlays the routed region,
   the probed regions, the true neighbours and the ones the route never
   reached on the same projection, as the teaser does.

5. **The caption says what it is, in the view.** Every projected drawing
   carries, as part of the drawing and not as fine print: *positions are a
   declared projection, illustrative; nothing on this picture was measured
   from where the points are.* A screenshot of the ground must carry that
   sentence. The `positions:` row in "what this drawing says about itself"
   changes from `couldn't check` to `declared` with the method and seed.

6. **Prove it against the teaser.** On the arXiv run with the fixture's
   own `projection.npy`, the lab's ground at ε 0.20 and the teaser's
   `data/base.bin` must place every vector at the same coordinates and the
   same copy count — compare by id, report the maximum coordinate
   difference and the count of copy-count disagreements, both expected to
   be zero. The 020 acceptance script must still pass 20 of 20.

7. **Docs.** `docs/STATE.md`: the new column, its kind, why it is declared
   and what a view may not do with it. `docs/LAB.md`: the two ground
   modes and what each is for.

## Acceptance
- Column emitted as declared, with provenance in `state_info.json`.
- Guard refuses measurement over projected coordinates; tested.
- Ground and trace draw the projection; cell layout remains as fallback
  and toggle.
- Caption in the drawing; `positions: declared`.
- Coordinate and copy-count agreement with the teaser: 0 and 0.
- 020 acceptance 20 of 20; suite green; identifier scan clean; pushed.

## Do not
- Compute anything from projected coordinates in a view. Make the
  projection a precondition. Change any measured value. Rebase or merge
  to `main`.
