# Task 034, addition — what the engine can actually build

*To be merged into `tasks/034-index-algorithms.md` before it is executed.*

---

## Why this addition exists

034 makes the index algorithm a choice: `flat`, `hnsw`, `ivf`, `ivf_pq`,
all four measured in `simulate` against exact ground truth. Those are
faiss's four, and the simulation is honest about them.

Engines offer something else. Qdrant builds HNSW and nothing else —
its quantisation is a modifier on that graph, not a separate index
family. pgvector offers HNSW and IVFFlat, and its IVFFlat is not faiss's
IVF: different construction, different parameter names, different
behaviour.

So without this addition, a user simulates `ivf_pq`, learns it costs 3%
of recall for a fifth of the memory on their corpus, takes that to
`verify`, and finds out only afterwards that neither engine they are
considering can build it. The simulation answered a question about the
algorithm class; the deployment question is about what their engine
implements, and the tool should say so before the run rather than after.

The rules for this already exist and need no invention. The
same-configuration rule already refuses to let a measurement settle a
constraint for an option the engine was not built with, so an `ivf_pq`
row verified on Qdrant is already impossible. What is missing is that the
refusal should be **early, named, and distinguishable from an absence**.

## Do

1. **Each adapter declares its index families**, in the same shape as the
   parameter tables: which families it can build, and for each, the
   engine's own parameter names beside the family's declared ones. An
   adapter that does not declare them cannot be used to verify an
   indexed configuration — the conformance suite enforces the
   declaration, as it enforces every other protocol requirement.

   Do not guess what an engine supports. Resolve it live against the
   pinned versions, and where the mapping from a family's parameter to an
   engine's is not exact, record it as approximate with what differs —
   pgvector's IVFFlat is not faiss's IVF and the declaration must say so
   rather than implying a correspondence.

2. **`verify` refuses before it creates anything.** A configuration whose
   index family the engine cannot build is refused at plan time, naming
   the family, the engine, and what the engine does offer. This is the
   022 precondition rule and the money boundary applied together: the
   refusal must come before a pod is created, not after a run has been
   paid for.

3. **The report distinguishes three states, not two.** Today a
   constraint is `meets`, `fails`, or `couldnt_check`. The third now
   carries a reason that separates:
   - **not verified** — this configuration could have been verified and
     was not. Remedy: run it.
   - **not verifiable here** — no engine in this run can build this index
     family. Remedy: name the engines that could, or state that none of
     the adapters can and that this remains a simulation result.
   A reader must be able to tell "nobody ran it" from "it cannot be run
   here", because the actions are different and one of them is *choose a
   different engine*.

4. **Say it in the decision log**, in the sentence that already names
   what would settle a couldn't-check. For a not-verifiable-here row,
   what would settle it is not a command — it is a different engine, or
   an adapter that does not exist. The log should say which, and it
   should name the adapter as a contribution unit where that is the
   honest answer.

5. **Report the coverage.** After the sweep, one table: the four
   families against the adapters, showing which combinations are
   verifiable today. That table is a fact about the ecosystem rather than
   about the corpus, and it belongs in `docs/ADAPTERS.md` where someone
   choosing an engine will meet it.

## What this does not do

It does not make a simulation result less valid. An `ivf_pq` row measured
against exact ground truth is a true statement about that algorithm on
that corpus, and it stays in the report with its recall and its measured
memory. What changes is that the report no longer implies it is a
deployable option without saying where it could be deployed.

It also does not add engine-specific index families to `simulate`. If an
engine builds something faiss cannot, that is a gap in what the simulator
can predict and it is named as one — not papered over by simulating
something adjacent and calling it the same.

## Acceptance
- Every adapter declares its index families, resolved live, with
  approximate mappings marked as approximate and what differs stated.
- A configuration the engine cannot build is refused at plan time, before
  any billable resource exists.
- The report separates *not verified* from *not verifiable here*, and the
  decision log says what would settle each.
- The coverage table is in `docs/ADAPTERS.md`.

## Do not
- Guess an engine's capabilities from documentation rather than
  resolving them. Map a family onto an engine's nearest equivalent and
  call it the same. Let a not-verifiable-here row read as a run that
  simply has not happened yet.
