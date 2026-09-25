# Report: 056-qdrant-describe-nodes-fix

## Repo state expected vs found

Expected `main` at `4e4868d` with `oneground/adapters/qdrant/adapter.py::
describe()` carrying the bug found while researching task 037: a call to
`c.get_collection_cluster_info(...)`, a method the pinned `qdrant-
client==1.19.0` does not have, caught by a bare `except Exception: pass`
whose comment misattributes the failure to single-node deployments not
exposing cluster info. Found exactly that; branch `task-056` created from
`main` at that commit.

## What was done

**The method name.** `c.get_collection_cluster_info(...)` →
`c.collection_cluster_info(...)`. Confirmed directly against the pinned
client: `hasattr(QdrantClient(...), "get_collection_cluster_info")` is
`False`; the real method is `collection_cluster_info`.

**The handler, narrowed to what it actually claims to catch.** Was `except
Exception: pass` with a comment naming a case ("single-node deployments
may not expose cluster info") the code had never actually hit — checked
directly against a real, non-clustered `qdrant/qdrant:v1.19.1` instance:
the correctly-named call succeeds there too, returning one local shard and
an empty `remote_shards`. There is no real "this deployment doesn't expose
it" case for this client/server pair; the failure this code was hitting
every time was a coding mistake, and a bare `except Exception` swallowed
it identically to the case the comment describes. Narrowed to
`qdrant_client.http.exceptions.UnexpectedResponse` — the exception type
for the server itself declining a request — so a future coding mistake
under this line surfaces instead of being caught by a comment written for
a different failure.

**A test that would have caught it three months ago, run for real, not
asserted.** `oneground/adapters/conformance.py`'s check (d) — already run
against a live Qdrant whenever `ONEGROUND_QDRANT_URL` is set, per the
project's standing conformance pattern — now asserts `facts.nodes is not
None`. Verified end to end against Docker Desktop and WSL2, installed on
this machine specifically to do this research and this fix honestly:
brought up `oneground/verify/compose/qdrant.yml`'s single-node instance,
ran the live conformance test with the fix (`nodes 1`, passed), then
reverted the method name to the broken one and re-ran it — real failure,
`AttributeError: 'QdrantClient' object has no attribute
'get_collection_cluster_info'. Did you mean: 'collection_cluster_info'?`,
raised because the narrowed handler no longer swallows it. Reverted the
mutant, re-ran, green again.

**The general shape, recorded where its family lives.** `docs/PRACTICE.md`
§2 gains a thirteenth entry: an exception handler with an explanatory
comment is an unchecked coverage claim about which failure it catches, and
worse than the family's other instances because the comment actively
reassures a reader rather than merely failing to warn one. Full entry with
the instance, the tell, and the repair.

**The stale-reference finding, collected rather than left loose.**
`oneground/verify/compose/qdrant.yml`'s own comment — *"cluster shapes are
task 011 on a pod"* — checked against task 011, which built the cost model
and the `runpod` target, never cluster verification. Folded into `tasks/
finding-a-ruling-made-in-conversation-is-not-in-the-product.md` as a second,
narrower instance of the same general shape (a citation rather than a
whole absent brief), with the general form stated: a comment citing a task
number is a claim nobody verifies. A third instance was searched for, by
the same method used to verify this file's own claims, and not found;
the finding says two, not three, rather than stating a count it could not
check.

## Measurements

- Live conformance run against a real, single-node `qdrant/qdrant:v1.19.1`
  (Docker Desktop + WSL2, installed this task for this purpose): `describe:
  5000 points, dim 64, index hnsw {...}, nodes 1` — correct, real, declared.
- The same run with the method name reverted: `AttributeError` raised (not
  swallowed) and the new assertion's failure message printed, confirming
  both the narrowed handler and the new test independently catch the
  regression.
- `hasattr(QdrantClient(url=...), "get_collection_cluster_info")` → `False`;
  `hasattr(..., "collection_cluster_info")` → `True`. Checked once, stated
  here rather than assumed from the traceback alone.

## Verification

`oneground/adapters/conformance.py -k qdrant` against a live engine: 1
passed (both with the fix, and failing correctly with the mutant
reintroduced, per Measurements above).

Full suite, guard, identifier scan and `site/teaser/`: reported at the
merge, per the established pattern.

## Observed, not done

**`nodes` on a genuinely non-clustered older Qdrant version** (one that
predates the `collection_cluster_info` endpoint, if any such version this
adapter is meant to support exists) was not checked — only the pinned
`v1.19.1` was available to test against. The narrowed `UnexpectedResponse`
catch is written for exactly that case; it was not exercised against a
real old server, only reasoned about from the client's exception
hierarchy.

**pgvector's `describe()` was not touched.** It declares `nodes=1`
directly, with no cluster-info call to have the same class of bug in.

## Repo now contains

Changed:

- `oneground/adapters/qdrant/adapter.py` — the method name fixed; the
  `except` narrowed to `UnexpectedResponse` with an accurate comment
- `oneground/adapters/conformance.py` — check (d) asserts `facts.nodes is
  not None` against a live engine, and prints it
- `docs/PRACTICE.md` — §2's thirteenth entry
- `tasks/finding-a-ruling-made-in-conversation-is-not-in-the-product.md` —
  the qdrant.yml/task-011 instance folded in, with the general form stated

New:

- `tasks/056-qdrant-describe-nodes-fix.report.md` — this file

## Blocked on developer

Nothing. Committing, pushing to `task-056`, and merging into `main` once
its checks are green, per standing instruction.
