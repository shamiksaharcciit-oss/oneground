# Task 046 — The interface, slice 2: configure and run

## Setup
Branch `task-046` from `main` after 043 has merged — the comparability
verdict needs its receipts, and slice 1's side-by-side starts answering a
real verdict the moment they exist. Commit `task 046:` and push after
every commit.

Read three things whole before writing code, and say so if any of them
disagrees with this brief, because in a disagreement they win and the
brief is wrong:

- `docs/INTERFACE.md` — the position, including §4.3's reversal;
- `docs/UI.md`, the section **Settled before slice 2: what holds the
  write path** — the write guard, already ruled and measured;
- the front-door section of `docs/INTERFACE.md` — three paths in, one
  artifact out, and the file that explains itself.

## Why
Slice 1 made every run readable. Nothing runs from it, nothing is written
by it, and a user still needs a text editor and a terminal to produce a
single result. This slice closes that: the form that writes
`requirements.yaml`, jobs that run the stages, and a supervisor that
outlives a closed tab.

It is the first thing in this interface that is not a drawing, which is
why its guard was settled before the brief existed.

## What is already decided, and is not reopened here

- **The UI is a front-end over the CLI, never a second implementation.**
  Every action is a CLI invocation, and the receipt records which.
- **The write guard is `parse(write(D)) == D`**, on every write, on the
  parsed document rather than the bytes. The guard checks nothing is lost
  between the form's document and the file; coverage and comment
  fidelity are acceptance, because no guard has access to intent.
- **`D` is built from form state**, not by editing a loaded document, so
  upload-and-edit and fill-from-empty produce the same file for the same
  inputs — which makes the identity load-bearing rather than cheap.
- **The form's refusal is the CLI's refusal executed**, not re-expressed.
- **The UI does not launch pod sessions.** It prepares, prices, shows the
  card and hands the user the `up` command for a terminal. A confirmation
  dialog would be `--yes` with a nicer surface. The guard enforces this
  structurally: `oneground.pod` is in `MEASURING`.
- **The supervisor is a second process**, decided by the same guard —
  a server that may not import the measuring packages cannot run them.

## Do

1. **The form writes the file.** Three paths, one artifact:
   fill-in-the-form (primary), upload-and-edit (validated on arrival,
   errors named against fields rather than parse positions), and
   download-a-template. All three construct `D` through one code path and
   write through the guard.

   Validation is `intake`'s own validator, invoked — not a second
   implementation, and not a subset. Where the form can refuse before the
   CLI would (an empty required field), it says so in the CLI's words if
   the CLI has words for it.

2. **The file explains itself.** Each field's explanation is written into
   the file as a comment, generated from the same string the form
   displays. The intake field table this requires does not exist —
   `Param.note` is the precedent and it covers only family parameters.
   Build it, and generate `requirements.example.yaml` and
   `requirements.declared.example.yaml` from it or delete them: 56
   hand-written comment lines in two files is a second body of
   explanation, which is what the table exists to prevent.

   The explanation and the refusal for a field come from one declaration,
   or they will diverge and the shared-string test will pass while a
   field is explained one way and refused another.

3. **Jobs.** Each stage is a job — `characterize`, `simulate`, `verify`,
   `report`, `chunk`, `propose` — with a state (queued, running, done,
   failed, refused, cancelled), a log streamed from the CLI's own output,
   start and end times, and the receipt the CLI wrote. A job's record
   names the exact invocation, and a test replays that invocation from a
   terminal and asserts the outputs match on what must match — the
   receipt-replay rule in `docs/INTERFACE.md` §2, which names what must
   be byte-identical and what may differ.

   A refused job is a first-class outcome showing the CLI's refusal
   verbatim, never rephrased and never summarised.

4. **The supervisor.** A second process holding no state beyond the job
   list; the truth is the workdir. It survives a closed tab and a
   restarted server, and its crash must not kill a running `simulate`.
   Cancellation is a real stop with a receipt saying so, and a cancelled
   job's partial outputs are kept and marked partial, never presented as
   complete.

5. **The pod session, prepared and handed over.** The UI resolves and
   shows the same card the CLI prints — resolved GPU, datacenter derived
   from the volume, live price confirmed at the top of the range, caps,
   cost ceiling — and then prints the `up` command. It creates nothing.
   The API key is never read by the server and never reaches the browser.

6. **The write guard, as settled.** `parse(write(D)) == D` on every
   write, plus the source-scan half: exactly one module may open a file
   for writing, the inverse of `test_the_server_has_no_write_path`. Both
   halves have mutants, written against the guard's own code rather than
   a restatement — `docs/FAMILIES.md` §4.1 warnings 3 and 5.

7. **Coverage and fidelity, as acceptance.** Every field a requirements
   file can carry is offered by the form, tested against a worked
   example. Every field's explanation in the written file is the same
   string the form showed. Neither is a guard, because neither is a
   property of a write.

8. **The read half is unchanged and still holds.** No view gains a write
   path; the rendering contract, the module classification and the
   read-only proof all still pass. Run slice 1's read-only test over a
   directory this slice has written into — a proof that writing runs did
   not make the reader mutable.

9. **Looked at, not only tested.** Browser observations at 1200 px and
   500 px, covering: filling the form from empty, uploading a file with
   an error in it, a job running and finishing, a job refused, a job
   cancelled, and the pod card. Report what you see as observations. The
   developer looks after you do.

10. **Docs.** `docs/UI.md` gains the write half. If it creates a better
    home for the settled write-path section, **move** that section rather
    than copying it — two statements of that rule in two documents is the
    failure the rule is about.

## Acceptance
- Three paths produce the same file for the same inputs.
- The guard runs on every write, with mutants; the source scan holds.
- Validation is `intake`'s, invoked; a refusal is the CLI's words.
- The file carries its explanations; the example files are generated or
  gone; explanation and refusal come from one declaration.
- Jobs record their invocation, and replay matches under §2's rule.
- The supervisor survives a closed tab and a server restart; its crash
  does not kill a job; cancellation leaves a receipt and partial outputs
  marked partial.
- The pod card is shown and the command handed over; nothing is created.
- Slice 1's read-only proof passes over a written-into directory.
- Browser observations at both widths for all six cases.

## Do not
- Create a pod, or add a confirmation dialog for one. Reimplement any
  validation. Let the server hold the API key. Write a file from any
  module but the one the scan permits. Run a job in the server process.
  Present a cancelled job's outputs as complete. Rephrase a refusal.
  Copy the write-path section into a second document.
