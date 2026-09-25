# Task 037 — Multi-node: a position paper before a brief

*Rewritten from `docs/VERIFY.md` and `oneground/adapters/base.py` /
`docs/ADAPTERS.md` directly. The previous version of this file, described
in conversation as already written, reviewed and ruled on, was never in the
tree at any commit (`tasks/finding-a-ruling-made-in-conversation-is-not-in-
the-product.md`). Nothing below reuses that description; where this brief
lands near it, that is two people reasoning from the same protocol and
landing close, not a memory being confirmed.*

## What already exists, and what does not

**A per-engine node COUNT is already a declared fact.** `EngineFacts`
(`oneground/adapters/base.py`) has carried `shards`, `replicas` and `nodes`
since before this brief — returned by `describe()`, `kind: "declared"`, the
engine's own claim about its own layout, not something oneground measures.
A brief that proposed adding a new `describe_deployment()` method to name
these would be adding a second way to ask a question `describe()` already
answers. Whatever multi-node work exists here, it is not that.

**Nothing attributes a measurement to a specific node.** `oneground/verify/
load.py`'s load generator (`docs/VERIFY.md` "What the load generator
measures") issues queries against one connection — one endpoint, one client
— and reports `achieved_qps`, `latency_under_load` percentiles, `error_rate`
and `engine_cpu_pct` as a single aggregate. There is no per-node breakdown
anywhere in the load path, the recall path, or `EngineFacts`. `nodes` is a
count; it is not a list, and nothing reads or writes one.

**A node COUNT ESTIMATE already exists, and answers a different question.**
`oneground/cost/` derives a node count from the simulator's estimated memory
(`docs/VERIFY.md` "Cost") to price a configuration before anything runs.
That is *how many nodes would this configuration need*, a capacity estimate
over a simulated result. It has no access to a running cluster and nothing
to say about how queries actually fan out across one — a different question
answered by a different part of the system, not a partial version of this
one.

**Nothing here is `verify`'s existing three targets, extended.** `local`,
`runpod` and `existing` (`docs/VERIFY.md`'s opening table) each describe
*where the engine process runs relative to the client*. None of them says
anything about *how many machines that engine process is distributed
across*, or whether a query landed on one node or was routed among several.
A single-node Qdrant behind `runpod` and a three-node Qdrant behind
`runpod` are indistinguishable to everything `verify` measures today except
`describe()`'s own `nodes` count.

## Why this is a position paper, not a build brief

Every other capability this scale in the tree — `docs/HYBRID.md`,
`docs/BRIDGE.md`, `docs/PROPOSALS.md`, `docs/LIBRARY.md` — was written
before its code, for the same stated reason: "the exam before the code."
Multi-node has no equivalent, anywhere, at any commit
(`tasks/finding-a-ruling-made-in-conversation-is-not-in-the-product.md`
checked this exhaustively). The two open questions below are exactly the
kind this project's own convention answers with a paper first:

**What would oneground be able to know about a node, honestly, and where
would it come from?** `describe()` already shows the shape the answer has
to take — a `Protocol` method every adapter implements, the result
`kind: "declared"` unless oneground can measure it directly. Per-node
identity is not free: Qdrant's client speaks to one URL, which may itself
be a load balancer in front of several nodes, and nothing in the driver
says which physical node answered a given request unless the engine's own
API exposes that (many do, differently, or don't). Before any method
signature is proposed, the real question is per engine: **can this adapter
learn which node handled a request at all**, and if not, is "multi-node
verification" honestly `couldnt_check` for that engine rather than a
feature it lacks.

**What is worth reporting if node identity is available.** Two candidate
measures were named in the conversation this brief replaces —
fan-out reported as slowest-node against mean-node, and staleness kept as
an outcome distinct from recall loss — and they are worth stating here as
candidates, not rulings, because neither is independently checkable against
anything currently in the tree the way "describe() already has `nodes`"
is. Both need their own scrutiny: *slowest-vs-mean* presumes the client can
tell which node answered each query (the question directly above);
*staleness as distinct from recall loss* presumes a way to detect that a
returned result came from a node whose index has not caught up with a
recent write, which is a different signal from "the result is wrong" and
would need its own measurement, not a label applied to an existing one.

## Do

Write `docs/MULTI_NODE.md`, in the shape the four existing position papers
already establish (a question, what makes it honest, what is measured vs.
declared, what the design refuses, sequencing) answering, from adapter
behavior actually checked against at least one real multi-node-capable
engine's client and API (not assumed from documentation alone — the
standing rule this whole document set follows):

1. **Whether per-node attribution is obtainable at all**, and from where —
   the engine's own API, a side-channel `describe()` already has room for
   (`raw`, `runtime_settings`), or nowhere, per engine. An engine for which
   it is nowhere is a real, stated limit, not a gap to route around with a
   guess.
2. **What `EngineFacts` or a new declared shape would need to carry** to
   report it, if it is obtainable — and whether that is an addition to
   `describe()`'s existing return or genuinely needs a second method, argued
   from what `describe()` already covers rather than assumed to need one.
3. **Whether fan-out (slowest-vs-mean) and staleness-as-distinct-outcome are
   the right two things to measure**, or whether what is actually obtainable
   from a real engine's API points somewhere else. Keep three outcomes
   apart the way this project always does: measured, declared, couldn't
   check — per engine, not as one verdict for "multi-node."
4. **The boundary this brief's own conversation-source claimed**: oneground
   never provisions, scales or stops anything. Check it against what this
   project already refuses elsewhere — `docs/ADAPTERS.md`'s "not for
   verdicts... not for throughput" boundaries, and CLAUDE.md's "developer
   runs" convention for spending and infrastructure — and state it as
   continuous with those rather than as a new rule invented for this paper.
5. **Sequencing**, matching the other four papers' own last section: what
   has to be true before this is built (which engine, in what state,
   answers question 1 first) and what is explicitly not decided.

## Do not

- Build `describe_deployment()`, or any adapter method, before the paper
  above exists. `describe()` may turn out to be sufficient; deciding that
  requires reading what it already returns, done above, not assumed.
- Decide the fan-out/staleness measures are correct because they were named
  in a prior conversation. Treat them as candidates the paper either earns
  or replaces, checked against what a real engine's API can actually say.
- Reach for a cost or capacity framing (`oneground/cost/`'s node-count
  estimate). That is a different, already-built question; this paper is
  about a running cluster, not a simulated one.

## Blocked on developer

Which real multi-node-capable engine (if any is reachable — Qdrant's
cluster mode is the likely candidate, given it is already an adapter) the
research in item 1 should be checked against. Without one, item 1 is
answerable only from documentation, which is exactly the shortcut this
whole document set exists to refuse.
