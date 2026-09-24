# Task 046 — the interface write slice

*In progress. Sections are written as they are settled rather than at the
end, because a claim written three days after the measurement is a
recollection.*

## The guard did not move when the comments arrived

The write guard's identity is

    parse(write(D)) == D

over the **parsed document**, not over the bytes. That was settled in step 1,
before `render` wrote a single comment, and of everything decided in this
slice it was the ruling most likely to have been wrong. A guard over bytes is
the obvious thing to reach for: it is stricter, it is easier to explain, and
it catches more. Choosing the weaker-looking identity was an argument — that
a file's meaning is what it parses to, and that anything a parser discards is
presentation, so a byte guard would be checking the writer's layout rather
than the document's content.

Step 2 is the experiment that argument was making a prediction about. It put
an explanation above **every field in every file this tool writes**, a
preamble at the top, and wrapping that depends on indentation depth. Under a
byte identity, every one of those is a change to what the guard compares.

**Nothing in the guard moved.** Not the identity, not `check_write_path`, not
`write_violations`, not one line of the round-trip tests — which passed
unmodified against a writer whose output had grown by a comment per field.

That is the identity having been drawn in the right place, **proved rather
than argued**. It is the difference between a design decision with a good
reason behind it and one with evidence behind it, and it is worth saying
plainly because the reason and the evidence are not the same claim: the
reason predicted that comments would not disturb the guard, and step 2 is
what turned the prediction into a result. Had the guard needed a single
exemption to accommodate comments, the byte identity would have been the
right one all along and the argument would have been a rationalisation.

The general form, for whichever guard comes next: **an identity is in the
right place when the first thing built on top of it does not touch it.** Not
when it is well argued — when something new arrives and it stays still.

## A stale tab is §6's subject arriving as a process-management question

At the end of the slice the session serving the lab had been started three
commits earlier. Stopping it needed a permission this agent does not have, and
the obvious way round was to start a second session on a free port and hand
over the new URL.

That would have been wrong, and the reason is `docs/PRACTICE.md` §6 rather
than tidiness. **A stale tab one refresh away from a named build is a build
with no name in the only place it matters** — in front of the person looking
at it. The server would have reported its build correctly; there would simply
have been two of them, identical in every visible respect, differing in three
commits of behaviour, and the one thing distinguishing them would have been a
port number in a URL bar.

§6's instance was a URL served by a checkout nobody had named. This is the
same defect reached from the other end: not a build that cannot say what it
is, but two builds that both can, where saying so does not help because the
question a person asks is *which tab*. The rule survives the restatement —
**do not hand over a URL that is one refresh away from a different build** —
and it generalises: the identity of a build is a property of the session
serving it, so ending the old session is part of publishing the new one and
not housekeeping that follows it.

Worth recording because it did not arrive as a design question. It arrived as
a process that would not die, which is the form this class of problem takes
in practice and the form in which it is easiest to solve the wrong way.

## The browser observations

*Nine passes over three pages, at 1200px and 500px, with the contrast
instrument injected. What follows is what looking found that the suite could
not, which is the only reason the passes happened.*

### What the suite could not have caught, and did not

Every defect in this list was found by a person or a browser looking at a
rendered page. None of them was reachable from the source, and saying why
each was out of reach is more useful than the list.

| what was wrong | why no test could see it |
|---|---|
| ten stage buttons dark on dark | they matched **no rule at all** — `.door` was declared as `.compose-doors .door`, a descendant selector, so the runner's buttons rendered as bare UA buttons. There was no `var()` to check because there was no declaration |
| the form's controls on `--panel` instead of `--field` | the rule existed and named declared tokens. It named the wrong ones, which is a question about colour and not about syntax |
| the chooser deleted mid-click | the refresh timer rebuilt the list under the open panel. Both behaviours were correct alone |
| nothing driving queued jobs | enqueue worked, the list was correct, and no test asserted that anything advanced it |
| three identical rows | each row was right. The defect was that three of them were the same |
| the placeholder read as a command | it was a true sentence in the wrong typeface |
| the live pane dragging prose sideways | `white-space: pre` is correct CSS for a file. It is wrong for a pane narrower than the file |

The common shape is the one already on `docs/PRACTICE.md` §4: **each of these
was a correct thing in a context nothing tested.** A stylesheet check
verifies that a rule's tokens are declared; it cannot see a rule that was
never written, and it cannot resolve cascade, inheritance, specificity, or a
background inherited from three ancestors up.

### The contrast instrument, and what it settled

`oneground/lab/contrast.js` reads `getComputedStyle` and computes the WCAG
2.1 ratio, which is a formula over two colours and needs no judgement. Over
three pages at two widths:

    #/runs   1200px  125 checked  0 below threshold
    #/new    1200px  157 checked  0 below threshold
    #/jobs   1200px   63 checked  0 below threshold
    #/runs    500px  119 checked  0 below threshold
    #/new     500px  110 checked  0 below threshold
    #/jobs    500px   63 checked  0 below threshold
    637 elements checked, 0 below threshold

It began at **84 failures**. The largest single cause was not a colour choice
at all: the light page was resolving the dark theme's tokens, because
`ui.css` and `lab.css` both declare them and the page loaded both.

> **What the instrument settled, and it outranks the fixes.** A contrast
> check *is* possible against the declared tokens — and it is worth less than
> it looks, because the three worst failures were invisible to it. Two were
> coloured by the other stylesheet and one matched no rule. **Only a rendered
> page knows what colour a thing is.**

And what it does not claim: contrast is not readability. A 21:1 ratio at 6px
is unreadable and this says nothing about that. It catches one failure mode
completely and nothing else at all — which is worth writing down, because a
green instrument invites the reading that the page is fine.

### The end-to-end pass, which is the result

A requirements file written through the form, refused once:

    corpus.sample.target_sample_size must be a whole number;
    got '150,000 × 768'

That is `intake`'s own sentence, rendered verbatim at the field it belongs
to. The form validated nothing and could not have: eleven of the
twenty-five refusals are relational or not about a field at all, and a form
that re-expressed them would be the second implementation this design exists
to prevent. Corrected, accepted, written with its explanations as comments.

The jobs page then offered **all six** pipeline stages, because the file
existed — and had withheld five of six before it did, each with the reason.
`characterize requirements.yaml` ran to `done`, exit 0, on 20,000 vectors,
from a click.

> The thing worth noticing is that the offering changed **because the
> directory changed**, not because anything told it to. A stage is offered
> when the page can name everything it would run with; writing the file made
> that true for five more stages, and the page had nothing to be told.

### Two found in that pass, both fixed

**The live pane scrolled rather than wrapped.** `white-space: pre` is the
right declaration for a file and the wrong one for a pane narrower than the
file — and this pane is mostly prose, since the writer puts an explanation
above every field. Prose dragged sideways is prose nobody reads.

Now `pre-wrap`, with the preview given the wider half of the split. Measured
in the rendered page at both widths: `scrollWidth === clientWidth`, nothing
to drag.

> And a correction inside the fix, because it is the more useful half. I
> first wrote `text-indent: -2ch` to mark continuation lines so a wrap could
> not be misread as a newline. **It does not do that.** `text-indent`
> applies to the first line box of a *block*, and the newlines in a `pre`
> are line breaks inside one block, so it would have indented the file's
> first line and nothing else. `each-line` is the keyword that would work
> and is not supported widely enough to rely on.
>
> Then the comment I replaced it with claimed the widened column fits the
> writer's 74 columns. **It does not either**: at 1200px the pane is 552px
> and the longest line is 75 characters. Two false statements about CSS in
> one fix, both written confidently, both caught by measuring the rendered
> page rather than by reading the rule. The comment now says what was
> measured and what the trade is — fitting 74 columns would mean 12px type,
> which is worse than a wrapped comment.

**`Write it to requirements.yaml` named a file and not a place.** A reader
could not tell where it landed until the jobs page reacted to it, which is
finding out afterwards. The server already knew; the page was not asking.
The runs directory is now shown before the name box, in the same shortened
form the header uses, from the same field — so the two cannot disagree and
neither prints an absolute path.

### What I would look at next, and did not

- **The form at 500px** is usable and not good. The field groups stack
  correctly, but a form of this length on a phone wants a summary of what is
  filled in, and there is none.
- **The jobs page has no empty state worth the name.** With no jobs it is a
  heading and a withheld list, which reads as a page that failed to load.
- **Nothing shows a job's output while it runs.** The log is there after; a
  stage that takes ninety seconds shows `running` and nothing else, and a
  reader cannot tell a slow stage from a stuck one.

None is a defect in what this slice promised. All three are the same
question — *what does this page look like when it is not the happy path* —
and that question was asked of the refusals in this slice and not of the
waiting.
