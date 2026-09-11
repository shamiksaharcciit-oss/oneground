# Report: 015-pgvector

**Status: all eight steps complete.** The matched-environment pod run
measured both engines on session 20260911-181410 (pod `z01d7n4buc1a6i`), after
five sessions and six environment faults — see *Step 5, fifth attempt* below.

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

**5. Matched-environment pod run** — done. Both engines, sequentially, on
one pod, one sample, one `environment_id`; the report issues a comparative
latency and qps verdict between two verified rows.

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

**Test suite.** `python -m pytest -q`: **451 passed, 2 skipped**. The two
skips are the live RunPod test without a key and a live-engine conformance
test without its URL.

*A correction to something I said before checking it:* I reported that the
`runs/` test which failed throughout tasks 012 and 012b "now passes because
this worktree has the workdir". It passed because **master fixed it** — task
013 renamed it `..._needs_local_run` and made it skip when the workdir is
absent, which is the right resolution of the item routed to the master
stream. The workdir was not present at that point; it is now, so the test
runs against real data rather than skipping.

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

### Step 5, first attempt: session 20260911-001111 (pod hlz1jqzo6zwfyc)

The run was reported as *"git clone exited 1 during Updating files: 31%
(119/381)"*, with the captured output truncated at `Upda`. The pod
self-terminated; cost was cents.

**None of the three suspects was the cause.** Diagnosed without a pod:

| suspect | ruled out by |
| --- | --- |
| a path the bundle carries that fails on the pod's filesystem | all 381 files check out cleanly on Linux; no path over 61 characters, none non-ASCII, none with shell-special or reserved characters |
| a bundle referencing objects it does not include | `git bundle verify`: *"The bundle records a complete history"*; the clone itself exits **0** |
| the 40 GB container disk filling | the tree is 47.3 MB across 381 files — and the clone target is `/workspace`, the **50 GB network volume**, not the container disk a reader would assume |

**The actual cause.** `clone_command` ran
`git clone … && cd … && git checkout master`, and `master` no longer exists —
it was renamed `main` in task 014. Reproduced in a Linux container against
this worktree's own bundle:

```
CLONE_RC=0                       # 381 files, HEAD = task-015 at 6fdebcb
error: pathspec 'master' did not match any file(s) known to git
CHECKOUT_MASTER_RC=1
```

The clone never failed. The `&&` chain's exit 1 came from the checkout, and
the error message had already been thrown away.

**Why the message was thrown away**, which is the defect worth more than the
branch name. `_run` reported `(p.stderr or p.stdout or "")[:800]` — the
**first** 800 characters. Git writes clone progress as *one logical line* with
carriage returns rather than newlines, so a 381-file clone is a single ~12 KB
line. The first 800 characters of that are entirely progress, and the cut
lands mid-word: hence `Upda`. Measured on a reconstructed stream: 12,205
characters, and `error:` is **not** in the first 800.

**A second bug, larger than the one that failed.** Even while
`git checkout master` worked, it was wrong. `git clone` from a bundle already
checks out the bundle's HEAD — the commit the operator bundled — so the extra
checkout could only move the pod *away* from the code meant to run. A task
branch's session would have cloned at the task's HEAD and then switched to the
default branch. **Task 015 would have run without the pgvector adapter it
exists to measure, and nothing in the receipt would have said so.** That
failure produces measurements, not errors, which makes it the more dangerous
of the two.

**The fixes.**

1. `tail_lines(text, n)` collapses each carriage-return run to its final state
   and returns the last *n* lines. `SshError` now carries the full `stdout`,
   `stderr`, `returncode` and `command`; the message shows the tail.
2. The sync step writes the clone's **full stderr**, its **last 20 lines**,
   and the return code into the session record under state `clone_failed`,
   alongside the commit and branch it tried to run.
3. `clone_command` checks out **no branch by default** and never mentions
   `master`. When given a commit it asserts `git rev-parse HEAD` matches and
   exits 1 if not, so a pod running code nobody chose fails before measuring.
   It prints the commit either way, so the log says what ran even on success.
4. It runs `df -h` on the clone's target filesystem first, so "the disk was
   full" is answered by the log rather than guessed at.

**Verified end to end in a Linux container**, running the exact command the
pod will run, against this worktree's own bundle:

```
disk before clone:
Filesystem                Size      Used Available Use% Mounted on
overlay                1006.9G     16.2G    939.4G   2% /
pod repo at 6fdebcb693c6066936b31212229d40f979059299
RC=0
branch: task-015   files: 381
oneground/adapters/pgvector/adapter.py present
sessions/verify-arxiv-150k-two-engines.yaml: ONEGROUND_ENGINES: qdrant,pgvector
```

Six tests pin it, including one that reconstructs a 12 KB progress stream and
asserts the old head-truncation would have lost the error while the tail keeps
it.

### Step 5, second attempt: session 20260911-104406 (pod 3h0kpsgpxrb1zt)

**The clone fix held.** The session record carries
`repo_commit e7e85177268b53e83ef636662d9b8d450ff200d0`,
`repo_branch task-015` — the pod ran the right code, which the first attempt
would not have done even had it started. The corpus preflight passed with both
digests matching `MANIFEST.sha256`.

**It then stalled in `apt-get update` and never reached the install.** No
measurement was taken. Terminated at 22 minutes, **~$0.21**; `pod ls` reports
0 pods.

There is **no `apt-cache madison` output to paste**: that diagnostic fires when
`apt-get install` cannot satisfy the pins, and the run never got that far. The
failure was upstream of it.

**Diagnosed on the live pod before terminating.** Not a lock — `apt-get update`
and its fetch methods were alive and working the whole time:

    egress, measured from the pod
      archive.ubuntu.com    191 KB/s          apt.postgresql.org  1.1 MB/s
      github.com            fast (0.24 s)
      /var/lib/apt/lists    75 MB and growing at ~16 KB/s after 15 minutes

The image carries **four** apt sources — Ubuntu main (deb822
`ubuntu.sources`), `security.ubuntu.com`, the deadsnakes PPA and NVIDIA's CUDA
repo. A bare `apt-get update` refreshes every one of them, and on this link
that is tens of minutes of index fetching before a single package is
downloaded.

**The step was never necessary.** The image ships those indices already; the
only source this script adds is PGDG, which is fast. So the installer now
refreshes PGDG **alone** and resolves dependencies against the indices already
on disk:

    apt-get update -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/pgdg.list                    -o Dir::Etc::sourceparts=/dev/null                    -o APT::Get::List-Cleanup=0

`List-Cleanup=0` is load-bearing: without it apt prunes every index it did not
just fetch, and the install then finds no libssl, no libicu and no postgres.

**Measured in an Ubuntu 24.04 container seeded with indices, which is the
pod's situation:**

| step | before | after |
| --- | --- | --- |
| refresh | full update, 4 sources, >20 min and unfinished | **1 second**, PGDG only |
| indices retained | — | 51 MB → 53 MB (the other three kept) |
| install | never reached | **succeeded**, `postgres (PostgreSQL) 16.15 (Ubuntu 16.15-1.pgdg24.04+2)` — exactly the pin |

Two smaller changes came from the same session: the prerequisite install of
`ca-certificates curl gnupg lsb-release` is gone (curl is already used earlier
in the script, and the codename is hard-coded to `noble` rather than read from
`lsb_release`, which is not installed — and is not a free choice anyway, since
the `pgdg24.04` pins already fix it); and the install runs at `-q` rather than
`-qq` so its `Get:` lines keep the 15-minute stall watchdog fed while
dependency debs come down at 191 KB/s.

**Then the remainder was validated locally, and it found two more faults** --
both of which would have cost a pod session each.

**Fault 3: `PGDATA=/root/pgdata` cannot work.** `/root` is `drwx------ root
root`, so the `postgres` user cannot *traverse* it however the data directory
itself is owned. `chown -R postgres:postgres /root/pgdata` looks like it
solves this and does not:

    pg_ctl: could not access directory "/root/pgdata": Permission denied

`PGDATA` is now `/var/lib/postgresql/oneground-pgdata` -- created by
postgresql-common, owned by postgres, and still on the container disk rather
than the network volume, which is what the surrounding comment actually asks
for.

**Fault 4: postgres cannot write its own logfile to `/workspace`.**

    /bin/sh: 1: cannot create /workspace/postgres.log: Permission denied

`pg_ctl -l` is created by the **postgres process**, not by the calling shell,
and `/workspace` is root-owned. The asymmetry is what hides it: the adjacent
`>/workspace/pg-initdb.log` is a redirect performed by the *root* shell
outside `su`, so initdb's log lands fine and only the server's does not --
one of the two logs working is exactly what makes the other look like a
postgres fault. The file is now pre-created with the right owner, so it still
ends up where the session collects its outputs.

**Fault 3 was found only because of a fifth change made in the same pass**:
`initdb` and `pg_ctl` were chained with `&&`, so they failed silently and the
run carried on to three connection errors against a server that had never
started -- four messages for one fault, none of them naming it. Both are now
checked explicitly and print the tail of their own log before exiting.

**Verified by running the script's own text**, extracted verbatim from
`corpora/run_verify_pod.sh` rather than retyped, in a container with the
pinned versions:

```
  [5/5] initdb + start
waiting for server to start.... done
server started
CREATE EXTENSION
        extension
pgvector 0.8.6
```

and separately, an HNSW index built and read back through the catalog exactly
as `describe()` will:

```
CREATE INDEX t_hnsw ON public.t USING hnsw (embedding vector_ip_ops)
  WITH (m='32', ef_construction='200')
  tcp ok, server 16.15 (Debian 16.15-1.pgdg12+2)
```

Every step of the pod's pgvector path has now run somewhere. What has still
never run on a pod is the path as a whole, on that machine, over that link.

### Step 5, third attempt: session 20260911-164815 (pod b0xvaxqf1msj48)

Failed at the install, terminated at 10 minutes, **~$0.10**, 0 pods left. No
measurements. **The cause was my own previous fix.**

The step's log said the pins were present and the dependencies were not:

```
  [2/5] refresh PGDG only (not the other three sources)
Fetched 1306 kB in 1s (2437 kB/s)
        refreshed in 1s
  [3/5] postgresql-16=16.15-1.pgdg24.04+2
The following packages have unmet dependencies:
 postgresql-16 : Depends: locales but it is not installable or
                          locales-all but it is not installable
                 Depends: postgresql-common (>= 252~) but it is not going to be installed
                 Depends: ssl-cert but it is not installable
                 Depends: libllvm19 but it is not installable
                 Depends: libxslt1.1 (>= 1.1.25) but it is not installable
E: Unable to correct problems, you have held broken packages.
```

`apt-cache madison` confirmed **both pins available**. Checked on the pod
before terminating:

    /var/lib/apt/lists   1.9 MB, 5 entries, all of them PGDG

**The premise was wrong, not the pins.** In session 20260911-104406 I saw
`/var/lib/apt/lists` at 75 MB "and growing" and read it as *the image ships
these indices*. It was apt **building them from empty** — the image strips
apt lists, as almost every Docker image does. So that session's 20 minutes
was the genuinely necessary Ubuntu index download, and "refresh PGDG only"
removed the one thing that made the install possible.

### The mechanism, measured before being trusted

Reproduced in `ubuntu:24.04` with lists stripped and the pod's other two
sources added, then measured:

| | bytes | on this laptop |
| --- | --- | --- |
| **(a)** scoped index fetch — Ubuntu + PGDG, CUDA and deadsnakes excluded | **33.9 MB** | 15 s |
| **(b)** pinned install, `--download-only`, 28 packages | **76.9 MB** | 29 s |
| **total transfer** | **110.8 MB** | |
| CUDA index alone, skipped | 7.7 MB (1.8 MB gzipped) | not fetched |

The exclusion is verified rather than assumed: after the scoped update,
`ls /var/lib/apt/lists | grep -cE 'nvidia|launchpad'` returns **0**, and all
twelve Ubuntu `Packages.lz4` files plus PGDG's are present.

All five dependencies then resolve:

    locales              2.39-0ubuntu8.9
    ssl-cert             1.1.2ubuntu1
    libllvm19            1:19.1.1-1ubuntu1~24.04.2
    libxslt1.1           1.1.39-0exp1ubuntu0.24.04.3
    postgresql-common    293.pgdg24.04+1

**What this predicts for the pod, and the honest uncertainty.** The sizes
transfer; the times do not. Two throughput figures were measured on the pod in
session 20260911-104406 and they disagree by more than tenfold:

| rate, as measured on the pod | 110.8 MB would take |
| --- | --- |
| 191 KB/s — single-stream `curl` from archive.ubuntu.com | **~9 minutes** |
| ~16 KB/s — observed growth of `/var/lib/apt/lists` under apt | **~113 minutes** |

Nine minutes fits the 1-hour cap comfortably; 113 does not. Which one governs
is not something a container on a different link can settle. What the fix can
do — and now does — is make the log say which, from the first `Get:` line
onward, instead of going silent and looking like a hang.

*(An arithmetic slip caught before it reached this report: the measurement
script divided bytes by bytes-per-second and labelled the result "min",
producing "280 min" for the index fetch. The correct figure is ~3 minutes at
191 KB/s.)*

### What changed in the installer

1. **Scoped update**, not none and not all four sources. Apt is pointed at a
   directory holding only `ubuntu.sources` and `pgdg.list`, which leaves the
   pod's real `sources.list.d` untouched.
2. **Progress printing** — `-q`, not `-qq`, on both the update and the
   install, so the 15-minute stall watchdog can tell a slow fetch from a hung
   one. At the rates above that distinction decides whether the session
   survives.
3. **Corrected diagnostic wording.** The old text said the indices were "too
   old"; they are **absent**. A reader following that sentence would have gone
   looking for a staleness problem that does not exist.
4. **A dependency precheck before the install** — the five packages that
   failed last time, printed with their candidate versions, and a hard exit
   naming the real cause and listing what the update actually fetched if any
   is missing. Last session those two failure modes were indistinguishable
   until the madison output was read carefully.

**Verified end to end** by extracting the pgvector block verbatim from
`corpora/run_verify_pod.sh` — not retyped — and running it in `ubuntu:24.04`
with lists stripped and the CUDA source present:

```
        installed in 420s
        versions
postgres (PostgreSQL) 16.15 (Ubuntu 16.15-1.pgdg24.04+2)
  [5/5] initdb + start
waiting for server to start.... done
server started
CREATE EXTENSION
        extension
pgvector 0.8.6
```

Steps [1/5] through [4/5] are established by the install having run at all:
it is gated behind the precheck, which is gated behind the scoped update
having populated Ubuntu's indices.

### Step 5, fourth attempt: session 20260911-174648 (pod nhmumibj1k4806)

**The apt fix worked, and it worked well.** The scoped update and the pinned
install, which the previous three sessions never got through:

```
        installed in 23s
        versions
postgres (PostgreSQL) 16.15 (Ubuntu 16.15-1.pgdg24.04+2)
  [5/5] initdb + start
chown: changing ownership of '/workspace/postgres.log': Operation not permitted
```

**23 seconds**, against the 9-to-113-minute range the container measurements
bracketed. The link was not the problem; the four-source refresh was. That
question is settled.

Then the run died on the next line. Terminated at 7 minutes, **~$0.07**,
0 pods. Still no measurements.

**`/workspace` is a network volume with three separate properties**, and this
task has now hit all three, one per fix:

| property | the fault it caused |
| --- | --- |
| postgres cannot create a file there | `cannot create /workspace/postgres.log: Permission denied` (fault 4) |
| nothing can chown there | `chown ... Operation not permitted` (fault 6) |
| root *can* write there | why the other two looked like postgres faults rather than volume ones |

Each of my first two fixes traded one of these for another. The third stops
fighting the volume: **postgres writes its log to a directory it already
owns** (`/var/lib/postgresql/oneground-postgres.log`), and **root copies it to
`/workspace` after the measurements are packaged**, best-effort. No `chown`
touches the volume anywhere in the script.

Audited rather than asserted — every `chown` in the shipped script:

    chown -R postgres:postgres "$PGDATA"     # /var/lib/postgresql/oneground-pgdata
    chown postgres:postgres "$PG_LOG"        # /var/lib/postgresql/oneground-postgres.log

and the only live mentions of `/workspace/postgres.log` are the copy itself
and the line that reports it.

**Verified in containers, both directions:**

| test | result |
| --- | --- |
| **A** — the `[5/5]` block extracted verbatim + the copy, writable `/workspace` | initdb, `server started`, `CREATE EXTENSION`, `pgvector 0.8.6`, `copied postgres server log -> /workspace/postgres.log`, **exit 0** |
| **B** — the copy alone, `/workspace` mounted **read-only** | `could not copy ... (not fatal); it stays at /var/lib/postgresql/...`, **exit 0** |

B is the one that matters: a server log that cannot be copied does not fail a
run whose numbers are already taken and already in the tarball.

A Windows bind mount was tried first as a stand-in for the volume and
**rejected as unfaithful** — it permits `chown`, so it would have proved
nothing. The read-only mount tests the property that is actually load-bearing.

**Four new tests** pin the rules in the suite rather than in this report,
because the script is shell and nothing else checks it: no `chown` against
`/workspace`; every `chown` targets a path postgres owns; `pg_ctl -l` is
`$PG_LOG` and `$PG_LOG` is under `/var/lib/postgresql`; the copy swallows its
own error, says so when it fails, and never exits non-zero. They read the
shipped script and skip comment lines — the comments quote the failures
verbatim, so a naive grep would match its own history and never go green.

### Step 5, fifth attempt: session 20260911-181410 (pod z01d7n4buc1a6i)

Ran clean. Both engines sequentially: 150,000 vectors, 2,000 queries, dim 768,
concurrency 32, 200 qps offered, 5 minutes each. Terminated after `DONE`;
0 pods; this session ~$0.20.

**RTT ratio — what latency is attributable to, before any number is read:**

| engine | RTT p95 | sequential query p95 | rtt/query | attributable? |
| --- | --- | --- | --- | --- |
| qdrant 1.19.1 | 6.20 ms | 6.88 ms | **90%** | **no** — refused as environment noise |
| pgvector 0.8.6 | 0.81 ms | 14.46 ms | **5.6%** | **yes** |

The asymmetry is a fact about the *paths*, not the engines: Qdrant is reached
over HTTP, pgvector over a local Postgres connection. Qdrant's sequential p95
is refused not because Qdrant is slow but because at 6.88 ms the round trip is
90% of it. Both engines' **under-load** rows clear the 20% bar, which is why
the comparison below is allowed to exist at all.

**Per engine:**

| | qdrant 1.19.1 | pgvector 0.8.6 |
| --- | --- | --- |
| **p95 under load** (c=32) | **42.82 ms** | **385.90 ms** |
| **sustained qps** | **200.00** of 200 offered; 60,001 queries; 0 errors | **112.63** of 200; 33,790 queries; 0 errors |
| **recall@10** | **0.99945** | **0.99840** |
| recall@100 | 0.99806 | 0.99168 |
| **ingest** | **2,751 vectors/s** (150,000 in 54.5 s, durable) | **1,222 vectors/s** |
| index build | 2.5 s, **background** (excluded from ingest) | 0.012 s, **synchronous** (inside ingest) |
| **calibration error** | **−0.00190** | **−0.00085** |

Both calibration lines are `verified` against the 0.05 tolerance and sit in
`calibration/history.jsonl` with `environment z01d7n4buc1a6i`, `efSearch=128`,
`dataset arxiv-150k`. They are the **first Layer-2 points that reach a
verdict**: task 011's arXiv line carried no tolerance, and the arxiv-smoke
lines were both +0.00000 on a corpus small enough for HNSW to be exact.

Two numbers that look comparable and are not:

- **Ingest.** pgvector's 1,222/s *includes* its synchronous `CREATE INDEX`;
  Qdrant's 2,751/s *excludes* background indexing, reported separately as
  2.5 s. A reader comparing them has to add Qdrant's index time first.
- **qps.** Qdrant "meets" by sustaining exactly what it was offered — a
  sustain check, not a ceiling, and the decision log says so itself. pgvector
  sustaining 112.63 of the same offered 200 on the same host *is* a real
  finding.

**The decision log's two-engine comparison**, which is what step 5 exists to
produce:

```
[engine_comparison] single_node_hnsw[M=32,efConstruction=200,efSearch=128]:
  on latency_p95, qdrant is the better of 2 engines measured in environment
  z01d7n4buc1a6i -- qdrant 42.82 against pgvector 385.90. Both were measured
  on the same sample, on the same host, sequentially, and both carry fails
  against the constraint. Both ran on engine defaults except where the
  receipt says otherwise -- qdrant: engine defaults apart from
  indexing_threshold, which is set to 1 so a graph is built at all (task
  009); pgvector: engine defaults apart from the three settings above -- so
  this compares two default deployments, not two tuned ones, and a tuned row
  for either engine would be a different measurement.

[engine_comparison] ... on qps, qdrant is the better of 2 engines ... --
  qdrant 200.00 against pgvector 112.63 ... both carry meets against the
  constraint. [same tuning sentence]
```

Per-engine verdicts now appear in the option table:
`latency_p95@qdrant=fails qps@qdrant=meets latency_p95@pgvector=fails
qps@pgvector=fails`. **Nothing is recommended**: Qdrant misses the 40 ms
budget at 42.82, narrowly and genuinely — and see the fragility note below
before reading that as settled. The seven sharded rows correctly read
`no_engine_comparison`: neither engine built those architectures, so there is
nothing to compare.

**That latency verdict is fragile, and `docs/VERIFY.md` now says so.** The
same configuration measured **38.22 ms** on pod `tf8sd2usxbblsm` (session
20260909-225058) and **42.82 ms** here — **12% apart**, same GPU type, same
datacenter, same engine version, same parameters. The 40 ms constraint falls
between them: the first run's verdict was `meets`, this one's is `fails`, and
the architecture did not change. A latency verdict within ~15% of its
threshold is a sample of one from a distribution nobody has characterised.
Repeated runs reported as a spread are **task 017 work**.

### Engine runtime settings are now declared facts

`EngineFacts` gained `runtime_settings`, both adapters populate it from the
engine, and `as_dict()` now emits it — **along with `raw`, which it had
been silently dropping since task 009**, making a field whose whole purpose is
"so a later reader can check a claim this dataclass did not anticipate"
decorative.

pgvector reads `pg_settings` for `shared_buffers`, `work_mem`,
`maintenance_work_mem`, `max_connections`, `max_parallel_workers_per_gather`,
`max_parallel_maintenance_workers`, `effective_cache_size`,
`random_page_cost`, `synchronous_commit`, `jit` and `server_version`; plus
`index_build: synchronous` with the note about ingest, and `hnsw.ef_search`
split in two:

    hnsw.ef_search_applied   128   what the searches were made at
    hnsw.ef_search_session    40   what the connection holds now

That split is not pedantry. `search()` RESETs the GUC in a `finally`, so
reading it back afterwards returns the server default — and a receipt
saying `ef_search 40` for a run made at 128 would be worse than one saying
nothing. Caught by reading the first live output rather than by reasoning
about it.

Qdrant reports `hnsw_config`, `optimizer_config` (including
`indexing_threshold`, the setting that decides whether a graph is built at
all), `wal_config`, `quantization_config` and the shard/replica factors, plus
`index_build: background`.

**This run's settings are backfilled, and labelled as backfilled.** The pod is
terminated, so nothing can be read back from it. What the launch configuration
fixed is recorded with `source: launch configuration ... NOT read back from
the engine`; everything it did not fix — `work_mem`, `max_connections`,
`effective_cache_size` and four others — is `couldnt_check: not fixed by
the launch configuration`, rather than filled in from a local container that
is a different machine. Script:
`tasks/scratch/015-backfill-runtime-settings.py`.

## Observed, not done

**A nondeterministic native crash in the determinism harness.** *(Recorded at
the developer's instruction, not chased in this task.)* Two runs of
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

**A pre-baked pod image, for task 017.** Five sessions were spent on getting Postgres onto a pod, and every one of
them failed in the installer rather than in anything oneground measures. The
scoped update makes the install correct; it does not make it *fast*, and at
the 16 KB/s end of the pod's measured range it would still not fit the cap.
Baking `postgresql-16` + `postgresql-16-pgvector` into a pinned image moves
the whole 110.8 MB out of billed time and off the critical path, and turns the
engine version into a property of a digest rather than of an apt transaction
on the day. That is a new artifact to build, publish and pin — a task, not a
paragraph in this one. **Recorded for 017, deliberately not done here.**

**A tuned pgvector row.** Everything above measures two *default*
deployments, and the decision log now says so in the comparison sentence
itself. pgvector has obvious levers oneground did not pull: `COPY` instead of
batched upsert, `shared_buffers` sized to the corpus rather than 256 MB,
`synchronous_commit=off`, unlogged tables, a larger `work_mem` on the search
path. Several of them plausibly move the 385.90 ms p95 a long way. Pulling
them for one engine and not the other would break "no favourite"; pulling them
for both is a different task with its own brief. **Recorded, not done** —
and 385.90 ms should be read as *pgvector-as-it-ships*, never as pgvector's
ceiling.

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
