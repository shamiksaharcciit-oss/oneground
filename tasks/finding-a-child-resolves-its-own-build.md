# Finding — the same root three times: a process that does not know which build it runs

*Task 046. Recorded as a finding rather than left as three fixes, because
the third one showed that the first two repairs were narrower than the
defect.*

## The three appearances

**One — a server serving a build nobody named.** A `oneground ui` session was
started and handed over to be looked at. It answered 200, listed nine runs,
rendered cleanly, and served a page with no write half: the console script
resolves the package by install location, and that install pointed at a third
checkout weeks out of date. The suite had passed against a different
directory minutes earlier. Cost: a week of browser observations whose subject
could not be named afterwards.

**Two — the launcher refusal.** `provenance.conflicting_checkout` and
`identity()`: the server refuses to bind when the working directory holds a
checkout of this project whose package is not the one imported, prints its
build at startup and answers it on `/api/check`. Watched firing on the real
clash.

**Three — a supervisor spawning a build nobody named.** The supervisor's
first run produced a Python traceback from a build weeks out of date, in a
test asserting a refusal that build did not have. Same cause exactly: a
subprocess resolves `oneground` by install location, and nothing had told it
otherwise.

## What the second repair missed, stated plainly

**The launcher refusal covers the process that binds. It says nothing about
the processes that process starts.**

So a server can name its build correctly, refuse to bind on a clash, print an
honest startup line — and then spawn a child that resolves its own package
and runs something else entirely. Every guarantee the refusal offers stops at
the process boundary, and the supervisor's whole job is to cross it.

The repair is not another check:

> **A child inherits the parent's package rather than resolving its own.**

`supervisor.start` puts the directory containing the imported
`provenance.PACKAGE_DIR` ahead of whatever the child would otherwise find,
and the job record carries `build` — the package directory, because that is
the field that discriminated when two checkouts shared a version and a
commit.

## What would have caught it earlier

**Nothing did, and the reason is worth more than the fix: no test had ever
run a child.**

Every subprocess in the suite before this one ran `sys.executable -c` with an
explicit `sys.path.insert(0, REPO)` — written that way so the test would work,
which is exactly what made it useless as evidence. Each of those tests proved
something about the code; none of them could observe how a process *without*
that line resolves the package, because none existed.

The suite had a complete blind spot with a clean edge: **the first time
anything spawned a child the way the product spawns one, the defect appeared
immediately.** It did not need a clever test. It needed one that was not
pre-arranged to pass.

> The general form, which is `docs/PRACTICE.md` §2 warning 3 pointed at a
> fixture rather than at an assertion: **a test that arranges the conditions
> its subject will not have is not testing its subject.** `sys.path.insert`
> in a test harness is a helpful line that quietly removes the thing being
> checked.

And the tell for finding the rest of them: **look for what the tests do to
make things work.** Those lines are where the product's real conditions have
been replaced with convenient ones, and each is a place a defect can live
indefinitely.

## Why this is one finding and not three

The first two were treated as an incident and a repair. The third proved they
were an incident and *half* a repair, and the shape only became visible with
three points:

| | who resolves the build | what it cost |
|---|---|---|
| the session handed over | the console script's install location | a week of observations of an unknown subject |
| the launcher refusal | fixed: the process that binds | — |
| the supervisor's child | the child's own install location | a traceback from a build weeks old |

One root: **a process that does not know which build it is running, and
nothing that requires it to say.** The refusal answers it for one process.
Inheritance answers it for the ones that process starts. Anything that
spawns across a boundary neither covers — a pod session, a hook, a scheduled
run — is the fourth appearance waiting, and the question to ask of each is
the same one: *does this know which build it runs, and can it say?*
