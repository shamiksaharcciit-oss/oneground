# Hosting

`site/teaser/` is served at **https://oneground.oneproof.dev/** by GitHub
Pages, deployed from an artifact by `.github/workflows/pages.yml`. Nothing is
generated, templated or rewritten on the way: what is in the repository is
what is served, byte for byte, and there is a command that proves it.

The README stays the repository's front page **on GitHub**. It is no longer
served by Pages — before this workflow, Pages built the branch root with
Jekyll and the README *was* the site.

---

## For the domain owner: one DNS record

Create one record on `oneproof.dev` and nothing else:

| type | name | value |
|---|---|---|
| `CNAME` | `oneground` | `shamiksaharcciit-oss.github.io` |

That is the whole ask. Note the value has **no** `/oneground` path and no
trailing dot beyond whatever your DNS provider adds itself.

**When the repository moves to the organisation**, this value changes to the
org's Pages host — `<org>.github.io` — and nothing else about it does. The
record is a pointer to a Pages host, not to a repository; GitHub picks the
repository by matching the `CNAME` file in the published site.

### What happens after the record resolves

1. GitHub sees the domain, provisions a Let's Encrypt certificate, and the
   site answers on `https://`. This takes minutes, occasionally up to an hour,
   and until it finishes the browser will warn about the certificate. That is
   expected; it is not a misconfiguration.
2. Once the certificate exists, tick **Enforce HTTPS** in
   *Settings → Pages*. It stays greyed out until then. With it on, `http://`
   is redirected rather than served.

`site/teaser/CNAME` carries `oneground.oneproof.dev` and is what tells GitHub
which domain this artifact claims. It is part of the deployed site; do not
remove it, and do not edit it in the Pages UI, which would rewrite the file
and put the repository and the setting out of step.

---

## Enabling the workflow (one-time, repository settings)

*Settings → Pages → Build and deployment → Source* must be set to **GitHub
Actions**. If it is left on *Deploy from a branch*, the workflow will run and
report success while Pages keeps serving the branch build — the two do not
conflict, they just ignore each other, and the site does not change.

Then, in *Settings → Pages → Custom domain*, enter `oneground.oneproof.dev`.

---

## What the workflow does

`.github/workflows/pages.yml`, on every push to `main` and on manual dispatch:

1. checks out the repository;
2. **runs `site/teaser/verify_teaser_data.py`** — a data directory that fails
   its own check never reaches the web;
3. uploads `site/teaser/` as the Pages artifact;
4. deploys it.

**After any edit to that workflow, run:**

```bash
python .github/scripts/validate-pages-workflow.py
```

A workflow is only really tested by pushing it, and a broken one fails where a
failure costs most. That check does what can be done beforehand: the file
parses and carries the keys a Pages deployment needs, the upload step points at
`site/teaser` and keeps hidden files, every action is pinned to a real commit
SHA that matches the version its comment claims, and the `run:` step names a
script that exists and needs nothing installed. It reads only, and reports an
unreachable GitHub API as `couldnt_check` rather than as a failure.

Two details that are easy to get wrong and are deliberate here:

- **Every action is pinned by commit SHA**, with the version in a comment
  beside it. A tag is a moving pointer, and a workflow that publishes a public
  site should not change what it runs because someone else moved one.
- **`include-hidden-files: true`** on the upload step. The action's tar
  excludes dotfiles by default, so without it `.nojekyll` is dropped from the
  artifact silently.

`site/teaser/.nojekyll` is belt and braces: artifact deployment runs no
generator at all, so Jekyll cannot process anything. It is there so that if
the source is ever switched back to a branch folder, the site does not
silently start being rebuilt.

---

## Handing changed data to whoever copies it

**Before sending changed files, compute the declaration. Do not write it.**

```bash
python corpora/declare_export_changes.py          # against HEAD
```

It prints every field of `values.json` that changed, was removed or was
added, grouped by block. Every block it names goes in the hand-over,
**including the ones that are obviously fine** — whether a change is benign is
a judgement the recipient is entitled to make for themselves.

This is a step because skipping it has a specific and repeatable failure. A
hand-over in task 044e listed what had changed; the list was sincere, and it
was short by three, all of which the recipient found by diffing. The fault was
not inattention to those fields — it was a declaration with **no comparison
behind it**. A list written from memory records what the author meant to
change, and the changes that matter are the ones they did not mean. When the
comparison was finally run, it found a fourth that nobody on either side had
noticed.

> A declaration of changes is only as good as the comparison behind it.

## Confirming the hosted copy is the repository's copy

```bash
python site/teaser/check_hosted.py https://oneground.oneproof.dev
```

It fetches `data/MANIFEST.sha256`, then every file the **repository's**
manifest lists — reading the file list locally, so a host cannot choose what
gets checked — then `index.html`, `app.js` and `style.css`, which no manifest
covers. Each file gets one of three outcomes:

| outcome | meaning |
|---|---|
| `verified` | the hosted bytes are the repository's bytes |
| `contradicted` | the host served something else |
| `couldnt_check` | the host has no such file, or could not be reached |

Exit status is non-zero **only** on a contradiction. A file the host does not
have is a gap, not a disagreement, and couldn't-check is never rounded up —
before the workflow has run for the first time, every file is legitimately
absent and the command says so in as many words.

Requests are sent with `Cache-Control: no-cache`, so an intermediate cache
cannot answer on the origin's behalf and make a stale copy look verified.

---

## Caching

Pages sets its own cache headers and a CDN sits in front of them; neither is
configurable from the repository. The site is built so that this does not
matter:

- **`data/*` is content-addressed.** Every file's sha256 is in
  `data/MANIFEST.sha256`, so a stale copy is *detectable* —
  `check_hosted.py` reports it as `contradicted`.
- **Each data URL carries `?v=<first 8 hex of that file's sha256>.** The
  export writes those digests into the generated block in `app.js`, so a new
  export changes the URL and the cache has nothing stale to serve. The token
  lives in the code rather than in the data, which is what lets the four files
  still be fetched in parallel: there is no manifest to fetch first in order
  to learn it.
- **`verify_teaser_data.py` fails if the stamp and the manifest disagree**, so
  a stamp cannot go stale unnoticed — and the workflow runs that check before
  it uploads.
- **The page catches a mismatch anyway.** It checks `base.bin`'s length
  against `values.json` and recounts the closure at the reference epsilon
  before rendering; if a stale file did get through, the page refuses to draw
  and prints both numbers rather than showing a wrong picture.

`index.html` itself is served with a short cache lifetime by Pages, which is
what lets a new `app.js` stamp reach a returning reader.

---

## If you host it somewhere else

Nothing here is GitHub-specific except the workflow and the `CNAME` file. The
site is a directory of static files with no server-side anything:

- serve `site/teaser/` as the document root;
- `base.bin` wants `Content-Type: application/octet-stream`;
- let the host gzip the `.json` files;
- `data/inline.js` is only used by the `file://` path and a host that never
  serves `file://` can drop it — `verify_teaser_data.py` will then report it
  missing, which is the intended reminder rather than a failure of the page.

`check_hosted.py` takes any base URL, so it works against whatever you deploy
to.

See `site/teaser/README.md` for what the page is and how its data is produced.
