# Report: 042c — fanout reports what was built

## Repo state expected vs found

The brief was given inline: fix `fanout` to report the shards that were
built rather than the ones requested, check whether any published value
moves, and stop before changing one if it does.

Found as described. `main` at `e246180`, task 042's finding open in
`tasks/042-family-conformance.report.md` under "Observed, not done", and
`test_hash_sharded_accepts_more_shards_than_vectors_task_042` documenting it
as a live defect with the instruction *"when this is fixed, this test fails
and is deleted."*

One thing the brief did not say and the tree did: **`semantic_sharded` has
the same defect.** It is fixed here too, for the reason below.

## No published value moves

Checked before anything was changed, which was the gating instruction.

`fanout` appears in `fixtures/arxiv-150k/report/simulate.json` and
`report.json` — tracked receipts with MANIFEST digests. Every published row
already satisfies the new rule, so the fix is a no-op on all of them:

| published row | fanout | shards | after |
|---|---|---|---|
| `hash_sharded[M=32,efSearch=96,shards=3]` | 3.0 | 3 | 3.0 |
| `semantic_sharded[…]` × 6 | 1.0 / 2.0 | 256 | `min(probe, 256)` = probe |
| `single_node_hnsw[…]` | 1.0 | 1 | 1.0 |

`fanout` is also not one of the eight published values in
`fixtures/arxiv-150k.fixture.yaml` — those are the five characterization
measures plus `single_node_hnsw.recall_at_10`,
`semantic_sharded.recall_at_10` and `semantic_sharded.storage_amplification`
— and none of them is derived from it.

It **is** consumed downstream: `capacity.py:99,105` prices a query against it
and `verdict.py:1006` breaks ties on it. That is why the check mattered rather
than being a formality. Since no row's fan-out changes, nothing those compute
changes either.

## What was done

### `hash_sharded`: the fan-out is the built shard count

`build` skips a shard that came back empty, so a configuration asking for 4
can produce 3. `footprint` reported the request and the build in two fields of
one return value, and they contradicted each other — 042 measured a fan-out of
1501 over a 960-shard index.

`search` iterates `shards.items()`: every built shard, every query. So the
fan-out this family pays **is** the built shard count, and both fields now
come from one expression rather than from two places that happened to agree at
the shard counts anyone had tried.

### `semantic_sharded`: the same defect, capped at what exists

Not named in 042's finding, and present:

```python
for r in q_r[qi]:
    if r not in shards:        # a probed region with no shard
        continue
```

A query cannot touch a region that has no shard, however high `probe` is, so
`fanout` is now `min(probe, len(shards))`.

**`min`, and not the built count.** Below the cap the requested probe *is*
what a query pays. This is an upper bound on the fan-out rather than a
measurement of it: the exact per-query figure depends on which regions each
query probes, and `footprint(built)` is handed no queries to measure that
from. Said in the code rather than approximated silently.

### The rule, where contributed families meet it

`check_fanout_matches_the_build` in `oneground/models/conformance.py` — the
042 suite, now ten checks rather than nine. It fails a family whose fan-out
exceeds its shard count or falls below one, and it runs against every family
including one arriving through `--module`.

**Two mutants, in `test_family_conformance.py`, against the check's own
code** rather than a restatement of it — a rule and a mutant that share no
code can drift apart, and then the mutant proves the defect is reproducible
while proving nothing about the rule. One reports `shards + 1`, one reports
`0`, both must make the check fail, and the real family must pass the same
check on the same corpus so the failure is the mutation and not the fixture.

## Measurements

| | |
|---|---|
| conformance checks | 9 → **10** |
| full suite | **1395 passed, 2 skipped** |
| with the fix reverted | **2 failed**, 26 passed (module), and the targeted regression names the reverted line |
| published values moved | **0** |

Verified by reverting the source and running, not by reading it — task 041's
Finding 6b: a check that fires when something is wrong is only tested by
making it wrong.

## Verification

- The regression test constructs the case: 200 vectors, `shards: 201`, build
  skips empties, and `fanout == shards < 201`.
- `semantic_sharded` with `centroids: 4, probe: 64` reports `min(64, shards)`
  and the cap is asserted to have applied.
- The 10-check suite passes for all three shipped families and for the
  unregistered worked example.
- Both mutants fail the check; the clean family passes it.

**Couldn't-check:** whether the fan-out any *particular* query pays matches
the cap in `semantic_sharded`. It is an upper bound by construction, and
measuring the per-query figure would need `footprint` to be handed queries,
which is a protocol change rather than a fix.

## One correction I made to my own work

The check first returned `couldnt_check` when no configuration in a family's
grid produced an empty shard, reasoning that a family reporting the request
and one reporting the build would look identical there.

That was over-reach. The invariant the check asserts — a fan-out within the
shard count — **did** hold on every configuration, and downgrading a held
measurement because a *stronger* claim is unproven reports a gap where
evidence exists. That is couldn't-check used as a hedge, which is the misuse
the three outcomes exist to prevent. It passes, and its `meaning` states how
strong the evidence is: whether any configuration exercised a skipped shard,
and that the mutant is what requires the family to read the build.

## Observed, not done

- **`hash_sharded` still accepts `shards > len(vectors)`.** This was the other
  half of 042's two decisions and the brief did not authorise it. The finding
  test is rewritten rather than deleted: it now asserts the fan-out half as
  fixed and the refusal half as open, and says it fails and is deleted when
  the `ParameterError` lands.
- **`capacity.py:99` computes `fanout = float(cfg.get("probe", 1))`** from a
  configuration with no build in hand — the planning path, where the defect
  cannot be fixed the same way because nothing has been built to read. It is a
  prediction rather than a report, and whether it should be capped by a
  predicted shard count is a question for whoever owns capacity planning.
- **The faiss `WARNING clustering N points to M centroids` lines** during the
  conformance run are the synthetic corpus being smaller than faiss would
  like. Pre-existing, unrelated, and noisy enough to hide a real warning.

## Repo now contains

Changed: `oneground/models/hash_sharded/model.py`,
`oneground/models/semantic_sharded/model.py` (the two footprints),
`oneground/models/conformance.py` (the check and its registration),
`oneground/models/test_family_conformance.py` (two mutants; the 042 finding
test rewritten to its open half), `oneground/models/test_conformance.py` (two
family-specific regressions).

New: this report.

## Blocked on developer

None. One decision remains from 042 and is not this task's: the
`ParameterError` refusing `shards > len(vectors)`.
