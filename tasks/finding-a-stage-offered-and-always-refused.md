# Finding — a stage that is offered and always refuses passes the picker's rule

*Task 046. Found by a person clicking `propose` three times and getting three
identical refusals, and it is a hole in a rule this slice wrote.*

## The rule, as it stands

> A stage is offered only when this page can name what it would run
> **against**. One that cannot is not offered, and says why.

It works, and it withheld five of six pipeline stages correctly. It is also
satisfiable by a stage that can never run.

## What happens

`propose` takes a workdir, and the page can name nine. So it is offered, the
chooser lists them, a click enqueues `oneground propose <run>` — and the
command refuses, every time, for every run:

    usage: oneground propose [-h] --policy POLICY --prediction PREDICTION
                             [--name NAME] [--requirements REQUIREMENTS]
    oneground propose: error: the following arguments are required:
      --policy, --prediction

The picker's rule is satisfied — the target *was* nameable — and the stage is
unrunnable from this page regardless of which target is chosen. Nine choices,
one outcome.

**The refusal is correct and good.** It is argparse's own message, arriving as
a refusal rather than a traceback because of this slice's CLI repair, and it
names exactly what is missing. That is the machinery working. What is wrong is
that the page offered the click at all.

## Why the rule has the hole

Because it distinguishes one kind of argument and the command has two.

- **What a stage runs *against*** — the positional. The rule covers it.
- **What a stage runs *with*** — required options. The rule does not mention
  them, so a stage with unsatisfiable required options passes.

`propose` is the only stage with required options today, which is why this
took a person clicking to find: five stages are withheld for want of a target
and never reach the question, and the sixth is the one that has it.

## The rule with the hole closed

> **A stage is offered when this page can name everything it would run with,
> not only what it would run against.**

The second clause is the general one and the first is a special case of it: a
positional is something a command runs with. Stating it that way also makes
the next case — a required option added to `characterize` next year — fall
under the rule instead of past it.

## What is not decided here, and it is one question rather than two

Whether the picker **asks** for the two files or the stage is **withheld** is
the same question the rule now has to answer, because both are consequences of
it. Asking means the chooser grows from one list to three, and needs to know
that `--policy` and `--prediction` are files of particular kinds — which is a
declaration this page does not have and `intake`'s field table does not cover,
since these are not requirements fields. Withholding means `propose` joins the
pod verbs with a reason, and the page offers five stages it can complete and
nothing it cannot.

**The measurement that should decide it**: are there policy and prediction
files in a runs directory in the ordinary course of things? If they are
artifacts the pipeline produces, asking is cheap and correct. If a user brings
them from somewhere else, the page cannot name them and withholding is the
honest answer — the same reasoning that withholds the pod verbs, which take an
id this directory does not hold.

I have not measured that, because it decides a design and the decision is not
mine.

## The shape, which is the part worth keeping

**A rule that names one prerequisite is satisfied by a thing that lacks a
different one.** The picker's rule was written to stop a job running against
a target nobody chose, and it does. It was then read as *this stage can run*,
which it never said.

The tell: **a rule of the form "offered when X" invites being read as
"offered when runnable".** If X is not the whole of runnable, the gap is
invisible until something in it fails — and here it failed identically nine
times, which is what made it look like a defect in `propose` rather than in
the offering.
