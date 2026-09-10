# Report: 011-cloud-verify-cost

## Repo state expected vs found

Expected: tasks 009 and 010 committed, tree clean, HEAD naming task 010.
Found: exactly that. HEAD was `task 010: report, verdicts, decision log`, tree
clean. No deviation to report at the start.

One assumption in the brief did not hold, and it cost the first pod: task
009's own report had flagged `pywin32==312` as unconditionally pinned in
`requirements.txt`, and nothing had actioned it. `pip install -r
requirements.txt` cannot succeed on Linux with that line. Fixed on
instruction, with `; sys_platform == "win32"`.

## What was done

Steps 1–8 of the brief, plus eleven defects found by running it. The defects
are the substance of this task: the code was written in a few hours and the
eight pod sessions that followed found something real every time.

**Step 1 — carried fix.** `report.html` now draws only the run's own
`projection.npy` via `render_projection(workdir, char)`; the hardcoded
`GROUND_IMAGE` is gone, so a smoke report cannot show the arXiv ground.
Three tests.

**Step 2 — `verify.target: runpod`.** `oneground/verify/runpod.py` generates a
session spec and prints the commands. It creates nothing: `oneground pod up`
remains the only thing that can, and it still needs a typed `y`.

**Step 3 — load generator.** `oneground/verify/load.py`: closed-loop workers,
token bucket, warm-up excluded from the measurement, percentiles, error rate.
It never measures recall — recall comes from a separate sequential pass, so a
query slowed or dropped under load can never be counted as a recall miss.

**Step 4 — matched-environment mode.** The pod runs the engine's **release
binary**, not its container. Docker-in-docker needs `--privileged` and
RunPod's `POST /pods` has no way to ask: probed live, 33 accepted fields, none
of `privileged`, `capAdd`, `securityOpt`, `devices`, `sysctls`, `hostNetwork`.
The version matches the local compose pin (v1.19.1) so a pod run and a laptop
run measure the same engine.

**Step 5 — cost model.** `oneground/cost/`: `PriceTable`, `Cost` with
`.low`/`.high`, `size_and_cost()`, error bands, declared EU list prices in
`prices.example.yaml`. Budget verdicts use the **upper** bound. 16 tests.

**Step 6 — report wiring.** `qps_target()`, `monthly_budget_from_cost()`, and
the `environment_id` refusal inside `latency_p95()`.

**Step 7 — run it.** Eight pod sessions, ~$0.60 total. Seven failed; each
failure was a distinct real defect, and each is written up in `docs/VERIFY.md`
with its cause and fix. Zero pods left running after every session.

**Step 8 — `docs/VERIFY.md`.** Targets, the same-environment rule, the
native-binary decision, the load generator's boundaries, eight incident
records, two new rules, and the volume-first decision.

## Measurements

### The arXiv run — session 20260909-225058, pod tf8sd2usxbblsm

RTX PRO 4000, EU-RO-1, $0.57/hr confirmed and actual. 150,000 vectors, dim
768, 2,000 queries. All numbers from
`runs/arxiv-150k-via-characterize/verify.json`.

| | |
| --- | --- |
| ingest | 2,775 vectors/s (150,000 in 54.0 s, durable writes) |
| index | 150,000/150,000 fully indexed in 2.5 s |
| RTT baseline | p50 4.53 ms, p95 **6.99 ms** (empty collection, 50 pings) |
| recall@10 | **0.99935** |
| recall@100 | **0.99796** |
| achieved QPS | **199.99** of 200 offered, 59,999 queries, **0 errors** |
| p95 under load | **38.22 ms** (p50 22.75, p99 48.48, max 202.29), c=32 |
| calibration error | **−0.0018** (simulated 0.99755 − measured 0.99935) |
| session cost | ~$0.09 (9 min at $0.57/hr, estimate) |

**The RTT ratio, which is what the run existed to settle:**

| row | query p95 | RTT / query | |
| --- | --- | --- | --- |
| k=10 sequential | 7.18 ms | **97%** | refused |
| k=100 sequential | 6.64 ms | **105%** | refused |
| k=10 under load, c=32 | **38.22 ms** | **18.3%** | **attributable** |

The gate clears under load and does not clear sequentially. Method: `verify`
computes `rtt_p95 / query_p95` against a 20% limit and writes a
`couldnt_check` string in place of the shape when it fails.

Scaling 75× from the smoke fixture (2,000 vectors) moved the sequential ratio
from 113% to 97% — almost not at all, because the dominating term is the path
and the path did not change. That is now a rule in `docs/VERIFY.md`: **no
corpus size reachable on one pod makes single-client latency attributable.**

### Calibration — the first meaningful value

`calibration_error_recall = simulated − measured = 0.99755 − 0.99935 =
−0.0018`. The simulator under-predicted Qdrant by under two parts in a
thousand on this corpus at these parameters. Seeded as the first line of
`calibration/history.jsonl`.

### Cost

`size_and_cost()` over the price table, error band 0.25, headroom 0.70.
Budget verdicts take the upper bound: `monthly_budget=meets` for all eight
options against EUR 1200. The pod sessions themselves are the measured cost of
producing the evidence: **~$0.60 across eight sessions**, of which ~$0.09 was
the run that produced the decision and ~$0.51 was the seven that found
defects.

### The decision

```
8 option(s): 1 meets, 6 fails, 1 couldnt_check

Recommended: single_node_hnsw[M=32,efConstruction=200,efSearch=128]
  indistinguishable on recall from: hash_sharded[M=32,efSearch=96,shards=3]
```

`single_node_hnsw[M=32,efConstruction=200,efSearch=128]` is the only option
carrying a latency or throughput verdict, because it is the only one the
engine was actually built as. The other seven read
`couldnt_check: this configuration was not the one verified`.

with, in the log:

```
[meets_environment] single_node_hnsw[...] meets latency_p95 in environment
  tf8sd2usxbblsm: p95 38.22 ms <= 40.0 ms on runpod (environment
  tf8sd2usxbblsm) (from k=10_under_load: under load at concurrency 32).
    source: verify.json:searches[k=10_under_load].latency_shape_single_client.p95_ms

[meets_environment] single_node_hnsw[...] meets qps in environment
  tf8sd2usxbblsm: sustained the offered 200 qps at concurrency 32: 59999 of
  60000 queries in 300 s, short by 1 against a tolerance of 300 (one query
  per second of duration, the generator's tick), 0 errors. Achieved 199.99
  qps against a 200.0 target; this is a sustain check -- a throttled run
  cannot exceed what it was offered, so it is not a measurement of the
  engine's ceiling. See qps_max
    source: verify.json:load.completed
```

The six failures are all `recall_at_k` and `storage_amplification` on
`semantic_sharded`, from `simulate.json` — recall@10 between 0.5472 and 0.9318
against a 0.95 floor, and 2.67×–3.72× storage against a 2.0× cap.

## Verification

**Passed.** 303 tests, 1 skipped (the live RunPod test, skipped without a key).
Against the brief's acceptance list:

- *Smoke and arXiv pod sessions complete with zero pods left.* Yes — smoke
  session 20260909-220900 and arXiv session 20260909-225058 both reached
  `DONE`; `oneground pod ls` reported 0 pods after each.
- *arXiv `verify.json` has a latency verdict-capable row; report shows a
  latency verdict with the pod id in the log.* Yes — `k=10_under_load`, and
  the log entry above carries `tf8sd2usxbblsm`.
- *Cost appears with error bands; budget verdict uses the upper bound.* Yes,
  16 tests in `oneground/cost/test_cost.py`.
- *Cross-pod latency comparison is refused by test.* Yes,
  `test_a_latency_row_from_another_pod_is_refused_synthetic`.

**Failed, then fixed.** Seven pod sessions. Each is a dated incident record in
`docs/VERIFY.md` with cause and fix: pywin32 on Linux; a dirty tree reaching
the pod; shell operator precedence reporting a pid for a process that never
started; session env not reaching an sshd shell; `tar` ownership under
`set -e`; the workdir never reaching the pod; the corpus vectors never
reaching the pod; a string split destroying a completed measurement; outputs
landing beside the workdir rather than in it.

**Couldn't-check.**

- *Whether session 20260909-195824's traceback really named the arXiv workdir.*
  The committed `requirements.smoke.yaml` and session spec both say
  `runs/arxiv-smoke`, so nothing in the repo explains it. The pod and its log
  are gone. Most likely a conflation with session 20260909-194107, which did
  run the arXiv defaults.
- *Whether `qps_max` — the engine's ceiling — clears anything.* Not measured;
  a ramp is a different run. Documented in `verdict.py`, not implemented, by
  ruling.
- *Whether the price table's declared EU list prices are current.* They are
  `declared`, dated `as_of: 2026-09-11`, and the brief forbids fetching prices
  live.

## Observed, not done

**Resolved during this task, after being found.** One measurement was being
attributed to eight architectures, and seven of them had not earned it.

The pod built exactly one Qdrant index -- HNSW `m=32, ef_construct=200,
hnsw_ef=128`, per `verify_info.json:engine_facts.index_params`. That is
`single_node_hnsw[M=32,efConstruction=200,efSearch=128]` and nothing else. But
`latency_p95()` and `qps_target()` took `sim_row` only to name the option and
never checked whether the verified engine corresponded to it, so all eight
rows read `latency_p95=meets` and `qps=meets` off that single measurement --
six `semantic_sharded` rows and one `hash_sharded` row that were never built
in any engine. Until the load-row ruling landed every latency row was
couldnt_check, so the error was invisible; making latency answerable exposed
it.

Now: a measured row settles latency or qps only for the option whose
(family, params) match what the engine reported building. `index_params` is
the authority rather than `engine_params`, because the first is what the
engine says it built and the second is only what oneground asked for -- an
engine is free to clamp or ignore a request. `efSearch` is the exception and
is read from `engine_params.hnsw_ef`, because it is a query-time parameter
that Qdrant does not list in `index_params`; dropping it would have let a row
specifying `efSearch=64` claim a measurement made at 128, which is the same
defect in a subtler place.

Eight tests, including one that is **not synthetic**: it loads the real arXiv
workdir and asserts that exactly one of the eight simulated options can carry
the measurement, and that it is the one `engine_facts` names.

**One residual, not a defect but worth seeing.** The recommendation block
still reads:

```
Recommended: single_node_hnsw[M=32,efConstruction=200,efSearch=128]
  indistinguishable on recall from: hash_sharded[M=32,efSearch=96,shards=3]
```

`hash_sharded` is now `couldnt_check` overall, and the table shows that. The
claim is scoped to recall and recall genuinely is indistinguishable, sourced
from `simulate.json`. But a reader skimming the recommendation could take the
named runner-up as an equally-supported alternative when its latency and
throughput are explicitly unchecked. `mark_indistinguishable` includes
`couldnt_check` options by design -- they are still in contention -- so this is
the design working, not a bug. Whether the line should say which outcome the
runner-up carries is a presentation decision, not made here.

Smaller items:

Smaller items:

- `latency_shape_single_client` holds an under-load shape in the
  `*_under_load` rows. Renaming the field changes `verify.json` for every
  reader including the verdict rules, so it is recorded rather than changed
  quietly.
- `characterize` reads metadata and text that never reach the pod. Harmless
  today because `verify --on-pod` reads neither, and a future pod-side
  `characterize` would need them.
- Nothing consumes `calibration/history.jsonl` yet. One line is a
  measurement; a trend needs many.
- The smoke fixture's `verify.json` from task 009 was superseded by the pod's;
  the local one is preserved at
  `tasks/scratch/011-local-verify-superseded.json`.

## Repo now contains

New:

    oneground/verify/runpod.py            session generation, git_carries, corpus_inputs
    oneground/verify/load.py              closed-loop load generator
    oneground/verify/test_matched.py      65 tests: rules, load, preflight, rulings
    oneground/cost/__init__.py            price table, error bands, sizing
    oneground/cost/prices.example.yaml    declared EU list prices, as_of 2026-09-11
    oneground/cost/test_cost.py           16 tests
    corpora/run_verify_pod.sh             pod-side runner + corpus preflight
    requirements.arxiv-150k.pod.yaml      the file the POD runs (volume-first)
    calibration/history.jsonl             first calibration point
    calibration/README.md                 what a line means and when two compare
    docs/VERIFY.md                        285 -> ~700 lines

Changed:

    oneground/pod/cli.py         single post-create terminate guard; inputs;
                                 stale-record reconciler; extract destination
    oneground/pod/sshx.py        launch precedence; env in payload; one-archive
                                 upload; scaled timeouts; BatchMode
    oneground/pod/session.py     Input, input_size_cap_mb
    oneground/pod/api.py         PodApiError.status, is_gone()
    oneground/pod/state.py       launch record
    oneground/report/verdict.py  latency reads the row the constraint asks for;
                                 qps is a sustain check; a measurement settles
                                 only the configuration it was made on;
                                 qps_max documented
    oneground/report/__init__.py verify_info reaches the verdicts
    oneground/report/html.py     per-run projection; GROUND_IMAGE removed
    oneground/verify/__init__.py summary row keys and captions; generation output
    requirements.txt             pywin32 marked win32-only
    requirements.arxiv-150k.yaml requirements_on_pod, corpus tarball + manifest
    requirements.smoke.yaml      verify.target: runpod, latency constraint
    sessions/*.yaml              regenerated

## Blocked on developer

Nothing is blocked, and nothing is outstanding for me.

Two items are recorded for a future task rather than left open here:

1. **`qps_max`.** Documented in `oneground/report/verdict.py` and deliberately
   not implemented, by ruling. It needs a ramped load phase -- several load
   phases rather than one -- and therefore several more minutes of pod time
   per session. The engine's ceiling and the rate it sustained are different
   numbers and must never share a row.
2. **Whether the recommendation's runner-up line should carry its outcome.**
   See "Observed, not done". A presentation decision.

Settled by ruling during this task, recorded so the reasoning is not lost:

- Intake keeps accepting a single-client `p95_ms` constraint with no
  `at_qps`. Such a constraint yields `couldnt_check` on any hardware this tool
  runs on, which is honest; refusing it at intake was considered and declined.
