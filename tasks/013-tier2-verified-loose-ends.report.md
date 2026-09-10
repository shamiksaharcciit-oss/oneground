# Report: 013-tier2-verified-loose-ends

## Repo state expected vs found

| the brief assumed | found |
| --- | --- |
| master at or after `a4a579a` (T2) | yes — `a4a579a T2: the verdict, verified` was HEAD. |
| tree clean | one untracked file, `tasks/scratch/T2-values-before.json`, which the brief said to ignore. Untouched. |
| the tree is shared with the teaser stream | yes. Every commit here is prefixed `task 013:` and touches only package, fixture, docs and `tasks/` paths. Nothing under `site/teaser/` was read or written. |

Two things about the repo the brief did not mention and that are worth
recording, because they changed how I worked:

- `task-012` is a separate branch, two commits ahead of anything on master.
  Not merged, not touched.
- The release asset is at `~/oneground-assets/arxiv-150k\` and is
  complete: `vectors.npy` (460,800,128 bytes), `queries.npy`, `sample.jsonl.zst`,
  and the two metadata parquets.

## What was done

Eight commits. Steps 1–7 of the brief, plus six defects found while doing
them — four of them mine, all found and fixed inside this task.

**Step 1 — 011's leftovers** (`cf6dbcb`).

The `scope` decision-log entry said *"judged against 4 constraint(s)"* and
omitted `qps` while every option carried five verdicts. Two defects, not one:
`_constraint_names` is a hand-maintained list of `if` branches and task 011
shipped `qps_target` without adding one — but more importantly the entry was
reading the requirements rather than the verdicts. It now counts **the
constraints actually judged**, read off the options, so an issued-but-unlisted
verdict cannot drift again. The missing branch was added too, for the
pre-flight line that runs before any option exists.

The runner-up line now carries its outcome. On the arXiv report it reads:

```
  indistinguishable on recall from: hash_sharded[M=32,efSearch=96,shards=3]
    hash_sharded[M=32,efSearch=96,shards=3]: couldnt_check -- could not be
    checked on latency_p95, qps. Indistinguishable on recall is not
    indistinguishable overall.
```

`test_the_real_arxiv_workdir_gives_one_option_the_measurement` read gitignored
`runs/`; it now skips with a reason naming the workdir, and its name says it
needs a local run.

**Found while doing that, and not in the brief**: the standalone runner in
`oneground/verify/test_matched.py` sat at line 283, so `_main()` collected
`globals()` before the rest of the file was defined. `python
oneground/verify/test_matched.py` — which the module docstring advertises —
reported **"19 passed"** out of **65** test functions. 46 never ran. `pytest`
ran all 65 throughout, so nothing was actually unverified, but a runner that
silently under-collects reports a green number that means less than it says.
The block moved to the end of the file and `_main` learned to report skips.

**Step 2 — Tier 2 intake and declared-mode characterize** (`7730bda`).

`intake` refused `corpus.declared` as "not implemented"; it now validates it
and marks the requirements Tier 2. `size_now` and `dimension` are required
because the capacity arithmetic is arithmetic over exactly those two.
`text_length` is checked against the set the fixtures declare, since a value
outside it can only match by accident. A file with Tier-1 fields outside
`corpus.sample` is refused rather than silently run as Tier 2.

`characterization.json` is shaped exactly like Tier 1's, with all five
measured fields carrying `couldnt_check: declared, not measured` rather than
being absent — an absent field reads as an oversight, one that says why it is
empty reads as a boundary, and every consumer that already renders a
couldn't-check string renders it unchanged.

`n_base` stays couldn't-check and does **not** borrow `size_now`. The size of
a sample and the size of a corpus are different numbers, and filling one from
the other would turn a declaration into a measurement in the field a reader is
most likely to trust.

**Step 3 — the fixture analogy** (`dde4e29`). Detailed under *Measurements*.

**Step 4 — capacity arithmetic** (`25b8510`). Detailed under *Measurements*.

**Steps 3+4+6 — the Tier 2 report** (`2cc8ac1`).

Fixture values live under `fixture_*` keys so they can never sit beside the
user's own numbers unlabelled. A Tier-1 workdir under a Tier-2 requirements
file is refused rather than half-read.

Fixed while wiring: the cost call used a `PriceTable.load` that does not exist
and a `cost_for_options` signature that is not the one in `oneground/cost`. It
now uses `load_prices` and `size_and_cost`, and keeps **both** node counts —
how many nodes of the size the user said they would run, and the cheapest way
the price table can hold it. Those answer different questions and a reader
should see both.

**Step 5 — `fixture verify` value reproduction** (`833b2eb`, then drift,
the digest fix and the running-pin rule in the final commit).

**Step 7 — `docs/INTAKE.md`** (`833b2eb`).

## Measurements

### Step 5: arxiv-150k, values recomputed from the release asset

Method: `oneground fixture verify arxiv-150k`, recomputing with the same
functions the product path uses, on this machine, against the spec's own
published tolerances. Full log in
`tasks/scratch/013-arxiv-verify-pinned.log`; the two earlier unpinned runs
are kept beside it as the evidence for the cross-version finding.

Run in the pinned environment: `.venv/Scripts/python.exe`, numpy 2.5.3,
faiss-cpu 1.15.0, scikit-learn 1.9.0.

| value | recomputed | published | delta | tolerance | |
| --- | --- | --- | --- | --- | --- |
| intrinsic_dimensionality | 32.5533 | 32.55 | 0.00326 | 0.5 | verified |
| boundary_crispness | 0.0362467 | 0.036 | 0.000247 | 0.02 | verified |
| skew_top10_share | 0.0754 | 0.075 | 0.0004 | 0.02 | verified |
| ambiguous_query_rate | 0.8915 | 0.891 | 0.0005 | 0.02 | verified |
| drift (before / after) | 0.523212 / 0.551401 | 0.522 / 0.549 | 0.00121 / 0.00240 | 0.02 | verified |
| single_node_hnsw.recall_at_10 | 0.9978 | 0.997 | 0.0008 | 0.01 | verified |
| semantic_sharded.recall_at_10 | 0.932 | 0.932 | 0 | 0.01 | verified |
| semantic_sharded.storage_amplification | 3.71516 | 3.715 | 0.00016 | 0.01 | verified |

```
summary: digests 11 verified, 0 contradicted, 0 couldnt_check
         values   8 verified, 0 contradicted, 0 couldnt_check
```

**All eight reproduce, on a second machine and a second operating system.**
Build 3 was made on Linux with a CUDA GPU; this ran on Windows on a laptop,
under the same pins. `status: verified` is set.

### drift, the value that was unreachable

The brief's step 5 scoped recomputation to "vectors, queries", which left
`drift` unreachable: it needs `update_date` per record, and that lives in
`sample.jsonl.zst`. On the developer's ruling the scope became **the release
asset** — a value checkable from the published artifacts is a value this
command checks — and drift is now recomputed from there.

The reconstruction is exact rather than reimplemented. `fixture.build` writes
`sample.jsonl.zst` as base records tagged `role: "base"` followed by query
records tagged `role: "query"`, in the order it embeds them; reading it back
and splitting on the tag reproduces the `base_recs` and `q_recs` the build
held, and the same `drift_pair` is then called with the same seed and the
cutoff read from the spec's own definition text.

One check landed before any arithmetic: the reader finds **965** query records
dated before 2019-01-01, and the fixture's published `drift_n_before` is 965.

Guards, because a plausible-looking number is the failure mode: base and query
row counts are asserted against `vectors.npy` and `queries.npy` rather than
trusted — a sample file whose rows do not match is not the file that produced
those vectors, and zipping two corpora together would give something that
looks like a reproduction. A cutoff that empties either side is refused, as
are records without `update_date`.

**And a fourth defect, found by running it.** The digest half reported

```
couldnt_check  vectors.npy  artifact not present (release asset, or not built)
```

for `vectors.npy`, `queries.npy` and `sample.jsonl.zst` — on a machine where
all three are present, at the location the fixture's own documentation names.
`verify_digests` looked only in the fixture directory; the value half already
looked in both. Saying couldn't-check about something checkable is the same
error as rounding couldn't-check up, failing in the quiet direction instead of
the loud one.

Fixed, and the three now verify against their manifest digests, with the
detail naming which directory answered:

```
verified  receipt  vectors.npy       141a9220…  (from ~/oneground-assets/arxiv-150k)
verified  receipt  queries.npy       dbed194a…  (from …)
verified  receipt  sample.jsonl.zst  404cb92e…  (from …)
```

**All 11 digests verify.** The digest half of the spec's criterion is fully
met; the value half is not.

### The fifth defect: the pin check compared the wrong pair

The brief specified the pin check as *"compare `build_info` pins to
`requirements.txt`"*, and that is what was built. On arxiv-150k it passes:
`build_info` records numpy 2.5.3 and faiss-cpu 1.15.0, and `requirements.txt`
pins exactly those.

It answers the wrong question. It confirms the **historical build** was pinned
and says nothing about the process recomputing the values. The first complete
run reported `8 verified` and *"status may be set to `verified`"* while
executing on numpy 2.2.6 and faiss 1.14.3.

The fixture spec's own note is the authority on what the status means:

> `couldnt_check` is reported when a dependency version differs from the
> pinned one; it is never rounded up to verified.

For a verification, the version that differs is the verifier's. So
`running_pin_mismatches()` compares **this process's** imported versions
against `requirements.txt`, and that is what now decides.

It downgrades rather than short-circuits. The values are still computed,
compared and printed; only the outcome changes, and the detail reads
`WITHIN TOLERANCE, but not under the pinned environment (numpy: running
2.2.6, pinned 2.5.3; ...)`. Throwing the agreement away would have discarded a
real measurement. A **contradiction** is never downgraded — disagreement is
disagreement, and unpinned libraries explain it at most.

Had this not been caught, `status: verified` would have been set on a
reproduction that never happened under the pins.

### The sixth: nothing was ever running in the venv

Chasing the pin mismatch found its cause, and it is not a dependency problem.

```
bare `python`  ->  ~\AppData\Local\Programs\Python\Python312
                   numpy 2.2.6, faiss 1.14.3      the system install
.venv          ->  created 2026-09-08 15:44 from that same base,
                   include-system-site-packages = false
                   numpy 2.5.3, faiss 1.15.0      correct since creation
```

**Nothing downgraded numpy or faiss, and no `pip install` was needed.** All 65
packages pinned in `requirements.txt` already matched in `.venv`.
(`pydantic-core` looks absent from a naive comparison only because pip freeze
normalises it to `pydantic_core`; it is present at 2.46.5.) Installing over a
correct environment to satisfy the instruction would have been theatre, so it
was checked, reported, and skipped.

The fault is an invocation error, and it is mine: every command in this
session used bare `python`, which resolves to the system interpreter.
`CLAUDE.md` says "venv at `.venv`" and warns about the Store stub, but nothing
forced the choice and nothing in the tooling noticed.

**What it affects.** Local test runs and local `report` generation this
session executed on numpy 2.2.6. The tests are logic tests and `report` is
arithmetic over JSON, so no conclusion changes — but the runs were not in the
pinned environment and the earlier parts of this report were written without
saying so. The task-011 pod results are unaffected: those installed
`requirements.txt` fresh on the pod. Task 011's arXiv `report.json` was
generated locally, on the system Python.

The full suite has since been re-run in `.venv`: **385 passed, 1 skipped.**

**For 014's fresh-venv release**, the fix is not to reinstall anything — it is
to make the wrong interpreter impossible to use silently. Cheapest first:
invoke `.venv/Scripts/python.exe` explicitly everywhere; or refuse to write a
canonical artifact when `running_pin_mismatches()` is non-empty, which is the
guard built here for `fixture verify`, generalised; or both. The guard is the
one that survives someone forgetting.


### Step 3: the analogy, on the two shipped requirements files

Method: `oneground.analogy.choose` against `fixtures/*.fixture.yaml`.

```
support_tickets  ->  no analogy   (arxiv-150k scores 0.33 against a 0.70 floor)
papers           ->  arxiv-150k   (1.00, matched on all six fields)
```

**The example file gets no analogy, and that is the honest answer.**
`requirements.declared.example.yaml` is support-tickets-like, as the brief
specified; the only fixture declaring an `analogy:` block is arxiv-150k, which
is papers. The report says so and names the near miss:

> no fixture is close enough to be an analogy. The nearest, arxiv-150k, scores
> 0.33 against a floor of 0.70 (matched on topics_trend, time_ordered,
> dimension, model_family; differs on corpus_type, text_length). A fixture
> chosen because it was the only one available is a default, not an analogy.

Lowering the floor to force a match would have been changing a threshold to
make something pass. The analogy display path is exercised instead by a
papers-shaped Tier-2 file (`tasks/scratch/013-papers-tier2.yaml`), which
matches at 1.00 and renders the fixture's surface under the required label.
When 012 lands `glove-100k`, and when a ticket-like fixture exists, the
example will match something.

**A defect in my own weighting, found and fixed inside this task.** I first
gave `corpus_type` a weight of 4.0 against 7.0 for the other five, with a
comment claiming a wrong corpus type could never be rescued by the smaller
fields agreeing. The arithmetic says the opposite: 7.0/11.0 = 0.64 beats
4.0/11.0 = 0.36. A weighting whose stated rationale is false is worse than one
with no rationale. It is now 8.0 — strictly above the sum of the rest — with a
test asserting the ordering holds rather than the comment asserting it.

### Step 4: capacity arithmetic

Method: `oneground.capacity.plan` over the declared 2,100,000 × 768.

| family | amplification | stored | memory | nodes @ 64 GB |
| --- | --- | --- | --- | --- |
| single_node_hnsw | 1.0 | 2,100,000 | 6.5 GB | 1 |
| hash_sharded | 1.0 | 2,100,000 | 6.5 GB | 1 |
| semantic_sharded | **couldn't-check** | — | — | couldn't-check |

With a papers analogy in play, `semantic_sharded` borrows arxiv-150k's
*measured* 3.715147, labelled as the fixture's, and the arithmetic becomes
7,801,500 stored / 24.2 GB.

Cost: `EUR 140 +/- 35` per family from the declared list-price table at a 0.25
error band.

**Why `semantic_sharded` is refused.** It replicates a vector into every
region whose centroid is within `(1+epsilon)` of its nearest. How many regions
that is depends on how the corpus clusters — the geometry Tier 1 measures and
Tier 2 does not have. On isotropic random vectors the answer is near-uniform
and bears no relation to real text embeddings. So the family is not built at
all: its fan-out and shard count are read from the configuration where they
are *stated*, and its amplification is refused.

That refusal replaced an earlier version that did build it. The only visible
effect of that build was a faiss warning that 4,096 points is too few to
cluster into 256 regions — a 256-way k-means over noise, producing a number
the next line threw away.

### Step 6: Tier 2 end to end

`requirements.declared.example.yaml` → `characterize` → `report`. The final
decision-log entry, verbatim:

```
[to_resolve] To turn these into measurements, add `corpus.sample` to the
requirements file: 10,000-20,000 vectors drawn stratified from the corpus
turns recall_at_k (k=10), storage_amplification and memory_budget into
measurements against exact ground truth; 50 or more real queries -- logged,
not invented -- turns ambiguous_query_rate into a measurement and is the floor
below which it stays couldn't-check; a timestamp column on both the corpus and
the queries turns drift into a measurement, and corpus timestamps alone are
not enough; latency_p95 and qps need more than a sample: they need a real
engine in an environment where the round trip is small relative to the query,
which is `oneground verify` with verify.target: runpod. monthly_budget stays
declared either way -- the price table is list prices, and the arithmetic
above uses the upper bound of its error band.
        source: requirements:corpus.sample
```

The report issues **6 constraints, 0 judged**, and recommends nothing.

## Verification

**Passed.** 385 tests, 1 skipped (the live RunPod test), run in the pinned
`.venv`. Against the brief's acceptance list:

- *Step-1 tests pass; scope entry correct on the arXiv workdir.* Yes — the
  entry now reads `5 constraint(s): recall_at_k, storage_amplification,
  latency_p95, qps, monthly_budget`.
- *Tier 2 produces a report with zero verdicts and a correct "what would make
  this measurable" entry.* Yes. A test asserts the report's JSON contains
  neither `"meets"` nor `"fails"` anywhere.
- *`fixture verify arxiv-150k` reports per-value outcomes; status flipped only
  on a clean reproduction.* Yes — 8/8 values and 11/11 digests, in the pinned
  environment, and the status was flipped only after that run. It was
  **withheld** from an earlier run that reproduced the same numbers outside
  the pins.
- *Tests pass; INTAKE.md exists.* Yes.

**Verified, and worth stating plainly:** `fixtures/arxiv-150k` is the first
fixture in this project to reach `status: verified`, and it did so on a
different operating system and different hardware from the build that produced
it.

**Couldn't-check.**

- *Whether the analogy matcher's weights are right in general.* They are
  defensible and tested for one ordering property, against one fixture. A
  weighting is only really tested by fixtures it has to discriminate between,
  and there is currently one.
- *Whether Tier 2's memory estimate is close.* It is `estimate_memory_bytes`,
  the same estimate the simulator uses, labelled an estimate everywhere it
  appears. Nothing has measured a real 2.1M-vector index against it.
- *Whether anything else in the repo was produced outside the pinned
  environment.* This session's local runs were, and are re-run. Earlier
  sessions are not audited here.

## Observed, not done

- **`requirements.example.yaml` still documents Tier 2 as the schema by
  example**, which is now correct rather than aspirational, but it and
  `requirements.declared.example.yaml` overlap. Whether the declared block
  should live in one file or two is a documentation call.
- **Only one fixture declares an `analogy:` block.** The brief anticipated
  this ("add `analogy:` keys to arxiv-150k and glove-100k when 012 lands; for
  now arxiv-150k"). Until a second one exists the matcher is discriminating
  between one candidate and nothing.
- **The Tier-2 report writes no `report.html`.** Tier 1 does. Nothing in the
  brief asked for one, and the console output plus `report.json` carry
  everything; but the asymmetry will be noticed.
- **`epsilon_sweep` is implemented and tested but not called by the report.**
  The brief asked for "storage at each ε for semantic-sharded" as part of the
  capacity arithmetic; what the report shows is the single configured ε. The
  function is there, correct, and refuses without measured values — wiring it
  into the report is a display decision I did not make unilaterally.

## Repo now contains

New:

    oneground/analogy.py                  fixture matching on declared fields
    oneground/test_analogy.py             17 tests
    oneground/capacity.py                 arithmetic over a declared corpus
    oneground/test_capacity.py            15 tests
    oneground/intake/test_tier2.py        21 tests, intake + characterize + report
    requirements.declared.example.yaml    the Tier-2 file by example
    docs/INTAKE.md                        the two tiers and the honesty rules

Changed:

    oneground/intake/__init__.py     Tier 2 validated rather than refused
    oneground/characterize.py        declared mode
    oneground/report/__init__.py     Tier-2 branch; scope counts what was
                                     judged; runner_up_lines
    oneground/report/test_verdict.py 9 tests for the step-1 fixes
    oneground/fixture/verify.py      value reproduction incl. drift;
                                     assets-dir digests; the running-pin rule
    oneground/fixture/test_verify.py 21 tests
    oneground/verify/test_matched.py the standalone runner collects the file
    oneground/test_characterize.py   the Tier-2 refusal test, updated
    fixtures/arxiv-150k.fixture.yaml `analogy:` block (declared)

`fixtures/arxiv-150k.fixture.yaml` `fixture.status` is **`verified`**, with
a changelog entry naming the run, both environments and all eight values,
and a `values_survive_a_library_version_change` finding carrying the
cross-version agreement as advisory evidence — explicitly not as the status.

## Blocked on developer

Nothing is blocked and nothing is outstanding.

Two things are handed forward rather than left open:

1. **For 014's fresh-venv release**: make the wrong interpreter impossible to
   use silently. See *The sixth defect* above — the guard already exists for
   `fixture verify` and wants generalising to anything that writes a canonical
   artifact.
2. **A second fixture with an `analogy:` block.** Until `glove-100k` lands
   from 012, the matcher discriminates between one candidate and nothing, and
   `requirements.declared.example.yaml` correctly gets no analogy.

One judgement call is recorded in case you would have made it differently:
`epsilon_sweep` is implemented, tested and **not wired into the report**. The
brief asked for "storage at each ε for semantic-sharded" as part of the
capacity arithmetic; what the report shows is the single configured ε. The
function refuses without measured values, so wiring it in would add a column
of couldn't-checks unless an analogy fixture published a sweep. That is a
display decision I did not make unilaterally.


---

# Report: 013b — the pinned-environment guard

## Repo state expected vs found

As left by 013: master at `132dcba`, tree clean apart from
`tasks/scratch/T2-values-before.json` (the teaser stream's, untouched) and
`tasks/014-preview-release.md`, which appeared during 013 and has not been
read or staged.

## What was done

**1. `running_pin_mismatches()` generalised into a guard.**

`oneground/environment.py` now holds the pin machinery, and every command that
writes a canonical artifact calls it before computing anything:

    oneground characterize     oneground verify      oneground fixture verify
    oneground simulate         oneground report      oneground fixture build

Each prints the interpreter path — the line whose absence let 013 run a whole
session on the wrong Python — and **refuses**, exit 2, when any pinned package
differs. `--allow-unpinned` proceeds and stamps.

`fixture verify` guards itself rather than being guarded from the CLI: it
needs the pin comparison anyway, to decide each value's outcome, and stopping
at the front saves ten minutes of recomputation under the wrong libraries.

**Only the packages that can move a number are checked** — numpy, faiss,
faiss-cpu, scikit-learn. A guard that fires on `pyyaml` teaches people to pass
`--allow-unpinned` by reflex, which is worse than not checking.

**2. The stamp reaches the artifact.** `build_info.json` gains an
`environment` block and `report.json` a `run_environment` block: interpreter,
version, whether it was a venv, the pinned verdict, and every mismatch. When
`pinned` is false the report's console footer says so above the file paths.

`run_environment`, not `environment`, because the Tier-1 report already uses
that key for the *verify target's* environment. Both were briefly in the same
dict literal and the later one silently won — caught by checking the written
JSON rather than the code.

**3. `CLAUDE.md`** gained the two sentences under Environment.

## Measurements

### The guard, both ways

Method: the same command run twice, once per interpreter. Full output in
`tasks/scratch/013b-smoke-venv.log`.

**Under `.venv` — passes.**

```
python  <repo>\.venv\Scripts\python.exe  (venv)
digests 11 verified, 0 contradicted, 0 couldnt_check
values   0 verified, 0 contradicted, 8 couldnt_check
exit=0
```

**Under the system interpreter — refuses.**

```
python  ~\AppData\Local\Programs\Python\Python312\python.exe  (SYSTEM INTERPRETER)

REFUSED: `oneground fixture verify` writes a canonical artifact, and this
interpreter is not running the versions requirements.txt pins:

    numpy            running 2.2.6        pinned 2.5.3
    faiss-cpu        running 1.14.3       pinned 1.15.0
...
  To proceed anyway, pass --allow-unpinned. The artifact is then
  stamped `unpinned environment` and every reader of it can see that.
exit=2
```

`oneground report requirements.smoke.yaml` behaves identically: exit 0 under
the venv, exit 2 and no report written under the system interpreter.

### The escape hatch stamps

`report --allow-unpinned` under the system interpreter, exit 0, and in
`runs/arxiv-smoke/report.json`:

```json
"run_environment": {"pinned": false, "note": "unpinned environment",
                    "allowed_by": "--allow-unpinned", "in_venv": false,
                    "mismatches": [{"package": "numpy", "running": "2.2.6",
                                    "pinned": "2.5.3"}, ...]}
```

with, in the footer:

```
ENVIRONMENT      unpinned environment: numpy 2.2.6 (pinned 2.5.3), faiss-cpu 1.14.3 (pinned 1.15.0)
                 every verdict above was judged outside requirements.txt
```

That workdir was then regenerated under the venv, so what is on disk reads
`pinned: true`.

### A defect the demonstration found

`oneground fixture verify arxiv-smoke` **crashed** under the venv:

```
ValueError: could not convert string to float: 'TO_BE_FILLED'
```

`arxiv-smoke.fixture.yaml` is a scaffold whose characterization values were
never filled in — its own header says "Values marked TO_BE_FILLED are set by
the first canonical build" — and `_compare` called `float()` on the
placeholder, killing the command after the digests had already passed.

An unfilled field is neither a contradiction nor a crash: it is a value nobody
has published. `_as_number()` now returns a reason instead of raising, and the
eight values report

```
couldnt_check  intrinsic_dimensionality  the spec publishes 'TO_BE_FILLED' rather
                                         than a number; this value has not been
                                         filled in yet
```

This had never been hit because value reproduction was written in 013 and only
ever pointed at arxiv-150k, whose values are real. The brief's step 3 —
"re-run the smoke fixture verify" — is what exposed it.

## Verification

**Passed.** 401 tests, 1 skipped, in `.venv`. 16 of them new, in
`oneground/test_environment.py`.

The new tests are synthetic about versions on purpose: they inject them rather
than asserting anything about the running interpreter, so they pass in a
pinned venv and in a contributor's unpinned checkout alike. Two are not
synthetic — they read `cli.py` and `fixture/verify.py` and assert that each of
the six commands actually calls the guard and offers the flag, because a guard
someone forgets to wire into a seventh command is the failure this task
exists to prevent.

- *A command refuses under an unpinned interpreter.* Demonstrated above, twice.
- *A command passes under the venv.* Demonstrated above, twice.
- *`--allow-unpinned` stamps rather than shrugs.* Demonstrated above, in both
  the footer and the JSON.

**Couldn't-check.** Whether every *future* canonical-artifact command gets
guarded. `test_every_canonical_artifact_command_runs_the_guard` names the six
that exist; a seventh added without a guard would pass the suite. The list is
maintained by hand, which is the same shape of defect as 013's
`_constraint_names`.

## Observed, not done

- **`oneground fixture verify` and `python -m oneground.fixture.verify` parse
  different flags.** `cli.py` builds its own fixture parser and does not use
  `fixture/verify.py`'s `build_parser()`, so `--assets-dir`, `--verbose` and
  `--strict` are available on one path and not the other. Pre-existing; the
  guard flag was added to both so 013b does not widen the gap.
- **`build_info.json`'s `environment` key** is new and not in the fixture
  specs' documented artifact shape. No spec references it yet.
- **The guard does not cover `oneground pod`.** A pod session creates no local
  canonical artifact — the pod builds its own environment from
  `requirements.txt` — and it is deliberately outside the shared parser.

## Repo now contains

New:

    oneground/environment.py         the guard, the stamp, the pin comparison
    oneground/test_environment.py    16 tests

Changed:

    oneground/cli.py                 six commands guarded; the two meanings of
                                     `requirements` kept apart
    oneground/fixture/verify.py      guards itself; re-exports the pin
                                     machinery; TO_BE_FILLED is couldnt_check
    oneground/fixture/test_verify.py two wording assertions sharpened
    oneground/characterize.py        build_info carries the stamp
    oneground/report/__init__.py     report.json + footer carry run_environment
    CLAUDE.md                        the two sentences under Environment

## Blocked on developer

Nothing. 014 is not started, as instructed — it waits on the task-012 merge.
