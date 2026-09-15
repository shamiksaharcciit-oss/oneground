# Report: 018f-teaser-report-pypi

## Repo state expected vs found

| expected | found |
|---|---|
| `main` after 018d, tree clean | `383c7a1 task 018d`, **not clean**: `oneground/fixture/verify.py` held the interrupted, untested 018e work, and `tasks/020-simulator-state.md` was untracked |
| `v0.1.0` on 018d, unpushed | yes, on `383c7a1`. **Not moved.** |

**The 018e work was stashed, not committed and not discarded:**

    stash@{0}: On main: 018e WIP (interrupted, untested): fixture verify per-value couldnt_check

It is the per-value `couldnt_check` handling for `MemoryError` — patched into
`verify.py`, never tested, never committed, and this brief did not mention it.
Leaving it in the tree would have put untested code inside this commit, because
this task also edits `verify.py`. `git stash pop` restores it; the hunks it
touches do not overlap the one-line change below.

`tasks/020-simulator-state.md` is your brief and was left untracked.

## What was done

### 3. (answered first) `oneground==0.1.0rc1` from PyPI

A fresh venv from the system Python 3.12.10, `pip install oneground==0.1.0rc1`,
no extras, no `requirements.txt`. Installed from the index (no
`direct_url.json`), resolving numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0.

**It works.** Verbatim, from a directory outside any clone:

```
$ oneground calibrate show
calibration/history.jsonl is empty.
Run `oneground calibrate curve` or `oneground calibrate engine` to write the first line.
rc=0

$ oneground --version
oneground 0.1.0-preview (0.1.0rc1)
```

No missing dependency and not absent. What a page should not imply: **the wheel
does not ship the calibration history.** `calibrate show` reads
`calibration/history.jsonl` relative to the working directory, so a bare install
reports it empty; the same binary run inside a clone prints the full history
(exit 0, last lines `simulator_vs_engine … arxiv-smoke … verified (2026-09-13)`).

### 1. The teaser

- The fixture-spec link `../../fixtures/arxiv-150k.fixture.yaml` — which 404s
  on every host, since only `site/teaser/` is deployed — now points at
  `https://github.com/shamiksaharcciit-oss/oneground/blob/main/fixtures/arxiv-150k.fixture.yaml`.
- The promise block describes what is installable today and what is dated:

      oneground 0.1.0-preview — the advisor — installable today.
      pip install oneground · characterize · simulate · verify (Qdrant) · report.
      [later] v0.1, 23 September: pgvector as a second engine, measured in turn
              on one host; a second fixture where the ground looks different;
              a latency verdict that says couldn't-check when three runs
              straddle the threshold.

  This reverses the wording task 018 put there, which described 0.1.0 as if it
  were already out.

### 2. The published arXiv report

`runs/arxiv-150k-via-characterize/` → `fixtures/arxiv-150k/report/`: `report.json`,
`report.html`, `simulate.json`, `verify.json`, `verify_info.json`,
`characterization.json`.

**One developer path, redacted before anything was staged.** The pre-copy scan
found it in `report.json` at `price_table.path` — the same field task T2b
redacted in the teaser data — and it is redacted to the same repo-relative form,
`oneground/cost/prices.example.yaml`. Nothing else in the six files matched.

**The pod id stays.** `1ombs4scr257a5` is in `verify.json` and the report; per
014's ruling a terminated pod id is evidence for the same-environment rule and
grants nothing.

**Declared, in the MANIFEST.** Six lines appended as `report/<name>`, and
`DECLARED_GLOBS` in `oneground/fixture/verify.py` gains `"report/*"` so
`fixture verify` classifies them as declared rather than receipts: a report
carries timestamps, an environment id and a price table, and nothing about it
is re-derivable from the seeds.

**`docs/FIXTURES.md`** gains a paragraph under *Getting the artifacts* saying
the published report is a developer's own run of the product path over the
session `20260913-161921` workdir, that it is declared, and that nothing is
verified against it.

### One number this change made false, and one it did not

- **`docs/EXTERNAL_RUN.md`** said a successful run prints `digests 11
  verified`. On `main` the arXiv fixture now lists 17, so a stranger following
  it from a clone would see a number the page does not predict. Changed to 17.
  The brief did not name the file; the change it asked for is what made the
  sentence wrong.
- **`RELEASE_NOTES.md`** also says `digests 11 verified`, under *"On the machine
  that cut this release"*. That is a measurement of the tagged tree, where the
  MANIFEST still has 11 lines, so it is left alone — but it means the notes on
  `main` and a clone of `main` now disagree by six. See *Blocked on developer*.

## Measurements

### Report files, published

```
report.json            138,544 bytes  e75387ff93514e2660ce8fc62ef7ca62fb49197481c6de53cb5e2006b07ce7f2
report.html             50,355 bytes  e462a6b48900ea8fa24148a051ec2af6ac5d9ba63e21d3ad356e08c7fb0d6b64
simulate.json            6,307 bytes  e084bb68a4d325de05b3643b5e9ae4f267549d2e1abefac787c210f6ff8eb250
verify.json             20,206 bytes  32071cfc08ecf2996a6d0bdca8aae8bb1280ff455597ca95fa94cad1f929cc93
verify_info.json         8,463 bytes  01f515cf7b29fbe64e9a2c9c24f6ecb3ba52eb9c9c2cc4b4979785b74a40c7b0
characterization.json      589 bytes  da41fb73897f52f845541931fb1005f9caef3cd59c285912faf9c2d902267199
```

`report.json` is 41 bytes shorter than the workdir's: the redacted path.

### Digests, via `verify_digests`

```
receipt   verified  6
declared  verified  11   (5 existing + the 6 report files)
unlisted: []
```

### Teaser

`site/teaser/verify_teaser_data.py`: **ALL CHECKS PASSED** — eps sweep, 2,000
queries with 0 disagreements, the cache-bust stamp, `inline.js` against its four
files, and the load bound: 4.59 MB over http, 4.78 MB from `file://`, under 5 MB
either way. The page grew 108 bytes.

Bounds check (`tasks/scratch/T1-bounds.js`, headless Chrome, `file://`):

| viewport | promise | document | overlaps |
|---|---|---|---|
| 1440×900 | 900 | 6848 | none |
| 1440×740 | 740 | 6384 | none |
| 1280×720 | 720 | 6631 | none |
| 1024×768 | 768 | 6990 | none |
| 390×844 | 553 | 10290 | none |

Against T3: `promise` at 390 px grew 511 → 553 px (one paragraph is longer),
and the document at 1024×768 by 17 px. No overlap at any viewport.

### Scans

- Identifier scan over the staged tree: **303 tracked files, 0 findings.**
- Leak scan: one hit, `oneground/test_environment.py` — the synthetic
  `DESKTOP-` probe task 018 installed. Pod ids kept.
- The six report files scanned individually before staging: 0 findings each
  after the redaction.
- `tasks/scratch/018-docs-numbers.py`: ALL CHECKS PASSED.

### The suite

**781 passed, 0 skipped** (781 collected). The usual one skip ran this time:
`test_pod.py::test_live_plan_against_the_real_api`, because this process
inherited `RUNPOD_API_KEY`. It is read-only by construction -- it resolves a
plan for `sessions/arxiv-build.yaml` against the live API and asserts the
client cannot create -- so it created no pod and spent nothing. The count is
unchanged from 019 because this task adds no tests.

## Observed, not done

- **The teaser's "check it yourself" link points at `releases/tag/v0.1.0`**,
  which 404s until the 23rd — the same class as the spec link this task fixed.
  Task 018 set it; the brief named only the spec link and the promise block.
- **`site/teaser/data/values.json` embeds a copy of the arXiv fixture's
  MANIFEST** (per the teaser README) and nothing compares it to the repository's.
  It is now six lines behind. It is a snapshot of the data the page was exported
  from, so this may be correct as it stands; it is not checked either way.
- **`calibrate show` on a bare install cannot show the published history.** The
  history file is not in the wheel. Either that is the intended shape — history
  is the repository's, not the package's — or the page should link to it rather
  than suggest running the command.
- **018e is unfinished and stashed.** The per-value `couldnt_check` for
  `MemoryError`, the summary line and the injected-failure test are the open
  items.

## Repo now contains

Changed:

    site/teaser/index.html                  spec link absolute; promise block
    fixtures/arxiv-150k/MANIFEST.sha256     six declared report lines
    oneground/fixture/verify.py             DECLARED_GLOBS += "report/*"
    docs/FIXTURES.md                        the published-report paragraph
    docs/EXTERNAL_RUN.md                    digests 11 -> 17

New:

    fixtures/arxiv-150k/report/             six files, one path redacted
    tasks/018f-teaser-report-pypi.report.md

Not committed: `stash@{0}` (018e WIP); `tasks/020-simulator-state.md` (your brief).

## Blocked on developer

1. **Push `main`.** The tag is not moved, so `v0.1.0` still names `383c7a1`
   and this commit sits above it, outside the release.
2. **Decide the `RELEASE_NOTES.md` count.** The notes say `digests 11 verified`
   for arxiv-150k, true of the tagged tree. A clone of `main` after this commit
   prints 17. Either the notes gain a sentence, or the tag moves again — which
   this brief says not to do.
3. **018e**: finish from `stash@{0}` when you want it, or drop it.
