# Report: 003-fixture-publish

## Repo state expected vs found

The brief expected task 002b committed and `fixtures/arxiv-150k/` present with
the small artifacts from the pod tarball, and said to stop if any of the first
five was missing.

| Expected | Found |
|---|---|
| 002b committed | yes — `3092b67`, plus `c48d785` carrying the addendum |
| `MANIFEST.sha256` | present, 8 entries |
| `characterization.json` | present |
| `build_info.json` | present |
| `query_ids.json` | present, 2,000 unique ids |
| `ground_truth.npy` | present, (2000, 100) int64 |
| `projection.npy` ("if UMAP completed") | **present**, (150000, 2) float32 — UMAP completed |

All five required artifacts are present, so I proceeded. Three things differ
from what the brief anticipated:

1. **`docs/CHARTER.md` does not exist**, and never has. `git log --all --
   '*CHARTER*'` returns nothing and `git ls-files docs/` lists only
   `docs/README.md`. Commit `3092b67`'s message ends "; charter", but its
   diffstat shows no such file was added. **Step 5 could not be executed** —
   there is no status table to update and no findings section to add a
   sentence to. Everything else in the brief was done. See "Blocked on
   developer".
2. **`oneground.bundle` (untracked) sits in the repo root** — the bundle used
   to seed the pod. Not ignored, so it is currently committable.
3. **The pod did not run the pinned numpy.** `requirements.txt` pins
   `numpy==2.5.3`; `build_info.json` records `numpy 2.1.2`. Details under
   Measurements; this is the one thing in this report that could bear on
   whether the published values are reproducible.

## What was done

Steps 1, 2, 3, 4 and 6. Step 5 is blocked, above. Nothing was rebuilt or
recomputed — this task publishes.

### 1. Value cross-check

`tasks/scratch/003-fixture-publish-crosscheck.py` loads the local
`characterization.json` and `build_info.json` and re-applies the builder's own
print formatting to each stored value (`:.2f` for LID, `:.3f` for the rest,
`v if isinstance(v, int) else round(v, 3)` for the `semantic_sharded` dict),
then compares against the values block in the brief. **17 of 17 match, 0
mismatch.** Table under Measurements.

### 2. Spec fields written

`tasks/scratch/003-fixture-publish-edit.py` performs each substitution
anchored on the exact line it replaces, asserting a single occurrence, so a
miss or a double-hit fails loudly rather than half-editing the spec. Written:
`status: built`, the seven digest/version fields, `device: cuda` with the
required comment, every characterization value, every reference-results value,
the two new `p50_copies` / `p95_copies` lines, and the changelog entry.

### 3. `findings:` block

Four entries appended at the end of the spec, with ids
`no_crisp_boundaries`, `semantic_sharded_loses`, `no_drift_penalty`,
`loss_is_partitioning`, plus a header comment recording that these are
descriptive of arxiv-150k under the configurations fixed above and are not
transferable to another corpus.

**The fourth finding does not say what the brief asked it to say.** The brief's
wording is "index loss is zero (recall = routing ceiling); all loss is
partitioning." That is true of the *published* numbers and false of the
*measured* ones. `characterization.json` holds `recall_at_10: 0.9318` and
`routing_ceiling: 0.9324`. Both round to `0.932` at the three decimals the log
prints and the spec publishes, which is why they look identical — but the gap
is 0.0006, or 12 of 20,000 neighbour slots. So I wrote the finding as
"essentially all of the semantic-sharded loss is partitioning, not the index …
the index loss is negligible, not zero", with both full-precision numbers and
the rounding effect stated. Writing "index loss is zero" into a fixture spec
would have published a claim the fixture's own measurement artifact
contradicts. The substance of the finding — that the loss is partitioning, not
the index — is unchanged and, if anything, better supported by giving the
number.

For contrast: on the smoke fixture (task 002b) the two were exactly equal at
full precision, 0.6345 and 0.6345. The pattern held there; it does not here.

### 4. Verifier

The verifier did **not** fail hard on the missing large artifacts — absence was
already reported as `couldnt_check`, never `contradicted`. What did not match
the acceptance criterion was the exit code: the contract I wrote in task 001
returned 2 when anything was couldn't-check, so this run exited 2 rather than
the required 0.

Changed so that **only a contradiction is a failure**: `return 1 if
counts[CONTRADICTED] else 0`. The docstring now states the reasoning — a
contributor who cloned the repo without the large release artifacts should not
see a failure, because their fixture is not broken, it is incomplete, and the
report says which. `couldnt_check` is still never rounded up to `verified` in
the output, and the summary line still counts it; only the exit code treats
absence as non-fatal. The per-file detail text also changed from "not present
(not committed, or not built)" to "artifact not present (release asset, or not
built)", matching the brief's phrasing.

Two tests cover it: `test_exit_codes_synthetic` updated (listed-but-absent now
asserts 0, contradiction still asserts 1), and a new
`test_absent_large_artifacts_are_couldnt_check_not_contradicted_synthetic`
reproducing the fresh-clone view — the three release-asset artifacts absent,
five present — asserting the absent ones are `couldnt_check` and explicitly
*not* `contradicted`, the present ones `verified`, and the exit code 0.
9 tests pass.

## Measurements

### Every value written, against the log

Method: the log column is the brief's values block; the stored column is the
raw number in `fixtures/arxiv-150k/characterization.json`; the written column
is what now stands in `fixtures/arxiv-150k.fixture.yaml`. The brief specified
"at the precision printed", so written == log throughout.

| Spec field | Log | Stored (full precision) | Written |
|---|---|---|---|
| `source.snapshot_sha256` | `99dc9b05…ef7b` | `99dc9b05…ef7b` (build_info) | `99dc9b05…ef7b` |
| `sampling.sample_sha256` | `404cb92e…3655` | `404cb92e…3655` (MANIFEST) | `404cb92e…3655` |
| `embedding.weights_sha256` | `c7c1988a…67d7` | — | `c7c1988a…67d7` |
| `embedding.library_version` | `6.0.1` | `6.0.1` (build_info) | `6.0.1` |
| `embedding.vectors_sha256` | `90ffb256…f573` | — | `90ffb256…f573` |
| `queries.queries_sha256` | `f1b7b015…cfed` | — | `f1b7b015…cfed` |
| `ground_truth.ground_truth_sha256` | `ff231cc9…21df` | — | `ff231cc9…21df` |
| `characterization.intrinsic_dimensionality.value` | 32.55 | 32.553246 | 32.55 |
| `characterization.boundary_crispness.value` | 0.036 | 0.036273 | 0.036 |
| `characterization.ambiguous_query_rate.value` | 0.891 | 0.8915 | 0.891 |
| `characterization.skew_top10_share.value` | 0.075 | 0.0754 | 0.075 |
| `characterization.drift.value_before` | 0.523 (n=965) | 0.52342 (n=965) | 0.523 |
| `characterization.drift.value_after` | 0.549 (n=1035) | 0.548986 (n=1035) | 0.549 |
| `reference_results.single_node_hnsw.recall_at_10` | 0.997 | 0.997 | 0.997 |
| `reference_results.semantic_sharded.recall_at_10` | 0.932 | **0.9318** | 0.932 |
| `reference_results.semantic_sharded.routing_ceiling` | 0.932 | **0.9324** | 0.932 |
| `reference_results.semantic_sharded.storage_amplification` | 3.715 | 3.715147 | 3.715 |
| `reference_results.semantic_sharded.p50_copies` | 4 | 4 | 4 (new line) |
| `reference_results.semantic_sharded.p95_copies` | 4 | 4 | 4 (new line) |
| `reference_results.semantic_sharded.p99_copies_per_vector` | 4 | 4 | 4 |

`embedding.weights_sha256`, `vectors_sha256`, `queries_sha256` and
`ground_truth_sha256` have no "stored" counterpart: the builder prints those as
`sha256_array(...)` over the raw array bytes, whereas `MANIFEST.sha256` digests
the `.npy` *files* (header included). The two are different by construction, so
the MANIFEST's `54185c5f…` for `vectors.npy` is not comparable to the spec's
`90ffb256…`. They are taken on the log's authority; I cannot recompute them
without the arrays.

### The rounding that hides an index loss

    semantic_sharded recall_at_10    = 0.9318
    semantic_sharded routing_ceiling = 0.9324
    index loss (ceiling - recall)    = 0.000600  -> 12 of 20,000 neighbour slots
    both round to 0.932 at the log's 3 decimals: True

Obtained by subtracting the two stored values and multiplying by
2,000 queries x 10 neighbours. This is the basis for rewording finding 4.

### build_info.json, and the numpy discrepancy

    built_at        2026-09-08T20:04:26Z
    device          cuda
    platform        Linux-6.8.0-111-generic-x86_64-with-glibc2.39
    python_version  3.12.3
    library_versions  faiss-cpu 1.15.0, numpy 2.1.2,
                      sentence-transformers 6.0.1, umap-learn 0.5.12

`device: cuda` and `python_version: 3.12.3` confirm both deviations the brief
recorded. But comparing against `requirements.txt`:

| Package | Pinned | Pod ran | |
|---|---|---|---|
| faiss-cpu | 1.15.0 | 1.15.0 | match |
| sentence-transformers | 6.0.1 | 6.0.1 | match |
| umap-learn | 0.5.12 | 0.5.12 | match |
| **numpy** | **2.5.3** | **2.1.2** | **differs** |

The spec's own `verification.note` reads: "couldnt_check is reported when a
dependency version differs from the pinned one; it is never rounded up to
verified." By that rule, once value reproduction exists, this build's values
will be `couldnt_check` against any environment honouring the pin. Not
something this task can fix — the values are what the pod produced — but it
should be settled before the fixture is called `verified`.

### Corroboration from the artifacts that are present

I cannot check `vectors.npy`, `queries.npy` or `sample.jsonl.zst`, but the
artifacts that did arrive independently corroborate the log's shape claims
(`numpy.load`, `json.load`):

    ground_truth.npy   (2000, 100) int64      -> 2,000 queries, k = 100
    projection.npy     (150000, 2) float32    -> 150,000 base vectors
    query_ids.json     2,000 ids, all unique
    gt id range        0 .. 149999             consistent with a base of 150,000
    hot_categories     8                       matches "hot categories 8"
    drift n_before + n_after = 965 + 1035 = 2000   accounts for every query

The log's "base 150,000 · queries 2,000 · hot categories 8" is therefore
corroborated by three independent artifacts, not taken on trust.

The eight hot categories are `astro-ph`, `cond-mat.mes-hall`, `cs.CL`,
`cs.CV`, `cs.LG`, `hep-ph`, `hep-th`, `quant-ph` — from
`characterization.json`. The real corpus has enough categories for the spec's
"top 5%" rule to select 8, against the degenerate 1 the smoke fixture produced
(task 001).

### MANIFEST against the local files

Recomputed sha256 for every present file:

    sample.jsonl.zst    ABSENT (release asset)
    vectors.npy         ABSENT (release asset)
    queries.npy         ABSENT (release asset)
    query_ids.json      match
    ground_truth.npy    match
    characterization.json  match
    build_info.json     match
    projection.npy      match

All five present artifacts match the manifest the pod wrote. `build_info.json`
matching also confirms the projection succeeded on the pod: had it failed, the
builder would have rewritten `build_info.json` with `"projection": "failed"`
and reissued the manifest (task 002b), and there is no `projection` key.

### Verifier output

    fixture: arxiv-150k
    directory: fixtures\arxiv-150k
    manifest: MANIFEST.sha256 (8 files listed)

    digests
      couldnt_check receipt  sample.jsonl.zst       artifact not present (release asset, or not built)
      couldnt_check receipt  vectors.npy            artifact not present (release asset, or not built)
      couldnt_check receipt  queries.npy            artifact not present (release asset, or not built)
      verified      receipt  query_ids.json         a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
      verified      receipt  ground_truth.npy       a0a4354a59ea12ca6b718718087e048cc79b3d3c3f54f33701b544d1a73165ca
      verified      receipt  characterization.json  a8ed5536e9d776122af4a29856a290a66c69dc89089daa9640e82bbac89f3f1f
      verified      declared build_info.json        873c9d6d42aefad15c0ba9e8c35830f424e7136fcce451554f03b74d23bafd84
      verified      declared projection.npy         cb17b756b562fdce97169788594d0fa98a1756da93eee018b16c49c0e0bf1f1f

    values
      couldnt_check characterization and reference_results (value reproduction not implemented)

    summary: 5 verified, 0 contradicted, 3 couldnt_check  (digests only; 6 receipt, 2 declared)

Exit code **0**. The pod's own verifier reported 8 verified / 0 contradicted /
0 couldn't-check, with all eight artifacts on the volume; the difference here
is purely which files travelled in the small tarball.

The smoke fixture still verifies after the exit-code change: 7 verified,
0 contradicted, 0 couldn't-check, exit 0.

### Spec diff

`git diff --numstat`: **57 insertions, 20 deletions**. The 20 deletions are the
20 value lines replaced. The insertions are those 20, plus `p50_copies` and
`p95_copies` (2), the changelog entry (5), and the `findings` block (30).

Seeds, tolerances, thresholds, params, definitions and sampling rules are
byte-identical to the committed version — extracted with a grep over
`seed:`, `tolerance:`, `k:`, `target_size:`, `count:`, `params:`, `1.20`,
`1.10`, `definition`, `rule:`, `text_template` from both revisions and diffed:
identical.

### Tests

9 passed, including the two touching this task:

    ok  test_absent_large_artifacts_are_couldnt_check_not_contradicted_synthetic
    ok  test_exit_codes_synthetic

## Verification

**Passed**

- Every one of the 17 checkable values in the brief's block matches
  `characterization.json` / `build_info.json` under the builder's own print
  formatting. 0 mismatches, so step 1's stop condition was not triggered.
- The spec has **no remaining `TO_BE_FILLED` field**; `status: built`.
  (`grep` finds one remaining occurrence of the string, on line 9 — the header
  comment that explains the convention. It is prose, not a field.)
- Verifier: present files verified, absent large files couldn't-check, **exit
  0**, nothing contradicted.
- Spec diff touches only the named fields plus `findings` and `changelog`; no
  seed, tolerance, definition or sampling rule changed.
- The spec parses under `yaml.safe_load` with 4 findings and 2 changelog
  entries.
- Shapes and counts in the log are corroborated by three independent local
  artifacts.

**Failed**

Nothing failed. One instruction could not be carried out: step 5, because
`docs/CHARTER.md` does not exist.

**Couldn't check**

- **`embedding.vectors_sha256`, `queries_sha256`, `ground_truth_sha256`,
  `weights_sha256`.** These are digests over raw array bytes (and over the
  model weights), not over files in the manifest. `vectors.npy` and
  `queries.npy` are not here, so three of them cannot be recomputed locally at
  all. `ground_truth.npy` *is* here, but the spec's value is
  `sha256_array(gt)` while the manifest's is `sha256_file`, and only the
  latter is independently checkable — it matches. All four are published on
  the log's authority.
- **Whether the published values are reproducible.** Value reproduction is
  still unimplemented, and the numpy pin was not honoured on the pod. Nobody
  has yet re-derived these numbers on a second machine.
- **The 12 lost neighbour slots.** I can compute the aggregate index loss from
  the two stored scalars but not attribute it — which queries, which shards —
  without `vectors.npy` and the ground truth arrays together.
- **That `snapshot_sha256` identifies the dump the developer intended.**
  `99dc9b05…` is what the pod hashed and what `build_info.json` records; that
  it corresponds to the 2026-09-05 Kaggle dump is the developer's attestation,
  set in task 002.

## Observed, not done

- **`docs/CHARTER.md` is missing** — step 5. I did not create it: the brief
  says "update … status table" and "add one sentence under findings", which
  presumes an existing document whose structure I would otherwise be
  inventing, and CLAUDE.md treats `docs/` as read-only except for a named
  file and a named change. Creating a charter from nothing is not that change.
- **The finding-4 rewording**, described under "What was done". If the
  intended claim really is exact equality, then `characterization.json`
  contradicts it and the reference implementation would need looking at, not
  the wording.
- **numpy 2.1.2 vs the pinned 2.5.3.** Flagged above. Either the pin moves to
  what was actually used, or the next build honours the pin; leaving them
  divergent means the fixture's own verification note will classify its own
  canonical build as `couldnt_check`.
- **Exit code 2 no longer exists**, so a caller can no longer distinguish
  "fully verified" from "verified as far as the files present allow" by exit
  code alone — only by reading the summary line. A `--strict` flag restoring
  the old behaviour for CI would recover it. Not in this brief's scope.
- **The changelog now has two entries both labelled `version: 1`**, because
  the brief specified `- version: 1` for the new entry and the existing one is
  also 1. Written as instructed. A reader may expect the second to be
  version 2, or the first to be superseded rather than kept.
- **`oneground.bundle` sits untracked in the repo root** and is not ignored.
  It is a full copy of the repository history; committing it would be odd.
- **The spec still says `# canonical build is CPU for reproducibility` nowhere
  now**, but `CLAUDE.md` still states "Canonical fixture builds are CPU,
  single deterministic path. GPU may be used for exploration only, never for a
  published artifact." The canonical build was on an RTX 4090 and is being
  published. The brief authorises the spec change; it does not authorise
  changing CLAUDE.md, and I have not. **These two documents now disagree**,
  and the constitution is the one that says a published artifact may not come
  from GPU.
- **`fixtures/arxiv-150k/` has no `.gitignore` coverage** matching the smoke
  fixture's: the pattern `fixtures/*/vectors.npy` etc. already applies, and
  the large files are absent anyway, so nothing is at risk today.

## Repo now contains

Modified:

    fixtures/arxiv-150k.fixture.yaml   (+57 / -20: values, status, device,
                                        p50/p95 lines, changelog, findings)
    oneground/fixture_verify.py        (exit-code contract, docstring,
                                        absent-file detail text)
    oneground/test_fixture_verify.py   (exit-code test updated, one test added)

New:

    tasks/003-fixture-publish.report.md
    tasks/scratch/003-fixture-publish-crosscheck.py
    tasks/scratch/003-fixture-publish-edit.py

Untracked, arrived with the pod tarball, not created by me:

    fixtures/arxiv-150k/MANIFEST.sha256
    fixtures/arxiv-150k/build_info.json
    fixtures/arxiv-150k/characterization.json
    fixtures/arxiv-150k/ground_truth.npy
    fixtures/arxiv-150k/projection.npy
    fixtures/arxiv-150k/query_ids.json
    oneground.bundle

Not created: `docs/CHARTER.md`.

Nothing was rebuilt. No fixture artifact was written or altered by this task.

### Dependencies added

None.

### Not committed

Nothing was committed.

## Blocked on developer

- **`docs/CHARTER.md` (step 5).** It does not exist in the working tree or
  anywhere in history. Either supply it, or say what the status table and
  findings section should contain and I will write it. What step 5 asked for
  is unambiguous once the file exists: mark 002 B done and 003 done, and add a
  sentence recording the crispness result (boundary crispness 0.036 with an
  ambiguous-query rate of 0.891 — effectively no crisp region boundaries under
  k-means-256).
- **Decision on finding 4.** I published "the index loss is negligible, not
  zero" with the 0.9318 / 0.9324 pair. If you want the brief's exact wording
  instead, say so and I will change it — but the spec would then assert
  something its own `characterization.json` contradicts.
- **Decision on the numpy pin**, 2.5.3 pinned vs 2.1.2 used.
- **The CPU-only rule in CLAUDE.md** versus a canonical build published from
  an RTX 4090. The constitution needs amending or the deviation needs
  recording there; I did not edit CLAUDE.md.
