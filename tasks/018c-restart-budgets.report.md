# Report: 018c-restart-budgets

The flake 018b diagnosed and declined to fix, fixed.

## Repo state expected vs found

| expected | found |
|---|---|
| `main` after 018b | `35d4934 task 018b: the coverage walk stopped one call short of the bug it was for`, tree clean |
| `v0.1.0` local, on 018's commit | yes, `6ddcb5e`; **not moved** by this task |
| 764 passed, 1 skipped | yes |

`origin/main` is at `643e96f`, so 018 and the 019 brief are pushed and 018b
was the only unpushed commit when this task began. Nothing here is pushed and
the tag is untouched.

## What was done

### The defect, restated precisely

`restart_engine(engine, cfg, engine_name, endpoint, log_fn, timeout=180.0)`
spent one parameter on two unrelated quantities:

1. `subprocess.run(..., timeout=timeout)` — how long the **restart command**
   may take to run;
2. `deadline = started + timeout` — how long the **engine** may take to answer
   a readiness probe afterwards.

These are not the same thing and never were. *"Wait up to three minutes for
pgvector to come back"* is a statement about an engine reloading a corpus.
*"Allow sixty seconds for `pg_ctl restart` to return"* is a statement about
starting a process. A caller who shortens the first never meant to shorten the
second — and with one parameter, a 2-second readiness budget also gave the
shell 2 seconds to start.

On a loaded machine the spawn then exceeded it, `subprocess.run` raised
`TimeoutExpired`, and `restart_engine` **returned**:

```python
except (OSError, subprocess.SubprocessError) as e:
    return f"not restarted: {how} could not be run ({e})"
```

A return, not a raise — correct behaviour, since a restart command that will
not run is a fact about the session rather than a reason to abort. But the
readiness loop was never reached, so the test asserting the readiness path got
`DID NOT RAISE`.

### The fix

```python
RESTART_COMMAND_TIMEOUT = 60.0

def restart_command_timeout(ready_timeout, command_timeout=None):
    if command_timeout is not None:
        return float(command_timeout)
    return max(RESTART_COMMAND_TIMEOUT, float(ready_timeout))

def restart_engine(..., timeout=180.0, command_timeout=None):
```

`timeout` is now unambiguously the **readiness** budget and is documented as
such. The command's budget is derived by `restart_command_timeout`, or passed
explicitly by a caller that means something specific.

**The floor is a maximum against the readiness budget, never a replacement.**
That shape is chosen deliberately over two alternatives that look similar:

- *a fraction of the readiness budget* (`timeout / 4`) would have the same
  defect in a smaller size — a 2 s readiness budget would give the spawn
  0.5 s;
- *a flat 60 s* would **shorten** what a long-running session asked for, so a
  pod that wants to wait three minutes for a restart command would start
  failing at one.

`max(60, timeout)` means **no caller ever gets less spawn budget than it got
before this task**. The only callers affected are those with a readiness
budget under a minute, and what they gain is budget for a different quantity.

**Neither threshold was raised to make anything pass.** The readiness budget in
the test is still `2.0`, and a test asserts that the readiness loop still gives
up on schedule rather than inheriting the larger number. The 60 s value is not
a relaxation of a chosen threshold: nobody ever chose 2 seconds as a process
spawn limit, it was an accident of sharing one parameter.

One smaller thing fell out. The message now names the budget it exceeded —
*"could not be run within its 60 s command budget"* — because "could not be
run" against 2 s reads as a broken command and against 60 s as a stuck one,
and those call for different next steps. It formats with `:g` rather than
`:.0f`, because a 0.5 s budget printed as "0 s" reads as a bug in the message.
That was found by a test assertion of mine being wrong, not by review.

### What changes pod-side, and what a pod run would exercise

**The only production caller is `oneground/verify/__init__.py:932`**, inside
the `runs: N` load loop, and it passes no `timeout` — so it takes the 180 s
default:

    restart_command_timeout(180.0) == 180.0      (was 180.0 before 018c)

**A pod session's behaviour is bit-for-bit what it was.** The command budget
for the only path that runs on a pod is unchanged, asserted by a test and
printed by the diagnostic. Nothing about `corpora/restart_engine.sh`, the
session's `ONEGROUND_ENGINE_RESTART_COMMAND`, the probes, or the spread
changed.

**What a pod run would newly exercise: nothing, unless a restart command times
out** — and then only the wording of the sentence recorded in `load_restarts`.
The failure path itself is the same failure path.

What a pod run would *confirm*, and this task cannot: that
`bash corpora/restart_engine.sh {engine}` returns inside 180 s on a real pod
for both engines. That was already true on session `20260913-161921` (four
restarts, 121.3 s and 8.8 s to reachable for pgvector, under 0.05 s for
qdrant) and this task does not change what is measured there. **No pod was
created and no money was spent.**

### The regression tests

Five, from the deterministic reproduction 018b already had:

| test | what it pins |
|---|---|
| `test_the_command_budget_is_never_below_the_floor_or_the_readiness_budget` | the rule, over nine readiness values, plus the production default unchanged at 180.0 and an explicit budget winning |
| `test_a_spawn_slower_than_the_readiness_budget_still_reaches_the_probe` | **the regression itself**, with a command that really sleeps 2.5 s against a 2.0 s readiness budget — no monkeypatching, so it cannot pass because a stub was wired up wrongly |
| `test_an_explicit_command_budget_is_honoured_and_says_which_budget` | the other half: a command that will not return is still reported, and the sentence names the budget |
| `test_the_readiness_budget_is_not_silently_widened` | that the fix was not bought by waiting longer — the readiness loop must still give up on schedule |
| `test_the_engine_name_is_substituted` (strengthened) | that it is the **readiness** failure, not the spawn failure: an assertion that could not be made before the budgets were split |

## Measurements

### The suite

| point | passed | failed | skipped |
|---|---|---|---|
| after 018b | 764 | 0 | 1 |
| after 018c | **768** | 0 | 1 |

+4: four new tests, plus one existing test strengthened rather than added to.
`test_verify.py` alone: 47 passed in 98 s, of which about 5 s is the two tests
that deliberately run slow commands.

### The negative control

`tasks/scratch/018b-restart-flake.py`, extended: it restores the pre-018c
shared budget and requires the new tests to fail on it.

```
4. the fix's own negative control: the shared budget restored
   caught  test_the_command_budget_is_never_below_the_floor_or_the_readiness_budget
           a 2.0 s readiness budget gave the command 2.0 s; the two budgets
           are still shared
   caught  test_a_spawn_slower_than_the_readiness_budget_still_reaches_the_probe
           Failed: DID NOT RAISE VerifyError

5. the production path is unchanged
   restart_command_timeout(180.0) = 180.0  (was 180.0 before 018c)
```

The second control reproduces **the original failure message exactly** —
`Failed: DID NOT RAISE VerifyError` — deterministically, with no dependence on
catching the machine slow.

### Two things the controls found about themselves

- **A bare `assert x == y` carries no message**, so `str(e)` is `""` and
  `splitlines()[0]` raises `IndexError`. The first version of the control
  crashed there, and the crash looked like the control failing rather than the
  guard firing. Fixed in the control, and the bare asserts in the new test
  gained messages — a guard whose failure output is empty is a guard that will
  be misread.
- **`pytest.fail` raises `_pytest.outcomes.Failed`, which inherits from
  `BaseException`, not `Exception`.** A control catching `except Exception`
  misses the exact failure it is looking for. That is what `pytest.raises`
  calls on DID NOT RAISE, so it is precisely the case this control exists for.

### The spawn times that caused it

Measured on this machine, unchanged by this task:

```
under load   6 spawns: 0.21 0.31 0.53 0.60 1.04 2.93 s   -- one over 2.0 s
quiet       12 spawns: min 0.20  median 0.30  max 0.55   -- none over
```

## Verification

**Passed.**

- Both new-test controls fail against the restored shared budget, one of them
  with the original error message.
- `restart_command_timeout(180.0) == 180.0`: the production path, and
  therefore every pod session, is unchanged.
- The readiness budget was not widened; a test asserts the loop still gives up
  on schedule.
- The regression test uses a genuinely slow command rather than a stub.
- Full suite: see Measurements.

**Couldn't check.**

- **Nothing ran on a pod.** The claim that pod behaviour is unchanged rests on
  the production caller taking the default and `max(60, 180) == 180`, which is
  argued and tested rather than observed on hardware. A matched session would
  observe it; none was created.
- **Whether 60 s is the right floor** for every restart command anyone writes.
  It is comfortably above what `corpora/restart_engine.sh` needs (pkill +
  setsid, or `pg_ctl restart`, all of which return immediately and leave
  readiness to the probe) and it is never used where the readiness budget is
  larger. It is a chosen number, not a measured one, and it says so.

## Observed, not done

- **`docs/VERIFY.md` does not mention either budget.** The `runs: N` section
  describes the restart and the probes without saying how long anything is
  allowed to take. Adding it is a documentation change to a file this brief
  does not name.
- **`restart_engine` still takes its readiness budget from a default rather
  than from the session.** A session that knows its corpus takes four minutes
  to reload cannot say so; `timeout=180.0` is hard-coded at the one call site.
  The shape for fixing it now exists — a named budget with a rule — but the
  requirements schema would need a field, which is out of scope here.
- **The per-probe slice is still `timeout / 4`, capped at 10 s.** That is a
  fraction of the readiness budget, which is the shape rejected above for the
  spawn — but here it is correct: it *is* a subdivision of the same quantity,
  one attempt within a budget for the thing being attempted.

## Repo now contains

Changed:

    oneground/verify/__init__.py        RESTART_COMMAND_TIMEOUT;
                                        restart_command_timeout(); restart_engine
                                        gains command_timeout and uses the two
                                        budgets separately; the message names
                                        which budget was exceeded
    oneground/verify/test_verify.py     four new tests, one strengthened

New:

    tasks/018c-restart-budgets.report.md

Not tracked (`.gitignore:62`):

    tasks/scratch/018b-restart-flake.py   the 018c negative control appended

## Blocked on developer

Nothing new. The 018 list stands: push `main` and the `v0.1.0` tag, create the
release with both assets, paste `RELEASE_NOTES.md`, `twine upload`. Nothing in
this task touches the release artifacts, and the tag still points at `6ddcb5e`.
