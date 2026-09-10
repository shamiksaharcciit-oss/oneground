# Report: 003c-torch-receipt

## Repo state expected vs found

The brief expected task 003b committed and the tree clean.

| Expected | Found |
|---|---|
| 003b committed | yes — `0ab7567 task 003b: build 2 canonical, findings, constitution reconciled, --strict` |
| tree clean | yes — the only entry in `git status` was the untracked brief |

`CLAUDE.md` carries the reconciled canonical-build bullet from 003b, and
`docs/CHARTER.md` has the status table and Phase 1 roadmap this task edits.
Nothing was missing and nothing blocked.

## What was done

All five steps.

### 1. torch in the receipt

A `torch_receipt()` helper was added to `corpora/build_fixture.py`, next to
the other small helpers, returning `torch`, `torch_cuda` and
`cuda_device_name`. `library_versions` gains `torch`; the other two go in at
`build_info.json`'s top level. `build_info.json` stays declared — nothing about
its classification changed.

It reads defensively: by the time it runs, every receipt artifact is already
written (task 002b), so an odd or missing torch install degrades to null
fields rather than sinking a build at the last step.

**One deliberate departure from the obvious implementation**, because the
obvious one loses exactly the information this task exists to capture. The
existing `library_versions` is built from `importlib.metadata.version(...)`.
Measured on this machine:

    importlib.metadata.version("torch")  ->  2.14.0
    torch.__version__                    ->  2.14.0+cpu

The metadata drops the local version segment. Adding `"torch"` to the existing
`md.version` tuple would therefore have recorded `2.14.0` — which does not
distinguish a CPU build from `+cu130` from `+cu121`, the precise gap the 003b
report raised and this brief's own step 2 quotes `2.14.0+cu130` to close. So
`library_versions["torch"]` is taken from `torch.__version__`.

Nothing is lost by this and something is gained: the recorded string now
matches the format of the `torch_version: "2.14.0+cu130"` line this task adds
to the spec, so when build 3 lands, its recorded value and that declared value
will be directly comparable as strings rather than needing to be reassembled
from `torch` plus `torch_cuda`.

`cuda_device_name` and `torch_cuda` are written as explicit `null` on a CPU
build rather than omitted, so `build_info.json` keeps the same shape on CPU and
GPU and two builds stay diffable.

### 2. Spec — declared torch and CUDA device

`torch_version` and `cuda_device` added under `embedding`, with the brief's
comments verbatim, and a sixth finding
`torch_version_is_declared_not_recorded` recording that build 2's torch
version and device rest on the developer's attestation rather than on an
artifact, and are recorded from build 3 onward.

### 3. Changelog

The three entries relabelled `build: 1-prep`, `build: 1`, `build: 2`, dates and
notes untouched, and the comment
`# 'version' is the fixture schema version; 'build' is the canonical build number`
added under `changelog:`.

### 4. Charter

`002b` → done (the stale row I flagged in 003b), new row
`| 003c | torch in receipts, loose ends | done |`, and a Phase 1 roadmap line
for build 3, marked planned and not scheduled.

### 5. Smoke rebuild, tests, verifier

Rebuilt once with `--skip-projection` via the 002b scratch runner, which
imports the builder unmodified and measures in-process. `fixtures/arxiv-150k/`
was not touched — confirmed below.

## Measurements

### The new build_info.json fields (acceptance item)

`fixtures/arxiv-smoke/build_info.json` after the rebuild, in full:

    {
      "built_at": "2026-09-08T21:56:30Z",
      "cuda_device_name": null,
      "device": "cpu",
      "library_versions": {
        "faiss-cpu": "1.15.0",
        "numpy": "2.5.3",
        "sentence-transformers": "6.0.1",
        "torch": "2.14.0+cpu",
        "umap-learn": "0.5.12"
      },
      "platform": "Windows-11-10.0.26200-SP0",
      "python_version": "3.12.10",
      "source_snapshot_sha256": "cc5fc2ef52d68240c4d03b278b10ef174040f41a146062a8395f0581d39ae2a1",
      "torch_cuda": null
    }

Answering the acceptance question directly — **on this CPU build both are
`null`, not absent**:

| Field | Value | Present? |
|---|---|---|
| `library_versions.torch` | `"2.14.0+cpu"` | yes |
| `torch_cuda` | `null` | **present, null** |
| `cuda_device_name` | `null` | **present, null** |

`torch_cuda` is null because `torch.version.cuda` is `None` on a CPU wheel;
`cuda_device_name` is null because `torch.cuda.is_available()` is `False`, so
`get_device_name(0)` was never called. Both verified directly:

    torch.version.cuda      : None
    torch.cuda.is_available : False

On the pod these would carry the CUDA toolkit version and the device string —
which is what makes build 3 able to replace the two declared spec lines with
recorded ones.

### torch_receipt() in isolation

Called on the imported-unmodified builder before the rebuild:

    {"torch": "2.14.0+cpu", "torch_cuda": null, "cuda_device_name": null}

### The smoke rebuild

| | |
|---|---|
| embedding | 8m 32s (2,200 texts) |
| wall clock | 617.4 s (10.29 min) |
| peak RSS | 799 MB |
| mode | skip-projection |

Method: the builder's own elapsed logging, and the scratch runner's
in-process `GetProcessMemoryInfo(GetCurrentProcess())`. Consistent with the
6m 00s–11m 02s spread of earlier smoke runs on this machine, which is machine
load rather than the build.

### The rebuild changed only the declared file

    fixtures/arxiv-smoke/MANIFEST.sha256   1 insertion, 1 deletion
    fixtures/arxiv-smoke/build_info.json   5 insertions, 2 deletions

and the single MANIFEST line is `build_info.json`'s own digest:

    -8c50b8be49735f193655a4525ba2ea09569f8586ec878b4b5d11774d9d5f3e85  build_info.json
    +fa6168a52acb45283a51f73554e3683dd24abde014e0b82a4091e0e3ebb944c1  build_info.json

`sample.jsonl.zst`, `vectors.npy`, `queries.npy`, `query_ids.json`,
`ground_truth.npy` and `characterization.json` are byte-identical to before —
they do not appear in the diff at all. The builder change is confined to the
declared artifact, which is what "keep `build_info.json` declared" should mean
in practice: adding environment detail cannot move a receipt.

### `fixtures/arxiv-150k/` was not touched

    git diff --stat -- fixtures/arxiv-150k/     -> 0 lines
    git status --porcelain -- fixtures/arxiv-150k/ -> 0 lines

No hand-edit, no rebuild, as instructed.

### Diffs

| File | +/- | What |
|---|---|---|
| `corpora/build_fixture.py` | +38 / -0 | `torch_receipt()`, its two call sites |
| `fixtures/arxiv-150k.fixture.yaml` | +13 / -3 | 2 embedding lines, changelog comment + 3 relabels, 1 finding |
| `docs/CHARTER.md` | +4 / -1 | 002b row, 003c row, roadmap line |
| `fixtures/arxiv-smoke/build_info.json` | +5 / -2 | rebuild output |
| `fixtures/arxiv-smoke/MANIFEST.sha256` | +1 / -1 | rebuild output |

The arxiv-150k spec diff in full is the two `embedding` lines, the changelog
comment, the three `version: 1` → `build: …` relabels, and the new finding —
nothing else. Confirmed mechanically: every line matching `value`,
`value_before`, `value_after`, `recall_at_10`, `routing_ceiling`,
`storage_amplification`, the copies percentiles, `seed`, `tolerance`,
`status`, `device` and `_sha256` was extracted from both the committed and
working revisions and diffed — **identical**. No measured value, digest, seed,
tolerance or status changed.

`requirements.txt`: `git diff --stat` returns nothing. Untouched, as
instructed.

### Tests and verifier (step 5)

Full suite, 10 passed:

    ok  test_absent_large_artifacts_are_couldnt_check_not_contradicted_synthetic
    ok  test_declared_file_is_still_digest_checked_synthetic
    ok  test_exit_codes_synthetic
    ok  test_kind_split_synthetic
    ok  test_malformed_manifest_raises_synthetic
    ok  test_projection_is_declared_but_still_digest_checked_synthetic
    ok  test_strict_flag_synthetic
    ok  test_three_outcomes_stay_distinct_synthetic
    ok  test_unlisted_files_are_reported_synthetic
    ok  test_verifies_with_and_without_projection_synthetic
    10 passed

Verifier, default:

    arxiv-150k   5 verified, 0 contradicted, 3 couldnt_check   exit 0
    arxiv-smoke  7 verified, 0 contradicted, 0 couldnt_check   exit 0

The smoke fixture verifying at 7 confirms the rebuild's new `build_info.json`
matches the manifest the same run wrote.

## Verification

**Passed**

- Smoke `build_info.json` shows `torch` (`2.14.0+cpu`), `torch_cuda` (null)
  and `cuda_device_name` (null) — present as explicit nulls, reported above.
- arxiv-150k spec diff is exactly the two `embedding` lines, one finding, the
  changelog relabel and its comment; nothing else, verified mechanically.
- Tests pass (10); verifier default exit 0 on both fixtures.
- `fixtures/arxiv-150k/` untouched; `requirements.txt` untouched; arxiv-150k
  not rebuilt; no measured value edited.
- Spec parses under `yaml.safe_load`: 6 findings, 3 changelog entries.
- Charter updated as specified.

**Failed**

Nothing.

**Couldn't check**

- **That `torch_cuda` and `cuda_device_name` populate correctly on a GPU
  build.** Both are null here because this machine has a CPU-only torch wheel,
  which exercises the null path but not the populated one. The populated path
  is three lines guarded by `torch.cuda.is_available()`, and it will first run
  for real on build 3. Until then, the CUDA branch is unexecuted code.
- **Build 2's actual torch version.** Unchanged from 003b: not recorded in
  `fixtures/arxiv-150k/build_info.json`, and this task deliberately did not
  hand-edit that artifact. `2.14.0+cu130` and the device name are in the spec
  as declared values with the caveat comment, and the new finding says so.
  They remain attestation, not measurement.
- **Whether `md.version` would also drop the local segment on the pod's CUDA
  wheel.** I measured the drop on this machine's `+cpu` wheel. PyTorch's CUDA
  wheels usually do carry `+cu130` in their metadata, so `md.version` might
  have sufficed there — but "might, on the other machine" is not a basis for
  a receipt, and `torch.__version__` is correct in both cases.

## Observed, not done

- **`build` is now mixed-typed in the changelog.** YAML parses `1-prep` as the
  string `"1-prep"` and `1`/`2` as integers, so a consumer reading `build`
  across entries gets `str, int, int`. Quoting all three (`"1-prep"`, `"1"`,
  `"2"`) would make the field uniformly a string. The brief specified the
  literal labels, so I wrote them as given.
- **The CUDA branch of `torch_receipt()` has no test.** Rule 8 asks for tests
  where there is a contract; this is environment-dependent code that cannot
  run on this machine, and testing it would mean monkeypatching `torch` —
  worth doing when build 3 gives a real result to compare against, and not
  something this brief asked for.
- **`cuda_device_name` records only the device at index 0.** A multi-GPU pod
  would report the first device regardless of which one embedded. Fine for a
  single-GPU pod; worth revisiting if a build ever uses more than one.
- **No CUDA driver version is recorded**, only the toolkit version torch was
  built against. Driver differences can change numerics; `torch.version.cuda`
  does not capture them.
- **`fixtures/arxiv-150k/build_info.json` will stay incomplete forever.** It
  is build 2's artifact and correctly not hand-edited, so the fixture's own
  environment record is permanently thinner than the schema now supports.
  Build 3 is the only thing that fixes it — which is why the roadmap line and
  the finding both exist.
- **The charter's `004` row still reads `after 003`**, now ambiguous with 003b
  and 003c done. Not in this brief's scope.

## Repo now contains

Modified:

    corpora/build_fixture.py               (+38 / -0: torch_receipt and its call sites)
    fixtures/arxiv-150k.fixture.yaml       (+13 / -3: torch_version, cuda_device,
                                            changelog relabel + comment, one finding)
    docs/CHARTER.md                        (+4 / -1: 002b done, 003c row, roadmap line)
    fixtures/arxiv-smoke/build_info.json   (rebuild output: torch, torch_cuda,
                                            cuda_device_name)
    fixtures/arxiv-smoke/MANIFEST.sha256   (rebuild output: build_info digest)

New:

    tasks/003c-torch-receipt.report.md

Unchanged: `requirements.txt`, every file under `fixtures/arxiv-150k/`, and
the six receipt artifacts of the smoke fixture. No new scratch script was
needed — step 1's rebuild reused
`tasks/scratch/002b-projection-nonfatal-build.py` unmodified.

### Dependencies added

None. torch was already an installed transitive dependency of
sentence-transformers and is pinned at `torch==2.14.0` in `requirements.txt`;
this task only reads its version.

### Not committed

Nothing was committed.

## Blocked on developer

Nothing blocked this task.

For build 3, when it happens: it needs no code change — the builder now
records `torch`, `torch_cuda` and `cuda_device_name` by itself. What it will
produce is the first execution of the CUDA branch, and the values that let the
two declared `embedding` lines in the spec be replaced by recorded ones and
the `torch_version_is_declared_not_recorded` finding retired.
