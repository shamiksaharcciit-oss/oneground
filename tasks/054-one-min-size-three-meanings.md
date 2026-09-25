# Task 054 — The floor parameter, three strategies, three meanings

## Setup
New branch from `main`: `git checkout -b task-054 main`. Commit `054:` and
push after every commit. No pod required to characterize the defect (it is
readable from `oneground/chunk/strategies.py`); a pod session is only
needed if the fix is re-measured against `sec-filings-10k` at the same
scale task 031 used (the declared 10% subsample is enough for that;
full-scale re-measurement is not this task's job).

## Why

Found while writing task 052's statement on what the published chunking
comparison establishes: `sentence` and `structure` produce roughly 7,400
orphan chunks each (under the 64-token floor) against `fixed`'s 60 —
**not because `fixed` handles a size floor better, but because the three
strategies implement one underneath a size floor with three different
mechanisms, none stated as differing from the others:**

- **`fixed.min_final`** (`strategies.py:_windows`): a trailing window
  shorter than `min_final` is **not created at all** — the tokens past the
  last full window are dropped from the chunking entirely. The parameter's
  own note says so ("a trailing window shorter than this is dropped, not
  shipped as a fragment"), so this half is documented — but the
  consequence, that content at the end of a document can go completely
  unchunked, is not stated anywhere a reader comparing orphan counts
  across strategies would see it.
- **`sentence.min_final`**: a too-small **final** chunk is merged into the
  previous one (`strategies.py:315-319`). This only ever fires once per
  document, on the last chunk. A document whose *interior* sentence
  grouping produces several small chunks — short sentences, or a document
  short enough that most groups land under the floor — gets no correction
  at all; only the tail is protected.
- **`structure.min_size`**: a *different parameter name*, and a different
  stage entirely — consecutive structural units shorter than `min_size`
  are merged **before** chunking happens (`strategies.py:340-346`), based
  on the unit's own length, not the resulting chunk's. It has no concept
  of "the trailing chunk" at all.

**This is a defect in the strategies, not a caveat on the comparison
that found it.** "60 orphans against 7,400" currently reads, to anyone
who has not read this code, as a quality signal — `fixed` is careful about
fragment size, the other two are not. It is instead three unrelated
behaviors answering to two differently-named parameters, none of which
says in its own documentation that the other strategies mean something
else by the same idea. `docs/CHUNKING.md`'s task-052 addendum names this
and defers the mechanism here rather than re-deriving it.

**Two constraints from the ruling, ahead of the Do list because they
decide its shape.** (1) Decide what `min_size` — the floor, under
whichever parameter name each strategy calls it — means, **once**, and
make all three strategies obey that one meaning. A strategy that
genuinely cannot obey it gets a **declared exception with a reason**,
the same shape `OUTSIDE_THE_TABLE` already uses elsewhere in this
package for a rule one place cannot express — not a silent third
behavior standing in for a decision nobody made. (2) Say what changes in
the *published* 031 comparison once the floor is unified. If the 241×
boundary-alignment result or the A/B disagreement (`structure` losing
`self_recall@5` to `fixed`) moves — direction, not just margin — **that
is the finding, and it outranks the repair.** A cleaner floor that leaves
the headline unchanged is a smaller result than a cleaner floor that
changes what the project's best-known finding was actually measuring.

## Do

1. **State the one floor semantics, and make all three strategies use
   it.** Read the three current behaviors (above) as three candidate
   answers to one question — *what happens to content that would produce
   a chunk shorter than the floor* — and decide which is right, applying
   it uniformly: merge into the nearest neighbor (`sentence`'s current
   trailing-only behavior, extended to every undersized group, in every
   position a document can produce one); or something else, stated as
   plainly. `fixed`'s current behavior (drop the tail rather than ship or
   merge it) is silent data loss and is not a defensible landing point on
   its own merits — if it is kept, it needs the declared-exception
   treatment in item 2, not silent retention.
2. **Where a strategy genuinely cannot implement the chosen semantics,
   declare the exception, with the reason, in the same place the Param
   notes live** — not a footnote, not a comment three functions away from
   where a reader would look. `structure.min_size`'s pre-chunking merge
   (by structural unit, not by resulting chunk) may be one of these,
   since it operates at a different stage than `fixed`/`sentence`'s
   post-hoc window fixup — decide whether that difference is a genuine
   structural necessity (structure cuts on document boundaries that exist
   before tokenization has a "trailing window" to speak of) or whether it
   too can be brought in line.
3. **Update each Param's own note** to state its (possibly now-shared)
   behavior and to name any declared exception — a reader of one note
   should not have to separately read three functions to learn the other
   two differ.
4. **Re-measure on the same `sec-filings-10k` 10% subsample task 031
   used**, before-and-after, every measure orphan count could plausibly
   move (length distribution, both path-B columns, and boundary
   alignment / span survival if the floor change alters chunk starts
   materially) — and lead the report with whichever of the 241× ratio or
   the `self_recall@5` A/B disagreement moved, if either did, ahead of
   the mechanical description of what changed in the code.

## Acceptance

- One stated floor semantics, applied by all three strategies, or a
  declared exception with a reason for any that does not — no strategy
  left on undocumented, ad hoc behavior.
- Every floor-handling Param note states its own behavior and names any
  other strategy that differs and why.
- `fixed`'s silent tail-drop is gone, merged into the chosen semantics,
  or kept only as a declared exception with a stated reason — never left
  as an undocumented default.
- Orphan counts and every measure named in item 4 re-measured on the same
  10% subsample and compared against task 031's published numbers.
- The report states plainly whether the 241× finding or the A/B
  disagreement moved direction, not only margin — and if either did, that
  is stated as the task's headline finding, ahead of the mechanical
  description of the fix.
- Full suite green, guard clean, identifier scan runs rather than skips.

## Do not

- Change what "size", "max_size" or "overlap" mean for any strategy —
  this is scoped to the floor/minimum parameters only.
- Re-run the full-corpus 3-strategy comparison. The 10% subsample is
  sufficient to measure what this task changes; a full-scale re-run is a
  separate cost decision.
- Leave a strategy's inability to comply undeclared. If it cannot be
  brought in line, say so, with a reason, where the Param notes live —
  not silently, and not as a private judgment call left unexplained in
  the report alone.
