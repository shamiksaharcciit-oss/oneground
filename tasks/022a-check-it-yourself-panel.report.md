# Report: 022a-check-it-yourself-panel

## Repo state expected vs found

| expected | found |
|---|---|
| a 022a brief and 022a work to revise | **neither.** No `tasks/022a*` brief, no commit, no `site/teaser/` change in the tree. Confirmed with the developer: their message is the whole brief. |
| `main` at `7dc1303` (the 022 brief) | yes |
| 022 in progress | yes: staged, uncommitted, its fresh-venv proof running in the background. **Left untouched**; this commit carries only 022a's paths. |
| `v0.1.0` on `383c7a1` | yes, not moved |

**Two corrections to the mechanics, both confirmed with the developer before
editing:**

1. **`--report-only` cannot change this panel.** The panel is built in
   `site/teaser/app.js`. Its `pip install oneground` line and its comment were
   typed there, and the command came from `values.json:receipt.verify_command`,
   which only a full export reads from the spec. `--report-only` copies
   `receipt` over unchanged.
2. **No manifest covers `app.js` or `index.html`.** `data/MANIFEST.sha256`
   lists the five data files (`base.bin`, `centroids.json`, `queries.json`,
   `values.json`, `inline.js`). `data/inline.js` bundles the four data files
   and nothing else, and does not contain the panel text. `check_hosted.py`
   compares `index.html`, `app.js` and `style.css` directly against the
   repository copy (`PAGE_FILES`). So this change has no digest to update:
   `data/` is untouched, and pushing the repository copy is what makes the
   host match.

## What was done

The "check it yourself" panel now prints only what works today from a clone
with no install:

    python site/teaser/verify_teaser_data.py
    # needs a clone of the repository and nothing else: standard library only.

Beneath it, one line (`index.html`):

> verifying the full arXiv fixture is heavier — a checkout, the pinned
> environment and the release asset: [how the checks work](https://oneproof.dev/oneground/how-it-works.html#checks).

`pip install oneground` and `oneground fixture verify arxiv-150k` are gone from
the panel, with the three-line comment that described that command. `pip install
oneground` stays in the "what is coming" block, which is the install path.

**Why:** the developer installed the published `0.1.0rc1` into a fresh venv and
ran the proposed replacement, `oneground fixture verify arxiv-smoke`; it fails
exactly as the `arxiv-150k` form does (`error: no such fixture directory:
fixtures\arxiv-smoke`), because that wheel ships no fixture data. The panel
pointed at a failing command either way.

**This panel changes again when task 022 ships.** 022 makes `oneground fixture
verify` work from a bare install (specs and small receipts in the wheel,
preconditions named in one run). Once a release carrying it is published, the
installed-package route works and the panel should say so.

## Measurements

**The claims in the new text, checked before writing them:**

- `verify_teaser_data.py` imports `argparse`, `base64`, `gzip`, `hashlib`,
  `json`, `os`, `re`, `struct`, `sys`: standard library only.
- It reads only files under `site/teaser/` (`data/*` and `app.js`), and all of
  them are tracked (`git ls-files site/teaser/data`: all six).
- "nothing else" is literal apart from the interpreter the printed command
  names: it needs Python 3.
- `https://oneproof.dev/oneground/how-it-works.html`: HTTP 200, and the page
  carries `id="checks"` (curl, 2026-09-16).

**Digests** (`sha256sum`, before → after):

| file | before | after |
|---|---|---|
| `site/teaser/index.html` | `100a3fbb685a…` | `a4aa05b2349d…` |
| `site/teaser/app.js` | `4d2848da6500…` | `fe2eebebbb85…` |
| `site/teaser/style.css` | `6517d6b87c65…` | unchanged |
| `data/MANIFEST.sha256` | `31314947b8df…` | unchanged |
| `data/base.bin` | `08268d208c3d…` | unchanged |
| `data/centroids.json` | `26cd059b1a05…` | unchanged |
| `data/queries.json` | `97289c3ab2ac…` | unchanged |
| `data/values.json` | `deada30f4343…` | unchanged |
| `data/inline.js` | `793c00ae3bd9…` | unchanged |

`git diff --stat -- site/teaser`: `app.js` +8 −7, `index.html` +5. No other
file under `site/teaser/` differs from `HEAD`.

**No published figure moved.** Every figure on the page is read from the four
data files or recomputed from `base.bin`, and none of those five files changed
a byte. `app.js`'s `DATA_VERSION` stamp is untouched, and the diff touches only
the panel's lines.

**`site/teaser/verify_teaser_data.py`: ALL CHECKS PASSED.** Load 4.59 MB over
http (data 4,509,912 + page 79,456), 4.78 MB from `file://`, under 5 MB either
way. The page grew 299 bytes (79,157 → 79,456).

**Bounds check** (`tasks/scratch/T1-bounds.js`, headless Chrome, `file://`),
against 018g:

| viewport | promise | document (018g → now) | overlaps |
|---|---|---|---|
| 1440×900 | 900 | 6848 → 6784 | none |
| 1440×740 | 740 | 6384 → 6320 | none |
| 1280×720 | 720 | 6631 → 6568 | none |
| 1024×768 | 768 | 6990 → 6927 | none |
| 390×844 | 553 | 10290 → 10262 | none |

The document is 28–64 px shorter: the code block went from five lines to two,
and the source paragraph beneath it gained one. The rendered panel was
inspected in the 1440×900 and 390×844 screenshots.

**Scans:** identifier scan over the staged tree, 0 findings; leak scan, the one
known synthetic `DESKTOP-` probe in `oneground/test_environment.py`.

## Verification

- Passed: everything above.
- Contradicted: none.
- Couldn't-check: the hosted page. It changes only when this is pushed and the
  Pages workflow deploys it; `check_hosted.py` against the host is the check
  for that and was not run.

## Observed, not done

- **At 390 px the comment line scrolls sideways inside the code block**
  (`# needs a clone …` is wider than the phone viewport). The old panel's
  comment lines did the same, and the brief asks for one line, so it is left.
- `values.json:receipt.verify_command` still carries `oneground fixture verify
  arxiv-150k`. Nothing on the page reads it now. It comes from the fixture spec
  and changes only on a full export.
- The "what is coming" block still says `0.1.0-preview … installable today` and
  `v0.1, 23 September: …`. Not in this brief; it changes with the release.

## Repo now contains

Changed:

    site/teaser/app.js       the panel: the clone-only command and its one line
    site/teaser/index.html   the heavier-path line and link beneath it

New:

    tasks/022a-check-it-yourself-panel.report.md

Not in this commit: task 022's staged work (`oneground/fixture/*`,
`oneground/environment.py`, `oneground/test_packaging.py`, `setup.py`,
`MANIFEST.in`, `docs/EXTERNAL_RUN.md`, `RELEASE_NOTES.md`) and
`tasks/020-simulator-state.md`.

## Blocked on developer

1. **Push `main`**, then let the Pages workflow deploy, and run
   `python site/teaser/check_hosted.py <host>`: `index.html` and `app.js` should
   come back verified against this commit.
2. **When 022 ships**, revise this panel to the installed-package route.
