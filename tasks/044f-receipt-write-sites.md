# Task 044f — every module that writes a receipt routes its paths through
`receipts.public_path`

**Written up from the developer's ruling on the 044e write-site check**, in
the form 042d should have had. Branch `task-044f` from `main`.

## Why

The rule has cost three times and has been stated three times. A rule stated
three times and enforced never is a habit.

1. **Task 016** — two absolute developer paths published in
   `tasks/016-decision-log.txt`. Fixed by building the tracked-tree scan.
2. **Tasks 041 → 043** — `report.json` recording `price_table.path` as the
   absolute path of the checkout. Fixed by `receipts.public_path`, applied at
   the write site, after sanitising at publish time had forced the same repair
   at three boundaries in one task.
3. **Task 044c** — a scratch script writing the asset store's absolute path
   into output that was then committed. Written by the author of 043's report.

## The scoping the 044e check changed

The obvious check is *every module writing a **tracked** file*. **Tracked is
the wrong predicate**, and 044e measured why: three `runs/*/report.json` carry
an absolute path, dated ten days before 043, and `runs/` is gitignored so
`test_no_tracked_file_carries_a_machine_identifier` can never see them — while
`corpora/export_teaser_data.py`, a publishing path, reads exactly that
directory.

So the blind spot is not that guard's implementation but **its subject**: it
asks what git tracks, and the exposure is what a publishing path reads.

    tracked   a file git happens to store
    receipt   a file this project writes as a record of a measurement

Scope the check to **every module that writes a receipt, tracked or not**, and
say in its own docstring why "tracked" was the wrong word.

## Do

### 1. Build it, under two constraints

- **Select on provenance, not locality.** The write and the sanitiser will not
  share a module — `report/__init__.py` writes the field and
  `receipts.public_path` sanitises it. A check requiring them to be adjacent
  is 044d's defect repeated.
- **Run it against a commit predating each of the three known instances and
  require it to name them.** A check that cannot rediscover its motivating
  cases is not evidence. **If it sees two of three, ship it saying so rather
  than weakening it.**

### 2. Keep the identifier scan

Two checks that see different things are not redundant, and this pair is the
proof: one sees the tracked tree, one sees the write site, and the gap between
them held a ten-day-old machine identifier on a publishing path. Deleting
either restores a blind spot. Do not fold one into the other.

### 3. Report what it finds, fix what it covers

Every finding is a finding about a write site, never a reason to soften the
check.

## What this may not do

- **Widen the guard until it passes.** A carve-out at first contact with real
  code is how a guard becomes decorative.
- **Delete or weaken `test_no_tracked_file_carries_a_machine_identifier`.**
- **Fold in the teaser shim.** That is its own task on the publishing path.

## Acceptance

- The guard exists, is scoped to receipt write sites rather than to tracked
  files, and says in its docstring why tracked was the wrong word.
- It is run against pre-fix source for each known instance, and the report
  states how many of the three it names — including if that is fewer than
  three, with what the missing coverage would require.
- Its own findings on the current tree are reported and fixed or declared,
  each declaration stating what the **code** guarantees rather than what the
  field is for.
- Both checks present and passing. Full suite green.
