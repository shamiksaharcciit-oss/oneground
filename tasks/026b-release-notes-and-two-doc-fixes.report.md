# Report: 026b-release-notes-and-two-doc-fixes

## Repo state expected vs found

`main` at `2ad3433` (026), clean apart from `tasks/020-simulator-state.md`:
found. `v0.1.0` on `872e7a6`, not moved.

## What was done

**1. `RELEASE_NOTES.md`, under *What is new since `0.1.0-preview`*,** after
*A checked claim invariant*. A new entry, **Configurations are validated
against each family's declared parameters**, says:
- every family declares the parameters it reads, with types and valid ranges;
- a requirements file naming an undeclared key is refused, with the declared
  list;
- a key the family would ignore (a constant it fixes, or a grid entry for a
  parameter it does not sweep) is refused rather than accepted;
- before this, such a key was accepted, put in the label and silently
  ignored, while the run reported numbers;
- **a file that used to run with a misspelled key will now stop, and that is
  deliberate;**
- no working configuration changes: a silently ignored key was never applied,
  so every number measured without it is the number measured with it.

**2. `simulate_info.json`'s `shard_depth_note`** (written by
`oneground/simulate/__init__.py`). It said the depth was "used by every sharded
family in this run", which was never true of `hash_sharded`. It now says:
- the depth is given to `semantic_sharded`, as max(30, largest k reported);
- `hash_sharded` does not read the setting, and computes max(30, k) itself on
  every search, the same rule;
- `single_node_hnsw` has no shards;
- the `semantic_sharded` default is 30, what published fixture values were
  measured with.

Only the sentence was wrong. For the ks a run reports, both sharded families
used the same depth.

**3. `docs/MODELS.md`, *Adding a family*.** A new step 2 says a family must
declare its parameters with `declare_parameters(NAME, (Param(...), ...))`:
every key it reads, with type, validity bounds, whether it is swept, and its
role (`parameter`, `run`, `build` or `constant`). It says an undeclared key is
refused and cannot be read, so a family without a table cannot be built, and
states the rule the table enforces: a key is either read, or refused, never
accepted and ignored. The tests step now names `models/test_parameters.py` and
what it requires. The later steps are renumbered.

## Measurements

- Full suite: **871 passed, 0 failed** (4 m 24 s).
- `tasks/scratch/018-docs-numbers.py`: ALL CHECKS PASSED.
- Identifier scan with this report staged: 0 findings. Leak scan: the one
  known synthetic `DESKTOP-` probe.

## Verification

Each sentence added was checked against the code it describes, not written
from memory:
- **"a family without a table cannot be built":** `Config.__post_init__` looks
  up the family's table, which raises when there is none;
- **"the same rule":** `hash_sharded.search` uses `max(SHARD_DEPTH, k)` with
  the run's largest k, the value `shard_depth_for` gives `semantic_sharded`;
- **"no working configuration changes":** labels are unchanged, and the
  families that ignored `shard_depth` never read it.

**One output change 026 made that the release notes do not describe,**
recorded here: before 026, `simulate` added `shard_depth` to every
configuration before writing the row, so `simulate.json` rows for
`single_node_hnsw` and `hash_sharded` listed `shard_depth` in their `params`
(confirmed in `872e7a6`'s `simulate/__init__.py`, lines 252 and 265). They no
longer do. No number or label changed.

## Observed, not done (recorded for after the release)

- **The `policies/` naming clash.** `policies/README.md` and `CLAUDE.md` define
  policies as "small policy functions" producing "a concrete recommendation";
  in `docs/PROPOSALS.md` a policy is never code and a card never recommends.
- **Cross-parameter checks.** `probe` greater than `centroids`, and `shards`
  greater than the corpus, are not refused.
- **The charter's Phase 5 lists adversarial review as part of the loop,** while
  `docs/PROPOSALS.md` §5 leaves whether to build it unsettled.

## Repo now contains

    RELEASE_NOTES.md                                       the validation entry
    oneground/simulate/__init__.py                         the shard_depth note
    docs/MODELS.md                                         declare your parameters
    tasks/026b-release-notes-and-two-doc-fixes.report.md   this report

## Blocked on developer

Retag `v0.1.0` at this commit (subject `task 026b:`) and rebuild.
