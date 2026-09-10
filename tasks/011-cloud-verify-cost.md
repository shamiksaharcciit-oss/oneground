# Task 011 — Cloud verify: matched environment, concurrency, cost

## Expected repo state
Tasks 009 and 010 committed (one commit is acceptable); tree clean.
Check HEAD's message names task 010; if not, say so first and continue.

## Step 1 — carried fix
`report.html` embeds the ground only from the run's own `projection`
(characterize must have produced one; add `--project` to characterize
using the fixture's UMAP params when the user asks). Otherwise the
characterization numbers panel. The smoke report must no longer show the
arXiv image. Test.

## Why
Local verify proved recall and produced a latency *shape*; Windows Docker
NAT made latency couldn't-check. This task puts client and engine in the
same environment on a pod, measures throughput at the requested
concurrency, and adds the cost model — the last inputs the report needs
for a full set of verdicts. The matched-environment run is also what a
user runs to compare two engines fairly.

## Do
2. **`verify.target: runpod`** — `oneground verify` generates a session
   spec for `oneground pod` (CPU pod, Docker available in the image;
   resolve a real image tag live and pin it), syncs the workdir sample +
   queries + ground truth, runs the engine(s) from the compose files and
   a load generator on the same host, fetches `verify.json` back.
   Confirmation prompt and caps as always. Session log carries RTT
   baseline first.
3. **Load generator** `oneground/verify/load.py`: closed-loop workers at
   `constraints.latency.concurrency`, target QPS via token bucket,
   `duration_minutes` from the requirements file, warm-up excluded.
   Reports achieved QPS, p50/p95/p99 under load, error rate, CPU% of the
   engine container (from `docker stats`), and ingest rate from the
   upsert phase. Recall is measured from the same client at k=10 on a
   separate sequential pass so load never affects recall accounting.
4. **Matched-environment mode**: `verify.engines: [qdrant, ...]` (only
   qdrant exists; the code path must handle a list) — each engine gets
   its own compose service on the same pod, run **sequentially**, same
   sample, same load profile; `verify.json` rows carry
   `environment_id = <pod id>` so the report's same-environment rule can
   match them. Two rows from different pods never get compared for a
   latency verdict; test that in `verdict.py`.
5. **Cost model** `oneground/cost/`: per option, `nodes × node_price ×
   hours/month`, where node sizing comes from `simulate.footprint`
   (est. memory + headroom from `constraints.memory_budget_gb` policy) and
   prices from a **provided table** (`cost/prices.example.yaml`: a few EU
   list prices with `as_of`, `kind: declared`). No live pricing API in
   this task. Every cost carries `error_band` from the requirements file
   (default 0.25) and appears in the report as `€X ± Y`. Budget verdicts
   use the upper bound.
6. **Report wiring**: latency/QPS verdicts from same-environment verify
   rows; budget verdicts from cost; decision log names the pod id for any
   latency verdict.
7. **Run it**: a pod session on smoke (fast; proves the path), then on
   arXiv-150k with Qdrant only, `concurrency 32`, `at_qps 200`,
   `duration_minutes 5`. The developer types `y` twice. Report: achieved
   QPS, p95 under load, RTT baseline, recall, ingest rate, the
   `calibration_error_recall` on arXiv (first meaningful value), cost of
   the session. Then `oneground report` on arXiv with the full constraint
   set — paste the decision log; latency should now be a verdict.
8. `docs/VERIFY.md`: targets, the same-environment rule, what the load
   generator does and does not measure, how a user runs the matched
   comparison against their own cluster (`existing`).

## Acceptance
- Smoke and arXiv pod sessions complete with zero pods left (`ls`).
- arXiv `verify.json` has a latency verdict-capable row; report shows a
  latency verdict with the pod id in the log.
- Cost appears with error bands; budget verdict uses the upper bound.
- Cross-pod latency comparison is refused by test.

## Do not
- Add engines. Fetch prices live. Raise caps beyond `max_hours 1.0`.
