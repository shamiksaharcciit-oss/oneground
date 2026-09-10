# Report: T2-verdict-verified

## Repo state expected vs found

| the brief assumed | found |
|---|---|
| task 011 committed | yes — `d2e0d5e` and eight earlier 011 commits on `master`. |
| `report.json` holds 1 meets / 6 fails / 1 couldn't-check | yes, exactly. |
| recommended `single_node_hnsw[M=32,efConstruction=200,efSearch=128]` | yes. |
| environment `tf8sd2usxbblsm` | yes, and `verify.json` names the same pod — the export now asserts the two agree. |
| teaser at `620d06d`+ on master | yes; `8ba368b` (the T2-blocked report) was HEAD when I started, `ceee694` after the briefs landed. |
| `verify.json` beside the report | yes, with `verify_info.json`. |

Every number the brief quotes was checked against `verify.json` before being
used, and all of them hold: RTT baseline p95 6.987379 ms, sequential p95
7.17682 ms at 97.4% baseline share, under-load p95 38.216508 ms at 18.3%,
achieved 199.99 of 200.0 offered qps at concurrency 32, recall@10 measured
0.99935, calibration error −0.0018, ingest 2775.26 vectors/s, Qdrant 1.19.1.

**One number in the brief does not match the artifact.** The brief writes the
calibration line as *"measured 2026-09-10"*. `verify_info.json:run_at` is
`2026-09-09T23:00:40Z`, so the page renders **2026-09-09** — the date the
receipt carries. The two are the same instant: 23:00 UTC is 01:00 on the 10th
in UTC+2, and the developer's clock read the 10th. Every other timestamp on
this page and in this project is UTC (`built_at`, `generated_at`, `run_at`), and
a date on the page that did not trace to its source field is the one thing the
page must not have. Rendering the local date instead is a one-word change if
you prefer it.

## What was done

### 1. `--report-only` (`corpora/export_teaser_data.py`)

A new mode that rebuilds `values.json` from `--report` and `--verify` and
leaves the geometry alone. `--spec`, `--dir` and `--assets` became optional and
are required only for a full export; the failure message says which are missing
and points at `--report-only`.

It carries over every block of the existing `values.json` that came from the
fixture — `published`, `measured`, `receipt`, `geometry`, `base_bin`,
`categories`, `findings` — and rebuilds only `verdict` and `verify`. It also
records `geometry_from`: the `generated_at` and `generated_by` of the full
export whose geometry is still in the file, so the file says where its older
half came from.

`base.bin`, `queries.json` and `centroids.json` are digested before and after
and must be identical. If any moved, the run exits non-zero — the assertion the
brief asked for, made a gate rather than a printout.

**It also rewrites `inline.js`, which the acceptance criterion does not
mention.** `inline.js` is not a fifth source: it is those four files gzipped
for the `file://` path, and `values.json` is one of them. Left stale, the page
would show the **pre-verify** verdict — "Nothing recommended" — to anyone who
opened `index.html` by double-clicking, while showing the recommendation over
http. A page that states two different decisions depending on how it was loaded
is worse than a page with an extra file in its diff. `verify_teaser_data.py`
checks the bundle against the four files beside it and would have failed had I
skipped it. The brief's *Do not* list — don't re-derive `base.bin`,
`queries.json`, `centroids.json` — is satisfied exactly: those three are
byte-identical.

### 2. The fourth quoted decision-log entry

`QUOTED_LOG_KINDS` is now three kinds (`scope`, `indistinguishable`,
`recommendation`) plus `FOURTH_LOG_ENTRY`, a first-match-wins list:

    ("meets_environment", "latency_p95")    the sentence carrying the pod id
    ("to_resolve", None)                    the fallback, for an unverified run

Still four or nothing: if neither matches, the export exits non-zero naming
both candidates. On this report the fourth entry is now the `meets_environment`
one — *"…meets latency_p95 in environment tf8sd2usxbblsm: p95 38.22 ms <= 40.0
ms on runpod…"*.

### 3. `values.json` gained a `verify` block

Copied from `verify.json` (receipt) and `verify_info.json` (declared), nothing
recomputed and nothing rounded — the page formats, the file stores: pod id,
target, platform, run date, engine and version, namespace, index type and
params, RTT baseline (all percentiles), sequential latency with its
`rtt_share_of_p95` and its `couldnt_check` sentence, under-load latency with
its share and concurrency, qps (target, achieved, completed, offered, errors,
warm-up excluded), recall@10 measured, the calibration triple, ingest rate and
the index build.

`offered` (60,000) is the one derived number: `target_qps × duration_seconds`,
computed once in the export and stored with `offered_basis` naming the
derivation, so the page states it rather than doing arithmetic of its own.

Two guards: the export refuses if `verify.json` and `report.json` name
different `environment_id`s (the page would hang a latency number on the wrong
machine), and refuses if `report.json` recommends a config that is not among
its own options.

`verdict` also gained `recommended` (config, family, params, outcome, all five
constraints, full measurement, and the cost block) and `runner_up` (the option
named in `indistinguishable_from`, with each constraint it could not be checked
on and why).

**The monthly_budget addition.** `verdict.recommended.cost` carries the whole
cost entry — `monthly` 140.16, `monthly_low` 105.12, `monthly_high` 175.20,
`error_band` 0.25, `rendered`, `basis`, `kind`, `note` — plus the budget it was
judged against (`{amount: 1200, currency: EUR}`) and its source field. The
recommendation block prints it as the fifth constraint and states which end of
the band the verdict used: *"monthly_budget: €140 ± €35 — the verdict uses the
upper bound, €175, against a budget of €1,200."* followed by the estimate's own
kind, basis and the note that it is compute only.

### 4. The page

- **Heading is data-driven.** `verdict-h` is built from
  `families.length` and whether `recommendation` is null: `Three options. One
  recommended.` today, `Nothing recommended.` if a future run recommends
  nothing. The hardcoded sentence that went false when the verify landed cannot
  go false again.
- **The lede too**, and it now names **all five** constraints from their own
  thresholds: *"oneground judged 8 configurations across three architecture
  families against 5 constraints: recall@10 ≥ 0.95, storage ≤ 2.0×, p95 ≤ 40 ms
  at 200 qps / concurrency 32, sustains 200 qps, €1,200/month. One meets every
  constraint that could be checked."*
- **A recommendation panel**: the configuration, `built and measured on qdrant
  1.19.1 · runpod pod tf8sd2usxbblsm · Linux-… · 2026-09-09`, the two numbers
  that needed a real engine (p95 under load 38.22 ms, sustained qps 199.99)
  shown large with their sources on hover, then all five constraint verdicts
  with their source fields, then the cost sentence, then the runner-up line.
- **The runner-up line**: *"indistinguishable on recall from hash_sharded —
  couldn't check on latency_p95 and qps: this configuration was not the one
  verified — the verify run built hnsw in a single namespace, which is not a
  hash_sharded deployment…"*, with the config and source field beneath.
- **"the number this run existed to settle"**: RTT baseline p95 6.99 ms;
  sequential 7.18 ms at 97.4% baseline share (amber); under load 38.22 ms at
  18.3% (teal); then the rule, *"Single-client latency is unattributable on
  loopback; loaded latency is not."*, and a line explaining the 20% limit and
  that the recommendation rests on the loaded p95.
- **Footer calibration line**: *"Simulator vs Qdrant 1.19.1 on this corpus:
  −0.0018 recall@10 (simulated 0.99755, measured 0.99935), measured 2026-09-09,
  environment tf8sd2usxbblsm."*

## Measurements

### The report-only export

Method: `corpora/export_teaser_data.py --report-only --report
runs/arxiv-150k-via-characterize/report.json --out site/teaser/data/`.

| | |
|---|---|
| wall time | **2.7 s** against 56.8 s for a full export |
| vectors read | none — `vectors.npy` was not opened |
| `base.bin` | `08268d208c3d…` → `08268d208c3d…` **unchanged** |
| `queries.json` | `97289c3ab2ac…` → `97289c3ab2ac…` **unchanged** |
| `centroids.json` | `26cd059b1a05…` → `26cd059b1a05…` **unchanged** |
| `values.json` | `b2e005c2ed0a…` → `29c88d49ff72…` rewritten, 29,437 → 44,823 bytes |
| `inline.js` | `41afa73c1740…` → `d0dce51ca730…` rewritten, 4,697,985 → 4,701,157 bytes |
| `MANIFEST.sha256` | `b3ce5ba9a74e…` → `37455b6d710e…` rewritten |

Method for the digests: sha256 of each file on disk against `git show HEAD:<path>`
before the run.

### Load size

Method: `site/teaser/verify_teaser_data.py`.

| | before T2 | after |
|---|---|---|
| data over http | 4,491,847 | 4,507,233 |
| page (`index.html` + `app.js` + `style.css`) | 65,533 | 75,409 |
| **total over http** | 4.56 MB | **4.58 MB** |
| **total from `file://`** | 4.76 MB | **4.78 MB** |

Both under 5 MB.

### Layout — no section overlap

Method: `tasks/scratch/T1-bounds.js`, which reports any section whose
`scrollHeight` exceeds its own box or whose bottom crosses the next section's
top.

| viewport | ground | query | verdict | receipt | promise | document | overlaps |
|---|---|---|---|---|---|---|---|
| 1440×900 | 900 | 900 | 2667 | 1132 | 900 | 6784 | none |
| 1440×740 | 740 | 756 | 2667 | 1132 | 740 | 6320 | none |
| 1280×720 | 720 | 754 | 2926 | 1163 | 720 | 6568 | none |
| 1024×768 | 768 | 768 | 2925 | 1413 | 768 | 6909 | none |
| 390×844 | 1199 | 1454 | 4384 | 1920 | 347 | 9590 | none |

The verdict section grew from 1,428 px to 2,667 px at 1440×900 and the
document from 5,485 px to 6,784 px, which is what the recommendation panel,
the settle panel and five constraints per option cost. No section's content
escapes its own box at any of the five.

### Slider, console, requests, overflow

Method: `tasks/scratch/T1-browser-measure.js` over CDP, six runs, three per
load path, run one at a time. Each row is 82 frames.

| run | slider median | p95 | max |
|---|---|---|---|
| http, desktop | 10.5 / 9.2 / 8.1 ms | 20.1 / 18.9 / 13.4 | 28.5 / 52.7 / 24.4 |
| http, 390×844 dpr 3 | 8.3 / 6.9 / 8.7 ms | 14.7 / 11.8 / 15.7 | 30.4 / 12.9 / 60.2 |
| `file://`, desktop | 7.8 / 7.9 / 7.7 ms | 12.7 / 11.1 / 12.0 | 14.9 / 14.5 / 21.8 |
| `file://`, 390×844 dpr 3 | 7.3 / 8.1 / 7.2 ms | 10.8 / 10.9 / 10.7 | 33.4 / 12.2 / 12.7 |

**Worst frame across the six runs: 60.2 ms, against a 100 ms target**; every
median is under 11 ms. The slider does the same work it did before T2 — this
task changed nothing in the hot path — and the spread is the machine, not the
page: the laptop was down to about 350 MB free at one point, with headless
Chromes from earlier runs still resident. I killed those (only processes I had
spawned; the developer had no browser of their own running) and the numbers
tightened, which is the `file://` block above.

Time to first ground: `file://` 631 / 993 / 999 ms; http 3097 / 3687 / 4358 ms
against `python -m http.server`, which is single-threaded and slow with a
3.9 MB body and is not a static host.

Every run, both paths: **console empty, exceptions empty, no request
off-origin** (7 same-origin over http, 4 over `file://`), and
`documentElement.scrollWidth` 390 = `clientWidth` at 390 px.

## Verification

**Passed.** `site/teaser/verify_teaser_data.py` — every check: all five
digests, `base.bin` layout and monotone distances, storage amplification
3.7152 against published 3.715, boundary crispness 0.0362 against 0.036, p99
copies 4, the ε sweep at 0.00/0.20/0.40, all 2,000 queries' recall identity,
`inline.js` decompressing to the four files byte-for-byte, and load size under
5 MB on both paths.

**Passed.** The acceptance criteria, one by one:

- *Only `values.json` and its MANIFEST line changed in `site/teaser/data/`* —
  **with one stated exception**: `inline.js` also changed, necessarily, because
  it is a gzipped copy of `values.json` and three others. The three geometry
  files are byte-identical. See *What was done, §1*.
- *Heading reads `One recommended.`* — measured from the rendered DOM:
  `verdict-h` is `Three options. One recommended.`
- *Every number in the new panel and the footer traces to `values.json` with a
  source* — each of the three latency rows carries its `verify.json` field on
  hover; the two large recommendation numbers carry theirs; the cost sentence
  carries `report.json:costs[…]`; the calibration line is built from
  `values.verify.calibration` and `values.verify.date`.
- *No section overlap at the five viewports* — none, see above.
- *Slider still < 100 ms* — see above.

**Passed.** No `task` or `T1` in the rendered `document.body.textContent`, at
1440 and 390 px — the T2 additions did not reintroduce internal numbering.

**Couldn't check.**

- **Edge.** Everything was measured in headless Chrome over CDP. Edge is the
  same engine and the developer reviews there, but I did not drive it.
- **A real phone.** 390 px is CDP device emulation at dpr 3: right layout,
  right canvas size, not a touch device and not a phone's CPU.
- **That the verify numbers are correct.** This task copies `verify.json`
  faithfully and asserts it names the same environment as the report; it does
  not re-run the pod or re-measure latency. If the load generator was wrong,
  this page is wrong in exactly the same way, and says where to look.

## Observed, not done

- **The date discrepancy** in *Repo state* above: brief says 2026-09-10, the
  artifact says `2026-09-09T23:00:40Z`, page renders 2026-09-09.
- **The runner-up line says `latency_p95`, the brief says "latency".** I kept
  the constraint's actual field name, because every other verdict cell on the
  page names its field and a reader following the source line will look for
  `latency_p95`. One word, easily changed.
- **The `scope` decision-log entry undercounts.** It says *"judged against 4
  constraint(s): recall_at_k, storage_amplification, latency_p95,
  monthly_budget"* — `qps` is missing, though every option carries a `qps`
  verdict and the page's own lede names five. It is quoted verbatim in the log
  panel, so the page shows both numbers. That is a `report.json` matter, in the
  package, which this task must not touch.
- **The verdict section is now 2,597 px at 1440×900**, up from 1,428 px: the
  recommendation and settle panels, plus five constraints per option instead of
  three. Still no overlap and still collapsible, but it is the longest section
  on the page by a wide margin.
- **`costs` for the other seven options and `price_table` are in
  `values.json`** (`verdict.price_table`) but only the recommended option's cost
  is shown. Whether the losing options should show theirs is a product call.
- **Three streams still share `master`.** No collision this time.

## Repo now contains

Changed:

    corpora/export_teaser_data.py        --report-only, build_verify(),
                                         FOURTH_LOG_ENTRY, recommended/runner_up
    site/teaser/index.html               verdict markup, footer calibration line
    site/teaser/app.js                   data-driven heading and lede,
                                         buildRecommendation(), buildSettle()
    site/teaser/style.css                recommendation and settle panels
    site/teaser/data/values.json         verdict + verify, regenerated
    site/teaser/data/inline.js           the same four files, rebundled
    site/teaser/data/MANIFEST.sha256     three lines changed

New:

    tasks/T2-verdict-verified.report.md  this file
    tasks/scratch/T2-patch-export.py     the report_only/build_verify insertion
    tasks/scratch/T2-patch-verdict.py    the quoting rule and recommendation blocks
    tasks/scratch/T2-patch-page.py       the page patches

Unchanged, and asserted so: `site/teaser/data/base.bin`, `queries.json`,
`centroids.json`. No file under `oneground/`, `fixtures/`, `docs/`, `runs/`,
`models/`, `adapters/` or `policies/` was written; all were read only. No new
dependency.

## Blocked on developer

Nothing blocking. Three things only you can decide:

1. **The calibration date**: UTC `2026-09-09` as rendered, or the local
   `2026-09-10` the brief specified.
2. **Whether `inline.js` changing is acceptable** in a `--report-only` run, or
   whether you would rather the `file://` bundle be rebuilt by a separate
   command and left stale in between. I took the view that a page which states
   two different verdicts depending on how it was opened is not shippable.
3. **Edge and a real phone** before 16 September, as at the end of T1.
