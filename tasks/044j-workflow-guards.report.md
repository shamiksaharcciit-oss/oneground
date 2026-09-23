# Report: 044j-workflow-guards

## A tool's coverage is a claim, and nobody checks it

**Leading, because it is the fourth instance of one failure and the first to
occur inside the pass written to end that exact failure.**

Four tools in this project have each been correct about what they examined and
silent about what they did not reach:

| | the tool | what it could not see |
|---|---|---|
| 1 | a grep | — |
| 2 | a `var()` check | — |
| 3 | an `atexit` test | — |
| 4 | **an enumeration of a page's claims** | the options table's outcome badges |

*The first three are named as the developer named them; the fourth is the one
this task produced and the one described below in detail.*

**The fourth.** Core found a self-contradiction on the workspace mockup and the
instruction was explicit: read the whole page before editing, not the section
the finding names, because that scoping failure had already produced a second
pass three times. So the page was enumerated — every section header, every
figure cell, every decision-log entry, every drawer — and five edits were
applied in one pass.

The enumeration had no pattern for the options table's outcome badges. So the
decision-log entry became *couldn't check* and the table row stating the same
verdict stayed *meets*. Sweeping afterwards for everything that had to move
because one verdict moved then found the tally at the top of the page still
reading *1 meets · 6 fails · 1 couldn't check*.

> **Reading the whole page is not enough if the reading is done by a pattern
> list. The pattern list is itself a claim about where claims live — and it
> was incomplete.**

### The general form

> **A tool's coverage is a claim, and a claim nobody checked is what all four
> have in common.**

Each of these tools reported a result and, silently alongside it, a second
proposition: *these are all of them*. The first is tested, argued about and
believed on evidence. The second is never stated, so it is never doubted — and
it is the one that fails.

This is why a zero from a search is the least trustworthy result it can give,
and it is the same shape as `docs/PRACTICE.md`'s rule that a survey which
cannot rediscover its own motivating case is not evidence. That rule asked a
tool to prove it could find one known thing. The general form asks the harder
question: **what kind of thing can this tool not find at all?**

The cheap check is to state the coverage claim out loud beside the result —
*"patterns: section headers, figure cells, log entries, drawers"* — because a
list written down invites the question *what else is there?* and a list left
implicit does not.


Four guards, built against a tree that was already correct so each could be
seen to fail. Core proposed two of them, added the third, and the fourth is
their second option made code.

## The test that matters more than the function it tests

**Leading, because the next person to codify a convention will write the
function and not the test.**

`copy_cited_run` decides where a run a page cites is kept. The obvious thing
to write is the function. The valuable thing is beside it:

```python
def test_the_two_runs_already_kept_by_hand_are_where_this_would_put_them():
```

The route had been walked twice by hand before it was code — once for
`1ombs4scr257a5`, once for the superseded 9 September report. The test asserts
that the function agrees with both.

> **A function governs what comes next. A test that checks what already
> happened governs both.** If the function ever disagrees with either of those
> two, one of them is in the wrong place — and nobody would otherwise find
> out, because the hand-placed copies are exactly the ones no future run will
> touch.

Codifying a convention without checking it against what the convention
already produced leaves the old instances unverified forever, and they are the
ones most likely to be cited: they are older, so more things point at them.

## The four

### 1. Refuse if exists — the guard whose absence caused all of this

`verify.guard_verify_output`. On 2026-09-13 a pod run wrote `verify.json` into
a workdir already holding the 9 September run's receipts. Nothing refused,
nothing kept a copy, and the evidence behind a verdict the public site was
publishing stopped existing.

Two halves, and the second is the one that makes the first survivable:

- **refuse** an incoming run whose `environment_id` differs from the one
  already there. That is a different measurement landing on another's
  receipts, and it is never what anyone meant.
- **archive** the existing pair first, *always*, even when the ids match and
  nothing is refused.

**Two deliberate divergences from core's proposal**, both measured:

**Archiving is unconditional, not a consequence of refusing.** A retry of the
same environment is legitimate and its predecessor is still evidence. More
practically: *a guard that turns every honest re-run into an argument with a
flag is a guard someone disables.* Keeping the legitimate path cheap is what
makes the refusal survive.

**The live path does not move.** Core proposed `runs/<name>/verify/
<environment_id>/`. Better in the abstract, and not cheaper here: `verify.json`
at the workdir root is read by `calibrate`, `lab/runs.py`, `lab/receipt.py`,
the pod extractor, `report` and the exporter. Six modules and their tests, for
a safety property archiving already delivers. So **the displaced copy takes
core's layout and the live one stays where six readers expect it**. The
relocation is a task with its own measurement, not a rider on this one.

The archive is itself guarded against overwrite. That would be the same defect
one directory down, which is exactly how it would come back.

Eight tests. The sabotage runs twice into one directory and requires the
second to refuse **and the first's digest to be unchanged** — a refusal that
fires after clobbering would pass a test that only checked for the exception.

### 2. The exporter refuses an uncommitted verdict source

The published verdict cited `runs/arxiv-150k-via-characterize/report.json`,
and `runs/` is ignored. The page named a report no commit held, so nobody
could rebuild the decision from the tree that published it.

Refuses a source under `runs/`, refuses anything git does not track, and —
the part that would actually have caught the original — **speaks when more
than one committed report sits beside the one chosen**, naming which it used.

> **Picking one quietly is the failure mode. Picking the wrong one is just its
> symptom.**

### 3. `source_sha256` on the verdict — core's addition

The verdict named a path and not the bytes at it, so the path could be right
and the file anything. `measured.k_sweep` already carried a digest; the
verdict is the block where it matters most, because it is the one a reader is
asked to trust.

**The end-to-end test failed first for the right reason**: the live page cited
its report by path and not by bytes. Re-exported; the declaration was exactly
one added field.

### 4. The cited-run route

`cited_run_destination` and `copy_cited_run`. Copies, then **verifies by
digest** — rule 9 exists because an artifact a report cites was lost twice
between being produced and being cited, the second time unrecoverably. Refuses
a destination holding different bytes, with the sabotage proving the refusal
fires *before* the replacement.

## What core found that we did not, twice

**Worth saying plainly, because it runs the opposite way to the last one.**

Our workspace-page note treated the panel as one run with two unverifiable
figures. Core's addendum showed it is a **composite**: the p95 and the query
count are 9 September's; the 381.2 ceiling is 13 September's `qps_max`; the
18.3% round-trip share is in no report at all, and the one measured share for
that engine is 60%; and the header frames all of it as a corpus that never had
a verify run. **Four multi-run claims our note missed, and then a fifth thing
entirely in the header.**

Both times the correction came from **core tracing our artifacts**, not from
us reading our own page. That is the same asymmetry we noted about their three
undeclared changes, running the other way: we found their understatement by
diffing their files, they found ours by tracing our data.

> A relationship where both sides have now caught the other's understatement
> is worth more than either check, because neither check would have found its
> own side's.

We verified every point of their trace against our own artifacts before
accepting it — `381.25` is 13 September's qdrant `qps_max` and `381.2` occurs
nowhere in the 9 September report; `18.3`, `0.183` and `rtt_share` are absent
from it entirely. It holds.

### And one distinction the reply had to keep separate

The median is **unverifiable** — no receipt settles it either way. The 18.3% is
**contradicted** — no receipt carries it *and* the only measured share is 60%,
which is why that run could not be latency-checked at all.

The sentence *"under the 20% limit, so this figure describes the engine"* is
withdrawn rather than softened, because it is our own attribution rule run
backwards: the rule exists to **refuse** a latency number when the round trip
is too large a share of it, and used this way it asserts a number is
trustworthy on the strength of an input nothing records.

> **An unsupported figure at least stays silent about its own standing. That
> sentence vouches.**

## Verification

| check | result |
|---|---|
| Two runs, one directory, second refuses | **PASS** — and the first's digest is unchanged |
| The real colliding pair of environment ids refuses | **PASS** |
| A retry of the same environment is allowed and still archived | **PASS** |
| The archive is not itself overwritten | **PASS** |
| An unreadable existing file still refuses | **PASS** |
| A `runs/` report is refused, and named | **PASS** |
| An untracked report outside `runs/` is refused | **PASS** |
| The real committed report is accepted | **PASS** |
| The guard's mechanism is present (git reachable) | **PASS** — not vacuous |
| The page carries the digest of the report it cites | **PASS** after re-export; failed first |
| The two hand-placed runs are where the function would put them | **PASS** |
| A destination with different bytes is refused before replacement | **PASS** |

## Repo now contains

| path | what |
|---|---|
| `oneground/verify/__init__.py` | `guard_verify_output`, `VerifyOutputExists`, `DISPLACED_VERIFY_DIR`, `replace_verify` through `run` |
| `oneground/verify/test_output_is_not_overwritten.py` | 8 tests, one the sabotage |
| `corpora/export_teaser_data.py` | `committed_report`, `source_sha256`, `cited_run_destination`, `copy_cited_run` |
| `corpora/test_export_refuses_untracked_verdict.py` | 6 tests |
| `corpora/test_cited_run_route.py` | 6 tests |
| `tasks/note-workspace-page-9-september.md` | rewritten; supersedes the routed version |

## Blocked on developer

Nothing. The relocation of the live verify path is named as its own task if
ever wanted, with the six-module measurement attached.
