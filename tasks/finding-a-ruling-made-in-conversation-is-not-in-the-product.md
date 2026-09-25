# Finding — a ruling made in conversation is not in the product until something in the tree carries it

*Prompted by a stock-take that named "multi-node" as designed-but-unbuilt,
citing `tasks/037-multi-node-deployment.md` — a `deployment:` block,
`describe_deployment()` on each adapter, fan-out reported as slowest-node
against mean-node, staleness kept as an outcome distinct from recall loss,
and the rule that oneground never provisions, scales or stops anything.
Checked rather than taken on trust, per this project's own standing rule for
claims from any source, including the developer's.*

## What was checked

Whether `tasks/037-multi-node-deployment.md` exists, anywhere a commit could
have put it:

- Not in the working tree.
- Not in `main`'s history, nor any branch's — `git log --all -- "tasks/037*"`
  returns nothing.
- The string never introduced: `git log --all -S"multi-node"` and
  `-S"multi_node"`, over every commit in the repository, both empty.
- Not named in any current doc — `docs/CHARTER.md`'s own phase list, which
  names related backlog items by exact string (`node_counts`,
  `nodes_needed`, "Cluster heat view"), does not contain "multi-node" either.

`tasks/` briefs run 001 through 054 with one visible gap: 035, 036, then
038b, 039 — **037 and plain 038 are both absent**, no report, no brief,
nothing a `git log` over any ref surfaces. Whatever number a design once had,
the number is empty in the tree.

## What this is, and what it is not

**Not a gap in the queue.** A gap in the queue is a real thing not yet
started — findable, nameable, waiting. This is a claim that specific,
detailed design work — a schema, a method signature, a reporting rule — was
produced, reviewed and ruled on, describable in enough detail to sound like a
brief. None of that detail exists anywhere a second reader can check it. The
description was accurate to a real design, or it was reconstructed
after the fact and believed real, or it was invented for this
conversation — and from inside the tree, those three are indistinguishable.
That is the finding: **a claim about work that cannot be checked**, the same
family `tasks/T1-teaser-ground.report.md` recorded for a mockup named in a
brief and absent from every location a mockup could be.

**Not a defect in any command, guard or check.** Nothing here failed to run.
There is no bug to fix, because there is no artifact for a bug to be in.

## The general form

A ruling made in conversation is not in the product until something in the
tree carries it — a doc section, a brief, a comment with the date and the
decision. This project's own habit for design work is the position paper
before the code: `docs/HYBRID.md`, `docs/BRIDGE.md`, `docs/PROPOSALS.md`,
`docs/LIBRARY.md` each open by saying they were written before
implementation, for exactly this reason — so that a design decision has a
location a second reader can open, rather than living only in whoever
remembers agreeing to it. A ruling that skips that step is real to the
people who discussed it and to no one else, for exactly as long as both of
them remember it the same way.

**The tell:** if a design is detailed enough to describe from memory — field
names, function signatures, a specific reporting rule — ask where it is
written down before treating the description as the design. A precise
memory and a checked-in document produce identical-sounding summaries; only
one of them survives being asked "show me."

## A narrower instance of the same shape, found researching this one

`oneground/verify/compose/qdrant.yml`'s own comment: *"Single node. Verify
measures latency shape on one node in this task; cluster shapes are task
011 on a pod."* Checked: `tasks/011-cloud-verify-cost.md` and its report
built the `runpod` verify target, the load generator and the cost model
(`nodes × node_price × hours/month` — a capacity estimate, not a
measurement of a running cluster). It never built cluster verification.
The comment has pointed at a task that does not close its own gap since
the file was written, uncorrected.

This is the same general shape one size down: not a whole brief that never
reached the tree, but a comment *citing* one that, when checked, turns out
not to have done the thing cited. **The general form: a comment citing a
task number is a claim nobody verifies**, and it is cheaper to write than
the work it cites, which is exactly why it survives — nothing about
writing "task 011" costs more than writing nothing, and nothing checks
that task 011 actually settled what the comment says it settled.

Two instances of this shape are recorded here, both found in this same
research pass. A third was not independently found — searched for in
`docs/PRACTICE.md` and the other `tasks/finding-*.md` files by the same
method used to verify this file's own count elsewhere, and nothing else
matched the pattern closely enough to cite as a third without the same
verification this whole finding insists on. If a third instance is known,
it belongs here by name; absent that, this file records two, not three,
because a count stated on trust is the same failure this finding exists to
name.

## What is not decided here

Whether "multi-node" should be designed at all, and if so what it means
in this project's terms — a new simulated family, real-cluster
verification, something else — is a product decision this finding does not
make. `docs/HYBRID.md`/`docs/BRIDGE.md`/`docs/PROPOSALS.md`/`docs/LIBRARY.md`
each exist because someone wrote the position paper first; multi-node has no
paper, position or otherwise, in the tree, and that is a decision for
whoever owns the roadmap, not a gap this finding closes.
