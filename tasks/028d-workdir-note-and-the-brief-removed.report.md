# Report: 028d-workdir-note-and-the-brief-removed

Two items, both housekeeping with a receipt: annotate the workdir instead of
re-sweeping it, and get the 029 brief off this branch before it is revised.

## Repo state expected vs found

On `task-028` at `af0ace6`: found. `main` untouched at `570f07d`.

`task-029` has moved on since 028c saw it — its tip is `82b0b36`, after
`149ddda` "SIMD dispatch disproved, and the divergence reproduced locally".
Nothing on this branch depends on it and I have not read it; it is named here
only because it is the branch the removed file belongs to.

Three untracked briefs are in the working tree —
`tasks/020-simulator-state.md`, `tasks/030-sec-filings-fixture.md`,
`tasks/031-chunking-stage.md`. None was staged; only the four paths under
*Repo now contains* were.

## What was done

### 1. The workdir says what built its sharded rows. No re-sweep.

`runs/arxiv-150k-via-characterize/simulate_info.json` gains one key,
`sharded_rows_predate_deterministic_build`, written by
`tasks/scratch/028d-annotate-workdir.py` through `receipts.write_json_stable`.
It records:

* **which rows**: every `semantic_sharded` and `hash_sharded` row in
  `simulate.json`; `single_node_hnsw` is not affected, that family having
  been building single-threaded already;
* **what happened**: this run measured with a multi-threaded HNSW build,
  `dc85609` (task 015) put both sharded families under one thread, and its
  author date is a day after this run's `run_at`;
* **how that was established**: 028c's three-revision measurement, including
  the reading that does not depend on a commit date — today's build returns
  `recall_at_1` 0.874 deterministically and this run recorded 0.875;
* **the effect size**, three ways: 691 of 20,000 ids over one shard (3.455%,
  max score difference 0.068346) under four threads and none under one;
  `recall_at_1` 0.8745 against 0.875 and `recall_at_10` 0.83775 against
  0.83785 between two pre-015 runs of a whole configuration; and routing
  identical throughout;
* **what it is not**: nothing outside a published tolerance — those are 0.01
  on recall and 0.02 on the ratios against differences of 1e-5 to 1e-3 — and
  no verdict in any report or card moves;
* **what was not done**: no re-sweep and no value changed, with the
  statement that the decision is the developer's.

**`simulate.json` was not touched.** Its digest is `e084bb68a4d3…` before and
after. `MANIFEST.sha256` was rewritten through `receipts.write_manifest` over
the same six files, because the annotation changes `simulate_info.json`'s
digest and a workdir whose manifest disagrees with its bytes is worse than one
carrying an unannotated file.

`runs/` is `.gitignore` line 34, so **none of this is in the commit**: it is a
change to a local artifact, and this report is the tracked record of it.

### 2. `tasks/029-kmeans-determinism.md` removed from this branch

`git rm`. The file stays where it belongs, on `task-029`, which is also where
it is about to be revised. Two branches carrying one path merge cleanly only
while the copies agree, and they were about to stop agreeing.

The cross-reference in 028's report is now prose — *"the brief, which lives on
the `task-029` branch, not this one"* — rather than a path, so nothing on this
branch points at a file this branch no longer has. 028c's *Observed, not done*
item 3, which raised the duplicate, is marked closed by this task.

## Measurements

| | before | after |
|---|---|---|
| `simulate.json` sha256 | `e084bb68a4d3…` | `e084bb68a4d3…` (unchanged) |
| `simulate_info.json` sha256 | `da041af26976…` | `490eb7d3bf90…` (annotated) |
| `MANIFEST.sha256` | 6 files | 6 files, rewritten |

**Every citation still verifies.** The two proposal cards cite
`simulate.json` by file digest and their baseline rows by row digest; both
were recomputed after the annotation, for both cards:

    semantic_sharded_epsilon-0.1-to-0.2   file digest True | row digest True
    semantic_sharded_probe-1-to-2         file digest True | row digest True

`oneground propose … --dry-run` against the annotated workdir runs every
precondition — corpus digests, seed, baseline row, pinned libraries — and
prints the same plan as before, citing `simulate.json sha256 e084bb68a4d3…,
row b95f9f1e3cc5…`.

The two copies of the 029 brief were byte-identical at the moment of removal
(`git diff 7c13582:… task-029:…` empty), so nothing was lost by deleting one.

## Verification

* The annotation is in the declared half of the pair, names its own author
  and task, and is distinguishable from what the run measured: it is one
  top-level key holding prose and numbers, beside fields the run wrote.
* No measured value, no digest cited by anything, and no card changed.
* The manifest agrees with the bytes.
* The brief is gone from `task-028` and present on `task-029`.
* Couldn't check: **whether a later `simulate` run into this workdir would
  preserve the annotation.** It would not — `simulate.run` writes
  `simulate_info.json` from scratch. A re-sweep therefore removes this note as
  well as the condition it describes, which is consistent but worth knowing
  before one is run.
* Couldn't check: nothing else. This task measured nothing new.

## Observed, not done

1. **The annotation is a workdir convention with one instance.** Nothing in
   the code writes or reads `sharded_rows_predate_deterministic_build`, and
   no other workdir has one. If this kind of note is worth having generally —
   a run recording, after the fact, that something about how it was produced
   is now known — it wants a named field and a writer, not a key invented by
   a report. Not proposed here; it is a design question.
2. **`simulate_info.json` still records no oneground version**, which is why
   this annotation had to be written by hand from a measurement rather than
   read off the run. Third time it has cost something; 028's *Observed, not
   done* item 3 has the detail.

## Repo now contains

    tasks/029-kmeans-determinism.md                             removed (it is on task-029)
    tasks/028-proposals-tier1.report.md                         the 029 reference is prose, not a path
    tasks/028c-third-measurement-and-the-stale-comment.report.md   Observed item 3 closed
    tasks/028d-workdir-note-and-the-brief-removed.report.md     this report
    tasks/scratch/028d-annotate-workdir.py                      the annotation (untracked, .gitignore:62)

Not in the commit, and deliberately: the annotated
`runs/arxiv-150k-via-characterize/simulate_info.json` and its rewritten
`MANIFEST.sha256`, under `.gitignore` line 34.

## Blocked on developer

Nothing.
