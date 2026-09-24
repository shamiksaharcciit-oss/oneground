# The claim `docs/PRACTICE.md` §4 is about went stale again, in the slice that made it false

*Found by asking the running server what it was, thirty seconds before
handing over its URL. Not found by any check.*

## What the server says right now

`/api/check`, at `93095e6`, in a `ui` session:

    "writes": "requirements files, through one guarded path",
    "runs":   "nothing: no job, no session is created from this page",

The first is true and was corrected earlier in this slice. **The second is
false.** The jobs page forwards an enqueue to the supervisor, the supervisor
records the job and runs it, and this slice's own tests assert exactly that
(`test_a_forward_that_works_returns_the_supervisors_own_answer` checks
`out["job"]["state"] == "queued"` and that the supervisor's list contains it).

A job is created from that page. The page beside it says no job is created
from that page.

## The part that makes it a finding rather than a typo

Four lines above the false string, in the same function, is this comment —
written earlier in this slice, by me, as the repair for this exact claim:

> *They now answer per mode, which is the repair that makes the next change
> impossible to miss: a `lab` session still writes nothing and the sentence
> says so, and a `ui` session says what it writes. **When jobs land, `runs` is
> the field that has to change, and it is the field a reader asks.***

Jobs landed four commits later. The field did not change. The instruction was
correct, specific, addressed to the right field, sitting directly above it,
and it did not work.

## Why the repair failed, which is the useful part

§4's repair was **answer per mode**: split the claim along `lab` vs `ui`, so
that a sentence which is true for one and false for the other cannot be
written as one string. That was the right axis for the defect it was fixing —
the form landed in `ui` only.

Jobs did not arrive along that axis. They arrived along **capability**, and
`ui` mode gained one. The split the repair installed had nothing to say about
it: both branches of the conditional were `ui`-versus-`lab`, and the `ui`
branch was simply wrong from the commit that added the forward.

> **A claim split along the axis that made it stale is not protected against
> the next axis.** Splitting by mode makes mode changes visible and makes
> every other kind of change invisible in a slightly more convincing way,
> because the field now looks considered.

That is the general form and it is worse than leaving the claim flat. A flat
false sentence is a sentence nobody has thought about. A split false sentence
carries evidence that someone did.

## What would have caught it

Nothing on the page and nothing in the suite. The claim is a string; no test
asserts a relationship between it and what the server can do. The check that
would work is the one §4 already prescribes for coverage claims, pointed at
capability instead:

    the set of things this session can do, derived from the routes it serves

`/api/check`'s `runs` field should be **computed** from whether the enqueue
route is mounted, not written as prose beside it. Then the sentence cannot
disagree with the server, because it is read off the server.

## The other homes, measured

The same claim, in its own wording, in five more places. Three are false at
this HEAD and two are correctly historical:

| where | what it says | at `93095e6` |
|---|---|---|
| `server.py:1131` | `runs: nothing: no job, no session is created from this page` | **false** |
| `server.py:227` — the `--host --i-know` warning | "It still writes nothing and runs nothing." | **false**, and it is a security sentence: a `ui` session exposed with `--i-know` can now be written to and enqueued to by anyone holding the URL |
| `server.py:135` — the comment over the jobs routes | "all reads. The server never enqueues … the page … speaks to it directly" | **false**, and it describes **option A**, which was abandoned for the CSP reason four commits earlier |
| `docs/UI.md:4` | "Nothing runs from this page — no job, no written file, no session." | **false** on two of three |
| `docs/UI.md:257` | "Nothing runs from this page." | correct — under *What slice 1 did not do* |
| `docs/INTERFACE.md:355` | "No job runs from the UI yet." | correct — under *Sequencing*, describing slice 1, with slice 2 the next item |
| `server.py:1320` | the eyebrow's comment, predicting this | correct, and unheeded |

**A correction to my own first count.** I reported `docs/INTERFACE.md:355` as
false and it is not: it sits in a numbered sequencing list whose next item is
*Configure and run*, so *"no job runs from the UI yet"* is a description of
slice 1 and reads correctly beside slice 2. I had grepped the sentence and
ruled on the line — which is warning 1 exactly, *a check must run the rule,
not search for it*, performed by hand while writing up an instance of it.

Seven homes, then, not six, and three false rather than four. The seventh —
`server.py:135` — is the worst of them and the grep found it only because it
was nearby: it is not a stale claim about what the server does but **a
description of a design that was never built.** Option A had the page talk to
the supervisor directly; the CSP made that impossible and option B forwards
through the server. The comment kept explaining option A directly above the
routes that implement option B.

**The claim gained two homes in the slice that was supposed to have taught
this project about its homes**, which is `7.4.2` — a defect recurs in
whatever is newest, written by whoever just fixed it — with the longest
interval yet, and in the surface where the rule itself is written down.

## What was done

All three false statements are repaired, and the two in `server.py` are no
longer statements. `CAPABILITY` maps each write route to one phrase;
`capabilities(runs_dir)` reads the routes `answer_write` actually mounts; the
network warning and `/api/check`'s `runs` field are both composed from it.
A test asserts `set(WRITE_ENDPOINTS) == set(CAPABILITY)`, so a route added
without a phrase fails the suite, and a mutant adds a route and asserts both
sentences change with nothing else edited.

The exposure warning now reads, for a `ui` session:

> … and the workdir's path and digests. **They can also write requirements
> files into the runs directory, start stages — characterize, simulate,
> report and the rest — through the supervisor on loopback and stop a stage
> that is running. This session is not read-only: exposing it hands those
> powers to anyone holding the URL.**

and for a `lab` session over one run, *"It writes nothing and runs nothing"*
— which it now says because no write route is mounted rather than because the
sentence says so.
