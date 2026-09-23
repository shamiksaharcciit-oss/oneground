# Finding — a refusal and a failure sharing a class, twice, in one package

*From task 046. `oneground/refusals.py` classifies exceptions as the tool
declining or the tool breaking, and `embed.EmbedError` had to be excluded
because it is declared as both. That exclusion is a statement about the type,
not about the table, and it deserved measuring rather than a footnote.*

Measured, it is two types rather than one, and the interesting one is not the
one that was excluded.

## `EmbedError`: declared as both, and raised nowhere

```python
class EmbedError(RuntimeError):
    """Text was supplied with no model to embed it with, or the model failed."""
```

*No model to embed it with* is a refusal: the user's file did not name one,
and the remedy is to name one. *The model failed* is a failure: something
came apart. One class, two outcomes, and a caller handed one cannot tell
which it got.

**It is exported in `__all__` and raised zero times.** Nothing in the package
raises it. So the ambiguity is, today, entirely hypothetical — and that is
what makes it worth acting on now rather than later:

> **The cheapest moment to split a type that promises two things is before
> anything raises it.** There are no call sites to migrate, no messages to
> re-word and no callers to re-test. Every raise added from here makes the
> split more expensive, and the docstring is an instruction to the next
> person to use one class for both.

## `ModelUnresolved`: the same defect, live, and it says so itself

This is the one that matters.

```python
class ModelUnresolved(ValueError):
    """A model name that sentence-transformers could not load.

    Names what was tried and what the failure was, because the two common
    causes -- a typo and no network -- need different actions from the reader
    and the underlying exception distinguishes them badly.
    """
```

Raised three times in `embed/registry.py`. **A typo is a refusal** — the
user's requirements file names a model that does not exist, and the remedy is
to fix the name. **No network is a failure** — the name may be perfect and
the machine could not reach HuggingFace.

The docstring already contains the whole finding: *the two common causes need
different actions from the reader*. It solves the problem for a **human**, by
putting both into the message. It does not solve it for a **caller**, which
is what `refusals.is_refusal` is, and what the supervisor's classifier is:
one class, so one answer, so the answer is wrong for one of the two causes
whichever way it is given.

And the last clause is the sharpest part: *the underlying exception
distinguishes them badly*. The information exists one layer down, is known to
be poor there, is correctly re-expressed for a reader — and is then lost for
every programmatic caller, because it went into prose rather than into the type.

## Why both are excluded rather than guessed at

`refusals.py` lists them in `NOT_REFUSALS`, and the reason is not that they
are failures. It is that **they are both**, and a type that cannot answer
which it is has to be excluded.

Note which way that exclusion is safe. Calling one a refusal would present a
broken network to the user as *the tool declined, and here is what to do* —
telling them the tool meant it, and sending them to fix a model name that was
never wrong. Calling it a failure shows a traceback for a typo, which is the
old defect and is bad, but it is bad in the direction of saying less rather
than saying something false.

> **Excluding a type from a classification is a statement about the type.**
> It says *this class does not carry enough to answer*, and that is a finding
> to record rather than a gap in the table to apologise for.

## What splitting would cost

**`EmbedError`: nothing.** Delete it, or split it into a refusal and a
failure and raise neither until there is a use. It is dead.

**`ModelUnresolved`: three raise sites and their tests.** Split into
`ModelUnknown` (the name resolves to nothing — a refusal) and
`ModelUnreachable` (the name may be fine and the load failed — a failure),
with the common base kept so `except ModelUnresolved` in any caller keeps
working. The three sites already know which they are: `registry.py:81` and
`:94` are decisions about the name, `:132` is the load attempt.

The work is small. What it buys is that `refusals.py` gains a row it can
justify, the supervisor can classify a mistyped model name as `refused` and
show the user the name and the remedy, and the distinction the docstring
already argues for becomes available to something other than a person reading
the screen.

**Not done here.** It changes an exception type three modules use, which is a
contract change of the same kind as the refusal fix and worth ruling on
separately rather than folding into a UI slice. Recorded with its cost so the
ruling is cheap.

## One more thing found on the way

`embed/multimodel.py:138` raises a bare `ValueError` for *"multimodel.run is
for two or more models"* — which is a refusal, with a named field and a
remedy, wearing no type at all. It cannot be classified, cannot be caught
distinctly, and would reach a user as a traceback. It is the same defect
again with the class omitted entirely rather than overloaded.
