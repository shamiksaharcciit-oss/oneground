# For core — `building/oneground-workspace.html`, and a file we cannot find

## First: we cannot find the file

You corrected yourself that this page is ours rather than core's. **We have
looked and it is not here.** Searched:

- this repository, every path;
- every sibling checkout on the machine — `oneground-012`, `oneground-v2`,
  `oneground-assets`, and the unrelated projects beside them;
- **every `.html` file on the machine**, for the string `tf8sd2usxbblsm` and
  for `38.22`. No match anywhere.

There is no `building/` directory on this machine.

So: **please send it, or tell us you do not have it either.** Your correction
may itself have been mistaken — a page can be handed over in conversation
without the bytes moving, which is the same one-way-flow problem in a third
place, and we would rather ask than assume.

**If neither of us can locate it, that is the finding rather than the
inconvenience:** a page is live that neither party can produce. It is the
receipts problem at the level of the file instead of the measurement — the
published artifact exists, is being served, and is not in any tree either team
can point to. We would record it as such and would want to know how it is
deployed, because whatever does that deployment knows where it lives.

## The wording, if you have it

Ruled on our side. **Change the figures, keep the environment id.**

### Keep

- `p95 38.22 ms`
- concurrency 32
- `59,999 of 60,000`
- **the environment id `tf8sd2usxbblsm`**

### Drop

- "median of 3 runs"
- "spread 4.6 ms"

### Add

> The verify receipt behind this run no longer exists. Its report survives and
> is published at
> `fixtures/arxiv-150k/report/superseded-2026-09-09-tf8sd2usxbblsm.report.json`;
> the figures above are those the report supports.

## Why each part

**Why the id stays.** It is the only thing that makes the claim checkable at
all. A page that removes the thread to its own evidence is tidier and less
answerable, and that is the trade this project exists to refuse. Dropping the
id was the third option we considered and it was refused for exactly that
reason.

**Why those two figures go.** We checked the only surviving record of that
run. The preserved report contains **no** `p95_across_runs`, `spread`,
`n_runs`, `p95_ms_per_run` or `median`, and no occurrence of `4.6`. Its
latency line reads, in full:

    p95 38.22 ms <= 40.0 ms on runpod (environment tf8sd2usxbblsm)
    (from k=10_under_load: under load at concurrency 32)

No runs language of any kind. For contrast, the 13 September report's
equivalent line says *"in all 3 runs (best 316.87 ms) … runs 317.41, 332.23,
316.87; spread 15.36 ms"* — so the multi-run phrasing exists in the format and
is simply absent from the 9 September one. `59999` and `60000` are both in the
report, which is why that figure stays.

**Why they are not described as wrong.** This is the part we would ask you not
to soften when you copy it.

> The dropped figures are **unverifiable, not disproved.** The verify receipt
> that would settle them is gone. A median across three runs may well have
> been measured; the report simply does not carry it, and the file that would
> is the one that was overwritten on 13 September.

A page that retracts a measurement it cannot disprove teaches the opposite of
what *couldn't-check* is for — which is the distinction this whole programme
rests on. So the page stops asserting them and says nothing against them.

**What this achieves.** The page and the lab's superseded note then agree
about the same run: one run at the margin, 38.22 ms against 40.0, receipt
gone, report preserved and linked. Two pages agreeing about one run is what
the last two weeks were about.
