# Verify — measuring a real engine

Simulation predicts. `oneground verify` measures: it ingests the sample
`characterize` drew into a real engine, asks it the same queries `simulate`
scored, and reports what actually happened.

Three targets, and the difference between them is what a latency number is
worth.

| target | where the engine runs | what it can settle |
|---|---|---|
| `local` | a container on your machine | recall, ingest; latency **only if the path is quiet** |
| `runpod` | a pod, with the client beside it | recall, ingest, latency, **throughput** |
| `existing` | a collection you already have | recall as a **lower bound**, read-only |

---

## The same-environment rule

> **A latency or throughput verdict may only come from a measurement taken in
> the environment the constraint targets.**

Every `verify.json` carries `environment_id`: the pod id for a
matched-environment run, or `local:<hostname>` off a pod. A constraint may
name one:

```yaml
constraints:
  latency:
    p95_ms: 40
    at_qps: 200
    concurrency: 32
    environment_id: abc123pod
```

`verdict.latency_p95` and `verdict.qps` refuse any row whose `environment_id`
is not the one named, and say so:

> `couldnt_check: measured in environment pod-B, constraint targets pod-A.`
> `Latency rows from different environments are never compared: they are`
> `different machines.`

Two pods are two machines with two sets of noisy neighbours. Comparing their
p95 compares the hosts, not the engines. `local:<hostname>` is deliberately
not comparable to anything: two laptops both called "local" are still two
laptops.

There is a test for the refusal, because it is the rule most likely to be
quietly dropped for convenience.

### Why `local` usually cannot settle latency

Task 009 measured this laptop against a container: the empty-collection round
trip p95 was **132% of the query p95**. The path *was* the measurement. So
`verify` computes an RTT baseline of 50 pings against an empty collection
before every run, and if that baseline's p95 exceeds 20% of the query p95 it
reports

> `couldnt_check: environment noise`

for latency while still reporting recall, which noise cannot move. The measured
numbers are kept under `latency_measured_but_not_attributable` rather than
discarded — they are real, they are just not about the engine.

---

## The matched-environment run

```yaml
verify:
  target: runpod
  engines: [qdrant]          # a list; only qdrant has an adapter today
  duration_minutes: 5
  cost:
    prices: oneground/cost/prices.example.yaml
    error_band: 0.25
```

```
oneground verify requirements.yaml        # writes a session spec, creates nothing
python -m oneground.pod plan sessions/verify-<run>.yaml
python -m oneground.pod up   sessions/verify-<run>.yaml     # asks for a typed y
python -m oneground.pod watch <id>                          # DONE -> fetch -> terminate
```

`oneground verify` with `target: runpod` **prepares and stops**. It writes the
session spec, prints the commands, and creates nothing. `oneground pod up` is
still the only thing that can create a billable resource, and it still needs a
typed `y` at a terminal — see [POD.md](POD.md). There is no `--yes` here
either.

### Decision: the pod runs the engine's release binary, not its container

*Recorded 11 September 2026, task 011.*

**Context.** Locally, `verify --target local` starts the engine from
`oneground/verify/compose/qdrant.yml` with a pinned image. The obvious design
for the pod target was to do the same there: same compose file, same image,
one code path.

**The constraint.** A RunPod pod is itself a container, and running Docker
inside a container needs `--privileged`. RunPod's create API has no way to ask
for it — measured, not assumed. `POST /pods` accepts **33 fields**, and none of
them is:

```
  privileged     NOT PRESENT
  capAdd         NOT PRESENT
  securityOpt    NOT PRESENT
  devices        NOT PRESENT
  sysctls        NOT PRESENT
  hostNetwork    NOT PRESENT
```

(`tasks/scratch/011-privileged-probe.py`, run against the live API.)

**The decision.** The pod fetches Qdrant's official Linux release binary and
runs it natively:

```
qdrant-x86_64-unknown-linux-gnu.tar.gz   from release v1.19.1
```

**Why this is not a compromise.** The binary is pinned to the *same release*
the local compose image is pinned to — `qdrant/qdrant:v1.19.1` and the v1.19.1
binary — so a pod run and a laptop run measure the same engine build. Both move
in lockstep with `qdrant-client==1.19.0`, for the reason in
[the adapter's notes](../oneground/adapters/qdrant/ADAPTER.md): the client
refuses to vouch for a server more than one minor version away.

**What it costs.** Two ways of starting the same engine, kept in step by hand.
When the image tag moves the binary version must move with it, and nothing
checks that automatically. That is the price of the constraint, written down
here so whoever changes one knows to change the other.

**What was rejected.** Asking RunPod for privileged pods (not offered). Using a
different provider (out of scope — no engine of our own means no cloud of our
own either). Running the engine on the laptop and the load generator on the pod
(that reintroduces the network path this target exists to remove).

Engine storage goes on the container disk, never the network volume. An
engine's storage on a network mount measures the mount — the same lesson task
006 learned when a venv on `/workspace` took thirty minutes to populate.

---

## What the load generator measures

`oneground/verify/load.py`. Closed-loop: N workers issuing queries
concurrently against a token-bucket rate limit, for a fixed duration, warm-up
excluded.

| reported | meaning |
|---|---|
| `achieved_qps` | completed queries / measured seconds |
| `latency_under_load` p50/p95/p99 | **a different quantity** from the single-client shape |
| `error_rate` | failed / attempted |
| `engine_cpu_pct` | the engine process's CPU, sampled while under load |

### What it does not measure

**Recall.** Deliberately. Recall comes from a separate **sequential** pass, so
a query dropped or slowed under load can never be counted as a recall miss.
Mixing them would let a saturated server look like a bad index. There is a
test that no recall key appears in a load result.

**The engine's maximum throughput.** A closed-loop generator with N workers
measures what N clients get, not what the server could do with more. When
`achieved_qps` falls well short of the target the row carries a `shortfall`
note saying the bottleneck could be the engine, the client, or the host they
share — and that this generator reports it rather than diagnosing it.

**Anything at a different concurrency.** Throughput at concurrency 32 says
nothing about concurrency 8, so a constraint specifying one and a row measured
at another is `couldnt_check`, not an approximation.

---

## Comparing two engines fairly

`verify.engines: [a, b]` runs each engine **sequentially on the same host**,
with the same corpus, the same query set, the same index parameters, the same
concurrency and the same duration.

```yaml
verify:
  engines: [qdrant, pgvector]
  endpoints:
    qdrant: http://localhost:6333
    pgvector: postgresql://oneground:oneground@localhost:55432/oneground
  engine_params:
    m: 32
    ef_construct: 200        # Qdrant's name
    ef_construction: 200     # pgvector's name, same value
    hnsw_ef: 128
    indexing_threshold: 1    # Qdrant only; pgvector has no equivalent
```

One `engine_params` block serves both engines, which is what makes the two
rows comparable rather than two different indexes measured side by side.
Each engine is brought up, measured, and torn down before the next one starts.

`verify.json` holds an `engines` list. **No engine is promoted to the top
level**: a file with a primary engine and an also-ran would be picking a
favourite in the format itself.

### What "matched" guarantees

- **Same host.** One machine, one kernel, one set of cores and one disk.
- **Same client.** The same `verify` process, the same Python, the same
  load generator, the same client-side timing code.
- **Same sample and same queries.** Byte-identical inputs from one workdir.
- **Same `environment_id`.** Which is what lets the report compare the rows
  at all — see the same-environment rule above.
- **No mutual contention.** They never run at the same time, so neither
  number contains the other's load.

### What "matched" does **not** guarantee

- **Nothing about behaviour under a shared load.** Sequential is the honest
  way to compare, and it is also a different question from "what happens when
  both run on one box". This project does not answer the second one.
- **That the engines were configured equivalently in any deeper sense.**
  `m` and `ef_construction` mean the same thing in both; almost nothing else
  does. pgvector's ingest excludes a synchronous `CREATE INDEX` that Qdrant
  does in the background, so the two ingest rates are not the same quantity
  unless the index build is added — the receipt carries both halves.
- **That either engine was tuned.** Neither is. `COPY`, unlogged tables,
  `synchronous_commit=off`, Qdrant's gRPC path, quantization: all absent, for
  both, deliberately. This measures two default deployments on one host.
- **That the client is not the bottleneck.** The RTT-ratio guard is what
  answers that, per engine, per row. On this laptop it refused Qdrant's
  sequential latency and admitted pgvector's, which is not a statement about
  the engines — it is a statement about how much of each number was the path.
- **That a faster engine here is faster for you.** Different corpus,
  dimensionality, hardware and query mix all move it. The fixture is the
  instrument, not the answer.

### What the report may say about two engines

Latency and throughput are judged **per engine**, so one architecture
measured on two engines produces two latency verdicts, each naming its
engine. A constraint is met if any engine meets it and fails only if every
engine that could be checked fails — and the decision log names the engine
every time, because "meets on qdrant" is a fact and "meets" alone is not.
`report.json` carries `engines_meeting` per option: the engines on which that
architecture cleared every engine-scoped constraint.

The comparative entry fires only when the same configuration was verified on
more than one engine, in the same environment, and both produced a value.
Otherwise the log says why no comparison was made. A missing comparison and
an unfavourable one look identical if only the favourable ones are printed.

Two adapters exist today. The code path takes a list and refuses an unknown
engine by name, so adding a third is an adapter and nothing else — see
[ADAPTERS.md](ADAPTERS.md).

---

## Against your own cluster

`target: existing` measures a collection you already run, read-only:

```yaml
verify:
  target: existing
  endpoint: https://qdrant.internal:6333
  credentials_env: QDRANT_API_KEY      # the NAME of an env var, never a key
  collection: support-tickets
  sample_size: 20000
```

It scrolls a sample out, computes exact ground truth **over that sample**, and
searches the live collection. It creates nothing, writes nothing and deletes
nothing — the RTT baseline is timed with `describe()` calls rather than by
creating a scratch collection, precisely so the claim holds.

> **Recall in this mode is a LOWER BOUND.** Ground truth covers the sampled
> vectors; the engine searches the whole collection. A neighbour the engine
> returns that is genuinely nearer but was not in the sample is scored as a
> miss. The true recall is at least the reported number and probably higher,
> and the gap grows as the sample shrinks. Compare two runs of this mode only
> at the same `sample_fraction`, which the receipt records.

---

## Cost

`oneground/cost/`. Node count from the simulator's estimated memory, prices
from a **provided table** you can read and edit
(`oneground/cost/prices.example.yaml`). There is no pricing API call and there
will not be one: a cost you cannot re-derive from a file is a cost you cannot
check.

Every figure is `EUR X +/- Y`, and **budget verdicts use the upper bound** —
under-running a budget is a pleasant surprise, over-running one is the failure
the constraint exists to prevent.

Compute only. Storage, egress, load balancers, backups and the people who run
it are outside the table and outside every number. Nothing is a quote.

---

## Incident: the launch that reported a pid and started nothing

*11 September 2026, session `20260909-184937`, pod `j8xm82i6mfgbe3`.*

Setup completed, the launch reported `pid 361`, and the log at
`/workspace/oneground-verify.log` never appeared. The no-run watchdog
terminated the pod after 180 s, which is what it is for.

**Cause.** `&` binds looser than `&&` in the shell, so

```sh
mkdir -p $(dirname LOG) && setsid nohup bash -c PAYLOAD > LOG 2>&1 </dev/null & echo $!
```

does not mean "make the directory, then background the launch". It means
"background the whole `mkdir && launch` list, then echo". Reproduced without a
pod (`tasks/scratch/011-launch-precedence.sh`) -- `jobs -l` reports **one** job
for the entire list, and `$!` is that subshell's pid, not the run's.

Two consequences, both fatal together:

- The pid is meaningless. `tasks/scratch/011-launch-repro.py` shows the old
  shape exiting **0 with a plausible pid for a command that does not exist**.
- ssh returns as soon as `echo` finishes and sshd tears the session down. The
  backgrounded subshell was never in its own session -- only the inner
  `setsid` would have done that, and it had not run yet -- so it could take
  SIGHUP before reaching the redirect. No redirect, no log file.

**Fix.** The setup runs in the foreground separated by `;`, the log is created
**synchronously** with `: > LOG` before anything is backgrounded so its
existence never depends on a race, only the run is backgrounded, and the
launcher confirms itself:

```
ONEGROUND_LAUNCHED <pid> setsid=<setsid|none>
```

Anything else -- a non-zero exit, a missing confirmation -- raises
`LaunchFailed`, which carries the remote exit code and both streams into the
session record and terminates the pod instead of waiting three minutes to find
out.

`setsid` became optional in the same change. It is hardening (its own session,
immune to a HUP aimed at the ssh session), not a requirement -- `nohup` already
ignores HUP, and Git Bash and some minimal images have no `setsid` at all.
Which form was used is reported, so a run that got the weaker one is visible
rather than assumed.

## Incident: the pod ran the wrong requirements at the wrong load

*11 September 2026, session `20260909-194107`, pod `lig6glzwaagcbu`.*

The launch confirmed correctly this time, and the run started -- then printed
its own configuration:

```
  requirements: requirements.arxiv-150k.yaml     <- smoke session
  concurrency : 8
  target qps  : 0                                <- session says 50
  duration min: 5                                <- session says 1
```

**Every value was a default.** None of the session's `ONEGROUND_*` variables
reached the run.

**Cause.** A pod's `env` in `POST /pods` is set for the container's *main
process*. `oneground pod` launches the run over ssh, and sshd hands out a fresh
login shell that does not inherit it. The session spec was correct; the
environment simply never arrived.

**Fix.** The launch carries its own environment. `up` already knows the
session's `env` locally, so `build_start_command` exports it inside the payload
`bash -c` receives:

```sh
nohup bash -c 'cd /workspace/oneground && export ONEGROUND_REQUIREMENTS=... ;                export ONEGROUND_CONCURRENCY=8; bash corpora/run_verify_pod.sh'
```

The run no longer depends on how an image wires sshd. `run_verify_pod.sh` also
refuses to start when `ONEGROUND_REQUIREMENTS` is unset, so a run that would
measure the wrong corpus stops in seconds instead of after five minutes of
load.

**And one more, in the same session.** `tar -xzf` as root tried to honour the
archive's recorded uid/gid 1001 and failed on a container filesystem:

```
tar: qdrant: Cannot change ownership to uid 1001, gid 1001: Operation not permitted
```

Under `set -euo pipefail` that killed the run before the engine existed.
Extraction now passes `--no-same-owner --no-same-permissions`.

---

### Incident: the pod that could not have had the workdir

Session `20260909-195824` (pod `ujumfjkqpsgm6p`, RTX PRO 4000, $0.57/hr).

The environment fix above worked — the run printed exactly the session's own
configuration:

```
  requirements: requirements.smoke.yaml
  concurrency : 8
  target qps  : 50
  duration min: 1
```

qdrant 1.19.1 started in 2 s. Then:

```
VerifyError: no characterization in /workspace/oneground/runs/arxiv-smoke
```

**Cause.** The repo reaches the pod as a git bundle. A bundle carries commits,
and `.gitignore` line 34 is `runs/` — so the workdir, which is the entire
input to `verify --on-pod`, could never have arrived. The pod had no `runs/`
directory at all. This was not a race or a partial sync; the design had no
path by which those files could reach the pod.

**Not the fix: recomputing on the pod.** `verify` exists to measure an engine
against the *same* exact k-NN the local decision was made against. A ground
truth recomputed on the pod is a different ground truth, and comparing an
engine to it would answer a question nobody asked.

**Fix.** A session spec now declares `inputs`, symmetrically with the
`outputs` it already brings back:

```yaml
inputs:
  - {local: runs/arxiv-smoke/characterization.json,
     remote: /workspace/oneground/runs/arxiv-smoke/characterization.json}
  - {local: runs/arxiv-smoke/ground_truth.npy, ...}
  - {local: runs/arxiv-smoke/ground_truth_scores.npy, optional: true, ...}
```

`oneground verify --target runpod` generates these from the workdir. `up`
uploads them after the clone and before setup, and — this is the part that
matters for money — **refuses before the create** if a required input is
missing locally. Discovering an absent file four minutes into a billing pod is
the wrong side of the boundary.

The remote path is the same relative path as the local one, deliberately: the
pod runs the same requirements file, which names its workdir as `./runs/<name>`.

### Incident: `environment_id: unknown-pod`

Same session. Every row it would have produced carried
`environment_id: unknown-pod`, because `run_verify_pod.sh` reads
`${RUNPOD_POD_ID:-${ONEGROUND_SESSION:-unknown-pod}}` and neither is set in an
sshd shell — the same container-process-variable problem as the session env.

This is not cosmetic. Under the same-environment rule, `verdict.latency_p95`
and `verdict.qps` refuse to settle a constraint from a row whose
`environment_id` is not the one the constraint names. `unknown-pod` matches
nothing, so every latency verdict from that run would have been
couldn't-check regardless of how good the measurement was.

**Fix.** The launch supplies both: `up` knows the session id and the pod id it
just created, and exports them into the run's environment alongside the spec's
own `env`.

### Incident: a stale record blocking a session that cost nothing

Session `20260909-194107` was terminated, but its local record stayed
`running`. `ls` printed "no such pod is on the account" and changed nothing;
`up` counted the record against `max_concurrent` and refused the next session;
`down` got a `404` from RunPod and left the record untouched. The only way out
was editing `.oneground/sessions/` by hand.

**Fix.** The record is a convenience; RunPod is the source of truth. Every
path that asks "how many sessions are live" now reconciles against
`GET /pods` first:

- `ls` marks an absent pod's record `terminated`
  (`finished_because: absent-from-account`).
- `down` treats a `404` as the outcome it was asked for and closes the record.
  Any other status still fails loudly and leaves the record alone — a `500` is
  not proof the meter stopped.
- `up` counts only records whose pod is actually on the account.

Two deliberate asymmetries, both on the expensive side: a record younger than
120 s is kept even when `GET /pods` has not listed its pod yet (the listing
lags a create, and under-counting would create a second pod), and if the
account cannot be reached at all the records are trusted unchanged
(over-counting only refuses a session).

### Incident: twelve handshakes to move a quarter of a megabyte

Session `20260909-202938` (pod `nsspxnmlkjv5ri`). The clone succeeded, the
input upload timed out with `timed out: ssh -p 44089`, and `up` exited leaving
the pod running.

**Size was not the cause**, and that is arithmetic rather than opinion — the
six declared inputs of the smoke session:

```
characterization.json              459
sample_ids.json                 14,893
queries_ids.json                 1,693
ground_truth.npy               160,128
ground_truth_scores.npy         80,128
build_info.json                  1,197
total                          258,498 bytes  (0.25 MB)
```

**Cause.** The first version of `_upload_inputs` opened two ssh connections
per input — an `ssh mkdir -p <parent>` at a fixed 120 s timeout, then an
`scp` — so six files meant twelve handshakes to a pod that had been reachable
for seconds. The error names `ssh`, not `scp`, so it was one of the `mkdir`
calls. A `mkdir -p` does not take two minutes; the connection was hanging, and
the code discarded the only evidence about why (`TimeoutExpired` carries the
partial streams; they were thrown away).

**Fix, in three parts.**

1. *One transfer, not twelve.* The inputs are packed into a single archive
   whose member names are their remote absolute paths minus the leading
   slash, sent with one `scp`, and extracted with one `tar -xzf … -C /`.
   Three connections however many files a session declares. Measured on the
   real smoke inputs: 6 files, 258,498 bytes raw, 113,308 packed, one transfer.
2. *Timeouts scaled to bytes, and evidence when they fire.*
   `transfer_timeout(n)` is 120 s plus the payload's time at a floor rate of
   256 KB/s, bounded at an hour — a floor, not an estimate, so hitting it
   means something is wrong rather than slow. A timeout now reports how long
   it waited and whatever the command had already written. `BatchMode=yes` and
   `ConnectTimeout=30` were added at the same time: an ssh sitting at a
   password prompt on a terminal nobody is watching is indistinguishable from
   a network hang, and burns the caller's whole timeout before saying so.
3. *A size cap, checked before the create.* `input_size_cap_mb`, 50 by
   default. A session that genuinely needs more says so in the spec; there is
   no command-line flag, for the same reason the dirty tree has none. This is
   what will stop the arXiv session from trying to push 460 MB of vectors up
   an scp.

### Decision: nothing after the create may leave a pod alive

The same session exposed a second and worse problem. `up` caught the upload
failure, printed

```
The pod is still running and still billing.
  oneground pod down <id>     # terminate now
```

and exited. The developer terminated it by hand.

That message is not a cleanup. It is a bill with instructions attached. The
no-run watchdog, the price check and the launch-failure path all terminated
correctly already — so the only paths that ever leaked a pod were the ones
nobody had thought about yet, which is the shape this class of bug will always
have. A guarantee that each known failure remembers to clean up is not a
guarantee.

So it is now a property of one `try` around one call:

```python
    try:
        return _run_session(client, args, s, p, root, session_id, pod_id, pod)
    except sshx.LaunchFailed as e:   ... _terminate(..., "launch-failed")
    except Exception as e:           ... _terminate(..., "failed-after-create")
    except BaseException:            ... _terminate(..., "interrupted"); raise
```

`BaseException` is deliberate: Ctrl-C after the create terminates the pod
before the interrupt propagates, because the pod does not care that a human
changed their mind. The single case that cannot be cleaned up automatically is
a create that returns no pod id — there is nothing to name in a `DELETE` — and
that one says so at full volume and points at `ls` and the console.

Two existing tests had to change, and the reason is worth recording: they
asserted "no `DELETE` appeared" as a proxy for "the price check did not
terminate this pod". That proxy stopped being valid the moment every
post-create failure terminates. They now assert on the recorded
`finished_because` instead, which is what they were always about.

### Incident: the comment that said the vectors were committed

Session `20260909-205151` (pod `3875tt62dugtbz`). Three fixes confirmed live —
the session env arrived, `environment_id` was the real pod id, and the workdir
upload landed, carrying the run all the way into `_verify_local`:

```
  requirements: requirements.smoke.yaml
  concurrency : 8
  target qps  : 50
  duration min: 1
environment_id: 3875tt62dugtbz
...
LoadError: vectors: file not found:
    /workspace/oneground/fixtures/arxiv-smoke/vectors.npy
```

**Cause.** `.gitignore` line 10 is `fixtures/*/vectors.npy`. The 6.1 MB smoke
vectors are ignored and never reach the pod. `queries.npy` is tracked, which
is why only the vectors failed.

`requirements.smoke.yaml` says, in a comment:

> The vectors are the committed smoke artifacts, so this file needs no
> external asset.

That comment is wrong, and it was believed. The first `inputs` implementation
enumerated the *workdir* because the workdir was what the previous failure
named — but the rule was never "the workdir". It is **everything the run reads
that git does not carry**, and the only authority on that is git.

**Fix.** `git_carries(path)` asks `git check-ignore` and `git ls-files` per
path at session-generation time, and returns *why*, because the two ways git
fails to carry a file need different answers:

| verdict | answer |
| --- | --- |
| tracked | nothing to do; the bundle carries it |
| git-ignored, or untracked, inside the repo | upload it, same relative path |
| outside the repository | **never upload**; it must already be on the pod |

That last row is the volume-first ruling enforced rather than remembered. The
arxiv-150k vectors are 460 MB at an absolute path outside the repo; they now
land in an `external` list that `verify --target runpod` prints under
`MUST ALREADY BE ON THE POD`, instead of being silently packed into an scp.

Measured on the two real requirements files:

```
requirements.smoke.yaml       upload   fixtures/arxiv-smoke/vectors.npy
requirements.arxiv-150k.yaml  external vectors  ...\arxiv-150k\vectors.npy
                              external queries  ...\arxiv-150k\queries.npy
```

The smoke session now uploads 7 files, 6,402,626 bytes raw and 5,824,031
packed, in one archive with a 142 s derived timeout — against the 50 MB cap.

Two tests are deliberately **not** synthetic: they load the two real
requirements files and assert what each would upload. If the smoke one ever
comes back empty, this incident is about to repeat.

### Incident: a string split destroyed a completed measurement

Session `20260909-213526` (pod `6itbyb2m315h0i`). The corpus-inputs fix
worked — this run loaded its vectors, reused the uploaded ground truth, and
measured everything:

```
2,000 vectors, 200 queries, dim 768
ground truth: reusing runs/arxiv-smoke/ground_truth.npy
rtt baseline over 50 pings: p50 2.89 ms, p95 4.19 ms
ingesting 2,000 vectors -> 2,819 vectors/s, indexed 2000/2000 in 0.5 s
recall@10  1.0000   p50 3.14 ms  p95 4.38 ms
recall@100 1.0000   p50 3.71 ms  p95 5.03 ms
load: 50.0 qps achieved, p95 5.0 ms, errors 0.0000%
KeyError: 'recall_at_10_under_load'
```

**Cause.** `_summary` did `key.split("=")[1]`, which turns `k=10_under_load`
into `10_under_load`, and then looked up `recall_at_10_under_load`. The row
carries `recall_at_10`; nothing was missing. A string split killed a run that
had already measured, and written, every number it was asked for.

**What was actually lost, and why.** `verify.json` *was* written — `_write`
runs before `_summary`. But `run_verify_pod.sh` runs under `set -euo pipefail`,
so the crash killed the script before it packaged the outputs. The completed
measurement existed on the pod and died with it.

**Fix.** Two parts, and the second matters more than the first:

1. `_summary` parses `k=10_under_load` to `10`, and tolerates a row with no
   recall at all.
2. The runner captures the verifier's exit code instead of letting `set -e`
   take it, packages whatever the verifier left behind either way, and prints
   `DONE` **only** on success. `watch` already fetches before terminating on a
   stall, so partial evidence now comes home with no client-side change.

`package_outputs` is a shell function at the top of the runner, and the file
can be sourced with `ONEGROUND_RUNNER_LIB=1` to define it and run nothing —
so the tests exercise the implementation that ships rather than a copy of it
in a fixture.

**And a labelling error the fix exposed.** With the crash gone, the
`k=10_under_load` row printed for the first time — under the caption
`(sequential, 1 client -- not throughput)`, below a footer reading
`Nothing here was measured under load.` Both false for that row: it is
measured at the session's concurrency, and its own `note` says so. A load
measurement presented as a single-client latency shape is exactly the blur
this target exists to prevent; it had simply moved into the presentation
layer. The row is now captioned `(UNDER LOAD at concurrency N)` and the
footer is conditional. The recall in that row keeps its own caveat — it is
copied from the sequential run, because the load generator never measures
recall — so a carried-over number cannot read as a second measurement.

The stored field is still named `latency_shape_single_client` even when it
holds an under-load shape. That is a schema wart; renaming it would change
`verify.json` for every reader including the verdict rules, so it is recorded
here rather than fixed quietly.

### Correction: the matched environment did not make latency attributable

Reported in this session, and worth keeping because the first reading of it
was wrong. The build agent looked at an RTT p95 of 4.19 ms against a query p95
of 4.38 ms and called the path "a small fraction of the query". It is 96% of
it, and `verify` refused both k accordingly:

```
k=10   latency  couldnt_check: environment noise -- the baseline RTT p95
                (4.19 ms) is 96% of the query p95 (4.38 ms), over the 20% limit
k=100  latency  couldnt_check: ... 83% of the query p95 (5.03 ms)
```

The pod did what it was built to do — task 009's laptop ratio was 132%, this
is 96% — but "better" is not "attributable", and the `p95_ms: 40` constraint
in `requirements.smoke.yaml` cannot be settled by this run.

The likely reason is the fixture, not the environment: on 2,000 vectors the
engine's own work is a fraction of a millisecond, so nearly all of the query
time is path. Smoke exists to prove the path works, not to produce a latency
verdict. **Whether arxiv-150k at 150k vectors clears the 20% gate is an open
question and is not settled by anything measured so far.**

### The first complete matched-environment run

Session `20260909-220900` (pod `6ym6p1wf230ff5`) reached `DONE`, and `watch`
fetched and terminated. The full result, on the arxiv-smoke fixture:

```
environment_id  6ym6p1wf230ff5
rtt baseline    p50 3.59 ms   p95 6.28 ms
recall@10       1.0000
recall@100      1.0000
load            50.0 qps achieved (target 50), 3,000 queries, concurrency 8,
                0 errors, p95 under load 6.18 ms
```

`report` consumed it and settled `qps = meets` **in environment
6ym6p1wf230ff5** from `verify.json:load.achieved_qps` — the first throughput
verdict this project has ever produced, because no earlier run had a load
phase at all.

**Latency is still couldn't-check, on all three rows**, and the ratios are the
reason:

| row | baseline p95 | query p95 | ratio |
| --- | --- | --- | --- |
| k=10 | 6.28 ms | 5.54 ms | 113% |
| k=100 | 6.28 ms | 5.87 ms | 107% |
| k=10_under_load | 6.28 ms | 6.18 ms | 102% |

On 2,000 vectors the engine's work is a fraction of a millisecond, so the
query p95 and the empty-collection RTT are the same number. The matched
environment removed the NAT (task 009 measured 132% on the laptop) but a
fixture this small has nothing for the engine to do. **Whether arxiv-150k
clears the 20% gate is not settled by this and remains open.**

### Incident: the result landed beside the workdir, not in it

Same session. `watch` reported:

```
-> runs\arxiv-smoke\verify-out.tgz  (1918 bytes)
extracting into <repo>
extracted
```

The tarball's members were `arxiv-smoke/verify.json`, so extracting at the
repo root created a stray `<repo>/arxiv-smoke/` while
`runs/arxiv-smoke/verify.json` kept the stale local file from task 009.
`report` then read the old one. Nothing was lost, and nothing errored — the
run's result was simply not where anything looks for it, which is worse than a
failure.

**Fix, in two halves that have to agree.** `_fetch_outputs` extracted into
`root` regardless of the output's `local`; it now extracts into the directory
the tarball was fetched into, which is `local` resolved against the root. And
the runner tarred `$(basename $WORKDIR)/verify.json`, prefixing every member
with the workdir's name; it now tars bare filenames from inside the workdir,
so the members are exactly what should appear in the destination. For the
arxiv-build session, whose outputs say `local: ./`, the behaviour is
unchanged.

`simulate.json` was also added to the uploaded workdir inputs: the run came
back with `calibration: couldnt_check: no simulate.json in the workdir`,
having measured everything the simulated-minus-measured comparison needs.

### Decision: volume-first, and what is still unverified

`requirements.arxiv-150k.pod.yaml` is the file the **pod** runs, named from
the developer's file by `verify.requirements_on_pod`. It is identical except
that its corpus paths point at the network volume:

```
vectors  /workspace/arxiv-150k/vectors.npy
queries  /workspace/arxiv-150k/queries.npy
```

460 MB does not go up an scp, and `corpus_inputs` refuses anything outside the
repository on purpose, so the volume is the only route. The session generator
now computes its inputs and its "must already be on the pod" list from the
file the pod will run rather than the one the developer ran — otherwise it
describes a session that is not the one about to happen.

**Those two paths are a guess and are marked as one.** Nothing on the
developer's machine can see the volume. `run_verify_pod.sh` therefore stats
them in a preflight **before it downloads an engine**, and on failure prints
what it looked for, lists what is actually under `/workspace`, and exits 3. A
wrong guess costs seconds of pod time and returns the information needed to
correct it — rather than four minutes and a traceback, which is how sessions
20260909-195824 and 20260909-205151 were spent.

**The gap is now closed.** The volume layout was confirmed from build 3's log:

```
/workspace/arxiv-150k-large.tgz      483,468,013 bytes
  members: fixtures/arxiv-150k/{vectors.npy,queries.npy,sample.jsonl.zst}
```

There is no bare `/workspace/arxiv-150k/`, so the preflight extracts one.
What it does, in order, before an engine is downloaded:

1. If the corpus paths are absent, extract **only** `vectors.npy` and
   `queries.npy` from the declared tarball, stripping the `fixtures/<name>/`
   member prefix. `sample.jsonl.zst` is 50 MB of source records that `verify`
   never opens, and it stays packed.
2. sha256 both files and compare against `fixtures/arxiv-150k/MANIFEST.sha256`
   — the repo's own record, which reaches the pod in the git bundle. A
   mismatch prints both digests and exits 3.
3. If neither the corpus nor the tarball is there, list what *is* under
   `/workspace` and exit 3, so one cheap pod returns the real layout.

The digest check runs on **every** pass, not only after this run's own
extraction. The volume outlives the pod, so the directory can hold a partial
extraction left by a session terminated mid-way — the likeliest way a wrong
corpus appears, and the case a check on freshly-written files alone would
miss. It costs a few seconds against a 460 MB read.

That answers the question this section previously recorded as unanswerable:
whether the vectors on the volume are the bytes the ground truth was built
from. Verifying an engine against a different corpus would produce a recall
number that means nothing, and now it cannot happen silently.

The tarball and manifest are declared in the requirements file
(`verify.pod_corpus_tarball`, `verify.pod_corpus_manifest`) and travel in the
session env, so nothing in the runner is hardcoded to one fixture. A session
with no manifest declared reports `couldnt-check` for digests — not "ok".

---

## Rule: single-client latency is not rescued by a matched environment; loaded latency is

Measured on arxiv-150k, session `20260909-225058` (pod `tf8sd2usxbblsm`),
150,000 vectors at dim 768, RTT baseline p95 6.99 ms:

| row | query p95 | RTT / query | |
| --- | --- | --- | --- |
| k=10, sequential | 7.18 ms | **97%** | refused |
| k=100, sequential | 6.64 ms | **105%** | refused |
| k=10, under load, concurrency 32 | **38.22 ms** | **18.3%** | attributable |

A single HNSW query over 150k vectors is a few hundred microseconds of engine
work. A loopback round trip on this pod is ~7 ms. Scaling the corpus 75× from
the smoke fixture moved the sequential ratio from 113% to 97% — that is,
almost not at all, because the term that dominates is the path and the path
did not change. **No corpus size reachable on one pod makes single-client
latency attributable.** It is not a fixture problem to be fixed with more
vectors.

Under load the picture inverts. At concurrency 32 the queue is most of the
latency, the engine's own work is most of the queue, and the round trip falls
to under a fifth of the number. That is a real measurement of the engine.

**The rule.** A latency constraint that names `at_qps` or `concurrency` is a
statement about the engine under load and is answered **only** by an
under-load row measured at that concurrency. There is no fallback to the
sequential row: the two measure different things, and substituting one for the
other silently answers a question nobody asked. A constraint with no `at_qps`
keeps reading the sequential row, and on a matched-environment pod will
usually be couldn't-check — correctly.

The corollary is a product one: **`oneground` cannot settle a single-client
p95 constraint, and should say so rather than appearing to try.** A user who
writes `p95_ms: 40` with no `at_qps` is asking a question this tool cannot
answer on any hardware it runs on.

## Rule: a throttled load run is a sustain check, not a ceiling

The load generator holds the offered rate with a token bucket, so achieved can
never exceed target. `achieved >= at_qps` is therefore a knife-edge that fails
by a hair on essentially every targeted run — it measures the token bucket,
not the engine. arxiv-150k completed 59,999 of 60,000 queries in five minutes
and was reported as `200.0 qps achieved < 200 target`: wrong, and as printed,
self-contradictory.

A throttled run **meets** when errors are zero and the shortfall is at most
one query per second of measured duration — the generator's own tick
granularity, so a run is never failed for landing inside its own resolution.
The reason states the tolerance and prints both numbers unrounded:

```
sustained the offered 200 qps at concurrency 32: 59999 of 60000 queries in
300 s, short by 1 against a tolerance of 300 (one query per second of
duration, the generator's tick), 0 errors (environment tf8sd2usxbblsm).
Achieved 199.99 qps against a 200.0 target; this is a sustain check -- a
throttled run cannot exceed what it was offered, so it is not a measurement
of the engine's ceiling. See qps_max
```

An **unthrottled** run (`target_qps: 0`) is a ceiling, and keeps the plain
comparison.

`qps_max` — the highest offered rate at which errors stay zero and p95 stays
under the cap — is a different measurement needing a ramp rather than one load
phase. It is documented in `oneground/report/verdict.py` and deliberately not
implemented. The engine's ceiling and the rate it sustained are not the same
number and must never share a row.

## Rule: a single run does not settle a latency verdict near its threshold

*Recorded 2026-09-11, from two sessions measuring the same thing.*

The same configuration — `single_node_hnsw[M=32,efConstruction=200,efSearch=128]`
on arxiv-150k, Qdrant 1.19.1, concurrency 32, 200 qps offered, 5 minutes —
measured **p95 under load** twice:

| session | pod | p95 under load |
|---|---|---|
| 20260909-225058 | `tf8sd2usxbblsm` | **38.22 ms** |
| 20260911-181410 | `z01d7n4buc1a6i` | **42.82 ms** |

**12% apart.** Both are RTX PRO 4000 in EU-RO-1, both ran the same sample
against the same engine version with the same parameters, and neither is
wrong. Two different physical machines from the same pool, on two different
days, simply do not produce the same p95.

That spread is larger than the distance from either number to the 40 ms
constraint those runs were judged against — and the constraint fell between
them. The first session's verdict was `meets`; the second's was `fails`. **The
architecture did not change. The machine did.**

So:

- **A latency verdict within ~15% of its threshold is not settled by one run.**
  It is a sample of one from a distribution nobody has characterised, and the
  report presents it with exactly the confidence it presents a number that is
  nowhere near its threshold — which is too much.
- The `environment_id` rule already stops a verdict crossing machines. It does
  **not** stop a verdict being read as more precise than one sample can be.
- Nothing in the tool currently reports a spread, because nothing has ever run
  the same configuration twice on purpose.

**What would fix it, and what is not done here.** Repeated runs of one
configuration in one session, reported as a distribution rather than a point —
median and spread, with the verdict taken against the spread rather than
against a single p95. That is a change to what `verify` runs and to what
`latency_p95` reads, and it costs pod minutes per repetition. It is **task 017
work**, recorded here so the next reader of a near-threshold verdict knows the
number's precision before acting on it.

Until then, read a latency verdict whose value sits within about 15% of its
threshold as *couldn't-check wearing a verdict's clothes*.
