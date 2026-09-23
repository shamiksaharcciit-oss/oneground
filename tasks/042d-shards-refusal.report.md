# Report: 042d-shards-refusal

## Repo state expected vs found

Expected, and found:

- `hash_sharded.build` accepting `shards > len(vectors)`. Found.
- 042b's precedent — `semantic_sharded` refusing `centroids > len(vectors)`
  with `indexes.IndexTooSmall`, raised before the `context` shortcut. Found,
  and copied rather than re-invented.
- 042c's fan-out fix already landed. Found.
- A finding test written to fail when this lands. Found, and **deleted**:
  `test_hash_sharded_still_accepts_more_shards_than_vectors_task_042`.

**One thing not expected, and it forced a second edit.** 042c's own test
(`test_hash_sharded_fanout_follows_the_build_not_the_request_synthetic`) built
its scenario with `shards = len(x) + 1` — a configuration this task now
refuses. Its subject is still real: a hash partition leaves shards empty by
collision well before it runs out of vectors. So the test asks for
`len(x)` shards instead, which is legal and still produces empty shards. **The
property under test and 042c's fix are unchanged**; only the input is.

Worth recording as a pattern rather than a nuisance: **a test that
demonstrates a fix by constructing the defective case is coupled to that case
remaining constructible.** 042c demonstrated its fix at the boundary 042d then
closed.

## Checked before building

No published value moves and none can:

- No published fixture row carries a shard count at all.
- The largest `shards` in any tracked requirements file is **5**, against a
  20,000-vector sample. Every fixture grid uses **3** against 150,000.

**The refusal is unreachable from anything committed.**
(`tasks/scratch/042d-precheck.py`.)

## What was done

`hash_sharded.build` raises `indexes.IndexTooSmall` — a `ParameterError` —
when `shards > len(vectors)`, naming both numbers and what to lower, **before
any work**: before the timer, before `resolve_deterministic`, before the
context shortcut. A configuration incoherent on its face costs nothing to
reject, and the same rule cannot then be enforced from one caller and skipped
from another.

`ParameterError` specifically, for the reason 042b used it: `simulate` catches
it to drop one row and report the drop, and anything else ends the run.

## Measurements

The defect, before:

```
config accepted:  hash_sharded[M=16,efSearch=64,shards=1501]   (1,500 vectors)
build succeeded.   footprint.shards = 960      label says 1501
```

After:

```
IndexTooSmall: hash_sharded: shards=1501 over 1500 vector(s); a partition
cannot have more shards than there are vectors to put in them, and the empty
ones are skipped -- so this would build fewer shards than its own label
names. Lower shards to at most 1500.
```

### The conformance suite, all three families

```
family conformance: 3 family(ies), 10 checks each
  hash_sharded         9 passes, 0 fails, 1 couldn't-check
  semantic_sharded     9 passes, 0 fails, 1 couldn't-check
  single_node_hnsw     9 passes, 0 fails, 1 couldn't-check
total: 27 passes, 0 FAILS, 3 couldn't-check
```

**The first time every shipped family has passed every decidable check.** The
three couldn't-checks are the same one — the cross-environment half of the
state contract, which one machine cannot answer.

Worth stating plainly: the suite found two defects on the day it was written,
and both are now closed by the tasks it caused. That is the argument for the
suite, and it is now a measurement rather than a claim.

## Verification

| check | result |
|---|---|
| `shards > len(vectors)` raises `ParameterError`, naming both numbers | **PASS** |
| Raised before any work | **PASS** — tested with a `context` supplied, mirroring 042b |
| Both partitioning families refuse the same shape | **PASS** — one test covering both, since neither introduced an idea |
| The finding test deleted, not skipped or amended | **PASS** — replaced by a refusal test |
| `hash_sharded` passes every conformance check | **PASS** |
| No published value moved | **PASS** — pre-checked, and nothing under `fixtures/` or `site/` changed |
| Models tests | **PASS** — 164 |
| Full suite | *(below)* |

## Observed, not done

- **042c's test was coupled to the defect being constructible.** Fixed by
  changing its input, not its assertion. A test that demonstrates a fix by
  building the broken case will break when the broken case is forbidden, and
  that is worth knowing before the next such pair.
- **The brief for this task did not exist.** It was ruled in conversation and
  never written up, which is why 042's report carried it as an open decision
  longer than it needed to. The brief is now written, after the fact and
  marked as such.

## Repo now contains

New:

- `tasks/042d-shards-refusal.md` — the brief, written after the ruling
- `tasks/042d-shards-refusal.report.md` — this file

Changed:

- `oneground/models/hash_sharded/model.py` — the refusal
- `oneground/models/test_family_conformance.py` — finding test deleted, three
  refusal tests added
- `oneground/models/test_conformance.py` — 042c's test given a legal input

Scratch: `tasks/scratch/042d-precheck.py`.

## Blocked on developer

Nothing.
