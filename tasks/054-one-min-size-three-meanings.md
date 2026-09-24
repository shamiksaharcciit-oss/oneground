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

## Do

1. **State the three behaviors as one comparison**, in `oneground/chunk/
   strategies.py` where the three `Param` declarations already live —
   each `min_final`/`min_size` note should say what it does *and* that
   the other two strategies mean something different by the same role,
   so a reader of one Param's note is not left to discover the other two
   by separately reading three functions.
2. **Decide, and rule on, whether `fixed` dropping trailing content is
   the behavior this project wants.** It is currently silent data loss at
   the chunk level: tokens the user's document contains that appear in no
   chunk `oneground chunk` writes. Options to weigh, not to pick
   unilaterally — bring them to the developer rather than choosing:
   - keep it, documented more prominently, with the dropped token count
     surfaced somewhere the run reports it (today it is invisible —
     nothing counts or reports how many tokens `fixed` drops per
     document);
   - change `fixed` to merge its short tail into the previous window the
     way `sentence` does, which would make the two consistent and would
     change `fixed`'s own numbers on every existing measurement that used
     it, including 031's;
   - leave `fixed` as is and give it its own reported count (analogous to
     `orphans`) of tokens dropped, so the behavior is visible without
     changing it.
3. **Give `sentence` the same interior-group protection its trailing-chunk
   merge already has, or explain why the asymmetry is correct.** If a
   too-small chunk deserves merging at the end of a document, say why one
   in the middle of a document does not — or extend the merge to every
   undersized group, and remeasure what that does to the 7,333 orphan
   count.
4. **Re-measure orphan counts (and anything downstream of them) on the
   same `sec-filings-10k` 10% subsample task 031 used**, under whatever
   the developer rules on for items 2 and 3, and report the before/after
   — this is what task 052 named as the prerequisite for eventually
   quantifying self-retrieval's orphan exposure, not something this task
   itself needs to resolve.

## Acceptance

- Each strategy's floor-handling Param note states its own behavior *and*
  names that the others differ, cross-referenced rather than siloed.
- A ruling exists (from the developer, brought to them per item 2) on
  whether `fixed`'s silent tail-drop stays, is counted and reported, or is
  changed to merge — and the code matches whichever is chosen.
- `sentence`'s asymmetry (protects only the trailing chunk) is either
  extended to interior short groups or explicitly justified in the
  module's own documentation.
- Orphan counts (and any measure that moved) re-measured on the same
  10% subsample and compared against task 031's published numbers, with
  the delta reported plainly.
- Full suite green, guard clean, identifier scan runs rather than skips.

## Do not

- Change what "size", "max_size" or "overlap" mean for any strategy —
  this is scoped to the floor/minimum parameters only.
- Re-run the full-corpus 3-strategy comparison. The 10% subsample is
  sufficient to measure what this task changes; a full-scale re-run is a
  separate cost decision.
- Silently pick one of item 2's three options without bringing it to the
  developer first — a strategy's data-loss behavior is exactly the kind
  of thing this project does not decide unilaterally partway through a
  task.
