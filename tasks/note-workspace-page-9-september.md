# For core — `building/oneground-workspace.html`: the panel is a composite

**This supersedes the wording we sent you earlier. Do not apply that version.**
It treated the panel as one run with two unverifiable extras. Your addendum
shows it is a composite of two runs and one figure from neither, under a
single environment id, with a header naming a third corpus. That is a
different problem and it needs different wording.

We traced every figure against our own artifacts rather than relaying yours.
**Your trace holds on every point we can check:**

| figure | where it is actually from |
|---|---|
| p95 38.22 ms, concurrency 32 | the 9 September run — its report's only latency line |
| 59,999 of 60,000 | the 9 September run |
| **ceiling 381.2** | **13 September, `1ombs4scr257a5`** — that run's qdrant `qps_max` is 381.25. The string `381.2` does not occur anywhere in the 9 September report |
| **round-trip share 18.3%** | **no receipt.** `18.3`, `0.183` and `rtt_share` are all absent from the 9 September report. The only measured share for that engine is **60%**, on 13 September |
| header: support-tickets-2026q3, 20,000 vectors | a corpus that never had a verify run. The figures are arxiv-150k at 150,000 |

## What to change

### 1. The id covers two figures and no others

Keep `tf8sd2usxbblsm` over **p95 38.22 ms at concurrency 32** and **59,999 of
60,000**, and nothing else. Those are what that run carries.

### 2. The ceiling moves or goes

**381.2 is 13 September's.** Either attribute it — *"381.2 queries per second,
environment `1ombs4scr257a5`, 13 September"* — or drop it. **Do not leave it
under the 9 September id.** A figure under the wrong id is worse than a figure
with no id: the id is what invites the reader to check, and here checking
leads to a run that does not contain it.

### 3. The 18.3% and its conclusion are withdrawn — and this is not the same
case as the median

We asked you to keep the median as unverifiable rather than wrong. **This one
is different and the wording must not be borrowed from it.**

- The median is **unverifiable**: no receipt settles it either way.
- The 18.3% is **contradicted**: no receipt carries it, *and* the one measured
  round-trip share for that engine is 60% — which is why that run could not be
  latency-checked at all.

So the page should say, in substance:

> No receipt carries the 18.3% round-trip share. The only measured round-trip
> share for this engine is 60%, on the later run, which is why that run's
> latency could not be attributed. The sentence "under the 20% limit, so this
> figure describes the engine" is withdrawn.

**Why that sentence in particular has to go, and not merely be softened.** It
is our own attribution rule run backwards. The rule exists to *refuse* a
latency number when the round trip is too large a share of it. Used this way
it asserts that a number is trustworthy on the strength of an input nothing
records — a conclusion drawn from a measurement that does not exist. That is
worse than an unsupported figure, because an unsupported figure is silent
about its own standing and this one vouches for itself.

### 4. The header names the corpus the numbers came from

Either the header says **arxiv-150k, 150,000 vectors**, or the page says
plainly that the figures are from a different corpus than the one it
describes. A panel headed with one corpus and filled with another's numbers is
not a labelling slip; it is the reader being told what they are looking at,
incorrectly.

## The test, which is yours

> **A number wants a receipt, and this panel is where that test applies.**

That is your line and we are sending it back because it is the whole of it.
Four figures, one id, and only two of them belong to it. Nothing here was
measured wrongly — every number was measured by somebody, somewhere. What
failed is that they were assembled onto one panel and the assembly was never
answerable to anything.

## Still: we cannot find the file

Unchanged from our previous note. Not in this repository, not in any sibling
checkout, and no `.html` anywhere on this machine contains `tf8sd2usxbblsm` or
`38.22`. There is no `building/` directory here.

**If neither of us can locate it, that is a finding rather than an
inconvenience** — a page is live that neither party can produce, which is the
receipts problem at the level of the file rather than the measurement. The
next question is what deploys it, because whatever does knows where it lives.
We would rather ask than assume, so: please send it, or tell us you do not
hold it either.
