# Report: 026-proposals-first-slice

## Repo state expected vs found

| expected | found |
|---|---|
| `main` with `docs/PROPOSALS.md` committed | `872e7a6 docs: the proposals position, before the code`, clean apart from `tasks/020-simulator-state.md` |
| the review's findings: silent unknown-parameter acceptance, scopes, no two-run rule | all three confirmed in the code before building |
| `v0.1.0` not moved by this task | not moved |

## What was done

Built against the three rulings and the wording fixes. No model, no scopes, no
card, and no command: nothing here translates a sentence, runs a proposal or
publishes anything.

### 1. Parameter tables, and a strict `get()` (the shipped defect)

`oneground/models/base.py` gains `Param` and `declare_parameters`. Every family
declares every key it reads, with a type, validity bounds, whether its
`configs()` sweeps it from a grid, and a role:

| role | meaning | may a policy change it |
|---|---|---|
| `parameter` | the architecture | yes, the only one |
| `run` | set per run by the simulator (`shard_depth`) | no |
| `build` | how the index is built (`deterministic`) | no |
| `constant` | fixed inside the family; refused in any config, with its value | no |

| family | parameter | run | build | constant |
|---|---|---|---|---|
| `single_node_hnsw` | M, efSearch (swept); efConstruction (pinned by include, not swept) | — | deterministic | — |
| `semantic_sharded` | centroids, epsilon, probe, M, efSearch (swept) | shard_depth | deterministic | efConstruction (200) |
| `hash_sharded` | shards, M, efSearch (swept) | — | deterministic | efConstruction (200), shard_depth (max(30, k), computed per search) |

Ranges are validity bounds, not recommendations: positive integers, epsilon at
least 0.

**What is refused, and where:**
- **At every `Config`'s construction,** through `make` or directly: any key the
  family does not declare; a constant; a wrong type; a value out of range.
  Every problem is named, with the declared set.
- **`Config.get(key)`:** an undeclared key, naming the declared ones.
- **`ConfigSpace.for_family`:** a grid key the family does not declare, a
  constant, or a declared key the family does not sweep. Before 026,
  `efConstruction: [400]` in a `single_node_hnsw` grid built every config at
  200 and said nothing.
- **`simulate`** turns these into its own `SimulateError`, before anything is
  measured.

**The defect, observed before the fix:** an include entry with `probez: 3` was
accepted and labelled `semantic_sharded[...,probe=3,probez=3]`. Now:

    semantic_sharded has no parameter 'probez'. semantic_sharded declares: M,
    centroids, deterministic, efConstruction, efSearch, epsilon, probe, shard_depth

**Two call sites in `simulate` changed because of it:**
- `_with_shard_depth` added `shard_depth` to **every** family's config.
  `hash_sharded` computes its own depth and `single_node_hnsw` has no shards,
  so both ignored it: the same accept-and-ignore defect, inside the simulator.
  It now adds the key only where the family `accepts` it (declared and not a
  constant). Labels are unchanged. The measured numbers cannot change either,
  since those families never read the key.
- `context_for` asked every config for `centroids` and relied on `None`. It now
  asks whether the family accepts `centroids` first.

`Config` gains `declares(key)` (declared at all, constants included) and
`accepts(key)` (a value may be set). The first run of the tests caught me
using `declares` where `accepts` was meant: `hash_sharded` declares
`shard_depth` as a constant, so the simulator added it and the strict check
refused it.

**`oneground/models/test_parameters.py`, the conformance test:**
- **At runtime,** every family builds, searches, ceilings and footprints a tiny
  synthetic corpus while every `get` is recorded. The keys read must equal
  exactly the declared non-constant keys. Nothing undeclared is read,
  nothing declared goes unread, and no constant is read.
- **Statically,** an AST scan of each family module, and of `base.py`'s shared
  helper, finds every `config.get("key")`; each must be declared. No family
  reads `.params` directly, which would bypass `get`.
- **Refusals:** undeclared key, direct construction, `get`, constants with
  their fixed values, a grid key that would be ignored, types and ranges, and
  `simulate`'s own error.
- **Shipped files:** every `requirements*.yaml` plans valid configs, and every
  fixture spec's reference parameters build as configs.

### 2. The policy schema and validator (`oneground/proposals/policy.py`)

    policy:
      family: semantic_sharded
      configuration: {centroids: 256, epsilon: 0.2, probe: 2, M: 32, efSearch: 96}
      changes:
        - param: probe
          from: 2
          to: 3
      rationale: "..."

- **The family** must be registered. **The configuration** must name every
  `parameter`-role key, every value valid. **Each change** must be to a
  `parameter`-role key, its `from` equal to the configuration's value, its `to`
  valid and different, and no parameter may be changed twice.
- **`scope` is refused anywhere,** at the top level or in a change: *a policy
  has no scope: it is a parameter change over a whole configuration. A change
  to a subset of queries or vectors requires a family that does not exist.*
- **Every problem is reported together.**
- **The rationale** is stored as quoted text and read by nothing.
- **Output:** a `Policy` with `from_config` and `to_config` as real `Config`s,
  and a sha256 over its canonical JSON, independent of key order.

**One addition to the design, stated:** `configuration`. The paper's example
had none, but without it `from` cannot be checked and the two configurations
have no label. Requiring every parameter makes a policy's labels exactly the
ones a run gives the same configurations through `include`.

### 3. The prediction file, with its digest in the run's inputs (`prediction.py`)

    expects:
      - {metric: recall_at_10, direction: rises, by_at_least: 0.02}
    side_effects:
      - {metric: storage_amplification, stays_at_or_below: 4.0}

**Refused before anything runs, all reasons together:**
- no expected change, or one missing its metric, direction or threshold ("it
  will be better" is not a prediction);
- a threshold below `CALIBRATION_TOLERANCE`, with the tolerance named;
- a metric outside `recall_at_10`, `ceiling_at_10`, `storage_amplification`
  and `fanout` (the fractions and ratios the tolerance's scale fits);
- the same metric predicted twice, or both predicted and bounded;
- a side effect without exactly one bound.

**`write_prediction`** writes `prediction.json` once, refusing to overwrite. It
is marked declared, and carries:
- the canonical policy and its sha256;
- both configurations' labels and parameters;
- the checked expectations and bounds;
- the tolerance validated against;
- the seed, and digests of the workdir's `characterization.json`,
  `sample_ids.json` and `queries_ids.json`.

**The citation:** `simulate.run` reads `prediction.json`'s sha256 at its start,
before any configuration is measured. It records it in `simulate_info.json`
as `prediction: {file, sha256, read}`, marks the file declared in its kind map,
and lists it in the workdir `MANIFEST.sha256`. `report`'s `INPUT_FILES` gains
`prediction.json`, so a report's `inputs` digest it too. `simulate_include(policy)`
gives the two include entries that measure a policy's before and after.

### 4. The two-run verdict rule (`verdict.py`)

For an expected change with threshold T and tolerance t, delta is after minus
before (before minus after for `falls`):

    |delta - T| < t    couldnt_check   (indistinguishable from the threshold)
    delta > T          held            (so delta >= T + t)
    delta < T          did_not_hold    (so delta <= T - t)

**A side-effect bound** on the policy row reads the same way.

**Rounding:** deltas and gaps are rounded to 6 decimals first, as
`calibrate.history` does. Without it `0.83 - 0.80 - 0.02` is
`0.009999999999999915`, and a point exactly on the band would be decided by
float representation.

**The whole judgement is couldnt_check, with the reason,** when:
- the run's inputs cite no prediction;
- they cite a different sha256 (written or edited after the run started);
- the seed differs;
- either configuration's row is missing.

**Overall:** did_not_hold if any row did not hold, else couldnt_check if any
could not be checked, else held. The rule never uses the report's absolute
thresholds.

### 5. Documents

`docs/PROPOSALS.md`:
- the scope removed from the example and the rules, replaced by the whole
  configuration and the rule that a per-subset change requires a family that
  does not exist;
- §1's example sentence no longer a per-subset one;
- "only keys whose role is *parameter*";
- "a receipt" → declared, and why;
- "a signed statement" → hashed and cited by the run's inputs, since ordering
  comes from the citation, not from the hash;
- the tolerance rule in §2.3, the two-run rule in §2.4, and §3's list to
  match;
- "five numbers" → "five measures, six numbers — drift is a pair".

A test validates the document's policy example with the real validator, so
the paper cannot describe a policy the code refuses.

`docs/CHARTER.md`, under Phase 5: *Planned, not shipped. PROPOSALS.md is the
position written before the code, not a description of anything that runs: no
command translates an idea, runs a proposal or publishes a card.* The charter
listed proposals as a planned phase but did not say the paper is a position.

## Measurements

**Tests added:**
- `oneground/models/test_parameters.py`: 23 tests (with parametrisation).
- `oneground/proposals/test_proposals.py`: 29 tests, one of them end to end:
  1. a `single_node_hnsw` policy (`efSearch` 16 → 64) is validated;
  2. its prediction is written;
  3. the real `simulate` runs on the 2k synthetic corpus with the policy's two
     include entries;
  4. `simulate_info.json` cites the prediction's sha256 and the manifest lists
     it, and the judgement comes back with no citation problem;
  5. the prediction is edited, and the judgement becomes couldnt_check,
     "written or edited after the run".

**Negative controls** (`tasks/scratch/026-mutants.py`, gitignored): each mutant
applied to a scratch copy of the tree. **9 of 9 caught; the unmutated copy
passes 52 tests.**

    caught  get() returns any key, declared or not
    caught  configs are not validated at construction
    caught  a family declares a parameter it never reads
    caught  simulate adds shard_depth to every family again
    caught  a policy may carry a scope
    caught  a prediction below the tolerance runs
    caught  the two-run rule has no tolerance band
    caught  the verdict judges without checking the citation
    caught  simulate does not cite the prediction

**Full suite:** **871 passed, 0 failed, 0 skipped** (3 m 54 s): 819 before, plus the 52 added here. The live RunPod plan test passed on this run.

**Scans:** identifier scan 0 findings, with this report staged; leak scan, the one known synthetic
`DESKTOP-` probe; `tasks/scratch/018-docs-numbers.py`: ALL CHECKS PASSED.

## Verification

- Parameter tables with names, types, ranges and constants; strict `get()`;
  conformance on every key read: done, and caught by mutants when broken.
- `shard_depth` and the `efConstruction` constants included, and `shard_depth`
  found to be a constant in `hash_sharded`, not only a missing declaration.
- Scopes out of the schema and the paper: done.
- A delta below the tolerance rejected before the run, naming it: done.
- The prediction's digest in the run's inputs: done, and proven with the real
  `simulate`.
- The two wording fixes and "five measures, six numbers": done. The charter
  line: done.

**Couldn't-check:**
- **Whether any requirements file outside this repository** uses an
  undeclared key. Every shipped one plans cleanly. A user's file that did will
  now be refused where it was silently ignored. That is the intended
  behaviour change, and it is a behaviour change.

## Observed, not done

- **`policies/README.md` and `CLAUDE.md` still define `policies/` as "small
  policy functions" producing "a concrete recommendation".** That contradicts
  the paper, where a policy is never code and a card never recommends. The
  package is `oneground/proposals/` to avoid the name, but the directory's
  definition is unchanged.
- **`simulate_info.json`'s `shard_depth_note` says the depth is "used by every
  sharded family in this run".** `hash_sharded` never read it; its own
  `max(30, k)` gives the same number for the ks reported, so no value was
  wrong, only the sentence.
- **Cross-parameter validity is not checked:** `probe` greater than
  `centroids`, `shards` greater than the corpus.
- **`docs/MODELS.md` "Adding a family"** does not yet say a family must
  declare its parameter table. The conformance test will say so to a
  contributor who forgets.
- **The charter's Phase 5 still lists adversarial review as part of the
  loop,** while the paper's §5 leaves whether to build it unsettled.

## Repo now contains

Changed:

    oneground/models/base.py                   Param, declare_parameters, strict Config and grid
    oneground/models/single_node_hnsw/model.py PARAMETERS
    oneground/models/semantic_sharded/model.py PARAMETERS
    oneground/models/hash_sharded/model.py     PARAMETERS
    oneground/simulate/__init__.py             shard_depth and centroids only where accepted;
                                               ParameterError -> SimulateError; the prediction cited
    oneground/report/__init__.py               prediction.json in INPUT_FILES
    docs/PROPOSALS.md                          the rulings and wording fixes
    docs/CHARTER.md                            the one line

New:

    oneground/models/test_parameters.py
    oneground/proposals/__init__.py
    oneground/proposals/policy.py
    oneground/proposals/prediction.py
    oneground/proposals/verdict.py
    oneground/proposals/test_proposals.py
    tasks/026-proposals-first-slice.report.md

## Blocked on developer

1. Push `main`. Whether this slice goes into the `v0.1.0` retag is your call:
   it changes `simulate`'s behaviour on a requirements file naming an
   undeclared key, from silently ignoring the key to refusing the file.
