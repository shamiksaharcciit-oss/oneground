# Finding — a refusal cannot be told from a crash, and the commonest one is a traceback

*Found while designing task 046's supervisor, against the instruction that a
supervisor must be able to tell a refusal from a failure **from what the CLI
gives it**, and that if it cannot, that is a finding about what the CLI
returns rather than a reason to collapse the two states.*

It cannot. This is what it can see instead.

## The shape being looked for

`oneground/jobs.py` has six states and two of them are `refused` and
`failed`. They are kept apart deliberately: a refusal is the tool declining,
with a reason and a remedy; a failure is something breaking.
`docs/INTERFACE.md` §4.4 requires the UI show a refusal **verbatim, with the
reason and the remedy**, and §4.2 makes a refused job a first-class outcome.

A supervisor runs the CLI as a subprocess. All it is given is an exit code, a
stream of output, and whatever landed in the workdir. So: **does the exit
code say which happened?**

## Measured

Every stage command, run for real from this worktree:

| command | what happened | exit |
|---|---|---|
| `characterize nope.yaml` | `RequirementsError: requirements file not found` | **1**, with a traceback |
| `simulate runs/nowhere` | unhandled exception | **1**, with a traceback |
| `report runs/nowhere` | unhandled exception | **1**, with a traceback |
| any guarded command, unpinned | `UnpinnedEnvironment` / `ForeignPackage` | **2**, one line, no traceback |
| `propose`, bad inputs | `ProposeError`, every problem at once | **2**, no traceback |
| `simulate`, some configs dropped | the run happened; the rest are in `simulate.json` | **1** |
| any command, success | — | 0 |

`cli.py` returns literal `0` eight times, `2` six times and `1` twice.

## The three problems, in order of how much they cost

### 1. `RequirementsError` escapes as a traceback

`oneground/intake/__init__.py` defines it as the project's own refusal type.
Its docstring says *"The message always names the field"*, and the module
header states the two rules that shape every message it raises: **name the
field**, and **refuse rather than guess**. Twenty-five of them are written
that way.

`cli.main` catches none of them. So the most common refusal a user will ever
meet — a requirements file that is missing, or malformed, or names both
`vectors.path` and `text.path` — arrives as a Python traceback with the
carefully-written sentence on the last line.

**What this costs the UI specifically.** §4.4 says the interface shows the
CLI's own message verbatim rather than rephrasing it. Today that would mean
showing a traceback, and the alternative — parsing the last line out of it —
is a second implementation of the CLI's error formatting, in the one place
the whole design says not to have one.

It is worth noting what already works: the write guard in `compose.py`
catches `RequirementsError` from `intake.load()` directly, which is why the
form shows clean refusals today. That path never goes through `cli.main`.
The defect is in the command line, not in intake.

### 2. Exit 1 means two unrelated things

*A run that happened and dropped some configurations* and *a run that
crashed* are both exit 1. The first is closer to `done` than to `failed` —
`simulate.json` exists, the measured rows are in it, and each dropped
configuration is named with its reason in `simulate_info.json:dropped`. The
second produced nothing.

A supervisor with only the exit code will call both of them the same thing.

### 3. Exit 2 is refusal for stages, and not only refusal elsewhere

For the ten job stages, exit 2 is always a refusal. But `_cmd_ui` and
`_cmd_lab` also return 2 for an `OSError` on binding, which is a failure. No
job runs those — they are servers, not stages — so this does not reach the
supervisor today. It is recorded because the next command to reuse 2 for a
failure would break the mapping silently, and nothing would report it.

## What the supervisor can do without a fix, and what it cannot

It can be honest, because **the truth is the workdir** — step 4's own
principle, and the resolution to problem 2:

- exit 0 → `done`
- exit 2 → `refused`, for a stage (problem 3 says why that holds today)
- exit 1 **with the stage's receipt written** → `done`, drops recorded in the
  receipt where they already are
- exit 1 **with no receipt** → `failed`

That classification is declarable as data, and every row is checkable.

What it **cannot** do is satisfy §4.4 for problem 1. A `RequirementsError`
arrives as exit 1 with no receipt, so the supervisor will correctly call it
`failed` — and it was a refusal, with a named field and a remedy, which the
user will not be shown. **Step 3's acceptance — "a refused job is a
first-class outcome showing the CLI's refusal verbatim" — is not reachable
for the commonest refusal in the tool until the CLI returns one.**

## The repair, not taken here

`cli.main` catches `RequirementsError` (and the other first-class refusal
types) and returns the refusal the way the guard already does: the message,
one line, no traceback, exit 2. That is the shape `guard_or_exit` established
and the shape `_cmd_propose` already uses — *"a refusal is not a crash"*, in
its own comment.

It is small and it is not mine to make unasked: it changes what the command
line prints and returns for a case that is not rare, which is a contract more
than the UI depends on. Recorded here for a ruling.

**And a note on which way to fix it.** The temptation will be to make the
supervisor smarter — parse the traceback, match the exception name, infer the
refusal. That is the second implementation §2's rule exists to prevent, and
it would leave the command line's own users still reading tracebacks. The
refusal should be produced where it is raised, once.
