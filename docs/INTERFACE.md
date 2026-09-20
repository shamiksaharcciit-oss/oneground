# oneground — the interface: the position, before the code

*19 September 2026. Written before implementation, in the order the four
earlier positions were written: the exam before the code. Settles what the
UI is, what it is not, and the rules that keep a thing that runs commands
as honest as the commands themselves.*

---

## 1. The decision

The UI becomes the primary way to operate oneground. Every operation —
configuring a corpus, running the four stages, launching a pod session,
proposing a change, reading a report, using the lab — is reachable from it.
The CLI remains, unchanged, for automation and for anyone who prefers it.

Five things follow, and the developer has ruled on each:

| question | ruling |
|---|---|
| Does the UI launch pod sessions? | **No — reversed.** It prepares, prices and shows the card, then hands the user the `up` command to run at a terminal. See §4.3 |
| Does it edit `requirements.yaml`? | **Yes, by writing the file.** The file stays the artifact |
| Long-running jobs? | **Needed.** Job state, a log, cancellation, surviving a closed tab |
| One run or many? | **Many.** A list of runs, each a workdir |
| How much of the report? | **All of it**, including the evidence drawer |

## 2. The one rule that keeps it honest

**The UI is a front-end over the CLI. It is never a second implementation.**

Every action the UI takes is exactly a CLI invocation — the same command,
the same arguments, the same code path — and it is recorded as such in the
run's receipt. A run started from the UI is byte-identical to one started
from the terminal and can be reproduced by someone who has only the
terminal.

This is not a convenience; it is the property that makes everything else
in this paper cheap. The pin guard, the refusals with their reasons, the
three outcomes, the money boundary, the claim invariant — the UI inherits
all of them by construction because it invokes the code that has them. A
UI that reimplemented any of them would drift from the CLI the first time
one was fixed and the other was not, and a user would then have two tools
that disagree.

The test that enforces it: for every UI action, the receipt names the CLI
command that ran, and a test replays that command from the terminal and
compares the outputs.

Two corrections, both found by reading the tree rather than the paper.

**The invocation is not recorded today.** No receipt writer captures
`sys.argv` or an equivalent. `simulate_info.json` records the requirements
file with its digest, `run_at`, `platform`, `python_version`,
`library_versions` and — since 033 — `oneground` with its five keys; it does
not record what was invoked. So a UI action would have nothing to replay
*from*. The fix is additive and small: the invocation becomes a receipt
field in the shape 033 established, recorded beside the version that
produced the artifact, with the same null-and-a-reason rule where it cannot
be known.

**"Byte-identical" is a claim this tree already refutes.** The first draft of
this paper asserted it; two runs of the same command differ in
`simulate_info.json` at `run_at`, `elapsed_seconds`, `timings` and
`oneground.dirty`, and `MANIFEST.sha256` covers both files, so it differs
too. That is not a defect to fix — it is 020b's deliberate split, which
moved facts about a run out of the rows precisely so that the rows would be
byte-identical. Asserting identity over everything would fail on the design.

So the test states **what must be identical and what may differ**, in the
shape `corpora/compare_state.py` already uses: `simulate.json`, the state
files and the other receipts byte-identical; the `_info.json` pair identical
with the environment-dependent fields set aside, as `strip_environmental`
sets them aside there. A test that names the exemption is a test; one that
asserts identity and is then quietly loosened is not.

## 3. What today's lab already settled

The lab is a loopback server, token in the URL, read-only, writing
nothing — proved by unchanged digests after every session. Its rendering
contract forbids a view from computing a measurement: a view is a drawing
of the run's recorded state, never a second calculation.

All of that carries forward unchanged as the **read** half of the UI.
Every view of a run — the characterization, the simulate table, the
verify rows, the report, the ground, the trace — is a rendering of files
the CLI wrote, under the same contract, with the same guard.

What the UI adds is a **write** half, and the two halves are kept apart
in the code and in the page: reading a run can never trigger a run, and
running something can never bypass the receipts the read half renders.

## 4. The write half, and what it must do

### 4.1 The front door: three paths in, one artifact out

All three end at the same file, and that is the property worth keeping:
the YAML remains the thing that runs and the thing someone else can
reproduce from.

**Fill in the form** — the primary path. Each field explained beside it,
validated as it is typed by the CLI's own validator, so the form refuses
exactly what the command refuses, with the same message. The file is shown
live as it is edited. Saving writes it.

**Upload one you have** — second. Validated on arrival, with any error
named against the field it belongs to rather than as a parse failure, and
then editable in the same form. A user arriving with a file from a
colleague, a repository or an earlier run lands in the same place as a
user starting empty.

**Download a template** — third, and not a blank form; see below.

**Why the form is primary and the template is the fallback.** A template
downloaded, edited in a text editor without validation, and uploaded is
the command-line experience with extra steps: the user finds out what was
wrong from a refusal rather than while typing. The template exists for
people who want a file under review, not as the ordinary way in.

#### The file explains itself

The form writes its reasoning into the file as comments — not field names
restated, the *why*, in the words the form used beside each field:

```yaml
corpus:
  sample:
    # Ten to twenty thousand vectors, not your whole corpus. The exact
    # answer key is computed by brute force over this sample, which is
    # what makes it cheap; at full scale it would not be.
    vectors: ./data/sample.npy
    queries: ./data/queries.npy    # 50+ or the ambiguity measure
                                   # cannot be computed
  # Your real corpus size. Used for capacity arithmetic and for the
  # caveat printed on every result: a sample does not tell you how the
  # whole corpus behaves.
  size_now: 2_100_000

constraints:
  # Measured at this concurrency, in the same environment, for the
  # configuration the engine was actually built with. Anything else is
  # reported couldn't-check rather than guessed.
  latency_p95: {ms: 40, at_qps: 200, concurrency: 32}
```

Three consequences:

- **The downloaded template is the tool explaining itself** in a file the
  user keeps, rather than a blank form they must look up.
- **A file that leaves the tool carries its own reasoning**, so a
  colleague reading it in a pull request learns the schema from the
  artifact.
- **The comments are generated from the same strings the form shows**, so
  they cannot drift from the interface. A test asserts that every field
  with an explanation in the form has it in the written file, and that the
  two are the same string.

Comments are not read back as data. A user editing them by hand changes
nothing about the run, and re-saving through the form rewrites them from
the current strings — stated in the file itself, once, at the top.

**What this costs, and it is not nothing.** There is no table of field
explanations in the tree today. `intake` validates `requirements.yaml`
with about twenty `raise RequirementsError(...)` statements whose messages
are built at the raise site, and those are *refusals* — what is wrong —
not *explanations* — what the field is for. The only declared table with
per-key prose is `models/base.py`'s `Param.note`, and it covers the
fourteen family parameters (`M`, `centroids`, `nprobe`, …), none of the
fields above. The explanations the example shows currently exist only as
hand-maintained comments in `requirements.example.yaml` (36 comment lines
of 139) and `requirements.declared.example.yaml` (20 of 64).

So this slice creates that table, on `Param.note`'s precedent, and the
"one string" test is a test about it. Three consequences follow.

The form and the writer share one origin, which is what makes the test
mean anything rather than assert a tautology.

**The two example files are part of the same work.** Between them
`requirements.example.yaml` and `requirements.declared.example.yaml` carry
**56 hand-written comment lines** today — 36 of 139 and 20 of 64. Once the
table exists they are generated from it or they are deleted. Leaving them
is leaving two bodies of explanation for the same fields, maintained
separately, drifting — which is precisely what the table exists to
prevent, so shipping the table and keeping them by hand would be building
the fix and declining it.

And the third is the one to watch: **the explanation and the refusal for
the same field remain two different strings in two places**, so a field
can still be described one way and refused in another — and the "one
string" test would pass throughout, because it compares the form to the
file and never to the refusal. A test that is green while the thing it is
named for is broken is the same class of defect as a guard that passes
while checking nothing.

The shape that would close it, **not decided here**: an intake field
table on `Param.note`'s precedent that declares each field **once**, with
both the form's explanation and the refusal message rendered from that one
declaration — so the two cannot diverge, because there is one string.
Slice 2's brief settles whether that is the shape and what it costs; this
paper only names it, and does not claim the shared-string test covers the
gap in the meantime.

The form's validation is the CLI's validation, not a second
implementation — an unknown parameter is named with the declared list, a
prediction without a threshold is refused, a `deployment:` block with one
endpoint behaves as single-node. If the two could disagree, the front
door would be the first place the UI drifted from the tool it is a
front-end to.

### 4.2 Running is a job

Each stage is a job: `characterize`, `simulate`, `verify`, `report`,
`chunk`, `propose`, and a pod session. A job has a state — queued,
running, done, failed, refused, cancelled — a log streamed from the CLI's
own output, a start and end time, and the receipt the CLI wrote.

Jobs run in a process the UI does not own: a small supervisor that
survives a closed browser tab and a restarted server. A user who starts
`simulate` at 150k and closes the laptop lid finds it finished, or
finished-with-a-refusal, when they return. The supervisor holds no state
of its own beyond the job list; the truth is the workdir.

**The supervisor is a second process, and the guard decides it** — this is
not open. `oneground/lab/guard.py` lists `oneground.simulate`,
`oneground.verify`, `oneground.report`, `oneground.models`, `oneground.pod`,
`oneground.adapters` and `oneground.fixture` in `MEASURING`, and
`server.py` runs `check_views()` and `check_transport()` over its own source
and **refuses to start** if either is broken. A supervisor running jobs
in-process would have to import exactly what the server may not, and the
server would then not start. The architecture already answers the question,
and it answers it the way the constraint wanted: a crash of the UI cannot
kill a running `simulate`, because the UI was never the thing running it.

Cancellation is a real stop with a receipt saying so. A cancelled job's
partial outputs are kept and marked partial, never presented as complete.

### 4.3 The money boundary does not move at all

**Reversed from this paper's first draft.** The UI does **not** launch pod
sessions.

The draft said the typed `y` "becomes a confirmation showing the same price
card", and required the user to type the cost ceiling "as the CLI requires
the letter". That asserted an equivalence where it had made a substitution.
A terminal prompt and a browser dialog are not the same boundary: a page can
be scripted, automated, clicked through by a wrapper, or driven by something
that is not a person, in ways a typed letter at a terminal cannot. `--yes`
was refused when the pod helper was built, for that reason, and the reason
has not changed. **A scriptable page is `--yes` with a nicer surface.**

So the UI does what the agents do today, and no more: it resolves the
session, runs the read-only plan, shows the card — the resolved GPU, the
datacenter derived from the volume, the live price range **confirmed at the
top**, the caps, the cost ceiling — and then **prints the `up` command for
the user to run at a terminal**. The typed `y` stays where it is.

This is less convenient and it is the point. The one operation that spends
money keeps the one boundary that cannot be automated by accident, and the
UI's job at that boundary is to make the decision well-informed rather than
to take it.

Everything else in the session is the UI's: `plan`, `status`, `watch`, the
fetch, the comparison, and the receipts. Only the create is a terminal.

The UI never holds the API key. It is read from the environment by the
CLI process, as today; the browser never sees it.

### 4.4 Refusals are the same refusals

When a job is refused — unpinned environment, missing precondition,
unbuildable configuration, a session whose environment and requirements
disagree — the UI shows the CLI's own message, verbatim, with the reason
and the remedy. It does not rephrase, soften, or summarise a refusal. The
message that says what would settle it is the most useful thing the tool
produces, and it was written once, in the CLI, on purpose.

## 5. The read half, extended

### 5.1 Many runs

A list of workdirs: name, corpus, when, which stages have run, the
report's verdict if there is one, and the version that produced each.
Selecting one opens it. Two runs can be shown side by side **only** under
the comparability verdict the library position defines — comparable,
not comparable, couldn't-check — and a not-comparable pair is shown as
two observations, never as a comparison.

### 5.2 The report, whole, with the evidence drawer

Every sentence of the report is a `Claim` carrying the rows it cites.
The drawer renders that: select any figure, see the file and field it
was read from, its kind, and — for a couldn't-check — what would settle
it. This is nearly free because 019 already made every sentence
reconstructible from what it cites; the drawer is a rendering of a
property the report has.

The three outcomes keep their equal visual weight. Couldn't-check is a
result with a reason, never a greyed-out absence, and selecting it is the
most informative click on the page because it is the only one that ends
in an action.

### 5.3 The lab, as it is

The ground and the trace, unchanged, now reached from the run rather than
from a separate command. The ε rule, the render-mode measurement and its
caption, the projection's declared status — all as built.

## 6. What the UI must never do

- **Compute a measurement.** The rendering contract holds over every
  view, extended from the lab to the whole interface. A number on screen
  came from a file the CLI wrote, or it is not on screen.
- **Run anything the CLI cannot.** No UI-only operation exists.
- **Spend without the boundary.** No pod is created, no cost incurred,
  without the confirmation in §4.3.
- **Hold a secret.** No key, no token, no credential in the browser or in
  the UI's own state.
- **Leave the machine.** Loopback by default, as the lab; a non-loopback
  bind requires the explicit flag with its printed warning, and the
  reasons the lab's security model gives apply to a UI that can now run
  things with more force, not less.
- **Round a couldn't-check.** Neither in a verdict, nor in a summary, nor
  in a colour.
- **Replace the file.** `requirements.yaml` remains the artifact and the
  UI remains a way of writing it.

## 7. What this position does not settle

- ~~The front door for a user with documents and no vectors.~~ **Settled
  in §4.1**: three paths in — form, upload, template — one artifact out,
  and the file carries the form's own explanations as comments. What
  remains open inside it is narrower and named there: the explanation of
  a field and the refusal for that field are still two strings in two
  places, and nothing keeps them honest against each other.
- Authentication beyond the loopback token, if the UI is ever exposed to
  a team rather than a person. Not designed, and the loopback default
  means it need not be yet.
- ~~Whether the supervisor is a second process or a mode of the same
  server.~~ **Settled in §4.2**: a second process, decided by the lab's
  import guard rather than by preference. Left here struck through because
  the reason it was open — nobody had checked what the guard already
  forbade — is the more useful record.
- The visual design beyond the tokens already published. The workspace
  mockup of 17 September is a study, not a specification; what survives
  from it is the shape — a rail of stages, a main view, an evidence
  drawer — and the study's own banner said no application like it
  existed. This paper makes it exist; the mockup does not become the
  design by default.

## 8. Sequencing

Two slices, each shippable alone:

1. **Read.** Many runs, the report with its drawer, the lab reached from
   a run. No job runs from the UI yet. This is the lab's own machinery
   extended and it carries the lab's guarantees unchanged.
2. **Configure and run.** The form that writes the file; jobs with the
   supervisor; every stage. The receipt-replay test from §2 lands here and
   gates everything after.

There is no third slice. It was **Spend** — the pod session with its
confirmation — and §4.3's reversal removes it: the UI never creates a pod,
so there is nothing to sequence last. What remains of that work is session
preparation and the card, which are reads, and they belong in slice 1 with
everything else the UI only looks at.

*The exam, before the code.*
