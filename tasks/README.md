# tasks/

Briefs (`tasks/NNN-name.md`) and the build agent's reports
(`tasks/NNN-name.report.md`). A brief is bounded: it is built, measured and
reported against, and anything discovered adjacent to it is recorded in the
report under "Observed, not done" rather than fixed in passing. Scratch
diagnostic scripts live in `tasks/scratch/`.

## Correcting a brief or a report

A brief is corrected in place rather than superseded by a second file: two
documents sharing a number is how one gets built and the other forgotten. Fold
and delete, and say in the commit what was kept.

**When you correct one, correct its checklist in the same pass.** A correction
updates the argument and leaves the acceptance behind, and **the acceptance is
where an implementer looks last and trusts most** — so a stale line there
outranks a corrected paragraph above it. Task 045 was corrected twice and both
times kept an acceptance line the correction had invalidated: once a count
that no longer matched the code, once the name of the one branch that could
not demonstrate the fix.

The same applies to any section of a document that states a current state
rather than a rule. State-bearing sections go stale silently, because nothing
fails when the world moves and the sentence does not.

## Currently blocked

Nothing. *(This section states a current state, so it goes stale silently —
see above. It last named task 041 as blocked on an unmerged `task-039`; both
merged, and 041 shipped. Emptied rather than deleted, because the next blocked
task needs somewhere to say so.)*
