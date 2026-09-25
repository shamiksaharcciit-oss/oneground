# Finding — a capability with no command

*Found while wiring `oneground propose translate` (task 063). `oneground/
proposals/translate.py` (task 059) implemented path 2 of the proposal
system in full — the CLI refusal, the sampling-parameter closed list, the
disclosure receipt, the payload boundary — with 14 real tests, all
passing, all against a real local HTTP server. It shipped, and its own
report described what tests it had and what real infrastructure they
ran against. It did not describe, because nothing asked it to, that no
command reached it: `oneground propose translate` did not exist. A
capability that closed a design conversation existed, correctly built,
as a function nothing called.*

## What this is, and what it is not

**Not a bug in `translate.py`.** Every test passed because every test
called `translate.translate(...)` directly, the way a library function
is tested — and the function did exactly what it claimed. Nothing about
the module was wrong.

**Not a bug in the test suite either.** The tests proved the function's
own contract: given a workdir, a sentence and a model, it calls the right
endpoint, shows the model only what it should, writes a policy and a
disclosure, and stops. That contract does not include "a user can invoke
this," because a unit test's job is the function, not the path to it.

**What actually happened: two different questions were answered by two
different kinds of evidence, and only one of them was checked.** *Does
this code do what it says* was checked, fourteen ways. *Can anyone
reach it* was never checked at all, because nothing in this project's
practice asks that question of a finished module the way it asks "does
the suite pass" or "does the guard cover this command." A task's report
format (`CLAUDE.md`) has a "Repo now contains" section listing files and
a "Blocked on developer" section for what's left — neither one has a
slot for "and here is how a user reaches this," so a report can be
complete by its own template and still not say whether the thing it
built has a door.

## The general form

**A capability can pass every test, satisfy its own position paper, and
have no way in, because tests call functions and users call commands.**
The two are different objects in this codebase — `oneground/cli.py`'s
`_dispatch()`/`build_parser()` on one side, a module's own public
functions on the other — and nothing connects them automatically. A
module's test file imports the module directly; it does not, and
should not, have to go through the CLI to prove the module works. That
correct, ordinary separation is exactly what leaves the gap invisible:
the thing that would notice a missing command (a person trying to run
one) never runs, because every test that exists takes the shorter path
around it.

**Why nobody caught it at the time.** The report `translate.py` shipped
with named what was tested and what infrastructure it ran against, in
detail — and did not name what wired it to a command line, because the
question "is there a command" is not one this project's report template
or review habit asks by name. A checklist that does not ask does not
fail to answer; it simply never poses the question, which reads,
afterward, exactly like an oversight because it is one, at the level of
the checklist rather than the person filling it in.

> The tell: **when a task's report lists what a capability does and what
> tests exercise it, ask a third question before calling the task
> closed: what does a user type, or click, to reach this at all.** A
> module with real tests and no entry point will pass every check this
> project already runs, because none of them ask that question — the
> same shape `docs/PRACTICE.md`'s own recurring-failure section keeps
> finding: a scope defined by what gets checked is correct for exactly
> as long as nothing exposes what the checks do not ask.

## What was checked afterward, and what it found

Asked directly, because one instance found by accident is not evidence
that it is the only one: whether any other built capability in this
tree has real tests and no reachable entry point — no CLI subcommand, no
lab/interface endpoint. Full detail in `tasks/063-propose-translate-
cli.report.md`; the shape of the answer belongs here.

**Four more exist, and every one of them is a different case from this
one.** `oneground/library/card_schema.py::submit_card` (task 058),
`oneground/bridge/import_result.py` (task 055), `oneground/bridge/
export.py` (task 051) and `oneground/verify/load.py::run_load_per_node`
(task 057) are all built, tested, and unreachable by any command or
endpoint — and every one of their own task reports says so, in an
"Observed, not done" line, at the moment each shipped. `translate.py`'s
own report did too. **The difference is what happened next.** The other
four's gaps have sat self-reported, across as many as seven subsequent
tasks, with no follow-up task ever closing them — task 060's own
state-of-the-product inventory even re-confirmed several by name and
still nothing followed. `translate.py`'s gap closed one task cycle
later, specifically because this finding's own trigger — the developer
asking about it directly — made it the thing being looked at. **A
documented gap and a closed one are not the same event, and the
document does not close it by existing.** Writing "no CLI command" in a
report's own "Observed, not done" section is not a different kind of
gap from the one this finding names; it is the same gap, with its own
receipt, which turns out not to be what closes it either.

## What is not decided here

Whether every module needs a CLI verb. Most of `oneground`'s modules are
correctly internal — called by `characterize`, `simulate`, `verify`,
`report` and never meant to be typed by a user directly. This finding is
about the narrower case: a module built specifically to be a *user-
facing* capability (translate exists because a person describes a
change in a sentence) that ended up reachable by nothing a person could
type. Telling that case apart from an ordinary internal library is a
judgement this finding names but does not automate.
