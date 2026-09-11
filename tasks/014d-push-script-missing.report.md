# Report: 014d-push-script-missing

## Repo state expected vs found

| Expected from the task | Found |
|---|---|
| `.github/scripts/merge_history.py` is **not in the commit**, hence run #5's `No such file or directory` | **No — it is in the commit, and always was.** `git ls-tree -r origin/main .github/scripts` lists it, and `origin/main` is `1537ff5`, the 014c commit, which has been pushed. So are `push-calibration.sh` (mode 100755) and `count_contradictions.py`. |
| the fix is to add the missing file, plus any other referenced-but-missing path | **No path is missing from the commit.** Every path the workflow and the action name exists. The failure is real and the error message is verbatim correct, and the file is nonetheless there — because it stops being on disk *between* the checkout and the invocation. |
| a test asserting every referenced path exists | built, and it passes on the repo as found — which is exactly why it could not have caught run #5 on its own. It ships alongside a structural assertion that does. |

Per CLAUDE.md rule 1 this is a repo state that does not match the task's
assumption, so it is at the top rather than buried. I did not stop, because
the task — make run #6 not die on a missing script, and pin the referenced
paths with a test — is well defined and unchanged by the correction; only the
location of the defect moved. The one scope call I made is under "Observed,
not done".

## What was done

### The diagnosis

`git ls-remote` says the `calibration` branch exists, at `9f6d883`. Its
ancestry is the giveaway:

    $ git merge-base origin/calibration origin/main
    27173ae oneground 0.1.0-preview

    $ git ls-tree -r origin/calibration --name-only .github/scripts
    .github/scripts/fetch-glove.sh

The branch was cut by run #1 from `27173ae`, **three commits before
`.github/scripts/` gained any of 014c's files**, and it has only ever received
`calibration/history.jsonl` commits since. Its tree has one script in it.

014c's `push-calibration.sh` did this, in `start_branch`:

    git checkout -B "$BRANCH" "refs/remotes/$REMOTE/$BRANCH"

That is a checkout of the calibration branch **into the job's working tree**.
Git makes the working tree match the target tree, so it *deletes*
`.github/scripts/merge_history.py`, `count_contradictions.py` and
`push-calibration.sh` from disk. Eleven lines later:

    python "$here/merge_history.py" --base "$HISTORY" ...

`$here` is an absolute path into the workspace, resolved before the loop and
still correct — the file it names is simply gone. Hence run #5.

**There is a second failure behind it.** The action's `find contradictions`
step runs one step after the push:

    python "${{ github.action_path }}/../../scripts/count_contradictions.py" --lines ...

That path is in the workspace too, and the same checkout removed it. Fixing
only `merge_history.py`'s resolution would have moved run #6's failure one
step later, to an identical error on a different file. Both are fixed by the
same change, because both have one cause.

### Reproduction, before any fix

`tasks/scratch/014d-repro.py` builds a bare remote with the real shape — a
`calibration` branch cut at a commit with no `.github/scripts/`, and a `main`
carrying the scripts — clones it, appends a line, and runs the **shipped**
script from inside the clone:

    calibration branch tree: ['calibration/history.jsonl']
    --- exit 2 ---
    attempt 1/3: branch existing on origin
    python.exe: can't open file '...\work\.github\scripts\merge_history.py':
        [Errno 2] No such file or directory
    merge_history.py on disk after the checkout: False

Run #5, locally, with no CI involved.

### Why 014c's eleven tests all passed over it

`test_push_calibration.py` invokes the script at `SCRIPT`, which is the **real
repository's** `.github/scripts/push-calibration.sh`, with `cwd=work` pointing
at a clone under `tmp_path`. So `$here` resolved into the real repo, which no
checkout inside `tmp_path` can touch, and `merge_history.py` was always
present. The harness ran the script from outside the tree it was operating on.
CI runs it from inside. That single difference is the whole bug, and it is why
a genuinely non-synthetic stubbed remote still could not see it.

### The fix

The lesson of #5 is not "resolve that path differently" — a copy to a temp
directory would have rescued `merge_history.py` and left
`count_contradictions.py` broken. It is that **the working tree is the wrong
vehicle for this update**: the branch being written to has a different tree
from the branch the job is running from, and a checkout makes those two facts
collide.

So `push-calibration.sh` now builds the commit out of the object database and
never moves HEAD, the index, or a file in the checkout:

    git cat-file -p "$tip:$HISTORY_PATH" > base.jsonl      # the branch's history
    python "$here/merge_history.py" --base base.jsonl ...  # unchanged, still tested
    blob="$(git hash-object -w --path "$HISTORY_PATH" -- merged.jsonl)"
    GIT_INDEX_FILE="$tmp/index" git read-tree "$tip"       # a scratch index
    GIT_INDEX_FILE="$tmp/index" git update-index --add \
        --cacheinfo "100644,$blob,$HISTORY_PATH"
    tree="$(GIT_INDEX_FILE="$tmp/index" git write-tree)"
    commit="$(git commit-tree "$tree" -p "$tip" -m "$MSG")"
    git push "$REMOTE" "$commit:refs/heads/$BRANCH"

Consequences worth naming:

- Every script path stays valid for the whole job. `count_contradictions.py`
  is fixed by the same change, without being touched.
- `git reset --hard HEAD~1` between attempts is **gone**. 014c ran that
  against the runner's real checkout; it was safe there only because the
  checkout had already been switched to a throwaway branch. Now there is
  nothing to undo — the commit is a dangling object no ref points at.
- `git checkout -- "$HISTORY"`, which restored the run's dirty history file
  before switching branches, is also gone. The base is read from the object
  database, so the working copy's contents are irrelevant.
- A failed run leaves the workspace byte for byte as it found it.

The three properties 014c established are unchanged: the `ls-remote` probe
(run #3's fix), the semantic append-only merge, and the bounded retry with no
force anywhere.

## Measurements

All on `.venv\Scripts\python.exe` (Python 3.12, pinned environment).

| Measurement | How obtained | Result |
|---|---|---|
| Workflow-script suite | `python -m pytest -q .github/scripts` | **44 passed** in 158.4 s |
| — of which pre-existing | same run | 34, all passing unchanged against the rewritten script |
| — new in this task | same run | 10 |
| Full suite | `python -m pytest -q` | **484 passed, 1 skipped** in 345.0 s — the 014c baseline, unchanged |
| `calibration` branch tree | `git ls-tree -r origin/calibration --name-only .github/scripts` | **1 file** (`fetch-glove.sh`) |
| `calibration` fork point | `git merge-base origin/calibration origin/main` | `27173ae`, 3 commits behind `main` |
| `merge_history.py` in `origin/main` | `git ls-tree -r origin/main --name-only .github/scripts` | **present** |
| Script mode | `git ls-files -s` | `100755`, unchanged |

### The negative control

Each new guard was run against 014c's script, restored from `HEAD`:

    FAILED test_the_scripts_survive_a_push_to_a_branch_whose_tree_lacks_them
            [Errno 2] No such file or directory
            ...\work\.github\scripts\merge_history.py
    FAILED test_the_push_leaves_the_checkout_exactly_as_it_found_it
            assert 'f943d63944e5...' == 'db2154907a67...'      # HEAD moved
    FAILED test_the_push_never_checks_the_target_branch_into_the_working_tree
            git checkout -B "$BRANCH" "refs/remotes/$REMOTE/$BRANCH"

The first reproduces run #5's error verbatim. The second shows collateral
damage that had not yet been observed: 014c's push left the job's checkout on
a different commit, which is what would have broken `count_contradictions.py`
one step later. The third is the invariant that keeps the design from
regressing.

`test_every_path_the_workflow_names_exists` passes both before and after, as
it must — nothing was ever missing from the commit. It is worth having, and it
is worth being explicit that it is not the test that catches this class.

## Verification

**Verified.**

- Run #5 reproduced from the shipped script, then shown fixed, against a real
  bare git repository whose `calibration` branch has no `.github/scripts/`.
- All 34 pre-existing workflow-script tests pass against the rewritten script,
  including both shallow-clone paths, the concurrent-push race, the bounded
  retry, the no-force source check, and the no-duplicate merge.
- The job's checkout is unchanged by a successful push: HEAD, current branch,
  local branch list and the working copy of the history file all asserted.
- Every path named in `calibration.yml`, `pages.yml` and
  `record-calibration/action.yml` resolves to something in the repo, including
  `${{ github.action_path }}`-relative ones; every `on: paths:` filter still
  matches at least one tracked file.

**Couldn't check.**

- That run #6 is green on a GitHub runner. That needs a push and a dispatch,
  which are the developer's.
- 014c's open couldn't-check — whether **GitHub's** receive-pack accepts a push
  from the depth-1 checkout — is still open, and this change makes it more
  likely to be fine rather than less: the pushed commit's parent is a tip the
  remote already has, and the local clone's shallowness is now irrelevant to
  how the commit is built. A `file://` remote still cannot reproduce GitHub's
  `shallow update not allowed` policy.

## Observed, not done

- **The `calibration` branch will keep diverging.** It is a receipts branch cut
  from `27173ae` that only ever gains `calibration/history.jsonl` commits, so
  its tree drifts further from `main` with every task. That is now harmless —
  nothing checks it out — and arguably correct for an append-only receipts
  branch. But if anyone ever wants CI to *run* from that branch, it cannot.
  Not changed: no brief asks for it, and merging `main` into it would rewrite
  the shape of a record.
- **Run #5's error was reported as a missing file and is not one.** Worth
  saying plainly because the next instance of this class will look the same:
  any step that switches the working tree mid-job invalidates every
  repo-relative path the rest of the job uses. The structural test is the
  guard; the existence test cannot be.
- `.github/scripts/fetch-glove.sh` is still mode `100644` and still invoked as
  `bash .github/scripts/fetch-glove.sh`, so it remains harmless. Unchanged, as
  in 014c.
- The `drift` job still has no `unit tests` step and so still runs no script
  tests. Left as found, as in 014c.

## Repo now contains

Committed on `main`, `task 014d:` prefix. **Not pushed.**

| Path | |
|---|---|
| `.github/scripts/push-calibration.sh` | rewritten: the commit is built with plumbing, the working tree is never switched. Mode 100755 unchanged. |
| `.github/scripts/test_push_calibration.py` | +2 tests — run #5 reproduced, and the checkout left as found |
| `.github/scripts/test_referenced_paths.py` | new — every path the workflow and the action name exists; every trigger filter still matches; the push never checks out the target branch |
| `tasks/scratch/014d-repro.py` | the standalone reproduction (scratch is gitignored) |

`merge_history.py`, `count_contradictions.py` and `action.yml` are unchanged:
nothing was wrong with them.

## Blocked on developer

1. **Push the `task 014d:` commit.** I do not push.
2. **Dispatch the calibration workflow again** for run #6. Run #5's failure
   mode is fixed and reproduced-then-prevented locally; the two things only a
   real run can settle are GitHub's shallow-push policy and the end-to-end
   green.
