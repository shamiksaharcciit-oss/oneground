# Task 042d — hash_sharded refuses more shards than vectors

## Setup
Branch `task-042d` from `main`. Commit `task 042d:` and push. No pod.

*Written up after the fact: this was ruled in conversation and never given a
brief, which is why 042's report carried it as an open decision for longer
than it needed to. The omission is recorded rather than tidied away.*

## Why

Task 042's conformance suite found `hash_sharded` building a configuration
that asks for more shards than there are vectors. At 1,500 vectors and
`shards=1501`:

```
config accepted:  hash_sharded[M=16,efSearch=64,shards=1501]
build succeeded.
  footprint.shards  =  960        (the artifact)
  footprint.fanout  = 1501.0      (what the config asked for)
  label says        = 1501
```

042's report recorded this as **two** decisions, not one. **042c fixed the
second** — `fanout` now reports the shards that were built. This is the first:
the configuration should never have built at all.

A partition that labels itself `shards=1501` and holds 960 is **claiming
something that cannot exist**. Empty shards are skipped, so the label and the
artifact disagree by construction, and every row carrying that label describes
an architecture nobody built.

**The precedent is this project's own.** Task 042b gave `semantic_sharded` a
refusal for `centroids > len(vectors)`, using `indexes.IndexTooSmall` and the
message shape `indexes.build` already used for `nlist > n`. This makes the two
partitioning families consistent; it introduces no new idea.

## Do

1. **Refuse in `hash_sharded.build`** when `shards > len(vectors)`, with a
   `ParameterError` naming **both numbers** and what to do. `ParameterError`
   specifically: `simulate` catches it to drop one row and report the drop,
   and anything else ends the run.
2. **Raise it before any work.** 042b's refusal sits before the `context`
   shortcut for a reason — a configuration incoherent on its face should cost
   nothing to reject, and the same rule should not be enforced from one caller
   and skipped from another.
3. **Delete the finding test.**
   `test_hash_sharded_still_accepts_more_shards_than_vectors_task_042` in
   `oneground/models/test_family_conformance.py` was written to fail when this
   lands. Deleting it is the intended outcome, not collateral — leaving it red
   would be leaving a test that asserts a defect.
   Replace it with a test of the refusal, in the shape of 042b's.
4. **Confirm the conformance suite goes green** for `hash_sharded` on
   *refusals, not crashes* — the check that found this.

## Checked before building, as 042c was

No published value moves and none can. The largest `shards` in any tracked
requirements file is **5**, against a 20,000-vector sample; every fixture grid
uses **3** against 150,000. No published fixture row carries a shard count at
all. **The refusal is unreachable from anything committed**
(`tasks/scratch/042d-precheck.py`).

## Acceptance

- `shards > len(vectors)` raises `ParameterError`, naming both numbers.
- It is raised before the build does any work.
- The finding test is **deleted**, not skipped or amended, and a refusal test
  replaces it.
- `oneground models conformance --family hash_sharded` shows no failure.
- No published value moved.
- Full suite green apart from the known stale-artifact failure recorded in
  `tasks/045-correction-the-remedy-test.md`.

## Do not

- Weaken the conformance check instead of fixing the family.
- Change `footprint.fanout`; that was 042c and is done.
- Leave the finding test failing.
