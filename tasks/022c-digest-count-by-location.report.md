# Report: 022c-digest-count-by-location

## Repo state expected vs found

`main` at `13e32f0` (022b), clean apart from `tasks/020-simulator-state.md`:
found. `v0.1.0` on `383c7a1`, not moved.

## What was done

`docs/EXTERNAL_RUN.md`, under *What a successful run prints*, gains one
paragraph. The verified-digest count depends on where the command runs. For
`arxiv-smoke`, a clone verifies eight of the eleven listed files and a bare
wheel install verifies four, because `queries.npy` and the three ground-view
tables are in the repository and not in the package. The paragraph says
neither result is a failure, and that each couldn't-check line gives the
reason its file is absent. The purpose: a reader running the wheel should
expect a different number from an instruction printed from a clone, not be
alarmed by it.

**One wording departure from the brief, stated.** The brief said the output
"names which" in both cases. The runs below show that it names a reason for
every absent file, but not in every case that the repository carries it. From
the wheel, the three ground-view tables say "not shipped with the installed
package; the repository carries it", while `queries.npy` says "not present,
and no release asset is published for this fixture; building it produces this
file". That is true, but it does not say the repository has it. The paragraph
therefore says what every line does say ("each couldn't-check line gives the
reason that file is absent"), not more.

## Measurements

Both counts observed on `13e32f0`, before the paragraph was written:

- **From a clone:** a fresh `git clone` of the local repository at `13e32f0`,
  so no gitignored files, running the clone's own code with
  `python -m oneground.cli`.
- **From a bare wheel:** from an empty directory, with the venv that 022b's
  PowerShell proof installed from the built wheel. `USERPROFILE` points at an
  empty directory in both runs.

**From a clone:** 8 verified, 3 couldn't-check, exit 0.

```
cwd: a fresh clone of 13e32f0 (git clone of the local repository; no gitignored files)
$ python -m oneground.cli fixture verify arxiv-smoke    # the clone's own code
python  <repo>\.venv\Scripts\python.exe  (venv)
fixture: arxiv-smoke
directory: <scratch>\022c2\clone\fixtures\arxiv-smoke
manifest: MANIFEST.sha256 (11 files listed)

preconditions
  fixture      found      <scratch>\022c2\clone\fixtures\arxiv-smoke  (the current directory)
  environment  pinned     numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0
                          (pins from <scratch>\022c2\clone\requirements.txt)
                          in a virtual environment
  asset        not needed the spec publishes no values yet, so no asset is read

digests
  couldnt_check receipt  sample.jsonl.zst               not present, and no release asset is published for this fixture; building it produces this file; looked in <scratch>\022c2\clone\fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke
  couldnt_check receipt  vectors.npy                    not present, and no release asset is published for this fixture; building it produces this file; looked in <scratch>\022c2\clone\fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke
  verified      receipt  queries.npy                    2359ce716b2ca7ef75c5d9f4fa4a42924df83eeac5848918b6a823efa7f7433a
  verified      receipt  query_ids.json                 0081604bb50d8dd48b4ae5605a05fc894dcd2ae4db41511657464772c911b8e2
  verified      receipt  ground_truth.npy               13919bb5174ebeb4febe037017a2e2b8bbfe4998b3ce261e7989e4649c2a9cce
  verified      receipt  characterization.json          07b576e27e680596d8cb52c59f01dcb18e1039a9be135c48db921e5a56dc30e1
  verified      declared build_info.json                fa6168a52acb45283a51f73554e3683dd24abde014e0b82a4091e0e3ebb944c1
  couldnt_check declared projection.npy                 artifact not present (release asset, or not built); looked in <scratch>\022c2\clone\fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke
  verified      declared ground_view_base.parquet       23ee242d845034ed91c01f3dd6f57817d3b5d426ce3b2b1502a61fb10c2cf948
  verified      declared ground_view_queries.parquet    32a562466ccb29932742d3c146892b7f9f420676ce91dfe8219c320ac70ef6c6
  verified      declared ground_view_centroids.parquet  b9655c45a31bd2fde2440bb05d5764d6c4611767bfa39015e64c6352beeea496

values
  couldnt_check intrinsic_dimensionality                the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check boundary_crispness                      the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check skew_top10_share                        the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check ambiguous_query_rate                    the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check single_node_hnsw.recall_at_10           the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check semantic_sharded.recall_at_10           the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check semantic_sharded.storage_amplification  the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check drift                                   the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.

summary: digests 8 verified, 0 contradicted, 3 couldnt_check (6 receipt, 5 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check

         3 listed files are not present here, so their bytes were not checked:
         sample.jsonl.zst, vectors.npy and projection.npy.
         No value is published in the spec yet, so there was nothing to
         reproduce (8 placeholders).
[exit 0]
```

**From a bare wheel install:** 4 verified, 7 couldn't-check, exit 0.

```
cwd: an empty directory, not a checkout
$ oneground fixture verify arxiv-smoke    # a venv with the wheel installed
python  <scratch>\022b\ps\.venv\Scripts\python.exe  (venv)
fixture: arxiv-smoke
directory: <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-smoke
manifest: MANIFEST.sha256 (11 files listed)

preconditions
  fixture      found      <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-smoke  (the installed package)
                          not in <scratch>\022c2\empty\fixtures (the current directory)
  environment  pinned     numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0
                          (pins from the installed oneground 0.1.0)
                          in a virtual environment
  asset        not needed the spec publishes no values yet, so no asset is read

digests
  couldnt_check receipt  sample.jsonl.zst               not present, and no release asset is published for this fixture; building it produces this file; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke
  couldnt_check receipt  vectors.npy                    not present, and no release asset is published for this fixture; building it produces this file; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke
  couldnt_check receipt  queries.npy                    not present, and no release asset is published for this fixture; building it produces this file; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke
  verified      receipt  query_ids.json                 0081604bb50d8dd48b4ae5605a05fc894dcd2ae4db41511657464772c911b8e2
  verified      receipt  ground_truth.npy               13919bb5174ebeb4febe037017a2e2b8bbfe4998b3ce261e7989e4649c2a9cce
  verified      receipt  characterization.json          07b576e27e680596d8cb52c59f01dcb18e1039a9be135c48db921e5a56dc30e1
  verified      declared build_info.json                fa6168a52acb45283a51f73554e3683dd24abde014e0b82a4091e0e3ebb944c1
  couldnt_check declared projection.npy                 not shipped with the installed package; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke
  couldnt_check declared ground_view_base.parquet       not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke
  couldnt_check declared ground_view_queries.parquet    not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke
  couldnt_check declared ground_view_centroids.parquet  not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <empty profile>\oneground-assets\arxiv-smoke

values
  couldnt_check intrinsic_dimensionality                the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check boundary_crispness                      the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check skew_top10_share                        the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check ambiguous_query_rate                    the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check single_node_hnsw.recall_at_10           the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check semantic_sharded.recall_at_10           the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check semantic_sharded.storage_amplification  the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check drift                                   the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.

summary: digests 4 verified, 0 contradicted, 7 couldnt_check (6 receipt, 5 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check

         7 listed files are not present here, so their bytes were not checked:
         sample.jsonl.zst, vectors.npy, queries.npy, projection.npy,
         ground_view_base.parquet, ground_view_queries.parquet and
         ground_view_centroids.parquet.
         No value is published in the spec yet, so there was nothing to
         reproduce (8 placeholders).
[exit 0]
```

The four files verified from the clone and not from the wheel: `queries.npy`,
`ground_view_base.parquet`, `ground_view_queries.parquet` and
`ground_view_centroids.parquet`.

`tasks/scratch/018-docs-numbers.py`: ALL CHECKS PASSED. Identifier scan with this
report staged: 0 findings.

## Verification

- The two counts in the paragraph: observed, above.
- "Both exit 0": observed.
- "Each couldn't-check line gives the reason that file is absent": observed
  for all ten couldn't-check lines across the two runs.
- Suite not re-run: this change is one paragraph of documentation, and no test
  reads it. The docs-numbers check does read the docs, and passes.

## Observed, not done

- From a wheel install, `arxiv-smoke`'s `queries.npy` line does not say the
  repository carries it, though it does. The code decides that wording from
  whether a release asset exists for the fixture, and cannot know what git
  tracks.
- From a clone, `projection.npy`'s line says "artifact not present (release
  asset, or not built)". `arxiv-smoke` has no release asset, and no release
  asset contains a projection.

## Repo now contains

    docs/EXTERNAL_RUN.md                            the paragraph
    tasks/022c-digest-count-by-location.report.md   this report

## Blocked on developer

Retag `v0.1.0` at this commit (subject `task 022c:`), then rebuild the
artifacts.
