# For `docs/PRACTICE.md` — a key whose meaning differs by file

*From task 043, for the interface stream to place. The page's constraint is
that nothing goes in it that has not cost something; what this cost is at the
bottom.*

## The rule

> **A key whose meaning differs by file is a defect waiting to be written.**
> Before adding a field to a receipt, look at what that name already means in
> every other artifact that carries it — not at whether the name is free.

## Why the usual instinct fails

The check people actually perform is *does this key already exist here?* That
is the wrong question, and it passes exactly when the defect is about to be
introduced: the name is free **in this file**, which is what makes it
available, and taken **in another**, which is what makes it wrong.

The failure is invisible at the point of writing and invisible afterwards. The
field is present, well-formed and plausible. Nothing is missing, so no absence
check fires; the value is of the right type and shape, so no schema check
fires. It surfaces only when a reader that knows the *other* meaning reaches
the *new* block, and then it surfaces as a wrong value rather than as an
error.

## The instance

`report.json` carries two environment blocks, deliberately:

```
environment       the machine that MEASURED
run_environment   the machine that WROTE THE REPORT
```

For a pod run those are different machines, and the distinction is the point
of having both.

Task 043 needed `characterize` to record where a run happened, believed the
block was missing from `build_info.json`, and added `run_environment` to it.
Two things were true and neither was visible from the edit:

- `build_info.json` **already carried `environment`**, holding the same stamp,
  **three lines below** where the new key went.
- In `build_info.json` there is no separate reporting machine, so
  `run_environment` there means *the measuring machine* — the opposite of what
  the same key means in `report.json`.

The result was a second block reading as a different fact, in the function
whose defect is that names mean different things in different files, in the
task that existed to eliminate that defect.

## What caught it, and what did not

Not review. Not the test suite — the writer change was correct in isolation
and every test passed. Not the exhaustive reader test written in the same
task, because that test finds **absences** and this was a **wrong value**.

It was caught by an instruction to look at the blocks rather than the fields,
which meant reading `report.json`'s two environment blocks side by side, which
is when the duplicate three lines away became visible.

## The tell

**A fix to the writer changes nothing.** If you have just made a producer
record something and the consumer still reports it missing or wrong, the
problem is not in the producer — either the reader consults the wrong source,
or you have written the right value under a name that means something else.

## What it cost

The fifth instance of the defect, written by the person eliminating the first
four, in the task doing the eliminating, after three of them had already been
diagnosed. One reverted commit, and it would have shipped had the ruling
arrived an hour later.

Full account: `tasks/043-provenance-foundation.report.md`, leading section.
