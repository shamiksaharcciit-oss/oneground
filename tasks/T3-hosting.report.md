# Report: T3-hosting

## Repo state expected vs found

| the brief assumed | found |
|---|---|
| `main` is the public single-commit branch at `27173ae` | yes — `27173ae oneground 0.1.0-preview`, with `b719603 brief: T3 hosting` on top. |
| pushed to `github.com/shamiksaharcciit-oss/oneground` | yes — `origin` points there and `remotes/origin/main` exists. |
| Pages currently serves the README through Jekyll | yes, and `check_hosted.py` measured it: the host's `index.html` is a different file from this repository's, and `app.js`, `style.css` and the whole of `data/` are 404. |
| `site/teaser/` is launch-ready (T2b) | yes, and MASTER's hostname fix and final re-export landed: `DESKTOP-HAGOPQC` is gone from `values.json`, `verify_teaser_data.py` passes on the committed tree. |
| branch model per `docs/RELEASE.md` §6 | read: `main` is the sole history, `archive/private-history` is never merged in either direction. Worked on `main`. Not pushed. |
| `docs/HOSTING.md` | absent, as expected — created. |
| `.github/workflows/` | exists, with `calibration.yml`. Added `pages.yml` beside it. |

One thing the brief did not mention and I did not assume: `.github/` already
holds `actions/record-calibration` and `scripts/fetch-glove.sh`. Untouched.

## What was done

### 1. Deploy by Actions

`.github/workflows/pages.yml` — on push to `main` and on manual dispatch:
checkout, **verify the data**, `configure-pages`, `upload-pages-artifact`
(`path: site/teaser`), `deploy-pages`. One job, the `github-pages`
environment, `concurrency: pages` with `cancel-in-progress: false` because a
cancelled deploy can leave the site half-published.

No path filter, deliberately: a filter that is subtly wrong fails by silently
not deploying, which is the slowest failure to notice.

Three things worth stating:

- **Every action is pinned by commit SHA**, with its version in a comment.
  The SHAs were resolved from the GitHub API and are checked back against
  their tags by `.github/scripts/validate-pages-workflow.py`, which is the
  check to run after any edit to the workflow. Note this differs
  from `calibration.yml`, which pins by tag (`@v4`, `@v5`) — the brief asked
  for SHA pinning here and I did not touch the other workflow.
- **`include-hidden-files: true` on the upload step.** This one is a trap:
  `upload-pages-artifact`'s tar carries `--exclude=.[^/]*` unless that input
  is set, and the input defaults to `"false"`. Without it `.nojekyll` is
  dropped from the artifact silently. I read the action's `action.yml` at the
  pinned SHA to confirm rather than assuming.
- **The workflow runs `site/teaser/verify_teaser_data.py` before uploading.**
  It is stdlib-only (checked by parsing its imports against
  `sys.stdlib_module_names`), so the runner installs nothing. A data
  directory that fails its own check never reaches the web.

`site/teaser/.nojekyll` added. It is belt and braces — artifact deployment
runs no generator at all — and it is there so that if the source is ever
switched back to a branch folder the site does not silently start being
rebuilt. `site/teaser/README.md` now says the repository README is no longer
served by Pages.

### 2. Custom domain

`site/teaser/CNAME` contains `oneground.oneproof.dev` and nothing else.
`docs/HOSTING.md` gives the domain owner **one record**:

    CNAME   oneground   →   shamiksaharcciit-oss.github.io

and says what changes when the repository moves to the organisation (that
value, and nothing else — the record points at a Pages host, not a
repository; GitHub matches the repository by the `CNAME` file in the
artifact). It documents that TLS is provisioned once the record resolves,
that the browser will warn until it does, and that **Enforce HTTPS** stays
greyed out until the certificate exists.

### 3. Hosted-copy check

`site/teaser/check_hosted.py <base-url>`, stdlib only. Fetches
`data/MANIFEST.sha256`, every file it lists (`inline.js` included), then
`index.html`, `app.js` and `style.css`, and reports one outcome per file:
`verified` / `contradicted` / `couldnt_check`. Exit non-zero **only** on a
contradiction.

Two decisions inside it:

- **The file list is read from the repository's manifest, not the host's.**
  If the host served a manifest of its own choosing, letting it name the files
  to check would let it choose what gets checked.
- **Absent is `couldnt_check`, not `contradicted`.** An undeployed site is a
  gap, not a disagreement, and couldn't-check is never rounded up. Requests
  carry `Cache-Control: no-cache` so an intermediate cache cannot answer on
  the origin's behalf and make a stale copy look verified.

### 4. Promise block

Set to the brief's text, verbatim. It is split into paragraphs at the sentence
groups the brief's own line breaks mark and nowhere else; no word is added,
removed or reordered. The two later items (`v0.1, 23 September` and `v0.2`)
are muted, because what ships today and what is dated but not yet true should
not read at the same weight. `pip install oneground` links to PyPI; the
"check it yourself" block gained a line linking to the
`v0.1.0-preview` release. An `<a href>` is not a request — nothing is fetched
until a reader clicks — so the page still makes no external request at load,
measured below.

### 5. Cache-busting

Each data URL now carries `?v=<first 8 hex of that file's sha256>`, taken from
`data/MANIFEST.sha256`. The digests live in a **generated block at the top of
`app.js`**, written by `stamp_page()` in the export:

    // --- generated by corpora/export_teaser_data.py --- do not edit by hand ---
    const DATA_VERSION = {"base.bin": "08268d20", ...};
    // --- end generated ---

The token is in the code rather than in the data on purpose. Putting it in
`values.json` would mean fetching that file before the other three could be
named, adding a round trip in front of the 3.9 MB `base.bin`; with it here,
**the four files are still fetched in parallel**. The export refuses if the
markers are missing rather than leaving the page pinned to digests that no
longer exist, and `verify_teaser_data.py` now fails if the stamp and the
manifest disagree — proven by corrupting one entry and watching it fail.

Two consequences worth naming:

- **`--report-only` now also rewrites `app.js`.** T2b's guarantee was "only
  `values.json`, `inline.js` and their MANIFEST lines change". That is now
  "…and the generated block in `app.js`". The three geometry files are still
  asserted byte-identical and the run still exits non-zero if one moves.
- The export was re-run to write the first stamp, so `values.json` and
  `inline.js` have new digests. **No number changed** — the field-by-field
  diff against the committed copy shows only `generated_at`, `generated_by`
  and `geometry_from` moved.

`docs/HOSTING.md` documents the whole caching story: `data/*` is
content-addressed so a stale copy is *detectable* by `check_hosted.py`, `?v=`
makes it unlikely in the first place, the stamp check makes staleness of the
stamp itself impossible to miss, and the page still refuses to render if a
mismatched file gets through anyway.

## Measurements

### The workflow, validated without a runner

`act` is **not installed** on this machine, and neither is `actionlint`, so
there was no dry run. What was checked instead
(`.github/scripts/validate-pages-workflow.py`, all passing):

- parses as YAML; `name`, `on.push.branches == [main]`, `workflow_dispatch`
- `permissions` = `contents: read`, `pages: write`, `id-token: write`
- `concurrency.cancel-in-progress` is `false`
- the job declares the `github-pages` environment and takes its URL from the
  deploy step's output
- exactly one upload step, `path: site/teaser`, `include-hidden-files: true`
- every `uses:` is a 40-hex SHA, **each SHA is a real commit in the repository
  it names**, and each **matches the version its comment claims** — checked
  against `api.github.com`:

| action | pinned SHA | tag |
|---|---|---|
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` | v7.0.1 |
| `actions/configure-pages` | `45bfe0192ca1faeb007ade9deae92b16b8254a0d` | v6.0.0 |
| `actions/upload-pages-artifact` | `fc324d3547104276b827a68afc52ff2a11cc49c9` | v5.0.0 |
| `actions/deploy-pages` | `368f82528645a54fb793d4d04e342629a3f51346` | v5.0.1 |

- the one `run:` step names a script that exists and imports only
  `argparse, base64, gzip, hashlib, json, os, re, struct, sys` — all stdlib
- `.nojekyll`, `CNAME`, `index.html` and `data/MANIFEST.sha256` all present;
  `CNAME` is exactly `oneground.oneproof.dev`

### `check_hosted.py` against the live URL

Method: run it against `https://shamiksaharcciit-oss.github.io/oneground`,
which is the Pages **branch** build the brief describes.

    couldnt_check  data/MANIFEST.sha256  HTTP 404
    contradicted   index.html            host 876db0741e9ddc22… repo b7ad1e767fbb1442…  16,703 bytes
    couldnt_check  app.js                HTTP 404
    couldnt_check  style.css             HTTP 404

    0 verified · 1 contradicted · 3 couldn't-check      exit 1

**Which files are which, since the brief asked:** `app.js`, `style.css` and
everything under `data/` are **absent** (404) — the README-era site has no
such files. `index.html` is **not** absent: the host serves one, and it is the
README rendered by Jekyll, so it is `contradicted`, not couldn't-check. That
distinction is the honest reading and the tool makes it rather than lumping
the two together. The closing message names the cause specifically — no
manifest plus a disagreeing `index.html` is the shape of a branch build — and
says the fix is the Pages source setting.

The manifest's own files were not fetched, because the manifest was not there
to be trusted; the tool says so rather than reporting eleven silent 404s.

### The page, re-measured

Method: CDP against `python -m http.server` on 127.0.0.1, and against
`file://`.

**Requests over http — `?v=` present, still four, still parallel, all
same-origin:**

    /                                    /style.css        /app.js
    /data/values.json?v=deada30f         /data/centroids.json?v=26cd059b
    /data/queries.json?v=97289c3a        /data/base.bin?v=08268d20

**Console output: none. Exceptions: none.** Both paths.

**`file://` — four requests, all `file:`**: `index.html`, `style.css`,
`app.js`, `data/inline.js`. No `?v=` there, and none needed: nothing is
cached and `inline.js` is loaded by script tag.

**Section heights, and whether any section's content escapes its own box**
(`tasks/scratch/T1-bounds.js`):

| viewport | ground | query | verdict | receipt | promise | document | overlaps |
|---|---|---|---|---|---|---|---|
| 1440×900 | 900 | 900 | 2713 | 1150 | 900 | 6848 | none |
| 1440×740 | 740 | 756 | 2713 | 1150 | 740 | 6384 | none |
| 1280×720 | 720 | 754 | 2972 | 1181 | 720 | 6631 | none |
| 1024×768 | 768 | 768 | 2971 | 1431 | 768 | 6973 | none |
| 390×844 | 1199 | 1454 | 4521 | 1956 | 511 | 9927 | none |

**No overlap at any of the five.** Against T2b, `promise` grew from 347 px to
511 px at 390 px and the document from 9,507 px to 9,927 px — the promise
block is five paragraphs where it was one sentence. `receipt` moved by 18 px
(the release link) and `verdict` by 46 px; nothing else changed.

**Slider, overflow and load** (`tasks/scratch/T1-browser-measure.js` over
CDP, two runs, 82 frames each, run one at a time):

| run | slider median | p95 | max |
|---|---|---|---|
| desktop | 7.1 / 6.5 ms | 11.6 / 9.7 | 38.5 / 11.0 |
| 390×844 dpr 3 | 7.6 / 7.8 ms | 13.1 / 10.3 | 18.1 / 11.7 |

Worst frame 38.5 ms against a 100 ms target; every median under 8 ms. This
task touched nothing in the hot path, and the numbers match T2's.

`documentElement.scrollWidth` = 390 = `clientWidth` at 390 px, both runs:
**no horizontal overflow.** Console empty and exceptions empty in both.

Time to first ground 510 ms and 4,883 ms — the spread is `python -m
http.server`, which is single-threaded with a 3.9 MB body, not the page.

Load size, from `verify_teaser_data.py`: **4.59 MB over http**
(data 4,509,912 + page 79,026) and **4.78 MB from `file://`**
(inline.js 4,702,205 + page 79,026). Both under 5 MB. The page grew by
2,855 bytes: the `DATA_VERSION` block, the promise markup and its styles.

### The promise block as rendered

Read out of the DOM, matching the brief line for line:

    oneground 0.1.0-preview — the advisor — installable today.
    pip install oneground · characterize · simulate · verify (Qdrant) · report.
    Every number carries its receipt; every report cites the calibration run
    it was generated under.
    v0.1, 23 September: a second engine (pgvector), a second fixture where the
    ground looks different, and what the preview week teaches us.
    v0.2: the ground you just moved, and the query you just followed — live,
    on your own vectors. Dated when a witnessed run makes it true.
    Prevent · Detect · Prove · Choose.

## Verification

**Passed.** `site/teaser/verify_teaser_data.py` — every check, including the
new stamp check, and load size under 5 MB on both paths.

**Passed.** The stamp check actually fails. One `DATA_VERSION` entry was
changed to `deadbeef`; the verifier reported
`FAIL stamp matches every manifest line` and named the file
(`base.bin: app.js deadbeef manifest 08268d20`), exit 1. Restored, exit 0. A
check that cannot fail is not a check.

**Passed.** The export re-run changed no number: field-by-field against the
committed `values.json`, only `generated_at`, `generated_by` and
`geometry_from` moved.

**Passed.** No developer identifier reached the shipped data
(`tasks/scratch/T2b-scan-identifiers.py`): `polo2` 0, `DESKTOP-` 0, including
inside the compressed bundle.

**Couldn't check.**

- **A workflow dry run.** `act` is not installed and neither is `actionlint`.
  The workflow has never executed; everything above is static validation plus
  the fact that each pinned SHA resolves. The first real evidence will be the
  developer's first push.
- **The deployed site.** `check_hosted.py` cannot verify anything until the
  workflow runs; today it correctly reports the branch build.
- **DNS, TLS and Enforce HTTPS.** Nothing to measure until the record exists.
- **Edge and a real phone**, as in T1 and T2.

## Observed, not done

- **`calibration.yml` pins by tag, `pages.yml` pins by SHA.** The brief asked
  for SHA pinning on the new workflow and I did not touch the existing one, so
  the repository now has two conventions. Worth reconciling.
- **`check_hosted.py` does not check `CNAME` or `.nojekyll`.** Pages consumes
  both rather than serving them, so fetching them proves nothing about whether
  they were in the artifact. If you want positive evidence the artifact
  carried `.nojekyll`, the artifact listing in the workflow run log is where
  it shows.
- **The `?v=` token changes on every export even when no data changed**,
  because `values.json` carries a `generated_at`. That over-busts rather than
  under-busts, which is the right way round, but it does mean a re-export with
  no content change still re-downloads 4.5 MB for returning readers.
- **The promise block adds two outward links** (PyPI, the GitHub release).
  They are the only two on the page besides the fixture spec and the data
  manifest. No request is made until clicked, and that was measured.
- **`site/teaser/README.md` still describes four sections in one place**; I
  corrected the file list to five but did not audit the whole document against
  the page as it now stands.

## Repo now contains

New:

    .gitignore                           tasks/scratch/ is not published
    .github/workflows/pages.yml          deploy site/teaser by artifact
    .github/scripts/validate-pages-workflow.py   run after any workflow edit
    docs/HOSTING.md                      the DNS record, the settings, caching
    site/teaser/CNAME                    oneground.oneproof.dev
    site/teaser/.nojekyll                nothing is ever processed
    site/teaser/check_hosted.py          is the hosted copy this copy?
    tasks/T3-hosting.report.md           this file

Changed:

    corpora/export_teaser_data.py        stamp_page(), --page-dir, markers
    site/teaser/app.js                   DATA_VERSION block, ?v=, RELEASE_URL,
                                         the promise section's release link
    site/teaser/index.html               promise block, release link markup
    site/teaser/style.css                promise block styles
    site/teaser/verify_teaser_data.py    the stamp check
    site/teaser/README.md                hosting, the new files, the ?v= note
    site/teaser/data/values.json         re-exported (timestamp only)
    site/teaser/data/inline.js           rebundled
    site/teaser/data/MANIFEST.sha256     two lines

**The scratch scripts this task used are not in the repository**, with one
exception. `tasks/scratch/` is ignored, per `docs/RELEASE.md` §6: the briefs
and reports are the receipt trail and ship; the working does not. Six scripts
were written and run — four one-shot text patches, the report filler, and the
workflow validator — and each is named where its result is reported, so a
reader knows which instrument produced which number even though the instrument
is not published. Five remain on the developer's machine.

The sixth is not scratch. A workflow is only really tested by pushing it, so
the validator is the only check that stands between an edit and a failure in
the most expensive place; it belongs beside the thing it validates. It is now
`.github/scripts/validate-pages-workflow.py`, resolves its paths from the
repository root rather than the caller's directory, and reports an unreachable
GitHub API as `couldnt_check` rather than as a failure. `docs/HOSTING.md` says
to run it after any workflow edit.

Nothing outside `site/teaser/`, `.github/workflows/pages.yml`,
`docs/HOSTING.md`, `corpora/export_teaser_data.py` and `.gitignore` was
written.
`corpora/export_teaser_data.py` is outside the brief's list; it is the file
that has to write the stamp, and step 5 asks for a stamp derived "at export
time", so there was no way to do step 5 without it. No new dependency; the
workflow installs nothing.

Not pushed.

## Blocked on developer

Everything below needs your GitHub account; none of it is blocked on me.

1. **Push `main`.**
2. **Settings → Pages → Source → GitHub Actions.** If it is left on *Deploy
   from a branch*, the workflow will run and report success while Pages keeps
   serving the branch build. The two do not conflict — they ignore each other
   — and the site does not change. This is the one step whose failure looks
   like success.
3. **Settings → Pages → Custom domain →** `oneground.oneproof.dev`.
4. **The domain owner creates one record:** `CNAME oneground →
   shamiksaharcciit-oss.github.io`.
5. **Tick Enforce HTTPS** once the certificate is provisioned; it is greyed
   out until then.
6. **Run the check:**
   `python site/teaser/check_hosted.py https://oneground.oneproof.dev`
   — every file `verified` is what a finished deployment looks like.
