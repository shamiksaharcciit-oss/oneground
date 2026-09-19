# Task 039 — The nprobe sweep: is the IVF divergence the cell structure?

## Setup
Branch `task-039` from `main`. Commit `task 039:` and push after every
commit. No pod: both 150k corpora are on the laptop and the sweep runs
there, in the background, in about six hours.

## Why

Task 034 measured that the two published corpora **agree about
quantisation and disagree about IVF**, at one operating point each:

| family | arxiv index loss | stackexchange index loss |
|---|---|---|
| single_node ivf | 0.1431 | 0.2414 |
| hash ivf | 0.0603 | 0.1552 |
| semantic ivf | 0.1882 | 0.2138 |

| family | arxiv hnsw→ivf_pq | stackexchange hnsw→ivf_pq | apart |
|---|---|---|---|
| single_node | −0.7096 | −0.7166 | 0.0070 |
| hash | −0.7523 | −0.7493 | 0.0030 |
| semantic | −0.5000 | −0.4808 | 0.0192 |

034 offered an explanation and **marked it a hypothesis**, because
nothing in that run tested it:

> the coarse quantiser's cell structure is corpus-dependent in a way the
> product quantiser's additional loss is not, because the PQ error is
> large enough on both corpora to swamp the difference between them.

Every IVF row there was `nprobe=8` of `nlist=1024` — 0.8% of the cells.
One point is not a curve, and a gap measured at one point cannot say
whether it is a property of the corpora or of that point.

## The prediction, stated before the run

**If the hypothesis holds:**

1. The two corpora's **IVF** curves **converge as `nprobe` rises**. More
   cells probed means less of the cell structure matters, so the gap
   narrows monotonically and is small by `nprobe=64`. Concretely: the
   single_node IVF gap of 0.098 at `nprobe=8` should be **under 0.03 at
   `nprobe=64`**.
2. The two corpora's **IVF-PQ** gap **stays roughly flat in `nprobe`** —
   within about 0.02 across the whole range — because the PQ error does
   not depend on how many cells were read.
3. Both corpora's IVF recall rises monotonically with `nprobe` and
   approaches their flat/HNSW recall at the top of the range.

**If the hypothesis is wrong**, the most likely shapes are:

- the IVF gap is **flat** in `nprobe` — then the divergence is not the
  cell structure but something that does not wash out with more probing,
  and the explanation in 034 is withdrawn;
- the IVF gap **widens** — then something about stackexchange makes more
  probing help less, which nobody here has a story for;
- the IVF-PQ gap **also converges** — then the two effects are the same
  effect at different magnitudes, not two effects.

**Rule: if the curves do something neither of these anticipates, that is
the finding and it is reported as one.** No explanation is to be
constructed after the fact and presented as though it had been tested.
An unexplained shape is a result; a story fitted to it afterwards is not.

## Do

1. **The sweep.** On both published fixtures, at the partition each
   family publishes:

   ```yaml
   grid:
     <family>:
       index: [ivf, ivf_pq]
       nprobe: [1, 2, 4, 8, 16, 32, 64]
   ```

   with `nlist`, `m` and `nbits` at 034's values so the new rows are
   comparable with the old ones, and the families' own partition
   parameters unchanged. 034's `flat` and `hnsw` rows are the reference
   points and are **not** re-measured — they are in
   `runs/034-index-{arxiv,stackexchange}-150k/simulate.json` and are
   cited from there.

2. **Report the curves**, not only the endpoints: recall@10 and index
   loss against `nprobe`, per corpus, per family, per algorithm, with
   the gap between corpora as its own column.

3. **Answer the three predictions explicitly**, each with the number
   that settles it and the word held / did not hold. A prediction that
   did not hold is the more useful outcome and is reported first.

4. **Routing loss stays a check, not a finding.** It must be identical
   across every row of a family on a corpus, as it was in 034 — the
   partition does not change with `nprobe`. If it moves, that is a
   defect in the decomposition and the sweep stops.

5. **Cost.** About six hours across both corpora. Run it in the
   background and report the measured elapsed time, per corpus. If the
   budget trips, report which configurations were not measured — 034
   made that a drop rather than an abort.

## What this may not say

- That one algorithm is better than another, or one corpus better than
  another. Two corpora differing is a fact about the corpora.
- That a result at `nlist=1024`, `m=16`, `nbits=8` holds at other
  values. This sweeps one axis and says so.
- That the mechanism is the cell structure, unless the prediction held.
  "Consistent with" is not "tested"; 034's whole point was the
  difference.

## Acceptance
- The prediction above is in this file before the run starts, and the
  file is committed before the first row is measured.
- Both corpora swept over the seven `nprobe` values for both algorithms.
- The three predictions answered, each with its number.
- Routing loss identical within each family on each corpus.
- Whatever the curves did, stated as measured — including if it is
  neither the hypothesis nor any of the three anticipated failures.

## Do not
- Explain an unexpected shape and present the explanation as a result.
- Re-measure 034's `flat` or `hnsw` rows; cite them.
- Change `nlist`, `m` or `nbits` to make a curve look cleaner.
