# Finding — a reported gap is not a scheduled one

*Prompted by `tasks/finding-a-capability-with-no-command.md`'s own
audit: `translate.py` and four other built, tested capabilities
(`oneground.library.card_schema.submit_card`, `oneground/bridge/
export.py`, `oneground/bridge/import_result.py`, `oneground/verify/
load.py::run_load_per_node`) each shipped with an "Observed, not done"
line naming exactly this gap. Only one of the five has since closed.
This finding is about why four did not, and it is a claim about the
project's own practice, not about any one of the five capabilities.*

## The evidence, counted rather than gestured at

Five capabilities, five self-reports, one closure:

| capability | task | self-reported | closed |
|---|---|---|---|
| bridge exporter | 051 | `tasks/051-vectordbbench-exporter.report.md` | no |
| bridge importer | 055 | `tasks/055-vectordbbench-importer.report.md` | no |
| multi-node fan-out | 057 | `tasks/057-multi-node-fan-out.report.md` | no |
| library validator | 058 | `tasks/058-library-card-validator.report.md` | no |
| proposals path 2 | 059 | `tasks/059-proposals-translate.report.md` | **yes — task 063** |

Four of the five sat unwired across every task that followed them —
`export.py` across eight (051→055→057→058→059→060→062→063),
`submit_card` across five (058→059→060→062→063) — including
`tasks/060-state-of-the-product.report.md`, whose own inventory named
several of them again, by name, in the same self-reporting shape, and
still nothing followed. The one that closed did so at task 063, one
cycle after task 059 shipped it — and closed specifically because it was
asked about by name, not because its own report had said "no CLI
command" three tasks earlier than the others said the same thing about
themselves.

## The claim

**A self-reported gap is a gap that has been seen, and seeing it obliges
nobody.** Writing "no CLI command" in a task's own "Observed, not done"
section is a true, complete, honestly-written sentence, every time it
happened here — and it is also, on this evidence, indistinguishable in
its effect from not writing it at all. Reporting a gap and closing one
are different acts, performed by different mechanisms, and **this
project has only ever built the first.** A brief produces a report; a
report's "Observed, not done" line produces nothing that reads it back.
There is no ledger of open "Observed, not done" items, no task that
exists to sweep them, and no check anywhere in this codebase — the same
family `docs/PRACTICE.md`'s own recurring-failure section tracks for
other things — that asks, of a merged task, whether its own prior
self-report is still true.

**Why five is enough to say this rather than four, or one.** One
instance is an oversight; four with the identical shape, across a
combined nineteen task-cycles of not being followed up, several of them
re-surfaced by a dedicated audit that still did not trigger a fix, is a
property of the mechanism rather than of any capability. The fifth —
the one that closed — is not a counter-example to the claim; it is the
control that isolates the variable. The only difference between it and
the other four is that someone asked about it by name. Nothing about
its report made it more discoverable, more urgent, or more finished
than the other four's reports; the asking is the entire difference, and
the asking is not a mechanism this project has built — it is what
happened this week, once, from outside the loop that produces reports.

## What this is not

**Not a claim that self-reporting is worthless.** Every one of the five
reports is the reason this finding is checkable at all — each states,
precisely, what was built and what was left, and this finding's own
table is built entirely from reading them back. The failure is not in
the honesty of the report; it is in treating the report as the last
step rather than the first one of a second process that was never
built.

**Not a claim about any one capability's priority.** Whether `submit_
card` is worth wiring before `run_load_per_node` is not this finding's
question, and it does not rank the four. It states that "reported"
and "scheduled" have been the same word in this project's practice so
far, and they are not the same fact.

## The general form

> A report that names what it left undone is not thereby a task that
> will do it. The two need different mechanisms — one that produces the
> honest sentence, and a separate one that reads every such sentence
> back and asks whether it is still true — and a project that has only
> built the first will accumulate exactly the gaps this one did:
> correctly reported, and correctly still there.

The tell, for next time a task's own report says "not done": **ask
what, mechanically, causes that sentence to be read again** — not
whether it is true when written, which every instance here already
was, but whether anything is going to look at it a second time. If the
honest answer is "whoever happens to ask," the sentence is doing the
work of a receipt without the follow-through a receipt is supposed to
earn.

## What is not decided here

Whether this project should build the second mechanism — an "Observed,
not done" ledger, a periodic sweep, a task type dedicated to closing
prior gaps — or whether asking, by name, when it matters, is judged
sufficient given how small this project's task cadence still is. That
is a process decision for whoever owns the practice, not a gap this
finding closes by naming it.
