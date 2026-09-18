# Report: release rehearsal (for Monday's merge)

A dry run of Monday on a throwaway branch: `rehearse-release` from `main`,
`origin/task-020` then `origin/task-028` merged into it, everything checked,
the branch deleted. Nothing was pushed to `main`; `v0.1.0` still points at
`dba2fed` and was not touched.

**The headline: Monday is not a clean merge.** Three textual conflicts, all
trivial; one *semantic* conflict that git merges cleanly and breaks 22 tests;
one blocker before the first merge can start; and two failures that belong to
`task-020` and are not the merge's fault. All four are below with their fixes.

## Repo state expected vs found

`main` at `570f07d`, `origin/main` the same, `v0.1.0` on `dba2fed`, the two
branches at `05a4e67` (task-020) and `7422098` (task-028): found, all.

## 1. The blocker, before any merge

    git merge origin/task-020
    error: The following untracked working tree files would be overwritten by
    merge: tasks/020-simulator-state.md

The working tree has an **untracked** `tasks/020-simulator-state.md`, and
`task-020` commits a file at that path. Git refuses and merges nothing.

It is not a duplicate. The two differ by exactly one line, line 4, which names
the second worktree's path: the committed copy writes the home directory as
`C:\Users\<developer>\projects\oneground-v2` and the untracked one spells the
real account name out. The untracked copy is the unredacted original.

*(That line is described rather than quoted here on purpose: quoting it put a
home directory into this report, and the identifier scan caught it while this
was being written — which is the guard doing exactly its job, on the very
report about the file that evades it.)*
**Delete the untracked copy, or move it outside the repository, before
merging.** It must never be `git add`ed: the identifier scan reads tracked
files only, so an untracked file carrying a home directory is exactly the
thing the scan cannot see until the moment it is too late.

For this rehearsal it was moved aside and put back afterwards; it is still
there, untracked, as it was.

## 2. `origin/task-020` merges clean

No conflicts. Merge commit, 14 new task reports among the files.

## 3. `origin/task-028`: three textual conflicts, all additive

| file | what collided | resolution |
|---|---|---|
| `oneground/cli.py` | the docstring's command list: `lab` from 020, `propose` from 028 | keep both, `lab` then `propose` |
| `oneground/cli.py` | the subparser block: `lab`'s ten arguments against `propose`'s five | keep both, in that order |
| `oneground/simulate/__init__.py` | `measure_config`'s signature and docstring: `state_sink=None` from 020, `shard_depth=None` from 028 | keep both parameters and both docstring paragraphs |

`oneground/models/base.py` auto-merged — 020's edits and 028c's rewritten
Determinism section do not overlap.

None of the three is a decision: both sides are additions, and nothing either
branch does is dropped. Ten minutes with the editor.

## 4. The one that matters: a semantic conflict git merges cleanly

**Task 020b changed `simulate.measure_config` to return `(row, timing)`.**
Task 028's `propose.measure_changed` calls it and expects a row. Git sees no
conflict — the two edits are in different functions — and the merged tree
fails 22 of `oneground/proposals/test_propose.py`'s 31 tests with

    AttributeError: 'tuple' object has no attribute 'get'
    oneground/proposals/verdict.py:79

because the tuple reaches `judge()` as a simulate row.

The fix is four hunks in `oneground/proposals/propose.py`, applied and
verified in the rehearsal (**61 of 61 proposals tests pass with it**):

1. `measure_changed` unpacks `row, timing = sim.measure_config(...)` and
   returns the pair;
2. `run` accepts either shape — a test's `measure` stub still returns a row
   alone;
3. `run` passes `timing=changed_timing` to `_info`;
4. `_info` takes `timing=None` and records it under `"timing"`, which is where
   020b put timings: out of the measured row, into the declared file.

The patch is saved at
`tasks/scratch/merge-fix.patch` (untracked, `.gitignore:62`). **It cannot be
applied to `task-028` as it stands** — on that branch `measure_config` still
returns a row, and the unpacking would break it. Two ways to land it:

* **apply it during Monday's merge**, as part of resolving the merge (what
  this rehearsal did), or
* **land a shape-tolerant version on `task-028` first** — `result =
  sim.measure_config(...)` then `row, timing = result if isinstance(result,
  tuple) else (result, None)` — which works on both branches and makes
  Monday's merge hands-off. Say the word and I will; I have not, because it is
  a change to a branch you have already accepted.

## 5. Two failures that are not the merge's

    FAILED oneground/verify/test_matched.py::test_every_session_engine_list_matches_its_requirements
    FAILED oneground/verify/test_matched.py::test_every_session_load_shape_matches_its_requirements

Both **fail on `origin/task-020` by itself** — checked in a worktree of that
branch alone, same two failures, same assertion. `sessions/027-emit-state-arxiv.yaml`
carries three environment keys (`ONEGROUND_REQUIREMENTS`, `ONEGROUND_WORKDIR`,
`ONEGROUND_OUT`) and the test requires five more, from the requirements file's
latency block: `ONEGROUND_CONCURRENCY` (wanted `8`, found empty),
`ONEGROUND_TARGET_QPS`, `ONEGROUND_DURATION_MIN`, `ONEGROUND_RUNS`,
`ONEGROUND_MEASURE_CEILING`.

Either the session file gains those keys or the test learns that a
state-emitting session has no load phase. **That is a `task-020` decision, and
it is the only thing standing between Monday and a green suite.**

## 6. The suite, the guard, the scan

Full suite on the merged tree, after the §4 fix:

    982 passed, 2 failed, 2 skipped in 458.52s (7 m 39 s)

The two failures are §5. The two skips both say why:
`oneground/lab/test_server.py:602` — *node is not on PATH, so lab.js was not
parsed*; `oneground/pod/test_pod.py:2089` — *RUNPOD_API_KEY not set*. Before
the fix it was 24 failed, 960 passed.

**The guard**: 16 dispatchable commands after the merge, including `oneground
lab` and `oneground propose`; five guarded by decoration; zero unaccounted;
`test_every_dispatchable_command_is_guarded_or_deliberately_not` passes. The
stamp on this machine reads `pinned = True`, `local:windows-amd64`, numpy
2.5.3 / faiss-cpu 1.15.0 / scikit-learn 1.9.0.

**The identifier scan ran rather than skipped**: `checkout_root()` is not
None, `identifier_findings()` returned a list, **0 findings over 375 tracked
paths**. The three tests that could have skipped instead —
`test_no_tracked_file_carries_a_machine_identifier`,
`test_the_scan_actually_reads_the_tree`, and 022e's
`test_the_tree_tests_fail_rather_than_skip_when_git_cannot_run` — all
**PASSED**, checked with `-rs` so a skip would have been printed.

## 7. `site/teaser/` against `dba2fed`

    git diff dba2fed HEAD -- site/teaser/     →  empty

Byte-identical. There are **15 tracked paths** under `site/teaser/`, not nine:
nine outside `data/` (`.nojekyll`, `CNAME`, `README.md`, `app.js`,
`check_hosted.py`, `fonts/README.md`, `index.html`, `style.css`,
`verify_teaser_data.py`) and six inside it (`MANIFEST.sha256`, `base.bin`,
`centroids.json`, `inline.js`, `queries.json`, `values.json`). All fifteen are
unchanged; the nine are presumably what you meant, and the other six are
unchanged too.

## 8. A fresh wheel off the merged tree

Built with `python -m build` (setuptools 84.0.0, wheel 0.46.3):

    oneground-0.1.0-py3-none-any.whl   1,985,668 bytes
    oneground-0.1.0.tar.gz             1,904,416 bytes

Installed into a clean venv — which pulled faiss-cpu 1.15.0, numpy 2.5.3,
scikit-learn 1.9.0, PyYAML 6.0.3, zstandard 0.25.0 — and run from an empty
directory that is not a checkout:

    $ oneground --version
    oneground 0.1.0

    $ oneground fixture verify arxiv-smoke
    …
    summary: digests 4 verified, 0 contradicted, 7 couldnt_check (6 receipt, 5 declared)
             values  0 verified, 0 contradicted, 8 couldnt_check
    exit code: 0

It found the fixture inside the installed package, said the environment was
pinned *from the installed distribution's own pins*, said the asset was **not
needed** because the spec publishes no values, verified the four digests that
ship, and named every file it could not check and where it looked. Both
commands behave.

**One wart in that output.** The summary line reads `7 couldnt_check (6
receipt, 5 declared)` — and 6 + 5 is 11, not 7. The parenthetical is the
breakdown of all eleven *listed* files by kind, printed immediately after a
count of seven, so it reads as a breakdown of the seven. It is not new to this
merge and no number is wrong; it is a sentence that invites a wrong reading,
on the one command an outsider is told to run. Not changed here.

## 9. `RELEASE_BODY.md`

Drafted at **`tasks/RELEASE_BODY.md`** — on `task-028`, not on the deleted
rehearsal branch, so it survives: what v0.1 is, the two commands an outsider
can run, what changed since the preview in a user's terms, the four digests,
and the known limits.

The two tarball digests and byte counts you gave **match `RELEASE_NOTES.md`
exactly** (`437ac5db…` / 483,467,899 and `2871c613…` / 460,106,909). The wheel
and sdist digests are in as given, abbreviated as you wrote them
(`a6203b78…`, `1c2eb6ba…`); my rehearsal build is a different artifact from
the one you will upload, so I did not compare them and the body should carry
your full digests before it is pasted.

**One decision the body cannot make for you.** The merged tree ships two
commands `RELEASE_NOTES.md` never mentions: `oneground lab` (task-020's local
read-only server) and `oneground propose` (028's tier-1 loop). The draft
mentions neither, matching the notes. If v0.1 is to announce them they need a
paragraph each and a line in *What works today*; if not, they ship present and
undocumented, which is defensible for `propose` — tier 1 is a machinery proof
— and less so for `lab`, which has `docs/LAB.md` and a teaser behind it.

## Observed, not done

1. **The 022-era summary line in §8**, which sums to eleven and is labelled
   seven.
2. **`RELEASE_NOTES.md` predates both merges.** Beyond the two unmentioned
   commands, its *What works today* block lists seven commands and the merged
   tree dispatches sixteen.
3. **Nothing was pushed except this report and the release body**, both to
   `task-028`. The rehearsal branch is deleted (`4212d41`, gone).

## Repo now contains

    tasks/RELEASE_BODY.md              the release text, for the 23rd
    tasks/release-rehearsal.report.md  this report
    tasks/scratch/merge-fix.patch      the §4 patch (untracked, .gitignore:62)

## Blocked on developer

1. **`task-020`'s two failing session tests** (§5) — the only thing between
   Monday and a green suite.
2. Whether to land the shape-tolerant `propose` shim on `task-028` now (§4) or
   apply the patch during the merge.
3. Whether v0.1 announces `lab` and `propose` (§9).
4. The full wheel and sdist digests for the release body.
