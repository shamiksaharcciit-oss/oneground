# Task 044g — `write_json_stable` refuses a payload carrying a machine path

**Written up from the developer's ruling on the 044f report.** Branch
`task-044g` from `main`. A behaviour change on the write path, which is why it
is its own task and not folded into 044f.

## Two of this project's rules are in direct conflict

> **A receipt does not name the filesystem it was produced on** (task 043).
>
> **A later command must be able to reopen what the run used**
> (`proposals/propose.py`, which reads `requirements_file.path` back out of
> `simulate_info.json`).

Both are right. `requirements_file.path` has been **satisfying the second by
violating the first since the field existed**, on every run, and nobody had
noticed the two rules could not both hold — because the violation is silent
and the satisfaction is invisible until something moves.

It was found only because a refusal forced the question. 044f fixed the four
writers, `propose` could no longer find the file, and 30 tests said so. A
guard that repairs, warns, or is scoped around the awkward case would have
left both rules standing and the conflict undiscovered.

**That is this task's opening, not its problem statement.** The refusal in
step 1 is what makes the conflict unavoidable rather than perpetual, and
resolving it is the substance of the work. The three-checks argument below is
why the refusal belongs at the serialisation boundary; the conflict is what
the refusal is for.

## Why the refusal goes where it goes — 044f's own gap is the specification

044f built a static guard over receipt write sites. It found four live
sites writing an absolute path and it **cannot reach the instance that
motivated the whole rule**: `report.json`'s `price_table.path` arrives inside
`prices.as_dict()`, an opaque call into another module. No static check
reading the write site can see inside a call's return value.

> **At serialisation an opaque value is a value.** That is the one place the
> path is always visible, whatever module built it and whatever the key is
> called.

So the third check goes where the first two cannot:

| check | subject | blind to |
|---|---|---|
| `test_no_tracked_file_carries_a_machine_identifier` | the tracked tree | anything under `runs/`, which a publisher reads |
| `receipts.pathguard` (044f) | the write site's source | a path inside an opaque call |
| **this one** | the payload, at write time | nothing about the value; only what it cannot recognise as a machine path |

Three checks, three different things. **None replaces another** and all three
stay — 044f's four live sites were invisible to the first, and `price_table`
is invisible to the second.

## Do

### 1. Refuse. Do not repair.

**The refusal is a refusal.** It names the key path within the payload and the
offending fragment, and it does not rewrite the value.

This is the ruling and the reason is measured rather than stylistic. 044e
found `export_teaser_data.public_price_table` silently repairing exactly this
on read — and a ten-day-old machine identifier sat in three receipts
unnoticed **because it was being repaired on read**. A silent repair on a
write path is the same defect with a better excuse: it removes the symptom
and leaves the writer wrong, so the next writer is wrong too and nobody is
told.

An error message naming the field and the remedy is a better artifact than a
quietly corrected value.

### 2. Where

`receipts.write_json_stable`, the choke point every receipt goes through. Walk
the payload; raise on a string that looks like a machine-local path.

What counts as one is the decision to get right, and it must be **narrow
enough not to fire on legitimate content** — receipts carry prose, notes,
error text and repo-relative paths, all of which may contain slashes. A home
directory, a drive letter and a UNC prefix are the shapes that matter. State
the rule, and state what it deliberately does not catch.

### 3. The remedy in the message, and the report says what a real user sees

A user whose old receipt trips this has a remedy: **re-run the command**,
which now writes public paths. Say so in the refusal. `couldnt_check` is not
the outcome here — this is a refusal to write, not a measurement that could
not be made.

**And the report states what a user with pre-043 receipts actually sees**,
verbatim and in order: which command they run, which message they get, what
they do next, and what happens when they do it. They exist — six info files in
this checkout alone, and every workdir fetched from a pod — so **the remedy
has to be a sentence they read, not an inference they make.** A refusal whose
remedy is obvious to the person who wrote the refusal is not a remedy.

Show the real text, not a paraphrase of it. If reading it back reveals that
the next step is not obvious, that is a finding about the message and it is
cheaper to find here than in a bug report.

### 4. Rediscovery, as the standing rule now requires

Run it against the pre-fix source for each of the three known instances and
report how many it names. It should reach `price_table.path`, which is the
reason it exists; say so with the measurement rather than by assertion, and if
it misses one, say which and why.

### 5. Settle `requirements_file.path` first, because it is the hard case

044f found four writers recording it as `os.path.abspath(...)`, fixed them,
and **reverted** — `proposals/propose.py` reads the field back and reopens the
file, so a public path breaks resolution when the requirements file is outside
the checkout. 30 tests in `test_propose.py`, measured.

> **A receipt does not name the filesystem it was produced on**, and **a later
> command must be able to reopen what the run used.** Both are right. This
> field has been satisfying the second by violating the first, on every run,
> and nobody had noticed the two rules were in conflict.

Once `write_json_stable` refuses, this field cannot stay as it is. Options, to
be judged rather than assumed:

- **the digest plus the repo-relative path, resolved against the workdir.**
  The receipt records what it already records — `sha256` — and a path that
  names no filesystem; `propose` resolves it relative to the workdir rather
  than reopening an absolute path. **Satisfies both rules, and makes a run
  portable**: the workdir and its receipts can move to another machine and
  still resolve. Its cost is the case below;
- a public `path` for the record and a separate, non-published field for
  resolution, which splits one fact into two and needs a reason;
- the field is only ever resolvable inside a checkout, declared as such.

**The developer's inclination is the first, argued rather than imposed, and it
turns on one measurement.** Resolving against the workdir breaks when a
workdir has been moved away from the checkout it was produced beside.

> **Measure that case before deciding. If it is common, say so and the ruling
> changes.**

### It was measured, and it points the other way

`tasks/scratch/044g_moved_workdirs.py`, over all 32 info files in `runs/`:

| | |
|---|---|
| recorded path resolves against this checkout | **25** |
| does not resolve | **7** (one is a `c:` / `C:` artifact of the check, so **6** real) |
| field absent | 0 |

The kinds matter more than the 19%:

| workdir | recorded | why it fails |
|---|---|---|
| `032b-state-pod/simulate_info.json` | `/workspace/oneground/…` | **pod-produced** |
| `arxiv-150k-via-characterize/verify_info.json` | `/workspace/oneground/…` | **pod-produced** |
| `034-reference-before-034` ×2 | `…/oneground-pre034/…` | a checkout that no longer exists |
| `032b-state-pod`, `032b-state-local.before-fix` | `…/oneground-v2/…` | a sibling checkout |

**The moved workdir is not the edge case. It is this project's standard
heavy-job workflow.** Every pod session produces `/workspace/...` paths and
fetches the workdir here, so a pod run's recorded path can never resolve on
the laptop — by design, not by accident.

So the worry inverts. **The absolute-path scheme is what breaks on the moved
case, today, in 19% of workdirs and in 100% of pod runs.** And the files those
broken paths name are present in this checkout by basename —
`requirements.arxiv-150k.pod.yaml`,
`requirements.arxiv-150k.determinism.032b.pod.yaml` and
`requirements.arxiv-150k.reference.yaml` all resolve here — so a repo-relative
path resolved against the workdir's checkout **fixes** the pod case rather
than breaking it.

The one case nothing recovers is `020-ref-arxiv.yaml`, from the deleted
`oneground-v2` worktree: absent from this checkout entirely. No scheme
resolves a file that does not exist, and losing it is the worktree-deletion
rule this project already has, not an argument about path form.

### Ruled: the digest plus the repo-relative path, resolved against the workdir

**On the measurement, not on anyone's inclination.** A pod session always
produces a path the laptop cannot resolve, so **the absolute scheme fails on
this project's standard heavy-job workflow while claiming to protect a case it
does not protect.**

**The deleted-worktree casualty is not to be scored against this change.**
`020-ref-arxiv.yaml` lived in the `oneground-v2` worktree and the worktree was
deleted; the file is gone. No path scheme recovers a file that does not exist,
and an absolute path pointing at it fails exactly as a repo-relative one does.
That loss belongs to the worktree rule this project already has — *a
throwaway worktree's contents are deleted with it* — and naming it here is so
that nobody counts it as a cost of moving to repo-relative paths. It is not
one.

`oneground/receipts/test_pathguard.py:KNOWN_OPEN` holds the four sites and
asserts the set is exactly those four, so closing them here fails that test
until the entry is deleted. That is deliberate.

### 6. What else breaks

This will refuse payloads that are written today. Find them before deciding
the shape of the check, not after: the four sites 044f fixed are done, but
`runs/` holds pre-043 receipts and some test fixtures may construct payloads
with absolute paths deliberately. **Report the blast radius as a measurement
before changing behaviour**, and if a test legitimately needs an absolute path
in a payload, that is a finding about the test.

## What this may not do

- **Repair, normalise or warn-and-continue.** Ruled: it refuses.
- **Replace either existing check.** Three checks see three different things.
- **Widen what counts as a machine path until nothing fires.** If it is too
  noisy, the finding is the noise and what it is made of.
- **Turn the refusal into `couldnt_check`.**

## Acceptance

- `write_json_stable` refuses a payload containing a machine-local path,
  naming the key path and the fragment, with the re-run remedy in the message.
- **`requirements_file.path` settled**, with the option chosen and the other
  two said to be refused and why; `KNOWN_OPEN` emptied and its assertion
  updated in the same commit.
- **The moved-workdir case measured, not reasoned about** — done above, 7 of
  32, and the ruling rests on it.
- **What a user with pre-043 receipts sees**, quoted verbatim in the report:
  command, message, next step, result.
- The blast radius measured and reported before the behaviour changed.
- The rediscovery tally reported, including `price_table.path`.
- Both existing checks present and passing, unmodified.
- Full suite green, and no published value moved.
