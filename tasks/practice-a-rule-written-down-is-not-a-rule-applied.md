# For `docs/PRACTICE.md` — a rule written down is not a rule applied

*From task 044c, for the interface stream to place. It is a companion to §4,
*A key whose meaning differs by file*, which came from task 043 — this is the
same task's other rule breaking in the task immediately after it, against the
same author. Whether it reads better as a §4.1 or as its own section is yours
to judge. What it cost is at the bottom.*

## The rule

> **A rule you have written down is not a rule you have applied, and the tell
> is a new write site rather than a new file.**
>
> When a rule governs what may be written into a file, it is enforced at every
> place that writes — including the places that do not look like they are
> producing the kind of file the rule was written about.

## Why the usual instinct fails

The check people perform is *is this file the kind the rule covers?* That
question is answered at the wrong time. A file's kind is often decided **after
it is written**, by someone deciding to keep it, publish it, cite it or commit
it — and the write site has no way to know which of those will happen.

So the rule appears not to apply, truthfully, at the only moment it could have
been applied cheaply.

The working question is not *is this a receipt?* but **does this write a
path, a hostname, a home directory or a machine name?** That one can be
answered where the code is, by the person writing it, without knowing what
anyone will later do with the output.

## The instance

Task 043 built `receipts.public_path` and ruled that a machine-local path is
sanitised **at the write site**. The ruling was not theoretical: sanitising at
publish time had already forced the identical fix at **three separate
boundaries in one task** — the teaser exporter, which owned the function; the
fixture builder; the report writer.

Task 044c, the next task, written by the author of 043's report:

- a scratch script wrote the absolute path of the developer's asset store into
  its JSON output;
- the output lived under `runs/`, which is gitignored, so at the moment of
  writing the rule genuinely did not apply;
- rule 9 — *an artifact a report cites lives in the main checkout* — then made
  the file evidence, and it was copied into the tracked tree and committed.

**A fourth write site, opened by the person who wrote the rule down, one task
later.** The author had the transform, knew the rule, and did not ask whether
a file that gets committed is a receipt. It is.

## What caught it, and what did not

- **Not review.** The script was read and extended four times.
- **Not the copy step.** Its digests were checked carefully — and the wrong
  property was verified: that the copy matched its source, not that either was
  fit to commit.
- **Not a correction pass about these exact files.** A CRLF-normalisation
  issue was found and fixed *in the digests of the same four files*, without
  anyone asking what was inside them.
- **It was `test_no_tracked_file_carries_a_machine_identifier`**, which task
  015 found missing and 017 built, after task 016 published two absolute
  developer paths in `tasks/016-decision-log.txt` with nothing noticing.

A guard built for precisely this, many tasks earlier, catching the author of
the most recent rule about it. That is the argument for mechanical guards over
documented rules in one line: **the guard does not need to be in front of
anyone.**

## The tell

**You have just created a new place that writes a file, and you are thinking
about what the file contains rather than where it might end up.** If any
written field can name a filesystem, a host or a person, apply the project's
transform there — not later, and not with a local equivalent.

The corollary matters as much: **the repair is the shared function, not a
string replacement.** 043's own finding is that a second private
implementation of a shared rule is a second place for it to be wrong. Writing
one inside the fix for that finding would have been a fifth instance rather
than a fourth.

## What it cost

Task 043 recorded four instances of one defect and a fifth written by the
person eliminating the first four. This is the same task's *other* rule,
broken by the same author, in the very next task — the machine-local path
reaching the tracked tree despite a shipped transform, a written ruling and a
report arguing for it.

Caught before merge by a test, not by a person, and fixed by calling the
function that already existed. The cost is one failed suite run and the fact
that the tracked evidence for a report no longer byte-matches the run that
produced it — a small price for the clearest possible demonstration that
**writing a rule down and being the person who wrote it are not protection
against breaking it.**
