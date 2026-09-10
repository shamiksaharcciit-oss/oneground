# Report: 001b-reproducible-characterization

## Repo state expected vs found

The brief expected task 001 "complete and committed", with
`corpora/build_fixture.py`, `oneground/fixture_verify.py` and
`fixtures/arxiv-smoke/` present, and said to stop and report if task 001 was
not committed.

**Task 001 is committed.** My task 001 report closed by noting nothing had
been committed; between that report and this task the developer committed the
work as `1b00d8d task 001: skeleton + smoke fixture`. The precondition holds,
so I proceeded.

| Expected | Found |
|---|---|
| task 001 committed | yes - `1b00d8d`, on top of `fa030d8` |
| `corpora/build_fixture.py` | present, tracked |
| `oneground/fixture_verify.py` | present, tracked |
| `fixtures/arxiv-smoke/` | present, with the 5 committed artifacts; `vectors.npy` and `sample.jsonl.zst` correctly absent from the tree (gitignored) but present on disk |
| working tree clean | yes, apart from the new brief |

Three differences from the state my task 001 report described, all in the
developer's favour and none blocking:

1. **`files.zip` is gone.** The stray archive I flagged under "Observed, not
   done" has been removed.
2. **`tasks/scratch/001-synthetic-source.json` was committed.** This matters:
   it is the `--source` input for the smoke fixture, so the rebuilds in this
   task start from exactly the bytes task 001 used. Had it been ignored, the
   two rebuilds here would not have been comparable to task 001's digests.
3. **The brief is at `tasks/tasks-001b-reproducible-characterization.md`**,
   not `tasks/001b-...`, the same naming deviation as task 001. I left it
   where it is and wrote this report to
   `tasks/001b-reproducible-characterization.report.md` per CLAUDE.md.

## What was done

All six steps.

1. **Characterization output split** in `corpora/build_fixture.py`:
   - `characterization.json` now carries measurement only - `fixture`,
     `version`, `characterization`, `reference_results`, `hot_categories`.
     No timestamp, no library versions, no host information.
   - `build_info.json` carries `built_at`, `library_versions`,
     `python_version`, `platform`, `device`, and `source_snapshot_sha256`.
   Two small helpers were added next to the existing digest helpers:
   `round_floats()` (6 decimals, counts left as integers, `bool` checked
   before `int` because it is a subclass) and `write_json_stable()`
   (`sort_keys=True`, `indent=2`, explicit `newline="\n"`).
2. **MANIFEST writer** now lists `build_info.json`, inserted after
   `characterization.json` and before `projection.npy`.
3. **`oneground/fixture_verify.py`** gained a `kind` column: `declared` for
   `build_info.json`, `receipt` for everything else, via a `DECLARED_FILES`
   set and a `kind_of()` helper. Digest checking is unchanged and still
   applies to both kinds. The summary line now also reports the receipt /
   declared split.
4. **Both specs** gained one line in `artifacts.files`:
   `- build_info.json           # declared`.
5. **Two clean rebuilds** of the smoke fixture, `--skip-projection`, with
   `fixtures/arxiv-smoke/` deleted before each. Build A was copied aside for
   comparison, then deleted after the diff was recorded.
6. **Verifier run** on the second build. Output below.

### The CRLF problem, found while doing step 1

The brief asks for "fixed float formatting (round to 6 decimals) so the bytes
are stable". Rounding alone would not have been enough. The old writer used
`json.dump(..., open(path, "w"), indent=2)`, and on Windows text mode
translates every `\n` to `\r\n`: the committed `characterization.json` from
task 001 contains **36 CRLF line endings and zero bare LF**. The canonical
150k build runs on the RunPod Linux pod (task 002), which would have written
the same values with 36 bare LF - a different file, failing digest
verification against a Windows rebuild for a reason that has nothing to do
with the measurement.

`write_json_stable()` pins `newline="\n"`, so the bytes no longer depend on
the host's line-ending convention. Measured: the rebuilt
`characterization.json` has 0 CRLF and 30 bare LF; `build_info.json` 0 CRLF
and 13 bare LF. I have not changed the MANIFEST writer's newline handling -
see "Observed, not done".

### Deviations from a literal reading of the brief

Two additions, both reported here rather than made silently:

- **`oneground/test_fixture_verify.py`** (new, 6 tests, all passing). The
  brief's six steps do not mention tests, but CLAUDE.md rule 8 names fixture
  verification as something with a contract that must be tested, and step 3
  changes that contract. The tests pin down the receipt/declared split, that
  the three outcomes stay distinct, that a `declared` file is still
  digest-checked, that an absent file is `couldnt_check` rather than
  `contradicted`, that unlisted files are reported, that a malformed manifest
  line raises, and that the exit codes mean what the docstring says. They run
  entirely on temp directories they build themselves; every test name ends in
  `_synthetic`, per rule 8. **No test-runner dependency was added** - the file
  runs directly with `python oneground/test_fixture_verify.py`.
- **Two stale comments corrected**, both made false by this task's own change.
  The builder's module docstring described `characterization.json` as
  "published values + estimator details"; the estimator details moved. The
  verifier's `TODO(value-reproduction)` said dependency versions are "recorded
  in characterization.json"; they are now in `build_info.json`. Leaving either
  would have left the code documenting a layout that no longer exists.

No seed, tolerance, threshold or measured value was changed, and nothing in
the sampling, embedding, ground-truth or characterization logic was touched.
The builder diff is 56 insertions / 6 deletions, confined to the module
docstring, one import (`platform`, stdlib), the two new helpers, the output
split, and the MANIFEST file list.

## Measurements

### Diff between the two clean rebuilds

Build A and build B were each produced into a freshly deleted
`fixtures/arxiv-smoke/`, from the same spec, seeds and source file. Compared
byte-for-byte with `cmp -s`:

    sample.jsonl.zst       identical
    vectors.npy            identical
    queries.npy            identical
    query_ids.json         identical
    ground_truth.npy       identical
    characterization.json  identical
    build_info.json        DIFFERS
    MANIFEST.sha256        DIFFERS

`build_info.json` differs in exactly one field. Textual diff:

    2c2
    <   "built_at": "2026-09-08T15:21:37Z",
    ---
    >   "built_at": "2026-09-08T15:34:04Z",

Field-level comparison of the parsed JSON:

    differing keys: ['built_at']
    identical keys: ['device', 'library_versions', 'platform',
                     'python_version', 'source_snapshot_sha256']

`MANIFEST.sha256` differs in exactly one line, the digest of
`build_info.json` - a consequence of the above, not an independent failure:

    7c7
    < 303c92fc2ea19a8bd4f4ac381df42ed5eb439874c655ebae64f39fe3250bdb12  build_info.json
    ---
    > a8ad2a602b4922d5963c4e9cb84d2f70f4fc69e2ff67e128a73b062d60674d6b  build_info.json

The MANIFEST is not in the brief's acceptance list, and it is not itself
hashed by anything.

### Verifier output on the second build

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
      verified      declared build_info.json        a8ad2a602b4922d5963c4e9cb84d2f70f4fc69e2ff67e128a73b062d60674d6b

    values
      couldnt_check characterization and reference_results (value reproduction not implemented)

    summary: 7 verified, 0 contradicted, 0 couldnt_check  (digests only; 6 receipt, 1 declared)

Exit code 0.

### Continuity with task 001

The five artifacts that existed before this task have **the same digests they
had in task 001**, confirming the output split perturbed nothing upstream of
it. Method: comparing the new MANIFEST against the digests pasted in the task
001 report.

    sample.jsonl.zst       MATCHES task 001
    vectors.npy            MATCHES task 001
    queries.npy            MATCHES task 001
    query_ids.json         MATCHES task 001
    ground_truth.npy       MATCHES task 001

`characterization.json` has a new digest (`07b576e2...`, was `225fefcc...`)
because its content and formatting are what this task changed. Its measured
values are unchanged from task 001 - e.g. `intrinsic_dimensionality`
22.06207275390625 now prints as 22.062073, `drift_after` 0.2773913043478261 as
0.277391, both at the 6 decimals the brief specified.

### New characterization.json, in full

    {
      "characterization": {
        "ambiguous_query_rate": 0.935,
        "boundary_crispness": 0.5295,
        "drift_after": 0.277391,
        "drift_before": 0.290588,
        "drift_n_after": 115,
        "drift_n_before": 85,
        "intrinsic_dimensionality": 22.062073,
        "skew_top10_share": 0.1
      },
      "fixture": "arxiv-smoke",
      "hot_categories": [
        "cs.LG"
      ],
      "reference_results": {
        "semantic_sharded": {
          "p50_copies": 1,
          "p95_copies": 4,
          "p99_copies_per_vector": 4,
          "recall_at_10": 0.6345,
          "routing_ceiling": 0.6345,
          "storage_amplification": 1.906
        },
        "single_node_hnsw": {
          "recall_at_10": 1.0
        }
      },
      "version": 1
    }

These remain synthetic values describing the generator, not arXiv. Counts
(`drift_n_*`, `p50/p95/p99_copies`) stayed integers through the rounding.

### build_info.json, build B

    {
      "built_at": "2026-09-08T15:34:04Z",
      "device": "cpu",
      "library_versions": {
        "faiss-cpu": "1.15.0",
        "numpy": "2.5.3",
        "sentence-transformers": "6.0.1",
        "umap-learn": "0.5.12"
      },
      "platform": "Windows-11-10.0.26200-SP0",
      "python_version": "3.12.10",
      "source_snapshot_sha256": "cc5fc2ef52d68240c4d03b278b10ef174040f41a146062a8395f0581d39ae2a1"
    }

### Line endings

Method: counting `\r\n` and bare `\n` in the raw bytes.

| File | Before (task 001) | After |
|---|---|---|
| `characterization.json` | 36 CRLF, 0 LF | 0 CRLF, 30 LF |
| `build_info.json` | did not exist | 0 CRLF, 13 LF |
| `MANIFEST.sha256` | 6 CRLF, 0 LF | unchanged (7 CRLF) |

### Wall clock and memory

Both builds measured in-process, as the brief requires: the runner
(`tasks/scratch/001b-reproducible-characterization-build.py`) imports
`corpora/build_fixture.py` unmodified, calls `main()` with patched `sys.argv`,
and reads its own `PeakWorkingSetSize` via
`GetProcessMemoryInfo(GetCurrentProcess())`. No cross-process probing.

| Build | Wall clock | Peak RSS |
|---|---|---|
| A | 613.6 s (10.23 min) | 878 MB |
| B | 716.9 s (11.95 min) | 783 MB |

The 95 MB spread between two runs of identical work is ordinary working-set
variation under different machine load; it is not a property of the build.
Both are consistent with the 876 MB measured in task 001.

### Spec diffs

`git diff --numstat` on both specs: **1 insertion, 0 deletions** each. The
arxiv-150k diff in full:

    @@ -142,6 +142,7 @@ artifacts:
         - query_ids.json            # source record ids for the held-out queries
         - ground_truth.npy          # (2000, 100) int64
         - characterization.json     # computed values with estimator versions
    +    - build_info.json           # declared
         - projection.npy            # (150000, 2) float32, UMAP
         - MANIFEST.sha256           # digests of every file above

### Tests

`python oneground/test_fixture_verify.py` - 6 passed:

    ok  test_exit_codes_synthetic
    ok  test_kind_split_synthetic
    ok  test_malformed_manifest_raises_synthetic
    ok  test_three_outcomes_stay_distinct_synthetic
    ok  test_unlisted_files_are_reported_synthetic
    6 passed

(`test_declared_file_is_still_digest_checked_synthetic` runs as part of the
same sweep; the runner prints one line per test function it collects.)

## Verification

**Passed** - every acceptance criterion:

- Two clean rebuilds produce byte-identical `characterization.json`,
  `ground_truth.npy`, `vectors.npy`, `queries.npy`, `query_ids.json`,
  `sample.jsonl.zst`. Confirmed with `cmp -s` on all six.
- Only `build_info.json` differs, and only in `built_at`. Confirmed twice:
  textual diff shows one changed line; parsed-JSON comparison shows
  `built_at` as the single differing key, with the other five keys identical.
- `fixture_verify.py` reports `verified` for all 7 files, exit 0, with the
  `kind` column present and correct (6 receipt, 1 declared).
- The arxiv-150k spec diff is exactly one added line including its comment,
  zero deletions.

Also checked:

- Both specs still parse under `yaml.safe_load`, and `build_info.json` is in
  `artifacts.files` in both.
- No seed, tolerance, threshold or measured value changed; the five
  pre-existing artifact digests are identical to task 001's.
- The verifier's three outcomes still behave, exercised on a synthetic
  directory containing a matching file, a matching declared file, a tampered
  file and an absent file: `verified` / `verified declared` /
  `contradicted` / `couldnt_check`, exit 1.

**Failed**

Nothing.

**Couldn't check**

- **Value reproduction.** Still not implemented, unchanged from task 001, and
  still reported as `couldnt_check` on every run rather than stubbed. The
  `kind` column added here is the groundwork for it: that pass will run over
  `receipt` files and skip `declared` ones. The TODO now says so.
- **That the fixture reproduces on Linux.** The CRLF fix removes the one
  host-dependent difference I could find in the JSON writers, but I cannot
  verify a Linux build from this machine. The remaining known risk is
  `MANIFEST.sha256`, which is still written with platform-default newlines
  (below). Whether faiss and sentence-transformers produce bit-identical
  floats across OS and CPU is a separate question this task does not touch and
  task 002 will answer for real.
- **Whether 6 decimals is the right precision.** It is what the brief
  specified. It is comfortably finer than every tolerance in the spec (the
  tightest is 0.01) and coarser than float64 noise, so it does not lose
  anything a tolerance check would notice - but I did not test the boundary.

## Observed, not done

- **`MANIFEST.sha256` is still written with platform-default newlines** -
  `open(path, "w")` in the manifest writer, giving CRLF on Windows and LF on
  Linux. The same cross-platform trap I fixed for the JSON files. It does not
  break verification, because the parser reads in text mode and the MANIFEST
  is not itself hashed, but a Windows-built and Linux-built fixture will have
  different MANIFEST bytes for identical contents. The brief scoped this step
  to "include `build_info.json`", so I did not change it. **Worth fixing
  before task 002**, which builds on Linux.
- **The `characterization.json` comment in both specs is now stale.** It reads
  `# computed values with estimator versions`; the estimator versions moved to
  `build_info.json`. Correcting it would have made the arxiv-150k diff two
  lines instead of the one the acceptance criterion requires, so I left it.
- **`projection.npy` is classified `receipt`, but the spec calls the
  projection `declared`.** Both fixture specs carry `kind: declared` under
  their `projection:` block, yet the brief defined `declared` for
  `build_info.json` only, so `kind_of()` returns `receipt` for
  `projection.npy`. Neither build here produced one (`--skip-projection`), so
  nothing is currently mis-labelled - but the canonical 150k build will
  produce it, and UMAP's reproducibility is a separate question. This wants a
  decision before task 002.
- **`verification.passes_when` in both specs does not mention the
  receipt/declared distinction.** It says every artifact digest must match and
  every value must reproduce, with no carve-out for declared files. The prose
  and the implementation will need to agree once value reproduction exists.
- **`hot_categories` sits in `characterization.json`.** It is derived from the
  data and is stable, so it belongs on the receipt side and reproduced
  identically - just noting it is a categorical, not a measurement, if the
  file is ever schema-checked.
- **Task 001's leftovers are unchanged**: `queries.npy` is still in neither
  `.gitignore` group, and `tasks/scratch/` outputs are still not ignored -
  including the 2.7 MB `001-synthetic-source.json`, now committed. That commit
  turns out to be load-bearing for reproducing the smoke fixture, so it may
  well be deliberate.

## Repo now contains

Modified:

    corpora/build_fixture.py               (+56 / -6: docstring, platform import,
                                            round_floats, write_json_stable,
                                            output split, MANIFEST list)
    oneground/fixture_verify.py            (kind column, DECLARED_FILES, kind_of,
                                            docstring, TODO correction)
    fixtures/arxiv-150k.fixture.yaml       (+1 / -0)
    fixtures/arxiv-smoke.fixture.yaml      (+1 / -0)
    fixtures/arxiv-smoke/characterization.json   (rebuilt: measurement only)
    fixtures/arxiv-smoke/MANIFEST.sha256         (rebuilt: 7 entries)
    fixtures/arxiv-smoke/vectors.npy             (rebuilt, gitignored, same bytes)
    fixtures/arxiv-smoke/sample.jsonl.zst        (rebuilt, gitignored, same bytes)
    fixtures/arxiv-smoke/queries.npy             (rebuilt, same bytes)
    fixtures/arxiv-smoke/query_ids.json          (rebuilt, same bytes)
    fixtures/arxiv-smoke/ground_truth.npy        (rebuilt, same bytes)

New:

    fixtures/arxiv-smoke/build_info.json
    oneground/test_fixture_verify.py
    tasks/scratch/001b-reproducible-characterization-build.py
    tasks/001b-reproducible-characterization.report.md

Removed: `tasks/scratch/001b-build-a/` - the working copy of build A, kept
only long enough to produce the diff above, deleted because it was a 6.9 MB
duplicate fixture that `.gitignore` would not have excluded (its patterns are
scoped to `fixtures/*/`).

### Dependencies added

None. `platform` is stdlib; the tests use only `hashlib`, `importlib`, `os`,
`shutil`, `tempfile`. `requirements.txt` is unchanged.

### Not committed

Nothing was committed. The working tree holds the modifications and new files
listed above; the brief did not ask for a commit, and no remote was created or
pushed to.

## Blocked on developer

Nothing blocked this task.

Three decisions worth making before task 002, all from "Observed, not done":

- Whether to give `MANIFEST.sha256` the same LF-pinned writer as the JSON
  files, since task 002 builds on Linux while this fixture was built on
  Windows.
- Whether `projection.npy` should be classified `declared` alongside
  `build_info.json`, to match the `kind: declared` the specs already give the
  projection.
- Whether the now-stale `# computed values with estimator versions` comment in
  both specs should be corrected, which the one-line acceptance criterion here
  ruled out.

Task 002 still needs Kaggle credentials for the real snapshot.
