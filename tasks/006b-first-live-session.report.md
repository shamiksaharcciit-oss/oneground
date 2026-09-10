# Report: 006b-first-live-session

## Repo state expected vs found

| Expected | Found |
|---|---|
| task 006 committed | yes — `512600d task 006: oneground pod helper, dry-run live, no create outside up` |
| tree clean | yes, apart from the untracked brief |
| volume renamed to `vecbench` | **yes** — `name=vecbench, dc=EU-RO-1, size=50GB, id=rvoku0jgda`. Same id as before, so it is the same volume renamed, not a new one. Stop condition not triggered. |

`RUNPOD_API_KEY` was again absent from this process's environment and present
at Windows user scope. Step 3 of this brief adds exactly that case to
`CLAUDE.md`, so the handling is now the documented one rather than a judgement
call; it was read from user scope into a subprocess environment for each live
call, never printed, logged or persisted.

## What was done

All seven steps. Step 6 took **two live attempts** — the first failed and cost
about four times what the second did, and it is the more useful half of this
report.

### 1. `.gitignore`

`*.code-workspace` added. It matches new files (verified against a hypothetical
path), **but `oneground.code-workspace` was committed in `512600d` and remains
tracked** — `.gitignore` does not apply to tracked files. The rule as briefed
does not achieve what it was presumably meant to achieve; see "Observed, not
done".

### 2. `corpora/POD_SETUP.md`

The two volume references turned out to need **no change**: the file already
said `vecbench` in both places (opening line, step 12), which the rename made
correct again. What the file did need was the helper framing, so:

- new `## Using oneground pod (start here)` section at the top, pointing at
  `docs/POD.md` for the money boundary and naming `sessions/smoke.yaml` as the
  thing to run first after any change to `oneground/pod/`;
- the twelve manual steps retitled `## The manual path (fallback)`;
- the near-duplicate "Running this as a session instead" section that task 006
  appended at the bottom removed, so the file states the helper flow once.

### 3. `CLAUDE.md`

The sentence added verbatim to the Environment section.

### 4. `sessions/smoke.yaml`

The brief's four env vars, plus `TARBALL_LARGE=/workspace/smoke-large.tgz`,
which the brief did not name. Left unset, `run_arxiv_150k.sh` defaults it to
`/workspace/arxiv-150k-large.tgz` and would have written 2,000 smoke vectors
into a file named for the 150k release asset **on the same volume that holds
the real one**. That is a collision with "Do not: touch arxiv-150k", so the
smoke run keeps its own name.

### 5. `plan sessions/smoke.yaml`

Resolved. Output in Measurements.

### 6. The live run

Two attempts, both terminated, nothing left running. Details and root causes in
Measurements.

**Three defects were found by attempt 1 and fixed, each with a regression test
that needs no pod.** They are product bugs in code task 006 shipped, not
environment problems:

1. **`nohup` cannot parse `VAR=value` prefixes.** `start_run` passed the
   session's `run:` string straight to `nohup`, which is a binary, not a shell:
   it execs its first argument. Fixed by routing through `bash -c`
   (`sshx.build_start_command`, split out so it is testable without a pod).
2. **Subprocess output was decoded with the console codepage.** Fixed by
   pinning `encoding="utf-8", errors="replace"`.
3. **`start_run` inherited the 600-second timeout.** Fixed to 60.

A fourth, found while adding the tests: installing pytest in task 006 silently
broke the no-runner path (`python oneground/pod/test_pod.py`), because
`pytest.skip()` then raises pytest's `Skipped` rather than the shim's. The
runner now honours both.

### 7. `docs/POD.md`

`## First live session` appended: date, pod type, both attempts with elapsed
and cost, the three defects, what attempt 2 verified, and the two things this
session exposed that are still unfixed.

### Deviations

- **`TARBALL_LARGE` set**, above.
- **Bugs fixed rather than only reported.** CLAUDE.md rule 2 says report
  adjacent discoveries rather than fix them. These were not adjacent: they were
  the direct cause of step 6 failing, and step 6 is the task. Fixing them was
  the only route to the acceptance criteria.
- **A second `up` was run.** The brief describes one live run. The first
  created a pod that never ran anything, so the acceptance criteria were unmet
  until the second.

## Measurements

### Step 5 — `plan sessions/smoke.yaml`

    session      : smoke   (sessions/smoke.yaml)

      volume     : vecbench
                   id rvoku0jgda, 50 GB
      datacenter : EU-RO-1   (derived from the volume, not the spec)
      gpu        : RTX PRO 4500   [NVIDIA RTX PRO 4500 Blackwell]
                   stock Low
      image      : runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404
      disk       : 20 GB container disk, volume at /workspace
      run        : SPEC=fixtures/arxiv-smoke.fixture.yaml
                   SOURCE=tasks/scratch/001-synthetic-source.json
                   TARBALL=/workspace/smoke-small.tgz
                   TARBALL_LARGE=/workspace/smoke-large.tgz
                   bash corpora/run_arxiv_150k.sh
      price      : $0.34/hr  (live, on-demand, EU-RO-1)
      caps       : max_hours 0.5, max_usd $0.50, max_concurrent 1
      COST CAP   : 0.5 h x $0.34/hr = $0.17   within max_usd
      considered : RTX PRO 4500=$0.34/Low  RTX PRO 6000=$1.69/Low
                   RTX 6000 Ada=unavailable  RTX 4090=unavailable
    EXIT=0

Stock had fallen from `Medium` (task 006, same morning) to `Low`.

### The two attempts

| | attempt 1 | attempt 2 |
|---|---|---|
| session | `20260909-133506` | `20260909-140954` |
| pod | `siz33fs3xais06` | `6ca69zkayfpmtg` |
| created | 13:35:07Z | 14:09:55Z |
| terminated | 13:55:37Z | 14:15:39Z |
| elapsed | **20.5 min** | **5.7 min** |
| deploy → RUNNING → sync → setup | all fine | all fine |
| run launched | **no** | **yes** |
| ended by | `down`, by me | `watch`, automatically |
| est. cost at the real $0.72/hr | **$0.246** | **$0.069** |

Total elapsed across both: 26.2 min; total estimated cost **$0.315**.

### Attempt 1's root cause, reproduced locally for free

The pod log held one line:

    nohup: failed to run command 'SPEC=fixtures/arxiv-smoke.fixture.yaml':
    No such file or directory

Reproduced on the laptop in seconds (`tasks/scratch/006b-nohup-repro.sh`):

    $ nohup FOO=bar bash -c 'echo hi'
    nohup: failed to run command 'FOO=bar': No such file or directory
    $ nohup bash -c 'FOO=bar; echo "ok, FOO=$FOO"'
    ok, FOO=bar

Attempt 1's 20.5 minutes decompose as roughly 10 minutes of legitimate setup
(venv + `pip install`), then **10 minutes of `start_run` hanging on a launch
that had already failed** — the 600-second default timeout. That half was pure
waste and is what the 60-second timeout now prevents.

### Attempt 2 — the full chain

    DONE seen in /workspace/oneground-session.log after 0h 05m.
    Fetching, then terminating.
    fetching /workspace/smoke-small.tgz
      -> <repo>\smoke-small.tgz  (119527 bytes)
      extracting into <repo>
      extracted
    terminating pod 6ca69zkayfpmtg ...
    terminated.
    EXIT=0

The pod's own build finished at 14:14:10Z, ~4 minutes after creation. `watch`
detected `DONE`, fetched, extracted and terminated with no intervention.

**`start_run` still reported a timeout in attempt 2, and the run started
anyway.** The `bash -c` fix worked; what remains is that ssh does not close the
channel after backgrounding the remote command, so `up` reports a failure for a
launch that succeeded. This is why attempt 2 ended with `up` printing
"FAILED after the pod was created" while the build was already running.

### Cost

| | |
|---|---|
| elapsed, attempt 2 | 5.7 min |
| at the **confirmed** $0.34/hr | **$0.0325** |
| at the **actual** $0.72/hr | **$0.0688** |
| `GET /billing/pods` | **0 rows, $0.0000** |

The brief expected under $0.05. At the rate the developer was shown, $0.033 —
under. At the rate actually charged, **$0.069 — over**. The honest figure is
$0.069, and the reason it exceeds the expectation is the pricing defect below,
not the session.

The billing endpoint returned no rows for either pod, hours after termination,
so the **billed** figure is **couldn't-check**. Both cost figures above are
elapsed × rate.

### The price defect — confirmed at $0.34/hr, billed at $0.72/hr

Both pods reported `costPerHr: 0.72`. The developer confirmed $0.34.

`plan` reads GraphQL `lowestPrice(input:{gpuCount:1, dataCenterId:...})
.uninterruptablePrice`, which is a **floor across machine configurations**, not
the price of the machine allocated. The pod that arrived had 32 vCPU / 62 GB
(`tasks/scratch/006b-price-diag.py`) and cost 2.1x the quoted floor.

Consequences, measured:

- The confirmation prompt understated the rate by **2.1x**.
- `COST CAP` arithmetic was wrong: printed $0.17 for 0.5 h, actual worst case
  $0.36. It stayed inside `max_usd: 0.50` **by margin, not by design** — a
  `max_usd` of 0.20 would have been silently breached.
- `status`'s "cost so far" is understated by the same factor, since it uses
  `usd_per_hr_at_create`.
- `watch`'s cap enforcement is **unaffected**: it is time-based
  (`max_hours`), so termination happened correctly regardless of price.

### Verifier on the fetched fixture — 9 verified, 2 contradicted

    verified      receipt  sample.jsonl.zst
    contradicted  receipt  vectors.npy    expected 4d3b19ef..., got d9f44ded...
    contradicted  receipt  queries.npy    expected 8a48a4b8..., got 2359ce71...
    verified      receipt  query_ids.json, ground_truth.npy, characterization.json
    verified      declared build_info.json, projection.npy,
                           ground_view_{base,queries,centroids}.parquet

    summary: 9 verified, 2 contradicted, 0 couldnt_check

`projection.npy` is present and verified, as the brief expected.

**The two contradictions are mixed provenance, not a broken build.** The small
tarball carries 8 of the 11 manifest entries; `vectors.npy`, `queries.npy` and
`sample.jsonl.zst` stay on the volume, so those three remained the laptop's
copies while `MANIFEST.sha256` became the pod's.

The decomposition is sharper than expected, and it is the useful finding:

- `sample.jsonl.zst` also stayed local and **verified** — the pod and the
  laptop produced byte-identical sampled source.
- `query_ids.json` came from the tarball and is byte-identical to the laptop's
  (checked directly against the backup).
- `vectors.npy` and `queries.npy` **differ in bytes**.

So the boundary sits exactly at the embedding step: **sampling is
byte-reproducible across environments; embedding is not**, and every artifact
downstream of embedding inherits that.

I predicted 8 verified / 3 contradicted before the run. The prediction was
wrong about `sample.jsonl.zst`, which is the part that locates the boundary.

### Values agree where bytes do not

All 14 numeric values, laptop (CPU, Windows) vs pod (CPU, Linux):

| field | laptop | pod | delta |
|---|---|---|---|
| `intrinsic_dimensionality` | 22.062073 | 22.062065 | **8e-06** |
| `boundary_crispness` | 0.5295 | 0.5295 | 0 |
| `ambiguous_query_rate` | 0.935 | 0.935 | 0 |
| `skew_top10_share` | 0.1 | 0.1 | 0 |
| `drift_before` / `drift_after` | 0.290588 / 0.277391 | identical | 0 |
| `drift_n_before` / `drift_n_after` | 85 / 115 | identical | 0 |
| `single_node_hnsw.recall_at_10` | 1.0 | 1.0 | 0 |
| `semantic_sharded.recall_at_10` | 0.6345 | 0.6345 | 0 |
| `semantic_sharded.routing_ceiling` | 0.6345 | 0.6345 | 0 |
| `semantic_sharded.storage_amplification` | 1.906 | 1.906 | 0 |
| p50 / p95 / p99 copies | 1 / 4 / 4 | identical | 0 |

Thirteen of fourteen identical; one differs by 8e-06, four orders of magnitude
below published precision. A **fourth** environment agreeing on values while
disagreeing on bytes.

### The pod embedded on CPU

`build_info.json` from the pod:

    device                 cpu
    cuda_device_name       NVIDIA RTX PRO 4500 Blackwell
    torch                  2.14.0+cu130
    torch_cuda             13.0
    python_version         3.12.3
    platform               Linux-6.8.0-138-generic-x86_64-with-glibc2.39
    library_versions       faiss-cpu 1.15.0, numpy 2.5.3,
                           sentence-transformers 6.0.1, umap-learn 0.5.12

`device: cpu` on a GPU pod. Not a bug: `fixtures/arxiv-smoke.fixture.yaml:60`
pins `device: cpu # canonical build is CPU for reproducibility`, and the
builder honours the spec. `fixtures/arxiv-150k.fixture.yaml:55` pins
`device: cuda`, so the canonical build does use the GPU.

The brief's expectation "projection present since the pod spec has cuda" holds
in its conclusion and not in its reason. It also means **this session rented a
GPU it did not use** — pennies here, and nothing checks that a session's
hardware and its fixture spec agree.

The pins took: numpy 2.5.3 and torch 2.14.0+cu130, matching build 3.

### Tests

| suite | result |
|---|---|
| `pytest oneground/ -m "not live"` | **51 passed** (40 pod + 11 fixture) |
| `python oneground/pod/test_pod.py` | **40 passed, 0 failed, 1 skipped** |

Four tests added, all of which fail against the pre-fix code:

- `test_start_command_runs_through_a_shell_not_nohup_directly`
- `test_start_command_survives_a_command_with_quotes`
- `test_start_command_actually_works_in_a_real_shell` — executes the generated
  launch line in a real shell and asserts the env assignment arrived
- `test_subprocess_output_is_decoded_as_utf8_not_the_console_codepage`

## Verification

**Passed**

- Volume `vecbench` resolves; datacenter EU-RO-1 derived from it.
- `plan sessions/smoke.yaml` runs live read-only, exit 0, real price.
- The full session chain: deploy → RUNNING → bundle sync → local-disk venv →
  launch → `DONE` → fetch → extract → **terminate**, unattended after `up`.
- **`ls` shows zero oneground pods.** Confirmed after each attempt and again at
  the end of the task, and corroborated by a raw `GET /pods` returning `[]`.
  Both pods are gone from the account (`status` on the terminated session
  returns HTTP 404, which is the correct reading).
- Smoke fixture rebuilt on the pod agrees with the laptop's on all 14 values.
- 51 tests pass; both test entry points work.
- `.gitignore` matches `*.code-workspace` for untracked files.
- `arxiv-150k` untouched: `git status --porcelain fixtures/arxiv-150k` empty,
  and no session other than smoke was run.

**Failed**

- **Attempt 1's live run.** Diagnosed to root cause, fixed, regression-tested.
- **`up` still reports a spurious failure at `start_run`.** Attempt 2's run
  launched and completed while `up` printed "FAILED after the pod was created".
  Fixed for the *exec* bug; the ssh-channel-close bug remains.
- **The verifier exits 1** on the fetched fixture (2 contradicted). Explained
  above; it is mixed provenance, and I did not move the local files aside to
  produce a green result, because that is changing the inputs to make a check
  pass.

**Couldn't check**

- **Billed cost.** `GET /billing/pods` returned 0 rows for both pods well after
  termination. Both cost figures are elapsed × rate.
- **Why ssh does not return after backgrounding the remote command.** Two
  candidates — a file descriptor still held by the remote session, or the
  reader-thread interaction that the UTF-8 fix addressed — and distinguishing
  them needs another live run.
- **Whether the pod's `vectors.npy` would verify against the pod's manifest.**
  It stayed in `smoke-large.tgz` on the volume; the session does not fetch it
  and the pod is gone. The `contradicted` verdict is about the laptop's copy.
- **Whether `max_concurrent` blocks a second live `up`.** Only ever one pod at
  a time; the stubbed test covers it, the live path does not.

## Observed, not done

- **`oneground.code-workspace` is still tracked.** It was committed in
  `512600d`, and `.gitignore` has no effect on tracked files, so the rule added
  in step 1 does not cover the file it was presumably added for.
  `git rm --cached oneground.code-workspace` is the one-line completion; the
  brief said only "add `*.code-workspace`", so I stopped there.
- **`sessions/arxiv-build.yaml` is now broken.** It still names
  `volume: organic_orange_catfish_volume`, so `plan sessions/arxiv-build.yaml`
  fails to resolve after the rename. The brief scoped the rename edits to
  `POD_SETUP.md`. It is a one-line fix and it blocks the next canonical build.
- **`docs/POD.md` shows the old volume name** in its example spec (line 84) and
  its sample `plan` output (line 114), and `oneground/pod/session.py`'s module
  docstring shows it too (line 9). Same rename, three more places.
- **7 tracked smoke-fixture files now hold the pod's build**, because the brief
  said to extract over `fixtures/arxiv-smoke/`. Combined with the two local
  files the tarball does not carry, the committed fixture would be internally
  inconsistent and `fixture verify arxiv-smoke` exits 1. The laptop's originals
  are preserved at `tasks/scratch/006b-smoke-before/` (12 files). See "Blocked
  on developer".
- **`smoke-small.tgz` (119 KB) sits untracked in the repo root.** `.gitignore`
  covers `*.bundle` but not `*.tgz`, and `outputs.local: ./` puts every fetched
  small tarball there.
- **Nothing checks that a session's hardware matches its fixture spec.** This
  session rented a GPU and embedded on CPU because the two specs disagree, and
  no code compares them.
- **The `setup:` field in a session spec is documentation only.** `plan` prints
  it; nothing executes it. `_setup_script` generates the steps in code, so
  `setup: corpora/POD_SETUP.md` is inert — carried over from task 006 and now
  confirmed against a live run.
- **`up` has no recovery path after a post-create failure.** It correctly tells
  the developer the pod is still billing, but leaves termination to them. Both
  attempts ended with a pod I had to kill by hand from a separate shell.
- **`watch` polls with a fresh SSH connection each time** — unchanged from 006.
- **The `logs/build-arxiv-smoke.log` in the tarball** was extracted into
  `logs/`, which is git-ignored.

## Repo now contains

New:

    sessions/smoke.yaml
    tasks/006b-first-live-session.report.md
    tasks/scratch/006b-volumes.py
    tasks/scratch/006b-price-diag.py
    tasks/scratch/006b-billing.py
    tasks/scratch/006b-nohup-repro.sh
    tasks/scratch/006b-smoke-digests.py
    tasks/scratch/006b-final.py
    tasks/scratch/006b-smoke-before/     (12 files: the laptop's smoke fixture,
                                          preserved before the extract)
    smoke-small.tgz                      (fetched; untracked, unignored)

Modified:

    .gitignore                  +4   (*.code-workspace)
    CLAUDE.md                   +4   (RUNPOD_API_KEY handling)
    corpora/POD_SETUP.md        restructured: helper section at the top,
                                manual steps marked fallback, duplicate removed
    docs/POD.md                 +~70 (First live session)
    oneground/pod/sshx.py       build_start_command, utf-8 decoding, 60 s
                                launch timeout
    oneground/pod/test_pod.py   +4 tests, sshx import, dual skip handling
    fixtures/arxiv-smoke/       7 tracked files replaced by the pod's build:
                                MANIFEST.sha256, build_info.json,
                                characterization.json, ground_truth.npy,
                                ground_view_{base,queries,centroids}.parquet
                                (projection.npy also replaced; git-ignored)

Unchanged: `fixtures/arxiv-150k/` and its spec, `fixtures/arxiv-smoke.fixture.yaml`,
`corpora/build_fixture.py`, `corpora/export_ground_view.py`,
`corpora/run_arxiv_150k.sh`, `oneground/fixture_verify.py`,
`sessions/arxiv-build.yaml`, `docs/CHARTER.md`.

### Dependencies added

None.

### Not committed

Nothing was committed.

## Blocked on developer

Nothing is blocked, and **no pod is running** — that is the first thing to
check and it is confirmed twice over.

Five decisions:

1. **What to do with `fixtures/arxiv-smoke/`.** It currently mixes the pod's 8
   files with the laptop's 2, so it does not verify. Either restore the
   laptop's build from `tasks/scratch/006b-smoke-before/` (a copy back), or
   keep the pod's build and fetch `smoke-large.tgz` from the volume to complete
   it — which needs another pod. My reading is restore: nothing about the pod's
   smoke build is more canonical than the laptop's, and the values are
   identical anyway.
2. **The pricing defect.** `plan` quotes a floor, not the price. I would fix
   this before the next canonical build, where 2.1x is dollars rather than
   cents: have `up` read `costPerHr` from the created pod and terminate
   immediately if it exceeds the confirmed rate by more than a small margin.
3. **`sessions/arxiv-build.yaml`'s stale volume name**, which blocks the next
   canonical build. One line.
4. **The spurious `start_run` timeout.** Cosmetic but it makes a successful
   session look like a failure, which is how attempt 2 ended.
5. **Whether `oneground.code-workspace` should be untracked**, since step 1's
   rule cannot reach it while it stays in the index.
