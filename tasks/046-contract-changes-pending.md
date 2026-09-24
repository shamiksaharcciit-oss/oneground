# Task 046 — the seven times this slice wanted to change a contract

*Collected rather than raised one at a time, because seven of them is a
finding about the seam and not seven findings about a UI slice. To be ruled on
as a shape when 046 closes.*

*The fifth arrived after this note was written, and **it arrived from
building the test for a rule rather than from reading the code the rule is
about.** That is the argument for writing the test at all, and it is worth
separating from the usual one. A test is normally written to stop a known
defect recurring. This one was written to make a rule enforceable, found a
violation of it on its first run, and the violation was in code that had been
read carefully three times that week — by me, while writing the rule the code
breaks. Reading tells you what the code says. Writing the check tells you
what it does.*

**A consequence worth recording before the instances**, because it is the
first place this slice's two halves meet without being wired together: the
form writes requirements files *into* the runs directory, and the jobs page
offers a stage only when it can name a target in that directory — so **saving
a requirements file is what makes `characterize` offerable.** Nothing
connects them. Neither knows the other exists. They meet because both were
made to ask what a thing is rather than to assume one, and that is the only
kind of connection that does not need maintaining.

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

## 5. `simulate` reports a finding through its exit code — **pending**

Found by building the test for the exit-code rule, which is what the test was
for. `_cmd_simulate` returns **1** when configurations were planned and not
measured — and the run happened: the measured rows are in `simulate.json` and
each drop is named with its reason in `simulate_info.json:dropped`.

Its own comment gives the argument: *"couldn't-check is never rounded up to
success."* That is right about the outcome and it is asserting it in the wrong
channel. The artifact already refuses to round it up; the exit code is being
asked to repeat a claim the receipt makes better, and by doing so it becomes
a finding travelling in a process.

**What it costs, visibly:** it is the sole reason `jobs.EXIT_MEANING[1]` means
two things and `classify` has to consult the workdir at all. Remove it and
that row collapses to *did not finish*, and the workdir check — the thing that
needed its own mutant to prove it was read — becomes unnecessary.

Declared in `jobs.EXIT_CONTRACT` with its reason rather than quietly
permitted, so the rule is enforced with one stated exception rather than
weakened. `oneground/test_exit_contract.py` holds it.

Not taken: it is `simulate`'s contract, a script may depend on the code, and
changing it is not a UI slice's to do unasked.

## 6. `pod plan` returns 1 for a refusal — **pending**

Found the same way as the fifth, one step further: by widening the test built
for the rule. The first version read only `oneground/cli.py` and so checked
six of the ten stages while reading as though it checked all ten — warning 1,
in the test written to enforce the rule. The pod verbs are stages; their
handlers are in `oneground/pod/cli.py`.

`cmd_plan` prints

    REFUSED: the cost cap is exceeded. `up` would not proceed.

and returns **1**. So the tool declines, says so in the word this project
uses for it, and exits with the code that means *did not finish*.

Now that `pod plan` is a job, the consequence is immediate: `classify` reads
1 with no receipt and records **failed**, so the page shows a crash for the
one refusal in the product that exists to stop somebody spending money.

The repair is one character — `return 2`. Declared in `jobs.EXIT_CONTRACT`
with its cost rather than changed, because `pod` is a module this slice has
now wanted to reach into and this is the sixth contract item, not a UI
slice's to take.

### The fifth and sixth are a category, and it is the one that makes the ruling easy

Two ways for one seam to leak, and naming them together is more useful than
either alone:

| | what travels | where it should have been | what a reader is told |
|---|---|---|---|
| **5** `simulate` exits 1 on dropped configs | a **finding** | `simulate_info.json:dropped`, which already has it | the run did not finish |
| **6** `pod plan` exits 1 on the cost cap | a **refusal** | exit 2, which already means refusal | the run crashed |

Both are the process carrying something the artifact carries better, and in
both the exit code is *less* informative than what is already written down
beside it.

**The sixth is the instance that should decide this**, because of which
refusal it is. `cmd_plan` prints `REFUSED: the cost cap is exceeded. \`up\`
would not proceed.` — **the one refusal in the product whose entire job is to
stop somebody spending money** — and `classify` reads exit 1 with no receipt
and records **failed**. So the page shows a crash where the tool was
protecting the user's wallet, and the sentence that says so is in a log
nobody opens after a job has failed.

One character fixes it. The cost of not fixing it is that the most important
refusal in the tool is the one most likely to be mistaken for a bug.

## 7. 58 of the 74 fields a requirements file can carry are validated by nothing — **pending**

Measured while answering step 2's instruction to generate the example files
from the field table. `requirements.example.yaml` has **74** leaf fields;
`intake` validates **21**.

    constraints.latency.p95_ms: fourty

loads without a word. So do `cost.error_band: "a lot"`, a `simulate.families`
naming a family that does not exist, and a `constraints.monthly_budget` with
no currency. They are read later by whatever consumes them, or not at all.

**This one changes the shape of the decision rather than lengthening the
list.** The first six are all about how a refusal *travels* — printed as a
traceback, carried by a type that means two things, exiting under the wrong
number, arriving where a classifier reads it as a crash. Every one of them
presupposes a refusal that exists and is correct.

This is about refusals that **do not exist**. Not a message that arrives
badly: no message, no check, no field named, for three quarters of the
document that starts every run.

Which reframes the question the other six ask. *Who owns a refusal after it
is raised* has an answer worth ruling on — but underneath it sits *what does
`intake` owe a refusal for at all*, and today the answer is: whatever someone
wrote a check for, with no statement of what the set should be. The 25
refusals are excellent and nobody has ever written down why there are 25
rather than 74.

**Why it is not this slice's to take**, beyond its size: adding validation
changes which files load. A requirements file that works today and is refused
tomorrow is a contract change of the loudest kind, and some of those 58 are
fields whose absence of a check may be deliberate — `nearest_fixture: auto`
and a `deployment` block with one endpoint are both documented as tolerant.
Sorting the deliberate from the unexamined is the work, and it is a reading
of intent rather than of code.

**What I would want to know first**, and it is one measurement: of the 58,
how many are read by anything? A field nothing validates and nothing reads is
a different problem from one that is read and trusted. The second kind is
where a wrong value becomes a wrong number in a report, which is the thing
this project exists to refuse.

Full account: `tasks/finding-the-table-and-the-example-describe-different-things.md`.

## What the seven have in common, which is the thing to rule on

Six of them are **one seam**, hit from six angles, and the seventh is the
floor that seam sits on: the boundary where `intake`'s refusals stop being `intake`'s problem.

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
   **My reading, asked for and measured, is below.**
3. Does `intake` owe a refusal for every way a requirements file can be
   unusable, or only for every way its *contents* can be? Number 4 above is
   that question with a concrete instance.


---

# On `exit 2`: my reading, measured

*Asked for before the ruling. The short answer is that the premise of my own
question was wrong: this slice did not promote an implementation detail to a
contract. Exit 2 was already a contract — an undocumented one that three
parts of the tree depended on — and what 046 did was extend it to the place
it was missing and write it down for the first time.*

## What was already true

| where | assertions on exit 2 | what it meant there |
|---|---|---|
| `fixture/test_verify.py` | 10 | a fixture did not verify |
| `test_environment.py` | 4 | the environment guard refused |
| `lab/test_server.py` | 1 | the lab refused to start |

Fifteen assertions across three files, all predating this slice, none of them
written by it. And **no document anywhere states an exit code** — I grepped
`docs/` and `README.md`: the only matches are prose about pipelines and a
remote runner.

So exit 2 was a *convention with tests* — which is a contract by every
practical measure, since breaking it breaks fifteen assertions, and not a
contract by the only measure a user has, since nothing tells them.

`cli.py` returned 2 six times before this slice. It now returns it for every
declared refusal type as well. **That is the same meaning applied where it was
missing**, not a new meaning. The promotion that happened was from
*undocumented* to *written down*, which is the direction worth having.

## The real problem hiding inside it

The three places above do not all mean the same thing, and one of them is the
project's third outcome.

- *the environment guard refused* — **the tool declined.** A refusal.
- *the lab refused to start* — **the tool declined.** A refusal.
- *a fixture did not verify* — **the tool ran, and the answer was no.** That
  is not a refusal and not a failure. It is a negative result, and this
  project has a whole vocabulary for exactly that distinction.

So exit 2 currently carries two of the three outcomes, and
`jobs.EXIT_MEANING` maps it to `refused` without qualification. **Nothing is
broken today**, and the reason is worth stating precisely, because it is not
luck:

`fixture verify` is not a job stage. And the stage that could most obviously
have had this problem does not: `_cmd_verify` returns **0** even when a real
engine contradicts the simulation, because the contradiction is written into
`verify.json`. That is the project's own rule — **the three outcomes live in
the artifact, not in the process** — holding at the process boundary without
anyone having said so there.

The day a stage exits 2 for a negative result, `classify` will call it
`refused` and the page will say *the tool declined* about an answer the tool
gave. Nothing would report it: the job record would be internally consistent
and wrong, which is §4's shape again.

## What I would write down, if it were mine to rule

Not *exit 2 means refused*. That is true of the job stages and false of
`fixture verify`, so writing it would make a document wrong on the day it
shipped. The sentence that is true of everything today and is worth being
held to:

> **A stage's exit code says whether the command ran. It never says what the
> command found.**
>
> - `0` — it ran. What it found is in the artifact.
> - `2` — it declined, with a reason, and printed it.
> - `1` — it did not finish. Whether anything survives is the workdir's to
>   say, not the code's.

That makes `fixture verify` the named exception rather than a
counter-example — it is a checker whose whole output *is* the verdict, so its
exit code carries one — and it gives the supervisor's classifier a rule it
can be held to rather than a mapping that happens to work.

**And it makes one thing checkable that currently is not:** a test that every
stage returns 0 when it completes, whatever it found. That is the assertion
that would have caught the failure above before it existed, and it does not
exist today.
