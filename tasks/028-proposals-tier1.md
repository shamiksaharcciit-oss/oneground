# Task 028 — Proposals, tier 1: the loop without a model

## Setup
Branch `task-028` from `main` at `dba2fed` **after** `task-020`'s rebase
has landed — check `git log origin/task-020 -1` shows a rebase onto
`dba2fed` first, and if it does not, wait and say so. Work only on
`task-028`; `main` stays frozen for release content until 23 September.
Commit `task 028:` and push after every commit.

## Why
026 built the parts with no model in them: each family's parameter table,
the policy schema and validator, the prediction file with its digest cited
by the run, and the two-run verdict rule. What does not exist is the loop
those parts are for.

Tier 1 is that loop with the model removed: **the user writes the policy
themselves.** Pick a family, change a parameter, state a prediction, run,
get a card. No translation, no approval flow, no model anywhere — those
are tier 2, and they are only writable once tier 1 has run on a real
corpus and we know what a policy looks like in practice.

This task is a receipt-machinery proof, not a demonstration. If the
prediction digest, the two-run verdict or the card's claims are wrong, it
is far cheaper to find out here.

## Do

1. **The command.** `oneground propose <workdir> --policy <file>
   --prediction <file>` — both written by the user, both validated before
   anything runs, both refused with everything wrong named at once (the
   022 precondition rule). It runs the changed configuration against the
   same sample, seed and ground truth as the baseline already in the
   workdir, and writes a card. `--dry-run` validates and prints what it
   would run, without running.

2. **The baseline is not re-run.** The workdir already holds the baseline
   configuration's `simulate.json` row; the proposal runs only the changed
   configuration and compares against that row, citing it by digest. If
   the baseline row is absent, or its digest does not match what the
   prediction cited, refuse — naming which, and what to run.

3. **The card.** `card.json` plus `card.html`, written through the 019
   `Claim` renderer so every sentence is reconstructible from the rows it
   cites. It carries: the policy (in full), the prediction with its
   digest, the baseline and changed configurations, the measured result
   per predicted metric, the side-effect budget against its bounds, the
   environment, the calibration line the verdicts were judged under, and
   one outcome — **held**, **did not hold**, or **couldn't check** — from
   026's two-run rule.
   What the card may never say, tested: that the change is good,
   recommended, or should be deployed; anything about a corpus other than
   this one; that a result on this sample holds at full scale. The
   sample caveat is in the card's own text, not a footnote.

4. **Failures are cards too.** A proposal whose prediction did not hold
   produces a card, published, with the same completeness as one that
   held. A run that could not complete produces a couldn't-check card
   naming why and what would settle it. There is no path that produces
   nothing.

5. **The side-effect budget is the interesting half.** A prediction names
   metrics that must *not* move beyond stated bounds. Implement it as a
   first-class part of the verdict: a proposal whose predicted metric
   moved as promised but whose budget was breached is **did not hold**,
   with the breach named first. Most well-meaning changes die here and the
   card should show why.

6. **End to end on a real corpus.** Run it on the arXiv workdir with two
   proposals of your own writing — one you expect to hold (a probe or
   efSearch increase against a recall prediction) and one you expect to
   fail on the side-effect budget (an ε increase against a storage bound).
   Paste both cards' text in full. If either outcome surprises you, say so
   rather than adjusting the prediction.

7. **Docs.** `docs/PROPOSALS.md` gains a "Tier 1: writing a policy
   yourself" section — the two files, what each field means, the refusals,
   and one worked example. Mark plainly that the model-written tier is not
   built.

## Acceptance
- Two real cards from the arXiv workdir, pasted, one held and one not.
- Every card sentence passes the 019 claim invariant; the forbidden
  claims are tested.
- A missing or mismatched baseline digest refuses, naming what to run.
- A budget breach produces *did not hold* with the breach named first.
- `--dry-run` runs nothing; a failed run still writes a card.
- Suite green, guard clean, identifier scan runs rather than skips,
  pushed after every commit.

## Do not
- Put a model, an API call, or a prompt anywhere in this task. Re-run the
  baseline. Emit a card that recommends. Touch `main`, the tag, `site/`,
  or `task-020`.
