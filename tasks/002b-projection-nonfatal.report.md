# Report: 002b-projection-nonfatal

## Repo state expected vs found

The brief expected task 002 Part A committed and the working tree clean, and
said to stop and report if it was not clean.

| Expected | Found |
|---|---|
| 002 Part A committed | yes — `54956bc task 002 part A: newline pinning, projection declared, pod run script, POD_SETUP` |
| working tree clean | yes — the only entry in `git status` was the untracked brief itself, `tasks/tasks-002b-projection-nonfatal.md` |

Everything I flagged as "Blocked on developer" in the 002 report has been
resolved: 002 Part A is committed, and the four untracked 001b files went in
with it. A later commit, `40b8f07 tasks: normalise brief filenames`, renamed
the older briefs to the `tasks/NNN-name.md` convention. The 002b brief itself
still arrived as `tasks/tasks-002b-...`; I left it where it is and wrote this
report to `tasks/002b-projection-nonfatal.report.md`.

`logs/` and `.gitattributes`, the two optional items from the 002 report, were
not acted on and are not in this brief's scope.

## What was done

All six steps.

### 1. Reorder — receipts and MANIFEST before the projection

`main()` previously ran the projection between the reference results and the
`characterization.json` write, so a UMAP failure at hour three would have
aborted the process with every receipt on disk and no MANIFEST at all. The
projection block was moved to the end, after `characterization.json`,
`build_info.json` and `MANIFEST.sha256`.

Three helpers were added next to the existing digest helpers:

- `RECEIPT_ARTIFACTS` — the seven re-derivable artifacts, with `projection.npy`
  deliberately absent, since it does not exist when the manifest is written.
- `write_manifest(outdir, files)` — digests every listed file that exists,
  LF-pinned (as task 002 A1 established), returns the names written.
- `append_manifest(outdir, fn)` — appends a single LF-pinned digest line, for
  the projection specifically.

The manifest write now logs
`manifest written, 7 artifacts - fixture is verifiable from here`, so the log
itself marks the point past which nothing can be lost.

### 2. Projection made non-fatal

The projection step is wrapped in `try/except Exception`:

- **Success** — save `projection.npy`, append its digest to the manifest. No
  other file is touched, which is exactly why the brief asked for an append:
  `build_info.json` is already manifested and must not change.
- **Failure** — `traceback.print_exc()` to the build log, then the labelled
  line `PROJECTION FAILED - fixture is complete without it (after <elapsed>)`,
  then `"projection": "failed"` added to `build_info.json` and the file
  rewritten.

**The failure path has to reissue the manifest, and this is the one subtlety
in the task.** `build_info.json` is listed in a manifest written *before* the
projection runs. Rewriting it afterwards changes its digest, so the manifest
line would go stale and the verifier would report `build_info.json` as
**contradicted** — a projection failure would have corrupted verification by a
different route than the one the brief set out to close. So the failure branch
calls `write_manifest(...)` again after rewriting `build_info.json`. Step 6
confirms the digest matches; without the reissue that build would have failed
verification.

### 3. Elapsed-time logging

A `fmt_dur()` helper (seconds under 90 s, else `m:ss` or `h:mm:ss`) and timers
around both steps:

    [18:44:28] embedding done in 6m 27s (2,200 texts)
    [18:45:10] projection done in 39.5 s

The embedding timer spans both `embed()` calls (base documents and query
titles) and reports the combined text count.

### 4. Verifier

No change was needed: `verify_digests()` iterates the manifest entries, so it
already verifies exactly what the manifest lists and is indifferent to whether
`projection.npy` exists. Confirmed with a new test rather than asserted —
`test_verifies_with_and_without_projection_synthetic`, covering three cases:
listed and present (projection succeeded), not listed at all (projection
failed), and a stale `projection.npy` on disk that the manifest does not list,
which is reported as unlisted and does not fail verification. 8 tests pass.

### 5 and 6 — three builds

Three full smoke builds, each measured in-process (task 001 established that
probing across process boundaries on this machine reads the wrong process and
destabilises the run; the 002b brief requires in-process too):

1. with projection, into `fixtures/`
2. with a deliberately broken projection, into `tasks/scratch/002b-fail/`
3. with `--skip-projection`, into `fixtures/` — the final state

The failure was injected by a scratch script that imports
`corpora/build_fixture.py` unmodified and rebinds `bf.project` to a function
that raises. `main()` looks that symbol up as a module global, so the real
`try/except` and the real control flow are exercised. **No test hook was added
to the builder** — the brief allowed an env var the builder reads, but that
would have meant shipping a failure-injection path in production code for the
canonical build to carry.

### Deviations from a literal reading of the brief

- **`project()` returning `None` is also recorded.** The brief specifies the
  exception path. `project()` has a second non-exception failure mode: it
  returns `None` when umap-learn is not installed. With the reorder that would
  have left `projection.npy` absent and `build_info.json` silent about why, so
  that branch records `"projection": "unavailable"` and reissues the manifest
  the same way. It is a third status value the brief did not name.
- **A fourth build was run and discarded.** My first with-projection run was
  piped through `tail -30`, which truncated the `embedding done` line the
  brief requires. I re-ran it capturing the full log rather than report the
  number from a different build. Both runs are reported below, since together
  they say something about UMAP determinism.

No seed, tolerance, threshold, or measurement logic was changed. The builder
diff is 103 insertions / 21 deletions, confined to the imports, the three new
helpers, `fmt_dur`, the embedding timer, and the relocated projection block.

## Measurements

### Order of writes, from the build log

    [18:44:28] embedding done in 6m 27s (2,200 texts)
    [18:44:28] exact ground truth
    [18:44:29] characterize: TwoNN LID
    [18:44:29] characterize: k-means 256
    [18:44:29] characterize: drift pair (centroids trained pre-2019)
    [18:44:29] reference: single-node HNSW
    [18:44:30] reference: semantic-sharded
    [18:44:30] manifest written, 7 artifacts - fixture is verifiable from here
    [18:44:30] UMAP projection
    [18:45:10] projection done in 39.5 s

The manifest is written before the projection starts, and `projection.npy` is
the eighth and last line of the manifest, appended after `build_info.json`.

### Elapsed times — smoke run with projection

| Step | Elapsed | Method |
|---|---|---|
| embedding (2,200 texts) | **6m 27s** | `time.time()` around both `embed()` calls, logged by the builder |
| UMAP projection (2,000 x 768 → 2-D) | **39.5 s** | `time.time()` around the projection block, logged by the builder |
| whole build | **478.3 s (7.97 min)** | scratch runner, wall clock around `bf.main()` |
| peak RSS | **882 MB** | `GetProcessMemoryInfo(GetCurrentProcess())` after `main()` returns |

**This is the first time UMAP has run in this project.** Every previous build
used `--skip-projection`.

### All three builds

| Run | Mode | Wall clock | Peak RSS | Verifier |
|---|---|---|---|---|
| 1 | with projection | 478.3 s (7.97 min) | 882 MB | 8 verified (6 receipt, 2 declared), exit 0 |
| 2 | broken projection | 403.6 s (6.73 min) | 797 MB | 7 verified (6 receipt, 1 declared), exit 0 |
| 3 | `--skip-projection` | 478.9 s (7.98 min) | 699 MB | 7 verified (6 receipt, 1 declared), exit 0 |

Embedding elapsed varied across the three runs — 6m 27s, 6m 00s, 7m 22s — for
identical work. That spread is machine load, not the build.

**Peak RSS with projection exceeded the skip build by 183 MB** (882 vs 699).
I am not extrapolating that to 150k: the delta bundles UMAP's actual data
structures with numba's one-off JIT compilation, which is a fixed cost, and
two runs cannot separate them. What it does say is that UMAP is the only step
whose memory profile is still unmeasured at scale, which is why POD_SETUP.md's
memory guard exists.

### UMAP was bit-identical across two runs

The discarded first with-projection run and the reported one both produced
`projection.npy` hashing to

    adba41731040b549d0726fa76d9b9a6a03e417348c951f28e4db177f096bcf7f

So the seeded UMAP is reproducible run-to-run on this machine. That does **not**
justify reclassifying it as a receipt: the reason it is `declared` (task 002
A2) is that it is not guaranteed bit-identical across *BLAS builds*, and both
these runs used the same BLAS on the same CPU. Two samples on one machine
cannot speak to that.

### Failure path — evidence

Injected failure, from the log:

    [18:52:21] manifest written, 7 artifacts - fixture is verifiable from here
    [18:52:21] UMAP projection
    Traceback (most recent call last):
        raise RuntimeError(
    RuntimeError: simulated UMAP failure (task 002b failure-path test); stands
    in for an OOM / numba / pynndescent fault at 150k scale
    PROJECTION FAILED - fixture is complete without it (after 0.0 s)

The build ran to completion, exit code 0, and printed its `TO_BE_FILLED` block
as normal.

Artifacts on disk — seven, no `projection.npy`:

    MANIFEST.sha256  build_info.json  characterization.json  ground_truth.npy
    queries.npy      query_ids.json   sample.jsonl.zst       vectors.npy

`MANIFEST.sha256` covers every receipt artifact:

    b6383e226a14e631a2e5c875cd658230c194ebe5ac908abea6ea5e52d1fa4c6c  sample.jsonl.zst
    d9f44ded9e68af7495544c9a90da5bfee3798204f77ce0efbd219508268d7a6e  vectors.npy
    2359ce716b2ca7ef75c5d9f4fa4a42924df83eeac5848918b6a823efa7f7433a  queries.npy
    0081604bb50d8dd48b4ae5605a05fc894dcd2ae4db41511657464772c911b8e2  query_ids.json
    13919bb5174ebeb4febe037017a2e2b8bbfe4998b3ce261e7989e4649c2a9cce  ground_truth.npy
    07b576e27e680596d8cb52c59f01dcb18e1039a9be135c48db921e5a56dc30e1  characterization.json
    34c073cc6ea81ac1cfa1298b5c21ac5b0b3cb265b170ea032ed9c44836d3dd96  build_info.json

The first six digests are identical to the successful build — a failed
projection changed nothing upstream of it.

`build_info.json` records the failure:

    {
      "built_at": "2026-09-08T16:52:21Z",
      "device": "cpu",
      "library_versions": {
        "faiss-cpu": "1.15.0",
        "numpy": "2.5.3",
        "sentence-transformers": "6.0.1",
        "umap-learn": "0.5.12"
      },
      "platform": "Windows-11-10.0.26200-SP0",
      "projection": "failed",
      "python_version": "3.12.10",
      "source_snapshot_sha256": "cc5fc2ef52d68240c4d03b278b10ef174040f41a146062a8395f0581d39ae2a1"
    }

Verifier on that fixture — note `build_info.json`'s digest matches
`34c073cc...` above, i.e. the reissued manifest tracks the rewritten file:

    digests
      verified      receipt  sample.jsonl.zst       b6383e226a14e631a2e5c875cd658230c194ebe5ac908abea6ea5e52d1fa4c6c
      verified      receipt  vectors.npy            d9f44ded9e68af7495544c9a90da5bfee3798204f77ce0efbd219508268d7a6e
      verified      receipt  queries.npy            2359ce716b2ca7ef75c5d9f4fa4a42924df83eeac5848918b6a823efa7f7433a
      verified      receipt  query_ids.json         0081604bb50d8dd48b4ae5605a05fc894dcd2ae4db41511657464772c911b8e2
      verified      receipt  ground_truth.npy       13919bb5174ebeb4febe037017a2e2b8bbfe4998b3ce261e7989e4649c2a9cce
      verified      receipt  characterization.json  07b576e27e680596d8cb52c59f01dcb18e1039a9be135c48db921e5a56dc30e1
      verified      declared build_info.json        34c073cc6ea81ac1cfa1298b5c21ac5b0b3cb265b170ea032ed9c44836d3dd96

    values
      couldnt_check characterization and reference_results (value reproduction not implemented)

    summary: 7 verified, 0 contradicted, 0 couldnt_check  (digests only; 6 receipt, 1 declared)

Exit code 0.

### Verifier on the final (skip-projection) fixture

    summary: 7 verified, 0 contradicted, 0 couldnt_check  (digests only; 6 receipt, 1 declared)

Exit code 0. And on the with-projection build, `projection.npy` verified as
`declared`:

    verified      declared projection.npy         adba41731040b549d0726fa76d9b9a6a03e417348c951f28e4db177f096bcf7f

    summary: 8 verified, 0 contradicted, 0 couldnt_check  (digests only; 6 receipt, 2 declared)

### Receipts unchanged

`git status` after all three builds lists `MANIFEST.sha256` and
`build_info.json` as modified and **`characterization.json` as unmodified**.
The two changes are one line each:

    -9040b9e6c72a0d2fc09dbb051856e6eea994a813bec823c12906c8a7512258ae  build_info.json
    +6554b1710ae7940d7069661e624b76434cc38af03bd680deaa7e65ab7897ed42  build_info.json
    -  "built_at": "2026-09-08T16:14:14Z",
    +  "built_at": "2026-09-08T17:01:05Z",

That is the timestamp and its digest, nothing else. All five binary receipt
digests are unchanged from task 001.

### Line endings (002 regression check)

    CRLF in text artifacts: 0

`write_manifest()` and `append_manifest()` both pin `newline="\n"`, so the
appended projection line does not reintroduce the CRLF that task 002 removed.

### Tests

`python oneground/test_fixture_verify.py` — 8 passed:

    test_declared_file_is_still_digest_checked_synthetic
    test_exit_codes_synthetic
    test_kind_split_synthetic
    test_malformed_manifest_raises_synthetic
    test_projection_is_declared_but_still_digest_checked_synthetic
    test_three_outcomes_stay_distinct_synthetic
    test_unlisted_files_are_reported_synthetic
    test_verifies_with_and_without_projection_synthetic   <- new

## Verification

**Passed** — every acceptance criterion:

- **Order of writes**: receipts and MANIFEST first, projection last and
  appended. Shown by the build log and by `projection.npy` being the eighth
  and final manifest line.
- **A projection failure yields a complete, verifiable fixture minus
  `projection.npy`, with the failure recorded in `build_info.json`**: seven
  artifacts, seven manifest lines, `"projection": "failed"`, verifier 7
  verified / 0 contradicted, exit 0.
- **Smoke build with projection ran to completion**; wall clock 478.3 s and
  peak RSS 882 MB reported, with embedding at 6m 27s and projection at 39.5 s.
- **No seed, tolerance, threshold or measurement logic changed**: all five
  binary receipt digests and `characterization.json` are byte-identical to
  what task 001/001b produced.

Also checked: the verifier passes on all three builds; 8 tests pass; zero CRLF
in the text artifacts; the file is still parseable and the diff is confined to
the areas listed above.

**Failed**

Nothing.

**Couldn't check**

- **Whether UMAP actually survives 150,000 x 768.** This task makes its
  failure survivable; it does not make it less likely. The projection ran on
  2,000 vectors, three orders of magnitude below the canonical build, and
  neither its runtime nor its memory extrapolates cleanly (the 183 MB delta
  includes numba's fixed JIT cost).
- **Whether UMAP is bit-identical across BLAS builds.** Two runs on one
  machine produced the same digest; that is one data point about one BLAS, not
  evidence about the pod. `declared` remains the right classification.
- **The real failure modes.** The injected failure is a `RuntimeError` raised
  synchronously inside `project()`. A true OOM kill (SIGKILL) is *not* catchable
  by `try/except` — see below.
- **Value reproduction**, unchanged from 001b: still not implemented, still
  reported as `couldnt_check`.

## Observed, not done

- **An OOM kill would still lose the projection but not the receipts — which
  is now the point.** `try/except Exception` catches a Python-level exception,
  including `MemoryError`, but not the OS killing the process. With the
  reorder this no longer matters for the receipts: if the kernel kills the
  build during UMAP, `characterization.json`, `build_info.json` and
  `MANIFEST.sha256` are already on disk and the fixture verifies. What is lost
  is the `TO_BE_FILLED` block, which prints after the projection step. Moving
  that print before the projection would make the run survivable end-to-end.
  I did not move it — the brief specifies the order of the *writes*, and the
  values are also recoverable from `characterization.json`.
- **A stale `projection.npy` is left in place after a failed projection.** If a
  directory is rebuilt in-place and the new projection fails, the previous
  run's `projection.npy` stays on disk, unmanifested. The verifier reports it
  as "present but not listed in the manifest" and still passes, which is the
  safe outcome, and there is now a test for it. Removing it in the builder
  would mean deleting data, which needs an explicit instruction.
- **`RECEIPT_ARTIFACTS` and `oneground/fixture_verify.py`'s `DECLARED_FILES`
  are two independent lists of the same artifact set.** They agree today. A
  future artifact added to the builder and not to the verifier would be
  classified `receipt` silently. A shared definition would remove the risk.
- **`build_info.json` has no `"projection": "ok"` on success.** Deliberate —
  writing one would change the file after it was manifested, forcing a
  manifest reissue on the *success* path too, for no gain. It does mean the
  key's absence is what signals success.
- **The elapsed times are logged but not recorded in `build_info.json`.** The
  brief asked for the log. For the canonical build, having embedding and
  projection durations in the declared file would make them reviewable without
  the log; `build_info.json` is declared, so adding them is free.
- **`logs/` still not in `.gitignore`**, and no `.gitattributes` — both carried
  over from the 002 report, neither in this brief's scope.

## Repo now contains

Modified:

    corpora/build_fixture.py               (+103 / -21: traceback import, fmt_dur,
                                            MANIFEST_NAME, RECEIPT_ARTIFACTS,
                                            write_manifest, append_manifest,
                                            embedding timer, relocated and
                                            guarded projection block)
    oneground/test_fixture_verify.py       (+35: with/without-projection test)
    fixtures/arxiv-smoke/MANIFEST.sha256   (rebuilt; 1 line differs — build_info digest)
    fixtures/arxiv-smoke/build_info.json   (rebuilt; 1 line differs — built_at)

New:

    tasks/scratch/002b-projection-nonfatal-build.py
    tasks/002b-projection-nonfatal.report.md

Unmodified despite three rebuilds: `fixtures/arxiv-smoke/characterization.json`,
and the gitignored `vectors.npy`, `queries.npy`, `query_ids.json`,
`ground_truth.npy`, `sample.jsonl.zst`.

Removed after its evidence was recorded: `tasks/scratch/002b-fail/`, the
failure-path build output. It was a 6.9 MB duplicate fixture, and
`.gitignore`'s patterns are scoped to `fixtures/*/` so it would not have been
excluded. Its manifest, `build_info.json` and verifier output are quoted in
full above.

The final `fixtures/arxiv-smoke/` is the `--skip-projection` build, matching
the state task 002 left: seven artifacts, no `projection.npy`.

### Dependencies added

None. `requirements.txt` unchanged.

### Not committed

Nothing was committed. The same warning as the 002 report applies: the pod
gets its repo from `git bundle create oneground.bundle --all`, which carries
commits and not the working tree, so this task's changes must be committed
before the bundle is made.

## Blocked on developer

Nothing blocked this task.

Unchanged from the 002 report, for Part B: commit before bundling, Kaggle
credentials, and a RunPod CPU pod. The projection-related item that was open
in that report — whether `projection.npy` should be `declared` — was settled by
task 002 A2 and is now covered by a test.

---

## Addendum — TO_BE_FILLED block moved before the projection

Follow-up instruction, after the report above was written: move the
`TO_BE_FILLED` print block in `corpora/build_fixture.py` to immediately after
the manifest write and before the projection step, so a kill during UMAP
cannot lose it. This closes the first item under "Observed, not done".

### What changed

The block (header plus every value line) now sits between the manifest write
and the projection, with a comment recording why. Every value it prints is
derived from artifacts already on disk at that point — `src_sha`,
`sample_path`, `weights_sha`, `versions`, `base`, `queries`, `gt`, `ch`,
`ref_single`, `ref_sem` are all in scope before the projection runs — so
nothing had to be recomputed or reordered to make the move.

**One line was deliberately left at the end**: `artifacts written to <dir>
(N min)`. Moving it too would have made its elapsed figure exclude the
projection, understating a canonical build that the developer pastes upstream.
The values are what a kill must not destroy; the total-time summary is not,
and it is more useful where it is. `print(flush=True)` closes the block so the
values are flushed before UMAP begins rather than sitting in a buffer.

No other change: no seed, tolerance, threshold, or measurement logic touched.

### Rebuild with SKIP_PROJECTION=1

Run via `corpora/run_arxiv_150k.sh` with the smoke spec, so the verifier ran in
the same invocation. Script exit code 0, reached `DONE`.

Log order, with line numbers from the run log — manifest, then the values, then
the projection step:

    39:[19:20:58] manifest written, 7 artifacts - fixture is verifiable from here
    41:================ TO_BE_FILLED values ================
    42:source.snapshot_sha256:               cc5fc2ef52d68240c4d03b278b10ef174040f41a146062a8395f0581d39ae2a1
    43:sampling.sample_sha256:               b6383e226a14e631a2e5c875cd658230c194ebe5ac908abea6ea5e52d1fa4c6c
    44:embedding.weights_sha256:             c7c1988aae201f80cf91a5dbbd5866409503b89dcaba877ca6dba7dd0a5167d7
    45:embedding.library_version:            6.0.1
    46:embedding.vectors_sha256:             d7bbda6af7496e4c911e603baf78c921964e0cf81eeb2ff03f070414902023ca
    47:queries.queries_sha256:               a3ea6e53d3b11ca220353ac8f9f6277e4e9c28f868fbea55861ab6b9e360ff0d
    48:ground_truth.ground_truth_sha256:     7975fc6162d0fad61c89905b5a43d85e6243f800b6ce9adebee4b2385f39d584
    49:characterization.intrinsic_dimensionality.value: 22.06
    50:characterization.boundary_crispness.value:       0.529
    51:characterization.ambiguous_query_rate.value:     0.935
    52:characterization.skew_top10_share.value:         0.100
    53:characterization.drift.value_before:             0.291  (n=85)
    54:characterization.drift.value_after:              0.277  (n=115)
    55:reference_results.single_node_hnsw.recall_at_10: 1.000
    56:reference_results.semantic_sharded.recall_at_10: 0.634
    57:reference_results.semantic_sharded.routing_ceiling: 0.634
    58:reference_results.semantic_sharded.storage_amplification: 1.906
    59:reference_results.semantic_sharded.p50_copies: 1
    60:reference_results.semantic_sharded.p95_copies: 4
    61:reference_results.semantic_sharded.p99_copies_per_vector: 4
    63:[19:20:58] projection skipped (--skip-projection)
    65:artifacts written to fixtures/arxiv-smoke   (12.0 min)

The complete block is printed before line 63. On the canonical build, line 63
is where UMAP starts; a SIGKILL there now costs the projection and the
`artifacts written` summary, and nothing else.

Verifier, same invocation:

    fixture: arxiv-smoke
    directory: fixtures\arxiv-smoke
    manifest: MANIFEST.sha256 (7 files listed)

    digests
      verified      receipt  sample.jsonl.zst       b6383e226a14e631a2e5c875cd658230c194ebe5ac908abea6ea5e52d1fa4c6c
      verified      receipt  vectors.npy            d9f44ded9e68af7495544c9a90da5bfee3798204f77ce0efbd219508268d7a6e
      verified      receipt  queries.npy            2359ce716b2ca7ef75c5d9f4fa4a42924df83eeac5848918b6a823efa7f7433a
      verified      receipt  query_ids.json         0081604bb50d8dd48b4ae5605a05fc894dcd2ae4db41511657464772c911b8e2
      verified      receipt  ground_truth.npy       13919bb5174ebeb4febe037017a2e2b8bbfe4998b3ce261e7989e4649c2a9cce
      verified      receipt  characterization.json  07b576e27e680596d8cb52c59f01dcb18e1039a9be135c48db921e5a56dc30e1
      verified      declared build_info.json        8c50b8be49735f193655a4525ba2ea09569f8586ec878b4b5d11774d9d5f3e85

    values
      couldnt_check characterization and reference_results (value reproduction not implemented)

    summary: 7 verified, 0 contradicted, 0 couldnt_check  (digests only; 6 receipt, 1 declared)

Exit code 0.

### Measurements

Embedding took 11m 02s in this run, against 6m 00s to 7m 22s in the three runs
above, for identical work — machine load, not the build. Total 12.0 min by the
builder's own figure.

The six receipt digests are unchanged from every build in this report and from
task 001. `build_info.json` differs in `built_at` only, as always.

### Repo now contains

Modified beyond the report above:

    corpora/build_fixture.py               (TO_BE_FILLED block relocated;
                                            +21 / -19, no logic change)
    fixtures/arxiv-smoke/MANIFEST.sha256   (rebuilt; build_info digest line)
    fixtures/arxiv-smoke/build_info.json   (rebuilt; built_at)

`characterization.json` unchanged. Nothing committed.
