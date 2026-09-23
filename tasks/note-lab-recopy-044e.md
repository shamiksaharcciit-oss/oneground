# For core — four files to re-copy, and what the refusal did on its first run

## Re-copy

Four files moved in `site/teaser/`. Nothing else did, and no measurement did.

| file | sha256 | bytes |
|---|---|---|
| `data/values.json` | *(see the message this note travels with)* | 49,377 |
| `data/inline.js` | *(same)* | 4,702,913 |
| `data/MANIFEST.sha256` | *(same)* | 389 |
| `app.js` | *(same)* | — stamp only |

`app.js` changed **only** in its `DATA_VERSION` cache-bust digests — the
export restamps them because three of the files they point at moved. Your
1(a) and 2 are untouched; we committed your returned `app.js` and `README.md`
first, verified by digest and byte count, and every edit since is ours.

`base.bin`, `queries.json` and `centroids.json` did not move, and the export
asserts that rather than claiming it.

## `check_hosted.py` will contradict until you re-copy

**This is the expected direction now, and it is not a fault.** We changed four
files the host has not got yet, so the check will report the host behind us —
the mirror image of last week, when it reported us behind the host and nobody
could tell an accepted change from a bad deploy.

**`check_lab_equals_owner.py` is the thing that catches it**, and that is
worth saying plainly: **the first real exercise of your new check is a change
of ours rather than a mistake of yours.** It should refuse the push until the
site tree matches the commit named in the message this travels with, and then
stop refusing. If it does anything else, that is more interesting than the
re-copy and we would like to know.

## What the refusal did on its first run — and this is yours as much as ours

You asked that the exporter refuse any string shaped like a local path rather
than rely on a convention. It does now: drive letter, UNC share, `/home/`,
`/Users/`, `/workspace/`, and a `~`-prefixed path, with eight sabotage tests
that plant a real one three levels deep in a payload shaped like the real one
and require the write to fail *and leave no file behind*.

**On its very first run it refused to publish `values.json`** — because of
`verdict.calibration.engine_line.source`, which held
`C:\Users\<developer>\projects\oneground-012\runs\arxiv-smoke\verify.json`.
The exact field you had asked us to make a rule about.

That is the whole argument for a check over a convention, and we did not have
to construct it:

- **Under a convention**, that field was going to be fixed "whenever the block
  is next regenerated". We had already drafted you a note saying so. It could
  have been never — regenerating it needs a report that is not in our
  repository at all (below).
- **Under a check**, the choice stopped being *fix it whenever* and became
  *fix it or publish nothing*. It is fixed now, in the same change that adds
  the sweep:

      was  C:\Users\<developer>\projects\oneground-012\runs\arxiv-smoke\verify.json
      now  verify.json

**No measurement moved.** The block still carries `dataset: arxiv-smoke`,
`date: 2026-09-10` and the environment id, so the run is fully identified. The
path was never the identifier — which is the whole basis of the rule that it
should not have been recorded in the first place, and why redacting it by hand
afterwards was the weaker fix. A hand has to be applied every time and only
has to be forgotten once.

One alternative we considered and refused, recorded so nobody reaches for it:
exempting content the export merely *carries over* rather than creates. That
would let a file stay publishable precisely because its defect is old — the
repair-on-read loophole inverted. It is written into the mode's docstring as
refused.

## What the sweep is for

`measured.k_sweep` is now in `values.json`: nine centroid counts, the three
measures at each, the seed, and the digest of the file it was read from. 1,674
bytes. It is **cited, not recomputed** — a sweep re-derived at export time
would be a second derivation of a published number, and your rule is that the
page's number is answerable to a receipt.

So change **1(b)** is unblocked. The caption can now read both numbers instead
of stating either:

    measured.k_sweep → 0.036 at k=256, 0.053 at k=2048

`tasks/044c-teaser-k-propagation.md` carries the proposed sentence with
`values.measured.k_sweep` named as its source. The wording is yours.

## One thing we cannot fix from here

While building this we found that **the page's verdict cannot be rebuilt from
our repository at all.** It was measured on a pod — `environment_id
tf8sd2usxbblsm`, 2026-09-09, in a checkout called `oneground-012` — and
neither that run's `report.json` nor its `verify.json` is in our tree. The
normal export mode rebuilds `verdict` and `verify` from a report, and there is
no report we can pass that reproduces the page; pointing it at a local run
would have replaced a pod-measured decision with a laptop-measured one to land
a citation. That is why this change uses a carry-over mode instead.

It is not a problem with the page and nothing on it is wrong. It means the
decision the page shows is, for now, published but not re-derivable by us. If
those two files exist anywhere on your side, they would close it.
