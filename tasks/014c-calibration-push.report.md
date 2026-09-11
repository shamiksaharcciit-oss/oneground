# Report: 014c-calibration-push

## Repo state expected vs found

| Expected from the brief | Found |
|---|---|
| `record-calibration` pushes to `calibration` with inline git | yes — `.github/actions/record-calibration/action.yml`, the `push to the calibration branch` step |
| that step checks out a stale tip before committing | confirmed, and the cause is narrower than "stale" — see below |
| `workflow_dispatch` may need adding to the calibration workflow | **already present.** `.github/workflows/calibration.yml` triggers on push, pull_request, schedule and workflow_dispatch, and the `pins` job runs under it (`if: github.event_name != 'schedule'`). No change made. |

One thing the brief did not ask about turned out to be load-bearing and is
reported under "Observed, not done": the tests guarding this workflow were
collected by nothing.

## What was done

### The diagnosis

Run #3's measurement steps were all green. The failure was the push alone.
The brief's reading — "checked out a stale tip" — is right in effect, but the
mechanism is more specific, and it matters because a stale tip would have been
cured by the retry the brief asks for, and this would not.

The old step:

```bash
git fetch origin "$BRANCH" || true
git checkout -B "$BRANCH" "origin/$BRANCH" 2>/dev/null \
  || git checkout -B "$BRANCH"
```

`actions/checkout` configures a `refs/remotes/origin/*` refspec when it checks
out a branch. On a **tag** push it does not. So `origin/calibration` did not
exist as a local ref, `git fetch origin "$BRANCH"` updated only `FETCH_HEAD`,
the `|| true` hid that, the first checkout failed, and the fallback started
`calibration` **from the tag commit** — a commit with no ancestry relationship
to what the remote's `calibration` already held. The push was not racing
anything. It was rejected because the branch had been re-pointed at an
unrelated history, and it would have been rejected on every retry.

This is confirmed rather than argued: [`test_push_calibration.py`](.github/scripts/test_push_calibration.py)
reproduces it (see Verification).

### The fix

[`.github/scripts/push-calibration.sh`](.github/scripts/push-calibration.sh) — the git plumbing, out of YAML so it
can be tested:

1. **Asks the remote.** `git ls-remote --exit-code --heads "$REMOTE" "$BRANCH"`
   decides whether the branch exists, rather than inferring it from whether a
   local ref happens to be configured. It then fetches an explicit refspec
   (`+refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH`) so the ref really is
   there before checkout. Absent → created from `$BASE_BRANCH` (`main`).
2. **Merges, does not rebase.** A rebase of an append-only JSONL conflicts on
   the last line, and resolving that conflict either way silently discards one
   run's measurement. [`merge_history.py`](.github/scripts/merge_history.py) instead appends this run's
   lines to whatever the branch now holds, validating every line as JSON first
   so a malformed run fails here rather than pushing a history `calibrate
   show` cannot read.
3. **Bounded retry, never a force.** Three attempts by default, each
   re-deriving from the *new* tip, with `git reset --hard HEAD~1` in between so
   attempts do not stack duplicate commits. There is no `--force` anywhere: a
   force here deletes precisely the concurrent lines the retry exists to
   preserve. A test asserts its absence from the source.

### Two defects found while wiring it

Neither was in the brief; both are in the path the brief asked me to fix, and
both would have produced a wrong result rather than a visible failure.

**(a) The contradiction check was about to re-acquire run #1's bug.**
`find contradictions` ran `count_contradictions.py --appended N`, which slices
the last N lines of `calibration/history.jsonl`. That step runs *after* the
push — which now switches to the `calibration` branch and merges. The tail of
the merged file is not reliably this run's lines: a concurrent run's lines can
sit among them, and deduplicated lines shift the count. The step would then
have opened an issue and failed the build on somebody else's measurement —
the same class of error as run #1, relocated.

`count_contradictions.py` gains `--lines <file>`, which judges exactly the
lines it is given, with no slice. The action uses it. `--appended` stays for
callers that genuinely only have a count, with a docstring saying when it is
safe.

**(b) A history that loses lines would have been pushed.**
`what changed` only counted added lines. It now captures them, and refuses a
diff with a non-zero *removed* count: the history is append-only, and a
removal means a run rewrote a measurement that is not its own. No retry makes
that the right push.

## Measurements

All on `.venv\Scripts\python.exe` (Python 3.12, pinned environment).

| Measurement | How obtained | Result |
|---|---|---|
| Full suite | `python -m pytest -q` | **484 passed, 1 skipped** in 297.9 s |
| Workflow-script suite | `python -m pytest -q .github/scripts` | **34 passed** in 163.3 s |
| Total collected | the two runs above | 519 (485 + 34) |
| New tests in this task | 17 (11 push, 6 counter) | — |
| Leak scan | `tasks/scratch/014-leak-scan.py`, all paths staged | **0 files would be published**; 22 pod-id occurrences kept as evidence |
| YAML validity | `yaml.safe_load` on the action and the workflow | both parse; steps and inputs as intended |
| Script mode | `git ls-files -s` | `100755` (the action invokes it directly; 100644 would be a runner failure) |

### The negative control

A test that passes against the bug is worthless, so run #3's logic was
restored into `start_branch` and the suite re-run:

```
FAILED test_an_existing_branch_is_extended_not_replaced
FAILED test_a_tag_checkout_with_no_tracking_ref_still_finds_the_branch
2 failed, 6 passed
```

and the tag-checkout test printed run #3's failure verbatim:

```
attempt 1/3: branch created on origin      <- "created", against an existing branch
push rejected -- the tip moved. Re-deriving from it.
attempt 2/3: branch created on origin
...
::error::could not push calibration after 3 attempt(s)
```

Worth recording: **the retry loop alone does not rescue run #3.** With the old
`start_branch`, all three attempts restart from the same wrong commit. The
`ls-remote` probe is the fix; the retry only covers genuine concurrency.

### Shallow clones — measured, not assumed

`actions/checkout@v4` defaults to `fetch-depth: 1`, and pushing from a shallow
clone is a documented refusal mode. Rather than pre-emptively adding
`fetch-depth: 0`, I measured it against a bare repo: **both paths exit 0**, and
no prior run's lines are lost — our commit's parent is a tip the remote already
has, so only the new commit is sent. Both cases are now tests
(`test_a_shallow_checkout_can_create_the_branch`,
`test_a_shallow_tag_checkout_extends_an_existing_branch`). No `fetch-depth`
change was made.

## Verification

**Verified.** Eleven tests drive the shipped script against a real bare git
repository — a stubbed remote, not a mocked one:

- branch absent → created from `main`, both lines present *(the brief's case 1)*
- branch present → extended, the earlier run's line still there *(case 2)*
- a tag checkout with every remote-tracking ref and the fetch refspec deleted
  → still finds the branch *(run #3's exact condition)*
- two runs racing → the loser retries and **both** lines survive
- a remote whose `pre-receive` hook rejects everything → exits 1 after exactly
  `PUSH_ATTEMPTS` attempts, no attempt 3 of 2
- a wedged run leaves no commit behind
- a byte-identical line is not duplicated
- an empty new-lines file is not a failure
- no `--force` in the source
- both shallow-clone paths

Six further tests cover `--lines`, including one showing the tail slice
misreading a merged history where `--lines` does not.

**Couldn't check.** Whether **GitHub's** receive-pack accepts the shallow push.
The local bare remote exercises git's client-side logic, but GitHub applies its
own `shallow update not allowed` policy, which a `file://` remote cannot
reproduce. This resolves on the next real run and nowhere else. It is the one
part of the fix not settled by measurement.

Also couldn't check: the fix running end-to-end on a runner. That needs a push,
which is the developer's.

## Observed, not done

- **The tests guarding this workflow ran nowhere, and I fixed that.** The only
  pytest invocations in the repo are `python -m pytest -q` in the `pins` and
  `weekly` jobs. pytest prunes dot-directories, so `.github/scripts` was never
  collected — neither 014b's counter tests nor these. Naming the directory
  alongside `.` does not help: pytest drops an argument that is a descendant of
  another, and collection stays at 485 rather than 519 — measured both ways.
  Both jobs now have a second step, `tests for this workflow's own scripts`,
  running `python -m pytest -q .github/scripts`. This is slightly wider than
  the brief; leaving tests that cannot run to guard a workflow that has now
  failed three times seemed the wrong call, but it is a scope call and yours to
  reverse.
- `.github/scripts/fetch-glove.sh` is mode `100644`, but it is invoked as
  `bash .github/scripts/fetch-glove.sh`, so the mode is harmless. Not changed.
- The `drift` job has no `unit tests` step at all, so it gains no script-test
  step either. Left as found.
- `merge_history.py` treats a byte-identical line as one measurement, not two.
  For genuinely separate measurements this cannot collapse anything — they
  differ in date, run id or environment — but it does mean a re-run of an
  identical job records nothing new. That is the intended reading of
  append-only, but it is a decision, not a fact, and belongs in front of you.

## Repo now contains

Committed as **`f4f3e27`** on `main`, `task 014c:` prefix. Not pushed.

| Path | |
|---|---|
| [.github/scripts/push-calibration.sh](.github/scripts/push-calibration.sh) | new, mode 100755 — the branch/merge/retry plumbing |
| [.github/scripts/merge_history.py](.github/scripts/merge_history.py) | new — append-only semantic merge |
| [.github/scripts/test_push_calibration.py](.github/scripts/test_push_calibration.py) | new — 11 tests against a stubbed remote |
| [.github/scripts/count_contradictions.py](.github/scripts/count_contradictions.py) | `--lines`, and `judge()` split from the slice |
| [.github/scripts/test_count_contradictions.py](.github/scripts/test_count_contradictions.py) | +6 tests |
| [.github/actions/record-calibration/action.yml](.github/actions/record-calibration/action.yml) | captures the appended lines, refuses removals, calls the script, judges by name; new `new_lines` input |
| [.github/workflows/calibration.yml](.github/workflows/calibration.yml) | `pins` and `weekly` run the script tests |
| `tasks/scratch/014c-patch-action.py` | the patch script (scratch is gitignored) |

## Blocked on developer

1. **Push `f4f3e27`.** I do not push.
2. **Run the calibration workflow via `workflow_dispatch`** to produce a green
   run before the 15th. That is the only thing that settles the one
   couldn't-check above — whether GitHub's receive-pack accepts a push from the
   depth-1 checkout. If it refuses with `shallow update not allowed`, the fix
   is one line, `fetch-depth: 0` on the three `actions/checkout@v4` steps, and
   I would rather you saw that possibility named in advance than discover it as
   run #4.
3. If the first dispatched run creates `calibration` fresh from `main`, its
   first commit will carry `main`'s existing history lines. That is correct —
   the branch is a superset — but it will look like a large first diff.
