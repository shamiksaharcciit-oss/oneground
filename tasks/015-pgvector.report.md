# Report: 015-pgvector

**Status: steps 1–4, 6 and 7 complete. Step 5 (the pod run) is prepared and
waiting on the developer's confirmation — see Blocked on developer.**

## Repo state expected vs found

Expected: worktree `..\oneground-012` on `task-015` from master ≥ `700b367`;
task 012's calibration work merged; `hash_sharded` and `semantic_sharded`
still non-deterministic; one adapter (`qdrant`).

Found exactly that, plus more of master than the brief mentions: `700b367` is
the merge of my own task 012, and master had also gained tasks 013 and 013b —
`oneground/environment.py` (the pinned-environment guard), `analogy.py` and
`capacity.py`. The guard matters for every command run here: it refuses to
compute when the interpreter is off the pins. It passes throughout
(`pinned: True`, numpy 2.5.3 / faiss 1.15.0 / scikit-learn 1.9.0), including
after `psycopg` was added to `requirements.txt`.

One assumption in the brief needed checking rather than accepting, and it did
not hold — see *Postgres on the pod* under Measurements. Nothing else deviated.

## What was done

**1. Carried from 012b.** Both sharded families build single-threaded by
default. Cost measured at three scales; byte-identity proven for each; the
arxiv-150k published values re-derived and still reproducing.

**2. `oneground/adapters/pgvector/`** via `psycopg` 3 against
`pgvector/pgvector:0.8.6-pg16`, with `ADAPTER.md` recording eight quirks and
what each cost.

**3. Conformance** passes live against both engines. `wait_for_index` and
`namespace_exists` are now required protocol methods rather than duck-typed
optional ones.

**4. Local two-engine verify** on arxiv-smoke; both rows in one `verify.json`
under one `environment_id`; the report issues a comparative latency verdict.

**5. Matched-environment pod run** — prepared, not run. Awaiting the
developer's `y`.

**6. Calibration** — pgvector's engine line is in `history.jsonl`; the report
cites both engines.

**7. Docs** — `ADAPTERS.md` gains pgvector and a table of every known way an
engine skips its index; `VERIFY.md` gains the two-engine procedure and, at
length, what "matched" does *not* guarantee.

## Measurements

### 1. Sharded determinism — the defect is real, and it is fixed

`hash_sharded` and `semantic_sharded` now build inside
`single_threaded_faiss`, the helper task 012b added for `single_node_hnsw`.
`semantic_sharded` wraps its **whole** build, not only the HNSW adds: k-means
is seeded, but its centroid update is a floating-point sum whose order OpenMP
does not fix, and a last-bit difference in a centroid moves a point across a
region boundary, which changes shard membership, which changes every graph
built from it. Region build order is also sorted rather than left to dict
insertion order.

Method: `tasks/scratch/015-sharded-determinism.py`, driving `MODEL.build`
directly, with a discarded warm-up build before each timing pair.

| family | corpus | n | parallel | deterministic | ratio | two deterministic builds identical | two **parallel** builds identical |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hash_sharded | arxiv-smoke | 2,000 | 0.64 s | 0.74 s | 1.15× | **yes** | yes |
| semantic_sharded | arxiv-smoke | 2,000 | 0.23 s | 0.24 s | 1.03× | **yes** | yes |
| hash_sharded | synthetic | 20,000 | 3.03 s | 8.62 s | 2.84× | **yes** | yes |
| semantic_sharded | synthetic | 20,000 | 6.94 s | 11.21 s | 1.62× | **yes** | yes |
| hash_sharded | glove | 200,000 | 144.11 s | 315.22 s | 2.19× | **yes** | **NO — 5.05% of ids differ** |
| semantic_sharded | glove | 200,000 | 87.35 s | 223.10 s | 2.55× | **yes** | **NO — 0.35% of ids differ** |

**The 200,000-vector row is the point.** At 2,000 and 20,000 two parallel
builds agree, so a test at those sizes proves nothing — which is exactly the
blind spot that hid the same defect in `single_node_hnsw` through the whole of
task 012. At 200,000 both families diverge. This was a real bug being fixed,
not a hole being closed on principle, and the difference is worth stating
because only the 200k row establishes it.

Shard membership was checked separately from returned ids: a family can return
identical ids and still have been lucky about which vectors landed where.
Membership is identical across deterministic builds for both families at every
size, including `semantic_sharded`'s 256 regions.

**Cost**: 1.03×–1.15× at 2,000, 1.62×–2.84× at 20,000, 2.19×–2.55× at 200,000.
Consistent with task 012b's finding on `single_node_hnsw` (1.76× at 1.18 M):
faiss's parallel HNSW add gets nowhere near a 4× speedup on four cores, so
single-threading gives back much less than the core count suggests.

### 1b. arxiv-150k still reproduces its published values

The check the brief asks for: does making the sharded models deterministic
move the numbers the fixture publishes? Method:
`oneground fixture verify arxiv-150k` against the 460 MB release asset at
`~/oneground-assets/arxiv-150k/`, which recomputes each published value with
the same functions the product path uses. Full log:
`tasks/scratch/015-arxiv-150k-fixture-verify.log`.

| value | recomputed | published | delta | tolerance | outcome |
| --- | --- | --- | --- | --- | --- |
| `semantic_sharded.recall_at_10` | 0.9318 | 0.932 | 0.0002 | 0.01 | **verified** |
| `semantic_sharded.storage_amplification` | 3.71516 | 3.715 | 0.00016 | 0.01 | **verified** |
| `single_node_hnsw.recall_at_10` | 0.9968 | 0.997 | 0.0002 | 0.01 | **verified** |
| intrinsic_dimensionality | 32.5533 | 32.55 | 0.00326 | 0.5 | verified |
| boundary_crispness | 0.0362467 | 0.036 | 0.000247 | 0.02 | verified |
| skew_top10_share | 0.0754 | 0.075 | 0.0004 | 0.02 | verified |
| ambiguous_query_rate | 0.8915 | 0.891 | 0.0005 | 0.02 | verified |
| drift (before / after) | 0.523212 / 0.551401 | 0.522 / 0.549 | 0.00121 / 0.00240 | 0.02 | verified |

**8 values verified, 0 contradicted, 0 couldn't-check.** Digests: 10 verified,
1 couldn't-check (`projection.npy`, not in the asset). The determinism change
did not move any published value.

### 2. The pgvector adapter

Pinned and resolved live from Docker Hub on 2026-09-11:

    image     pgvector/pgvector:0.8.6-pg16
    digest    sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b
    postgres  16.15 (Debian 16.15-1.pgdg12+2)
    pgvector  0.8.6
    client    psycopg==3.3.5 (+ psycopg-binary, tzdata), pinned

`0.8.6-pg16` is the newest pgvector 0.8.x built on Postgres 16 at the time of
resolution; the tag list also carried 0.8.5, 0.8.4, 0.8.3 and 0.8.2 on pg16.

**Two adapter defects found by running it, and what each cost.** Both were
mine, not pgvector's, and both would have made the engine look worse than it
is in the comparison the whole task exists to produce:

| defect | measured effect |
| --- | --- |
| `SET LOCAL hnsw.ef_search` inside a transaction per query — correct, and an extra round trip inside every *timed* query | p50 **19.49 ms → 11.25 ms** when moved to one `SET` per `search()` call with a `RESET` in a `finally` |
| psycopg 3 has no `mogrify`, so a first implementation fell back to one statement per row | ingest **535 → 1,942 vectors/s** with batched `INSERT ... SELECT FROM unnest(%s::bigint[], %s::vector[])` |

**And one "optimization" that is a trap.** The query sends the vector twice —
once in `SELECT` for the distance, once in `ORDER BY`. At 768 dimensions that
is ~9 KB of literal, twice. Ordering by the output alias instead removes half
of it:

| form | p50 | p95 | plan |
| --- | --- | --- | --- |
| expression repeated (kept) | 91.20 ms | 360.46 ms | `Index Scan using ..._hnsw` |
| `ORDER BY d` (alias) | 69.69 ms | 120.49 ms | **`Sort`** |

It is 25% faster, the answers are *exact*, and recall goes **up** — because
Postgres has stopped using the index and is sorting all 2,000 rows. Every
signal a careless reader would check says the change was an improvement.
`EXPLAIN` is the only thing that tells them apart. This is the third instance
of the same trap in this project (Qdrant's `indexing_threshold` in task 009,
the operator/opclass mismatch, and this), and `docs/ADAPTERS.md` now carries
all three in one table.

**Index build is synchronous** and is reported separately from ingest, because
Qdrant's equivalent happens in the background and the two "ingest rates" are
otherwise not the same quantity. `ef_search` is a session GUC and therefore
cannot appear in `describe()` — the receipt records what oneground *asked
for*, under `search_params`, never as an index property.

### 3. Conformance

All seven checks pass live against pgvector:

```
(a) created oneground-conf-b7379693-conformance
(b) upserted 5000 at 1,942/s
    indexed 5000/5000 in 0.0s
(c) recall@10 1.0000 >= 0.95
(d) describe: 5000 points, dim 64, index hnsw
    {'m': 16, 'ef_construction': 200, 'opclass': 'vector_ip_ops'}
(e) scrolled 100 vectors, all match
(f) namespace deleted
(g) namespace deleted after an exception
```

`recall@10 = 1.0000` is an easy problem, not a skipped index: `EXPLAIN
(ANALYZE)` reports `Index Scan using "..._hnsw"`, and the evidence is in
`ADAPTER.md` rather than in anyone's memory.

**8 passed** with both `ONEGROUND_QDRANT_URL` and `ONEGROUND_PGVECTOR_URL`
set; 6 passed / 2 skipped with neither, and a skip is reported as a skip.

**Two methods promoted to the protocol.** The brief's rule — *if a conformance
check needs an adapter-specific step, add it to the protocol as a required
method, not a special case* — applied to `wait_for_index`, and the same
argument applied to `namespace_exists`, so both moved. They were duck-typed
with `getattr` while Qdrant was the only adapter. pgvector is unready in a
completely different way:

| engine | how it is not ready | how you find out |
| --- | --- | --- |
| Qdrant | background indexing has not caught up | `indexed_vectors_count < points_count`; `status: green` does **not** mean indexed |
| pgvector | an interrupted build left the index `indisvalid = false`, or one is still running | `pg_index.indisvalid`/`indisready`; `pg_stat_progress_create_index` non-empty |

Both produce the same symptom — recall that looks perfect because the index
was never consulted — and an adapter that simply omitted the method would have
had that check silently skipped. `wait_for_index` for pgvector checks both
conditions the brief names. The stub, which is genuinely always ready, returns
`(points, points, 0.0)` and says so; that is a claim it makes, not a method it
omits. A new test asserts every registered adapter implements all nine
methods.

### 4. The local two-engine verify

`verify.engines: [qdrant, pgvector]` on arxiv-smoke, sequentially, one host,
one `environment_id` (`local:DESKTOP-HAGOPQC`), one `verify.json`.

| engine | recall@10 | RTT p95 | query p95 | rtt/query | latency attributable? | ingest/s |
| --- | --- | --- | --- | --- | --- | --- |
| qdrant 1.19.1 | 1.0000 | — | — | — | **no** — refused as environment noise | 560 |
| pgvector 0.8.6 | 1.0000 | 3.93 ms | 111.41 ms | **4%** | **yes** | 120 |

Under load (concurrency 8, 50 qps offered, 60 s):

| engine | p95 under load | sustained qps |
| --- | --- | --- |
| qdrant | 358.94 ms | 46.20 of 50 |
| pgvector | 1177.85 ms | 11.25 of 50 |

Both fail the 40 ms budget on this laptop, which is the expected result and
not the interesting one. The interesting one is that the report can now *say
which is better and why it is allowed to*:

```
[engine_comparison] single_node_hnsw[M=32,efConstruction=200,efSearch=128]:
  on latency_p95, qdrant is the better of 2 engines measured in environment
  local:DESKTOP-HAGOPQC -- qdrant 358.94 against pgvector 1177.85. Both were
  measured on the same sample, on the same host, sequentially, and both carry
  fails against the constraint
[engine_comparison] single_node_hnsw[M=32,efConstruction=200,efSearch=128]:
  on qps, qdrant is the better of 2 engines measured in environment
  local:DESKTOP-HAGOPQC -- qdrant 46.20 against pgvector 11.25. ...
```

and, where it cannot:

```
[no_engine_comparison] semantic_sharded[...]: latency_p95 was not compared
  across engines because fewer than two engines produced a value --
  qdrant (couldnt_check), pgvector (couldnt_check). A comparison here would be
  between a number and an absence
```

**Ingest is not a like-for-like number and the receipt says so.** pgvector's
120/s excludes a synchronous `CREATE INDEX`; Qdrant's 560/s excludes
background indexing that has not finished. Both halves are recorded and a
reader has to add them to compare.

**How the report changed to allow this.** Latency and qps are judged per
engine, so one architecture measured on two engines carries two latency
verdicts, each naming its engine. `overall()` folds by *constraint*, not by
verdict: a constraint is met if any engine meets it, fails only if every
engine that could be checked fails. That permissive direction is only safe
because the log names the engine every time — "meets on qdrant" is a fact,
"meets" alone is not — and `report.json` carries `engines_meeting` per option.

### 6. Calibration

| engine | version | efSearch | simulated − measured | tolerance | outcome |
| --- | --- | --- | --- | --- | --- |
| qdrant | 1.19.1 | 128 | +0.00000 | 0.05 | verified |
| **pgvector** | **0.8.6** | **128** | **+0.00000** | 0.05 | **verified** |

Both easy numbers: 2,000 vectors is small enough that HNSW is effectively
exact at efSearch=128, so both sides sit at 1.0. They confirm the mechanism
and resolve nothing about the simulator. The report footer cites both:

```
calibration:
  engine qdrant: last calibrated 2026-09-10 on arxiv-smoke as
    single_node_hnsw[M=32,efConstruction=200,efSearch=128] -- verified,
    deviation +0.00000 against tolerance 0.05
  engine pgvector: last calibrated 2026-09-10 on arxiv-smoke as
    single_node_hnsw[M=32,efConstruction=200,efSearch=128] -- verified,
    deviation +0.00000 against tolerance 0.05
```

**A third defect found by running it.** `calibrate engine` read
`ONEGROUND_QDRANT_URL` whatever engine it was calibrating, so calibrating
pgvector against an already-running instance would have pointed the run at
Qdrant's endpoint and written a line naming pgvector for a Qdrant number. It
now reads `ONEGROUND_<ENGINE>_URL`. The line written through the wrong
variable was dropped and re-measured through the right one.

### Postgres on the pod — the brief's option that does not work

The brief offers "the official binary tarball or an apt install into the pod —
no Docker — resolve which works and record it". Resolved against the package
indexes **before** any pod ran, because the obvious choice is wrong:

| source | postgresql-16 | pgvector |
| --- | --- | --- |
| Ubuntu 24.04 `universe` | 16.x | **0.6.0** |
| `apt.postgresql.org` `noble-pgdg` | **16.15**-1.pgdg24.04+2 | **0.8.6**-1.pgdg24.04+1 |
| EDB binary tarball | 16.x | **none — ships no extensions** |

Installing from Ubuntu's own archive would have produced a pod row measured
against pgvector 0.6.0 while every local row used 0.8.6, and **nothing in the
receipt would have said the comparison was invalid** — `describe()` would
simply have read one version in one place and another elsewhere. The EDB
tarball ships no extensions at all, so pgvector would have to be compiled
inside a billed session to arrive at the binaries apt installs in about a
minute.

`corpora/run_verify_pod.sh` therefore installs from PGDG, pinned to those
exact versions, matching the local compose file. No Docker: this is a package
install into the pod's own filesystem.

## Verification

**Test suite.** `python -m pytest -q`: **451 passed, 2 skipped** (was 449
before this task's changes; the two skips are the live RunPod test without a
key and one live-engine conformance test without its URL). No failures — the
`runs/` test that failed throughout tasks 012 and 012b now passes, because
this worktree has an arxiv-150k workdir.

**Conformance, live.** 8 passed with both engines reachable.

**Against the brief's acceptance list.**

- *"Step 1: both sharded models deterministic; costs reported; arxiv-150k
  reference values reproduce."* Yes to all three — tables above. Two
  deterministic builds are byte-identical at every size for both families;
  the parallel path is shown to diverge at 200,000 vectors, so the fix
  addresses a measured defect rather than a hypothesis.
- *"pgvector conformance passes live in Docker; stub in CI."* Yes. Live: all
  seven checks. Stub: runs on every machine with no Docker and no network, and
  a new test asserts every registered adapter implements the whole protocol.
- *"Two-engine `verify.json` from one pod; report issues a comparative latency
  verdict between two verified rows, or says why not."* **Partially.** The
  two-engine `verify.json`, the comparative verdict and the "why not" branch
  are all implemented and demonstrated — but from a **local** run, not a pod.
  The pod half is step 5 and is waiting on the developer.
- *"History has a pgvector line; report cites both."* Yes, both.

**Against the brief's "Do not" list.** No engine was ranked by anything not
measured in the same environment — the comparison refuses unless both rows
share an `environment_id` and both produced a value. Qdrant's adapter
behaviour is unchanged: the file is untouched except that its two existing
methods are now named in the protocol. Nothing was merged to master.

**Couldn't-check.**

- *Everything step 5 would establish*: pod RTT ratios, p95 under load at
  concurrency 32, sustained qps at 200, ingest and calibration per engine on
  150,000 vectors, and whether the report issues a comparative verdict between
  two rows that both carry `meets`. Not run.
- *Whether the PGDG install path works on a RunPod container.* Written and
  syntax-checked (`bash -n`), never executed. It is the most likely thing to
  fail in step 5.
- *Whether pgvector's numbers here reflect pgvector or this laptop.* The RTT
  guard admits pgvector's sequential latency (4%) and refuses Qdrant's, which
  is a statement about how much of each number was the path, not about the
  engines. A pod is what settles it.

## Observed, not done

**A nondeterministic native crash in the determinism harness.** Two runs of
`tasks/scratch/015-sharded-determinism.py` died with Windows exception
`0xC000070A` after the arxiv-smoke section, with no Python traceback; a third
and fourth ran to completion. A 20-build stress test that alternates
`deterministic=True`/`False` — the toggling `single_threaded_faiss` does —
survives cleanly and restores the thread count each time, so the toggling
itself is not implicated. Free memory was 0.2–0.4 GB during the failures.
Most likely memory pressure on a 7.5 GB machine, but that is a hypothesis, not
a measurement. **Recorded, not chased**: it did not affect any reported number
(every measurement in this report comes from a run that completed), and
diagnosing a native crash under memory pressure is not this brief.

**pgvector's query cost is dominated by text encoding, and there is a fix this
task did not take.** The vector goes over the wire as a text literal, twice per
query — ~18 KB per query at 768 dimensions. `pgvector-python` registers a
binary type handler for psycopg, which would send it as binary and cannot
change what is measured. It is a third dependency and it favours one engine's
numbers, so it wants to be a deliberate decision rather than something slipped
in during a comparison task. **Not done**; named here with the reason.

**No filtered search, for either engine.** pgvector's strongest argument
against a dedicated vector store is that a `WHERE` clause is just SQL.
oneground measures no filtered search for any engine, so the comparison this
task enables is narrower than the real choice a team faces, and `ADAPTER.md`
says so.

**Neither engine is tuned.** No `COPY`, no unlogged tables, no
`synchronous_commit=off`, no Qdrant gRPC path, no quantization — for either,
deliberately. This measures two default deployments on one host.

## Repo now contains

New:

    oneground/adapters/pgvector/adapter.py     the adapter
    oneground/adapters/pgvector/ADAPTER.md     eight quirks, each with its measurement
    oneground/adapters/pgvector/__init__.py
    oneground/verify/compose/pgvector.yml      pinned image + digest, host port 55432
    tasks/scratch/015-sharded-determinism.py   the step-1 measurement
    tasks/scratch/015-sharded-determinism.json/.log
    tasks/scratch/015-arxiv-150k-fixture-verify.log

Changed:

    oneground/adapters/base.py            namespace_exists + wait_for_index are
                                          protocol methods, with the reason
    oneground/adapters/conformance.py     pgvector; both methods required, not
                                          probed; a whole-protocol test
    oneground/adapters/stub.py            wait_for_index: always ready, and says so
    oneground/adapters/__init__.py        pgvector registered lazily
    oneground/models/hash_sharded/model.py       deterministic by default
    oneground/models/semantic_sharded/model.py   deterministic, whole build, sorted regions
    oneground/verify/__init__.py          per-engine compose/endpoints; run() loops
                                          over engines; verify.json gains `engines`
    oneground/verify/test_verify.py       reads the engines list
    oneground/report/verdict.py           Verdict.engine; engine_blocks;
                                          per-engine latency/qps; overall folds
                                          by constraint; engines_meeting
    oneground/report/__init__.py          compare_engines; log names the engine;
                                          footer cites every engine
    oneground/calibrate/__init__.py       ONEGROUND_<ENGINE>_URL; reads the block
    corpora/run_verify_pod.sh             PGDG install, pinned; engines conditional
    requirements.txt                      psycopg 3.3.5 + binary + tzdata
    requirements.smoke.yaml               two engines, per-engine endpoints
    requirements.arxiv-150k{,.pod}.yaml   two engines, pod endpoints
    docs/ADAPTERS.md                      pgvector; the three index-skip traps
    docs/VERIFY.md                        two-engine procedure; what matched is not
    calibration/history.jsonl             appended only

## Blocked on developer

**Step 5 needs one `y`, and about 40 minutes of local compute before that `y`
is actionable.**

`runs/arxiv-150k-via-characterize/` does not exist in this worktree — it is
gitignored, and the pod session spec is generated from it. `characterize` and
`simulate` have to run locally over the 150,000-vector release asset first.
I have not started that: it is 40 minutes of a memory-constrained laptop, and
if the pod run is not wanted it is 40 minutes for nothing.

Two things to weigh before spending:

1. **The PGDG install path has never run on a pod.** It is written,
   syntax-checked and pinned to versions confirmed present in the index, but
   an apt install inside a RunPod container is exactly the kind of step that
   fails for a reason nobody predicted — task 011 burned seven sessions on
   defects of that shape. If it fails, the session is spent.

2. **Caps are unchanged** at `max_hours: 1.0` / `max_usd: 2.00`. Two engines
   sequentially at 5 minutes each, plus a pgvector install and a 460 MB corpus
   extraction, will take longer than task 011's single-engine session (~9 min,
   ~$0.09). It should still be well inside the caps, but it is not the same
   size of session.

Say the word and I will run the local prep and hand over the exact
`oneground pod up` command. The typed `y` stays yours — nothing in this task
has created a pod, and `oneground pod up` remains the only thing that can.

**Total spend for this task so far: $0.**
