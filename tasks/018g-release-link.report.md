# Report: 018g-release-link

## Repo state expected vs found

| expected | found |
|---|---|
| `main` at `82fef09 task 018f`, clean apart from your brief | yes; `tasks/020-simulator-state.md` untracked, left untracked |
| `v0.1.0` on `383c7a1` | yes. **Not moved.** |
| `stash@{0}` holds the 018e WIP | yes. **Not popped, not dropped, not applied.** Listed unchanged after the suite ran. |

## What was done

- **The "check it yourself" link.** `RELEASE_URL` in `site/teaser/app.js` now
  points at `https://github.com/shamiksaharcciit-oss/oneground/releases/tag/v0.1.0-preview`,
  and the link text in `site/teaser/index.html` reads
  `oneground 0.1.0-preview on GitHub` so the label names the page it opens.
  `app.js` sets the `href` at load; the HTML keeps `href="#"` as before. No
  other reference to a release tag exists under `site/`.
- **`RELEASE_NOTES.md`**, directly after the *"On the machine that cut this
  release"* digest block:

  > The arXiv fixture on `main` carries 17 digests, because a published report
  > (`fixtures/arxiv-150k/report/`, declared) was added after the `v0.1.0` tag;
  > the tagged release carries the 11 above.

  This closes 018f's *Blocked on developer* item 2 without moving the tag.

## Measurements

- **Link targets**, `curl -s -o /dev/null -w '%{http_code}'` against GitHub
  tonight: `releases/tag/v0.1.0-preview` **200**; `releases/tag/v0.1.0` **404**.
- **Diff:** 3 files, +6 / −2 (`git diff --stat`).
- **`site/teaser/verify_teaser_data.py`: ALL CHECKS PASSED.** Load 4.59 MB over
  http (data 4,509,912 + page 79,157), 4.78 MB from `file://`; the page grew
  16 bytes over 018f.
- **Bounds check** (`tasks/scratch/T1-bounds.js`, headless Chrome, `file://`):

  | viewport | promise | document | overlaps |
  |---|---|---|---|
  | 1440×900 | 900 | 6848 | none |
  | 1440×740 | 740 | 6384 | none |
  | 1280×720 | 720 | 6631 | none |
  | 1024×768 | 768 | 6990 | none |
  | 390×844 | 553 | 10290 | none |

  Identical to 018f at every viewport: the longer label did not wrap anywhere.
- **Identifier scan** (`oneground.environment.identifier_findings()`, staged
  tree, 305 files by `git ls-files`): **0 findings**. The first pass found one
  — this report, quoting the synthetic hostname probe in full — so the quote
  was shortened to its prefix, as 018f's is, and the scan re-run.
- **Leak scan** (`tasks/scratch/014-leak-scan.py`): the one known hit, the
  synthetic `DESKTOP-` probe in `oneground/test_environment.py`; pod ids
  kept (23 occurrences).
- **`tasks/scratch/018-docs-numbers.py`: ALL CHECKS PASSED.**
- **Suite:** `pytest -q` — **781 passed** in 529 s. The live RunPod plan test
  ran read-only, as in 018f; no pod created, nothing spent.

## Verification

- Passed: every check above.
- Contradicted: none.
- Couldn't-check: whether the page, once deployed, opens the preview release —
  the check is against the source files over `file://` plus the HTTP status of
  the target; the deployed site was not fetched.

## Observed, not done

- **`site/teaser/data/values.json`'s embedded MANIFEST** is still 11 lines
  against the repository's 17 (carried from 018f).
- **018e** remains in `stash@{0}`, as instructed.

## Repo now contains

Changed:

    site/teaser/app.js        RELEASE_URL -> releases/tag/v0.1.0-preview
    site/teaser/index.html    link text "oneground 0.1.0-preview on GitHub"
    RELEASE_NOTES.md          one sentence: 17 digests on main, 11 in the tag

New:

    tasks/018g-release-link.report.md

Not committed: `stash@{0}` (018e WIP); `tasks/020-simulator-state.md` (your brief).

## Blocked on developer

1. **Push `main`.** The tag stays on `383c7a1`; this commit and 018f sit above it.
2. **On the 23rd, as part of the release:** add the `releases/tag/v0.1.0` link
   to the teaser (it 404s until then).
3. **018e / `stash@{0}`:** your decision after the release.
