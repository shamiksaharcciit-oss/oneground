# Task 052 — What the 10% comparison does and does not establish

## Setup
New branch from `main`: `git checkout -b task-052 main`. Commit `052:` and
push after every commit. No pod — this is written from `tasks/031-
chunking-stage.report.md`'s own measurements and, where a specific number
is missing, a cheap local recomputation on the same subsample already on
disk; it is not a re-run of the pod build and not a full-corpus run.
**Bring the statement to the developer before it is written up anywhere
public** — `docs/CHUNKING.md` or wherever it lands is a second step, after
the ruling.

## Why

Task 031's headline finding — `structure` wins boundary alignment by
**241×** and loses `self_recall@5` — is, in the developer's own words,
**"this project's best finding, and a reader will ask about the subsample
first."** The comparison it comes from ran on a declared 10% subsample
(1,000 of 10,000 filings, seed 20260921), for a stated, honest reason:
three strategies over the full corpus is ~9–10 hours and ~$7 of embedding,
recorded so nobody repeats the measurement. That scope cut was disclosed,
not silent (`tasks/031-chunking-stage.report.md`, the `population_note`
in the requirements file it ran from).

031's own report separately named three things it left unresolved, in
"Observed, not done," without connecting them to the subsample question:

- `sentence` and `structure` produce **~7,400 orphan chunks each** (under
  the 64-token floor) against `fixed`'s **60** — `fixed` enforces a hard
  `min_final` merge the other two strategies do not, so the three are not
  chunked to the same floor.
- `structure` leaves **75 spans with no containing chunk**, against
  `fixed`'s 8 and `sentence`'s 0 — Items longer than `max_size`, whose
  split pieces each cut the span. `span_survival` is computed over exactly
  this population.
- The near-duplicate measure took **257–300 s per strategy on 158k–186k
  chunk texts** at 10% of the corpus; "at full corpus it would dominate
  path A."

**These are one task, not three, because all three are really one
question asked three ways: does the published comparison's conclusion —
not just its numbers — hold at full scale, and hold across a fair
chunking-parameter choice?** A fix to any one of them, taken alone, invites
re-running the pod to get a fresher wrong impression of the other two.
Answering the question once, honestly, for all three, is cheaper and is
the actual thing a reader needs before citing the 241× result.

## Do

**Produce one statement: what the 10% comparison establishes, and what it
does not, with each of the three items named as a reason wherever it
bears on the answer. Not fixes. Not a re-run.**

For the five path-A measures, both path-B columns, and the 241×/
`self_recall` disagreement specifically, work out and say, for each:

1. **Does the orphan-chunk floor difference bias this measure, and in
   which direction?** `sentence`/`structure` carrying ~7,400 tiny
   fragments each where `fixed` carries 60 is a real difference in what is
   being measured, not merely in scale. Say which measures a floor-aware
   re-chunk of `sentence`/`structure` could plausibly move, and whether
   moving them could plausibly flip a comparison (structure vs fixed, or
   structure vs sentence) rather than only its margin. Where you cannot
   tell without actually re-chunking, say couldn't-check rather than
   assume the floor difference is cosmetic — it may not be.
2. **Does the 75-span gap change what `span_survival` measured for
   `structure`?** The 241× alignment finding and the span-survival numbers
   (0.5551 / 0.5607 / **0.6386**) come from the same measurement family.
   Say whether the 75 uncontained spans were excluded from, or scored
   against, `structure`'s survival denominator, and whether counting them
   the other way would change the 2.6×/241× table's story or only its
   decimals.
3. **Does the subsample itself, independent of the above two, threaten
   the 241× finding or only its exact value?** A boundary-alignment ratio
   this large is unlikely to be a subsample artifact — say so if the
   measurement's own definition supports that, rather than asserting it.
   Where the near-duplicate rate specifically is concerned, say plainly
   that this measure's own cost is what makes a full-corpus number
   expensive to get, and whether the 10%-measured rate (0.0152/0.0584/
   0.0633, with `fixed`'s negative excess explained in the report) is the
   kind of statistic that a 10× larger sample would be expected to move
   the *conclusion* on, or just tighten.
4. **State the corpus-wide cost of actually answering any part of this
   at full scale**, reusing 031's own figures rather than re-deriving
   them (9–10 h / ~$7 for the embedding-bound comparison; the near-dup
   measure's own share of that, extrapolated from 257–300 s at 10%).

## Acceptance

- One written statement, not three patches and not a code change to
  `oneground/chunk/`.
- Every one of the three named items is addressed by name, with a
  direction (biases toward X, or does not, or couldn't-check) for each
  measure it plausibly touches — not a blanket "this might all be
  slightly off."
- The 241× finding and the A/B disagreement are explicitly addressed:
  does the statement leave them standing, standing with a caveat, or
  genuinely in question — said plainly, not left for the reader to infer
  from the surrounding prose.
- Brought to the developer before it is written into `docs/CHUNKING.md`
  or anywhere else a reader would find it as settled.

## Do not

- Re-run the pod, or any part of the 3-strategy comparison, at full
  corpus scale or at a different subsample size. That is a cost decision
  for the developer, not this task's to make by doing it.
- Change `oneground/chunk/strategies.py`'s floor handling, `structure`'s
  span-matching, or the near-duplicate measure's implementation. The
  deliverable is an assessment of what is already measured, not a repair.
- Present the statement as though it were already part of `docs/
  CHUNKING.md` before the developer has ruled on it.
