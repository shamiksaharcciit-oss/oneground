# Report: 052-what-the-subsample-comparison-establishes

## Repo state expected vs found

Expected `main` at `0515b6d` (task 051's merge) with the accepted brief
and nothing built against it. Found exactly that.

## What was done

One statement, added to `docs/CHUNKING.md` §7 as "What the 10% comparison
establishes, and what it does not (task 052)" — no code change, no
re-measurement, no re-run of any part of the 3-strategy comparison, per
the brief.

Read `oneground/chunk/measures.py`, `selfretrieval.py`, `strategies.py` in
full rather than reason about the numbers from the report's prose alone,
because "does X bias measure Y" needs the actual denominator, not a guess
at it.

**The three named items, addressed by name, each with a direction:**

- **The orphan-chunk floor** (`sentence`/`structure` ≈7,400 orphans vs
  `fixed`'s 60). Traced to three different mechanisms behind two
  differently-named parameters (`fixed.min_final` silently drops trailing
  content rather than shipping it; `sentence.min_final` merges only the
  final chunk per document; `structure.min_size` merges structural units
  before chunking, a different stage entirely) — not a quality signal
  about how carefully each strategy handles small fragments. Per measure:
  `length_distribution` shows it directly (not biased, the thing being
  measured); `boundary_alignment`'s published `% of ceiling` figure is
  immune to it **by construction** — `alignment_rate` and
  `alignment_ceiling` share the same `starts` denominator, which cancels
  algebraically, and the raw 241× ratio is, if anything, understated by
  `structure`'s larger chunk count, not inflated; `self_recall`/
  `containing_hit` carry the real, unquantified exposure — the project's
  own `BIAS_CAPTION` already names orphan count as something a reader must
  check beside self-retrieval, and the `fragmented` flag exists for
  exactly this bias, but keys on `p50` (391/389, unremarkable) and cannot
  see a long tail of small chunks sitting below the median.
- **`structure`'s 75 unmatched spans.** Read `span_survival` line by line:
  it does not exclude them. Every span is counted in `total`; a span with
  no containing chunk scores `split`, already inside the reported 0.6386.
  Not a methodological gap in the number — a known structural ceiling
  (an Item longer than `max_size` cannot be survived by any chunk that
  respects `max_size`, regardless of cutting quality) sitting on top of
  whatever the real cutting quality contributes.
- **The near-duplicate measure's cost** (257–300 s/strategy at 10%).
  Labelled `couldnt_check` at full scale, in the project's own vocabulary,
  rather than assessed as probably fine — nobody has run it, there is no
  specific reason to expect the rate to move qualitatively at ten times
  the sample (a large-N proportion estimate), and that is not the same
  claim as asserting it would not.

**The 241× finding and the A/B disagreement are stated as standing** —
none of the three items changes either direction; the orphan floor is the
one place a real margin (not direction) is open, on `self_recall@5`/
`containing_hit@5` specifically.

**A fourth thing, found while doing this and not asked for: the floor
mechanism itself is a defect, not a caveat, and does not belong inside
this statement.** Scoped as its own task, `tasks/054-one-min-size-three-
meanings.md` — three genuinely different behaviors (one of them silent
token loss at the end of a document under `fixed`) behind two
differently-named parameters, none of which states that the others mean
something different by the same role. `docs/CHUNKING.md`'s new section
names the task rather than re-deriving the mechanism, per the ruling that
it should not stay inside this statement.

## Measurements

None taken; all figures cited are task 031's own, read from its report
and cross-checked against the code that produced them (the `% of ceiling`
algebra, and `span_survival`'s per-span accounting) rather than re-run.

## Verification

No test suite change — this task added prose to `docs/CHUNKING.md` and a
new task brief; nothing in `oneground/` changed. Full suite, guard,
identifier scan and `site/teaser/` reported at the merge, below, as a
sanity check that nothing was inadvertently touched.

## Observed, not done

Task 054's own scope (the floor-parameter defect) is deliberately not
touched here — brief written, not executed, per the ruling that it is
its own task.

Self-retrieval's orphan exposure stays genuinely unquantified. Closing it
needs the three strategies re-chunked under a matched floor, which needs
task 054's ruling first (on whether `fixed`'s tail-drop stays, is counted,
or changes) — stated as the reason it is open rather than answered, both
in `docs/CHUNKING.md` and here.

## Repo now contains

Changed:

- `docs/CHUNKING.md` — new §7 subsection, "What the 10% comparison
  establishes, and what it does not (task 052)"

New:

- `tasks/052-what-the-subsample-comparison-establishes.md` — the brief
- `tasks/052-what-the-subsample-comparison-establishes.report.md` — this
  file
- `tasks/054-one-min-size-three-meanings.md` — the follow-up brief this
  task's own reading produced, not executed

## Blocked on developer

Nothing. Committing, pushing to `task-052`, and merging into `main` once
its checks are green, per standing instruction. Task 054 is scoped and
waiting; task 053 is next, per instruction.
