# Report: 002-canonical-build (Part A only)

Part A is complete. **Part B was not started** — it is developer-runs on
RunPod, and nothing in this task touched the real arXiv dump, which is not on
this machine.

## Repo state expected vs found

The brief expected tasks 001 and 001b committed, `oneground/fixture_verify.py`
carrying the `kind` column, and the `characterization.json` /
`build_info.json` split in place, and said to stop and report if 001b was not
committed.

| Expected | Found |
|---|---|
| 001 committed | yes — `1b00d8d` |
| 001b committed | yes — `a3d05c6 task 001b: reproducible characterization, build_info split` |
| `kind` column in the verifier | yes — `DECLARED_FILES` and `kind_of()` present in the committed blob |
| characterization/build_info split | yes — `write_json_stable`, `build_info.json` write, and the MANIFEST entry all present in the committed blob |

**001b was committed partially.** `a3d05c6` contains the six source and spec
files, but four 001b outputs are still untracked:
`fixtures/arxiv-smoke/build_info.json`, `oneground/test_fixture_verify.py`,
`tasks/001b-reproducible-characterization.report.md`, and
`tasks/scratch/001b-reproducible-characterization-build.py`. I checked the
commit's contents rather than its message: the two things the brief names as
the precondition — the `kind` column and the split — are both in the committed
tree, so the precondition holds and I proceeded. Worth noting because A2 says
"update `test_fixture_verify.py`", and that file exists only in the working
tree.

The brief is again at `tasks/tasks-002-canonical-build.md` rather than
`tasks/002-...`, the same naming deviation as 001 and 001b. Report written to
`tasks/002-canonical-build.report.md` per CLAUDE.md.

## What was done

### A1 — newline pinning

Audited every write in `corpora/build_fixture.py` (`grep` for `open(`,
`np.save`, `stream_writer`, `json.dump`). Five writers, three already safe:

| Writer | Mode | Finding | Action |
|---|---|---|---|
| `write_json_stable()` | `newline="\n"` | pinned in 001b | none |
| `sample.jsonl.zst` | `"wb"` + `.encode()` | bytes through a binary handle, `\n` explicit — no translation possible | none |
| `query_ids.json` | `"w"` text | `json.dump` with no `indent` emits **zero** newline characters, and `ensure_ascii` keeps it ASCII, so no translation can occur | none |
| `np.save` x4 | binary | not text | none |
| `MANIFEST.sha256` | `"w"` text | **CRLF on Windows** — 7 CRLF, 0 bare LF in the committed file | pinned to `encoding="utf-8", newline="\n"` |

So `MANIFEST.sha256` was the only offender, and it is now written the same way
as the JSON artifacts. This is the item I flagged at the end of 001b: the
manifest is the fixture's index of receipts, and a Windows-built and
Linux-built fixture would otherwise carry different manifest bytes for
identical contents — which matters because Part B builds on Linux.

The smoke fixture was rebuilt once (via the A4 script, so one rebuild serves
both steps) and every text artifact now contains zero CRLF. Numbers below.

### A2 — projection kind

`projection.npy` added to `DECLARED_FILES` in `oneground/fixture_verify.py`,
with the reason recorded next to it (UMAP is seeded but not guaranteed
bit-identical across BLAS builds, and the spec marks the projection
illustrative). The module docstring's description of `declared` was extended
to cover both files. Digest checking is unchanged — declared exempts a file
from *reproduction*, never from its digest.

`oneground/test_fixture_verify.py` updated accordingly: `test_kind_split_synthetic`
now asserts `projection.npy` is `declared`, and a new test,
`test_projection_is_declared_but_still_digest_checked_synthetic`, asserts a
tampered `projection.npy` is still reported `contradicted`. 7 tests, all
passing.

### A3 — spec corrections

`fixtures/arxiv-150k.fixture.yaml`, the three named edits:

1. `# computed values with estimator versions` → `# measurement only; versions in build_info.json` — applied.
2. `build_info.json` line comment `# declared` — **already present**, added in 001b. The brief allowed for this ("if not already present"), so this edit produces no diff.
3. `source.snapshot_date: "2026-09-05"` — applied, replacing `TO_BE_FILLED`. `snapshot_sha256` left as `TO_BE_FILLED`, as instructed.

The same comment fix (edit 1 only) applied to `fixtures/arxiv-smoke.fixture.yaml`.
No other edits to either file.

### A4 — pod run script

`corpora/run_arxiv_150k.sh`, covering every bullet in the brief. Design notes
worth stating:

- **The fixture id is derived from the spec**, not hardcoded, so the log
  filename, the verify target and the artifact directory cannot drift apart.
  With the default spec this yields exactly `logs/build-arxiv-150k.log`.
- **Venv activation handles both layouts** — `.venv/bin/activate` on the pod,
  `.venv/Scripts/activate` under Git Bash — so the same script is genuinely
  testable locally rather than a near-copy.
- **`set -o pipefail`** means a builder failure fails the run despite the
  `tee`.
- **Four env vars, not two.** The brief specified `SPEC` and `SOURCE`. I added
  `TARBALL` (the default `/workspace/arxiv-150k-small.tgz` is not writable on
  a laptop) and `SKIP_PROJECTION` (see below). All four default to the
  canonical values, so the pod run sets nothing.
- **`SKIP_PROJECTION` exists to satisfy the acceptance criterion.** Acceptance
  asks for the smoke rebuild to show "7 verified with `projection.npy`
  absent", which requires `--skip-projection`; the canonical build must *not*
  skip it. An env var defaulting to off gives both. `POD_SETUP.md` says
  explicitly to leave it unset.
- **`projection.npy` is tarred if present, with a loud warning if absent**,
  rather than aborting. `build_fixture.project()` already returns `None` when
  umap-learn is missing, so an absent projection is a reachable state; losing
  the whole tarball over it would be the wrong failure mode on a pod the
  developer is about to terminate.
- **The verify invocation is `python oneground/fixture_verify.py fixture verify <id>`.**
  The brief writes it as `oneground/fixture_verify.py arxiv-150k`; the actual
  CLI, built in 001, is `fixture verify <id>`. I used the real one.

### A5 — pod setup notes

`corpora/POD_SETUP.md`, with the developer's steps in the brief's order:
bundle, upload, clone, venv, `requirements.txt`, `kaggle`, `kaggle.json` at
`chmod 600`, dataset download, `nohup ... &` plus `tail -f`. Includes the
expected wall clock with its basis, the sub-2 GB memory guard and how to stop,
what to do when it finishes (download the tarball, terminate the pod, keep the
volume), and a short troubleshooting section.

## Measurements

### CRLF audit — before and after

Method: counting `\r\n` and bare `\n` in raw bytes; `sample.jsonl.zst` was
decompressed first with `zstandard` and its inner content counted.

| Artifact | Before (committed) | After rebuild |
|---|---|---|
| `MANIFEST.sha256` | **7 CRLF**, 0 LF | 0 CRLF, 7 LF |
| `characterization.json` | 0 CRLF, 30 LF | 0 CRLF, 30 LF |
| `build_info.json` | 0 CRLF, 13 LF | 0 CRLF, 13 LF |
| `query_ids.json` | 0 CRLF, 0 LF | 0 CRLF, 0 LF |
| `sample.jsonl.zst` (inner) | 0 CRLF, 2200 LF | 0 CRLF, 2200 LF |

    TOTAL CRLF ACROSS ALL TEXT ARTIFACTS: 0

All five are pure ASCII, so no encoding-dependent bytes either.

### Verifier on the rebuilt smoke fixture

    summary: 7 verified, 0 contradicted, 0 couldnt_check  (digests only; 6 receipt, 1 declared)

Exit code 0, `projection.npy` absent from the directory and the manifest, as
the acceptance criterion requires. Full output:

    digests
      verified      receipt  sample.jsonl.zst       b6383e226a14e631a2e5c875cd658230c194ebe5ac908abea6ea5e52d1fa4c6c
      verified      receipt  vectors.npy            d9f44ded9e68af7495544c9a90da5bfee3798204f77ce0efbd219508268d7a6e
      verified      receipt  queries.npy            2359ce716b2ca7ef75c5d9f4fa4a42924df83eeac5848918b6a823efa7f7433a
      verified      receipt  query_ids.json         0081604bb50d8dd48b4ae5605a05fc894dcd2ae4db41511657464772c911b8e2
      verified      receipt  ground_truth.npy       13919bb5174ebeb4febe037017a2e2b8bbfe4998b3ce261e7989e4649c2a9cce
      verified      receipt  characterization.json  07b576e27e680596d8cb52c59f01dcb18e1039a9be135c48db921e5a56dc30e1
      verified      declared build_info.json        f04a9e4ebda0e5c70fe24812f901fc3efb6e231db255833ca7b5eb004dcbbc74

### Reproduction held across the newline change

`git status` after the rebuild lists `MANIFEST.sha256` as modified and
`characterization.json` as **unmodified** — the rebuilt measurement artifact
is byte-identical to the one committed in 001b (`07b576e2...`), and the five
receipt digests are unchanged from task 001. The manifest changed only because
its own line endings did.

### Script run

Git Bash (`GNU bash 5.3.9(1)-release, x86_64-pc-cygwin`), smoke spec,
synthetic source, `SKIP_PROJECTION=1`.

    SCRIPT EXIT CODE: 0

Last lines of its output:

    tarball contents:
      fixtures/arxiv-smoke/MANIFEST.sha256
      fixtures/arxiv-smoke/characterization.json
      fixtures/arxiv-smoke/build_info.json
      fixtures/arxiv-smoke/query_ids.json
      fixtures/arxiv-smoke/ground_truth.npy
      logs/build-arxiv-smoke.log

      bytes: 44938
      finished: 2026-09-08T16:14:20Z

    Paste to the orchestrator: the TO_BE_FILLED block above, the last 40
    lines of logs/build-arxiv-smoke.log, and this source.snapshot_sha256:
      cc5fc2ef52d68240c4d03b278b10ef174040f41a146062a8395f0581d39ae2a1

    DONE
    /tmp/arxiv-smoke-small.tgz

Wall clock 405 s (6.75 min) start to finish; the builder's own figure for the
build step was 6.6 min. The tarball was extracted to a temp directory to
confirm it is a valid gzip archive with the six expected members.

An earlier run of the same script failed at the `tar` step with
`tar (child): Cannot connect to C: resolve failed`. Cause: I had passed
`TARBALL=C:/Users/...`, and GNU tar reads `host:path` as a remote location.
It is a property of the Windows test path, not of the script — the pod's
`/workspace/arxiv-150k-small.tgz` has no colon — so I re-ran with
`/tmp/arxiv-smoke-small.tgz` and added a comment to the script's header
recording the trap. Worth noting that `set -e` did stop the script correctly;
what hid the failure was my own wrapper piping the script through `grep | tail`,
so the reported exit code was `tail`'s. The re-run captured the script's own
exit code directly.

### Wall-clock extrapolation for the pod (basis for POD_SETUP.md)

Measured, this machine: `os.cpu_count()` = 4, faiss 4 threads, torch 2
threads. Task 001 embedded 2,000 base documents in 566 s = **3.53 docs/s**.

Linear extrapolation to 150,000 documents at that rate: 42,493 s = **11.8 h**.
At 16 vCPU, assuming roughly 4x, that is **~3 h** for embedding, which is 86%
of the smoke run's time and will dominate here too. Consistent with the
brief's ~2–3 h, so POD_SETUP.md states 2–3 h.

This is an extrapolation, not a measurement, and I have flagged the weakest
part of it in POD_SETUP.md: the UMAP projection over 150,000 x 768 has never
been run at that size — every build so far used `--skip-projection` — so the
upper bound is soft.

### Spec diffs

`fixtures/arxiv-150k.fixture.yaml`, complete diff — the two edits that needed
making, zero deletions of anything else:

    @@ -22,7 +22,7 @@ source:
       provider: arxiv.org via Kaggle "Cornell-University/arxiv" (mirrored on Hugging Face)
    -  snapshot_date: TO_BE_FILLED          # date of the metadata dump used
    +  snapshot_date: "2026-09-05"          # date of the metadata dump used
       snapshot_sha256: TO_BE_FILLED        # digest of the raw dump file

    @@ -141,7 +141,7 @@ artifacts:
         - ground_truth.npy          # (2000, 100) int64
    -    - characterization.json     # computed values with estimator versions
    +    - characterization.json     # measurement only; versions in build_info.json
         - build_info.json           # declared
         - projection.npy            # (150000, 2) float32, UMAP

`"2026-09-05"` is the same character width as `TO_BE_FILLED`, so the column
alignment of the trailing comments is unchanged.

`fixtures/arxiv-smoke.fixture.yaml`: the comment fix only, 1 changed line.

### Tests

`python oneground/test_fixture_verify.py` — 7 passed:

    test_declared_file_is_still_digest_checked_synthetic
    test_exit_codes_synthetic
    test_kind_split_synthetic
    test_malformed_manifest_raises_synthetic
    test_projection_is_declared_but_still_digest_checked_synthetic
    test_three_outcomes_stay_distinct_synthetic
    test_unlisted_files_are_reported_synthetic

## Verification

**Passed** — all four Part A acceptance criteria:

- Smoke rebuild: **zero CRLF** in every text artifact (measured above).
- Verifier: **7 verified**, 0 contradicted, 0 couldn't-check, exit 0, with
  `projection.npy` absent.
- A unit test asserts `projection.npy`'s `declared` kind
  (`test_kind_split_synthetic`), plus a second asserting it is still
  digest-checked.
- `run_arxiv_150k.sh` reaches **DONE** on the smoke fixture locally, exit
  code 0, under Git Bash.
- `POD_SETUP.md` exists and contains every step the brief lists, in order.
- The arxiv-150k spec diff shows exactly the named edits (two producing a
  diff, the third already satisfied).

Also checked: both specs still parse under `yaml.safe_load`; the script
passes `bash -n`; the tarball extracts cleanly with its six expected members;
`characterization.json` and the five receipt digests are unchanged from
001b/001, so nothing in this task perturbed a measurement.

**Failed**

Nothing, on the final state. One intermediate failure (the `tar` colon
problem) is described under Measurements with its cause and fix.

**Couldn't check**

- **Everything about the canonical 150k build.** No part of Part B was run.
  The real dump is not on this machine and the brief forbids downloading it.
  Wall clock, peak RSS, UMAP behaviour at 150k, and whether faiss and
  sentence-transformers produce bit-identical output on the pod's CPU are all
  open until Part B runs.
- **`run_arxiv_150k.sh` on Linux.** Its logic is verified on this machine
  under Git Bash, which exercises the same code path apart from the venv
  layout branch (`.venv/bin/activate`, taken only on the pod). I cannot
  execute the Linux branch here.
- **That the pod's tar accepts the invocation.** Tested against GNU tar under
  Git Bash. Standard on Debian/Ubuntu images; a BusyBox-only image would
  differ.
- **`snapshot_date: "2026-09-05"`.** Written as the brief instructed and
  attributed there to the developer's confirmation. I have no way to check it
  against Kaggle from here, and did not try.

## Observed, not done

- **`logs/` is not in `.gitignore`.** The run script creates it, and
  `logs/build-arxiv-smoke.log` is currently untracked-but-committable. On the
  pod the canonical log also gets tarred, so it reaches the repo that way
  anyway. One line (`logs/`) would fix it; not in the brief's scope.
- **No `.gitattributes`.** This machine has `core.autocrlf=true`, so
  `run_arxiv_150k.sh` will be stored LF in the repo and checked out LF on the
  pod — the bundle path in POD_SETUP.md is safe. But `*.sh text eol=lf` would
  make that guarantee explicit rather than incidental. I documented the
  failure mode and its one-line fix in POD_SETUP.md's troubleshooting section
  instead.
- **The four untracked 001b files** listed under "Repo state". In particular
  `oneground/test_fixture_verify.py`, which A2 asked me to update, exists only
  in the working tree — it needs committing for the pod clone to carry it.
  The bundle in POD_SETUP.md step 1 is `--all`, which bundles commits, not the
  working tree, so **anything uncommitted will not reach the pod.** The build
  itself does not need the tests, but it does need every source change from
  this task.
- **`queries.npy` still in neither `.gitignore` group**, unchanged from 001.
- **The `# (2000, 100) int64` comment on `ground_truth.npy`** in the
  arxiv-150k spec looks wrong — 2,000 queries is right, but that line sits
  among the 150k shapes and reads oddly next to `vectors.npy # (150000, 768)`.
  It is in fact correct (2,000 queries x k=100). Noting it only because it
  invites a "fix" that would be wrong.
- **`build_fixture.py` writes `query_ids.json` via `json.dump(..., open(...))`**
  without closing the handle explicitly. Harmless under CPython refcounting
  and unrelated to newlines; would matter on a different interpreter.

## Repo now contains

New:

    corpora/run_arxiv_150k.sh
    corpora/POD_SETUP.md
    tasks/002-canonical-build.report.md
    logs/build-arxiv-smoke.log            (build output, see Observed)

Modified:

    corpora/build_fixture.py              (MANIFEST writer: encoding + newline="\n")
    oneground/fixture_verify.py           (projection.npy -> declared; docstring)
    oneground/test_fixture_verify.py      (projection kind assertions; +1 test)
    fixtures/arxiv-150k.fixture.yaml      (2 lines: snapshot_date, comment)
    fixtures/arxiv-smoke.fixture.yaml     (1 line: comment)
    fixtures/arxiv-smoke/MANIFEST.sha256  (rebuilt, now LF)

Rebuilt and byte-identical, so not shown as modified:
`characterization.json`, `build_info.json`, `vectors.npy`, `queries.npy`,
`query_ids.json`, `ground_truth.npy`, `sample.jsonl.zst`.

### Dependencies added

None. `requirements.txt` unchanged.

### Not committed

Nothing was committed. See "Blocked on developer" — this matters more than
usual for this task.

## Blocked on developer

Part A is not blocked. Part B is developer-runs and was not started.

Before Part B can work, in order:

1. **Commit this task's changes, and the four untracked 001b files.**
   `git bundle create oneground.bundle --all` bundles commits only — the
   working tree does not travel. If the bundle is made now, the pod would get
   a repo without the newline fix, without the projection reclassification,
   without the corrected spec, and **without `corpora/run_arxiv_150k.sh` or
   `POD_SETUP.md` at all**. This is the one hard prerequisite.
2. **Kaggle credentials** — `~/.kaggle/kaggle.json`, step 7 of POD_SETUP.md.
   Never needed on this machine.
3. **A RunPod CPU pod**, 16 vCPU / 40 GB, with the `vecbench` volume at
   `/workspace`. Spend.

Optional, both from "Observed, not done": adding `logs/` to `.gitignore`, and
adding a `.gitattributes` with `*.sh text eol=lf`.

Stopping here as instructed. Part B is not mine to execute.
