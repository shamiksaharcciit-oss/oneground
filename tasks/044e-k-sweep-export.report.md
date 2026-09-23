# Report: 044e-k-sweep-export

## The page's verdict cannot be rebuilt from this repository

**Leading, because it is the third form of one gap and the only one still
open.**

`site/teaser/data/values.json` publishes a decision — 8 options, 1 meets, 6
fails, 1 couldn't-check — built from a verify run measured on a pod,
`environment_id tf8sd2usxbblsm`, dated 2026-09-09, in a checkout called
`oneground-012`. **Neither that run's `report.json` nor its `verify.json` is
in this repository.** Two gitignored scratch snapshots mention the id; neither
is usable as an export input.

`--report-only` takes a `--report` and rebuilds `verdict` and `verify` from
it. There is no argument that reproduces the page. Pointing it at the local
`runs/arxiv-smoke` — `local:windows-amd64`, 2026-09-13 — would have replaced a
pod-measured decision with a laptop-measured one in order to land a citation.

> **A published decision whose inputs are not in the repository that publishes
> it.** Until that pod run's `report.json` and `verify.json` land here,
> **nobody can rebuild the page's verdict from this tree** — not us, not core,
> not a future maintainer. The page can be re-published; the decision on it
> cannot be re-derived.

### Three forms of one gap, two closed

| form | what drifted | closed by |
|---|---|---|
| **file** | core edited `app.js`, deployed, and our tree was behind | core: returned both files, wrote `site/tools/check_lab_equals_owner.py` refusing a push where the site tree differs from our named commit |
| **coverage** | `README.md` changed too — outside the eight files `check_hosted.py` covers, so behind with nothing able to say so | the same check, which compares the tree rather than a list |
| **artifact** | the inputs to a published decision were never here at all | **open** |

The first two were about bytes diverging between two copies. The third is
different in kind: nothing diverged, because the artifact was never in the
repository to diverge from. `check_hosted.py` reads 9 verified while the
decision behind the page is underivable, and it is right to — it checks
copies, and this is not a copy problem.

**What would close it:** that run's `report.json` and `verify.json` committed
here, after which `--report-only` reproduces the page's verdict and
`public_sources` cleans `engine_line.source` at its source rather than at the
carry-over. Nothing else is needed and nothing else substitutes.

## Repo state expected vs found

| expected | found |
|---|---|
| `values.json` regenerable by the export | **no** — see above |
| `site/teaser/` in step with the host | **no at first** — `check_hosted.py` read 8 verified, 1 contradicted |
| the sweep committed and citable | yes — `tasks/044c-centroid-count.sweep/`, digest `22a90a80afe70044…` |
| core's changes 1(a) and 2 present in our tree | **no at first**, then returned |

## What was done

### 1. The gate fired on something real, for the first time

`check_hosted.py` contradicted on `app.js`: host `e65aee1190418bdf…` 49,486
bytes, repo `fe2eebebbb85936f…` 49,038. The standing rule is nine verified
before the teaser is touched, so **nothing was touched**, and the cause was
diagnosed rather than assumed: reading the live file showed `cut into`,
`n_centroids` and `geometry.n_centroids` present — core's accepted change 1(a)
— and the typed `0.053` and `2,048` correctly absent, 1(b) being refused.

Had the export run then, it would have restamped an `app.js` 448 bytes behind
the deployed one and published a manifest describing a page that is not the
page, silently.

**The gap statement went to core with the request** and they took it as
theirs: their deploy note already carried the rule, they have written
`site/tools/check_lab_equals_owner.py`, and they returned a file we had not
asked for — `README.md`, `99eb1604…` → `a2603581…`, outside our check's eight.

Both verified before committing, by digest and byte count, then
`verify_teaser_data.py` run **before** the export rather than after, which is
core's point: no data file had moved, so the `DATA_VERSION` stamp had not
either, and that is the state the export needs to start from.
Commit `a4aa4b2`.

### 2. `measured.k_sweep`, cited and not recomputed

Ruled: the export cites a file with a digest rather than re-deriving the
sweep, because a sweep recomputed at export time is a second derivation of a
published number, and the lab's rule is that the page's number is answerable
to a receipt.

`k_sweep_block()` reads
`tasks/044c-centroid-count.sweep/arxiv-150k.default.json`, records its
`sha256`, and carries the nine k values with the three measures at each, the
seed, the fixture and the vector counts. 1,674 bytes. The export was wired to
`receipts.public_path` rather than gaining a seventh private copy of the
transform — it already carries one.

### 3. `--cite-only`, because the citation could not be landed any other way

`--report-only` would have rebuilt the verdict. So: a mode that carries every
block over and refreshes the citation alone, deriving nothing and reading no
report.

**Its acceptance is the before/after digest**, per block, with `measured`
opened one level down. The run prints every carried block with its digest and
refuses if any it must carry has moved. On the real run: **20 blocks carried
over byte-identically**, three geometry files unchanged.

Its docstring states that `--report-only` exists for a rebuild and this for a
carry-over, so nobody folds them.

### 4. The exporter refuses a local path, with the sabotage

Core's request, ruled in. `write_json` is the one writer in this project that
bypasses `receipts.write_json_stable`, and the file it writes is the only one
actually published — so 044g's runtime refusal arrives at the publishing
boundary. Drive letter, UNC share, `/home/`, `/Users/`, `/workspace/`, and a
`~`-prefixed path, which a receipt never holds but a hand-edited page datum
might.

18 tests. **Eight are the sabotage**: a real local path planted three levels
deep in a payload shaped like the real one, required to fail the write *and
leave no file*. Without them the file passes equally well against a refusal
whose body is `return`. Seven honest values are required to be written —
repo-relative paths, URLs, prose with slashes — because a refusal that fires
on correct values gets switched off. One is not synthetic: the string that was
in the published `values.json`.

### 5. The permitted-change set has two members, with different justifications

The refusal and `--cite-only` turned out to be **mutually blocking**: the
carried `verdict` block held the redacted path, so the exporter refused to
write the file at all, and the mode's own acceptance forbade changing that
block. Reported rather than improvised, and ruled.

| permitted change | justification |
|---|---|
| `measured.k_sweep` | **the mode's purpose** |
| `public_sources` over the carried blocks | **a precondition** — without it `write_json` refuses and the mode cannot write at all |

They are different kinds of permission and the mode says so. The second is
constrained three ways: no measurement may move, every block it touches is
**named in the output**, and the acceptance still digests everything else. On
the real run it touched exactly one block:

    REFRESHED  measured.k_sweep   (the citation)
    SANITISED  verdict            (a path made publishable; no measurement moved)

**The claim is narrowed, not weakened.** Before: *nothing but the citation
changed*. Now: *nothing but the citation and a named sanitisation changed, and
here is the sanitisation.* Both are checked by the same digest.

A third option — exempting content the mode merely carries — was **refused**
and the refusal is in the docstring so nobody reaches for it later. It would
let a file stay publishable precisely because its defect is old, which is the
repair-on-read loophole inverted, and repair-on-read is what let a machine
identifier sit unnoticed in three receipts for ten days.

## Measurements

| | |
|---|---|
| `check_hosted.py` before | 8 verified, 1 contradicted |
| `check_hosted.py` after core's return | **9 verified, 0 contradicted** |
| blocks carried over byte-identically | **20** |
| blocks changed | 2 — one citation, one sanitisation, both named |
| geometry files moved | **0** |
| `values.json` | 47,502 → **49,377** bytes |
| `k_sweep` page weight | 1,674 bytes |
| the caption's two numbers, read from the data | **0.036** at k=256, **0.053** at k=2048 |
| `verdict.summary` | unchanged: 8 options, 1 meets, 6 fails, 1 couldn't-check |
| `engine_line.source` | `C:\Users\<developer>\…\verify.json` → `verify.json` |

## Verification

| check | result |
|---|---|
| Both returned files verified before committing | **PASS** — digest and byte count, both exact |
| `verify_teaser_data.py` before the export | **PASS** — no data file moved, so no stamp moved |
| `verify_teaser_data.py` after the export | **PASS** — all checks, under 5 MB either way |
| Nothing but the two named blocks changed | **PASS** — 20 carried, asserted by digest |
| No measurement moved | **PASS** — `verdict.summary` and every `measured.*` but `k_sweep` byte-identical |
| The run is still identified after sanitisation | **PASS** — `dataset`, `date`, `environment_id` all present |
| The caption can read its two numbers | **PASS** — 0.036 and 0.053 from `measured.k_sweep` |
| The exporter refuses a planted local path | **PASS** — 8 sabotage cases, no file written |
| The refusal does not fire on honest values | **PASS** — 7 cases |
| The sweep's digest matches the committed file | **PASS** — `22a90a80afe70044…` |
| No published *value* moved | **PASS** — the fixtures, specs and MANIFESTs are untouched; `values.json` changed by design |
| Full suite | see below |

## Observed, not done

1. **The page's verdict is underivable here** — the leading finding. Needs
   that pod run's two receipts.
2. **1(b) is still staged.** `tasks/044c-teaser-k-propagation.md` carries the
   sentence with `values.measured.k_sweep` named as its source. The data it
   waits on now exists; the caption change is core's to make.
3. **`check_hosted.py` will now contradict** until core re-copies: we changed
   `values.json`, `inline.js`, `MANIFEST.sha256` and the `app.js` stamp. That
   is the expected direction and their new check is what catches it.
4. **`public_price_table` is still a private copy**, no-op on this fixture,
   ruled to go with the exporter refusing instead.

## Repo now contains

| path | what |
|---|---|
| `corpora/export_teaser_data.py` | `k_sweep_block`, `--cite-only`, `public_sources`, `LOCAL_PATH`, `refuse_local_paths` |
| `corpora/test_export_refuses_local_paths.py` | 18 tests, 8 of them the sabotage |
| `site/teaser/data/values.json`, `inline.js`, `MANIFEST.sha256`, `app.js` | the cite-only export's output |
| `site/teaser/app.js`, `README.md` | core's returned files |
| `tasks/note-teaser-return-path.md` | the gap statement and the ask, sent |
| `tasks/note-values-json-redacted-path.md` | updated: the path travels with this change |

## Blocked on developer

1. **Route the updated `values.json` note to core** — the path they accepted
   travels with this change rather than a later rebuild, and the reason is
   their own request that the rule be a check rather than a convention.
2. **The pod run's `report.json` and `verify.json`**, to close the artifact
   leg.
