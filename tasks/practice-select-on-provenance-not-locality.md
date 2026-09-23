# For `docs/PRACTICE.md` §2 — a survey that excluded its own motivating case

*From task 044d, for the interface stream to place. The developer's reading is
that this is the sharpest instance of §2 warning 3 so far and is worse than
the canonical form; whether it becomes the next numbered warning or a
sub-entry under 3 is yours. **No number is written in below** — §2 was at
seven warnings when this was drafted and is at eight by the time it is sent,
so numbering it here would be the stale-state defect §1 is about. What it cost
is at the bottom.*

---

**A survey gave a clean bill of health from a predicate that structurally
excluded the case that prompted it.**

## The rule, and it is one line of work

> **Run the audit against the tree *before* the fix, and require it to name
> the known instance. A survey that cannot rediscover its own motivating case
> is not evidence.**

This is the whole entry and everything below it is why. It generalises past
the particular mistake to **every audit anyone writes here** — every "are
there others like this?" step in every brief — and it costs one run against a
commit you already have. There is no excuse for skipping it.

The asymmetry that makes it necessary:

> **A check that cannot fail is suspicious. A check that passes convincingly,
> while unable to see the one case that prompted it, is trusted.**

Warning 3 is *a check that passed for the wrong reason, which is worse than
one that fails*. This is that at its worst setting, and what makes it worse is
how the result is received rather than anything about the check. An all-clear
from a survey reads as evidence of absence. This one had a plausible
predicate, a real AST walk over the real tree, and nine named candidates with
line numbers — the texture of a thorough negative result. Nothing in the
output suggested it had not looked where the defect was.

## The instance

Task 044d fixed two published fixtures reading outside the
band they were themselves the endpoints of, caused by a percentile stored to
two decimals and compared against a full-precision recomputation under a
strict inequality. The brief added a survey step: find any other stored
rounded literal in the same situation, because one that currently passes is
only passing by the direction of its own rounding.

The survey looked for **a rounded float literal whose name appears in a
comparison in the same module.** It reported nine candidates, judged all nine
as chosen thresholds, and found nothing.

It could not have found anything. `PUBLISHED_AMBIGUITY_PERCENTILES` is
declared in `measures/ambiguity.py`; the comparison that bit is in
`measures/crispness.py`, inside `against_published`, reached by passing the
table in as an argument. **Same-module comparison describes where this
particular defect happened to be caught — not what the defect is.** The
predicate was written from the memory of debugging it, which is the most
natural way to write one and the most likely to encode the investigation
instead of the fault.

## The repair for this particular audit

Distinct from the rule above: the rule catches the mistake, this is what the
survey should have selected on once it was caught.

> **Select on provenance, not on locality.** The question is not *where is
> this value used* but *where did this value come from*. A literal that is a
> rounded copy of a quantity the system can recompute is the defect; whether
> the comparison happens in the same file, another file, or a caller three
> layers up is an accident of structure.

"Compared somewhere" then needs no predicate at all, because anything worth
storing gets used. And the rewritten survey needs one distinction to be
useful, which is the other half of the rule:

> **A choice is not a copy.** `CRISP_RATIO = 1.20` is a rounded-looking
> literal, compared against a recomputed ratio, and it is *not* this defect —
> nothing recomputes "the true value of `CRISP_RATIO`". A threshold chosen in
> one module is a different kind of thing from a measurement copied between
> two. The defect needs **both sides to be the same quantity**, one stored
> short and one computed long.

Selecting on provenance turned 36 literals into 31 obvious choices and 5 to
judge by hand, of which none was this shape and two were an adjacent, milder
one. That is a survey whose negative result means something.

## The tell

You have written a search for other instances of a bug you just fixed, and the
search describes **how you found it**. A predicate written from the memory of
debugging encodes the investigation rather than the fault, which is both the
most natural way to write one and the most likely to be wrong in exactly this
way. Ask the search about the original; if it cannot see it, every zero it
returns is uninformative and will be believed anyway.

## What it cost Nine candidates, a confident all-clear, and — had the
mismatch not been noticed before the report was written — a sentence in a task
report saying no other instance exists, resting on a search that could not
have found one. The report would have been wrong in the direction reports are
least often corrected in: reassuring.

---

*Companion note: `tasks/practice-a-rule-written-down-is-not-a-rule-applied.md`
is from the same task's neighbour and belongs beside §4.*
