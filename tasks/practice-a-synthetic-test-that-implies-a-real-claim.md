# For `docs/PRACTICE.md` §2 — warning 8

*From task 044c, for the interface stream to place. §2 is "Checks that do not
check" and its warnings are numbered 1–7; this is the eighth and it belongs
there rather than in a section of its own. What it cost is at the bottom, per
the page's constraint.*

---

**8. A test that passes on synthetic data and would imply a claim only real
data supports.** This project already names synthetic tests — 550 of them end
in `_synthetic`, and `docs/CLAIMS.md` treats the suffix as the disclosure. The
suffix says *the data is made up*. It does not say **which of the things the
test appears to establish the made-up data cannot establish**, and those are
different facts.

The dangerous shape is a test whose synthetic case **passes for a reason that
does not generalise**, sitting next to prose or a function name asserting the
general thing. Nothing fails. The suffix is present. A later reader — or a
later task's report — cites the test as the evidence for the general claim,
and the citation is the first time anyone treats the synthetic result as
though it were the real one.

**The instance.** Task 044c established that `skew_top10_share` is not
comparable across centroid counts, and refuted the obvious rescaling: dividing
by the uniform baseline `10/k` does **not** make two counts comparable, which
was measured on real corpora — on `arxiv-150k` that ratio climbs 1.19 to 3.10
as k goes 16 to 4096.

The test written for it constructs two *perfectly even* synthetic partitions,
at k=64 and k=256. Under an even partition the rescaling works exactly:
`excess_over_uniform` is 1.0 for both. **So the synthetic fixture demonstrates
the opposite of the finding**, for the sound reason that real corpora are not
evenly partitioned and synthetic ones can be made so.

Had the test simply asserted the reading refuses the comparison, it would have
passed, carried its `_synthetic` suffix honestly, and been available to cite
as *"the rescaling was tested"* — for a refutation it contains no evidence of.

**The repair, and it is the part worth copying: make the test say so in
itself.** It now asserts *both* — that `excess_over_uniform == 1.0` for both
synthetic partitions, i.e. that the rescaling **does** work here, and that the
reading still refuses the comparison — with a docstring naming the real
measurement as the evidence and this test as not it. The assertion that the
rescaling works is the disclosure, and it is an assertion rather than a
comment, so it breaks if someone later makes the synthetic data uneven and
quietly turns the test into the thing it was careful not to be.

> **The rule: a synthetic test that would be read as supporting a claim only
> real data supports must assert the limitation, not merely disclose it in a
> name.** Name the real measurement that is the evidence, in the test. A
> comment saying "synthetic" is removed by the next person who needs the test
> to pass; an assertion that the synthetic case behaves the other way cannot
> be.

**The tell.** Ask of a passing synthetic test: *if the real data behaved the
opposite way, would this still pass?* If yes, the test is not evidence for the
real behaviour and must say which part of itself is not evidence. §2's
recurring theme is a check reporting something other than what it appears to
report; this is the version where what it reports is **true**, and the
inference a reader draws from it is not.

**What it cost.** Nothing, this time — the test was written this way the first
time and the trap was seen while writing it, not after. It is recorded because
the page is a catalogue of ways to be wrong and this one was avoided by
accident of attention rather than by a rule, which means the next one will not
be. It is also the cheapest entry here: every other warning was paid for with
a false result on a shipped artifact.

---

## On whether this qualifies for the page — yours to rule

Offered with its own weakness stated: under a strict reading of *"nothing goes
in it that has not cost something"*, a trap caught while writing does not
qualify and should be dropped.

**The developer's inclination, on being shown that, is that it belongs**, and
the argument is worth recording whichever way you rule:

> A trap caught while writing rather than after a false result is **cheaper
> evidence, not absent evidence**. And a page that only admits defects which
> shipped will teach people to wait until one does.

That second clause is the substantive point, and it is about the page rather
than about this entry: a bar set at *it must have caused visible damage*
prices near-misses out, and near-misses are the cheapest kind of evidence a
project ever gets. The constraint exists to keep out speculation, not to keep
out things that were nearly wrong.

**The page is yours and the ruling is yours.** If it goes in, the price above
should stay in it, stated as plainly as it is — an entry that overstates what
it cost would undermine the constraint more than an entry that cost little.
