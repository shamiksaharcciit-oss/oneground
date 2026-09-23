# Task 046 — the four times this slice wanted to change one module's contract

*Collected rather than raised one at a time, because four of them is a
finding about the module and not four findings about a UI slice. To be ruled
on as a shape when 046 closes.*

**The shape, stated first so the instances read as evidence for it:** a slice
that touches no measurement and adds no stage has needed to reach into how
`intake` and the CLI express a refusal **four times in one week**. Every one
was found by running the product rather than by reading it, and every one was
invisible from inside the module — because from inside, each refusal is
correct. What is wrong is what happens to it afterwards.

## 1. `cli.main` let refusals out as tracebacks — **ruled, taken**

`intake.RequirementsError`, the project's own refusal type with twenty-five
messages that each name a field, escaped `main` unhandled. The commonest
refusal in the product reached every command-line user as a stack trace with
the sentence on the last line.

Taken in this slice as a deliberate contract change: one line, no traceback,
exit 2. `tasks/finding-refusals-arrive-as-tracebacks.md`.

## 2. Two types carried a refusal and a failure at once — **ruled, taken**

`embed.EmbedError` said so in its docstring and was raised nowhere;
`registry.ModelUnresolved` said so too and was live in three places. A caller
handed either could not tell which it got.

Split, bases kept, with the undecidable third site keeping the ambiguous base.
`tasks/finding-one-class-two-outcomes.md`.

## 3. A bare `ValueError` for a precondition — **examined, correctly left**

`embed/multimodel.py:138`. I reported it as a refusal wearing no type;
measuring showed `multimodel.run` has **no callers** and its message
addresses a programmer. It is a precondition, and typing it as a refusal
would put a programmer's sentence in front of a user. Left alone, and the
finding corrected rather than left to stand.

Listed because *the wrong ones matter to the shape*: a module whose refusals
are hard to tell from its preconditions is a module worth looking at, and
three of four wanting a change while the fourth looked like one is part of
the evidence.

## 4. `intake.load` accepts a directory — **pending**

`os.path.exists` where `isfile` was meant, so a directory reaches `open()`
and raises `PermissionError` on Windows — a message that is misleading rather
than merely unhelpful, since the file is readable and simply is not a file.

One line, written out in
`tasks/finding-a-path-check-that-accepts-a-directory.md`. Not taken.

## What the four have in common, which is the thing to rule on

They are not four defects in one module. They are **one seam**, hit from four
angles: the boundary where `intake`'s refusals stop being `intake`'s problem.

- Inside `intake`, all twenty-five refusals are correct: named field, stated
  remedy, refuse rather than guess. The module honours its own header.
- Outside it, nothing knew a refusal from a failure, one refusal was never
  raised at all, two types carried both, and the CLI printed the lot as
  tracebacks.

**No test could have caught any of them**, and that is the common cause
rather than a coincidence. `intake`'s tests assert that `load()` raises
`RequirementsError` with the right message — which it does. Every defect
above is about what happens to that exception *after* it leaves, and nothing
owned that question until a supervisor had to classify one.

> So the question worth ruling on is not any of the four. It is: **who owns a
> refusal after it is raised, and where is that written down?** Today the
> answer is `oneground/refusals.py`, which task 046 wrote for its own needs
> and which now carries a sixteen-entry table nobody outside this slice has
> agreed to.

The three smaller questions that follow from it, for the same ruling:

1. Should `refusals.py`'s table live where the refusals do — a declaration in
   each module, rather than one list that has to know sixteen dotted names?
2. Is `exit 2` the contract, or an implementation detail this slice promoted?
   It is now load-bearing for the supervisor's classifier.
3. Does `intake` owe a refusal for every way a requirements file can be
   unusable, or only for every way its *contents* can be? Number 4 above is
   that question with a concrete instance.
