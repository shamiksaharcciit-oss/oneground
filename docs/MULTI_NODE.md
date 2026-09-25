# oneground — multi-node verification: the position, before the code

*25 September 2026. Written before implementation, in the order the other
five positions were written: the exam before the code. Every claim below
about Qdrant's real behaviour was checked against a real three-node cluster
(`qdrant/qdrant:v1.19.1`, Docker Compose, native cluster mode) and the
pinned `qdrant-client==1.19.0`, not read from documentation alone — the
standing rule this whole document set follows, and the reason task 037's
brief existed: the previous version of this question was answered from a
conversation neither party could check
(`tasks/finding-a-ruling-made-in-conversation-is-not-in-the-product.md`).*

*Researched before task 056; the `nodes` bug §3 describes was fixed on 25
September as a consequence of this paper. Left as researched below rather
than edited to match — a paper edited to agree with a later fix reads as
though it was always true, and §3 is stronger for having found the bug
than for describing one already known.*

## 1. The question

`describe()` (`oneground/adapters/base.py`) already declares `shards`,
`replicas` and `nodes` — a count. `oneground/verify/load.py` measures one
aggregate `achieved_qps`/`latency_under_load` against one connection. Two
questions sit in the gap between a count and an aggregate: **can oneground
learn which physical node served a given request**, and if it can, **is
that worth reporting, and how**. Nothing before this paper answered either
from a running cluster.

## 2. What makes this honest, and it is not obvious

The obvious approach is to ask the engine which node answered. That
question has an answer, and the answer is no — checked, not assumed, in
§4.1 below. The honest version of "multi-node verification" has to be built
on what a client can actually know from *outside* the engine, not on a
field that looks like it should exist and does not.

## 3. What already exists, checked against a running cluster

**`describe()`'s `shards` and `replicas` are correct, and real.** Against a
collection created with `shard_number: 6, replication_factor: 2`, the
adapter's `describe()` returned `shards: 6, replicas: 2` — read from
`get_collection().config.params`, which is what the collection was actually
configured with, not inferred.

**`describe()`'s `nodes` has never worked, on any topology, since the
repository's first commit — and it is not a multi-node limitation.** The
adapter calls `c.get_collection_cluster_info(...)`
(`oneground/adapters/qdrant/adapter.py:406`). The pinned client,
`qdrant-client==1.19.0`, has no method by that name — it is
`collection_cluster_info` (no `get_` prefix). Confirmed directly:
`hasattr(QdrantClient(...), "get_collection_cluster_info")` is `False`.
Every call raises `AttributeError`, caught by the bare
`except Exception: pass` two lines below with the comment *"single-node
deployments may not expose cluster info"* — which reads as an expected,
narrow case and is not one: the exception fires identically whether the
collection has one shard on one peer or six shards on three, because the
method name is wrong regardless of topology. `nodes` has silently returned
`None` on every deployment this adapter has ever described, and nothing
caught it — there is no test anywhere that asserts `EngineFacts.nodes` is
populated. **This is a pre-existing defect in shipped code, not a gap this
paper's design has to fill**, and it is named here rather than fixed here,
per this brief's own scope. A one-line rename
(`get_collection_cluster_info` → `collection_cluster_info`) is enough to
make `nodes` real; a test asserting it against a real multi-peer cluster is
what would have caught it three months ago.

**The count itself, once the name is fixed, is cheap and correct.**
`collection_cluster_info` returns `peer_id` (this peer), `local_shards` and
`remote_shards` (each carrying the remote's `peer_id`). `nodes = 1 +
len({distinct peer_ids in remote_shards})` is exactly right on a real
cluster: three nodes, six shards, replication factor two, and the count
comes back three once the method name is fixed.

**`oneground/verify/compose/qdrant.yml` already names this gap and points
at a task that does not close it.** Its own comment: *"Single node. Verify
measures latency shape on one node in this task; cluster shapes are task
011 on a pod."* Checked: task 011 (`tasks/011-cloud-verify-cost.md`/
`.report.md`) built the `runpod` verify target, the load generator and the
cost model — `nodes × node_price × hours/month`, a capacity estimate, not a
running cluster measurement. It never built cluster verification. The
comment is a second, smaller instance of the same finding this paper
exists because of: a forward reference to work that was never done, sitting
in the tree since the file was written, uncorrected.

## 4. What a client can and cannot know

### 4.1 Nothing in a search response identifies the node that answered it

Checked directly against `qdrant_client.http.models.models.QueryResponse`
and `ScoredPoint`, the real return types of `query_points()` (the call
oneground's adapter's `search()` wraps): `QueryResponse` has exactly one
field, `points`. `ScoredPoint` carries `id, version, score, payload, vector,
shard_key, order_value` — no peer id, no node id. `shard_key` is a
user-declared logical partition key (set at insert time, for routing), not
the identity of the physical peer that executed the query. A raw HTTP
request against the REST API carries no node identity in its headers
either (checked: `content-length`, `content-type`, `vary`, `date` — nothing
else).

**This rules out "ask the engine" as a mechanism entirely**, for Qdrant.
Whatever multi-node measurement is built, it cannot come from a field the
search call returns.

### 4.2 Node identity is available, structurally, and only if the deployment exposes it

`collection_cluster_info` *does* answer a different, adjacent question:
**which peer holds which shard**, as static topology — checked against a
real cluster with `shard_number: 6`, it correctly reported 4 shards local
to the peer queried and 8 shards spread across the other two. That is
placement, not routing: it says where a shard *lives*, not which peer
answered any specific request, and with `replication_factor: 2` more than
one peer can legitimately answer the same shard's queries.

**The only real mechanism is dialing each node directly.** If a deployment
exposes every peer's own address (as this paper's research cluster did —
three separate host ports, one per node, no load balancer in front) then
the *client* knows which node it queried, because it chose the address —
not because the engine declared it. Measuring per-node fan-out is possible
exactly to the extent oneground's adapter can be pointed at each peer's own
endpoint and issue the same query set against each in turn.

**Behind a single entrypoint — a load balancer, a Kubernetes Service, a
managed cluster's one connection string — this mechanism is unavailable,
and the honest answer is `couldnt_check`, not a guess.** Nothing in the
client or the protocol lets a request "ask" which node a shared endpoint
routed it to. A user's own cluster, reached through whatever front door
their deployment uses, is very often exactly this case.

## 5. What this rules out

- **`describe_deployment()`, or any new adapter method, for the node
  count.** `describe()` already carries `shards`/`replicas`/`nodes`; the
  gap was a wrong method name inside it, not a missing one beside it.
- **Any mechanism that reads node identity from a search response, a
  response header, or `collection_cluster_info`.** None of the three
  carries it, checked directly against a real cluster and the pinned
  client's real return types.
- **Per-node measurement for a deployment reached through a single
  entrypoint.** This is not a smaller version of the multi-node measure —
  it is the case the measure cannot be built for, honestly, and it is
  common: most production clusters put something in front of their nodes
  precisely so a client does not have to know how many there are.

## 6. What this earns, if built

**Slowest-node-against-mean-node** (one of the two candidates the
conversation this paper replaces named) is buildable, conditionally: for a
deployment whose every node's own address is reachable — which needs to be
declared as a fact about the deployment, the same way `credentials_env`
declares where a secret comes from, not assumed — the load generator issues
the same query set against each address, `EngineFacts`-style per-node rows
each carrying their own `achieved_qps`/`latency_under_load`, and the
report states slowest against mean. Nothing about this needs a new
protocol method: it needs the load generator (`oneground/verify/load.py`)
parameterised over more than one endpoint, and a declared list of those
endpoints in the requirements file rather than one.

**Staleness as an outcome distinct from recall loss** (the second
candidate) was not researched here — it presumes read-your-own-write
visibility across replicas, which needs a write followed immediately by a
read against a *specific* replica, and Qdrant's read routing (which replica
answers a given read, absent per-node addressing) was not part of this
paper's scope. It remains a candidate, not a ruling, exactly as the brief
that commissioned this paper said it should.

## 7. What this position does not settle

- Whether any real user's deployment exposes per-node addresses at all, as
  opposed to one entrypoint — this paper's research cluster was built to
  expose them, deliberately, to answer the mechanism question; a survey of
  what real Qdrant Cloud / self-hosted deployments actually expose was not
  done.
- Staleness-as-distinct-outcome (§6), entirely — a separate research pass
  against per-replica addressing, not attempted here.
- Whether pgvector's clustering story (which does not have Qdrant's native
  peer/shard model — Postgres replication is a different mechanism
  entirely) reaches the same conclusion. This paper checked one engine, as
  its own brief asked for a real client and API rather than a second
  document.
- Whether "couldnt_check, no per-node addressing" is a state worth
  building the honest refusal for now, or worth deferring until a user
  with a genuinely addressable cluster asks for the measurement.

## 8. Sequencing

Not before the one-line fix to `describe()`'s method name — cheap,
independent of everything else here, and the thing that makes `nodes`
real. The first implementation of the fan-out measure itself is
`oneground/verify/load.py` parameterised over a declared list of endpoints
instead of one, tested against the same kind of real multi-node cluster
this paper used — not a mock, for the same reason no position paper in
this set is written from documentation. Staleness is not sequenced here at
all; it needs its own research pass before it has a sequence to state.
