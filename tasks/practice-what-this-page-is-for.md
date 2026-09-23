# For the top of `docs/PRACTICE.md` — what the page is for, and what it is not

*Ruled by the developer: this belongs at the top of the page itself, not only
in the note it came from. It is still yours to place and word — the page is
yours — but the ruling is that a reader who meets the page without it will
either over-trust it or dismiss it, and **both are the same misreading**.*

*It follows the existing opening well: that one says what earns a rule its
place, and this says what a rule, once placed, can and cannot do.*

---

## Suggested, for immediately after "If you want to add one, bring the instance"

### What this page is for

**These rules are for diagnosis, not prevention.**

That is not modesty and it is the only honest reading of the record. The
clearest case on this page is a rule broken three times by its own author
within a week — including once where the warning had been written **by the
person who would need it, about the exact command, in the file that command
reads.** There is no version of *put the rule closer to the action* left to
try; it was already as close as text can get.

Every one of those three was caught by a **mechanism** — a failing test, three
times — and *understood* because a rule existed to name what had happened.
That is the division of labour, and it holds across the page:

> **A rule shortens the distance between a symptom and a decision. It does not
> shorten the distance between an intention and an action.**

A reader who expects the second will conclude the page is useless, because it
will keep failing at a job it was never doing. A reader who expects only the
first gets what it actually provides: when something goes wrong, the failure
is named, placed against what is already known, and ruled on in one pass —
instead of being repaired as the one-line change it superficially looks like.

**So knowing the list is not the same as not making the mistakes**, and the
page says so elsewhere already. What this section adds is that this was never
the promise.

### And therefore: the repair form

If a rule cannot prevent, the repair for a rule that keeps being broken is not
a better-worded rule. It is to **remove the moment of choice.**

The page has been converging on this without naming it. Nearly every durable
fix recorded here is the same move — not *document the hazard* but *make the
hazardous form unavailable, or make it refuse*:

| the rule | the fix that actually held |
|---|---|
| a gated commit must not run in the background (§3) | the launcher refuses it |
| a verify run must not overwrite another's receipts | `guard_verify_output` refuses, and archives first |
| a receipt must not name a filesystem | `write_json_stable` refuses the payload; the exporter refuses at the publishing boundary |
| a page must not cite an uncommitted report | the exporter refuses the source |
| historical receipts must not be bulk-added | staging by path, so `git add -A` is not typed |

Each removes a decision rather than describing one.

**The last is smallest and is last on purpose, because it makes the argument
the other five cannot.** The other five fixes could all be read as a rule
merely being enforced better — a warning turned into a refusal, which still
leaves "write the warning well" on the table as an alternative. The
`git add -A` case removes that reading. The warning existed, in `.gitignore`,
written by the person who would need it, about that exact command, in the file
the command consults. It was **maximally well placed** and it failed twice
anyway. So it rules out the remedy a reader would otherwise reach for first,
and leaves only the one that worked: never typing the command.

> **When a rule is broken twice, stop editing the rule and look for the
> decision to delete.**

That turns this page from a list of mistakes into an argument for a kind of
fix, which is a more useful thing for it to be — and it gives a reader
something to do with an entry besides remember it.
