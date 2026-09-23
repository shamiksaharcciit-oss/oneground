# Finding — a path check that accepts a directory is a refusal that never fires

*Task 046. Found by measuring what the jobs page's run button actually did:
it enqueued `oneground characterize .`, and the command came back with a
`PermissionError` traceback rather than a refusal.*

## What happens

`oneground/intake/__init__.py:load()` opens with:

```python
if not os.path.exists(path):
    raise RequirementsError(f"requirements file not found: {path}")
with open(path, encoding="utf-8") as f:
    data = yaml.safe_load(f)
```

`os.path.exists` is true for a directory. So a directory reaches `open()`,
which raises `IsADirectoryError` on POSIX and `PermissionError` on Windows —
neither of which is a declared refusal, so `cli.main` re-raises it and the
user gets a stack trace.

Measured, from this worktree:

```
$ oneground characterize .
exit 1
PermissionError: [Errno 13] Permission denied: '.'
Traceback (most recent call last): ...
```

## Why it is the shape it is

This is the refusal defect one notch further in, and the notch matters.

The one task 046 fixed was **a refusal that existed and arrived badly**:
`RequirementsError` was raised correctly, with a named field and a remedy,
and `cli.main` let it out as a traceback. The repair was to catch it.

This one is **a refusal that was never raised at all.** The check that should
have produced it — *is there a requirements file here?* — was written as *does
this path exist?*, and those differ on exactly one input. Nothing downstream
can recover a refusal that was not made; `refusals.py` has nothing to
classify and the supervisor correctly calls the job `failed`.

> **A check that is nearly the right question produces a refusal that never
> fires.** `exists` for `isfile` is the cheapest possible instance: one word,
> correct in every case but one, and the one is a path a user can type.

## Why it matters more than the traceback

`intake`'s own module header states the two rules shaping all twenty-five of
its messages: **name the field**, and **refuse rather than guess**. A
directory gets neither. It gets an operating-system error naming a permission
problem that does not exist — the file is readable, it is simply not a file —
so the message is not merely unhelpful, it is **misleading about what is
wrong**.

And the failure mode is worse on Windows than on POSIX, where at least
`IsADirectoryError` says the true thing. A user on Windows is told about
permissions and will go and check permissions.

## The repair

One line, in the same style as the twenty-five around it:

```python
if os.path.isdir(path):
    raise RequirementsError(
        f"{path} is a directory, not a requirements file. Name the file "
        "itself -- `requirements.yaml` inside it, if that is what you meant.")
```

`isdir` rather than `not isfile`, deliberately: a path that exists and is
neither — a socket, a device — is rare enough that guessing at its message
would be inventing a case nobody has met, and `open()` failing on it is
honest. The directory is the case a person actually types.

**Not done here.** It is a change to `intake`'s refusals, which is the CLI's
contract and the fourth such change this slice has wanted; the last three were
ruled individually and this one should be too. Recorded with its one line so
the ruling is cheap.

## A note on how it was found

Not by reading `intake`, and not by any test. By running the command the
interface would have run, and reading what came back — the same way the
build defect was found, and the same way the CLI's traceback was. Three of
this slice's findings came from executing the product rather than inspecting
it, which is worth its own line somewhere: **the suite tests what the code
does; running the product tests what a user gets.**
