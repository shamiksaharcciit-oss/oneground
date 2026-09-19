# Report: 030c-one-output-failure-costs-only-itself

## Repo state expected vs found

Expected `_fetch_outputs` to probe each output outside any `try`, and
`cmd_watch`'s new stop message to assert that no deliberate stop exists. Found
both, on `task-030` at `5f0a3b8`.

## What was done

Two changes, both in `oneground/pod/cli.py`.

### 1. Each output is attempted inside its own `try`

`_fetch_outputs` had four levels of protection where it needed one:

| call | protection before |
|---|---|
| `ssh.exists(remote)` | **none** |
| `ssh.get(...)` | `except sshx.SshError` only |
| `os.path.getsize(dest)` | none |
| `subprocess.run(tar …)` | return code checked, exceptions not |

So a transient ssh failure on the probe — `exit 255`, the kind that already
happened once in task 030 when a `pkill -f` killed its own shell — raised
straight out of the loop. Every later output was skipped, not attempted, not
mentioned, and the session's exit code said "fetch failed" without saying
which outputs had never been tried.

The per-output body is now `_fetch_one`, and the loop wraps each call in a
`try` that catches broadly, names the output that failed, says it is
continuing, and goes on. The exit code still reports whether everything
arrived, and a closing line says how many of how many did not.

The distinction the old code got right is kept: **an output that is not there
is couldn't-check, not a transport failure**. Absent says the run did not get
that far; failed says we could not look. They are counted the same and printed
differently, and a test pins that they stay apart.

### 2. The stop message says what was observed

```
before:  POD STOPPED UNEXPECTEDLY: desiredStatus is EXITED. …
after:   POD IS NO LONGER RUNNING: desiredStatus is EXITED, and nothing in
         this session asked for that. …
```

"UNEXPECTEDLY" asserted that no deliberate stop exists. That is true only
while `oneground pod down` terminates rather than stops — a claim about the
rest of the tool that this line is in no position to make, and one that would
quietly become false the day a stop is added. The new wording states the two
things actually known at that point: the pod is not running, and this session
did not ask for that.

## Why it mattered

This is the failure task 030b just fixed, one layer down — and 030b's own
remedy had made it worse.

030b's fix was to declare the run log **first**, so a run terminated before
its MANIFEST still comes home with its phase timings and its rejection tally.
`_fetch_outputs` walks the list in order. So after 030b, a flaky probe on the
log would have cost **both tarballs** as well as the log: the change that
protected the evidence had put it in front of the bus.

Neither task's fix is safe without the other.

## Measurements

No runtime measurements; this is error handling. What is measured is coverage.

| | before | after |
|---|---|---|
| unguarded calls per output in the fetch loop | 3 | **0** |
| an output failure skips later outputs | yes | **no** |
| tests in `oneground/pod/test_pod.py` | 191 | **196** |
| full suite | 1021 passed, 5 skipped | **1026 passed, 5 skipped** |

## Verification

Five new tests. The first is the one the developer asked for.

- `test_a_failed_probe_on_the_first_output_does_not_skip_the_rest` — a fake
  whose `exists` raises `SshError` on the **first** output only. Asserts the
  failure is reported, that the loop says it is continuing, and that the two
  later outputs **still arrive** (`ssh.fetched == [small.tgz, large.tgz]`).
  Fails against the old code, which fetched nothing at all.
- `test_every_output_is_probed_even_when_an_earlier_one_fails` — all three
  outputs are probed, not just the one that failed.
- `test_a_missing_output_is_couldnt_check_not_a_transport_failure` — an absent
  output prints couldn't-check and not FAILED. This is the distinction that a
  broad `except` is most likely to erase, so it is pinned.
- `test_all_outputs_arriving_is_a_clean_exit` — exit 0, no "did not arrive"
  line, all three fetched. The happy path still behaves.
- `test_a_transfer_failure_on_one_output_does_not_cost_the_others` — `ssh.get`
  raising `OSError(ENOSPC)` rather than `SshError`. The old guard caught only
  `SshError`, so a full local disk escaped the loop exactly as the probe did;
  the middle output fails and the other two arrive.

Full suite: **1026 passed, 5 skipped**.

**Couldn't check:** the live path, for the same reason as 030b — provoking a
transient ssh failure mid-fetch against a real pod is not something I can
arrange on demand. The fakes exercise the loop's control flow; the code they
exercise is the code that ran for real three times in task 030.

## Observed, not done

- **`provenance_warning` and the extract are inside the per-output `try`
  now**, which is right, but it means a malformed tarball is reported as a
  fetch failure rather than as an extraction failure. The message carries the
  `tar` stderr either way, so nothing is hidden, but the two are no longer
  distinguishable by exit path. Not worth a separate status today.
- **`failures` counts outputs, not causes.** A session with one absent output
  and one transport failure exits 1 and the summary says "2 of 3 did not
  arrive", which is true but flattens couldn't-check and failed into one
  number. The per-output lines keep them apart; the summary does not.

## Repo now contains

Changed:

- `oneground/pod/cli.py` — `_fetch_one` extracted, `_fetch_outputs` made
  per-output fault-tolerant, the stop message softened
- `oneground/pod/test_pod.py` — `_FakeSshFlakyProbe` and five tests, plus the
  030b assertions updated to the new wording

New:

- `tasks/030c-one-output-failure-costs-only-itself.report.md`

## Blocked on developer

None.
