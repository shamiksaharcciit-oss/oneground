# Report: 038b-teaser-promise

## Repo state expected vs found

Expected the teaser's one stale promise, found exactly one occurrence:
`site/teaser/index.html`, the `v0.1, 23 September:` line in the promise
section. Expected `site/teaser/` to be ours; confirmed, and confirmed we hold
no copy of the two pages core owns.

## What was done

One line, one file. The version and the date were removed and the release
model put in their place; the three items behind the colon are untouched.

```
-  <p class="later">v0.1, 23 September: pgvector as a second engine, …
+  <p class="later">Next, undated — it ships when it is ready and tested:
                    pgvector as a second engine, …
```

`git diff --numstat` is `1 1`. The next paragraph's `v0.2: … Dated when a
witnessed run makes it true.` is deliberately untouched: it is the house
formula, it is still true, and with the stale line gone the two read as
distinct rather than as one repeated.

No date and no version appears in the new line — scanned for `23 September`,
`September`, `v0.1`, `0.1.0` and `2026`.

## Measurements

### Provenance: is the copy we hold the copy that is published?

Core's rule, adopted here: **before editing a published file, prove the copy
you hold is the one that is published.** Core nearly deleted five of their
own corrections by editing a stale working tree.

`check_hosted.py https://oneproof.dev/oneground/lab`, run against the
**pre-edit** tree (extracted from the commit before the edit, because the
tool compares the host to the repository copy and ours was already changed —
running it from the live tree would have contradicted on `index.html` by
construction and proved nothing):

```
9 verified · 0 contradicted · 0 couldn't-check
The hosted copy is this repository's copy.

  data/MANIFEST.sha256   base.bin   centroids.json   queries.json
  values.json   inline.js   index.html   app.js   style.css
```

`index.html` there digests to `a4aa05b2…`, the value recorded before the
edit. **The copy edited was the published copy.**

*Honestly: this ran after the edit, not before.* The rule reached this task
mid-flight. Had it contradicted, the merge — unpushed at that point — would
have been reverted.

### The changed file

```
site/teaser/index.html
  bytes   9443 → 9479
  sha256  a4aa05b2349d0e80bffd19aba7cea71b7f129b5c3649f90ffeb11170de0bc943
       →  5e86953a61d6c3ce0b5acee132026049e0d65f7cce9dfa59e73336ec91aecc3e
```

`app.js` (49,038 bytes, `fe2eebeb…`) and `style.css` (20,975 bytes,
`6517d6b8…`) are byte-identical and were not touched.

### No published figure moved

All five `data/` digests match `MANIFEST.sha256`: `base.bin`,
`centroids.json`, `inline.js`, `queries.json`, `values.json`.

`verify_teaser_data.py`: **ALL CHECKS PASSED**. Load size 4.59 MB over http,
4.78 MB from `file://` — under 5 MB either way.

## Verification

**Layout, at two of five viewports: verified.** The developer opened the
edited page in a browser at **1200 px and 500 px**. At 500 the changed line
wraps across four lines, sits clear of the paragraph below it, and nothing
runs past the right edge; the `v0.2` line, the house formula and the footer
all flow normally.

**The other three viewports: couldn't-check.** The automated check at all
five, `tasks/scratch/T1-bounds.js`, drives headless Chrome over the DevTools
protocol and needs node and Chrome; this machine has neither. Not worked
around, and not rounded up.

    W=<width> H=<height> node tasks/scratch/T1-bounds.js <url>

What lowers the risk rather than removing it: T1's own fix was `min-height`,
never `height`, so a section that needs more room grows instead of spilling
into the one below. The new line is 40 characters longer — at most one
wrapped line at the narrowest viewport, which is what the developer observed
at 500.

**Suite**: 1237 passed, 5 skipped, 1 deselected on the merged tree.
**Identifier scan**: ran, 0 findings.

## Observed, not done

- `check_hosted.py`'s usage lines name two older hosts and not
  `https://oneproof.dev/oneground/lab`, which is where our copy is actually
  served. Not changed: it is core's deploy path and the file is published.

## Repo now contains

- `site/teaser/index.html` — one line changed
- `tasks/038b-teaser-promise.report.md` — this file

## Blocked on developer

- The bounds check at the other three viewports, on a machine with node and
  Chrome, before the file goes to core.
