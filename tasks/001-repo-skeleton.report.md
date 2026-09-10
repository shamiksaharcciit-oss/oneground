# Report: 001-repo-skeleton

## Repo state expected vs found

The brief expected "an empty or near-empty directory containing only:
CLAUDE.md, this brief, `build_fixture.py`, `arxiv-150k.fixture.yaml`."

Found, at the repo root:

| Path | Expected by brief | Note |
|---|---|---|
| `CLAUDE.md` | yes | as expected |
| `build_fixture.py` | yes | as expected, 519 lines |
| `arxiv-150k.fixture.yaml` | yes | as expected, 160 lines |
| `tasks/tasks-001-repo-skeleton.md` | yes, as `tasks/NNN-name.md` | **name differs** from the convention in CLAUDE.md |
| `files.zip` | **no** | 4,319 bytes; contains only copies of `CLAUDE.md` and `tasks-001-repo-skeleton.md`. Left untouched. |
| `.git/` | not stated | one commit, `fa030d8`, containing all five files above |

Two deviations, neither of which invalidates the brief's assumptions, so I
proceeded rather than stopping:

1. `files.zip` is an extra file. Its contents are duplicates of two files
   already present, so it carries nothing the brief depends on. I did not
   delete it (deleting data needs an explicit instruction).
2. The brief is at `tasks/tasks-001-repo-skeleton.md`, not
   `tasks/001-repo-skeleton.md`. I left the brief where it is and wrote this
   report to `tasks/001-repo-skeleton.report.md`, following the CLAUDE.md
   convention rather than the existing filename.

Everything the brief's steps operate on was present and matched.

## What was done

All nine steps. In order:

1. **Layout created**: `fixtures/ models/ adapters/ policies/ corpora/
   oneground/ docs/ tasks/ tasks/scratch/`, each with a `README.md` saying
   what belongs there, worded from the corresponding CLAUDE.md text.
2. **Files moved** with `git mv` (rename preserved in the index):
   `arxiv-150k.fixture.yaml` to `fixtures/arxiv-150k.fixture.yaml`,
   `build_fixture.py` to `corpora/build_fixture.py`. The builder's docstring
   was updated to the new paths - a 3-line diff, all inside the module
   docstring, verified with `git diff --numstat` (3 insertions, 3 deletions)
   and by reading the diff. No logic changed. The spec file is byte-identical
   to the committed version (`git show HEAD:arxiv-150k.fixture.yaml | diff -`
   returns empty) - a pure rename.
3. **Venv created** at `.venv` with Python 3.12.10 (`py -3.12 -m venv`), and
   the six named packages installed. Exact versions recorded in
   `requirements.txt`.
4. **`corpora/make_synthetic_source.py`** written: emits arXiv-format JSONL,
   6,000 records, seeded (`--seed 20260908`), 12 real arXiv category strings
   skewed toward cs.LG/cs.CL, `update_date` spanning 2007-2025, abstracts
   over the builder's 200-character floor. Its docstring states in the first
   line that it is for pipeline testing only and must never back a published
   artifact. Text is drawn from per-category vocabularies so the embedding
   space has some cluster structure rather than being uniform noise.
5. **`fixtures/arxiv-smoke.fixture.yaml`** written as a copy of the 150k spec
   with `fixture.id: arxiv-smoke`, `sampling.target_size: 2000`,
   `queries.count: 200`, and a `license_notice` stating the data is synthetic
   and carries no arXiv content. See "Deviations" below for the additional
   descriptive fields I updated.
6. **Pipeline run** on the synthetic source with `--skip-projection`.
   Completed without error. Model downloaded once (438 MB).
7. **`oneground/fixture_verify.py`** written: recomputes every digest against
   `MANIFEST.sha256` and reports per-file verified / contradicted /
   couldnt_check. Value reproduction is **not implemented and not stubbed**:
   it is a marked `TODO(value-reproduction)` and is reported as
   `couldnt_check` in every run.
8. **Verifier run** on `fixtures/arxiv-smoke/`. Output pasted below.
9. **`.gitignore`** added, covering exactly what the brief named.

### Deviations from a literal reading of the brief

Step 5 says the smoke spec is "a copy of the arxiv-150k spec" with three
changes plus a `license_notice` note. I also updated seven descriptive fields
that would otherwise have stated something false about this fixture:
`source.name`, `source.provider`, the query counts inside `queries.rule`
(the prose said "1,000 and 1,000", which is wrong at `count: 200`),
`artifacts.directory`, the three array-shape comments under
`artifacts.files`, `verification.command`, and the changelog note.

I did **not** touch any seed, threshold, tolerance, parameter block, or
`TO_BE_FILLED` marker. Verified mechanically: extracting every line matching
`seed:`, `tolerance:`, `params:`, `TO_BE_FILLED`, `1.20`, `1.10`, `k: 100`
from both specs and diffing them returns empty - the two files are identical
on all of them. Both specs still contain all 20 `TO_BE_FILLED` markers; no
measured value was written into any YAML.

## Measurements

### Pipeline wall clock

Obtained by wrapping `corpora/build_fixture.py` in a scratch script
(`tasks/scratch/001-repo-skeleton-run.py`) that records `time.time()` around
`subprocess.Popen(...).wait()`. The builder's own self-reported figure agrees
to 0.1 min in both cases.

| Run | Wall clock | Notes |
|---|---|---|
| Build 1 (the committed fixture) | **658.6 s = 10.98 min** | includes the one-time 438 MB model download, 77 s of it |
| Build 3 (model cached) | **481.3 s = 8.02 min** | representative of a repeat run |

Phase breakdown from the builder's own timestamped log, build 1:
sampling both passes under 1 s; model fetch 77 s; embedding 2,000 base
documents 566 s (9.4 min, 16 batches, ~35 s/batch); embedding 200 query
titles 7 s; exact ground truth plus all characterization plus both reference
configurations under 2 s combined. Embedding is 86% of the run.

### Peak RSS

**876 MB**, for a complete run. Method: a scratch script
(`tasks/scratch/001-repo-skeleton-rss4.py`) imports `corpora/build_fixture.py`
unmodified, calls `main()` in its own process with patched `sys.argv`, and
then reads `PeakWorkingSetSize` from
`GetProcessMemoryInfo(GetCurrentProcess())`.

This took four attempts and the failures are worth recording, because they
would mislead anyone measuring memory on this machine again:

- The venv's `.venv/Scripts/python.exe` is a **launcher stub**: it spawns the
  real interpreter as a separate process. Sampling the pid returned by
  `subprocess.Popen` therefore reads ~4 MB and misses the entire workload. I
  confirmed this directly: a child told to allocate 600 MB showed pid 12284
  at 4 MB peak while pid 16148 held 587 MB. Two independent instruments
  (ctypes `GetProcessMemoryInfo`, .NET `PeakWorkingSet64`) both reported the
  same wrong 4 MB, because both were pointed at the same wrong process -
  agreement between instruments was not evidence of correctness here.
- Probing the *worker* process across process boundaries during embedding
  destabilised it. A per-second `Win32_Process` CIM walk killed the run at
  110 s; a `CreateToolhelp32Snapshot` plus `PROCESS_VM_READ` sampler crashed
  it with `ACCESS_VIOLATION` (exit 3221225477) at 190 s. Both partial runs
  had reached 639-653 MB before dying, consistent with the 876 MB final
  figure. The two runs that completed were the two that never opened a handle
  into the worker. Self-measurement avoids the problem entirely.

The 876 MB figure includes the scratch runner's own interpreter, which is a
few MB of the total.

### Determinism (not requested by the brief; measured as a by-product)

The pipeline was run three times to completion from the same seeds and source.
Comparing the third build against the committed one:

- `sample.jsonl.zst`, `vectors.npy`, `queries.npy`, `query_ids.json`,
  `ground_truth.npy` - **byte-identical**, all five digests match.
- `characterization.json` - differs, and the only differing field is
  `built_at` (a wall-clock timestamp). `characterization`,
  `reference_results`, `hot_categories` and `library_versions` compare equal
  as parsed JSON.

So every computed value in this pipeline is reproducible from the seeds; the
one non-reproducible byte-level artifact is a timestamp. Method: `diff` of
sorted MANIFESTs, plus a field-level dict comparison of the parsed JSON.

### Artifact shapes

From `numpy.load` on the committed fixture: `vectors.npy` (2000, 768)
float32, mean L2 norm 1.000000; `queries.npy` (200, 768) float32, mean L2
norm 1.000000; `ground_truth.npy` (200, 100) int64, ids in [0, 1999];
`query_ids.json` 200 entries, all unique. All match the smoke spec.

### Synthetic source properties

Measured by `tasks/scratch/001-repo-skeleton-check-source.py`, which imports
`build_fixture` and reuses its own `eligible()` predicate, so what is counted
is exactly what the pipeline accepts:

    records           : 6,000
    eligible (>=200ch): 6,000  (100.0%)
    unique ids        : 6,000
    year range        : 2007-2025, 19 distinct years
    pre-2019 share    : 40.3%  -> ~806 of a 2000 base
    primary categories: 12
        cs.LG                 1322  22.0%
        cs.CL                 1050  17.5%
        cs.CV                  711  11.8%
        cs.AI                  531   8.8%
        stat.ML                506   8.4%
        cs.IR                  411   6.9%
        eess.SP                356   5.9%
        math.OC                296   4.9%
        cond-mat.stat-mech     222   3.7%
        hep-th                 220   3.7%
        astro-ph.GA            218   3.6%
        q-bio.NC               157   2.6%
    abstract chars    : min 263, median 308, max 341

The 40.3% pre-2019 share was designed so the drift split's k-means has more
points than centroids: the build reported 803 pre-2019 base records against
256 centroids.

### TO_BE_FILLED block, verbatim

Pasted exactly as `corpora/build_fixture.py` printed it. **These are synthetic
values. They describe the generator, not arXiv, and were not written into any
YAML.**

    ================ TO_BE_FILLED values ================
    source.snapshot_sha256:               cc5fc2ef52d68240c4d03b278b10ef174040f41a146062a8395f0581d39ae2a1
    sampling.sample_sha256:               b6383e226a14e631a2e5c875cd658230c194ebe5ac908abea6ea5e52d1fa4c6c
    embedding.weights_sha256:             c7c1988aae201f80cf91a5dbbd5866409503b89dcaba877ca6dba7dd0a5167d7
    embedding.library_version:            6.0.1
    embedding.vectors_sha256:             d7bbda6af7496e4c911e603baf78c921964e0cf81eeb2ff03f070414902023ca
    queries.queries_sha256:               a3ea6e53d3b11ca220353ac8f9f6277e4e9c28f868fbea55861ab6b9e360ff0d
    ground_truth.ground_truth_sha256:     7975fc6162d0fad61c89905b5a43d85e6243f800b6ce9adebee4b2385f39d584
    characterization.intrinsic_dimensionality.value: 22.06
    characterization.boundary_crispness.value:       0.529
    characterization.ambiguous_query_rate.value:     0.935
    characterization.skew_top10_share.value:         0.100
    characterization.drift.value_before:             0.291  (n=85)
    characterization.drift.value_after:              0.277  (n=115)
    reference_results.single_node_hnsw.recall_at_10: 1.000
    reference_results.semantic_sharded.recall_at_10: 0.634
    reference_results.semantic_sharded.routing_ceiling: 0.634
    reference_results.semantic_sharded.storage_amplification: 1.906
    reference_results.semantic_sharded.p50_copies: 1
    reference_results.semantic_sharded.p95_copies: 4
    reference_results.semantic_sharded.p99_copies_per_vector: 4

    artifacts written to fixtures/arxiv-smoke   (10.9 min)

Note the block prints `p50_copies` and `p95_copies` in addition to the four
`semantic_sharded` fields the spec marks `TO_BE_FILLED`; both come from the
`ref_sem` dict the builder iterates. Not a problem, just more than the spec
has slots for.

### Weights hash

`c7c1988aae201f80cf91a5dbbd5866409503b89dcaba877ca6dba7dd0a5167d7` - a real
sha256, not `None`. Independently confirmed with `sha256sum` against the file
the builder hashed:

    ~/.cache/huggingface/hub/models--BAAI--bge-base-en-v1.5/
      snapshots/a5beb1e3e68b9ab74eb54cfd186867f64f240e1a/model.safetensors
    437,955,512 bytes

`load_model()` tries `model.safetensors` before `pytorch_model.bin`; both are
in the cache (the `.bin` hashes to `4b9d4a4b...`), so the receipt depends on
that ordering, which is fixed in the code.

## Verification

**Passed**

- `fixtures/arxiv-smoke/` exists. `MANIFEST.sha256` lists 6 artifacts -
  `sample.jsonl.zst`, `vectors.npy`, `queries.npy`, `query_ids.json`,
  `ground_truth.npy`, `characterization.json` - and correctly omits
  `projection.npy`, which was skipped. Matches the acceptance criterion.
- The builder printed every TO_BE_FILLED value without error; exit code 0.
- `fixture_verify.py` reports **verified for all 6 files**, exit code 0:

      fixture: arxiv-smoke
      directory: fixtures\arxiv-smoke
      manifest: MANIFEST.sha256 (6 files listed)

      digests
        verified      sample.jsonl.zst       b6383e226a14e631a2e5c875cd658230c194ebe5ac908abea6ea5e52d1fa4c6c
        verified      vectors.npy            d9f44ded9e68af7495544c9a90da5bfee3798204f77ce0efbd219508268d7a6e
        verified      queries.npy            2359ce716b2ca7ef75c5d9f4fa4a42924df83eeac5848918b6a823efa7f7433a
        verified      query_ids.json         0081604bb50d8dd48b4ae5605a05fc894dcd2ae4db41511657464772c911b8e2
        verified      ground_truth.npy       13919bb5174ebeb4febe037017a2e2b8bbfe4998b3ce261e7989e4649c2a9cce
        verified      characterization.json  225fefcc06edce24abd7141af25425acf10614baecdce1c2797dc6edf798b65c

      values
        couldnt_check characterization and reference_results (value reproduction not implemented)

      summary: 6 verified, 0 contradicted, 0 couldnt_check  (digests only)

- The verifier's three outcomes were each exercised before the real run, on a
  throwaway directory with one good file, one tampered file and one missing
  file: it reported `verified` / `contradicted` / `couldnt_check`
  respectively, flagged an unlisted extra file, and exited 1.
- The weights hash is a real sha256 (above).
- `requirements.txt` pins every installed distribution to its exact version.
- `.gitignore` behaves as specified, checked with `git check-ignore -v`:
  `vectors.npy`, `sample.jsonl.zst` and `.venv/` are ignored;
  `MANIFEST.sha256`, `characterization.json`, `query_ids.json`,
  `ground_truth.npy` are not.
- The 150k spec is untouched: byte-identical to the committed version.
- The pipeline is deterministic in every computed value across three runs
  (see Measurements).

**Failed**

Nothing failed. No gate, threshold, tolerance, seed or fixture value was
changed at any point.

**Couldn't check**

- **Value reproduction.** Not implemented, by the brief's instruction. The
  verifier reports `couldnt_check` for it on every run and carries a marked
  `TODO(value-reproduction)`. It is not stubbed with a pass, and the
  digests-only scope is stated in the docstring, in the output, and in the
  exit-code contract.
- **Whether the characterization values are meaningful.** They are not, and
  cannot be at this size: 2,000 points clustered to 256 centroids, which faiss
  warned about twice (`please provide at least 9984 training points`), exactly
  as the brief predicted. `ambiguous_query_rate` of 0.935 and
  `boundary_crispness` of 0.529 are artifacts of that ratio and of the
  generator's vocabulary, not properties of anything real. The run proves the
  pipeline executes and is deterministic; it says nothing about corpus
  structure.
- **Peak RSS of the canonical 150k build.** The 876 MB here is for 2,000
  vectors. It does not extrapolate directly: base vectors alone go from 6 MB
  to 460 MB at 150k, and `ref_semantic_sharded` builds an HNSW index per
  region plus an exact index per query.

## Observed, not done

- **`files.zip`** sits in the repo root and is tracked. It contains only
  copies of `CLAUDE.md` and the task brief. Probably a transfer leftover.
  Not deleted.
- **The brief's filename** is `tasks/tasks-001-repo-skeleton.md`, which does
  not match the `tasks/NNN-name.md` convention in CLAUDE.md. Not renamed.
- **`queries.npy` is in neither `.gitignore` group.** The brief named three
  files to ignore and four to commit; `queries.npy` appears in neither list.
  It is currently committable at 614 KB (6 MB at 150k scale). Left tracked,
  following the brief literally.
- **`tasks/scratch/` outputs are not ignored.** `001-synthetic-source.json`
  is 2.7 MB and would be committed as-is. It is fully regenerable from
  `make_synthetic_source.py` with its default seed. The brief specified the
  `.gitignore` contents exactly, so I did not add a rule.
- **`characterization.json` cannot be digest-verified across rebuilds**
  because `built_at` embeds wall-clock time. Any future value-reproduction
  check will need to compare parsed fields, or the timestamp will need to
  move out of the hashed artifact.
- **`semantic_sharded.recall_at_10` equals `routing_ceiling` exactly**
  (0.6345 both). At this size the HNSW graphs inside the probed shards lose
  nothing; 100% of the recall shortfall is routing, i.e. the true neighbours
  are in shards that were not probed. Worth re-checking at 150k, where the
  two should separate.
- **`hot categories 1`.** `split_queries` computes
  `max(1, int(len(counts) * 0.05))`; with 12 categories that is
  `int(0.6) = 0 -> 1`, so all 100 "hot" queries were drawn from cs.LG alone.
  At 150k there will be ~150 categories and the top 5% will be ~7 of them, as
  the spec's prose intends. Not a defect, but the smoke fixture exercises a
  degenerate corner of that rule.
- **The venv launcher-stub behaviour** documented under Peak RSS will bite
  any future memory measurement on this machine, and cross-process probing of
  the worker crashed the run twice. Recorded here rather than worked around.
- **`build_fixture.py` derives its output path from `--out` and the spec id**,
  so `artifacts.directory` in a spec is documentation only; nothing validates
  that the two agree.

## Repo now contains

New:

    .gitignore
    requirements.txt
    adapters/README.md
    corpora/README.md
    corpora/make_synthetic_source.py
    docs/README.md
    fixtures/README.md
    fixtures/arxiv-smoke.fixture.yaml
    fixtures/arxiv-smoke/MANIFEST.sha256
    fixtures/arxiv-smoke/characterization.json
    fixtures/arxiv-smoke/ground_truth.npy
    fixtures/arxiv-smoke/queries.npy
    fixtures/arxiv-smoke/query_ids.json
    fixtures/arxiv-smoke/sample.jsonl.zst      (gitignored)
    fixtures/arxiv-smoke/vectors.npy           (gitignored)
    models/README.md
    oneground/README.md
    oneground/fixture_verify.py
    policies/README.md
    tasks/README.md
    tasks/001-repo-skeleton.report.md
    tasks/scratch/README.md
    tasks/scratch/001-synthetic-source.json
    tasks/scratch/001-repo-skeleton-check-source.py
    tasks/scratch/001-repo-skeleton-run.py
    tasks/scratch/001-repo-skeleton-rss.py
    tasks/scratch/001-repo-skeleton-rss-selftest.py
    tasks/scratch/001-repo-skeleton-rss2.ps1
    tasks/scratch/001-repo-skeleton-rss3.py
    tasks/scratch/001-repo-skeleton-rss4.py
    .venv/                                     (gitignored)

Moved:

    arxiv-150k.fixture.yaml -> fixtures/arxiv-150k.fixture.yaml   (content unchanged)
    build_fixture.py        -> corpora/build_fixture.py           (docstring paths only)

Unchanged: `CLAUDE.md`, `files.zip`, `tasks/tasks-001-repo-skeleton.md`.

Five of the scratch scripts are the memory-measurement attempts. I kept the
failed ones because the report cites their results; they can be deleted
without affecting anything.

### Dependencies added

All six named in CLAUDE.md, pinned in `requirements.txt` alongside their full
transitive closure (44 distributions total). Core:

    numpy==2.5.3
    faiss-cpu==1.15.0
    pyyaml==6.0.3
    zstandard==0.25.0
    sentence-transformers==6.0.1
    umap-learn==0.5.12

Notable transitive pins: `torch==2.14.0`, `transformers==5.16.1`,
`scikit-learn==1.9.0`, `numba==0.67.0`, `huggingface_hub==1.30.0`.
Python 3.12.10.

### Not committed

Nothing was committed. The working tree holds the `git mv` renames staged and
everything else untracked; the brief did not ask for a commit, and no remote
was created or pushed to.

## Blocked on developer

Nothing blocked this task.

Two things ahead of task 002:

- **Kaggle credentials** for `arxiv-metadata-oai-snapshot.json`. Developer
  runs; the brief explicitly excluded it here.
- **A decision on committing** the work in this report, and on the two
  `.gitignore` gaps under "Observed, not done" (`queries.npy`, and
  `tasks/scratch/` outputs) if the 2.7 MB synthetic source should stay out of
  git.
