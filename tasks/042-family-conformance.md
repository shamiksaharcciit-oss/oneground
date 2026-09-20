# Task 042 — A family is a contribution: the suite and the documentation

## Setup
Branch `task-042` from `main`. Commit `task 042:` and push after every
commit. No pod is required; the 150k checks run locally or are reported
as couldn't-check with their cost.

## Why
A sharding method is a **family**, and a family is one of the four named
contribution units in the charter — alongside adapters, engines and
corpora. Three families ship. The protocol they implement is designed for
contribution and has never been used by a contributor, and the difference
between those two facts is this task.

Two gaps make the claim thinner than the charter states:

- **Adapters have a conformance suite; families do not.** An engine
  adapter must pass namespace lifecycle, recall against exact truth,
  index readiness and cleanup-on-failure before it is usable. A family
  relies on whatever acceptance criteria its own task carried — which was
  adequate when every family was written by this team and is not adequate
  for anyone else.
- **There is no document telling someone how to write one.** The
  protocol is discoverable by reading `models/base.py`. That is not the
  same as being documented, and a contribution unit nobody can find the
  instructions for is not a contribution unit.

This also closes something the proposals loop keeps pointing at. A policy
may only select among parameters of families that exist, so a genuinely
new idea returns *this requires a family that does not exist*. That
refusal is the tool naming the unit of work. It should be followed by a
place to go.

## Do

1. **The family conformance suite**, in the shape of the adapter one, run
   by a single command against any family — shipped or contributed. Each
   check states what it measured and what it means, and a failure names
   the protocol requirement it violated rather than an assertion.

   The checks, each with its reason:

   - **The parameter table is complete and honest.** Every parameter the
     family reads is declared; every declared parameter is read. A knob
     that exists and is undeclared cannot be swept; a knob declared and
     unread silently does nothing. Both are found by comparing the
     declared table against the keys the family actually gets.
   - **Defaults and omissions agree.** A parameter written at its default
     produces the same config label as its omission — 032's rule, applied
     to every family including new ones, because a sweep must not measure
     identical work twice.
   - **The ceiling is a real ceiling.** `ceiling()` must be ≥ measured
     recall at every configuration tested, and must equal 1.0 for a
     family that partitions nothing. A ceiling below its own recall is
     the decomposition lying, and every report that reads routing loss
     depends on it.
   - **Routing loss is invariant to the index.** The same partition, with
     each index algorithm, must give identical routing loss — by
     definition, since the partition decides reachability and the index
     does not. 034 verified this for the three shipped families; the
     suite makes it a requirement rather than an observation.
   - **Determinism, per the declared flag.** With `deterministic=True`,
     two builds on one machine produce byte-identical state. The
     cross-environment claim is `docs/STATE.md`'s two-part contract —
     identical decisions, scored floats within a couple of ulps — and the
     suite checks what it can on one machine and reports the rest as
     couldn't-check with the session that would settle it.
   - **Footprint is measured, not computed.** `footprint()` must be
     derivable from the built index rather than from a formula over
     vector count and dimension. The suite builds, measures, and refuses
     a family whose reported figure cannot be reconciled with the
     artifact — the 66×-measured-against-61×-high finding is why.
   - **State is emitted and renders.** The declared state columns exist,
     have the declared types, and are sufficient for the lab's ground and
     trace views. A family that cannot be drawn is usable and invisible,
     and the suite says which.
   - **Refusals, not crashes.** An impossible configuration (more shards
     than vectors, a centroid count above the sample size) is refused
     with a reason and does not abort a sweep — 034's dropped-row rule
     applied at the family boundary.

2. **Run it against the three shipped families** and paste the output.
   Any check a shipped family fails is a finding about that family, not a
   reason to soften the check — report it, do not weaken it. If
   `hash_sharded` or `single_node_hnsw` has never been measured for
   something the suite now requires, that is exactly what the suite is
   for.

3. **A worked example family**, complete and deliberately simple:
   `random_sharded` — partition by a seeded random assignment, no
   closure, no routing intelligence. It is a bad architecture and a
   perfect teaching artifact: it shows every protocol method, passes the
   suite, and its measured result (worse than hash on every corpus) is
   itself instructive. Ship it under `examples/` rather than as a
   selectable family, so nobody deploys it by accident, and say in its
   own docstring why it exists.

4. **`docs/FAMILIES.md`** — the contributor document, written for
   somebody outside this team:
   - what a family is, and the one-line test for whether an idea is a
     family, a parameter of an existing family, or something the
     simulator cannot represent;
   - the protocol, method by method, with what each is for and what
     depends on it — particularly that `ceiling()` is what makes routing
     loss meaningful and is therefore not optional;
   - the parameter table, with 026's rules: declared types, ranges,
     roles, constants declared as constants, defaults that do not
     re-label;
   - the conformance suite, how to run it, and what each failure means;
   - the worked example, referenced not reproduced;
   - what a family may never do: compute its own ground truth, read the
     projection, report a figure it did not measure, or rank itself
     against another family;
   - and how a family gets from a fork into the tool — the suite green,
     the acceptance criteria, and that a new family's first published
     result carries the same caveats as everyone else's.

5. **Point the refusal at the document.** `propose`'s *this requires a
   family that does not exist* gains one line naming `docs/FAMILIES.md`.
   The tool should say where to go next when it says no.

6. **The charter's claim becomes checkable.** `docs/CHARTER.md` says
   families are a contribution unit. Update it to state what that now
   means concretely — the protocol, the suite, the document — and
   record honestly that no family has yet been contributed from outside.

## Acceptance
- The suite runs against any family by name and reports per-check,
  with reasons, and refusals naming the protocol requirement.
- All three shipped families measured; every failure reported as a
  finding rather than absorbed.
- `random_sharded` exists under `examples/`, passes the suite, and its
  measured inferiority is reported rather than hidden.
- `docs/FAMILIES.md` written for an outside reader; a person who has not
  seen this codebase could implement a family from it.
- `propose`'s family refusal names the document.
- The charter says what the contribution unit concretely is, and that
  none has come from outside yet.

## Do not
- Weaken a check because a shipped family fails it. Let a family compute
  its own ground truth. Accept a computed footprint where a measured one
  is possible. Make `ceiling()` optional. Ship `random_sharded` as a
  selectable architecture.
