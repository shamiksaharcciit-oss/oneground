# Report: 010-report

## Repo state expected vs found

| Expected | Found |
|---|---|
| task 009 committed | **no — HEAD is `c73c71e` (task 008)** |
| tree clean | **no — all of task 009 is uncommitted** |
| a workdir from characterize → simulate → verify on smoke | yes, `runs/arxiv-smoke/` complete |
| an arXiv workdir from task 008's simulate | yes, `runs/arxiv-150k-via-characterize/` |

### Task 009 is not committed

`git log` shows HEAD at task 008. Everything task 009 built —
`oneground/adapters/`, `oneground/verify/`, `docs/ADAPTERS.md`,
`requirements.smoke.yaml`, the `semantic_sharded` and `simulate` changes — is
sitting in the working tree.

I did not stop (CLAUDE.md rule 1): the code is present and working, so nothing
in task 010 is blocked by it. But the consequence is worth stating plainly,
because this project has hit it before (the task 004 report flagged the same
thing): **the working tree now contains two tasks' changes**, and
`git diff` cannot separate 009's adapter work from 010's report work. If 009
was meant to be reviewed on its own, that is no longer possible without
splitting by path.

### The workdirs

`runs/arxiv-smoke/` — characterize, simulate and verify all present:

    MANIFEST.sha256  build_info.json  characterization.json
    ground_truth.npy  ground_truth_scores.npy
    queries_ids.json  sample_ids.json
    simulate.json  simulate_info.json
    verify.json  verify_info.json

`runs/arxiv-150k-via-characterize/` — the same minus `verify*`, which is what
run 3 needs:

    MANIFEST.sha256  build_info.json  characterization.json
    ground_truth.npy  ground_truth_scores.npy
    queries_ids.json  sample_ids.json
    simulate.json  simulate_info.json

## What was done

All seven steps.

### 1–3. `oneground/report/` and the verdict rules

`oneground report <requirements.yaml>` reads the workdir's receipts and the
requirements file's `constraints`, and produces three outcomes per option, a
decision log, a manifest and an HTML page.

`report/verdict.py` is pure functions over dicts — no I/O — so every branch is
testable on synthetic rows. The rules the house cares about are enforced in
code rather than trusted to the caller:

- **`latency_p95` takes `verify_data`, not `sim_row`.** There is no code path
  from a simulated number to a latency verdict. `sim_row` is accepted only to
  name the option in the source string, and no field of it is read for a
  value.
- **`overall()` returns `couldnt_check` for an empty verdict list.** Nothing
  judged is not the same as everything passing.
- **Every `Verdict` carries a `source`** — a file and a field path — and a
  test asserts none is empty.

### 4. Outputs

`report.json` (measurement and judgement under separate keys per option),
`manifest.yaml` (the recommended configuration plus the sha256 of every input)
and `report.html`.

### 5. `report.html` and `docs/design/`

`docs/design/tokens.md` and `tokens.css` created with the brief's palette. The
CSS is inlined into the page verbatim, so the tokens have one definition
rather than two.

The page is **one self-contained file with no network calls of any kind** — no
CDN, no webfont fetch, no `<script>`, no remote image. Fonts fall back through
system stacks; the ground view is embedded as a data URI. Sections in the order
the brief specifies: recommendation, options table, the ground, decision log,
receipt table, calibration footer. No charts.

One note on the amber choice, recorded in `tokens.md`: couldn't-check is
deliberately a real colour rather than a muted grey. Greying it out would
invite a reader to skip it, which is the exact failure the three-outcome rule
exists to prevent.

### 6. The three runs

All three below, with the arXiv decision log verbatim.

### 7. Tests

33 in `report/test_verdict.py`, covering every branch of every constraint,
both cross-option rules, ranking, and the two house properties.

### Deviations

- **Run 1's constraints omit latency**, and the reason is a measurement, not a
  preference — see below.
- **`mark_indistinguishable` was widened** from `meets` to all non-`fails`
  options, or the brief's own run-3 expectation could not be produced.

## Measurements

### Run 1 — smoke, constraints it meets

`requirements.smoke.yaml`: recall@10 ≥ 0.90, storage ≤ 2.0x, memory ≤ 1.0 GB.

    2 option(s): 1 meets, 1 fails, 0 couldnt_check

    configuration                                    outcome   constraints
    semantic_sharded[...epsilon=0.2,probe=2]         fails     recall_at_k=fails
                                                               storage_amplification=meets
                                                               memory_budget=meets
    single_node_hnsw[M=32,efConstruction=200,ef=128] meets     all three meet

    Recommended: single_node_hnsw[M=32,efConstruction=200,efSearch=128]

Decision log entries: scope, the semantic failure with its source, the
single-node pass listing each constraint, the recommendation with its ranking
reason ("fewest constraints at margin (0), then lowest storage amplification
(1.00x), then lowest fan-out (1)"), and finally *"Every constraint was
decidable from this workdir; nothing is outstanding."*

**Why this run has no latency constraint.** Task 009 measured that this
machine cannot attribute latency to the engine at all: the empty-collection
RTT p95 was 132% of the query p95, so `verify` reports
`couldnt_check: environment noise` for *any* threshold. A latency constraint
here would make every option couldn't-check forever and say nothing about the
architectures — so "constraints it meets" has to mean constraints this workdir
can decide. Run 2 exercises the latency path deliberately.

### Run 2 — smoke, impossible latency (p95 ≤ 1 ms)

`tasks/scratch/010-latency.yaml`, same workdir, plus
`latency: {p95_ms: 1, environment: local}`.

    2 option(s): 0 meets, 1 fails, 1 couldnt_check

    single_node_hnsw[...]  couldnt_check  recall_at_k=meets
                                          storage_amplification=meets
                                          memory_budget=meets
                                          latency_p95=couldnt_check

    No option meets every constraint, so nothing is recommended.

And the log's final entry, which is the point of the run:

> **[to_resolve]** To decide latency_p95: re-run `oneground verify` where the
> round trip to the engine is small relative to the query. On
> Windows-11-10.0.26200-SP0 the baseline RTT was a large fraction of the query
> p95, so the number measured the path rather than the engine. **A pod session
> with the client and engine in the same environment is the way to settle it
> (task 011).**
> source: `verify.json:searches[k=10].latency_shape_single_client`

Note what did **not** happen: `single_node_hnsw` meets three of four
constraints and is not recommended. couldn't-check was not rounded up.

### Run 3 — arXiv-150k, no verify

`requirements.arxiv-150k.yaml`: recall@10 ≥ 0.95, storage ≤ 2.0x, latency p95
≤ 40 ms targeting `production`.

    8 option(s): 0 meets, 6 fails, 2 couldnt_check

| configuration | outcome | recall | storage | latency |
|---|---|---|---|---|
| `hash_sharded[shards=3]` | couldnt_check | meets 0.9984 | meets 1.00x | couldnt_check |
| `single_node_hnsw[M=32,ef=128]` | couldnt_check | meets 0.9976 | meets 1.00x | couldnt_check |
| `semantic_sharded[ε=0.2,P=2]` | fails | fails 0.9318 | fails 3.72x | couldnt_check |
| `semantic_sharded[ε=0.1,P=2]` | fails | fails 0.8952 | fails 2.67x | couldnt_check |
| `semantic_sharded[ε=0.2,P=1]` | fails | fails 0.8378 | fails 3.72x | couldnt_check |
| `semantic_sharded[ε=0.1,P=1]` | fails | fails 0.7755 | fails 2.67x | couldnt_check |
| `semantic_sharded[ε=0.0,P=2]` | fails | fails 0.7205 | meets 1.00x | couldnt_check |
| `semantic_sharded[ε=0.0,P=1]` | fails | fails 0.5472 | meets 1.00x | couldnt_check |

**Against the brief's expectation**, which was "`single_node_hnsw` and
`hash_sharded` meet, indistinguishable on recall; `semantic_sharded` fails
storage; latency couldn't-check for all":

- The two baselines **meet on recall and storage** and are marked
  indistinguishable. Their *overall* outcome is `couldnt_check`, not `meets`,
  because latency could not be checked — which is the brief's own
  overall-outcome rule applied to its own latency expectation. The two clauses
  cannot both hold literally, and I read the rule as governing.
- `semantic_sharded` fails **storage at ε ≥ 0.1 and recall at every ε**. The
  brief says "fails storage"; the ε=0.0 rows pass storage (1.00x) and fail
  only recall. Both failures are reported.

### The arXiv decision log, verbatim

```
[scope] 8 configuration(s) were measured and judged against 3 constraint(s):
        recall_at_k, storage_amplification, latency_p95.
    source: requirements:constraints
[fails] semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2]
        fails recall_at_k: recall@10 0.9318 < 0.95.
    source: simulate.json:rows[semantic_sharded[...epsilon=0.2,probe=2]].recall_at_10
[fails] semantic_sharded[...epsilon=0.2,probe=2] fails storage_amplification:
        3.72x stored copies per vector > 2.0x.
    source: simulate.json:rows[...].storage_amplification
[fails] semantic_sharded[...epsilon=0.1,probe=2] fails recall_at_k:
        recall@10 0.8952 < 0.95.
[fails] semantic_sharded[...epsilon=0.1,probe=2] fails storage_amplification:
        2.67x stored copies per vector > 2.0x.
[fails] semantic_sharded[...epsilon=0.2,probe=1] fails recall_at_k:
        recall@10 0.8378 < 0.95.
[fails] semantic_sharded[...epsilon=0.2,probe=1] fails storage_amplification:
        3.72x stored copies per vector > 2.0x.
[fails] semantic_sharded[...epsilon=0.1,probe=1] fails recall_at_k:
        recall@10 0.7755 < 0.95.
[fails] semantic_sharded[...epsilon=0.1,probe=1] fails storage_amplification:
        2.67x stored copies per vector > 2.0x.
[fails] semantic_sharded[...epsilon=0.0,probe=2] fails recall_at_k:
        recall@10 0.7205 < 0.95.
[fails] semantic_sharded[...epsilon=0.0,probe=1] fails recall_at_k:
        recall@10 0.5472 < 0.95.
[indistinguishable] These options are indistinguishable on recall:
        hash_sharded[M=32,efSearch=96,shards=3] 0.9984;
        single_node_hnsw[M=32,efConstruction=200,efSearch=128] 0.9976.
        Their recall differs by less than the calibration tolerance (0.01),
        which is what this project can currently defend, so choosing between
        them on recall would be reading noise. They are separated only where
        they differ measurably.
    source: simulate.json:rows[*].recall_at_10
[recommendation] No option meets every constraint, so nothing is recommended.
        Recommending an option whose constraints could not all be checked
        would be rounding couldn't-check up to a verdict.
    source: (rule)
[to_resolve] To decide latency_p95: run `oneground verify` against a real
        engine in the environment the constraint targets. Latency is never
        taken from simulation.
    source: verify.json (absent)
```

That is a correct account of task 008's table: the two full-reach families are
within 0.0008 of each other at 1.00x storage; every semantic configuration is
below the 0.95 floor; and the ε ≥ 0.1 configurations also breach the 2.0x
storage cap — 3.72x at ε=0.2, which is the fixture's published amplification.

### `report.json` separates measurement from judgement

    option keys:  ['config', 'family', 'judgement', 'measurement', 'params']
      measurement: build_seconds, ceiling_at_10, est_memory_bytes, fanout,
                   index_loss, inv_ratio_at_10, ... (the sweep's numbers)
      judgement:   constraints, indistinguishable_from, outcome

Re-running with a different `constraints` block changes every `judgement` and
no `measurement`, and the file's shape makes that visible.

### `manifest.yaml`

Lists the recommended configuration (or `null` with a reason) and the sha256
and kind of every input:

    characterization.json  da41fb73...  receipt
    build_info.json        efa0ee15...  declared
    sample_ids.json        ea580b43...  receipt
    queries_ids.json       3690bdf2...  receipt
    simulate.json          e084bb68...  receipt
    simulate_info.json     da041af2...  declared
    MANIFEST.sha256        20b76bfb...  receipt

### `report.html`

| | smoke | arXiv |
|---|---|---|
| size | 2,899,553 bytes | 2,908,107 bytes |
| outbound references | **none** | **none** |
| embedded data URIs | 1 (the ground view) | 1 |
| well-formed | yes | yes |

Checked for `http://`, `https://`, `//cdn`, `<script`, `fonts.googleapis`,
`<iframe>`: none present. Well-formedness checked with a tag-stack parser that
handles void and self-closing elements. All eight design tokens appear; both
font families are named with fallbacks.

The recommendation block renders as:

> **recommendation** `single_node_hnsw[M=32,efConstruction=200,efSearch=128]`
> 1 meets · 1 fails · 0 couldn't-check
> recall_at_k — recall@10 1.0000 >= 0.9
> storage_amplification — 1.00x stored copies per vector <= 2.0x

Most of the 2.9 MB is the embedded ground view; the markup and CSS are ~30 KB.

### Tests

| suite | result |
|---|---|
| `pytest oneground/ -m "not live"` | **173 passed, 1 deselected** |
| `oneground/report/test_verdict.py` | 33 passed |
| everything from tasks 007–009 | still passing |

The two that matter most:

`test_NO_LATENCY_VERDICT_IS_EVER_DERIVED_FROM_SIMULATION_synthetic` feeds a
simulate row carrying `query_seconds`, `latency_p95_ms`, `p95_ms` *and* a
fake `latency_shape_single_client`, with no verify data, and asserts the
outcome is `couldnt_check` **and** that `verdict.value is None` — so no
simulated number leaked in even as a recorded value.

`test_couldnt_check_is_never_rounded_up_synthetic` gives an option perfect
recall and one unknown constraint, and asserts it is neither `meets` nor
recommended.

### Two defects I introduced and fixed

**An unasked-for constraint blocked every recommendation.** `latency_p95`
returned `couldnt_check: no constraints.latency.p95_ms was given` when the
user had not asked for latency at all — so run 1 produced no recommendation
even though every constraint it *did* ask for was met. A constraint nobody
requested is not a check that could not be made. All four evaluators now
return `None` when their constraint is absent (as `monthly_budget` already
did), `judge_option` filters them, and `overall([])` returns `couldnt_check`
so "no constraints" can never read as "everything passes".

**Indistinguishability was scoped to `meets` only.** Run 3's two baselines are
`couldnt_check` overall (latency), so neither was marked — and the brief's
expected "indistinguishable on recall" could not be produced. Indistinguish-
ability is a claim about *recall*, not about the overall outcome: two options
whose latency is unknown are still identical on recall, and a reader choosing
between them needs to know the recall column cannot separate them. Now scoped
to all non-`fails` contenders, with `fails` options excluded so a beaten
option is not compared as though it were still in the running.

Also: my HTML test's regex was greedy enough to run from a "not run" cell into
the embedded base64 image, producing a 2.8 MB assertion message. Tightened to
match only constraint cells and stop at the first `<`.

## Verification

**Passed**

- The three runs produce the outcomes above; the arXiv log is a correct
  account of task 008's table.
- `report.json` separates `measurement` from `judgement` per option.
- **No verdict is derived from a simulated latency**, asserted directly
  against a row carrying fake latency fields.
- couldn't-check is never rounded up: an option with one unknown constraint is
  never `meets` and never recommended, in both the rules and run 2.
- `manifest.yaml` produced in both workdirs, listing every input digest and
  its kind.
- `report.html` opens offline: no outbound references of any kind, well-formed,
  all eight tokens applied, calibration status stated in the footer.
- Families requested but not run are listed with their reason, never omitted.
- 173 tests pass. **`fixtures/` untouched.**

**Failed**

Nothing at the end. Two design defects and one test defect, all mine, all
above.

**Couldn't check**

- **How the HTML actually looks.** I verified it is well-formed, self-
  contained, token-applied and correctly worded, and I read the rendered text
  of each section — but I have no browser here, so nothing in this task
  confirms the *visual* result. Task 005 rendered PNGs and looked at them;
  this is the equivalent gap for HTML.
- **Whether a `meets` latency verdict works end to end.** The rule is unit-
  tested both ways, but no run in this task produced one, because this machine
  cannot attribute latency at all. The `meets` branch has never fired against
  a real `verify.json`.
- **The `environment` mismatch branch against real data.** Unit-tested; no
  workdir here has a verify run whose target differs from a constraint's.
- **Whether the ranking rule picks well.** `fewest constraints at margin, then
  storage, then fan-out` is implemented and tested, but run 1 had a single
  `meets` option so the ordering never had to choose.
- **`monthly_budget`** is `couldnt_check` by construction — there is no cost
  model until task 011, and nothing here estimates one.

## Observed, not done

- **Task 009 is uncommitted**, so this tree carries two tasks.
- **Run 2 shares run 1's workdir** and overwrites its `report.*`. I re-ran
  run 1 afterwards so the smoke workdir holds the run-1 outputs, but nothing
  in `report` prevents two constraint sets from clobbering each other's
  report in one workdir. A `--out` flag, or naming the report after the
  requirements file, would fix it.
- **`report.html` is 2.9 MB**, almost entirely the embedded ground view. Fine
  for a local file, awkward to email. A `--no-image` flag or a downscaled
  embed would cut it to ~30 KB.
- **The ground view is embedded regardless of whether it belongs to this
  run.** `docs/img/ground_b_copies.png` is the *arxiv-150k* ground; the smoke
  report embeds it too, captioned as "the ground". For the smoke run that
  picture is not this corpus. The brief says to embed variant B "when the run
  has a projection", and neither workdir records whether it has one — so this
  is a real mislabelling in the smoke report that wants either a per-run
  projection or a caption naming the fixture.
- **`rank_by` is not read from the requirements file.** The brief describes it
  as "the user's `rank_by` (default: ...)"; only the default is implemented.
- **Verdict reasons are English strings assembled in code.** Fine now;
  a second language or a machine consumer would want the parts separately.
- **The `at_margin` fraction (10%) is a constant with no measurement behind
  it**, unlike the calibration tolerance which at least comes from the fixture
  specs.
- **`_kind_of` re-reads the info files once per input file** — negligible at
  eight files, silly in principle.
- **The root `README.md` still does not mention `simulate`, `verify` or
  `report`** under "what exists today"; `oneground/README.md` mentions the
  first two but not `report`.

## Repo now contains

New:

    oneground/report/__init__.py        the command, decision log, manifest
    oneground/report/verdict.py         the rules, pure functions
    oneground/report/html.py            the self-contained page
    oneground/report/test_verdict.py    33 tests
    docs/design/tokens.md               the palette and the rules for it
    docs/design/tokens.css              inlined verbatim into every report
    tasks/010-report.report.md
    tasks/scratch/010-latency.yaml      run 2's requirements
    tasks/scratch/010-arxiv-log.txt     run 3's decision log, verbatim

Modified:

    oneground/cli.py                    `report` added
    requirements.smoke.yaml             constraints block (run 1)
    requirements.arxiv-150k.yaml        constraints block (run 3)

Written outside the repo (git-ignored `runs/`):

    runs/arxiv-smoke/{report.json,manifest.yaml,report.html}
    runs/arxiv-150k-via-characterize/{report.json,manifest.yaml,report.html}

Unchanged: `fixtures/` entirely, `corpora/`, `oneground/{characterize,intake,
measures,receipts,sample,truth,embed,fixture,models,simulate,adapters,verify,
pod}`.

### Dependencies added

None.

### Not committed

Nothing was committed — including task 009.

## Blocked on developer

Nothing was blocked.

Five things to decide:

1. **Task 009 is uncommitted and this tree now holds two tasks.** Splitting
   them after the fact means committing by path.
2. **The smoke report embeds the arXiv ground view**, captioned as its own.
   That is a mislabelling and it wants either a per-run projection or a
   caption that names the fixture.
3. **Two constraint sets against one workdir overwrite each other's report.**
4. **The brief's run-3 expectation ("both baselines meet") conflicts with its
   own overall-outcome rule** when latency is couldn't-check. I applied the
   rule; if the intent was that unaskable constraints should not sink an
   option, that is a different rule and a bigger decision.
5. **The `meets` branch of the latency verdict has never fired against real
   data**, and cannot on this machine — task 011's pod work is what will
   exercise it.
