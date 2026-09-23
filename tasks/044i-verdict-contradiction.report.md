# Report: 044i-verdict-contradiction

## Closed

Core deployed `7f1ddc3`: **`check_lab_equals_owner` EQUAL across 14 files**,
the door-vs-lab consistency row passed, `check_hosted` 9 verified. **The
contradiction is off the public site.** This closes 044e, 044i and the
k-propagation thread that began in 044c.

What the site said for thirteen days, and says now:

| | before | after |
|---|---|---|
| lab verdict | 1 meets · 6 fails · 1 couldn't-check — **one recommended** | 0 meets · 6 fails · 2 couldn't-check — **nothing recommended** |
| built from | `tf8sd2usxbblsm`, 9 Sept, receipts gone | `1ombs4scr257a5`, 13 Sept, receipts committed |
| home page | nothing recommended | unchanged, and now agreed with |
| rebuildable from our tree | no | **yes** |

## The leading finding: it was impossible, not undone

**`build_verify` never learned task 015's multi-engine shape.** It expected a
single-engine `searches` block; a two-engine verify carries `engines`, a list.
Handed one, it died on the first line that touched it.

So re-exporting the page **could not be done** at any point after 015. The
stale verdict did not survive through an omission — it survived because the
only mechanism that could have replaced it was broken, and nothing noticed
because nothing tried.

> **The generalisation is the value: every export path should be asked when it
> was last exercised, not assumed to work.** A path that is never run is
> indistinguishable from one that works, right up until the day it is needed,
> which is the day something is wrong.

## The contradiction, and why it was the serious kind

One click apart, on the same fixture, the site published opposite verdicts,
and **nothing told a reader they were two runs**. Neither number was false —
each is what its run measured. That is what made it the failure this product
exists to prevent, occurring on our own page.

The 9 September "meets" was 38.22 ms against 40.0: **1.8 ms, on one run.** The
same configuration measured again on 13 September fails on pgvector in all
three runs (316.87, 317.41, 332.23 ms) and cannot be judged on qdrant at all,
the baseline round-trip being 60% of the query p95.

The older run is kept visible, not deleted. A page that silently replaces one
decision with another teaches a reader that decisions are opinions — and a
measurement that met a threshold by 1.8 ms on one run is not a result that
turned out to be wrong, it is one that was never separable from its margin.

## Both engines, named, neither chosen

Ruled, and the data made the case better than the argument did. qdrant's
under-load latency is a couldn't-check **string**; pgvector's is numbers. One
engine has a reason and the other has a result, and collapsing them to "no
data" would have lost exactly what a couldn't-check is for. Both are
normalised to `{outcome, …}` so a renderer reads one key rather than
type-testing a union.

Outcomes are copied from the report, not re-derived, and taken from the option
the verify run actually built — otherwise the first option wins and every row
reads *"this configuration was not the one verified"*, which is true and not
what the panel is about.

## Measured-when against recorded-when: one conflation, twice, in one task

**The finding worth carrying, because the second instance proves the first was
not a coding slip.**

1. **In code.** `geometry_from.generated_at` took the *previous run's* stamp.
   A timestamp that takes the previous value does not go stale — **it walks
   backwards**, and the tell is that it looks plausible at every step. Found
   by exporting twice and diffing, not by reading.
2. **In prose.** The superseded note said the page showed a different verdict
   *"until 2026-09-20"* and that the re-measurement happened *"on
   2026-09-20"*. The measurement was **13 September**; 20 September is when
   the report was built from it. Written on the note whose entire subject is
   exactness, by the author who had fixed instance 1 an hour earlier.

Core's replacement wording is kept because it **cannot go stale**: *"Until the
page was re-exported from the report of 2026-09-20…"* is true whatever day the
deploy lands, so the note never has to know one. `measured_on` and
`report_built_on` are now fields as well as prose.

My own report-only runs pushed `geometry_from` further from the truth before I
fixed the chase, and **that loss is unrecoverable**: when something was made is
the one thing an artifact cannot re-derive from itself.

## The process change that outlasts the task

Core found three undeclared changes in the 044e hand-over. **That was not
inattention to three fields — it was a declaration with no comparison behind
it.** A list written from memory records what the author *meant* to change,
and the changes that matter are the ones they did not mean.

Computing it found a **fourth** nobody on either side had seen:
`verdict.calibration.family_line` absent, 110 fields, because the rebuilt
report carries no glove calibration line.

> **A declaration of changes is only as good as the comparison behind it.**

`corpora/declare_export_changes.py` is now a documented step in
`docs/HOSTING.md`, placed immediately before the hosted-copy check so it is
met in the order it is used. Its instruction: every block it names goes in the
hand-over, **including the obviously fine ones** — whether a change is benign
is the recipient's judgement to make.

It earned itself immediately: the date fix was reported as *2 changed, 0
removed, 2 added*, which is how I knew substituting `--report-only` for the
ruled `--cite-only` was safe rather than merely believing it.

## Two corrections inside this task

**The first `.gitignore` narrowing was wrong.** Committing the 110
newly-trackable files put **95+ machine identifiers** into the tracked tree —
those receipts predate 044g's path fix. The identifier scan failed and the
commit was undone before pushing. That is the guard working, not a trap, and
it is why the rule is now forward-looking: new receipts are clean at their
write site and are kept; a historical receipt a page cites takes the curated
route into `fixtures/<id>/report/`.

**The preserved receipt has the one allowlist entry it needs**, stating that
its absolute paths are *fact about that run* and that rewriting them to
satisfy a scan would falsify a receipt — the one repair this project must
never make.

**The price_table full stop was ours.** `public_sources` transformed every key
*named* `source`; `price_table.source` is prose; `public_path` resolved the
sentence as a repo-relative path and `normpath` ate the trailing `.` as a path
component. Keyed on `LOCAL_PATH` now, so exactly what the refusal would reject
is transformed. Written up as
`tasks/practice-match-the-shape-not-the-name.md`.

## The receipts are gone, confirmed independently

`tasks/scratch/T2b-report-before.json` **is** that run's `report.json` — same
id, same 6/1/1 summary, `p95 38.22 ms <= 40.0 ms` at the cited line. So the
receipts were **mislabelled rather than lost**: the report survives, the
verify receipt does not. Preserved as
`fixtures/arxiv-150k/report/superseded-2026-09-09-tf8sd2usxbblsm.report.json`.

`C:\Users\<HOME>\projects\oneground-012\` — the checkout the published path
named — **still exists and is empty.** Nothing to recover.

## Measurements

| | |
|---|---|
| days the contradiction was live | 13 |
| fields changed in the rebuild | 799 (changed + removed + added) |
| fields changed by the date fix | 4, of which 2 are the note and its stamp |
| newly trackable under the narrowed rule | 110 files, **0.8 MB — the whole cost of making every decision in this repository re-derivable** |
| machine identifiers the first narrowing would have committed | 95+ |
| files core's equality check named | 14 EQUAL; 5 changed by us, one more than our list |
| suite | 1545 passed, 40 skipped, 1 failed (known stale artifact) |

## Observed, not done

1. **A page is live that neither party can locate** — and this is a finding
   beside the receipts one, not an inconvenience. `building/
   oneground-workspace.html` repeats the 9 September figures. Core said it was
   theirs, then corrected that it is ours. It is **not in this repository, not
   in any sibling checkout on this machine, and no `.html` file anywhere on
   the machine contains `tf8sd2usxbblsm` or `38.22`.** There is no `building/`
   directory here.

   It is the receipts problem one level up: **the published artifact exists,
   is being served, and is in no tree either team can point to.** The
   measurement case was a number whose evidence was gone; this is a *file*
   whose source is gone, while the file itself is still being deployed by
   something that must know where it lives.

   Asked of core in `tasks/note-workspace-page-9-september.md`, with the ruled
   wording attached so it can be applied the moment it is found. If they do
   not hold it either, the next question is what deploys it.
2. **044j** carries core's two workflow guards, the copy-cited-runs route and
   `source_sha256` on the verdict.
3. **The `.gitignore` sentence to quote if anyone proposes widening it again:**
   110 files and 0.8 MB is the whole cost of making every decision in this
   repository re-derivable.
