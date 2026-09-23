# 044c — the teaser change the U-shape requires

**For core, via the developer.** Nothing under `site/teaser/` has been read
for editing or changed by 044c; the digests below are so core can prove they
hold the copy this was written against before touching anything, the same gate
the promise line used.

| file | sha256 | bytes |
|---|---|---|
| `site/teaser/app.js` | `fe2eebebbb85936fa8320f69943683f991faf54e4a706171b46e45bd65c95c12` | 49,038 |
| `site/teaser/data/values.json` | `deada30f4343864b0f2e55f17bc3a8481b60e6b61825ef16cb4b839e562c8c82` | 47,502 |
| `site/teaser/README.md` | `99eb1604e04d68f895556b769e0228e4bf439dc9266275321b42913df0fecbfe` | 10,713 |
| `site/teaser/index.html` | `5e86953a61d6c3ce0b5acee132026049e0d65f7cce9dfa59e73336ec91aecc3e` | 9,479 |

If any of these differs, stop: the copy has moved and the line numbers below
are not the lines you have.

## What was measured, in one paragraph

Task 044c swept the centroid count from 16 to 4096 on arxiv-150k's published
vectors. **`boundary_crispness` is U-shaped in that count, with its minimum at
k = 512** — the published 0.036 sits one step to the left of the least-crisp
configuration in the whole range:

    k        16      32      64     128     256     512    1024    2048    4096
    crisp  0.1430  0.0461  0.0369  0.0394  0.0362  0.0347  0.0407  0.0529  0.0810
                                          published      minimum ^

At k = 2048 — well inside faiss's own floor of 39 points per centroid, so no
caveat attaches to it — the same corpus, the same vectors, the same embedding
reads **0.0529, 46% higher than the published figure**. At k = 4096 it reads
0.0810, more than double, though that point is past the library's floor and
is marked as such wherever 044c uses it.

So **0.036 is not arXiv's crispness. It is arXiv's crispness at 256 regions**,
and the count was fixed before anyone measured that fixing it mattered.

**No published value is wrong and none moves.** The fixture spec's own
definition already says *"under k-means with 256 centroids"*, and
`values.json` already carries `geometry.n_centroids: 256` and
`fixture.counts.centroids: 256`. The defect is only that the figure travels
into prose without the clause. **Nothing needs re-exporting** — every change
below is text, and the number it needs is already in the data the page loads.

## The changes

### 1. `app.js:433–439` — the ε = 0.00 caption. **The one that matters.**

Today:

```js
const crisp = values.measured.boundary_crispness;
if (s.copied === 0) {
  return 'At ε = 0.00 every vector sits within ε of exactly one region — ' +
    'one copy each, 1.000× storage, and routing to that one region finds <b>' +
    fmtPct(values.measured.one_region_recall_at_10, 1) + '</b> of true ' +
    'neighbours. The boundaries are still there: <b>' + fmtPct(1 - crisp) +
    '</b> of vectors have a second centroid inside 1.20× of the first.';
```

The last sentence is the teaser's crispness claim in prose, and it names the
ratio 1.20 while omitting the count — the number it is **more** sensitive to.
Proposed:

```js
const crisp = values.measured.boundary_crispness;
const nc = values.geometry.n_centroids;
if (s.copied === 0) {
  return 'At ε = 0.00 every vector sits within ε of exactly one region — ' +
    'one copy each, 1.000× storage, and routing to that one region finds <b>' +
    fmtPct(values.measured.one_region_recall_at_10, 1) + '</b> of true ' +
    'neighbours. The boundaries are still there: cut into <b>' + nc +
    '</b> regions, <b>' + fmtPct(1 - crisp) + '</b> of vectors have a second ' +
    'centroid inside 1.20× of the first. Both numbers are part of the ' +
    'reading: cut the same corpus into 2,048 regions instead and the crisp ' +
    'fraction is 0.053 rather than 0.036.';
```

`values.geometry.n_centroids` is already loaded; no data change.

The last sentence is the whole point of this document. A reader who is shown
*"96.4% of vectors sit near a boundary"* concludes something about arXiv. The
true statement is about arXiv **cut 256 ways**, and giving them a second
number from the same corpus is what makes the difference legible rather than
merely disclosed.

---

### 1(b) — status: **staged, waiting on task 044e**

Core accepted 1(a) — the clause naming the count — and **refused the typed
`0.053`**, correctly: it would be the first number on that page the page
cannot check, on the caption whose whole purpose is to stop a figure
travelling without what it depends on. The caption's own argument, turned on
the caption.

So the sentence is not dropped and it is not to be typed. It lands when
`values.json` carries the sweep, as **`measured.k_sweep`** — task 044e — and
reads:

```js
// measured.k_sweep, exported from the same vectors and the same seed as
// every other number on this page. Read, not stated: see task 044e.
const sw = values.measured.k_sweep;
const hi = sw.rows.find((r) => r.k === 2048);
… 'Both numbers are part of the reading: cut the same corpus into ' +
  fmtInt(hi.k) + ' regions instead and the crisp fraction is ' +
  hi.boundary_crispness.toFixed(3) + ' rather than ' + crisp.toFixed(3) + '.';
```

**Its source is `values.measured.k_sweep`, and the sentence does not ship
before that key does.** Naming the source here so the two land as one change
rather than as a caption waiting for a data file nobody connected to it.

**Of the four changes, 1(a), 2 and 3 are landed; this one is staged.**

### 2. `app.js:928–931` — the verification panel rows

Today the rows are bare metric names:

```js
['boundary_crispness', ch.boundary_crispness.value, m.boundary_crispness, ...],
['ambiguous_query_rate', ch.ambiguous_query_rate.value, ...],
['skew_top10_share', ch.skew_top10_share.value, ...],
```

This table is the page's *"recomputed here vs published"* receipt, so each row
is a claim that two numbers agree. They agree because both were computed at
256 regions, and the table does not say so. Proposed — append the count to the
three rows that are functions of it:

```js
const nc = values.geometry.n_centroids;
const rows = [
  ['boundary_crispness @ ' + nc + ' regions', ch.boundary_crispness.value, ...],
  ['ambiguous_query_rate @ ' + nc + ' regions', ch.ambiguous_query_rate.value, ...],
  ['skew_top10_share @ ' + nc + ' regions', ch.skew_top10_share.value, ...],
  ['storage_amplification', ref.storage_amplification, ...],   // unchanged
];
```

`storage_amplification` keeps its bare name: it is a function of ε and the
copy cap, not of the region count in the same way.

**`skew_top10_share` is the strongest case of the three and is easy to miss
here**, because on this page it looks like the quietest row. 044c measured
that it holds its ±0.02 tolerance at k = 256 **and at no other count tested**,
in either direction — 0.1246 at k = 128, 0.0357 at k = 512, against a
published 0.0754. It is a share of the ten largest of 256 regions, and ten of
4,096 is a different question rather than a weaker version of the same one.
The fixture specs have been updated to say so (task 044c, applied); this row
is where the same fact reaches a reader.

### 3. `README.md`, the "checks itself" paragraph around line 50

It lists what the export recomputes. One clause, so the page's own
documentation carries what the page now says:

> It recomputes `boundary_crispness`, … **at the 256 centroids named above —
> which is part of each of those three values and not a setting behind them.
> Task 044c measured the crisp fraction at 0.053 at 2,048 regions against
> 0.036 at 256 on the same vectors, and `skew_top10_share` holds its published
> tolerance at 256 alone.**

### 4. Nothing else

`index.html` needs no change. `values.json` needs no change and must not be
re-exported for this — a re-export moves every digest in
`data/MANIFEST.sha256` and every `?v=` URL, for text that the existing data
already supports.

## What this does not ask for

- **No published number changes.** 0.036, 0.891 and 0.075 all stand, at the
  same tolerances, and 044c reproduced each of them at k = 256 from the
  published vectors to the last published digit.
- **No change to the centroid count**, in the fixtures or here. 044c's report
  argues against that at length: there is no k to move to, and picking one
  because a reading looks better is choosing a parameter to make a finding
  come out.
- **No re-export, no new digests, no `?v=` churn.**

## Ours, not core's — a ruling wanted

Two strings in this repository carry the same figure without its count and are
inside our reach rather than core's. They are **not** part of this document
and have not been changed, because the skew migration did not name them:

- `corpora/render_ground.py:222` — the caption
  `"crispness 0.036 · ambiguity 0.891 · storage 3.7×"`
- `corpora/render_ground.py:16–17` — *"Build 3 measured boundary crispness
  0.036 … under k-means-256"*, which **does** name the count and is fine as it
  stands; listed so the pair is visible together.

Only line 222 needs the clause. Say the word and it is a one-line change.
