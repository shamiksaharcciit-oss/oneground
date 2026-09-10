# Report: 003b-canonical-build-2

## Repo state expected vs found

The brief expected task 003 committed, `fixtures/arxiv-150k/` holding build
2's small artifacts extracted over build 1, and `docs/CHARTER.md` present —
stopping if the charter were missing.

| Expected | Found |
|---|---|
| task 003 committed | yes — `595ce9f task 003: publish values; build 2 artifacts; charter; ignore bundles` |
| `docs/CHARTER.md` | present, 143 lines, with the status table and findings paragraph the brief describes |
| build 2 artifacts in `fixtures/arxiv-150k/` | yes — `MANIFEST.sha256`, `build_info.json`, `characterization.json`, `ground_truth.npy`, `query_ids.json`, `projection.npy` |
| working tree clean | yes, apart from the untracked brief |

The charter is present, so I did not stop. Both blockers I raised at the end
of task 003 are resolved: the charter exists, and `oneground.bundle` is now
ignored.

Two things differ from the brief's assumptions, both reported rather than
fixed:

1. **`build_info.json` does not record torch.** Step 1 asks me to confirm it
   records "numpy 2.5.3 and torch 2.14.0+cu130, device cuda". numpy and device
   are there; **torch is not, and cannot be** — `build_fixture.py` builds its
   `library_versions` from a fixed tuple `("numpy", "faiss-cpu",
   "sentence-transformers", "umap-learn")`, which has no torch in it. On a
   `cuda` build torch is the library that did the embedding, so this is the
   one version the receipt most needs and does not have. Not fixed: the brief
   does not ask for a builder change, and changing it now would not
   retroactively record what build 2 ran.
2. **Build 1's MANIFEST is not in the repo.** Build 2 was extracted over build
   1 before task 003 was committed, so the committed
   `fixtures/arxiv-150k/MANIFEST.sha256` is already build 2's. Build 1's
   per-file digests survive only where my task 003 report quoted them in full
   — which covers the five files that were present, but not
   `sample.jsonl.zst`, `vectors.npy` or `queries.npy`, which that report shows
   as `artifact not present` with no digest. This limits how much of finding
   (a) I can evidence from the repo alone; see Measurements.

## What was done

All six steps.

### 1. Spec

Written by `tasks/scratch/003b-canonical-build-2-edit.py`, each substitution
anchored on the exact text it replaces and asserted to occur once:

- the three array digests replaced with build 2's;
- the drift pair `0.523 / 0.549` → `0.524 / 0.551`;
- the array-vs-file comment added to all three array `*_sha256` fields;
- the changelog entry appended;
- the two findings.

The comment went on the line **above** each field rather than trailing it: the
digest lines are already 82 characters, and a trailing comment would have made
them ~180. The association is unambiguous either way.

Only three fields took the comment — `vectors_sha256`, `queries_sha256`,
`ground_truth_sha256`. `source.snapshot_sha256`, `sampling.sample_sha256` and
`embedding.weights_sha256` are `sha256_file` digests of real files, not array
digests, so the comment would be false on them.

### The two findings, and two I had to update

The brief says "append two items". I appended **one** and updated **two
existing** ones, because appending as instructed would have left the spec
self-contradictory:

- **(a) appended** as `digests_are_environment_specific` — new, as specified.
- **(b)** is the index-loss finding, which task 003 already wrote as
  `loss_is_partitioning`. The brief says "keep task 003's wording; update the
  numbers if they changed". They changed: build 1 was 0.9318 / 0.9324, build 2
  is 0.9316 / 0.9323. Appending a second index-loss finding would have left
  build 1's numbers standing beside build 2's in the same list, both presented
  as findings about a fixture whose published values are now build 2's. I
  updated it in place instead.
- **`no_drift_penalty` also had to change.** It quotes "0.523 before / 0.549
  after" — the exact pair step 1 told me to replace. Updating the spec's drift
  values while leaving that finding would have introduced the contradiction
  myself. Now reads 0.524 / 0.551.

Net: 5 findings, all citing build 2. No finding cites a superseded number.

### 2. CLAUDE.md

The CPU-only line replaced with the brief's text. Verified verbatim by
whitespace-normalised comparison against the brief's string: present, and the
old "GPU may be used for exploration only" text is gone. This closes the
conflict I raised at the end of task 003, where the constitution forbade
exactly the build that had just been published.

### 3. docs/CHARTER.md

Status table: `002 B` → done, `003` → done, new row
`| 003b | republish build 2, reconcile docs | done |`. One sentence added to
the findings paragraph, covering crispness/ambiguity, semantic-sharded losing,
and the two builds agreeing on values but not bytes. No other edits.

### 4. `--strict`

`--strict` added to the `fixture verify` parser: exit 2 when nothing is
contradicted but at least one file is couldn't-check; default unchanged. The
report is byte-identical either way — `--strict` changes what the exit code
means, never what is printed. Implemented as `getattr(args, "strict", False)`
so `cmd_verify` stays callable with a bare namespace.

It counts **files** only. Value reproduction is unimplemented and permanently
`couldnt_check`; if that counted, `--strict` would exit 2 unconditionally and
carry no information. Noted in the docstring.

`test_strict_flag_synthetic` covers all four paths: nothing absent (0 both
ways), one absent (0 default, 2 strict), the report unchanged between them,
and a contradiction outranking `--strict` (1). 10 tests pass.

### 5 and 6

Verifier run both ways, and the laptop venv compared against the pod's
recorded versions. Numbers below.

## Measurements

### Recall and ceiling from characterization.json (asked for explicitly)

Read from `fixtures/arxiv-150k/characterization.json`, build 2:

    semantic_sharded recall_at_10    = 0.9316
    semantic_sharded routing_ceiling = 0.9323
    index loss (ceiling - recall)    = 0.000700
                                     -> 14 of 20,000 neighbour slots

Build 1 was 0.9318 / 0.9324, an index loss of 0.0006 and 12 slots. Both builds
round to `0.932` for both fields at the precision the spec publishes, so the
published pair is equal in both while the underlying measurement never is. The
finding says so.

Method: the two stored scalars, subtracted, times 2,000 queries x 10
neighbours.

### Drift, at the file's own precision

    drift_before  0.523523  -> printed 0.524   (n=965)
    drift_after   0.550918  -> printed 0.551   (n=1035)

Confirmed: the file on disk carries build 2's drift values, matching the
brief's `0.524 / 0.551`. Method: `f"{v:.3f}"`, the builder's own formatting.

### Every other published value, build 2 vs build 1 at printed precision

| Value | Build 2 stored | Printed | Build 1 stored | Agree at printed precision |
|---|---|---|---|---|
| intrinsic_dimensionality | 32.553249 | 32.55 | 32.553246 | yes |
| boundary_crispness | 0.036247 | 0.036 | 0.036273 | yes |
| ambiguous_query_rate | 0.8915 | 0.891 | 0.8915 | yes (identical) |
| skew_top10_share | 0.0754 | 0.075 | 0.0754 | yes (identical) |
| single_node_hnsw.recall_at_10 | 0.99695 | 0.997 | 0.997 | yes |
| semantic_sharded.recall_at_10 | 0.9316 | 0.932 | 0.9318 | yes |
| semantic_sharded.routing_ceiling | 0.9323 | 0.932 | 0.9324 | yes |
| storage_amplification | 3.715167 | 3.715 | 3.715147 | yes |
| p50 / p95 / p99 copies | 4 / 4 / 4 | 4 / 4 / 4 | 4 / 4 / 4 | yes (identical) |
| drift_before | 0.523523 | 0.524 | 0.52342 | **no — 0.523 → 0.524** |
| drift_after | 0.550918 | 0.551 | 0.548986 | **no — 0.549 → 0.551** |

The drift pair is the only published value that moved. `drift_after` moved
0.002, `drift_before` 0.001; the tolerance on `drift` is 0.02, so both are
inside it by an order of magnitude. Build 1 values are from the task 003
report and the pre-edit spec.

### Build 1 vs build 2, per artifact

MANIFEST digests are of the `.npy` **files**; build 1's come from the verifier
output quoted in the committed task 003 report.

| Artifact | Build 1 | Build 2 | |
|---|---|---|---|
| `sample.jsonl.zst` | `404cb92e…` (spec field, written from build 1's log) | `404cb92e…` | **identical** |
| `query_ids.json` | `a0f3236c…` | `a0f3236c…` | **identical** |
| `ground_truth.npy` | `a0a4354a…` | `24fd8525…` | differs |
| `characterization.json` | `a8ed5536…` | `06cba393…` | differs |
| `build_info.json` | `873c9d6d…` | `ae283833…` | differs |
| `projection.npy` | `cb17b756…` | `be5b5016…` | differs |
| `vectors.npy` | not recoverable | `73c0b870…` | — |
| `queries.npy` | not recoverable | `f7385cd2…` | — |

`sample.jsonl.zst` is the interesting one and it is checkable without build 1's
MANIFEST: `sampling.sample_sha256` in the spec was written in task 003 from
**build 1's** log as `404cb92e…`, and build 2's MANIFEST independently lists
`404cb92e…` for the same file. Two environments, same sampled bytes.

`vectors.npy` and `queries.npy` file digests cannot be compared — build 1's
were never committed. But the **array** digests can, and they are what the spec
publishes: `90ffb256… → 414e1484…` and `f1b7b015… → 87718975…`. The embedding
bytes differ; that is the root of every downstream difference.

So finding (a)'s claim decomposes into: sampling receipts identical
(2 artifacts, evidenced), embedding output different (2 array digests,
evidenced), everything downstream different (4 artifacts, evidenced), all
published values equal at printed precision except drift within tolerance
(table above).

### MANIFEST vs the files present

    sample.jsonl.zst       ABSENT (release asset)
    vectors.npy            ABSENT (release asset)
    queries.npy            ABSENT (release asset)
    query_ids.json         match
    ground_truth.npy       match
    characterization.json  match
    build_info.json        match
    projection.npy         match

All five present artifacts match build 2's manifest. `build_info.json` matching
also confirms the projection succeeded on the pod — a failure would have
rewritten it with `"projection": "failed"` and reissued the manifest (task
002b), and no `projection` key is present.

### build_info.json (build 2)

    built_at        2026-09-08T21:03:01Z
    device          cuda
    platform        Linux-6.8.0-111-generic-x86_64-with-glibc2.39
    python_version  3.12.3
    library_versions  faiss-cpu 1.15.0, numpy 2.5.3,
                      sentence-transformers 6.0.1, umap-learn 0.5.12

**numpy 2.5.3 — confirmed**, the pin honoured, and the discrepancy I flagged
in task 003 (build 1 ran 2.1.2) is resolved. **device cuda — confirmed.**
**torch — not recorded**, see "Repo state" above; the brief's
`torch 2.14.0+cu130` cannot be confirmed from the artifact.

### Step 6 — laptop venv vs the pod

`pip freeze` in `.venv` against `build_info.json`:

| Package | Laptop `.venv` | Pod (build 2) | |
|---|---|---|---|
| numpy | 2.5.3 | 2.5.3 | match |
| faiss-cpu | 1.15.0 | 1.15.0 | match |
| sentence-transformers | 6.0.1 | 6.0.1 | match |
| umap-learn | 0.5.12 | 0.5.12 | match |
| torch | 2.14.0 | **not recorded** | cannot compare |

All four recorded libraries match exactly, and all four match
`requirements.txt`. torch is 2.14.0 on the laptop against the brief's stated
`2.14.0+cu130` on the pod: the same upstream version, different wheel (CPU vs
CUDA 13.0). Reported, not fixed, as instructed.

### Verifier, both paths

Default:

    digests
      couldnt_check receipt  sample.jsonl.zst       artifact not present (release asset, or not built)
      couldnt_check receipt  vectors.npy            artifact not present (release asset, or not built)
      couldnt_check receipt  queries.npy            artifact not present (release asset, or not built)
      verified      receipt  query_ids.json         a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
      verified      receipt  ground_truth.npy       24fd8525fe5b63ab3a81ed90ba47b2dced90e001ef8dfa3fcc027ba8cff102f9
      verified      receipt  characterization.json  06cba3933df215de426560febd5e94b5161de7c69a6b37f9b8d2473fc91c8abd
      verified      declared build_info.json        ae283833bf0060641d4c3872e25fb642f9e8212f37052e303b1a9c571be970ec
      verified      declared projection.npy         be5b5016439154389b367a2d17c6b7965a4e405fd3c6237dea9f043c16dd12e2

    summary: 5 verified, 0 contradicted, 3 couldnt_check  (digests only; 6 receipt, 2 declared)

Exit **0**. With `--strict`, byte-identical output, exit **2**.

The smoke fixture is unaffected: 7 verified, 0 contradicted, 0 couldn't-check,
exit 0.

### Diffs

`fixtures/arxiv-150k.fixture.yaml`: **32 insertions, 11 deletions** — three
digests (3+3 with their comments), the drift pair (2), the changelog (5), the
two updated findings (7 lines changed), and the new finding (13).

Seeds, tolerances, params, definitions, sampling rules, `status`, `device`, and
the two non-array digest fields are byte-identical to the committed version:
extracted from both revisions with one grep and diffed — identical.

`CLAUDE.md`: 2 lines out, 5 in, the single bullet.
`docs/CHARTER.md`: status table rows and one sentence.

### Tests

10 passed, including the new one:

    ok  test_strict_flag_synthetic

## Verification

**Passed**

- Spec carries build 2's three array digests and drift pair; both findings
  present (one appended, one updated — see below); the array-digest comment is
  on all three array fields and only those; changelog appended; the diff shows
  only these changes.
- `CLAUDE.md` line replaced verbatim (whitespace-normalised match against the
  brief's text; old line absent).
- Charter updated: `002 B` done, `003` done, `003b` row added, one sentence
  under the findings paragraph.
- Verifier: default **exit 0** with 5 verified and 3 couldn't-check;
  `--strict` **exit 2**. Report identical between them.
- `characterization.json` on disk confirmed to carry build 2's drift values at
  the file's own precision, and recall/ceiling reported.
- `build_info.json` confirmed for numpy 2.5.3 and device cuda.
- Spec parses under `yaml.safe_load`: 5 findings, 3 changelog entries.
- 10 tests pass; smoke fixture still verifies.

**Failed**

Nothing.

**Couldn't check**

- **torch's version on the pod.** Not recorded in `build_info.json`, and the
  builder cannot record it. The brief's `2.14.0+cu130` is taken on the
  developer's word; I can neither confirm nor contradict it from any artifact.
  For a `cuda` build this is the version that most determines the embedding
  bytes.
- **Build 1's `vectors.npy` / `queries.npy` / `sample.jsonl.zst` file
  digests.** Not preserved in the repo. The array digests carry the same
  argument for the first two, and the spec field carries it for the third, so
  finding (a) is still evidenced — but not from build 1's own manifest.
- **Whether the drift movement is the embedding or the estimator.** The pair
  moved 0.001 / 0.002 while everything else held at printed precision. Drift is
  the only value computed from a k-means fitted on a *subset* (pre-2019
  records), so it is the most sensitive to small changes in the vectors — but I
  cannot show that without both builds' `vectors.npy`, and neither is here.
- **Value reproduction**, unchanged: unimplemented, always `couldnt_check`.
- **That build 2's values are reproducible anywhere else.** Two builds is one
  comparison. Both ran on the same GPU model, same platform string, same
  Python 3.12.3, differing only in the package environment.

## Observed, not done

- **The charter's `002b` row still reads `in progress`.** Task 002b was
  completed and committed (`3092b67`, `c48d785`). The brief listed exactly
  which rows to change and said "No other edits", so I left it. It is the only
  stale row in a table this task otherwise brought current.
- **`build_info.json` records no torch, and no CUDA/driver information.**
  Adding `torch` to the builder's version tuple is a one-line change and would
  make the next build's receipt complete. For a GPU build, the device string
  `cuda` without a torch build identifier is thin: `2.14.0+cu130` and
  `2.14.0+cu121` would not be distinguishable in the record.
- **The changelog now has three entries all labelled `version: 1`.** Each was
  specified that way by its brief. A reader looking for which entry describes
  the current artifacts has only the note text to go on.
- **`fixture.status` is still `built`, not `verified`.** Correct as things
  stand — value reproduction does not exist, so nothing has verified this
  fixture. Worth stating because the spec's own `verification.passes_when`
  describes a check no code performs yet.
- **The spec's `verification.note`** ("couldnt_check is reported when a
  dependency version differs from the pinned one") is now satisfiable for the
  four recorded libraries and unsatisfiable for torch, since the version is not
  in the record to compare against.
- **`sampling.sample_sha256` and `source.snapshot_sha256` did not get the
  array comment** — correctly, they are file digests. But nothing in the spec
  says so, so the distinction is now documented on three fields and implicit on
  the other three.

## Repo now contains

Modified:

    fixtures/arxiv-150k.fixture.yaml   (+32 / -11: build 2 digests, drift pair,
                                        array comments, changelog, findings)
    CLAUDE.md                          (canonical-build bullet replaced)
    docs/CHARTER.md                    (status table, one findings sentence)
    oneground/fixture_verify.py        (--strict flag, docstring)
    oneground/test_fixture_verify.py   (test_strict_flag_synthetic)

New:

    tasks/003b-canonical-build-2.report.md
    tasks/scratch/003b-canonical-build-2-crosscheck.py
    tasks/scratch/003b-canonical-build-2-edit.py

Unchanged: `requirements.txt` (step 6 is report-only), every artifact in
`fixtures/arxiv-150k/` and `fixtures/arxiv-smoke/`. Nothing was rebuilt or
recomputed.

### Dependencies added

None.

### Not committed

Nothing was committed.

## Blocked on developer

Nothing blocked this task.

Three decisions, none urgent:

- **Whether to add torch to `build_fixture.py`'s version tuple**, so a GPU
  build's receipt records the library that produced the vectors. It would not
  fix build 2's record, only the next one's.
- **The charter's stale `002b` row**, left untouched under "No other edits".
- **Whether appending finding (b) rather than updating `loss_is_partitioning`
  in place was what you intended.** I updated in place, and also updated
  `no_drift_penalty`, so that no finding in the spec cites a superseded
  number. If you wanted both index-loss findings kept side by side as a
  build-1/build-2 record, say so and I will restore the build 1 one with an
  explicit label.
