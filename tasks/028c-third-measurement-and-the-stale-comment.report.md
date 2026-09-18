# Report: 028c-third-measurement-and-the-stale-comment

Three items: the measurement skipped in 028b, the stale comment 029's brief
quoted, and a note in 028's report about what the cards' baselines were built
by.

**The pre-015 explanation holds, and it is now established rather than
consistent-with:** today's build produces a row the 2026-09-09 sweep does not
contain, deterministically, twice; the pre-015 build produces the sweep's row,
and produces a different one when run again.

## Repo state expected vs found

On `task-028` at `27683f7`: found. `main` untouched at `570f07d`.

Two corrections to what 028b's *Repo state* said, both because the developer
moved things while it was being written:

* 028b said the 029 brief was on `main` as the cherry-pick `e2c9a01`. **It is
  not.** `main` is back at `570f07d`, frozen and without it; the brief is on a
  new `task-029` at `e610275`, branched from `570f07d`, and `e2c9a01` is
  dangling with no branch pointing at it. Corrected in 028b's own text as
  well as here.
* `task-028` still carries its copy, `7c13582`. That file is byte-identical to
  `e610275`'s, so two branches add the same content and a later merge of both
  will do it twice.

`oneground-v2`, the second worktree, is now on `task-029`. Nothing in this
report touches it.

## What was done

### 1. The third measurement

One sharded configuration —
`semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=1]`, the
one card B measured — measured at three revisions in `git worktree`
checkouts, each importing its own tree's `oneground`:

| revision | what it is |
|---|---|
| `1fe8e26` | task 026c, the commit `task-028` branched from, post-015 |
| `570f07d` (`main`) | `1fe8e26` plus 022e/022f and two briefs; post-015 |
| `8056afb` (`dc85609^`) | the commit before task 015 converted the sharded builds; **pre-015** |

`tasks/scratch/028c-revision-measure.py` does not call
`simulate.measure_config`: that function injects a run-level `shard_depth`
whose rule changed across these revisions, and the sweep ran under the
family's own default. It calls `build`/`search`/`ceiling`/`footprint`
directly with no `shard_depth` in the config, on the workdir's own sample,
queries and cached ground truth, and it leaves the thread count alone — which
is the entire point, since a pre-015 tree builds shards multi-threaded and a
post-015 tree pins them to one thread.

The pre-015 revision was measured **twice**, because a nondeterministic build
has a spread and the spread is the number that decides this.

### 2. The stale comment

`oneground/models/base.py:52-53` said `hash_sharded` and `semantic_sharded`
"have not been converted; they take the same helper when someone does."
`dc85609` converted both a week earlier. Replaced with what is true, citing
the commit, plus a per-family statement of what `deterministic=True`
guarantees — each line of it measured, in tasks 012, 015 and 028b — and what
it does not: the cross-environment case, which is open and is 029's. The
paragraph also records that the sentence outlived what it described and that
a task brief then quoted it as a recorded gap.

### 3. The note in 028's report

`tasks/028-proposals-tier1.report.md`, *Observed, not done*, gains item 7:
the sharded rows in `runs/arxiv-150k-via-characterize/simulate.json` were
measured by the pre-015 build and are the baselines both cards cite by digest;
they are inside every tolerance and no verdict moves; a re-sweep would remove
that difference from future cards' deltas; **the re-sweep was not run and the
decision is the developer's.**

## Measurements

Same machine, `.venv\Scripts\python.exe`, numpy 2.5.3, faiss-cpu 1.15.0,
faiss default threads 4. Same sample, queries and cached ground truth for
every row.

| measured by | `recall_at_1` | `recall_at_10` | `recall_at_100` | `ceiling_at_10` | `storage_amplification` | build s |
|---|---|---|---|---|---|---|
| the sweep, 2026-09-09 | **0.875** | 0.83785 | 0.29780 | 0.8382 | 3.71516 | 375.8 |
| `1fe8e26`, post-015 | **0.874** | 0.83785 | 0.297795 | 0.8382 | 3.71516 | 531.0 |
| `main` `570f07d`, post-015 | **0.874** | 0.83785 | 0.297795 | 0.8382 | 3.71516 | 297.0 |
| `8056afb`, pre-015, run 1 | **0.8745** | 0.83775 | 0.297815 | 0.8382 | 3.71516 | 127.6 |
| `8056afb`, pre-015, run 2 | **0.875** | 0.83785 | 0.29779 | 0.8382 | 3.71516 | 127.7 |

Both post-015 trees record `deterministic: True` in the built state; the
pre-015 tree records nothing, the field not existing yet.

Four readings, in the order that matters:

1. **The two post-015 revisions agree exactly**, on every field. Whatever
   changed between `1fe8e26` and `main` — the identifier scan, the script
   runner, two briefs — does not touch a measured number, and neither does
   anything in `task-028` (this script bypasses the one function 028
   changed). So "the code moved between the sweep and today" is now a claim
   about one specific commit rather than about nine days of commits.
2. **The pre-015 revision disagrees with itself.** Two runs, same tree, same
   seed, same inputs, minutes apart: `recall_at_1` 0.8745 against 0.875,
   `recall_at_10` 0.83775 against 0.83785, `recall_at_100` 0.297815 against
   0.29779. That is the multi-threaded build's own run-to-run spread, at the
   level of a whole configuration rather than one shard, and it is the same
   size as the difference 028 reported between the sweep and today.
3. **The sweep's row is one of the pre-015 draws.** Run 2 reproduces it
   exactly on `recall_at_1` (0.875) and `recall_at_10` (0.83785), and to
   1e-5 on `recall_at_100`.
4. **Today's build cannot produce the sweep's row.** Post-015 gives
   `recall_at_1` 0.874, twice, deterministically — 028b showed the same build
   under one thread is bit-identical run to run. The sweep says 0.875. A
   deterministic process that always answers 0.874 did not produce 0.875,
   so the sweep was not produced by post-015 code.

Reading 4 is what makes this established rather than consistent-with, and it
is the reading the author date could not give: it does not depend on when
`dc85609` was written, only on what the two builds do.

**The routing is identical in all five rows** — `ceiling_at_10` 0.8382 and
`storage_amplification` 3.71516 everywhere, including the sweep. Across two
code revisions, two thread regimes and nine days, the k-means and its closure
have not moved on this machine. That is the third independent confirmation,
after 028's row comparison and 028b's centroid comparison.

**Cost, incidentally measured:** the pre-015 multi-threaded builds took 127.6
and 127.7 s; the post-015 single-threaded ones 531.0 and 297.0 s on a machine
that was doing other things, against the sweep's own 375.8 s. The spread
among the single-threaded runs is background load, not a property of the
build, so this bounds the determinism penalty loosely — somewhere above 2× on
this configuration — and 029's step 5 is where it gets measured properly.

## Verification

* **Does the pre-015 baseline explanation hold?** Yes, on readings 2, 3 and 4
  together. The only remaining way for it to be false is for the 2026-09-09
  run to have used some *other* code that also produces 0.875 — which is not
  excluded by anything here, and is not a hypothesis anyone has offered.
* **`base.py` corrected**: the comment now cites `dc85609`, states what
  `deterministic=True` guarantees for each of the three families with the task
  that measured each claim, and says plainly that the cross-environment case
  is open. `python -m pytest oneground/models -q` → **39 passed**.
* **028's report carries the baseline note**, in *Observed, not done*, saying
  the re-sweep is the developer's decision and was not run.
* Couldn't check: **what the pre-015 spread is over more than two runs.** Two
  draws bracket the sweep's row; they do not give a distribution. Five runs
  would, and 029's step 5 asks for five at each size for the cost measurement
  anyway.
* Couldn't check, still: **the cross-environment case.** Everything here is
  one machine.

## Observed, not done

1. **The `simulate_info.json` gap is now twice-demonstrated.** Both 028 and
   028c had to reason about which code produced a row from commit dates and
   from the numbers themselves, because a run records its library versions and
   not its own version. 028's *Observed, not done* item 3 already names it;
   this is the second time it cost a measurement to work around.
2. **`hash_sharded` was converted by the same commit and is not separately
   measured.** The new `base.py` text says so rather than implying it was
   tested. One shard of it, built twice, would close that — 028b's script
   would need a few lines.
3. **Two branches now add the same 029 brief file.** `7c13582` on `task-028`
   and `e610275` on `task-029`. Identical today; if either is edited before
   both merge, the merge conflicts.

## Repo now contains

    oneground/models/base.py                                    the Determinism section, corrected and per-family
    tasks/028-proposals-tier1.report.md                         Observed item 7: what the cards' baselines were built by
    tasks/028b-determinism-measurements.report.md               the 029-brief location corrected
    tasks/028c-third-measurement-and-the-stale-comment.report.md   this report
    tasks/scratch/028c-revision-measure.py                      the measurement (untracked, .gitignore:62)

## Blocked on developer

Nothing. The re-sweep of `runs/arxiv-150k-via-characterize` is yours to
decide and was not run.
