# Task T3 — Hosting: the teaser on GitHub Pages

## Expected repo state
`main` is the public single-commit branch at `27173ae`, pushed to
`github.com/shamiksaharcciit-oss/oneground`. GitHub Pages is currently
enabled from the branch root and serves the README through Jekyll at
`https://shamiksaharcciit-oss.github.io/oneground/`. `site/teaser/` is
launch-ready (T2b). Work on `main`; commit `T3:` prefixes; do not push —
the developer pushes.

## Goal
`https://oneground.oneproof.dev/` serves `site/teaser/` exactly as it is
in the repo, byte for byte, with no Jekyll processing, no external
requests, and a way for anyone to confirm the hosted copy matches the
repo. The README stays the repo's front page on GitHub; it is not the
site.

## Do
1. **Deploy by Actions, not from a branch folder.** Add
   `.github/workflows/pages.yml`: on push to `main` (and manual dispatch),
   upload `site/teaser/` as the Pages artifact and deploy it (the
   official `actions/upload-pages-artifact` + `actions/deploy-pages`,
   pinned by SHA). Add `site/teaser/.nojekyll` so nothing is processed.
   The README is no longer served by Pages after this; say so in
   `site/teaser/README.md`.
2. **Custom domain.** Add `site/teaser/CNAME` containing
   `oneground.oneproof.dev`. Document in `docs/HOSTING.md`: the DNS record
   the domain owner creates (`CNAME oneground → shamiksaharcciit-oss.github.io`,
   to be updated to the org's Pages host after the transfer), that GitHub
   provisions TLS once it resolves, and the "Enforce HTTPS" setting.
3. **Hosted-copy check.** Add `site/teaser/check_hosted.py`: fetch
   `https://<host>/data/MANIFEST.sha256` and every listed file, compare
   digests to the repo's copy, report verified / contradicted per file,
   exit non-zero on any contradiction. Also fetch `index.html`, `app.js`,
   `style.css`, `inline.js` and compare to the repo. This is the command
   the hosting brief promised: "anyone can confirm the hosted copy is the
   repo's copy."
4. **Promise block.** Set the teaser's promise section to the corrected
   text, verbatim:
       oneground 0.1.0-preview — the advisor — installable today.
       pip install oneground · characterize · simulate · verify (Qdrant) · report.
       Every number carries its receipt; every report cites the calibration
       run it was generated under.
       v0.1, 23 September: a second engine (pgvector), a second fixture where
       the ground looks different, and what the preview week teaches us.
       v0.2: the ground you just moved, and the query you just followed —
       live, on your own vectors. Dated when a witnessed run makes it true.
       Prevent · Detect · Prove · Choose.
   The install line links to `https://pypi.org/project/oneground/`; the
   "check it yourself" block links to the release. No other copy changes.
5. **Cache and headers.** Pages sets its own; document that `data/*` is
   content-addressed by MANIFEST so a stale cache is detectable by
   `check_hosted.py`, and add a `?v=<short digest>` query to the four data
   URLs in `app.js` derived from the MANIFEST at export time, so a new
   export busts the cache. Re-run `verify_teaser_data.py` after.
6. Re-measure: no external requests (the CNAME and workflow add none),
   `file://` still works, 390 px, bounds check.

## Acceptance
- Workflow validates (parse; and a dry run with `act` if available,
  else say so); `.nojekyll` and `CNAME` present.
- `check_hosted.py` runs against the current `github.io` URL after the
  developer pushes and reports the teaser's files (it will report the
  README-era files as absent until the workflow deploys — say which).
- Promise block matches the text above exactly.
- `docs/HOSTING.md` gives the domain owner one record to create and
  nothing else.

## Developer runs (after the report)
- push `main`; in repo Settings → Pages set source to **GitHub Actions**;
  enter the custom domain; after the DNS record resolves, tick Enforce
  HTTPS; run `site/teaser/check_hosted.py https://oneground.oneproof.dev`.

## Do not
- Touch anything outside `site/teaser/`, `.github/workflows/pages.yml`,
  `docs/HOSTING.md`. Change any number. Push.
