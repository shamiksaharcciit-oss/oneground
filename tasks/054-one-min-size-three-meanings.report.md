# Report: 054-one-min-size-three-meanings

## Repo state expected vs found

Expected `main` at `4876b04` (task 053's merge, with the two report
refinements) and the three floor mechanisms exactly as `tasks/054-one-min-
size-three-meanings.md` described them: `fixed` dropping a short trailing
window, `sentence` merging only a document's final chunk, `structure`
merging short *units* before chunking on an unrelated parameter name. Found
exactly that; branch `task-054` created from `main` at that commit.

## What was done

**One floor semantics, stated once, applied by all three.** A chunk shorter
than the floor is merged into the adjacent chunk of the same document — the
previous one where one exists, the next one only when the short chunk is a
document's first. Implemented as a single shared function,
`_merge_undersized()`, called as the last step of `_fixed()`, `_sentence()`
and `_structure()` alike, replacing `fixed`'s drop-the-tail behavior,
`sentence`'s trailing-only merge, and running as an added safety net after
`structure`'s existing pre-chunking unit merge.

**`fixed`'s silent drop is gone**, not kept as a declared exception — the
brief named it indefensible on its own merits, and nothing about `fixed`
made merging harder than it was for `sentence`, so there was no genuine
exception to declare.

**One declared exception, for `structure` only.** `structure` still runs
its pre-chunking unit merge *and* the shared post-hoc rule, for a stated
structural reason: a unit that `max_size` forced `structure` to split into
pieces produces pieces that can legitimately be short, and merging them
back together would silently undo the split the size cap exists to
enforce. `_merge_undersized()` takes an optional `mergeable` flag per chunk;
`structure` marks a split piece `False` — eligible neither to absorb a
neighbour nor to be absorbed by one — so the shared rule cannot reverse a
`max_size` decision it does not know was made. This is the one place the
three strategies still differ, and it is now named at the point a reader
meets it: in `structure.min_size`'s own `Param` note, in the module
docstring, and in `_merge_undersized`'s own docstring.

**Param notes updated**, all three cross-referencing the shared rule and,
for `structure`, the declared exception — a reader of one note no longer
has to separately read three functions to learn the other two differ.

**Two real bugs found while implementing this, both caught by tests rather
than assumed away:**

1. `_merge_undersized`'s first version compared a chunk's *character*
   length against `min_final`, which every strategy declares in *tokens* —
   reproducing, in the new shared code, the exact mistake `structure.
   min_size`'s own pre-existing comment already warns about elsewhere in
   this file. Caught by `test_fixed_merges_a_trailing_fragment_rather_
   than_dropping_it` failing on a case where the fix should have merged
   and did not. Fixed by threading a `tokens_in(start, end)` callable
   through `_merge_undersized` and every call site, replacing the
   character check.
2. Applying the shared rule to `structure`'s full output list without the
   `mergeable` guard wrongly re-merged a unit's `max_size`-forced split
   pieces back together, undoing the split. Caught by the existing test
   `test_a_merged_unit_over_max_size_is_still_split` failing. Fixed by
   adding the `mergeable` parameter described above.

Both were hand-verified as real mutants: each was reproduced by
temporarily reintroducing the buggy comparison, confirming the specific
test failed for the reason expected, then reverting.

## Measurements

**Path A, re-measured on the declared 10% subsample** (1,000 of 10,000
`sec-filings-10k` documents, ordered by accession, `seed 20260921` — the
same subsample `requirements.chunking-sec-filings.yaml` and task 031 used),
old code (`git show main:oneground/chunk/strategies.py`, `main@4876b04`)
against the current tree, both run against identical documents and token
offsets. No pod, no embeddings: path A does not read chunk vectors.
Method: `tasks/scratch/054-remeasure.py` (gitignored, per project
convention for scratch diagnostics — regenerate the `old` snapshot with the
`git show` command the script's docstring gives before running it).

| strategy  | code | chunks  | orphans (< 64 whitespace tok) | orphan rate | boundary_alignment |
|-----------|------|--------:|-------------------------------:|------------:|--------------------:|
| fixed     | old  | 158,341 | 60                              | 0.0379%     | 0.00030946           |
| fixed     | new  | 158,341 | 60                              | 0.0379%     | 0.00030946           |
| sentence  | old  | 185,771 | 7,333                           | 3.9473%     | 0.00173332           |
| sentence  | new  | 181,188 | 2,750                           | 1.5178%     | 0.00162262           |
| structure | old  | 182,361 | 7,566                           | 4.1489%     | 0.07230164           |
| structure | new  | 182,361 | 7,566                           | 4.1489%     | 0.07230164           |

**`fixed` and `structure` are bit-for-bit identical, old code to new.**
`fixed`'s trailing-window drop never fired on this subsample — no
document's final window fell under `min_final` (32 tokens) in the first
place, so there was nothing for the old bug to drop here — which is also
why `fixed`'s 60 orphans (a *different*, coarser floor: 64 whitespace
tokens, not the 32-model-token `min_final` the drop bug used) match task
031's published number exactly and are unmoved by this fix. `structure`'s
7,566 remaining orphans are, by the declared exception above, exactly the
population the new code deliberately leaves untouched: `max_size`-forced
split pieces. Its post-hoc merge pass ran and found nothing eligible to
merge, which is the exception working as declared, not the fix failing to
apply.

**`sentence` is the one strategy path A's numbers move for.** Its old
trailing-only merge fixed at most one chunk per document (≤ 1,000 merges
possible across the subsample); the new rule fixes every undersized chunk
wherever `sentence`'s grouping produced one. Orphans fall from 7,333 to
2,750 (−62.5%), chunk count from 185,771 to 181,188 (−4,583, exactly the
orphan reduction — each merge both removes one chunk and resolves the
orphan that triggered it). `sentence`'s near-duplicate rate also drops,
0.0584 → 0.0449, consistent with fewer, less-fragmented chunks.
`boundary_alignment` moves by a negligible amount, 0.0017333 → 0.0016226
(sentence cuts on sentence boundaries, not structural ones, so this number
was never large for it either way).

**The 241× finding does not move, because its two inputs do not move.**
`structure`'s and `fixed`'s `boundary_alignment` values are unchanged to
the last published digit (0.07230164 and 0.00030946), because both
strategies' chunk sets are unchanged to the last chunk. The precise ratio
at full precision is 233.7×, not exactly 241× — that headline number was
itself a division of the two *rounded, 4-significant-digit* published
values (0.0723 / 0.0003 = 241 exactly), a rounding artifact of the
original report rather than anything this fix touches; the underlying,
unrounded ratio was already 233.7× before this task and is 233.7× after
it. Either way: **the 241×-class finding is untouched by the floor
unification.** It was never built on the orphan-handling behavior this
task changed — `boundary_alignment` measures where a chunk's *start*
falls relative to a structural edge, and no merge this task performs moves
a chunk's start unless the *first* chunk of a document was itself
undersized, which did not occur for `fixed` or `structure` on this
subsample.

**The A/B disagreement (`self_recall@5`) was not re-measured.** Path B
requires re-embedding the new chunk sets (`BAAI/bge-base-en-v1.5`), which
task 031's original run did on a paid RunPod GPU session (RTX PRO 4500,
~$0.80, 43.9 minutes) — real spending CLAUDE.md's "developer runs"
convention reserves for explicit authorization, which this task has not
received specifically. Since `sentence`'s chunk set is the only one that
changed at all, and `fixed`/`structure` — the two strategies the published
A/B disagreement is about — produced bit-identical chunks, **there is
a strong prior that the disagreement does not move either**, but that is
an inference from path A, not a path B measurement, and this report does
not present it as one.

## Verification

`oneground/chunk/test_strategies.py`: 92 of 92 passed, including the two
mutants above (hand-verified by temporarily reintroducing each bug) and
three new/rewritten tests (`test_fixed_merges_a_trailing_fragment_rather_
than_dropping_it`, `test_min_final_is_measured_in_tokens_not_characters`,
the strengthened `test_every_character_is_in_at_least_one_chunk`).

Full suite: **1,807 passed, 40 skipped**, run twice on this tree (once
after the code fix, once after the test additions) — both green, no
regressions elsewhere from a shared function three strategies now call.

`oneground/test_environment.py` (pinned-environment guard): passed.

`oneground.environment.identifier_findings()`: clean — no machine-local
paths or identifiers in any changed file (the report above uses `~/
oneground-assets/...`, the generic form the project already uses
elsewhere, not this machine's actual path).

`git diff origin/main..HEAD --stat -- site/teaser/`: empty.

## Observed, not done

**Path B (`self_recall@5`, `containing_hit@5`) was not re-measured**, per
the money-spending caution above. If the developer authorizes a pod
session at the declared 10% subsample scale (the same scope task 031
used, not the full corpus — the brief's own "Do not" already excludes a
full-scale re-run), it would need: re-chunking all three strategies under
the new code (the six-way local comparison above already proves `fixed`
and `structure`'s chunks are unchanged, so only `sentence`'s new chunk set
actually needs a fresh embedding pass; `fixed` and `structure` could reuse
task 031's original vectors byte-for-byte if they are still held, avoiding
two-thirds of the embedding cost) and running `selfretrieval.self_
retrieval()` against the same anchor/query set task 031 drew (`seed
20260922`, `k=5`, the same three perturbations).

**The precise 241× vs 233.7× rounding gap** is noted above but not
corrected anywhere published — `docs/CHUNKING.md`'s task-052 addendum and
task 031's own report both state "241×" from the rounded figures. Whether
to correct the published number to the unrounded ratio, or to leave the
established headline as is and note the precision separately, is a
documentation call this task's scope (the floor defect) does not cover.

## Repo now contains

Changed:

- `oneground/chunk/strategies.py` — `_merge_undersized()` (the shared
  floor rule) and `_merge_label()`; `_windows()` no longer drops a short
  trailing window; `_fixed()`, `_sentence()`, `_structure()` all end by
  calling the shared rule, `_structure()` additionally passing the
  `mergeable` flag for its declared exception; three `Param` notes
  (`fixed.min_final`, `sentence.min_final`, `structure.min_size`) updated
  to state the shared semantics and the one declared exception
- `oneground/chunk/test_strategies.py` — strengthened coverage assertion,
  one test renamed and rewritten, one new test for the token-vs-character
  bug, the split-piece mutant's docstring extended
- `tasks/054-one-min-size-three-meanings.md` — the brief itself, per the
  developer's two-constraint refinement

New:

- `tasks/054-one-min-size-three-meanings.report.md` — this file
- `tasks/scratch/054-remeasure.py` — the re-measurement script (gitignored,
  not part of this commit; kept locally as the reproducible method behind
  the Measurements section above)

## Blocked on developer

**Path B re-measurement needs a pod session** (~$0.80, well under an hour
at task 031's rate, likely less since two of three strategies' chunks did
not change and could reuse existing vectors). Authorize it, or accept path
A's finding — the 241× result is untouched, `sentence`'s orphan population
is cut by 62.5%, and the A/B disagreement has a strong but unconfirmed
prior of also being untouched — as sufficient for this task's close.

Committing, pushing to `task-054`, and merging into `main` once its checks
are green, per standing instruction.
