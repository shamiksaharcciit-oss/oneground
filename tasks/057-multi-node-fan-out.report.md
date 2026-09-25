# Report: 057-multi-node-fan-out

## Repo state expected vs found

Expected `main` at `ea431ee` (task 037's merge) with `docs/MULTI_NODE.md`
§6/§8 as the design and no per-node measurement anywhere in
`oneground/verify/load.py`. Found exactly that; branch `task-057` created
from `main` at that commit.

## What was done

**`run_load_per_node()`**, added to `oneground/verify/load.py` after
`ramp_to_ceiling`. Per §6: no new adapter method, a declared list of node
endpoints instead of one, `run_load()` run against each in turn, the
report stating slowest against mean.

- `node_endpoints` fewer than two → `couldnt_check`, named, quoting
  `docs/MULTI_NODE.md` §4.2's own reason: a single shared entrypoint
  cannot be attributed to a node by anything the client can ask the
  engine, and this is the case the measurement cannot be built for, not a
  smaller version of it.
- Two or more → a fresh `engine_factory()` instance connects to each
  address in turn (the same factory shape
  `oneground.adapters.conformance.run_conformance` already takes), and
  `run_load()` runs unchanged against each — the exact same measurement
  the single-node path already makes, attributed to a node because the
  client dialled that address, never because the engine declared one
  (§4.1).
- **"Slowest" is reported two ways**, not collapsed to one: lowest
  `achieved_qps` and highest `latency_under_load.p95_ms`, each naming its
  own node. Measured against a real cluster (below), these named
  *different* nodes — the reason both are kept rather than picking one.

**Tested against a real three-node cluster, not a mock**, per §8's own
instruction. `oneground/verify/compose/qdrant-cluster.yml` — three
`qdrant/qdrant:v1.19.1` containers in native cluster mode, each publishing
its *own* REST port on the host (16333/16343/16353), no shared entrypoint,
the addressable case §4.2 needs to exist for this to be tested honestly.
Built with Docker Desktop + WSL2 (installed for task 056's research;
reused here). `oneground/verify/test_load_multi_node.py` gates the live
test on `ONEGROUND_QDRANT_CLUSTER_URLS` (three comma-separated endpoints),
matching `oneground/adapters/conformance.py`'s established live-engine
pattern exactly — skipped without it, never faked.

## Measurements

Live run against the real cluster (500 vectors, dim 16, 40 queries,
concurrency 4, ~9s measured per node, `k=5`):

| node | endpoint | achieved_qps | p95_ms |
|---|---|---:|---:|
| 0 | `http://localhost:16333` | 101.32 | 71.64 |
| 1 | `http://localhost:16343` | 95.50 | 69.90 |
| 2 | `http://localhost:16353` | 157.92 | 51.41 |

`fan_out`: `mean_achieved_qps: 118.25`, `min_achieved_qps: 95.5`
(node 1), `mean_p95_ms: 64.32`, `max_p95_ms: 71.64` (node 0). **The
slowest node by throughput (1) and the slowest node by latency (0) are
different nodes** — real numbers, not constructed to make this point;
confirms the design choice to report both rather than one "slowest"
figure, which would have silently picked one and hidden the other. The
spread itself is plausibly internal cluster routing (a request landing on
a node that does not hold the shard locally is proxied to the one that
does, per Qdrant's own cluster model — `docs/MULTI_NODE.md` §4.2 notes
shard placement is static topology, not per-request routing), though this
task did not set an explicit `replication_factor` to isolate that
specifically; the collection used Qdrant's default.

## Verification

`oneground/verify/test_load_multi_node.py`: 2 of 2 passed — the
`couldnt_check` mutant (fewer than two endpoints, both the empty-list and
single-endpoint cases) and the live three-node run, both against a real
cluster brought up and torn down for this task, not left running.

Full suite, guard, identifier scan and `site/teaser/`: reported at the
merge, per the established pattern.

## Observed, not done

**No requirements-file or CLI wiring.** `docs/MULTI_NODE.md` §6 says the
declared list belongs "in the requirements file" as the deployment-level
fact; this task built the function `run_load_per_node()` takes that
declaration as a plain argument, matching the brief's literal scope
("`oneground/verify/load.py` parameterised over a declared list of
endpoints"), but did not add a `verify.node_endpoints` (or similar)
requirements-file field, nor call sites in `oneground/verify/__init__.py`
(`_verify_local` and friends) or in report writing. Wiring the function
into the CLI/requirements schema is a second, separable task — this one
built and verified the measurement itself.

**Staleness as an outcome distinct from recall loss** — `docs/MULTI_NODE.md`
§6 explicitly left this a candidate, not a ruling, and out of scope for
this task; not touched.

**Replication factor was not set explicitly** on the test collection
(Qdrant's default was used), so the measured spread above is plausible
but not isolated evidence of routing-vs-replication effects specifically
— noted in Measurements rather than asserted as a clean decomposition.

## Repo now contains

New:

- `oneground/verify/compose/qdrant-cluster.yml` — the three-node research
  cluster, checked in as a proper testing asset
- `oneground/verify/test_load_multi_node.py` — 2 tests, live-gated
- `tasks/057-multi-node-fan-out.report.md` — this file

Changed:

- `oneground/verify/load.py` — `run_load_per_node()` and its
  `couldnt_check` constant

## Blocked on developer

Nothing. Committing, pushing to `task-057`, and merging into `main` once
its checks are green, per standing instruction.
