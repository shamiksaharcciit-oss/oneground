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
| Does the UI launch pod sessions? | **Yes.** The typed `y` becomes a confirmation showing the same price card |
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
asserts the outputs are byte-identical.

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

### 4.1 Configuration writes the file

A form for `requirements.yaml`, with every field explained beside it and
the file shown live as it is edited. Saving writes the file; the file is
what runs. A user who opens it in a text editor sees exactly what the
form produced, with the form's explanations preserved as comments, so the
artifact teaches the schema rather than hiding it.

The form refuses what the CLI would refuse, using the CLI's own
validator — an unknown parameter is named with the declared list, a
prediction without a threshold is refused, a `deployment:` block with one
endpoint behaves as single-node. There is no separate validation.

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

Cancellation is a real stop with a receipt saying so. A cancelled job's
partial outputs are kept and marked partial, never presented as complete.

### 4.3 The money boundary moves, and does not weaken

Launching a pod session from the UI shows the identical card the CLI
prints — the resolved GPU, the datacenter derived from the volume, the
live price range **confirmed at the top**, the caps, the cost ceiling —
and waits for a click that is the same commitment as the typed `y`.

Three rules carried over, none relaxed: nothing is created before the
confirmation; any failure after creation terminates the pod; there is no
"don't ask again". A confirmation dialog that can be dismissed by habit is
not a boundary, so the dialog requires the user to type the cost ceiling
they are accepting, as the CLI requires the letter.

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

- The front door for a user with documents and no vectors: `chunk` is a
  stage the UI runs, but the moment before it — choosing an extraction
  tool, declaring it — is a form nobody has designed.
- Authentication beyond the loopback token, if the UI is ever exposed to
  a team rather than a person. Not designed, and the loopback default
  means it need not be yet.
- Whether the supervisor is a second process or a mode of the same
  server. A decision for the brief, with the constraint that a crash of
  the UI must not kill a running `simulate`.
- The visual design beyond the tokens already published. The workspace
  mockup of 17 September is a study, not a specification; what survives
  from it is the shape — a rail of stages, a main view, an evidence
  drawer — and the study's own banner said no application like it
  existed. This paper makes it exist; the mockup does not become the
  design by default.

## 8. Sequencing

Three slices, each shippable alone:

1. **Read.** Many runs, the report with its drawer, the lab reached from
   a run. No job runs from the UI yet. This is the lab's own machinery
   extended and it carries the lab's guarantees unchanged.
2. **Configure and run.** The form that writes the file; jobs with the
   supervisor; every stage but the pod. The receipt-replay test from §2
   lands here and gates everything after.
3. **Spend.** The pod session with its confirmation. Last, because it is
   the only slice where a defect costs money rather than time.

*The exam, before the code.*
